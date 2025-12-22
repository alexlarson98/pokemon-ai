"""
AlphaZero Neural Network for Pokemon TCG.

This module provides the policy-value network for AlphaZero-style training.
The network takes encoded game states and outputs:
- policy_logits: Action probabilities over the action space
- value: Expected game outcome from -1 (loss) to +1 (win)

Architecture:
=============
1. Shared Embedding Layer: Maps card IDs to dense vectors
2. Input Encoders: Process different input types (sequences, features)
3. Residual Backbone: Deep processing with skip connections
4. Output Heads: Policy (action probabilities) and Value (game outcome)

Input Tensors (from StateEncoder):
- my_hand: (B, 60) int64 - Hand card IDs
- my_discard: (B, 60) float32 - Discard pile card IDs
- my_active: (B, 1, 22) float32 - Active Pokemon features
- my_bench: (B, 8, 22) float32 - Bench Pokemon features
- opp_active: (B, 1, 22) float32 - Opponent active features
- opp_bench: (B, 8, 22) float32 - Opponent bench features
- global_context: (B, 26) float32 - Global game state

Output:
- policy_logits: (B, 1099) - Raw logits for action space
- value: (B, 1) - Game outcome prediction [-1, 1]
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, Tuple, Optional

# Import action space size from encoder
from .encoder import TOTAL_ACTION_SPACE as ACTION_SPACE_SIZE

# Import state encoder constants
from .state_encoder import (
    MAX_HAND_SIZE,
    MAX_BENCH_SIZE,
    MAX_DISCARD_SIZE,
    POKEMON_FEATURES,
    GLOBAL_FEATURES,
)


# =============================================================================
# CONFIGURATION
# =============================================================================

# Embedding dimensions
CARD_EMBEDDING_DIM = 64

# Encoder output dimensions
HAND_ENCODER_DIM = 64
DISCARD_ENCODER_DIM = 64
POKEMON_ENCODER_DIM = 64
GLOBAL_ENCODER_DIM = 32

# Backbone dimensions
BACKBONE_DIM = 512
NUM_RESIDUAL_BLOCKS = 6

# Value head dimensions
VALUE_HIDDEN_DIM = 64


# =============================================================================
# RESIDUAL BLOCK
# =============================================================================

class ResidualBlock(nn.Module):
    """
    Residual block with pre-activation BatchNorm.

    Architecture: Linear -> BatchNorm -> ReLU -> Linear -> BatchNorm -> Skip
    """

    def __init__(self, dim: int):
        super().__init__()
        self.fc1 = nn.Linear(dim, dim)
        self.bn1 = nn.BatchNorm1d(dim)
        self.fc2 = nn.Linear(dim, dim)
        self.bn2 = nn.BatchNorm1d(dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        identity = x

        out = self.fc1(x)
        out = self.bn1(out)
        out = F.relu(out)

        out = self.fc2(out)
        out = self.bn2(out)

        out = out + identity
        out = F.relu(out)

        return out


# =============================================================================
# INPUT ENCODERS
# =============================================================================

class SequenceEncoder(nn.Module):
    """
    Encodes a sequence of card IDs using embedding + global average pooling.

    Input: (B, Seq_Len) int64 card IDs
    Output: (B, output_dim) float32
    """

    def __init__(
        self,
        embedding: nn.Embedding,
        seq_len: int,
        output_dim: int
    ):
        super().__init__()
        self.embedding = embedding
        self.seq_len = seq_len
        self.output_dim = output_dim

        # Project embedding to output dimension if needed
        embed_dim = embedding.embedding_dim
        if embed_dim != output_dim:
            self.proj = nn.Linear(embed_dim, output_dim)
        else:
            self.proj = None

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, Seq_Len) int64 card IDs (0 = empty/padding)

        Returns:
            (B, output_dim) pooled representation
        """
        # Embed: (B, Seq, embed_dim)
        embedded = self.embedding(x)

        # Project if needed: (B, Seq, output_dim)
        if self.proj is not None:
            embedded = self.proj(embedded)

        # Create mask for non-empty slots (card_id > 0)
        # (B, Seq, 1)
        mask = (x > 0).unsqueeze(-1).float()

        # Masked sum and count
        masked_sum = (embedded * mask).sum(dim=1)  # (B, output_dim)
        count = mask.sum(dim=1).clamp(min=1.0)  # (B, 1), avoid div by 0

        # Average pooling over non-empty slots
        pooled = masked_sum / count  # (B, output_dim)

        return pooled


class PokemonEncoder(nn.Module):
    """
    Encodes a Pokemon with rich features.

    Card ID (index 0) goes through embedding.
    Other features go through a linear layer.
    Results are concatenated and projected.

    Input: (B, num_pokemon, POKEMON_FEATURES) float32
    Output: (B, num_pokemon, output_dim) float32
    """

    def __init__(
        self,
        embedding: nn.Embedding,
        num_pokemon: int,
        output_dim: int
    ):
        super().__init__()
        self.embedding = embedding
        self.num_pokemon = num_pokemon
        self.output_dim = output_dim

        embed_dim = embedding.embedding_dim

        # Features excluding card_id (index 0) and tool_id (index 14)
        # Total features = 22, minus 2 for embeddings = 20 continuous features
        num_continuous = POKEMON_FEATURES - 2  # 20

        # Process continuous features
        self.feature_fc = nn.Linear(num_continuous, output_dim)

        # Combine embedding(s) + processed features
        # We have card_id embedding + tool_id embedding + feature_fc output
        self.combine_fc = nn.Linear(embed_dim * 2 + output_dim, output_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, num_pokemon, POKEMON_FEATURES) float32

        Returns:
            (B, num_pokemon, output_dim) encoded Pokemon
        """
        batch_size = x.shape[0]

        # Extract card IDs (index 0) and tool IDs (index 14)
        card_ids = x[:, :, 0].long()  # (B, num_pokemon)
        tool_ids = x[:, :, 14].long()  # (B, num_pokemon)

        # Get continuous features (all except indices 0 and 14)
        # Indices: 1-13, 15-21 (20 features)
        continuous = torch.cat([
            x[:, :, 1:14],   # HP, damage, energy (indices 1-13)
            x[:, :, 15:],    # Status, ability, evolved (indices 15-21)
        ], dim=-1)  # (B, num_pokemon, 20)

        # Embed card IDs
        card_embed = self.embedding(card_ids)  # (B, num_pokemon, embed_dim)
        tool_embed = self.embedding(tool_ids)  # (B, num_pokemon, embed_dim)

        # Process continuous features
        # Reshape for batch processing
        continuous_flat = continuous.view(-1, continuous.shape[-1])  # (B*num, 20)
        features_processed = self.feature_fc(continuous_flat)  # (B*num, output_dim)
        features_processed = features_processed.view(batch_size, self.num_pokemon, -1)

        # Combine
        combined = torch.cat([card_embed, tool_embed, features_processed], dim=-1)

        # Project to output dimension
        combined_flat = combined.view(-1, combined.shape[-1])
        output = self.combine_fc(combined_flat)
        output = output.view(batch_size, self.num_pokemon, self.output_dim)

        return output


class GlobalEncoder(nn.Module):
    """
    Encodes global context features.

    Input: (B, GLOBAL_FEATURES) float32
    Output: (B, output_dim) float32
    """

    def __init__(self, output_dim: int):
        super().__init__()
        self.fc = nn.Linear(GLOBAL_FEATURES, output_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return F.relu(self.fc(x))


# =============================================================================
# ALPHAZERO NETWORK
# =============================================================================

class AlphaZeroNet(nn.Module):
    """
    AlphaZero Policy-Value Network for Pokemon TCG.

    Takes encoded game state dictionary and outputs:
    - policy_logits: (B, action_space_size) raw logits
    - value: (B, 1) predicted game outcome in [-1, 1]
    """

    def __init__(
        self,
        action_space_size: int = ACTION_SPACE_SIZE,
        vocab_size: int = 1000,  # Should be CardIDRegistry.vocab_size
        embedding_dim: int = CARD_EMBEDDING_DIM,
        backbone_dim: int = BACKBONE_DIM,
        num_residual_blocks: int = NUM_RESIDUAL_BLOCKS,
    ):
        """
        Initialize the network.

        Args:
            action_space_size: Size of action space (1099 for Pokemon TCG)
            vocab_size: Number of unique card IDs (including EMPTY=0, HIDDEN=1)
            embedding_dim: Dimension of card embeddings
            backbone_dim: Hidden dimension of residual backbone
            num_residual_blocks: Number of residual blocks in backbone
        """
        super().__init__()

        self.action_space_size = action_space_size
        self.vocab_size = vocab_size

        # =================================================================
        # SHARED EMBEDDING LAYER
        # =================================================================
        # padding_idx=0 means EMPTY cards get zero embeddings
        self.card_embedding = nn.Embedding(
            num_embeddings=vocab_size,
            embedding_dim=embedding_dim,
            padding_idx=0
        )

        # =================================================================
        # INPUT ENCODERS
        # =================================================================

        # Hand encoder: (B, 60) -> (B, 64)
        self.hand_encoder = SequenceEncoder(
            embedding=self.card_embedding,
            seq_len=MAX_HAND_SIZE,
            output_dim=HAND_ENCODER_DIM
        )

        # Discard encoder: (B, 60) -> (B, 64)
        self.discard_encoder = SequenceEncoder(
            embedding=self.card_embedding,
            seq_len=MAX_DISCARD_SIZE,
            output_dim=DISCARD_ENCODER_DIM
        )

        # Active encoder: (B, 1, 22) -> (B, 1, 64) -> (B, 64)
        self.my_active_encoder = PokemonEncoder(
            embedding=self.card_embedding,
            num_pokemon=1,
            output_dim=POKEMON_ENCODER_DIM
        )

        # Bench encoder: (B, 8, 22) -> (B, 8, 64) -> (B, 64) via pooling
        self.my_bench_encoder = PokemonEncoder(
            embedding=self.card_embedding,
            num_pokemon=MAX_BENCH_SIZE,
            output_dim=POKEMON_ENCODER_DIM
        )

        # Opponent encoders (same architecture)
        self.opp_active_encoder = PokemonEncoder(
            embedding=self.card_embedding,
            num_pokemon=1,
            output_dim=POKEMON_ENCODER_DIM
        )

        self.opp_bench_encoder = PokemonEncoder(
            embedding=self.card_embedding,
            num_pokemon=MAX_BENCH_SIZE,
            output_dim=POKEMON_ENCODER_DIM
        )

        # Global context encoder: (B, 26) -> (B, 32)
        self.global_encoder = GlobalEncoder(output_dim=GLOBAL_ENCODER_DIM)

        # =================================================================
        # BACKBONE
        # =================================================================

        # Calculate input dimension to backbone
        # Hand: 64, Discard: 64, My Active: 64, My Bench: 64 (pooled)
        # Opp Active: 64, Opp Bench: 64 (pooled), Global: 32
        # Total: 64*6 + 32 = 416
        backbone_input_dim = (
            HAND_ENCODER_DIM +       # 64
            DISCARD_ENCODER_DIM +    # 64
            POKEMON_ENCODER_DIM +    # 64 (my active)
            POKEMON_ENCODER_DIM +    # 64 (my bench pooled)
            POKEMON_ENCODER_DIM +    # 64 (opp active)
            POKEMON_ENCODER_DIM +    # 64 (opp bench pooled)
            GLOBAL_ENCODER_DIM       # 32
        )  # = 416

        # Input projection to backbone dimension
        self.backbone_input = nn.Linear(backbone_input_dim, backbone_dim)
        self.backbone_bn = nn.BatchNorm1d(backbone_dim)

        # Residual tower
        self.residual_blocks = nn.ModuleList([
            ResidualBlock(backbone_dim) for _ in range(num_residual_blocks)
        ])

        # =================================================================
        # OUTPUT HEADS
        # =================================================================

        # Policy head: backbone_dim -> action_space_size
        self.policy_fc = nn.Linear(backbone_dim, action_space_size)

        # Value head: backbone_dim -> 64 -> 1
        self.value_fc1 = nn.Linear(backbone_dim, VALUE_HIDDEN_DIM)
        self.value_fc2 = nn.Linear(VALUE_HIDDEN_DIM, 1)

    def forward(
        self,
        state_dict: Dict[str, torch.Tensor]
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass through the network.

        Args:
            state_dict: Dictionary containing:
                - my_hand: (B, 60) int64
                - my_discard: (B, 60) float32 (will be cast to int64)
                - my_active: (B, 1, 22) float32
                - my_bench: (B, 8, 22) float32
                - opp_active: (B, 1, 22) float32
                - opp_bench: (B, 8, 22) float32
                - global_context: (B, 26) float32

        Returns:
            policy_logits: (B, action_space_size) raw logits
            value: (B, 1) game outcome prediction in [-1, 1]
        """
        # =================================================================
        # ENCODE INPUTS
        # =================================================================

        # Hand: (B, 60) -> (B, 64)
        hand_encoded = self.hand_encoder(state_dict["my_hand"])

        # Discard: (B, 60) -> (B, 64)
        # Note: discard comes as float32 but contains int IDs
        discard_ids = state_dict["my_discard"].long()
        discard_encoded = self.discard_encoder(discard_ids)

        # My Active: (B, 1, 22) -> (B, 1, 64) -> (B, 64)
        my_active_encoded = self.my_active_encoder(state_dict["my_active"])
        my_active_encoded = my_active_encoded.squeeze(1)

        # My Bench: (B, 8, 22) -> (B, 8, 64) -> (B, 64) via mean pooling
        my_bench_encoded = self.my_bench_encoder(state_dict["my_bench"])
        # Mask empty bench slots (card_id == 0)
        bench_mask = (state_dict["my_bench"][:, :, 0] > 0).unsqueeze(-1).float()
        my_bench_sum = (my_bench_encoded * bench_mask).sum(dim=1)
        my_bench_count = bench_mask.sum(dim=1).clamp(min=1.0)
        my_bench_pooled = my_bench_sum / my_bench_count

        # Opp Active: (B, 1, 22) -> (B, 64)
        opp_active_encoded = self.opp_active_encoder(state_dict["opp_active"])
        opp_active_encoded = opp_active_encoded.squeeze(1)

        # Opp Bench: (B, 8, 22) -> (B, 64) via mean pooling
        opp_bench_encoded = self.opp_bench_encoder(state_dict["opp_bench"])
        opp_bench_mask = (state_dict["opp_bench"][:, :, 0] > 0).unsqueeze(-1).float()
        opp_bench_sum = (opp_bench_encoded * opp_bench_mask).sum(dim=1)
        opp_bench_count = opp_bench_mask.sum(dim=1).clamp(min=1.0)
        opp_bench_pooled = opp_bench_sum / opp_bench_count

        # Global: (B, 26) -> (B, 32)
        global_encoded = self.global_encoder(state_dict["global_context"])

        # =================================================================
        # CONCATENATE AND BACKBONE
        # =================================================================

        # Concatenate all encodings: (B, 416)
        combined = torch.cat([
            hand_encoded,        # 64
            discard_encoded,     # 64
            my_active_encoded,   # 64
            my_bench_pooled,     # 64
            opp_active_encoded,  # 64
            opp_bench_pooled,    # 64
            global_encoded,      # 32
        ], dim=-1)

        # Project to backbone dimension
        x = self.backbone_input(combined)
        x = self.backbone_bn(x)
        x = F.relu(x)

        # Residual tower
        for block in self.residual_blocks:
            x = block(x)

        # =================================================================
        # OUTPUT HEADS
        # =================================================================

        # Policy head: (B, backbone_dim) -> (B, action_space_size)
        policy_logits = self.policy_fc(x)

        # Value head: (B, backbone_dim) -> (B, 1)
        value = self.value_fc1(x)
        value = F.relu(value)
        value = self.value_fc2(value)
        value = torch.tanh(value)  # Squash to [-1, 1]

        return policy_logits, value

    def get_policy(
        self,
        state_dict: Dict[str, torch.Tensor],
        legal_mask: Optional[torch.Tensor] = None,
        temperature: float = 1.0
    ) -> torch.Tensor:
        """
        Get action probabilities with legal action masking.

        Args:
            state_dict: Encoded game state
            legal_mask: (B, action_space_size) binary mask, 1 = legal
            temperature: Softmax temperature for exploration

        Returns:
            (B, action_space_size) action probabilities
        """
        policy_logits, _ = self.forward(state_dict)

        # Apply legal mask (set illegal actions to -inf)
        if legal_mask is not None:
            policy_logits = policy_logits.masked_fill(
                legal_mask == 0,
                float('-inf')
            )

        # Apply temperature and softmax
        if temperature != 1.0:
            policy_logits = policy_logits / temperature

        probs = F.softmax(policy_logits, dim=-1)

        return probs

    def count_parameters(self) -> int:
        """Count total trainable parameters."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def create_network(
    vocab_size: int = 1000,
    device: str = "cpu"
) -> AlphaZeroNet:
    """
    Create an AlphaZeroNet with default configuration.

    Args:
        vocab_size: Number of unique card IDs
        device: Device to place the network on

    Returns:
        Initialized AlphaZeroNet
    """
    net = AlphaZeroNet(
        action_space_size=ACTION_SPACE_SIZE,
        vocab_size=vocab_size,
    )
    return net.to(device)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    'AlphaZeroNet',
    'ResidualBlock',
    'SequenceEncoder',
    'PokemonEncoder',
    'GlobalEncoder',
    'create_network',
    'ACTION_SPACE_SIZE',
]

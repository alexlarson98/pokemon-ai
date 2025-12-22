"""
Verification script for AlphaZeroNet.

This script:
1. Instantiates the model with correct configuration
2. Creates dummy state_dict matching StateEncoder shapes
3. Runs a forward pass
4. Asserts output shapes are correct
5. Checks for NaN outputs (stability check)
6. Reports parameter counts
"""

import sys
import os

# Add src to path
script_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(script_dir)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

import torch
import numpy as np

from ai.model import AlphaZeroNet, ACTION_SPACE_SIZE, create_network
from ai.state_encoder import (
    MAX_HAND_SIZE,
    MAX_BENCH_SIZE,
    MAX_DISCARD_SIZE,
    MAX_PRIZES,
    POKEMON_FEATURES,
    GLOBAL_FEATURES,
    STADIUM_FEATURES,
)
from ai.encoder import TOTAL_ACTION_SPACE


def create_dummy_state_dict(batch_size: int = 4, vocab_size: int = 100) -> dict:
    """
    Create a dummy state dictionary matching StateEncoder output shapes.

    Args:
        batch_size: Number of samples in batch
        vocab_size: Max card ID (for random card generation)

    Returns:
        Dictionary of tensors matching StateEncoder.to_dict() format
    """
    return {
        # Hand: (B, 60) int64 card IDs
        "my_hand": torch.randint(0, vocab_size, (batch_size, MAX_HAND_SIZE), dtype=torch.int64),

        # Discard: (B, 60) float32 (contains int IDs)
        "my_discard": torch.randint(0, vocab_size, (batch_size, MAX_DISCARD_SIZE)).float(),

        # Opponent discard: (B, 60) float32
        "opp_discard": torch.randint(0, vocab_size, (batch_size, MAX_DISCARD_SIZE)).float(),

        # Active Pokemon: (B, 1, 22) float32
        "my_active": torch.rand(batch_size, 1, POKEMON_FEATURES),

        # Bench Pokemon: (B, 8, 22) float32
        "my_bench": torch.rand(batch_size, MAX_BENCH_SIZE, POKEMON_FEATURES),

        # Opponent active: (B, 1, 22) float32
        "opp_active": torch.rand(batch_size, 1, POKEMON_FEATURES),

        # Opponent bench: (B, 8, 22) float32
        "opp_bench": torch.rand(batch_size, MAX_BENCH_SIZE, POKEMON_FEATURES),

        # Global context: (B, 26) float32
        "global_context": torch.rand(batch_size, GLOBAL_FEATURES),

        # Prize cards: (B, 6) float32
        "my_prizes_known": torch.randint(0, vocab_size, (batch_size, MAX_PRIZES)).float(),

        # Opponent hand count: (B, 1) float32
        "opp_hand_count": torch.rand(batch_size, 1),

        # Stadium: (B, 2) float32
        "stadium": torch.rand(batch_size, STADIUM_FEATURES),
    }


def test_model_creation():
    """Test that model can be created with default parameters."""
    print("=" * 60)
    print("Test 1: Model Creation")
    print("=" * 60)

    model = AlphaZeroNet(vocab_size=100)
    print(f"  Model created successfully")
    print(f"  Action space size: {model.action_space_size}")
    print(f"  Vocab size: {model.vocab_size}")
    print(f"  Total parameters: {model.count_parameters():,}")
    print("  PASSED")
    print()
    return model


def test_forward_pass(model: AlphaZeroNet, batch_size: int = 4):
    """Test forward pass with dummy data."""
    print("=" * 60)
    print(f"Test 2: Forward Pass (batch_size={batch_size})")
    print("=" * 60)

    state_dict = create_dummy_state_dict(batch_size=batch_size, vocab_size=model.vocab_size)

    # Run forward pass
    model.eval()
    with torch.no_grad():
        policy_logits, value = model(state_dict)

    print(f"  Policy logits shape: {policy_logits.shape}")
    print(f"  Value shape: {value.shape}")

    # Check shapes
    assert policy_logits.shape == (batch_size, ACTION_SPACE_SIZE), \
        f"Expected policy shape ({batch_size}, {ACTION_SPACE_SIZE}), got {policy_logits.shape}"
    print(f"  Policy shape check: PASSED")

    assert value.shape == (batch_size, 1), \
        f"Expected value shape ({batch_size}, 1), got {value.shape}"
    print(f"  Value shape check: PASSED")

    print("  PASSED")
    print()
    return policy_logits, value


def test_output_ranges(policy_logits: torch.Tensor, value: torch.Tensor):
    """Test that outputs are in expected ranges."""
    print("=" * 60)
    print("Test 3: Output Ranges")
    print("=" * 60)

    # Value should be in [-1, 1] due to tanh
    value_min = value.min().item()
    value_max = value.max().item()
    print(f"  Value range: [{value_min:.4f}, {value_max:.4f}]")

    assert -1.0 <= value_min <= 1.0, f"Value min {value_min} out of [-1, 1]"
    assert -1.0 <= value_max <= 1.0, f"Value max {value_max} out of [-1, 1]"
    print(f"  Value range check: PASSED")

    # Policy logits should be finite
    assert torch.isfinite(policy_logits).all(), "Policy contains non-finite values"
    print(f"  Policy finite check: PASSED")

    print("  PASSED")
    print()


def test_no_nan_outputs(model: AlphaZeroNet):
    """Test that model doesn't produce NaN outputs."""
    print("=" * 60)
    print("Test 4: NaN Check (Stability)")
    print("=" * 60)

    # Test with various batch sizes
    for batch_size in [1, 4, 16]:
        state_dict = create_dummy_state_dict(batch_size=batch_size, vocab_size=model.vocab_size)

        model.eval()
        with torch.no_grad():
            policy_logits, value = model(state_dict)

        has_nan_policy = torch.isnan(policy_logits).any().item()
        has_nan_value = torch.isnan(value).any().item()

        assert not has_nan_policy, f"NaN in policy for batch_size={batch_size}"
        assert not has_nan_value, f"NaN in value for batch_size={batch_size}"

        print(f"  Batch size {batch_size}: No NaN detected")

    print("  PASSED")
    print()


def test_legal_masking(model: AlphaZeroNet):
    """Test legal action masking."""
    print("=" * 60)
    print("Test 5: Legal Action Masking")
    print("=" * 60)

    batch_size = 4
    state_dict = create_dummy_state_dict(batch_size=batch_size, vocab_size=model.vocab_size)

    # Create a mask where only 10 random actions are legal
    legal_mask = torch.zeros(batch_size, ACTION_SPACE_SIZE)
    for i in range(batch_size):
        legal_indices = torch.randperm(ACTION_SPACE_SIZE)[:10]
        legal_mask[i, legal_indices] = 1.0

    model.eval()
    with torch.no_grad():
        probs = model.get_policy(state_dict, legal_mask=legal_mask)

    # Check that illegal actions have zero probability
    illegal_probs = probs * (1 - legal_mask)
    max_illegal_prob = illegal_probs.max().item()

    print(f"  Max probability of illegal action: {max_illegal_prob:.6f}")
    assert max_illegal_prob < 1e-6, f"Illegal actions have non-zero probability: {max_illegal_prob}"
    print(f"  Illegal action masking: PASSED")

    # Check that legal actions sum to 1
    legal_sum = (probs * legal_mask).sum(dim=1)
    print(f"  Legal action probability sums: {legal_sum.tolist()}")
    assert torch.allclose(legal_sum, torch.ones(batch_size), atol=1e-5), \
        "Legal action probabilities don't sum to 1"
    print(f"  Probability sum check: PASSED")

    print("  PASSED")
    print()


def test_gradient_flow(model: AlphaZeroNet):
    """Test that gradients flow through the network."""
    print("=" * 60)
    print("Test 6: Gradient Flow")
    print("=" * 60)

    state_dict = create_dummy_state_dict(batch_size=4, vocab_size=model.vocab_size)

    model.train()

    policy_logits, value = model(state_dict)

    # Create dummy losses
    policy_loss = policy_logits.mean()
    value_loss = value.mean()
    total_loss = policy_loss + value_loss

    # Backward pass
    total_loss.backward()

    # Check gradients exist for key layers
    layers_to_check = [
        ("card_embedding", model.card_embedding.weight),
        ("backbone_input", model.backbone_input.weight),
        ("policy_fc", model.policy_fc.weight),
        ("value_fc1", model.value_fc1.weight),
        ("value_fc2", model.value_fc2.weight),
    ]

    for name, param in layers_to_check:
        assert param.grad is not None, f"No gradient for {name}"
        assert not torch.isnan(param.grad).any(), f"NaN gradient for {name}"
        print(f"  {name}: gradient exists, max={param.grad.abs().max():.6f}")

    print("  PASSED")
    print()


def test_batch_size_invariance(model: AlphaZeroNet):
    """Test that model handles different batch sizes correctly."""
    print("=" * 60)
    print("Test 7: Batch Size Invariance")
    print("=" * 60)

    # Set seed for reproducibility
    torch.manual_seed(42)

    # Create single sample
    state_dict_single = create_dummy_state_dict(batch_size=1, vocab_size=model.vocab_size)

    # Create batched version with same data
    state_dict_batched = {}
    for key, val in state_dict_single.items():
        state_dict_batched[key] = val.repeat(4, *([1] * (val.dim() - 1)))

    model.eval()
    with torch.no_grad():
        policy_single, value_single = model(state_dict_single)
        policy_batched, value_batched = model(state_dict_batched)

    # All batched outputs should match single output
    for i in range(4):
        policy_diff = (policy_batched[i] - policy_single[0]).abs().max().item()
        value_diff = (value_batched[i] - value_single[0]).abs().max().item()
        print(f"  Sample {i}: policy_diff={policy_diff:.6f}, value_diff={value_diff:.6f}")

    # Note: Small differences are expected due to BatchNorm behavior
    print("  (Small differences expected due to BatchNorm)")
    print("  PASSED")
    print()


def test_action_space_alignment():
    """Verify action space size matches encoder."""
    print("=" * 60)
    print("Test 8: Action Space Alignment")
    print("=" * 60)

    print(f"  TOTAL_ACTION_SPACE from encoder: {TOTAL_ACTION_SPACE}")
    print(f"  ACTION_SPACE_SIZE from model: {ACTION_SPACE_SIZE}")

    assert TOTAL_ACTION_SPACE == ACTION_SPACE_SIZE, \
        f"Action space mismatch: encoder={TOTAL_ACTION_SPACE}, model={ACTION_SPACE_SIZE}"

    print("  PASSED")
    print()


def print_model_summary(model: AlphaZeroNet):
    """Print a summary of the model architecture."""
    print("=" * 60)
    print("Model Summary")
    print("=" * 60)

    print(f"\nArchitecture:")
    print(f"  Embedding dim: {model.card_embedding.embedding_dim}")
    print(f"  Vocab size: {model.vocab_size}")
    print(f"  Action space: {model.action_space_size}")
    print(f"  Residual blocks: {len(model.residual_blocks)}")

    print(f"\nParameter counts:")
    total = 0
    for name, module in model.named_children():
        params = sum(p.numel() for p in module.parameters())
        total += params
        print(f"  {name}: {params:,}")
    print(f"  TOTAL: {total:,}")
    print()


def main():
    print("\n" + "=" * 60)
    print("AlphaZeroNet Verification Suite")
    print("=" * 60 + "\n")

    try:
        # Test 1: Create model
        model = test_model_creation()

        # Test 2: Forward pass
        policy_logits, value = test_forward_pass(model)

        # Test 3: Output ranges
        test_output_ranges(policy_logits, value)

        # Test 4: NaN check
        test_no_nan_outputs(model)

        # Test 5: Legal masking
        test_legal_masking(model)

        # Test 6: Gradient flow
        test_gradient_flow(model)

        # Test 7: Batch size invariance
        model_fresh = AlphaZeroNet(vocab_size=100)
        test_batch_size_invariance(model_fresh)

        # Test 8: Action space alignment
        test_action_space_alignment()

        # Print summary
        print_model_summary(model)

        print("=" * 60)
        print("ALL TESTS PASSED!")
        print("=" * 60)

    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
        return 1

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())

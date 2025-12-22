"""
AlphaZero Training Loop for Pokemon TCG.

This module provides:
- PokemonDataset: PyTorch Dataset for training samples
- AlphaZeroTrainer: Handles forward/backward passes and optimization
- train_loop: Main training loop (self-play -> train -> checkpoint)

Training Pipeline:
1. Self-play: Generate games using current model
2. Dataset: Wrap samples in PokemonDataset
3. Train: Run epochs of gradient updates
4. Checkpoint: Save model weights
5. Repeat

Usage:
    from ai.train import train_loop

    train_loop(
        engine=engine,
        model=model,
        state_encoder=state_encoder,
        device='cuda',
        num_iterations=100,
        games_per_iter=10,
        epochs_per_iter=5
    )
"""

import os
import time
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from torch.optim import Adam

# Add src to path for imports
import sys
script_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(script_dir)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from ai.model import AlphaZeroNet, ACTION_SPACE_SIZE
from ai.state_encoder import StateEncoder, MAX_HAND_SIZE, MAX_BENCH_SIZE
from ai.self_play import SelfPlayWorker, run_self_play_games


# =============================================================================
# POKEMON DATASET
# =============================================================================

class PokemonDataset(Dataset):
    """
    PyTorch Dataset for AlphaZero training samples.

    Each sample is a tuple of:
    - state_dict: Dict[str, np.ndarray] - Encoded game state
    - policy_target: np.ndarray - MCTS visit count probabilities
    - value_target: float - Game outcome (+1 win, -1 loss, 0 draw)
    """

    def __init__(self, samples: List[Tuple[Dict[str, np.ndarray], np.ndarray, float]]):
        """
        Initialize the dataset.

        Args:
            samples: List of (state_dict, policy_target, value_target) tuples
        """
        self.samples = samples

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Tuple[Dict[str, torch.Tensor], torch.Tensor, torch.Tensor]:
        """
        Get a single training sample.

        Returns:
            Tuple of (state_tensors, policy_target, value_target)
        """
        state_dict, policy_target, value_target = self.samples[idx]

        # Convert state_dict arrays to tensors
        state_tensors = {}
        for key, arr in state_dict.items():
            if key == 'my_hand':
                # Hand is int64 for embedding lookup
                state_tensors[key] = torch.from_numpy(arr).long()
            else:
                # Everything else is float32
                state_tensors[key] = torch.from_numpy(arr).float()

        # Convert policy target (probability distribution)
        policy_tensor = torch.from_numpy(policy_target).float()

        # Convert value target (scalar)
        value_tensor = torch.tensor([value_target], dtype=torch.float32)

        return state_tensors, policy_tensor, value_tensor


def pokemon_collate_fn(
    batch: List[Tuple[Dict[str, torch.Tensor], torch.Tensor, torch.Tensor]]
) -> Tuple[Dict[str, torch.Tensor], torch.Tensor, torch.Tensor]:
    """
    Custom collate function to batch samples with dictionary states.

    Args:
        batch: List of (state_dict, policy, value) tuples

    Returns:
        Batched (state_dict, policy, value) where state_dict values are stacked
    """
    # Separate the components
    state_dicts = [item[0] for item in batch]
    policies = [item[1] for item in batch]
    values = [item[2] for item in batch]

    # Stack state tensors by key
    batched_state = {}
    keys = state_dicts[0].keys()

    for key in keys:
        tensors = [sd[key] for sd in state_dicts]
        batched_state[key] = torch.stack(tensors, dim=0)

    # Stack policies and values
    batched_policy = torch.stack(policies, dim=0)
    batched_value = torch.stack(values, dim=0)

    return batched_state, batched_policy, batched_value


# =============================================================================
# ALPHAZERO TRAINER
# =============================================================================

@dataclass
class TrainMetrics:
    """Metrics from a training step."""
    total_loss: float
    policy_loss: float
    value_loss: float
    policy_accuracy: float  # Top-1 accuracy
    value_mae: float        # Mean absolute error


class AlphaZeroTrainer:
    """
    Handles training of the AlphaZero network.

    Losses:
    - Policy: Cross-entropy between predicted logits and target probabilities
    - Value: MSE between predicted value and target value
    """

    def __init__(
        self,
        model: AlphaZeroNet,
        optimizer: Optional[torch.optim.Optimizer] = None,
        device: str = 'cpu',
        learning_rate: float = 0.001,
        weight_decay: float = 1e-4,
        policy_weight: float = 1.0,
        value_weight: float = 1.0
    ):
        """
        Initialize the trainer.

        Args:
            model: AlphaZeroNet instance
            optimizer: Optional optimizer (creates Adam if None)
            device: 'cuda' or 'cpu'
            learning_rate: Learning rate for optimizer
            weight_decay: L2 regularization weight
            policy_weight: Weight for policy loss
            value_weight: Weight for value loss
        """
        self.model = model
        self.device = device
        self.policy_weight = policy_weight
        self.value_weight = value_weight

        # Move model to device
        self.model = self.model.to(device)

        # Create optimizer if not provided
        if optimizer is None:
            self.optimizer = Adam(
                model.parameters(),
                lr=learning_rate,
                weight_decay=weight_decay
            )
        else:
            self.optimizer = optimizer

        # Loss functions
        # Note: We use cross-entropy with soft targets (KL divergence equivalent)
        # pred_policy = logits, target_policy = probabilities

    def train_step(
        self,
        state_dict: Dict[str, torch.Tensor],
        target_policy: torch.Tensor,
        target_value: torch.Tensor
    ) -> TrainMetrics:
        """
        Perform a single training step.

        Args:
            state_dict: Batched state tensors
            target_policy: (B, ACTION_SPACE_SIZE) probability distribution
            target_value: (B, 1) value targets

        Returns:
            TrainMetrics with loss values
        """
        self.model.train()

        # Move to device
        state_dict = {k: v.to(self.device) for k, v in state_dict.items()}
        target_policy = target_policy.to(self.device)
        target_value = target_value.to(self.device)

        # Forward pass
        pred_policy_logits, pred_value = self.model(state_dict)

        # Policy Loss: Cross-entropy with soft targets
        # CE = -sum(target * log(softmax(pred)))
        # This is equivalent to KL divergence when target is a distribution
        log_probs = F.log_softmax(pred_policy_logits, dim=-1)
        policy_loss = -torch.sum(target_policy * log_probs, dim=-1).mean()

        # Value Loss: MSE
        value_loss = F.mse_loss(pred_value, target_value)

        # Total loss
        total_loss = self.policy_weight * policy_loss + self.value_weight * value_loss

        # Backward pass
        self.optimizer.zero_grad()
        total_loss.backward()
        self.optimizer.step()

        # Calculate metrics
        with torch.no_grad():
            # Policy accuracy (does predicted max match target max?)
            pred_actions = pred_policy_logits.argmax(dim=-1)
            target_actions = target_policy.argmax(dim=-1)
            policy_accuracy = (pred_actions == target_actions).float().mean().item()

            # Value MAE
            value_mae = (pred_value - target_value).abs().mean().item()

        return TrainMetrics(
            total_loss=total_loss.item(),
            policy_loss=policy_loss.item(),
            value_loss=value_loss.item(),
            policy_accuracy=policy_accuracy,
            value_mae=value_mae
        )

    def train_epoch(
        self,
        dataloader: DataLoader,
        verbose: bool = False
    ) -> Dict[str, float]:
        """
        Train for one epoch over the dataset.

        Args:
            dataloader: DataLoader with training samples
            verbose: Print batch progress

        Returns:
            Dictionary with average metrics for the epoch
        """
        total_metrics = {
            'total_loss': 0.0,
            'policy_loss': 0.0,
            'value_loss': 0.0,
            'policy_accuracy': 0.0,
            'value_mae': 0.0,
        }
        num_batches = 0

        for batch_idx, (state_dict, target_policy, target_value) in enumerate(dataloader):
            metrics = self.train_step(state_dict, target_policy, target_value)

            total_metrics['total_loss'] += metrics.total_loss
            total_metrics['policy_loss'] += metrics.policy_loss
            total_metrics['value_loss'] += metrics.value_loss
            total_metrics['policy_accuracy'] += metrics.policy_accuracy
            total_metrics['value_mae'] += metrics.value_mae
            num_batches += 1

            if verbose and (batch_idx + 1) % 10 == 0:
                print(f"    Batch {batch_idx + 1}: loss={metrics.total_loss:.4f}")

        # Average over batches
        for key in total_metrics:
            total_metrics[key] /= max(num_batches, 1)

        return total_metrics

    def evaluate(
        self,
        dataloader: DataLoader
    ) -> Dict[str, float]:
        """
        Evaluate model on a dataset (no gradient updates).

        Args:
            dataloader: DataLoader with evaluation samples

        Returns:
            Dictionary with evaluation metrics
        """
        self.model.eval()

        total_metrics = {
            'total_loss': 0.0,
            'policy_loss': 0.0,
            'value_loss': 0.0,
            'policy_accuracy': 0.0,
            'value_mae': 0.0,
        }
        num_batches = 0

        with torch.no_grad():
            for state_dict, target_policy, target_value in dataloader:
                # Move to device
                state_dict = {k: v.to(self.device) for k, v in state_dict.items()}
                target_policy = target_policy.to(self.device)
                target_value = target_value.to(self.device)

                # Forward pass
                pred_policy_logits, pred_value = self.model(state_dict)

                # Losses
                log_probs = F.log_softmax(pred_policy_logits, dim=-1)
                policy_loss = -torch.sum(target_policy * log_probs, dim=-1).mean()
                value_loss = F.mse_loss(pred_value, target_value)
                total_loss = self.policy_weight * policy_loss + self.value_weight * value_loss

                # Metrics
                pred_actions = pred_policy_logits.argmax(dim=-1)
                target_actions = target_policy.argmax(dim=-1)
                policy_accuracy = (pred_actions == target_actions).float().mean().item()
                value_mae = (pred_value - target_value).abs().mean().item()

                total_metrics['total_loss'] += total_loss.item()
                total_metrics['policy_loss'] += policy_loss.item()
                total_metrics['value_loss'] += value_loss.item()
                total_metrics['policy_accuracy'] += policy_accuracy
                total_metrics['value_mae'] += value_mae
                num_batches += 1

        # Average
        for key in total_metrics:
            total_metrics[key] /= max(num_batches, 1)

        return total_metrics

    def save_checkpoint(
        self,
        path: str,
        iteration: int = 0,
        additional_info: Optional[Dict] = None
    ) -> None:
        """
        Save model checkpoint.

        Args:
            path: File path for checkpoint
            iteration: Training iteration number
            additional_info: Optional extra info to save
        """
        checkpoint = {
            'model_state_dict': self.model.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'iteration': iteration,
        }

        if additional_info:
            checkpoint.update(additional_info)

        # Ensure directory exists
        os.makedirs(os.path.dirname(path), exist_ok=True)

        torch.save(checkpoint, path)

    def load_checkpoint(self, path: str) -> Dict[str, Any]:
        """
        Load model checkpoint.

        Args:
            path: File path to checkpoint

        Returns:
            Dictionary with checkpoint info (iteration, etc.)
        """
        checkpoint = torch.load(path, map_location=self.device)

        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])

        return {
            'iteration': checkpoint.get('iteration', 0),
        }


# =============================================================================
# REPLAY BUFFER
# =============================================================================

class ReplayBuffer:
    """
    Simple replay buffer for storing and sampling training data.

    Maintains a fixed-size buffer of recent samples.
    """

    def __init__(self, max_size: int = 100000):
        """
        Initialize the replay buffer.

        Args:
            max_size: Maximum number of samples to store
        """
        self.max_size = max_size
        self.samples: List[Tuple[Dict[str, np.ndarray], np.ndarray, float]] = []

    def add_samples(
        self,
        samples: List[Tuple[Dict[str, np.ndarray], np.ndarray, float]]
    ) -> None:
        """
        Add samples to the buffer.

        Args:
            samples: List of (state_dict, policy, value) tuples
        """
        self.samples.extend(samples)

        # Trim if over capacity (remove oldest)
        if len(self.samples) > self.max_size:
            self.samples = self.samples[-self.max_size:]

    def get_all_samples(self) -> List[Tuple[Dict[str, np.ndarray], np.ndarray, float]]:
        """Get all samples in the buffer."""
        return self.samples

    def sample(self, n: int) -> List[Tuple[Dict[str, np.ndarray], np.ndarray, float]]:
        """
        Sample n random samples from the buffer.

        Args:
            n: Number of samples to retrieve

        Returns:
            List of randomly sampled training tuples
        """
        if n >= len(self.samples):
            return self.samples

        indices = np.random.choice(len(self.samples), size=n, replace=False)
        return [self.samples[i] for i in indices]

    def __len__(self) -> int:
        return len(self.samples)

    def clear(self) -> None:
        """Clear all samples."""
        self.samples = []


# =============================================================================
# MAIN TRAINING LOOP
# =============================================================================

def train_loop(
    engine,
    model: AlphaZeroNet,
    state_encoder: StateEncoder,
    device: str = 'cpu',
    num_iterations: int = 100,
    games_per_iter: int = 10,
    epochs_per_iter: int = 5,
    batch_size: int = 64,
    num_simulations: int = 100,
    learning_rate: float = 0.001,
    checkpoint_dir: str = 'checkpoints',
    replay_buffer_size: int = 100000,
    min_buffer_size: int = 1000,
    verbose: bool = True,
    verbose_games: bool = False
) -> Dict[str, Any]:
    """
    Main AlphaZero training loop.

    Each iteration:
    1. Self-play: Generate training data
    2. Train: Update model on collected data
    3. Checkpoint: Save model weights

    Args:
        engine: PokemonEngine instance
        model: AlphaZeroNet instance
        state_encoder: StateEncoder instance
        device: 'cuda' or 'cpu'
        num_iterations: Number of training iterations
        games_per_iter: Self-play games per iteration
        epochs_per_iter: Training epochs per iteration
        batch_size: Batch size for training
        num_simulations: MCTS simulations per move
        learning_rate: Optimizer learning rate
        checkpoint_dir: Directory for saving checkpoints
        replay_buffer_size: Maximum samples in replay buffer
        min_buffer_size: Minimum samples before training starts
        verbose: Print progress

    Returns:
        Dictionary with training history
    """
    # Initialize components
    trainer = AlphaZeroTrainer(
        model=model,
        device=device,
        learning_rate=learning_rate
    )

    replay_buffer = ReplayBuffer(max_size=replay_buffer_size)

    # Training history
    history = {
        'iterations': [],
        'games_played': [],
        'samples_collected': [],
        'policy_loss': [],
        'value_loss': [],
        'policy_accuracy': [],
    }

    total_games = 0
    total_samples = 0

    if verbose:
        print("=" * 60)
        print("AlphaZero Training Loop")
        print("=" * 60)
        print(f"Device: {device}")
        print(f"Iterations: {num_iterations}")
        print(f"Games per iteration: {games_per_iter}")
        print(f"Epochs per iteration: {epochs_per_iter}")
        print(f"MCTS simulations: {num_simulations}")
        print(f"Batch size: {batch_size}")
        print("=" * 60)
        print()

    for iteration in range(1, num_iterations + 1):
        iter_start = time.time()

        if verbose:
            print(f"--- Iteration {iteration}/{num_iterations} ---")

        # =====================================================================
        # SELF-PLAY
        # =====================================================================
        if verbose:
            print(f"[Self-Play] Generating {games_per_iter} games...")

        selfplay_start = time.time()

        samples, stats = run_self_play_games(
            engine=engine,
            model=model,
            state_encoder=state_encoder,
            device=device,
            num_games=games_per_iter,
            num_simulations=num_simulations,
            verbose=verbose_games
        )

        replay_buffer.add_samples(samples)
        total_games += games_per_iter
        total_samples += len(samples)

        selfplay_time = time.time() - selfplay_start

        if verbose:
            print(f"  Games: {games_per_iter}, Samples: {len(samples)}, "
                  f"Buffer: {len(replay_buffer)}, Time: {selfplay_time:.1f}s")
            print(f"  Avg turns: {stats['avg_turns']:.1f}, "
                  f"P0 wins: {stats['player_0_wins']}, P1 wins: {stats['player_1_wins']}")

        # =====================================================================
        # TRAINING
        # =====================================================================
        if len(replay_buffer) >= min_buffer_size:
            if verbose:
                print(f"[Training] {epochs_per_iter} epochs on {len(replay_buffer)} samples...")

            train_start = time.time()

            # Create dataset and dataloader
            dataset = PokemonDataset(replay_buffer.get_all_samples())
            dataloader = DataLoader(
                dataset,
                batch_size=batch_size,
                shuffle=True,
                collate_fn=pokemon_collate_fn,
                num_workers=0,  # Keep simple for now
                drop_last=True  # BatchNorm needs batch_size > 1
            )

            # Train for multiple epochs
            epoch_metrics = []
            for epoch in range(epochs_per_iter):
                metrics = trainer.train_epoch(dataloader, verbose=False)
                epoch_metrics.append(metrics)

                if verbose:
                    print(f"  Epoch {epoch + 1}: loss={metrics['total_loss']:.4f}, "
                          f"policy_acc={metrics['policy_accuracy']:.2%}, "
                          f"value_mae={metrics['value_mae']:.3f}")

            train_time = time.time() - train_start

            # Record average metrics
            avg_policy_loss = np.mean([m['policy_loss'] for m in epoch_metrics])
            avg_value_loss = np.mean([m['value_loss'] for m in epoch_metrics])
            avg_policy_acc = np.mean([m['policy_accuracy'] for m in epoch_metrics])

            history['policy_loss'].append(avg_policy_loss)
            history['value_loss'].append(avg_value_loss)
            history['policy_accuracy'].append(avg_policy_acc)

            if verbose:
                print(f"  Training time: {train_time:.1f}s")
        else:
            if verbose:
                print(f"[Training] Skipped (buffer {len(replay_buffer)} < {min_buffer_size})")

            history['policy_loss'].append(None)
            history['value_loss'].append(None)
            history['policy_accuracy'].append(None)

        # =====================================================================
        # CHECKPOINT
        # =====================================================================
        checkpoint_path = os.path.join(checkpoint_dir, f"model_iter_{iteration}.pt")
        trainer.save_checkpoint(
            path=checkpoint_path,
            iteration=iteration,
            additional_info={
                'total_games': total_games,
                'total_samples': total_samples,
                'buffer_size': len(replay_buffer),
            }
        )

        if verbose:
            print(f"[Checkpoint] Saved to {checkpoint_path}")

        # Record history
        history['iterations'].append(iteration)
        history['games_played'].append(total_games)
        history['samples_collected'].append(total_samples)

        iter_time = time.time() - iter_start
        if verbose:
            print(f"[Iteration {iteration}] Total time: {iter_time:.1f}s")
            print()

    # Final summary
    if verbose:
        print("=" * 60)
        print("Training Complete!")
        print("=" * 60)
        print(f"Total games played: {total_games}")
        print(f"Total samples collected: {total_samples}")
        print(f"Final buffer size: {len(replay_buffer)}")
        if history['policy_accuracy'][-1] is not None:
            print(f"Final policy accuracy: {history['policy_accuracy'][-1]:.2%}")

    return history


# =============================================================================
# QUICK TRAINING TEST
# =============================================================================

def quick_training_test(
    engine,
    model: AlphaZeroNet,
    state_encoder: StateEncoder,
    device: str = 'cpu'
) -> bool:
    """
    Run a quick training test to verify the pipeline works.

    Args:
        engine: PokemonEngine instance
        model: AlphaZeroNet instance
        state_encoder: StateEncoder instance
        device: 'cuda' or 'cpu'

    Returns:
        True if test passes
    """
    print("Quick Training Test")
    print("-" * 40)

    # Generate a small amount of data
    print("[1/3] Generating 1 self-play game...")
    worker = SelfPlayWorker(
        engine=engine,
        model=model,
        state_encoder=state_encoder,
        device=device,
        num_simulations=5,  # Very low for speed
        max_turns=50,
        verbose=False
    )

    samples, game_info = worker.play_game()
    print(f"  Generated {len(samples)} samples")

    if len(samples) == 0:
        print("  ERROR: No samples generated")
        return False

    # Create dataset and dataloader
    print("[2/3] Testing dataset and dataloader...")
    dataset = PokemonDataset(samples)
    dataloader = DataLoader(
        dataset,
        batch_size=min(16, len(samples)),
        shuffle=True,
        collate_fn=pokemon_collate_fn,
        drop_last=True  # BatchNorm needs batch_size > 1
    )

    # Get a batch
    batch = next(iter(dataloader))
    state_dict, target_policy, target_value = batch
    print(f"  Batch size: {target_policy.shape[0]}")
    print(f"  Policy shape: {target_policy.shape}")
    print(f"  Value shape: {target_value.shape}")

    # Test training step
    print("[3/3] Testing training step...")
    trainer = AlphaZeroTrainer(model=model, device=device, learning_rate=0.001)

    metrics = trainer.train_step(state_dict, target_policy, target_value)
    print(f"  Total loss: {metrics.total_loss:.4f}")
    print(f"  Policy loss: {metrics.policy_loss:.4f}")
    print(f"  Value loss: {metrics.value_loss:.4f}")
    print(f"  Policy accuracy: {metrics.policy_accuracy:.2%}")

    print("-" * 40)
    print("Quick Training Test: PASSED")
    return True


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    'PokemonDataset',
    'pokemon_collate_fn',
    'AlphaZeroTrainer',
    'TrainMetrics',
    'ReplayBuffer',
    'train_loop',
    'quick_training_test',
]

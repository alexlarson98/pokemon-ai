"""
AI Module - Neural Network Action Encoding and Policy Components.

This module provides:
- UniversalActionEncoder: Maps Actions <-> integer indices for neural networks
- StateEncoder: Converts GameState to neural network input tensors
- CardIDRegistry: Maps card_id strings to integer IDs for embeddings
- AlphaZeroNet: Policy-value neural network for AlphaZero training
- MCTS: Monte Carlo Tree Search with neural network guidance
- SelfPlayWorker: Generates training data through self-play
- AlphaZeroTrainer: Handles model training and checkpointing
- train_loop: Main training loop orchestration
- RandomAgent: Simple random action selection for testing
"""

from .encoder import UniversalActionEncoder, TOTAL_ACTION_SPACE
from .mcts import MCTS, MCTSNode, RandomAgent, decode_to_action
from .state_encoder import (
    StateEncoder,
    CardIDRegistry,
    EncodedState,
    encode_state,
    get_global_registry,
    set_global_registry,
    MAX_HAND_SIZE,
    MAX_BENCH_SIZE,
    FEATURES_PER_SLOT,
    GLOBAL_CONTEXT_SIZE,
)
from .model import AlphaZeroNet, create_network, ACTION_SPACE_SIZE
from .self_play import GameHistory, SelfPlayWorker, run_self_play_games
from .parallel_self_play import (
    BatchMCTS,
    ParallelSelfPlayWorker,
    run_parallel_self_play,
)
from .train import (
    PokemonDataset,
    pokemon_collate_fn,
    AlphaZeroTrainer,
    ReplayBuffer,
    train_loop,
    quick_training_test,
)

__all__ = [
    # Action encoding
    'UniversalActionEncoder',
    'decode_to_action',
    'TOTAL_ACTION_SPACE',
    'ACTION_SPACE_SIZE',
    # State encoding
    'StateEncoder',
    'CardIDRegistry',
    'EncodedState',
    'encode_state',
    'get_global_registry',
    'set_global_registry',
    'MAX_HAND_SIZE',
    'MAX_BENCH_SIZE',
    'FEATURES_PER_SLOT',
    'GLOBAL_CONTEXT_SIZE',
    # Neural Network
    'AlphaZeroNet',
    'create_network',
    # MCTS
    'MCTS',
    'MCTSNode',
    'RandomAgent',
    # Self-Play
    'GameHistory',
    'SelfPlayWorker',
    'run_self_play_games',
    # Parallel Self-Play
    'BatchMCTS',
    'ParallelSelfPlayWorker',
    'run_parallel_self_play',
    # Training
    'PokemonDataset',
    'pokemon_collate_fn',
    'AlphaZeroTrainer',
    'ReplayBuffer',
    'train_loop',
    'quick_training_test',
]

"""
AI Module - Neural Network Action Encoding and Policy Components.

This module provides:
- UniversalActionEncoder: Maps Actions <-> integer indices for neural networks
- StateEncoder: Converts GameState to neural network input tensors
- CardIDRegistry: Maps card_id strings to integer IDs for embeddings
- MCTS: Monte Carlo Tree Search (pure or AlphaZero-compatible)
- RandomAgent: Simple random action selection for testing
"""

from .encoder import UniversalActionEncoder
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

__all__ = [
    # Action encoding
    'UniversalActionEncoder',
    'decode_to_action',
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
    # MCTS
    'MCTS',
    'MCTSNode',
    'RandomAgent',
]

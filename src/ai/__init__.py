"""
AI Module - Neural Network Action Encoding and Policy Components.

This module provides:
- UniversalActionEncoder: Maps Actions <-> integer indices for neural networks
- MCTS: Monte Carlo Tree Search (pure or AlphaZero-compatible)
- RandomAgent: Simple random action selection for testing
"""

from .encoder import UniversalActionEncoder
from .mcts import MCTS, MCTSNode, RandomAgent, decode_to_action

__all__ = [
    'UniversalActionEncoder',
    'MCTS',
    'MCTSNode',
    'RandomAgent',
    'decode_to_action',
]

"""
Shared Card Logic Library

This module provides reusable card effect and action generator implementations
that can be imported by multiple set files to solve the 'Reprints Problem'.

All trainer cards use the Stack-based Resolution Architecture for optimal
MCTS branching factor reduction.

Example: Iono appears in both Paldea Evolved and Paldean Fates,
but the logic is implemented once here and imported by both sets.
"""

from .trainers import (
    # Buddy-Buddy Poffin
    buddy_buddy_poffin_actions,
    buddy_buddy_poffin_effect,

    # Rare Candy
    rare_candy_actions,
    rare_candy_effect,

    # Ultra Ball
    ultra_ball_actions,
    ultra_ball_effect,

    # Nest Ball
    nest_ball_actions,
    nest_ball_effect,

    # Iono
    iono_actions,
    iono_effect,
)

__all__ = [
    # Buddy-Buddy Poffin
    'buddy_buddy_poffin_actions',
    'buddy_buddy_poffin_effect',

    # Rare Candy
    'rare_candy_actions',
    'rare_candy_effect',

    # Ultra Ball
    'ultra_ball_actions',
    'ultra_ball_effect',

    # Nest Ball
    'nest_ball_actions',
    'nest_ball_effect',

    # Iono
    'iono_actions',
    'iono_effect',
]

"""
Shared Card Logic Library

This module contains reusable card effect implementations that can be
imported by multiple set files to solve the 'Reprints Problem'.

Example: Iono appears in both Paldea Evolved and Paldean Fates,
but the logic is implemented once here and imported by both sets.
"""

from .trainers import (
    buddy_buddy_poffin_effect,
    rare_candy_effect,
    ultra_ball_effect,
    nest_ball_effect,
    iono_effect,
    buddy_buddy_poffin_actions,
    rare_candy_actions,
    ultra_ball_actions,
    nest_ball_actions,
    iono_actions,
)

__all__ = [
    'buddy_buddy_poffin_effect',
    'rare_candy_effect',
    'ultra_ball_effect',
    'nest_ball_effect',
    'iono_effect',
    'buddy_buddy_poffin_actions',
    'rare_candy_actions',
    'ultra_ball_actions',
    'nest_ball_actions',
    'iono_actions',
]

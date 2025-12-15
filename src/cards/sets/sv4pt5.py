"""
Pokémon TCG Engine - Paldean Fates Card Logic
Set Code: PAF (sv4pt5)

This module contains card-specific logic for Paldean Fates.
For reprints, this module imports logic from the set where the card was first released.
"""

from cards.library.trainers import (
    rare_candy_effect,
    rare_candy_actions,
    ultra_ball_effect,
    ultra_ball_actions,
    iono_actions,
    iono_effect
)
from .sv2 import chien_pao_ex_hail_blade_actions, chien_pao_ex_hail_blade_effect


# ============================================================================
# SV4PT5 LOGIC REGISTRY
# ============================================================================

SV4PT5_LOGIC = {
    # Chien-Pao ex (reprint from sv2)
    "sv4pt5-242": {
        "Hail Blade": {
            "generator": chien_pao_ex_hail_blade_actions,
            "effect": chien_pao_ex_hail_blade_effect,
        }
    },

    # TRAINERS
    
    "sv4pt5-80": {  # Iono
        "effect": iono_effect,
        "generator": iono_actions,
    },
    "sv4pt5-237": {  # Iono
        "effect": iono_effect,
        "generator": iono_actions,
    },
    "sv4pt5-91": {  # Ultra Ball
        "effect": ultra_ball_effect,
        "generator": ultra_ball_actions,
    },
}

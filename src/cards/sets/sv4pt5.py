"""
Pokémon TCG Engine - Paldean Fates Card Logic
Set Code: PAF (sv4pt5)

This module contains card-specific logic for Paldean Fates.
For reprints, this module imports logic from the set where the card was first released.
"""

# Import Chien-Pao ex logic from sv2 (Paldea Evolved - first release)
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
}

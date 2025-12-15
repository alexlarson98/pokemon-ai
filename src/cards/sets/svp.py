"""
Pokémon TCG Engine - Scarlet & Violet Promo Cards (SVP)
Set Code: SVP

This module contains card-specific logic for the Scarlet & Violet Promo set.
For reprints, this module imports logic from the set where the card was first released.
"""

# Import Chien-Pao ex logic from sv2 (Paldea Evolved - first release)
from cards.library.trainers import iono_actions, iono_effect
from .sv2 import chien_pao_ex_hail_blade_actions, chien_pao_ex_hail_blade_effect


# ============================================================================
# SVP LOGIC REGISTRY
# ============================================================================

SVP_LOGIC = {
    # Chien-Pao ex (promo reprint from sv2)
    "svp-30": {
        "Hail Blade": {
            "generator": chien_pao_ex_hail_blade_actions,
            "effect": chien_pao_ex_hail_blade_effect,
        }
    },

    # TRAINERS
    
    "svp-124": {  # Iono
        "effect": iono_effect,
        "generator": iono_actions,
    },
}

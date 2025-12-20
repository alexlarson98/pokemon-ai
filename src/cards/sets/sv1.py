"""
Pokémon TCG Engine - Scarlet & Violet Base Set Card Logic
Set Code: SVI
"""

from cards.library.trainers import (
    nest_ball_effect,
    nest_ball_actions,
    ultra_ball_effect,
    ultra_ball_actions,
)

# ============================================================================
# SV1 LOGIC REGISTRY (Unified Schema)
# ============================================================================

SV1_LOGIC = {
    "sv1-181": {  # Nest Ball
        "Play Nest Ball": {
            "category": "activatable",
            "generator": nest_ball_actions,
            "effect": nest_ball_effect,
        },
    },
    "sv1-196": {  # Ultra Ball
        "Play Ultra Ball": {
            "category": "activatable",
            "generator": ultra_ball_actions,
            "effect": ultra_ball_effect,
        },
    },
}

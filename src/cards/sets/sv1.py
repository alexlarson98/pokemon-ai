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

SV1_LOGIC = {
    "sv1-181": {  # Nest Ball
        "actions": {
            "play": {
                "generator": nest_ball_actions,
                "effect": nest_ball_effect,
            }
        }
    },
    "sv1-196": {  # Ultra Ball
        "actions": {
            "play": {
                "generator": ultra_ball_actions,
                "effect": ultra_ball_effect,
            }
        }
    },
}

"""
Pokémon TCG Engine - Scarlet & Violet Base Set Card Logic
Set Code: SVI
"""

from cards.library.trainers import (
    rare_candy_effect,
    rare_candy_actions,
    ultra_ball_effect,
    ultra_ball_actions,
    nest_ball_effect,
    nest_ball_actions
)

SV1_LOGIC = {
    "sv1-181": {  # Nest Ball
        "effect": nest_ball_effect,
        "generator": nest_ball_actions,
    },
    "sv1-196": {  # Ultra Ball
        "effect": ultra_ball_effect,
        "generator": ultra_ball_actions,
    },
}

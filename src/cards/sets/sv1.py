"""
Pokémon TCG Engine - Scarlet & Violet Base Set Card Logic
Set Code: SVI
"""

from ..library.trainers import nest_ball_effect, nest_ball_actions

SV1_LOGIC = {
    "sv1-181": {  # Nest Ball
        "effect": nest_ball_effect,
        "generator": nest_ball_actions,
    },
}

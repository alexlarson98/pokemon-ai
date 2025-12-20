"""
Pokémon TCG Engine - Mega Evolution A Card Logic
Set Code: MEG/MEX
"""

from ..library.trainers import (
    rare_candy_effect,
    rare_candy_actions,
    ultra_ball_effect,
    ultra_ball_actions,
)

ME1_LOGIC = {
    "me1-125": {  # Rare Candy
        "Play Rare Candy": {
            "category": "activatable",
            "generator": rare_candy_actions,
            "effect": rare_candy_effect,
        },
    },
    "me1-131": {  # Ultra Ball
        "Play Ultra Ball": {
            "category": "activatable",
            "generator": ultra_ball_actions,
            "effect": ultra_ball_effect,
        },
    },
}

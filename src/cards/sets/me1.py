"""
Pokémon TCG Engine - Mega Evolution A Card Logic
Set Code: MEG/MEX
"""

from ..library.trainers import (
    rare_candy_effect,
    rare_candy_actions,
    ultra_ball_effect,
    ultra_ball_actions,
    bosss_orders_actions,
    bosss_orders_effect,
    night_stretcher_actions,
    night_stretcher_effect,
)

ME1_LOGIC = {
    "me1-114": {  # Boss's Orders
        "Play Boss's Orders": {
            "category": "activatable",
            "generator": bosss_orders_actions,
            "effect": bosss_orders_effect,
        },
    },
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
    "me1-173": {  # Night Stretcher
        "Play Night Stretcher": {
            "category": "activatable",
            "generator": night_stretcher_actions,
            "effect": night_stretcher_effect,
        },
    },
}

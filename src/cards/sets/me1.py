"""
Pokémon TCG Engine - Mega Evolution A Card Logic
Set Code: MEG/MEX
"""

from ..library.trainers import rare_candy_effect, ultra_ball_effect

ME1_LOGIC = {
    "me1-125:effect": rare_candy_effect,  # Rare Candy
    "me1-131:effect": ultra_ball_effect,  # Ultra Ball
}

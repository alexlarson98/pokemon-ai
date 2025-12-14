"""
Pokémon TCG Engine - Paldea Evolved Card Logic
Set Code: PAL
"""

from ..library.trainers import iono_effect, iono_actions

SV2_LOGIC = {
    "sv2-185": {  # Iono
        "effect": iono_effect,
        "generator": iono_actions,
    },
}

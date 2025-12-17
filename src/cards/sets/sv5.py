"""
Pokémon TCG Engine - Temporal Forces Card Logic
Set Code: TEF
"""

from ..library.trainers import buddy_buddy_poffin_effect, buddy_buddy_poffin_actions

SV5_LOGIC = {
    "sv5-144": {  # Buddy-Buddy Poffin
        "actions": {
            "play": {
                "generator": buddy_buddy_poffin_actions,
                "effect": buddy_buddy_poffin_effect,
            }
        }
    },
}

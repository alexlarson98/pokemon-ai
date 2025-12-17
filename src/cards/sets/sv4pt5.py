"""
Pokémon TCG Engine - Paldean Fates Card Logic
Set Code: PAF (sv4pt5)

This module contains card-specific logic for Paldean Fates.
For reprints, this module imports logic from the set where the card was first released.
"""

from cards.library.trainers import (
    rare_candy_effect,
    rare_candy_actions,
    ultra_ball_effect,
    ultra_ball_actions,
    iono_actions,
    iono_effect
)
from .sv2 import chien_pao_ex_hail_blade_actions, chien_pao_ex_hail_blade_effect
from .sv3pt5 import (
    charmander_blazing_destruction_actions,
    charmander_blazing_destruction_effect,
    charmander_steady_firebreathing_actions,
    charmander_steady_firebreathing_effect,
    pidgey_call_for_family_actions,
    pidgey_call_for_family_effect,
    pidgey_tackle_actions,
    pidgey_tackle_effect
)


# ============================================================================
# SV4PT5 LOGIC REGISTRY
# ============================================================================

SV4PT5_LOGIC = {
    # Charmander - Version 3 reprints (from sv3pt5)
    "sv4pt5-7": {
        "Blazing Destruction": {
            "generator": charmander_blazing_destruction_actions,
            "effect": charmander_blazing_destruction_effect,
        },
        "Steady Firebreathing": {
            "generator": charmander_steady_firebreathing_actions,
            "effect": charmander_steady_firebreathing_effect,
        },
    },
    "sv4pt5-109": {
        "Blazing Destruction": {
            "generator": charmander_blazing_destruction_actions,
            "effect": charmander_blazing_destruction_effect,
        },
        "Steady Firebreathing": {
            "generator": charmander_steady_firebreathing_actions,
            "effect": charmander_steady_firebreathing_effect,
        },
    },

    # Chien-Pao ex (reprint from sv2)
    "sv4pt5-242": {
        "Hail Blade": {
            "generator": chien_pao_ex_hail_blade_actions,
            "effect": chien_pao_ex_hail_blade_effect,
        }
    },

    "sv4pt5-80": {  # Iono
        "actions": {
            "play": {
                "generator": iono_actions,
                "effect": iono_effect,
            }
        }
    },
    "sv4pt5-237": {  # Iono
        "actions": {
            "play": {
                "generator": iono_actions,
                "effect": iono_effect,
            }
        }
    },
    "sv4pt5-91": {  # Ultra Ball
        "actions": {
            "play": {
                "generator": ultra_ball_actions,
                "effect": ultra_ball_effect,
            }
        }
    },

    # Pidgey - Version 2 reprint (from sv3pt5)
    "sv4pt5-196": {
        "Call for Family": {
            "generator": pidgey_call_for_family_actions,
            "effect": pidgey_call_for_family_effect,
        },
        "Tackle": {
            "generator": pidgey_tackle_actions,
            "effect": pidgey_tackle_effect,
        },
    },
}

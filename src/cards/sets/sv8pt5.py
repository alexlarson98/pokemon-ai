"""
Pokémon TCG Engine - Prismatic Evolutions Card Logic
Set Code: PRE (sv8pt5)

This module contains card-specific logic for Prismatic Evolutions.
For reprints, this module imports logic from the set where the card was first released.
"""

from typing import List
from models import GameState, CardInstance, Action, ActionType, PlayerState, StatusCondition
from actions import apply_damage, calculate_damage

from .sv6pt5 import (
    duskull_come_and_get_you_actions,
    duskull_come_and_get_you_effect,
    duskull_mumble_actions,
    duskull_mumble_effect,
    dusclops_cursed_blast_actions,
    dusclops_cursed_blast_effect,
    dusclops_will_o_wisp_actions,
    dusclops_will_o_wisp_effect,
    dusknoir_cursed_blast_actions,
    dusknoir_cursed_blast_effect,
    dusknoir_shadow_bind_actions,
    dusknoir_shadow_bind_effect,
)
from .svp import (
    noctowl_jewel_seeker_hook,
    noctowl_speed_wing_actions,
    noctowl_speed_wing_effect,
    terapagos_ex_unified_beatdown_actions,
    terapagos_ex_unified_beatdown_effect,
    terapagos_ex_crown_opal_actions,
    terapagos_ex_crown_opal_effect,
)
from .sv7 import (
    fan_rotom_fan_call_actions,
    fan_rotom_fan_call_effect,
    fan_rotom_assault_landing_actions,
    fan_rotom_assault_landing_effect,
)
from cards.library.trainers import (
    professors_research_actions,
    professors_research_effect,
)


# ============================================================================
# HOOTHOOT - VERSION 3: TACKLE + INSOMNIA (sv8pt5-77)
# ============================================================================

def hoothoot_tackle_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Hoothoot's "Tackle" attack.

    Attack: Tackle [CC]
    20 damage. No additional effects.

    Args:
        state: Current game state
        card: Hoothoot CardInstance
        player: PlayerState of the attacking player

    Returns:
        List with single attack action
    """
    return [Action(
        action_type=ActionType.ATTACK,
        player_id=player.player_id,
        card_id=card.id,
        attack_name="Tackle",
        display_label="Tackle - 20 Dmg"
    )]


def hoothoot_tackle_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Hoothoot's "Tackle" attack effect.

    Deals 20 damage to opponent's Active Pokémon.

    Args:
        state: Current game state
        card: Hoothoot CardInstance
        action: Attack action

    Returns:
        Modified GameState
    """
    opponent = state.get_opponent()

    # Deal 20 damage to opponent's Active Pokémon
    if opponent.board.active_spot:
        final_damage = calculate_damage(
            state=state,
            attacker=card,
            defender=opponent.board.active_spot,
            base_damage=20,
            attack_name="Tackle"
        )

        state = apply_damage(
            state=state,
            target=opponent.board.active_spot,
            damage=final_damage,
            is_attack_damage=True,
            attacker=card
        )

    return state


def hoothoot_insomnia_guard(state: GameState, card: CardInstance, condition: StatusCondition) -> bool:
    """
    Guard for Hoothoot's "Insomnia" ability.

    Ability: Insomnia
    This Pokémon can't be Asleep.

    Args:
        state: Current game state
        card: Hoothoot CardInstance
        condition: The StatusCondition being applied

    Returns:
        True if the condition should be blocked, False otherwise
    """
    # Block only the Asleep condition
    if condition == StatusCondition.ASLEEP:
        return True  # Block this condition

    return False  # Allow other conditions


# ============================================================================
# SV8PT5 LOGIC REGISTRY (Unified Schema)
# ============================================================================

SV8PT5_LOGIC = {
    # Duskull - Reprint from sv6pt5
    "sv8pt5-35": {
        "Come and Get You": {
            "category": "attack",
            "generator": duskull_come_and_get_you_actions,
            "effect": duskull_come_and_get_you_effect,
        },
        "Mumble": {
            "category": "attack",
            "generator": duskull_mumble_actions,
            "effect": duskull_mumble_effect,
        },
    },

    # Dusclops - Reprint from sv6pt5
    "sv8pt5-36": {
        "Cursed Blast": {
            "category": "activatable",
            "generator": dusclops_cursed_blast_actions,
            "effect": dusclops_cursed_blast_effect,
        },
        "Will-O-Wisp": {
            "category": "attack",
            "generator": dusclops_will_o_wisp_actions,
            "effect": dusclops_will_o_wisp_effect,
        },
    },

    # Dusknoir - Reprint from sv6pt5
    "sv8pt5-37": {
        "Cursed Blast": {
            "category": "activatable",
            "generator": dusknoir_cursed_blast_actions,
            "effect": dusknoir_cursed_blast_effect,
        },
        "Shadow Bind": {
            "category": "attack",
            "generator": dusknoir_shadow_bind_actions,
            "effect": dusknoir_shadow_bind_effect,
        },
    },

    # Hoothoot - Version 3 (Tackle + Insomnia guard)
    "sv8pt5-77": {
        "Tackle": {
            "category": "attack",
            "generator": hoothoot_tackle_actions,
            "effect": hoothoot_tackle_effect,
        },
        "Insomnia": {
            "category": "guard",
            "guard_type": "status_condition",
            "scope": "self",
            "effect": hoothoot_insomnia_guard,
        },
    },

    # Fan Rotom - Reprint from sv7-118
    "sv8pt5-85": {
        "Fan Call": {
            "category": "activatable",
            "generator": fan_rotom_fan_call_actions,
            "effect": fan_rotom_fan_call_effect,
        },
        "Assault Landing": {
            "category": "attack",
            "generator": fan_rotom_assault_landing_actions,
            "effect": fan_rotom_assault_landing_effect,
        },
    },

    # Noctowl - Version 1 (Reprint from svp-141)
    "sv8pt5-78": {
        "Speed Wing": {
            "category": "attack",
            "generator": noctowl_speed_wing_actions,
            "effect": noctowl_speed_wing_effect,
        },
        "Jewel Seeker": {
            "category": "hook",
            "trigger": "on_evolve",
            "effect": noctowl_jewel_seeker_hook,
        },
    },

    # Professor's Research reprints
    "sv8pt5-122": {
        "Play Professor's Research": {
            "category": "activatable",
            "generator": professors_research_actions,
            "effect": professors_research_effect,
        },
    },
    "sv8pt5-123": {
        "Play Professor's Research": {
            "category": "activatable",
            "generator": professors_research_actions,
            "effect": professors_research_effect,
        },
    },
    "sv8pt5-124": {
        "Play Professor's Research": {
            "category": "activatable",
            "generator": professors_research_actions,
            "effect": professors_research_effect,
        },
    },
    "sv8pt5-125": {
        "Play Professor's Research": {
            "category": "activatable",
            "generator": professors_research_actions,
            "effect": professors_research_effect,
        },
    },

    # Terapagos ex - Version 1 (Tera variant, reprint from svp-165)
    "sv8pt5-169": {
        "Unified Beatdown": {
            "category": "attack",
            "generator": terapagos_ex_unified_beatdown_actions,
            "effect": terapagos_ex_unified_beatdown_effect,
        },
        "Crown Opal": {
            "category": "attack",
            "generator": terapagos_ex_crown_opal_actions,
            "effect": terapagos_ex_crown_opal_effect,
        },
    },
    "sv8pt5-180": {
        "Unified Beatdown": {
            "category": "attack",
            "generator": terapagos_ex_unified_beatdown_actions,
            "effect": terapagos_ex_unified_beatdown_effect,
        },
        "Crown Opal": {
            "category": "attack",
            "generator": terapagos_ex_crown_opal_actions,
            "effect": terapagos_ex_crown_opal_effect,
        },
    },

    # Terapagos ex - Version 2 (non-Tera variant)
    "sv8pt5-92": {
        "Unified Beatdown": {
            "category": "attack",
            "generator": terapagos_ex_unified_beatdown_actions,
            "effect": terapagos_ex_unified_beatdown_effect,
        },
        "Crown Opal": {
            "category": "attack",
            "generator": terapagos_ex_crown_opal_actions,
            "effect": terapagos_ex_crown_opal_effect,
        },
    },
}

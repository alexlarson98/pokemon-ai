"""
Pokémon TCG Engine - Paldean Fates Card Logic
Set Code: PAF (sv4pt5)

This module contains card-specific logic for Paldean Fates.
For reprints, this module imports logic from the set where the card was first released.
"""

from typing import List
from models import GameState, CardInstance, Action, ActionType, PlayerState
from actions import apply_damage, calculate_damage

from cards.library.trainers import (
    rare_candy_effect,
    rare_candy_actions,
    ultra_ball_effect,
    ultra_ball_actions,
    iono_actions,
    iono_effect,
    professors_research_actions,
    professors_research_effect,
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

# Import Charizard ex Version 1/2 logic from svp (first release)
from .svp import (
    charizard_ex_infernal_reign_hook,
    charizard_ex_burning_darkness_actions,
    charizard_ex_burning_darkness_effect,
)

# Import Pidgeot ex logic from sv3 (first release)
from .sv3 import (
    pidgeot_ex_quick_search_actions,
    pidgeot_ex_quick_search_effect,
    pidgeot_ex_blustery_wind_actions,
    pidgeot_ex_blustery_wind_effect,
)


# ============================================================================
# CHARMELEON - VERSION 3: COMBUSTION + FLARE VEIL (sv4pt5-8, sv4pt5-110)
# ============================================================================

def charmeleon_v3_combustion_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Charmeleon's "Combustion" attack (Version 3).

    Attack: Combustion [FF]
    50 damage. No additional effects.

    Args:
        state: Current game state
        card: Charmeleon CardInstance
        player: PlayerState of the attacking player

    Returns:
        List with single attack action
    """
    return [Action(
        action_type=ActionType.ATTACK,
        player_id=player.player_id,
        card_id=card.id,
        attack_name="Combustion",
        display_label="Combustion - 50 Dmg"
    )]


def charmeleon_v3_combustion_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Charmeleon's "Combustion" attack effect (Version 3).

    Deals 50 damage to opponent's Active Pokémon.

    Args:
        state: Current game state
        card: Charmeleon CardInstance
        action: Attack action

    Returns:
        Modified GameState
    """
    opponent = state.get_opponent()

    # Deal 50 damage to opponent's Active Pokémon
    if opponent.board.active_spot:
        final_damage = calculate_damage(
            state=state,
            attacker=card,
            defender=opponent.board.active_spot,
            base_damage=50,
            attack_name="Combustion"
        )

        state = apply_damage(
            state=state,
            target=opponent.board.active_spot,
            damage=final_damage,
            is_attack_damage=True,
            attacker=card
        )

    return state


def charmeleon_flare_veil_guard(state: GameState, card: CardInstance, context: dict) -> bool:
    """
    Guard for Charmeleon's "Flare Veil" ability.

    Ability: Flare Veil
    Prevent all effects of attacks used by your opponent's Pokemon done to this Pokemon.
    (Damage is not an effect.)

    This guard blocks attack effects (status conditions, special effects, etc.)
    but NOT damage. It only applies to effects from opponent's attacks.

    Args:
        state: Current game state
        card: Charmeleon CardInstance
        context: Context dict containing:
            - 'source': The source of the effect ('attack', 'ability', etc.)
            - 'source_player_id': The player who owns the source
            - 'effect_type': Type of effect being applied

    Returns:
        True if the effect should be blocked, False otherwise
    """
    # Only block effects from opponent's attacks
    source = context.get('source')
    source_player_id = context.get('source_player_id')

    # Only block if it's from an attack
    if source != 'attack':
        return False

    # Only block if it's from the opponent
    if source_player_id == card.owner_id:
        return False  # Don't block our own attack effects

    # Block the effect (but not damage - damage is handled separately)
    return True


# ============================================================================
# SV4PT5 LOGIC REGISTRY
# ============================================================================

SV4PT5_LOGIC = {
    # Charmander - Version 3 reprints (from sv3pt5)
    "sv4pt5-7": {
        "Blazing Destruction": {
            "category": "attack",
            "generator": charmander_blazing_destruction_actions,
            "effect": charmander_blazing_destruction_effect,
        },
        "Steady Firebreathing": {
            "category": "attack",
            "generator": charmander_steady_firebreathing_actions,
            "effect": charmander_steady_firebreathing_effect,
        },
    },
    "sv4pt5-109": {
        "Blazing Destruction": {
            "category": "attack",
            "generator": charmander_blazing_destruction_actions,
            "effect": charmander_blazing_destruction_effect,
        },
        "Steady Firebreathing": {
            "category": "attack",
            "generator": charmander_steady_firebreathing_actions,
            "effect": charmander_steady_firebreathing_effect,
        },
    },

    # Charmeleon - Version 3 (Combustion 50 + Flare Veil guard)
    "sv4pt5-8": {
        "Combustion": {
            "category": "attack",
            "generator": charmeleon_v3_combustion_actions,
            "effect": charmeleon_v3_combustion_effect,
        },
        "Flare Veil": {
            "category": "guard",
            "guard_type": "effect_prevention",
            "scope": "self",
            "effect": charmeleon_flare_veil_guard,
        },
    },
    "sv4pt5-110": {
        "Combustion": {
            "category": "attack",
            "generator": charmeleon_v3_combustion_actions,
            "effect": charmeleon_v3_combustion_effect,
        },
        "Flare Veil": {
            "category": "guard",
            "guard_type": "effect_prevention",
            "scope": "self",
            "effect": charmeleon_flare_veil_guard,
        },
    },

    # Chien-Pao ex (reprint from sv2)
    "sv4pt5-242": {
        "Hail Blade": {
            "category": "attack",
            "generator": chien_pao_ex_hail_blade_actions,
            "effect": chien_pao_ex_hail_blade_effect,
        }
    },

    "sv4pt5-80": {  # Iono
        "Play Iono": {
            "category": "activatable",
            "generator": iono_actions,
            "effect": iono_effect,
        },
    },
    "sv4pt5-237": {  # Iono
        "Play Iono": {
            "category": "activatable",
            "generator": iono_actions,
            "effect": iono_effect,
        },
    },
    "sv4pt5-89": {  # Rare Candy
        "Play Rare Candy": {
            "category": "activatable",
            "generator": rare_candy_actions,
            "effect": rare_candy_effect,
        },
    },
    "sv4pt5-91": {  # Ultra Ball
        "Play Ultra Ball": {
            "category": "activatable",
            "generator": ultra_ball_actions,
            "effect": ultra_ball_effect,
        },
    },
    "sv4pt5-87": {  # Professor's Research
        "Play Professor's Research": {
            "category": "activatable",
            "generator": professors_research_actions,
            "effect": professors_research_effect,
        },
    },
    "sv4pt5-88": {  # Professor's Research
        "Play Professor's Research": {
            "category": "activatable",
            "generator": professors_research_actions,
            "effect": professors_research_effect,
        },
    },

    # Pidgey - Version 2 reprint (from sv3pt5)
    "sv4pt5-196": {
        "Call for Family": {
            "category": "attack",
            "generator": pidgey_call_for_family_actions,
            "effect": pidgey_call_for_family_effect,
        },
        "Tackle": {
            "category": "attack",
            "generator": pidgey_tackle_actions,
            "effect": pidgey_tackle_effect,
        },
    },

    # Charizard ex - Version 1/2 reprints (Infernal Reign + Burning Darkness)
    "sv4pt5-54": {
        "Burning Darkness": {
            "category": "attack",
            "generator": charizard_ex_burning_darkness_actions,
            "effect": charizard_ex_burning_darkness_effect,
        },
        "Infernal Reign": {
            "category": "hook",
            "trigger": "on_evolve",
            "effect": charizard_ex_infernal_reign_hook,
        },
    },
    "sv4pt5-234": {
        "Burning Darkness": {
            "category": "attack",
            "generator": charizard_ex_burning_darkness_actions,
            "effect": charizard_ex_burning_darkness_effect,
        },
        "Infernal Reign": {
            "category": "hook",
            "trigger": "on_evolve",
            "effect": charizard_ex_infernal_reign_hook,
        },
    },

    # Pidgeot ex - Reprint from sv3
    "sv4pt5-221": {
        "Quick Search": {
            "category": "activatable",
            "generator": pidgeot_ex_quick_search_actions,
            "effect": pidgeot_ex_quick_search_effect,
        },
        "Blustery Wind": {
            "category": "attack",
            "generator": pidgeot_ex_blustery_wind_actions,
            "effect": pidgeot_ex_blustery_wind_effect,
        },
    },
}

"""
Pokémon TCG Engine - Obsidian Flames Card Logic
Set Code: OBF (sv3)

This module contains card-specific logic for the Obsidian Flames set.
For reprints, this module imports logic from the set where the card was first released.
"""

from typing import List
from models import GameState, CardInstance, Action, ActionType, PlayerState
from actions import apply_damage, calculate_damage

# Import Charmander Version 1 logic from svp (first release)
from .svp import charmander_heat_tackle_actions, charmander_heat_tackle_effect


# ============================================================================
# PIDGEY - VERSION 1: GUST (sv3-162, sv3-207)
# ============================================================================

def pidgey_gust_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Pidgey's "Gust" attack.

    Attack: Gust [C]
    20 damage. No additional effects.

    Args:
        state: Current game state
        card: Pidgey CardInstance
        player: PlayerState of the attacking player

    Returns:
        List with single attack action
    """
    return [Action(
        action_type=ActionType.ATTACK,
        player_id=player.player_id,
        card_id=card.id,
        attack_name="Gust",
        display_label="Gust - 20 Dmg"
    )]


def pidgey_gust_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Pidgey's "Gust" attack effect.

    Deals 20 damage to opponent's Active Pokémon.

    Args:
        state: Current game state
        card: Pidgey CardInstance
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
            attack_name="Gust"
        )

        state = apply_damage(
            state=state,
            target=opponent.board.active_spot,
            damage=final_damage,
            is_attack_damage=True,
            attacker=card
        )

    return state


# ============================================================================
# SV3 LOGIC REGISTRY
# ============================================================================

SV3_LOGIC = {
    # Charmander - Version 1 reprint (Heat Tackle from svp)
    "sv3-26": {
        "Heat Tackle": {
            "generator": charmander_heat_tackle_actions,
            "effect": charmander_heat_tackle_effect,
        },
    },

    # Pidgey - Version 1 (Gust)
    "sv3-162": {
        "Gust": {
            "generator": pidgey_gust_actions,
            "effect": pidgey_gust_effect,
        },
    },
    "sv3-207": {
        "Gust": {
            "generator": pidgey_gust_actions,
            "effect": pidgey_gust_effect,
        },
    },
}

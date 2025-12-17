"""
Pokémon TCG Engine - Phantasmal Flames Card Logic
Set Code: PFL (me2)

This module contains card-specific logic for the Phantasmal Flames set.
"""

from typing import List
from models import GameState, CardInstance, Action, ActionType, PlayerState
from actions import apply_damage, calculate_damage


# ============================================================================
# CHARMANDER - VERSION 4: AGILE ABILITY & LIVE COAL ATTACK
# ============================================================================

def charmander_agile_modifier(state: GameState, card: CardInstance, current_cost: int) -> int:
    """
    Modifier for Charmander's "Agile" ability.

    Ability: Agile
    If this Pokémon has no Energy attached, it has no Retreat Cost.

    This is a LOCAL MODIFIER (4 Pillars Architecture) that is automatically
    checked during retreat cost calculation in engine.calculate_retreat_cost().

    Args:
        state: Current game state
        card: Charmander CardInstance
        current_cost: Current retreat cost before this modifier

    Returns:
        Modified retreat cost (0 if no energy attached, else unchanged)
    """
    # If Charmander has no Energy attached, retreat cost is 0
    if not card.attached_energy or len(card.attached_energy) == 0:
        return 0
    # Otherwise, return unchanged cost
    return current_cost


def charmander_live_coal_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Charmander's "Live Coal" attack.

    Attack: Live Coal [F]
    20 damage. No additional effects.

    Args:
        state: Current game state
        card: Charmander CardInstance
        player: PlayerState of the attacking player

    Returns:
        List with single attack action
    """
    return [Action(
        action_type=ActionType.ATTACK,
        player_id=player.player_id,
        card_id=card.id,
        attack_name="Live Coal",
        display_label="Live Coal - 20 Dmg"
    )]


def charmander_live_coal_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Charmander's "Live Coal" attack effect.

    Deals 20 damage to opponent's Active Pokémon.

    Args:
        state: Current game state
        card: Charmander CardInstance
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
            attack_name="Live Coal"
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
# ME2 LOGIC REGISTRY
# ============================================================================

ME2_LOGIC = {
    # Charmander - Version 4 (Agile ability + Live Coal attack)
    "me2-11": {
        # Attack: Live Coal [F] - 20 damage
        "Live Coal": {
            "generator": charmander_live_coal_actions,
            "effect": charmander_live_coal_effect,
        },
        # Ability: Agile (MODIFIER) - If no Energy attached, retreat cost = 0
        "modifiers": {
            "retreat_cost": charmander_agile_modifier,
        },
    },
}

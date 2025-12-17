"""
Pokémon TCG Engine - Scarlet & Violet Promo Cards (SVP)
Set Code: SVP

This module contains card-specific logic for the Scarlet & Violet Promo set.
For reprints, this module imports logic from the set where the card was first released.
"""

from typing import List
from models import GameState, CardInstance, Action, ActionType, PlayerState
from actions import apply_damage, calculate_damage
from cards.library.trainers import iono_actions, iono_effect
from .sv2 import chien_pao_ex_hail_blade_actions, chien_pao_ex_hail_blade_effect


# ============================================================================
# CHARMANDER - VERSION 1: HEAT TACKLE (svp-44)
# ============================================================================

def charmander_heat_tackle_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Charmander's "Heat Tackle" attack.

    Attack: Heat Tackle [F]
    30 damage. This Pokémon also does 10 damage to itself.

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
        attack_name="Heat Tackle",
        display_label="Heat Tackle - 30 Dmg (10 recoil)"
    )]


def charmander_heat_tackle_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Charmander's "Heat Tackle" attack effect.

    1. Deal 30 damage to opponent's Active Pokémon
    2. Deal 10 damage to Charmander itself (recoil)

    Args:
        state: Current game state
        card: Charmander CardInstance
        action: Attack action

    Returns:
        Modified GameState
    """
    player = state.get_player(action.player_id)
    opponent = state.get_opponent()

    # Step 1: Deal 30 damage to opponent's Active Pokémon
    if opponent.board.active_spot:
        final_damage = calculate_damage(
            state=state,
            attacker=card,
            defender=opponent.board.active_spot,
            base_damage=30,
            attack_name="Heat Tackle"
        )

        state = apply_damage(
            state=state,
            target=opponent.board.active_spot,
            damage=final_damage,
            is_attack_damage=True,
            attacker=card
        )

    # Step 2: Deal 10 recoil damage to Charmander itself
    state = apply_damage(
        state=state,
        target=card,
        damage=10,
        is_attack_damage=False,
        attacker=card
    )

    return state


# ============================================================================
# CHARMANDER - VERSION 2: EMBER (svp-47)
# ============================================================================

def charmander_ember_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Charmander's "Ember" attack.

    Attack: Ember [FF]
    40 damage. Discard an Energy from this Pokémon.

    Creates one action per energy attached to Charmander.

    Args:
        state: Current game state
        card: Charmander CardInstance
        player: PlayerState of the attacking player

    Returns:
        List of attack actions, one per energy that could be discarded
    """
    actions = []

    # Get all energy attached to Charmander
    attached_energy = card.attached_energy

    if not attached_energy:
        # No energy to discard - attack cannot be performed
        # (This should be caught by energy validation, but return empty just in case)
        return actions

    # Generate one action per energy card that could be discarded
    from cards.registry import create_card
    for idx, energy in enumerate(attached_energy):
        # Get card definition to get the name
        energy_def = create_card(energy.card_id)
        energy_name = energy_def.name if energy_def else f"Energy {idx+1}"

        actions.append(Action(
            action_type=ActionType.ATTACK,
            player_id=player.player_id,
            card_id=card.id,
            attack_name="Ember",
            parameters={'discard_energy_id': energy.id},
            display_label=f"Ember - 40 Dmg (Discard {energy_name})"
        ))

    return actions


def charmander_ember_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Charmander's "Ember" attack effect.

    1. Deal 40 damage to opponent's Active Pokémon
    2. Discard one Energy from Charmander

    Args:
        state: Current game state
        card: Charmander CardInstance
        action: Attack action with energy_id parameter

    Returns:
        Modified GameState
    """
    player = state.get_player(action.player_id)
    opponent = state.get_opponent()

    # Get the energy to discard from parameters
    energy_id = action.parameters.get('discard_energy_id')

    # Step 1: Deal 40 damage to opponent's Active Pokémon
    if opponent.board.active_spot:
        final_damage = calculate_damage(
            state=state,
            attacker=card,
            defender=opponent.board.active_spot,
            base_damage=40,
            attack_name="Ember"
        )

        state = apply_damage(
            state=state,
            target=opponent.board.active_spot,
            damage=final_damage,
            is_attack_damage=True,
            attacker=card
        )

    # Step 2: Discard the specified energy from Charmander
    if energy_id:
        energy_to_discard = next((e for e in card.attached_energy if e.id == energy_id), None)
        if energy_to_discard:
            card.attached_energy.remove(energy_to_discard)
            player.discard.add_card(energy_to_discard)

    return state


# ============================================================================
# SVP LOGIC REGISTRY
# ============================================================================

SVP_LOGIC = {
    # Charmander - Version 1: Heat Tackle
    "svp-44": {
        "Heat Tackle": {
            "generator": charmander_heat_tackle_actions,
            "effect": charmander_heat_tackle_effect,
        },
    },

    # Charmander - Version 2: Ember
    "svp-47": {
        "Ember": {
            "generator": charmander_ember_actions,
            "effect": charmander_ember_effect,
        },
    },

    # Chien-Pao ex (promo reprint from sv2)
    "svp-30": {
        "Hail Blade": {
            "generator": chien_pao_ex_hail_blade_actions,
            "effect": chien_pao_ex_hail_blade_effect,
        }
    },

    # TRAINERS

    "svp-124": {  # Iono
        "actions": {
            "play": {
                "generator": iono_actions,
                "effect": iono_effect,
            }
        }
    },
}

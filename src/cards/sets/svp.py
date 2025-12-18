"""
Pokémon TCG Engine - Scarlet & Violet Promo Cards (SVP)
Set Code: SVP

This module contains card-specific logic for the Scarlet & Violet Promo set.
For reprints, this module imports logic from the set where the card was first released.
"""

from typing import List, Optional
from models import (
    GameState, CardInstance, Action, ActionType, PlayerState,
    EnergyType, Subtype, SearchAndAttachState, InterruptPhase
)
from actions import apply_damage, calculate_damage, shuffle_deck
from cards.library.trainers import iono_actions, iono_effect
from cards.factory import get_card_definition
from cards.base import EnergyCard
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
# CHARIZARD EX - VERSION 1/2/4: INFERNAL REIGN HOOK + BURNING DARKNESS
# (svp-56, svp-74, sv4pt5-54, sv4pt5-234, sv3-125, sv3-215, sv3-223, sv3-228)
# ============================================================================

def charizard_ex_infernal_reign_hook(state: GameState, card: CardInstance, context: dict) -> GameState:
    """
    Hook for Charizard ex's "Infernal Reign" ability.

    Ability: Infernal Reign
    When you play this Pokemon from your hand to evolve 1 of your Pokemon during
    your turn, you may search your deck for up to 3 Basic Fire Energy cards and
    attach them to your Pokemon in any way you like. Then, shuffle your deck.

    This hook is triggered when Charizard ex evolves from Charmeleon.
    The evolved_pokemon in context is this Charizard ex card.

    INTERRUPT STACK ARCHITECTURE:
    This hook creates a SearchAndAttachState interrupt that breaks the ability
    into atomic MCTS-friendly choices:
    1. Search Phase: Select 0-3 Basic Fire Energy from deck
    2. Attach Phase: For each selected energy, choose target Pokemon

    Args:
        state: Current game state
        card: Charizard ex CardInstance (the evolved Pokemon)
        context: Hook context containing:
            - 'evolved_pokemon': The Charizard ex that just evolved
            - 'previous_stage': The Charmeleon that was evolved from
            - 'player_id': The player who evolved
            - 'trigger_card': The card that triggered (same as card for on_evolve)
            - 'trigger_player_id': The player who owns the trigger card

    Returns:
        Modified GameState with pending_interrupt set for player choice
    """
    # Only trigger if this is the card that just evolved
    evolved_pokemon = context.get('evolved_pokemon')
    if evolved_pokemon is None or evolved_pokemon.id != card.id:
        return state

    player_id = context.get('player_id')
    player = state.get_player(player_id)

    if not player or player.deck.is_empty():
        return state

    # Check if player has any Pokemon in play to attach to
    if not player.board.get_all_pokemon():
        return state

    # Create the SearchAndAttachState interrupt
    # Even if no Fire Energy exists, player should be able to "search" and find nothing
    # This maintains the correct game flow and allows MCTS to explore this branch
    interrupt = SearchAndAttachState(
        ability_name="Infernal Reign",
        source_card_id=card.id,
        player_id=player_id,
        phase=InterruptPhase.SELECT_COUNT,  # Use upfront count selection (optimized for MCTS)
        search_filter={
            "energy_type": EnergyType.FIRE,
            "subtype": Subtype.BASIC
        },
        max_select=3,
        selected_card_ids=[],
        cards_to_attach=[],
        current_attach_index=0,
        is_complete=False
    )

    # Set the interrupt on the game state
    state.pending_interrupt = interrupt

    return state


def charizard_ex_burning_darkness_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Charizard ex's "Burning Darkness" attack.

    Attack: Burning Darkness [FF]
    180+ damage. This attack does 30 more damage for each Prize card
    your opponent has taken.

    Args:
        state: Current game state
        card: Charizard ex CardInstance
        player: PlayerState of the attacking player

    Returns:
        List with single attack action
    """
    # Calculate bonus damage based on opponent's prize cards taken
    opponent = state.get_opponent()
    prizes_taken = 6 - len(opponent.prizes.cards)  # Standard game has 6 prizes
    bonus_damage = 30 * prizes_taken
    total_damage = 180 + bonus_damage

    return [Action(
        action_type=ActionType.ATTACK,
        player_id=player.player_id,
        card_id=card.id,
        attack_name="Burning Darkness",
        display_label=f"Burning Darkness - {total_damage} Dmg (180+{bonus_damage})"
    )]


def charizard_ex_burning_darkness_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Charizard ex's "Burning Darkness" attack effect.

    Deals 180 + 30 damage for each Prize card opponent has taken.

    Args:
        state: Current game state
        card: Charizard ex CardInstance
        action: Attack action

    Returns:
        Modified GameState
    """
    opponent = state.get_opponent()

    # Calculate damage: 180 base + 30 per prize taken by opponent
    prizes_taken = 6 - len(opponent.prizes.cards)
    base_damage = 180 + (30 * prizes_taken)

    # Deal damage to opponent's Active Pokémon
    if opponent.board.active_spot:
        final_damage = calculate_damage(
            state=state,
            attacker=card,
            defender=opponent.board.active_spot,
            base_damage=base_damage,
            attack_name="Burning Darkness"
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
# CHARIZARD EX - VERSION 3: BRAVE WING + EXPLOSIVE VORTEX
# (svp-161, sv3pt5-6, sv3pt5-183, sv3pt5-199)
# ============================================================================

def charizard_ex_brave_wing_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Charizard ex's "Brave Wing" attack.

    Attack: Brave Wing [F]
    60+ damage. If this Pokemon has any damage counters on it,
    this attack does 100 more damage.

    Args:
        state: Current game state
        card: Charizard ex CardInstance
        player: PlayerState of the attacking player

    Returns:
        List with single attack action
    """
    # Check if Charizard ex has damage
    has_damage = card.damage_counters > 0
    bonus = 100 if has_damage else 0
    total_damage = 60 + bonus

    if has_damage:
        label = f"Brave Wing - {total_damage} Dmg (60+100)"
    else:
        label = "Brave Wing - 60 Dmg"

    return [Action(
        action_type=ActionType.ATTACK,
        player_id=player.player_id,
        card_id=card.id,
        attack_name="Brave Wing",
        display_label=label
    )]


def charizard_ex_brave_wing_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Charizard ex's "Brave Wing" attack effect.

    Deals 60 damage, +100 if Charizard ex has any damage counters.

    Args:
        state: Current game state
        card: Charizard ex CardInstance
        action: Attack action

    Returns:
        Modified GameState
    """
    opponent = state.get_opponent()

    # Calculate damage: 60 base + 100 if damaged
    base_damage = 60
    if card.damage_counters > 0:
        base_damage += 100

    # Deal damage to opponent's Active Pokémon
    if opponent.board.active_spot:
        final_damage = calculate_damage(
            state=state,
            attacker=card,
            defender=opponent.board.active_spot,
            base_damage=base_damage,
            attack_name="Brave Wing"
        )

        state = apply_damage(
            state=state,
            target=opponent.board.active_spot,
            damage=final_damage,
            is_attack_damage=True,
            attacker=card
        )

    return state


def charizard_ex_explosive_vortex_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Charizard ex's "Explosive Vortex" attack.

    Attack: Explosive Vortex [FFFF]
    330 damage. Discard 3 Energy from this Pokemon.

    Args:
        state: Current game state
        card: Charizard ex CardInstance
        player: PlayerState of the attacking player

    Returns:
        List with single attack action (energy discard is mandatory)
    """
    # Attack requires discarding 3 energy - check if we have enough
    if len(card.attached_energy) < 3:
        return []  # Can't use attack without 3 energy to discard

    return [Action(
        action_type=ActionType.ATTACK,
        player_id=player.player_id,
        card_id=card.id,
        attack_name="Explosive Vortex",
        display_label="Explosive Vortex - 330 Dmg (Discard 3 Energy)"
    )]


def charizard_ex_explosive_vortex_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Charizard ex's "Explosive Vortex" attack effect.

    Deals 330 damage and discards 3 Energy from Charizard ex.

    Args:
        state: Current game state
        card: Charizard ex CardInstance
        action: Attack action

    Returns:
        Modified GameState
    """
    player = state.get_player(action.player_id)
    opponent = state.get_opponent()

    # Deal 330 damage to opponent's Active Pokémon
    if opponent.board.active_spot:
        final_damage = calculate_damage(
            state=state,
            attacker=card,
            defender=opponent.board.active_spot,
            base_damage=330,
            attack_name="Explosive Vortex"
        )

        state = apply_damage(
            state=state,
            target=opponent.board.active_spot,
            damage=final_damage,
            is_attack_damage=True,
            attacker=card
        )

    # Discard 3 Energy from Charizard ex
    energy_to_discard = min(3, len(card.attached_energy))
    for _ in range(energy_to_discard):
        if card.attached_energy:
            energy = card.attached_energy.pop(0)
            player.discard.add_card(energy)

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

    # Charizard ex - Version 1/2 (Infernal Reign + Burning Darkness)
    "svp-56": {
        "Burning Darkness": {
            "generator": charizard_ex_burning_darkness_actions,
            "effect": charizard_ex_burning_darkness_effect,
        },
        "hooks": {
            "on_evolve": charizard_ex_infernal_reign_hook,
        },
    },
    "svp-74": {
        "Burning Darkness": {
            "generator": charizard_ex_burning_darkness_actions,
            "effect": charizard_ex_burning_darkness_effect,
        },
        "hooks": {
            "on_evolve": charizard_ex_infernal_reign_hook,
        },
    },

    # Charizard ex - Version 3 (Brave Wing + Explosive Vortex)
    "svp-161": {
        "Brave Wing": {
            "generator": charizard_ex_brave_wing_actions,
            "effect": charizard_ex_brave_wing_effect,
        },
        "Explosive Vortex": {
            "generator": charizard_ex_explosive_vortex_actions,
            "effect": charizard_ex_explosive_vortex_effect,
        },
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

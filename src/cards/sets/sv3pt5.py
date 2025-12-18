"""
Pokémon TCG Engine - 151 Card Logic
Set Code: MEW (sv3pt5)

This module contains card-specific logic for the 151 set.
"""

from typing import List
from models import GameState, CardInstance, Action, ActionType, PlayerState
from actions import apply_damage, calculate_damage

# Import Charizard ex Version 3 logic from svp (first release)
from .svp import (
    charizard_ex_brave_wing_actions,
    charizard_ex_brave_wing_effect,
    charizard_ex_explosive_vortex_actions,
    charizard_ex_explosive_vortex_effect,
)


# ============================================================================
# CHARMANDER - VERSION 3: BLAZING DESTRUCTION & STEADY FIREBREATHING
# ============================================================================

def charmander_blazing_destruction_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Charmander's "Blazing Destruction" attack.

    Attack: Blazing Destruction [F]
    Discard a Stadium in play.

    Args:
        state: Current game state
        card: Charmander CardInstance
        player: PlayerState of the attacking player

    Returns:
        List with single attack action (always available, even if no stadium)
    """
    return [Action(
        action_type=ActionType.ATTACK,
        player_id=player.player_id,
        card_id=card.id,
        attack_name="Blazing Destruction",
        display_label="Blazing Destruction (Discard Stadium)"
    )]


def charmander_blazing_destruction_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Charmander's "Blazing Destruction" attack effect.

    Discards the Stadium card currently in play (if any).

    Args:
        state: Current game state
        card: Charmander CardInstance
        action: Attack action

    Returns:
        Modified GameState
    """
    # Check if there's a Stadium in play
    if state.stadium:
        # Determine which player owns the stadium to discard to correct discard pile
        stadium_owner = state.get_player(state.stadium.owner_id)

        # Discard the stadium
        stadium_owner.discard.add_card(state.stadium)
        state.stadium = None

    return state


def charmander_steady_firebreathing_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Charmander's "Steady Firebreathing" attack.

    Attack: Steady Firebreathing [FF]
    30 damage. No additional effects.

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
        attack_name="Steady Firebreathing",
        display_label="Steady Firebreathing - 30 Dmg"
    )]


def charmander_steady_firebreathing_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Charmander's "Steady Firebreathing" attack effect.

    Deals 30 damage to opponent's Active Pokémon.

    Args:
        state: Current game state
        card: Charmander CardInstance
        action: Attack action

    Returns:
        Modified GameState
    """
    opponent = state.get_opponent()

    # Deal 30 damage to opponent's Active Pokémon
    if opponent.board.active_spot:
        final_damage = calculate_damage(
            state=state,
            attacker=card,
            defender=opponent.board.active_spot,
            base_damage=30,
            attack_name="Steady Firebreathing"
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
# CHARMELEON - VERSION 2: COMBUSTION & FIRE BLAST (sv3pt5-5, sv3pt5-169)
# ============================================================================

def charmeleon_combustion_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Charmeleon's "Combustion" attack.

    Attack: Combustion [F]
    20 damage. No additional effects.

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
        display_label="Combustion - 20 Dmg"
    )]


def charmeleon_combustion_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Charmeleon's "Combustion" attack effect.

    Deals 20 damage to opponent's Active Pokémon.

    Args:
        state: Current game state
        card: Charmeleon CardInstance
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


def charmeleon_fire_blast_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Charmeleon's "Fire Blast" attack.

    Attack: Fire Blast [FFF]
    90 damage. Discard an Energy from this Pokemon.

    Args:
        state: Current game state
        card: Charmeleon CardInstance
        player: PlayerState of the attacking player

    Returns:
        List with attack actions for each energy that can be discarded
    """
    actions = []

    # Get attached energy cards
    attached_energy = card.attached_energy

    if not attached_energy:
        # No energy to discard - attack cannot be used
        # (This shouldn't happen since attack costs FFF)
        return []

    # Generate one action per unique energy type that can be discarded
    # For simplicity, we'll just pick the first energy
    # In a full implementation, you might want to let the player choose
    actions.append(Action(
        action_type=ActionType.ATTACK,
        player_id=player.player_id,
        card_id=card.id,
        attack_name="Fire Blast",
        parameters={'discard_energy_id': attached_energy[0].id},
        display_label="Fire Blast - 90 Dmg (Discard Energy)"
    ))

    return actions


def charmeleon_fire_blast_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Charmeleon's "Fire Blast" attack effect.

    Deals 90 damage to opponent's Active Pokémon and discards an Energy from self.

    Args:
        state: Current game state
        card: Charmeleon CardInstance
        action: Attack action with discard_energy_id parameter

    Returns:
        Modified GameState
    """
    player = state.get_player(action.player_id)
    opponent = state.get_opponent()

    # Deal 90 damage to opponent's Active Pokémon
    if opponent.board.active_spot:
        final_damage = calculate_damage(
            state=state,
            attacker=card,
            defender=opponent.board.active_spot,
            base_damage=90,
            attack_name="Fire Blast"
        )

        state = apply_damage(
            state=state,
            target=opponent.board.active_spot,
            damage=final_damage,
            is_attack_damage=True,
            attacker=card
        )

    # Discard an Energy from this Pokemon
    discard_energy_id = action.parameters.get('discard_energy_id') if action.parameters else None

    if discard_energy_id:
        # Find and remove the specific energy
        energy_to_discard = None
        for i, energy in enumerate(card.attached_energy):
            if energy.id == discard_energy_id:
                energy_to_discard = card.attached_energy.pop(i)
                break

        if energy_to_discard:
            player.discard.add_card(energy_to_discard)
    elif card.attached_energy:
        # Fallback: discard first attached energy
        energy_to_discard = card.attached_energy.pop(0)
        player.discard.add_card(energy_to_discard)

    return state


# ============================================================================
# PIDGEY - VERSION 2: CALL FOR FAMILY & TACKLE (sv3pt5-16)
# ============================================================================

def pidgey_tackle_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Pidgey's "Tackle" attack.

    Attack: Tackle [CC]
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
        attack_name="Tackle",
        display_label="Tackle - 20 Dmg"
    )]


def pidgey_tackle_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Pidgey's "Tackle" attack effect.

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


# ============================================================================
# PIDGEY - CALL FOR FAMILY (Stack-Based)
# ============================================================================

def pidgey_call_for_family_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate Call for Family attack action using the Stack architecture.

    Generates a SINGLE action that initiates the resolution stack.
    The actual selection happens through SearchDeckStep.

    Branching Factor: 1 (initial) + N choices (sequential)
    """
    bench_space = player.board.max_bench_size - player.board.get_bench_count()
    if bench_space <= 0:
        return []

    return [Action(
        action_type=ActionType.ATTACK,
        player_id=player.player_id,
        card_id=card.id,
        attack_name="Call for Family",
        parameters={'use_stack': True},
        display_label="Call for Family (search up to 2 Basic)"
    )]


def pidgey_call_for_family_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Call for Family Effect - Push search step onto the stack.

    Stack Sequence:
    1. SearchDeckStep: Search deck for up to 2 Basic Pokemon
       - Pokemon go directly to bench
       - Deck is shuffled after
    """
    from models import SearchDeckStep, ZoneType, SelectionPurpose

    player = state.get_player(action.player_id)

    bench_space = player.board.max_bench_size - player.board.get_bench_count()
    max_search = min(2, bench_space)

    search_step = SearchDeckStep(
        source_card_id=card.id,
        source_card_name="Call for Family",
        player_id=player.player_id,
        purpose=SelectionPurpose.SEARCH_TARGET,
        count=max_search,
        min_count=0,
        destination=ZoneType.BENCH,
        filter_criteria={
            'supertype': 'Pokemon',
            'subtype': 'Basic'
        },
        shuffle_after=True
    )

    state.push_step(search_step)
    return state


# ============================================================================
# SV3PT5 LOGIC REGISTRY
# ============================================================================

SV3PT5_LOGIC = {
    # Charmander - Version 3 (both printings have same attacks)
    "sv3pt5-4": {
        "Blazing Destruction": {
            "generator": charmander_blazing_destruction_actions,
            "effect": charmander_blazing_destruction_effect,
        },
        "Steady Firebreathing": {
            "generator": charmander_steady_firebreathing_actions,
            "effect": charmander_steady_firebreathing_effect,
        },
    },
    "sv3pt5-168": {
        "Blazing Destruction": {
            "generator": charmander_blazing_destruction_actions,
            "effect": charmander_blazing_destruction_effect,
        },
        "Steady Firebreathing": {
            "generator": charmander_steady_firebreathing_actions,
            "effect": charmander_steady_firebreathing_effect,
        },
    },

    # Charmeleon - Version 2 (Combustion + Fire Blast)
    "sv3pt5-5": {
        "Combustion": {
            "generator": charmeleon_combustion_actions,
            "effect": charmeleon_combustion_effect,
        },
        "Fire Blast": {
            "generator": charmeleon_fire_blast_actions,
            "effect": charmeleon_fire_blast_effect,
        },
    },
    "sv3pt5-169": {
        "Combustion": {
            "generator": charmeleon_combustion_actions,
            "effect": charmeleon_combustion_effect,
        },
        "Fire Blast": {
            "generator": charmeleon_fire_blast_actions,
            "effect": charmeleon_fire_blast_effect,
        },
    },

    # Pidgey - Version 2 (Call for Family + Tackle)
    "sv3pt5-16": {
        "Call for Family": {
            "generator": pidgey_call_for_family_actions,
            "effect": pidgey_call_for_family_effect,
        },
        "Tackle": {
            "generator": pidgey_tackle_actions,
            "effect": pidgey_tackle_effect,
        },
    },

    # Charizard ex - Version 3 (Brave Wing + Explosive Vortex)
    "sv3pt5-6": {
        "Brave Wing": {
            "generator": charizard_ex_brave_wing_actions,
            "effect": charizard_ex_brave_wing_effect,
        },
        "Explosive Vortex": {
            "generator": charizard_ex_explosive_vortex_actions,
            "effect": charizard_ex_explosive_vortex_effect,
        },
    },
    "sv3pt5-183": {
        "Brave Wing": {
            "generator": charizard_ex_brave_wing_actions,
            "effect": charizard_ex_brave_wing_effect,
        },
        "Explosive Vortex": {
            "generator": charizard_ex_explosive_vortex_actions,
            "effect": charizard_ex_explosive_vortex_effect,
        },
    },
    "sv3pt5-199": {
        "Brave Wing": {
            "generator": charizard_ex_brave_wing_actions,
            "effect": charizard_ex_brave_wing_effect,
        },
        "Explosive Vortex": {
            "generator": charizard_ex_explosive_vortex_actions,
            "effect": charizard_ex_explosive_vortex_effect,
        },
    },
}

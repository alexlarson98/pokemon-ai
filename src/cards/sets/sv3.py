"""
Pokémon TCG Engine - Obsidian Flames Card Logic
Set Code: OBF (sv3)

This module contains card-specific logic for the Obsidian Flames set.
For reprints, this module imports logic from the set where the card was first released.
"""

from typing import List
from models import (
    GameState, CardInstance, Action, ActionType, PlayerState,
    SearchDeckStep, ZoneType, SelectionPurpose
)
from actions import apply_damage, calculate_damage
from cards.factory import get_card_definition

# Import Charmander Version 1 logic from svp (first release)
from .svp import charmander_heat_tackle_actions, charmander_heat_tackle_effect

# Import Charizard ex Version 1/2/4 logic from svp (first release)
from .svp import (
    charizard_ex_infernal_reign_hook,
    charizard_ex_burning_darkness_actions,
    charizard_ex_burning_darkness_effect,
)


# ============================================================================
# CHARMELEON - VERSION 1: HEAT TACKLE (sv3-27)
# ============================================================================

def charmeleon_heat_tackle_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Charmeleon's "Heat Tackle" attack.

    Attack: Heat Tackle [FF]
    70 damage. This Pokemon also does 20 damage to itself.

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
        attack_name="Heat Tackle",
        display_label="Heat Tackle - 70 Dmg (20 to self)"
    )]


def charmeleon_heat_tackle_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Charmeleon's "Heat Tackle" attack effect.

    Deals 70 damage to opponent's Active Pokémon and 20 damage to itself.

    Args:
        state: Current game state
        card: Charmeleon CardInstance
        action: Attack action

    Returns:
        Modified GameState
    """
    opponent = state.get_opponent()

    # Deal 70 damage to opponent's Active Pokémon
    if opponent.board.active_spot:
        final_damage = calculate_damage(
            state=state,
            attacker=card,
            defender=opponent.board.active_spot,
            base_damage=70,
            attack_name="Heat Tackle"
        )

        state = apply_damage(
            state=state,
            target=opponent.board.active_spot,
            damage=final_damage,
            is_attack_damage=True,
            attacker=card
        )

    # Deal 20 damage to self (recoil damage - not affected by weakness/resistance)
    state = apply_damage(
        state=state,
        target=card,
        damage=20,
        is_attack_damage=False,  # Self-damage is not attack damage
        attacker=card
    )

    return state


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
# PIDGEOT EX - QUICK SEARCH + BLUSTERY WIND (sv3-164, sv3-217, sv3-225)
# ============================================================================

def pidgeot_ex_quick_search_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Pidgeot ex's "Quick Search" ability.

    Ability: Quick Search
    Once during your turn, you may search your deck for a card and put it
    into your hand. Then, shuffle your deck. You can't use more than 1
    Quick Search Ability each turn.

    GLOBAL RESTRICTION: The card text explicitly says "You can't use more
    than 1 Quick Search Ability each turn." This means only ONE Quick Search
    can be used per turn total, even with multiple Pidgeot ex in play.

    Args:
        state: Current game state
        card: Pidgeot ex CardInstance
        player: PlayerState of the owner

    Returns:
        List with ability action if available, empty list otherwise
    """
    # Check global restriction: Only one Quick Search per turn across ALL Pidgeot ex
    if state.turn_metadata.get('quick_search_used', False):
        return []

    # Check if this specific card has already used Quick Search this turn
    if "Quick Search" in card.abilities_used_this_turn:
        return []

    # Check if deck is empty
    if player.deck.is_empty():
        return []

    return [Action(
        action_type=ActionType.USE_ABILITY,
        player_id=player.player_id,
        card_id=card.id,
        ability_name="Quick Search",
        display_label="Quick Search - Search deck for any card"
    )]


def pidgeot_ex_quick_search_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Pidgeot ex's "Quick Search" ability effect.

    Search your deck for a card and put it into your hand. Then, shuffle your deck.

    Args:
        state: Current game state
        card: Pidgeot ex CardInstance
        action: Ability action

    Returns:
        Modified GameState with SearchDeckStep pushed
    """
    player = state.get_player(action.player_id)

    # Mark as used globally (no other Quick Search can be used this turn)
    state.turn_metadata['quick_search_used'] = True
    card.abilities_used_this_turn.add("Quick Search")

    # Push SearchDeckStep for 1 card (any type - no filter)
    if not player.deck.is_empty():
        search_step = SearchDeckStep(
            source_card_id=card.id,
            source_card_name="Quick Search",
            player_id=player.player_id,
            purpose=SelectionPurpose.SEARCH_TARGET,
            count=1,
            min_count=0,  # "may" - can choose not to take a card
            destination=ZoneType.HAND,
            filter_criteria={},  # No filter - any card can be selected
            shuffle_after=True
        )

        state.push_step(search_step)

    return state


def pidgeot_ex_blustery_wind_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Pidgeot ex's "Blustery Wind" attack.

    Attack: Blustery Wind [CC]
    120 damage. You may discard a Stadium in play.

    If a Stadium is in play, generate two actions:
    - One that deals damage without discarding
    - One that deals damage and discards the Stadium

    Args:
        state: Current game state
        card: Pidgeot ex CardInstance
        player: PlayerState of the attacking player

    Returns:
        List of attack actions
    """
    actions = []

    # Base action - always available (no stadium discard)
    actions.append(Action(
        action_type=ActionType.ATTACK,
        player_id=player.player_id,
        card_id=card.id,
        attack_name="Blustery Wind",
        display_label="Blustery Wind - 120 Dmg",
        parameters={'discard_stadium': False}
    ))

    # If a Stadium is in play, offer option to discard it
    if state.stadium is not None:
        stadium_def = get_card_definition(state.stadium)
        stadium_name = stadium_def.name if stadium_def else "Stadium"

        actions.append(Action(
            action_type=ActionType.ATTACK,
            player_id=player.player_id,
            card_id=card.id,
            attack_name="Blustery Wind",
            display_label=f"Blustery Wind - 120 Dmg (Discard {stadium_name})",
            parameters={'discard_stadium': True}
        ))

    return actions


def pidgeot_ex_blustery_wind_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Pidgeot ex's "Blustery Wind" attack effect.

    Deals 120 damage to opponent's Active Pokémon.
    If the action has 'discard_stadium': True, discard the Stadium in play.

    Args:
        state: Current game state
        card: Pidgeot ex CardInstance
        action: Attack action

    Returns:
        Modified GameState
    """
    opponent = state.get_opponent()

    # Deal 120 damage to opponent's Active Pokémon
    if opponent.board.active_spot:
        final_damage = calculate_damage(
            state=state,
            attacker=card,
            defender=opponent.board.active_spot,
            base_damage=120,
            attack_name="Blustery Wind"
        )

        state = apply_damage(
            state=state,
            target=opponent.board.active_spot,
            damage=final_damage,
            is_attack_damage=True,
            attacker=card
        )

    # Discard Stadium if requested
    if action.parameters and action.parameters.get('discard_stadium', False):
        if state.stadium is not None:
            # Move Stadium to its owner's discard pile
            stadium_card = state.stadium
            owner = state.get_player(stadium_card.owner_id)
            owner.discard.add_card(stadium_card)
            state.stadium = None

    return state


# ============================================================================
# SV3 LOGIC REGISTRY (Unified Schema)
# ============================================================================

SV3_LOGIC = {
    # Charmander - Version 1 reprint (Heat Tackle from svp)
    "sv3-26": {
        "Heat Tackle": {
            "category": "attack",
            "generator": charmander_heat_tackle_actions,
            "effect": charmander_heat_tackle_effect,
        },
    },

    # Charmeleon - Version 1 (Heat Tackle)
    "sv3-27": {
        "Heat Tackle": {
            "category": "attack",
            "generator": charmeleon_heat_tackle_actions,
            "effect": charmeleon_heat_tackle_effect,
        },
    },

    # Pidgey - Version 1 (Gust)
    "sv3-162": {
        "Gust": {
            "category": "attack",
            "generator": pidgey_gust_actions,
            "effect": pidgey_gust_effect,
        },
    },
    "sv3-207": {
        "Gust": {
            "category": "attack",
            "generator": pidgey_gust_actions,
            "effect": pidgey_gust_effect,
        },
    },

    # Charizard ex - Version 4 (Infernal Reign + Burning Darkness)
    "sv3-125": {
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
    "sv3-215": {
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
    "sv3-223": {
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
    "sv3-228": {
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

    # Pidgeot ex - Quick Search + Blustery Wind
    "sv3-164": {
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
    "sv3-217": {
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
    "sv3-225": {
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

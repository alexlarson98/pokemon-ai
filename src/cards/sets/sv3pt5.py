"""
Pokémon TCG Engine - 151 Card Logic
Set Code: MEW (sv3pt5)

This module contains card-specific logic for the 151 set.
"""

from typing import List
from models import GameState, CardInstance, Action, ActionType, PlayerState, Subtype
from actions import apply_damage, calculate_damage, shuffle_deck
from cards.utils import get_deck_search_candidates, resolve_search_target
from cards.factory import get_card_definition


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
# PIDGEY - VERSION 2: CALL FOR FAMILY & TACKLE (sv3pt5-16)
# ============================================================================

def pidgey_call_for_family_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Pidgey's "Call for Family" attack.

    Attack: Call for Family [C]
    Search your deck for up to 2 Basic Pokémon and put them onto your Bench.
    Then, shuffle your deck.

    Args:
        state: Current game state
        card: Pidgey CardInstance
        player: PlayerState of the attacking player

    Returns:
        List of attack actions with search target options
    """
    actions = []

    # Check bench space - attack requires bench space to be legal
    bench_space = player.board.max_bench_size - player.board.get_bench_count()
    if bench_space <= 0:
        # No bench space - attack cannot be used
        return []

    if player.deck.is_empty():
        # Empty deck - can still use attack
        return [Action(
            action_type=ActionType.ATTACK,
            player_id=player.player_id,
            card_id=card.id,
            attack_name="Call for Family",
            parameters={'target_pokemon_ids': []},
            display_label="Call for Family (deck empty)"
        )]

    # Define criteria for Basic Pokémon
    def is_basic(card_def):
        return card_def and hasattr(card_def, 'subtypes') and Subtype.BASIC in card_def.subtypes

    # Get searchable candidates
    candidate_names = get_deck_search_candidates(state, player, is_basic)

    if not candidate_names:
        # No valid targets - can still use attack (fail to find)
        return [Action(
            action_type=ActionType.ATTACK,
            player_id=player.player_id,
            card_id=card.id,
            attack_name="Call for Family",
            parameters={'target_pokemon_ids': []},
            display_label="Call for Family (find nothing)"
        )]

    # Map candidate names to actual deck cards
    from itertools import combinations

    deck_cards_by_name = {}
    for card_name in candidate_names:
        matching_cards = [
            c for c in player.deck.cards
            if get_card_definition(c) and get_card_definition(c).name == card_name
            and is_basic(get_card_definition(c))
        ]
        if matching_cards:
            deck_cards_by_name[card_name] = matching_cards

    # Option to find nothing (player may choose to fail)
    actions.append(Action(
        action_type=ActionType.ATTACK,
        player_id=player.player_id,
        card_id=card.id,
        attack_name="Call for Family",
        parameters={'target_pokemon_ids': []},
        display_label="Call for Family (find nothing)"
    ))

    # Generate single search actions
    for card_name, deck_cards in deck_cards_by_name.items():
        if deck_cards:
            target_card = deck_cards[0]
            actions.append(Action(
                action_type=ActionType.ATTACK,
                player_id=player.player_id,
                card_id=card.id,
                attack_name="Call for Family",
                parameters={'target_pokemon_ids': [target_card.id]},
                display_label=f"Call for Family ({card_name})"
            ))

    # Generate pair search actions (if bench has space for 2)
    if bench_space >= 2:
        # Get all unique card instances (one per name)
        all_cards = [(name, cards[0]) for name, cards in deck_cards_by_name.items() if cards]

        for pair in combinations(all_cards, 2):
            (name1, card1), (name2, card2) = pair
            sorted_names = sorted([name1, name2])
            actions.append(Action(
                action_type=ActionType.ATTACK,
                player_id=player.player_id,
                card_id=card.id,
                attack_name="Call for Family",
                parameters={'target_pokemon_ids': [card1.id, card2.id]},
                display_label=f"Call for Family ({sorted_names[0]}, {sorted_names[1]})"
            ))

        # Also allow searching for 2 of the same Pokémon if multiple copies exist
        for card_name, deck_cards in deck_cards_by_name.items():
            if len(deck_cards) >= 2:
                actions.append(Action(
                    action_type=ActionType.ATTACK,
                    player_id=player.player_id,
                    card_id=card.id,
                    attack_name="Call for Family",
                    parameters={'target_pokemon_ids': [deck_cards[0].id, deck_cards[1].id]},
                    display_label=f"Call for Family ({card_name}, {card_name})"
                ))

    return actions


def pidgey_call_for_family_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Pidgey's "Call for Family" attack effect.

    Search your deck for up to 2 Basic Pokémon and put them onto your Bench.
    Then, shuffle your deck.

    Args:
        state: Current game state
        card: Pidgey CardInstance
        action: Attack action with target_pokemon_ids parameter

    Returns:
        Modified GameState
    """
    player = state.get_player(action.player_id)

    # Get target Pokémon IDs from action parameters
    target_ids = action.parameters.get('target_pokemon_ids', [])

    # Put each target onto the bench
    for target_id in target_ids:
        # Resolve the target (handles both regular and belief-based IDs)
        def is_basic(card_def):
            return card_def and hasattr(card_def, 'subtypes') and Subtype.BASIC in card_def.subtypes

        target_card = resolve_search_target(player, target_id, is_basic)

        if target_card and player.board.get_bench_count() < player.board.max_bench_size:
            # Remove from deck
            player.deck.remove_card(target_card.id)
            # Add to bench
            player.board.add_to_bench(target_card)

    # Shuffle deck after search
    state = shuffle_deck(state, player.player_id)

    return state


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
}

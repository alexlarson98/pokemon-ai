"""
Shared Trainer Card Logic Library

This module contains reusable trainer effect implementations.
Each function follows the standard signature:
    def card_name_effect(state: GameState, card: CardInstance, action: Action) -> GameState

Action generators follow the signature:
    def card_name_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]
"""

from typing import List, Tuple
from itertools import combinations  # Used by Ultra Ball and Rare Candy
from models import GameState, CardInstance, Action, ActionType, Subtype, PlayerState
from actions import shuffle_deck, evolve_pokemon
from cards.factory import get_card_definition
from cards.base import PokemonCard


# ============================================================================
# BUDDY-BUDDY POFFIN
# ============================================================================

def buddy_buddy_poffin_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Buddy-Buddy Poffin - Search deck for specific Basic Pokemon (Atomic Execution).

    Expects action.parameters['target_pokemon_ids'] to contain the IDs of the 
    cards chosen by the player/agent during the atomic action generation phase.

    Args:
        state: Current game state
        card: The Buddy-Buddy Poffin card being played
        action: Action containing 'target_pokemon_ids' in parameters

    Returns:
        Modified GameState
    """
    player = state.get_player(action.player_id)
    target_ids = action.parameters.get('target_pokemon_ids', [])

    # Validate we aren't exceeding bench limits (engine should prevent this, but safety first)
    bench_space = player.board.max_bench_size - player.board.get_bench_count()
    if len(target_ids) > bench_space:
        # Truncate list if bench became full since action generation
        target_ids = target_ids[:bench_space]

    # Retrieve specific cards from deck
    cards_to_bench = []

    # We iterate a copy of the deck to safely modify it later
    # Note: We look for specific IDs because the atomic action selected specific instances
    for target_id in target_ids:
        # Find the card in the deck by ID
        found_card = next((c for c in player.deck.cards if c.id == target_id), None)

        if found_card:
            cards_to_bench.append(found_card)
        else:
            # This handles the rare "Theory vs Reality" desync where the AI thought
            # a card was there (Prized logic error) but it wasn't.
            # In a perfect engine, this branch is never hit.
            print(f"Warning: Atomic target {target_id} not found in deck.")

    # Execute the move
    for deck_card in cards_to_bench:
        player.deck.remove_card(deck_card.id)
        player.board.add_to_bench(deck_card)
        # Initialize Pokemon state
        deck_card.turns_in_play = 0

    # Shuffle deck
    state = shuffle_deck(state, action.player_id)

    return state


# ============================================================================
# RARE CANDY
# ============================================================================

def rare_candy_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Rare Candy - Evolve a Basic Pokemon directly to Stage 2 (skip Stage 1).
    """
    target_pokemon_id = action.parameters.get('target_pokemon_id')
    evolution_card_id = action.parameters.get('evolution_card_id')

    if not target_pokemon_id or not evolution_card_id:
        raise ValueError("Rare Candy requires target_pokemon_id and evolution_card_id in action.parameters")

    # Use the existing evolve_pokemon function with skip_stage=True
    state = evolve_pokemon(
        state=state,
        player_id=action.player_id,
        target_pokemon_id=target_pokemon_id,
        evolution_card_id=evolution_card_id,
        skip_stage=True  # Allow Basic -> Stage 2
    )

    return state


# ============================================================================
# ULTRA BALL
# ============================================================================

def ultra_ball_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Ultra Ball - Discard 2 cards, then search deck for 1 Pokemon.
    
    Current Implementation:
    - Atomic Discard: action.parameters['discard_ids'] handles the cost.
    - Search: Currently assumes a secondary step or parameters. 
      (Note: If Ultra Ball search becomes fully atomic later, logic goes here).
    """
    player = state.get_player(action.player_id)

    discard_ids = action.parameters.get('discard_ids', [])
    search_target_id = action.parameters.get('search_target_id')

    if len(discard_ids) != 2:
        raise ValueError("Ultra Ball requires exactly 2 card IDs in discard_ids parameter")

    # Discard 2 cards from hand
    for card_id in discard_ids:
        discarded_card = player.hand.remove_card(card_id)
        if discarded_card:
            player.discard.add_card(discarded_card)
        else:
            raise ValueError(f"Card {card_id} not found in hand for discard")

    # Search for Pokemon (Atomic if provided, otherwise generic flow)
    if search_target_id:
        target_card = next((c for c in player.deck.cards if c.id == search_target_id), None)

        if target_card:
            card_def = get_card_definition(target_card)
            # Verify it's a Pokemon
            if isinstance(card_def, PokemonCard):
                player.deck.remove_card(target_card.id)
                player.hand.add_card(target_card)

    # Shuffle deck
    state = shuffle_deck(state, action.player_id)

    return state


# ============================================================================
# NEST BALL
# ============================================================================

def nest_ball_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Nest Ball - Search deck for 1 Basic Pokemon, put it on bench (Atomic Execution).

    Expects action.parameters['target_pokemon_id'] from the atomic action.
    This respects the atomic choice made during action generation.
    """
    player = state.get_player(action.player_id)
    target_pokemon_id = action.parameters.get('target_pokemon_id')

    # Bench space check
    if player.board.get_bench_count() >= player.board.max_bench_size:
        # Even if played, if bench is full, effect fails (or shouldn't have been playable)
        return state

    if target_pokemon_id:
        # Atomic execution: Retrieve the specific card chosen by the action
        target_card = next((c for c in player.deck.cards if c.id == target_pokemon_id), None)

        if target_card:
            # Validate the card still exists and is a Basic Pokemon
            card_def = get_card_definition(target_card)
            if (isinstance(card_def, PokemonCard) and
                hasattr(card_def, 'subtypes') and Subtype.BASIC in card_def.subtypes):

                # Execute the atomic choice
                player.deck.remove_card(target_card.id)
                player.board.add_to_bench(target_card)
                target_card.turns_in_play = 0
            else:
                # Card no longer valid (shouldn't happen, but safety check)
                print(f"Warning: Nest Ball target {target_pokemon_id} is not a valid Basic Pokemon")
        else:
            # Card not found in deck (Theory vs Reality desync)
            print(f"Warning: Nest Ball target {target_pokemon_id} not found in deck")

    # Shuffle deck
    state = shuffle_deck(state, action.player_id)

    return state


# ============================================================================
# IONO
# ============================================================================

def iono_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Iono - Both players shuffle hand and put on bottom of deck, then draw cards equal to remaining prizes.
    """
    import random

    # Process both players
    for player in state.players:
        # Shuffle hand cards
        hand_cards = player.hand.cards.copy()

        # Remove cards from hand
        for hand_card in hand_cards:
            player.hand.remove_card(hand_card.id)

        # Shuffle the hand cards before putting them on bottom
        random.shuffle(hand_cards)

        # Put shuffled hand cards on BOTTOM of deck
        for hand_card in hand_cards:
            player.deck.cards.append(hand_card)  # Add to bottom

        # Draw cards equal to remaining prizes
        remaining_prizes = player.prizes.count()
        cards_to_draw = min(remaining_prizes, player.deck.count())

        for _ in range(cards_to_draw):
            if not player.deck.is_empty():
                drawn_card = player.deck.cards.pop(0)  # Draw from top
                player.hand.add_card(drawn_card)

    return state


# ============================================================================
# ACTION GENERATORS (Eager Action Generation)
# ============================================================================

def rare_candy_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate all valid Rare Candy actions.

    Finds all valid (Basic Pokemon, Stage 2) pairs and creates an action for each.

    Args:
        state: Current game state
        card: The Rare Candy card
        player: Player who owns the card

    Returns:
        List of Action objects with parameters and display_label populated
    """
    actions = []

    # Get all Pokemon on board (active + bench)
    board_pokemon = player.board.get_all_pokemon()

    # Get all Stage 2 Pokemon in hand
    stage2_cards = []
    for hand_card in player.hand.cards:
        if hand_card.id == card.id:
            continue  # Skip the Rare Candy itself
        card_def = get_card_definition(hand_card)
        if (isinstance(card_def, PokemonCard) and
            hasattr(card_def, 'subtypes') and Subtype.STAGE_2 in card_def.subtypes):
            stage2_cards.append((hand_card, card_def))

    # Find valid pairs
    for target_pokemon in board_pokemon:
        # Check evolution sickness (must have been in play for at least 1 turn)
        if target_pokemon.turns_in_play == 0:
            continue

        target_def = get_card_definition(target_pokemon)

        # Check if it's a Basic Pokemon
        if not (hasattr(target_def, 'subtypes') and Subtype.BASIC in target_def.subtypes):
            continue

        # Find Stage 2 cards that can evolve from this Basic
        for stage2_card, stage2_def in stage2_cards:
            # Check if the Stage 2 evolves from this Basic
            # Note: We need to check the evolution chain - Stage 2 lists the Stage 1 it evolves from
            # But Rare Candy allows skipping, so we need to verify the Stage 2 is in the right line
            # For now, we'll use a simplified check based on name matching
            if hasattr(stage2_def, 'evolves_from'):
                # TODO: Proper evolution chain validation
                # For now, create action for all Stage 2 cards (engine will validate)
                actions.append(Action(
                    action_type=ActionType.PLAY_ITEM,
                    player_id=player.player_id,
                    card_id=card.id,
                    parameters={
                        'target_pokemon_id': target_pokemon.id,
                        'evolution_card_id': stage2_card.id
                    },
                    display_label=f"Rare Candy: Evolve {target_def.name} into {stage2_def.name}"
                ))

    return actions


def ultra_ball_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate all valid Ultra Ball actions.

    Creates an action for every possible pair of cards to discard.

    Args:
        state: Current game state
        card: The Ultra Ball card
        player: Player who owns the card

    Returns:
        List of Action objects with parameters and display_label populated
    """
    actions = []

    # Get all cards in hand except Ultra Ball itself
    discardable_cards = [c for c in player.hand.cards if c.id != card.id]

    # Need at least 2 cards to discard
    if len(discardable_cards) < 2:
        return actions

    # Generate all possible pairs of cards to discard
    for discard_pair in combinations(discardable_cards, 2):
        card1, card2 = discard_pair

        # Get card names for display
        card1_def = get_card_definition(card1)
        card2_def = get_card_definition(card2)
        card1_name = card1_def.name if card1_def and hasattr(card1_def, 'name') else card1.card_id
        card2_name = card2_def.name if card2_def and hasattr(card2_def, 'name') else card2.card_id

        actions.append(Action(
            action_type=ActionType.PLAY_ITEM,
            player_id=player.player_id,
            card_id=card.id,
            parameters={
                'discard_ids': [card1.id, card2.id]
            },
            display_label=f"Ultra Ball (Discard {card1_name}, {card2_name})"
        ))

    return actions


def buddy_buddy_poffin_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate Buddy-Buddy Poffin actions (Atomic Search Actions).

    Creates actions for searching 1 or 2 Basic Pokémon with HP ≤ 70.
    Uses the Knowledge Layer to respect belief-based action generation.

    Args:
        state: Current game state
        card: The Buddy-Buddy Poffin card
        player: Player who owns the card

    Returns:
        List of Actions for single and double searches
    """
    from ..utils import generate_search_actions

    # Define search criteria: Basic Pokémon with HP ≤ 70
    def is_basic_hp_70_or_less(card_def):
        return (hasattr(card_def, 'subtypes') and Subtype.BASIC in card_def.subtypes and
                hasattr(card_def, 'hp') and card_def.hp <= 70)

    # Use the shared utility to generate actions (count=2 for single + pair actions)
    return generate_search_actions(
        state=state,
        player=player,
        card=card,
        criteria=is_basic_hp_70_or_less,
        count=2,
        label_template="Buddy-Buddy Poffin (Search {names})",
        parameter_key='target_pokemon_ids'
    )


def nest_ball_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate Nest Ball actions (Atomic Search Actions).

    Creates one action per searchable Basic Pokémon in the deck.
    Uses the Knowledge Layer to respect belief-based action generation.

    Args:
        state: Current game state
        card: The Nest Ball card
        player: Player who owns the card

    Returns:
        List of Actions, one per searchable Basic Pokémon
    """
    from ..utils import generate_search_actions

    # Define search criteria: Basic Pokémon
    def is_basic(card_def):
        return hasattr(card_def, 'subtypes') and Subtype.BASIC in card_def.subtypes

    # Use the shared utility to generate actions
    return generate_search_actions(
        state=state,
        player=player,
        card=card,
        criteria=is_basic,
        count=1,
        label_template="Nest Ball (Search {name})",
        parameter_key='target_pokemon_id'
    )


def iono_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate Iono action.

    Always returns a single action (Iono is always playable).

    Args:
        state: Current game state
        card: The Iono card
        player: Player who owns the card

    Returns:
        List with single Action
    """
    return [Action(
        action_type=ActionType.PLAY_SUPPORTER,
        player_id=player.player_id,
        card_id=card.id,
        display_label="Iono"
    )]

"""
Shared Trainer Card Logic Library

This module contains reusable trainer effect implementations.
Each function follows the standard signature:
    def card_name_effect(state: GameState, card: CardInstance, action: Action) -> GameState

Action generators follow the signature:
    def card_name_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]
"""

from typing import List, Tuple
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
    Ultra Ball - Discard 2 cards, then search deck for 1 Pokemon (Atomic Execution).

    Expects action.parameters to contain:
    - 'discard_ids': List of 2 card IDs to discard
    - 'search_target_id': Card ID to search for (or None for "fail search")

    Args:
        state: Current game state
        card: The Ultra Ball card being played
        action: Action containing 'discard_ids' and 'search_target_id' in parameters

    Returns:
        Modified GameState
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

    # Search for Pokemon (atomic choice from action generation)
    if search_target_id:
        target_card = next((c for c in player.deck.cards if c.id == search_target_id), None)

        if target_card:
            card_def = get_card_definition(target_card)
            # Verify it's a Pokemon
            if isinstance(card_def, PokemonCard):
                player.deck.remove_card(target_card.id)
                player.hand.add_card(target_card)
            else:
                # Card exists but isn't a Pokemon (shouldn't happen with proper action generation)
                print(f"Warning: Ultra Ball target {search_target_id} is not a Pokemon")
        else:
            # Card not found in deck (Theory vs Reality desync)
            print(f"Warning: Ultra Ball target {search_target_id} not found in deck")
    # If search_target_id is None, this is a "fail search" action (discard only)

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
    Generate all valid Rare Candy actions (Atomic Evolution Actions).

    Finds all valid (Basic Pokemon, Stage 2) pairs and creates an action for each.
    Uses the evolution action utility to eliminate boilerplate.

    Args:
        state: Current game state
        card: The Rare Candy card
        player: Player who owns the card

    Returns:
        List of Action objects with parameters and display_label populated
    """
    from ..utils import generate_evolution_actions

    return generate_evolution_actions(
        state=state,
        player=player,
        card=card,
        target_subtype=Subtype.BASIC,
        evolution_subtype=Subtype.STAGE_2,
        label_template="Rare Candy: Evolve {target} into {evolution}",
        skip_stage=True
    )


def ultra_ball_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate all valid Ultra Ball actions (Atomic Discard + Search Actions).

    Creates actions for every unique discard pair × search target combination.

    De-duplication: Groups cards by name to avoid duplicate actions for multiple
    copies of the same card (e.g., 2x Gimmighoul creates only 1 discard pair).

    Atomic Search: Includes search target in the action upfront for MCTS.

    Args:
        state: Current game state
        card: The Ultra Ball card
        player: Player who owns the card

    Returns:
        List of Action objects with parameters and display_label populated
    """
    from ..utils import get_deck_search_candidates
    from collections import defaultdict

    actions = []

    # Get all cards in hand except Ultra Ball itself
    discardable_cards = [c for c in player.hand.cards if c.id != card.id]

    # Need at least 2 cards to discard
    if len(discardable_cards) < 2:
        return actions

    # Group cards by name for de-duplication
    cards_by_name = defaultdict(list)
    for c in discardable_cards:
        card_def = get_card_definition(c)
        card_name = card_def.name if card_def and hasattr(card_def, 'name') else c.card_id
        cards_by_name[card_name].append(c)

    # Get unique card names
    card_names = sorted(cards_by_name.keys())

    # Generate unique discard pairs (by name)
    unique_discard_pairs = []
    for i, name1 in enumerate(card_names):
        # Same card name twice (if we have 2+ copies)
        if len(cards_by_name[name1]) >= 2:
            unique_discard_pairs.append((name1, name1))

        # Different card names
        for name2 in card_names[i+1:]:
            unique_discard_pairs.append((name1, name2))

    # Get search candidates using Knowledge Layer (any Pokemon)
    def is_pokemon(card_def):
        return isinstance(card_def, PokemonCard)

    search_candidates = get_deck_search_candidates(state, player, is_pokemon)

    # Map search candidate names to actual card instances in deck
    deck_cards_by_name = {}
    for card_name in search_candidates:
        matching_cards = [
            c for c in player.deck.cards
            if get_card_definition(c).name == card_name
        ]
        if matching_cards:
            deck_cards_by_name[card_name] = matching_cards

    # Generate cartesian product: discard pairs × search targets
    for discard_name1, discard_name2 in unique_discard_pairs:
        # Get actual card instances for this discard pair
        discard_card1 = cards_by_name[discard_name1][0]
        discard_card2 = cards_by_name[discard_name2][1 if discard_name1 == discard_name2 else 0]

        # Format discard display (sorted for consistency)
        if discard_name1 == discard_name2:
            discard_display = f"{discard_name1}, {discard_name2}"
        else:
            sorted_names = sorted([discard_name1, discard_name2])
            discard_display = f"{sorted_names[0]}, {sorted_names[1]}"

        # Option 1: Fail search (discard only, no search target)
        actions.append(Action(
            action_type=ActionType.PLAY_ITEM,
            player_id=player.player_id,
            card_id=card.id,
            parameters={
                'discard_ids': [discard_card1.id, discard_card2.id],
                'search_target_id': None
            },
            display_label=f"Ultra Ball (Discard {discard_display} → Fail Search)"
        ))

        # Options 2+: Search for each candidate
        for search_name in search_candidates:
            search_cards = deck_cards_by_name.get(search_name, [])
            if search_cards:
                search_target = search_cards[0]

                actions.append(Action(
                    action_type=ActionType.PLAY_ITEM,
                    player_id=player.player_id,
                    card_id=card.id,
                    parameters={
                        'discard_ids': [discard_card1.id, discard_card2.id],
                        'search_target_id': search_target.id
                    },
                    display_label=f"Ultra Ball (Discard {discard_display} → Search {search_name})"
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
        List of Actions for single and double searches, plus fail search option
    """
    from ..utils import generate_search_actions

    actions = []

    # Check bench space
    bench_space = player.board.max_bench_size - player.board.get_bench_count()

    if bench_space <= 0 or player.deck.is_empty():
        return actions

    # Define search criteria: Basic Pokémon with HP ≤ 70
    def is_basic_hp_70_or_less(card_def):
        return (hasattr(card_def, 'subtypes') and Subtype.BASIC in card_def.subtypes and
                hasattr(card_def, 'hp') and card_def.hp <= 70)

    # Use the shared utility to generate actions (count=2 for single + pair actions)
    actions = generate_search_actions(
        state=state,
        player=player,
        card=card,
        criteria=is_basic_hp_70_or_less,
        count=2,
        label_template="Buddy-Buddy Poffin (Search {names})",
        parameter_key='target_pokemon_ids'
    )

    # Add "fail search" option (no targets selected)
    actions.append(Action(
        action_type=ActionType.PLAY_ITEM,
        player_id=player.player_id,
        card_id=card.id,
        parameters={'target_pokemon_ids': []},
        display_label="Buddy-Buddy Poffin (Fail Search)"
    ))

    return actions


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
        List of Actions, one per searchable Basic Pokémon, plus fail search option
    """
    from ..utils import generate_search_actions

    actions = []

    # Check bench space
    bench_space = player.board.max_bench_size - player.board.get_bench_count()

    if bench_space <= 0 or player.deck.is_empty():
        return actions

    # Define search criteria: Basic Pokémon
    def is_basic(card_def):
        return hasattr(card_def, 'subtypes') and Subtype.BASIC in card_def.subtypes

    # Use the shared utility to generate actions
    actions = generate_search_actions(
        state=state,
        player=player,
        card=card,
        criteria=is_basic,
        count=1,
        label_template="Nest Ball (Search {name})",
        parameter_key='target_pokemon_id'
    )

    # Add "fail search" option (no target selected)
    actions.append(Action(
        action_type=ActionType.PLAY_ITEM,
        player_id=player.player_id,
        card_id=card.id,
        parameters={'target_pokemon_id': None},
        display_label="Nest Ball (Fail Search)"
    ))

    return actions


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

"""
Shared Trainer Card Logic Library

This module contains reusable trainer effect implementations.
Each function follows the standard signature:
    def card_name_effect(state: GameState, card: CardInstance, action: Action) -> GameState

Action generators follow the signature:
    def card_name_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]

Key Design Principles:
1. Reprints Problem: Logic is written ONCE and imported by multiple sets
2. State Immutability: All operations return modified GameState
3. Action Parameters: Complex inputs passed via action.parameters dict
4. Eager Action Generation: Generators create fully-populated actions upfront
5. Validation: Caller (engine/set file) validates playability before calling
"""

from typing import List, Tuple
from itertools import combinations
from models import GameState, CardInstance, Action, ActionType, Subtype, Supertype, PlayerState
from actions import shuffle_deck, evolve_pokemon
from cards.factory import get_card_definition


# ============================================================================
# BUDDY-BUDDY POFFIN
# ============================================================================

def buddy_buddy_poffin_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Buddy-Buddy Poffin - Search deck for up to 2 Basic Pokemon with HP <= 70, bench them.

    Playability Requirements (checked by caller):
    - Deck is not empty
    - Bench is not full (has at least 1 open spot)

    Effect:
    1. Search deck for up to 2 Basic Pokemon with HP <= 70
    2. Put them directly onto the bench
    3. Shuffle deck

    Args:
        state: Current game state
        card: The Buddy-Buddy Poffin card being played
        action: Action containing player_id and parameters

    Returns:
        Modified GameState
    """
    player = state.get_player(action.player_id)

    # Search deck for Basic Pokemon with HP <= 70
    matching_cards = []
    for deck_card in player.deck.cards:
        card_def = get_card_definition(deck_card)

        # Check if it's a Basic Pokemon with HP <= 70
        if (hasattr(card_def, 'supertype') and card_def.supertype == Supertype.POKEMON and
            hasattr(card_def, 'subtypes') and Subtype.BASIC in card_def.subtypes and
            hasattr(card_def, 'hp') and card_def.hp <= 70):
            matching_cards.append(deck_card)

    # Take up to 2 cards (limited by bench space)
    bench_space = player.board.max_bench_size - player.board.get_bench_count()
    num_to_take = min(2, len(matching_cards), bench_space)

    found_cards = matching_cards[:num_to_take]

    # Remove from deck and add to bench
    for deck_card in found_cards:
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

    Playability Requirements (checked by caller):
    - At least one Basic Pokemon on board with turns_in_play >= 1
    - At least one Stage 2 card in hand that evolves from that Basic

    Effect:
    1. Evolve target Basic Pokemon to Stage 2 (skip Stage 1)

    Required action.parameters:
    - 'target_pokemon_id': ID of the Basic Pokemon to evolve
    - 'evolution_card_id': ID of the Stage 2 card in hand

    Args:
        state: Current game state
        card: The Rare Candy card being played
        action: Action containing player_id and parameters

    Returns:
        Modified GameState
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

    Playability Requirements (checked by caller):
    - Hand size >= 3 (2 to discard + Ultra Ball itself)

    Effect:
    1. Discard 2 cards from hand (specified in action.parameters)
    2. Search deck for 1 Pokemon card
    3. Add to hand
    4. Shuffle deck

    Required action.parameters:
    - 'discard_ids': List of 2 card instance IDs to discard
    - 'search_target_id': ID of Pokemon card to search for (if choosing to find)

    Args:
        state: Current game state
        card: The Ultra Ball card being played
        action: Action containing player_id and parameters

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

    # Search for Pokemon (player may choose to fail search)
    if search_target_id:
        # Find the target card in deck
        target_card = None
        for deck_card in player.deck.cards:
            if deck_card.id == search_target_id:
                card_def = get_card_definition(deck_card)
                # Verify it's a Pokemon
                if hasattr(card_def, 'supertype') and card_def.supertype == Supertype.POKEMON:
                    target_card = deck_card
                    break

        if target_card:
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
    Nest Ball - Search deck for 1 Basic Pokemon, put it on bench.

    Playability Requirements (checked by caller):
    - Bench is not full

    Effect:
    1. Search deck for 1 Basic Pokemon
    2. Put it directly onto bench
    3. Shuffle deck

    Required action.parameters:
    - 'search_target_id': ID of Basic Pokemon to search for (if choosing to find)

    Args:
        state: Current game state
        card: The Nest Ball card being played
        action: Action containing player_id and parameters

    Returns:
        Modified GameState
    """
    player = state.get_player(action.player_id)

    search_target_id = action.parameters.get('search_target_id')

    # Search for Basic Pokemon (player may choose to fail search)
    if search_target_id:
        # Find the target card in deck
        target_card = None
        for deck_card in player.deck.cards:
            if deck_card.id == search_target_id:
                card_def = get_card_definition(deck_card)
                # Verify it's a Basic Pokemon
                if (hasattr(card_def, 'supertype') and card_def.supertype == Supertype.POKEMON and
                    hasattr(card_def, 'subtypes') and Subtype.BASIC in card_def.subtypes):
                    target_card = deck_card
                    break

        if target_card:
            player.deck.remove_card(target_card.id)
            player.board.add_to_bench(target_card)
            # Initialize Pokemon state
            target_card.turns_in_play = 0

    # Shuffle deck
    state = shuffle_deck(state, action.player_id)

    return state


# ============================================================================
# IONO
# ============================================================================

def iono_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Iono - Both players shuffle hand into deck, then draw cards equal to remaining prizes.

    Playability Requirements (checked by caller):
    - None (always playable)

    Effect:
    1. Both players shuffle their hand into their deck
    2. Both players draw cards equal to their remaining prize count

    Args:
        state: Current game state
        card: The Iono card being played
        action: Action containing player_id

    Returns:
        Modified GameState
    """
    # Process both players
    for player in state.players:
        # Shuffle hand into deck
        hand_cards = player.hand.cards.copy()
        for hand_card in hand_cards:
            player.hand.remove_card(hand_card.id)
            player.deck.add_card(hand_card)

        # Shuffle deck
        state = shuffle_deck(state, player.player_id)

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
        if (hasattr(card_def, 'supertype') and card_def.supertype == Supertype.POKEMON and
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
    Generate Buddy-Buddy Poffin action.

    Returns a single action if bench has space (search targets chosen during resolution).

    Args:
        state: Current game state
        card: The Buddy-Buddy Poffin card
        player: Player who owns the card

    Returns:
        List with single Action if playable, empty list otherwise
    """
    actions = []

    # Check if bench has space
    bench_space = player.board.max_bench_size - player.board.get_bench_count()

    if bench_space > 0 and not player.deck.is_empty():
        actions.append(Action(
            action_type=ActionType.PLAY_ITEM,
            player_id=player.player_id,
            card_id=card.id,
            display_label="Buddy-Buddy Poffin"
        ))

    return actions


def nest_ball_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate Nest Ball action.

    Returns a single action if bench has space (search target chosen during resolution).

    Args:
        state: Current game state
        card: The Nest Ball card
        player: Player who owns the card

    Returns:
        List with single Action if playable, empty list otherwise
    """
    actions = []

    # Check if bench has space
    bench_space = player.board.max_bench_size - player.board.get_bench_count()

    if bench_space > 0 and not player.deck.is_empty():
        actions.append(Action(
            action_type=ActionType.PLAY_ITEM,
            player_id=player.player_id,
            card_id=card.id,
            display_label="Nest Ball"
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

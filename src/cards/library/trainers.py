"""
Shared Trainer Card Logic Library

This module contains reusable trainer effect implementations using the
Stack-based Resolution Architecture for optimal MCTS branching factor.

Each effect function follows the signature:
    def card_name_effect(state: GameState, card: CardInstance, action: Action) -> GameState

Action generators follow the signature:
    def card_name_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]
"""

from typing import List
from models import (
    GameState, CardInstance, Action, ActionType, Subtype, PlayerState,
    SearchDeckStep, ZoneType, SelectionPurpose
)
from cards.factory import get_card_definition
from cards.base import PokemonCard


# ============================================================================
# BUDDY-BUDDY POFFIN
# ============================================================================

def buddy_buddy_poffin_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate Buddy-Buddy Poffin action using the Stack architecture.

    Generates a SINGLE action that initiates the resolution stack.
    The actual selection happens through SearchDeckStep.

    Branching Factor: 1 (initial) + N choices (sequential)
    """
    if player.board.get_bench_count() >= player.board.max_bench_size:
        return []

    return [Action(
        action_type=ActionType.PLAY_ITEM,
        player_id=player.player_id,
        card_id=card.id,
        parameters={'use_stack': True},
        display_label="Buddy-Buddy Poffin (search up to 2 Basic HP<=70)"
    )]


def buddy_buddy_poffin_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Buddy-Buddy Poffin Effect - Push search step onto the stack.

    Stack Sequence:
    1. SearchDeckStep: Search deck for up to 2 Basic Pokemon with HP <= 70
       - Pokemon go directly to bench
       - Deck is shuffled after
    """
    from models import SearchDeckStep, ZoneType, SelectionPurpose

    player = state.get_player(action.player_id)

    bench_space = player.board.max_bench_size - player.board.get_bench_count()
    max_search = min(2, bench_space)

    search_step = SearchDeckStep(
        source_card_id=card.id,
        source_card_name="Buddy-Buddy Poffin",
        player_id=player.player_id,
        purpose=SelectionPurpose.SEARCH_TARGET,
        count=max_search,
        min_count=0,
        destination=ZoneType.BENCH,
        filter_criteria={
            'supertype': 'Pokemon',
            'subtype': 'Basic',
            'max_hp': 70
        },
        shuffle_after=True
    )

    state.push_step(search_step)
    return state


# ============================================================================
# RARE CANDY
# ============================================================================

def rare_candy_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate Rare Candy action using the Stack architecture.

    Generates a SINGLE action that initiates the resolution stack.
    The actual selection happens through SelectFromZoneStep.

    Branching Factor: 1 (initial) + N basics + M stage2s (sequential)

    Note: Rare Candy cannot be played on the first turn (turn_count == 1).
    """
    from cards.utils import find_stage_2_chain_for_basic, get_valid_basics_for_rare_candy

    # Rare Candy cannot be played on turn 1
    if state.turn_count <= 1:
        return []

    valid_basics = get_valid_basics_for_rare_candy(state, player)
    if not valid_basics:
        return []

    has_valid_stage_2 = False
    for hand_card in player.hand.cards:
        if hand_card.id == card.id:
            continue
        hand_def = get_card_definition(hand_card)
        if hand_def and hasattr(hand_def, 'subtypes') and Subtype.STAGE_2 in hand_def.subtypes:
            for basic_pokemon in valid_basics:
                basic_def = get_card_definition(basic_pokemon)
                if basic_def and find_stage_2_chain_for_basic(basic_def, hand_def):
                    has_valid_stage_2 = True
                    break
        if has_valid_stage_2:
            break

    if not has_valid_stage_2:
        return []

    return [Action(
        action_type=ActionType.PLAY_ITEM,
        player_id=player.player_id,
        card_id=card.id,
        parameters={'use_stack': True},
        display_label="Rare Candy (select Basic -> Stage 2)"
    )]


def rare_candy_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Rare Candy Effect - Push resolution steps onto the stack.

    Stack Sequence:
    1. SelectFromZoneStep: Select Basic Pokemon from bench
    2. SelectFromZoneStep: Select Stage 2 from hand (filtered by chosen Basic)
    3. EvolveTargetStep: Execute the evolution
    """
    from models import SelectFromZoneStep, ZoneType, SelectionPurpose

    player = state.get_player(action.player_id)

    select_basic_step = SelectFromZoneStep(
        source_card_id=card.id,
        source_card_name="Rare Candy",
        player_id=player.player_id,
        purpose=SelectionPurpose.EVOLUTION_BASE,
        zone=ZoneType.BOARD,  # Can target Active or Bench
        count=1,
        exact_count=True,
        filter_criteria={
            'supertype': 'Pokemon',
            'subtype': 'Basic',
            'rare_candy_target': True
        },
        on_complete_callback="rare_candy_select_evolution"
    )

    state.push_step(select_basic_step)
    return state


# ============================================================================
# ULTRA BALL
# ============================================================================

def ultra_ball_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate Ultra Ball action using the Stack architecture.

    Generates a SINGLE action that initiates the resolution stack.
    The actual selections happen through SelectFromZoneStep and SearchDeckStep.

    Branching Factor: 1 (initial) + D discards + S search targets (sequential)
    """
    discardable_cards = [c for c in player.hand.cards if c.id != card.id]
    if len(discardable_cards) < 2:
        return []

    return [Action(
        action_type=ActionType.PLAY_ITEM,
        player_id=player.player_id,
        card_id=card.id,
        parameters={'use_stack': True},
        display_label="Ultra Ball (discard 2 -> search Pokemon)"
    )]


def ultra_ball_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Ultra Ball Effect - Push resolution steps onto the stack.

    Stack Sequence:
    1. SelectFromZoneStep: Select 2 cards from hand to discard
       - Callback pushes SearchDeckStep after discards are confirmed
    2. SearchDeckStep: Search deck for any Pokemon
    """
    from models import SelectFromZoneStep, ZoneType, SelectionPurpose

    player = state.get_player(action.player_id)

    select_discard_step = SelectFromZoneStep(
        source_card_id=card.id,
        source_card_name="Ultra Ball",
        player_id=player.player_id,
        purpose=SelectionPurpose.DISCARD_COST,
        zone=ZoneType.HAND,
        count=2,
        exact_count=True,
        min_count=2,
        filter_criteria={},
        exclude_card_ids=[card.id],
        on_complete_callback="ultra_ball_search"
    )

    state.push_step(select_discard_step)
    return state


# ============================================================================
# NEST BALL
# ============================================================================

def nest_ball_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate Nest Ball action using the Stack architecture.

    Generates a SINGLE action that initiates the resolution stack.
    The actual selection happens through SearchDeckStep.

    Branching Factor: 1 (initial) + N search targets (sequential)
    """
    if player.board.get_bench_count() >= player.board.max_bench_size:
        return []

    return [Action(
        action_type=ActionType.PLAY_ITEM,
        player_id=player.player_id,
        card_id=card.id,
        parameters={'use_stack': True},
        display_label="Nest Ball (search Basic Pokemon)"
    )]


def nest_ball_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Nest Ball Effect - Push search step onto the stack.

    Stack Sequence:
    1. SearchDeckStep: Search deck for a Basic Pokemon
       - Pokemon goes directly to bench
       - Deck is shuffled after
    """
    from models import SearchDeckStep, ZoneType, SelectionPurpose

    player = state.get_player(action.player_id)

    search_step = SearchDeckStep(
        source_card_id=card.id,
        source_card_name="Nest Ball",
        player_id=player.player_id,
        purpose=SelectionPurpose.SEARCH_TARGET,
        count=1,
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
# IONO
# ============================================================================

def iono_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate Iono action.

    Always returns a single action (Iono is always playable).
    """
    return [Action(
        action_type=ActionType.PLAY_SUPPORTER,
        player_id=player.player_id,
        card_id=card.id,
        display_label="Iono"
    )]


def iono_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Iono - Both players shuffle hand and put on bottom of deck,
    then draw cards equal to remaining prizes.
    """
    import random

    for player in state.players:
        hand_cards = player.hand.cards.copy()

        for hand_card in hand_cards:
            player.hand.remove_card(hand_card.id)

        random.shuffle(hand_cards)

        for hand_card in hand_cards:
            player.deck.cards.append(hand_card)

        remaining_prizes = player.prizes.count()
        cards_to_draw = min(remaining_prizes, player.deck.count())

        for _ in range(cards_to_draw):
            if not player.deck.is_empty():
                drawn_card = player.deck.cards.pop(0)
                player.hand.add_card(drawn_card)

    return state


# ============================================================================
# PROFESSOR'S RESEARCH
# ============================================================================

def professors_research_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate Professor's Research action.

    Professor's Research is always playable (discarding 0 cards is valid).
    """
    return [Action(
        action_type=ActionType.PLAY_SUPPORTER,
        player_id=player.player_id,
        card_id=card.id,
        display_label="Professor's Research (discard hand, draw 7)"
    )]


def professors_research_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Professor's Research - Discard your hand and draw 7 cards.

    Simple effect with no user choices - just discard everything and draw 7.
    """
    player = state.get_player(action.player_id)

    # Discard entire hand (excluding the Professor's Research card itself, already played)
    hand_cards = player.hand.cards.copy()
    for hand_card in hand_cards:
        player.hand.remove_card(hand_card.id)
        player.discard.add_card(hand_card)

    # Draw 7 cards
    cards_to_draw = min(7, player.deck.count())
    for _ in range(cards_to_draw):
        if not player.deck.is_empty():
            drawn_card = player.deck.cards.pop(0)
            player.hand.add_card(drawn_card)

    return state


# ============================================================================
# DAWN - SUPPORTER (me2-87, me2-118, me2-129)
# ============================================================================

def dawn_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Dawn supporter card.

    Dawn: Search your deck for a Basic Pokemon, a Stage 1 Pokemon, and a
    Stage 2 Pokemon, reveal them, and put them into your hand. Then, shuffle
    your deck.

    Args:
        state: Current game state
        card: Dawn CardInstance
        player: PlayerState of the player

    Returns:
        List with single action to play Dawn
    """
    # Dawn is always playable (can fail to find any/all of the Pokemon)
    return [Action(
        action_type=ActionType.PLAY_SUPPORTER,
        player_id=player.player_id,
        card_id=card.id,
        display_label="Dawn (search Basic + Stage 1 + Stage 2)"
    )]


def dawn_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Dawn supporter effect.

    Search your deck for a Basic Pokemon, a Stage 1 Pokemon, and a Stage 2
    Pokemon, reveal them, and put them into your hand. Then, shuffle your deck.

    Uses Stack Architecture with 3 sequential SearchDeckStep calls.
    Steps are pushed in reverse order (LIFO) so they resolve:
    1. Search for Basic Pokemon
    2. Search for Stage 1 Pokemon
    3. Search for Stage 2 Pokemon (with shuffle_after=True)

    Args:
        state: Current game state
        card: Dawn CardInstance
        action: Play supporter action

    Returns:
        Modified GameState with search steps pushed
    """
    player = state.get_player(action.player_id)

    # Push steps in reverse order (LIFO - last pushed = first resolved)

    # Step 3: Search for Stage 2 Pokemon (shuffle after this one)
    search_stage2_step = SearchDeckStep(
        source_card_id=card.id,
        source_card_name="Dawn",
        player_id=player.player_id,
        purpose=SelectionPurpose.SEARCH_TARGET,
        count=1,
        min_count=0,  # Can fail to find
        destination=ZoneType.HAND,
        filter_criteria={
            'supertype': 'Pokemon',
            'subtype': 'Stage 2'
        },
        shuffle_after=True,  # Shuffle after the final search
        reveal_cards=True
    )
    state.push_step(search_stage2_step)

    # Step 2: Search for Stage 1 Pokemon
    search_stage1_step = SearchDeckStep(
        source_card_id=card.id,
        source_card_name="Dawn",
        player_id=player.player_id,
        purpose=SelectionPurpose.SEARCH_TARGET,
        count=1,
        min_count=0,  # Can fail to find
        destination=ZoneType.HAND,
        filter_criteria={
            'supertype': 'Pokemon',
            'subtype': 'Stage 1'
        },
        shuffle_after=False,  # Don't shuffle yet
        reveal_cards=True
    )
    state.push_step(search_stage1_step)

    # Step 1: Search for Basic Pokemon (first to resolve)
    search_basic_step = SearchDeckStep(
        source_card_id=card.id,
        source_card_name="Dawn",
        player_id=player.player_id,
        purpose=SelectionPurpose.SEARCH_TARGET,
        count=1,
        min_count=0,  # Can fail to find
        destination=ZoneType.HAND,
        filter_criteria={
            'supertype': 'Pokemon',
            'subtype': 'Basic'
        },
        shuffle_after=False,  # Don't shuffle yet
        reveal_cards=True
    )
    state.push_step(search_basic_step)

    return state
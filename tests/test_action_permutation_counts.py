"""
Comprehensive pytest suite for action permutation count validation.

Tests that the number of generated actions matches the expected mathematical
permutation calculations. This ensures:
1. No duplicate actions are generated
2. No valid actions are missing
3. Deduplication by functional ID (card_id) works correctly
4. Functional ID grouping for search targets works correctly

IMPORTANT: Tests use card IDs (card_id like 'sv3pt5-16') and instance IDs
(like 'card_abc123') for validation, NOT card names. This ensures:
- Same-name cards with different card_ids are treated as distinct
- Multiple copies of same card_id are properly grouped

Formula for Ultra Ball:
- Discard pairs: C(n_unique_card_ids, 2) + count of card_ids with 2+ copies
- Search targets: count of unique functional IDs (Pokemon in deck) + 1 (fail search)
- Before deck search: search targets include belief placeholders
- After deck search: search targets are only actual deck contents

Total actions = discard_pairs × search_targets

NOTE: Tests verify action counts against mathematical expectations,
ensuring the action generation is correct and complete.
"""

import pytest
import sys
from math import comb  # C(n, k) = n! / (k! * (n-k)!)
from collections import Counter
sys.path.insert(0, 'src')

from models import GameState, PlayerState, GamePhase
from engine import PokemonEngine
from cards.factory import create_card_instance
from cards.library.trainers import ultra_ball_actions, nest_ball_actions, buddy_buddy_poffin_actions
from cards.registry import create_card
from cards.base import Subtype, PokemonCard


# =============================================================================
# ID-BASED HELPER FUNCTIONS
# =============================================================================

def get_action_target_ids(action, parameter_key='target_pokemon_ids'):
    """
    Extract target card instance IDs from an action's parameters.

    Args:
        action: Action object
        parameter_key: Key to look for in parameters (default: 'target_pokemon_ids')

    Returns:
        List of target card instance IDs, or empty list if none
    """
    params = action.parameters or {}

    # Handle list parameters (like target_pokemon_ids)
    if parameter_key in params:
        value = params[parameter_key]
        if isinstance(value, list):
            return value
        return [value] if value else []

    # Handle single ID parameters (like target_pokemon_id)
    single_key = parameter_key.rstrip('s')  # target_pokemon_ids -> target_pokemon_id
    if single_key in params:
        value = params[single_key]
        return [value] if value else []

    return []


def get_action_target_card_ids(action, deck_cards, parameter_key='target_pokemon_ids'):
    """
    Get the card_ids (like 'sv3pt5-16') for targets in an action.

    Args:
        action: Action object
        deck_cards: List of CardInstance objects in deck
        parameter_key: Key to look for in parameters

    Returns:
        List of card_ids for the targets, sorted for comparison
    """
    instance_ids = get_action_target_ids(action, parameter_key)

    # Build instance_id -> card_id mapping
    id_to_card_id = {card.id: card.card_id for card in deck_cards}

    result = []
    for inst_id in instance_ids:
        if inst_id.startswith('belief:'):
            # Belief placeholder - keep as-is
            result.append(inst_id)
        elif inst_id in id_to_card_id:
            result.append(id_to_card_id[inst_id])
        else:
            result.append(inst_id)  # Unknown, keep as-is

    return sorted(result)


def get_unique_action_target_sets(actions, deck_cards, parameter_key='target_pokemon_ids'):
    """
    Get all unique target card_id sets from a list of actions.

    Args:
        actions: List of Action objects
        deck_cards: List of CardInstance objects in deck
        parameter_key: Key to look for in parameters

    Returns:
        Set of frozensets, each representing a unique target combination by card_id
    """
    unique_sets = set()
    for action in actions:
        card_ids = get_action_target_card_ids(action, deck_cards, parameter_key)
        unique_sets.add(frozenset(card_ids))
    return unique_sets


def build_instance_to_card_id_map(cards):
    """
    Build a mapping from card instance IDs to card_ids.

    Args:
        cards: List of CardInstance objects

    Returns:
        Dict mapping instance_id -> card_id
    """
    return {card.id: card.card_id for card in cards}


def get_cards_by_card_id(cards):
    """
    Group card instances by their card_id.

    Args:
        cards: List of CardInstance objects

    Returns:
        Dict mapping card_id -> list of CardInstance objects
    """
    result = {}
    for card in cards:
        if card.card_id not in result:
            result[card.card_id] = []
        result[card.card_id].append(card)
    return result


def count_cards_by_card_id(cards):
    """
    Count cards by their card_id.

    Args:
        cards: List of CardInstance objects

    Returns:
        Counter mapping card_id -> count
    """
    return Counter(card.card_id for card in cards)


# =============================================================================
# HELPER FUNCTIONS FOR PERMUTATION CALCULATIONS
# =============================================================================

def calculate_discard_pair_count(hand_cards_by_card_id: dict) -> int:
    """
    Calculate the number of unique discard pairs for Ultra Ball.

    Ultra Ball requires discarding 2 cards. The game deduplicates by card_id,
    so multiple copies of the same card_id count as one discard option unless
    you're discarding two of the same card_id.

    Formula:
    - C(n_unique_card_ids, 2): pairs of different card_ids
    - Plus: count of card_ids with 2+ copies (can discard two of the same)

    Args:
        hand_cards_by_card_id: Dict mapping card_id -> count of that card in hand

    Returns:
        Number of unique discard pair combinations
    """
    unique_card_ids = list(hand_cards_by_card_id.keys())
    n = len(unique_card_ids)

    # Pairs of different card_ids: C(n, 2)
    different_pairs = comb(n, 2) if n >= 2 else 0

    # Pairs of same card_id (need 2+ copies)
    same_pairs = sum(1 for count in hand_cards_by_card_id.values() if count >= 2)

    return different_pairs + same_pairs


def calculate_search_target_count(
    deck_pokemon_by_functional_id: dict,
    has_searched_deck: bool,
    belief_candidates: list = None
) -> int:
    """
    Calculate the number of unique search targets for Ultra Ball.

    Search targets are grouped by functional ID (card_id), so multiple copies
    of the exact same card count as one search option.

    Before searching deck:
    - Includes belief placeholders for cards believed to be in deck
    - These are cards from initial deck that aren't visible elsewhere

    After searching deck:
    - Only actual deck contents (player has perfect knowledge)

    Plus 1 for fail search option.

    Args:
        deck_pokemon_by_functional_id: Dict mapping functional_id -> list of cards
        has_searched_deck: Whether player has searched deck (perfect knowledge)
        belief_candidates: List of card names from belief system (before search)

    Returns:
        Number of unique search target options (including fail search)
    """
    actual_targets = len(deck_pokemon_by_functional_id)

    # Belief-based targets only apply before searching
    if not has_searched_deck and belief_candidates:
        # Add belief candidates that aren't already in deck
        actual_names = set()
        for cards in deck_pokemon_by_functional_id.values():
            for card in cards:
                card_def = create_card(card.card_id)
                if card_def:
                    actual_names.add(card_def.name)

        belief_only = [name for name in belief_candidates if name not in actual_names]
        actual_targets += len(belief_only)

    # Plus 1 for fail search
    return actual_targets + 1


def calculate_ultra_ball_action_count(
    hand_cards_by_card_id: dict,
    deck_pokemon_by_functional_id: dict,
    has_searched_deck: bool = False,
    belief_candidates: list = None
) -> int:
    """
    Calculate the total expected Ultra Ball action count.

    Total = discard_pairs × search_targets

    Args:
        hand_cards_by_card_id: Dict mapping card_id -> count (excluding Ultra Ball)
        deck_pokemon_by_functional_id: Dict mapping functional_id -> list of cards
        has_searched_deck: Whether player has searched deck
        belief_candidates: List of card_ids from belief system

    Returns:
        Expected total number of Ultra Ball actions
    """
    discard_pairs = calculate_discard_pair_count(hand_cards_by_card_id)
    search_targets = calculate_search_target_count(
        deck_pokemon_by_functional_id,
        has_searched_deck,
        belief_candidates
    )

    return discard_pairs * search_targets


def get_hand_cards_by_card_id(player, exclude_instance_id=None):
    """
    Get a dict of card_id -> count for cards in hand.

    Uses card_id (like 'sv3pt5-16') to group cards, NOT card names.
    This ensures same-name cards with different card_ids are counted separately.

    Args:
        player: Player state
        exclude_instance_id: Instance ID to exclude (e.g., the Ultra Ball being played)

    Returns:
        Dict mapping card_id -> count
    """
    cards_by_card_id = Counter()
    for card in player.hand.cards:
        if exclude_instance_id and card.id == exclude_instance_id:
            continue
        cards_by_card_id[card.card_id] += 1
    return dict(cards_by_card_id)


def get_deck_pokemon_by_functional_id(player):
    """Get a dict of functional_id -> list of Pokemon cards in deck."""
    from cards.base import PokemonCard
    result = {}
    for card in player.deck.cards:
        card_def = create_card(card.card_id)
        if card_def and isinstance(card_def, PokemonCard):
            functional_id = player.functional_id_map.get(card.card_id, card.card_id)
            if functional_id not in result:
                result[functional_id] = []
            result[functional_id].append(card)
    return result


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def engine():
    """Create PokemonEngine instance."""
    return PokemonEngine()


# =============================================================================
# TEST CLASS: Ultra Ball Permutation Validation
# =============================================================================

class TestUltraBallPermutationCounts:
    """Test that Ultra Ball generates the correct number of actions."""

    def test_basic_permutation_count(self, engine):
        """
        Test basic Ultra Ball permutation with simple hand and deck.

        Setup:
        - Hand: Ultra Ball + 3 unique cards (A, B, C)
        - Deck: 2 unique Pokemon (P1, P2)

        Expected:
        - Discard pairs: C(3,2) = 3 pairs (A+B, A+C, B+C)
        - Search targets: 2 Pokemon + 1 fail = 3
        - Total: 3 × 3 = 9 actions
        """
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        # Ultra Ball in hand
        ultra_ball = create_card_instance("sv1-196", owner_id=0)
        player0.hand.add_card(ultra_ball)

        # 3 unique discard cards (non-Pokemon to keep it simple)
        player0.hand.add_card(create_card_instance("sv1-196", owner_id=0))  # Another Ultra Ball
        player0.hand.add_card(create_card_instance("sv1-181", owner_id=0))  # Nest Ball
        player0.hand.add_card(create_card_instance("sv3pt5-144", owner_id=0))  # Poffin

        # 2 unique Pokemon in deck
        player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))  # Pidgey
        player0.deck.add_card(create_card_instance("sv4pt5-7", owner_id=0))   # Charmander

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        # Mark as searched to avoid belief placeholders
        player.has_searched_deck = True

        actions = ultra_ball_actions(state, ultra_ball, player)

        # Calculate expected count
        hand_by_card_id = get_hand_cards_by_card_id(player, exclude_instance_id=ultra_ball.id)
        deck_by_fid = get_deck_pokemon_by_functional_id(player)

        expected_discard_pairs = calculate_discard_pair_count(hand_by_card_id)
        expected_search_targets = calculate_search_target_count(deck_by_fid, has_searched_deck=True)
        expected_total = expected_discard_pairs * expected_search_targets

        assert len(actions) == expected_total, \
            f"Expected {expected_total} actions ({expected_discard_pairs} discard pairs × {expected_search_targets} targets), got {len(actions)}"

    def test_duplicate_cards_in_hand(self, engine):
        """
        Test Ultra Ball with duplicate cards in hand.

        Setup:
        - Hand: Ultra Ball + 2x CardA + 1x CardB
        - Deck: 1 Pokemon

        Expected:
        - Unique names: 2 (CardA, CardB)
        - Discard pairs: C(2,2) + 1 (CardA has 2+ copies) = 1 + 1 = 2
        - Search targets: 1 Pokemon + 1 fail = 2
        - Total: 2 × 2 = 4 actions
        """
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        ultra_ball = create_card_instance("sv1-196", owner_id=0)
        player0.hand.add_card(ultra_ball)

        # 2x Nest Ball (same name)
        player0.hand.add_card(create_card_instance("sv1-181", owner_id=0))
        player0.hand.add_card(create_card_instance("sv1-181", owner_id=0))
        # 1x Poffin (different name)
        player0.hand.add_card(create_card_instance("sv3pt5-144", owner_id=0))

        # 1 Pokemon in deck
        player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]
        player.has_searched_deck = True

        actions = ultra_ball_actions(state, ultra_ball, player)

        hand_by_card_id = get_hand_cards_by_card_id(player, exclude_instance_id=ultra_ball.id)
        deck_by_fid = get_deck_pokemon_by_functional_id(player)

        expected_discard_pairs = calculate_discard_pair_count(hand_by_card_id)
        expected_search_targets = calculate_search_target_count(deck_by_fid, has_searched_deck=True)
        expected_total = expected_discard_pairs * expected_search_targets

        # Verify our calculation matches expectation
        # hand_by_card_id should be: {"Nest Ball": 2, "Buddy-Buddy Poffin": 1}
        # discard_pairs: C(2,2) + 1 = 1 + 1 = 2
        assert expected_discard_pairs == 2, f"Expected 2 discard pairs, calculated {expected_discard_pairs}"
        assert expected_search_targets == 2, f"Expected 2 search targets, calculated {expected_search_targets}"
        assert len(actions) == expected_total, \
            f"Expected {expected_total} actions, got {len(actions)}"

    def test_multiple_same_name_pokemon_in_deck(self, engine):
        """
        Test Ultra Ball with multiple Pokemon of the same name but different card IDs.

        Setup:
        - Hand: Ultra Ball + 2 discard cards
        - Deck: 2x Charmander (sv4pt5-7), 1x Charmander (me2-11), 1x Pidgey

        Expected (with functional ID grouping):
        - Discard pairs: C(2,2) = 1
        - Search targets: 3 functional IDs (sv4pt5-7, me2-11, sv3pt5-16) + 1 fail = 4
        - Total: 1 × 4 = 4 actions

        Note: The two sv4pt5-7 Charmanders share a functional ID, but me2-11 has
        a different functional ID even though it's also named "Charmander".
        """
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        ultra_ball = create_card_instance("sv1-196", owner_id=0)
        player0.hand.add_card(ultra_ball)

        # 2 discard cards with different names
        player0.hand.add_card(create_card_instance("sv1-181", owner_id=0))
        player0.hand.add_card(create_card_instance("sv3pt5-144", owner_id=0))

        # Deck: 2x same Charmander + 1x different Charmander + 1x Pidgey
        player0.deck.add_card(create_card_instance("sv4pt5-7", owner_id=0))   # Charmander A
        player0.deck.add_card(create_card_instance("sv4pt5-7", owner_id=0))   # Charmander A (same)
        player0.deck.add_card(create_card_instance("me2-11", owner_id=0))     # Charmander B (different set)
        player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))  # Pidgey

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]
        player.has_searched_deck = True

        actions = ultra_ball_actions(state, ultra_ball, player)

        hand_by_card_id = get_hand_cards_by_card_id(player, exclude_instance_id=ultra_ball.id)
        deck_by_fid = get_deck_pokemon_by_functional_id(player)

        expected_discard_pairs = calculate_discard_pair_count(hand_by_card_id)
        expected_search_targets = calculate_search_target_count(deck_by_fid, has_searched_deck=True)
        expected_total = expected_discard_pairs * expected_search_targets

        # Verify functional ID grouping is correct
        # Should have 3 functional IDs: sv4pt5-7, me2-11, sv3pt5-16
        assert len(deck_by_fid) == 3, \
            f"Expected 3 functional IDs, got {len(deck_by_fid)}: {list(deck_by_fid.keys())}"

        assert len(actions) == expected_total, \
            f"Expected {expected_total} actions, got {len(actions)}"

    def test_before_vs_after_deck_search(self, engine):
        """
        Test that action count changes after searching deck (perfect knowledge).

        Setup:
        - Hand: Ultra Ball + 2 discard cards
        - Deck: 1 Pidgey
        - Prizes: 1 Klefki (hidden)
        - Initial deck knowledge: Klefki in initial_deck_counts

        Before searching:
        - Belief system thinks Klefki might be in deck
        - Search targets: Pidgey + Klefki (belief) + fail = 3

        After searching:
        - Perfect knowledge: only Pidgey actually in deck
        - Search targets: Pidgey + fail = 2
        """
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        ultra_ball = create_card_instance("sv1-196", owner_id=0)
        player0.hand.add_card(ultra_ball)

        # 2 discard cards
        player0.hand.add_card(create_card_instance("sv1-181", owner_id=0))
        player0.hand.add_card(create_card_instance("sv3pt5-144", owner_id=0))

        # 1 Pokemon in deck
        player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))  # Pidgey

        # 1 Pokemon in prizes (hidden - belief system doesn't know it's not in deck)
        klefki = create_card_instance("sv1-96", owner_id=0)
        player0.prizes.add_card(klefki)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        # BEFORE searching deck (imperfect knowledge)
        player.has_searched_deck = False
        actions_before = ultra_ball_actions(state, ultra_ball, player)

        # AFTER searching deck (perfect knowledge)
        player.has_searched_deck = True
        actions_after = ultra_ball_actions(state, ultra_ball, player)

        # Calculate expected counts
        hand_by_card_id = get_hand_cards_by_card_id(player, exclude_instance_id=ultra_ball.id)
        discard_pairs = calculate_discard_pair_count(hand_by_card_id)

        # Before: belief system includes Klefki
        # After: only actual deck contents
        deck_by_fid = get_deck_pokemon_by_functional_id(player)

        # Expected search targets before (with belief): Pidgey + Klefki + fail = 3
        # Expected search targets after (perfect): Pidgey + fail = 2

        # Verify that actions_before > actions_after (belief adds more options)
        assert len(actions_before) > len(actions_after), \
            f"Before search should have more actions due to beliefs. Before: {len(actions_before)}, After: {len(actions_after)}"

        # Verify after search count is correct
        expected_after = discard_pairs * (len(deck_by_fid) + 1)  # +1 for fail search
        assert len(actions_after) == expected_after, \
            f"After search: expected {expected_after} actions, got {len(actions_after)}"

    def test_large_hand_permutation_count(self, engine):
        """
        Test Ultra Ball with a large hand (8 cards).

        Setup:
        - Hand: Ultra Ball + 7 unique cards
        - Deck: 3 unique Pokemon

        Expected:
        - Discard pairs: C(7,2) = 21
        - Search targets: 3 Pokemon + 1 fail = 4
        - Total: 21 × 4 = 84 actions
        """
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        ultra_ball = create_card_instance("sv1-196", owner_id=0)
        player0.hand.add_card(ultra_ball)

        # 7 unique discard cards (use different trainer cards)
        unique_cards = [
            "sv1-181",   # Nest Ball
            "sv3pt5-144", # Buddy-Buddy Poffin
            "sv1-196",   # Ultra Ball (another copy)
            "sv1-191",   # Rare Candy
            "sv5-162",   # Ultra Ball (different set)
            "sv5-163",   # Energy card
            "sv5-191",   # Energy card (different)
        ]
        for card_id in unique_cards:
            player0.hand.add_card(create_card_instance(card_id, owner_id=0))

        # 3 unique Pokemon in deck
        player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))  # Pidgey
        player0.deck.add_card(create_card_instance("sv4pt5-7", owner_id=0))   # Charmander
        player0.deck.add_card(create_card_instance("sv1-96", owner_id=0))     # Klefki

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]
        player.has_searched_deck = True

        actions = ultra_ball_actions(state, ultra_ball, player)

        hand_by_card_id = get_hand_cards_by_card_id(player, exclude_instance_id=ultra_ball.id)
        deck_by_fid = get_deck_pokemon_by_functional_id(player)

        expected_discard_pairs = calculate_discard_pair_count(hand_by_card_id)
        expected_search_targets = calculate_search_target_count(deck_by_fid, has_searched_deck=True)
        expected_total = expected_discard_pairs * expected_search_targets

        assert len(actions) == expected_total, \
            f"Expected {expected_total} actions ({expected_discard_pairs} × {expected_search_targets}), got {len(actions)}"

    def test_all_duplicates_in_hand(self, engine):
        """
        Test Ultra Ball when hand has multiple copies of the same cards.

        Setup:
        - Hand: Ultra Ball + 2x CardA + 2x CardB
        - Deck: 1 Pokemon

        Expected:
        - Unique names: 2 (CardA, CardB)
        - Discard pairs: C(2,2) + 2 (both have 2+ copies) = 1 + 2 = 3
          - A+A, B+B, A+B
        - Search targets: 1 Pokemon + 1 fail = 2
        - Total: 3 × 2 = 6 actions
        """
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        ultra_ball = create_card_instance("sv1-196", owner_id=0)
        player0.hand.add_card(ultra_ball)

        # 2x Nest Ball
        player0.hand.add_card(create_card_instance("sv1-181", owner_id=0))
        player0.hand.add_card(create_card_instance("sv1-181", owner_id=0))
        # 2x Poffin
        player0.hand.add_card(create_card_instance("sv3pt5-144", owner_id=0))
        player0.hand.add_card(create_card_instance("sv3pt5-144", owner_id=0))

        # 1 Pokemon in deck
        player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]
        player.has_searched_deck = True

        actions = ultra_ball_actions(state, ultra_ball, player)

        hand_by_card_id = get_hand_cards_by_card_id(player, exclude_instance_id=ultra_ball.id)
        deck_by_fid = get_deck_pokemon_by_functional_id(player)

        expected_discard_pairs = calculate_discard_pair_count(hand_by_card_id)
        expected_search_targets = calculate_search_target_count(deck_by_fid, has_searched_deck=True)
        expected_total = expected_discard_pairs * expected_search_targets

        # Verify our formula
        assert expected_discard_pairs == 3, \
            f"Expected 3 discard pairs (A+A, B+B, A+B), calculated {expected_discard_pairs}"

        assert len(actions) == expected_total, \
            f"Expected {expected_total} actions, got {len(actions)}"

    def test_empty_deck_permutation(self, engine):
        """
        Test Ultra Ball when deck has no Pokemon.

        Setup:
        - Hand: Ultra Ball + 2 discard cards
        - Deck: empty (no Pokemon)

        Expected:
        - Discard pairs: C(2,2) = 1
        - Search targets: 0 Pokemon + 1 fail = 1 (only fail search)
        - Total: 1 × 1 = 1 action
        """
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        ultra_ball = create_card_instance("sv1-196", owner_id=0)
        player0.hand.add_card(ultra_ball)

        # 2 discard cards
        player0.hand.add_card(create_card_instance("sv1-181", owner_id=0))
        player0.hand.add_card(create_card_instance("sv3pt5-144", owner_id=0))

        # Empty deck (no Pokemon)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]
        player.has_searched_deck = True

        actions = ultra_ball_actions(state, ultra_ball, player)

        # Should only have fail search actions
        expected_discard_pairs = 1  # C(2,2) = 1
        expected_total = expected_discard_pairs * 1  # Only fail search

        assert len(actions) == expected_total, \
            f"Expected {expected_total} action (only fail search), got {len(actions)}"

    def test_insufficient_discard_cards(self, engine):
        """
        Test Ultra Ball when hand doesn't have enough cards to discard.

        Setup:
        - Hand: Ultra Ball + 1 card (need 2)

        Expected:
        - 0 actions (cannot play Ultra Ball)
        """
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        ultra_ball = create_card_instance("sv1-196", owner_id=0)
        player0.hand.add_card(ultra_ball)

        # Only 1 discard card (need 2)
        player0.hand.add_card(create_card_instance("sv1-181", owner_id=0))

        # Pokemon in deck (but can't search without discarding 2)
        player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        actions = ultra_ball_actions(state, ultra_ball, player)

        assert len(actions) == 0, \
            f"Expected 0 actions (insufficient discard cards), got {len(actions)}"


class TestPermutationFormulas:
    """Unit tests for the permutation calculation helper functions."""

    def test_discard_pair_formula_unique_cards(self):
        """Test discard pair calculation with all unique cards."""
        # 3 unique cards: C(3,2) = 3
        hand = {"A": 1, "B": 1, "C": 1}
        assert calculate_discard_pair_count(hand) == 3

        # 4 unique cards: C(4,2) = 6
        hand = {"A": 1, "B": 1, "C": 1, "D": 1}
        assert calculate_discard_pair_count(hand) == 6

        # 5 unique cards: C(5,2) = 10
        hand = {"A": 1, "B": 1, "C": 1, "D": 1, "E": 1}
        assert calculate_discard_pair_count(hand) == 10

    def test_discard_pair_formula_with_duplicates(self):
        """Test discard pair calculation with duplicate cards."""
        # 2 cards, one with 2 copies: C(2,2) + 1 = 1 + 1 = 2
        hand = {"A": 2, "B": 1}
        assert calculate_discard_pair_count(hand) == 2

        # 2 cards, both with 2 copies: C(2,2) + 2 = 1 + 2 = 3
        hand = {"A": 2, "B": 2}
        assert calculate_discard_pair_count(hand) == 3

        # 3 cards, one with 3 copies: C(3,2) + 1 = 3 + 1 = 4
        hand = {"A": 3, "B": 1, "C": 1}
        assert calculate_discard_pair_count(hand) == 4

    def test_discard_pair_formula_edge_cases(self):
        """Test discard pair edge cases."""
        # 2 unique cards minimum: C(2,2) = 1
        hand = {"A": 1, "B": 1}
        assert calculate_discard_pair_count(hand) == 1

        # 1 card with 2 copies: 0 pairs from C(1,2) + 1 from same = 1
        hand = {"A": 2}
        assert calculate_discard_pair_count(hand) == 1

        # Empty hand: 0 pairs
        hand = {}
        assert calculate_discard_pair_count(hand) == 0

        # 1 card with 1 copy: 0 pairs (can't discard 2)
        hand = {"A": 1}
        assert calculate_discard_pair_count(hand) == 0

    def test_search_target_formula(self):
        """Test search target calculation."""
        # 2 functional IDs + fail = 3
        deck = {"fid1": ["card1"], "fid2": ["card2"]}
        assert calculate_search_target_count(deck, has_searched_deck=True) == 3

        # Empty deck + fail = 1
        deck = {}
        assert calculate_search_target_count(deck, has_searched_deck=True) == 1


# =============================================================================
# HELPER FUNCTIONS FOR NEST BALL / POFFIN PERMUTATION CALCULATIONS
# =============================================================================

def get_deck_pokemon_by_functional_id_with_criteria(player, criteria_func):
    """
    Get a dict of functional_id -> list of Pokemon cards in deck that match criteria.

    Args:
        player: Player state
        criteria_func: Function that takes card_def and returns True if valid

    Returns:
        Dict mapping functional_id -> list of card instances
    """
    result = {}
    for card in player.deck.cards:
        card_def = create_card(card.card_id)
        if card_def and isinstance(card_def, PokemonCard) and criteria_func(card_def):
            functional_id = player.functional_id_map.get(card.card_id, card.card_id)
            if functional_id not in result:
                result[functional_id] = []
            result[functional_id].append(card)
    return result


def calculate_nest_ball_action_count(
    deck_pokemon_by_functional_id: dict,
    has_searched_deck: bool = False,
    belief_candidates: list = None
) -> int:
    """
    Calculate the expected Nest Ball action count.

    Nest Ball: Search for 1 Basic Pokemon
    - Single actions: 1 per functional ID
    - Plus 1 fail search

    Args:
        deck_pokemon_by_functional_id: Dict mapping functional_id -> list of Basic Pokemon
        has_searched_deck: Whether player has searched deck
        belief_candidates: List of card names from belief system

    Returns:
        Expected total number of Nest Ball actions
    """
    actual_targets = len(deck_pokemon_by_functional_id)

    # Belief-based targets only apply before searching
    if not has_searched_deck and belief_candidates:
        # Add belief candidates that aren't already in deck
        actual_names = set()
        for cards in deck_pokemon_by_functional_id.values():
            for card in cards:
                if card:
                    card_def = create_card(card.card_id)
                    if card_def:
                        actual_names.add(card_def.name)

        belief_only = [name for name in belief_candidates if name not in actual_names]
        actual_targets += len(belief_only)

    # Plus 1 for fail search
    return actual_targets + 1


def calculate_poffin_action_count(
    deck_pokemon_by_functional_id: dict,
    bench_space: int,
    has_searched_deck: bool = False,
    belief_candidates: list = None
) -> int:
    """
    Calculate the expected Buddy-Buddy Poffin action count.

    Buddy-Buddy Poffin: Search for up to 2 Basic Pokemon with HP <= 70
    - Single actions: 1 per functional ID (search for just 1)
    - Pair actions (if bench_space >= 2):
      - Different-ID pairs: C(n, 2) = combinations of different functional IDs
      - Same-ID pairs: 1 for each functional ID that has 2+ copies in deck
    - Plus 1 fail search

    Formula:
    - n = number of unique functional IDs (Basic Pokemon with HP <= 70)
    - Single actions: n
    - Different-ID pairs (if bench >= 2): C(n, 2) = n*(n-1)/2
    - Same-ID pairs (if bench >= 2): count of functional IDs with 2+ cards
    - Plus 1 fail search

    Total = n + C(n,2) + same_id_pairs + 1

    Args:
        deck_pokemon_by_functional_id: Dict mapping functional_id -> list of valid Pokemon
        bench_space: Available bench space
        has_searched_deck: Whether player has searched deck
        belief_candidates: List of card names from belief system

    Returns:
        Expected total number of Buddy-Buddy Poffin actions
    """
    n = len(deck_pokemon_by_functional_id)

    # Count functional IDs that have 2+ copies (can form same-ID pairs)
    same_id_pair_count = sum(1 for cards in deck_pokemon_by_functional_id.values() if len(cards) >= 2)

    # Belief-based targets only apply before searching
    belief_only_count = 0
    if not has_searched_deck and belief_candidates:
        # Add belief candidates that aren't already in deck
        actual_names = set()
        for cards in deck_pokemon_by_functional_id.values():
            for card in cards:
                if card:
                    card_def = create_card(card.card_id)
                    if card_def:
                        actual_names.add(card_def.name)

        belief_only = [name for name in belief_candidates if name not in actual_names]
        belief_only_count = len(belief_only)
        n += belief_only_count

    # Single actions: n (one per functional ID or belief candidate)
    single_actions = n

    # Pair actions (if bench space >= 2):
    # - Different-ID pairs: C(n, 2)
    # - Same-ID pairs: count of functional IDs with 2+ cards
    if bench_space >= 2 and n >= 2:
        different_id_pairs = comb(n, 2)
        pair_actions = different_id_pairs + same_id_pair_count
    else:
        pair_actions = 0

    # Plus 1 fail search
    return single_actions + pair_actions + 1


def is_basic_hp_70_or_less(card_def):
    """Criteria function for Buddy-Buddy Poffin: Basic Pokemon with HP <= 70."""
    return (hasattr(card_def, 'subtypes') and Subtype.BASIC in card_def.subtypes and
            hasattr(card_def, 'hp') and card_def.hp <= 70)


def is_basic(card_def):
    """Criteria function for Nest Ball: Basic Pokemon."""
    return hasattr(card_def, 'subtypes') and Subtype.BASIC in card_def.subtypes


# =============================================================================
# TEST CLASS: Nest Ball Permutation Validation
# =============================================================================

class TestNestBallPermutationCounts:
    """Test that Nest Ball generates the correct number of actions."""

    def test_basic_nest_ball_count(self, engine):
        """
        Test basic Nest Ball permutation with unique Basic Pokemon.

        Setup:
        - Deck: 3 unique Basic Pokemon (Pidgey, Charmander, Klefki)

        Expected:
        - Search targets: 3 functional IDs + 1 fail = 4 actions
        """
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        # Nest Ball in hand
        nest_ball = create_card_instance("sv1-181", owner_id=0)
        player0.hand.add_card(nest_ball)

        # 3 unique Basic Pokemon in deck
        player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))  # Pidgey (Basic)
        player0.deck.add_card(create_card_instance("sv4pt5-7", owner_id=0))   # Charmander (Basic)
        player0.deck.add_card(create_card_instance("sv1-96", owner_id=0))     # Klefki (Basic)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]
        player.has_searched_deck = True

        actions = nest_ball_actions(state, nest_ball, player)

        deck_by_fid = get_deck_pokemon_by_functional_id_with_criteria(player, is_basic)
        expected_total = calculate_nest_ball_action_count(deck_by_fid, has_searched_deck=True)

        assert len(actions) == expected_total, \
            f"Expected {expected_total} Nest Ball actions, got {len(actions)}"

    def test_nest_ball_multiple_same_functional_id(self, engine):
        """
        Test Nest Ball with multiple copies of the same functional ID.

        Setup:
        - Deck: 3x Pidgey (sv3pt5-16), 1x Charmander (sv4pt5-7)

        Expected:
        - 2 functional IDs (sv3pt5-16, sv4pt5-7) + 1 fail = 3 actions
        - Multiple Pidgeys should NOT create multiple actions
        """
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        nest_ball = create_card_instance("sv1-181", owner_id=0)
        player0.hand.add_card(nest_ball)

        # 3x same Pidgey + 1x Charmander
        player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))
        player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))
        player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))
        player0.deck.add_card(create_card_instance("sv4pt5-7", owner_id=0))

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]
        player.has_searched_deck = True

        actions = nest_ball_actions(state, nest_ball, player)

        deck_by_fid = get_deck_pokemon_by_functional_id_with_criteria(player, is_basic)

        # Should have exactly 2 functional IDs
        assert len(deck_by_fid) == 2, \
            f"Expected 2 functional IDs, got {len(deck_by_fid)}: {list(deck_by_fid.keys())}"

        expected_total = calculate_nest_ball_action_count(deck_by_fid, has_searched_deck=True)
        assert len(actions) == expected_total, \
            f"Expected {expected_total} actions, got {len(actions)}"

    def test_nest_ball_same_name_different_functional_id(self, engine):
        """
        Test Nest Ball with same-name Pokemon but different functional IDs.

        Setup:
        - Deck: Charmander (sv4pt5-7) HP=70, Charmander (me2-11) HP=60

        Expected:
        - 2 functional IDs (different card_ids) + 1 fail = 3 actions
        - Each Charmander variant gets its own action
        """
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        nest_ball = create_card_instance("sv1-181", owner_id=0)
        player0.hand.add_card(nest_ball)

        # Two Charmanders with different functional IDs
        player0.deck.add_card(create_card_instance("sv4pt5-7", owner_id=0))  # Charmander A
        player0.deck.add_card(create_card_instance("me2-11", owner_id=0))    # Charmander B (different set)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]
        player.has_searched_deck = True

        actions = nest_ball_actions(state, nest_ball, player)

        deck_by_fid = get_deck_pokemon_by_functional_id_with_criteria(player, is_basic)

        # Should have 2 functional IDs (different card_ids)
        assert len(deck_by_fid) == 2, \
            f"Expected 2 functional IDs for different Charmanders, got {len(deck_by_fid)}"

        expected_total = calculate_nest_ball_action_count(deck_by_fid, has_searched_deck=True)
        assert len(actions) == expected_total, \
            f"Expected {expected_total} actions, got {len(actions)}"

    def test_nest_ball_before_vs_after_deck_search(self, engine):
        """
        Test Nest Ball action count changes after searching deck.

        Setup:
        - Deck: 1 Pidgey (Basic)
        - Prizes: 1 Klefki (Basic, hidden)

        Before search: Pidgey + Klefki (belief) + fail = 3
        After search: Pidgey + fail = 2
        """
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        nest_ball = create_card_instance("sv1-181", owner_id=0)
        player0.hand.add_card(nest_ball)

        # 1 Basic in deck
        player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))  # Pidgey

        # 1 Basic in prizes (hidden)
        klefki = create_card_instance("sv1-96", owner_id=0)
        player0.prizes.add_card(klefki)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        # BEFORE searching deck
        player.has_searched_deck = False
        actions_before = nest_ball_actions(state, nest_ball, player)

        # AFTER searching deck
        player.has_searched_deck = True
        actions_after = nest_ball_actions(state, nest_ball, player)

        # Before should have more actions due to belief placeholder
        assert len(actions_before) > len(actions_after), \
            f"Before search should have more actions. Before: {len(actions_before)}, After: {len(actions_after)}"

        # Verify after search count
        deck_by_fid = get_deck_pokemon_by_functional_id_with_criteria(player, is_basic)
        expected_after = calculate_nest_ball_action_count(deck_by_fid, has_searched_deck=True)
        assert len(actions_after) == expected_after, \
            f"After search: expected {expected_after} actions, got {len(actions_after)}"


# =============================================================================
# TEST CLASS: Buddy-Buddy Poffin Permutation Validation
# =============================================================================

class TestBuddyBuddyPoffinPermutationCounts:
    """Test that Buddy-Buddy Poffin generates the correct number of actions."""

    def test_basic_poffin_count(self, engine):
        """
        Test basic Buddy-Buddy Poffin permutation.

        Setup:
        - Deck: 3 unique Basic Pokemon with HP <= 70

        Expected (with bench space >= 2):
        - n = 3 functional IDs
        - Single actions: 3
        - Pair actions: C(3,2) = 3
        - Fail search: 1
        - Total: 3 + 3 + 1 = 7 actions
        """
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        # Poffin in hand
        poffin = create_card_instance("sv3pt5-144", owner_id=0)
        player0.hand.add_card(poffin)

        # 3 unique Basic Pokemon with HP <= 70
        player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))  # Pidgey HP=50
        player0.deck.add_card(create_card_instance("sv4pt5-7", owner_id=0))   # Charmander HP=70
        player0.deck.add_card(create_card_instance("sv1-96", owner_id=0))     # Klefki HP=70

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]
        player.has_searched_deck = True

        actions = buddy_buddy_poffin_actions(state, poffin, player)

        deck_by_fid = get_deck_pokemon_by_functional_id_with_criteria(player, is_basic_hp_70_or_less)
        bench_space = player.board.max_bench_size - player.board.get_bench_count()
        expected_total = calculate_poffin_action_count(deck_by_fid, bench_space, has_searched_deck=True)

        assert len(actions) == expected_total, \
            f"Expected {expected_total} Poffin actions, got {len(actions)}"

    def test_poffin_excludes_high_hp_pokemon(self, engine):
        """
        Test that Poffin excludes Pokemon with HP > 70.

        Setup:
        - Deck: Pidgey HP=50, Charmander HP=70, Charmeleon HP=90 (Stage 1)

        Expected:
        - Only Pidgey and Charmander are valid (HP <= 70 AND Basic)
        - n = 2 functional IDs
        - Single: 2, Pair: C(2,2) = 1, Fail: 1
        - Total: 2 + 1 + 1 = 4 actions
        """
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        poffin = create_card_instance("sv3pt5-144", owner_id=0)
        player0.hand.add_card(poffin)

        # 2 valid + 1 invalid (Stage 1, even if HP was low it wouldn't be Basic)
        player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))  # Pidgey HP=50 (valid)
        player0.deck.add_card(create_card_instance("sv4pt5-7", owner_id=0))   # Charmander HP=70 (valid)
        player0.deck.add_card(create_card_instance("sv3pt5-17", owner_id=0))  # Pidgeotto HP=80 Stage 1 (invalid)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]
        player.has_searched_deck = True

        actions = buddy_buddy_poffin_actions(state, poffin, player)

        deck_by_fid = get_deck_pokemon_by_functional_id_with_criteria(player, is_basic_hp_70_or_less)

        # Should only have 2 valid Pokemon
        assert len(deck_by_fid) == 2, \
            f"Expected 2 valid Pokemon (HP <= 70 & Basic), got {len(deck_by_fid)}"

        bench_space = player.board.max_bench_size - player.board.get_bench_count()
        expected_total = calculate_poffin_action_count(deck_by_fid, bench_space, has_searched_deck=True)

        assert len(actions) == expected_total, \
            f"Expected {expected_total} actions, got {len(actions)}"

    def test_poffin_same_name_different_functional_id(self, engine):
        """
        Test Poffin with same-name Pokemon but different functional IDs.

        Setup:
        - Deck: Capsakid (sv3-23) HP=50, Capsakid (sv3-24) HP=70, Pidgey HP=50
        - Both Capsakids are Basic with HP <= 70 but have different attacks

        Expected:
        - 3 functional IDs (sv3-23, sv3-24, sv3pt5-16)
        - All are Basic with HP <= 70
        - Single: 3, Pair: C(3,2) = 3, Same-ID pairs: 0, Fail: 1
        - Total: 3 + 3 + 0 + 1 = 7 actions
        """
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        poffin = create_card_instance("sv3pt5-144", owner_id=0)
        player0.hand.add_card(poffin)

        # 2 Capsakids with different functional IDs (different attacks) + 1 Pidgey
        player0.deck.add_card(create_card_instance("sv3-23", owner_id=0))     # Capsakid A HP=50
        player0.deck.add_card(create_card_instance("sv3-24", owner_id=0))     # Capsakid B HP=70
        player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))  # Pidgey HP=50

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]
        player.has_searched_deck = True

        actions = buddy_buddy_poffin_actions(state, poffin, player)

        deck_by_fid = get_deck_pokemon_by_functional_id_with_criteria(player, is_basic_hp_70_or_less)

        # Should have 3 functional IDs
        assert len(deck_by_fid) == 3, \
            f"Expected 3 functional IDs, got {len(deck_by_fid)}: {list(deck_by_fid.keys())}"

        bench_space = player.board.max_bench_size - player.board.get_bench_count()
        expected_total = calculate_poffin_action_count(deck_by_fid, bench_space, has_searched_deck=True)

        assert len(actions) == expected_total, \
            f"Expected {expected_total} actions, got {len(actions)}"

    def test_poffin_same_functional_id_multiple_copies(self, engine):
        """
        Test Poffin with multiple copies of same functional ID.

        Setup:
        - Deck: 3x Pidgey (sv3pt5-16), 2x Charmander (sv4pt5-7)

        Expected:
        - Only 2 functional IDs (copies don't multiply actions)
        - Single: 2, Pair: C(2,2) = 1, Fail: 1
        - Total: 2 + 1 + 1 = 4 actions
        """
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        poffin = create_card_instance("sv3pt5-144", owner_id=0)
        player0.hand.add_card(poffin)

        # 3x same Pidgey + 2x same Charmander
        player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))
        player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))
        player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))
        player0.deck.add_card(create_card_instance("sv4pt5-7", owner_id=0))
        player0.deck.add_card(create_card_instance("sv4pt5-7", owner_id=0))

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]
        player.has_searched_deck = True

        actions = buddy_buddy_poffin_actions(state, poffin, player)

        deck_by_fid = get_deck_pokemon_by_functional_id_with_criteria(player, is_basic_hp_70_or_less)

        # Should have exactly 2 functional IDs
        assert len(deck_by_fid) == 2, \
            f"Expected 2 functional IDs (copies deduplicated), got {len(deck_by_fid)}"

        bench_space = player.board.max_bench_size - player.board.get_bench_count()
        expected_total = calculate_poffin_action_count(deck_by_fid, bench_space, has_searched_deck=True)

        assert len(actions) == expected_total, \
            f"Expected {expected_total} actions, got {len(actions)}"

    def test_poffin_before_vs_after_deck_search(self, engine):
        """
        Test Poffin action count changes after searching deck.

        Setup:
        - Deck: Pidgey HP=50, Charmander HP=70
        - Prizes: Klefki HP=70 (hidden, belief system thinks it's in deck)

        Before search:
        - n = 3 (Pidgey + Charmander + Klefki belief)
        - Single: 3, Pair: C(3,2) = 3, Fail: 1
        - Total: 3 + 3 + 1 = 7 actions

        After search:
        - n = 2 (only Pidgey + Charmander)
        - Single: 2, Pair: C(2,2) = 1, Fail: 1
        - Total: 2 + 1 + 1 = 4 actions
        """
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        poffin = create_card_instance("sv3pt5-144", owner_id=0)
        player0.hand.add_card(poffin)

        # 2 valid Pokemon in deck
        player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))  # Pidgey
        player0.deck.add_card(create_card_instance("sv4pt5-7", owner_id=0))   # Charmander

        # 1 valid Pokemon in prizes (hidden)
        klefki = create_card_instance("sv1-96", owner_id=0)  # Klefki HP=70
        player0.prizes.add_card(klefki)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        # BEFORE searching deck
        player.has_searched_deck = False
        actions_before = buddy_buddy_poffin_actions(state, poffin, player)

        # AFTER searching deck
        player.has_searched_deck = True
        actions_after = buddy_buddy_poffin_actions(state, poffin, player)

        # Before should have more actions due to belief placeholder
        assert len(actions_before) > len(actions_after), \
            f"Before search should have more actions. Before: {len(actions_before)}, After: {len(actions_after)}"

        # Verify after search count
        deck_by_fid = get_deck_pokemon_by_functional_id_with_criteria(player, is_basic_hp_70_or_less)
        bench_space = player.board.max_bench_size - player.board.get_bench_count()
        expected_after = calculate_poffin_action_count(deck_by_fid, bench_space, has_searched_deck=True)

        assert len(actions_after) == expected_after, \
            f"After search: expected {expected_after} actions, got {len(actions_after)}"

    def test_poffin_limited_bench_space(self, engine):
        """
        Test Poffin when bench space is limited to 1.

        Setup:
        - Bench: 4 Pokemon (1 space left)
        - Deck: 3 valid Pokemon

        Expected:
        - Only single actions (no pairs due to bench limit)
        - Single: 3, Pair: 0, Fail: 1
        - Total: 3 + 0 + 1 = 4 actions
        """
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        # Fill bench to leave only 1 space
        for _ in range(4):
            player0.board.add_to_bench(create_card_instance("sv3pt5-16", owner_id=0))

        poffin = create_card_instance("sv3pt5-144", owner_id=0)
        player0.hand.add_card(poffin)

        # 3 valid Pokemon in deck
        player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))
        player0.deck.add_card(create_card_instance("sv4pt5-7", owner_id=0))
        player0.deck.add_card(create_card_instance("sv1-96", owner_id=0))

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]
        player.has_searched_deck = True

        actions = buddy_buddy_poffin_actions(state, poffin, player)

        deck_by_fid = get_deck_pokemon_by_functional_id_with_criteria(player, is_basic_hp_70_or_less)
        bench_space = player.board.max_bench_size - player.board.get_bench_count()

        assert bench_space == 1, f"Expected 1 bench space, got {bench_space}"

        expected_total = calculate_poffin_action_count(deck_by_fid, bench_space, has_searched_deck=True)

        # With bench_space=1, should have no pair actions
        n = len(deck_by_fid)
        expected_single = n
        expected_pair = 0  # No pairs when bench_space < 2
        expected_fail = 1
        assert expected_total == expected_single + expected_pair + expected_fail

        assert len(actions) == expected_total, \
            f"Expected {expected_total} actions (no pairs due to bench limit), got {len(actions)}"

    def test_poffin_mixed_valid_invalid_pokemon(self, engine):
        """
        Test Poffin with a mix of valid and invalid Pokemon.

        Setup:
        - Deck:
          - Pidgey (sv3pt5-16) HP=50 Basic - VALID
          - Charmander (sv4pt5-7) HP=70 Basic - VALID
          - Capsakid (sv3-23) HP=50 Basic - VALID (different card_id)
          - Pidgeotto (sv3pt5-17) HP=80 Stage 1 - INVALID (Stage 1)
          - Charizard ex (sv3-125) HP=330 Stage 2 - INVALID (Stage 2 + HP > 70)

        Expected:
        - 3 valid functional IDs (sv3pt5-16, sv4pt5-7, sv3-23)
        - Single: 3, Pair: C(3,2) = 3, Fail: 1
        - Total: 7 actions
        """
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        poffin = create_card_instance("sv3pt5-144", owner_id=0)
        player0.hand.add_card(poffin)

        # Valid Pokemon (Basic, HP <= 70)
        player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))  # Pidgey HP=50
        player0.deck.add_card(create_card_instance("sv4pt5-7", owner_id=0))   # Charmander HP=70
        player0.deck.add_card(create_card_instance("sv3-23", owner_id=0))     # Capsakid HP=50

        # Invalid Pokemon
        player0.deck.add_card(create_card_instance("sv3pt5-17", owner_id=0))  # Pidgeotto (Stage 1)
        player0.deck.add_card(create_card_instance("sv3-125", owner_id=0))    # Charizard ex (Stage 2)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]
        player.has_searched_deck = True

        actions = buddy_buddy_poffin_actions(state, poffin, player)

        deck_by_fid = get_deck_pokemon_by_functional_id_with_criteria(player, is_basic_hp_70_or_less)

        # Should have exactly 3 valid Pokemon
        assert len(deck_by_fid) == 3, \
            f"Expected 3 valid Pokemon, got {len(deck_by_fid)}: {list(deck_by_fid.keys())}"

        bench_space = player.board.max_bench_size - player.board.get_bench_count()
        expected_total = calculate_poffin_action_count(deck_by_fid, bench_space, has_searched_deck=True)

        assert len(actions) == expected_total, \
            f"Expected {expected_total} actions, got {len(actions)}"

    def test_poffin_large_deck_permutation(self, engine):
        """
        Test Poffin with many valid Pokemon.

        Setup:
        - Deck: 5 unique Basic Pokemon with HP <= 70

        Expected:
        - n = 5 functional IDs
        - Single: 5
        - Pair: C(5,2) = 10
        - Fail: 1
        - Total: 5 + 10 + 1 = 16 actions
        """
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        poffin = create_card_instance("sv3pt5-144", owner_id=0)
        player0.hand.add_card(poffin)

        # 5 unique Basic Pokemon with HP <= 70 (all different card_ids)
        player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))  # Pidgey HP=50
        player0.deck.add_card(create_card_instance("sv4pt5-7", owner_id=0))   # Charmander HP=70
        player0.deck.add_card(create_card_instance("sv1-96", owner_id=0))     # Klefki HP=70
        player0.deck.add_card(create_card_instance("sv3-1", owner_id=0))      # Oddish HP=50
        player0.deck.add_card(create_card_instance("sv3-23", owner_id=0))     # Capsakid HP=50

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]
        player.has_searched_deck = True

        actions = buddy_buddy_poffin_actions(state, poffin, player)

        deck_by_fid = get_deck_pokemon_by_functional_id_with_criteria(player, is_basic_hp_70_or_less)
        n = len(deck_by_fid)

        bench_space = player.board.max_bench_size - player.board.get_bench_count()
        expected_total = calculate_poffin_action_count(deck_by_fid, bench_space, has_searched_deck=True)

        # Verify formula: n + C(n,2) + 1
        expected_single = n
        expected_pair = comb(n, 2) if bench_space >= 2 else 0
        expected_fail = 1
        assert expected_total == expected_single + expected_pair + expected_fail

        assert len(actions) == expected_total, \
            f"Expected {expected_total} actions (n={n}), got {len(actions)}"

    def test_poffin_empty_deck(self, engine):
        """
        Test Poffin when deck has no valid Pokemon.

        Setup:
        - Deck: Only Stage 1/2 Pokemon or high HP Pokemon

        Expected:
        - Only fail search option: 1 action
        """
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        poffin = create_card_instance("sv3pt5-144", owner_id=0)
        player0.hand.add_card(poffin)

        # Only invalid Pokemon (Stage 1 and Stage 2)
        player0.deck.add_card(create_card_instance("sv3pt5-17", owner_id=0))  # Pidgeotto (Stage 1)
        player0.deck.add_card(create_card_instance("sv3-125", owner_id=0))    # Charizard ex (Stage 2)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]
        player.has_searched_deck = True

        actions = buddy_buddy_poffin_actions(state, poffin, player)

        deck_by_fid = get_deck_pokemon_by_functional_id_with_criteria(player, is_basic_hp_70_or_less)

        # Should have 0 valid Pokemon
        assert len(deck_by_fid) == 0, \
            f"Expected 0 valid Pokemon, got {len(deck_by_fid)}"

        # Only fail search should be available
        assert len(actions) == 1, \
            f"Expected 1 action (only fail search), got {len(actions)}"


class TestPoffinPermutationFormulas:
    """Unit tests for Poffin permutation calculation helpers."""

    def test_poffin_formula_basic(self):
        """Test Poffin action count formula."""
        # n=3, bench>=2: 3 + C(3,2) + 1 = 3 + 3 + 1 = 7
        deck = {"fid1": ["c1"], "fid2": ["c2"], "fid3": ["c3"]}
        assert calculate_poffin_action_count(deck, bench_space=5, has_searched_deck=True) == 7

        # n=2, bench>=2: 2 + C(2,2) + 1 = 2 + 1 + 1 = 4
        deck = {"fid1": ["c1"], "fid2": ["c2"]}
        assert calculate_poffin_action_count(deck, bench_space=5, has_searched_deck=True) == 4

        # n=1, bench>=2: 1 + C(1,2) + 1 = 1 + 0 + 1 = 2
        deck = {"fid1": ["c1"]}
        assert calculate_poffin_action_count(deck, bench_space=5, has_searched_deck=True) == 2

        # n=0: only fail search = 1
        deck = {}
        assert calculate_poffin_action_count(deck, bench_space=5, has_searched_deck=True) == 1

    def test_poffin_formula_limited_bench(self):
        """Test Poffin formula when bench space limits pairs."""
        # n=3, bench=1: 3 + 0 + 1 = 4 (no pairs)
        deck = {"fid1": ["c1"], "fid2": ["c2"], "fid3": ["c3"]}
        assert calculate_poffin_action_count(deck, bench_space=1, has_searched_deck=True) == 4

        # n=3, bench=0: should still give 1 for fail search only (edge case)
        # Actually with bench=0, Poffin shouldn't be playable, but formula should still work
        assert calculate_poffin_action_count(deck, bench_space=0, has_searched_deck=True) == 4

    def test_nest_ball_formula(self):
        """Test Nest Ball action count formula."""
        # n=3: 3 + 1 = 4
        deck = {"fid1": ["c1"], "fid2": ["c2"], "fid3": ["c3"]}
        assert calculate_nest_ball_action_count(deck, has_searched_deck=True) == 4

        # n=0: only fail = 1
        deck = {}
        assert calculate_nest_ball_action_count(deck, has_searched_deck=True) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

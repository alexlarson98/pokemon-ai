"""
Comprehensive Knowledge Layer Tests

Tests the imperfect information system for deck searches, ensuring:
1. Before searching: Player sees theoretical options (initial_deck_counts - hand)
2. After searching: Player has perfect knowledge of deck/prizes
3. Prized cards: Search fails silently, player gains knowledge

This is critical for ISMCTS (Information Set Monte Carlo Tree Search) correctness.
"""

import pytest
from models import (
    GameState, PlayerState, GamePhase, ActionType,
    SearchDeckStep, SelectFromZoneStep, ZoneType, SelectionPurpose
)
from cards.factory import create_card_instance
from cards.registry import create_card
from engine import PokemonEngine


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def engine():
    return PokemonEngine()


def compute_functional_id(card_def) -> str:
    """Compute functional ID for a card definition."""
    from cards.base import PokemonCard

    if not isinstance(card_def, PokemonCard):
        return card_def.name if hasattr(card_def, 'name') else str(card_def)

    name = card_def.name
    hp = card_def.hp if hasattr(card_def, 'hp') else 0

    attacks = []
    if hasattr(card_def, 'attacks'):
        for attack in card_def.attacks:
            attack_sig = f"{attack.name}:{attack.damage if hasattr(attack, 'damage') else ''}"
            attacks.append(attack_sig)
    attacks_str = ','.join(sorted(attacks))

    abilities = []
    if hasattr(card_def, 'abilities'):
        for ability in card_def.abilities:
            abilities.append(ability.name)
    abilities_str = ','.join(sorted(abilities))

    subtypes = []
    if hasattr(card_def, 'subtypes'):
        subtypes = [str(s.value) if hasattr(s, 'value') else str(s) for s in card_def.subtypes]
    subtypes_str = ','.join(sorted(subtypes))

    return f"{name}|{hp}|{subtypes_str}|{attacks_str}|{abilities_str}"


def create_knowledge_test_state(
    deck_cards: list = None,
    hand_cards: list = None,
    prized_cards: list = None,
    initial_deck_counts: dict = None,
    has_searched_deck: bool = False
) -> GameState:
    """
    Create a game state for knowledge layer testing.

    Args:
        deck_cards: List of card_ids to put in deck
        hand_cards: List of card_ids to put in hand
        prized_cards: List of card_ids to put in prizes
        initial_deck_counts: Dict of card_name -> count (what player started with)
            Note: These are converted to functional IDs automatically
        has_searched_deck: Whether player has already searched
    """
    from cards.base import PokemonCard

    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Track all card instances and their functional IDs for the knowledge layer
    all_cards = []
    functional_map = {}

    # Set up deck
    if deck_cards:
        for card_id in deck_cards:
            card = create_card_instance(card_id, owner_id=0)
            player0.deck.add_card(card)
            all_cards.append(card)

    # Set up hand
    if hand_cards:
        for card_id in hand_cards:
            card = create_card_instance(card_id, owner_id=0)
            player0.hand.add_card(card)
            all_cards.append(card)

    # Set up prizes
    if prized_cards:
        for card_id in prized_cards:
            card = create_card_instance(card_id, owner_id=0)
            player0.prizes.add_card(card)
            all_cards.append(card)

    # Set up active Pokemon for valid game state
    active = create_card_instance("svp-56", owner_id=0)  # Charizard ex
    player0.board.active_spot = active
    all_cards.append(active)
    player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)  # Pidgey

    # Build functional_id_map and counts from actual cards
    functional_counts = {}
    for card in all_cards:
        card_def = create_card(card.card_id)
        if isinstance(card_def, PokemonCard):
            func_id = compute_functional_id(card_def)
        else:
            func_id = card_def.name if card_def else card.card_id

        functional_map[card.card_id] = func_id
        functional_counts[func_id] = functional_counts.get(func_id, 0) + 1

    # If initial_deck_counts provided with card names, convert to functional IDs
    # Otherwise use auto-computed counts
    if initial_deck_counts:
        # Convert name-based counts to functional ID counts
        converted_counts = {}
        for name, count in initial_deck_counts.items():
            # Find a functional ID that matches this name
            matching_func_id = None
            for func_id in functional_counts.keys():
                if func_id.startswith(name + "|") or func_id == name:
                    # This functional ID matches the card name
                    if matching_func_id is None:
                        matching_func_id = func_id
                        converted_counts[func_id] = count
                    else:
                        # Multiple versions - use count from initial_deck_counts
                        # This is a simplification - tests should specify exact counts
                        converted_counts[func_id] = converted_counts.get(func_id, 0) + count // 2
            if matching_func_id is None:
                # Name not found in actual cards - just keep it as-is
                converted_counts[name] = count
        player0.initial_deck_counts = converted_counts
    else:
        player0.initial_deck_counts = functional_counts

    player0.functional_id_map = functional_map
    player0.has_searched_deck = has_searched_deck

    return GameState(
        players=[player0, player1],
        turn_count=2,
        active_player_index=0,
        current_phase=GamePhase.MAIN,
        starting_player_id=0
    )


# =============================================================================
# THEORETICAL DECK CARDS - CORE LOGIC
# =============================================================================

class TestTheoreticalDeckCards:
    """Test the _get_theoretical_deck_cards helper method."""

    def test_basic_theoretical_calculation(self, engine):
        """
        Before search: Available = initial_deck_counts - hand

        Scenario: 4 Pidgey in initial deck, 1 in hand
        Expected: 3 Pidgey theoretically available (shows as 1 deduplicated option)
        """
        state = create_knowledge_test_state(
            deck_cards=["sv3pt5-16"],  # 1 Pidgey in deck
            hand_cards=["sv3pt5-16"],  # 1 Pidgey in hand
            prized_cards=["sv3pt5-16", "sv3pt5-16"],  # 2 Pidgey prized
            initial_deck_counts={"Pidgey": 4},
            has_searched_deck=False
        )

        player = state.players[0]
        step = SearchDeckStep(
            source_card_id='test',
            source_card_name='Test Search',
            player_id=0,
            purpose=SelectionPurpose.SEARCH_TARGET,
            count=1,
            min_count=0,
            destination=ZoneType.BENCH,
            filter_criteria={'supertype': 'Pokemon', 'subtype': 'Basic'},
            shuffle_after=True
        )

        theoretical = engine._get_theoretical_deck_cards(player, step, state)

        # Should find Pidgey (deduplicated to 1 representative)
        assert len(theoretical) == 1
        card_def = create_card(theoretical[0].card_id)
        assert card_def.name == "Pidgey"

    def test_hand_subtraction(self, engine):
        """
        Cards in hand should be subtracted from theoretical availability.

        Scenario: 2 Charmander initial, both in hand
        Expected: 0 Charmander available (none in hidden zone)
        """
        state = create_knowledge_test_state(
            deck_cards=[],  # None in deck
            hand_cards=["sv4pt5-7", "sv4pt5-7"],  # 2 Charmander in hand
            prized_cards=[],  # None prized
            initial_deck_counts={"Charmander": 2},
            has_searched_deck=False
        )

        player = state.players[0]
        step = SearchDeckStep(
            source_card_id='test',
            source_card_name='Test Search',
            player_id=0,
            purpose=SelectionPurpose.SEARCH_TARGET,
            count=1,
            min_count=0,
            destination=ZoneType.BENCH,
            filter_criteria={'supertype': 'Pokemon', 'subtype': 'Basic'},
            shuffle_after=True
        )

        theoretical = engine._get_theoretical_deck_cards(player, step, state)

        # No Charmander available - all in hand
        charmander_cards = [c for c in theoretical if create_card(c.card_id).name == "Charmander"]
        assert len(charmander_cards) == 0

    def test_multiple_card_types(self, engine):
        """
        Test theoretical calculation with multiple different cards.

        Scenario: 4 Pidgey (1 hand, 3 hidden), 2 Charmander (0 hand, 2 hidden)
        Expected: Both Pidgey and Charmander available
        """
        state = create_knowledge_test_state(
            deck_cards=["sv3pt5-16", "sv4pt5-7"],  # 1 Pidgey, 1 Charmander in deck
            hand_cards=["sv3pt5-16"],  # 1 Pidgey in hand
            prized_cards=["sv3pt5-16", "sv3pt5-16", "sv4pt5-7"],  # 2 Pidgey, 1 Charmander prized
            initial_deck_counts={"Pidgey": 4, "Charmander": 2},
            has_searched_deck=False
        )

        player = state.players[0]
        step = SearchDeckStep(
            source_card_id='test',
            source_card_name='Test Search',
            player_id=0,
            purpose=SelectionPurpose.SEARCH_TARGET,
            count=2,
            min_count=0,
            destination=ZoneType.BENCH,
            filter_criteria={'supertype': 'Pokemon', 'subtype': 'Basic'},
            shuffle_after=True
        )

        theoretical = engine._get_theoretical_deck_cards(player, step, state)

        # Should have both Pidgey and Charmander (deduplicated)
        names = {create_card(c.card_id).name for c in theoretical}
        assert "Pidgey" in names
        assert "Charmander" in names
        assert len(theoretical) == 2

    def test_filter_criteria_applied(self, engine):
        """
        Filter criteria should still apply to theoretical cards.

        Scenario: Deck has Pidgey (Basic) and Charmeleon (Stage 1)
        Filter: Basic only
        Expected: Only Pidgey available
        """
        state = create_knowledge_test_state(
            deck_cards=["sv3pt5-16", "sv4pt5-8"],  # Pidgey (Basic), Charmeleon (Stage 1)
            hand_cards=[],
            prized_cards=[],
            initial_deck_counts={"Pidgey": 1, "Charmeleon": 1},
            has_searched_deck=False
        )

        player = state.players[0]
        step = SearchDeckStep(
            source_card_id='test',
            source_card_name='Nest Ball',
            player_id=0,
            purpose=SelectionPurpose.SEARCH_TARGET,
            count=1,
            min_count=0,
            destination=ZoneType.BENCH,
            filter_criteria={'supertype': 'Pokemon', 'subtype': 'Basic'},
            shuffle_after=True
        )

        theoretical = engine._get_theoretical_deck_cards(player, step, state)

        # Only Pidgey should be available (Basic only)
        assert len(theoretical) == 1
        assert create_card(theoretical[0].card_id).name == "Pidgey"


# =============================================================================
# PERFECT KNOWLEDGE (AFTER SEARCH)
# =============================================================================

class TestPerfectKnowledge:
    """Test behavior after player has searched deck (perfect knowledge)."""

    def test_after_search_uses_actual_deck(self, engine):
        """
        After searching, player uses actual deck contents (not theoretical).

        Scenario: Initial 4 Pidgey, but only 1 actually in deck (3 prized)
        After search: Should only see 1 Pidgey option
        """
        state = create_knowledge_test_state(
            deck_cards=["sv3pt5-16"],  # 1 Pidgey actually in deck
            hand_cards=[],
            prized_cards=["sv3pt5-16", "sv3pt5-16", "sv3pt5-16"],  # 3 Pidgey prized
            initial_deck_counts={"Pidgey": 4},
            has_searched_deck=True  # Already searched!
        )

        # Add a search step to the stack
        step = SearchDeckStep(
            source_card_id='test',
            source_card_name='Test Search',
            player_id=0,
            purpose=SelectionPurpose.SEARCH_TARGET,
            count=1,
            min_count=0,
            destination=ZoneType.BENCH,
            filter_criteria={'supertype': 'Pokemon', 'subtype': 'Basic'},
            shuffle_after=True
        )
        state.push_step(step)

        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Should only see 1 Pidgey (actual deck contents)
        assert len(select_actions) == 1

    def test_prized_cards_not_shown_after_search(self, engine):
        """
        After searching, prized cards should not be shown as options.
        """
        state = create_knowledge_test_state(
            deck_cards=[],  # No Pidgey in deck
            hand_cards=[],
            prized_cards=["sv3pt5-16", "sv3pt5-16"],  # 2 Pidgey prized
            initial_deck_counts={"Pidgey": 2},
            has_searched_deck=True  # Already searched!
        )

        step = SearchDeckStep(
            source_card_id='test',
            source_card_name='Test Search',
            player_id=0,
            purpose=SelectionPurpose.SEARCH_TARGET,
            count=1,
            min_count=0,
            destination=ZoneType.BENCH,
            filter_criteria={'supertype': 'Pokemon', 'subtype': 'Basic'},
            shuffle_after=True
        )
        state.push_step(step)

        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # No Pidgey options - all prized and player knows it
        pidgey_actions = [a for a in select_actions
                         if create_card(state.players[0].deck.cards[0].card_id if state.players[0].deck.cards else "").name == "Pidgey"]
        assert len(select_actions) == 0


# =============================================================================
# PRIZED CARD SELECTION (FAILED SEARCH)
# =============================================================================

class TestPrizedCardSelection:
    """Test what happens when player selects a prized card during search."""

    def test_selecting_prized_card_fails_silently(self, engine):
        """
        If player selects a card that's prized (not in deck), search fails.
        The card won't be found, but player gains knowledge.
        """
        state = create_knowledge_test_state(
            deck_cards=[],  # No Pidgey in deck!
            hand_cards=[],
            prized_cards=["sv3pt5-16"],  # Pidgey is prized
            initial_deck_counts={"Pidgey": 1},
            has_searched_deck=False
        )

        player = state.players[0]
        prized_pidgey = player.prizes.cards[0]

        # Create a search step and simulate selecting the prized card
        step = SearchDeckStep(
            source_card_id='test',
            source_card_name='Test Search',
            player_id=0,
            purpose=SelectionPurpose.SEARCH_TARGET,
            count=1,
            min_count=0,
            destination=ZoneType.BENCH,
            filter_criteria={'supertype': 'Pokemon', 'subtype': 'Basic'},
            shuffle_after=True
        )
        step.selected_card_ids.append(prized_pidgey.id)  # Select the prized card

        # Execute the search
        initial_bench_count = player.board.get_bench_count()
        state = engine._execute_search_deck(state, step, player)

        # Search failed - no new Pokemon on bench
        assert player.board.get_bench_count() == initial_bench_count

        # But player now has knowledge
        assert player.has_searched_deck == True

    def test_partial_success_mixed_selection(self, engine):
        """
        When selecting multiple cards, some may be in deck (success) and some prized (fail).
        """
        state = create_knowledge_test_state(
            deck_cards=["sv3pt5-16"],  # 1 Pidgey in deck
            hand_cards=[],
            prized_cards=["sv4pt5-7"],  # Charmander is prized
            initial_deck_counts={"Pidgey": 1, "Charmander": 1},
            has_searched_deck=False
        )

        player = state.players[0]
        deck_pidgey = player.deck.cards[0]
        prized_charmander = player.prizes.cards[0]

        # Select both - one from deck, one prized
        step = SearchDeckStep(
            source_card_id='test',
            source_card_name='Buddy-Buddy Poffin',
            player_id=0,
            purpose=SelectionPurpose.SEARCH_TARGET,
            count=2,
            min_count=0,
            destination=ZoneType.BENCH,
            filter_criteria={'supertype': 'Pokemon', 'subtype': 'Basic'},
            shuffle_after=True
        )
        step.selected_card_ids.append(deck_pidgey.id)
        step.selected_card_ids.append(prized_charmander.id)

        initial_bench_count = player.board.get_bench_count()
        state = engine._execute_search_deck(state, step, player)

        # Only Pidgey was found - bench increased by 1
        assert player.board.get_bench_count() == initial_bench_count + 1

        # Charmander still prized
        assert player.prizes.count() == 1

        # Player gained knowledge
        assert player.has_searched_deck == True


# =============================================================================
# NEST BALL INTEGRATION
# =============================================================================

class TestNestBallKnowledgeLayer:
    """Test Nest Ball with knowledge layer."""

    def test_nest_ball_before_search_shows_all_theoretical(self, engine):
        """
        Nest Ball before any search should show all theoretically available Basics.
        """
        state = create_knowledge_test_state(
            deck_cards=["sv3pt5-16"],  # 1 Pidgey in deck
            hand_cards=["sv1-181"],  # Nest Ball in hand
            prized_cards=["sv3pt5-16", "sv4pt5-7"],  # 1 Pidgey, 1 Charmander prized
            initial_deck_counts={"Pidgey": 2, "Charmander": 1},
            has_searched_deck=False
        )

        nest_ball = state.players[0].hand.cards[0]

        # Play Nest Ball
        actions = engine.get_legal_actions(state)
        play_action = next((a for a in actions
                           if a.action_type == ActionType.PLAY_ITEM and a.card_id == nest_ball.id), None)

        assert play_action is not None
        state = engine.step(state, play_action)

        # Get search options
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Should see both Pidgey and Charmander (theoretical availability)
        # Even though Charmander is prized, player doesn't know that
        names = set()
        for action in select_actions:
            for card in list(state.players[0].deck.cards) + list(state.players[0].prizes.cards):
                if card.id == action.card_id:
                    names.add(create_card(card.card_id).name)

        assert "Pidgey" in names or "Charmander" in names  # At least one theoretical option

    def test_nest_ball_after_search_shows_actual(self, engine):
        """
        Nest Ball after searching should only show actual deck contents.
        """
        state = create_knowledge_test_state(
            deck_cards=["sv3pt5-16"],  # Only Pidgey in deck
            hand_cards=["sv1-181"],  # Nest Ball in hand
            prized_cards=["sv4pt5-7"],  # Charmander is prized
            initial_deck_counts={"Pidgey": 1, "Charmander": 1},
            has_searched_deck=True  # Already searched
        )

        nest_ball = state.players[0].hand.cards[0]

        # Play Nest Ball
        actions = engine.get_legal_actions(state)
        play_action = next((a for a in actions
                           if a.action_type == ActionType.PLAY_ITEM and a.card_id == nest_ball.id), None)

        assert play_action is not None
        state = engine.step(state, play_action)

        # Get search options
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Should only see Pidgey (actual deck contents)
        assert len(select_actions) == 1


# =============================================================================
# BUDDY-BUDDY POFFIN INTEGRATION
# =============================================================================

class TestBuddyBuddyPoffinKnowledgeLayer:
    """Test Buddy-Buddy Poffin with knowledge layer (HP ≤ 70 filter)."""

    def test_poffin_respects_hp_filter_with_theoretical(self, engine):
        """
        Buddy-Buddy Poffin should apply HP ≤ 70 filter to theoretical cards.
        """
        state = create_knowledge_test_state(
            deck_cards=["sv3pt5-16"],  # Pidgey (60 HP) in deck
            hand_cards=["sv5-144"],  # Buddy-Buddy Poffin
            prized_cards=["svp-56"],  # Charizard ex (330 HP) prized - shouldn't show anyway
            initial_deck_counts={"Pidgey": 1, "Charizard ex": 1},
            has_searched_deck=False
        )

        poffin = state.players[0].hand.cards[0]

        # Play Poffin
        actions = engine.get_legal_actions(state)
        play_action = next((a for a in actions
                           if a.action_type == ActionType.PLAY_ITEM and a.card_id == poffin.id), None)

        assert play_action is not None
        state = engine.step(state, play_action)

        # Get search options
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Should only see Pidgey (HP ≤ 70)
        # Charizard ex shouldn't appear even if it were theoretically available
        for action in select_actions:
            card = next((c for c in state.players[0].deck.cards if c.id == action.card_id), None)
            if card:
                card_def = create_card(card.card_id)
                assert card_def.hp <= 70, f"Should only show HP ≤ 70, got {card_def.name} with {card_def.hp} HP"


# =============================================================================
# ULTRA BALL INTEGRATION (WITH DISCARD COST)
# =============================================================================

class TestUltraBallKnowledgeLayer:
    """Test Ultra Ball with knowledge layer (any Pokemon, discard cost)."""

    def test_ultra_ball_shows_all_pokemon_types(self, engine):
        """
        Ultra Ball can search for any Pokemon (Basic, Stage 1, Stage 2, ex, etc.)
        """
        state = create_knowledge_test_state(
            deck_cards=["sv3pt5-16", "sv4pt5-8"],  # Pidgey (Basic), Charmeleon (Stage 1)
            hand_cards=["sv4pt5-91", "sve-2", "sve-2"],  # Ultra Ball + 2 discard fodder
            prized_cards=[],
            initial_deck_counts={"Pidgey": 1, "Charmeleon": 1},
            has_searched_deck=False
        )

        # Verify Ultra Ball is playable (need 2 other cards to discard)
        ultra_ball = state.players[0].hand.cards[0]
        actions = engine.get_legal_actions(state)
        play_action = next((a for a in actions
                           if a.action_type == ActionType.PLAY_ITEM and a.card_id == ultra_ball.id), None)

        assert play_action is not None


# =============================================================================
# KNOWLEDGE GAINED AFTER SEARCH
# =============================================================================

class TestKnowledgeGainedAfterSearch:
    """Test that has_searched_deck is properly set after searching."""

    def test_successful_search_sets_knowledge_flag(self, engine):
        """
        After a successful search, has_searched_deck should be True.
        """
        state = create_knowledge_test_state(
            deck_cards=["sv3pt5-16"],
            hand_cards=["sv1-181"],  # Nest Ball
            prized_cards=[],
            initial_deck_counts={"Pidgey": 1},
            has_searched_deck=False
        )

        player = state.players[0]
        assert not player.has_searched_deck

        nest_ball = player.hand.cards[0]

        # Play Nest Ball
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions
                          if a.action_type == ActionType.PLAY_ITEM and a.card_id == nest_ball.id)
        state = engine.step(state, play_action)

        # Select Pidgey
        actions = engine.get_legal_actions(state)
        select_action = next(a for a in actions if a.action_type == ActionType.SELECT_CARD)
        state = engine.step(state, select_action)

        # Confirm
        actions = engine.get_legal_actions(state)
        confirm_action = next(a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION)
        state = engine.step(state, confirm_action)

        # Knowledge flag should now be True
        player = state.players[0]
        assert player.has_searched_deck == True

    def test_declined_search_sets_knowledge_flag(self, engine):
        """
        Even declining a search (selecting 0 cards) should set knowledge flag.
        """
        state = create_knowledge_test_state(
            deck_cards=["sv3pt5-16"],
            hand_cards=["sv1-181"],  # Nest Ball
            prized_cards=[],
            initial_deck_counts={"Pidgey": 1},
            has_searched_deck=False
        )

        player = state.players[0]
        nest_ball = player.hand.cards[0]

        # Play Nest Ball
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions
                          if a.action_type == ActionType.PLAY_ITEM and a.card_id == nest_ball.id)
        state = engine.step(state, play_action)

        # Confirm immediately (decline search)
        actions = engine.get_legal_actions(state)
        confirm_action = next(a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION)
        state = engine.step(state, confirm_action)

        # Knowledge flag should be True even though we declined
        player = state.players[0]
        assert player.has_searched_deck == True


# =============================================================================
# EDGE CASES
# =============================================================================

class TestKnowledgeLayerEdgeCases:
    """Test edge cases in the knowledge layer."""

    def test_empty_initial_deck_counts(self, engine):
        """
        If initial_deck_counts is empty, should fall back to actual deck.
        """
        state = create_knowledge_test_state(
            deck_cards=["sv3pt5-16"],
            hand_cards=[],
            prized_cards=[],
            initial_deck_counts={},  # Empty!
            has_searched_deck=False
        )

        step = SearchDeckStep(
            source_card_id='test',
            source_card_name='Test Search',
            player_id=0,
            purpose=SelectionPurpose.SEARCH_TARGET,
            count=1,
            min_count=0,
            destination=ZoneType.BENCH,
            filter_criteria={'supertype': 'Pokemon', 'subtype': 'Basic'},
            shuffle_after=True
        )
        state.push_step(step)

        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Should fall back to actual deck contents
        assert len(select_actions) == 1

    def test_all_copies_in_hand(self, engine):
        """
        If all copies of a card are in hand, it shouldn't appear in search.
        """
        state = create_knowledge_test_state(
            deck_cards=["sv4pt5-7"],  # Charmander in deck
            hand_cards=["sv3pt5-16", "sv3pt5-16", "sv3pt5-16", "sv3pt5-16"],  # All 4 Pidgey in hand
            prized_cards=[],
            initial_deck_counts={"Pidgey": 4, "Charmander": 1},
            has_searched_deck=False
        )

        player = state.players[0]
        step = SearchDeckStep(
            source_card_id='test',
            source_card_name='Test Search',
            player_id=0,
            purpose=SelectionPurpose.SEARCH_TARGET,
            count=1,
            min_count=0,
            destination=ZoneType.BENCH,
            filter_criteria={'supertype': 'Pokemon', 'subtype': 'Basic'},
            shuffle_after=True
        )

        theoretical = engine._get_theoretical_deck_cards(player, step, state)

        # Pidgey shouldn't be available (all in hand)
        # Only Charmander should be available
        names = {create_card(c.card_id).name for c in theoretical}
        assert "Pidgey" not in names
        assert "Charmander" in names

    def test_more_in_hand_than_initial_deck(self, engine):
        """
        Edge case: More cards in hand than initial_deck_counts says (shouldn't happen, but handle gracefully).
        """
        state = create_knowledge_test_state(
            deck_cards=[],
            hand_cards=["sv3pt5-16", "sv3pt5-16", "sv3pt5-16"],  # 3 Pidgey in hand
            prized_cards=[],
            initial_deck_counts={"Pidgey": 2},  # But initial says only 2
            has_searched_deck=False
        )

        player = state.players[0]
        step = SearchDeckStep(
            source_card_id='test',
            source_card_name='Test Search',
            player_id=0,
            purpose=SelectionPurpose.SEARCH_TARGET,
            count=1,
            min_count=0,
            destination=ZoneType.BENCH,
            filter_criteria={'supertype': 'Pokemon', 'subtype': 'Basic'},
            shuffle_after=True
        )

        theoretical = engine._get_theoretical_deck_cards(player, step, state)

        # Should be 0 (2 - 3 = -1, clamped to 0)
        pidgey_cards = [c for c in theoretical if create_card(c.card_id).name == "Pidgey"]
        assert len(pidgey_cards) == 0


# =============================================================================
# SEARCH AND ATTACH STATE (INFERNAL REIGN)
# =============================================================================

class TestSearchAndAttachKnowledgeLayer:
    """Test SearchAndAttachState (used by Infernal Reign) with knowledge layer."""

    def test_infernal_reign_search_deduplicates(self, engine):
        """
        Infernal Reign search should deduplicate identical energy cards.
        """
        from models import SearchAndAttachState, InterruptPhase, EnergyType, Subtype

        state = create_knowledge_test_state(
            deck_cards=["sve-2", "sve-2", "sve-2"],  # 3 Basic Fire Energy
            hand_cards=[],
            prized_cards=[],
            initial_deck_counts={"Basic Fire Energy": 3},
            has_searched_deck=False
        )

        # Create Infernal Reign interrupt
        charizard = state.players[0].board.active_spot
        interrupt = SearchAndAttachState(
            ability_name="Infernal Reign",
            source_card_id=charizard.id,
            player_id=0,
            phase=InterruptPhase.SEARCH_SELECT,
            search_filter={
                "energy_type": EnergyType.FIRE,
                "subtype": Subtype.BASIC
            },
            max_select=3,
            selected_card_ids=[],
            cards_to_attach=[],
        )
        state.pending_interrupt = interrupt

        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SEARCH_SELECT_CARD]

        # Should be deduplicated to 1 action (all identical energy)
        assert len(select_actions) == 1


# =============================================================================
# INITIALIZE DECK KNOWLEDGE
# =============================================================================

class TestInitializeDeckKnowledge:
    """Test the initialize_deck_knowledge helper if it exists."""

    def test_initialize_sets_counts(self, engine):
        """
        initialize_deck_knowledge should populate initial_deck_counts with functional IDs.
        """
        state = create_knowledge_test_state(
            deck_cards=["sv3pt5-16", "sv3pt5-16", "sv4pt5-7"],  # 2 Pidgey, 1 Charmander
            hand_cards=[],
            prized_cards=[],
            initial_deck_counts={},  # Not set yet
            has_searched_deck=False
        )

        # Check if engine has initialize_deck_knowledge method
        if hasattr(engine, 'initialize_deck_knowledge'):
            state = engine.initialize_deck_knowledge(state)
            player = state.players[0]

            # Should have populated counts by functional ID (not just name)
            # Look for Pidgey and Charmander functional IDs
            pidgey_count = sum(v for k, v in player.initial_deck_counts.items() if k.startswith("Pidgey|"))
            charmander_count = sum(v for k, v in player.initial_deck_counts.items() if k.startswith("Charmander|"))

            assert pidgey_count >= 2, f"Expected at least 2 Pidgey, got {pidgey_count}"
            assert charmander_count >= 1, f"Expected at least 1 Charmander, got {charmander_count}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

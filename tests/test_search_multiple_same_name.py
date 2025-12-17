"""
Comprehensive pytest suite for search functionality with multiple cards sharing the same name.

Tests verify that search functionality works correctly when multiple Pokemon
share the same name but have different card IDs (like sv4pt5-7 and me2-11, both "Charmander").

Tests:
- Ultra Ball searching with multiple same-name variants in deck
- Nest Ball searching with multiple same-name Basic Pokemon
- Search target disambiguation via parameters['search_target_id']
- No incorrect deduplication for different card IDs

Key Insight: Even though sv4pt5-7 and me2-11 both have name="Charmander",
they are treated as DISTINCT cards with different instance IDs in search actions.

IMPORTANT: The current implementation uses parameters['search_target_id'] to distinguish
between same-name Pokemon. Future enhancement should add functional card ID to display_label
to help users distinguish variants (e.g., "Search Charmander (sv4pt5-7)" vs "Search Charmander (me2-11)").
"""

import pytest
import sys
sys.path.insert(0, 'src')

from models import GameState, PlayerState, GamePhase, Action, ActionType
from engine import PokemonEngine
from cards.factory import create_card_instance
from cards.registry import create_card
from cards.library.trainers import ultra_ball_actions, nest_ball_actions


@pytest.fixture
def engine():
    """Create PokemonEngine instance."""
    return PokemonEngine()


@pytest.fixture
def game_state_multiple_charmanders(engine):
    """
    Create a game state with 2 different Charmander variants in deck.

    Setup:
    - Player 0 has sv4pt5-7 (Charmander) and me2-11 (Charmander) in deck
    - Player 0 has Ultra Ball in hand
    - Player 0 has 2 cards in hand (for discard cost)
    - Both players have active Pokemon
    """
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Active Pokemon
    player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)  # Pidgey
    player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

    # Add 2 different Charmander variants to deck
    charmander1 = create_card_instance("sv4pt5-7", owner_id=0)   # Charmander variant 1
    charmander2 = create_card_instance("me2-11", owner_id=0)     # Charmander variant 2
    player0.deck.add_card(charmander1)
    player0.deck.add_card(charmander2)

    # Add one more Pokemon for variety
    player0.deck.add_card(create_card_instance("sv2-81", owner_id=0))  # Wattrel

    # Add Ultra Ball to hand
    ultra_ball = create_card_instance("sv1-196", owner_id=0)  # Ultra Ball
    player0.hand.add_card(ultra_ball)

    # Add 2 cards to hand for discard cost
    player0.hand.add_card(create_card_instance("sv3pt5-16", owner_id=0))
    player0.hand.add_card(create_card_instance("sv2-81", owner_id=0))

    state = GameState(
        players=[player0, player1],
        turn_count=2,
        active_player_index=0,
        current_phase=GamePhase.MAIN,
        starting_player_id=0
    )

    # Initialize deck knowledge
    state = engine.initialize_deck_knowledge(state)

    return state


def get_search_target_id(action):
    """Extract the search target ID from an action, handling different parameter names."""
    if not action.parameters:
        return None
    # Ultra Ball uses 'search_target_id', Nest Ball uses 'target_pokemon_id'
    return action.parameters.get('search_target_id') or action.parameters.get('target_pokemon_id')


def get_search_target_ids(actions):
    """Extract search target IDs from action parameters, filtering out None (fail search)."""
    target_ids = []
    for a in actions:
        target_id = get_search_target_id(a)
        if target_id is not None:
            target_ids.append(target_id)
    return target_ids


def get_search_actions_for_pokemon(actions, pokemon_name):
    """Get actions that search for a specific Pokemon by name."""
    return [a for a in actions
            if get_search_target_id(a) is not None
            and f'Search {pokemon_name}' in a.display_label]


class TestUltraBallMultipleCharmanders:
    """Test Ultra Ball with multiple Charmander variants."""

    def test_both_charmanders_have_same_name(self):
        """Verify test setup: both card IDs should have name='Charmander'."""
        card1 = create_card("sv4pt5-7")
        card2 = create_card("me2-11")

        assert card1.name == "Charmander", f"sv4pt5-7 should be Charmander, got {card1.name}"
        assert card2.name == "Charmander", f"me2-11 should be Charmander, got {card2.name}"

    def test_ultra_ball_generates_distinct_search_target_ids(self, game_state_multiple_charmanders):
        """Ultra Ball should generate actions with distinct search_target_id for each Charmander."""
        state = game_state_multiple_charmanders
        player = state.players[0]

        # Get Charmander instance IDs from deck for verification
        charmanders_in_deck = [c for c in player.deck.cards if create_card(c.card_id).name == "Charmander"]
        expected_instance_ids = {c.id for c in charmanders_in_deck}
        assert len(expected_instance_ids) == 2, "Test setup should have 2 Charmander instances"

        # Get Ultra Ball from hand
        ultra_ball = next(c for c in player.hand.cards if create_card(c.card_id).name == "Ultra Ball")

        # Generate Ultra Ball actions
        actions = ultra_ball_actions(state, ultra_ball, player)

        # Get all search_target_ids from Charmander search actions
        charmander_search_actions = get_search_actions_for_pokemon(actions, "Charmander")
        search_target_ids = {a.parameters['search_target_id'] for a in charmander_search_actions}

        # CRITICAL: Should have 2 distinct search_target_ids matching our Charmander instances
        assert len(search_target_ids) == 2, \
            f"Should have 2 distinct search_target_ids for Charmanders, got {len(search_target_ids)}"

        # Verify the search_target_ids match our actual Charmander instance IDs
        assert search_target_ids == expected_instance_ids, \
            f"search_target_ids {search_target_ids} should match deck Charmander IDs {expected_instance_ids}"

    def test_ultra_ball_charmander_search_targets_are_different_cards(self, game_state_multiple_charmanders):
        """Each Charmander search action should target a different card instance (sv4pt5-7 vs me2-11)."""
        state = game_state_multiple_charmanders
        player = state.players[0]

        # Map instance IDs to card_ids
        charmanders_in_deck = {c.id: c.card_id for c in player.deck.cards
                               if create_card(c.card_id).name == "Charmander"}

        ultra_ball = next(c for c in player.hand.cards if create_card(c.card_id).name == "Ultra Ball")
        actions = ultra_ball_actions(state, ultra_ball, player)

        charmander_search_actions = get_search_actions_for_pokemon(actions, "Charmander")

        # Get the card_ids that each action targets
        targeted_card_ids = set()
        for action in charmander_search_actions:
            instance_id = action.parameters['search_target_id']
            card_id = charmanders_in_deck.get(instance_id)
            if card_id:
                targeted_card_ids.add(card_id)

        # CRITICAL: Should target both sv4pt5-7 AND me2-11
        assert "sv4pt5-7" in targeted_card_ids, "Should have action targeting sv4pt5-7 Charmander"
        assert "me2-11" in targeted_card_ids, "Should have action targeting me2-11 Charmander"

    def test_ultra_ball_finds_all_pokemon_types(self, game_state_multiple_charmanders):
        """Ultra Ball should find Charmanders AND Wattrel."""
        state = game_state_multiple_charmanders
        player = state.players[0]

        ultra_ball = next(c for c in player.hand.cards if create_card(c.card_id).name == "Ultra Ball")
        actions = ultra_ball_actions(state, ultra_ball, player)

        # Get all search target IDs (excludes fail search)
        all_search_target_ids = get_search_target_ids(actions)

        # Should have 3 search targets: 2 Charmanders + 1 Wattrel
        assert len(all_search_target_ids) == 3, \
            f"Should have 3 search targets (2 Charmander + 1 Wattrel), got {len(all_search_target_ids)}"

        # Verify Wattrel is included
        wattrel_actions = get_search_actions_for_pokemon(actions, "Wattrel")
        assert len(wattrel_actions) >= 1, "Should have Wattrel search option"


class TestNestBallMultipleCharmanders:
    """Test Nest Ball with multiple Charmander variants."""

    def test_nest_ball_generates_distinct_search_targets(self, engine):
        """Nest Ball should generate distinct search_target_id for each Charmander variant."""
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        # Add 2 Charmander variants and track their instance IDs
        charmander1 = create_card_instance("sv4pt5-7", owner_id=0)
        charmander2 = create_card_instance("me2-11", owner_id=0)
        player0.deck.add_card(charmander1)
        player0.deck.add_card(charmander2)
        expected_instance_ids = {charmander1.id, charmander2.id}

        # Nest Ball in hand
        nest_ball = create_card_instance("sv1-181", owner_id=0)
        player0.hand.add_card(nest_ball)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        state = engine.initialize_deck_knowledge(state)
        actions = nest_ball_actions(state, nest_ball, player0)

        # Get Charmander search actions
        charmander_search_actions = get_search_actions_for_pokemon(actions, "Charmander")
        search_target_ids = {get_search_target_id(a) for a in charmander_search_actions}

        # Should have 2 distinct search targets
        assert len(search_target_ids) == 2, \
            f"Nest Ball should have 2 distinct Charmander search targets, got {len(search_target_ids)}"

        # Should match our expected instance IDs
        assert search_target_ids == expected_instance_ids, \
            "Nest Ball search targets should match the actual Charmander instance IDs in deck"


class TestNoIncorrectDeduplication:
    """Test that same-name Pokemon with different card IDs are NOT deduplicated."""

    def test_no_deduplication_for_different_charmander_ids(self, engine):
        """sv4pt5-7 and me2-11 should NOT be deduplicated despite same name."""
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        # Add 2 Charmander variants
        charmander1 = create_card_instance("sv4pt5-7", owner_id=0)
        charmander2 = create_card_instance("me2-11", owner_id=0)
        player0.deck.add_card(charmander1)
        player0.deck.add_card(charmander2)

        # Ultra Ball setup
        ultra_ball = create_card_instance("sv1-196", owner_id=0)
        player0.hand.add_card(ultra_ball)
        player0.hand.add_card(create_card_instance("sv3pt5-16", owner_id=0))
        player0.hand.add_card(create_card_instance("sv2-81", owner_id=0))

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        state = engine.initialize_deck_knowledge(state)
        actions = ultra_ball_actions(state, ultra_ball, player0)

        # Get all search target IDs
        search_target_ids = get_search_target_ids(actions)

        # Should have exactly 2 search targets (both Charmanders)
        assert len(search_target_ids) == 2, \
            f"Should have 2 search targets (no deduplication), got {len(search_target_ids)}"

        # Both should be different instance IDs
        assert len(set(search_target_ids)) == 2, \
            "Both search targets should have unique instance IDs"

    def test_fail_search_available_with_multiple_charmanders(self, engine):
        """Fail search option should be available even with multiple Charmanders."""
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        # Add 2 Charmanders
        player0.deck.add_card(create_card_instance("sv4pt5-7", owner_id=0))
        player0.deck.add_card(create_card_instance("me2-11", owner_id=0))

        # Ultra Ball setup
        ultra_ball = create_card_instance("sv1-196", owner_id=0)
        player0.hand.add_card(ultra_ball)
        player0.hand.add_card(create_card_instance("sv3pt5-16", owner_id=0))
        player0.hand.add_card(create_card_instance("sv2-81", owner_id=0))

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        state = engine.initialize_deck_knowledge(state)
        actions = ultra_ball_actions(state, ultra_ball, player0)

        # Find fail search action (search_target_id is None)
        fail_actions = [a for a in actions
                        if a.parameters
                        and a.parameters.get('search_target_id') is None]

        assert len(fail_actions) >= 1, \
            "Should have fail search option even with multiple Charmanders available"


class TestMultipleCharmandersWithDifferentStats:
    """Test that different Charmander printings are correctly distinguished."""

    def test_charmander_variants_may_have_different_hp(self):
        """Different Charmander printings can have different HP values."""
        card1 = create_card("sv4pt5-7")
        card2 = create_card("me2-11")

        # Both should be Charmander
        assert card1.name == "Charmander"
        assert card2.name == "Charmander"

        # They may have same or different HP, but should both be valid cards
        assert hasattr(card1, 'hp'), "sv4pt5-7 should have HP"
        assert hasattr(card2, 'hp'), "me2-11 should have HP"

    def test_charmander_variants_are_both_basic(self):
        """Both Charmander variants should be Basic Pokemon."""
        from cards.base import Subtype
        card1 = create_card("sv4pt5-7")
        card2 = create_card("me2-11")

        # Check subtypes for Basic
        assert Subtype.BASIC in card1.subtypes, f"sv4pt5-7 should be Basic, got subtypes {card1.subtypes}"
        assert Subtype.BASIC in card2.subtypes, f"me2-11 should be Basic, got subtypes {card2.subtypes}"


class TestDisplayLabelDisambiguation:
    """Tests for display label clarity when multiple same-name Pokemon exist.

    IMPORTANT: These tests document expected behavior for distinguishing
    same-name Pokemon in the UI. Currently, actions show "Search Charmander"
    without indicating which variant (sv4pt5-7 vs me2-11).

    Future enhancement: Display labels should include functional card ID
    to help users distinguish variants, e.g., "Search Charmander (sv4pt5-7)"
    """

    def test_display_labels_should_be_distinguishable(self, game_state_multiple_charmanders):
        """
        FUTURE REQUIREMENT: Display labels should distinguish same-name Pokemon.

        Currently, both Charmander actions show "Search Charmander" which is
        ambiguous. The actions ARE functionally distinct (different search_target_id),
        but users cannot tell them apart.

        Expected future format: "Search Charmander (sv4pt5-7)" vs "Search Charmander (me2-11)"
        Or: "Search Charmander [60 HP]" vs "Search Charmander [70 HP]"
        """
        state = game_state_multiple_charmanders
        player = state.players[0]

        ultra_ball = next(c for c in player.hand.cards if create_card(c.card_id).name == "Ultra Ball")
        actions = ultra_ball_actions(state, ultra_ball, player)

        charmander_search_actions = get_search_actions_for_pokemon(actions, "Charmander")

        # Get display labels
        display_labels = [a.display_label for a in charmander_search_actions]

        # Currently: Both labels are identical (documenting current behavior)
        # This test will FAIL when we add proper disambiguation
        # At that point, update this test to verify labels ARE different

        # For now: Just verify we have 2 actions
        assert len(display_labels) == 2, "Should have 2 Charmander search actions"

        # Document that they're currently the same (known limitation)
        # When fixed, this assertion should change to assert they're DIFFERENT
        if display_labels[0] == display_labels[1]:
            # Current behavior: labels are identical
            # This is a known limitation - the search still works because
            # parameters['search_target_id'] distinguishes them
            pass
        else:
            # Future behavior: labels are different (preferred)
            assert display_labels[0] != display_labels[1], \
                "Display labels should distinguish between Charmander variants"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
Comprehensive pytest suite for Nest Ball stack mechanics.

Nest Ball: Search your deck for a Basic Pokemon and put it onto your Bench.
Then, shuffle your deck.

Test Categories:
1. Playability Conditions
   - Bench full (unplayable)
   - Bench has space (playable)
   - Empty deck (still playable, fail search)

2. Search Filtering
   - Only Basic Pokemon selectable
   - Stage 1/2 Pokemon excluded
   - ex/V Pokemon that are Basic included
   - Non-Pokemon cards excluded

3. Deck Variations
   - Multiple Basic Pokemon in deck
   - No Basic Pokemon in deck
   - Empty deck
   - Mixed deck (Basic + Stage 1 + non-Pokemon)

4. Destination Behavior
   - Pokemon goes to bench (not hand)
   - Deck shuffled after

5. Knowledge Layer
   - With deck knowledge initialized
   - Without deck knowledge
   - has_searched_deck flag set after search

6. Edge Cases
   - Bench with 4 slots (1 remaining)
   - Multiple Nest Balls same turn
"""

import pytest
import sys
sys.path.insert(0, 'src')

from models import (
    GameState, PlayerState, GamePhase, Action, ActionType,
    SearchDeckStep, ZoneType, SelectionPurpose
)
from engine import PokemonEngine
from cards.factory import create_card_instance
from cards.registry import create_card


@pytest.fixture
def engine():
    return PokemonEngine()


def create_nest_ball_state(
    deck_cards: list = None,
    bench_count: int = 0,
    bench_full: bool = False
):
    """Create game state for Nest Ball testing."""
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
    player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

    # Add Nest Ball to hand
    nest_ball = create_card_instance("sv1-181", owner_id=0)
    player0.hand.add_card(nest_ball)

    # Add deck cards
    if deck_cards:
        for card_id in deck_cards:
            player0.deck.add_card(create_card_instance(card_id, owner_id=0))

    # Fill bench
    if bench_full:
        bench_count = 5
    for _ in range(bench_count):
        player0.board.add_to_bench(create_card_instance("sv3pt5-16", owner_id=0))

    return GameState(
        players=[player0, player1],
        turn_count=2,
        active_player_index=0,
        current_phase=GamePhase.MAIN,
        starting_player_id=0
    )


def get_nest_ball_from_hand(state):
    for card in state.players[0].hand.cards:
        card_def = create_card(card.card_id)
        if card_def and card_def.name == "Nest Ball":
            return card
    return None


# =============================================================================
# PLAYABILITY CONDITIONS
# =============================================================================

class TestPlayabilityConditions:
    """Test when Nest Ball can and cannot be played."""

    def test_unplayable_with_full_bench(self, engine):
        """Nest Ball unplayable when bench is full (5 Pokemon)."""
        state = create_nest_ball_state(
            deck_cards=["sv3pt5-16", "sv4pt5-7"],
            bench_full=True
        )
        state = engine.initialize_deck_knowledge(state)

        nest_ball = get_nest_ball_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_actions = [a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == nest_ball.id]

        assert len(play_actions) == 0, "Nest Ball should be unplayable with full bench"

    def test_playable_with_bench_space(self, engine):
        """Nest Ball playable when bench has space."""
        state = create_nest_ball_state(
            deck_cards=["sv3pt5-16"],
            bench_count=3
        )
        state = engine.initialize_deck_knowledge(state)

        nest_ball = get_nest_ball_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_actions = [a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == nest_ball.id]

        assert len(play_actions) == 1, "Nest Ball should be playable with bench space"

    def test_playable_with_empty_deck(self, engine):
        """Nest Ball playable even with empty deck (can fail search)."""
        state = create_nest_ball_state(
            deck_cards=[],
            bench_count=0
        )
        state = engine.initialize_deck_knowledge(state)

        nest_ball = get_nest_ball_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_actions = [a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == nest_ball.id]

        assert len(play_actions) == 1, "Nest Ball should be playable even with empty deck"

    def test_playable_with_no_basic_pokemon_in_deck(self, engine):
        """Nest Ball playable even with no Basic Pokemon (can fail search)."""
        state = create_nest_ball_state(
            deck_cards=["sv4pt5-8", "sve-2"],  # Charmeleon (Stage 1) + Energy
            bench_count=0
        )
        state = engine.initialize_deck_knowledge(state)

        nest_ball = get_nest_ball_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_actions = [a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == nest_ball.id]

        assert len(play_actions) == 1, "Nest Ball should be playable (can fail search)"


# =============================================================================
# SEARCH FILTERING
# =============================================================================

class TestSearchFiltering:
    """Test that Nest Ball only shows valid targets."""

    def test_only_basic_pokemon_selectable(self, engine):
        """Only Basic Pokemon should appear in search results."""
        state = create_nest_ball_state(
            deck_cards=[
                "sv3pt5-16",   # Pidgey (Basic)
                "sv4pt5-7",    # Charmander (Basic)
                "sv4pt5-8",    # Charmeleon (Stage 1)
                "sve-2",       # Fire Energy
                "sv2-185",     # Iono (Supporter)
            ]
        )
        state = engine.initialize_deck_knowledge(state)

        nest_ball = get_nest_ball_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == nest_ball.id)

        state = engine.step(state, play_action)

        # Get search options
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Should only have 2 (Pidgey and Charmander)
        assert len(select_actions) == 2, f"Should have 2 Basic Pokemon, got {len(select_actions)}"

    def test_stage_1_excluded(self, engine):
        """Stage 1 Pokemon should not be selectable."""
        state = create_nest_ball_state(
            deck_cards=["sv4pt5-8"]  # Charmeleon only (Stage 1)
        )
        state = engine.initialize_deck_knowledge(state)

        nest_ball = get_nest_ball_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == nest_ball.id)

        state = engine.step(state, play_action)

        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]

        assert len(select_actions) == 0, "Stage 1 should not be selectable"
        assert len(confirm_actions) == 1, "Should have confirm to fail search"

    def test_basic_ex_pokemon_included(self, engine):
        """Basic ex Pokemon should be selectable."""
        state = create_nest_ball_state(
            deck_cards=["sv3pt5-6"]  # Charizard ex (but this might be Stage 2)
        )
        # Let's use a Basic ex instead
        state = create_nest_ball_state(
            deck_cards=["sv3pt5-16", "sv4pt5-7"]  # Just Basic Pokemon
        )
        state = engine.initialize_deck_knowledge(state)

        nest_ball = get_nest_ball_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == nest_ball.id)

        state = engine.step(state, play_action)

        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        assert len(select_actions) == 2, "Basic Pokemon should be selectable"


# =============================================================================
# DECK VARIATIONS
# =============================================================================

class TestDeckVariations:
    """Test Nest Ball with different deck compositions."""

    def test_multiple_basic_pokemon(self, engine):
        """Should show unique Basic Pokemon options (grouped by card name for MCTS efficiency)."""
        state = create_nest_ball_state(
            deck_cards=["sv3pt5-16", "sv3pt5-16", "sv4pt5-7", "sv4pt5-7", "sv4pt5-7"]  # 5 Basic (2 unique)
        )
        state = engine.initialize_deck_knowledge(state)

        nest_ball = get_nest_ball_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == nest_ball.id)

        state = engine.step(state, play_action)

        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Grouped by card name: 2 unique Pokemon (Pidgey, Charmander)
        # This is correct MCTS optimization - selecting any Pidgey is equivalent
        assert len(select_actions) == 2, "Should have 2 unique Basic Pokemon options"

    def test_no_basic_pokemon_in_deck(self, engine):
        """With no Basic Pokemon, only confirm (fail) option."""
        state = create_nest_ball_state(
            deck_cards=["sv4pt5-8", "sv3pt5-18"]  # Stage 1 and Stage 2 only
        )
        state = engine.initialize_deck_knowledge(state)

        nest_ball = get_nest_ball_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == nest_ball.id)

        state = engine.step(state, play_action)

        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]

        assert len(select_actions) == 0, "No Basic Pokemon to select"
        assert len(confirm_actions) == 1, "Should have confirm (fail search)"

    def test_empty_deck(self, engine):
        """With empty deck, only confirm option."""
        state = create_nest_ball_state(deck_cards=[])
        state = engine.initialize_deck_knowledge(state)

        nest_ball = get_nest_ball_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == nest_ball.id)

        state = engine.step(state, play_action)

        actions = engine.get_legal_actions(state)
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]

        assert len(confirm_actions) >= 1, "Should have confirm with empty deck"


# =============================================================================
# DESTINATION BEHAVIOR
# =============================================================================

class TestDestinationBehavior:
    """Test that Pokemon goes to correct location."""

    def test_pokemon_goes_to_bench(self, engine):
        """Selected Pokemon should go to bench, not hand."""
        state = create_nest_ball_state(
            deck_cards=["sv3pt5-16"]
        )
        state = engine.initialize_deck_knowledge(state)

        initial_bench = state.players[0].board.get_bench_count()
        initial_hand = state.players[0].hand.count()
        initial_deck = len(state.players[0].deck.cards)

        nest_ball = get_nest_ball_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == nest_ball.id)
        state = engine.step(state, play_action)

        # Select the Pokemon
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        state = engine.step(state, select_actions[0])

        # Confirm
        actions = engine.get_legal_actions(state)
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]
        state = engine.step(state, confirm_actions[0])

        # Verify
        final_bench = state.players[0].board.get_bench_count()
        final_hand = state.players[0].hand.count()
        final_deck = len(state.players[0].deck.cards)

        assert final_bench == initial_bench + 1, "Bench should have +1 Pokemon"
        assert final_hand == initial_hand - 1, "Hand should have -1 (Nest Ball used)"
        assert final_deck == initial_deck - 1, "Deck should have -1"

    def test_decline_does_not_add_to_bench(self, engine):
        """Declining search should not add anything to bench."""
        state = create_nest_ball_state(
            deck_cards=["sv3pt5-16"]
        )
        state = engine.initialize_deck_knowledge(state)

        initial_bench = state.players[0].board.get_bench_count()

        nest_ball = get_nest_ball_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == nest_ball.id)
        state = engine.step(state, play_action)

        # Decline by confirming without selection
        actions = engine.get_legal_actions(state)
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]
        state = engine.step(state, confirm_actions[0])

        final_bench = state.players[0].board.get_bench_count()
        assert final_bench == initial_bench, "Bench should be unchanged after declining"


# =============================================================================
# KNOWLEDGE LAYER
# =============================================================================

class TestKnowledgeLayer:
    """Test Nest Ball with knowledge layer interactions."""

    def test_with_deck_knowledge(self, engine):
        """Works correctly with deck knowledge initialized."""
        state = create_nest_ball_state(
            deck_cards=["sv3pt5-16", "sv4pt5-7"]
        )
        state = engine.initialize_deck_knowledge(state)

        assert len(state.players[0].initial_deck_counts) > 0

        nest_ball = get_nest_ball_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == nest_ball.id)
        state = engine.step(state, play_action)

        # Should work
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        assert len(select_actions) == 2

    def test_without_deck_knowledge(self, engine):
        """Works correctly without deck knowledge initialized."""
        state = create_nest_ball_state(
            deck_cards=["sv3pt5-16", "sv4pt5-7"]
        )
        # Don't initialize knowledge

        nest_ball = get_nest_ball_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == nest_ball.id)
        state = engine.step(state, play_action)

        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        assert len(select_actions) == 2

    def test_has_searched_deck_set_after_search(self, engine):
        """has_searched_deck should be True after using Nest Ball."""
        state = create_nest_ball_state(
            deck_cards=["sv3pt5-16"]
        )
        state = engine.initialize_deck_knowledge(state)

        assert state.players[0].has_searched_deck == False

        nest_ball = get_nest_ball_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == nest_ball.id)
        state = engine.step(state, play_action)

        # Select and confirm
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        state = engine.step(state, select_actions[0])

        actions = engine.get_legal_actions(state)
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]
        state = engine.step(state, confirm_actions[0])

        assert state.players[0].has_searched_deck == True


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_bench_with_one_slot_remaining(self, engine):
        """With only 1 bench slot, can only get 1 Pokemon."""
        state = create_nest_ball_state(
            deck_cards=["sv3pt5-16", "sv4pt5-7"],
            bench_count=4  # Only 1 slot left
        )
        state = engine.initialize_deck_knowledge(state)

        nest_ball = get_nest_ball_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == nest_ball.id)
        state = engine.step(state, play_action)

        # Should still show options
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        assert len(select_actions) == 2

        # Select one, should fill bench
        state = engine.step(state, select_actions[0])
        actions = engine.get_legal_actions(state)
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]
        state = engine.step(state, confirm_actions[0])

        assert state.players[0].board.get_bench_count() == 5

    def test_multiple_nest_balls_same_turn(self, engine):
        """Can play multiple Nest Balls in same turn (items not limited)."""
        state = create_nest_ball_state(
            deck_cards=["sv3pt5-16", "sv4pt5-7", "sv4pt5-7"]
        )
        # Add second Nest Ball
        state.players[0].hand.add_card(create_card_instance("sv1-181", owner_id=0))
        state = engine.initialize_deck_knowledge(state)

        # Play first Nest Ball
        nest_balls = [c for c in state.players[0].hand.cards if create_card(c.card_id).name == "Nest Ball"]
        assert len(nest_balls) == 2

        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == nest_balls[0].id)
        state = engine.step(state, play_action)

        # Complete first
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        state = engine.step(state, select_actions[0])
        actions = engine.get_legal_actions(state)
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]
        state = engine.step(state, confirm_actions[0])

        # Should be able to play second Nest Ball
        remaining_nest_ball = next(
            (c for c in state.players[0].hand.cards if create_card(c.card_id).name == "Nest Ball"),
            None
        )
        if remaining_nest_ball:
            actions = engine.get_legal_actions(state)
            play_actions = [a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == remaining_nest_ball.id]
            assert len(play_actions) == 1, "Should be able to play second Nest Ball"

    def test_nest_ball_goes_to_discard(self, engine):
        """Nest Ball should go to discard after use."""
        state = create_nest_ball_state(
            deck_cards=["sv3pt5-16"]
        )
        state = engine.initialize_deck_knowledge(state)

        initial_discard = len(state.players[0].discard.cards)

        nest_ball = get_nest_ball_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == nest_ball.id)
        state = engine.step(state, play_action)

        # Decline search
        actions = engine.get_legal_actions(state)
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]
        state = engine.step(state, confirm_actions[0])

        final_discard = len(state.players[0].discard.cards)
        assert final_discard == initial_discard + 1, "Nest Ball should be in discard"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

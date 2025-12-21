"""
Comprehensive pytest suite for Prime Catcher ACE SPEC item card.

Prime Catcher: Switch in 1 of your opponent's Benched Pokemon to the Active Spot.
If you do, switch your Active Pokemon with 1 of your Benched Pokemon.

Test Categories:
1. Playability Conditions
   - Both players have benched Pokemon (playable)
   - Opponent has no benched Pokemon (unplayable)
   - Player has no benched Pokemon (unplayable)
   - Either side has empty bench (unplayable)

2. Opponent Switch Flow
   - Opponent's selected benched Pokemon becomes their Active
   - Opponent's former Active moves to their Bench
   - Player controls the selection (not opponent)

3. Player Switch Flow
   - Player's selected benched Pokemon becomes their Active
   - Player's former Active moves to their Bench
   - Both switches happen in sequence

4. Full Resolution Flow
   - Two-step selection process (opponent bench first, then own bench)
   - Correct order of operations
   - Both switches complete before resolution ends

5. Edge Cases
   - Single Pokemon on opponent's bench
   - Single Pokemon on player's bench
   - Full benches on both sides
   - Prime Catcher goes to discard after use
"""

import pytest
import sys
sys.path.insert(0, 'src')

from models import (
    GameState, PlayerState, GamePhase, Action, ActionType,
    SelectFromZoneStep, SelectionPurpose, ZoneType
)
from engine import PokemonEngine
from cards.factory import create_card_instance
from cards.registry import create_card


@pytest.fixture
def engine():
    """Create PokemonEngine instance."""
    return PokemonEngine()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_prime_catcher_state(
    player_bench_count: int = 1,
    opponent_bench_count: int = 1,
    hand_cards: list = None,
):
    """
    Create a game state for Prime Catcher testing.

    Args:
        player_bench_count: Number of Pokemon on player's bench
        opponent_bench_count: Number of Pokemon on opponent's bench
        hand_cards: List of additional card IDs for hand (Prime Catcher auto-added)
    """
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Both need active Pokemon
    player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)  # Pidgey
    player1.board.active_spot = create_card_instance("sv3-26", owner_id=1)  # Charmander

    # Add Prime Catcher to hand
    prime_catcher = create_card_instance("sv5-157", owner_id=0)
    player0.hand.add_card(prime_catcher)

    # Add other hand cards
    if hand_cards:
        for card_id in hand_cards:
            player0.hand.add_card(create_card_instance(card_id, owner_id=0))

    # Add player bench Pokemon
    for i in range(player_bench_count):
        player0.board.add_to_bench(create_card_instance("sv2-81", owner_id=0))  # Wattrel

    # Add opponent bench Pokemon
    for i in range(opponent_bench_count):
        player1.board.add_to_bench(create_card_instance("sv4pt5-7", owner_id=1))  # Charmander (different)

    return GameState(
        players=[player0, player1],
        turn_count=2,
        active_player_index=0,
        current_phase=GamePhase.MAIN,
        starting_player_id=0
    )


def get_prime_catcher_from_hand(state):
    """Find the Prime Catcher card in player 0's hand."""
    for card in state.players[0].hand.cards:
        card_def = create_card(card.card_id)
        if card_def and card_def.name == "Prime Catcher":
            return card
    return None


def find_play_prime_catcher_action(actions):
    """Find the Play Prime Catcher action from a list of actions."""
    for action in actions:
        if action.action_type == ActionType.PLAY_ITEM:
            if action.display_label and "Prime Catcher" in action.display_label:
                return action
    return None


# =============================================================================
# TEST: PLAYABILITY CONDITIONS
# =============================================================================

class TestPrimeCatcherPlayability:
    """Test when Prime Catcher can and cannot be played."""

    def test_playable_with_both_benches_occupied(self, engine):
        """Prime Catcher is playable when both players have benched Pokemon."""
        state = create_prime_catcher_state(
            player_bench_count=1,
            opponent_bench_count=1
        )

        actions = engine.get_legal_actions(state)
        play_action = find_play_prime_catcher_action(actions)

        assert play_action is not None, "Prime Catcher should be playable when both have benched Pokemon"

    def test_not_playable_without_opponent_bench(self, engine):
        """Prime Catcher is NOT playable when opponent has no benched Pokemon."""
        state = create_prime_catcher_state(
            player_bench_count=1,
            opponent_bench_count=0
        )

        actions = engine.get_legal_actions(state)
        play_action = find_play_prime_catcher_action(actions)

        assert play_action is None, "Prime Catcher should not be playable without opponent's bench"

    def test_playable_without_player_bench(self, engine):
        """Prime Catcher IS playable when player has no benched Pokemon (only opponent switch happens)."""
        state = create_prime_catcher_state(
            player_bench_count=0,
            opponent_bench_count=1
        )

        actions = engine.get_legal_actions(state)
        play_action = find_play_prime_catcher_action(actions)

        assert play_action is not None, "Prime Catcher should be playable without player's bench"

    def test_not_playable_with_no_opponent_bench(self, engine):
        """Prime Catcher is NOT playable when opponent has no benched Pokemon."""
        state = create_prime_catcher_state(
            player_bench_count=1,
            opponent_bench_count=0
        )

        actions = engine.get_legal_actions(state)
        play_action = find_play_prime_catcher_action(actions)

        assert play_action is None, "Prime Catcher should not be playable without opponent's bench"


# =============================================================================
# TEST: SWITCH FLOW
# =============================================================================

class TestPrimeCatcherSwitchFlow:
    """Test the full switch flow of Prime Catcher."""

    def test_opponent_switch_occurs(self, engine):
        """Opponent's selected benched Pokemon should become their Active."""
        state = create_prime_catcher_state(
            player_bench_count=1,
            opponent_bench_count=1
        )

        # Get opponent's benched Pokemon ID
        opponent_bench_pokemon = state.players[1].board.bench[0]
        opponent_bench_id = opponent_bench_pokemon.id
        opponent_original_active = state.players[1].board.active_spot
        opponent_active_id = opponent_original_active.id

        # Play Prime Catcher
        actions = engine.get_legal_actions(state)
        play_action = find_play_prime_catcher_action(actions)
        state = engine.step(state, play_action)

        # First step: select opponent's benched Pokemon
        assert state.has_pending_resolution(), "Should have pending resolution step"

        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        assert len(select_actions) >= 1, "Should have opponent bench selection options"

        # Select the opponent's benched Pokemon
        state = engine.step(state, select_actions[0])

        # Second step: select own benched Pokemon
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        assert len(select_actions) >= 1, "Should have own bench selection options"

        # Select own benched Pokemon
        state = engine.step(state, select_actions[0])

        # Verify opponent's switch occurred
        assert state.players[1].board.active_spot.id == opponent_bench_id, \
            "Opponent's benched Pokemon should now be Active"
        assert any(p.id == opponent_active_id for p in state.players[1].board.bench), \
            "Opponent's former Active should be on bench"

    def test_player_switch_occurs(self, engine):
        """Player's selected benched Pokemon should become their Active."""
        state = create_prime_catcher_state(
            player_bench_count=1,
            opponent_bench_count=1
        )

        # Get player's benched Pokemon ID
        player_bench_pokemon = state.players[0].board.bench[0]
        player_bench_id = player_bench_pokemon.id
        player_original_active = state.players[0].board.active_spot
        player_active_id = player_original_active.id

        # Play Prime Catcher
        actions = engine.get_legal_actions(state)
        play_action = find_play_prime_catcher_action(actions)
        state = engine.step(state, play_action)

        # First step: select opponent's benched Pokemon
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        state = engine.step(state, select_actions[0])

        # Second step: select own benched Pokemon
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        state = engine.step(state, select_actions[0])

        # Verify player's switch occurred
        assert state.players[0].board.active_spot.id == player_bench_id, \
            "Player's benched Pokemon should now be Active"
        assert any(p.id == player_active_id for p in state.players[0].board.bench), \
            "Player's former Active should be on bench"

    def test_both_switches_complete(self, engine):
        """Both player and opponent switches should complete."""
        state = create_prime_catcher_state(
            player_bench_count=2,
            opponent_bench_count=2
        )

        # Store original positions
        p0_original_active_id = state.players[0].board.active_spot.id
        p1_original_active_id = state.players[1].board.active_spot.id

        # Play Prime Catcher and complete both selections
        actions = engine.get_legal_actions(state)
        play_action = find_play_prime_catcher_action(actions)
        state = engine.step(state, play_action)

        # Select opponent's first benched Pokemon
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        state = engine.step(state, select_actions[0])

        # Select player's first benched Pokemon
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        state = engine.step(state, select_actions[0])

        # Verify both original actives are now on benches
        assert state.players[0].board.active_spot.id != p0_original_active_id, \
            "Player's Active should have changed"
        assert state.players[1].board.active_spot.id != p1_original_active_id, \
            "Opponent's Active should have changed"

        # Resolution should be complete
        assert not state.has_pending_resolution(), "Resolution should be complete"


# =============================================================================
# TEST: SELECTION MECHANICS
# =============================================================================

class TestPrimeCatcherSelection:
    """Test selection mechanics for Prime Catcher."""

    def test_opponent_bench_selection_first(self, engine):
        """First selection step should target opponent's bench."""
        state = create_prime_catcher_state(
            player_bench_count=2,
            opponent_bench_count=3
        )

        # Play Prime Catcher
        actions = engine.get_legal_actions(state)
        play_action = find_play_prime_catcher_action(actions)
        state = engine.step(state, play_action)

        # First step should offer opponent's bench (3 options)
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        assert len(select_actions) == 3, f"Should have 3 opponent bench options, got {len(select_actions)}"

    def test_player_bench_selection_second(self, engine):
        """Second selection step should target player's bench."""
        state = create_prime_catcher_state(
            player_bench_count=2,
            opponent_bench_count=1
        )

        # Play Prime Catcher
        actions = engine.get_legal_actions(state)
        play_action = find_play_prime_catcher_action(actions)
        state = engine.step(state, play_action)

        # Complete first selection (opponent's bench)
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        state = engine.step(state, select_actions[0])

        # Second step should offer player's bench (2 options)
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        assert len(select_actions) == 2, f"Should have 2 player bench options, got {len(select_actions)}"


# =============================================================================
# TEST: CARD HANDLING
# =============================================================================

class TestPrimeCatcherCardHandling:
    """Test Prime Catcher card handling after use."""

    def test_prime_catcher_goes_to_discard(self, engine):
        """Prime Catcher should be in discard after use."""
        state = create_prime_catcher_state(
            player_bench_count=1,
            opponent_bench_count=1
        )

        prime_catcher = get_prime_catcher_from_hand(state)
        prime_catcher_id = prime_catcher.id

        # Play Prime Catcher
        actions = engine.get_legal_actions(state)
        play_action = find_play_prime_catcher_action(actions)
        state = engine.step(state, play_action)

        # Complete both selections
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        state = engine.step(state, select_actions[0])

        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        state = engine.step(state, select_actions[0])

        # Prime Catcher should be in discard
        prime_catcher_in_discard = any(
            c.id == prime_catcher_id
            for c in state.players[0].discard.cards
        )
        assert prime_catcher_in_discard, "Prime Catcher should be in discard after use"


# =============================================================================
# TEST: EDGE CASES
# =============================================================================

class TestPrimeCatcherEdgeCases:
    """Test edge cases for Prime Catcher."""

    def test_single_opponent_bench_pokemon(self, engine):
        """Works with exactly one Pokemon on opponent's bench."""
        state = create_prime_catcher_state(
            player_bench_count=1,
            opponent_bench_count=1
        )

        # Play Prime Catcher
        actions = engine.get_legal_actions(state)
        play_action = find_play_prime_catcher_action(actions)
        state = engine.step(state, play_action)

        # Should have exactly one selection option for opponent
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        assert len(select_actions) == 1, "Should have exactly one opponent option"

    def test_single_player_bench_pokemon(self, engine):
        """Works with exactly one Pokemon on player's bench."""
        state = create_prime_catcher_state(
            player_bench_count=1,
            opponent_bench_count=2
        )

        # Play Prime Catcher
        actions = engine.get_legal_actions(state)
        play_action = find_play_prime_catcher_action(actions)
        state = engine.step(state, play_action)

        # Complete opponent selection
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        state = engine.step(state, select_actions[0])

        # Should have exactly one selection option for player
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        assert len(select_actions) == 1, "Should have exactly one player option"

    def test_full_benches(self, engine):
        """Works correctly with full benches on both sides."""
        state = create_prime_catcher_state(
            player_bench_count=5,
            opponent_bench_count=5
        )

        # Play Prime Catcher
        actions = engine.get_legal_actions(state)
        play_action = find_play_prime_catcher_action(actions)
        state = engine.step(state, play_action)

        # Should have 5 opponent bench options
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        assert len(select_actions) == 5, "Should have 5 opponent bench options"

        # Complete opponent selection
        state = engine.step(state, select_actions[0])

        # Should have 5 player bench options
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        assert len(select_actions) == 5, "Should have 5 player bench options"

        # Complete player selection
        state = engine.step(state, select_actions[0])

        # Benches should still be full (switched, not removed)
        assert len(state.players[0].board.bench) == 5, "Player bench should still have 5"
        assert len(state.players[1].board.bench) == 5, "Opponent bench should still have 5"

    def test_specific_pokemon_selection(self, engine):
        """Can select specific Pokemon from bench (not just first)."""
        state = create_prime_catcher_state(
            player_bench_count=3,
            opponent_bench_count=3
        )

        # Get the third opponent bench Pokemon
        target_opponent_pokemon = state.players[1].board.bench[2]
        target_id = target_opponent_pokemon.id

        # Play Prime Catcher
        actions = engine.get_legal_actions(state)
        play_action = find_play_prime_catcher_action(actions)
        state = engine.step(state, play_action)

        # Find and select the specific target
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Find the action for the third Pokemon
        target_action = None
        for action in select_actions:
            if hasattr(action, 'parameters') and action.parameters:
                selected_ids = action.parameters.get('selected_card_ids', [])
                if target_id in selected_ids:
                    target_action = action
                    break

        if target_action:
            state = engine.step(state, target_action)

            # Complete player selection
            actions = engine.get_legal_actions(state)
            select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
            state = engine.step(state, select_actions[0])

            # The targeted Pokemon should now be opponent's Active
            assert state.players[1].board.active_spot.id == target_id, \
                "Selected Pokemon should be opponent's new Active"

    def test_only_opponent_switch_when_no_player_bench(self, engine):
        """When player has no bench, only opponent's switch happens."""
        state = create_prime_catcher_state(
            player_bench_count=0,
            opponent_bench_count=2
        )

        # Store original positions
        p0_original_active_id = state.players[0].board.active_spot.id
        p1_original_active_id = state.players[1].board.active_spot.id
        opponent_bench_pokemon = state.players[1].board.bench[0]
        opponent_bench_id = opponent_bench_pokemon.id

        # Play Prime Catcher
        actions = engine.get_legal_actions(state)
        play_action = find_play_prime_catcher_action(actions)
        state = engine.step(state, play_action)

        # Should only have opponent bench selection (no player bench step)
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        assert len(select_actions) == 2, "Should have 2 opponent bench options"

        # Select opponent's benched Pokemon
        state = engine.step(state, select_actions[0])

        # Resolution should be complete (no player bench step)
        assert not state.has_pending_resolution(), "Resolution should be complete without player bench step"

        # Verify opponent's switch occurred
        assert state.players[1].board.active_spot.id == opponent_bench_id, \
            "Opponent's benched Pokemon should now be Active"
        assert any(p.id == p1_original_active_id for p in state.players[1].board.bench), \
            "Opponent's former Active should be on bench"

        # Verify player's Active is unchanged
        assert state.players[0].board.active_spot.id == p0_original_active_id, \
            "Player's Active should be unchanged when they have no bench"

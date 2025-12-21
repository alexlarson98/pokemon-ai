"""
Tests for Area Zero Underdepths Stadium.

Stadium Effect:
- Each player who has any Tera Pokemon in play can have up to 8 Pokemon on their Bench.
- If a player no longer has any Tera Pokemon in play, that player discards Pokemon
  from their Bench until they have 5.
- When this card leaves play, both players discard Pokemon from their Bench until
  they have 5, and the player who played this card discards first.
"""

import pytest
from cards.factory import create_card_instance
from engine import PokemonEngine
from models import (
    GameState, PlayerState, Board, GamePhase,
    Action, ActionType
)


@pytest.fixture
def engine():
    return PokemonEngine()


def create_test_state():
    """Create a basic test state."""
    p0_board = Board()
    p1_board = Board()

    p0 = PlayerState(player_id=0, name='Player 0', board=p0_board)
    p1 = PlayerState(player_id=1, name='Player 1', board=p1_board)

    state = GameState(players=[p0, p1])

    # Give both players active Pokemon
    p0_board.active_spot = create_card_instance('sv7-114', owner_id=0)  # Hoothoot
    p1_board.active_spot = create_card_instance('sv7-114', owner_id=1)  # Hoothoot

    state.current_phase = GamePhase.MAIN

    return state


class TestBenchSizeWithStadium:
    """Test that bench size increases to 8 with Area Zero Underdepths + Tera Pokemon."""

    def test_player0_gets_8_bench_with_tera(self, engine):
        """Player 0 should get 8 max bench when they have Tera Pokemon."""
        state = create_test_state()
        p0 = state.players[0]

        # Place stadium
        stadium = create_card_instance('sv7-131', owner_id=0)
        p0.hand.add_card(stadium)

        state.active_player_index = 0
        play_stadium = Action(
            action_type=ActionType.PLAY_STADIUM,
            player_id=0,
            card_id=stadium.id
        )
        state = engine._apply_action(state, play_stadium)

        # Bench size should still be 5 (no Tera Pokemon yet)
        assert p0.board.max_bench_size == 5

        # Add Terapagos ex to bench
        terapagos = create_card_instance('sv7-128', owner_id=0)
        p0.hand.add_card(terapagos)

        play_tera = Action(
            action_type=ActionType.PLAY_BASIC,
            player_id=0,
            card_id=terapagos.id
        )
        state = engine._apply_action(state, play_tera)

        # Now bench size should be 8
        assert p0.board.max_bench_size == 8

    def test_player1_gets_8_bench_with_tera(self, engine):
        """Player 1 should get 8 max bench when they have Tera Pokemon."""
        state = create_test_state()
        p0 = state.players[0]
        p1 = state.players[1]

        # Player 0 places stadium
        stadium = create_card_instance('sv7-131', owner_id=0)
        p0.hand.add_card(stadium)

        state.active_player_index = 0
        play_stadium = Action(
            action_type=ActionType.PLAY_STADIUM,
            player_id=0,
            card_id=stadium.id
        )
        state = engine._apply_action(state, play_stadium)

        # Player 1's bench size should still be 5 (no Tera Pokemon yet)
        assert p1.board.max_bench_size == 5

        # Player 1 adds Terapagos ex to bench
        terapagos = create_card_instance('sv7-128', owner_id=1)
        p1.hand.add_card(terapagos)

        state.active_player_index = 1
        play_tera = Action(
            action_type=ActionType.PLAY_BASIC,
            player_id=1,
            card_id=terapagos.id
        )
        state = engine._apply_action(state, play_tera)

        # Now Player 1's bench size should be 8
        assert p1.board.max_bench_size == 8

    def test_both_players_get_8_bench(self, engine):
        """Both players should get 8 max bench when both have Tera Pokemon."""
        state = create_test_state()
        p0 = state.players[0]
        p1 = state.players[1]

        # Place stadium
        stadium = create_card_instance('sv7-131', owner_id=0)
        p0.hand.add_card(stadium)

        state.active_player_index = 0
        play_stadium = Action(
            action_type=ActionType.PLAY_STADIUM,
            player_id=0,
            card_id=stadium.id
        )
        state = engine._apply_action(state, play_stadium)

        # Player 0 adds Terapagos
        tera0 = create_card_instance('sv7-128', owner_id=0)
        p0.hand.add_card(tera0)
        state = engine._apply_action(state, Action(
            action_type=ActionType.PLAY_BASIC,
            player_id=0,
            card_id=tera0.id
        ))

        # Player 1 adds Terapagos
        tera1 = create_card_instance('sv7-128', owner_id=1)
        p1.hand.add_card(tera1)
        state.active_player_index = 1
        state = engine._apply_action(state, Action(
            action_type=ActionType.PLAY_BASIC,
            player_id=1,
            card_id=tera1.id
        ))

        # Both should have 8
        assert p0.board.max_bench_size == 8
        assert p1.board.max_bench_size == 8


class TestBuddyBuddyPoffinWithStadium:
    """Test that Buddy-Buddy Poffin correctly sees the 8-bench limit."""

    def test_poffin_playable_when_tera_in_play(self, engine):
        """Buddy-Buddy Poffin should be playable when player has Tera + 5 on bench."""
        state = create_test_state()
        p0 = state.players[0]

        # Place stadium
        stadium = create_card_instance('sv7-131', owner_id=0)
        p0.hand.add_card(stadium)
        state.active_player_index = 0
        state = engine._apply_action(state, Action(
            action_type=ActionType.PLAY_STADIUM,
            player_id=0,
            card_id=stadium.id
        ))

        # Add Terapagos to bench
        terapagos = create_card_instance('sv7-128', owner_id=0)
        p0.hand.add_card(terapagos)
        state = engine._apply_action(state, Action(
            action_type=ActionType.PLAY_BASIC,
            player_id=0,
            card_id=terapagos.id
        ))

        # Add 4 more to bench (5 total with Terapagos)
        for _ in range(4):
            pokemon = create_card_instance('sv7-114', owner_id=0)
            p0.hand.add_card(pokemon)
            state = engine._apply_action(state, Action(
                action_type=ActionType.PLAY_BASIC,
                player_id=0,
                card_id=pokemon.id
            ))

        # Verify: 5 on bench, max_bench_size is 8
        assert p0.board.get_bench_count() == 5
        assert p0.board.max_bench_size == 8

        # Add Buddy-Buddy Poffin to hand
        poffin = create_card_instance('sv5-144', owner_id=0)  # Buddy-Buddy Poffin
        p0.hand.add_card(poffin)

        # Get legal actions
        actions = engine.get_legal_actions(state)

        # Find the Poffin action
        poffin_action = None
        for a in actions:
            if a.action_type == ActionType.PLAY_ITEM and a.card_id == poffin.id:
                poffin_action = a
                break

        assert poffin_action is not None, "Buddy-Buddy Poffin should be playable with 5 on bench and 8 max"

    def test_poffin_not_playable_at_8_bench(self, engine):
        """Buddy-Buddy Poffin should NOT be playable when player already has 8 on bench."""
        state = create_test_state()
        p0 = state.players[0]

        # Place stadium
        stadium = create_card_instance('sv7-131', owner_id=0)
        p0.hand.add_card(stadium)
        state.active_player_index = 0
        state = engine._apply_action(state, Action(
            action_type=ActionType.PLAY_STADIUM,
            player_id=0,
            card_id=stadium.id
        ))

        # Add Terapagos to bench
        terapagos = create_card_instance('sv7-128', owner_id=0)
        p0.hand.add_card(terapagos)
        state = engine._apply_action(state, Action(
            action_type=ActionType.PLAY_BASIC,
            player_id=0,
            card_id=terapagos.id
        ))

        # Add 7 more to bench (8 total with Terapagos)
        for _ in range(7):
            pokemon = create_card_instance('sv7-114', owner_id=0)
            p0.hand.add_card(pokemon)
            state = engine._apply_action(state, Action(
                action_type=ActionType.PLAY_BASIC,
                player_id=0,
                card_id=pokemon.id
            ))

        # Verify: 8 on bench, max_bench_size is 8
        assert p0.board.get_bench_count() == 8
        assert p0.board.max_bench_size == 8

        # Add Buddy-Buddy Poffin to hand
        poffin = create_card_instance('sv5-144', owner_id=0)  # Buddy-Buddy Poffin
        p0.hand.add_card(poffin)

        # Get legal actions
        actions = engine.get_legal_actions(state)

        # Poffin should NOT be playable
        poffin_action = None
        for a in actions:
            if a.action_type == ActionType.PLAY_ITEM and a.card_id == poffin.id:
                poffin_action = a
                break

        assert poffin_action is None, "Buddy-Buddy Poffin should NOT be playable at 8 bench"


class TestOpponentBenefitsFromStadium:
    """Test that the opponent also benefits from the stadium."""

    def test_opponent_poffin_works_with_stadium(self, engine):
        """Opponent's Buddy-Buddy Poffin should work when they have Tera + 5 bench."""
        state = create_test_state()
        p0 = state.players[0]
        p1 = state.players[1]

        # Player 0 places stadium
        stadium = create_card_instance('sv7-131', owner_id=0)
        p0.hand.add_card(stadium)
        state.active_player_index = 0
        state = engine._apply_action(state, Action(
            action_type=ActionType.PLAY_STADIUM,
            player_id=0,
            card_id=stadium.id
        ))

        # Switch to Player 1
        state.active_player_index = 1

        # Player 1 adds Terapagos to bench
        terapagos = create_card_instance('sv7-128', owner_id=1)
        p1.hand.add_card(terapagos)
        state = engine._apply_action(state, Action(
            action_type=ActionType.PLAY_BASIC,
            player_id=1,
            card_id=terapagos.id
        ))

        # Player 1 adds 4 more to bench (5 total)
        for _ in range(4):
            pokemon = create_card_instance('sv7-114', owner_id=1)
            p1.hand.add_card(pokemon)
            state = engine._apply_action(state, Action(
                action_type=ActionType.PLAY_BASIC,
                player_id=1,
                card_id=pokemon.id
            ))

        # Verify: Player 1 has 5 on bench, max_bench_size is 8
        assert p1.board.get_bench_count() == 5
        assert p1.board.max_bench_size == 8, f"P1 should have 8 max bench, got {p1.board.max_bench_size}"

        # Add Buddy-Buddy Poffin to Player 1's hand
        poffin = create_card_instance('sv5-144', owner_id=1)
        p1.hand.add_card(poffin)

        # Get legal actions for Player 1
        actions = engine.get_legal_actions(state)

        # Find the Poffin action
        poffin_action = None
        for a in actions:
            if a.action_type == ActionType.PLAY_ITEM and a.card_id == poffin.id:
                poffin_action = a
                break

        assert poffin_action is not None, "Player 1's Buddy-Buddy Poffin should be playable"

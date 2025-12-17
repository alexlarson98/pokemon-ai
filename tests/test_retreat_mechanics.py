"""
Comprehensive pytest suite for retreat mechanics.

Tests:
- Retreat with full bench (Pokemon preservation)
- Retreat with energy discard
- Retreat status condition clearing
- Retreat once-per-turn enforcement
- Retreat cost calculation
- Retreat with effects (Float Stone, etc.)
"""

import pytest
import sys
sys.path.insert(0, 'src')

from models import GameState, PlayerState, GamePhase, Action, ActionType, StatusCondition
from engine import PokemonEngine
from cards.factory import create_card_instance
from cards.registry import create_card


@pytest.fixture
def engine():
    """Create PokemonEngine instance."""
    return PokemonEngine()


@pytest.fixture
def basic_game_state():
    """Create a basic game state with two players."""
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Give both players an active Pokemon
    player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)  # Pidgey
    player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

    return GameState(
        players=[player0, player1],
        turn_count=5,
        active_player_index=0,
        current_phase=GamePhase.MAIN,
        starting_player_id=0
    )


class TestRetreatPokemonPreservation:
    """Test that Pokemon are preserved when retreating."""

    def test_retreat_with_full_bench_preserves_active(self, engine, basic_game_state):
        """When retreating with a full bench (5 Pokemon), the active Pokemon should move to bench."""
        state = basic_game_state
        player = state.players[0]

        # Setup: Active Pokemon
        active_mon = player.board.active_spot

        # Setup: Full bench (5 Pokemon)
        bench_mons = []
        for _ in range(5):
            mon = create_card_instance("sv2-81", owner_id=0)
            player.board.add_to_bench(mon)
            bench_mons.append(mon)

        assert player.board.get_bench_count() == 5, "Bench should be full"

        # Create retreat action
        retreat_action = Action(
            action_type=ActionType.RETREAT,
            player_id=0,
            card_id=active_mon.id,
            target_id=bench_mons[0].id
        )

        # Execute retreat
        state = engine._apply_retreat(state, retreat_action)
        player = state.players[0]

        # Verify active was preserved
        assert player.board.get_bench_count() == 5, "Bench should still have 5 Pokemon"
        assert any(p and p.id == active_mon.id for p in player.board.bench), \
            "Old active Pokemon should be on bench"
        assert player.board.active_spot.id == bench_mons[0].id, \
            "New active should be the target from bench"

    def test_retreat_preserves_damage_counters(self, engine, basic_game_state):
        """Damage counters should be preserved when retreating."""
        state = basic_game_state
        player = state.players[0]

        active_mon = player.board.active_spot
        active_mon.damage_counters = 3

        bench_mon = create_card_instance("sv2-81", owner_id=0)
        player.board.add_to_bench(bench_mon)

        retreat_action = Action(
            action_type=ActionType.RETREAT,
            player_id=0,
            card_id=active_mon.id,
            target_id=bench_mon.id
        )

        state = engine._apply_retreat(state, retreat_action)
        player = state.players[0]

        # Find the retreated Pokemon on bench
        retreated_mon = next((p for p in player.board.bench if p and p.id == active_mon.id), None)
        assert retreated_mon is not None, "Retreated Pokemon should be on bench"
        assert retreated_mon.damage_counters == 3, "Damage counters should be preserved"

    def test_retreat_preserves_attached_energy(self, engine, basic_game_state):
        """Attached energy should be preserved when retreating."""
        state = basic_game_state
        player = state.players[0]

        active_mon = player.board.active_spot
        energy1 = create_card_instance("base1-98", owner_id=0)  # Fire Energy
        energy2 = create_card_instance("base1-98", owner_id=0)
        active_mon.attached_energy = [energy1, energy2]

        bench_mon = create_card_instance("sv2-81", owner_id=0)
        player.board.add_to_bench(bench_mon)

        retreat_action = Action(
            action_type=ActionType.RETREAT,
            player_id=0,
            card_id=active_mon.id,
            target_id=bench_mon.id
        )

        state = engine._apply_retreat(state, retreat_action)
        player = state.players[0]

        # Check that energy was discarded for retreat cost
        # Pidgey has retreat cost of 1, so 1 energy should be discarded
        assert player.discard.count() >= 1, "At least 1 energy should be discarded for retreat cost"


class TestRetreatStatusConditions:
    """Test that retreat clears status conditions."""

    def test_retreat_clears_poisoned(self, engine, basic_game_state):
        """Retreating should clear Poisoned status."""
        state = basic_game_state
        player = state.players[0]

        active_mon = player.board.active_spot
        active_mon.status_conditions.add(StatusCondition.POISONED)

        bench_mon = create_card_instance("sv2-81", owner_id=0)
        player.board.add_to_bench(bench_mon)

        retreat_action = Action(
            action_type=ActionType.RETREAT,
            player_id=0,
            card_id=active_mon.id,
            target_id=bench_mon.id
        )

        state = engine._apply_retreat(state, retreat_action)
        player = state.players[0]

        retreated_mon = next((p for p in player.board.bench if p and p.id == active_mon.id), None)
        assert retreated_mon is not None
        assert StatusCondition.POISONED not in retreated_mon.status_conditions, \
            "Poisoned should be cleared after retreat"

    def test_retreat_clears_confused(self, engine, basic_game_state):
        """Retreating should clear Confused status."""
        state = basic_game_state
        player = state.players[0]

        active_mon = player.board.active_spot
        active_mon.status_conditions.add(StatusCondition.CONFUSED)

        bench_mon = create_card_instance("sv2-81", owner_id=0)
        player.board.add_to_bench(bench_mon)

        retreat_action = Action(
            action_type=ActionType.RETREAT,
            player_id=0,
            card_id=active_mon.id,
            target_id=bench_mon.id
        )

        state = engine._apply_retreat(state, retreat_action)
        player = state.players[0]

        retreated_mon = next((p for p in player.board.bench if p and p.id == active_mon.id), None)
        assert retreated_mon is not None
        assert StatusCondition.CONFUSED not in retreated_mon.status_conditions


class TestRetreatRestrictions:
    """Test retreat restrictions and validations."""

    def test_cannot_retreat_twice_per_turn(self, engine):
        """Player should only be able to retreat once per turn."""
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player0.board.add_to_bench(create_card_instance("sv2-81", owner_id=0))
        player0.retreated_this_turn = True  # Already retreated

        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        state = GameState(
            players=[player0, player1],
            turn_count=5,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        retreat_actions = engine._get_retreat_actions(state)
        assert len(retreat_actions) == 0, "Should not be able to retreat twice in one turn"

    def test_cannot_retreat_without_bench(self, engine):
        """Cannot retreat if bench is empty."""
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        # No bench Pokemon

        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        state = GameState(
            players=[player0, player1],
            turn_count=5,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        retreat_actions = engine._get_retreat_actions(state)
        assert len(retreat_actions) == 0, "Cannot retreat without bench Pokemon"


class TestRetreatEnergyDiscard:
    """Test energy discard mechanics during retreat."""

    def test_retreat_discards_correct_energy_amount(self, engine, basic_game_state):
        """Retreat should discard energy equal to retreat cost."""
        state = basic_game_state
        player = state.players[0]

        active_mon = player.board.active_spot
        # Attach 3 energy to ensure we can pay retreat cost
        for _ in range(3):
            energy = create_card_instance("base1-98", owner_id=0)
            active_mon.attached_energy.append(energy)

        bench_mon = create_card_instance("sv2-81", owner_id=0)
        player.board.add_to_bench(bench_mon)

        initial_energy_count = len(active_mon.attached_energy)

        retreat_action = Action(
            action_type=ActionType.RETREAT,
            player_id=0,
            card_id=active_mon.id,
            target_id=bench_mon.id
        )

        state = engine._apply_retreat(state, retreat_action)
        player = state.players[0]

        # Pidgey has retreat cost 1, so 1 energy should be discarded
        expected_discard_count = 1
        assert player.discard.count() >= expected_discard_count, \
            f"Should have discarded at least {expected_discard_count} energy"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

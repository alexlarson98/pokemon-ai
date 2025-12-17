"""
Pytest suite for Hoothoot's Insomnia ability.

Tests the guard functionality that prevents Hoothoot (sv8pt5-77) from being Asleep.
This validates the 4 Pillars Architecture "guards" pillar implementation.
"""

import pytest
import sys
sys.path.insert(0, 'src')

from models import GameState, PlayerState, GamePhase, StatusCondition
from engine import PokemonEngine
from cards.factory import create_card_instance
from cards.logic_registry import get_card_guard
from actions import apply_status_condition


@pytest.fixture
def engine():
    """Create PokemonEngine instance."""
    return PokemonEngine()


@pytest.fixture
def game_state_with_hoothoot():
    """Create a game state with Hoothoot (sv8pt5-77) as player 0's active."""
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Hoothoot v3 (sv8pt5-77) with Insomnia ability
    player0.board.active_spot = create_card_instance("sv8pt5-77", owner_id=0)
    player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)  # Pidgey

    return GameState(
        players=[player0, player1],
        turn_count=2,
        active_player_index=0,
        current_phase=GamePhase.MAIN,
        starting_player_id=0
    )


@pytest.fixture
def game_state_with_pidgey():
    """Create a game state with Pidgey (no Insomnia) as player 0's active."""
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Pidgey without Insomnia
    player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
    player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

    return GameState(
        players=[player0, player1],
        turn_count=2,
        active_player_index=0,
        current_phase=GamePhase.MAIN,
        starting_player_id=0
    )


class TestInsomniaGuardRegistration:
    """Test that the Insomnia guard is properly registered."""

    def test_hoothoot_has_status_condition_guard(self):
        """Hoothoot sv8pt5-77 should have a status_condition guard registered."""
        guard = get_card_guard("sv8pt5-77", "status_condition")
        assert guard is not None, "Hoothoot should have a status_condition guard"

    def test_pidgey_has_no_status_condition_guard(self):
        """Pidgey sv3pt5-16 should not have a status_condition guard."""
        guard = get_card_guard("sv3pt5-16", "status_condition")
        assert guard is None, "Pidgey should not have a status_condition guard"


class TestInsomniaBlocksAsleep:
    """Test that Insomnia blocks the Asleep status condition."""

    def test_guard_blocks_asleep_condition(self):
        """The Insomnia guard should return True for Asleep condition."""
        guard = get_card_guard("sv8pt5-77", "status_condition")
        assert guard is not None

        # Guard should block Asleep
        result = guard(None, None, StatusCondition.ASLEEP)
        assert result is True, "Insomnia should block Asleep condition"

    def test_guard_allows_poisoned_condition(self):
        """The Insomnia guard should return False for Poisoned condition."""
        guard = get_card_guard("sv8pt5-77", "status_condition")
        assert guard is not None

        result = guard(None, None, StatusCondition.POISONED)
        assert result is False, "Insomnia should not block Poisoned"

    def test_guard_allows_burned_condition(self):
        """The Insomnia guard should return False for Burned condition."""
        guard = get_card_guard("sv8pt5-77", "status_condition")
        assert guard is not None

        result = guard(None, None, StatusCondition.BURNED)
        assert result is False, "Insomnia should not block Burned"

    def test_guard_allows_paralyzed_condition(self):
        """The Insomnia guard should return False for Paralyzed condition."""
        guard = get_card_guard("sv8pt5-77", "status_condition")
        assert guard is not None

        result = guard(None, None, StatusCondition.PARALYZED)
        assert result is False, "Insomnia should not block Paralyzed"

    def test_guard_allows_confused_condition(self):
        """The Insomnia guard should return False for Confused condition."""
        guard = get_card_guard("sv8pt5-77", "status_condition")
        assert guard is not None

        result = guard(None, None, StatusCondition.CONFUSED)
        assert result is False, "Insomnia should not block Confused"


class TestApplyStatusConditionWithInsomnia:
    """Test apply_status_condition integration with Insomnia guard."""

    def test_hoothoot_cannot_be_made_asleep(self, game_state_with_hoothoot):
        """Applying Asleep to Hoothoot should have no effect due to Insomnia."""
        state = game_state_with_hoothoot
        hoothoot = state.players[0].board.active_spot

        # Verify no status conditions initially
        assert StatusCondition.ASLEEP not in hoothoot.status_conditions

        # Try to apply Asleep
        state = apply_status_condition(state, hoothoot, StatusCondition.ASLEEP)

        # Hoothoot should NOT be Asleep
        assert StatusCondition.ASLEEP not in hoothoot.status_conditions, \
            "Hoothoot with Insomnia should not become Asleep"

    def test_hoothoot_can_be_poisoned(self, game_state_with_hoothoot):
        """Applying Poisoned to Hoothoot should work (Insomnia doesn't block it)."""
        state = game_state_with_hoothoot
        hoothoot = state.players[0].board.active_spot

        # Apply Poisoned
        state = apply_status_condition(state, hoothoot, StatusCondition.POISONED)

        # Hoothoot should be Poisoned
        assert StatusCondition.POISONED in hoothoot.status_conditions, \
            "Hoothoot should be able to be Poisoned"

    def test_hoothoot_can_be_burned(self, game_state_with_hoothoot):
        """Applying Burned to Hoothoot should work (Insomnia doesn't block it)."""
        state = game_state_with_hoothoot
        hoothoot = state.players[0].board.active_spot

        # Apply Burned
        state = apply_status_condition(state, hoothoot, StatusCondition.BURNED)

        # Hoothoot should be Burned
        assert StatusCondition.BURNED in hoothoot.status_conditions, \
            "Hoothoot should be able to be Burned"

    def test_hoothoot_can_be_paralyzed(self, game_state_with_hoothoot):
        """Applying Paralyzed to Hoothoot should work (Insomnia doesn't block it)."""
        state = game_state_with_hoothoot
        hoothoot = state.players[0].board.active_spot

        # Apply Paralyzed
        state = apply_status_condition(state, hoothoot, StatusCondition.PARALYZED)

        # Hoothoot should be Paralyzed
        assert StatusCondition.PARALYZED in hoothoot.status_conditions, \
            "Hoothoot should be able to be Paralyzed"

    def test_hoothoot_can_be_confused(self, game_state_with_hoothoot):
        """Applying Confused to Hoothoot should work (Insomnia doesn't block it)."""
        state = game_state_with_hoothoot
        hoothoot = state.players[0].board.active_spot

        # Apply Confused
        state = apply_status_condition(state, hoothoot, StatusCondition.CONFUSED)

        # Hoothoot should be Confused
        assert StatusCondition.CONFUSED in hoothoot.status_conditions, \
            "Hoothoot should be able to be Confused"

    def test_pidgey_can_be_made_asleep(self, game_state_with_pidgey):
        """Applying Asleep to Pidgey (no Insomnia) should work normally."""
        state = game_state_with_pidgey
        pidgey = state.players[0].board.active_spot

        # Apply Asleep
        state = apply_status_condition(state, pidgey, StatusCondition.ASLEEP)

        # Pidgey should be Asleep
        assert StatusCondition.ASLEEP in pidgey.status_conditions, \
            "Pidgey without Insomnia should be able to be Asleep"


class TestInsomniaWithMultipleConditions:
    """Test Insomnia behavior when multiple conditions are applied."""

    def test_hoothoot_can_have_poison_and_burn(self, game_state_with_hoothoot):
        """Hoothoot can have both Poisoned and Burned (both allowed by Insomnia)."""
        state = game_state_with_hoothoot
        hoothoot = state.players[0].board.active_spot

        # Apply both conditions
        state = apply_status_condition(state, hoothoot, StatusCondition.POISONED)
        state = apply_status_condition(state, hoothoot, StatusCondition.BURNED)

        # Both should be present
        assert StatusCondition.POISONED in hoothoot.status_conditions
        assert StatusCondition.BURNED in hoothoot.status_conditions

    def test_hoothoot_asleep_blocked_but_poisoned_stays(self, game_state_with_hoothoot):
        """If Hoothoot is Poisoned and someone tries to put it to Sleep, it stays Poisoned but not Asleep."""
        state = game_state_with_hoothoot
        hoothoot = state.players[0].board.active_spot

        # Apply Poisoned first
        state = apply_status_condition(state, hoothoot, StatusCondition.POISONED)
        assert StatusCondition.POISONED in hoothoot.status_conditions

        # Try to apply Asleep (should be blocked)
        state = apply_status_condition(state, hoothoot, StatusCondition.ASLEEP)

        # Should still be Poisoned, but NOT Asleep
        assert StatusCondition.POISONED in hoothoot.status_conditions, \
            "Hoothoot should still be Poisoned"
        assert StatusCondition.ASLEEP not in hoothoot.status_conditions, \
            "Hoothoot should not be Asleep due to Insomnia"


class TestHoothootTackleAttack:
    """Test Hoothoot's Tackle attack functionality."""

    def test_hoothoot_tackle_is_registered(self):
        """Hoothoot sv8pt5-77 should have Tackle attack registered."""
        from cards.logic_registry import get_card_logic, MASTER_LOGIC_REGISTRY

        card_data = MASTER_LOGIC_REGISTRY.get("sv8pt5-77")
        assert card_data is not None, "Hoothoot should be in registry"
        assert "Tackle" in card_data, "Hoothoot should have Tackle attack"
        assert "generator" in card_data["Tackle"], "Tackle should have generator"
        assert "effect" in card_data["Tackle"], "Tackle should have effect"

    def test_hoothoot_tackle_generates_action(self, game_state_with_hoothoot):
        """Hoothoot's Tackle should generate an attack action."""
        from cards.sets.sv8pt5 import hoothoot_tackle_actions

        state = game_state_with_hoothoot
        hoothoot = state.players[0].board.active_spot
        player = state.players[0]

        actions = hoothoot_tackle_actions(state, hoothoot, player)

        assert len(actions) == 1, "Tackle should generate exactly 1 action"
        assert actions[0].attack_name == "Tackle"
        assert "20" in actions[0].display_label, "Tackle should show 20 damage"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

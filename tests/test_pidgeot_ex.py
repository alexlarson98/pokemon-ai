"""
Tests for Pidgeot ex - Quick Search ability and Blustery Wind attack.

Tests:
- Quick Search global once-per-turn restriction
- Quick Search deck search functionality
- Blustery Wind damage and optional stadium discard
- All card variants (sv3-164, sv3-217, sv3-225, sv4pt5-221)
"""

import pytest
import sys
sys.path.insert(0, 'src')

from models import GameState, PlayerState, Action, ActionType
from cards.factory import create_card_instance
from engine import PokemonEngine
from cards.logic_registry import MASTER_LOGIC_REGISTRY


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def engine():
    """Create a Pokemon engine instance."""
    return PokemonEngine()


def create_pidgeot_game_state(pidgeot_card_id: str = "sv3-164"):
    """Create a game state with Pidgeot ex in active spot."""
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Player 0: Pidgeot ex active
    pidgeot = create_card_instance(pidgeot_card_id, owner_id=0)
    player0.board.active_spot = pidgeot

    # Player 1: Basic Pokemon active
    opponent_active = create_card_instance("sv3pt5-16", owner_id=1)  # Pikachu 60HP
    player1.board.active_spot = opponent_active

    # Add cards to decks
    for _ in range(10):
        player0.deck.add_card(create_card_instance("base1-98", owner_id=0))
        player1.deck.add_card(create_card_instance("base1-98", owner_id=1))

    # Add prizes
    for _ in range(6):
        player0.prizes.add_card(create_card_instance("base1-98", owner_id=0))
        player1.prizes.add_card(create_card_instance("base1-98", owner_id=1))

    state = GameState(
        players=[player0, player1],
        active_player_index=0,
        turn_count=2
    )

    return state


# ============================================================================
# REGISTRATION TESTS
# ============================================================================

class TestPidgeotExRegistration:
    """Test that all Pidgeot ex variants are properly registered."""

    @pytest.mark.parametrize("card_id", ["sv3-164", "sv3-217", "sv3-225", "sv4pt5-221"])
    def test_pidgeot_ex_registered(self, card_id):
        """Verify Pidgeot ex is in the logic registry."""
        assert card_id in MASTER_LOGIC_REGISTRY, f"{card_id} not in MASTER_LOGIC_REGISTRY"
        assert "Quick Search" in MASTER_LOGIC_REGISTRY[card_id]
        assert "Blustery Wind" in MASTER_LOGIC_REGISTRY[card_id]

    @pytest.mark.parametrize("card_id", ["sv3-164", "sv3-217", "sv3-225", "sv4pt5-221"])
    def test_quick_search_is_activatable(self, card_id):
        """Quick Search should be an activatable ability."""
        entry = MASTER_LOGIC_REGISTRY[card_id]["Quick Search"]
        assert entry["category"] == "activatable"
        assert "generator" in entry
        assert "effect" in entry

    @pytest.mark.parametrize("card_id", ["sv3-164", "sv3-217", "sv3-225", "sv4pt5-221"])
    def test_blustery_wind_is_attack(self, card_id):
        """Blustery Wind should be an attack."""
        entry = MASTER_LOGIC_REGISTRY[card_id]["Blustery Wind"]
        assert entry["category"] == "attack"
        assert "generator" in entry
        assert "effect" in entry


# ============================================================================
# QUICK SEARCH TESTS
# ============================================================================

class TestQuickSearch:
    """Test Quick Search ability functionality."""

    def test_quick_search_generates_action(self):
        """Quick Search should generate an action when available."""
        from cards.sets.sv3 import pidgeot_ex_quick_search_actions

        state = create_pidgeot_game_state()
        pidgeot = state.players[0].board.active_spot
        player = state.players[0]

        actions = pidgeot_ex_quick_search_actions(state, pidgeot, player)

        assert len(actions) == 1
        assert actions[0].action_type == ActionType.USE_ABILITY
        assert actions[0].ability_name == "Quick Search"

    def test_quick_search_no_action_if_deck_empty(self):
        """Quick Search should not generate action if deck is empty."""
        from cards.sets.sv3 import pidgeot_ex_quick_search_actions

        state = create_pidgeot_game_state()
        pidgeot = state.players[0].board.active_spot
        player = state.players[0]

        # Empty the deck
        player.deck.cards.clear()

        actions = pidgeot_ex_quick_search_actions(state, pidgeot, player)

        assert len(actions) == 0

    def test_quick_search_global_once_per_turn(self):
        """Quick Search can only be used once per turn globally (across all Pidgeot ex)."""
        from cards.sets.sv3 import pidgeot_ex_quick_search_actions, pidgeot_ex_quick_search_effect

        state = create_pidgeot_game_state()
        pidgeot = state.players[0].board.active_spot
        player = state.players[0]

        # Add a second Pidgeot ex to bench
        pidgeot2 = create_card_instance("sv3-217", owner_id=0)
        player.board.add_to_bench(pidgeot2)

        # First Pidgeot should have action available
        actions1 = pidgeot_ex_quick_search_actions(state, pidgeot, player)
        assert len(actions1) == 1

        # Use the ability
        action = actions1[0]
        state = pidgeot_ex_quick_search_effect(state, pidgeot, action)

        # Both Pidgeots should now have no Quick Search action (global restriction)
        actions1_after = pidgeot_ex_quick_search_actions(state, pidgeot, player)
        actions2_after = pidgeot_ex_quick_search_actions(state, pidgeot2, player)

        assert len(actions1_after) == 0, "First Pidgeot should not have Quick Search after use"
        assert len(actions2_after) == 0, "Second Pidgeot should not have Quick Search (global limit)"

    def test_quick_search_pushes_search_step(self):
        """Quick Search should push a SearchDeckStep."""
        from cards.sets.sv3 import pidgeot_ex_quick_search_effect
        from models import StepType

        state = create_pidgeot_game_state()
        pidgeot = state.players[0].board.active_spot

        action = Action(
            action_type=ActionType.USE_ABILITY,
            player_id=0,
            card_id=pidgeot.id,
            ability_name="Quick Search"
        )

        initial_stack_size = len(state.resolution_stack)
        state = pidgeot_ex_quick_search_effect(state, pidgeot, action)

        assert len(state.resolution_stack) == initial_stack_size + 1
        step = state.resolution_stack[-1]
        assert step.step_type == StepType.SEARCH_DECK
        assert step.count == 1  # Search for 1 card
        assert step.min_count == 0  # "may" - can choose 0
        assert step.shuffle_after == True


# ============================================================================
# BLUSTERY WIND TESTS
# ============================================================================

class TestBlusteryWind:
    """Test Blustery Wind attack functionality."""

    def test_blustery_wind_generates_single_action_no_stadium(self):
        """Blustery Wind should generate one action when no stadium is in play."""
        from cards.sets.sv3 import pidgeot_ex_blustery_wind_actions

        state = create_pidgeot_game_state()
        pidgeot = state.players[0].board.active_spot
        player = state.players[0]

        # No stadium
        state.stadium = None

        actions = pidgeot_ex_blustery_wind_actions(state, pidgeot, player)

        assert len(actions) == 1
        assert actions[0].attack_name == "Blustery Wind"
        assert actions[0].parameters.get('discard_stadium') == False

    def test_blustery_wind_generates_two_actions_with_stadium(self):
        """Blustery Wind should generate two actions when a stadium is in play."""
        from cards.sets.sv3 import pidgeot_ex_blustery_wind_actions

        state = create_pidgeot_game_state()
        pidgeot = state.players[0].board.active_spot
        player = state.players[0]

        # Add a stadium
        stadium = create_card_instance("sv5-156", owner_id=1)  # Any stadium
        state.stadium = stadium

        actions = pidgeot_ex_blustery_wind_actions(state, pidgeot, player)

        assert len(actions) == 2

        # One action without discard
        no_discard_action = [a for a in actions if not a.parameters.get('discard_stadium')]
        assert len(no_discard_action) == 1

        # One action with discard
        discard_action = [a for a in actions if a.parameters.get('discard_stadium')]
        assert len(discard_action) == 1

    def test_blustery_wind_deals_120_damage(self):
        """Blustery Wind should deal 120 damage."""
        from cards.sets.sv3 import pidgeot_ex_blustery_wind_effect

        state = create_pidgeot_game_state()
        pidgeot = state.players[0].board.active_spot
        opponent_active = state.players[1].board.active_spot

        initial_damage = opponent_active.damage_counters

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=pidgeot.id,
            attack_name="Blustery Wind",
            parameters={'discard_stadium': False}
        )

        state = pidgeot_ex_blustery_wind_effect(state, pidgeot, action)

        # 120 damage = 12 damage counters
        assert opponent_active.damage_counters == initial_damage + 12

    def test_blustery_wind_discards_stadium_when_requested(self):
        """Blustery Wind should discard the stadium when discard_stadium is True."""
        from cards.sets.sv3 import pidgeot_ex_blustery_wind_effect

        state = create_pidgeot_game_state()
        pidgeot = state.players[0].board.active_spot

        # Add a stadium owned by opponent
        stadium = create_card_instance("sv5-156", owner_id=1)
        state.stadium = stadium

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=pidgeot.id,
            attack_name="Blustery Wind",
            parameters={'discard_stadium': True}
        )

        state = pidgeot_ex_blustery_wind_effect(state, pidgeot, action)

        # Stadium should be removed and in opponent's discard
        assert state.stadium is None
        assert stadium in state.players[1].discard.cards

    def test_blustery_wind_keeps_stadium_when_not_requested(self):
        """Blustery Wind should keep the stadium when discard_stadium is False."""
        from cards.sets.sv3 import pidgeot_ex_blustery_wind_effect

        state = create_pidgeot_game_state()
        pidgeot = state.players[0].board.active_spot

        # Add a stadium
        stadium = create_card_instance("sv5-156", owner_id=1)
        state.stadium = stadium

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=pidgeot.id,
            attack_name="Blustery Wind",
            parameters={'discard_stadium': False}
        )

        state = pidgeot_ex_blustery_wind_effect(state, pidgeot, action)

        # Stadium should still be in play
        assert state.stadium is stadium


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestPidgeotExIntegration:
    """Integration tests for Pidgeot ex through the engine."""

    @pytest.mark.skip(reason="Pidgeot ex cards not in standard_cards.json - integration test")
    @pytest.mark.parametrize("card_id", ["sv3-164", "sv3-217", "sv3-225", "sv4pt5-221"])
    def test_quick_search_available_through_engine(self, engine, card_id):
        """Quick Search should be available as an action through engine.get_legal_actions()."""
        state = create_pidgeot_game_state(card_id)

        actions = engine.get_legal_actions(state)

        quick_search_actions = [a for a in actions if a.ability_name == "Quick Search"]
        assert len(quick_search_actions) == 1

    @pytest.mark.skip(reason="Pidgeot ex cards not in standard_cards.json - integration test")
    @pytest.mark.parametrize("card_id", ["sv3-164", "sv3-217", "sv3-225", "sv4pt5-221"])
    def test_blustery_wind_available_through_engine(self, engine, card_id):
        """Blustery Wind should be available as an attack through engine.get_legal_actions()."""
        state = create_pidgeot_game_state(card_id)
        pidgeot = state.players[0].board.active_spot

        # Add energy for attack cost [CC]
        energy1 = create_card_instance("base1-98", owner_id=0)
        energy2 = create_card_instance("base1-98", owner_id=0)
        pidgeot.attached_energy = [energy1, energy2]

        actions = engine.get_legal_actions(state)

        blustery_wind_actions = [a for a in actions if a.attack_name == "Blustery Wind"]
        assert len(blustery_wind_actions) >= 1

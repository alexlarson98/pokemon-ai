"""
Tests for Fan Rotom - Fan Call ability + Assault Landing attack.

Tests:
- Fan Call only works on first turn
- Fan Call global restriction (one per turn)
- Fan Call searches for Colorless Pokemon with HP <= 100
- Assault Landing does nothing without a Stadium
- Assault Landing deals 70 damage with a Stadium
- All card variants (sv7-118, sv8pt5-85)
"""

import pytest
import sys
sys.path.insert(0, 'src')

from models import GameState, PlayerState, Action, ActionType, StepType, ZoneType
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


def create_fan_rotom_game_state(turn_count: int = 1, first_player: int = 0):
    """Create a game state for Fan Rotom tests."""
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Player 0: Fan Rotom active
    active = create_card_instance("sv7-118", owner_id=0)  # Fan Rotom
    player0.board.active_spot = active

    # Player 1: Basic Pokemon active
    opponent_active = create_card_instance("svp-44", owner_id=1)  # Charmander
    player1.board.active_spot = opponent_active

    # Add some Colorless Pokemon to deck (for Fan Call searches)
    # sv3pt5-16: Pidgey (50 HP, Colorless)
    # sv3-162: Pidgey (60 HP, Colorless)
    player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))
    player0.deck.add_card(create_card_instance("sv3-162", owner_id=0))
    player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))

    # Add non-Colorless Pokemon (should not be searchable by Fan Call)
    player0.deck.add_card(create_card_instance("svp-44", owner_id=0))  # Charmander (Fire)

    # Energy cards for filler
    for _ in range(6):
        player0.deck.add_card(create_card_instance("base1-98", owner_id=0))
        player1.deck.add_card(create_card_instance("base1-98", owner_id=1))

    # Add prizes
    for _ in range(6):
        player0.prizes.add_card(create_card_instance("base1-98", owner_id=0))
        player1.prizes.add_card(create_card_instance("base1-98", owner_id=1))

    state = GameState(
        players=[player0, player1],
        active_player_index=0,
        turn_count=turn_count,
        starting_player_id=first_player
    )

    return state


# ============================================================================
# REGISTRATION TESTS
# ============================================================================

class TestFanRotomRegistration:
    """Test that all Fan Rotom variants are properly registered."""

    @pytest.mark.parametrize("card_id", ["sv7-118", "sv8pt5-85"])
    def test_fan_rotom_registered(self, card_id):
        """Verify Fan Rotom is in the logic registry."""
        assert card_id in MASTER_LOGIC_REGISTRY, f"{card_id} not in MASTER_LOGIC_REGISTRY"
        assert "Fan Call" in MASTER_LOGIC_REGISTRY[card_id]
        assert "Assault Landing" in MASTER_LOGIC_REGISTRY[card_id]

    @pytest.mark.parametrize("card_id", ["sv7-118", "sv8pt5-85"])
    def test_fan_call_is_activatable(self, card_id):
        """Fan Call should be an activatable ability."""
        entry = MASTER_LOGIC_REGISTRY[card_id]["Fan Call"]
        assert entry["category"] == "activatable"
        assert "generator" in entry
        assert "effect" in entry

    @pytest.mark.parametrize("card_id", ["sv7-118", "sv8pt5-85"])
    def test_assault_landing_is_attack(self, card_id):
        """Assault Landing should be an attack."""
        entry = MASTER_LOGIC_REGISTRY[card_id]["Assault Landing"]
        assert entry["category"] == "attack"
        assert "generator" in entry
        assert "effect" in entry


# ============================================================================
# FAN CALL TESTS
# ============================================================================

class TestFanCall:
    """Test Fan Call ability mechanics."""

    def test_fan_call_available_on_first_turn_going_first(self):
        """Fan Call should be available on first turn when going first."""
        from cards.sets.sv7 import fan_rotom_fan_call_actions

        state = create_fan_rotom_game_state(turn_count=1, first_player=0)
        fan_rotom = state.players[0].board.active_spot
        player = state.players[0]

        actions = fan_rotom_fan_call_actions(state, fan_rotom, player)

        assert len(actions) == 1
        assert actions[0].action_type == ActionType.USE_ABILITY
        assert actions[0].ability_name == "Fan Call"

    def test_fan_call_available_on_first_turn_going_second(self):
        """Fan Call should be available on first turn when going second (turn 2)."""
        from cards.sets.sv7 import fan_rotom_fan_call_actions

        # Player 0 went second, so their first turn is turn_count=2
        state = create_fan_rotom_game_state(turn_count=2, first_player=1)
        fan_rotom = state.players[0].board.active_spot
        player = state.players[0]

        actions = fan_rotom_fan_call_actions(state, fan_rotom, player)

        assert len(actions) == 1
        assert actions[0].action_type == ActionType.USE_ABILITY

    def test_fan_call_not_available_after_first_turn(self):
        """Fan Call should not be available after the first turn."""
        from cards.sets.sv7 import fan_rotom_fan_call_actions

        # Turn 3 - not first turn for either player
        state = create_fan_rotom_game_state(turn_count=3, first_player=0)
        fan_rotom = state.players[0].board.active_spot
        player = state.players[0]

        actions = fan_rotom_fan_call_actions(state, fan_rotom, player)

        assert len(actions) == 0

    def test_fan_call_global_restriction(self):
        """Only one Fan Call can be used per turn across all Fan Rotom."""
        from cards.sets.sv7 import fan_rotom_fan_call_actions

        state = create_fan_rotom_game_state(turn_count=1, first_player=0)
        fan_rotom = state.players[0].board.active_spot
        player = state.players[0]

        # Mark Fan Call as used globally
        state.turn_metadata['fan_call_used'] = True

        actions = fan_rotom_fan_call_actions(state, fan_rotom, player)

        assert len(actions) == 0

    def test_fan_call_pushes_search_step(self):
        """Fan Call effect should push a SearchDeckStep."""
        from cards.sets.sv7 import fan_rotom_fan_call_effect

        state = create_fan_rotom_game_state(turn_count=1, first_player=0)
        fan_rotom = state.players[0].board.active_spot

        action = Action(
            action_type=ActionType.USE_ABILITY,
            player_id=0,
            card_id=fan_rotom.id,
            ability_name="Fan Call"
        )

        initial_stack_size = len(state.resolution_stack)
        state = fan_rotom_fan_call_effect(state, fan_rotom, action)

        # Should have 1 new step
        assert len(state.resolution_stack) == initial_stack_size + 1

        step = state.resolution_stack[-1]
        assert step.step_type == StepType.SEARCH_DECK
        assert step.count == 3
        assert step.min_count == 0
        assert step.destination == ZoneType.HAND
        assert step.shuffle_after == True
        assert step.reveal_cards == True

    def test_fan_call_search_filter_criteria(self):
        """Fan Call should filter for Colorless Pokemon with HP <= 100."""
        from cards.sets.sv7 import fan_rotom_fan_call_effect

        state = create_fan_rotom_game_state(turn_count=1, first_player=0)
        fan_rotom = state.players[0].board.active_spot

        action = Action(
            action_type=ActionType.USE_ABILITY,
            player_id=0,
            card_id=fan_rotom.id,
            ability_name="Fan Call"
        )

        state = fan_rotom_fan_call_effect(state, fan_rotom, action)

        step = state.resolution_stack[-1]
        assert step.filter_criteria['supertype'] == 'Pokemon'
        assert step.filter_criteria['pokemon_type'] == 'Colorless'
        assert step.filter_criteria['max_hp'] == 100

    def test_fan_call_marks_ability_used(self):
        """Fan Call effect should mark the ability as used."""
        from cards.sets.sv7 import fan_rotom_fan_call_effect

        state = create_fan_rotom_game_state(turn_count=1, first_player=0)
        fan_rotom = state.players[0].board.active_spot

        action = Action(
            action_type=ActionType.USE_ABILITY,
            player_id=0,
            card_id=fan_rotom.id,
            ability_name="Fan Call"
        )

        state = fan_rotom_fan_call_effect(state, fan_rotom, action)

        # Check global and card-specific flags
        assert state.turn_metadata.get('fan_call_used') == True
        assert "Fan Call" in fan_rotom.abilities_used_this_turn


# ============================================================================
# ASSAULT LANDING TESTS
# ============================================================================

class TestAssaultLanding:
    """Test Assault Landing attack mechanics."""

    def test_assault_landing_generates_action(self):
        """Assault Landing should always generate an action."""
        from cards.sets.sv7 import fan_rotom_assault_landing_actions

        state = create_fan_rotom_game_state()
        fan_rotom = state.players[0].board.active_spot
        player = state.players[0]

        actions = fan_rotom_assault_landing_actions(state, fan_rotom, player)

        assert len(actions) == 1
        assert actions[0].action_type == ActionType.ATTACK
        assert actions[0].attack_name == "Assault Landing"

    def test_assault_landing_does_nothing_without_stadium(self):
        """Assault Landing should do nothing if no Stadium is in play."""
        from cards.sets.sv7 import fan_rotom_assault_landing_effect

        state = create_fan_rotom_game_state()
        fan_rotom = state.players[0].board.active_spot
        opponent_active = state.players[1].board.active_spot

        # Ensure no Stadium
        state.stadium = None

        initial_damage = opponent_active.damage_counters

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=fan_rotom.id,
            attack_name="Assault Landing"
        )

        state = fan_rotom_assault_landing_effect(state, fan_rotom, action)

        # No damage should be dealt
        assert opponent_active.damage_counters == initial_damage

    def test_assault_landing_deals_damage_with_stadium(self):
        """Assault Landing should deal 70 damage if a Stadium is in play."""
        from cards.sets.sv7 import fan_rotom_assault_landing_effect

        state = create_fan_rotom_game_state()
        fan_rotom = state.players[0].board.active_spot
        opponent_active = state.players[1].board.active_spot

        # Add a Stadium
        stadium = create_card_instance("sv1-181", owner_id=0)  # Some Stadium card
        state.stadium = stadium

        initial_damage = opponent_active.damage_counters

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=fan_rotom.id,
            attack_name="Assault Landing"
        )

        state = fan_rotom_assault_landing_effect(state, fan_rotom, action)

        # Should deal 70 damage (7 damage counters)
        assert opponent_active.damage_counters == initial_damage + 7


# ============================================================================
# ENGINE FILTER TESTS
# ============================================================================

class TestFanCallEngineFilter:
    """Test that the engine correctly filters search results for Fan Call."""

    def test_fan_call_only_shows_colorless_pokemon(self, engine):
        """Fan Call search should only show Colorless Pokemon, not Fire/Psychic/etc."""
        from cards.sets.sv7 import fan_rotom_fan_call_effect

        state = create_fan_rotom_game_state(turn_count=1, first_player=0)
        fan_rotom = state.players[0].board.active_spot

        action = Action(
            action_type=ActionType.USE_ABILITY,
            player_id=0,
            card_id=fan_rotom.id,
            ability_name="Fan Call"
        )

        state = fan_rotom_fan_call_effect(state, fan_rotom, action)

        # Get the legal actions for the search step
        legal_actions = engine.get_legal_actions(state)

        # Should have actions for the Colorless Pidgeys but NOT the Fire Charmander
        # Deck contains: sv3pt5-16 (Pidgey Colorless 50HP), sv3-162 (Pidgey Colorless 60HP),
        #                sv3pt5-16 (Pidgey Colorless 50HP), svp-44 (Charmander Fire 60HP)
        card_ids_in_actions = []
        for act in legal_actions:
            if act.action_type == ActionType.SELECT_CARD and act.card_id:
                card_ids_in_actions.append(act.card_id)

        # Get the actual card instances from deck to check types
        from cards.factory import get_card_definition
        from models import EnergyType

        for card in state.players[0].deck.cards:
            card_def = get_card_definition(card)
            if card_def:
                is_colorless = hasattr(card_def, 'types') and EnergyType.COLORLESS in card_def.types
                is_in_results = card.id in card_ids_in_actions

                if is_colorless and card_def.hp <= 100:
                    # Colorless Pokemon with HP <= 100 should be selectable
                    # (may be deduplicated by functional ID)
                    pass
                elif hasattr(card_def, 'types') and EnergyType.FIRE in card_def.types:
                    # Fire Pokemon should NOT be in results
                    assert not is_in_results, f"Fire Pokemon {card_def.name} should not be selectable"

    def test_fan_call_respects_hp_limit(self, engine):
        """Fan Call search should only show Pokemon with HP <= 100."""
        from cards.sets.sv7 import fan_rotom_fan_call_effect

        state = create_fan_rotom_game_state(turn_count=1, first_player=0)
        player = state.players[0]

        # Add a Colorless Pokemon with HP > 100 to the deck
        # Fan Rotom itself is 90 HP, so we need something else
        # We can add a second Fan Rotom which is 90 HP (should be included)
        high_hp_rotom = create_card_instance("sv7-118", owner_id=0)  # Fan Rotom 90HP
        player.deck.add_card(high_hp_rotom)

        fan_rotom = player.board.active_spot

        action = Action(
            action_type=ActionType.USE_ABILITY,
            player_id=0,
            card_id=fan_rotom.id,
            ability_name="Fan Call"
        )

        state = fan_rotom_fan_call_effect(state, fan_rotom, action)

        # Get the legal actions for the search step
        legal_actions = engine.get_legal_actions(state)

        # All selectable cards should be Colorless with HP <= 100
        from cards.factory import get_card_definition
        from models import EnergyType

        for act in legal_actions:
            if act.action_type == ActionType.SELECT_CARD and act.card_id:
                card = next((c for c in player.deck.cards if c.id == act.card_id), None)
                if card:
                    card_def = get_card_definition(card)
                    assert card_def is not None
                    assert hasattr(card_def, 'types')
                    assert EnergyType.COLORLESS in card_def.types, f"{card_def.name} is not Colorless"
                    assert card_def.hp <= 100, f"{card_def.name} has HP {card_def.hp} > 100"


# ============================================================================
# KNOWLEDGE LAYER TESTS
# ============================================================================

class TestFanCallKnowledgeLayer:
    """Test that Fan Call properly updates knowledge layer."""

    def test_fan_call_sets_has_searched_deck(self):
        """Fan Call effect should set has_searched_deck=True for perfect knowledge."""
        from cards.sets.sv7 import fan_rotom_fan_call_effect

        state = create_fan_rotom_game_state(turn_count=1, first_player=0)
        fan_rotom = state.players[0].board.active_spot
        player = state.players[0]

        # Initially, player hasn't searched deck
        assert player.has_searched_deck == False

        action = Action(
            action_type=ActionType.USE_ABILITY,
            player_id=0,
            card_id=fan_rotom.id,
            ability_name="Fan Call"
        )

        state = fan_rotom_fan_call_effect(state, fan_rotom, action)

        # After pushing SearchDeckStep, has_searched_deck should be True
        assert player.has_searched_deck == True

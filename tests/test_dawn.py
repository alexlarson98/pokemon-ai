"""
Tests for Dawn supporter card - Search for Basic + Stage 1 + Stage 2 Pokemon.

Tests:
- Dawn generates action (always playable)
- Dawn pushes 3 SearchDeckStep onto resolution stack
- Search steps have correct filter criteria
- Search steps execute in correct order (Basic -> Stage 1 -> Stage 2)
- Only final step shuffles the deck
- All card variants (me2-87, me2-118, me2-129)
"""

import pytest
import sys
sys.path.insert(0, 'src')

from models import GameState, PlayerState, Action, ActionType, StepType
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


def create_dawn_game_state():
    """Create a game state for Dawn tests."""
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Player 0: Basic Pokemon active
    active = create_card_instance("sv3pt5-16", owner_id=0)  # Pikachu
    player0.board.active_spot = active

    # Player 1: Basic Pokemon active
    opponent_active = create_card_instance("svp-44", owner_id=1)  # Charmander
    player1.board.active_spot = opponent_active

    # Add cards to decks - include Basic, Stage 1, Stage 2 Pokemon
    # Basic Pokemon
    player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))  # Pikachu
    player0.deck.add_card(create_card_instance("svp-44", owner_id=0))  # Charmander

    # Stage 1 Pokemon
    player0.deck.add_card(create_card_instance("sv3-27", owner_id=0))  # Charmeleon

    # Stage 2 Pokemon
    player0.deck.add_card(create_card_instance("sv3-6", owner_id=0))  # Charizard

    # Energy cards
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
        turn_count=2
    )

    return state


# ============================================================================
# REGISTRATION TESTS
# ============================================================================

class TestDawnRegistration:
    """Test that all Dawn variants are properly registered."""

    @pytest.mark.parametrize("card_id", ["me2-87", "me2-118", "me2-129"])
    def test_dawn_registered(self, card_id):
        """Verify Dawn is in the logic registry."""
        assert card_id in MASTER_LOGIC_REGISTRY, f"{card_id} not in MASTER_LOGIC_REGISTRY"
        assert "Play Dawn" in MASTER_LOGIC_REGISTRY[card_id]

    @pytest.mark.parametrize("card_id", ["me2-87", "me2-118", "me2-129"])
    def test_dawn_is_activatable(self, card_id):
        """Dawn should be an activatable supporter."""
        entry = MASTER_LOGIC_REGISTRY[card_id]["Play Dawn"]
        assert entry["category"] == "activatable"
        assert "generator" in entry
        assert "effect" in entry


# ============================================================================
# ACTION GENERATION TESTS
# ============================================================================

class TestDawnActions:
    """Test Dawn action generation."""

    def test_dawn_generates_action(self):
        """Dawn should always generate an action."""
        from cards.sets.me2 import dawn_actions

        state = create_dawn_game_state()
        dawn = create_card_instance("me2-87", owner_id=0)
        player = state.players[0]

        actions = dawn_actions(state, dawn, player)

        assert len(actions) == 1
        assert actions[0].action_type == ActionType.PLAY_SUPPORTER

    def test_dawn_generates_action_with_empty_deck(self):
        """Dawn should still generate action even with empty deck."""
        from cards.sets.me2 import dawn_actions

        state = create_dawn_game_state()
        dawn = create_card_instance("me2-87", owner_id=0)
        player = state.players[0]

        # Empty the deck
        player.deck.cards.clear()

        actions = dawn_actions(state, dawn, player)

        # Dawn is still playable (can fail to find cards)
        assert len(actions) == 1


# ============================================================================
# EFFECT TESTS
# ============================================================================

class TestDawnEffect:
    """Test Dawn effect execution."""

    def test_dawn_pushes_three_search_steps(self):
        """Dawn effect should push 3 SearchDeckStep onto the stack."""
        from cards.sets.me2 import dawn_effect

        state = create_dawn_game_state()
        dawn = create_card_instance("me2-87", owner_id=0)

        action = Action(
            action_type=ActionType.PLAY_SUPPORTER,
            player_id=0,
            card_id=dawn.id
        )

        initial_stack_size = len(state.resolution_stack)
        state = dawn_effect(state, dawn, action)

        # Should have 3 new steps
        assert len(state.resolution_stack) == initial_stack_size + 3

    def test_dawn_search_steps_order(self):
        """Dawn search steps should resolve in order: Basic -> Stage 1 -> Stage 2."""
        from cards.sets.me2 import dawn_effect

        state = create_dawn_game_state()
        dawn = create_card_instance("me2-87", owner_id=0)

        action = Action(
            action_type=ActionType.PLAY_SUPPORTER,
            player_id=0,
            card_id=dawn.id
        )

        state = dawn_effect(state, dawn, action)

        # Steps are pushed in reverse order (LIFO)
        # Stack order (from top/first to bottom/last): Basic, Stage 1, Stage 2
        step1 = state.resolution_stack[-1]  # First to resolve
        step2 = state.resolution_stack[-2]
        step3 = state.resolution_stack[-3]  # Last to resolve

        assert step1.step_type == StepType.SEARCH_DECK
        assert step1.filter_criteria['subtype'] == 'Basic'

        assert step2.step_type == StepType.SEARCH_DECK
        assert step2.filter_criteria['subtype'] == 'Stage 1'

        assert step3.step_type == StepType.SEARCH_DECK
        assert step3.filter_criteria['subtype'] == 'Stage 2'

    def test_dawn_only_final_step_shuffles(self):
        """Only the final search step (Stage 2) should shuffle the deck."""
        from cards.sets.me2 import dawn_effect

        state = create_dawn_game_state()
        dawn = create_card_instance("me2-87", owner_id=0)

        action = Action(
            action_type=ActionType.PLAY_SUPPORTER,
            player_id=0,
            card_id=dawn.id
        )

        state = dawn_effect(state, dawn, action)

        # Check shuffle_after flags
        step_basic = state.resolution_stack[-1]
        step_stage1 = state.resolution_stack[-2]
        step_stage2 = state.resolution_stack[-3]

        assert step_basic.shuffle_after == False, "Basic search should NOT shuffle"
        assert step_stage1.shuffle_after == False, "Stage 1 search should NOT shuffle"
        assert step_stage2.shuffle_after == True, "Stage 2 search SHOULD shuffle"

    def test_dawn_all_steps_reveal_cards(self):
        """All search steps should reveal the selected cards."""
        from cards.sets.me2 import dawn_effect

        state = create_dawn_game_state()
        dawn = create_card_instance("me2-87", owner_id=0)

        action = Action(
            action_type=ActionType.PLAY_SUPPORTER,
            player_id=0,
            card_id=dawn.id
        )

        state = dawn_effect(state, dawn, action)

        # All steps should have reveal_cards=True
        for i in range(3):
            step = state.resolution_stack[-(i + 1)]
            assert step.reveal_cards == True, f"Step {i+1} should reveal cards"

    def test_dawn_all_steps_destination_is_hand(self):
        """All search steps should put cards into hand."""
        from cards.sets.me2 import dawn_effect
        from models import ZoneType

        state = create_dawn_game_state()
        dawn = create_card_instance("me2-87", owner_id=0)

        action = Action(
            action_type=ActionType.PLAY_SUPPORTER,
            player_id=0,
            card_id=dawn.id
        )

        state = dawn_effect(state, dawn, action)

        # All steps should go to HAND
        for i in range(3):
            step = state.resolution_stack[-(i + 1)]
            assert step.destination == ZoneType.HAND, f"Step {i+1} should go to HAND"

    def test_dawn_search_can_fail(self):
        """Dawn searches should have min_count=0 (can fail to find)."""
        from cards.sets.me2 import dawn_effect

        state = create_dawn_game_state()
        dawn = create_card_instance("me2-87", owner_id=0)

        action = Action(
            action_type=ActionType.PLAY_SUPPORTER,
            player_id=0,
            card_id=dawn.id
        )

        state = dawn_effect(state, dawn, action)

        # All steps should have min_count=0
        for i in range(3):
            step = state.resolution_stack[-(i + 1)]
            assert step.min_count == 0, f"Step {i+1} should allow failing to find"
            assert step.count == 1, f"Step {i+1} should search for 1 card"


# ============================================================================
# KNOWLEDGE LAYER TESTS
# ============================================================================

class TestDawnKnowledgeLayer:
    """Test that Dawn properly updates knowledge layer."""

    def test_dawn_sets_has_searched_deck(self):
        """Dawn effect should set has_searched_deck=True for perfect knowledge."""
        from cards.library.trainers import dawn_effect

        state = create_dawn_game_state()
        dawn = create_card_instance("me2-87", owner_id=0)
        player = state.players[0]

        # Initially, player hasn't searched deck
        assert player.has_searched_deck == False

        action = Action(
            action_type=ActionType.PLAY_SUPPORTER,
            player_id=0,
            card_id=dawn.id
        )

        state = dawn_effect(state, dawn, action)

        # After pushing SearchDeckStep, has_searched_deck should be True
        assert player.has_searched_deck == True

    def test_search_deck_gives_perfect_knowledge(self):
        """After search, player should only see actual deck cards, not prized."""
        from cards.library.trainers import dawn_effect

        state = create_dawn_game_state()
        dawn = create_card_instance("me2-87", owner_id=0)
        player = state.players[0]

        action = Action(
            action_type=ActionType.PLAY_SUPPORTER,
            player_id=0,
            card_id=dawn.id
        )

        state = dawn_effect(state, dawn, action)

        # has_searched_deck should now be True
        # This means the engine will use actual deck contents for searches,
        # not the theoretical deck (which includes prized cards)
        assert player.has_searched_deck == True

"""
Comprehensive pytest suite for Resolution Stack mechanics.

Tests the new stack-based architecture that replaces atomic action permutations
with sequential state machine steps.

Tests:
- Stack push/pop operations
- SelectFromZoneStep state transitions
- SearchDeckStep state transitions
- Selection count limits
- CONFIRM_SELECTION behavior
- Multi-step sequences (e.g., Ultra Ball: discard + search)
- Nest Ball single-selection behavior
- Buddy-Buddy Poffin multi-selection behavior
"""

import pytest
import sys
sys.path.insert(0, 'src')

from models import (
    GameState, PlayerState, GamePhase, Action, ActionType,
    SelectFromZoneStep, SearchDeckStep, ZoneType, SelectionPurpose, StepType
)
from engine import PokemonEngine
from cards.factory import create_card_instance
from cards.library.trainers import (
    nest_ball_effect, nest_ball_actions,
    ultra_ball_effect, ultra_ball_actions,
    buddy_buddy_poffin_effect, buddy_buddy_poffin_actions,
    rare_candy_effect, rare_candy_actions,
)
from cards.registry import create_card


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def engine():
    """Create PokemonEngine instance."""
    return PokemonEngine()


@pytest.fixture
def basic_game_state():
    """Create basic game state for testing."""
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
    player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

    # Add Pokemon to deck
    player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))  # Pidgey (Basic)
    player0.deck.add_card(create_card_instance("sv4pt5-7", owner_id=0))   # Charmander (Basic)
    player0.deck.add_card(create_card_instance("sv4pt5-8", owner_id=0))   # Charmeleon (Stage 1)

    return GameState(
        players=[player0, player1],
        turn_count=1,
        active_player_index=0,
        current_phase=GamePhase.MAIN,
        starting_player_id=0
    )


# =============================================================================
# STACK BASIC OPERATIONS
# =============================================================================

class TestStackBasicOperations:
    """Test basic stack push/pop/peek operations."""

    def test_push_step_adds_to_stack(self, basic_game_state):
        """Pushing a step should add it to the resolution stack."""
        state = basic_game_state

        step = SearchDeckStep(
            source_card_id="test-card",
            source_card_name="Test Card",
            player_id=0,
            purpose=SelectionPurpose.SEARCH_TARGET,
            count=1,
            destination=ZoneType.BENCH
        )

        assert not state.has_pending_resolution()
        state.push_step(step)
        assert state.has_pending_resolution()
        assert len(state.resolution_stack) == 1

    def test_pop_step_removes_from_stack(self, basic_game_state):
        """Popping a step should remove it from the resolution stack."""
        state = basic_game_state

        step = SearchDeckStep(
            source_card_id="test-card",
            source_card_name="Test Card",
            player_id=0,
            purpose=SelectionPurpose.SEARCH_TARGET,
            count=1,
            destination=ZoneType.BENCH
        )

        state.push_step(step)
        popped = state.pop_step()

        assert popped == step
        assert not state.has_pending_resolution()

    def test_peek_step_returns_top_without_removing(self, basic_game_state):
        """Peeking should return top step without removing it."""
        state = basic_game_state

        step = SearchDeckStep(
            source_card_id="test-card",
            source_card_name="Test Card",
            player_id=0,
            purpose=SelectionPurpose.SEARCH_TARGET,
            count=1,
            destination=ZoneType.BENCH
        )

        state.push_step(step)
        peeked = state.get_current_step()

        assert peeked == step
        assert state.has_pending_resolution()

    def test_multiple_steps_are_lifo(self, basic_game_state):
        """Multiple steps should be processed LIFO (last in, first out)."""
        state = basic_game_state

        step1 = SelectFromZoneStep(
            source_card_id="card1",
            source_card_name="Card 1",
            player_id=0,
            purpose=SelectionPurpose.DISCARD_COST,
            zone=ZoneType.HAND,
            count=2
        )

        step2 = SearchDeckStep(
            source_card_id="card2",
            source_card_name="Card 2",
            player_id=0,
            purpose=SelectionPurpose.SEARCH_TARGET,
            count=1,
            destination=ZoneType.HAND
        )

        state.push_step(step1)
        state.push_step(step2)

        # Pop should return step2 first (LIFO)
        assert state.pop_step() == step2
        assert state.pop_step() == step1


# =============================================================================
# NEST BALL STACK MECHANICS
# =============================================================================

class TestNestBallStackMechanics:
    """Test Nest Ball using stack architecture."""

    def test_nest_ball_generates_single_play_action(self, engine, basic_game_state):
        """Nest Ball stack should generate a single PLAY_ITEM action."""
        state = basic_game_state
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        nest_ball = create_card_instance("sv1-181", owner_id=0)
        player.hand.add_card(nest_ball)

        actions = nest_ball_actions(state, nest_ball, player)

        # Should generate exactly 1 action to play Nest Ball
        assert len(actions) == 1
        assert actions[0].action_type == ActionType.PLAY_ITEM

    def test_nest_ball_effect_pushes_search_step(self, engine, basic_game_state):
        """Nest Ball effect should push a SearchDeckStep onto the stack."""
        state = basic_game_state
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        nest_ball = create_card_instance("sv1-181", owner_id=0)
        player.hand.add_card(nest_ball)

        action = Action(
            action_type=ActionType.PLAY_ITEM,
            player_id=0,
            card_id=nest_ball.id
        )

        state = nest_ball_effect(state, nest_ball, action)

        # Should have pushed a search step
        assert state.has_pending_resolution()
        step = state.get_current_step()
        assert isinstance(step, SearchDeckStep)
        assert step.count == 1  # Nest Ball searches for exactly 1
        assert step.destination == ZoneType.BENCH

    def test_nest_ball_search_step_generates_select_card_actions(self, engine, basic_game_state):
        """SearchDeckStep should generate SELECT_CARD actions for valid Pokemon."""
        state = basic_game_state
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        nest_ball = create_card_instance("sv1-181", owner_id=0)
        player.hand.add_card(nest_ball)

        action = Action(
            action_type=ActionType.PLAY_ITEM,
            player_id=0,
            card_id=nest_ball.id
        )

        state = nest_ball_effect(state, nest_ball, action)

        # Get legal actions (should be SELECT_CARD actions)
        actions = engine.get_legal_actions(state)

        # Should have SELECT_CARD actions for Basic Pokemon + CONFIRM_SELECTION
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]

        # Pidgey and Charmander are Basic, Charmeleon is Stage 1
        assert len(select_actions) == 2, f"Expected 2 SELECT_CARD actions for Basic Pokemon, got {len(select_actions)}"
        assert len(confirm_actions) == 1, "Should have CONFIRM_SELECTION option"

    def test_nest_ball_selection_count_enforced(self, engine, basic_game_state):
        """Nest Ball should only allow selecting 1 card (count=1)."""
        state = basic_game_state
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        nest_ball = create_card_instance("sv1-181", owner_id=0)
        player.hand.add_card(nest_ball)

        # Play Nest Ball
        action = Action(
            action_type=ActionType.PLAY_ITEM,
            player_id=0,
            card_id=nest_ball.id
        )
        state = nest_ball_effect(state, nest_ball, action)

        # Select one card
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        assert len(select_actions) > 0

        # Execute selection
        state = engine.step(state, select_actions[0])

        # After selecting 1 card, should only have CONFIRM_SELECTION (no more SELECT_CARD)
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]

        assert len(select_actions) == 0, "Should not allow more selections after count reached"
        assert len(confirm_actions) == 1, "Should have CONFIRM_SELECTION option"


# =============================================================================
# ULTRA BALL STACK MECHANICS
# =============================================================================

class TestUltraBallStackMechanics:
    """Test Ultra Ball using stack architecture."""

    def test_ultra_ball_requires_discard_cards(self, engine, basic_game_state):
        """Ultra Ball needs 2 cards in hand to discard (excluding itself)."""
        state = basic_game_state
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        ultra_ball = create_card_instance("sv5-162", owner_id=0)
        player.hand.add_card(ultra_ball)

        # Only 1 other card - not enough to discard 2
        player.hand.add_card(create_card_instance("sv5-163", owner_id=0))

        actions = ultra_ball_actions(state, ultra_ball, player)

        # Should return empty (can't discard 2 cards)
        assert len(actions) == 0

    def test_ultra_ball_generates_single_action(self, engine, basic_game_state):
        """Ultra Ball with enough cards should generate single PLAY_ITEM action."""
        state = basic_game_state
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        ultra_ball = create_card_instance("sv5-162", owner_id=0)
        player.hand.add_card(ultra_ball)
        player.hand.add_card(create_card_instance("sv5-163", owner_id=0))
        player.hand.add_card(create_card_instance("sv5-191", owner_id=0))

        actions = ultra_ball_actions(state, ultra_ball, player)

        # Should generate exactly 1 action
        assert len(actions) == 1
        assert actions[0].action_type == ActionType.PLAY_ITEM

    def test_ultra_ball_effect_pushes_discard_step_first(self, engine, basic_game_state):
        """Ultra Ball effect should push discard step (to be resolved first via LIFO)."""
        state = basic_game_state
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        ultra_ball = create_card_instance("sv5-162", owner_id=0)
        player.hand.add_card(ultra_ball)
        player.hand.add_card(create_card_instance("sv5-163", owner_id=0))
        player.hand.add_card(create_card_instance("sv5-191", owner_id=0))

        action = Action(
            action_type=ActionType.PLAY_ITEM,
            player_id=0,
            card_id=ultra_ball.id
        )

        state = ultra_ball_effect(state, ultra_ball, action)

        # Should have steps on stack
        assert state.has_pending_resolution()

        # Top step should be discard (LIFO - pushed last, resolved first)
        step = state.get_current_step()
        assert isinstance(step, SelectFromZoneStep)
        assert step.purpose == SelectionPurpose.DISCARD_COST
        assert step.count == 2

    def test_ultra_ball_discard_count_enforced(self, engine, basic_game_state):
        """Ultra Ball should require exactly 2 discards before allowing confirm."""
        state = basic_game_state
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        ultra_ball = create_card_instance("sv5-162", owner_id=0)
        discard1 = create_card_instance("sv5-163", owner_id=0)
        discard2 = create_card_instance("sv5-191", owner_id=0)

        player.hand.add_card(ultra_ball)
        player.hand.add_card(discard1)
        player.hand.add_card(discard2)

        # Play Ultra Ball
        action = Action(
            action_type=ActionType.PLAY_ITEM,
            player_id=0,
            card_id=ultra_ball.id
        )
        state = ultra_ball_effect(state, ultra_ball, action)

        # Get initial actions
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]

        # Should have 2 cards to select, but no confirm yet (exact_count=True, min=2)
        assert len(select_actions) == 2
        assert len(confirm_actions) == 0, "Can't confirm until 2 cards selected"

        # Select first card
        state = engine.step(state, select_actions[0])

        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]

        # Still need one more
        assert len(select_actions) == 1
        assert len(confirm_actions) == 0

        # Select second card (auto-confirms since exact_count=True and count=2)
        state = engine.step(state, select_actions[0])

        # After auto-confirm, callback pushes SearchDeckStep
        # So now we should be in the search phase with SELECT_CARD actions for Pokemon
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]

        # Should have moved to search step - SELECT_CARD for Pokemon and CONFIRM to fail search
        assert len(select_actions) >= 1, "Should have search options after discard auto-confirms"
        assert len(confirm_actions) == 1, "Should have confirm option (to fail search)"

    def test_ultra_ball_excludes_itself_from_discard_options(self, engine, basic_game_state):
        """Ultra Ball being played should NOT appear as a discard option (single Ultra Ball case)."""
        state = basic_game_state
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        # Clear hand and set up exactly: Ultra Ball + 2 other cards (DIFFERENT cards)
        # Using different cards to properly test exclusion since identical cards
        # are deduplicated by functional ID
        player.hand.cards.clear()

        ultra_ball = create_card_instance("sv1-196", owner_id=0)  # Ultra Ball
        iono = create_card_instance("sv2-185", owner_id=0)         # Iono (Supporter)
        charmander = create_card_instance("svp-44", owner_id=0)    # Charmander (Pokemon)

        player.hand.add_card(ultra_ball)
        player.hand.add_card(iono)
        player.hand.add_card(charmander)

        # Get initial actions - should include PLAY_ITEM for Ultra Ball
        actions = engine.get_legal_actions(state)
        play_ultra_ball = [a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == ultra_ball.id]
        assert len(play_ultra_ball) == 1, "Should be able to play Ultra Ball"

        # Play Ultra Ball through engine.step (this removes Ultra Ball from hand first)
        state = engine.step(state, play_ultra_ball[0])

        # Now we should be in the discard selection phase
        assert state.has_pending_resolution()
        step = state.get_current_step()
        assert isinstance(step, SelectFromZoneStep)
        assert step.purpose == SelectionPurpose.DISCARD_COST

        # Get legal actions for discard selection
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Should have exactly 2 options (Iono and Charmander), NOT Ultra Ball
        assert len(select_actions) == 2, f"Should have 2 discard options, got {len(select_actions)}"

        # Verify Ultra Ball is NOT among the options
        select_card_ids = [a.card_id for a in select_actions]
        assert ultra_ball.id not in select_card_ids, "Ultra Ball should NOT be a discard option"
        assert iono.id in select_card_ids, "Iono should be a discard option"
        assert charmander.id in select_card_ids, "Charmander should be a discard option"

    def test_ultra_ball_with_two_ultra_balls_in_hand(self, engine, basic_game_state):
        """With 2 Ultra Balls, the one NOT being played CAN be discarded."""
        state = basic_game_state
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        # Clear hand and set up: 2 Ultra Balls + 1 other card
        player.hand.cards.clear()

        ultra_ball_1 = create_card_instance("sv1-196", owner_id=0)  # Ultra Ball 1 (will play)
        ultra_ball_2 = create_card_instance("sv1-196", owner_id=0)  # Ultra Ball 2 (can discard)
        iono = create_card_instance("sv2-185", owner_id=0)           # Iono

        player.hand.add_card(ultra_ball_1)
        player.hand.add_card(ultra_ball_2)
        player.hand.add_card(iono)

        # Play Ultra Ball 1
        actions = engine.get_legal_actions(state)
        play_ultra_ball = [a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == ultra_ball_1.id]
        assert len(play_ultra_ball) == 1

        state = engine.step(state, play_ultra_ball[0])

        # Get legal actions for discard selection
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Should have 2 options: Ultra Ball 2 and Iono
        # (Ultra Ball 1 was removed from hand when played)
        assert len(select_actions) == 2, f"Should have 2 discard options, got {len(select_actions)}"

        select_card_ids = [a.card_id for a in select_actions]
        assert ultra_ball_1.id not in select_card_ids, "Played Ultra Ball should NOT be a discard option"
        assert ultra_ball_2.id in select_card_ids, "Second Ultra Ball CAN be discarded"
        assert iono.id in select_card_ids, "Iono should be a discard option"


# =============================================================================
# BUDDY-BUDDY POFFIN STACK MECHANICS
# =============================================================================

class TestBuddyBuddyPoffinStackMechanics:
    """Test Buddy-Buddy Poffin using stack architecture."""

    def test_poffin_generates_single_action(self, engine, basic_game_state):
        """Buddy-Buddy Poffin should generate single PLAY_ITEM action."""
        state = basic_game_state
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        poffin = create_card_instance("sv5-144", owner_id=0)
        player.hand.add_card(poffin)

        actions = buddy_buddy_poffin_actions(state, poffin, player)

        # Should generate exactly 1 action
        assert len(actions) == 1
        assert actions[0].action_type == ActionType.PLAY_ITEM

    def test_poffin_allows_up_to_two_selections(self, engine, basic_game_state):
        """Buddy-Buddy Poffin should allow selecting up to 2 Basic Pokemon."""
        state = basic_game_state
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        poffin = create_card_instance("sv5-144", owner_id=0)
        player.hand.add_card(poffin)

        action = Action(
            action_type=ActionType.PLAY_ITEM,
            player_id=0,
            card_id=poffin.id
        )

        state = buddy_buddy_poffin_effect(state, poffin, action)

        # Should have a search step with count=2
        step = state.get_current_step()
        assert isinstance(step, SearchDeckStep)
        assert step.count == 2
        assert step.min_count == 0  # Can find nothing

    def test_poffin_can_confirm_with_one_selection(self, engine, basic_game_state):
        """Poffin allows confirming with 1 card (since it's 'up to 2')."""
        state = basic_game_state
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        poffin = create_card_instance("sv5-144", owner_id=0)
        player.hand.add_card(poffin)

        action = Action(
            action_type=ActionType.PLAY_ITEM,
            player_id=0,
            card_id=poffin.id
        )
        state = buddy_buddy_poffin_effect(state, poffin, action)

        # Select one card
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Find a valid HP <= 70 Pokemon (Pidgey=50, Charmander=70)
        if select_actions:
            state = engine.step(state, select_actions[0])

            # Should be able to confirm OR select another
            actions = engine.get_legal_actions(state)
            select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
            confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]

            # min_count=0 so can confirm with 1
            assert len(confirm_actions) >= 1, "Should allow confirming with 1 selection"

    def test_poffin_hp_filter_excludes_high_hp(self, engine, basic_game_state):
        """Poffin should only show Pokemon with HP <= 70."""
        state = basic_game_state
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        # Add a high-HP Pokemon to deck
        charizard_ex = create_card_instance("sv3pt5-6", owner_id=0)  # HP > 70
        player.deck.add_card(charizard_ex)

        poffin = create_card_instance("sv5-144", owner_id=0)
        player.hand.add_card(poffin)

        action = Action(
            action_type=ActionType.PLAY_ITEM,
            player_id=0,
            card_id=poffin.id
        )
        state = buddy_buddy_poffin_effect(state, poffin, action)

        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Should not include Charizard ex (high HP)
        for action in select_actions:
            # Actions should only target low HP Pokemon
            card_id = action.card_id
            # Check it's not the Charizard
            assert card_id != charizard_ex.id, "Should not allow selecting high HP Pokemon"


# =============================================================================
# CONFIRM_SELECTION BEHAVIOR
# =============================================================================

class TestConfirmSelectionBehavior:
    """Test CONFIRM_SELECTION action behavior."""

    def test_confirm_completes_step_and_pops_stack(self, engine, basic_game_state):
        """CONFIRM_SELECTION should complete the step and pop it from stack."""
        state = basic_game_state
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        nest_ball = create_card_instance("sv1-181", owner_id=0)
        player.hand.add_card(nest_ball)

        # Play Nest Ball
        action = Action(
            action_type=ActionType.PLAY_ITEM,
            player_id=0,
            card_id=nest_ball.id
        )
        state = nest_ball_effect(state, nest_ball, action)

        assert state.has_pending_resolution()

        # Find CONFIRM_SELECTION action (fail search)
        actions = engine.get_legal_actions(state)
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]

        assert len(confirm_actions) == 1

        # Execute confirm
        state = engine.step(state, confirm_actions[0])

        # Stack should be empty now
        assert not state.has_pending_resolution()

    def test_confirm_with_selection_moves_card(self, engine, basic_game_state):
        """CONFIRM_SELECTION should move selected cards to destination."""
        state = basic_game_state
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        nest_ball = create_card_instance("sv1-181", owner_id=0)
        player.hand.add_card(nest_ball)

        initial_deck_count = player.deck.count()
        initial_bench_count = player.board.get_bench_count()

        # Play Nest Ball
        action = Action(
            action_type=ActionType.PLAY_ITEM,
            player_id=0,
            card_id=nest_ball.id
        )
        state = nest_ball_effect(state, nest_ball, action)

        # Select a card
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        state = engine.step(state, select_actions[0])

        # Confirm
        actions = engine.get_legal_actions(state)
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]
        state = engine.step(state, confirm_actions[0])

        player = state.players[0]

        # Card should have moved from deck to bench
        assert player.deck.count() == initial_deck_count - 1
        assert player.board.get_bench_count() == initial_bench_count + 1


# =============================================================================
# BRANCHING FACTOR REDUCTION
# =============================================================================

class TestBranchingFactorReduction:
    """Test that stack architecture reduces branching factor."""

    def test_nest_ball_single_initial_action(self, engine, basic_game_state):
        """Nest Ball should generate 1 initial action (not N actions for N Pokemon)."""
        state = basic_game_state
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        # Add more Pokemon to deck
        for i in range(5):
            player.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))

        nest_ball = create_card_instance("sv1-181", owner_id=0)
        player.hand.add_card(nest_ball)

        actions = nest_ball_actions(state, nest_ball, player)

        # Should be 1 action regardless of deck size
        assert len(actions) == 1

    def test_ultra_ball_single_initial_action(self, engine, basic_game_state):
        """Ultra Ball should generate 1 initial action (not C(H,2) * N actions)."""
        state = basic_game_state
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        # Add many cards to hand
        for i in range(6):
            player.hand.add_card(create_card_instance("sv5-163", owner_id=0))

        # Add many Pokemon to deck
        for i in range(10):
            player.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))

        ultra_ball = create_card_instance("sv5-162", owner_id=0)
        player.hand.add_card(ultra_ball)

        actions = ultra_ball_actions(state, ultra_ball, player)

        # Should be 1 action regardless of hand/deck size
        # Old atomic approach: C(6,2) * 10 = 150 actions
        # New stack approach: 1 action
        assert len(actions) == 1

    def test_poffin_single_initial_action(self, engine, basic_game_state):
        """Buddy-Buddy Poffin should generate 1 initial action."""
        state = basic_game_state
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        # Add many low-HP Pokemon
        for i in range(8):
            player.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))

        poffin = create_card_instance("sv5-144", owner_id=0)
        player.hand.add_card(poffin)

        actions = buddy_buddy_poffin_actions(state, poffin, player)

        # Should be 1 action regardless of deck composition
        # Old atomic approach: C(8,2) = 28 pairs + 8 singles + 1 fail = 37 actions
        # New stack approach: 1 action
        assert len(actions) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

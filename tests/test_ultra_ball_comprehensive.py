"""
Comprehensive pytest suite for Ultra Ball stack mechanics.

This tests Ultra Ball's complex discard-then-search flow with all edge cases
that matter for gameplay correctness.

Test Categories:
1. Hand Size Permutations
   - Exactly 2 cards to discard (minimum playable)
   - 3+ cards to discard (choices available)
   - 0-1 cards (Ultra Ball unplayable)
   - Ultra Ball is the only card (unplayable - need 2 others)

2. Discard Selection
   - Can discard any card types (Pokemon, Trainer, Energy)
   - Cannot discard the Ultra Ball being played
   - Can discard another Ultra Ball if multiple in hand
   - Selection tracking across both discard selections

3. Deck Search Variations
   - Pokemon in deck (can find targets)
   - No Pokemon in deck (must confirm with nothing)
   - Multiple Pokemon types (all are valid targets)
   - Empty deck (fail search gracefully)

4. Knowledge Layer Interactions
   - With deck knowledge initialized
   - Without deck knowledge (should still work)
   - has_searched_deck flag set after search

5. Complete Flow Integration
   - Full flow: discard 2 -> search -> put on bench
   - Abort options (confirm with 0 at search)
   - Multiple Ultra Balls in same turn (once per turn NOT restricted for items)

6. Edge Cases
   - Exact hand size (Ultra Ball + 2 cards)
   - All energy hand (discard energy)
   - All Pokemon hand (discard Pokemon)
   - Mixed hand types
"""

import pytest
import sys
sys.path.insert(0, 'src')

from models import (
    GameState, PlayerState, GamePhase, Action, ActionType,
    SelectFromZoneStep, SearchDeckStep, SelectionPurpose, StepType
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

def create_ultra_ball_state(
    hand_cards: list = None,
    deck_cards: list = None,
    bench_cards: list = None,
    bench_full: bool = False
):
    """
    Create a game state for Ultra Ball testing.

    Args:
        hand_cards: List of card IDs for hand (Ultra Ball auto-added)
        deck_cards: List of card IDs for deck
        bench_cards: List of card IDs already on bench
        bench_full: If True, fill bench to 5 Pokemon
    """
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Both need active Pokemon
    player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)  # Pidgey
    player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

    # Add Ultra Ball to hand first
    ultra_ball = create_card_instance("sv1-196", owner_id=0)
    player0.hand.add_card(ultra_ball)

    # Add other hand cards
    if hand_cards:
        for card_id in hand_cards:
            player0.hand.add_card(create_card_instance(card_id, owner_id=0))

    # Add deck cards
    if deck_cards:
        for card_id in deck_cards:
            player0.deck.add_card(create_card_instance(card_id, owner_id=0))

    # Add bench cards
    if bench_cards:
        for card_id in bench_cards:
            player0.board.add_to_bench(create_card_instance(card_id, owner_id=0))

    # Fill bench if requested
    if bench_full:
        while player0.board.get_bench_count() < 5:
            player0.board.add_to_bench(create_card_instance("sv3pt5-16", owner_id=0))

    return GameState(
        players=[player0, player1],
        turn_count=2,
        active_player_index=0,
        current_phase=GamePhase.MAIN,
        starting_player_id=0
    )


def get_ultra_ball_from_hand(state):
    """Find the Ultra Ball card in player 0's hand."""
    for card in state.players[0].hand.cards:
        card_def = create_card(card.card_id)
        if card_def and card_def.name == "Ultra Ball":
            return card
    return None


def complete_ultra_ball_discard(engine, state, discard_card_ids: list = None):
    """
    Complete the discard phase of Ultra Ball.

    Args:
        engine: PokemonEngine instance
        state: GameState with Ultra Ball discard step active
        discard_card_ids: Specific card IDs to discard (or None for auto-select)

    Returns:
        State after discards are complete (at search phase)
    """
    discard_index = 0
    while state.has_pending_resolution():
        step = state.get_current_step()
        if not isinstance(step, SelectFromZoneStep) or step.purpose != SelectionPurpose.DISCARD_COST:
            break

        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        if not select_actions:
            break

        # Choose discard
        if discard_card_ids and discard_index < len(discard_card_ids):
            action = next((a for a in select_actions if a.card_id == discard_card_ids[discard_index]), select_actions[0])
        else:
            action = select_actions[0]

        state = engine.step(state, action)
        discard_index += 1

        # Check if we need to confirm
        actions = engine.get_legal_actions(state)
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]
        if confirm_actions and len(step.selected_card_ids) >= step.count:
            state = engine.step(state, confirm_actions[0])

    return state


# =============================================================================
# TEST CLASS: HAND SIZE PERMUTATIONS
# =============================================================================

class TestHandSizePermutations:
    """Test Ultra Ball playability based on hand composition."""

    def test_ultra_ball_unplayable_with_zero_other_cards(self, engine):
        """
        Ultra Ball requires discarding 2 cards. With only Ultra Ball in hand,
        it should not be playable.
        """
        state = create_ultra_ball_state(
            hand_cards=[],  # Only Ultra Ball
            deck_cards=["sv3pt5-16"],
        )
        state = engine.initialize_deck_knowledge(state)

        actions = engine.get_legal_actions(state)
        play_item_actions = [a for a in actions if a.action_type == ActionType.PLAY_ITEM]

        # Should have no PLAY_ITEM for Ultra Ball
        ultra_ball = get_ultra_ball_from_hand(state)
        ultra_ball_plays = [a for a in play_item_actions if a.card_id == ultra_ball.id]

        assert len(ultra_ball_plays) == 0, "Ultra Ball should not be playable with 0 other cards"

    def test_ultra_ball_unplayable_with_one_other_card(self, engine):
        """
        With only 1 other card, still can't discard 2, so unplayable.
        """
        state = create_ultra_ball_state(
            hand_cards=["sv3pt5-16"],  # 1 Pidgey
            deck_cards=["sv3pt5-16"],
        )
        state = engine.initialize_deck_knowledge(state)

        actions = engine.get_legal_actions(state)
        play_item_actions = [a for a in actions if a.action_type == ActionType.PLAY_ITEM]

        ultra_ball = get_ultra_ball_from_hand(state)
        ultra_ball_plays = [a for a in play_item_actions if a.card_id == ultra_ball.id]

        assert len(ultra_ball_plays) == 0, "Ultra Ball should not be playable with only 1 other card"

    def test_ultra_ball_playable_with_two_other_cards(self, engine):
        """
        With exactly 2 other cards, Ultra Ball should be playable.
        """
        state = create_ultra_ball_state(
            hand_cards=["sv3pt5-16", "sve-2"],  # Pidgey + Fire Energy
            deck_cards=["sv3pt5-16"],
        )
        state = engine.initialize_deck_knowledge(state)

        actions = engine.get_legal_actions(state)
        play_item_actions = [a for a in actions if a.action_type == ActionType.PLAY_ITEM]

        ultra_ball = get_ultra_ball_from_hand(state)
        ultra_ball_plays = [a for a in play_item_actions if a.card_id == ultra_ball.id]

        assert len(ultra_ball_plays) == 1, "Ultra Ball should be playable with 2 other cards"

    def test_ultra_ball_playable_with_many_cards(self, engine):
        """
        With many cards in hand, Ultra Ball should be playable with choice.
        """
        state = create_ultra_ball_state(
            hand_cards=["sv3pt5-16", "sv3pt5-16", "sve-2", "sve-2", "sv2-185"],  # 5 cards + Ultra Ball
            deck_cards=["sv3pt5-16"],
        )
        state = engine.initialize_deck_knowledge(state)

        actions = engine.get_legal_actions(state)
        play_item_actions = [a for a in actions if a.action_type == ActionType.PLAY_ITEM]

        ultra_ball = get_ultra_ball_from_hand(state)
        ultra_ball_plays = [a for a in play_item_actions if a.card_id == ultra_ball.id]

        assert len(ultra_ball_plays) == 1, "Ultra Ball should generate single play action"


# =============================================================================
# TEST CLASS: DISCARD SELECTION
# =============================================================================

class TestDiscardSelection:
    """Test the discard selection mechanics."""

    def test_cannot_discard_ultra_ball_being_played(self, engine):
        """
        The Ultra Ball being played should NOT appear as a discard option.
        """
        state = create_ultra_ball_state(
            hand_cards=["sv3pt5-16", "sve-2"],
            deck_cards=["sv3pt5-16"],
        )
        state = engine.initialize_deck_knowledge(state)

        ultra_ball = get_ultra_ball_from_hand(state)

        # Play Ultra Ball
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == ultra_ball.id)
        state = engine.step(state, play_action)

        # Get discard options
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Ultra Ball should NOT be in the discard options
        discard_card_ids = [a.card_id for a in select_actions]
        assert ultra_ball.id not in discard_card_ids, "Ultra Ball being played should not be a discard option"

    def test_can_discard_second_ultra_ball(self, engine):
        """
        With 2 Ultra Balls in hand, the second one CAN be discarded.
        """
        state = create_ultra_ball_state(
            hand_cards=["sv1-196", "sv3pt5-16"],  # Second Ultra Ball + Pidgey
            deck_cards=["sv3pt5-16"],
        )
        state = engine.initialize_deck_knowledge(state)

        # Find both Ultra Balls
        ultra_balls = [c for c in state.players[0].hand.cards if create_card(c.card_id).name == "Ultra Ball"]
        assert len(ultra_balls) == 2, "Should have 2 Ultra Balls"

        played_ultra_ball = ultra_balls[0]
        other_ultra_ball = ultra_balls[1]

        # Play the first Ultra Ball
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == played_ultra_ball.id)
        state = engine.step(state, play_action)

        # Get discard options
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        discard_card_ids = [a.card_id for a in select_actions]

        # Played Ultra Ball should NOT be there, but other Ultra Ball SHOULD be
        assert played_ultra_ball.id not in discard_card_ids, "Played Ultra Ball should not be a discard option"
        assert other_ultra_ball.id in discard_card_ids, "Second Ultra Ball should be discardable"

    def test_can_discard_any_card_type(self, engine):
        """
        Any card type (Pokemon, Trainer, Energy) can be discarded.
        """
        state = create_ultra_ball_state(
            hand_cards=["sv3pt5-16", "sve-2", "sv2-185"],  # Pokemon, Energy, Supporter
            deck_cards=["sv3pt5-16"],
        )
        state = engine.initialize_deck_knowledge(state)

        ultra_ball = get_ultra_ball_from_hand(state)

        # Play Ultra Ball
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == ultra_ball.id)
        state = engine.step(state, play_action)

        # Get discard options
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Should have 3 options (all non-Ultra Ball cards)
        assert len(select_actions) == 3, f"Should have 3 discard options, got {len(select_actions)}"

    def test_discard_exactly_two_required(self, engine):
        """
        Must discard exactly 2 cards - no more, no less.
        """
        state = create_ultra_ball_state(
            hand_cards=["sv3pt5-16", "sve-2", "sv2-185"],
            deck_cards=["sv3pt5-16"],
        )
        state = engine.initialize_deck_knowledge(state)

        ultra_ball = get_ultra_ball_from_hand(state)

        # Play Ultra Ball
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == ultra_ball.id)
        state = engine.step(state, play_action)

        # After selecting 1 card, should NOT have confirm option yet
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        state = engine.step(state, select_actions[0])

        actions = engine.get_legal_actions(state)
        confirm_after_1 = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]
        assert len(confirm_after_1) == 0, "Should NOT be able to confirm after only 1 discard"

        # After selecting 2nd card, confirm should appear
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        state = engine.step(state, select_actions[0])

        actions = engine.get_legal_actions(state)
        confirm_after_2 = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]
        assert len(confirm_after_2) == 1, "Should be able to confirm after 2 discards"

    def test_selected_card_removed_from_options(self, engine):
        """
        After selecting first discard, that card should not appear in second selection.
        """
        state = create_ultra_ball_state(
            hand_cards=["sv3pt5-16", "sve-2", "sv2-185"],
            deck_cards=["sv3pt5-16"],
        )
        state = engine.initialize_deck_knowledge(state)

        ultra_ball = get_ultra_ball_from_hand(state)
        pidgey = next(c for c in state.players[0].hand.cards if create_card(c.card_id).name == "Pidgey")

        # Play Ultra Ball
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == ultra_ball.id)
        state = engine.step(state, play_action)

        # Select Pidgey as first discard
        actions = engine.get_legal_actions(state)
        pidgey_action = next(a for a in actions if a.action_type == ActionType.SELECT_CARD and a.card_id == pidgey.id)
        state = engine.step(state, pidgey_action)

        # Pidgey should NOT be in second selection options
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        second_selection_ids = [a.card_id for a in select_actions]

        assert pidgey.id not in second_selection_ids, "Already selected card should not appear in second selection"


# =============================================================================
# TEST CLASS: DECK SEARCH VARIATIONS
# =============================================================================

class TestDeckSearchVariations:
    """Test Ultra Ball's search behavior with different deck states."""

    def test_search_with_pokemon_in_deck(self, engine):
        """
        With Pokemon in deck, should be able to select and add to bench.
        """
        state = create_ultra_ball_state(
            hand_cards=["sv3pt5-16", "sve-2"],
            deck_cards=["sv3pt5-16", "sv4pt5-7", "sv3pt5-17"],  # Pidgey, Charmander, Pidgeotto
        )
        state = engine.initialize_deck_knowledge(state)

        ultra_ball = get_ultra_ball_from_hand(state)

        # Play Ultra Ball
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == ultra_ball.id)
        state = engine.step(state, play_action)

        # Complete discards
        state = complete_ultra_ball_discard(engine, state)

        # Should now be at search phase
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Should have 3 Pokemon to choose from
        assert len(select_actions) == 3, f"Should have 3 Pokemon to select, got {len(select_actions)}"

    def test_search_with_no_pokemon_in_deck(self, engine):
        """
        With no Pokemon in deck, should only have confirm (fail search) option.
        """
        state = create_ultra_ball_state(
            hand_cards=["sv3pt5-16", "sve-2"],
            deck_cards=["sve-2", "sve-3", "sv2-185"],  # Energy and Supporters only
        )
        state = engine.initialize_deck_knowledge(state)

        ultra_ball = get_ultra_ball_from_hand(state)

        # Play Ultra Ball
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == ultra_ball.id)
        state = engine.step(state, play_action)

        # Complete discards
        state = complete_ultra_ball_discard(engine, state)

        # Should only have confirm option (no Pokemon to select)
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]

        assert len(select_actions) == 0, "Should have no Pokemon to select"
        assert len(confirm_actions) == 1, "Should have confirm option to fail search"

    def test_search_with_empty_deck(self, engine):
        """
        With empty deck, should handle gracefully.
        """
        state = create_ultra_ball_state(
            hand_cards=["sv3pt5-16", "sve-2"],
            deck_cards=[],  # Empty deck
        )
        state = engine.initialize_deck_knowledge(state)

        ultra_ball = get_ultra_ball_from_hand(state)

        # Play Ultra Ball
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == ultra_ball.id)
        state = engine.step(state, play_action)

        # Complete discards
        state = complete_ultra_ball_discard(engine, state)

        # Should only have confirm option
        actions = engine.get_legal_actions(state)
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]

        assert len(confirm_actions) >= 1, "Should have confirm option with empty deck"

    def test_search_finds_all_pokemon_types(self, engine):
        """
        Ultra Ball can find any Pokemon (Basic, Stage 1, Stage 2, ex, etc.).
        """
        state = create_ultra_ball_state(
            hand_cards=["sv3pt5-16", "sve-2"],
            deck_cards=[
                "sv3pt5-16",   # Basic (Pidgey)
                "sv3pt5-17",   # Stage 1 (Pidgeotto)
                "sv3pt5-18",   # Stage 2 (Pidgeot ex)
                "sv4pt5-7",    # Basic (Charmander)
            ],
        )
        state = engine.initialize_deck_knowledge(state)

        ultra_ball = get_ultra_ball_from_hand(state)

        # Play and discard
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == ultra_ball.id)
        state = engine.step(state, play_action)
        state = complete_ultra_ball_discard(engine, state)

        # Should have all 4 Pokemon selectable
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        assert len(select_actions) == 4, f"Should find all 4 Pokemon, got {len(select_actions)}"


# =============================================================================
# TEST CLASS: KNOWLEDGE LAYER INTERACTIONS
# =============================================================================

class TestKnowledgeLayerInteractions:
    """Test Ultra Ball with and without deck knowledge."""

    def test_with_deck_knowledge(self, engine):
        """
        With deck knowledge initialized, Ultra Ball should work correctly.
        """
        state = create_ultra_ball_state(
            hand_cards=["sv3pt5-16", "sve-2"],
            deck_cards=["sv4pt5-7"],
        )
        state = engine.initialize_deck_knowledge(state)

        assert len(state.players[0].initial_deck_counts) > 0, "Deck knowledge should be initialized"

        ultra_ball = get_ultra_ball_from_hand(state)

        # Full flow should work
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == ultra_ball.id)
        state = engine.step(state, play_action)
        state = complete_ultra_ball_discard(engine, state)

        # Should be at search phase
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        assert len(select_actions) == 1, "Should find the Charmander in deck"

    def test_without_deck_knowledge(self, engine):
        """
        Without deck knowledge, Ultra Ball should still work.
        """
        state = create_ultra_ball_state(
            hand_cards=["sv3pt5-16", "sve-2"],
            deck_cards=["sv4pt5-7"],
        )
        # Do NOT initialize deck knowledge

        assert len(state.players[0].initial_deck_counts) == 0, "Deck knowledge should not be initialized"

        ultra_ball = get_ultra_ball_from_hand(state)

        # Full flow should still work
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == ultra_ball.id)
        state = engine.step(state, play_action)
        state = complete_ultra_ball_discard(engine, state)

        # Should be at search phase
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        assert len(select_actions) == 1

    def test_has_searched_deck_set_after_search(self, engine):
        """
        After using Ultra Ball to search, has_searched_deck should be True.
        """
        state = create_ultra_ball_state(
            hand_cards=["sv3pt5-16", "sve-2"],
            deck_cards=["sv4pt5-7"],
        )
        state = engine.initialize_deck_knowledge(state)

        assert state.players[0].has_searched_deck == False, "Should not have searched yet"

        ultra_ball = get_ultra_ball_from_hand(state)

        # Complete full flow
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == ultra_ball.id)
        state = engine.step(state, play_action)
        state = complete_ultra_ball_discard(engine, state)

        # Select a Pokemon
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        state = engine.step(state, select_actions[0])

        # Confirm selection
        actions = engine.get_legal_actions(state)
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]
        state = engine.step(state, confirm_actions[0])

        assert state.players[0].has_searched_deck == True, "Should have searched deck after Ultra Ball"


# =============================================================================
# TEST CLASS: COMPLETE FLOW INTEGRATION
# =============================================================================

class TestCompleteFlowIntegration:
    """Test the full Ultra Ball flow from play to completion."""

    def test_full_flow_discard_search_hand(self, engine):
        """
        Complete flow: play -> discard 2 -> search -> select Pokemon -> hand.
        Note: Ultra Ball adds Pokemon to HAND, not bench (unlike Nest Ball).
        """
        state = create_ultra_ball_state(
            hand_cards=["sv3pt5-16", "sve-2"],
            deck_cards=["sv4pt5-7"],  # Charmander
        )
        state = engine.initialize_deck_knowledge(state)

        initial_deck_count = len(state.players[0].deck.cards)

        ultra_ball = get_ultra_ball_from_hand(state)

        # Play Ultra Ball
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == ultra_ball.id)
        state = engine.step(state, play_action)

        # Discard phase
        state = complete_ultra_ball_discard(engine, state)

        # Search phase - select Charmander
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        state = engine.step(state, select_actions[0])

        # Confirm
        actions = engine.get_legal_actions(state)
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]
        state = engine.step(state, confirm_actions[0])

        # Verify results
        final_hand_count = state.players[0].hand.count()
        final_deck_count = len(state.players[0].deck.cards)

        # Hand: started with 3 (Ultra Ball + 2), discarded 2, Ultra Ball used, +1 from search = 1
        assert final_hand_count == 1, f"Hand should have 1 card (searched Pokemon), got {final_hand_count}"
        # Deck: started with 1, removed 1 = 0
        assert final_deck_count == initial_deck_count - 1, "Deck should have 1 less card"
        assert not state.has_pending_resolution(), "Resolution stack should be clear"

        # Verify the Pokemon is now in hand
        hand_pokemon = [c for c in state.players[0].hand.cards if create_card(c.card_id).name == "Charmander"]
        assert len(hand_pokemon) == 1, "Charmander should be in hand"

    def test_decline_search_flow(self, engine):
        """
        Player can decline to search (confirm with 0 selected).
        """
        state = create_ultra_ball_state(
            hand_cards=["sv3pt5-16", "sve-2"],
            deck_cards=["sv4pt5-7"],
        )
        state = engine.initialize_deck_knowledge(state)

        initial_bench_count = state.players[0].board.get_bench_count()

        ultra_ball = get_ultra_ball_from_hand(state)

        # Play and discard
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == ultra_ball.id)
        state = engine.step(state, play_action)
        state = complete_ultra_ball_discard(engine, state)

        # At search phase, confirm without selecting
        actions = engine.get_legal_actions(state)
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]
        state = engine.step(state, confirm_actions[0])

        # Bench should be unchanged
        final_bench_count = state.players[0].board.get_bench_count()
        assert final_bench_count == initial_bench_count, "Bench should be unchanged after declining"
        assert not state.has_pending_resolution(), "Resolution should be complete"

    def test_multiple_ultra_balls_same_turn(self, engine):
        """
        Item cards can be played multiple times per turn.
        Playing multiple Ultra Balls in one turn should work.
        """
        state = create_ultra_ball_state(
            hand_cards=["sv1-196", "sv3pt5-16", "sve-2", "sv2-185", "sv3pt5-17"],  # 2nd Ultra Ball + 4 cards
            deck_cards=["sv4pt5-7", "sv4pt5-8"],  # Charmander, Charmeleon
        )
        state = engine.initialize_deck_knowledge(state)

        # Find both Ultra Balls
        ultra_balls = [c for c in state.players[0].hand.cards if create_card(c.card_id).name == "Ultra Ball"]
        assert len(ultra_balls) == 2

        # Play first Ultra Ball
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == ultra_balls[0].id)
        state = engine.step(state, play_action)
        state = complete_ultra_ball_discard(engine, state)

        # Select a Pokemon
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        state = engine.step(state, select_actions[0])

        # Confirm
        actions = engine.get_legal_actions(state)
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]
        state = engine.step(state, confirm_actions[0])

        # Should be able to play second Ultra Ball (if hand still has 2+ cards to discard)
        actions = engine.get_legal_actions(state)
        play_item_actions = [a for a in actions if a.action_type == ActionType.PLAY_ITEM]

        # Second Ultra Ball should be playable if we have enough cards
        second_ultra_ball_in_hand = next(
            (c for c in state.players[0].hand.cards if create_card(c.card_id).name == "Ultra Ball"),
            None
        )

        if second_ultra_ball_in_hand:
            # Check if playable (need 2 other cards)
            other_cards = [c for c in state.players[0].hand.cards if c.id != second_ultra_ball_in_hand.id]
            if len(other_cards) >= 2:
                second_plays = [a for a in play_item_actions if a.card_id == second_ultra_ball_in_hand.id]
                assert len(second_plays) == 1, "Second Ultra Ball should be playable"


# =============================================================================
# TEST CLASS: EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_bench_full_can_still_search(self, engine):
        """
        With full bench, Ultra Ball search should still work but found Pokemon
        might go to hand instead (or search might find nothing useful).
        Note: This depends on implementation - Ultra Ball typically adds to hand.
        """
        state = create_ultra_ball_state(
            hand_cards=["sv3pt5-16", "sve-2"],
            deck_cards=["sv4pt5-7"],
            bench_full=True,
        )
        state = engine.initialize_deck_knowledge(state)

        assert state.players[0].board.get_bench_count() == 5, "Bench should be full"

        ultra_ball = get_ultra_ball_from_hand(state)

        # Should still be able to play Ultra Ball
        actions = engine.get_legal_actions(state)
        play_item_actions = [a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == ultra_ball.id]

        # Ultra Ball adds Pokemon to hand, not bench, so should be playable
        assert len(play_item_actions) == 1, "Ultra Ball should be playable even with full bench"

    def test_exact_minimum_hand(self, engine):
        """
        With exactly Ultra Ball + 2 cards, all cards become mandatory discards.
        """
        state = create_ultra_ball_state(
            hand_cards=["sv3pt5-16", "sve-2"],  # Exactly 2 cards
            deck_cards=["sv4pt5-7"],
        )
        state = engine.initialize_deck_knowledge(state)

        ultra_ball = get_ultra_ball_from_hand(state)
        pidgey = next(c for c in state.players[0].hand.cards if create_card(c.card_id).name == "Pidgey")
        energy = next(c for c in state.players[0].hand.cards if "Energy" in create_card(c.card_id).name)

        # Play Ultra Ball
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == ultra_ball.id)
        state = engine.step(state, play_action)

        # First discard - should have 2 options
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        assert len(select_actions) == 2, "Should have exactly 2 discard options"

        # Discard first
        state = engine.step(state, select_actions[0])

        # Second discard - should have only 1 option (the remaining card)
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        assert len(select_actions) == 1, "Should have exactly 1 remaining discard option"

    def test_all_energy_hand_discard(self, engine):
        """
        Hand with all energy cards (+ Ultra Ball) should work.
        Note: Identical cards are deduplicated by functional ID for discard,
        so we use different energy types to get 3 unique options.
        """
        state = create_ultra_ball_state(
            hand_cards=["sve-2", "sve-3", "sv1-258"],  # Fire, Water, Fighting (3 different)
            deck_cards=["sv4pt5-7"],
        )
        state = engine.initialize_deck_knowledge(state)

        ultra_ball = get_ultra_ball_from_hand(state)

        # Play and verify discards work
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == ultra_ball.id)
        state = engine.step(state, play_action)

        # Should have 3 energy cards to choose from for discard (one per unique type)
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        assert len(select_actions) == 3, "Should have 3 energy cards to discard"

    def test_all_pokemon_hand_discard(self, engine):
        """
        Hand with all Pokemon cards (+ Ultra Ball) should work.
        """
        state = create_ultra_ball_state(
            hand_cards=["sv3pt5-16", "sv4pt5-7", "sv4pt5-8"],  # 3 Pokemon
            deck_cards=["sv4pt5-9"],
        )
        state = engine.initialize_deck_knowledge(state)

        ultra_ball = get_ultra_ball_from_hand(state)

        # Play and verify discards work
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == ultra_ball.id)
        state = engine.step(state, play_action)

        # Should have 3 Pokemon to choose from for discard
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        assert len(select_actions) == 3, "Should have 3 Pokemon cards to discard"

    def test_cards_actually_go_to_discard_pile(self, engine):
        """
        Discarded cards should end up in the discard pile.
        """
        state = create_ultra_ball_state(
            hand_cards=["sv3pt5-16", "sve-2"],
            deck_cards=["sv4pt5-7"],
        )
        state = engine.initialize_deck_knowledge(state)

        initial_discard_count = len(state.players[0].discard.cards)

        ultra_ball = get_ultra_ball_from_hand(state)
        pidgey = next(c for c in state.players[0].hand.cards if create_card(c.card_id).name == "Pidgey")
        energy = next(c for c in state.players[0].hand.cards if "Energy" in create_card(c.card_id).name)

        # Play and complete flow
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == ultra_ball.id)
        state = engine.step(state, play_action)

        # Discard Pidgey
        actions = engine.get_legal_actions(state)
        pidgey_action = next(a for a in actions if a.action_type == ActionType.SELECT_CARD and a.card_id == pidgey.id)
        state = engine.step(state, pidgey_action)

        # Discard Energy
        actions = engine.get_legal_actions(state)
        energy_action = next(a for a in actions if a.action_type == ActionType.SELECT_CARD and a.card_id == energy.id)
        state = engine.step(state, energy_action)

        # Confirm discards
        actions = engine.get_legal_actions(state)
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]
        state = engine.step(state, confirm_actions[0])

        # Finish search (decline)
        actions = engine.get_legal_actions(state)
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]
        if confirm_actions:
            state = engine.step(state, confirm_actions[0])

        # Discard pile should have: 2 discarded + Ultra Ball itself = 3
        final_discard_count = len(state.players[0].discard.cards)
        assert final_discard_count == initial_discard_count + 3, f"Should have 3 cards in discard, got {final_discard_count - initial_discard_count}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

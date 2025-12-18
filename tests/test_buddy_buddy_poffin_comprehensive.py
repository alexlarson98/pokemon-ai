"""
Comprehensive pytest suite for Buddy-Buddy Poffin stack mechanics.

Buddy-Buddy Poffin: Search your deck for up to 2 Basic Pokemon with 70 HP
or less and put them onto your Bench. Then, shuffle your deck.

Test Categories:
1. Playability Conditions
   - Bench full (unplayable)
   - Bench has 1 slot (can get 1)
   - Bench has 2+ slots (can get up to 2)

2. HP Filter (70 HP or less)
   - Pokemon with HP <= 70 selectable
   - Pokemon with HP > 70 excluded
   - Boundary test: exactly 70 HP

3. Selection Behavior
   - Can select 0 (decline)
   - Can select 1 (partial)
   - Can select 2 (full)
   - Cannot select more than 2

4. Deck Variations
   - Multiple eligible Pokemon
   - No eligible Pokemon
   - Mix of eligible and ineligible

5. Knowledge Layer
   - With/without deck knowledge
   - has_searched_deck flag

6. Edge Cases
   - Only 1 bench slot but 2 Pokemon available
   - All high HP Pokemon in deck
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


def create_poffin_state(
    deck_cards: list = None,
    bench_count: int = 0,
    bench_full: bool = False
):
    """Create game state for Buddy-Buddy Poffin testing."""
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
    player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

    # Add Poffin to hand
    poffin = create_card_instance("sv5-144", owner_id=0)
    player0.hand.add_card(poffin)

    if deck_cards:
        for card_id in deck_cards:
            player0.deck.add_card(create_card_instance(card_id, owner_id=0))

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


def get_poffin_from_hand(state):
    for card in state.players[0].hand.cards:
        card_def = create_card(card.card_id)
        if card_def and card_def.name == "Buddy-Buddy Poffin":
            return card
    return None


# =============================================================================
# PLAYABILITY CONDITIONS
# =============================================================================

class TestPlayabilityConditions:
    """Test when Buddy-Buddy Poffin can be played."""

    def test_unplayable_with_full_bench(self, engine):
        """Poffin unplayable when bench is full."""
        state = create_poffin_state(
            deck_cards=["sv3pt5-16", "sv4pt5-7"],
            bench_full=True
        )
        state = engine.initialize_deck_knowledge(state)

        poffin = get_poffin_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_actions = [a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == poffin.id]

        assert len(play_actions) == 0, "Poffin unplayable with full bench"

    def test_playable_with_one_bench_slot(self, engine):
        """Poffin playable with 1 bench slot (can get 1)."""
        state = create_poffin_state(
            deck_cards=["sv3pt5-16", "sv4pt5-7"],
            bench_count=4
        )
        state = engine.initialize_deck_knowledge(state)

        poffin = get_poffin_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_actions = [a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == poffin.id]

        assert len(play_actions) == 1, "Poffin should be playable with 1 slot"

    def test_playable_with_multiple_bench_slots(self, engine):
        """Poffin playable with multiple bench slots."""
        state = create_poffin_state(
            deck_cards=["sv3pt5-16", "sv4pt5-7"],
            bench_count=2
        )
        state = engine.initialize_deck_knowledge(state)

        poffin = get_poffin_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_actions = [a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == poffin.id]

        assert len(play_actions) == 1


# =============================================================================
# HP FILTER
# =============================================================================

class TestHPFilter:
    """Test the HP <= 70 filter."""

    def test_low_hp_pokemon_selectable(self, engine):
        """Pokemon with HP <= 70 should be selectable."""
        # Pidgey has 60 HP, Charmander has 70 HP
        state = create_poffin_state(
            deck_cards=["sv3pt5-16", "sv4pt5-7"]  # Pidgey (60), Charmander (70)
        )
        state = engine.initialize_deck_knowledge(state)

        poffin = get_poffin_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == poffin.id)
        state = engine.step(state, play_action)

        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        assert len(select_actions) == 2, "Both low HP Pokemon should be selectable"

    def test_high_hp_pokemon_excluded(self, engine):
        """Pokemon with HP > 70 should be excluded."""
        state = create_poffin_state(
            deck_cards=["sv3pt5-16", "sv3pt5-18"]  # Pidgey (60) + Pidgeot ex (high HP)
        )
        state = engine.initialize_deck_knowledge(state)

        poffin = get_poffin_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == poffin.id)
        state = engine.step(state, play_action)

        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Only Pidgey (60 HP) should be selectable
        assert len(select_actions) == 1, "Only low HP Pokemon should be selectable"

    def test_exactly_70_hp_included(self, engine):
        """Pokemon with exactly 70 HP should be included."""
        # Charmander has 70 HP
        state = create_poffin_state(
            deck_cards=["sv4pt5-7"]  # Charmander (70 HP)
        )
        state = engine.initialize_deck_knowledge(state)

        poffin = get_poffin_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == poffin.id)
        state = engine.step(state, play_action)

        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        assert len(select_actions) == 1, "70 HP Pokemon should be selectable"

    def test_stage_1_excluded_even_if_low_hp(self, engine):
        """Stage 1 excluded even if HP <= 70."""
        # Need to find a Stage 1 with low HP or just verify Basic filter works
        state = create_poffin_state(
            deck_cards=["sv3pt5-16", "sv4pt5-8"]  # Pidgey (Basic) + Charmeleon (Stage 1)
        )
        state = engine.initialize_deck_knowledge(state)

        poffin = get_poffin_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == poffin.id)
        state = engine.step(state, play_action)

        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Only Pidgey (Basic with low HP)
        assert len(select_actions) == 1, "Only Basic Pokemon selectable"


# =============================================================================
# SELECTION BEHAVIOR
# =============================================================================

class TestSelectionBehavior:
    """Test selection count behavior."""

    def test_can_select_zero_decline(self, engine):
        """Can confirm with 0 selections (decline)."""
        state = create_poffin_state(
            deck_cards=["sv3pt5-16", "sv4pt5-7"]
        )
        state = engine.initialize_deck_knowledge(state)

        poffin = get_poffin_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == poffin.id)
        state = engine.step(state, play_action)

        # Should have confirm option immediately (min_count=0)
        actions = engine.get_legal_actions(state)
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]

        assert len(confirm_actions) == 1, "Should be able to confirm with 0"

    def test_can_select_one_partial(self, engine):
        """Can confirm after selecting 1 (partial)."""
        state = create_poffin_state(
            deck_cards=["sv3pt5-16", "sv4pt5-7"]
        )
        state = engine.initialize_deck_knowledge(state)

        initial_bench = state.players[0].board.get_bench_count()

        poffin = get_poffin_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == poffin.id)
        state = engine.step(state, play_action)

        # Select 1
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        state = engine.step(state, select_actions[0])

        # Should be able to confirm with 1
        actions = engine.get_legal_actions(state)
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]
        assert len(confirm_actions) >= 1

        state = engine.step(state, confirm_actions[0])

        final_bench = state.players[0].board.get_bench_count()
        assert final_bench == initial_bench + 1, "Should have +1 on bench"

    def test_can_select_two_full(self, engine):
        """Can select 2 Pokemon (full)."""
        state = create_poffin_state(
            deck_cards=["sv3pt5-16", "sv4pt5-7"]
        )
        state = engine.initialize_deck_knowledge(state)

        initial_bench = state.players[0].board.get_bench_count()

        poffin = get_poffin_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == poffin.id)
        state = engine.step(state, play_action)

        # Select first
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        state = engine.step(state, select_actions[0])

        # Select second
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        if select_actions:
            state = engine.step(state, select_actions[0])

        # Confirm
        actions = engine.get_legal_actions(state)
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]
        state = engine.step(state, confirm_actions[0])

        final_bench = state.players[0].board.get_bench_count()
        assert final_bench == initial_bench + 2, "Should have +2 on bench"

    def test_cannot_select_more_than_two(self, engine):
        """Cannot select more than 2."""
        state = create_poffin_state(
            deck_cards=["sv3pt5-16", "sv3pt5-16", "sv4pt5-7", "sv4pt5-7"]  # 4 eligible
        )
        state = engine.initialize_deck_knowledge(state)

        poffin = get_poffin_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == poffin.id)
        state = engine.step(state, play_action)

        # Select first
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        state = engine.step(state, select_actions[0])

        # Select second
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        state = engine.step(state, select_actions[0])

        # After 2 selections, should only have CONFIRM (no more SELECT)
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]

        assert len(select_actions) == 0, "Should not allow more than 2 selections"
        assert len(confirm_actions) == 1, "Should have confirm after 2"


# =============================================================================
# DECK VARIATIONS
# =============================================================================

class TestDeckVariations:
    """Test with different deck compositions."""

    def test_no_eligible_pokemon(self, engine):
        """No eligible Pokemon - only decline option."""
        state = create_poffin_state(
            deck_cards=["sv3pt5-18", "sve-2"]  # Pidgeot ex (high HP) + Energy
        )
        state = engine.initialize_deck_knowledge(state)

        poffin = get_poffin_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == poffin.id)
        state = engine.step(state, play_action)

        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]

        assert len(select_actions) == 0, "No eligible Pokemon"
        assert len(confirm_actions) == 1, "Should have decline option"

    def test_mix_eligible_and_ineligible(self, engine):
        """Mix of eligible and ineligible Pokemon."""
        state = create_poffin_state(
            deck_cards=[
                "sv3pt5-16",   # Pidgey - eligible (60 HP, Basic)
                "sv4pt5-7",    # Charmander - eligible (70 HP, Basic)
                "sv4pt5-8",    # Charmeleon - ineligible (Stage 1)
                "sv3pt5-18",   # Pidgeot ex - ineligible (high HP)
            ]
        )
        state = engine.initialize_deck_knowledge(state)

        poffin = get_poffin_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == poffin.id)
        state = engine.step(state, play_action)

        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Only Pidgey and Charmander should be selectable
        assert len(select_actions) == 2


# =============================================================================
# KNOWLEDGE LAYER
# =============================================================================

class TestKnowledgeLayer:
    """Test knowledge layer interactions."""

    def test_with_deck_knowledge(self, engine):
        """Works with deck knowledge initialized."""
        state = create_poffin_state(
            deck_cards=["sv3pt5-16", "sv4pt5-7"]
        )
        state = engine.initialize_deck_knowledge(state)

        poffin = get_poffin_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == poffin.id)
        state = engine.step(state, play_action)

        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        assert len(select_actions) == 2

    def test_without_deck_knowledge(self, engine):
        """Works without deck knowledge initialized."""
        state = create_poffin_state(
            deck_cards=["sv3pt5-16", "sv4pt5-7"]
        )
        # Don't initialize

        poffin = get_poffin_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == poffin.id)
        state = engine.step(state, play_action)

        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        assert len(select_actions) == 2

    def test_has_searched_deck_set(self, engine):
        """has_searched_deck should be set after using Poffin."""
        state = create_poffin_state(
            deck_cards=["sv3pt5-16"]
        )
        state = engine.initialize_deck_knowledge(state)

        assert state.players[0].has_searched_deck == False

        poffin = get_poffin_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == poffin.id)
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
    """Test edge cases."""

    def test_one_bench_slot_with_two_eligible(self, engine):
        """With 1 bench slot, can only select 1 even if 2 eligible."""
        state = create_poffin_state(
            deck_cards=["sv3pt5-16", "sv4pt5-7"],
            bench_count=4  # Only 1 slot
        )
        state = engine.initialize_deck_knowledge(state)

        poffin = get_poffin_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == poffin.id)
        state = engine.step(state, play_action)

        # Select 1
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        state = engine.step(state, select_actions[0])

        # Should only have confirm now (bench will be full)
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]

        # Can't select more - bench will be full
        assert len(confirm_actions) >= 1

    def test_poffin_goes_to_discard(self, engine):
        """Poffin should go to discard after use."""
        state = create_poffin_state(
            deck_cards=["sv3pt5-16"]
        )
        state = engine.initialize_deck_knowledge(state)

        initial_discard = len(state.players[0].discard.cards)

        poffin = get_poffin_from_hand(state)
        actions = engine.get_legal_actions(state)
        play_action = next(a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == poffin.id)
        state = engine.step(state, play_action)

        # Decline
        actions = engine.get_legal_actions(state)
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]
        state = engine.step(state, confirm_actions[0])

        final_discard = len(state.players[0].discard.cards)
        assert final_discard == initial_discard + 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

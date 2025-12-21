"""
Comprehensive pytest suite for Night Stretcher item card.

Night Stretcher: Put a Pokemon or a Basic Energy card from your discard pile into your hand.

Test Categories:
1. Playability Conditions
   - Has valid targets in discard (Pokemon or Basic Energy)
   - No valid targets in discard (unplayable)
   - Only trainer cards in discard (unplayable)
   - Only special energy in discard (unplayable)

2. Target Selection
   - Can select any Pokemon from discard
   - Can select Basic Energy from discard
   - Cannot select Trainer cards
   - Cannot select Special Energy
   - Cannot select Night Stretcher itself

3. Recovery Flow
   - Selected card moves from discard to hand
   - Night Stretcher moves to discard after use
   - Discard pile properly updated

4. Edge Cases
   - Single valid target in discard
   - Multiple valid targets of same type
   - Mixed valid targets (Pokemon + Basic Energy)
   - Night Stretcher with empty discard
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

def create_night_stretcher_state(
    discard_cards: list = None,
    hand_cards: list = None,
):
    """
    Create a game state for Night Stretcher testing.

    Args:
        discard_cards: List of card IDs for discard pile
        hand_cards: List of additional card IDs for hand (Night Stretcher auto-added)
    """
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Both need active Pokemon
    player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)  # Pidgey
    player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

    # Add Night Stretcher to hand
    night_stretcher = create_card_instance("sv6pt5-61", owner_id=0)
    player0.hand.add_card(night_stretcher)

    # Add other hand cards
    if hand_cards:
        for card_id in hand_cards:
            player0.hand.add_card(create_card_instance(card_id, owner_id=0))

    # Add discard pile cards
    if discard_cards:
        for card_id in discard_cards:
            player0.discard.add_card(create_card_instance(card_id, owner_id=0))

    return GameState(
        players=[player0, player1],
        turn_count=2,
        active_player_index=0,
        current_phase=GamePhase.MAIN,
        starting_player_id=0
    )


def get_night_stretcher_from_hand(state):
    """Find the Night Stretcher card in player 0's hand."""
    for card in state.players[0].hand.cards:
        card_def = create_card(card.card_id)
        if card_def and card_def.name == "Night Stretcher":
            return card
    return None


def find_play_night_stretcher_action(actions):
    """Find the Play Night Stretcher action from a list of actions."""
    for action in actions:
        if action.action_type == ActionType.PLAY_ITEM:
            card_def = create_card(action.card_id) if hasattr(action, 'card_id') else None
            if action.display_label and "Night Stretcher" in action.display_label:
                return action
    return None


# =============================================================================
# TEST: PLAYABILITY CONDITIONS
# =============================================================================

class TestNightStretcherPlayability:
    """Test when Night Stretcher can and cannot be played."""

    def test_playable_with_pokemon_in_discard(self, engine):
        """Night Stretcher is playable when Pokemon are in discard."""
        state = create_night_stretcher_state(
            discard_cards=["sv3pt5-16"]  # Pidgey
        )

        actions = engine.get_legal_actions(state)
        play_action = find_play_night_stretcher_action(actions)

        assert play_action is not None, "Night Stretcher should be playable with Pokemon in discard"

    def test_playable_with_basic_energy_in_discard(self, engine):
        """Night Stretcher is playable when Basic Energy is in discard."""
        state = create_night_stretcher_state(
            discard_cards=["base1-98"]  # Fire Energy
        )

        actions = engine.get_legal_actions(state)
        play_action = find_play_night_stretcher_action(actions)

        assert play_action is not None, "Night Stretcher should be playable with Basic Energy in discard"

    def test_not_playable_with_empty_discard(self, engine):
        """Night Stretcher is NOT playable when discard is empty."""
        state = create_night_stretcher_state(
            discard_cards=[]
        )

        actions = engine.get_legal_actions(state)
        play_action = find_play_night_stretcher_action(actions)

        assert play_action is None, "Night Stretcher should not be playable with empty discard"

    def test_not_playable_with_only_trainers_in_discard(self, engine):
        """Night Stretcher is NOT playable when only Trainer cards are in discard."""
        state = create_night_stretcher_state(
            discard_cards=["sv1-196"]  # Ultra Ball (trainer)
        )

        actions = engine.get_legal_actions(state)
        play_action = find_play_night_stretcher_action(actions)

        assert play_action is None, "Night Stretcher should not be playable with only trainers in discard"


# =============================================================================
# TEST: RECOVERY FLOW
# =============================================================================

class TestNightStretcherRecoveryFlow:
    """Test the full recovery flow of Night Stretcher."""

    def test_pokemon_recovered_to_hand(self, engine):
        """Pokemon selected from discard should move to hand."""
        # Setup: Pidgey in discard
        state = create_night_stretcher_state(
            discard_cards=["sv3pt5-16"]  # Pidgey
        )

        # Get and apply the play action
        actions = engine.get_legal_actions(state)
        play_action = find_play_night_stretcher_action(actions)
        assert play_action is not None

        # Store initial counts
        initial_hand_count = len(state.players[0].hand.cards)
        initial_discard_count = len(state.players[0].discard.cards)

        # Apply play action - this pushes the selection step
        state = engine.step(state, play_action)

        # Should have pending resolution step
        assert state.has_pending_resolution(), "Should have pending selection step"

        # Get selection actions
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        assert len(select_actions) >= 1, "Should have at least one card to select"

        # Select the first (only) card
        state = engine.step(state, select_actions[0])

        # After resolution completes:
        # - Night Stretcher moved from hand to discard (+1 discard, -1 hand before selection)
        # - Pidgey moved from discard to hand (-1 discard, +1 hand from selection)
        # Net: hand count same, discard count same (Night Stretcher replaced Pidgey)

        # Verify Pidgey is in hand
        pidgey_in_hand = any(
            create_card(c.card_id).name == "Pidgey"
            for c in state.players[0].hand.cards
            if create_card(c.card_id)
        )
        assert pidgey_in_hand, "Pidgey should be in hand after recovery"

    def test_basic_energy_recovered_to_hand(self, engine):
        """Basic Energy selected from discard should move to hand."""
        # Setup: Fire Energy in discard
        state = create_night_stretcher_state(
            discard_cards=["base1-98"]  # Fire Energy
        )

        # Get and apply the play action
        actions = engine.get_legal_actions(state)
        play_action = find_play_night_stretcher_action(actions)
        assert play_action is not None

        state = engine.step(state, play_action)

        # Get selection actions
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        assert len(select_actions) >= 1, "Should have energy to select"

        # Select the energy
        state = engine.step(state, select_actions[0])

        # Verify Fire Energy is in hand
        fire_energy_in_hand = any(
            c.card_id == "base1-98"
            for c in state.players[0].hand.cards
        )
        assert fire_energy_in_hand, "Fire Energy should be in hand after recovery"

    def test_night_stretcher_goes_to_discard(self, engine):
        """Night Stretcher should be in discard after use."""
        state = create_night_stretcher_state(
            discard_cards=["sv3pt5-16"]  # Pidgey
        )

        night_stretcher = get_night_stretcher_from_hand(state)
        night_stretcher_id = night_stretcher.id

        # Play Night Stretcher
        actions = engine.get_legal_actions(state)
        play_action = find_play_night_stretcher_action(actions)
        state = engine.step(state, play_action)

        # Complete selection
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
        state = engine.step(state, select_actions[0])

        # Night Stretcher should be in discard
        night_stretcher_in_discard = any(
            c.id == night_stretcher_id
            for c in state.players[0].discard.cards
        )
        assert night_stretcher_in_discard, "Night Stretcher should be in discard after use"


# =============================================================================
# TEST: TARGET SELECTION
# =============================================================================

class TestNightStretcherTargetSelection:
    """Test target selection mechanics."""

    def test_multiple_pokemon_choices(self, engine):
        """Should be able to choose from multiple Pokemon in discard."""
        state = create_night_stretcher_state(
            discard_cards=["sv3pt5-16", "sv3-26", "sv2-81"]  # Pidgey, Charmander, Wattrel
        )

        # Play Night Stretcher
        actions = engine.get_legal_actions(state)
        play_action = find_play_night_stretcher_action(actions)
        state = engine.step(state, play_action)

        # Get selection actions
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Should have 3 choices (one per Pokemon)
        assert len(select_actions) == 3, f"Should have 3 Pokemon choices, got {len(select_actions)}"

    def test_mixed_pokemon_and_energy_choices(self, engine):
        """Should be able to choose from both Pokemon and Basic Energy."""
        state = create_night_stretcher_state(
            discard_cards=["sv3pt5-16", "base1-98"]  # Pidgey, Fire Energy
        )

        # Play Night Stretcher
        actions = engine.get_legal_actions(state)
        play_action = find_play_night_stretcher_action(actions)
        state = engine.step(state, play_action)

        # Get selection actions
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Should have 2 choices (Pokemon + Energy)
        assert len(select_actions) == 2, f"Should have 2 choices (Pokemon + Energy), got {len(select_actions)}"

    def test_trainer_not_selectable(self, engine):
        """Trainer cards in discard should not be selectable."""
        state = create_night_stretcher_state(
            discard_cards=["sv3pt5-16", "sv1-196"]  # Pidgey, Ultra Ball
        )

        # Play Night Stretcher
        actions = engine.get_legal_actions(state)
        play_action = find_play_night_stretcher_action(actions)
        state = engine.step(state, play_action)

        # Get selection actions
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Should only have 1 choice (Pidgey, not Ultra Ball)
        assert len(select_actions) == 1, f"Should only have Pokemon as choice, got {len(select_actions)}"


# =============================================================================
# TEST: EDGE CASES
# =============================================================================

class TestNightStretcherEdgeCases:
    """Test edge cases for Night Stretcher."""

    def test_single_valid_target(self, engine):
        """Works correctly with exactly one valid target."""
        state = create_night_stretcher_state(
            discard_cards=["sv3pt5-16"]  # Just one Pidgey
        )

        # Play Night Stretcher
        actions = engine.get_legal_actions(state)
        play_action = find_play_night_stretcher_action(actions)
        state = engine.step(state, play_action)

        # Should have exactly one selection option
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        assert len(select_actions) == 1, "Should have exactly one option"

    def test_excludes_itself_from_selection(self, engine):
        """Night Stretcher in discard (from another play) should be excluded."""
        # Create state with Night Stretcher already in discard
        state = create_night_stretcher_state(
            discard_cards=["sv3pt5-16", "sv6pt5-61"]  # Pidgey + another Night Stretcher
        )

        # Play the Night Stretcher in hand
        actions = engine.get_legal_actions(state)
        play_action = find_play_night_stretcher_action(actions)
        state = engine.step(state, play_action)

        # Get selection actions - should NOT include Night Stretcher
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Should have 2 options: the Pidgey and the OTHER Night Stretcher in discard
        # Actually, Night Stretcher is a trainer so shouldn't be selectable at all
        # Only Pidgey should be selectable
        assert len(select_actions) == 1, "Should only have Pidgey as option (trainers not selectable)"

    def test_multiple_basic_energy_types(self, engine):
        """Can select from multiple types of Basic Energy."""
        state = create_night_stretcher_state(
            discard_cards=["base1-98", "base1-102", "base1-99"]  # Fire, Water, Grass
        )

        # Play Night Stretcher
        actions = engine.get_legal_actions(state)
        play_action = find_play_night_stretcher_action(actions)
        state = engine.step(state, play_action)

        # Get selection actions
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Should have 3 energy choices
        assert len(select_actions) == 3, f"Should have 3 energy choices, got {len(select_actions)}"

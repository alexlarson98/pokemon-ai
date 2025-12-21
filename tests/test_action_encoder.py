"""
Tests for Action Encoder.

Verifies that actions are properly encoded with positional information
for ML/RL consumption.
"""

import pytest
from cards.factory import create_card_instance, get_card_definition
from engine import PokemonEngine
from models import (
    GameState, PlayerState, Board, GamePhase, Zone,
    Action, ActionType
)
from utils.action_encoder import (
    ActionEncoder, EncodedAction, encode_action, encode_actions,
    format_encoded_action, CardCategory, CardSubcategory
)


@pytest.fixture
def engine():
    return PokemonEngine()


def create_test_state():
    """Create a test state with cards in various positions."""
    p0_board = Board()
    p1_board = Board()

    p0 = PlayerState(player_id=0, name='Player 0', board=p0_board)
    p1 = PlayerState(player_id=1, name='Player 1', board=p1_board)

    state = GameState(players=[p0, p1])

    # Give both players active Pokemon
    p0.board.active_spot = create_card_instance('sv7-114', owner_id=0)  # Hoothoot
    p1.board.active_spot = create_card_instance('sv7-114', owner_id=1)  # Hoothoot

    # Add bench Pokemon (with turns_in_play for evolution)
    charmander_bench = create_card_instance('sv3pt5-4', owner_id=0)  # Charmander
    charmander_bench.turns_in_play = 1
    p0.board.bench.append(charmander_bench)

    # Add cards to hand
    p0.hand.add_card(create_card_instance('sv3pt5-4', owner_id=0))  # Charmander
    p0.hand.add_card(create_card_instance('base1-98', owner_id=0))  # Fire Energy
    p0.hand.add_card(create_card_instance('sv3pt5-5', owner_id=0))  # Charmeleon

    # Add cards to deck
    for _ in range(5):
        p0.deck.add_card(create_card_instance('sv7-114', owner_id=0))

    state.current_phase = GamePhase.MAIN
    state.turn_count = 2
    state.active_player_index = 0

    return state


class TestActionEncoderBasics:
    """Test basic action encoding functionality."""

    def test_encoder_requires_state(self):
        """Encoder should raise error if state not set."""
        encoder = ActionEncoder()
        action = Action(
            action_type=ActionType.END_TURN,
            player_id=0
        )
        with pytest.raises(ValueError, match="State must be set"):
            encoder.encode(action)

    def test_encode_end_turn(self, engine):
        """END_TURN action should encode correctly."""
        state = create_test_state()
        encoder = ActionEncoder()
        encoder.set_state(state)

        action = Action(
            action_type=ActionType.END_TURN,
            player_id=0
        )

        encoded = encoder.encode(action)

        assert encoded.action_type == "end_turn"
        assert encoded.source == {}  # No source card
        assert encoded.target == {}  # No target

    def test_encode_play_basic(self, engine):
        """PLAY_BASIC action should encode source from hand."""
        state = create_test_state()
        encoder = ActionEncoder()
        encoder.set_state(state)

        # Get the Charmander from hand
        charmander = state.players[0].hand.cards[0]

        action = Action(
            action_type=ActionType.PLAY_BASIC,
            player_id=0,
            card_id=charmander.id
        )

        encoded = encoder.encode(action)

        assert encoded.action_type == "play_basic"
        assert encoded.source["zone"] == "hand"
        assert encoded.source["index"] == 0
        assert encoded.source["card_category"] == "pokemon"
        assert encoded.source["card_subcategory"] == "basic"
        assert encoded.target["zone"] == "bench"

    def test_encode_attach_energy(self, engine):
        """ATTACH_ENERGY action should encode source and target."""
        state = create_test_state()
        encoder = ActionEncoder()
        encoder.set_state(state)

        # Get energy from hand and active Pokemon as target
        energy = state.players[0].hand.cards[1]  # Fire Energy at index 1
        active = state.players[0].board.active_spot

        action = Action(
            action_type=ActionType.ATTACH_ENERGY,
            player_id=0,
            card_id=energy.id,
            target_id=active.id
        )

        encoded = encoder.encode(action)

        assert encoded.action_type == "attach_energy"
        assert encoded.source["zone"] == "hand"
        assert encoded.source["index"] == 1
        assert encoded.source["card_category"] == "energy"
        assert encoded.target["zone"] == "active"
        assert encoded.target["index"] == 0


class TestActionEncoderPositions:
    """Test positional encoding of cards."""

    def test_bench_position_encoding(self, engine):
        """Cards on bench should have correct position index."""
        state = create_test_state()
        encoder = ActionEncoder()
        encoder.set_state(state)

        # Get the Charmander on bench (index 0)
        charmander_bench = state.players[0].board.bench[0]

        action = Action(
            action_type=ActionType.EVOLVE,
            player_id=0,
            card_id=state.players[0].hand.cards[2].id,  # Charmeleon
            target_id=charmander_bench.id
        )

        encoded = encoder.encode(action)

        assert encoded.target["zone"] == "bench"
        assert encoded.target["index"] == 0

    def test_hand_position_encoding(self, engine):
        """Cards in hand should have correct position index."""
        state = create_test_state()
        encoder = ActionEncoder()
        encoder.set_state(state)

        # Energy is at hand index 1
        energy = state.players[0].hand.cards[1]

        action = Action(
            action_type=ActionType.ATTACH_ENERGY,
            player_id=0,
            card_id=energy.id,
            target_id=state.players[0].board.active_spot.id
        )

        encoded = encoder.encode(action)

        assert encoded.source["zone"] == "hand"
        assert encoded.source["index"] == 1


class TestActionEncoderContext:
    """Test context encoding for complex actions."""

    def test_attack_context(self, engine):
        """Attack actions should include attack name in context."""
        state = create_test_state()
        encoder = ActionEncoder()
        encoder.set_state(state)

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=state.players[0].board.active_spot.id,
            attack_name="Wing Attack"
        )

        encoded = encoder.encode(action)

        assert encoded.action_type == "attack"
        assert encoded.context["attack_name"] == "Wing Attack"
        assert encoded.target["zone"] == "opponent_active"

    def test_ability_context(self, engine):
        """Ability actions should include ability name in context."""
        state = create_test_state()
        encoder = ActionEncoder()
        encoder.set_state(state)

        action = Action(
            action_type=ActionType.USE_ABILITY,
            player_id=0,
            card_id=state.players[0].board.active_spot.id,
            ability_name="Mach Search"
        )

        encoded = encoder.encode(action)

        assert encoded.context["ability_name"] == "Mach Search"

    def test_select_card_context(self, engine):
        """SELECT_CARD actions should include purpose and source card."""
        state = create_test_state()
        encoder = ActionEncoder()
        encoder.set_state(state)

        # Simulate Ultra Ball discard selection
        action = Action(
            action_type=ActionType.SELECT_CARD,
            player_id=0,
            card_id=state.players[0].hand.cards[0].id,
            metadata={
                "purpose": "discard_cost",
                "source_card": "Ultra Ball",
                "selection_number": 1,
                "max_selections": 2,
                "zone": "hand"
            }
        )

        encoded = encoder.encode(action)

        assert encoded.context["purpose"] == "discard_cost"
        assert encoded.context["source_card"] == "Ultra Ball"
        assert encoded.context["selection_number"] == 1
        assert encoded.context["max_selections"] == 2


class TestEncodedActionFormatting:
    """Test human-readable formatting of encoded actions."""

    def test_format_play_basic(self, engine):
        """Formatted PLAY_BASIC should be readable."""
        state = create_test_state()

        charmander = state.players[0].hand.cards[0]
        action = Action(
            action_type=ActionType.PLAY_BASIC,
            player_id=0,
            card_id=charmander.id
        )

        encoded = encode_action(action, state)
        formatted = format_encoded_action(encoded)

        assert "PLAY_BASIC" in formatted
        assert "hand[0]" in formatted
        assert "bench" in formatted

    def test_format_attack(self, engine):
        """Formatted ATTACK should show attack name."""
        state = create_test_state()

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=state.players[0].board.active_spot.id,
            attack_name="Explosive Vortex"
        )

        encoded = encode_action(action, state)
        formatted = format_encoded_action(encoded)

        assert "ATTACK" in formatted
        assert "Explosive Vortex" in formatted

    def test_format_select_card_with_context(self, engine):
        """Formatted SELECT_CARD should show context."""
        state = create_test_state()

        action = Action(
            action_type=ActionType.SELECT_CARD,
            player_id=0,
            card_id=state.players[0].hand.cards[0].id,
            metadata={
                "purpose": "discard_cost",
                "source_card": "Ultra Ball",
                "selection_number": 1,
                "max_selections": 2
            }
        )

        encoded = encode_action(action, state)
        formatted = format_encoded_action(encoded)

        assert "SELECT_CARD" in formatted
        assert "Ultra Ball" in formatted
        assert "discard_cost" in formatted
        assert "1/2" in formatted


class TestConvenienceFunctions:
    """Test convenience encode_action and encode_actions functions."""

    def test_encode_single_action(self, engine):
        """encode_action should work without creating encoder manually."""
        state = create_test_state()

        action = Action(
            action_type=ActionType.END_TURN,
            player_id=0
        )

        encoded = encode_action(action, state)

        assert isinstance(encoded, EncodedAction)
        assert encoded.action_type == "end_turn"

    def test_encode_multiple_actions(self, engine):
        """encode_actions should encode a list of actions."""
        state = create_test_state()

        actions = [
            Action(action_type=ActionType.END_TURN, player_id=0),
            Action(
                action_type=ActionType.PLAY_BASIC,
                player_id=0,
                card_id=state.players[0].hand.cards[0].id
            )
        ]

        encoded_list = encode_actions(actions, state)

        assert len(encoded_list) == 2
        assert encoded_list[0].action_type == "end_turn"
        assert encoded_list[1].action_type == "play_basic"


class TestEncodedActionSerialization:
    """Test that encoded actions can be serialized to dict."""

    def test_to_dict(self, engine):
        """EncodedAction.to_dict should produce serializable dict."""
        state = create_test_state()

        action = Action(
            action_type=ActionType.PLAY_BASIC,
            player_id=0,
            card_id=state.players[0].hand.cards[0].id
        )

        encoded = encode_action(action, state)
        d = encoded.to_dict()

        assert isinstance(d, dict)
        assert d["action_type"] == "play_basic"
        assert "source" in d
        assert "target" in d
        assert "context" in d
        assert d["source"]["zone"] == "hand"

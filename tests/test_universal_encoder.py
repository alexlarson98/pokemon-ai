"""
Tests for UniversalActionEncoder.

Verifies:
1. All ActionTypes can be encoded
2. No range overlaps
3. Edge cases (max hand, max bench)
4. Encode/decode round-trip consistency
5. Legal action mask generation
"""

import pytest
from cards.factory import create_card_instance
from engine import PokemonEngine
from models import (
    GameState, PlayerState, Board, GamePhase,
    Action, ActionType
)
from ai.encoder import (
    UniversalActionEncoder,
    get_action_space_info,
    TOTAL_ACTION_SPACE,
    MAX_HAND_SIZE,
    MAX_BENCH_SIZE,
    MAX_BOARD_SIZE,
    MAX_ATTACKS,
    MAX_ABILITIES,
    MAX_TARGETS,
    MAX_EFFECT_OPTIONS,
    OFFSET_PLAY_HAND_CARD,
    OFFSET_RETREAT,
    OFFSET_USE_ABILITY,
    OFFSET_ATTACK,
    OFFSET_TAKE_PRIZE,
    OFFSET_PROMOTE_ACTIVE,
    OFFSET_DISCARD_BENCH,
    OFFSET_END_TURN,
    OFFSET_SELECT_LIST_ITEM,
    OFFSET_SELECT_BOARD_SLOT,
    OFFSET_SELECT_EFFECT_OPTION,
    OFFSET_DECLINE_OPTIONAL,
    SIZE_SELECT_BOARD_SLOT,
    SIZE_SELECT_EFFECT_OPTION,
)


@pytest.fixture
def engine():
    return PokemonEngine()


@pytest.fixture
def encoder():
    return UniversalActionEncoder()


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
    for i in range(8):
        charmander = create_card_instance('sv3pt5-4', owner_id=0)
        charmander.turns_in_play = 1
        p0.board.bench.append(charmander)

    # Add cards to hand
    for _ in range(20):
        p0.hand.add_card(create_card_instance('sv3pt5-4', owner_id=0))  # Charmander
        p0.hand.add_card(create_card_instance('base1-98', owner_id=0))  # Fire Energy

    # Add cards to deck
    for _ in range(30):
        p0.deck.add_card(create_card_instance('sv7-114', owner_id=0))

    state.current_phase = GamePhase.MAIN
    state.turn_count = 2
    state.active_player_index = 0

    return state


class TestActionSpaceLayout:
    """Test action space structure and constants."""

    def test_action_space_size(self, encoder):
        """Encoder should have correct action space size."""
        assert encoder.action_space_size == TOTAL_ACTION_SPACE
        assert encoder.action_space_size == 1099  # Updated with new ranges

    def test_no_range_overlaps(self):
        """Action ranges should not overlap."""
        info = get_action_space_info()
        ranges = []

        for name, range_info in info['ranges'].items():
            offset = range_info['offset']
            size = range_info['size']
            end = offset + size - 1
            ranges.append((name, offset, end))

        # Sort by start offset
        ranges.sort(key=lambda x: x[1])

        # Check for overlaps
        for i in range(len(ranges) - 1):
            name1, start1, end1 = ranges[i]
            name2, start2, end2 = ranges[i + 1]
            assert end1 < start2, f"Overlap: {name1} ({start1}-{end1}) and {name2} ({start2}-{end2})"

    def test_constants_match(self, encoder):
        """Constants should be consistent."""
        assert MAX_HAND_SIZE == 60
        assert MAX_BENCH_SIZE == 8
        assert MAX_BOARD_SIZE == 9
        assert MAX_ATTACKS == 25  # Pokemon's own attacks + copied attacks + VSTAR/GX
        assert MAX_ABILITIES == 4  # Pokemon's own abilities + tool-granted abilities
        assert MAX_TARGETS == 10
        assert MAX_EFFECT_OPTIONS == 4  # Modal choices


class TestEncodeActions:
    """Test encoding various action types."""

    def test_encode_end_turn(self, encoder):
        """END_TURN should encode to fixed index."""
        state = create_test_state()
        action = Action(action_type=ActionType.END_TURN, player_id=0)

        index = encoder.encode(action, state)

        assert index == OFFSET_END_TURN

    def test_encode_play_basic(self, encoder):
        """PLAY_BASIC should encode with hand index and target."""
        state = create_test_state()
        card = state.players[0].hand.cards[0]

        action = Action(
            action_type=ActionType.PLAY_BASIC,
            player_id=0,
            card_id=card.id
        )

        index = encoder.encode(action, state)

        assert OFFSET_PLAY_HAND_CARD <= index < OFFSET_RETREAT

    def test_encode_attach_energy(self, encoder):
        """ATTACH_ENERGY should encode source and target."""
        state = create_test_state()
        # Find energy in hand
        energy = None
        for card in state.players[0].hand.cards:
            if 'base1-98' in card.card_id:
                energy = card
                break

        assert energy is not None, "Energy should be in hand"

        action = Action(
            action_type=ActionType.ATTACH_ENERGY,
            player_id=0,
            card_id=energy.id,
            target_id=state.players[0].board.active_spot.id
        )

        index = encoder.encode(action, state)

        assert OFFSET_PLAY_HAND_CARD <= index < OFFSET_RETREAT

    def test_encode_retreat(self, encoder):
        """RETREAT should encode with bench slot."""
        state = create_test_state()
        bench_pokemon = state.players[0].board.bench[0]

        action = Action(
            action_type=ActionType.RETREAT,
            player_id=0,
            target_id=bench_pokemon.id
        )

        index = encoder.encode(action, state)

        assert OFFSET_RETREAT <= index < OFFSET_USE_ABILITY

    def test_encode_attack(self, encoder):
        """ATTACK should encode with board index and attack index."""
        state = create_test_state()

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=state.players[0].board.active_spot.id,
            attack_name="Test Attack"
        )

        index = encoder.encode(action, state)

        assert OFFSET_ATTACK <= index < OFFSET_TAKE_PRIZE

    def test_encode_use_ability(self, encoder):
        """USE_ABILITY should encode with board index."""
        state = create_test_state()

        action = Action(
            action_type=ActionType.USE_ABILITY,
            player_id=0,
            card_id=state.players[0].board.active_spot.id,
            ability_name="Test Ability"
        )

        index = encoder.encode(action, state)

        assert OFFSET_USE_ABILITY <= index < OFFSET_ATTACK

    def test_encode_promote_active(self, encoder):
        """PROMOTE_ACTIVE should encode with bench slot."""
        state = create_test_state()
        bench_pokemon = state.players[0].board.bench[0]

        action = Action(
            action_type=ActionType.PROMOTE_ACTIVE,
            player_id=0,
            card_id=bench_pokemon.id
        )

        index = encoder.encode(action, state)

        assert OFFSET_PROMOTE_ACTIVE <= index < OFFSET_DISCARD_BENCH

    def test_encode_discard_bench(self, encoder):
        """DISCARD_BENCH should encode with bench slot."""
        state = create_test_state()
        bench_pokemon = state.players[0].board.bench[0]

        action = Action(
            action_type=ActionType.DISCARD_BENCH,
            player_id=0,
            card_id=bench_pokemon.id
        )

        index = encoder.encode(action, state)

        assert OFFSET_DISCARD_BENCH <= index < OFFSET_END_TURN


class TestEdgeCases:
    """Test edge cases with maximum indices."""

    def test_max_hand_index(self, encoder):
        """Hand index 59 should encode correctly."""
        state = create_test_state()

        # Fill hand to 60 cards
        while len(state.players[0].hand.cards) < 60:
            state.players[0].hand.add_card(create_card_instance('sv3pt5-4', owner_id=0))

        last_card = state.players[0].hand.cards[59]

        action = Action(
            action_type=ActionType.PLAY_BASIC,
            player_id=0,
            card_id=last_card.id
        )

        index = encoder.encode(action, state)

        # Hand index 59 * 10 targets + target slot
        assert index >= OFFSET_PLAY_HAND_CARD + (59 * MAX_TARGETS)
        assert index < OFFSET_RETREAT

    def test_max_bench_slot_retreat(self, encoder):
        """Bench slot 7 retreat should encode correctly."""
        state = create_test_state()
        bench_pokemon_7 = state.players[0].board.bench[7]

        action = Action(
            action_type=ActionType.RETREAT,
            player_id=0,
            target_id=bench_pokemon_7.id
        )

        index = encoder.encode(action, state)

        assert index == OFFSET_RETREAT + 7

    def test_max_board_index_ability(self, encoder):
        """Board index 8 (bench slot 7) ability should encode correctly."""
        state = create_test_state()
        bench_pokemon_7 = state.players[0].board.bench[7]

        action = Action(
            action_type=ActionType.USE_ABILITY,
            player_id=0,
            card_id=bench_pokemon_7.id,
            ability_name="Test"
        )

        index = encoder.encode(action, state)

        # Board index 8 * 2 abilities
        expected_min = OFFSET_USE_ABILITY + (8 * MAX_ABILITIES)
        expected_max = expected_min + MAX_ABILITIES - 1
        assert expected_min <= index <= expected_max


class TestDecodeActions:
    """Test decoding action indices."""

    def test_decode_all_indices(self, encoder):
        """All valid indices should decode without error."""
        for i in range(TOTAL_ACTION_SPACE):
            decoded = encoder.decode(i)
            assert "action_category" in decoded

    def test_decode_out_of_range(self, encoder):
        """Out-of-range indices should raise ValueError."""
        with pytest.raises(ValueError):
            encoder.decode(-1)

        with pytest.raises(ValueError):
            encoder.decode(TOTAL_ACTION_SPACE)

        with pytest.raises(ValueError):
            encoder.decode(TOTAL_ACTION_SPACE + 100)

    def test_decode_play_hand_card(self, encoder):
        """PLAY_HAND_CARD indices should decode with hand_index and target_slot."""
        decoded = encoder.decode(OFFSET_PLAY_HAND_CARD)

        assert decoded["action_category"] == "PLAY_HAND_CARD"
        assert decoded["hand_index"] == 0
        assert decoded["target_slot"] == 0

    def test_decode_retreat(self, encoder):
        """RETREAT indices should decode with bench_index."""
        decoded = encoder.decode(OFFSET_RETREAT + 5)

        assert decoded["action_category"] == "RETREAT"
        assert decoded["bench_index"] == 5

    def test_decode_attack(self, encoder):
        """ATTACK indices should decode with board_index and attack_index."""
        decoded = encoder.decode(OFFSET_ATTACK)

        assert decoded["action_category"] == "ATTACK"
        assert decoded["board_index"] == 0
        assert decoded["attack_index"] == 0


class TestLegalActionMask:
    """Test legal action mask generation."""

    def test_mask_length(self, encoder):
        """Mask should have correct length."""
        state = create_test_state()
        legal_actions = [
            Action(action_type=ActionType.END_TURN, player_id=0)
        ]

        mask = encoder.get_legal_action_mask(legal_actions, state)

        assert len(mask) == TOTAL_ACTION_SPACE

    def test_mask_marks_legal_actions(self, encoder):
        """Legal actions should be marked as 1 in mask."""
        state = create_test_state()

        legal_actions = [
            Action(action_type=ActionType.END_TURN, player_id=0),
            Action(
                action_type=ActionType.ATTACK,
                player_id=0,
                card_id=state.players[0].board.active_spot.id,
                attack_name="Test"
            ),
        ]

        mask = encoder.get_legal_action_mask(legal_actions, state)

        # Count legal actions
        assert sum(mask) == len(legal_actions)

        # Check specific indices
        for action in legal_actions:
            index = encoder.encode(action, state)
            assert mask[index] == 1

    def test_empty_actions_empty_mask(self, encoder):
        """Empty action list should produce all-zero mask."""
        state = create_test_state()

        mask = encoder.get_legal_action_mask([], state)

        assert sum(mask) == 0


class TestAllActionTypes:
    """Test that all ActionTypes can be encoded."""

    def test_all_action_types_encodable(self, encoder):
        """Every ActionType should have a valid encoding."""
        state = create_test_state()
        player = state.players[0]

        action_tests = {
            ActionType.MULLIGAN_DRAW: Action(action_type=ActionType.MULLIGAN_DRAW, player_id=0),
            ActionType.REVEAL_HAND_MULLIGAN: Action(action_type=ActionType.REVEAL_HAND_MULLIGAN, player_id=0),
            ActionType.PLACE_ACTIVE: Action(
                action_type=ActionType.PLACE_ACTIVE,
                player_id=0,
                card_id=player.hand.cards[0].id
            ),
            ActionType.PLACE_BENCH: Action(
                action_type=ActionType.PLACE_BENCH,
                player_id=0,
                card_id=player.hand.cards[0].id
            ),
            ActionType.PLAY_BASIC: Action(
                action_type=ActionType.PLAY_BASIC,
                player_id=0,
                card_id=player.hand.cards[0].id
            ),
            ActionType.EVOLVE: Action(
                action_type=ActionType.EVOLVE,
                player_id=0,
                card_id=player.hand.cards[0].id,
                target_id=player.board.bench[0].id
            ),
            ActionType.ATTACH_ENERGY: Action(
                action_type=ActionType.ATTACH_ENERGY,
                player_id=0,
                card_id=player.hand.cards[1].id,
                target_id=player.board.active_spot.id
            ),
            ActionType.PLAY_ITEM: Action(
                action_type=ActionType.PLAY_ITEM,
                player_id=0,
                card_id=player.hand.cards[0].id
            ),
            ActionType.PLAY_SUPPORTER: Action(
                action_type=ActionType.PLAY_SUPPORTER,
                player_id=0,
                card_id=player.hand.cards[0].id
            ),
            ActionType.PLAY_STADIUM: Action(
                action_type=ActionType.PLAY_STADIUM,
                player_id=0,
                card_id=player.hand.cards[0].id
            ),
            ActionType.ATTACH_TOOL: Action(
                action_type=ActionType.ATTACH_TOOL,
                player_id=0,
                card_id=player.hand.cards[0].id,
                target_id=player.board.active_spot.id
            ),
            ActionType.USE_ABILITY: Action(
                action_type=ActionType.USE_ABILITY,
                player_id=0,
                card_id=player.board.active_spot.id,
                ability_name="Test"
            ),
            ActionType.RETREAT: Action(
                action_type=ActionType.RETREAT,
                player_id=0,
                target_id=player.board.bench[0].id
            ),
            ActionType.ATTACK: Action(
                action_type=ActionType.ATTACK,
                player_id=0,
                card_id=player.board.active_spot.id,
                attack_name="Test"
            ),
            ActionType.END_TURN: Action(action_type=ActionType.END_TURN, player_id=0),
            ActionType.TAKE_PRIZE: Action(
                action_type=ActionType.TAKE_PRIZE,
                player_id=0,
                choice_index=0
            ),
            ActionType.PROMOTE_ACTIVE: Action(
                action_type=ActionType.PROMOTE_ACTIVE,
                player_id=0,
                card_id=player.board.bench[0].id
            ),
            ActionType.DISCARD_BENCH: Action(
                action_type=ActionType.DISCARD_BENCH,
                player_id=0,
                card_id=player.board.bench[0].id
            ),
            ActionType.SELECT_CARD: Action(
                action_type=ActionType.SELECT_CARD,
                player_id=0,
                card_id=player.hand.cards[0].id,
                metadata={"zone": "hand"}
            ),
            ActionType.CONFIRM_SELECTION: Action(action_type=ActionType.CONFIRM_SELECTION, player_id=0),
            ActionType.CANCEL_ACTION: Action(action_type=ActionType.CANCEL_ACTION, player_id=0),
            ActionType.COIN_FLIP: Action(action_type=ActionType.COIN_FLIP, player_id=0),
            ActionType.SHUFFLE: Action(action_type=ActionType.SHUFFLE, player_id=0),
            ActionType.SEARCH_SELECT_COUNT: Action(
                action_type=ActionType.SEARCH_SELECT_COUNT,
                player_id=0,
                choice_index=2
            ),
            ActionType.SEARCH_SELECT_CARD: Action(
                action_type=ActionType.SEARCH_SELECT_CARD,
                player_id=0,
                card_id=player.deck.cards[0].id
            ),
            ActionType.SEARCH_CONFIRM: Action(action_type=ActionType.SEARCH_CONFIRM, player_id=0),
            ActionType.INTERRUPT_ATTACH_ENERGY: Action(
                action_type=ActionType.INTERRUPT_ATTACH_ENERGY,
                player_id=0,
                card_id=player.hand.cards[1].id,
                target_id=player.board.active_spot.id
            ),
        }

        for action_type, action in action_tests.items():
            index = encoder.encode(action, state)
            assert 0 <= index < TOTAL_ACTION_SPACE, f"{action_type} encoded to invalid index {index}"


class TestNewRanges:
    """Test the new action ranges: SELECT_BOARD_SLOT, SELECT_EFFECT_OPTION, DECLINE_OPTIONAL."""

    def test_select_card_bench_uses_board_slot_range(self, encoder):
        """SELECT_CARD with zone='bench' should use SELECT_BOARD_SLOT range."""
        state = create_test_state()
        player = state.players[0]
        bench_target = player.board.bench[3]

        action = Action(
            action_type=ActionType.SELECT_CARD,
            player_id=0,
            card_id=bench_target.id,
            metadata={"zone": "bench", "purpose": "bench_target"}
        )

        index = encoder.encode(action, state)

        assert OFFSET_SELECT_BOARD_SLOT <= index < OFFSET_SELECT_BOARD_SLOT + SIZE_SELECT_BOARD_SLOT

    def test_select_card_active_uses_board_slot_range(self, encoder):
        """SELECT_CARD with zone='active' should use SELECT_BOARD_SLOT range."""
        state = create_test_state()
        player = state.players[0]

        action = Action(
            action_type=ActionType.SELECT_CARD,
            player_id=0,
            card_id=player.board.active_spot.id,
            metadata={"zone": "active", "purpose": "switch_target"}
        )

        index = encoder.encode(action, state)

        # Active = slot 0
        assert index == OFFSET_SELECT_BOARD_SLOT

    def test_select_card_deck_uses_list_item_range(self, encoder):
        """SELECT_CARD with zone='deck' should use SELECT_LIST_ITEM range."""
        state = create_test_state()
        player = state.players[0]

        action = Action(
            action_type=ActionType.SELECT_CARD,
            player_id=0,
            card_id=player.deck.cards[5].id,
            metadata={"zone": "deck", "purpose": "search_target"}
        )

        index = encoder.encode(action, state)

        assert OFFSET_SELECT_LIST_ITEM <= index < OFFSET_PLAY_HAND_CARD

    def test_decode_select_board_slot(self, encoder):
        """SELECT_BOARD_SLOT indices should decode correctly."""
        for i in range(SIZE_SELECT_BOARD_SLOT):
            idx = OFFSET_SELECT_BOARD_SLOT + i
            decoded = encoder.decode(idx)

            assert decoded["action_category"] == "SELECT_BOARD_SLOT"
            assert decoded["board_slot"] == i
            assert "slot_name" in decoded

    def test_decode_select_effect_option(self, encoder):
        """SELECT_EFFECT_OPTION indices should decode correctly."""
        for i in range(SIZE_SELECT_EFFECT_OPTION):
            idx = OFFSET_SELECT_EFFECT_OPTION + i
            decoded = encoder.decode(idx)

            assert decoded["action_category"] == "SELECT_EFFECT_OPTION"
            assert decoded["option_index"] == i

    def test_decode_decline_optional(self, encoder):
        """DECLINE_OPTIONAL should decode correctly."""
        decoded = encoder.decode(OFFSET_DECLINE_OPTIONAL)

        assert decoded["action_category"] == "DECLINE_OPTIONAL"
        assert decoded["action_type"] == "decline_optional"

    def test_decline_optional_is_last_index(self, encoder):
        """DECLINE_OPTIONAL should be the last valid index."""
        assert OFFSET_DECLINE_OPTIONAL == TOTAL_ACTION_SPACE - 1

"""
State Encoder Verification Script - Validate Comprehensive Feature Encoding.

This script tests that the StateEncoder correctly captures all game features:
1. Pokemon features (HP, energy, status, attacks, weakness/resistance)
2. Hand card encoding with type flags
3. Discard pile sequences
4. Global context (prizes, deck counts, turn flags, VSTAR/GX used)
5. Tensor shapes match expected dimensions
6. Index alignment with ActionEncoder

Run: python src/ai/verify_state.py
"""

import sys
import os
import numpy as np

script_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(script_dir)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from engine import PokemonEngine
from game_setup import build_game_state, setup_initial_board, load_deck_from_file
from models import GameState, PlayerState, Board, Zone, GamePhase, StatusCondition, EnergyType
from cards.factory import create_card_instance, get_card_definition
from ai.state_encoder import (
    StateEncoder, CardIDRegistry, EncodedState,
    encode_state, get_global_registry, set_global_registry,
    get_input_shapes, get_pokemon_feature_names, get_global_feature_names,
    MAX_HAND_SIZE, MAX_BENCH_SIZE, MAX_DISCARD_SIZE, MAX_PRIZES,
    POKEMON_FEATURES, HAND_FEATURES, GLOBAL_FEATURES, STADIUM_FEATURES,
)


def print_header(text):
    print(f"\n{'='*60}")
    print(f" {text}")
    print('='*60)


def print_result(name, passed, detail=""):
    status = "[PASS]" if passed else "[FAIL]"
    print(f"  {status} {name}: {detail}")
    return passed


class StateEncoderVerifier:
    """Verify comprehensive StateEncoder implementation."""

    def __init__(self):
        self.passed = 0
        self.failed = 0

    def verify_tensor_shapes(self) -> list:
        """Verify all tensor shapes match expected dimensions."""
        errors = []
        state = self._create_test_state()
        encoder = StateEncoder()
        encoded = encoder.encode(state)

        expected_shapes = get_input_shapes()

        for name, expected_shape in expected_shapes.items():
            actual_shape = getattr(encoded, name).shape
            if actual_shape != expected_shape:
                errors.append(f"{name}: expected {expected_shape}, got {actual_shape}")

        return errors

    def verify_pokemon_hp_features(self) -> list:
        """Verify HP ratio, damage counters, and max HP encoding."""
        errors = []
        state = self._create_test_state()

        # Add damage to active
        active = state.players[0].board.active_spot
        active.damage_counters = 5  # 50 damage

        card_def = get_card_definition(active)
        max_hp = card_def.hp if card_def else 60

        encoder = StateEncoder()
        encoded = encoder.encode(state)

        features = encoded.my_active[0]

        # HP ratio (index 1)
        expected_ratio = (max_hp - 50) / max_hp
        if abs(features[1] - expected_ratio) > 0.01:
            errors.append(f"HP ratio: expected {expected_ratio:.3f}, got {features[1]:.3f}")

        # Damage counters (index 2) - normalized by 34
        expected_damage = 5 / 34.0
        if abs(features[2] - expected_damage) > 0.01:
            errors.append(f"Damage counters: expected {expected_damage:.3f}, got {features[2]:.3f}")

        # Max HP (index 3) - normalized by 340
        expected_max_hp = max_hp / 340.0
        if abs(features[3] - expected_max_hp) > 0.01:
            errors.append(f"Max HP: expected {expected_max_hp:.3f}, got {features[3]:.3f}")

        return errors

    def verify_energy_counts(self) -> list:
        """Verify energy counts by type are encoded correctly."""
        errors = []
        state = self._create_test_state()

        # Add fire energy to active
        active = state.players[0].board.active_spot
        for _ in range(3):
            energy = create_card_instance('base1-98', owner_id=0)  # Fire Energy
            active.attached_energy.append(energy)

        encoder = StateEncoder()
        encoded = encoder.encode(state)

        features = encoded.my_active[0]

        # Fire energy is at index 4+1 = 5 (FIRE is second in ENERGY_TYPES: GRASS, FIRE, ...)
        expected_fire = 3 / 8.0  # Normalized by MAX_ENERGY_ATTACHED
        if abs(features[5] - expected_fire) > 0.01:
            errors.append(f"Fire energy: expected {expected_fire:.3f}, got {features[5]:.3f}")

        # Total energy (index 13 with 9 energy types)
        expected_total = 3 / 8.0
        if abs(features[13] - expected_total) > 0.01:
            errors.append(f"Total energy: expected {expected_total:.3f}, got {features[13]:.3f}")

        return errors

    def verify_status_conditions(self) -> list:
        """Verify status conditions are correctly one-hot encoded."""
        errors = []
        state = self._create_test_state()

        active = state.players[0].board.active_spot
        active.status_conditions.add(StatusCondition.BURNED)
        active.status_conditions.add(StatusCondition.POISONED)

        encoder = StateEncoder()
        encoded = encoder.encode(state)

        features = encoded.my_active[0]

        # Status indices (with 9 energy types): 15=asleep, 16=burned, 17=confused, 18=paralyzed, 19=poisoned
        if features[15] != 0.0:
            errors.append(f"ASLEEP should be 0, got {features[15]}")
        if features[16] != 1.0:
            errors.append(f"BURNED should be 1, got {features[16]}")
        if features[17] != 0.0:
            errors.append(f"CONFUSED should be 0, got {features[17]}")
        if features[18] != 0.0:
            errors.append(f"PARALYZED should be 0, got {features[18]}")
        if features[19] != 1.0:
            errors.append(f"POISONED should be 1, got {features[19]}")

        return errors

    def verify_hand_card_types(self) -> list:
        """Verify hand cards have correct type flags."""
        errors = []
        state = self._create_test_state()

        p0 = state.players[0]
        p0.hand.cards.clear()
        p0.hand.add_card(create_card_instance('sv3pt5-4', owner_id=0))   # Charmander (Basic Pokemon)
        p0.hand.add_card(create_card_instance('base1-98', owner_id=0))   # Fire Energy
        p0.hand.add_card(create_card_instance('sv3pt5-5', owner_id=0))   # Charmeleon (Stage 1)

        encoder = StateEncoder()
        encoded = encoder.encode(state)

        # Card 0: Charmander (Basic Pokemon)
        if encoded.my_hand[0, 1] != 1.0:  # is_pokemon
            errors.append("Charmander should have is_pokemon=1")
        if encoded.my_hand[0, 2] != 1.0:  # is_basic
            errors.append("Charmander should have is_basic=1")
        if encoded.my_hand[0, 3] != 0.0:  # is_evolution
            errors.append("Charmander should have is_evolution=0")

        # Card 1: Fire Energy
        if encoded.my_hand[1, 9] != 1.0:  # is_energy
            errors.append("Fire Energy should have is_energy=1")
        if encoded.my_hand[1, 10] != 1.0:  # is_basic_energy
            errors.append("Fire Energy should have is_basic_energy=1")

        # Card 2: Charmeleon (Stage 1)
        if encoded.my_hand[2, 1] != 1.0:  # is_pokemon
            errors.append("Charmeleon should have is_pokemon=1")
        if encoded.my_hand[2, 3] != 1.0:  # is_evolution
            errors.append("Charmeleon should have is_evolution=1")

        return errors

    def verify_discard_sequence(self) -> list:
        """Verify discard pile is encoded as card ID sequence."""
        errors = []
        state = self._create_test_state()

        p0 = state.players[0]
        p0.discard.add_card(create_card_instance('sv3pt5-4', owner_id=0))
        p0.discard.add_card(create_card_instance('base1-98', owner_id=0))

        encoder = StateEncoder()
        encoded = encoder.encode(state)

        # First two discard slots should have non-zero IDs
        if encoded.my_discard[0] <= 0:
            errors.append("Discard[0] should have non-zero card ID")
        if encoded.my_discard[1] <= 0:
            errors.append("Discard[1] should have non-zero card ID")
        if encoded.my_discard[2] != 0:
            errors.append("Discard[2] should be 0 (empty)")

        return errors

    def verify_global_context_flags(self) -> list:
        """Verify global context flags (VSTAR used, supporter played, etc.)."""
        errors = []
        state = self._create_test_state()

        state.turn_count = 5
        state.players[0].supporter_played_this_turn = True
        state.players[0].energy_attached_this_turn = True
        state.players[0].vstar_power_used = True
        state.players[1].gx_attack_used = True

        encoder = StateEncoder()
        encoded = encoder.encode(state)

        ctx = encoded.global_context

        # Turn number (index 0)
        expected_turn = 5 / 100.0
        if abs(ctx[0] - expected_turn) > 0.01:
            errors.append(f"Turn number: expected {expected_turn}, got {ctx[0]}")

        # is_first_turn (index 1)
        if ctx[1] != 0.0:
            errors.append(f"is_first_turn should be 0 for turn 5, got {ctx[1]}")

        # supporter_played (index 14)
        if ctx[14] != 1.0:
            errors.append(f"supporter_played should be 1, got {ctx[14]}")

        # energy_attached (index 15)
        if ctx[15] != 1.0:
            errors.append(f"energy_attached should be 1, got {ctx[15]}")

        # my_vstar_used (index 17)
        if ctx[17] != 1.0:
            errors.append(f"my_vstar_used should be 1, got {ctx[17]}")

        # opp_gx_used (index 20)
        if ctx[20] != 1.0:
            errors.append(f"opp_gx_used should be 1, got {ctx[20]}")

        return errors

    def verify_prizes_and_deck_counts(self) -> list:
        """Verify prize and deck count encoding."""
        errors = []
        state = self._create_test_state()

        encoder = StateEncoder()
        encoded = encoder.encode(state)

        ctx = encoded.global_context

        # Prizes remaining (indices 2-3)
        expected_my_prizes = len(state.players[0].prizes.cards) / 6.0
        if abs(ctx[2] - expected_my_prizes) > 0.01:
            errors.append(f"my_prizes: expected {expected_my_prizes}, got {ctx[2]}")

        # Deck counts (indices 6-7)
        expected_my_deck = len(state.players[0].deck.cards) / 60.0
        if abs(ctx[6] - expected_my_deck) > 0.01:
            errors.append(f"my_deck: expected {expected_my_deck}, got {ctx[6]}")

        return errors

    def verify_stadium_encoding(self) -> list:
        """Verify stadium is encoded correctly."""
        errors = []
        state = self._create_test_state()

        # Add a stadium
        stadium = create_card_instance('sv4-167', owner_id=0)  # Some stadium
        state.stadium = stadium

        encoder = StateEncoder()
        encoded = encoder.encode(state)

        # Stadium card ID should be non-zero
        if encoded.stadium[0] <= 0:
            errors.append("Stadium card ID should be > 0")

        # Stadium owner should be me (1.0)
        if encoded.stadium[1] != 1.0:
            errors.append(f"Stadium owner should be 1.0 (me), got {encoded.stadium[1]}")

        # Global context has_stadium (index 21)
        if encoded.global_context[21] != 1.0:
            errors.append("has_stadium should be 1.0")

        # Global context i_own_stadium (index 22)
        if encoded.global_context[22] != 1.0:
            errors.append("i_own_stadium should be 1.0")

        return errors

    def verify_hand_index_alignment(self) -> list:
        """Verify hand indices match exactly (for ActionEncoder alignment)."""
        errors = []
        state = self._create_test_state()

        p0 = state.players[0]
        p0.hand.cards.clear()
        cards = [
            create_card_instance('sv3pt5-4', owner_id=0),   # Index 0
            create_card_instance('base1-98', owner_id=0),   # Index 1
            create_card_instance('sv3pt5-5', owner_id=0),   # Index 2
        ]
        for card in cards:
            p0.hand.add_card(card)

        encoder = StateEncoder()
        encoded = encoder.encode(state)

        # Verify each card ID matches by index
        for i, card in enumerate(cards):
            expected_id = encoder.registry.get_id(card.card_id)
            actual_id = int(encoded.my_hand[i, 0])
            if actual_id != expected_id:
                errors.append(f"Hand[{i}]: expected ID {expected_id}, got {actual_id}")

        # Remaining slots should be 0
        for i in range(len(cards), MAX_HAND_SIZE):
            if encoded.my_hand[i, 0] != 0:
                errors.append(f"Hand[{i}] should be 0, got {encoded.my_hand[i, 0]}")
                break

        return errors

    def verify_player_perspective(self) -> list:
        """Verify encoding switches correctly based on active player."""
        errors = []
        state = self._create_test_state()

        # Set player 0 as active
        state.active_player_index = 0
        encoder = StateEncoder()
        encoded_p0 = encoder.encode(state)
        p0_active_id = int(encoded_p0.my_active[0, 0])

        # Set player 1 as active
        state.active_player_index = 1
        encoded_p1 = encoder.encode(state)
        p0_as_opp_id = int(encoded_p1.opp_active[0, 0])

        if p0_active_id != p0_as_opp_id:
            errors.append(f"P0's active should become opp_active when P1 is active")

        return errors

    def verify_real_game(self) -> list:
        """Test encoding with a full game setup."""
        errors = []

        try:
            decks_dir = os.path.join(src_dir, 'decks')
            deck_path = os.path.join(decks_dir, 'charizard_ex.txt')

            deck_text = load_deck_from_file(deck_path)
            engine = PokemonEngine()

            state = build_game_state(deck_text, deck_text, random_seed=12345)
            state = setup_initial_board(state, engine)

            encoder = StateEncoder()
            encoded = encoder.encode(state)

            # Verify we got valid data
            if encoded.my_active[0, 0] <= 0:
                errors.append("Real game: my_active should have a Pokemon")

            # Hand should have cards
            hand_count = sum(1 for i in range(MAX_HAND_SIZE) if encoded.my_hand[i, 0] > 0)
            if hand_count == 0:
                errors.append("Real game: hand should have cards")

            # Prizes should be set
            if encoded.global_context[2] <= 0:
                errors.append("Real game: prizes should be set")

            # Flat vector should work
            flat = encoded.to_flat_vector()
            if len(flat) == 0:
                errors.append("Real game: flat vector should not be empty")

        except Exception as e:
            errors.append(f"Real game test failed: {e}")

        return errors

    def _create_test_state(self) -> GameState:
        """Create a test state with basic setup."""
        p0_board = Board()
        p1_board = Board()

        p0 = PlayerState(player_id=0, name='Player 0', board=p0_board)
        p1 = PlayerState(player_id=1, name='Player 1', board=p1_board)

        state = GameState(players=[p0, p1])

        p0.board.active_spot = create_card_instance('sv3pt5-4', owner_id=0)
        p1.board.active_spot = create_card_instance('sv7-114', owner_id=1)

        state.current_phase = GamePhase.MAIN
        state.turn_count = 2
        state.active_player_index = 0

        for _ in range(10):
            p0.deck.add_card(create_card_instance('sv7-114', owner_id=0))
            p1.deck.add_card(create_card_instance('sv7-114', owner_id=1))

        for _ in range(6):
            p0.prizes.add_card(create_card_instance('sv7-114', owner_id=0))
            p1.prizes.add_card(create_card_instance('sv7-114', owner_id=1))

        return state


def run_all_tests():
    print_header("COMPREHENSIVE STATE ENCODER VERIFICATION")
    print("Testing all StateEncoder features...")

    verifier = StateEncoderVerifier()
    all_passed = True

    set_global_registry(CardIDRegistry())

    tests = [
        ("Tensor Shapes", verifier.verify_tensor_shapes),
        ("Pokemon HP Features", verifier.verify_pokemon_hp_features),
        ("Energy Counts", verifier.verify_energy_counts),
        ("Status Conditions", verifier.verify_status_conditions),
        ("Hand Card Types", verifier.verify_hand_card_types),
        ("Discard Sequence", verifier.verify_discard_sequence),
        ("Global Context Flags", verifier.verify_global_context_flags),
        ("Prizes & Deck Counts", verifier.verify_prizes_and_deck_counts),
        ("Stadium Encoding", verifier.verify_stadium_encoding),
        ("Hand Index Alignment", verifier.verify_hand_index_alignment),
        ("Player Perspective", verifier.verify_player_perspective),
        ("Real Game Integration", verifier.verify_real_game),
    ]

    for i, (name, test_func) in enumerate(tests, 1):
        print_header(f"TEST {i}: {name}")
        set_global_registry(CardIDRegistry())  # Fresh registry per test
        errors = test_func()
        passed = len(errors) == 0
        all_passed &= print_result(name, passed,
                                   "All checks passed" if passed else errors[0])

    # Print feature summary
    print_header("FEATURE SUMMARY")
    shapes = get_input_shapes()
    total_features = 0
    for name, shape in shapes.items():
        size = np.prod(shape)
        total_features += size
        print(f"  {name}: {shape} = {size} features")
    print(f"\n  TOTAL: {total_features} features")

    print(f"\n  Pokemon features: {POKEMON_FEATURES}")
    print(f"  Hand features: {HAND_FEATURES}")
    print(f"  Global features: {GLOBAL_FEATURES}")

    # Summary
    print_header("SUMMARY")
    if all_passed:
        print("  [SUCCESS] All StateEncoder tests passed!")
        return 0
    else:
        print("  [FAILURE] Some tests failed")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)

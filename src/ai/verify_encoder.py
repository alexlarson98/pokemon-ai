"""
Encoder Verification Script - Self-Contained Stress Tests for UniversalActionEncoder.

This script uses MOCK infrastructure to test encoder logic in isolation,
without needing the full game engine.

Tests:
1. Semantic Aliasing Fix: SELECT_CARD with zone="active" uses SELECT_BOARD_SLOT, not SELECT_LIST_ITEM
2. Theoretical Max Check: Hand Index 59 + Bench Slot 8 encodes without crashing
3. Modal Choices: SELECT_EFFECT_OPTION range is accessible
4. Round-Trip Integrity: Every action category encodes and decodes correctly
5. Edge Cases: Maximum indices for all ranges
6. No Range Overlaps: Action ranges don't collide
"""

import sys
import os
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

# Add src to path for imports - works from any directory
script_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(script_dir)  # Go up from ai/ to src/
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from models import ActionType, Action
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
    OFFSET_CONFIRM_SELECTION,
    OFFSET_CANCEL_ACTION,
    OFFSET_MULLIGAN_DRAW,
    OFFSET_SELECT_LIST_ITEM,
    OFFSET_SELECT_BOARD_SLOT,
    OFFSET_SELECT_EFFECT_OPTION,
    OFFSET_DECLINE_OPTIONAL,
    SIZE_SELECT_BOARD_SLOT,
    SIZE_SELECT_EFFECT_OPTION,
    SIZE_SELECT_LIST_ITEM,
    SIZE_PLAY_HAND_CARD,
)


# =============================================================================
# MOCK INFRASTRUCTURE - Self-contained test objects
# =============================================================================

@dataclass
class MockCard:
    """Mock card with controllable ID for positional testing."""
    id: str
    name: str = "Mock Card"
    card_id: str = ""  # For get_card_definition compatibility

    def __post_init__(self):
        # If card_id not set, default to id
        if not self.card_id:
            self.card_id = self.id

    def __hash__(self):
        return hash(self.id)


@dataclass
class MockHand:
    """Mock hand zone with indexed card access."""
    cards: List[MockCard] = field(default_factory=list)

    def add_card(self, card: MockCard):
        self.cards.append(card)


@dataclass
class MockDeck:
    """Mock deck zone."""
    cards: List[MockCard] = field(default_factory=list)

    def add_card(self, card: MockCard):
        self.cards.append(card)


@dataclass
class MockDiscard:
    """Mock discard zone."""
    cards: List[MockCard] = field(default_factory=list)


@dataclass
class MockBoard:
    """Mock board with active spot and bench."""
    active_spot: Optional[MockCard] = None
    bench: List[MockCard] = field(default_factory=list)

    def get_all_pokemon(self) -> List[MockCard]:
        """Get all Pokemon on board (active + bench)."""
        result = []
        if self.active_spot:
            result.append(self.active_spot)
        result.extend([p for p in self.bench if p])
        return result

    def get_bench_count(self) -> int:
        """Get number of Pokemon on bench."""
        return len([p for p in self.bench if p])


@dataclass
class MockPlayer:
    """Mock player with controllable zones."""
    player_id: int
    name: str = "Mock Player"
    hand: MockHand = field(default_factory=MockHand)
    deck: MockDeck = field(default_factory=MockDeck)
    discard: MockDiscard = field(default_factory=MockDiscard)
    board: MockBoard = field(default_factory=MockBoard)


@dataclass
class MockState:
    """Mock game state for encoder testing."""
    players: List[MockPlayer] = field(default_factory=list)

    def get_player(self, player_id: int) -> MockPlayer:
        """Get player by ID."""
        return self.players[player_id]


def create_mock_state(
    hand_size: int = 10,
    bench_size: int = 5,
    deck_size: int = 30
) -> MockState:
    """
    Create a mock game state with controllable sizes.

    Card IDs are deterministic: "hand_0", "hand_1", "bench_0", etc.
    """
    # Create players
    p0 = MockPlayer(player_id=0, name="Player 0")
    p1 = MockPlayer(player_id=1, name="Player 1")

    # Set up active Pokemon
    p0.board.active_spot = MockCard(id="active_0", name="Active Pokemon")
    p1.board.active_spot = MockCard(id="active_1", name="Opponent Active")

    # Fill bench with controllable IDs
    for i in range(bench_size):
        p0.board.bench.append(MockCard(id=f"bench_{i}", name=f"Bench Pokemon {i}"))

    # Fill hand with controllable IDs
    for i in range(hand_size):
        p0.hand.add_card(MockCard(id=f"hand_{i}", name=f"Hand Card {i}"))

    # Fill deck
    for i in range(deck_size):
        p0.deck.add_card(MockCard(id=f"deck_{i}", name=f"Deck Card {i}"))

    # Fill discard
    for i in range(5):
        p0.discard.cards.append(MockCard(id=f"discard_{i}", name=f"Discard Card {i}"))

    return MockState(players=[p0, p1])


# =============================================================================
# TEST RESULTS TRACKING
# =============================================================================

class TestResults:
    """Track test results with clear pass/fail indicators."""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.details = []

    def record_pass(self, test_name: str, message: str = ""):
        self.passed += 1
        self.details.append(f"  [PASS] {test_name}: {message}")
        print(f"  [PASS] {test_name}: {message}")

    def record_fail(self, test_name: str, expected: Any, actual: Any, message: str = ""):
        self.failed += 1
        msg = f"  [FAIL] {test_name}: Expected {expected}, got {actual}. {message}"
        self.details.append(msg)
        print(msg)

    def summary(self) -> str:
        return f"{self.passed} passed, {self.failed} failed"


# =============================================================================
# TEST 1: SEMANTIC ALIASING FIX
# =============================================================================

def test_semantic_aliasing_fix(results: TestResults):
    """
    Test that SELECT_CARD with zone="active" or zone="bench" uses SELECT_BOARD_SLOT,
    NOT SELECT_LIST_ITEM. This prevents button 0 meaning both "first deck card"
    and "active Pokemon".
    """
    print("\n" + "=" * 70)
    print("TEST 1: Semantic Aliasing Fix")
    print("=" * 70)
    print("Verifying board selections don't alias with list selections...")

    encoder = UniversalActionEncoder()
    state = create_mock_state(hand_size=10, bench_size=8)

    # Test 1a: SELECT_CARD with zone="active" should use SELECT_BOARD_SLOT
    action = Action(
        action_type=ActionType.SELECT_CARD,
        player_id=0,
        card_id="active_0",
        metadata={"zone": "active", "purpose": "switch_target"}
    )

    index = encoder.encode(action, state)

    if OFFSET_SELECT_BOARD_SLOT <= index < OFFSET_SELECT_BOARD_SLOT + SIZE_SELECT_BOARD_SLOT:
        results.record_pass(
            "zone='active' -> SELECT_BOARD_SLOT",
            f"index {index} is in range [{OFFSET_SELECT_BOARD_SLOT}, {OFFSET_SELECT_BOARD_SLOT + SIZE_SELECT_BOARD_SLOT})"
        )
    else:
        results.record_fail(
            "zone='active' -> SELECT_BOARD_SLOT",
            f"[{OFFSET_SELECT_BOARD_SLOT}, {OFFSET_SELECT_BOARD_SLOT + SIZE_SELECT_BOARD_SLOT})",
            index,
            "Active slot should NOT be in SELECT_LIST_ITEM range!"
        )

    # Test 1b: Verify it's NOT in SELECT_LIST_ITEM range
    if index < OFFSET_PLAY_HAND_CARD:
        results.record_fail(
            "zone='active' NOT in SELECT_LIST_ITEM",
            "index >= OFFSET_PLAY_HAND_CARD",
            index,
            "SEMANTIC ALIASING DETECTED! Active slot encoded to list item range."
        )
    else:
        results.record_pass(
            "zone='active' NOT in SELECT_LIST_ITEM",
            f"index {index} correctly outside list item range [0, {OFFSET_PLAY_HAND_CARD})"
        )

    # Test 1c: SELECT_CARD with zone="bench" should also use SELECT_BOARD_SLOT
    action = Action(
        action_type=ActionType.SELECT_CARD,
        player_id=0,
        card_id="bench_3",
        metadata={"zone": "bench", "purpose": "bench_target"}
    )

    index = encoder.encode(action, state)

    if OFFSET_SELECT_BOARD_SLOT <= index < OFFSET_SELECT_BOARD_SLOT + SIZE_SELECT_BOARD_SLOT:
        results.record_pass(
            "zone='bench' -> SELECT_BOARD_SLOT",
            f"index {index} is in SELECT_BOARD_SLOT range"
        )
    else:
        results.record_fail(
            "zone='bench' -> SELECT_BOARD_SLOT",
            f"[{OFFSET_SELECT_BOARD_SLOT}, {OFFSET_SELECT_BOARD_SLOT + SIZE_SELECT_BOARD_SLOT})",
            index
        )

    # Test 1d: SELECT_CARD with zone="deck" should still use SELECT_LIST_ITEM
    action = Action(
        action_type=ActionType.SELECT_CARD,
        player_id=0,
        card_id="deck_5",
        metadata={"zone": "deck", "purpose": "search_target"}
    )

    index = encoder.encode(action, state)

    if OFFSET_SELECT_LIST_ITEM <= index < OFFSET_PLAY_HAND_CARD:
        results.record_pass(
            "zone='deck' -> SELECT_LIST_ITEM",
            f"index {index} correctly in list item range"
        )
    else:
        results.record_fail(
            "zone='deck' -> SELECT_LIST_ITEM",
            f"[{OFFSET_SELECT_LIST_ITEM}, {OFFSET_PLAY_HAND_CARD})",
            index
        )


# =============================================================================
# TEST 2: THEORETICAL MAXIMUM CHECK
# =============================================================================

def test_theoretical_max_check(results: TestResults):
    """
    Test that extreme edge cases (Hand Index 59, Bench Slot 8) encode
    without crashing and stay within valid range.
    """
    print("\n" + "=" * 70)
    print("TEST 2: Theoretical Maximum Check")
    print("=" * 70)
    print("Testing extreme edge cases with maximum indices...")

    encoder = UniversalActionEncoder()

    # Create state with maximum sizes
    state = create_mock_state(hand_size=60, bench_size=8)

    # Test 2a: Hand Index 59 (maximum hand position)
    action = Action(
        action_type=ActionType.PLAY_BASIC,
        player_id=0,
        card_id="hand_59"
    )

    try:
        index = encoder.encode(action, state)

        if 0 <= index < TOTAL_ACTION_SPACE:
            results.record_pass(
                "Hand Index 59",
                f"encoded to index {index}, within valid range [0, {TOTAL_ACTION_SPACE})"
            )
        else:
            results.record_fail("Hand Index 59", f"< {TOTAL_ACTION_SPACE}", index)

    except Exception as e:
        results.record_fail("Hand Index 59", "successful encoding", f"Exception: {e}")

    # Test 2b: Bench Slot 7 (max bench with Area Zero = 8 slots, index 0-7)
    action = Action(
        action_type=ActionType.RETREAT,
        player_id=0,
        target_id="bench_7"
    )

    try:
        index = encoder.encode(action, state)
        expected = OFFSET_RETREAT + 7

        if index == expected:
            results.record_pass(
                "Bench Slot 7 Retreat",
                f"encoded to expected index {expected}"
            )
        else:
            results.record_fail("Bench Slot 7 Retreat", expected, index)

    except Exception as e:
        results.record_fail("Bench Slot 7 Retreat", "successful encoding", f"Exception: {e}")

    # Test 2c: Board Index 8 (bench slot 7 for abilities - 0=active, 1-8=bench)
    action = Action(
        action_type=ActionType.USE_ABILITY,
        player_id=0,
        card_id="bench_7",
        ability_name="Test Ability"
    )

    try:
        index = encoder.encode(action, state)
        expected_min = OFFSET_USE_ABILITY + (8 * MAX_ABILITIES)
        expected_max = expected_min + MAX_ABILITIES - 1

        if expected_min <= index <= expected_max:
            results.record_pass(
                "Board Index 8 Ability",
                f"encoded to index {index}, in range [{expected_min}, {expected_max}]"
            )
        else:
            results.record_fail(
                "Board Index 8 Ability",
                f"[{expected_min}, {expected_max}]",
                index
            )

    except Exception as e:
        results.record_fail("Board Index 8 Ability", "successful encoding", f"Exception: {e}")

    # Test 2d: Attack from max board position
    action = Action(
        action_type=ActionType.ATTACK,
        player_id=0,
        card_id="bench_7",
        attack_name="Max Position Attack"
    )

    try:
        index = encoder.encode(action, state)
        expected_min = OFFSET_ATTACK + (8 * MAX_ATTACKS)
        expected_max = expected_min + MAX_ATTACKS - 1

        if expected_min <= index <= expected_max:
            results.record_pass(
                "Board Index 8 Attack",
                f"encoded to index {index}, in range [{expected_min}, {expected_max}]"
            )
        else:
            results.record_fail(
                "Board Index 8 Attack",
                f"[{expected_min}, {expected_max}]",
                index
            )

    except Exception as e:
        results.record_fail("Board Index 8 Attack", "successful encoding", f"Exception: {e}")


# =============================================================================
# TEST 3: MODAL CHOICES (SELECT_EFFECT_OPTION)
# =============================================================================

def test_modal_choices(results: TestResults):
    """
    Test that the SELECT_EFFECT_OPTION range exists and decodes correctly.
    This range is for cards like "Choose 1 of N effects".
    """
    print("\n" + "=" * 70)
    print("TEST 3: Modal Choices (SELECT_EFFECT_OPTION)")
    print("=" * 70)
    print("Verifying modal choice range is properly configured...")

    encoder = UniversalActionEncoder()

    # Test 3a: Verify range size
    if SIZE_SELECT_EFFECT_OPTION == MAX_EFFECT_OPTIONS:
        results.record_pass(
            "SELECT_EFFECT_OPTION size",
            f"size {SIZE_SELECT_EFFECT_OPTION} matches MAX_EFFECT_OPTIONS"
        )
    else:
        results.record_fail(
            "SELECT_EFFECT_OPTION size",
            MAX_EFFECT_OPTIONS,
            SIZE_SELECT_EFFECT_OPTION
        )

    # Test 3b: Decode all option indices
    all_decode_ok = True
    for i in range(SIZE_SELECT_EFFECT_OPTION):
        idx = OFFSET_SELECT_EFFECT_OPTION + i
        try:
            decoded = encoder.decode(idx)
            if decoded["action_category"] != "SELECT_EFFECT_OPTION":
                all_decode_ok = False
                results.record_fail(
                    f"Decode option {i}",
                    "SELECT_EFFECT_OPTION",
                    decoded["action_category"]
                )
            elif decoded["option_index"] != i:
                all_decode_ok = False
                results.record_fail(
                    f"Decode option {i} index",
                    i,
                    decoded["option_index"]
                )
        except Exception as e:
            all_decode_ok = False
            results.record_fail(f"Decode option {i}", "success", f"Exception: {e}")

    if all_decode_ok:
        results.record_pass(
            "All modal options decode",
            f"indices {OFFSET_SELECT_EFFECT_OPTION}-{OFFSET_SELECT_EFFECT_OPTION + SIZE_SELECT_EFFECT_OPTION - 1} decode correctly"
        )

    # Test 3c: DECLINE_OPTIONAL exists (for "fail to find" / soft pass)
    try:
        decoded = encoder.decode(OFFSET_DECLINE_OPTIONAL)
        if decoded["action_category"] == "DECLINE_OPTIONAL":
            results.record_pass(
                "DECLINE_OPTIONAL exists",
                f"index {OFFSET_DECLINE_OPTIONAL} decodes to DECLINE_OPTIONAL"
            )
        else:
            results.record_fail(
                "DECLINE_OPTIONAL exists",
                "DECLINE_OPTIONAL",
                decoded["action_category"]
            )
    except Exception as e:
        results.record_fail("DECLINE_OPTIONAL exists", "success", f"Exception: {e}")


# =============================================================================
# TEST 4: ROUND-TRIP INTEGRITY
# =============================================================================

def test_round_trip_integrity(results: TestResults):
    """
    Test encode/decode round-trip for every action category.
    Each encoded index should decode to the correct category and parameters.
    """
    print("\n" + "=" * 70)
    print("TEST 4: Round-Trip Integrity")
    print("=" * 70)
    print("Testing encode->decode consistency for all action categories...")

    encoder = UniversalActionEncoder()
    state = create_mock_state(hand_size=20, bench_size=8)

    # Define test cases for each action category
    test_cases = [
        # (Action, expected_category, description)
        (
            Action(action_type=ActionType.END_TURN, player_id=0),
            "END_TURN",
            "END_TURN"
        ),
        (
            Action(
                action_type=ActionType.PLAY_BASIC,
                player_id=0,
                card_id="hand_5"
            ),
            "PLAY_HAND_CARD",
            "PLAY_BASIC -> PLAY_HAND_CARD"
        ),
        (
            Action(
                action_type=ActionType.ATTACH_ENERGY,
                player_id=0,
                card_id="hand_3",
                target_id="active_0"
            ),
            "PLAY_HAND_CARD",
            "ATTACH_ENERGY -> PLAY_HAND_CARD"
        ),
        (
            Action(
                action_type=ActionType.RETREAT,
                player_id=0,
                target_id="bench_2"
            ),
            "RETREAT",
            "RETREAT"
        ),
        (
            Action(
                action_type=ActionType.USE_ABILITY,
                player_id=0,
                card_id="active_0",
                ability_name="Test Ability"
            ),
            "USE_ABILITY",
            "USE_ABILITY"
        ),
        (
            Action(
                action_type=ActionType.ATTACK,
                player_id=0,
                card_id="active_0",
                attack_name="Test Attack"
            ),
            "ATTACK",
            "ATTACK"
        ),
        (
            Action(
                action_type=ActionType.TAKE_PRIZE,
                player_id=0,
                choice_index=3
            ),
            "TAKE_PRIZE",
            "TAKE_PRIZE"
        ),
        (
            Action(
                action_type=ActionType.PROMOTE_ACTIVE,
                player_id=0,
                card_id="bench_1"
            ),
            "PROMOTE_ACTIVE",
            "PROMOTE_ACTIVE"
        ),
        (
            Action(
                action_type=ActionType.DISCARD_BENCH,
                player_id=0,
                card_id="bench_0"
            ),
            "DISCARD_BENCH",
            "DISCARD_BENCH"
        ),
        (
            Action(action_type=ActionType.CONFIRM_SELECTION, player_id=0),
            "CONFIRM_SELECTION",
            "CONFIRM_SELECTION"
        ),
        (
            Action(action_type=ActionType.CANCEL_ACTION, player_id=0),
            "CANCEL_ACTION",
            "CANCEL_ACTION"
        ),
        (
            Action(action_type=ActionType.MULLIGAN_DRAW, player_id=0),
            "MULLIGAN_DRAW",
            "MULLIGAN_DRAW"
        ),
        (
            Action(
                action_type=ActionType.SELECT_CARD,
                player_id=0,
                card_id="deck_10",
                metadata={"zone": "deck"}
            ),
            "SELECT_LIST_ITEM",
            "SELECT_CARD (deck) -> SELECT_LIST_ITEM"
        ),
        (
            Action(
                action_type=ActionType.SELECT_CARD,
                player_id=0,
                card_id="bench_2",
                metadata={"zone": "bench"}
            ),
            "SELECT_BOARD_SLOT",
            "SELECT_CARD (bench) -> SELECT_BOARD_SLOT"
        ),
    ]

    for action, expected_category, description in test_cases:
        try:
            index = encoder.encode(action, state)
            decoded = encoder.decode(index)

            if decoded["action_category"] == expected_category:
                results.record_pass(description, f"index {index} -> {expected_category}")
            else:
                results.record_fail(
                    description,
                    expected_category,
                    decoded["action_category"],
                    f"index={index}"
                )
        except Exception as e:
            results.record_fail(description, "success", f"Exception: {e}")


# =============================================================================
# TEST 5: NO RANGE OVERLAPS
# =============================================================================

def test_no_range_overlaps(results: TestResults):
    """
    Verify that no action ranges overlap with each other.
    """
    print("\n" + "=" * 70)
    print("TEST 5: No Range Overlaps")
    print("=" * 70)
    print("Checking for range collisions...")

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
    overlaps_found = False
    for i in range(len(ranges) - 1):
        name1, start1, end1 = ranges[i]
        name2, start2, end2 = ranges[i + 1]

        if end1 >= start2:
            overlaps_found = True
            results.record_fail(
                f"Range overlap check",
                f"{name1} ends before {name2} starts",
                f"{name1}({start1}-{end1}) overlaps {name2}({start2}-{end2})"
            )

    if not overlaps_found:
        results.record_pass(
            "No range overlaps",
            f"All {len(ranges)} ranges are non-overlapping"
        )

    # Verify contiguity (ranges are adjacent)
    gaps_found = []
    for i in range(len(ranges) - 1):
        name1, start1, end1 = ranges[i]
        name2, start2, end2 = ranges[i + 1]

        if end1 + 1 != start2:
            gaps_found.append(f"Gap between {name1}(ends {end1}) and {name2}(starts {start2})")

    if gaps_found:
        print(f"  [INFO] {len(gaps_found)} gaps found (this may be intentional):")
        for gap in gaps_found[:5]:  # Show first 5
            print(f"    - {gap}")


# =============================================================================
# TEST 6: DECODE ALL INDICES
# =============================================================================

def test_decode_all_indices(results: TestResults):
    """
    Verify every valid index can be decoded without error.
    """
    print("\n" + "=" * 70)
    print("TEST 6: Decode All Indices")
    print("=" * 70)
    print(f"Decoding all {TOTAL_ACTION_SPACE} indices...")

    encoder = UniversalActionEncoder()
    errors = []

    for i in range(TOTAL_ACTION_SPACE):
        try:
            decoded = encoder.decode(i)
            if "action_category" not in decoded:
                errors.append(f"Index {i}: missing action_category")
        except Exception as e:
            errors.append(f"Index {i}: {e}")

    if errors:
        results.record_fail(
            "Decode all indices",
            "0 errors",
            f"{len(errors)} errors"
        )
        for err in errors[:5]:
            print(f"    - {err}")
    else:
        results.record_pass(
            "Decode all indices",
            f"All {TOTAL_ACTION_SPACE} indices decode successfully"
        )

    # Test out-of-range
    try:
        encoder.decode(TOTAL_ACTION_SPACE)
        results.record_fail(
            "Out-of-range rejection",
            "ValueError",
            "No exception raised"
        )
    except ValueError:
        results.record_pass(
            "Out-of-range rejection",
            f"index {TOTAL_ACTION_SPACE} correctly raises ValueError"
        )
    except Exception as e:
        results.record_fail(
            "Out-of-range rejection",
            "ValueError",
            f"{type(e).__name__}: {e}"
        )


# =============================================================================
# TEST 7: ACTION SPACE CONSTANTS
# =============================================================================

def test_action_space_constants(results: TestResults):
    """
    Verify action space constants are correctly configured.
    """
    print("\n" + "=" * 70)
    print("TEST 7: Action Space Constants")
    print("=" * 70)
    print("Verifying design constraints...")

    encoder = UniversalActionEncoder()

    # Check encoder size matches constant
    if encoder.action_space_size == TOTAL_ACTION_SPACE:
        results.record_pass(
            "Action space size",
            f"encoder.action_space_size == TOTAL_ACTION_SPACE == {TOTAL_ACTION_SPACE}"
        )
    else:
        results.record_fail(
            "Action space size",
            TOTAL_ACTION_SPACE,
            encoder.action_space_size
        )

    # Verify DECLINE_OPTIONAL is last index
    if OFFSET_DECLINE_OPTIONAL == TOTAL_ACTION_SPACE - 1:
        results.record_pass(
            "DECLINE_OPTIONAL is last",
            f"OFFSET_DECLINE_OPTIONAL ({OFFSET_DECLINE_OPTIONAL}) == TOTAL_ACTION_SPACE - 1"
        )
    else:
        results.record_fail(
            "DECLINE_OPTIONAL is last",
            TOTAL_ACTION_SPACE - 1,
            OFFSET_DECLINE_OPTIONAL
        )

    # Verify theoretical maximums
    expected_constants = {
        "MAX_HAND_SIZE": 60,
        "MAX_BENCH_SIZE": 8,
        "MAX_BOARD_SIZE": 9,
        "MAX_TARGETS": 10,
        "MAX_EFFECT_OPTIONS": 4,
    }

    actual_constants = {
        "MAX_HAND_SIZE": MAX_HAND_SIZE,
        "MAX_BENCH_SIZE": MAX_BENCH_SIZE,
        "MAX_BOARD_SIZE": MAX_BOARD_SIZE,
        "MAX_TARGETS": MAX_TARGETS,
        "MAX_EFFECT_OPTIONS": MAX_EFFECT_OPTIONS,
    }

    all_match = True
    for name, expected in expected_constants.items():
        actual = actual_constants[name]
        if actual != expected:
            all_match = False
            results.record_fail(name, expected, actual)

    if all_match:
        results.record_pass(
            "Theoretical maximums",
            "All constants match expected values"
        )


# =============================================================================
# MAIN RUNNER
# =============================================================================

def run_all_tests():
    """Run all verification tests."""
    print("\n" + "=" * 70)
    print("UNIVERSAL ACTION ENCODER - STRESS TEST VERIFICATION")
    print("=" * 70)
    print(f"Testing encoder with {TOTAL_ACTION_SPACE} total action indices")
    print("Using MOCK infrastructure for isolated testing")

    results = TestResults()

    tests = [
        ("Semantic Aliasing Fix", test_semantic_aliasing_fix),
        ("Theoretical Max Check", test_theoretical_max_check),
        ("Modal Choices", test_modal_choices),
        ("Round-Trip Integrity", test_round_trip_integrity),
        ("No Range Overlaps", test_no_range_overlaps),
        ("Decode All Indices", test_decode_all_indices),
        ("Action Space Constants", test_action_space_constants),
    ]

    for test_name, test_func in tests:
        try:
            test_func(results)
        except Exception as e:
            print(f"\n[CRITICAL] Test '{test_name}' crashed: {e}")
            results.failed += 1

    # Final summary
    print("\n" + "=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)
    print(f"  Total: {results.summary()}")

    if results.failed == 0:
        print("\n  [SUCCESS] ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n  [FAILURE] {results.failed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)

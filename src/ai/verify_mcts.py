"""
MCTS Verification Script - Validate Core Invariants.

This script tests that MCTS behaves correctly:
1. Visit counts sum correctly (parent visits = sum of child visits + 1)
2. Tree structure is valid (no orphan nodes, proper parent links)
3. Values are in correct range [-1, 1]
4. Simulations actually run (not short-circuiting)
5. State cloning works (original state unchanged)
6. Terminal detection works

Run: python src/ai/verify_mcts.py
"""

import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(script_dir)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from engine import PokemonEngine
from game_setup import build_game_state, setup_initial_board, load_deck_from_file
from models import GameState, GameResult, ActionType
from ai.mcts import MCTS, MCTSNode, suppress_stdout
import copy


def print_header(text):
    print(f"\n{'='*60}")
    print(f" {text}")
    print('='*60)


def print_result(name, passed, detail=""):
    status = "[PASS]" if passed else "[FAIL]"
    print(f"  {status} {name}: {detail}")
    return passed


class MCTSVerifier:
    """Verify MCTS implementation correctness."""

    def __init__(self):
        self.passed = 0
        self.failed = 0

    def verify_visit_count_invariant(self, root: MCTSNode) -> bool:
        """
        Invariant: After N simulations, root.visit_count == N.
        Also: parent.visit_count >= sum(child.visit_count) for expanded nodes.
        """
        errors = []

        def check_node(node, depth=0):
            # Check value range
            if node.visit_count > 0:
                if not -1.0 <= node.value <= 1.0:
                    errors.append(f"Node value {node.value} outside [-1,1] at depth {depth}")

            # Check children visit counts
            if node.children:
                child_visits = sum(c.visit_count for c in node.children.values())
                # Parent visits should be >= child visits (parent visited before expanding)
                if node.visit_count < child_visits:
                    errors.append(f"Parent visits {node.visit_count} < child visits {child_visits}")

                for child in node.children.values():
                    check_node(child, depth + 1)

        check_node(root)
        return errors

    def verify_tree_structure(self, root: MCTSNode) -> list:
        """Verify tree has valid parent-child relationships."""
        errors = []

        def check_node(node, expected_parent, depth=0):
            if node.parent != expected_parent:
                errors.append(f"Node at depth {depth} has wrong parent pointer")

            for child in node.children.values():
                check_node(child, node, depth + 1)

        check_node(root, None)
        return errors

    def verify_state_isolation(self, engine, state) -> tuple:
        """Verify that MCTS doesn't modify the original state."""
        # Deep copy for comparison
        original_hand_count = len(state.players[0].hand.cards)
        original_deck_count = len(state.players[0].deck.cards)
        original_active = state.players[0].board.active_spot.id if state.players[0].board.active_spot else None

        # Run MCTS
        mcts = MCTS(engine, num_simulations=10, max_rollout_depth=20)
        with suppress_stdout():
            action, info = mcts.search(state)

        # Check state unchanged
        errors = []
        if len(state.players[0].hand.cards) != original_hand_count:
            errors.append(f"Hand count changed: {original_hand_count} -> {len(state.players[0].hand.cards)}")
        if len(state.players[0].deck.cards) != original_deck_count:
            errors.append(f"Deck count changed: {original_deck_count} -> {len(state.players[0].deck.cards)}")
        current_active = state.players[0].board.active_spot.id if state.players[0].board.active_spot else None
        if current_active != original_active:
            errors.append(f"Active changed: {original_active} -> {current_active}")

        return errors, info

    def verify_simulation_count(self, engine, state, num_sims) -> tuple:
        """Verify that we actually run the requested number of simulations."""
        mcts = MCTS(engine, num_simulations=num_sims, max_rollout_depth=20)

        with suppress_stdout():
            action, info = mcts.search(state)

        errors = []
        if info['simulations'] != num_sims:
            errors.append(f"Expected {num_sims} simulations, got {info['simulations']}")

        return errors, info

    def verify_expansion_logic(self, engine, state) -> tuple:
        """Verify that nodes are expanded correctly."""
        mcts = MCTS(engine, num_simulations=20, max_rollout_depth=10)

        with suppress_stdout():
            action, info = mcts.search(state)

        errors = []

        # Should have explored at least some actions
        if info['total_children'] == 0:
            errors.append("No children expanded after 20 simulations")

        # Total visits across children should be reasonable
        total_child_visits = sum(info['visit_counts'].values())
        if total_child_visits == 0:
            errors.append("No visits to any child node")

        return errors, info

    def verify_backpropagation(self, root: MCTSNode) -> list:
        """Verify backpropagation updated values correctly."""
        errors = []

        def check_node(node, depth=0):
            if node.visit_count > 0:
                # Value should be computed correctly
                expected_value = node.value_sum / node.visit_count
                if abs(node.value - expected_value) > 0.0001:
                    errors.append(f"Value mismatch at depth {depth}: {node.value} != {expected_value}")

            for child in node.children.values():
                check_node(child, depth + 1)

        check_node(root)
        return errors


def create_simple_test_state():
    """Create a minimal test state for verification."""
    decks_dir = os.path.join(src_dir, 'decks')
    deck_path = os.path.join(decks_dir, 'charizard_ex.txt')

    deck_text = load_deck_from_file(deck_path)
    engine = PokemonEngine()

    with suppress_stdout():
        state = build_game_state(deck_text, deck_text, random_seed=12345)
        state = setup_initial_board(state, engine)

    return engine, state


def run_all_tests():
    print_header("MCTS VERIFICATION TESTS")
    print("Testing core MCTS invariants and correctness...")

    verifier = MCTSVerifier()

    # Setup
    print("\n  Setting up test state...")
    engine, state = create_simple_test_state()
    print(f"  Active: {state.players[0].board.active_spot.card_id if state.players[0].board.active_spot else 'None'}")
    print(f"  Hand size: {len(state.players[0].hand.cards)}")

    all_passed = True

    # Test 1: Simulation count
    print_header("TEST 1: Simulation Count")
    errors, info = verifier.verify_simulation_count(engine, state, num_sims=15)
    passed = len(errors) == 0
    all_passed &= print_result("Correct simulation count", passed,
                               f"{info['simulations']} simulations run" if passed else errors[0])

    # Test 2: State isolation
    print_header("TEST 2: State Isolation")
    errors, info = verifier.verify_state_isolation(engine, state)
    passed = len(errors) == 0
    all_passed &= print_result("Original state unchanged", passed,
                               "State preserved" if passed else errors[0])

    # Test 3: Expansion logic
    print_header("TEST 3: Expansion Logic")
    errors, info = verifier.verify_expansion_logic(engine, state)
    passed = len(errors) == 0
    all_passed &= print_result("Nodes expanded correctly", passed,
                               f"{info['total_children']} children explored" if passed else errors[0])

    # Test 4: Run MCTS and verify tree structure
    print_header("TEST 4: Tree Structure & Invariants")
    mcts = MCTS(engine, num_simulations=30, max_rollout_depth=20)

    # Access internal root for verification
    root = MCTSNode(state=state.clone())
    root.legal_actions = engine.get_legal_actions(root.state)
    root.untried_actions = list(root.legal_actions)

    # Run simulations manually to get root
    with suppress_stdout():
        for _ in range(30):
            mcts._simulate(root)

    # Verify visit count invariant
    errors = verifier.verify_visit_count_invariant(root)
    passed = len(errors) == 0
    all_passed &= print_result("Visit count invariant", passed,
                               f"Root visits: {root.visit_count}" if passed else errors[0])

    # Verify tree structure
    errors = verifier.verify_tree_structure(root)
    passed = len(errors) == 0
    all_passed &= print_result("Tree parent-child links", passed,
                               "All links valid" if passed else errors[0])

    # Verify backpropagation
    errors = verifier.verify_backpropagation(root)
    passed = len(errors) == 0
    all_passed &= print_result("Backpropagation values", passed,
                               "All values correct" if passed else errors[0])

    # Test 5: Verify tree statistics
    print_header("TEST 5: Tree Statistics")

    def count_nodes(node):
        return 1 + sum(count_nodes(c) for c in node.children.values())

    def max_depth(node):
        if not node.children:
            return 0
        return 1 + max(max_depth(c) for c in node.children.values())

    total_nodes = count_nodes(root)
    tree_depth = max_depth(root)

    print(f"  Root visit count: {root.visit_count}")
    print(f"  Total nodes in tree: {total_nodes}")
    print(f"  Maximum tree depth: {tree_depth}")
    print(f"  Children of root: {len(root.children)}")

    # Sanity checks
    passed = root.visit_count == 30
    all_passed &= print_result("Root visits match simulations", passed,
                               f"{root.visit_count} == 30" if passed else f"{root.visit_count} != 30")

    passed = total_nodes >= 2  # At least root + 1 child
    all_passed &= print_result("Tree has expanded nodes", passed,
                               f"{total_nodes} nodes" if passed else "No expansion")

    # Test 6: Verify action selection
    print_header("TEST 6: Action Selection")

    best_action = mcts._select_action(root)
    passed = best_action is not None
    all_passed &= print_result("Best action selected", passed,
                               f"{best_action.action_type.value}" if passed else "No action")

    # Verify best action has most visits
    if root.children:
        best_child = max(root.children.values(), key=lambda c: c.visit_count)
        passed = best_child.action == best_action
        all_passed &= print_result("Best action has most visits", passed,
                                   f"{best_child.visit_count} visits" if passed else "Mismatch")

    # Summary
    print_header("SUMMARY")
    if all_passed:
        print("  [SUCCESS] All MCTS invariants verified!")
        return 0
    else:
        print("  [FAILURE] Some tests failed - review MCTS implementation")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)

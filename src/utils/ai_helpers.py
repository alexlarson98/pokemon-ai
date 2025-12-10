"""
AI Training Helpers

Utilities for MCTS and neural network training.
"""

from typing import List
from collections import Counter

from models import GameState, Action, ActionType
from engine import PokemonEngine


def print_action_space_stats(state: GameState, engine: PokemonEngine) -> None:
    """
    Print action space statistics for debugging MCTS.

    This helps verify that action deduplication is working correctly
    and the action space isn't exploding.

    Args:
        state: Current game state
        engine: Game engine

    Example Output:
        ====== Action Space Stats ======
        Total Actions: 8
        Breakdown by Type:
          ATTACH_ENERGY: 1
          PLAY_BASIC: 2
          EVOLVE: 1
          ATTACK: 2
          END_TURN: 2
        ================================
    """
    legal_actions = engine.get_legal_actions(state)

    # Count actions by type
    action_counts = Counter()
    for action in legal_actions:
        action_counts[action.action_type.value] += 1

    # Print stats
    print("=" * 60)
    print("ACTION SPACE STATS")
    print("=" * 60)
    print(f"Total Actions: {len(legal_actions)}")
    print("\nBreakdown by Type:")

    # Sort by action type name for consistent output
    for action_type, count in sorted(action_counts.items()):
        print(f"  {action_type}: {count}")

    print("=" * 60)


def get_action_space_size(state: GameState, engine: PokemonEngine) -> int:
    """
    Get the current action space size.

    Useful for tracking action space explosion during training.

    Args:
        state: Current game state
        engine: Game engine

    Returns:
        Number of legal actions
    """
    return len(engine.get_legal_actions(state))


def verify_no_duplicates(state: GameState, engine: PokemonEngine) -> bool:
    """
    Verify that there are no duplicate actions in the action space.

    This checks for action space explosion caused by multiple copies
    of the same card.

    Args:
        state: Current game state
        engine: Game engine

    Returns:
        True if no duplicates found, False otherwise

    Example:
        >>> verify_no_duplicates(state, engine)
        [WARNING] Found duplicate actions:
          ATTACH_ENERGY to target_abc123: 5 copies
        False
    """
    legal_actions = engine.get_legal_actions(state)

    # Create action signatures (type + target + card name)
    from cards.registry import create_card

    action_signatures = []
    for action in legal_actions:
        # Create a signature based on action type and targets
        if action.action_type == ActionType.ATTACH_ENERGY:
            # For energy, check if we have the same energy type to same target
            card_def = create_card(action.card_id) if hasattr(action, 'card_id') else None
            card_name = card_def.name if card_def and hasattr(card_def, 'name') else "unknown"
            sig = f"{action.action_type.value}:{card_name}->target_{action.target_id}"
        elif action.action_type == ActionType.PLAY_BASIC:
            card_def = create_card(action.card_id) if hasattr(action, 'card_id') else None
            card_name = card_def.name if card_def and hasattr(card_def, 'name') else "unknown"
            sig = f"{action.action_type.value}:{card_name}"
        elif action.action_type == ActionType.ATTACK:
            attack_name = action.attack_name if hasattr(action, 'attack_name') else "unknown"
            sig = f"{action.action_type.value}:{attack_name}"
        else:
            sig = f"{action.action_type.value}"

        action_signatures.append(sig)

    # Check for duplicates
    signature_counts = Counter(action_signatures)
    duplicates_found = False

    for sig, count in signature_counts.items():
        if count > 1:
            if not duplicates_found:
                print("\n[WARNING] Found duplicate actions:")
                duplicates_found = True
            print(f"  {sig}: {count} copies")

    if not duplicates_found:
        print("[OK] No duplicate actions found")

    return not duplicates_found

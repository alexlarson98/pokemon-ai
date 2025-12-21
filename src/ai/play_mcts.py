"""
MCTS Test Harness - Watch the AI "Think"!

This script runs a game between an MCTS agent and a Random agent,
printing the AI's thinking process and decision-making.

Usage:
    python src/ai/play_mcts.py

    # With more simulations (slower but smarter):
    python src/ai/play_mcts.py --simulations 200

    # Verbose mode (see all simulations):
    python src/ai/play_mcts.py --verbose
"""

import sys
import os
import argparse
import random
from typing import Optional

# Add src to path
script_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(script_dir)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from engine import PokemonEngine
from game_setup import build_game_state, setup_initial_board, load_deck_from_file
from models import GameState, GameResult, ActionType, GamePhase
from ai.mcts import MCTS, RandomAgent
from cards.factory import create_card


# =============================================================================
# DISPLAY UTILITIES
# =============================================================================

def print_header(text: str, char: str = '=', width: int = 70):
    """Print a formatted header."""
    print(f"\n{char * width}")
    print(f" {text}")
    print(f"{char * width}")


def print_game_state(state: GameState, turn_num: int):
    """Print a summary of the current game state."""
    p0 = state.players[0]
    p1 = state.players[1]

    print(f"\n--- Turn {turn_num} | Player {state.active_player_index}'s Turn | Phase: {state.current_phase.value} ---")

    # Player 0 (MCTS)
    p0_active = get_pokemon_display(p0.board.active_spot) if p0.board.active_spot else "None"
    p0_bench_count = len([p for p in p0.board.bench if p])
    p0_prizes = 6 - len(p0.prizes.cards)
    print(f"  MCTS Bot   | Active: {p0_active} | Bench: {p0_bench_count} | Hand: {len(p0.hand.cards)} | Prizes Taken: {p0_prizes}")

    # Player 1 (Random)
    p1_active = get_pokemon_display(p1.board.active_spot) if p1.board.active_spot else "None"
    p1_bench_count = len([p for p in p1.board.bench if p])
    p1_prizes = 6 - len(p1.prizes.cards)
    print(f"  Random Bot | Active: {p1_active} | Bench: {p1_bench_count} | Hand: {len(p1.hand.cards)} | Prizes Taken: {p1_prizes}")


def get_pokemon_display(pokemon) -> str:
    """Get display string for a Pokemon."""
    if not pokemon:
        return "None"

    card_def = create_card(pokemon.card_id)
    name = card_def.name if card_def else pokemon.card_id
    hp_lost = pokemon.damage_counters * 10
    max_hp = card_def.hp if card_def else 0
    remaining_hp = max_hp - hp_lost

    return f"{name} ({remaining_hp}/{max_hp} HP)"


def format_action(action) -> str:
    """Format an action for display."""
    if action.display_label:
        return action.display_label

    if action.action_type == ActionType.END_TURN:
        return "END TURN"
    elif action.action_type == ActionType.ATTACK:
        return f"Attack: {action.attack_name}"
    elif action.action_type == ActionType.USE_ABILITY:
        return f"Ability: {action.ability_name}"
    elif action.action_type == ActionType.PLAY_BASIC:
        card_def = create_card(get_card_id(action.card_id)) if action.card_id else None
        name = card_def.name if card_def else action.card_id
        return f"Play Basic: {name}"
    elif action.action_type == ActionType.ATTACH_ENERGY:
        return f"Attach Energy"
    elif action.action_type == ActionType.RETREAT:
        return "Retreat"
    elif action.action_type == ActionType.EVOLVE:
        return f"Evolve"
    else:
        return action.action_type.value


def get_card_id(instance_id: str) -> str:
    """Extract card_id from instance (hacky but works for display)."""
    # Instance IDs are like "card_123", card_id is like "sv3-125"
    return instance_id


def print_thinking(info: dict, action, player_name: str):
    """Print the MCTS thinking process."""
    print(f"\n  {player_name} is thinking...")
    print(f"    Simulations: {info['simulations']}")
    print(f"    Actions explored: {info['total_children']}")
    print(f"    Terminal states found: {info['terminal_states']}")
    print(f"    Avg rollout depth: {info['avg_rollout_depth']:.1f}")

    # Top actions by visit count
    sorted_actions = sorted(info['visit_counts'].items(), key=lambda x: x[1], reverse=True)[:5]
    print(f"\n    Top Actions:")
    for action_str, visits in sorted_actions:
        value = info['values'].get(action_str, 0)
        win_rate = (value + 1.0) / 2.0 * 100
        print(f"      {action_str}: {visits} visits ({win_rate:.1f}% win rate)")

    print(f"\n  --> Chose: {info['best_action_str']} (Win Rate: {info['win_rate']*100:.1f}%)")


# =============================================================================
# MAIN GAME LOOP
# =============================================================================

def play_game(
    deck1_path: str,
    deck2_path: str,
    num_simulations: int = 50,
    verbose: bool = False,
    max_turns: int = 100,
    seed: Optional[int] = None
) -> GameResult:
    """
    Play a game between MCTS agent (Player 0) and Random agent (Player 1).

    Args:
        deck1_path: Path to MCTS agent's deck
        deck2_path: Path to Random agent's deck
        num_simulations: Number of MCTS simulations per move
        verbose: Print detailed simulation info
        max_turns: Maximum turns before declaring draw
        seed: Random seed for reproducibility

    Returns:
        Game result
    """
    if seed is not None:
        random.seed(seed)

    print_header("MCTS vs Random Bot - Pokemon TCG")
    print(f"\n  MCTS Simulations per move: {num_simulations}")
    print(f"  Max turns: {max_turns}")
    if seed:
        print(f"  Random seed: {seed}")

    # Load decks
    print("\n  Loading decks...")
    deck1_text = load_deck_from_file(deck1_path)
    deck2_text = load_deck_from_file(deck2_path)

    # Initialize game
    print("  Building game state...")
    engine = PokemonEngine()
    state = build_game_state(deck1_text, deck2_text, random_seed=seed)

    # Setup phase (draw hands, set prizes, etc)
    print("  Setting up board...")
    state = setup_initial_board(state, engine)

    # Create agents
    # Reduce max_rollout_depth for faster simulations (50 actions ~= few turns)
    mcts_agent = MCTS(
        engine,
        num_simulations=num_simulations,
        max_rollout_depth=50,  # Shorter rollouts for speed
        verbose=verbose
    )
    random_agent = RandomAgent(engine)

    print_header("Game Start!")

    turn_num = 0
    action_count = 0
    max_actions = max_turns * 50  # Safety limit

    while not state.is_game_over() and action_count < max_actions:
        # Print state summary at start of each turn
        if state.current_phase == GamePhase.MAIN:
            turn_num += 1
            print_game_state(state, turn_num)

            if turn_num > max_turns:
                print("\n[!] Max turns reached - declaring draw")
                break

        # Get legal actions
        legal_actions = engine.get_legal_actions(state)

        if not legal_actions:
            print("\n[!] No legal actions available - game stuck")
            break

        # Auto-step forced actions (single legal action) silently
        if len(legal_actions) == 1:
            state = engine.step(state, legal_actions[0])
            action_count += 1
            continue

        # Select action based on current player
        current_player = state.active_player_index

        if current_player == 0:
            # MCTS agent - use MCTS for all decisions with choice
            action, info = mcts_agent.search(state)
            print_thinking(info, action, "MCTS Bot")
        else:
            # Random agent
            action = random_agent.select_action(state)
            if state.current_phase == GamePhase.MAIN:
                print(f"\n  Random Bot: {format_action(action)}")

        # Apply action
        state = engine.step(state, action)
        action_count += 1

    # Game over
    print_header("Game Over!")

    result = state.result
    if result == GameResult.PLAYER_0_WIN:
        print("  Winner: MCTS Bot!")
    elif result == GameResult.PLAYER_1_WIN:
        print("  Winner: Random Bot!")
    elif result == GameResult.DRAW:
        print("  Result: Draw!")
    else:
        print("  Result: Incomplete (max actions reached)")

    print(f"\n  Total actions: {action_count}")
    print(f"  Total turns: {turn_num}")

    # Final state
    p0 = state.players[0]
    p1 = state.players[1]
    print(f"\n  MCTS Bot prizes taken: {6 - len(p0.prizes.cards)}")
    print(f"  Random Bot prizes taken: {6 - len(p1.prizes.cards)}")

    return result


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='MCTS vs Random Bot - Pokemon TCG')
    parser.add_argument('--simulations', '-s', type=int, default=50,
                        help='Number of MCTS simulations per move (default: 50)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Print detailed simulation info')
    parser.add_argument('--max-turns', '-t', type=int, default=100,
                        help='Maximum turns before declaring draw (default: 100)')
    parser.add_argument('--seed', type=int, default=None,
                        help='Random seed for reproducibility')
    parser.add_argument('--deck1', type=str, default=None,
                        help='Path to Player 0 deck (MCTS)')
    parser.add_argument('--deck2', type=str, default=None,
                        help='Path to Player 1 deck (Random)')

    args = parser.parse_args()

    # Default decks
    decks_dir = os.path.join(src_dir, 'decks')
    deck1 = args.deck1 or os.path.join(decks_dir, 'charizard_ex.txt')
    deck2 = args.deck2 or os.path.join(decks_dir, 'charizard_ex.txt')  # Mirror match

    # Check deck files exist
    if not os.path.exists(deck1):
        print(f"Error: Deck file not found: {deck1}")
        sys.exit(1)
    if not os.path.exists(deck2):
        print(f"Error: Deck file not found: {deck2}")
        sys.exit(1)

    play_game(
        deck1_path=deck1,
        deck2_path=deck2,
        num_simulations=args.simulations,
        verbose=args.verbose,
        max_turns=args.max_turns,
        seed=args.seed
    )


if __name__ == '__main__':
    main()

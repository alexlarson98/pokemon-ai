"""
Pokémon TCG Engine - Console Game Loop

Entry point for playing Pokémon TCG in the console.
Supports Human vs Bot, Bot vs Bot, or any agent combination.

Usage:
    python src/play_console.py
    python src/play_console.py --p1 src/decks/my_deck.txt --p2 src/decks/opponent.txt

Configuration:
    Change player_1_agent and player_2_agent to switch between:
    - HumanAgent (interactive console player)
    - RandomBot (random action selection)
    - Future: MCTSAgent, RLAgent, etc.
"""

import sys
import argparse
from typing import Optional

from models import GameState, GamePhase
from engine import PokemonEngine
from agents import HumanAgent, RandomBot
from game_setup import quick_setup, load_deck_from_file


# ============================================================================
# CONFIGURATION (Easy to swap agents)
# ============================================================================

# Player 1 Configuration
PLAYER_1_AGENT = HumanAgent(name="Alex")
# PLAYER_1_AGENT = RandomBot(name="Bot1", seed=42)

# Player 2 Configuration
PLAYER_2_AGENT = RandomBot(name="Bob the Bot")
# PLAYER_2_AGENT = HumanAgent(name="Bob")

# Game Configuration
RANDOM_SEED = None  # Set to None for random games
MAX_TURNS = 200   # Prevent infinite loops
ENABLE_XRAY_LOGGING = True  # Enable X-Ray debug logging (shows all hidden info)

# Default Deck Paths
DEFAULT_DECK_1_PATH = "src/decks/chienpao_ex.txt"
# DEFAULT_DECK_1_PATH = "src/decks/gholdengo.txt"
# DEFAULT_DECK_1_PATH = "src/decks/gardevoir_jellicent.txt"
# DEFAULT_DECK_1_PATH = "src/decks/dragapult_pidgeot.txt"
DEFAULT_DECK_2_PATH = "src/decks/charizard_ex.txt"


# ============================================================================
# GAME LOOP
# ============================================================================

def play_game(
    player_1_agent,
    player_2_agent,
    state: GameState,
    engine: PokemonEngine,
    max_turns: int = 200,
    verbose: bool = True,
    xray_logger = None
) -> GameState:
    """
    Run the main game loop.

    Args:
        player_1_agent: Agent for Player 0
        player_2_agent: Agent for Player 1
        state: Initial game state (after setup)
        engine: Game engine
        max_turns: Maximum turns before draw
        verbose: Print state updates
        xray_logger: Optional X-Ray logger for debug logging

    Returns:
        Final game state
    """
    # Assign player IDs to agents
    player_1_agent.on_game_start(player_id=0)
    player_2_agent.on_game_start(player_id=1)

    turn_count = 0

    print("\n" + "=" * 70)
    print("GAME START")
    print("=" * 70)
    print(f"Player 0: {player_1_agent.name}")
    print(f"Player 1: {player_2_agent.name}")
    print("=" * 70)

    # Log initial state if X-Ray logging enabled
    if xray_logger:
        xray_logger.log_state(state)

    # Main game loop
    while not state.is_game_over() and turn_count < max_turns:
        # Get current player
        current_player_id = state.active_player_index
        current_agent = player_1_agent if current_player_id == 0 else player_2_agent

        # Get legal actions
        legal_actions = engine.get_legal_actions(state)

        if not legal_actions:
            # No legal actions - game may be over or in invalid state
            if verbose:
                print(f"\n[ERROR] No legal actions available for Player {current_player_id}")
                print(f"  Phase: {state.current_phase.value}")
                print(f"  Turn: {state.turn_count}")
                print(f"  Active Player: {state.active_player_index}")
                print(f"  Game Over: {state.is_game_over()}")
            break

        # Agent chooses action
        try:
            action = current_agent.choose_action(state, legal_actions)
        except (KeyboardInterrupt, EOFError):
            print("\n\nGame interrupted by user.")
            if xray_logger:
                xray_logger.log_game_end(None, "User interrupted")
            return state

        # X-Ray: Log action -> state transition
        if xray_logger:
            xray_logger.log_action(state.turn_count, current_agent.name, action)

        # Apply action
        state = engine.step(state, action)

        # X-Ray: Log resulting state
        if xray_logger:
            xray_logger.log_state(state)

        # Print state summary (for RandomBot)
        if not isinstance(current_agent, HumanAgent) and verbose:
            _print_action_summary(current_agent, action, state)

        # Check win conditions
        if state.is_game_over():
            break

        # Increment turn counter
        turn_count += 1

        # Safety check for infinite loops
        if turn_count >= max_turns:
            print(f"\n[WARNING] Maximum turns ({max_turns}) reached. Game ends in draw.")
            break

    # Game over
    _print_game_over(state, player_1_agent, player_2_agent)

    # X-Ray: Log game end
    if xray_logger:
        if state.winner_id is not None:
            winner_name = player_1_agent.name if state.winner_id == 0 else player_2_agent.name
            reason = f"{winner_name} wins"
        else:
            reason = "Draw or max turns reached"
        xray_logger.log_game_end(state.winner_id, reason)

    # Notify agents
    player_1_agent.on_game_end(state)
    player_2_agent.on_game_end(state)

    return state


def _print_action_summary(agent, action, state: GameState):
    """Print action summary for bot players."""
    from models import ActionType

    # Prioritize display_label for atomic actions
    # TODO: This should be the only way to access actions eventually
    if hasattr(action, 'display_label') and action.display_label:
        action_str = action.display_label
    else:
        action_str = f"{action.action_type.value}"

        if action.action_type == ActionType.ATTACK:
            attack_name = action.attack_name if hasattr(action, 'attack_name') else 'Attack'
            action_str = f"ATTACK: {attack_name}"
        elif action.action_type == ActionType.END_TURN:
            action_str = "END_TURN"

    print(f"\n[{agent.name}] {action_str}")


def _print_game_over(state: GameState, player_1_agent, player_2_agent):
    """Print game over message."""
    from models import GameResult

    print("\n" + "=" * 70)
    print("GAME OVER")
    print("=" * 70)

    if state.result != GameResult.ONGOING:
        # Determine winner
        if state.winner_id is not None:
            winner_name = player_1_agent.name if state.winner_id == 0 else player_2_agent.name
            print(f"Winner: {winner_name} (Player {state.winner_id})")
        elif state.result == GameResult.DRAW:
            print("Result: DRAW")
        else:
            # Fallback - determine from result enum
            if state.result == GameResult.PLAYER_0_WIN:
                print(f"Winner: {player_1_agent.name} (Player 0)")
            elif state.result == GameResult.PLAYER_1_WIN:
                print(f"Winner: {player_2_agent.name} (Player 1)")

        # Print prize statistics
        p0_prizes = state.players[0].prizes_taken
        p1_prizes = state.players[1].prizes_taken
        print(f"\nPrizes Taken:")
        print(f"  {player_1_agent.name}: {p0_prizes}/6")
        print(f"  {player_2_agent.name}: {p1_prizes}/6")
    else:
        print("Game ended without result.")

    print("=" * 70)


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main entry point for console game."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Pokémon TCG Engine - Console Game",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/play_console.py
  python src/play_console.py --p1 src/decks/dragapult_pidgeot.txt
  python src/play_console.py --p1 decks/my_deck.txt --p2 decks/opponent.txt
        """
    )
    parser.add_argument(
        '--p1',
        type=str,
        default=DEFAULT_DECK_1_PATH,
        help=f'Path to Player 1 deck file (default: {DEFAULT_DECK_1_PATH})'
    )
    parser.add_argument(
        '--p2',
        type=str,
        default=DEFAULT_DECK_2_PATH,
        help=f'Path to Player 2 deck file (default: {DEFAULT_DECK_2_PATH})'
    )
    parser.add_argument(
        '--seed',
        type=int,
        default=RANDOM_SEED,
        help=f'Random seed for deterministic games (default: {RANDOM_SEED})'
    )
    parser.add_argument(
        '--max-turns',
        type=int,
        default=MAX_TURNS,
        help=f'Maximum turns before draw (default: {MAX_TURNS})'
    )
    parser.add_argument(
        '--no-xray',
        action='store_true',
        help='Disable X-Ray debug logging'
    )

    args = parser.parse_args()

    print("=" * 70)
    print("POKÉMON TCG ENGINE - CONSOLE MODE")
    print("=" * 70)

    # Load decks from files
    print(f"\n[Deck Loading]")
    print(f"  Player 1: {args.p1}")
    print(f"  Player 2: {args.p2}")

    try:
        deck_1_text = load_deck_from_file(args.p1)
        deck_2_text = load_deck_from_file(args.p2)
    except FileNotFoundError as e:
        print(f"\n[ERROR] Deck file not found: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Failed to load deck: {e}")
        sys.exit(1)

    # Setup game
    print("\n[Setup] Building game state...")
    try:
        state = quick_setup(deck_1_text, deck_2_text, random_seed=args.seed)
    except Exception as e:
        print(f"\n[ERROR] Failed to setup game: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Create engine
    engine = PokemonEngine(random_seed=args.seed)

    # Initialize X-Ray logger if enabled
    xray_logger = None
    if ENABLE_XRAY_LOGGING and not args.no_xray:
        from utils import XRayLogger
        xray_logger = XRayLogger()

    # Play game
    try:
        final_state = play_game(
            PLAYER_1_AGENT,
            PLAYER_2_AGENT,
            state,
            engine,
            max_turns=args.max_turns,
            verbose=True,
            xray_logger=xray_logger
        )
    except Exception as e:
        print(f"\n[ERROR] Game crashed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n[Exit] Game session complete.")


if __name__ == "__main__":
    main()

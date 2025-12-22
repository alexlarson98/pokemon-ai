"""
Self-Play Data Generator for AlphaZero Training.

This module provides:
- GameHistory: Stores game steps and assigns value targets
- SelfPlayWorker: Plays full games (MCTS vs MCTS) and generates training data

The self-play loop:
1. Initialize game state
2. For each turn:
   - Run MCTS search to get action probabilities
   - Store (state, action_probs, player_id)
   - Sample action and apply to game
3. When game ends, assign value targets based on winner
4. Return training samples

Usage:
    from ai.self_play import SelfPlayWorker

    worker = SelfPlayWorker(engine, model, state_encoder, device='cuda')
    samples = worker.play_game()

    # samples is List[Tuple[state_dict, action_probs, value_target]]
"""

import copy
import io
import contextlib
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field

import numpy as np
import torch

# Add src to path for imports
import sys
import os
script_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(script_dir)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from models import GameState, GameResult
from ai.mcts import MCTS
from ai.state_encoder import StateEncoder
from ai.encoder import TOTAL_ACTION_SPACE


# Context manager to suppress stdout during engine operations
@contextlib.contextmanager
def suppress_stdout():
    """Temporarily suppress stdout (for clean output)."""
    # Flush any pending output before suppressing to prevent lost/reordered output
    sys.stdout.flush()
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        yield
    finally:
        sys.stdout = old_stdout


# =============================================================================
# GAME STEP - Single step in game history
# =============================================================================

@dataclass
class GameStep:
    """A single step in game history."""
    state_dict: Dict[str, np.ndarray]  # Deep copy of encoded state
    action_probs: np.ndarray           # MCTS visit count probabilities
    player_id: int                     # Which player made this move
    turn_number: int                   # Turn number when this step occurred


# =============================================================================
# GAME HISTORY - Container for game steps
# =============================================================================

class GameHistory:
    """
    Container to store the steps of a single game.

    CRITICAL: Stores deep copies of state tensors to prevent all steps
    from pointing to the final game state.
    """

    def __init__(self):
        self.steps: List[GameStep] = []
        self.is_finished: bool = False
        self.winner_id: Optional[int] = None

    def store(
        self,
        state_dict: Dict[str, np.ndarray],
        action_probs: np.ndarray,
        player_id: int,
        turn_number: int
    ) -> None:
        """
        Store a game step.

        CRITICAL: Deep copies the state_dict to prevent reference issues.

        Args:
            state_dict: Encoded state dictionary (will be deep copied)
            action_probs: MCTS action probabilities
            player_id: Which player made this move
            turn_number: Current turn number
        """
        # Deep copy the state dict - each array gets its own copy
        copied_state = {
            key: arr.copy() for key, arr in state_dict.items()
        }

        # Copy action probs too
        copied_probs = action_probs.copy()

        step = GameStep(
            state_dict=copied_state,
            action_probs=copied_probs,
            player_id=player_id,
            turn_number=turn_number
        )

        self.steps.append(step)

    def finish_game(self, winner_id: Optional[int]) -> List[Tuple[Dict[str, np.ndarray], np.ndarray, float]]:
        """
        Finalize the game and assign value targets.

        Args:
            winner_id: ID of winning player (0 or 1), or None for draw

        Returns:
            List of training samples: (state_dict, action_probs, value_target)
        """
        self.is_finished = True
        self.winner_id = winner_id

        samples = []

        for step in self.steps:

            # Calculate a "Time Penalty"
            # Example: -0.002 per turn.
            # A win at Turn 20 = 1.0 - (0.04) = 0.96
            # A win at Turn 100 = 1.0 - (0.20) = 0.80
            # The AI will fight for that extra 0.16 points by winning faster.
            penalty = step.turn_number * 0.002

            # Assign value target based on winner
            if winner_id is None:
                # Draw
                value_target = 0.0
            elif step.player_id == winner_id:
                # This player won
                value_target = 1.0 - penalty
            else:
                # This player lost
                value_target = -1.0 + penalty


            samples.append((
                step.state_dict,
                step.action_probs,
                value_target
            ))

        return samples

    def __len__(self) -> int:
        return len(self.steps)


# =============================================================================
# SELF-PLAY WORKER
# =============================================================================

class SelfPlayWorker:
    """
    Plays full games (MCTS vs MCTS) and generates training data.

    The worker:
    1. Initializes a new game
    2. Alternates between players using MCTS
    3. Stores (state, action_probs, player_id) at each step
    4. Returns training samples with value targets when game ends
    """

    def __init__(
        self,
        engine,
        model,
        state_encoder: StateEncoder,
        device: str = 'cpu',
        num_simulations: int = 100,
        c_puct: float = 1.5,
        dirichlet_alpha: float = 0.3,
        dirichlet_epsilon: float = 0.25,
        max_turns: int = 500,
        temperature_threshold: int = 30,
        high_temp: float = 1.0,
        low_temp: float = 0.1,
        verbose: bool = False
    ):
        """
        Initialize the self-play worker.

        Args:
            engine: PokemonEngine instance
            model: AlphaZeroNet instance
            state_encoder: StateEncoder instance
            device: 'cuda' or 'cpu'
            num_simulations: MCTS simulations per move
            c_puct: Exploration constant for PUCT
            dirichlet_alpha: Dirichlet noise alpha for root exploration
            dirichlet_epsilon: Weight of Dirichlet noise
            max_turns: Maximum turns before declaring draw
            temperature_threshold: Turn number to switch to low temperature
            high_temp: Temperature for early game (exploration)
            low_temp: Temperature for late game (precision)
            verbose: Print game progress
        """
        self.engine = engine
        self.model = model
        self.state_encoder = state_encoder
        self.device = device
        self.num_simulations = num_simulations
        self.c_puct = c_puct
        self.dirichlet_alpha = dirichlet_alpha
        self.dirichlet_epsilon = dirichlet_epsilon
        self.max_turns = max_turns
        self.temperature_threshold = temperature_threshold
        self.high_temp = high_temp
        self.low_temp = low_temp
        self.verbose = verbose

        # Set model to eval mode
        if self.model is not None:
            self.model.eval()

    def play_game(
        self,
        initial_state: Optional[GameState] = None
    ) -> Tuple[List[Tuple[Dict[str, np.ndarray], np.ndarray, float]], Dict[str, Any]]:
        """
        Play a full game and return training samples.

        Args:
            initial_state: Starting game state (if None, creates new game)

        Returns:
            Tuple of (samples, game_info) where:
            - samples: List of (state_dict, action_probs, value_target)
            - game_info: Dictionary with game statistics
        """
        # Initialize game state
        if initial_state is not None:
            state = initial_state
        else:
            state = self._create_new_game()

        history = GameHistory()

        # Game statistics
        game_info = {
            'turns': 0,
            'winner': None,
            'result': None,
            'samples_collected': 0,
        }

        # Main game loop
        while not state.is_game_over() and state.turn_count < self.max_turns:
            # Determine temperature based on turn number
            if state.turn_count < self.temperature_threshold:
                temperature = self.high_temp
            else:
                temperature = self.low_temp

            # Create MCTS for this turn
            # Note: For v1, we create fresh MCTS each turn (simpler/safer)
            mcts = MCTS(
                engine=self.engine,
                model=self.model,
                state_encoder=self.state_encoder,
                device=self.device,
                num_simulations=self.num_simulations,
                c_puct=self.c_puct,
                dirichlet_alpha=self.dirichlet_alpha,
                dirichlet_epsilon=self.dirichlet_epsilon,
                temperature=temperature,
                verbose=False
            )

            # Get legal actions
            legal_actions = self.engine.get_legal_actions(state)

            if not legal_actions:
                if self.verbose:
                    print(f"  Turn {state.turn_count}: No legal actions, ending game", flush=True)
                break

            # Skip storing for forced moves (only one legal action)
            if len(legal_actions) == 1:
                forced_action = legal_actions[0]
                if self.verbose:
                    # Still log forced moves for visibility
                    action_str = str(forced_action)
                    if len(action_str) > 60:
                        action_str = action_str[:57] + "..."
                    print(f"  T{state.turn_count:3d} P{state.active_player_index}: {action_str} (forced)", flush=True)

                # Just apply the forced action (suppress engine output)
                with suppress_stdout():
                    state = self.engine.step_inplace(state, forced_action)
                continue

            # Run MCTS search (already suppresses internally)
            try:
                action, action_probs, info = mcts.search(state, add_noise=True)
            except ValueError as e:
                if self.verbose:
                    print(f"  Turn {state.turn_count}: MCTS error: {e}", flush=True)
                break

            # Encode current state for storage
            encoded = self.state_encoder.encode(state)
            state_dict = encoded.to_dict()

            # Store step in history
            history.store(
                state_dict=state_dict,
                action_probs=action_probs,
                player_id=state.active_player_index,
                turn_number=state.turn_count
            )

            if self.verbose:
                action_str = info.get('best_action_str', str(action))
                # Truncate long action strings
                if len(action_str) > 60:
                    action_str = action_str[:57] + "..."
                print(f"  T{state.turn_count:3d} P{state.active_player_index}: {action_str} (wr: {info.get('win_rate', 0):.0%})", flush=True)

            # Apply action (suppress engine output)
            with suppress_stdout():
                state = self.engine.step_inplace(state, action)

        # Game ended - determine winner
        winner_id = self._get_winner(state)

        # Get game end info
        result_str = state.result.value if state.result else 'max_turns'
        p0_prizes = len(state.players[0].prizes.cards)
        p1_prizes = len(state.players[1].prizes.cards)

        if self.verbose:
            print(f"  --- Game Over ---")
            print(f"  Result: {result_str}, Winner: P{winner_id if winner_id is not None else '?'}")
            print(f"  Turns: {state.turn_count}, Prizes remaining: P0={p0_prizes}, P1={p1_prizes}")

        # Generate training samples
        samples = history.finish_game(winner_id)

        # Update game info
        game_info['turns'] = state.turn_count
        game_info['winner'] = winner_id
        game_info['result'] = result_str
        game_info['samples_collected'] = len(samples)
        game_info['p0_prizes_left'] = p0_prizes
        game_info['p1_prizes_left'] = p1_prizes

        return samples, game_info

    def _create_new_game(self) -> GameState:
        """
        Create a new game state for self-play.

        Uses the same deck for both players (mirror match).
        """
        from game_setup import build_game_state, setup_initial_board

        # Try to load a real deck
        deck_path = os.path.join(src_dir, "decks", "charizard_ex.txt")

        if os.path.exists(deck_path):
            with open(deck_path, 'r') as f:
                deck_list = f.read()
        else:
            # Fallback deck
            deck_list = """4 Charmander SV3 26
2 Charmeleon SV3 27
3 Charizard ex SV3 54
4 Arcanine ex SV3 32
4 Growlithe SV3 31
4 Nest Ball SVI 181
4 Rare Candy SVI 191
4 Professor's Research SVI 189
4 Boss's Orders PAL 172
4 Ultra Ball SVI 196
23 Fire Energy SVE 2"""

        # Build and setup game (suppress setup messages)
        with suppress_stdout():
            state = build_game_state(deck_list, deck_list)
            state = setup_initial_board(state)

        return state

    def _get_winner(self, state: GameState) -> Optional[int]:
        """
        Determine the winner from game result.

        Args:
            state: Final game state

        Returns:
            0 or 1 for winner, None for draw/ongoing
        """
        result = state.result

        if result == GameResult.PLAYER_0_WIN:
            return 0
        elif result == GameResult.PLAYER_1_WIN:
            return 1
        elif result == GameResult.DRAW:
            return None
        else:
            # Game didn't end normally (max turns, etc.)
            return None


# =============================================================================
# BATCH SELF-PLAY
# =============================================================================

def run_self_play_games(
    engine,
    model,
    state_encoder: StateEncoder,
    device: str = 'cpu',
    num_games: int = 10,
    num_simulations: int = 100,
    verbose: bool = True
) -> Tuple[List[Tuple[Dict[str, np.ndarray], np.ndarray, float]], Dict[str, Any]]:
    """
    Run multiple self-play games and collect training data.

    Args:
        engine: PokemonEngine instance
        model: AlphaZeroNet instance
        state_encoder: StateEncoder instance
        device: 'cuda' or 'cpu'
        num_games: Number of games to play
        num_simulations: MCTS simulations per move
        verbose: Print progress

    Returns:
        Tuple of (all_samples, stats) where:
        - all_samples: Combined training samples from all games
        - stats: Dictionary with aggregate statistics
    """
    worker = SelfPlayWorker(
        engine=engine,
        model=model,
        state_encoder=state_encoder,
        device=device,
        num_simulations=num_simulations,
        verbose=verbose  # Pass verbose to worker for action logging
    )

    all_samples = []
    total_turns = 0
    wins = {0: 0, 1: 0, None: 0}  # Track wins by player

    for game_idx in range(num_games):
        if verbose:
            print(f"Game {game_idx + 1}/{num_games}...", end=" ")

        samples, game_info = worker.play_game()

        all_samples.extend(samples)
        total_turns += game_info['turns']
        wins[game_info['winner']] += 1

        if verbose:
            print(f"Turns: {game_info['turns']}, "
                  f"Winner: {game_info['winner']}, "
                  f"Samples: {len(samples)}")

    stats = {
        'num_games': num_games,
        'total_samples': len(all_samples),
        'total_turns': total_turns,
        'avg_turns': total_turns / num_games if num_games > 0 else 0,
        'player_0_wins': wins[0],
        'player_1_wins': wins[1],
        'draws': wins[None],
    }

    return all_samples, stats


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    'GameHistory',
    'GameStep',
    'SelfPlayWorker',
    'run_self_play_games',
]

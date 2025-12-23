"""
Parallel Self-Play with Batched MCTS for AlphaZero Training.

This module provides GPU-efficient self-play by:
1. Running multiple games in parallel
2. Batching neural network inference across all games

Key optimization: Instead of running 75 simulations one-by-one with individual
NN calls, we batch the leaf evaluations across N trees simultaneously.

Components:
- BatchMCTS: MCTS that manages N search trees and batches NN inference
- ParallelSelfPlayWorker: Manages N concurrent games

Usage:
    worker = ParallelSelfPlayWorker(
        engine=engine,
        model=model,
        state_encoder=encoder,
        device='cuda',
        num_parallel_games=16
    )
    samples, stats = worker.play_batch()
"""

import math
import io
import contextlib
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field

import torch
import torch.nn.functional as F
import numpy as np

import sys
import os
script_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(script_dir)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from models import GameState, Action, GameResult
from ai.encoder import UniversalActionEncoder, TOTAL_ACTION_SPACE
from ai.state_encoder import StateEncoder
from ai.self_play import GameHistory, suppress_stdout
from fast_clone import fast_clone_game_state


# =============================================================================
# MCTS NODE (reused structure)
# =============================================================================

@dataclass
class MCTSNode:
    """A node in the MCTS search tree."""
    state: GameState
    parent: Optional['MCTSNode'] = None
    action: Optional[Action] = None
    action_index: int = -1
    prior: float = 0.0
    visit_count: int = 0
    value_sum: float = 0.0
    children: Dict[int, 'MCTSNode'] = field(default_factory=dict)
    player_id: int = 0
    legal_actions: List[Action] = field(default_factory=list)
    is_expanded: bool = False

    def __post_init__(self):
        self.player_id = self.state.active_player_index

    @property
    def value(self) -> float:
        if self.visit_count == 0:
            return 0.0
        return self.value_sum / self.visit_count

    def is_terminal(self) -> bool:
        return self.state.is_game_over()


# =============================================================================
# BATCH MCTS - The Core Innovation
# =============================================================================

class BatchMCTS:
    """
    MCTS that manages multiple search trees and batches neural network inference.

    Instead of evaluating one state at a time, we:
    1. Select leaf nodes from ALL N trees
    2. Batch encode all N leaf states into one tensor
    3. Run ONE batched neural network inference
    4. Expand and backpropagate each tree with its respective results
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
        temperature: float = 1.0,
    ):
        self.engine = engine
        self.model = model
        self.state_encoder = state_encoder
        self.device = device
        self.num_simulations = num_simulations
        self.c_puct = c_puct
        self.dirichlet_alpha = dirichlet_alpha
        self.dirichlet_epsilon = dirichlet_epsilon
        self.temperature = temperature

        self.encoder = UniversalActionEncoder()

        if self.model is not None:
            self.model.eval()

    def search_batch(
        self,
        states: List[GameState],
        add_noise: bool = True
    ) -> List[Tuple[Action, np.ndarray, Dict[str, Any]]]:
        """
        Run MCTS on multiple game states simultaneously with batched NN inference.

        Args:
            states: List of N game states to search from
            add_noise: Whether to add Dirichlet noise at roots

        Returns:
            List of N tuples: (selected_action, action_probs, info_dict)
        """
        n_trees = len(states)
        if n_trees == 0:
            return []

        # Create root nodes for all trees
        roots: List[MCTSNode] = []
        for state in states:
            root = MCTSNode(state=fast_clone_game_state(state))
            root.legal_actions = self.engine.get_legal_actions(root.state)
            roots.append(root)

        # Batch expand all roots with noise
        self._batch_expand_nodes(roots, add_noise=add_noise)

        # Run simulations
        for sim_idx in range(self.num_simulations):
            # Selection: traverse each tree to find a leaf
            leaves: List[MCTSNode] = []
            for root in roots:
                leaf = self._select_to_leaf(root)
                leaves.append(leaf)

            # Separate terminal from non-terminal leaves
            terminal_indices = []
            expand_indices = []
            expand_leaves = []

            for i, leaf in enumerate(leaves):
                if leaf.is_terminal():
                    terminal_indices.append(i)
                else:
                    expand_indices.append(i)
                    expand_leaves.append(leaf)

            # Handle terminal leaves (no NN needed)
            terminal_values = []
            for i in terminal_indices:
                value = self._get_terminal_value(leaves[i])
                terminal_values.append(value)

            # Batch expand non-terminal leaves
            if expand_leaves:
                expand_values = self._batch_expand_nodes(expand_leaves, add_noise=False)
            else:
                expand_values = []

            # Backpropagate all
            for idx, ti in enumerate(terminal_indices):
                self._backpropagate(leaves[ti], terminal_values[idx])

            for idx, ei in enumerate(expand_indices):
                self._backpropagate(leaves[ei], expand_values[idx])

        # Extract results for each tree
        results = []
        for root in roots:
            action_probs = self._get_action_probabilities(root)
            selected_action, selected_idx = self._select_action(root, action_probs)
            info = self._gather_info(root, selected_action, selected_idx)
            results.append((selected_action, action_probs, info))

        return results

    def _select_to_leaf(self, root: MCTSNode) -> MCTSNode:
        """Traverse tree using PUCT until we find a leaf (unexpanded or terminal)."""
        node = root
        while node.is_expanded and not node.is_terminal():
            node = self._select_child(node)
        return node

    def _select_child(self, node: MCTSNode) -> MCTSNode:
        """Select best child using PUCT formula."""
        best_score = float('-inf')
        best_child = None

        sqrt_parent_visits = math.sqrt(node.visit_count)

        for child in node.children.values():
            if child.player_id != node.player_id:
                q_value = -child.value
            else:
                q_value = child.value

            exploration = self.c_puct * child.prior * sqrt_parent_visits / (1 + child.visit_count)
            score = q_value + exploration

            if score > best_score:
                best_score = score
                best_child = child

        return best_child

    def _batch_expand_nodes(
        self,
        nodes: List[MCTSNode],
        add_noise: bool = False
    ) -> List[float]:
        """
        Batch expand multiple nodes using a single batched NN inference.

        Args:
            nodes: List of nodes to expand
            add_noise: Whether to add Dirichlet noise

        Returns:
            List of value estimates for each node
        """
        if not nodes:
            return []

        # Filter out already expanded or terminal nodes
        to_expand = []
        expand_indices = []
        for i, node in enumerate(nodes):
            if not node.is_expanded and not node.is_terminal():
                if not node.legal_actions:
                    node.legal_actions = self.engine.get_legal_actions(node.state)
                if node.legal_actions:  # Only expand if there are legal actions
                    to_expand.append(node)
                    expand_indices.append(i)

        if not to_expand:
            return [0.0] * len(nodes)

        # Batch encode all states
        policy_batch, value_batch = self._batch_evaluate(to_expand)

        # Expand each node with its policy/value
        values = [0.0] * len(nodes)
        for idx, (node_idx, node) in enumerate(zip(expand_indices, to_expand)):
            policy = policy_batch[idx]
            value = value_batch[idx]

            self._expand_single_node(node, policy, add_noise=add_noise)
            values[node_idx] = value

        return values

    def _batch_evaluate(
        self,
        nodes: List[MCTSNode]
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Batch neural network evaluation.

        Args:
            nodes: List of nodes to evaluate

        Returns:
            (policies, values) where:
            - policies: (N, TOTAL_ACTION_SPACE) numpy array
            - values: (N,) numpy array
        """
        if self.model is None or self.state_encoder is None:
            # Fallback to uniform
            n = len(nodes)
            policies = np.ones((n, TOTAL_ACTION_SPACE)) / TOTAL_ACTION_SPACE
            values = np.zeros(n)
            return policies, values

        # Encode all states
        batch_dict = {}
        for i, node in enumerate(nodes):
            encoded = self.state_encoder.encode(node.state)
            state_dict = encoded.to_dict()

            if i == 0:
                # Initialize batch arrays
                for key, arr in state_dict.items():
                    batch_dict[key] = [arr]
            else:
                for key, arr in state_dict.items():
                    batch_dict[key].append(arr)

        # Stack into batched tensors
        tensor_dict = {}
        for key, arr_list in batch_dict.items():
            stacked = np.stack(arr_list, axis=0)
            tensor = torch.from_numpy(stacked).to(self.device)
            tensor_dict[key] = tensor

        # Run batched inference
        with torch.no_grad():
            policy_logits, values = self.model(tensor_dict)

        # Convert to numpy
        policies = F.softmax(policy_logits, dim=-1).cpu().numpy()
        values = values.squeeze(-1).cpu().numpy()

        return policies, values

    def _expand_single_node(
        self,
        node: MCTSNode,
        policy: np.ndarray,
        add_noise: bool = False
    ) -> None:
        """Expand a single node using pre-computed policy."""
        if node.is_terminal() or node.is_expanded:
            return

        if not node.legal_actions:
            node.legal_actions = self.engine.get_legal_actions(node.state)

        if not node.legal_actions:
            return

        # Extract priors for legal actions
        legal_priors = {}
        prior_sum = 0.0

        for action in node.legal_actions:
            try:
                action_index = self.encoder.encode(action, node.state)
                prior = policy[action_index]
                legal_priors[action_index] = (action, prior)
                prior_sum += prior
            except ValueError:
                action_index = hash(str(action)) % TOTAL_ACTION_SPACE
                legal_priors[action_index] = (action, 1.0 / len(node.legal_actions))
                prior_sum += 1.0 / len(node.legal_actions)

        # Normalize
        if prior_sum > 0:
            for idx in legal_priors:
                action, prior = legal_priors[idx]
                legal_priors[idx] = (action, prior / prior_sum)

        # Add Dirichlet noise
        if add_noise and len(legal_priors) > 0:
            noise = np.random.dirichlet([self.dirichlet_alpha] * len(legal_priors))
            for i, idx in enumerate(legal_priors.keys()):
                action, prior = legal_priors[idx]
                noisy_prior = (1 - self.dirichlet_epsilon) * prior + self.dirichlet_epsilon * noise[i]
                legal_priors[idx] = (action, noisy_prior)

        # Create children
        for action_index, (action, prior) in legal_priors.items():
            new_state = self.engine.step(node.state, action)
            new_state = self._auto_step_forced(new_state)

            child = MCTSNode(
                state=new_state,
                parent=node,
                action=action,
                action_index=action_index,
                prior=prior,
            )
            child.legal_actions = self.engine.get_legal_actions(child.state)
            node.children[action_index] = child

        node.is_expanded = True

    def _auto_step_forced(self, state: GameState, max_steps: int = 100) -> GameState:
        """Auto-step through forced actions."""
        steps = 0
        while not state.is_game_over() and steps < max_steps:
            legal_actions = self.engine.get_legal_actions(state)
            if not legal_actions or len(legal_actions) > 1:
                break
            state = self.engine.step_inplace(state, legal_actions[0])
            steps += 1
        return state

    def _get_terminal_value(self, node: MCTSNode) -> float:
        """Get value of terminal state from node's player perspective."""
        result = node.state.result
        player_id = node.player_id

        if result == GameResult.PLAYER_0_WIN:
            return 1.0 if player_id == 0 else -1.0
        elif result == GameResult.PLAYER_1_WIN:
            return 1.0 if player_id == 1 else -1.0
        return 0.0

    def _backpropagate(self, node: MCTSNode, value: float) -> None:
        """Backpropagate value up the tree."""
        leaf_player = node.player_id

        while node is not None:
            node.visit_count += 1
            if node.player_id == leaf_player:
                node.value_sum += value
            else:
                node.value_sum -= value
            node = node.parent

    def _get_action_probabilities(self, root: MCTSNode) -> np.ndarray:
        """Get action probabilities from visit counts."""
        probs = np.zeros(TOTAL_ACTION_SPACE, dtype=np.float32)
        total_visits = sum(child.visit_count for child in root.children.values())

        if total_visits == 0:
            for child in root.children.values():
                probs[child.action_index] = 1.0 / len(root.children)
            return probs

        if self.temperature == 0:
            best_child = max(root.children.values(), key=lambda c: c.visit_count)
            probs[best_child.action_index] = 1.0
        else:
            for child in root.children.values():
                visit_prob = child.visit_count / total_visits
                if self.temperature != 1.0:
                    visit_prob = visit_prob ** (1.0 / self.temperature)
                probs[child.action_index] = visit_prob

            prob_sum = probs.sum()
            if prob_sum > 0:
                probs /= prob_sum

        return probs

    def _select_action(
        self,
        root: MCTSNode,
        action_probs: np.ndarray
    ) -> Tuple[Action, int]:
        """Select action based on temperature."""
        if self.temperature == 0:
            best_child = max(root.children.values(), key=lambda c: c.visit_count)
            return best_child.action, best_child.action_index
        else:
            action_indices = list(root.children.keys())
            probs = np.array([action_probs[idx] for idx in action_indices])

            prob_sum = probs.sum()
            if prob_sum > 0:
                probs = probs / prob_sum
            else:
                probs = np.ones(len(probs)) / len(probs)

            chosen_idx = np.random.choice(len(action_indices), p=probs)
            chosen_action_index = action_indices[chosen_idx]

            return root.children[chosen_action_index].action, chosen_action_index

    def _gather_info(
        self,
        root: MCTSNode,
        selected_action: Action,
        selected_action_index: int
    ) -> Dict[str, Any]:
        """Gather search statistics."""
        selected_child = root.children.get(selected_action_index)

        if selected_child:
            if selected_child.player_id != root.player_id:
                selected_value = -selected_child.value
            else:
                selected_value = selected_child.value
            selected_visits = selected_child.visit_count
        else:
            selected_value = 0.0
            selected_visits = 0

        win_rate = (selected_value + 1.0) / 2.0

        return {
            'best_action_str': self._format_action(selected_action),
            'best_value': selected_value,
            'best_visits': selected_visits,
            'win_rate': win_rate,
            'total_children': len(root.children),
        }

    def _format_action(self, action: Action) -> str:
        if action.display_label:
            return action.display_label
        from models import ActionType
        action_type = action.action_type.value
        if action.attack_name:
            return f"{action_type}: {action.attack_name}"
        elif action.ability_name:
            return f"{action_type}: {action.ability_name}"
        elif action.action_type == ActionType.END_TURN:
            return "END_TURN"
        return action_type


# =============================================================================
# PARALLEL SELF-PLAY WORKER
# =============================================================================

class ParallelSelfPlayWorker:
    """
    Plays multiple games in parallel with batched MCTS.

    Instead of playing games sequentially, we:
    1. Start N games simultaneously
    2. At each step, batch MCTS across all active games
    3. Collect samples from all games when they finish
    """

    def __init__(
        self,
        engine,
        model,
        state_encoder: StateEncoder,
        device: str = 'cpu',
        num_parallel_games: int = 16,
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
        self.engine = engine
        self.model = model
        self.state_encoder = state_encoder
        self.device = device
        self.num_parallel_games = num_parallel_games
        self.num_simulations = num_simulations
        self.c_puct = c_puct
        self.dirichlet_alpha = dirichlet_alpha
        self.dirichlet_epsilon = dirichlet_epsilon
        self.max_turns = max_turns
        self.temperature_threshold = temperature_threshold
        self.high_temp = high_temp
        self.low_temp = low_temp
        self.verbose = verbose

        if self.model is not None:
            self.model.eval()

    def play_batch(self) -> Tuple[List[Tuple[Dict, np.ndarray, float]], Dict[str, Any]]:
        """
        Play N games in parallel and return combined samples.

        Returns:
            Tuple of (all_samples, stats) where:
            - all_samples: Combined training samples from all games
            - stats: Aggregate statistics
        """
        # Initialize all games
        games = []
        for i in range(self.num_parallel_games):
            state = self._create_new_game()
            history = GameHistory()
            games.append({
                'state': state,
                'history': history,
                'active': True,
                'game_idx': i,
                'last_action': None,  # Track last action for logging
            })

        # Track statistics
        total_steps = 0
        last_active_count = self.num_parallel_games
        last_max_turn = 0

        print(f"  Starting {self.num_parallel_games} parallel games...", flush=True)

        # Main loop - continue until all games are done
        while any(g['active'] for g in games):
            # Collect states from active games
            active_games = [g for g in games if g['active']]

            if not active_games:
                break

            # Check which games need MCTS vs forced moves
            mcts_games = []
            forced_games = []

            for game in active_games:
                state = game['state']

                # Check if game is over
                if state.is_game_over() or state.turn_count >= self.max_turns:
                    game['active'] = False
                    # Print game completion
                    finished_count = sum(1 for g in games if not g['active'])
                    winner = self._get_winner(state)
                    winner_str = f"P{winner}" if winner is not None else "Draw"
                    result = state.result
                    result_str = result.value if result else 'max_turns'
                    print(f"  Game {finished_count}/{self.num_parallel_games} done: "
                          f"T{state.turn_count} {winner_str} ({result_str})", flush=True)
                    continue

                legal_actions = self.engine.get_legal_actions(state)

                if not legal_actions:
                    game['active'] = False
                    # Print game completion for no legal actions
                    finished_count = sum(1 for g in games if not g['active'])
                    winner = self._get_winner(state)
                    winner_str = f"P{winner}" if winner is not None else "Draw"
                    print(f"  Game {finished_count}/{self.num_parallel_games} done: "
                          f"T{state.turn_count} {winner_str} (no_actions)", flush=True)
                    continue

                if len(legal_actions) == 1:
                    forced_games.append((game, legal_actions[0]))
                else:
                    mcts_games.append(game)

            # Handle forced moves (no MCTS needed)
            for game, forced_action in forced_games:
                with suppress_stdout():
                    game['state'] = self.engine.step_inplace(game['state'], forced_action)

            # Run batched MCTS on games with choices
            if mcts_games:
                self._run_batched_mcts_step(mcts_games)

            total_steps += 1

            # Print periodic status updates (every 20 turns if no games finished recently)
            active_count = sum(1 for g in games if g['active'])
            if active_count > 0:
                max_turn = max(g['state'].turn_count for g in games if g['active'])
                if max_turn >= last_max_turn + 20 and active_count == last_active_count:
                    min_turn = min(g['state'].turn_count for g in games if g['active'])
                    print(f"  ... {active_count} games running (turns {min_turn}-{max_turn})", flush=True)
                    last_max_turn = max_turn
                last_active_count = active_count

            # Safety check
            if total_steps > self.max_turns * self.num_parallel_games:
                if self.verbose:
                    print("  [WARN] Safety limit reached, ending remaining games")
                for g in games:
                    g['active'] = False

        # Collect samples from all finished games
        all_samples = []
        stats = {
            'num_games': self.num_parallel_games,
            'total_samples': 0,
            'total_turns': 0,
            'player_0_wins': 0,
            'player_1_wins': 0,
            'draws': 0,
        }

        for game in games:
            winner_id = self._get_winner(game['state'])
            samples = game['history'].finish_game(winner_id)
            all_samples.extend(samples)

            stats['total_samples'] += len(samples)
            stats['total_turns'] += game['state'].turn_count

            if winner_id == 0:
                stats['player_0_wins'] += 1
            elif winner_id == 1:
                stats['player_1_wins'] += 1
            else:
                stats['draws'] += 1

        stats['avg_turns'] = stats['total_turns'] / self.num_parallel_games

        # Print game summaries
        if self.verbose:
            print(f"  Game Results:")
            for game in games:
                winner = self._get_winner(game['state'])
                result = game['state'].result
                result_str = result.value if result else 'max_turns'
                winner_str = f"P{winner}" if winner is not None else "Draw"
                p0_prizes = len(game['state'].players[0].prizes.cards)
                p1_prizes = len(game['state'].players[1].prizes.cards)
                print(f"    G{game['game_idx']:2d}: T{game['state'].turn_count:3d} | "
                      f"{winner_str:4s} | Prizes: {p0_prizes}-{p1_prizes} | {result_str}")

        return all_samples, stats

    def _run_batched_mcts_step(self, games: List[Dict]) -> None:
        """
        Run one batched MCTS step across multiple games.

        This is where the magic happens - one batched NN call for all games.
        """
        states = [g['state'] for g in games]

        # Determine temperature for each game
        temperatures = []
        for g in games:
            if g['state'].turn_count < self.temperature_threshold:
                temperatures.append(self.high_temp)
            else:
                temperatures.append(self.low_temp)

        # Use the most common temperature (simplification)
        # In practice, early game exploration is more important
        avg_temp = sum(temperatures) / len(temperatures)

        # Create BatchMCTS
        batch_mcts = BatchMCTS(
            engine=self.engine,
            model=self.model,
            state_encoder=self.state_encoder,
            device=self.device,
            num_simulations=self.num_simulations,
            c_puct=self.c_puct,
            dirichlet_alpha=self.dirichlet_alpha,
            dirichlet_epsilon=self.dirichlet_epsilon,
            temperature=avg_temp,
        )

        # Run batched search
        with suppress_stdout():
            results = batch_mcts.search_batch(states, add_noise=True)

        # Apply results to each game
        for game, (action, action_probs, info) in zip(games, results):
            state = game['state']

            # Encode and store for training
            encoded = self.state_encoder.encode(state)
            state_dict = encoded.to_dict()

            game['history'].store(
                state_dict=state_dict,
                action_probs=action_probs,
                player_id=state.active_player_index,
                turn_number=state.turn_count
            )

            # Apply action
            with suppress_stdout():
                game['state'] = self.engine.step_inplace(state, action)

            # Store last action for potential detailed logging
            game['last_action'] = info.get('best_action_str', str(action))

    def _create_new_game(self) -> GameState:
        """Create a new game state."""
        from game_setup import build_game_state, setup_initial_board

        deck_path = os.path.join(src_dir, "decks", "charizard_ex.txt")

        if os.path.exists(deck_path):
            with open(deck_path, 'r') as f:
                deck_list = f.read()
        else:
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

        with suppress_stdout():
            state = build_game_state(deck_list, deck_list)
            state = setup_initial_board(state)

        return state

    def _get_winner(self, state: GameState) -> Optional[int]:
        """Get winner from game result."""
        result = state.result

        if result == GameResult.PLAYER_0_WIN:
            return 0
        elif result == GameResult.PLAYER_1_WIN:
            return 1
        elif result == GameResult.DRAW:
            return None
        return None


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def run_parallel_self_play(
    engine,
    model,
    state_encoder: StateEncoder,
    device: str = 'cpu',
    num_games: int = 16,
    num_simulations: int = 100,
    verbose: bool = True
) -> Tuple[List[Tuple[Dict, np.ndarray, float]], Dict[str, Any]]:
    """
    Run parallel self-play games with batched MCTS.

    This is a drop-in replacement for run_self_play_games that uses
    batched inference for better GPU utilization.

    Args:
        engine: PokemonEngine instance
        model: AlphaZeroNet instance
        state_encoder: StateEncoder instance
        device: 'cuda' or 'cpu'
        num_games: Number of parallel games
        num_simulations: MCTS simulations per move
        verbose: Print progress

    Returns:
        Tuple of (all_samples, stats)
    """
    worker = ParallelSelfPlayWorker(
        engine=engine,
        model=model,
        state_encoder=state_encoder,
        device=device,
        num_parallel_games=num_games,
        num_simulations=num_simulations,
        verbose=verbose
    )

    return worker.play_batch()


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    'BatchMCTS',
    'ParallelSelfPlayWorker',
    'run_parallel_self_play',
]

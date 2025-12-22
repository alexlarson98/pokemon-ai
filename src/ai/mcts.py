"""
Monte Carlo Tree Search (MCTS) - AlphaZero Neural Network Guided.

This implementation uses a neural network for both:
1. Policy: Action prior probabilities (which moves to explore)
2. Value: Position evaluation (who is winning)

Key Features:
- PUCT formula for selection with neural network priors
- No random rollouts - uses value network for leaf evaluation
- Returns action probabilities for training (visit count distribution)
- Value flipping for alternating players

Usage:
    from ai.mcts import MCTS
    from ai.model import AlphaZeroNet
    from ai.state_encoder import StateEncoder
    from engine import PokemonEngine

    model = AlphaZeroNet(vocab_size=1000)
    encoder = StateEncoder()
    engine = PokemonEngine()

    mcts = MCTS(engine, model, encoder, device='cuda')
    action, probs, info = mcts.search(state)
"""

import math
import random
import io
import contextlib
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field

import torch
import torch.nn.functional as F
import numpy as np

# Add src to path for imports
import sys
import os
script_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(script_dir)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from models import GameState, Action, ActionType, GameResult
from ai.encoder import UniversalActionEncoder, TOTAL_ACTION_SPACE
from fast_clone import fast_clone_game_state


# Context manager to suppress stdout during simulations
@contextlib.contextmanager
def suppress_stdout():
    """Temporarily suppress stdout (for clean simulations)."""
    # Flush any pending output before suppressing to prevent lost/reordered output
    sys.stdout.flush()
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        yield
    finally:
        sys.stdout = old_stdout


# =============================================================================
# MCTS NODE
# =============================================================================

@dataclass
class MCTSNode:
    """
    A node in the MCTS search tree.

    Attributes:
        state: Game state at this node
        parent: Parent node (None for root)
        action: Action that led to this node from parent
        action_index: Encoded action index
        prior: Prior probability from policy network
        visit_count: Number of times this node was visited
        value_sum: Total value accumulated (for averaging)
        children: Dict mapping action_index -> child node
        player_id: Which player's turn it is at this node
        legal_actions: List of legal actions at this node
        is_expanded: Whether this node has been expanded
    """
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
        """Initialize player_id from state."""
        self.player_id = self.state.active_player_index

    @property
    def value(self) -> float:
        """Average value of this node (Q-value)."""
        if self.visit_count == 0:
            return 0.0
        return self.value_sum / self.visit_count

    def is_terminal(self) -> bool:
        """Check if this is a terminal (game over) state."""
        return self.state.is_game_over()


# =============================================================================
# MCTS ENGINE
# =============================================================================

class MCTS:
    """
    Monte Carlo Tree Search with Neural Network guidance.

    Uses AlphaZeroNet for:
    - Policy priors (which actions to explore)
    - Value estimation (position evaluation)

    No random rollouts - pure neural network evaluation.
    """

    def __init__(
        self,
        engine,
        model=None,
        state_encoder=None,
        device: str = 'cpu',
        num_simulations: int = 100,
        c_puct: float = 1.5,
        dirichlet_alpha: float = 0.3,
        dirichlet_epsilon: float = 0.25,
        temperature: float = 1.0,
        verbose: bool = False
    ):
        """
        Initialize MCTS.

        Args:
            engine: PokemonEngine instance
            model: AlphaZeroNet instance (None for random fallback)
            state_encoder: StateEncoder instance (None for random fallback)
            device: 'cuda' or 'cpu'
            num_simulations: Number of simulations per search
            c_puct: Exploration constant for PUCT formula
            dirichlet_alpha: Dirichlet noise alpha (for root exploration)
            dirichlet_epsilon: Weight of Dirichlet noise at root
            temperature: Temperature for action selection (1.0 = proportional to visits)
            verbose: Print thinking process
        """
        self.engine = engine
        self.model = model
        self.state_encoder = state_encoder
        self.device = device
        self.num_simulations = num_simulations
        self.c_puct = c_puct
        self.dirichlet_alpha = dirichlet_alpha
        self.dirichlet_epsilon = dirichlet_epsilon
        self.temperature = temperature
        self.verbose = verbose

        # Set model to eval mode if provided
        if self.model is not None:
            self.model.eval()

        # Action encoder for neural network compatibility
        self.encoder = UniversalActionEncoder()

        # Statistics for debugging
        self.stats = {
            'simulations': 0,
            'nn_evaluations': 0,
            'terminal_states': 0,
        }

    def search(
        self,
        state: GameState,
        add_noise: bool = True
    ) -> Tuple[Action, np.ndarray, Dict[str, Any]]:
        """
        Run MCTS and return the best action with action probabilities.

        Args:
            state: Current game state
            add_noise: Whether to add Dirichlet noise at root (for training)

        Returns:
            Tuple of (best_action, action_probs, info_dict) where:
            - best_action: The selected action
            - action_probs: (TOTAL_ACTION_SPACE,) array of visit count probabilities
            - info_dict: Statistics about the search
        """
        # Reset stats
        self.stats = {'simulations': 0, 'nn_evaluations': 0, 'terminal_states': 0}

        # Suppress all engine output during search
        with suppress_stdout():
            # Create root node
            root = MCTSNode(state=fast_clone_game_state(state))
            root.legal_actions = self.engine.get_legal_actions(root.state)

            if not root.legal_actions:
                raise ValueError("No legal actions available")

            # Expand root with neural network evaluation
            self._expand_node(root, add_noise=add_noise)

            # Run simulations
            for i in range(self.num_simulations):
                self._simulate(root)
                self.stats['simulations'] += 1

        # Get action probabilities from visit counts
        action_probs = self._get_action_probabilities(root)

        # Select action based on temperature
        selected_action, selected_action_index = self._select_action(root, action_probs)

        # Gather statistics (pass selected action AND index to get correct logging)
        info = self._gather_info(root, selected_action, selected_action_index)

        return selected_action, action_probs, info

    def _simulate(self, root: MCTSNode) -> None:
        """
        Run one simulation: Select -> Expand/Evaluate -> Backpropagate.

        No rollouts - uses neural network for leaf evaluation.
        """
        node = root

        # === SELECTION ===
        # Traverse tree using PUCT until we find an unexpanded node or terminal
        while node.is_expanded and not node.is_terminal():
            node = self._select_child(node)

        # === EXPANSION & EVALUATION ===
        if node.is_terminal():
            # Terminal state - get actual game result
            value = self._get_terminal_value(node)
            self.stats['terminal_states'] += 1
        else:
            # Expand and evaluate with neural network
            value = self._expand_node(node)
            self.stats['nn_evaluations'] += 1

        # === BACKPROPAGATION ===
        self._backpropagate(node, value)

    def _select_child(self, node: MCTSNode) -> MCTSNode:
        """
        Select the best child using PUCT formula.

        PUCT(s,a) = Q(s,a) + c_puct * P(s,a) * sqrt(N(s)) / (1 + N(s,a))

        Returns the child with highest PUCT score.
        """
        best_score = float('-inf')
        best_child = None

        sqrt_parent_visits = math.sqrt(node.visit_count)

        for child in node.children.values():
            # Q-value from current player's perspective
            # Child value is from child's player perspective, so flip if different
            if child.player_id != node.player_id:
                q_value = -child.value
            else:
                q_value = child.value

            # PUCT exploration bonus
            exploration = (
                self.c_puct * child.prior * sqrt_parent_visits / (1 + child.visit_count)
            )

            score = q_value + exploration

            if score > best_score:
                best_score = score
                best_child = child

        return best_child

    def _expand_node(self, node: MCTSNode, add_noise: bool = False) -> float:
        """
        Expand a node using neural network evaluation.

        1. Get legal actions
        2. Encode state and run through neural network
        3. Extract policy priors for legal actions
        4. Create child nodes with priors
        5. Return value estimate

        Args:
            node: Node to expand
            add_noise: Whether to add Dirichlet noise (for root exploration)

        Returns:
            Value estimate from neural network (from node's player perspective)
        """
        if node.is_terminal():
            return self._get_terminal_value(node)

        # Get legal actions if not already set
        if not node.legal_actions:
            node.legal_actions = self.engine.get_legal_actions(node.state)

        if not node.legal_actions:
            # No legal actions - treat as terminal
            return 0.0

        # Get policy and value from neural network
        policy_probs, value = self._evaluate_with_network(node)

        # Create legal action mask and extract priors
        legal_priors = {}
        prior_sum = 0.0

        for action in node.legal_actions:
            try:
                action_index = self.encoder.encode(action, node.state)
                prior = policy_probs[action_index]
                legal_priors[action_index] = (action, prior)
                prior_sum += prior
            except ValueError:
                # Fallback for unencoded actions
                action_index = hash(str(action)) % TOTAL_ACTION_SPACE
                legal_priors[action_index] = (action, 1.0 / len(node.legal_actions))
                prior_sum += 1.0 / len(node.legal_actions)

        # Normalize priors to sum to 1
        if prior_sum > 0:
            for idx in legal_priors:
                action, prior = legal_priors[idx]
                legal_priors[idx] = (action, prior / prior_sum)

        # Add Dirichlet noise at root for exploration
        if add_noise and len(legal_priors) > 0:
            noise = np.random.dirichlet([self.dirichlet_alpha] * len(legal_priors))
            for i, idx in enumerate(legal_priors.keys()):
                action, prior = legal_priors[idx]
                noisy_prior = (
                    (1 - self.dirichlet_epsilon) * prior +
                    self.dirichlet_epsilon * noise[i]
                )
                legal_priors[idx] = (action, noisy_prior)

        # Create child nodes
        for action_index, (action, prior) in legal_priors.items():
            # Apply action to get new state
            new_state = self.engine.step(node.state, action)

            # Auto-step forced actions
            new_state = self._auto_step_forced(new_state)

            # Create child node
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

        return value

    def _evaluate_with_network(self, node: MCTSNode) -> Tuple[np.ndarray, float]:
        """
        Evaluate position using neural network.

        Args:
            node: Node to evaluate

        Returns:
            Tuple of (policy_probs, value) where:
            - policy_probs: (TOTAL_ACTION_SPACE,) array of action probabilities
            - value: Position value from node's player perspective
        """
        if self.model is None or self.state_encoder is None:
            # Fallback to uniform policy and zero value
            policy = np.ones(TOTAL_ACTION_SPACE) / TOTAL_ACTION_SPACE
            return policy, 0.0

        # Encode state
        encoded = self.state_encoder.encode(node.state)
        state_dict = encoded.to_dict()

        # Convert to tensors and add batch dimension
        tensor_dict = {}
        for key, arr in state_dict.items():
            tensor = torch.from_numpy(arr).unsqueeze(0)  # Add batch dim
            tensor_dict[key] = tensor.to(self.device)

        # Run neural network
        with torch.no_grad():
            policy_logits, value = self.model(tensor_dict)

        # Convert policy logits to probabilities
        policy_probs = F.softmax(policy_logits, dim=-1).squeeze(0).cpu().numpy()

        # Value is from the perspective of the current player (active_player_index)
        # The network always evaluates from active player's perspective
        value_scalar = value.item()

        return policy_probs, value_scalar

    def _auto_step_forced(self, state: GameState, max_steps: int = 100) -> GameState:
        """
        Auto-step through forced actions (states with only one legal action).

        This skips non-decisions like CONFIRM_SELECTION, SHUFFLE, etc.
        where the player has no real choice.

        Args:
            state: Current game state
            max_steps: Safety limit to prevent infinite loops

        Returns:
            State after all forced actions have been applied
        """
        steps = 0
        while not state.is_game_over() and steps < max_steps:
            legal_actions = self.engine.get_legal_actions(state)

            if not legal_actions:
                break

            # Stop when there's actually a choice to make
            if len(legal_actions) > 1:
                break

            # Auto-apply the single forced action
            state = self.engine.step_inplace(state, legal_actions[0])
            steps += 1

        return state

    def _get_terminal_value(self, node: MCTSNode) -> float:
        """
        Get value of a terminal state from node's player perspective.

        Args:
            node: Terminal node

        Returns:
            +1.0 for win, -1.0 for loss, 0.0 for draw
        """
        result = node.state.result
        player_id = node.player_id

        if result == GameResult.PLAYER_0_WIN:
            return 1.0 if player_id == 0 else -1.0
        elif result == GameResult.PLAYER_1_WIN:
            return 1.0 if player_id == 1 else -1.0
        elif result == GameResult.DRAW:
            return 0.0
        else:
            # Game not actually over
            return 0.0

    def _backpropagate(self, node: MCTSNode, value: float) -> None:
        """
        Backpropagate value up the tree.

        CRITICAL: Value must be flipped for alternating players!
        The value represents "how good this position is for the player at the leaf"

        Args:
            node: Leaf node where evaluation occurred
            value: Value from leaf node's player perspective
        """
        leaf_player = node.player_id

        while node is not None:
            node.visit_count += 1

            # Value is from leaf player's perspective
            # Flip sign when we're at a different player's node
            if node.player_id == leaf_player:
                node.value_sum += value
            else:
                node.value_sum -= value

            node = node.parent

    def _get_action_probabilities(self, root: MCTSNode) -> np.ndarray:
        """
        Get action probabilities from root visit counts.

        This is used for training - the policy target.

        Args:
            root: Root node after search

        Returns:
            (TOTAL_ACTION_SPACE,) array of probabilities based on visit counts
        """
        probs = np.zeros(TOTAL_ACTION_SPACE, dtype=np.float32)

        total_visits = sum(child.visit_count for child in root.children.values())

        if total_visits == 0:
            # Uniform over legal actions
            for child in root.children.values():
                probs[child.action_index] = 1.0 / len(root.children)
            return probs

        # Temperature-adjusted visit counts
        if self.temperature == 0:
            # Greedy - all weight on most visited
            best_child = max(root.children.values(), key=lambda c: c.visit_count)
            probs[best_child.action_index] = 1.0
        else:
            for child in root.children.values():
                # Apply temperature
                visit_prob = child.visit_count / total_visits
                if self.temperature != 1.0:
                    visit_prob = visit_prob ** (1.0 / self.temperature)
                probs[child.action_index] = visit_prob

            # Re-normalize after temperature
            prob_sum = probs.sum()
            if prob_sum > 0:
                probs /= prob_sum

        return probs

    def _select_action(
        self,
        root: MCTSNode,
        action_probs: np.ndarray
    ) -> Tuple[Action, int]:
        """
        Select action to play based on visit count probabilities.

        Args:
            root: Root node after search
            action_probs: Action probabilities from visit counts

        Returns:
            Tuple of (selected_action, action_index) for reliable child lookup
        """
        if self.temperature == 0:
            # Greedy selection
            best_child = max(root.children.values(), key=lambda c: c.visit_count)
            return best_child.action, best_child.action_index
        else:
            # Sample from probability distribution
            action_indices = list(root.children.keys())
            probs = np.array([action_probs[idx] for idx in action_indices])

            # Normalize to ensure valid distribution
            prob_sum = probs.sum()
            if prob_sum > 0:
                probs = probs / prob_sum
            else:
                probs = np.ones(len(probs)) / len(probs)

            chosen_idx = np.random.choice(len(action_indices), p=probs)
            chosen_action_index = action_indices[chosen_idx]

            return root.children[chosen_action_index].action, chosen_action_index

    def _gather_info(self, root: MCTSNode, selected_action: Action, selected_action_index: int) -> Dict[str, Any]:
        """
        Gather statistics about the search for debugging/display.

        Args:
            root: Root node after search
            selected_action: The action that was actually selected
            selected_action_index: The encoder index of the selected action (for reliable lookup)
        """
        visit_counts = {}
        values = {}

        for action_index, child in root.children.items():
            action_str = self._format_action(child.action)
            visit_counts[action_str] = child.visit_count

            # Value from root player's perspective
            if child.player_id != root.player_id:
                values[action_str] = -child.value
            else:
                values[action_str] = child.value

        # Get the selected child directly by index (reliable lookup)
        selected_child = root.children.get(selected_action_index)

        # Format the SELECTED action (not the most-visited one)
        # This ensures logging matches what's actually executed
        selected_action_str = self._format_action(selected_action)

        if selected_child:
            selected_value = values.get(selected_action_str, 0.0)
            selected_visits = selected_child.visit_count
        else:
            selected_value = 0.0
            selected_visits = 0

        # Calculate win rate for selected action (value is in [-1, 1], convert to [0, 1])
        win_rate = (selected_value + 1.0) / 2.0

        return {
            'visit_counts': visit_counts,
            'values': values,
            'best_action_str': selected_action_str,  # Shows SELECTED action, not most-visited
            'best_value': selected_value,
            'best_visits': selected_visits,
            'win_rate': win_rate,
            'simulations': self.stats['simulations'],
            'nn_evaluations': self.stats['nn_evaluations'],
            'terminal_states': self.stats['terminal_states'],
            'total_children': len(root.children),
        }

    def _format_action(self, action: Action) -> str:
        """Format action for display."""
        if action.display_label:
            return action.display_label

        action_type = action.action_type.value

        if action.attack_name:
            return f"{action_type}: {action.attack_name}"
        elif action.ability_name:
            return f"{action_type}: {action.ability_name}"
        elif action.action_type == ActionType.END_TURN:
            return "END_TURN"
        else:
            return action_type


# =============================================================================
# DECODE TO ACTION - Bridge between encoder index and Action object
# =============================================================================

def decode_to_action(
    index: int,
    state: GameState,
    legal_actions: List[Action],
    encoder: UniversalActionEncoder
) -> Optional[Action]:
    """
    Convert an encoded action index back to an Action object.

    This is the critical bridge for neural network -> game engine.
    The encoder.decode() returns a dictionary with positional info,
    and we must find the matching Action in legal_actions.

    Args:
        index: Encoded action index
        state: Current game state
        legal_actions: List of legal actions from engine
        encoder: UniversalActionEncoder instance

    Returns:
        Matching Action object, or None if not found
    """
    # Try exact match first
    for action in legal_actions:
        try:
            action_index = encoder.encode(action, state)
            if action_index == index:
                return action
        except ValueError:
            continue

    # Decode index to get category and positional info for fallback matching
    decoded = encoder.decode(index)
    category = decoded.get('action_category', '')

    # Fallback: Try to match by category
    if category == 'END_TURN':
        for action in legal_actions:
            if action.action_type == ActionType.END_TURN:
                return action

    elif category == 'ATTACK':
        attack_index = decoded.get('attack_index', 0)
        attack_actions = [a for a in legal_actions if a.action_type == ActionType.ATTACK]
        if attack_actions and attack_index < len(attack_actions):
            return attack_actions[attack_index]

    elif category == 'PLAY_HAND_CARD':
        hand_index = decoded.get('hand_index', 0)
        play_actions = [a for a in legal_actions if a.action_type in (
            ActionType.PLAY_BASIC, ActionType.ATTACH_ENERGY, ActionType.PLAY_ITEM,
            ActionType.PLAY_SUPPORTER, ActionType.EVOLVE
        )]
        if play_actions:
            player = state.get_active_player()
            for action in play_actions:
                if action.card_id:
                    for i, card in enumerate(player.hand.cards):
                        if card.id == action.card_id and i == hand_index:
                            return action

    return None


# =============================================================================
# RANDOM AGENT (for comparison/testing)
# =============================================================================

class RandomAgent:
    """Simple agent that picks random legal actions."""

    def __init__(self, engine):
        self.engine = engine

    def select_action(self, state: GameState) -> Action:
        """Select a random legal action."""
        legal_actions = self.engine.get_legal_actions(state)
        if not legal_actions:
            raise ValueError("No legal actions available")
        return random.choice(legal_actions)

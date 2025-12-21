"""
Monte Carlo Tree Search (MCTS) - AlphaZero Compatible Architecture.

This implementation supports both:
1. Pure MCTS (random rollouts) - For testing without neural network
2. AlphaZero MCTS (neural network guided) - Future upgrade path

Key Design Decisions:
- PUCT formula for selection (AlphaZero standard)
- Priors default to uniform (will be replaced by policy network)
- Value flipping for alternating players
- Action encoder integration for neural network compatibility

Usage:
    from ai.mcts import MCTS
    from engine import PokemonEngine

    engine = PokemonEngine()
    mcts = MCTS(engine, num_simulations=100)

    best_action = mcts.search(state)
"""

import math
import random
import io
import contextlib
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from copy import deepcopy

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
    """Temporarily suppress stdout (for clean rollouts)."""
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
        prior: Prior probability from policy network (default 1.0 for pure MCTS)
        visit_count: Number of times this node was visited
        value_sum: Total value accumulated (for averaging)
        children: Dict mapping action -> child node
        player_id: Which player's turn it is at this node
    """
    state: GameState
    parent: Optional['MCTSNode'] = None
    action: Optional[Action] = None
    prior: float = 1.0  # Will be set by policy network in AlphaZero mode
    visit_count: int = 0
    value_sum: float = 0.0
    children: Dict[int, 'MCTSNode'] = field(default_factory=dict)  # action_index -> child
    player_id: int = 0

    # For tracking which actions are legal at this node
    legal_actions: List[Action] = field(default_factory=list)
    untried_actions: List[Action] = field(default_factory=list)

    def __post_init__(self):
        """Initialize player_id from state."""
        self.player_id = self.state.active_player_index

    @property
    def value(self) -> float:
        """Average value of this node (Q-value)."""
        if self.visit_count == 0:
            return 0.0
        return self.value_sum / self.visit_count

    def is_fully_expanded(self) -> bool:
        """Check if all legal actions have been tried."""
        return len(self.untried_actions) == 0

    def is_terminal(self) -> bool:
        """Check if this is a terminal (game over) state."""
        return self.state.is_game_over()

    def get_ucb_score(self, c_puct: float = 1.41) -> float:
        """
        Calculate UCB1/PUCT score for selection.

        PUCT formula (AlphaZero variant):
        Q(s,a) + c_puct * P(s,a) * sqrt(N(s)) / (1 + N(s,a))

        Where:
        - Q(s,a) = value estimate (value_sum / visit_count)
        - P(s,a) = prior probability (from policy network, or uniform)
        - N(s) = parent visit count
        - N(s,a) = this node's visit count
        - c_puct = exploration constant (higher = more exploration)

        Args:
            c_puct: Exploration constant (default 1.41 ≈ sqrt(2) for UCB1)

        Returns:
            UCB score for selection
        """
        if self.parent is None:
            return float('inf')

        # Exploitation term: average value
        q_value = self.value

        # Exploration term: PUCT bonus
        exploration = c_puct * self.prior * math.sqrt(self.parent.visit_count) / (1 + self.visit_count)

        return q_value + exploration


# =============================================================================
# MCTS ENGINE
# =============================================================================

class MCTS:
    """
    Monte Carlo Tree Search engine.

    Supports two modes:
    1. Pure MCTS: Random rollouts to estimate value
    2. AlphaZero MCTS: Neural network for policy and value (future)

    Usage:
        mcts = MCTS(engine, num_simulations=100)
        best_action = mcts.search(state)
    """

    def __init__(
        self,
        engine,
        num_simulations: int = 100,
        c_puct: float = 1.41,
        max_rollout_depth: int = 200,
        use_neural_net: bool = False,
        policy_network=None,
        value_network=None,
        verbose: bool = False
    ):
        """
        Initialize MCTS.

        Args:
            engine: PokemonEngine instance
            num_simulations: Number of simulations per search
            c_puct: Exploration constant for PUCT formula
            max_rollout_depth: Maximum depth for random rollouts
            use_neural_net: Whether to use neural network (AlphaZero mode)
            policy_network: Neural network for action priors (optional)
            value_network: Neural network for state values (optional)
            verbose: Print thinking process
        """
        self.engine = engine
        self.num_simulations = num_simulations
        self.c_puct = c_puct
        self.max_rollout_depth = max_rollout_depth
        self.use_neural_net = use_neural_net
        self.policy_network = policy_network
        self.value_network = value_network
        self.verbose = verbose

        # Action encoder for neural network compatibility
        self.encoder = UniversalActionEncoder()

        # Statistics for debugging
        self.stats = {
            'simulations': 0,
            'rollout_depths': [],
            'terminal_states': 0,
        }

    def search(self, state: GameState) -> Tuple[Action, Dict[str, Any]]:
        """
        Run MCTS and return the best action.

        Args:
            state: Current game state

        Returns:
            Tuple of (best_action, info_dict) where info_dict contains:
            - visit_counts: Dict of action -> visit count
            - values: Dict of action -> average value
            - best_value: Value of best action
            - simulations: Number of simulations run
        """
        # Reset stats
        self.stats = {'simulations': 0, 'rollout_depths': [], 'terminal_states': 0}

        # Create root node
        root = MCTSNode(state=fast_clone_game_state(state))
        root.legal_actions = self.engine.get_legal_actions(root.state)
        root.untried_actions = list(root.legal_actions)

        if not root.legal_actions:
            raise ValueError("No legal actions available")

        # Run simulations
        for i in range(self.num_simulations):
            self._simulate(root)
            self.stats['simulations'] += 1

            if self.verbose and (i + 1) % 10 == 0:
                print(f"  Simulation {i + 1}/{self.num_simulations}")

        # Select best action by visit count (most robust)
        best_action = self._select_action(root)

        # Gather statistics
        info = self._gather_info(root)

        return best_action, info

    def _simulate(self, root: MCTSNode) -> None:
        """
        Run one simulation: Selection -> Expansion -> Rollout -> Backpropagation.

        All simulation steps are wrapped in suppress_stdout to prevent
        engine debug messages from polluting output.
        """
        with suppress_stdout():
            node = root

            # === SELECTION ===
            # Traverse tree using UCB until we find an unexpanded node
            while node.is_fully_expanded() and not node.is_terminal():
                node = self._select_child(node)

            # === EXPANSION ===
            # If not terminal, expand one untried action
            if not node.is_terminal() and not node.is_fully_expanded():
                node = self._expand(node)

            # === ROLLOUT / EVALUATION ===
            # Get value estimate for this position
            if node.is_terminal():
                value = self._get_terminal_value(node)
                self.stats['terminal_states'] += 1
            elif self.use_neural_net and self.value_network:
                value = self._evaluate_with_network(node)
            else:
                value = self._rollout(node)

            # === BACKPROPAGATION ===
            self._backpropagate(node, value)

    def _select_child(self, node: MCTSNode) -> MCTSNode:
        """
        Select the best child using UCB/PUCT formula.

        Returns the child with highest UCB score.
        """
        best_score = float('-inf')
        best_child = None

        for child in node.children.values():
            # Flip value for opponent's perspective
            # From the current player's view, we want to maximize our value
            # But child.value is from the child's player's perspective
            if child.player_id != node.player_id:
                # Opponent's turn at child - we want to minimize their value
                score = -child.value + self.c_puct * child.prior * math.sqrt(node.visit_count) / (1 + child.visit_count)
            else:
                # Same player at child (rare in Pokemon, but possible with interrupts)
                score = child.get_ucb_score(self.c_puct)

            if score > best_score:
                best_score = score
                best_child = child

        return best_child

    def _expand(self, node: MCTSNode) -> MCTSNode:
        """
        Expand the node by trying one untried action.

        Returns the new child node.
        """
        # Pick an untried action
        action = node.untried_actions.pop()

        # Apply action to get new state (engine.step handles cloning)
        new_state = self.engine.step(node.state, action)

        # Auto-step any forced actions (single legal action states)
        new_state = self._auto_step_forced(new_state)

        # Create child node
        child = MCTSNode(
            state=new_state,
            parent=node,
            action=action,
            prior=self._get_prior(action, node),
        )
        child.legal_actions = self.engine.get_legal_actions(child.state)
        child.untried_actions = list(child.legal_actions)

        # Encode action to get index for children dict
        try:
            action_index = self.encoder.encode(action, node.state)
        except ValueError:
            # Fallback: use hash of action string
            action_index = hash(str(action)) % TOTAL_ACTION_SPACE

        node.children[action_index] = child

        return child

    def _get_prior(self, action: Action, node: MCTSNode) -> float:
        """
        Get prior probability for an action.

        In pure MCTS mode, returns uniform prior (1 / num_actions).
        In AlphaZero mode, returns policy network output.
        """
        if self.use_neural_net and self.policy_network:
            # TODO: Get prior from policy network
            # priors = self.policy_network(node.state)
            # action_index = self.encoder.encode(action, node.state)
            # return priors[action_index]
            pass

        # Uniform prior for pure MCTS
        num_actions = len(node.legal_actions)
        return 1.0 / num_actions if num_actions > 0 else 1.0

    def _auto_step_forced(self, state: GameState, max_steps: int = 100) -> GameState:
        """
        Auto-step through any forced actions (states with only one legal action).

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

            # Auto-apply the single forced action (inplace since state already cloned)
            state = self.engine.step_inplace(state, legal_actions[0])
            steps += 1

        return state

    def _rollout(self, node: MCTSNode) -> float:
        """
        Perform random rollout from node to estimate value.

        Plays random moves until game ends or depth limit reached.
        Forced actions (single legal action) are auto-stepped without counting
        toward depth limit.

        Returns:
            Value from perspective of node's player (+1 win, -1 loss, 0 draw/timeout)
        """
        # Clone once at start, then mutate in place for speed
        state = fast_clone_game_state(node.state)
        start_player = node.player_id
        depth = 0

        while not state.is_game_over() and depth < self.max_rollout_depth:
            legal_actions = self.engine.get_legal_actions(state)

            if not legal_actions:
                break

            # Auto-step forced actions without counting toward depth
            if len(legal_actions) == 1:
                state = self.engine.step_inplace(state, legal_actions[0])
                # Don't increment depth for forced actions
                continue

            # Random action selection for actual decisions
            action = random.choice(legal_actions)
            state = self.engine.step_inplace(state, action)
            depth += 1

        self.stats['rollout_depths'].append(depth)

        # Get value from start player's perspective
        return self._get_result_value(state, start_player)

    def _evaluate_with_network(self, node: MCTSNode) -> float:
        """
        Evaluate position using value network.

        Returns value from perspective of node's player.
        """
        # TODO: Implement neural network evaluation
        # value = self.value_network(node.state)
        # return value if node.player_id == 0 else -value
        return 0.0

    def _get_terminal_value(self, node: MCTSNode) -> float:
        """Get value of a terminal state from node's player perspective."""
        return self._get_result_value(node.state, node.player_id)

    def _get_result_value(self, state: GameState, player_id: int) -> float:
        """
        Convert game result to value from player's perspective.

        Args:
            state: Game state (possibly terminal)
            player_id: Which player's perspective

        Returns:
            +1.0 for win, -1.0 for loss, 0.0 for draw/ongoing
        """
        result = state.result

        if result == GameResult.PLAYER_0_WIN:
            return 1.0 if player_id == 0 else -1.0
        elif result == GameResult.PLAYER_1_WIN:
            return 1.0 if player_id == 1 else -1.0
        elif result == GameResult.DRAW:
            return 0.0
        else:
            # Game not over - use heuristic evaluation
            return self._evaluate_heuristic(state, player_id)

    def _evaluate_heuristic(self, state: GameState, player_id: int) -> float:
        """
        Heuristic evaluation of a non-terminal game state.

        Returns a value in [-1, 1] representing how favorable the position
        is for the specified player. This will be replaced by a neural network
        in the future.

        Factors considered:
        - Prize cards remaining (most important - directly measures winning)
        - Active Pokemon HP percentage
        - Bench presence and HP
        - Energy attached (attack readiness)
        - Evolution stage (higher = more powerful)
        - Attack damage potential

        Args:
            state: Current game state
            player_id: Which player's perspective to evaluate from

        Returns:
            Heuristic value in [-1, 1]
        """
        from cards.factory import create_card

        my_player = state.players[player_id]
        opp_player = state.players[1 - player_id]

        score = 0.0

        # === PRIZE DIFFERENTIAL (Weight: 0.4) ===
        # Fewer prizes remaining = closer to winning
        my_prizes_remaining = len(my_player.prizes.cards)
        opp_prizes_remaining = len(opp_player.prizes.cards)
        # Each prize taken is worth ~0.067 (1/6 * 0.4)
        prize_score = (opp_prizes_remaining - my_prizes_remaining) / 6.0
        score += prize_score * 0.4

        # === ACTIVE POKEMON (Weight: 0.25) ===
        active_score = 0.0

        # My active
        if my_player.board.active_spot:
            my_active = my_player.board.active_spot
            my_active_def = create_card(my_active.card_id)
            if my_active_def:
                max_hp = my_active_def.hp
                current_hp = max_hp - (my_active.damage_counters * 10)
                hp_pct = current_hp / max_hp if max_hp > 0 else 0

                # HP percentage (0-1)
                active_score += hp_pct * 0.4

                # Evolution stage bonus (basic=0, stage1=0.15, stage2=0.3)
                stage = getattr(my_active_def, 'stage', 'Basic')
                if stage == 'Stage 1':
                    active_score += 0.15
                elif stage == 'Stage 2':
                    active_score += 0.3

                # Energy attached (readiness to attack)
                energy_count = len(my_active.attached_energy)
                active_score += min(energy_count / 4.0, 0.3) * 0.3

        # Opponent's active (we want them weak)
        if opp_player.board.active_spot:
            opp_active = opp_player.board.active_spot
            opp_active_def = create_card(opp_active.card_id)
            if opp_active_def:
                max_hp = opp_active_def.hp
                current_hp = max_hp - (opp_active.damage_counters * 10)
                hp_pct = current_hp / max_hp if max_hp > 0 else 0

                # Opponent low HP is good for us
                active_score += (1.0 - hp_pct) * 0.3

        score += active_score * 0.25

        # === BENCH PRESENCE (Weight: 0.2) ===
        bench_score = 0.0

        # My bench
        my_bench = [p for p in my_player.board.bench if p is not None]
        my_bench_count = len(my_bench)
        bench_score += min(my_bench_count / 5.0, 1.0) * 0.4  # Up to 5 bench = full score

        # Bench HP and evolution
        for pokemon in my_bench:
            poke_def = create_card(pokemon.card_id)
            if poke_def:
                max_hp = poke_def.hp
                current_hp = max_hp - (pokemon.damage_counters * 10)
                hp_pct = current_hp / max_hp if max_hp > 0 else 0
                bench_score += hp_pct * 0.05  # Small bonus per healthy benched Pokemon

                # Evolution bonus
                stage = getattr(poke_def, 'stage', 'Basic')
                if stage == 'Stage 1':
                    bench_score += 0.03
                elif stage == 'Stage 2':
                    bench_score += 0.06

        # Opponent bench (fewer = better for us)
        opp_bench = [p for p in opp_player.board.bench if p is not None]
        opp_bench_count = len(opp_bench)
        bench_score += (5 - min(opp_bench_count, 5)) / 5.0 * 0.2

        score += bench_score * 0.2

        # === ATTACK POTENTIAL (Weight: 0.15) ===
        attack_score = 0.0

        if my_player.board.active_spot:
            my_active = my_player.board.active_spot
            my_active_def = create_card(my_active.card_id)
            if my_active_def and hasattr(my_active_def, 'attacks'):
                # Check if we can attack and for how much damage
                max_damage = 0
                for attack in (my_active_def.attacks or []):
                    if hasattr(attack, 'damage'):
                        damage = attack.damage
                        if isinstance(damage, str):
                            # Parse damage like "120" or "30x"
                            damage = damage.replace('+', '').replace('x', '').replace('×', '')
                            try:
                                damage = int(damage) if damage else 0
                            except ValueError:
                                damage = 0
                        max_damage = max(max_damage, damage or 0)

                # Normalize damage (200+ damage = max score)
                attack_score = min(max_damage / 200.0, 1.0)

        score += attack_score * 0.15

        # Clamp to [-1, 1]
        return max(-1.0, min(1.0, score))

    def _backpropagate(self, node: MCTSNode, value: float) -> None:
        """
        Backpropagate value up the tree.

        CRITICAL: Value must be flipped for alternating players!
        The value represents "how good this position is for the player who reached it"
        """
        current_player = node.player_id

        while node is not None:
            node.visit_count += 1

            # Value is from the perspective of the player at the leaf node
            # We need to flip it for each alternating player
            if node.player_id == current_player:
                node.value_sum += value
            else:
                node.value_sum -= value

            node = node.parent

    def _select_action(self, root: MCTSNode) -> Action:
        """
        Select the best action from root based on visit counts.

        Visit count selection is more robust than value selection
        (AlphaZero uses visit count).
        """
        best_count = -1
        best_action = None

        for action_index, child in root.children.items():
            if child.visit_count > best_count:
                best_count = child.visit_count
                best_action = child.action

        return best_action

    def _gather_info(self, root: MCTSNode) -> Dict[str, Any]:
        """Gather statistics about the search for debugging/display."""
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

        # Find best action stats
        best_action = self._select_action(root)
        best_action_str = self._format_action(best_action)
        best_value = values.get(best_action_str, 0.0)
        best_visits = visit_counts.get(best_action_str, 0)

        # Calculate win rate (value is in [-1, 1], convert to [0, 1])
        win_rate = (best_value + 1.0) / 2.0

        return {
            'visit_counts': visit_counts,
            'values': values,
            'best_action_str': best_action_str,
            'best_value': best_value,
            'best_visits': best_visits,
            'win_rate': win_rate,
            'simulations': self.stats['simulations'],
            'terminal_states': self.stats['terminal_states'],
            'avg_rollout_depth': sum(self.stats['rollout_depths']) / len(self.stats['rollout_depths']) if self.stats['rollout_depths'] else 0,
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
    # Decode index to get category and positional info
    decoded = encoder.decode(index)
    category = decoded.get('action_category', '')

    # Find matching action in legal actions
    for action in legal_actions:
        try:
            action_index = encoder.encode(action, state)
            if action_index == index:
                return action
        except ValueError:
            continue

    # Fallback: Try to match by category and position
    # This is less precise but can help with edge cases
    if category == 'END_TURN':
        for action in legal_actions:
            if action.action_type == ActionType.END_TURN:
                return action

    elif category == 'ATTACK':
        attack_index = decoded.get('attack_index', 0)
        board_index = decoded.get('board_index', 0)
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
            # Find action with matching hand index
            player = state.get_active_player()
            for action in play_actions:
                if action.card_id:
                    for i, card in enumerate(player.hand.cards):
                        if card.id == action.card_id and i == hand_index:
                            return action

    return None


# =============================================================================
# RANDOM AGENT (for comparison)
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

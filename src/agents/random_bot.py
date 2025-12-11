"""
Pokémon TCG Engine - Random Bot Agent

Simple random agent for testing and baseline comparison.
Selects actions uniformly at random from legal actions.
"""

import random
from typing import List, TYPE_CHECKING
from agents.base import PlayerAgent

if TYPE_CHECKING:
    from models import GameState, Action


class RandomBot(PlayerAgent):
    """
    Random agent that selects actions uniformly at random.

    Useful for:
    - Testing game loop
    - Baseline performance comparison
    - Quick simulation (Bot vs Bot)

    Example:
        >>> bot = RandomBot(name="RandomBot", seed=42)
        >>> action = bot.choose_action(state, legal_actions)
    """

    def __init__(self, name: str = "RandomBot", seed: int = None):
        """
        Initialize random bot.

        Args:
            name: Display name for this bot
            seed: Random seed for reproducibility (optional)
        """
        super().__init__(name)
        self.seed = seed

        if seed is not None:
            random.seed(seed)

    def choose_action(self, state: 'GameState', legal_actions: List['Action']) -> 'Action':
        """
        Choose a random action from legal actions.

        Args:
            state: Current game state (unused by random bot)
            legal_actions: List of legal actions

        Returns:
            Randomly selected action

        Raises:
            ValueError: If no legal actions available
        """
        if not legal_actions:
            raise ValueError("No legal actions available")

        return random.choice(legal_actions)

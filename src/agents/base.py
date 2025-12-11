"""
Pokémon TCG Engine - Base Agent Interface

Abstract base class for all player agents.
Defines the contract that all agents (Human, Random, MCTS, etc.) must follow.
"""

from abc import ABC, abstractmethod
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from models import GameState, Action


class PlayerAgent(ABC):
    """
    Abstract base class for player agents.

    All agents must implement choose_action() to select a move from legal actions.
    This enables pluggable AI - swap agents without changing game loop.

    Attributes:
        name: Display name for this agent
        player_id: Player ID (0 or 1) - assigned by game loop
    """

    def __init__(self, name: str = "Agent"):
        """
        Initialize agent.

        Args:
            name: Display name for this agent
        """
        self.name = name
        self.player_id = None  # Assigned by game loop

    @abstractmethod
    def choose_action(self, state: 'GameState', legal_actions: List['Action']) -> 'Action':
        """
        Choose an action from the list of legal actions.

        This is the core interface method that all agents must implement.

        Args:
            state: Current game state (read-only)
            legal_actions: List of legal actions to choose from

        Returns:
            Selected action (must be from legal_actions list)

        Raises:
            ValueError: If no legal actions available
        """
        pass

    def on_game_start(self, player_id: int):
        """
        Called when game starts to assign player ID.

        Args:
            player_id: This agent's player ID (0 or 1)
        """
        self.player_id = player_id

    def on_game_end(self, state: 'GameState'):
        """
        Called when game ends (optional hook for learning agents).

        Args:
            state: Final game state
        """
        pass

    def __repr__(self):
        return f"{self.__class__.__name__}(name='{self.name}', player_id={self.player_id})"

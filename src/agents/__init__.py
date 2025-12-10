"""
Pokémon TCG Engine - Agent System

Pluggable agent architecture for game loop.
Supports Human players, Random bots, and future AI agents (MCTS, RL, etc.).

Usage:
    from agents import HumanAgent, RandomBot

    player1 = HumanAgent(name="Alice")
    player2 = RandomBot(name="Bot")
"""

from agents.base import PlayerAgent
from agents.human import HumanAgent
from agents.random_bot import RandomBot

__all__ = [
    'PlayerAgent',
    'HumanAgent',
    'RandomBot',
]

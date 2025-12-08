"""
Pytest configuration and fixtures.
Provides reusable game state setups for all tests.
"""

import sys
sys.path.insert(0, 'src')

import pytest
from typing import List

from models import (
    GameState,
    PlayerState,
    CardInstance,
    GamePhase,
    EnergyType,
    Subtype,
    Board,
    Zone
)
from cards.factory import create_card_instance, create_multiple
from engine import PokemonEngine
import actions


# ============================================================================
# FIXTURES: Standard Game States
# ============================================================================

@pytest.fixture
def engine():
    """Create a fresh PokemonEngine instance."""
    return PokemonEngine(random_seed=42)


@pytest.fixture
def empty_state():
    """
    Create an empty GameState with two players.

    Starting conditions:
    - Turn 1, Player 0's turn
    - Main Phase
    - Empty zones
    - No Pokémon in play
    """
    player0 = PlayerState(player_id=0, name="Player 0")
    player1 = PlayerState(player_id=1, name="Player 1")

    state = GameState(
        players=[player0, player1],
        turn_count=1,
        active_player_index=0,
        current_phase=GamePhase.MAIN
    )

    return state


@pytest.fixture
def basic_battle_state(empty_state):
    """
    Create a basic battle state with Active Pokémon for both players.

    Setup:
    - Player 0: Charmander Active (60 HP)
    - Player 1: Pikachu ex Active (200 HP)
    - Both players have 6 prizes
    - Turn 1, Player 0's turn, Main Phase
    """
    state = empty_state

    # Create Pokémon instances
    p0_active = create_card_instance("sv3-26", owner_id=0)  # Charmander
    p1_active = create_card_instance("sv8-57", owner_id=1)  # Pikachu ex

    # Place on field
    state.players[0].board.active_spot = p0_active
    state.players[1].board.active_spot = p1_active

    # Set up prizes (6 each)
    for _ in range(6):
        prize0 = create_card_instance("base1-98", owner_id=0)  # Fire Energy
        prize1 = create_card_instance("base1-98", owner_id=1)  # Fire Energy
        state.players[0].prizes.add_card(prize0)
        state.players[1].prizes.add_card(prize1)

    return state


@pytest.fixture
def charizard_battle_state(empty_state):
    """
    Create a battle state with Charizard ex vs Pikachu ex.

    Setup:
    - Player 0: Charizard ex Active (330 HP) with 2 Fire Energy
    - Player 1: Pikachu ex Active (120 HP)
    - Player 1 has taken 3 prizes
    - Turn 2, Player 0's turn, Attack Phase
    """
    state = empty_state

    # Create Pokémon
    p0_active = create_card_instance("sv3-125", owner_id=0)  # Charizard ex
    p1_active = create_card_instance("sv8-57", owner_id=1)  # Pikachu ex

    # Attach 2 Fire Energy to Charizard
    fire1 = create_card_instance("base1-98", owner_id=0)  # Fire Energy
    fire2 = create_card_instance("base1-98", owner_id=0)  # Fire Energy
    p0_active.attached_energy.append(fire1)
    p0_active.attached_energy.append(fire2)

    # Place on field
    state.players[0].board.active_spot = p0_active
    state.players[1].board.active_spot = p1_active

    # Set up prizes - Player 1 has taken 3
    for _ in range(6):
        prize0 = create_card_instance("base1-98", owner_id=0)  # Fire Energy
        state.players[0].prizes.add_card(prize0)

    for _ in range(3):
        prize1 = create_card_instance("base1-98", owner_id=1)  # Fire Energy
        state.players[1].prizes.add_card(prize1)

    state.players[1].prizes_taken = 3

    # Set to Turn 2, Attack Phase (can attack)
    state.turn_count = 2
    state.current_phase = GamePhase.ATTACK

    return state


@pytest.fixture
def evolution_state(empty_state):
    """
    Create a state ready for evolution testing.

    Setup:
    - Player 0: Charmander Active (played Turn 1, now Turn 2)
    - Player 0: Charmeleon in hand
    - Turn 2, Main Phase
    """
    state = empty_state

    # Create Charmander (already in play)
    charmander = create_card_instance("sv3-26", owner_id=0)
    charmander.turns_in_play = 1  # Played last turn
    state.players[0].board.active_spot = charmander

    # Add Charmeleon to hand
    charmeleon = create_card_instance("sv3-27", owner_id=0)
    state.players[0].hand.add_card(charmeleon)

    # Set to Turn 2 (can evolve)
    state.turn_count = 2
    state.current_phase = GamePhase.MAIN

    return state


# ============================================================================
# FIXTURES: Specialized States
# ============================================================================

@pytest.fixture
def deck_out_state(empty_state):
    """
    Create a state where Player 0's deck is about to run out.

    Setup:
    - Player 0: Empty deck
    - Player 0: Active Pokémon in play
    - Draw Phase (about to draw)
    """
    state = empty_state

    # Add Active Pokémon (needed to not lose immediately)
    p0_active = create_card_instance("sv3-26", owner_id=0)
    state.players[0].board.active_spot = p0_active

    # Empty deck (already empty by default)
    state.current_phase = GamePhase.DRAW

    return state


@pytest.fixture
def knockout_state(empty_state):
    """
    Create a state ready for knockout testing.

    Setup:
    - Player 0: Charmander Active with 50 damage (10 HP remaining)
    - Player 1: Active attacker
    - Player 1: Bench Pokémon (for promotion after KO)
    """
    state = empty_state

    # Create Charmander with heavy damage (60 HP - 50 damage = 10 HP)
    charmander = create_card_instance("sv3-26", owner_id=0)
    charmander.damage_counters = 5  # 50 damage
    state.players[0].board.active_spot = charmander

    # Add bench Pokémon for Player 0 (to promote after KO)
    bench_pokemon = create_card_instance("sv3-26", owner_id=0)
    state.players[0].board.add_to_bench(bench_pokemon)

    # Player 1 attacker
    attacker = create_card_instance("sv8-57", owner_id=1)  # Pikachu ex
    state.players[1].board.active_spot = attacker

    # Set up prizes
    for _ in range(6):
        prize0 = create_card_instance("base1-98", owner_id=0)  # Fire Energy
        prize1 = create_card_instance("base1-98", owner_id=1)  # Fire Energy
        state.players[0].prizes.add_card(prize0)
        state.players[1].prizes.add_card(prize1)

    return state


@pytest.fixture
def weakness_state(empty_state):
    """
    Create a state for testing weakness calculation.

    Setup:
    - Player 0: Fire-type attacker
    - Player 1: Grass-type defender (weak to Fire)
    """
    state = empty_state

    # For this test, we'll need to create mock Pokémon with specific types
    # Using existing cards - we'll verify weakness in the test itself

    return state


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def add_energy_to_pokemon(pokemon: CardInstance, energy_type: str, count: int, owner_id: int):
    """
    Helper to attach energy to a Pokémon.

    Args:
        pokemon: Target Pokémon
        energy_type: Energy card ID (e.g., "energy-fire")
        count: Number of energy to attach
        owner_id: Owner of the energy cards
    """
    for _ in range(count):
        energy = create_card_instance(energy_type, owner_id)
        pokemon.attached_energy.append(energy)


def add_cards_to_hand(player: PlayerState, card_id: str, count: int):
    """
    Helper to add cards to a player's hand.

    Args:
        player: Target player
        card_id: Card to add
        count: Number of copies
    """
    cards = create_multiple(card_id, count, player.player_id)
    for card in cards:
        player.hand.add_card(card)


def add_cards_to_deck(player: PlayerState, card_id: str, count: int):
    """
    Helper to add cards to a player's deck.

    Args:
        player: Target player
        card_id: Card to add
        count: Number of copies
    """
    cards = create_multiple(card_id, count, player.player_id)
    for card in cards:
        player.deck.add_card(card)


def set_pokemon_damage(pokemon: CardInstance, damage: int):
    """
    Helper to set a Pokémon's damage counters.

    Args:
        pokemon: Target Pokémon
        damage: Total damage (will be converted to counters)
    """
    pokemon.damage_counters = damage // 10


# ============================================================================
# ASSERTION HELPERS
# ============================================================================

def assert_has_action_type(actions: List, action_type):
    """Assert that at least one action of the given type exists."""
    from models import ActionType
    action_types = [a.action_type for a in actions]
    assert action_type in action_types, \
        f"Expected {action_type} in actions, but got: {action_types}"


def assert_no_action_type(actions: List, action_type):
    """Assert that no action of the given type exists."""
    from models import ActionType
    action_types = [a.action_type for a in actions]
    assert action_type not in action_types, \
        f"Did not expect {action_type} in actions, but found it in: {action_types}"


def assert_action_count(actions: List, expected_count: int):
    """Assert the exact number of legal actions."""
    assert len(actions) == expected_count, \
        f"Expected {expected_count} actions, but got {len(actions)}: {actions}"

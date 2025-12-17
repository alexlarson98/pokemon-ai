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


# ============================================================================
# ADDITIONAL FIXTURES FOR COMPREHENSIVE TESTS
# ============================================================================

@pytest.fixture
def basic_game_state():
    """
    Create a basic game state with two players, both with active Pokemon.

    Setup:
    - Turn count: 2 (past turn 1 restrictions)
    - Active player: Player 0
    - Phase: MAIN
    - Both players have active Pokemon (Pidgey)
    - No benched Pokemon
    - Empty hands

    Usage:
        def test_something(basic_game_state):
            player = basic_game_state.players[0]
            active = player.board.active_spot
    """
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Give both players an active Pokemon (Pidgey)
    player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
    player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

    return GameState(
        players=[player0, player1],
        turn_count=2,
        active_player_index=0,
        current_phase=GamePhase.MAIN,
        starting_player_id=0
    )


@pytest.fixture
def game_state_with_bench():
    """
    Create a game state with benched Pokemon for both players.

    Setup:
    - Same as basic_game_state
    - Player 0: Active Pidgey + 2 benched Pokemon
    - Player 1: Active Pidgey + 1 benched Pokemon
    """
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Active Pokemon
    player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
    player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

    # Add bench Pokemon
    player0.board.add_to_bench(create_card_instance("sv2-81", owner_id=0))
    player0.board.add_to_bench(create_card_instance("sv4pt5-7", owner_id=0))

    player1.board.add_to_bench(create_card_instance("sv2-81", owner_id=1))

    return GameState(
        players=[player0, player1],
        turn_count=2,
        active_player_index=0,
        current_phase=GamePhase.MAIN,
        starting_player_id=0
    )


@pytest.fixture
def full_bench_game_state():
    """
    Create a game state with full benches (5 Pokemon each).

    Setup:
    - Same as basic_game_state
    - Both players have full benches (5 Pokemon)
    - Useful for testing retreat with full bench
    """
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Active Pokemon
    player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
    player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

    # Fill benches to maximum (5 Pokemon)
    for _ in range(5):
        player0.board.add_to_bench(create_card_instance("sv2-81", owner_id=0))
        player1.board.add_to_bench(create_card_instance("sv2-81", owner_id=1))

    return GameState(
        players=[player0, player1],
        turn_count=2,
        active_player_index=0,
        current_phase=GamePhase.MAIN,
        starting_player_id=0
    )


@pytest.fixture
def turn_1_game_state():
    """
    Create a game state on turn 1 (for testing turn 1 restrictions).

    Setup:
    - Turn count: 1
    - Active player: Player 0 (went first)
    - Phase: MAIN
    - Both players have active Pokemon
    """
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
    player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

    return GameState(
        players=[player0, player1],
        turn_count=1,  # Turn 1
        active_player_index=0,
        current_phase=GamePhase.MAIN,
        starting_player_id=0  # Player 0 went first
    )


@pytest.fixture
def card_factory():
    """
    Provide a factory function for creating card instances.

    Usage:
        def test_something(card_factory):
            pidgey = card_factory("sv3pt5-16", owner_id=0)
            energy = card_factory("base1-98", owner_id=0)
    """
    def _create_card(card_id: str, owner_id: int = 0):
        """Create a card instance with the given card ID and owner."""
        return create_card_instance(card_id, owner_id=owner_id)

    return _create_card


@pytest.fixture
def energy_factory(card_factory):
    """
    Provide a factory function for creating energy cards.

    Usage:
        def test_something(energy_factory):
            fire_energy = energy_factory('fire', owner_id=0)
            water_energy = energy_factory('water', owner_id=0)
    """
    energy_mapping = {
        'fire': 'base1-98',      # Fire Energy
        'water': 'base1-102',    # Water Energy
        'grass': 'base1-99',     # Grass Energy
        'lightning': 'base1-100', # Lightning Energy
        'psychic': 'base1-101',  # Psychic Energy
        'fighting': 'base1-97',  # Fighting Energy
        'darkness': 'base1-104', # Darkness Energy
        'metal': 'base1-103',    # Metal Energy
    }

    def _create_energy(energy_type: str, owner_id: int = 0):
        """
        Create an energy card of the specified type.

        Args:
            energy_type: Type of energy ('fire', 'water', 'grass', etc.)
            owner_id: Owner player ID (0 or 1)

        Returns:
            CardInstance for the energy card
        """
        card_id = energy_mapping.get(energy_type.lower())
        if not card_id:
            raise ValueError(f"Unknown energy type: {energy_type}. Valid types: {list(energy_mapping.keys())}")
        return card_factory(card_id, owner_id=owner_id)

    return _create_energy


# ============================================================================
# COMMON CARD IDS (for reference and easy import)
# ============================================================================

# Basic Pokemon
PIDGEY = "sv3pt5-16"          # 60 HP, Colorless, retreat cost 1
CHARMANDER = "sv4pt5-7"       # 60 HP, Fire
WATTREL = "sv2-81"            # 50 HP, Lightning
HOOTHOOT = "sv3pt5-162"       # 60 HP, Colorless

# Stage 1 Pokemon
PIDGEOTTO = "sv3pt5-17"       # Evolves from Pidgey
CHARMELEON = "sv4pt5-8"       # Evolves from Charmander

# Stage 2 Pokemon
PIDGEOT = "sv3pt5-18"         # Evolves from Pidgeotto
CHARIZARD_EX = "sv4pt5-9"     # Evolves from Charmeleon

# Pokemon ex
PIDGEOT_EX = "sv3pt5-164"     # Basic Pokemon ex

# Trainer Cards
ULTRA_BALL = "sv3pt5-146"     # Search deck for Pokemon
NEST_BALL = "sv3pt5-145"      # Search deck for Basic Pokemon
BUDDY_BUDDY_POFFIN = "sv4pt5-139"  # Search for Pokemon with HP <= 70
RARE_CANDY = "sv3pt5-171"     # Evolve Basic to Stage 2

# Energy Cards
FIRE_ENERGY = "base1-98"
WATER_ENERGY = "base1-102"
GRASS_ENERGY = "base1-99"
LIGHTNING_ENERGY = "base1-100"


# ============================================================================
# PYTEST CONFIGURATION
# ============================================================================

def pytest_configure(config):
    """
    Configure pytest markers and other settings.
    """
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )

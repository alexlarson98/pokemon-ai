"""
Comprehensive pytest suite for Rare Candy evolution chain validation.

Tests:
- Valid evolution chains (Basic -> Stage 2 via intermediate Stage 1)
- Invalid evolution chains (wrong evolutionary line)
- Rare Candy only works with Stage 2 cards
- Rare Candy respects evolution sickness
- Rare Candy with multiple evolution lines

NOTE: Tests use action.parameters to verify evolution targets, NOT display_label strings.
This ensures we're testing actual data, not just UI text.
"""

import pytest
import sys
sys.path.insert(0, 'src')

from models import GameState, PlayerState, GamePhase
from engine import PokemonEngine
from cards.factory import create_card_instance
from cards.library.trainers import rare_candy_actions
from cards.utils import _check_evolution_chain
from cards.registry import create_card


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_evolution_card_id(action):
    """Extract the evolution card ID from a Rare Candy action."""
    if not action.parameters:
        return None
    return action.parameters.get('evolution_card_id')


def get_target_pokemon_id(action):
    """Extract the target Pokemon ID (Basic to evolve) from a Rare Candy action."""
    if not action.parameters:
        return None
    return action.parameters.get('target_pokemon_id')


def get_actions_evolving_to(actions, evolution_name, hand_cards):
    """
    Get actions that evolve into a specific Pokemon by name using parameter data.

    Args:
        actions: List of actions to filter
        evolution_name: Name of the evolution Pokemon (e.g., "Pidgeot")
        hand_cards: List of card instances in hand

    Returns:
        List of actions that evolve into the given Pokemon name
    """
    # Build map of instance_id -> card_name for hand cards
    hand_id_to_name = {}
    for card in hand_cards:
        card_def = create_card(card.card_id)
        if card_def:
            hand_id_to_name[card.id] = card_def.name

    matching_actions = []
    for action in actions:
        evo_id = get_evolution_card_id(action)
        if evo_id and evo_id in hand_id_to_name:
            if hand_id_to_name[evo_id] == evolution_name:
                matching_actions.append(action)

    return matching_actions


def get_actions_evolving_target(actions, target_name, board_pokemon):
    """
    Get actions that evolve a specific target Pokemon by name using parameter data.

    Args:
        actions: List of actions to filter
        target_name: Name of the target Pokemon (e.g., "Pidgey")
        board_pokemon: List of Pokemon on the board (active + bench)

    Returns:
        List of actions evolving the given target Pokemon name
    """
    # Build map of instance_id -> card_name for board pokemon
    board_id_to_name = {}
    for pokemon in board_pokemon:
        if pokemon:
            card_def = create_card(pokemon.card_id)
            if card_def:
                board_id_to_name[pokemon.id] = card_def.name

    matching_actions = []
    for action in actions:
        target_id = get_target_pokemon_id(action)
        if target_id and target_id in board_id_to_name:
            if board_id_to_name[target_id] == target_name:
                matching_actions.append(action)

    return matching_actions


def get_actions_evolving_pair(actions, target_name, evolution_name, board_pokemon, hand_cards):
    """
    Get actions that evolve a specific target into a specific evolution.

    Args:
        actions: List of actions to filter
        target_name: Name of the target Pokemon (e.g., "Pidgey")
        evolution_name: Name of the evolution Pokemon (e.g., "Pidgeot")
        board_pokemon: List of Pokemon on the board
        hand_cards: List of card instances in hand

    Returns:
        List of actions matching both target and evolution
    """
    # Build maps
    board_id_to_name = {}
    for pokemon in board_pokemon:
        if pokemon:
            card_def = create_card(pokemon.card_id)
            if card_def:
                board_id_to_name[pokemon.id] = card_def.name

    hand_id_to_name = {}
    for card in hand_cards:
        card_def = create_card(card.card_id)
        if card_def:
            hand_id_to_name[card.id] = card_def.name

    matching_actions = []
    for action in actions:
        target_id = get_target_pokemon_id(action)
        evo_id = get_evolution_card_id(action)

        target_matches = target_id and board_id_to_name.get(target_id) == target_name
        evo_matches = evo_id and hand_id_to_name.get(evo_id) == evolution_name

        if target_matches and evo_matches:
            matching_actions.append(action)

    return matching_actions


def get_all_board_pokemon(player):
    """Get all Pokemon on a player's board (active + bench)."""
    pokemon = []
    if player.board.active_spot:
        pokemon.append(player.board.active_spot)
    pokemon.extend(player.board.bench)
    return pokemon


@pytest.fixture
def engine():
    """Create PokemonEngine instance."""
    return PokemonEngine()


@pytest.fixture
def game_state_with_basic():
    """Create game state with a Basic Pokemon on board."""
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Active: Pidgey (Basic)
    pidgey = create_card_instance("sv3pt5-16", owner_id=0)
    pidgey.turns_in_play = 1  # No evolution sickness
    player0.board.active_spot = pidgey

    player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

    return GameState(
        players=[player0, player1],
        turn_count=2,  # Turn 2 to avoid turn 1 evolution restriction
        active_player_index=0,
        current_phase=GamePhase.MAIN,
        starting_player_id=0
    )


class TestEvolutionChainValidation:
    """Test that Rare Candy validates evolution chains correctly."""

    def test_valid_evolution_chain_pidgey_to_pidgeot(self, game_state_with_basic):
        """Pidgey -> Pidgeotto -> Pidgeot is a valid chain for Rare Candy."""
        state = game_state_with_basic
        player = state.players[0]

        # Add Rare Candy to hand
        rare_candy = create_card_instance("sv1-256", owner_id=0)
        player.hand.add_card(rare_candy)

        # Add Pidgeot (Stage 2) to hand
        pidgeot = create_card_instance("sv3pt5-18", owner_id=0)
        player.hand.add_card(pidgeot)

        # Generate actions
        actions = rare_candy_actions(state, rare_candy, player)

        # Should create action for Pidgey -> Pidgeot
        # Use parameter data to verify evolution target
        pidgeot_actions = get_actions_evolving_to(actions, "Pidgeot", player.hand.cards)
        assert len(pidgeot_actions) == 1, "Should create Rare Candy action for Pidgeot"

    def test_invalid_evolution_chain_pidgey_to_alakazam(self, game_state_with_basic):
        """Pidgey -> Alakazam should be blocked (Alakazam needs Abra -> Kadabra)."""
        state = game_state_with_basic
        player = state.players[0]

        # Add Rare Candy to hand
        rare_candy = create_card_instance("sv1-256", owner_id=0)
        player.hand.add_card(rare_candy)

        # Add Alakazam (Stage 2, different evolution line) to hand
        alakazam = create_card_instance("sv3pt5-66", owner_id=0)
        player.hand.add_card(alakazam)

        # Generate actions
        actions = rare_candy_actions(state, rare_candy, player)

        # Should NOT create action for Pidgey -> Alakazam
        # Use parameter data to verify no Alakazam evolution
        alakazam_actions = get_actions_evolving_to(actions, "Alakazam", player.hand.cards)
        assert len(alakazam_actions) == 0, "Should not allow Pidgey to evolve into Alakazam"

    def test_check_evolution_chain_helper(self):
        """Test the _check_evolution_chain helper function directly."""
        # Valid chains
        assert _check_evolution_chain('Pidgeotto', 'Pidgey') is True, \
            "Pidgeotto should evolve from Pidgey"
        assert _check_evolution_chain('Charmeleon', 'Charmander') is True, \
            "Charmeleon should evolve from Charmander"

        # Invalid chains
        assert _check_evolution_chain('Kadabra', 'Pidgey') is False, \
            "Kadabra should not evolve from Pidgey"
        assert _check_evolution_chain('Pidgeotto', 'Charmander') is False, \
            "Pidgeotto should not evolve from Charmander"


class TestRareCandyRestrictions:
    """Test Rare Candy restrictions and requirements."""

    def test_rare_candy_requires_stage_2(self, game_state_with_basic):
        """Rare Candy should only work with Stage 2 Pokemon."""
        state = game_state_with_basic
        player = state.players[0]

        rare_candy = create_card_instance("sv1-256", owner_id=0)
        player.hand.add_card(rare_candy)

        # Add Pidgeotto (Stage 1) to hand - should NOT work with Rare Candy
        pidgeotto = create_card_instance("sv3pt5-17", owner_id=0)
        player.hand.add_card(pidgeotto)

        actions = rare_candy_actions(state, rare_candy, player)

        # Should not create actions for Stage 1 Pokemon
        # Use parameter data to verify no Pidgeotto evolution
        pidgeotto_actions = get_actions_evolving_to(actions, "Pidgeotto", player.hand.cards)
        assert len(pidgeotto_actions) == 0, "Rare Candy should not work with Stage 1 Pokemon"

    def test_rare_candy_respects_evolution_sickness(self):
        """Rare Candy should not work on Pokemon played this turn."""
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        # Active: Pidgey with evolution sickness (turns_in_play = 0)
        pidgey = create_card_instance("sv3pt5-16", owner_id=0)
        pidgey.turns_in_play = 0  # Just played this turn
        player0.board.active_spot = pidgey

        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        player = state.players[0]

        rare_candy = create_card_instance("sv1-256", owner_id=0)
        player.hand.add_card(rare_candy)

        pidgeot = create_card_instance("sv3pt5-18", owner_id=0)
        player.hand.add_card(pidgeot)

        actions = rare_candy_actions(state, rare_candy, player)

        # Should not create actions due to evolution sickness
        assert len(actions) == 0, "Rare Candy should not bypass evolution sickness"

    def test_rare_candy_requires_evolution_in_hand(self, game_state_with_basic):
        """Rare Candy requires the Stage 2 Pokemon to be in hand."""
        state = game_state_with_basic
        player = state.players[0]

        rare_candy = create_card_instance("sv1-256", owner_id=0)
        player.hand.add_card(rare_candy)

        # Don't add any Stage 2 Pokemon to hand

        actions = rare_candy_actions(state, rare_candy, player)

        # Should create no actions
        assert len(actions) == 0, "Rare Candy requires Stage 2 Pokemon in hand"


class TestRareCandyMultipleLines:
    """Test Rare Candy with multiple evolution lines present."""

    def test_rare_candy_with_multiple_valid_evolutions(self):
        """Test Rare Candy when multiple valid Stage 2 cards are in hand."""
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        # Active: Pidgey
        pidgey = create_card_instance("sv3pt5-16", owner_id=0)
        pidgey.turns_in_play = 1
        player0.board.active_spot = pidgey

        # Bench: Charmander
        charmander = create_card_instance("sv4pt5-7", owner_id=0)
        charmander.turns_in_play = 1
        player0.board.add_to_bench(charmander)

        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        player = state.players[0]

        rare_candy = create_card_instance("sv1-256", owner_id=0)
        player.hand.add_card(rare_candy)

        # Add both Pidgeot (for Pidgey) and Charizard (for Charmander)
        pidgeot = create_card_instance("sv3pt5-18", owner_id=0)
        player.hand.add_card(pidgeot)

        # Find a Charizard card (need correct Stage 2)
        # sv3-125 is Charizard ex (Stage 2, evolves from Charmeleon)
        charizard = create_card_instance("sv3-125", owner_id=0)
        player.hand.add_card(charizard)

        actions = rare_candy_actions(state, rare_candy, player)

        # Should create actions for both valid evolutions
        # Use parameter data to verify evolution pairs
        board_pokemon = get_all_board_pokemon(player)
        pidgeot_actions = get_actions_evolving_pair(actions, "Pidgey", "Pidgeot", board_pokemon, player.hand.cards)
        charizard_actions = get_actions_evolving_pair(actions, "Charmander", "Charizard ex", board_pokemon, player.hand.cards)

        assert len(pidgeot_actions) >= 1, "Should allow Pidgey -> Pidgeot"
        assert len(charizard_actions) >= 1, "Should allow Charmander -> Charizard"


class TestRareCandyEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_rare_candy_with_evolved_pokemon(self):
        """Rare Candy should not work on already-evolved Pokemon."""
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        # Active: Pidgeotto (Stage 1 - already evolved)
        pidgeotto = create_card_instance("sv3pt5-17", owner_id=0)
        pidgeotto.turns_in_play = 1
        player0.board.active_spot = pidgeotto

        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        player = state.players[0]

        rare_candy = create_card_instance("sv1-256", owner_id=0)
        player.hand.add_card(rare_candy)

        # Pidgeot evolves from Pidgeotto, but Rare Candy requires Basic
        pidgeot = create_card_instance("sv3pt5-18", owner_id=0)
        player.hand.add_card(pidgeot)

        actions = rare_candy_actions(state, rare_candy, player)

        # Should create no actions (Rare Candy only works on Basic Pokemon)
        assert len(actions) == 0, "Rare Candy should only work on Basic Pokemon"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

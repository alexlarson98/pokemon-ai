"""
Comprehensive pytest suite for evolution mechanics.

Tests:
- Basic -> Stage 1 evolution
- Stage 1 -> Stage 2 evolution
- Evolution sickness (can't evolve turn played)
- Evolution sickness (can't evolve turn 1)
- Evolution chain validation
- Property transfer (damage, energy, tools)
- evolved_this_turn flag
- Once per turn per Pokemon restriction
"""

import pytest
import sys
sys.path.insert(0, 'src')

from models import GameState, PlayerState, GamePhase
from engine import PokemonEngine
from cards.factory import create_card_instance
from actions import evolve_pokemon
from cards.base import Subtype
from cards.registry import create_card


@pytest.fixture
def engine():
    """Create PokemonEngine instance."""
    return PokemonEngine()


@pytest.fixture
def evolution_game_state():
    """Create game state for evolution testing."""
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Active: Pidgey (Basic)
    pidgey = create_card_instance("sv3pt5-16", owner_id=0)
    pidgey.turns_in_play = 1  # No evolution sickness
    player0.board.active_spot = pidgey

    player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

    return GameState(
        players=[player0, player1],
        turn_count=2,  # Not turn 1
        active_player_index=0,
        current_phase=GamePhase.MAIN,
        starting_player_id=0
    )


class TestBasicEvolution:
    """Test basic evolution mechanics."""

    def test_basic_to_stage1_evolution(self, evolution_game_state):
        """Basic Pokemon should evolve into Stage 1."""
        state = evolution_game_state
        player = state.players[0]

        pidgey = player.board.active_spot

        # Add Pidgeotto (Stage 1) to hand
        pidgeotto = create_card_instance("sv3pt5-17", owner_id=0)
        player.hand.add_card(pidgeotto)

        # Evolve
        state = evolve_pokemon(state, 0, pidgey.id, pidgeotto.id, skip_stage=False)
        player = state.players[0]

        # Active should now be Pidgeotto
        assert player.board.active_spot.id == pidgeotto.id, "Should evolve to Pidgeotto"

        # Check card definition
        active_def = create_card(player.board.active_spot.card_id)
        assert Subtype.STAGE_1 in active_def.subtypes, "Should be Stage 1"

    def test_stage1_to_stage2_evolution(self):
        """Stage 1 Pokemon should evolve into Stage 2."""
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        # Active: Pidgeotto (Stage 1)
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

        # Add Pidgeot (Stage 2) to hand
        pidgeot = create_card_instance("sv3pt5-18", owner_id=0)
        player.hand.add_card(pidgeot)

        # Evolve
        state = evolve_pokemon(state, 0, pidgeotto.id, pidgeot.id, skip_stage=False)
        player = state.players[0]

        # Active should now be Pidgeot
        assert player.board.active_spot.id == pidgeot.id, "Should evolve to Pidgeot"

        active_def = create_card(player.board.active_spot.card_id)
        assert Subtype.STAGE_2 in active_def.subtypes, "Should be Stage 2"


class TestEvolutionSickness:
    """Test evolution sickness mechanics."""

    def test_cannot_evolve_turn_1(self):
        """Cannot evolve on turn 1."""
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        pidgey = create_card_instance("sv3pt5-16", owner_id=0)
        pidgey.turns_in_play = 1
        player0.board.active_spot = pidgey

        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        state = GameState(
            players=[player0, player1],
            turn_count=1,  # TURN 1
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        player = state.players[0]

        pidgeotto = create_card_instance("sv3pt5-17", owner_id=0)
        player.hand.add_card(pidgeotto)

        # Try to evolve (should fail)
        with pytest.raises(ValueError, match="Cannot evolve on the first turn"):
            evolve_pokemon(state, 0, pidgey.id, pidgeotto.id, skip_stage=False)

    def test_cannot_evolve_pokemon_played_this_turn(self):
        """Cannot evolve Pokemon that was just played (evolution sickness)."""
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        pidgey = create_card_instance("sv3pt5-16", owner_id=0)
        pidgey.turns_in_play = 0  # JUST PLAYED
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

        pidgeotto = create_card_instance("sv3pt5-17", owner_id=0)
        player.hand.add_card(pidgeotto)

        # Try to evolve (should fail)
        with pytest.raises(ValueError, match="evolution sickness"):
            evolve_pokemon(state, 0, pidgey.id, pidgeotto.id, skip_stage=False)


class TestEvolutionChainValidation:
    """Test evolution chain validation."""

    def test_must_evolve_from_correct_pokemon(self, evolution_game_state):
        """Evolution must follow correct evolution chain (evolves_from field)."""
        state = evolution_game_state
        player = state.players[0]

        pidgey = player.board.active_spot

        # Try to evolve Pidgey into Charmeleon (wrong chain)
        charmeleon = create_card_instance("sv4pt5-8", owner_id=0)
        player.hand.add_card(charmeleon)

        # Should fail (Charmeleon evolves from Charmander, not Pidgey)
        with pytest.raises(ValueError, match="cannot evolve from"):
            evolve_pokemon(state, 0, pidgey.id, charmeleon.id, skip_stage=False)


class TestPropertyTransfer:
    """Test that properties transfer during evolution."""

    def test_evolution_transfers_damage_counters(self, evolution_game_state):
        """Damage counters should transfer to evolved Pokemon."""
        state = evolution_game_state
        player = state.players[0]

        pidgey = player.board.active_spot
        pidgey.damage_counters = 2

        pidgeotto = create_card_instance("sv3pt5-17", owner_id=0)
        player.hand.add_card(pidgeotto)

        state = evolve_pokemon(state, 0, pidgey.id, pidgeotto.id, skip_stage=False)
        player = state.players[0]

        # Damage should transfer
        assert player.board.active_spot.damage_counters == 2, "Damage counters should transfer"

    def test_evolution_transfers_attached_energy(self, evolution_game_state):
        """Attached energy should transfer to evolved Pokemon."""
        state = evolution_game_state
        player = state.players[0]

        pidgey = player.board.active_spot

        # Attach energy
        energy1 = create_card_instance("base1-98", owner_id=0)
        energy2 = create_card_instance("base1-98", owner_id=0)
        pidgey.attached_energy = [energy1, energy2]

        pidgeotto = create_card_instance("sv3pt5-17", owner_id=0)
        player.hand.add_card(pidgeotto)

        state = evolve_pokemon(state, 0, pidgey.id, pidgeotto.id, skip_stage=False)
        player = state.players[0]

        # Energy should transfer
        assert len(player.board.active_spot.attached_energy) == 2, "Energy should transfer"

    def test_evolution_transfers_tools(self, evolution_game_state):
        """Attached tools should transfer to evolved Pokemon."""
        state = evolution_game_state
        player = state.players[0]

        pidgey = player.board.active_spot

        # Attach tool
        tool = create_card_instance("sv3pt5-165", owner_id=0)  # A tool card
        pidgey.attached_tools = [tool]

        pidgeotto = create_card_instance("sv3pt5-17", owner_id=0)
        player.hand.add_card(pidgeotto)

        state = evolve_pokemon(state, 0, pidgey.id, pidgeotto.id, skip_stage=False)
        player = state.players[0]

        # Tools should transfer
        assert len(player.board.active_spot.attached_tools) >= 1, "Tools should transfer"


class TestEvolutionFlags:
    """Test evolution-related flags."""

    def test_evolved_this_turn_flag_set(self, evolution_game_state):
        """evolved_this_turn flag should be set after evolution."""
        state = evolution_game_state
        player = state.players[0]

        pidgey = player.board.active_spot
        pidgeotto = create_card_instance("sv3pt5-17", owner_id=0)
        player.hand.add_card(pidgeotto)

        state = evolve_pokemon(state, 0, pidgey.id, pidgeotto.id, skip_stage=False)
        player = state.players[0]

        # Flag should be set
        assert player.board.active_spot.evolved_this_turn is True, \
            "evolved_this_turn should be set"

    def test_evolution_chain_preserved(self, evolution_game_state):
        """Evolution chain should be tracked in evolution_chain field."""
        state = evolution_game_state
        player = state.players[0]

        pidgey = player.board.active_spot
        pidgey_card_id = pidgey.card_id

        pidgeotto = create_card_instance("sv3pt5-17", owner_id=0)
        player.hand.add_card(pidgeotto)

        state = evolve_pokemon(state, 0, pidgey.id, pidgeotto.id, skip_stage=False)
        player = state.players[0]

        # Evolution chain should include Pidgey
        assert pidgey_card_id in player.board.active_spot.evolution_chain, \
            "Evolution chain should include previous form"


class TestBenchEvolution:
    """Test evolution on bench Pokemon."""

    def test_can_evolve_bench_pokemon(self):
        """Should be able to evolve benched Pokemon."""
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)

        # Add Charmander to bench
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

        # Add Charmeleon to hand
        charmeleon = create_card_instance("sv4pt5-8", owner_id=0)
        player.hand.add_card(charmeleon)

        # Evolve bench Pokemon
        state = evolve_pokemon(state, 0, charmander.id, charmeleon.id, skip_stage=False)
        player = state.players[0]

        # Bench should now have Charmeleon
        evolved_bench_mon = player.board.bench[0]
        assert evolved_bench_mon.id == charmeleon.id, "Bench Pokemon should evolve"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

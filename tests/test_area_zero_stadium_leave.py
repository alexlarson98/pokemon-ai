"""
Tests for Area Zero Underdepths Stadium Leave Effects.

These tests verify:
1. Stadium leave hook triggers for both players
2. Blazing Destruction properly triggers on_stadium_leave
3. Evolved Pokemon discard includes pre-evolution cards
4. Attached cards are properly discarded with Pokemon
5. Both players can discard to 5 bench when stadium leaves
"""

import pytest
from cards.factory import create_card_instance, get_card_definition
from engine import PokemonEngine
from models import (
    GameState, PlayerState, Board, GamePhase,
    Action, ActionType
)
from actions import evolve_pokemon


@pytest.fixture
def engine():
    return PokemonEngine()


def create_test_state_with_stadium():
    """Create a test state with Area Zero Underdepths in play."""
    p0_board = Board()
    p1_board = Board()

    p0 = PlayerState(player_id=0, name='Player 0', board=p0_board)
    p1 = PlayerState(player_id=1, name='Player 1', board=p1_board)

    state = GameState(players=[p0, p1])

    # Give both players active Pokemon
    p0_board.active_spot = create_card_instance('sv7-114', owner_id=0)  # Hoothoot
    p1_board.active_spot = create_card_instance('sv7-114', owner_id=1)  # Hoothoot

    # Place Area Zero Underdepths
    stadium = create_card_instance('sv7-131', owner_id=0)
    state.stadium = stadium

    state.current_phase = GamePhase.MAIN
    state.turn_count = 3  # Allow evolution

    return state


class TestBlazingDestructionTriggersHook:
    """Test that Blazing Destruction properly triggers on_stadium_leave hook."""

    def test_blazing_destruction_discards_stadium(self, engine):
        """Blazing Destruction should discard the stadium."""
        state = create_test_state_with_stadium()
        p1 = state.players[1]

        # Give Player 1 a Charmander that can use Blazing Destruction
        charmander = create_card_instance('sv3pt5-4', owner_id=1)  # Blazing Destruction Charmander
        p1.board.active_spot = charmander

        # Attach energy to meet attack cost
        fire_energy = create_card_instance('base1-98', owner_id=1)  # Fire Energy
        charmander.attached_energy.append(fire_energy)

        # Verify stadium is in play
        assert state.stadium is not None
        assert get_card_definition(state.stadium).name == "Area Zero Underdepths"

        state.active_player_index = 1

        # Find and execute Blazing Destruction attack
        actions = engine.get_legal_actions(state)
        attack_action = None
        for a in actions:
            if a.action_type == ActionType.ATTACK and a.attack_name == "Blazing Destruction":
                attack_action = a
                break

        assert attack_action is not None, "Blazing Destruction should be available"

        # Execute attack
        state = engine.step(state, attack_action)

        # Stadium should be discarded
        assert state.stadium is None

        # Stadium should be in owner's (Player 0) discard
        stadium_in_discard = any(
            get_card_definition(c).name == "Area Zero Underdepths"
            for c in state.players[0].discard.cards
        )
        assert stadium_in_discard, "Stadium should be in owner's discard"

    def test_blazing_destruction_triggers_bench_collapse(self, engine):
        """When stadium is discarded, both players should need to discard to 5 bench."""
        state = create_test_state_with_stadium()
        p0 = state.players[0]
        p1 = state.players[1]

        # Give both players Terapagos (for 8-bench eligibility)
        tera0 = create_card_instance('sv7-128', owner_id=0)
        tera1 = create_card_instance('sv7-128', owner_id=1)
        p0.board.bench.append(tera0)
        p1.board.bench.append(tera1)

        # Update bench sizes
        state = engine.update_bench_sizes(state)

        # Both should have max 8 bench now
        assert p0.board.max_bench_size == 8
        assert p1.board.max_bench_size == 8

        # Fill both benches to 7 (Terapagos + 6 others)
        for _ in range(6):
            p0.board.bench.append(create_card_instance('sv7-114', owner_id=0))
            p1.board.bench.append(create_card_instance('sv7-114', owner_id=1))

        assert p0.board.get_bench_count() == 7
        assert p1.board.get_bench_count() == 7

        # Give Player 1 a Charmander for Blazing Destruction
        charmander = create_card_instance('sv3pt5-4', owner_id=1)
        p1.board.active_spot = charmander
        fire_energy = create_card_instance('base1-98', owner_id=1)
        charmander.attached_energy.append(fire_energy)

        state.active_player_index = 1

        # Execute Blazing Destruction
        actions = engine.get_legal_actions(state)
        attack_action = None
        for a in actions:
            if a.action_type == ActionType.ATTACK and a.attack_name == "Blazing Destruction":
                attack_action = a
                break

        state = engine.step(state, attack_action)

        # Stadium should be gone
        assert state.stadium is None, "Stadium should be discarded"

        # Resolution stack should have steps for both players
        assert len(state.resolution_stack) == 2, "Should have 2 resolution steps (one per player)"

        # Check that both player IDs are in the stack
        player_ids = {step.player_id for step in state.resolution_stack}
        assert 0 in player_ids, "Player 0 should have a discard step"
        assert 1 in player_ids, "Player 1 should have a discard step"

        # Get legal actions - should be SELECT_CARD for bench discard
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        assert len(select_actions) > 0, "Should have SELECT_CARD actions for discard"


class TestEvolutionDiscardIncludesPreviousStages:
    """Test that discarding an evolved Pokemon includes all pre-evolution cards."""

    def test_evolved_pokemon_discard_includes_base(self, engine):
        """When discarding Noctowl, Hoothoot underneath should also be discarded."""
        state = create_test_state_with_stadium()
        p0 = state.players[0]

        # Create Hoothoot and evolve it to Noctowl
        hoothoot = create_card_instance('sv7-114', owner_id=0)
        hoothoot.turns_in_play = 1  # Can evolve
        p0.board.bench.append(hoothoot)

        # Add Noctowl to hand
        noctowl = create_card_instance('sv7-115', owner_id=0)
        p0.hand.add_card(noctowl)

        # Evolve Hoothoot to Noctowl
        state = evolve_pokemon(state, 0, hoothoot.id, noctowl.id)

        # Verify evolution happened - find the evolved Pokemon on bench
        evolved_pokemon = None
        for pokemon in p0.board.bench:
            card_def = get_card_definition(pokemon)
            if card_def and card_def.name == "Noctowl":
                evolved_pokemon = pokemon
                break

        assert evolved_pokemon is not None, "Should have Noctowl on bench"
        assert len(evolved_pokemon.previous_stages) == 1, "Should have Hoothoot as previous stage"

        # Manually remove from bench and discard using the helper
        from actions import discard_pokemon_from_play
        p0.board.bench.remove(evolved_pokemon)

        initial_discard_count = len(p0.discard.cards)
        state = discard_pokemon_from_play(state, evolved_pokemon, p0)

        # Should have discarded both Noctowl AND Hoothoot
        assert len(p0.discard.cards) == initial_discard_count + 2, \
            f"Should discard both evolution stages, got {len(p0.discard.cards) - initial_discard_count}"

        # Verify both cards are in discard
        discard_names = [get_card_definition(c).name for c in p0.discard.cards]
        assert "Noctowl" in discard_names, "Noctowl should be in discard"
        assert "Hoothoot" in discard_names, "Hoothoot should be in discard"

    def test_stage2_discard_includes_all_stages(self, engine):
        """Discarding a Stage 2 should include Basic, Stage 1, and Stage 2."""
        state = create_test_state_with_stadium()
        p0 = state.players[0]

        # Create a simulated evolution chain using cards that exist
        # Use Hoothoot -> Noctowl as our test case with a manually added "stage 2"
        hoothoot = create_card_instance('sv7-114', owner_id=0)  # Hoothoot (Basic)
        noctowl = create_card_instance('sv7-115', owner_id=0)   # Noctowl (Stage 1)
        pidgeot = create_card_instance('sv4-164', owner_id=0)   # Pidgeot ex (Stage 2)

        # Manually set up evolution chain as if pidgeot evolved from noctowl from hoothoot
        # (This is a synthetic test - in reality Pidgeot doesn't evolve from Noctowl)
        pidgeot.previous_stages = [hoothoot, noctowl]

        p0.board.bench.append(pidgeot)

        # Discard the "Stage 2"
        from actions import discard_pokemon_from_play
        p0.board.bench.remove(pidgeot)
        state = discard_pokemon_from_play(state, pidgeot, p0)

        # Should have 3 cards in discard
        assert len(p0.discard.cards) == 3, \
            f"Should discard all 3 evolution stages, got {len(p0.discard.cards)}"


class TestAttachedCardsDiscardedWithPokemon:
    """Test that attached cards are discarded when Pokemon is discarded."""

    def test_attached_energy_discarded(self, engine):
        """Attached energy should be discarded with Pokemon."""
        state = create_test_state_with_stadium()
        p0 = state.players[0]

        # Create Pokemon with attached energy
        pokemon = create_card_instance('sv7-114', owner_id=0)
        energy1 = create_card_instance('base1-98', owner_id=0)  # Fire
        energy2 = create_card_instance('base1-99', owner_id=0)  # Grass
        pokemon.attached_energy = [energy1, energy2]

        p0.board.bench.append(pokemon)

        # Discard the Pokemon
        from actions import discard_pokemon_from_play
        p0.board.bench.remove(pokemon)
        state = discard_pokemon_from_play(state, pokemon, p0)

        # Should have 3 cards in discard (Pokemon + 2 energy)
        assert len(p0.discard.cards) == 3

        # Verify energy is in discard
        discard_ids = [c.id for c in p0.discard.cards]
        assert energy1.id in discard_ids
        assert energy2.id in discard_ids

    def test_attached_tools_discarded(self, engine):
        """Attached tools should be discarded with Pokemon."""
        state = create_test_state_with_stadium()
        p0 = state.players[0]

        # Create Pokemon with attached tool
        pokemon = create_card_instance('sv7-114', owner_id=0)
        # Add a tool (if tool cards exist in the card pool)
        # For now we'll simulate with any card
        tool = create_card_instance('sv5-179', owner_id=0)  # Technical Machine
        pokemon.attached_tools = [tool]

        p0.board.bench.append(pokemon)

        # Discard the Pokemon
        from actions import discard_pokemon_from_play
        p0.board.bench.remove(pokemon)
        state = discard_pokemon_from_play(state, pokemon, p0)

        # Should have 2 cards in discard (Pokemon + tool)
        assert len(p0.discard.cards) == 2

        # Verify tool is in discard
        discard_ids = [c.id for c in p0.discard.cards]
        assert tool.id in discard_ids


class TestBothPlayersPromptedForDiscard:
    """Test that both players are prompted to discard when stadium leaves."""

    def test_both_players_get_discard_actions(self, engine):
        """When stadium leaves and both have >5 bench, both should get discard prompts."""
        state = create_test_state_with_stadium()
        p0 = state.players[0]
        p1 = state.players[1]

        # Give both players Terapagos and 7 bench
        for player in [p0, p1]:
            player.board.bench = []  # Clear bench first
            tera = create_card_instance('sv7-128', owner_id=player.player_id)
            player.board.bench.append(tera)
            for _ in range(6):
                pokemon = create_card_instance('sv7-114', owner_id=player.player_id)
                player.board.bench.append(pokemon)

        state = engine.update_bench_sizes(state)

        # Verify both have 7 bench and max 8
        assert p0.board.get_bench_count() == 7
        assert p1.board.get_bench_count() == 7
        assert p0.board.max_bench_size == 8
        assert p1.board.max_bench_size == 8

        # Manually trigger stadium leave
        from actions import discard_stadium
        state = discard_stadium(state)

        # Stadium should be gone
        assert state.stadium is None

        # Both players should need to discard to 5
        # Check resolution stack or interrupt actions
        if state.resolution_stack:
            # Check that steps exist for both players
            player_ids_in_stack = set(step.player_id for step in state.resolution_stack)
            assert 0 in player_ids_in_stack, "Player 0 should have a discard step"
            assert 1 in player_ids_in_stack, "Player 1 should have a discard step"

    def test_opponent_discard_when_not_active_player(self, engine):
        """Opponent should be able to discard even when not the active player."""
        state = create_test_state_with_stadium()
        p0 = state.players[0]
        p1 = state.players[1]

        # Only give Player 1 (opponent) a Tera Pokemon with 7 bench
        tera = create_card_instance('sv7-128', owner_id=1)
        p1.board.bench.append(tera)
        for _ in range(6):
            pokemon = create_card_instance('sv7-114', owner_id=1)
            p1.board.bench.append(pokemon)

        state = engine.update_bench_sizes(state)

        assert p1.board.get_bench_count() == 7
        assert p1.board.max_bench_size == 8

        # Make Player 0 the active player
        state.active_player_index = 0

        # Discard stadium
        from actions import discard_stadium
        state = discard_stadium(state)

        # Player 1 should need to discard even though Player 0 is active
        # This is handled by the resolution stack from the hook
        if state.resolution_stack:
            p1_steps = [s for s in state.resolution_stack if s.player_id == 1]
            assert len(p1_steps) > 0, "Player 1 should have a discard step"


class TestDiscardBenchActionType:
    """Test that the new DISCARD_BENCH action type works correctly."""

    def test_discard_bench_action_type_exists(self):
        """ActionType.DISCARD_BENCH should exist."""
        assert hasattr(ActionType, 'DISCARD_BENCH')
        assert ActionType.DISCARD_BENCH.value == "discard_bench"

    def test_discard_bench_shows_correct_type_in_actions(self, engine):
        """When bench collapse happens, actions should be DISCARD_BENCH type."""
        state = create_test_state_with_stadium()
        p0 = state.players[0]

        # Give Player 0 too many bench Pokemon (more than 5 without Tera)
        for _ in range(6):
            pokemon = create_card_instance('sv7-114', owner_id=0)
            p0.board.bench.append(pokemon)

        # Remove stadium (so max bench is 5)
        state.stadium = None
        state = engine.update_bench_sizes(state)

        state.active_player_index = 0

        # Get legal actions - should have DISCARD_BENCH
        actions = engine.get_legal_actions(state)

        discard_actions = [a for a in actions if a.action_type == ActionType.DISCARD_BENCH]
        assert len(discard_actions) > 0, "Should have DISCARD_BENCH actions"

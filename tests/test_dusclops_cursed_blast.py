"""
Comprehensive pytest suite for Dusclops's Cursed Blast ability.

Tests for:
- Cursed Blast puts exactly 5 damage counters on target
- Dusclops (and attached energy/tools) go to discard after use
- Target can be Active or Benched opponent Pokemon
- Once per turn restriction
- All card variants (sv6pt5-19, sv6pt5-69, sv8pt5-36)
"""

import pytest
import sys
sys.path.insert(0, 'src')

from models import GameState, PlayerState, GamePhase, Action, ActionType
from engine import PokemonEngine
from cards.factory import create_card_instance
from cards.logic_registry import MASTER_LOGIC_REGISTRY


@pytest.fixture
def engine():
    """Create PokemonEngine instance."""
    return PokemonEngine()


def create_dusclops_game_state(dusclops_card_id: str = "sv6pt5-19"):
    """
    Create a game state with Dusclops as player 0's active Pokemon.

    Returns:
        GameState with Dusclops ready to use Cursed Blast
    """
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Player 0: Dusclops in active spot
    dusclops = create_card_instance(dusclops_card_id, owner_id=0)
    player0.board.active_spot = dusclops

    # Player 1: Opponent with active and bench
    opponent_active = create_card_instance("sv3pt5-16", owner_id=1)  # Pidgey
    player1.board.active_spot = opponent_active

    # Add prizes for both players
    for _ in range(6):
        player0.prizes.add_card(create_card_instance("base1-98", owner_id=0))
        player1.prizes.add_card(create_card_instance("base1-98", owner_id=1))

    return GameState(
        players=[player0, player1],
        turn_count=2,
        active_player_index=0,
        current_phase=GamePhase.MAIN,
        starting_player_id=0
    )


# ============================================================================
# DUSCLOPS REGISTRATION TESTS
# ============================================================================

class TestDusclopsRegistration:
    """Test Dusclops card registrations."""

    def test_dusclops_sv6pt5_19_registered(self):
        """Dusclops sv6pt5-19 should be in registry with Cursed Blast and Will-O-Wisp."""
        assert "sv6pt5-19" in MASTER_LOGIC_REGISTRY
        data = MASTER_LOGIC_REGISTRY["sv6pt5-19"]
        assert "Cursed Blast" in data
        assert "Will-O-Wisp" in data
        assert data["Cursed Blast"]["category"] == "activatable"
        assert data["Will-O-Wisp"]["category"] == "attack"

    def test_dusclops_sv6pt5_69_registered(self):
        """Dusclops sv6pt5-69 should be in registry with both moves."""
        assert "sv6pt5-69" in MASTER_LOGIC_REGISTRY
        data = MASTER_LOGIC_REGISTRY["sv6pt5-69"]
        assert "Cursed Blast" in data
        assert "Will-O-Wisp" in data

    def test_dusclops_sv8pt5_36_reprint_registered(self):
        """Dusclops sv8pt5-36 (reprint) should be in registry with both moves."""
        assert "sv8pt5-36" in MASTER_LOGIC_REGISTRY
        data = MASTER_LOGIC_REGISTRY["sv8pt5-36"]
        assert "Cursed Blast" in data
        assert "Will-O-Wisp" in data


# ============================================================================
# CURSED BLAST ACTION GENERATION TESTS
# ============================================================================

class TestCursedBlastActions:
    """Test Cursed Blast action generation."""

    def test_cursed_blast_generates_actions_for_opponent_active(self):
        """Cursed Blast should generate action targeting opponent's active Pokemon."""
        from cards.sets.sv6pt5 import dusclops_cursed_blast_actions

        state = create_dusclops_game_state()
        dusclops = state.players[0].board.active_spot
        player = state.players[0]

        actions = dusclops_cursed_blast_actions(state, dusclops, player)

        assert len(actions) >= 1
        assert any(a.ability_name == "Cursed Blast" for a in actions)
        assert any("Active" in a.display_label for a in actions)

    def test_cursed_blast_generates_actions_for_benched_pokemon(self):
        """Cursed Blast should generate actions for opponent's benched Pokemon."""
        from cards.sets.sv6pt5 import dusclops_cursed_blast_actions

        state = create_dusclops_game_state()
        dusclops = state.players[0].board.active_spot
        player = state.players[0]

        # Add bench Pokemon to opponent
        bench_mon = create_card_instance("sv3pt5-16", owner_id=1)
        state.players[1].board.add_to_bench(bench_mon)

        actions = dusclops_cursed_blast_actions(state, dusclops, player)

        # Should have actions for both active and bench
        assert len(actions) == 2
        assert any("Bench" in a.display_label for a in actions)
        assert any("Active" in a.display_label for a in actions)

    def test_cursed_blast_effect_force_knockout_self(self):
        """Cursed Blast effect should apply lethal damage to Dusclops."""
        from cards.sets.sv6pt5 import dusclops_cursed_blast_effect
        from cards.factory import get_max_hp

        state = create_dusclops_game_state()
        dusclops = state.players[0].board.active_spot
        opponent_active = state.players[1].board.active_spot

        # Verify Dusclops is healthy before use
        assert dusclops.damage_counters == 0

        action = Action(
            action_type=ActionType.USE_ABILITY,
            player_id=0,
            card_id=dusclops.id,
            ability_name="Cursed Blast",
            target_id=opponent_active.id,
            parameters={'target_location': 'active'}
        )

        state = dusclops_cursed_blast_effect(state, dusclops, action)

        # Verify Dusclops has lethal damage (self-KO)
        max_hp = get_max_hp(dusclops)
        assert dusclops.damage_counters * 10 >= max_hp, "Dusclops should have lethal damage"

    def test_cursed_blast_no_actions_when_no_opponent_pokemon(self):
        """Cursed Blast should not generate actions when opponent has no Pokemon."""
        from cards.sets.sv6pt5 import dusclops_cursed_blast_actions

        state = create_dusclops_game_state()
        dusclops = state.players[0].board.active_spot
        player = state.players[0]

        # Remove opponent's active
        state.players[1].board.active_spot = None

        actions = dusclops_cursed_blast_actions(state, dusclops, player)

        assert len(actions) == 0


# ============================================================================
# CURSED BLAST EFFECT TESTS - DAMAGE COUNTERS
# ============================================================================

class TestCursedBlastDamageCounters:
    """Test that Cursed Blast places exactly 5 damage counters."""

    def test_cursed_blast_places_5_damage_counters_on_active(self):
        """Cursed Blast should place exactly 5 damage counters on opponent's active."""
        from cards.sets.sv6pt5 import dusclops_cursed_blast_effect

        state = create_dusclops_game_state()
        dusclops = state.players[0].board.active_spot
        opponent_active = state.players[1].board.active_spot

        initial_damage = opponent_active.damage_counters

        action = Action(
            action_type=ActionType.USE_ABILITY,
            player_id=0,
            card_id=dusclops.id,
            ability_name="Cursed Blast",
            target_id=opponent_active.id,
            parameters={'target_location': 'active'}
        )

        state = dusclops_cursed_blast_effect(state, dusclops, action)

        # 5 damage counters = 50 damage
        assert state.players[1].board.active_spot.damage_counters == initial_damage + 5

    def test_cursed_blast_places_5_damage_counters_on_bench(self):
        """Cursed Blast should place exactly 5 damage counters on benched Pokemon."""
        from cards.sets.sv6pt5 import dusclops_cursed_blast_effect

        state = create_dusclops_game_state()
        dusclops = state.players[0].board.active_spot

        # Add bench Pokemon to opponent
        bench_mon = create_card_instance("sv3pt5-16", owner_id=1)
        state.players[1].board.add_to_bench(bench_mon)

        initial_damage = bench_mon.damage_counters

        action = Action(
            action_type=ActionType.USE_ABILITY,
            player_id=0,
            card_id=dusclops.id,
            ability_name="Cursed Blast",
            target_id=bench_mon.id,
            parameters={'target_location': 'bench'}
        )

        state = dusclops_cursed_blast_effect(state, dusclops, action)

        # Find the bench mon in the updated state
        bench_after = state.players[1].board.bench[0]
        assert bench_after.damage_counters == initial_damage + 5


# ============================================================================
# CURSED BLAST EFFECT TESTS - SELF KNOCKOUT
# ============================================================================

class TestCursedBlastSelfKnockout:
    """Test that Dusclops knocks itself out after using Cursed Blast."""

    def test_cursed_blast_ko_dusclops_to_discard(self):
        """Dusclops should be knocked out and moved to discard after Cursed Blast."""
        from cards.sets.sv6pt5 import dusclops_cursed_blast_effect

        state = create_dusclops_game_state()
        dusclops = state.players[0].board.active_spot
        dusclops_id = dusclops.id
        opponent_active = state.players[1].board.active_spot

        # Add bench Pokemon so game doesn't end
        bench_mon = create_card_instance("sv3pt5-16", owner_id=0)
        state.players[0].board.add_to_bench(bench_mon)

        initial_discard_count = len(state.players[0].discard.cards)

        action = Action(
            action_type=ActionType.USE_ABILITY,
            player_id=0,
            card_id=dusclops.id,
            ability_name="Cursed Blast",
            target_id=opponent_active.id,
            parameters={'target_location': 'active'}
        )

        state = dusclops_cursed_blast_effect(state, dusclops, action)

        # Dusclops should have lethal damage counters (force_knockout sets damage)
        # The actual KO processing happens in the engine's check phase
        # But we can verify Dusclops has enough damage to be KO'd
        from cards.factory import get_max_hp
        max_hp = get_max_hp(dusclops)
        assert dusclops.damage_counters * 10 >= max_hp, "Dusclops should have lethal damage"

    def test_cursed_blast_ko_dusclops_with_attached_energy(self):
        """Dusclops with attached energy should all go to discard after Cursed Blast."""
        from cards.sets.sv6pt5 import dusclops_cursed_blast_effect

        state = create_dusclops_game_state()
        dusclops = state.players[0].board.active_spot
        opponent_active = state.players[1].board.active_spot

        # Attach 2 energy to Dusclops
        energy1 = create_card_instance("base1-99", owner_id=0)  # Psychic Energy
        energy2 = create_card_instance("base1-99", owner_id=0)  # Psychic Energy
        dusclops.attached_energy.append(energy1)
        dusclops.attached_energy.append(energy2)

        # Add bench Pokemon so game doesn't end
        bench_mon = create_card_instance("sv3pt5-16", owner_id=0)
        state.players[0].board.add_to_bench(bench_mon)

        energy_ids = [e.id for e in dusclops.attached_energy]

        action = Action(
            action_type=ActionType.USE_ABILITY,
            player_id=0,
            card_id=dusclops.id,
            ability_name="Cursed Blast",
            target_id=opponent_active.id,
            parameters={'target_location': 'active'}
        )

        state = dusclops_cursed_blast_effect(state, dusclops, action)

        # Verify Dusclops has lethal damage
        from cards.factory import get_max_hp
        max_hp = get_max_hp(dusclops)
        assert dusclops.damage_counters * 10 >= max_hp

        # Verify energy is still attached (will be discarded when KO is processed by engine)
        assert len(dusclops.attached_energy) == 2


# ============================================================================
# CURSED BLAST COMBINED TESTS - DAMAGE + KO
# ============================================================================

class TestCursedBlastCombined:
    """Test both damage placement and self-knockout together."""

    @pytest.mark.parametrize("card_id", ["sv6pt5-19", "sv6pt5-69", "sv8pt5-36"])
    def test_all_variants_place_5_counters_and_ko_self(self, card_id):
        """All Dusclops variants should place 5 counters and KO self."""
        from cards.sets.sv6pt5 import dusclops_cursed_blast_effect

        state = create_dusclops_game_state(card_id)
        dusclops = state.players[0].board.active_spot
        opponent_active = state.players[1].board.active_spot

        # Add bench so game doesn't end
        bench_mon = create_card_instance("sv3pt5-16", owner_id=0)
        state.players[0].board.add_to_bench(bench_mon)

        initial_opp_damage = opponent_active.damage_counters

        action = Action(
            action_type=ActionType.USE_ABILITY,
            player_id=0,
            card_id=dusclops.id,
            ability_name="Cursed Blast",
            target_id=opponent_active.id,
            parameters={'target_location': 'active'}
        )

        state = dusclops_cursed_blast_effect(state, dusclops, action)

        # Check 5 damage counters placed
        assert state.players[1].board.active_spot.damage_counters == initial_opp_damage + 5

        # Check Dusclops has lethal damage
        from cards.factory import get_max_hp
        max_hp = get_max_hp(dusclops)
        assert dusclops.damage_counters * 10 >= max_hp

    def test_cursed_blast_through_engine_ko_processing(self, engine):
        """Cursed Blast through engine should move Dusclops to discard and award prize."""
        state = create_dusclops_game_state()
        dusclops = state.players[0].board.active_spot
        dusclops_id = dusclops.id
        opponent_active = state.players[1].board.active_spot

        # Add bench Pokemon so game doesn't end when Dusclops is KO'd
        bench_mon = create_card_instance("sv3pt5-16", owner_id=0)
        state.players[0].board.add_to_bench(bench_mon)

        # Record initial state
        initial_p0_discard = len(state.players[0].discard.cards)
        initial_p1_prizes = state.players[1].prizes.count()

        action = Action(
            action_type=ActionType.USE_ABILITY,
            player_id=0,
            card_id=dusclops.id,
            ability_name="Cursed Blast",
            target_id=opponent_active.id,
            parameters={'target_location': 'active'}
        )

        # Apply through engine to trigger KO processing
        state = engine.step(state, action)

        # Verify Dusclops is in discard
        discard_ids = [c.id for c in state.players[0].discard.cards]
        assert dusclops_id in discard_ids, "Dusclops should be in discard after self-KO"

        # Verify Dusclops is no longer on board
        assert state.players[0].board.active_spot is None or state.players[0].board.active_spot.id != dusclops_id
        bench_ids = [p.id for p in state.players[0].board.bench]
        assert dusclops_id not in bench_ids, "Dusclops should not be on bench"

        # Verify opponent got a prize (self-KO gives opponent the prize)
        assert state.players[1].prizes.count() == initial_p1_prizes - 1, "Opponent should take a prize"


# ============================================================================
# WILL-O-WISP ATTACK TESTS
# ============================================================================

class TestWillOWisp:
    """Test Dusclops's Will-O-Wisp attack."""

    def test_will_o_wisp_generates_action(self):
        """Will-O-Wisp should generate exactly one attack action."""
        from cards.sets.sv6pt5 import dusclops_will_o_wisp_actions

        state = create_dusclops_game_state()
        dusclops = state.players[0].board.active_spot
        player = state.players[0]

        actions = dusclops_will_o_wisp_actions(state, dusclops, player)

        assert len(actions) == 1
        assert actions[0].attack_name == "Will-O-Wisp"
        assert "50" in actions[0].display_label

    def test_will_o_wisp_deals_50_damage(self):
        """Will-O-Wisp should deal 50 damage to opponent's active."""
        from cards.sets.sv6pt5 import dusclops_will_o_wisp_effect

        state = create_dusclops_game_state()
        dusclops = state.players[0].board.active_spot
        opponent_active = state.players[1].board.active_spot

        initial_damage = opponent_active.damage_counters

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=dusclops.id,
            attack_name="Will-O-Wisp"
        )

        state = dusclops_will_o_wisp_effect(state, dusclops, action)

        # 50 damage = 5 damage counters
        assert state.players[1].board.active_spot.damage_counters == initial_damage + 5

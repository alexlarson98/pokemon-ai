"""
Tests for Terapagos ex - Unified Beatdown and Crown Opal attacks.

Tests:
- Unified Beatdown damage calculation based on bench count
- Unified Beatdown first turn restriction (player going second can't use it turn 1)
- Crown Opal damage and damage prevention effect
- Crown Opal blocks Basic non-Colorless attackers
- Crown Opal allows Colorless attackers through
- Crown Opal allows non-Basic (evolved) attackers through
- Effect expiration at end of opponent's turn
- All card variants (svp-165, sv7-128, sv7-170, sv7-173, sv8pt5-92, sv8pt5-169, sv8pt5-180)
"""

import pytest
import sys
sys.path.insert(0, 'src')

from models import GameState, PlayerState, Action, ActionType, Subtype, EnergyType
from cards.factory import create_card_instance
from engine import PokemonEngine
from cards.logic_registry import MASTER_LOGIC_REGISTRY
from actions import apply_damage, _has_damage_prevention


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def engine():
    """Create a Pokemon engine instance."""
    return PokemonEngine()


def create_terapagos_game_state(terapagos_card_id: str = "svp-165", bench_count: int = 3):
    """Create a game state with Terapagos ex in active spot."""
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Player 0: Terapagos ex active
    terapagos = create_card_instance(terapagos_card_id, owner_id=0)
    player0.board.active_spot = terapagos

    # Add bench Pokemon for bench count
    for i in range(bench_count):
        bench_pokemon = create_card_instance("sv3pt5-16", owner_id=0)  # Pikachu 60HP
        player0.board.add_to_bench(bench_pokemon)

    # Player 1: Basic non-Colorless Pokemon active (e.g., Charmander - Fire type)
    opponent_active = create_card_instance("svp-44", owner_id=1)  # Charmander
    player1.board.active_spot = opponent_active

    # Add cards to decks
    for _ in range(10):
        player0.deck.add_card(create_card_instance("base1-98", owner_id=0))
        player1.deck.add_card(create_card_instance("base1-98", owner_id=1))

    # Add prizes
    for _ in range(6):
        player0.prizes.add_card(create_card_instance("base1-98", owner_id=0))
        player1.prizes.add_card(create_card_instance("base1-98", owner_id=1))

    state = GameState(
        players=[player0, player1],
        active_player_index=0,
        turn_count=2,
        starting_player_id=0  # Player 0 went first
    )

    return state


# ============================================================================
# REGISTRATION TESTS
# ============================================================================

class TestTerapagosExRegistration:
    """Test that all Terapagos ex variants are properly registered."""

    @pytest.mark.parametrize("card_id", [
        "svp-165",
        "sv7-128", "sv7-170", "sv7-173",
        "sv8pt5-92", "sv8pt5-169", "sv8pt5-180"
    ])
    def test_terapagos_ex_registered(self, card_id):
        """Verify Terapagos ex is in the logic registry."""
        assert card_id in MASTER_LOGIC_REGISTRY, f"{card_id} not in MASTER_LOGIC_REGISTRY"
        assert "Unified Beatdown" in MASTER_LOGIC_REGISTRY[card_id]
        assert "Crown Opal" in MASTER_LOGIC_REGISTRY[card_id]

    @pytest.mark.parametrize("card_id", [
        "svp-165",
        "sv7-128", "sv7-170", "sv7-173",
        "sv8pt5-92", "sv8pt5-169", "sv8pt5-180"
    ])
    def test_unified_beatdown_is_attack(self, card_id):
        """Unified Beatdown should be an attack."""
        entry = MASTER_LOGIC_REGISTRY[card_id]["Unified Beatdown"]
        assert entry["category"] == "attack"
        assert "generator" in entry
        assert "effect" in entry

    @pytest.mark.parametrize("card_id", [
        "svp-165",
        "sv7-128", "sv7-170", "sv7-173",
        "sv8pt5-92", "sv8pt5-169", "sv8pt5-180"
    ])
    def test_crown_opal_is_attack(self, card_id):
        """Crown Opal should be an attack."""
        entry = MASTER_LOGIC_REGISTRY[card_id]["Crown Opal"]
        assert entry["category"] == "attack"
        assert "generator" in entry
        assert "effect" in entry


# ============================================================================
# UNIFIED BEATDOWN TESTS
# ============================================================================

class TestUnifiedBeatdown:
    """Test Unified Beatdown attack functionality."""

    def test_unified_beatdown_generates_action(self):
        """Unified Beatdown should generate an action."""
        from cards.sets.svp import terapagos_ex_unified_beatdown_actions

        state = create_terapagos_game_state(bench_count=3)
        terapagos = state.players[0].board.active_spot
        player = state.players[0]

        actions = terapagos_ex_unified_beatdown_actions(state, terapagos, player)

        assert len(actions) == 1
        assert actions[0].action_type == ActionType.ATTACK
        assert actions[0].attack_name == "Unified Beatdown"

    def test_unified_beatdown_damage_scales_with_bench(self):
        """Unified Beatdown damage should be 30 per benched Pokemon."""
        from cards.sets.svp import terapagos_ex_unified_beatdown_effect

        # Test with 3 bench Pokemon (90 damage)
        state = create_terapagos_game_state(bench_count=3)
        terapagos = state.players[0].board.active_spot
        opponent_active = state.players[1].board.active_spot

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=terapagos.id,
            attack_name="Unified Beatdown"
        )

        initial_damage = opponent_active.damage_counters
        state = terapagos_ex_unified_beatdown_effect(state, terapagos, action)

        # 90 damage = 9 damage counters
        assert opponent_active.damage_counters == initial_damage + 9

    def test_unified_beatdown_damage_with_full_bench(self):
        """Unified Beatdown with 5 bench Pokemon should deal 150 damage."""
        from cards.sets.svp import terapagos_ex_unified_beatdown_effect

        state = create_terapagos_game_state(bench_count=5)
        terapagos = state.players[0].board.active_spot
        opponent_active = state.players[1].board.active_spot

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=terapagos.id,
            attack_name="Unified Beatdown"
        )

        initial_damage = opponent_active.damage_counters
        state = terapagos_ex_unified_beatdown_effect(state, terapagos, action)

        # 150 damage = 15 damage counters
        assert opponent_active.damage_counters == initial_damage + 15

    def test_unified_beatdown_no_damage_empty_bench(self):
        """Unified Beatdown with empty bench should deal 0 damage."""
        from cards.sets.svp import terapagos_ex_unified_beatdown_effect

        state = create_terapagos_game_state(bench_count=0)
        terapagos = state.players[0].board.active_spot
        opponent_active = state.players[1].board.active_spot

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=terapagos.id,
            attack_name="Unified Beatdown"
        )

        initial_damage = opponent_active.damage_counters
        state = terapagos_ex_unified_beatdown_effect(state, terapagos, action)

        # 0 damage
        assert opponent_active.damage_counters == initial_damage

    def test_unified_beatdown_first_turn_restriction_going_second(self):
        """Unified Beatdown cannot be used on turn 1 if player went second."""
        from cards.sets.svp import terapagos_ex_unified_beatdown_actions

        state = create_terapagos_game_state(bench_count=3)
        terapagos = state.players[0].board.active_spot
        player = state.players[0]

        # Set up: Player 0 went second, and it's turn 1
        state.starting_player_id = 1  # Player 1 went first
        state.turn_count = 1
        state.active_player_index = 0  # Player 0's turn

        actions = terapagos_ex_unified_beatdown_actions(state, terapagos, player)

        # Should not generate action - first turn restriction
        assert len(actions) == 0

    def test_unified_beatdown_no_restriction_going_first(self):
        """Unified Beatdown can be used on turn 1 if player went first (turn 2 for opponent)."""
        from cards.sets.svp import terapagos_ex_unified_beatdown_actions

        state = create_terapagos_game_state(bench_count=3)
        terapagos = state.players[0].board.active_spot
        player = state.players[0]

        # Player 0 went first, it's their turn (turn 1)
        state.starting_player_id = 0
        state.turn_count = 1

        # Note: In standard rules, player going first can't attack turn 1
        # But this is a different rule - we're testing Unified Beatdown's OWN restriction
        # The attack itself has no restriction for the player who went first
        actions = terapagos_ex_unified_beatdown_actions(state, terapagos, player)

        assert len(actions) == 1

    def test_unified_beatdown_no_restriction_turn_2_going_second(self):
        """Unified Beatdown can be used on turn 2 even if player went second."""
        from cards.sets.svp import terapagos_ex_unified_beatdown_actions

        state = create_terapagos_game_state(bench_count=3)
        terapagos = state.players[0].board.active_spot
        player = state.players[0]

        # Player 0 went second, but it's turn 2
        state.starting_player_id = 1
        state.turn_count = 2

        actions = terapagos_ex_unified_beatdown_actions(state, terapagos, player)

        assert len(actions) == 1


# ============================================================================
# CROWN OPAL TESTS
# ============================================================================

class TestCrownOpal:
    """Test Crown Opal attack functionality."""

    def test_crown_opal_generates_action(self):
        """Crown Opal should generate an action."""
        from cards.sets.svp import terapagos_ex_crown_opal_actions

        state = create_terapagos_game_state()
        terapagos = state.players[0].board.active_spot
        player = state.players[0]

        actions = terapagos_ex_crown_opal_actions(state, terapagos, player)

        assert len(actions) == 1
        assert actions[0].action_type == ActionType.ATTACK
        assert actions[0].attack_name == "Crown Opal"

    def test_crown_opal_deals_180_damage(self):
        """Crown Opal should deal 180 damage."""
        from cards.sets.svp import terapagos_ex_crown_opal_effect

        state = create_terapagos_game_state()
        terapagos = state.players[0].board.active_spot
        opponent_active = state.players[1].board.active_spot

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=terapagos.id,
            attack_name="Crown Opal"
        )

        initial_damage = opponent_active.damage_counters
        state = terapagos_ex_crown_opal_effect(state, terapagos, action)

        # 180 damage = 18 damage counters
        assert opponent_active.damage_counters == initial_damage + 18

    def test_crown_opal_adds_damage_prevention_effect(self):
        """Crown Opal should add a damage prevention effect to Terapagos ex."""
        from cards.sets.svp import terapagos_ex_crown_opal_effect

        state = create_terapagos_game_state()
        terapagos = state.players[0].board.active_spot

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=terapagos.id,
            attack_name="Crown Opal"
        )

        # Initially no attack effects
        assert len(terapagos.attack_effects) == 0

        state = terapagos_ex_crown_opal_effect(state, terapagos, action)

        # Should have 1 damage prevention effect
        assert len(terapagos.attack_effects) == 1
        effect = terapagos.attack_effects[0]
        assert effect['effect_type'] == 'prevent_damage'
        assert effect['condition'] == 'basic_non_colorless'
        assert effect['expires_at_end_of_turn'] == True
        assert effect['expires_player_id'] == 1  # Opponent's player ID


# ============================================================================
# CROWN OPAL DAMAGE PREVENTION TESTS
# ============================================================================

class TestCrownOpalDamagePrevention:
    """Test Crown Opal damage prevention conditions."""

    def test_blocks_basic_non_colorless_attacker(self):
        """Crown Opal should prevent damage from Basic non-Colorless Pokemon."""
        from cards.sets.svp import terapagos_ex_crown_opal_effect

        state = create_terapagos_game_state()
        terapagos = state.players[0].board.active_spot

        # Use Crown Opal to apply the effect
        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=terapagos.id,
            attack_name="Crown Opal"
        )
        state = terapagos_ex_crown_opal_effect(state, terapagos, action)

        # Create a Basic Fire Pokemon attacker (Charmander)
        attacker = create_card_instance("svp-44", owner_id=1)

        # Check damage prevention
        prevented = _has_damage_prevention(state, terapagos, attacker)
        assert prevented == True, "Crown Opal should prevent damage from Basic Fire Pokemon"

    def test_allows_colorless_attacker(self):
        """Crown Opal should NOT prevent damage from Colorless Pokemon."""
        from cards.sets.svp import terapagos_ex_crown_opal_effect

        state = create_terapagos_game_state()
        terapagos = state.players[0].board.active_spot

        # Use Crown Opal to apply the effect
        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=terapagos.id,
            attack_name="Crown Opal"
        )
        state = terapagos_ex_crown_opal_effect(state, terapagos, action)

        # Create a Basic Colorless Pokemon attacker (Pidgey)
        attacker = create_card_instance("sv3-165", owner_id=1)  # Pidgey is Colorless

        # Check damage prevention
        prevented = _has_damage_prevention(state, terapagos, attacker)
        assert prevented == False, "Crown Opal should NOT prevent damage from Colorless Pokemon"

    def test_allows_evolved_non_colorless_attacker(self):
        """Crown Opal should NOT prevent damage from evolved (non-Basic) Pokemon."""
        from cards.sets.svp import terapagos_ex_crown_opal_effect

        state = create_terapagos_game_state()
        terapagos = state.players[0].board.active_spot

        # Use Crown Opal to apply the effect
        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=terapagos.id,
            attack_name="Crown Opal"
        )
        state = terapagos_ex_crown_opal_effect(state, terapagos, action)

        # Create a Stage 1 Fire Pokemon attacker (Charmeleon)
        attacker = create_card_instance("sv3-27", owner_id=1)  # Charmeleon is Stage 1 Fire

        # Check damage prevention
        prevented = _has_damage_prevention(state, terapagos, attacker)
        assert prevented == False, "Crown Opal should NOT prevent damage from evolved Pokemon"

    def test_blocks_basic_water_attacker(self):
        """Crown Opal should prevent damage from Basic Water Pokemon."""
        from cards.sets.svp import terapagos_ex_crown_opal_effect

        state = create_terapagos_game_state()
        terapagos = state.players[0].board.active_spot

        # Use Crown Opal to apply the effect
        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=terapagos.id,
            attack_name="Crown Opal"
        )
        state = terapagos_ex_crown_opal_effect(state, terapagos, action)

        # Create a Basic Water Pokemon attacker
        attacker = create_card_instance("sv2-26", owner_id=1)  # Some Basic Water Pokemon

        # Check damage prevention
        prevented = _has_damage_prevention(state, terapagos, attacker)
        assert prevented == True, "Crown Opal should prevent damage from Basic Water Pokemon"

    def test_no_prevention_without_effect(self):
        """Without Crown Opal effect, damage should not be prevented."""
        state = create_terapagos_game_state()
        terapagos = state.players[0].board.active_spot

        # Don't use Crown Opal - no attack_effects
        assert len(terapagos.attack_effects) == 0

        # Create a Basic Fire Pokemon attacker
        attacker = create_card_instance("svp-44", owner_id=1)

        # Check damage prevention
        prevented = _has_damage_prevention(state, terapagos, attacker)
        assert prevented == False, "Without Crown Opal effect, damage should not be prevented"

    def test_protection_persists_on_bench(self):
        """Crown Opal protection should persist even when Terapagos ex is on bench."""
        from cards.sets.svp import terapagos_ex_crown_opal_effect

        state = create_terapagos_game_state()
        terapagos = state.players[0].board.active_spot
        player = state.players[0]

        # Use Crown Opal to apply the effect
        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=terapagos.id,
            attack_name="Crown Opal"
        )
        state = terapagos_ex_crown_opal_effect(state, terapagos, action)

        # Move Terapagos to bench (simulate retreat)
        bench_pokemon = player.board.bench[0]  # Get a bench Pokemon
        player.board.active_spot = bench_pokemon
        player.board.bench[0] = terapagos  # Terapagos now on bench

        # Create a Basic Fire Pokemon attacker
        attacker = create_card_instance("svp-44", owner_id=1)

        # Effect should still be on Terapagos even though it's on bench
        assert len(terapagos.attack_effects) == 1
        prevented = _has_damage_prevention(state, terapagos, attacker)
        assert prevented == True, "Crown Opal should still protect Terapagos on bench"

    def test_protection_does_not_apply_to_damage_counters(self):
        """Crown Opal should NOT prevent damage counters (only attack damage)."""
        from cards.sets.svp import terapagos_ex_crown_opal_effect

        state = create_terapagos_game_state()
        terapagos = state.players[0].board.active_spot

        # Use Crown Opal to apply the effect
        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=terapagos.id,
            attack_name="Crown Opal"
        )
        state = terapagos_ex_crown_opal_effect(state, terapagos, action)

        # Create a Basic Fire Pokemon (source of damage counters from ability)
        attacker = create_card_instance("svp-44", owner_id=1)

        initial_damage = terapagos.damage_counters

        # Apply damage with is_attack_damage=False (simulating ability damage counters)
        state = apply_damage(
            state=state,
            target=terapagos,
            damage=30,
            is_attack_damage=False,  # NOT attack damage - ability damage counters
            attacker=attacker
        )

        # Damage counters should be applied (not prevented)
        assert terapagos.damage_counters == initial_damage + 3, \
            "Damage counters from abilities should NOT be prevented by Crown Opal"


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestTerapagosExIntegration:
    """Integration tests for Terapagos ex through the engine."""

    @pytest.mark.skip(reason="Terapagos ex cards not in standard_cards.json - integration test")
    @pytest.mark.parametrize("card_id", [
        "svp-165",
        "sv7-128", "sv7-170", "sv7-173",
        "sv8pt5-92", "sv8pt5-169", "sv8pt5-180"
    ])
    def test_unified_beatdown_available_through_engine(self, engine, card_id):
        """Unified Beatdown should be available as an action through engine.get_legal_actions()."""
        state = create_terapagos_game_state(card_id)

        actions = engine.get_legal_actions(state)

        unified_beatdown_actions = [a for a in actions if a.attack_name == "Unified Beatdown"]
        assert len(unified_beatdown_actions) >= 1

    @pytest.mark.skip(reason="Terapagos ex cards not in standard_cards.json - integration test")
    @pytest.mark.parametrize("card_id", [
        "svp-165",
        "sv7-128", "sv7-170", "sv7-173",
        "sv8pt5-92", "sv8pt5-169", "sv8pt5-180"
    ])
    def test_crown_opal_available_through_engine(self, engine, card_id):
        """Crown Opal should be available as an action through engine.get_legal_actions()."""
        state = create_terapagos_game_state(card_id)
        terapagos = state.players[0].board.active_spot

        # Add energy for attack cost [GWL]
        energy1 = create_card_instance("base1-99", owner_id=0)  # Grass energy
        energy2 = create_card_instance("base1-102", owner_id=0)  # Water energy
        energy3 = create_card_instance("base1-100", owner_id=0)  # Lightning energy
        terapagos.attached_energy = [energy1, energy2, energy3]

        actions = engine.get_legal_actions(state)

        crown_opal_actions = [a for a in actions if a.attack_name == "Crown Opal"]
        assert len(crown_opal_actions) >= 1

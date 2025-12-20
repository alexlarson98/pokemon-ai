"""
Comprehensive pytest suite for Pokemon attack and ability implementations.

Tests for:
- Duskull (Come and Get You, Mumble)
- Hoothoot (Silent Wing, Triple Stab, Tackle)
- Charmeleon (Heat Tackle, Combustion, Fire Blast, Steady Firebreathing, Flare Veil)
"""

import pytest
import sys
sys.path.insert(0, 'src')

from models import GameState, PlayerState, GamePhase, Action, ActionType, StatusCondition
from engine import PokemonEngine
from cards.factory import create_card_instance
from cards.logic_registry import get_card_logic, get_card_guard, MASTER_LOGIC_REGISTRY


@pytest.fixture
def engine():
    """Create PokemonEngine instance."""
    return PokemonEngine()


@pytest.fixture
def basic_game_state():
    """Create a basic game state with two players."""
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Give both players an active Pokemon (Pidgey for simplicity)
    player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)  # Pidgey
    player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)  # Pidgey

    return GameState(
        players=[player0, player1],
        turn_count=2,
        active_player_index=0,
        current_phase=GamePhase.MAIN,
        starting_player_id=0
    )


# ============================================================================
# DUSKULL TESTS
# ============================================================================

class TestDuskullRegistration:
    """Test Duskull card registrations."""

    def test_duskull_sv6pt5_18_registered(self):
        """Duskull sv6pt5-18 should be in registry with both attacks."""
        assert "sv6pt5-18" in MASTER_LOGIC_REGISTRY
        data = MASTER_LOGIC_REGISTRY["sv6pt5-18"]
        assert "Come and Get You" in data
        assert "Mumble" in data

    def test_duskull_sv6pt5_68_registered(self):
        """Duskull sv6pt5-68 should be in registry with both attacks."""
        assert "sv6pt5-68" in MASTER_LOGIC_REGISTRY
        data = MASTER_LOGIC_REGISTRY["sv6pt5-68"]
        assert "Come and Get You" in data
        assert "Mumble" in data

    def test_duskull_sv8pt5_35_reprint_registered(self):
        """Duskull sv8pt5-35 (reprint) should be in registry with both attacks."""
        assert "sv8pt5-35" in MASTER_LOGIC_REGISTRY
        data = MASTER_LOGIC_REGISTRY["sv8pt5-35"]
        assert "Come and Get You" in data
        assert "Mumble" in data


class TestDuskullMumble:
    """Test Duskull's Mumble attack."""

    def test_mumble_generates_action(self):
        """Mumble should generate exactly one attack action."""
        from cards.sets.sv6pt5 import duskull_mumble_actions

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        duskull = create_card_instance("sv6pt5-18", owner_id=0)
        player0.board.active_spot = duskull
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        actions = duskull_mumble_actions(state, duskull, player0)

        assert len(actions) == 1
        assert actions[0].attack_name == "Mumble"
        assert "30" in actions[0].display_label

    def test_mumble_deals_30_damage(self):
        """Mumble should deal 30 damage to opponent's active."""
        from cards.sets.sv6pt5 import duskull_mumble_effect

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        duskull = create_card_instance("sv6pt5-18", owner_id=0)
        player0.board.active_spot = duskull
        defender = create_card_instance("sv3pt5-16", owner_id=1)
        player1.board.active_spot = defender

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        initial_damage = defender.damage_counters
        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=duskull.id,
            attack_name="Mumble"
        )

        state = duskull_mumble_effect(state, duskull, action)

        # 30 damage = 3 damage counters
        assert state.players[1].board.active_spot.damage_counters == initial_damage + 3


class TestDuskullComeAndGetYou:
    """Test Duskull's Come and Get You attack."""

    def test_come_and_get_you_no_duskull_in_discard(self):
        """With no Duskull in discard, should only offer 'find nothing' action."""
        from cards.sets.sv6pt5 import duskull_come_and_get_you_actions

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        duskull = create_card_instance("sv6pt5-18", owner_id=0)
        player0.board.active_spot = duskull
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        actions = duskull_come_and_get_you_actions(state, duskull, player0)

        assert len(actions) == 1
        assert "find nothing" in actions[0].display_label.lower()

    def test_come_and_get_you_with_duskull_in_discard(self):
        """With Duskull in discard, should offer options to retrieve them."""
        from cards.sets.sv6pt5 import duskull_come_and_get_you_actions

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        duskull = create_card_instance("sv6pt5-18", owner_id=0)
        player0.board.active_spot = duskull
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        # Add 2 Duskull to discard
        discard_duskull1 = create_card_instance("sv6pt5-18", owner_id=0)
        discard_duskull2 = create_card_instance("sv6pt5-68", owner_id=0)
        player0.discard.add_card(discard_duskull1)
        player0.discard.add_card(discard_duskull2)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        actions = duskull_come_and_get_you_actions(state, duskull, player0)

        # Should have: find nothing, 1 Duskull, 2 Duskull
        assert len(actions) == 3
        labels = [a.display_label for a in actions]
        assert any("find nothing" in l.lower() for l in labels)
        assert any("1 Duskull" in l for l in labels)
        assert any("2 Duskull" in l for l in labels)

    def test_come_and_get_you_effect_moves_duskull_to_bench(self):
        """Come and Get You should move Duskull from discard to bench."""
        from cards.sets.sv6pt5 import duskull_come_and_get_you_effect

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        duskull = create_card_instance("sv6pt5-18", owner_id=0)
        player0.board.active_spot = duskull
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        # Add Duskull to discard
        discard_duskull = create_card_instance("sv6pt5-18", owner_id=0)
        player0.discard.add_card(discard_duskull)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=duskull.id,
            attack_name="Come and Get You",
            parameters={'target_duskull_ids': [discard_duskull.id]}
        )

        initial_bench_count = player0.board.get_bench_count()
        initial_discard_count = len(player0.discard.cards)

        state = duskull_come_and_get_you_effect(state, duskull, action)

        # Duskull should be on bench
        assert state.players[0].board.get_bench_count() == initial_bench_count + 1
        # Duskull should be removed from discard
        assert len(state.players[0].discard.cards) == initial_discard_count - 1

    def test_come_and_get_you_respects_bench_limit(self):
        """Come and Get You should respect bench size limit."""
        from cards.sets.sv6pt5 import duskull_come_and_get_you_actions

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        duskull = create_card_instance("sv6pt5-18", owner_id=0)
        player0.board.active_spot = duskull
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        # Fill the bench (5 Pokemon)
        for i in range(5):
            bench_mon = create_card_instance("sv3pt5-16", owner_id=0)
            player0.board.add_to_bench(bench_mon)

        # Add Duskull to discard
        discard_duskull = create_card_instance("sv6pt5-18", owner_id=0)
        player0.discard.add_card(discard_duskull)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        actions = duskull_come_and_get_you_actions(state, duskull, player0)

        # With full bench, should only offer "find nothing"
        assert len(actions) == 1
        assert "find nothing" in actions[0].display_label.lower()


# ============================================================================
# HOOTHOOT TESTS
# ============================================================================

class TestHoothootRegistration:
    """Test Hoothoot card registrations."""

    def test_hoothoot_sv5_126_silent_wing(self):
        """Hoothoot sv5-126 should have Silent Wing attack."""
        assert "sv5-126" in MASTER_LOGIC_REGISTRY
        data = MASTER_LOGIC_REGISTRY["sv5-126"]
        assert "Silent Wing" in data

    def test_hoothoot_sv7_114_triple_stab(self):
        """Hoothoot sv7-114 should have Triple Stab attack."""
        assert "sv7-114" in MASTER_LOGIC_REGISTRY
        data = MASTER_LOGIC_REGISTRY["sv7-114"]
        assert "Triple Stab" in data

    def test_hoothoot_sv8pt5_77_tackle_and_insomnia(self):
        """Hoothoot sv8pt5-77 should have Tackle attack and Insomnia guard."""
        assert "sv8pt5-77" in MASTER_LOGIC_REGISTRY
        data = MASTER_LOGIC_REGISTRY["sv8pt5-77"]
        assert "Tackle" in data
        # Check for Insomnia guard using unified schema
        assert "Insomnia" in data
        assert data["Insomnia"]["category"] == "guard"
        assert data["Insomnia"]["guard_type"] == "status_condition"


class TestHoothootSilentWing:
    """Test Hoothoot's Silent Wing attack."""

    def test_silent_wing_generates_action(self):
        """Silent Wing should generate exactly one attack action."""
        from cards.sets.sv5 import hoothoot_silent_wing_actions

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        hoothoot = create_card_instance("sv5-126", owner_id=0)
        player0.board.active_spot = hoothoot
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        actions = hoothoot_silent_wing_actions(state, hoothoot, player0)

        assert len(actions) == 1
        assert actions[0].attack_name == "Silent Wing"

    def test_silent_wing_deals_damage_and_reveals_hand(self):
        """Silent Wing should deal 20 damage and reveal opponent's hand."""
        from cards.sets.sv5 import hoothoot_silent_wing_effect

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        hoothoot = create_card_instance("sv5-126", owner_id=0)
        player0.board.active_spot = hoothoot
        defender = create_card_instance("sv3pt5-16", owner_id=1)
        player1.board.active_spot = defender

        # Add cards to opponent's hand
        hand_card1 = create_card_instance("sv3pt5-16", owner_id=1)
        hand_card2 = create_card_instance("sv3pt5-16", owner_id=1)
        player1.hand.add_card(hand_card1)
        player1.hand.add_card(hand_card2)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=hoothoot.id,
            attack_name="Silent Wing"
        )

        state = hoothoot_silent_wing_effect(state, hoothoot, action)

        # Check damage (20 damage = 2 damage counters)
        assert state.players[1].board.active_spot.damage_counters == 2

        # Check hand is revealed
        for card in state.players[1].hand.cards:
            assert card.is_revealed is True


class TestHoothootTripleStab:
    """Test Hoothoot's Triple Stab attack."""

    def test_triple_stab_generates_action(self):
        """Triple Stab should generate exactly one attack action."""
        from cards.sets.sv7 import hoothoot_triple_stab_actions

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        hoothoot = create_card_instance("sv7-114", owner_id=0)
        player0.board.active_spot = hoothoot
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        actions = hoothoot_triple_stab_actions(state, hoothoot, player0)

        assert len(actions) == 1
        assert actions[0].attack_name == "Triple Stab"

    def test_triple_stab_effect_deals_variable_damage(self):
        """Triple Stab effect should deal 0-30 damage based on coin flips."""
        from cards.sets.sv7 import hoothoot_triple_stab_effect

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        hoothoot = create_card_instance("sv7-114", owner_id=0)
        player0.board.active_spot = hoothoot
        defender = create_card_instance("sv3pt5-16", owner_id=1)
        player1.board.active_spot = defender

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=hoothoot.id,
            attack_name="Triple Stab"
        )

        # Run multiple times to verify it works (coin flip is random)
        state = hoothoot_triple_stab_effect(state, hoothoot, action)

        # Damage should be 0, 10, 20, or 30 (0-3 heads * 10)
        damage = state.players[1].board.active_spot.damage_counters
        assert damage in [0, 1, 2, 3]  # 0, 10, 20, or 30 damage


# ============================================================================
# CHARMELEON TESTS
# ============================================================================

class TestCharmeleonRegistration:
    """Test Charmeleon card registrations."""

    def test_charmeleon_sv3_27_heat_tackle(self):
        """Charmeleon sv3-27 should have Heat Tackle attack."""
        assert "sv3-27" in MASTER_LOGIC_REGISTRY
        data = MASTER_LOGIC_REGISTRY["sv3-27"]
        assert "Heat Tackle" in data

    def test_charmeleon_sv3pt5_5_combustion_fire_blast(self):
        """Charmeleon sv3pt5-5 should have Combustion and Fire Blast attacks."""
        assert "sv3pt5-5" in MASTER_LOGIC_REGISTRY
        data = MASTER_LOGIC_REGISTRY["sv3pt5-5"]
        assert "Combustion" in data
        assert "Fire Blast" in data

    def test_charmeleon_sv4pt5_8_combustion_flare_veil(self):
        """Charmeleon sv4pt5-8 should have Combustion attack and Flare Veil guard."""
        assert "sv4pt5-8" in MASTER_LOGIC_REGISTRY
        data = MASTER_LOGIC_REGISTRY["sv4pt5-8"]
        assert "Combustion" in data
        # Check for Flare Veil guard using unified schema
        assert "Flare Veil" in data
        assert data["Flare Veil"]["category"] == "guard"
        assert data["Flare Veil"]["guard_type"] == "effect_prevention"

    def test_charmeleon_me2_12_steady_firebreathing(self):
        """Charmeleon me2-12 should have Steady Firebreathing attack."""
        assert "me2-12" in MASTER_LOGIC_REGISTRY
        data = MASTER_LOGIC_REGISTRY["me2-12"]
        assert "Steady Firebreathing" in data


class TestCharmeleonHeatTackle:
    """Test Charmeleon's Heat Tackle attack (sv3-27)."""

    def test_heat_tackle_generates_action(self):
        """Heat Tackle should generate exactly one attack action."""
        from cards.sets.sv3 import charmeleon_heat_tackle_actions

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        charmeleon = create_card_instance("sv3-27", owner_id=0)
        player0.board.active_spot = charmeleon
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        actions = charmeleon_heat_tackle_actions(state, charmeleon, player0)

        assert len(actions) == 1
        assert actions[0].attack_name == "Heat Tackle"
        assert "70" in actions[0].display_label
        assert "20" in actions[0].display_label  # Recoil damage mentioned

    def test_heat_tackle_deals_70_damage_and_20_recoil(self):
        """Heat Tackle should deal 70 damage to opponent and 20 to self."""
        from cards.sets.sv3 import charmeleon_heat_tackle_effect

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        charmeleon = create_card_instance("sv3-27", owner_id=0)
        player0.board.active_spot = charmeleon
        defender = create_card_instance("sv3pt5-16", owner_id=1)
        player1.board.active_spot = defender

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=charmeleon.id,
            attack_name="Heat Tackle"
        )

        state = charmeleon_heat_tackle_effect(state, charmeleon, action)

        # Opponent takes 70 damage (7 damage counters)
        assert state.players[1].board.active_spot.damage_counters == 7
        # Charmeleon takes 20 recoil (2 damage counters)
        assert state.players[0].board.active_spot.damage_counters == 2


class TestCharmeleonCombustion:
    """Test Charmeleon's Combustion attacks (different versions)."""

    def test_combustion_v2_deals_20_damage(self):
        """Combustion (sv3pt5) should deal 20 damage."""
        from cards.sets.sv3pt5 import charmeleon_combustion_effect

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        charmeleon = create_card_instance("sv3pt5-5", owner_id=0)
        player0.board.active_spot = charmeleon
        defender = create_card_instance("sv3pt5-16", owner_id=1)
        player1.board.active_spot = defender

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=charmeleon.id,
            attack_name="Combustion"
        )

        state = charmeleon_combustion_effect(state, charmeleon, action)

        # 20 damage = 2 damage counters
        assert state.players[1].board.active_spot.damage_counters == 2

    def test_combustion_v3_deals_50_damage(self):
        """Combustion (sv4pt5) should deal 50 damage."""
        from cards.sets.sv4pt5 import charmeleon_v3_combustion_effect

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        charmeleon = create_card_instance("sv4pt5-8", owner_id=0)
        player0.board.active_spot = charmeleon
        defender = create_card_instance("sv3pt5-16", owner_id=1)
        player1.board.active_spot = defender

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=charmeleon.id,
            attack_name="Combustion"
        )

        state = charmeleon_v3_combustion_effect(state, charmeleon, action)

        # 50 damage = 5 damage counters
        assert state.players[1].board.active_spot.damage_counters == 5


class TestCharmeleonFireBlast:
    """Test Charmeleon's Fire Blast attack (sv3pt5)."""

    def test_fire_blast_requires_energy(self):
        """Fire Blast should not generate actions without energy."""
        from cards.sets.sv3pt5 import charmeleon_fire_blast_actions

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        charmeleon = create_card_instance("sv3pt5-5", owner_id=0)
        player0.board.active_spot = charmeleon
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        # No energy attached
        actions = charmeleon_fire_blast_actions(state, charmeleon, player0)

        assert len(actions) == 0

    def test_fire_blast_generates_action_with_energy(self):
        """Fire Blast should generate action when energy is attached."""
        from cards.sets.sv3pt5 import charmeleon_fire_blast_actions

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        charmeleon = create_card_instance("sv3pt5-5", owner_id=0)
        player0.board.active_spot = charmeleon
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        # Attach energy
        energy = create_card_instance("sve-2", owner_id=0)  # Fire Energy
        charmeleon.attached_energy.append(energy)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        actions = charmeleon_fire_blast_actions(state, charmeleon, player0)

        assert len(actions) == 1
        assert actions[0].attack_name == "Fire Blast"

    def test_fire_blast_deals_90_and_discards_energy(self):
        """Fire Blast should deal 90 damage and discard an energy."""
        from cards.sets.sv3pt5 import charmeleon_fire_blast_effect

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        charmeleon = create_card_instance("sv3pt5-5", owner_id=0)
        player0.board.active_spot = charmeleon
        defender = create_card_instance("sv3pt5-16", owner_id=1)
        player1.board.active_spot = defender

        # Attach 3 energy (attack cost)
        energy1 = create_card_instance("sve-2", owner_id=0)
        energy2 = create_card_instance("sve-2", owner_id=0)
        energy3 = create_card_instance("sve-2", owner_id=0)
        charmeleon.attached_energy.extend([energy1, energy2, energy3])

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=charmeleon.id,
            attack_name="Fire Blast",
            parameters={'discard_energy_id': energy1.id}
        )

        initial_energy_count = len(charmeleon.attached_energy)
        state = charmeleon_fire_blast_effect(state, charmeleon, action)

        # 90 damage = 9 damage counters
        assert state.players[1].board.active_spot.damage_counters == 9
        # One energy discarded
        assert len(state.players[0].board.active_spot.attached_energy) == initial_energy_count - 1
        # Energy should be in discard
        assert len(state.players[0].discard.cards) == 1


class TestCharmeleonSteadyFirebreathing:
    """Test Charmeleon's Steady Firebreathing attack (me2-12)."""

    def test_steady_firebreathing_generates_action(self):
        """Steady Firebreathing should generate exactly one action."""
        from cards.sets.me2 import charmeleon_steady_firebreathing_actions

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        charmeleon = create_card_instance("me2-12", owner_id=0)
        player0.board.active_spot = charmeleon
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        actions = charmeleon_steady_firebreathing_actions(state, charmeleon, player0)

        assert len(actions) == 1
        assert actions[0].attack_name == "Steady Firebreathing"
        assert "40" in actions[0].display_label

    def test_steady_firebreathing_deals_40_damage(self):
        """Steady Firebreathing should deal 40 damage."""
        from cards.sets.me2 import charmeleon_steady_firebreathing_effect

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        charmeleon = create_card_instance("me2-12", owner_id=0)
        player0.board.active_spot = charmeleon
        defender = create_card_instance("sv3pt5-16", owner_id=1)
        player1.board.active_spot = defender

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=charmeleon.id,
            attack_name="Steady Firebreathing"
        )

        state = charmeleon_steady_firebreathing_effect(state, charmeleon, action)

        # 40 damage = 4 damage counters
        assert state.players[1].board.active_spot.damage_counters == 4


class TestCharmeleonFlareVeil:
    """Test Charmeleon's Flare Veil guard (sv4pt5)."""

    def test_flare_veil_guard_registered(self):
        """Flare Veil guard should be registered."""
        guard = get_card_guard("sv4pt5-8", "effect_prevention")
        assert guard is not None

    def test_flare_veil_blocks_opponent_attack_effects(self):
        """Flare Veil should block effects from opponent's attacks."""
        from cards.sets.sv4pt5 import charmeleon_flare_veil_guard

        charmeleon = create_card_instance("sv4pt5-8", owner_id=0)

        # Opponent's attack effect
        context = {
            'source': 'attack',
            'source_player_id': 1,  # Opponent
            'effect_type': 'status'
        }

        result = charmeleon_flare_veil_guard(None, charmeleon, context)
        assert result is True  # Should block

    def test_flare_veil_allows_own_attack_effects(self):
        """Flare Veil should not block effects from own attacks."""
        from cards.sets.sv4pt5 import charmeleon_flare_veil_guard

        charmeleon = create_card_instance("sv4pt5-8", owner_id=0)

        # Own attack effect
        context = {
            'source': 'attack',
            'source_player_id': 0,  # Self
            'effect_type': 'status'
        }

        result = charmeleon_flare_veil_guard(None, charmeleon, context)
        assert result is False  # Should allow

    def test_flare_veil_allows_ability_effects(self):
        """Flare Veil should not block effects from abilities."""
        from cards.sets.sv4pt5 import charmeleon_flare_veil_guard

        charmeleon = create_card_instance("sv4pt5-8", owner_id=0)

        # Ability effect (not attack)
        context = {
            'source': 'ability',
            'source_player_id': 1,
            'effect_type': 'status'
        }

        result = charmeleon_flare_veil_guard(None, charmeleon, context)
        assert result is False  # Should allow (only blocks attack effects)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

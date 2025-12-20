"""
Comprehensive pytest suite for Dusknoir's Shadow Bind attack.

Tests for:
- Shadow Bind deals 150 damage
- Defending Pokemon can't retreat during opponent's next turn
- Switching clears the effect (new Active can retreat)
- Effect expires at end of opponent's turn
- All card variants (sv6pt5-20, sv6pt5-70, sv8pt5-37)
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


def create_shadow_bind_game_state(dusknoir_card_id: str = "sv6pt5-20"):
    """
    Create a game state with Dusknoir as player 0's active Pokemon.

    Player 0: Dusknoir (Active) + Pidgey (Bench)
    Player 1: Charmander (Active) + Pidgey (Bench)

    Returns:
        GameState ready for Shadow Bind attack
    """
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Player 0: Dusknoir in active spot with bench
    dusknoir = create_card_instance(dusknoir_card_id, owner_id=0)
    player0.board.active_spot = dusknoir

    # Add bench Pokemon for player 0
    bench_pidgey = create_card_instance("sv3pt5-16", owner_id=0)
    player0.board.add_to_bench(bench_pidgey)

    # Player 1: Opponent with active and bench (for retreat/switch tests)
    opponent_active = create_card_instance("sv3pt5-4", owner_id=1)  # Charmander
    player1.board.active_spot = opponent_active

    # Add bench Pokemon for opponent (needed for retreat)
    opponent_bench = create_card_instance("sv3pt5-16", owner_id=1)  # Pidgey
    player1.board.add_to_bench(opponent_bench)

    # Add energy to opponent's active for retreat
    energy = create_card_instance("base1-98", owner_id=1)  # Fire Energy
    opponent_active.attached_energy.append(energy)

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
# DUSKNOIR REGISTRATION TESTS
# ============================================================================

class TestDusknoirRegistration:
    """Test Dusknoir card registrations."""

    def test_dusknoir_sv6pt5_20_registered(self):
        """Dusknoir sv6pt5-20 should be in registry with Cursed Blast and Shadow Bind."""
        assert "sv6pt5-20" in MASTER_LOGIC_REGISTRY
        data = MASTER_LOGIC_REGISTRY["sv6pt5-20"]
        assert "Cursed Blast" in data
        assert "Shadow Bind" in data
        assert data["Cursed Blast"]["category"] == "activatable"
        assert data["Shadow Bind"]["category"] == "attack"

    def test_dusknoir_sv6pt5_70_registered(self):
        """Dusknoir sv6pt5-70 should be in registry with both moves."""
        assert "sv6pt5-70" in MASTER_LOGIC_REGISTRY
        data = MASTER_LOGIC_REGISTRY["sv6pt5-70"]
        assert "Cursed Blast" in data
        assert "Shadow Bind" in data

    def test_dusknoir_sv8pt5_37_reprint_registered(self):
        """Dusknoir sv8pt5-37 (reprint) should be in registry with both moves."""
        assert "sv8pt5-37" in MASTER_LOGIC_REGISTRY
        data = MASTER_LOGIC_REGISTRY["sv8pt5-37"]
        assert "Cursed Blast" in data
        assert "Shadow Bind" in data


# ============================================================================
# SHADOW BIND DAMAGE TESTS
# ============================================================================

class TestShadowBindDamage:
    """Test Shadow Bind deals correct damage."""

    def test_shadow_bind_deals_150_damage(self):
        """Shadow Bind should deal 150 damage (15 damage counters)."""
        from cards.sets.sv6pt5 import dusknoir_shadow_bind_effect

        state = create_shadow_bind_game_state()
        dusknoir = state.players[0].board.active_spot
        opponent_active = state.players[1].board.active_spot

        initial_damage = opponent_active.damage_counters

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=dusknoir.id,
            attack_name="Shadow Bind"
        )

        state = dusknoir_shadow_bind_effect(state, dusknoir, action)

        # 150 damage = 15 damage counters
        assert state.players[1].board.active_spot.damage_counters == initial_damage + 15


# ============================================================================
# PREVENT RETREAT EFFECT TESTS
# ============================================================================

class TestPreventRetreatEffect:
    """Test that Shadow Bind prevents the defending Pokemon from retreating."""

    def test_shadow_bind_applies_prevent_retreat_effect(self):
        """Shadow Bind should add prevent_retreat effect to defender."""
        from cards.sets.sv6pt5 import dusknoir_shadow_bind_effect

        state = create_shadow_bind_game_state()
        dusknoir = state.players[0].board.active_spot
        opponent_active = state.players[1].board.active_spot

        # Verify no effects before attack
        assert len(opponent_active.attack_effects) == 0

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=dusknoir.id,
            attack_name="Shadow Bind"
        )

        state = dusknoir_shadow_bind_effect(state, dusknoir, action)

        # Verify effect was applied
        assert len(opponent_active.attack_effects) == 1
        effect = opponent_active.attack_effects[0]
        assert effect['effect_type'] == 'prevent_retreat'
        assert effect['expires_at_end_of_turn'] == True
        assert effect['expires_player_id'] == 1  # Opponent's player_id

    def test_defending_pokemon_cannot_retreat_after_shadow_bind(self, engine):
        """Defending Pokemon should not have retreat actions after Shadow Bind."""
        from cards.sets.sv6pt5 import dusknoir_shadow_bind_effect

        state = create_shadow_bind_game_state()
        dusknoir = state.players[0].board.active_spot
        opponent_active = state.players[1].board.active_spot

        # Apply Shadow Bind effect
        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=dusknoir.id,
            attack_name="Shadow Bind"
        )
        state = dusknoir_shadow_bind_effect(state, dusknoir, action)

        # Switch to opponent's turn
        state.active_player_index = 1
        state.current_phase = GamePhase.MAIN

        # Get legal actions for opponent
        actions = engine.get_legal_actions(state)

        # Verify no retreat actions are available
        retreat_actions = [a for a in actions if a.action_type == ActionType.RETREAT]
        assert len(retreat_actions) == 0, "Defending Pokemon should not be able to retreat"

    def test_normal_retreat_available_without_shadow_bind(self, engine):
        """Without Shadow Bind, retreat should be available normally."""
        state = create_shadow_bind_game_state()

        # Switch to opponent's turn (no Shadow Bind applied)
        state.active_player_index = 1
        state.current_phase = GamePhase.MAIN

        # Get legal actions for opponent
        actions = engine.get_legal_actions(state)

        # Verify retreat actions are available
        retreat_actions = [a for a in actions if a.action_type == ActionType.RETREAT]
        assert len(retreat_actions) > 0, "Should be able to retreat without Shadow Bind effect"


# ============================================================================
# SWITCH CLEARS EFFECT TESTS
# ============================================================================

class TestSwitchClearsEffect:
    """Test that switching clears the prevent_retreat effect from old Active."""

    def test_switch_allows_new_active_to_retreat(self, engine):
        """After switching, the new Active Pokemon should be able to retreat."""
        from cards.sets.sv6pt5 import dusknoir_shadow_bind_effect

        state = create_shadow_bind_game_state()
        dusknoir = state.players[0].board.active_spot
        opponent_active = state.players[1].board.active_spot
        opponent_bench = state.players[1].board.bench[0]

        # Apply Shadow Bind effect
        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=dusknoir.id,
            attack_name="Shadow Bind"
        )
        state = dusknoir_shadow_bind_effect(state, dusknoir, action)

        # Verify effect is on the original active
        assert len(opponent_active.attack_effects) == 1

        # Simulate a switch: swap active and bench
        # The effect stays on the Pokemon, but it's now benched
        old_active = state.players[1].board.active_spot
        state.players[1].board.active_spot = opponent_bench
        state.players[1].board.bench[0] = old_active

        # Add energy to new active for retreat
        energy = create_card_instance("base1-98", owner_id=1)
        state.players[1].board.active_spot.attached_energy.append(energy)

        # Add another bench Pokemon for retreat target
        another_bench = create_card_instance("sv3pt5-16", owner_id=1)
        state.players[1].board.add_to_bench(another_bench)

        # Switch to opponent's turn
        state.active_player_index = 1
        state.current_phase = GamePhase.MAIN

        # Get legal actions
        actions = engine.get_legal_actions(state)

        # New active should be able to retreat (no effect on it)
        retreat_actions = [a for a in actions if a.action_type == ActionType.RETREAT]
        assert len(retreat_actions) > 0, "New Active Pokemon should be able to retreat"

    def test_effect_stays_on_benched_pokemon(self):
        """The effect should stay on the Pokemon when it's switched to bench."""
        from cards.sets.sv6pt5 import dusknoir_shadow_bind_effect

        state = create_shadow_bind_game_state()
        dusknoir = state.players[0].board.active_spot
        opponent_active = state.players[1].board.active_spot
        opponent_bench = state.players[1].board.bench[0]

        # Apply Shadow Bind effect
        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=dusknoir.id,
            attack_name="Shadow Bind"
        )
        state = dusknoir_shadow_bind_effect(state, dusknoir, action)

        # Store reference to the affected Pokemon
        affected_pokemon = opponent_active
        affected_id = affected_pokemon.id

        # Simulate switch
        state.players[1].board.active_spot = opponent_bench
        state.players[1].board.bench[0] = affected_pokemon

        # Effect should still be on the benched Pokemon
        benched_pokemon = state.players[1].board.bench[0]
        assert benched_pokemon.id == affected_id
        assert len(benched_pokemon.attack_effects) == 1
        assert benched_pokemon.attack_effects[0]['effect_type'] == 'prevent_retreat'


# ============================================================================
# EFFECT EXPIRATION TESTS
# ============================================================================

class TestEffectExpiration:
    """Test that the effect expires at end of opponent's turn."""

    def test_effect_expires_after_opponent_turn_ends(self, engine):
        """The prevent_retreat effect should be removed at end of opponent's turn."""
        from cards.sets.sv6pt5 import dusknoir_shadow_bind_effect

        state = create_shadow_bind_game_state()
        dusknoir = state.players[0].board.active_spot
        opponent_active = state.players[1].board.active_spot

        # Apply Shadow Bind effect
        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=dusknoir.id,
            attack_name="Shadow Bind"
        )
        state = dusknoir_shadow_bind_effect(state, dusknoir, action)

        # Verify effect is present
        assert len(opponent_active.attack_effects) == 1

        # Move to cleanup phase (end of player 0's turn)
        state.current_phase = GamePhase.CLEANUP

        # Resolve phase transition (goes through cleanup -> draw -> main for opponent)
        state = engine.resolve_phase_transition(state)

        # Now it's opponent's turn (player 1) - effect should still be present
        assert state.active_player_index == 1
        assert len(opponent_active.attack_effects) == 1, "Effect should persist during opponent's turn"

        # Opponent ends their turn - move to cleanup
        state.current_phase = GamePhase.CLEANUP

        # Resolve phase transition (end of opponent's turn)
        state = engine.resolve_phase_transition(state)

        # Effect should now be expired (it was set to expire at end of player 1's turn)
        assert len(opponent_active.attack_effects) == 0, "Effect should expire at end of opponent's turn"

    def test_can_retreat_after_effect_expires(self, engine):
        """After the effect expires, the Pokemon should be able to retreat."""
        from cards.sets.sv6pt5 import dusknoir_shadow_bind_effect

        state = create_shadow_bind_game_state()
        dusknoir = state.players[0].board.active_spot
        opponent_active = state.players[1].board.active_spot

        # Add cards to deck to prevent deck-out during phase transitions
        for _ in range(10):
            state.players[0].deck.add_card(create_card_instance("base1-98", owner_id=0))
            state.players[1].deck.add_card(create_card_instance("base1-98", owner_id=1))

        # Apply Shadow Bind effect
        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=dusknoir.id,
            attack_name="Shadow Bind"
        )
        state = dusknoir_shadow_bind_effect(state, dusknoir, action)

        # End player 0's turn
        state.current_phase = GamePhase.CLEANUP
        state = engine.resolve_phase_transition(state)

        # Now opponent's turn - can't retreat
        assert state.active_player_index == 1
        actions = engine.get_legal_actions(state)
        retreat_actions = [a for a in actions if a.action_type == ActionType.RETREAT]
        assert len(retreat_actions) == 0, "Should not be able to retreat during this turn"

        # End opponent's turn
        state.current_phase = GamePhase.CLEANUP
        state = engine.resolve_phase_transition(state)

        # Now player 0's turn again
        assert state.active_player_index == 0

        # End player 0's turn to get back to opponent
        state.current_phase = GamePhase.CLEANUP
        state = engine.resolve_phase_transition(state)

        # Now opponent's second turn - effect should be gone
        assert state.active_player_index == 1
        assert len(opponent_active.attack_effects) == 0, "Effect should have expired"

        # Should be able to retreat now
        actions = engine.get_legal_actions(state)
        retreat_actions = [a for a in actions if a.action_type == ActionType.RETREAT]
        assert len(retreat_actions) > 0, "Should be able to retreat after effect expires"


# ============================================================================
# ALL VARIANTS TESTS
# ============================================================================

class TestAllVariants:
    """Test all Dusknoir card variants work correctly."""

    @pytest.mark.parametrize("card_id", ["sv6pt5-20", "sv6pt5-70", "sv8pt5-37"])
    def test_all_variants_apply_prevent_retreat(self, card_id):
        """All Dusknoir variants should apply prevent_retreat effect."""
        from cards.sets.sv6pt5 import dusknoir_shadow_bind_effect

        state = create_shadow_bind_game_state(card_id)
        dusknoir = state.players[0].board.active_spot
        opponent_active = state.players[1].board.active_spot

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=dusknoir.id,
            attack_name="Shadow Bind"
        )

        state = dusknoir_shadow_bind_effect(state, dusknoir, action)

        # Verify effect applied
        assert len(opponent_active.attack_effects) == 1
        assert opponent_active.attack_effects[0]['effect_type'] == 'prevent_retreat'

    @pytest.mark.parametrize("card_id", ["sv6pt5-20", "sv6pt5-70", "sv8pt5-37"])
    def test_all_variants_deal_150_damage(self, card_id):
        """All Dusknoir variants should deal 150 damage."""
        from cards.sets.sv6pt5 import dusknoir_shadow_bind_effect

        state = create_shadow_bind_game_state(card_id)
        dusknoir = state.players[0].board.active_spot
        opponent_active = state.players[1].board.active_spot

        initial_damage = opponent_active.damage_counters

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=dusknoir.id,
            attack_name="Shadow Bind"
        )

        state = dusknoir_shadow_bind_effect(state, dusknoir, action)

        assert opponent_active.damage_counters == initial_damage + 15

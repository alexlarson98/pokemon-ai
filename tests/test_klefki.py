"""
Tests for Klefki - Version 1 (Mischievous Lock + Joust) and Version 2 (Stick 'n' Draw + Hook).

Tests:
- Mischievous Lock condition (only active when Klefki in Active Spot)
- Mischievous Lock effect (blocks Basic Pokemon abilities, not evolved Pokemon)
- Mischievous Lock self-exemption (doesn't block itself)
- Joust discards tools then deals damage
- Stick 'n' Draw discard/draw mechanic
- Hook basic damage attack
- All card variants registration
"""

import pytest
import sys
sys.path.insert(0, 'src')

from models import GameState, PlayerState, Action, ActionType, StepType, ZoneType, GamePhase
from cards.factory import create_card_instance
from engine import PokemonEngine
from cards.logic_registry import MASTER_LOGIC_REGISTRY


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def engine():
    """Create a Pokemon engine instance."""
    return PokemonEngine()


def create_klefki_game_state(klefki_card_id: str = "sv1-96", klefki_in_active: bool = True):
    """Create a game state for Klefki tests."""
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Create Klefki
    klefki = create_card_instance(klefki_card_id, owner_id=0)

    if klefki_in_active:
        player0.board.active_spot = klefki
        # Add a bench Pokemon
        bench_pokemon = create_card_instance("svp-44", owner_id=0)  # Charmander
        player0.board.bench.append(bench_pokemon)
    else:
        # Klefki on bench, something else active
        active_pokemon = create_card_instance("svp-44", owner_id=0)  # Charmander
        player0.board.active_spot = active_pokemon
        player0.board.bench.append(klefki)

    # Player 1: Basic Pokemon active
    opponent_active = create_card_instance("svp-44", owner_id=1)  # Charmander (Basic)
    player1.board.active_spot = opponent_active

    # Add deck cards
    for _ in range(10):
        player0.deck.add_card(create_card_instance("base1-98", owner_id=0))
        player1.deck.add_card(create_card_instance("base1-98", owner_id=1))

    # Add hand cards for Stick 'n' Draw tests
    for _ in range(3):
        player0.hand.add_card(create_card_instance("base1-98", owner_id=0))

    # Add prizes
    for _ in range(6):
        player0.prizes.add_card(create_card_instance("base1-98", owner_id=0))
        player1.prizes.add_card(create_card_instance("base1-98", owner_id=1))

    state = GameState(
        players=[player0, player1],
        active_player_index=0,
        turn_count=1
    )

    return state


# ============================================================================
# REGISTRATION TESTS
# ============================================================================

class TestKlefkiRegistration:
    """Test that all Klefki variants are properly registered."""

    @pytest.mark.parametrize("card_id", ["sv1-96", "sv4pt5-159"])
    def test_klefki_v1_registered(self, card_id):
        """Verify Klefki Version 1 is in the logic registry."""
        assert card_id in MASTER_LOGIC_REGISTRY, f"{card_id} not in MASTER_LOGIC_REGISTRY"
        assert "Mischievous Lock" in MASTER_LOGIC_REGISTRY[card_id]
        assert "Joust" in MASTER_LOGIC_REGISTRY[card_id]

    @pytest.mark.parametrize("card_id", ["sv1-96", "sv4pt5-159"])
    def test_mischievous_lock_is_passive(self, card_id):
        """Mischievous Lock should be a passive ability."""
        entry = MASTER_LOGIC_REGISTRY[card_id]["Mischievous Lock"]
        assert entry["category"] == "passive"
        assert "condition" in entry
        assert "effect" in entry
        assert entry["condition_type"] == "in_active_spot"
        assert entry["effect_type"] == "ability_lock"
        assert entry["scope"] == "all_basic_pokemon"

    @pytest.mark.parametrize("card_id", ["sv1-96", "sv4pt5-159"])
    def test_joust_is_attack(self, card_id):
        """Joust should be an attack."""
        entry = MASTER_LOGIC_REGISTRY[card_id]["Joust"]
        assert entry["category"] == "attack"
        assert "generator" in entry
        assert "effect" in entry

    def test_klefki_v2_registered(self):
        """Verify Klefki Version 2 is in the logic registry."""
        assert "sv8-128" in MASTER_LOGIC_REGISTRY
        assert "Stick 'n' Draw" in MASTER_LOGIC_REGISTRY["sv8-128"]
        assert "Hook" in MASTER_LOGIC_REGISTRY["sv8-128"]

    def test_stick_n_draw_is_attack(self):
        """Stick 'n' Draw should be an attack."""
        entry = MASTER_LOGIC_REGISTRY["sv8-128"]["Stick 'n' Draw"]
        assert entry["category"] == "attack"
        assert "generator" in entry
        assert "effect" in entry

    def test_hook_is_attack(self):
        """Hook should be an attack."""
        entry = MASTER_LOGIC_REGISTRY["sv8-128"]["Hook"]
        assert entry["category"] == "attack"
        assert "generator" in entry
        assert "effect" in entry


# ============================================================================
# MISCHIEVOUS LOCK TESTS
# ============================================================================

class TestMischievousLock:
    """Test Mischievous Lock passive ability mechanics."""

    def test_condition_true_when_in_active_spot(self):
        """Mischievous Lock condition should return True when Klefki is in Active Spot."""
        from cards.sets.sv1 import klefki_mischievous_lock_condition

        state = create_klefki_game_state(klefki_in_active=True)
        klefki = state.players[0].board.active_spot

        result = klefki_mischievous_lock_condition(state, klefki)
        assert result == True

    def test_condition_false_when_on_bench(self):
        """Mischievous Lock condition should return False when Klefki is on Bench."""
        from cards.sets.sv1 import klefki_mischievous_lock_condition

        state = create_klefki_game_state(klefki_in_active=False)
        klefki = state.players[0].board.bench[0]

        result = klefki_mischievous_lock_condition(state, klefki)
        assert result == False

    def test_effect_blocks_basic_pokemon_abilities(self):
        """Mischievous Lock should block abilities of Basic Pokemon."""
        from cards.sets.sv1 import klefki_mischievous_lock_effect

        state = create_klefki_game_state(klefki_in_active=True)
        klefki = state.players[0].board.active_spot

        # Create a Basic Pokemon target
        basic_pokemon = create_card_instance("svp-44", owner_id=1)  # Charmander is Basic

        # Test blocking an ability on the Basic Pokemon
        should_block = klefki_mischievous_lock_effect(state, klefki, basic_pokemon, "Some Ability")
        assert should_block == True

    def test_effect_allows_evolved_pokemon_abilities(self):
        """Mischievous Lock should NOT block abilities of evolved Pokemon."""
        from cards.sets.sv1 import klefki_mischievous_lock_effect

        state = create_klefki_game_state(klefki_in_active=True)
        klefki = state.players[0].board.active_spot

        # Create a Stage 1 Pokemon target (Charmeleon)
        stage1_pokemon = create_card_instance("sv3-27", owner_id=1)

        # Test - should NOT block Stage 1 Pokemon abilities
        should_block = klefki_mischievous_lock_effect(state, klefki, stage1_pokemon, "Some Ability")
        assert should_block == False

    def test_effect_does_not_block_itself(self):
        """Mischievous Lock should NOT block itself."""
        from cards.sets.sv1 import klefki_mischievous_lock_effect

        state = create_klefki_game_state(klefki_in_active=True)
        klefki = state.players[0].board.active_spot

        # Create another Klefki as target
        other_klefki = create_card_instance("sv1-96", owner_id=1)

        # Test - Mischievous Lock should not block itself
        should_block = klefki_mischievous_lock_effect(state, klefki, other_klefki, "Mischievous Lock")
        assert should_block == False

    def test_effect_blocks_own_basic_pokemon_abilities(self):
        """Mischievous Lock affects BOTH players' Basic Pokemon."""
        from cards.sets.sv1 import klefki_mischievous_lock_effect

        state = create_klefki_game_state(klefki_in_active=True)
        klefki = state.players[0].board.active_spot

        # Create a Basic Pokemon owned by the same player
        own_basic = create_card_instance("svp-44", owner_id=0)

        # Test - should block own Basic Pokemon abilities too
        should_block = klefki_mischievous_lock_effect(state, klefki, own_basic, "Some Ability")
        assert should_block == True


# ============================================================================
# JOUST TESTS
# ============================================================================

class TestJoust:
    """Test Joust attack mechanics."""

    def test_joust_generates_action(self):
        """Joust should generate an attack action."""
        from cards.sets.sv1 import klefki_joust_actions

        state = create_klefki_game_state()
        klefki = state.players[0].board.active_spot
        player = state.players[0]

        actions = klefki_joust_actions(state, klefki, player)

        assert len(actions) == 1
        assert actions[0].action_type == ActionType.ATTACK
        assert actions[0].attack_name == "Joust"

    def test_joust_deals_10_damage(self):
        """Joust should deal 10 damage to opponent's Active Pokemon."""
        from cards.sets.sv1 import klefki_joust_effect

        state = create_klefki_game_state()
        klefki = state.players[0].board.active_spot
        opponent_active = state.players[1].board.active_spot

        initial_damage = opponent_active.damage_counters

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=klefki.id,
            attack_name="Joust"
        )

        state = klefki_joust_effect(state, klefki, action)

        # Should deal 10 damage (1 damage counter)
        assert opponent_active.damage_counters == initial_damage + 1

    def test_joust_discards_tools_before_damage(self):
        """Joust should discard all Pokemon Tools from opponent's Active before dealing damage."""
        from cards.sets.sv1 import klefki_joust_effect

        state = create_klefki_game_state()
        klefki = state.players[0].board.active_spot
        opponent = state.players[1]
        opponent_active = opponent.board.active_spot

        # Attach tools to opponent's active
        tool1 = create_card_instance("sv1-197", owner_id=1)  # Vitality Band
        tool2 = create_card_instance("sv1-197", owner_id=1)  # Another tool (shouldn't happen normally but test edge case)
        opponent_active.attached_tools = [tool1]

        initial_discard_size = len(opponent.discard.cards)

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=klefki.id,
            attack_name="Joust"
        )

        state = klefki_joust_effect(state, klefki, action)

        # Tools should be discarded
        assert len(opponent_active.attached_tools) == 0
        assert len(opponent.discard.cards) == initial_discard_size + 1

    def test_joust_works_without_tools(self):
        """Joust should still work even if opponent has no tools attached."""
        from cards.sets.sv1 import klefki_joust_effect

        state = create_klefki_game_state()
        klefki = state.players[0].board.active_spot
        opponent_active = state.players[1].board.active_spot

        # Ensure no tools
        opponent_active.attached_tools = []
        initial_damage = opponent_active.damage_counters

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=klefki.id,
            attack_name="Joust"
        )

        state = klefki_joust_effect(state, klefki, action)

        # Should still deal 10 damage
        assert opponent_active.damage_counters == initial_damage + 1


# ============================================================================
# STICK 'N' DRAW TESTS
# ============================================================================

class TestStickNDraw:
    """Test Stick 'n' Draw attack mechanics."""

    def test_stick_n_draw_generates_action(self):
        """Stick 'n' Draw should generate an attack action."""
        from cards.sets.sv8 import klefki_stick_n_draw_actions

        state = create_klefki_game_state(klefki_card_id="sv8-128")
        # Replace active with sv8 Klefki
        klefki = create_card_instance("sv8-128", owner_id=0)
        state.players[0].board.active_spot = klefki
        player = state.players[0]

        actions = klefki_stick_n_draw_actions(state, klefki, player)

        assert len(actions) == 1
        assert actions[0].action_type == ActionType.ATTACK
        assert actions[0].attack_name == "Stick 'n' Draw"

    def test_stick_n_draw_pushes_select_step(self):
        """Stick 'n' Draw effect should push a SelectFromZoneStep."""
        from cards.sets.sv8 import klefki_stick_n_draw_effect

        state = create_klefki_game_state()
        klefki = create_card_instance("sv8-128", owner_id=0)
        state.players[0].board.active_spot = klefki

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=klefki.id,
            attack_name="Stick 'n' Draw"
        )

        initial_stack_size = len(state.resolution_stack)
        state = klefki_stick_n_draw_effect(state, klefki, action)

        # Should have pushed a step
        assert len(state.resolution_stack) == initial_stack_size + 1

        step = state.resolution_stack[-1]
        assert step.step_type == StepType.SELECT_FROM_ZONE
        assert step.zone == ZoneType.HAND
        assert step.count == 1
        assert step.on_complete_callback == "klefki_stick_n_draw_complete"

    def test_stick_n_draw_does_nothing_with_empty_hand(self):
        """Stick 'n' Draw should do nothing if hand is empty."""
        from cards.sets.sv8 import klefki_stick_n_draw_effect

        state = create_klefki_game_state()
        klefki = create_card_instance("sv8-128", owner_id=0)
        state.players[0].board.active_spot = klefki
        state.players[0].hand.cards = []  # Empty hand

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=klefki.id,
            attack_name="Stick 'n' Draw"
        )

        initial_stack_size = len(state.resolution_stack)
        state = klefki_stick_n_draw_effect(state, klefki, action)

        # No step should be pushed
        assert len(state.resolution_stack) == initial_stack_size


# ============================================================================
# HOOK TESTS
# ============================================================================

class TestHook:
    """Test Hook attack mechanics."""

    def test_hook_generates_action(self):
        """Hook should generate an attack action."""
        from cards.sets.sv8 import klefki_hook_actions

        state = create_klefki_game_state()
        klefki = create_card_instance("sv8-128", owner_id=0)
        state.players[0].board.active_spot = klefki
        player = state.players[0]

        actions = klefki_hook_actions(state, klefki, player)

        assert len(actions) == 1
        assert actions[0].action_type == ActionType.ATTACK
        assert actions[0].attack_name == "Hook"

    def test_hook_deals_20_damage(self):
        """Hook should deal 20 damage to opponent's Active Pokemon."""
        from cards.sets.sv8 import klefki_hook_effect

        state = create_klefki_game_state()
        klefki = create_card_instance("sv8-128", owner_id=0)
        state.players[0].board.active_spot = klefki
        opponent_active = state.players[1].board.active_spot

        initial_damage = opponent_active.damage_counters

        action = Action(
            action_type=ActionType.ATTACK,
            player_id=0,
            card_id=klefki.id,
            attack_name="Hook"
        )

        state = klefki_hook_effect(state, klefki, action)

        # Should deal 20 damage (2 damage counters)
        assert opponent_active.damage_counters == initial_damage + 2


# ============================================================================
# INTEGRATION TESTS - ENGINE BLOCKING
# ============================================================================

class TestMischievousLockEngineIntegration:
    """Test that Mischievous Lock actually blocks abilities through the engine."""

    def test_klefki_blocks_fan_rotom_fan_call(self, engine):
        """Klefki in Active Spot should block Fan Rotom's Fan Call ability."""
        # Create a state where:
        # - Player 0 has Klefki in Active Spot
        # - Player 1 has Fan Rotom on bench with Fan Call ability
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        # Player 0: Klefki active
        klefki = create_card_instance("sv1-96", owner_id=0)
        player0.board.active_spot = klefki

        # Player 1: Something active, Fan Rotom on bench
        opponent_active = create_card_instance("svp-44", owner_id=1)  # Charmander
        player1.board.active_spot = opponent_active

        fan_rotom = create_card_instance("sv7-118", owner_id=1)  # Fan Rotom (Basic)
        player1.board.bench.append(fan_rotom)

        # Add deck cards for search
        for _ in range(10):
            player0.deck.add_card(create_card_instance("base1-98", owner_id=0))
            player1.deck.add_card(create_card_instance("base1-98", owner_id=1))

        # Add prizes
        for _ in range(6):
            player0.prizes.add_card(create_card_instance("base1-98", owner_id=0))
            player1.prizes.add_card(create_card_instance("base1-98", owner_id=1))

        state = GameState(
            players=[player0, player1],
            active_player_index=1,  # Player 1's turn
            turn_count=2,  # Player 1's first turn (they went second)
            starting_player_id=0,  # Player 0 went first
            current_phase=GamePhase.MAIN  # Must be in main phase for abilities
        )

        # Get legal actions for Player 1
        actions = engine.get_legal_actions(state)

        # Fan Call should NOT be available (Klefki is blocking it)
        fan_call_actions = [a for a in actions if a.ability_name == "Fan Call"]
        assert len(fan_call_actions) == 0, "Fan Call should be blocked by Klefki's Mischievous Lock"

    def test_klefki_does_not_block_evolved_pokemon_abilities(self, engine):
        """Klefki should NOT block abilities of evolved (non-Basic) Pokemon."""
        # This is a placeholder - would need an evolved Pokemon with an ability
        # Fan Rotom is Basic so it gets blocked. A Stage 1 or 2 would not be blocked.
        pass

    def test_klefki_on_bench_does_not_block(self, engine):
        """Klefki on bench should NOT block abilities."""
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        # Player 0: Something else active, Klefki on bench
        active_pokemon = create_card_instance("svp-44", owner_id=0)  # Charmander
        player0.board.active_spot = active_pokemon

        klefki = create_card_instance("sv1-96", owner_id=0)
        player0.board.bench.append(klefki)

        # Player 1: Fan Rotom active
        fan_rotom = create_card_instance("sv7-118", owner_id=1)
        player1.board.active_spot = fan_rotom

        # Add deck cards for search
        for _ in range(10):
            player0.deck.add_card(create_card_instance("base1-98", owner_id=0))
            player1.deck.add_card(create_card_instance("base1-98", owner_id=1))

        # Add prizes
        for _ in range(6):
            player0.prizes.add_card(create_card_instance("base1-98", owner_id=0))
            player1.prizes.add_card(create_card_instance("base1-98", owner_id=1))

        state = GameState(
            players=[player0, player1],
            active_player_index=1,  # Player 1's turn
            turn_count=2,  # Player 1's first turn (they went second)
            starting_player_id=0,
            current_phase=GamePhase.MAIN  # Must be in main phase for abilities
        )

        # Get legal actions for Player 1
        actions = engine.get_legal_actions(state)

        # Fan Call SHOULD be available (Klefki is on bench, not blocking)
        fan_call_actions = [a for a in actions if a.ability_name == "Fan Call"]
        assert len(fan_call_actions) == 1, "Fan Call should NOT be blocked when Klefki is on bench"

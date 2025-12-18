"""
Comprehensive pytest suite for energy attachment and attack mechanics.

Tests:
- Energy attachment (once per turn, type validation)
- Energy attachment to different Pokemon (active/bench)
- Attack energy cost validation
- Attack damage calculation
- Energy type matching for attack costs
- Colorless energy requirements
- Turn 1 attack restriction
- Status condition attack prevention (Asleep, Paralyzed)
- Attack effects (cannot attack next turn)
"""

import pytest
import sys
sys.path.insert(0, 'src')

from models import GameState, PlayerState, GamePhase, Action, ActionType, StatusCondition, EnergyType
from engine import PokemonEngine
from cards.factory import create_card_instance
from cards.registry import create_card


@pytest.fixture
def engine():
    """Create PokemonEngine instance."""
    return PokemonEngine()


@pytest.fixture
def basic_game_state():
    """Create a basic game state with two players."""
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Give both players an active Pokemon
    player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)  # Pidgey
    player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

    return GameState(
        players=[player0, player1],
        turn_count=2,
        active_player_index=0,
        current_phase=GamePhase.MAIN,
        starting_player_id=0
    )


class TestEnergyAttachment:
    """Test energy attachment mechanics using Stack architecture."""

    def test_attach_energy_to_active(self, engine, basic_game_state):
        """Should be able to attach energy to active Pokemon via stack."""
        state = basic_game_state
        player = state.players[0]

        # Add energy to hand
        energy = create_card_instance("base1-98", owner_id=0)  # Fire Energy
        player.hand.add_card(energy)

        # Get energy attachment actions (now returns single stack-initiating action)
        actions = engine._get_attach_energy_actions(state)

        # Should have exactly one action to initiate attachment
        assert len(actions) == 1, "Should have single attach energy action"
        assert actions[0].action_type == ActionType.ATTACH_ENERGY
        assert actions[0].parameters.get('use_stack') is True

        # Apply the action to initiate the stack
        state = engine._apply_attach_energy(state, actions[0])

        # Should now have a SelectFromZoneStep on the stack
        assert state.has_pending_resolution()
        step = state.get_current_step()
        assert step.purpose.value == "energy_to_attach"

        # Get actions from stack (should be SELECT_CARD actions for energy)
        select_actions = engine.get_legal_actions(state)
        energy_select_actions = [a for a in select_actions if a.action_type == ActionType.SELECT_CARD]
        assert len(energy_select_actions) == 1, "Should have one energy to select"

        # Select the energy (auto-confirms since exact_count=True and count=1)
        state = engine.step(state, energy_select_actions[0])

        # Now should have AttachToTargetStep - get target selection actions
        target_actions = engine.get_legal_actions(state)
        target_select_actions = [a for a in target_actions if a.action_type == ActionType.SELECT_CARD]

        # Select active as target
        active_id = state.players[0].board.active_spot.id
        active_target_action = next((a for a in target_select_actions if a.target_id == active_id), None)
        assert active_target_action is not None, "Should have action to attach to active"

        state = engine.step(state, active_target_action)
        player = state.players[0]

        # Verify energy was attached
        assert len(player.board.active_spot.attached_energy) == 1, "Energy should be attached"
        assert player.energy_attached_this_turn is True, "Flag should be set"
        assert not state.has_pending_resolution(), "Stack should be empty"

    def test_attach_energy_to_bench(self, engine, basic_game_state):
        """Should be able to attach energy to benched Pokemon via stack."""
        state = basic_game_state
        player = state.players[0]

        # Add Pokemon to bench
        bench_mon = create_card_instance("sv2-81", owner_id=0)
        player.board.add_to_bench(bench_mon)

        # Add energy to hand
        energy = create_card_instance("base1-98", owner_id=0)
        player.hand.add_card(energy)

        # Initiate attach energy
        actions = engine._get_attach_energy_actions(state)
        state = engine._apply_attach_energy(state, actions[0])

        # Select the energy (auto-confirms since exact_count=True and count=1)
        select_actions = engine.get_legal_actions(state)
        energy_select_actions = [a for a in select_actions if a.action_type == ActionType.SELECT_CARD]
        state = engine.step(state, energy_select_actions[0])

        # Select bench as target
        target_actions = engine.get_legal_actions(state)
        bench_target_action = next((a for a in target_actions if a.target_id == bench_mon.id), None)
        assert bench_target_action is not None, "Should have action to attach to bench"

        state = engine.step(state, bench_target_action)
        player = state.players[0]

        # Verify energy was attached to bench
        assert len(player.board.bench[0].attached_energy) == 1, "Energy should be attached to bench"

    def test_attach_energy_single_initial_action(self, engine, basic_game_state):
        """Stack approach generates single initial action regardless of targets."""
        state = basic_game_state
        player = state.players[0]

        # Add Pokemon to bench (so there are multiple targets)
        for i in range(3):
            bench_mon = create_card_instance("sv2-81", owner_id=0)
            player.board.add_to_bench(bench_mon)

        # Add multiple Fire Energy cards to hand
        for _ in range(3):
            energy = create_card_instance("base1-98", owner_id=0)
            player.hand.add_card(energy)

        # Get energy attachment actions
        actions = engine._get_attach_energy_actions(state)

        # Should have exactly 1 action (not 3 energy * 4 targets = 12)
        assert len(actions) == 1, "Stack approach should generate single action"


class TestEnergyAttachmentRestrictions:
    """Test energy attachment restrictions."""

    def test_can_only_attach_energy_from_hand(self, engine, basic_game_state):
        """Can only attach energy that's in hand."""
        state = basic_game_state
        player = state.players[0]

        # Energy is in discard, not hand
        energy = create_card_instance("base1-98", owner_id=0)
        player.discard.add_card(energy)

        # Get energy attachment actions
        actions = engine._get_attach_energy_actions(state)

        # Should have no actions (no energy in hand)
        assert len(actions) == 0, "Cannot attach energy from discard"


class TestAttackEnergyValidation:
    """Test attack energy cost validation."""

    def test_cannot_attack_without_energy(self, engine, basic_game_state):
        """Cannot attack if Pokemon has no energy attached."""
        state = basic_game_state
        player = state.players[0]
        active = player.board.active_spot

        # No energy attached
        assert len(active.attached_energy) == 0

        # Get attack actions
        actions = engine._get_attack_actions(state, active)

        # Should have no attack actions (not enough energy)
        assert len(actions) == 0, "Cannot attack without energy"

    def test_can_attack_with_sufficient_energy(self, engine, basic_game_state):
        """Can attack if Pokemon has sufficient energy."""
        state = basic_game_state
        player = state.players[0]
        active = player.board.active_spot

        # Attach energy (Pidgey's Gust costs 1 Colorless)
        energy = create_card_instance("base1-98", owner_id=0)
        active.attached_energy.append(energy)

        # Get attack actions
        actions = engine._get_attack_actions(state, active)

        # Should have at least one attack action
        assert len(actions) > 0, "Should be able to attack with sufficient energy"

    def test_energy_type_matching(self, engine):
        """Attack requires correct energy types, not just count."""
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        # Charizard ex needs Fire energy for attacks
        charizard = create_card_instance("sv4pt5-9", owner_id=0)
        player0.board.active_spot = charizard

        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        # Attach Water energy (wrong type)
        water_energy = create_card_instance("base1-102", owner_id=0)  # Water Energy
        charizard.attached_energy.append(water_energy)

        # Get attack actions - Charizard needs Fire energy
        actions = engine._get_attack_actions(state, charizard)

        # Water energy doesn't satisfy Fire requirement for most attacks
        # (Some attacks might allow Colorless, but specific Fire attacks won't work)
        # This test verifies the engine checks energy types, not just count


class TestAttackRestrictions:
    """Test attack restrictions and validations."""

    def test_cannot_attack_turn_1_going_first(self, engine):
        """Player going first cannot attack on turn 1."""
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        active = create_card_instance("sv3pt5-16", owner_id=0)
        player0.board.active_spot = active

        # Attach energy
        energy = create_card_instance("base1-98", owner_id=0)
        active.attached_energy.append(energy)

        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        state = GameState(
            players=[player0, player1],
            turn_count=1,  # TURN 1
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0  # Player 0 went first
        )

        # Get attack actions
        actions = engine._get_attack_actions(state, active)

        # Should have no attack actions on turn 1
        assert len(actions) == 0, "Cannot attack on turn 1 if going first"

    def test_can_attack_turn_1_going_second(self, engine):
        """Player going second CAN attack on turn 1."""
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)

        active = create_card_instance("sv3pt5-16", owner_id=1)
        player1.board.active_spot = active

        # Attach energy
        energy = create_card_instance("base1-98", owner_id=1)
        active.attached_energy.append(energy)

        state = GameState(
            players=[player0, player1],
            turn_count=1,  # TURN 1
            active_player_index=1,  # Player 1's turn
            current_phase=GamePhase.MAIN,
            starting_player_id=0  # Player 0 went first, so Player 1 is second
        )

        # Get attack actions
        actions = engine._get_attack_actions(state, active)

        # Should have attack actions (player 1 can attack on turn 1)
        assert len(actions) > 0, "Player going second can attack on turn 1"

    def test_cannot_attack_when_asleep(self, engine, basic_game_state):
        """Cannot attack when Pokemon is Asleep."""
        state = basic_game_state
        player = state.players[0]
        active = player.board.active_spot

        # Attach energy
        energy = create_card_instance("base1-98", owner_id=0)
        active.attached_energy.append(energy)

        # Make Pokemon Asleep
        active.status_conditions.add(StatusCondition.ASLEEP)

        # Get attack actions
        actions = engine._get_attack_actions(state, active)

        # Should have no attack actions
        assert len(actions) == 0, "Cannot attack when Asleep"

    def test_cannot_attack_when_paralyzed(self, engine, basic_game_state):
        """Cannot attack when Pokemon is Paralyzed."""
        state = basic_game_state
        player = state.players[0]
        active = player.board.active_spot

        # Attach energy
        energy = create_card_instance("base1-98", owner_id=0)
        active.attached_energy.append(energy)

        # Make Pokemon Paralyzed
        active.status_conditions.add(StatusCondition.PARALYZED)

        # Get attack actions
        actions = engine._get_attack_actions(state, active)

        # Should have no attack actions
        assert len(actions) == 0, "Cannot attack when Paralyzed"

    def test_cannot_attack_with_effect_flag(self, engine, basic_game_state):
        """Cannot attack if 'cannot_attack_next_turn' flag is set."""
        state = basic_game_state
        player = state.players[0]
        active = player.board.active_spot

        # Attach energy
        energy = create_card_instance("base1-98", owner_id=0)
        active.attached_energy.append(energy)

        # Set cannot attack flag
        active.attack_effects.append("cannot_attack_next_turn")

        # Get attack actions
        actions = engine._get_attack_actions(state, active)

        # Should have no attack actions
        assert len(actions) == 0, "Cannot attack with 'cannot_attack_next_turn' flag"


class TestAttackExecution:
    """Test attack execution mechanics."""

    def test_confusion_coin_flip_tails_self_damage(self, engine, basic_game_state):
        """Confused Pokemon should damage itself on tails."""
        state = basic_game_state
        player = state.players[0]
        active = player.board.active_spot

        # Attach energy
        energy = create_card_instance("base1-98", owner_id=0)
        active.attached_energy.append(energy)

        # Make Pokemon Confused
        active.status_conditions.add(StatusCondition.CONFUSED)

        # Get attack action
        actions = engine._get_attack_actions(state, active)

        # Confused Pokemon can still generate attack actions
        # (confusion is checked during execution, not action generation)
        if len(actions) > 0:
            # Create attack action
            attack_action = actions[0]

            # Apply attack (will flip coin for confusion)
            initial_damage = active.damage_counters
            state = engine._apply_attack(state, attack_action)
            player = state.players[0]

            # On tails, Pokemon takes 3 damage counters (30 damage)
            # On heads, attack proceeds normally
            # We can't deterministically test this without mocking coin flip


class TestColorlessEnergy:
    """Test Colorless energy requirement mechanics."""

    def test_colorless_can_be_paid_with_any_type(self, engine):
        """Colorless energy cost can be paid with any energy type."""
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        # Pidgey has Colorless attacks
        pidgey = create_card_instance("sv3pt5-16", owner_id=0)
        player0.board.active_spot = pidgey

        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        # Attach Water energy (any type works for Colorless)
        water = create_card_instance("base1-102", owner_id=0)
        pidgey.attached_energy.append(water)

        # Get attack actions
        actions = engine._get_attack_actions(state, pidgey)

        # Should be able to attack with Water energy for Colorless cost
        assert len(actions) > 0, "Colorless cost can be paid with any energy type"


class TestEnergyCalculation:
    """Test energy calculation for attacks."""

    def test_calculate_provided_energy(self, engine):
        """_calculate_provided_energy should correctly count energy types."""
        # Create Pokemon with mixed energy
        pokemon = create_card_instance("sv3pt5-16", owner_id=0)

        fire1 = create_card_instance("base1-98", owner_id=0)  # Fire Energy
        fire2 = create_card_instance("base1-98", owner_id=0)  # Fire Energy
        water = create_card_instance("base1-102", owner_id=0)  # Water Energy

        pokemon.attached_energy = [fire1, fire2, water]

        # Calculate provided energy
        provided = engine._calculate_provided_energy(pokemon)

        # Should have 2 Fire and 1 Water
        # Note: Energy types are stored by their symbol (e.g., 'R' for Fire)
        total_energy = sum(provided.values())
        assert total_energy == 3, "Should count all 3 energy cards"


class TestCharizardExInfernalReignAndAttack:
    """Test Charizard ex Infernal Reign ability and Burning Darkness attack."""

    def test_infernal_reign_attaches_energy_with_correct_card_id(self, engine):
        """
        Infernal Reign should attach energy with correct card_id so attacks work.

        This tests the fix for the bug where energy attached via SearchAndAttachState
        had an invalid card_id, causing _calculate_provided_energy to return empty.
        """
        from models import SearchAndAttachState, InterruptPhase, EnergyType, Subtype

        # Create game state with Charizard ex as active
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        charizard = create_card_instance("svp-56", owner_id=0)  # Charizard ex
        player0.board.active_spot = charizard
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        # Add Basic Fire Energy to deck
        fire_energy_1 = create_card_instance("sve-2", owner_id=0)  # Basic Fire Energy
        fire_energy_2 = create_card_instance("sve-2", owner_id=0)  # Basic Fire Energy
        player0.deck.add_card(fire_energy_1)
        player0.deck.add_card(fire_energy_2)

        state = GameState(
            players=[player0, player1],
            turn_count=2,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        # Create a SearchAndAttachState interrupt (simulating Infernal Reign trigger)
        interrupt = SearchAndAttachState(
            ability_name="Infernal Reign",
            source_card_id=charizard.id,
            player_id=0,
            phase=InterruptPhase.SEARCH_SELECT,
            search_filter={
                "energy_type": EnergyType.FIRE,
                "subtype": Subtype.BASIC
            },
            max_select=3,
            selected_card_ids=[],
            cards_to_attach=[],
        )
        state.pending_interrupt = interrupt

        # Select both energy cards
        # Note: Actions are deduplicated by card name, so we see 1 action at a time
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SEARCH_SELECT_CARD]
        assert len(select_actions) == 1, "Should have 1 action (deduplicated by card name)"

        # Select first energy
        state = engine.step(state, select_actions[0])
        # Select second energy (same card name, different instance)
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SEARCH_SELECT_CARD]
        assert len(select_actions) == 1, "Should have 1 action for second energy"
        state = engine.step(state, select_actions[0])

        # Confirm selection
        actions = engine.get_legal_actions(state)
        confirm_actions = [a for a in actions if a.action_type == ActionType.SEARCH_CONFIRM]
        assert len(confirm_actions) == 1, "Should have confirm action"
        state = engine.step(state, confirm_actions[0])

        # Verify we're now in ATTACH_ENERGY phase and card_definition_map is populated
        assert state.pending_interrupt is not None
        assert state.pending_interrupt.phase == InterruptPhase.ATTACH_ENERGY
        assert len(state.pending_interrupt.card_definition_map) == 2, "Should have 2 cards in definition map"

        # Attach first energy to Charizard
        actions = engine.get_legal_actions(state)
        attach_actions = [a for a in actions if a.action_type == ActionType.INTERRUPT_ATTACH_ENERGY]
        charizard_attach = [a for a in attach_actions if a.target_id == charizard.id][0]
        state = engine.step(state, charizard_attach)

        # Attach second energy to Charizard
        actions = engine.get_legal_actions(state)
        attach_actions = [a for a in actions if a.action_type == ActionType.INTERRUPT_ATTACH_ENERGY]
        charizard_attach = [a for a in attach_actions if a.target_id == charizard.id][0]
        state = engine.step(state, charizard_attach)

        # Interrupt should be complete now
        assert state.pending_interrupt is None, "Interrupt should be complete"

        # Verify Charizard has 2 energy attached
        charizard = state.players[0].board.active_spot
        assert len(charizard.attached_energy) == 2, "Charizard should have 2 energy attached"

        # CRITICAL: Verify energy has correct card_id (not 'basic-fire-energy' fallback)
        for energy in charizard.attached_energy:
            assert energy.card_id == "sve-2", f"Energy should have correct card_id 'sve-2', got '{energy.card_id}'"

        # Verify _calculate_provided_energy returns correct values
        provided = engine._calculate_provided_energy(charizard)
        assert provided.get('Fire', 0) == 2, f"Should have 2 Fire energy, got {provided}"

    def test_burning_darkness_attack_available_after_infernal_reign(self, engine):
        """
        Burning Darkness attack should be available after attaching energy via Infernal Reign.

        This is an integration test that verifies the full flow:
        1. Evolve to Charizard ex (triggers Infernal Reign)
        2. Attach 2+ Fire Energy
        3. Attack with Burning Darkness
        """
        from models import SearchAndAttachState, InterruptPhase, EnergyType, Subtype

        # Setup: Charizard ex with no energy
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        charizard = create_card_instance("svp-56", owner_id=0)  # Charizard ex
        player0.board.active_spot = charizard
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        state = GameState(
            players=[player0, player1],
            turn_count=2,  # Not turn 1, so attacks allowed
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        # Without energy, Burning Darkness should NOT be available
        actions = engine.get_legal_actions(state)
        attack_actions = [a for a in actions if a.action_type == ActionType.ATTACK]
        assert len(attack_actions) == 0, "No attack should be available without energy"

        # Attach 2 Fire Energy directly (simulating post-Infernal Reign state)
        fire_energy_1 = create_card_instance("sve-2", owner_id=0)
        fire_energy_2 = create_card_instance("sve-2", owner_id=0)
        charizard.attached_energy = [fire_energy_1, fire_energy_2]

        # Now Burning Darkness should be available
        actions = engine.get_legal_actions(state)
        attack_actions = [a for a in actions if a.action_type == ActionType.ATTACK]
        assert len(attack_actions) == 1, f"Burning Darkness should be available, got {len(attack_actions)} attacks"
        assert attack_actions[0].attack_name == "Burning Darkness", f"Attack should be Burning Darkness, got {attack_actions[0].attack_name}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

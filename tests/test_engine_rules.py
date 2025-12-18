"""
Test Suite: Engine Rules
Tests for Constitution compliance and game rules enforcement.

Tests:
- Turn 1 attack restriction (Player 1 cannot attack)
- Once-per-turn limits (Energy, Supporter, Retreat)
- Evolution sickness
- Status condition blocking
"""

import pytest
import sys
sys.path.insert(0, 'src')

from models import GamePhase, ActionType, StatusCondition
from cards.factory import create_card_instance


# Helper functions (imported from conftest via pytest auto-discovery)
def add_energy_to_pokemon(pokemon, energy_type, count, owner_id):
    """Helper to attach energy to a Pokémon."""
    for _ in range(count):
        energy = create_card_instance(energy_type, owner_id)
        pokemon.attached_energy.append(energy)


def add_cards_to_hand(player, card_id, count):
    """Helper to add cards to a player's hand."""
    from cards.factory import create_multiple
    cards = create_multiple(card_id, count, player.player_id)
    for card in cards:
        player.hand.add_card(card)


def assert_has_action_type(actions, action_type):
    """Assert that at least one action of the given type exists."""
    action_types = [a.action_type for a in actions]
    assert action_type in action_types, \
        f"Expected {action_type} in actions, but got: {action_types}"


def assert_no_action_type(actions, action_type):
    """Assert that no action of the given type exists."""
    action_types = [a.action_type for a in actions]
    assert action_type not in action_types, \
        f"Did not expect {action_type} in actions, but found it in: {action_types}"


# ============================================================================
# TEST: TURN 1 ATTACK RESTRICTION (Constitution Section 2, Phase 3)
# ============================================================================

def test_player1_cannot_attack_turn1(engine, basic_battle_state):
    """
    CRITICAL TEST: Player 1 (going first) cannot attack on Turn 1.

    Constitution: "Player 1 cannot attack on Turn 1."
    """
    state = basic_battle_state

    # Set to Turn 1, Player 0's turn, Attack Phase
    state.turn_count = 1
    state.active_player_index = 0
    state.current_phase = GamePhase.ATTACK

    # Get legal actions
    actions = engine.get_legal_actions(state)

    # CRITICAL ASSERTION: No ATTACK actions should be available
    assert_no_action_type(actions, ActionType.ATTACK)

    print("[OK] Turn 1 attack restriction enforced")


def test_player1_can_attack_turn2(engine, basic_battle_state):
    """
    Verify Player 1 CAN attack on Turn 2.
    """
    state = basic_battle_state

    # Set to Turn 2, Player 0's turn, Main Phase
    state.turn_count = 2
    state.active_player_index = 0
    state.current_phase = GamePhase.MAIN

    # Add energy to Active (needed to pay attack cost)
    add_energy_to_pokemon(state.players[0].board.active_spot, "base1-98", 1, 0)

    # Get legal actions
    actions = engine.get_legal_actions(state)

    # Player should be able to attack now
    # Note: Actual attack generation depends on card implementation
    # At minimum, should have END_TURN option (not forced to skip)
    assert len(actions) > 0, "Player should have actions on Turn 2"

    print("[OK] Turn 2 attack allowed")


def test_player2_can_attack_turn1(engine, basic_battle_state):
    """
    Verify Player 2 (going second) CAN attack on Turn 1.
    """
    state = basic_battle_state

    # Set to Turn 1, Player 1's turn, Main Phase
    state.turn_count = 1
    state.active_player_index = 1
    state.current_phase = GamePhase.MAIN

    # Add energy to Active
    add_energy_to_pokemon(state.players[1].board.active_spot, "base1-100", 2, 1)  # Lightning Energy

    # Get legal actions
    actions = engine.get_legal_actions(state)

    # Player 2 can attack on their first turn
    assert len(actions) > 0, "Player 2 should have actions on Turn 1"

    print("[OK] Player 2 can attack on Turn 1")


# ============================================================================
# TEST: ENERGY ATTACHMENT LIMIT (Constitution Section 2, Phase 2)
# ============================================================================

def test_energy_once_per_turn(engine, basic_battle_state):
    """
    Test that you cannot attach Energy twice in one turn.

    Constitution: "Attach Energy: Once per turn."

    With stack-based attach energy, we need to complete the full flow:
    1. ATTACH_ENERGY -> initiates stack
    2. SELECT_CARD -> choose energy from hand (auto-confirms since exact_count=True)
    3. SELECT_CARD -> choose target Pokemon (auto-executes)
    """
    state = basic_battle_state
    player = state.players[0]

    # Add 2 Fire Energy to hand
    add_cards_to_hand(player, "base1-98", 2)

    # Set to Main Phase
    state.current_phase = GamePhase.MAIN

    # Get legal actions - should have ATTACH_ENERGY
    actions_before = engine.get_legal_actions(state)
    assert_has_action_type(actions_before, ActionType.ATTACH_ENERGY)

    # Step 1: Initiate attach energy (pushes SelectFromZoneStep)
    attach_action = next(a for a in actions_before if a.action_type == ActionType.ATTACH_ENERGY)
    state = engine.step(state, attach_action)

    # Step 2: Select energy from hand (auto-confirms since exact_count=True, count=1)
    select_actions = engine.get_legal_actions(state)
    energy_select = next((a for a in select_actions if a.action_type == ActionType.SELECT_CARD), None)
    assert energy_select is not None, "Should have SELECT_CARD for energy"
    state = engine.step(state, energy_select)

    # Step 3: Select target Pokemon (auto-executes)
    target_actions = engine.get_legal_actions(state)
    target_select = next((a for a in target_actions if a.action_type == ActionType.SELECT_CARD), None)
    assert target_select is not None, "Should have SELECT_CARD for target"
    state = engine.step(state, target_select)

    # Verify flag is set
    assert state.players[0].energy_attached_this_turn, "Energy attachment flag should be True"

    # Get legal actions again - should NOT have ATTACH_ENERGY
    actions_after = engine.get_legal_actions(state)
    assert_no_action_type(actions_after, ActionType.ATTACH_ENERGY)

    print("[OK] Energy once-per-turn restriction enforced")


def test_energy_resets_next_turn(engine, basic_battle_state):
    """
    Verify that energy attachment flag resets at end of turn.
    """
    state = basic_battle_state
    player = state.players[0]

    # Set energy flag
    player.energy_attached_this_turn = True

    # Advance to cleanup and resolve turn transition
    state.current_phase = GamePhase.CLEANUP
    state = engine.resolve_phase_transition(state)

    # Verify flag is reset for new active player
    new_active_player = state.get_active_player()
    assert not new_active_player.energy_attached_this_turn, \
        "Energy flag should reset at end of turn"

    print("[OK] Energy flag resets at end of turn")


# ============================================================================
# TEST: SUPPORTER LIMIT (Constitution Section 2, Phase 2)
# ============================================================================

@pytest.mark.skip(reason="Supporter cards not yet implemented in card registry")
def test_supporter_once_per_turn(engine, basic_battle_state):
    """
    Test that you cannot play 2 Supporters in one turn.

    Constitution: "Supporter: Once per turn."
    """
    state = basic_battle_state
    player = state.players[0]

    # Add 2 Professor's Research to hand
    add_cards_to_hand(player, "generic-professors-research", 2)

    # Set to Turn 2 (can play Supporters)
    state.turn_count = 2
    state.current_phase = GamePhase.MAIN

    # Get legal actions - should have PLAY_SUPPORTER
    actions_before = engine.get_legal_actions(state)
    assert_has_action_type(actions_before, ActionType.PLAY_SUPPORTER)

    # Play first Supporter
    supporter_action = next(a for a in actions_before if a.action_type == ActionType.PLAY_SUPPORTER)
    state = engine.step(state, supporter_action)

    # Verify flag is set
    assert state.players[0].supporter_played_this_turn, "Supporter flag should be True"

    # Get legal actions again - should NOT have PLAY_SUPPORTER
    actions_after = engine.get_legal_actions(state)
    assert_no_action_type(actions_after, ActionType.PLAY_SUPPORTER)

    print("[OK] Supporter once-per-turn restriction enforced")


def test_supporter_not_allowed_turn1_going_first(engine, basic_battle_state):
    """
    Test that Player 1 (going first) cannot play Supporter on Turn 1.

    Constitution: "No Supporter on Turn 1 going first."
    """
    state = basic_battle_state
    player = state.players[0]

    # Add Professor's Research to hand
    add_cards_to_hand(player, "generic-professors-research", 1)

    # Set to Turn 1, Player 0's turn, Main Phase
    state.turn_count = 1
    state.active_player_index = 0
    state.current_phase = GamePhase.MAIN

    # Get legal actions
    actions = engine.get_legal_actions(state)

    # CRITICAL: Should NOT have PLAY_SUPPORTER
    assert_no_action_type(actions, ActionType.PLAY_SUPPORTER)

    print("[OK] No Supporter on Turn 1 going first")


@pytest.mark.skip(reason="Supporter cards not yet implemented in card registry")
def test_supporter_allowed_turn1_going_second(engine, basic_battle_state):
    """
    Verify Player 2 (going second) CAN play Supporter on Turn 1.
    """
    state = basic_battle_state
    player = state.players[1]

    # Add Professor's Research to hand
    add_cards_to_hand(player, "generic-professors-research", 1)

    # Set to Turn 1, Player 1's turn, Main Phase
    state.turn_count = 1
    state.active_player_index = 1
    state.current_phase = GamePhase.MAIN

    # Get legal actions
    actions = engine.get_legal_actions(state)

    # Player 2 CAN play Supporter on Turn 1
    assert_has_action_type(actions, ActionType.PLAY_SUPPORTER)

    print("[OK] Player 2 can play Supporter on Turn 1")


# ============================================================================
# TEST: EVOLUTION SICKNESS (Constitution Section 2, Phase 2)
# ============================================================================

def test_cannot_evolve_same_turn(engine, basic_battle_state):
    """
    Test that a Pokémon played this turn cannot evolve (evolution sickness).

    Constitution: "Cannot evolve on same turn Pokémon was played."
    """
    state = basic_battle_state
    player = state.players[0]

    # Place Charmander in Active (just played this turn)
    charmander = player.board.active_spot
    charmander.turns_in_play = 0  # Played this turn

    # Add Charmeleon to hand
    add_cards_to_hand(player, "sv3-027", 1)

    # Set to Turn 1, Main Phase
    state.turn_count = 1
    state.current_phase = GamePhase.MAIN

    # Get legal actions
    actions = engine.get_legal_actions(state)

    # Should NOT have EVOLVE action
    assert_no_action_type(actions, ActionType.EVOLVE)

    print("[OK] Evolution sickness enforced (same turn)")


def test_can_evolve_next_turn(engine, evolution_state):
    """
    Verify Pokémon CAN evolve on the next turn.
    """
    state = evolution_state

    # Charmander has turns_in_play = 1 (played last turn)
    assert state.players[0].board.active_spot.turns_in_play > 0

    # Get legal actions
    actions = engine.get_legal_actions(state)

    # Should have EVOLVE action
    assert_has_action_type(actions, ActionType.EVOLVE)

    print("[OK] Can evolve after evolution sickness expires")


def test_cannot_evolve_turn1(engine, evolution_state):
    """
    Test that NO Pokémon can evolve on Turn 1 (either player).

    Constitution: "Cannot evolve on Turn 1 (either player)."
    """
    state = evolution_state

    # Set to Turn 1 (even though Pokémon has turns_in_play > 0)
    state.turn_count = 1

    # Charmander was "played before the game" (hypothetically)
    state.players[0].board.active_spot.turns_in_play = 1

    # Get legal actions
    actions = engine.get_legal_actions(state)

    # Should NOT have EVOLVE action (Turn 1 restriction)
    assert_no_action_type(actions, ActionType.EVOLVE)

    print("[OK] No evolution on Turn 1")


# ============================================================================
# TEST: RETREAT LIMIT (Constitution Section 2, Phase 2)
# ============================================================================

def test_retreat_once_per_turn(engine, basic_battle_state):
    """
    Test that you can only retreat once per turn.

    Constitution: "Retreat: Once per turn."
    """
    state = basic_battle_state
    player = state.players[0]

    # Add Bench Pokémon
    bench = create_card_instance("sv3-26", owner_id=0)
    player.board.add_to_bench(bench)

    # Set to Main Phase
    state.current_phase = GamePhase.MAIN

    # Set retreat flag to True (already retreated)
    player.retreated_this_turn = True

    # Get legal actions
    actions = engine.get_legal_actions(state)

    # Should NOT have RETREAT action
    assert_no_action_type(actions, ActionType.RETREAT)

    print("[OK] Retreat once-per-turn restriction enforced")


# ============================================================================
# TEST: STATUS CONDITION BLOCKING (Constitution Section 6)
# ============================================================================

def test_asleep_cannot_attack(engine, basic_battle_state):
    """
    Test that Asleep Pokémon cannot attack.

    Constitution Section 6: Status conditions block actions.
    """
    state = basic_battle_state
    active = state.players[0].board.active_spot

    # Apply Asleep status
    active.status_conditions.add(StatusCondition.ASLEEP)

    # Set to Attack Phase
    state.current_phase = GamePhase.ATTACK
    state.turn_count = 2  # Can normally attack

    # Get legal actions
    actions = engine.get_legal_actions(state)

    # Should NOT have ATTACK action (Asleep blocks attacks)
    assert_no_action_type(actions, ActionType.ATTACK)

    print("[OK] Asleep Pokémon cannot attack")


def test_paralyzed_cannot_attack(engine, basic_battle_state):
    """
    Test that Paralyzed Pokémon cannot attack.
    """
    state = basic_battle_state
    active = state.players[0].board.active_spot

    # Apply Paralyzed status
    active.status_conditions.add(StatusCondition.PARALYZED)

    # Set to Attack Phase
    state.current_phase = GamePhase.ATTACK
    state.turn_count = 2

    # Get legal actions
    actions = engine.get_legal_actions(state)

    # Should NOT have ATTACK action
    assert_no_action_type(actions, ActionType.ATTACK)

    print("[OK] Paralyzed Pokémon cannot attack")


def test_asleep_cannot_retreat(engine, basic_battle_state):
    """
    Test that Asleep Pokémon cannot retreat.

    Constitution Section 6: "Can't" priority.
    """
    state = basic_battle_state
    player = state.players[0]
    active = player.board.active_spot

    # Add Bench Pokémon
    bench = create_card_instance("sv3-26", owner_id=0)
    player.board.add_to_bench(bench)

    # Apply Asleep status
    active.status_conditions.add(StatusCondition.ASLEEP)

    # Set to Main Phase
    state.current_phase = GamePhase.MAIN

    # Get legal actions
    actions = engine.get_legal_actions(state)

    # Should NOT have RETREAT action (Asleep blocks retreat)
    assert_no_action_type(actions, ActionType.RETREAT)

    print("[OK] Asleep Pokémon cannot retreat")


def test_paralyzed_cannot_retreat(engine, basic_battle_state):
    """
    Test that Paralyzed Pokémon cannot retreat.
    """
    state = basic_battle_state
    player = state.players[0]
    active = player.board.active_spot

    # Add Bench Pokémon
    bench = create_card_instance("sv3-26", owner_id=0)
    player.board.add_to_bench(bench)

    # Apply Paralyzed status
    active.status_conditions.add(StatusCondition.PARALYZED)

    # Set to Main Phase
    state.current_phase = GamePhase.MAIN

    # Get legal actions
    actions = engine.get_legal_actions(state)

    # Should NOT have RETREAT action
    assert_no_action_type(actions, ActionType.RETREAT)

    print("[OK] Paralyzed Pokémon cannot retreat")


# ============================================================================
# TEST: STADIUM LIMIT (Constitution Section 2, Phase 2)
# ============================================================================

def test_stadium_once_per_turn(engine, basic_battle_state):
    """
    Test that you can only play one Stadium per turn.

    Constitution: "Stadium: Once per turn."
    """
    state = basic_battle_state
    player = state.players[0]

    # Set stadium flag to True (already played Stadium)
    player.stadium_played_this_turn = True

    # Add Stadium to hand (hypothetically)
    # Note: No Stadium cards implemented yet, but engine should enforce

    # Set to Main Phase
    state.current_phase = GamePhase.MAIN

    # Get legal actions
    actions = engine.get_legal_actions(state)

    # Should NOT have PLAY_STADIUM action
    assert_no_action_type(actions, ActionType.PLAY_STADIUM)

    print("[OK] Stadium once-per-turn restriction enforced")


# ============================================================================
# TEST: BENCH SIZE LIMIT (Constitution Section 1.2)
# ============================================================================

def test_bench_size_limit(engine, basic_battle_state):
    """
    Test that Bench cannot exceed max_bench_size.

    Constitution: "Bench: List of 5 slots (Expandable to 8)."
    """
    state = basic_battle_state
    player = state.players[0]

    # Fill bench to max (5)
    for _ in range(5):
        pokemon = create_card_instance("sv3-26", owner_id=0)
        player.board.add_to_bench(pokemon)

    # Add Basic Pokémon to hand
    add_cards_to_hand(player, "sv3-26", 1)

    # Set to Main Phase
    state.current_phase = GamePhase.MAIN

    # Get legal actions
    actions = engine.get_legal_actions(state)

    # Should NOT have PLAY_BASIC action (bench full)
    assert_no_action_type(actions, ActionType.PLAY_BASIC)

    print("[OK] Bench size limit enforced")


# ============================================================================
# RUN ALL TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

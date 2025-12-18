"""
Comprehensive pytest suite for Charizard ex Infernal Reign ability.

This tests the complete flow from evolution trigger through energy attachment
and subsequent attack availability.

Test Categories:
1. Evolution Paths
   - Charmeleon -> Charizard ex (normal evolution)
   - Charmander -> Rare Candy -> Charizard ex (skip evolution)

2. Deck Energy Variations
   - 3+ Fire Energy in deck (can select max)
   - 2 Fire Energy in deck (limited selection)
   - 1 Fire Energy in deck (minimal selection)
   - 0 Fire Energy in deck (decline only)

3. Attachment Target Variations
   - Attach all to Charizard (active)
   - Attach to bench Pokemon
   - Split between multiple Pokemon

4. Knowledge Layer Interactions
   - With deck knowledge initialized
   - Without deck knowledge (should still work)

5. Edge Cases
   - Empty deck (no search possible)
   - No Pokemon to attach to (shouldn't happen but test defense)
   - Multiple Charizard ex in play (hook should only trigger for evolved one)
"""

import pytest
import sys
sys.path.insert(0, 'src')

from models import (
    GameState, PlayerState, GamePhase, Action, ActionType,
    SearchAndAttachState, InterruptPhase, EnergyType, Subtype
)
from engine import PokemonEngine
from cards.factory import create_card_instance
from cards.registry import create_card
from actions import evolve_pokemon


@pytest.fixture
def engine():
    """Create PokemonEngine instance."""
    return PokemonEngine()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_evolution_state(
    active_card_id: str,
    hand_cards: list = None,
    deck_cards: list = None,
    bench_cards: list = None,
    turn_count: int = 2,
    turns_in_play: int = 1
):
    """
    Create a game state for evolution testing.

    Args:
        active_card_id: Card ID for active Pokemon
        hand_cards: List of card IDs to add to hand
        deck_cards: List of card IDs to add to deck
        bench_cards: List of card IDs to add to bench
        turn_count: Turn number (affects turn 1 restrictions)
        turns_in_play: How many turns active has been in play
    """
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Setup active
    active = create_card_instance(active_card_id, owner_id=0)
    active.turns_in_play = turns_in_play
    player0.board.active_spot = active

    # Opponent active
    player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

    # Add hand cards
    if hand_cards:
        for card_id in hand_cards:
            player0.hand.add_card(create_card_instance(card_id, owner_id=0))

    # Add deck cards
    if deck_cards:
        for card_id in deck_cards:
            player0.deck.add_card(create_card_instance(card_id, owner_id=0))

    # Add bench cards
    if bench_cards:
        for card_id in bench_cards:
            bench_pokemon = create_card_instance(card_id, owner_id=0)
            bench_pokemon.turns_in_play = 1
            player0.board.add_to_bench(bench_pokemon)

    return GameState(
        players=[player0, player1],
        turn_count=turn_count,
        active_player_index=0,
        current_phase=GamePhase.MAIN,
        starting_player_id=0
    )


def complete_infernal_reign_flow(engine, state, attach_targets: list = None, count: int = None):
    """
    Complete the full Infernal Reign interrupt flow.

    Args:
        engine: PokemonEngine instance
        state: GameState with pending_interrupt set
        attach_targets: List of target card IDs for each energy (or None to attach all to active)
        count: Optional specific count to select (defaults to max available)

    Returns:
        Final state after all energy attached
    """
    if not state.pending_interrupt:
        return state

    interrupt = state.pending_interrupt

    # Phase 1: Select count (new upfront count selection)
    if interrupt.phase == InterruptPhase.SELECT_COUNT:
        actions = engine.get_legal_actions(state)
        count_actions = [a for a in actions if a.action_type == ActionType.SEARCH_SELECT_COUNT]

        if count_actions:
            if count is not None:
                # Select specific count
                action = next((a for a in count_actions if a.choice_index == count), count_actions[-1])
            else:
                # Select max count (last action in list)
                action = count_actions[-1]

            state = engine.step(state, action)
            if state.pending_interrupt:
                interrupt = state.pending_interrupt

    # Legacy Phase 1: Select all available energy (kept for backward compatibility)
    while state.pending_interrupt and interrupt.phase == InterruptPhase.SEARCH_SELECT:
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SEARCH_SELECT_CARD]
        confirm_actions = [a for a in actions if a.action_type == ActionType.SEARCH_CONFIRM]

        if select_actions and len(interrupt.selected_card_ids) < interrupt.max_select:
            # Select an energy
            state = engine.step(state, select_actions[0])
            interrupt = state.pending_interrupt
        elif confirm_actions:
            # Confirm selection
            state = engine.step(state, confirm_actions[0])
            if state.pending_interrupt:
                interrupt = state.pending_interrupt
            break
        else:
            break

    # Phase 2: Attach energy
    attach_index = 0
    while state.pending_interrupt and state.pending_interrupt.phase == InterruptPhase.ATTACH_ENERGY:
        actions = engine.get_legal_actions(state)
        attach_actions = [a for a in actions if a.action_type == ActionType.INTERRUPT_ATTACH_ENERGY]

        if not attach_actions:
            break

        # Choose target
        if attach_targets and attach_index < len(attach_targets):
            target_id = attach_targets[attach_index]
            action = next((a for a in attach_actions if a.target_id == target_id), attach_actions[0])
        else:
            # Default to first option (usually active)
            action = attach_actions[0]

        state = engine.step(state, action)
        attach_index += 1

    return state


# =============================================================================
# TEST CLASS: EVOLUTION PATHS
# =============================================================================

class TestEvolutionPaths:
    """Test Infernal Reign triggers correctly from different evolution paths."""

    def test_charmeleon_to_charizard_triggers_infernal_reign(self, engine):
        """
        Normal evolution: Charmeleon -> Charizard ex should trigger Infernal Reign.
        """
        # Setup: Charmeleon active with Charizard ex in hand
        state = create_evolution_state(
            active_card_id="sv4pt5-8",  # Charmeleon
            hand_cards=["svp-56"],       # Charizard ex
            deck_cards=["sve-2", "sve-2", "sve-2"],  # 3 Basic Fire Energy
            turns_in_play=1
        )
        state = engine.initialize_deck_knowledge(state)

        charmeleon = state.players[0].board.active_spot
        charizard = state.players[0].hand.cards[0]

        # Evolve
        state = evolve_pokemon(state, 0, charmeleon.id, charizard.id, skip_stage=False)

        # Should have pending interrupt for Infernal Reign
        assert state.pending_interrupt is not None, "Infernal Reign should trigger"
        assert state.pending_interrupt.ability_name == "Infernal Reign"
        assert state.pending_interrupt.phase == InterruptPhase.SELECT_COUNT  # Uses upfront count selection

    def test_rare_candy_charmander_to_charizard_triggers_infernal_reign(self, engine):
        """
        Rare Candy evolution: Charmander -> Charizard ex should trigger Infernal Reign.
        """
        # Setup: Charmander active with Charizard ex in hand
        state = create_evolution_state(
            active_card_id="sv4pt5-7",  # Charmander
            hand_cards=["svp-56"],       # Charizard ex
            deck_cards=["sve-2", "sve-2", "sve-2"],  # 3 Basic Fire Energy
            turns_in_play=1
        )
        state = engine.initialize_deck_knowledge(state)

        charmander = state.players[0].board.active_spot
        charizard = state.players[0].hand.cards[0]

        # Evolve via Rare Candy (skip_stage=True)
        state = evolve_pokemon(state, 0, charmander.id, charizard.id, skip_stage=True)

        # Should have pending interrupt for Infernal Reign
        assert state.pending_interrupt is not None, "Infernal Reign should trigger via Rare Candy"
        assert state.pending_interrupt.ability_name == "Infernal Reign"

    def test_evolution_on_bench_triggers_infernal_reign(self, engine):
        """
        Evolution on bench should also trigger Infernal Reign.
        """
        # Setup: Charmeleon on bench
        state = create_evolution_state(
            active_card_id="sv3pt5-16",  # Pidgey as active
            hand_cards=["svp-56"],        # Charizard ex
            deck_cards=["sve-2", "sve-2"],
            bench_cards=["sv4pt5-8"],     # Charmeleon on bench
            turns_in_play=1
        )
        state = engine.initialize_deck_knowledge(state)

        charmeleon = state.players[0].board.bench[0]
        charizard = state.players[0].hand.cards[0]

        # Evolve bench Pokemon
        state = evolve_pokemon(state, 0, charmeleon.id, charizard.id, skip_stage=False)

        # Should trigger Infernal Reign
        assert state.pending_interrupt is not None, "Infernal Reign should trigger for bench evolution"
        assert state.pending_interrupt.ability_name == "Infernal Reign"


# =============================================================================
# TEST CLASS: DECK ENERGY VARIATIONS
# =============================================================================

class TestDeckEnergyVariations:
    """Test Infernal Reign with different amounts of Fire Energy in deck."""

    def test_three_fire_energy_in_deck(self, engine):
        """
        With 3 Fire Energy in deck, should have count options: 0, 1, 2, 3.
        """
        state = create_evolution_state(
            active_card_id="sv4pt5-8",  # Charmeleon
            hand_cards=["svp-56"],
            deck_cards=["sve-2", "sve-2", "sve-2"],  # Exactly 3 Fire Energy
        )
        state = engine.initialize_deck_knowledge(state)

        charmeleon = state.players[0].board.active_spot
        charizard = state.players[0].hand.cards[0]

        state = evolve_pokemon(state, 0, charmeleon.id, charizard.id, skip_stage=False)

        # Get legal actions - upfront count selection
        actions = engine.get_legal_actions(state)
        count_actions = [a for a in actions if a.action_type == ActionType.SEARCH_SELECT_COUNT]

        # Should have 4 options: 0 (decline), 1, 2, 3
        assert len(count_actions) == 4, f"Should have 4 count options (0,1,2,3), got {len(count_actions)}"

        # Complete the flow and verify all 3 attached (Infernal Reign allows up to 3)
        state = complete_infernal_reign_flow(engine, state)

        charizard = state.players[0].board.active_spot
        assert len(charizard.attached_energy) == 3, "Should have 3 energy attached (Infernal Reign max)"

    def test_two_fire_energy_in_deck(self, engine):
        """
        With 2 Fire Energy in deck, should have count options: 0, 1, 2.
        """
        state = create_evolution_state(
            active_card_id="sv4pt5-8",
            hand_cards=["svp-56"],
            deck_cards=["sve-2", "sve-2"],  # Only 2 Fire Energy
        )
        state = engine.initialize_deck_knowledge(state)

        charmeleon = state.players[0].board.active_spot
        charizard = state.players[0].hand.cards[0]

        state = evolve_pokemon(state, 0, charmeleon.id, charizard.id, skip_stage=False)

        actions = engine.get_legal_actions(state)
        count_actions = [a for a in actions if a.action_type == ActionType.SEARCH_SELECT_COUNT]

        # Should have 3 options: 0 (decline), 1, 2
        assert len(count_actions) == 3, f"Should have 3 count options (0,1,2), got {len(count_actions)}"

        state = complete_infernal_reign_flow(engine, state)
        charizard = state.players[0].board.active_spot
        assert len(charizard.attached_energy) == 2, "Should have 2 energy attached"

    def test_one_fire_energy_in_deck(self, engine):
        """
        With 1 Fire Energy in deck, should have count options: 0, 1.
        """
        state = create_evolution_state(
            active_card_id="sv4pt5-8",
            hand_cards=["svp-56"],
            deck_cards=["sve-2"],  # Only 1 Fire Energy
        )
        state = engine.initialize_deck_knowledge(state)

        charmeleon = state.players[0].board.active_spot
        charizard = state.players[0].hand.cards[0]

        state = evolve_pokemon(state, 0, charmeleon.id, charizard.id, skip_stage=False)

        actions = engine.get_legal_actions(state)
        count_actions = [a for a in actions if a.action_type == ActionType.SEARCH_SELECT_COUNT]

        # Should have 2 options: 0 (decline), 1
        assert len(count_actions) == 2, f"Should have 2 count options (0,1), got {len(count_actions)}"

        state = complete_infernal_reign_flow(engine, state)
        charizard = state.players[0].board.active_spot
        assert len(charizard.attached_energy) == 1, "Should have 1 energy attached"

    def test_zero_fire_energy_in_deck(self, engine):
        """
        With 0 Fire Energy in deck, should only have decline option (count = 0).
        """
        state = create_evolution_state(
            active_card_id="sv4pt5-8",
            hand_cards=["svp-56"],
            deck_cards=["sv3pt5-16", "sv3pt5-16"],  # Non-energy cards only
        )
        state = engine.initialize_deck_knowledge(state)

        charmeleon = state.players[0].board.active_spot
        charizard = state.players[0].hand.cards[0]

        state = evolve_pokemon(state, 0, charmeleon.id, charizard.id, skip_stage=False)

        # Should still trigger (player can "search" and find nothing)
        assert state.pending_interrupt is not None

        actions = engine.get_legal_actions(state)
        count_actions = [a for a in actions if a.action_type == ActionType.SEARCH_SELECT_COUNT]

        # Should only have 1 option: 0 (decline)
        assert len(count_actions) == 1, f"Should have 1 count option (0 only), got {len(count_actions)}"
        assert count_actions[0].choice_index == 0, "Only option should be decline (0)"

        # Select decline option
        state = engine.step(state, count_actions[0])

        # Interrupt should be complete
        assert state.pending_interrupt is None, "Interrupt should complete after decline"

    def test_mixed_energy_types_only_fire_selectable(self, engine):
        """
        With mixed energy types in deck, only Basic Fire Energy count determines options.
        """
        state = create_evolution_state(
            active_card_id="sv4pt5-8",
            hand_cards=["svp-56"],
            deck_cards=[
                "sve-2",   # Basic Fire Energy
                "sve-3",   # Basic Water Energy (should not be counted)
                "sve-4",   # Basic Grass Energy (should not be counted)
                "sve-2",   # Basic Fire Energy
            ],
        )
        state = engine.initialize_deck_knowledge(state)

        charmeleon = state.players[0].board.active_spot
        charizard = state.players[0].hand.cards[0]

        state = evolve_pokemon(state, 0, charmeleon.id, charizard.id, skip_stage=False)

        actions = engine.get_legal_actions(state)
        count_actions = [a for a in actions if a.action_type == ActionType.SEARCH_SELECT_COUNT]

        # Should have 3 options: 0 (decline), 1, 2 (only 2 Fire Energy in deck)
        assert len(count_actions) == 3, f"Should have 3 count options (0,1,2), got {len(count_actions)}"

        # Verify the options are 0, 1, 2
        counts = [a.choice_index for a in count_actions]
        assert counts == [0, 1, 2], f"Count options should be [0, 1, 2], got {counts}"


# =============================================================================
# TEST CLASS: ATTACHMENT TARGET VARIATIONS
# =============================================================================

class TestAttachmentTargets:
    """Test attaching energy to different Pokemon."""

    def test_attach_all_to_active(self, engine):
        """
        Attach all energy to the active Pokemon (Charizard ex).
        """
        state = create_evolution_state(
            active_card_id="sv4pt5-8",
            hand_cards=["svp-56"],
            deck_cards=["sve-2", "sve-2", "sve-2"],
            bench_cards=["sv3pt5-16"],  # Pidgey on bench
        )
        state = engine.initialize_deck_knowledge(state)

        charmeleon = state.players[0].board.active_spot
        charizard = state.players[0].hand.cards[0]

        state = evolve_pokemon(state, 0, charmeleon.id, charizard.id, skip_stage=False)

        # Get charizard ID after evolution
        charizard_id = state.players[0].board.active_spot.id

        # Complete flow attaching all to Charizard
        state = complete_infernal_reign_flow(engine, state, attach_targets=[charizard_id] * 3)

        charizard = state.players[0].board.active_spot
        bench = state.players[0].board.bench[0]

        assert len(charizard.attached_energy) == 3, "Charizard should have 3 energy"
        assert len(bench.attached_energy) == 0, "Bench Pokemon should have no energy"

    def test_attach_all_to_bench(self, engine):
        """
        Attach all energy to a bench Pokemon.
        """
        state = create_evolution_state(
            active_card_id="sv4pt5-8",
            hand_cards=["svp-56"],
            deck_cards=["sve-2", "sve-2"],
            bench_cards=["sv3pt5-16"],
        )
        state = engine.initialize_deck_knowledge(state)

        charmeleon = state.players[0].board.active_spot
        charizard = state.players[0].hand.cards[0]
        bench_pokemon_id = state.players[0].board.bench[0].id

        state = evolve_pokemon(state, 0, charmeleon.id, charizard.id, skip_stage=False)

        # Complete flow attaching all to bench
        state = complete_infernal_reign_flow(engine, state, attach_targets=[bench_pokemon_id] * 2)

        charizard = state.players[0].board.active_spot
        bench = state.players[0].board.bench[0]

        assert len(charizard.attached_energy) == 0, "Charizard should have no energy"
        assert len(bench.attached_energy) == 2, "Bench Pokemon should have 2 energy"

    def test_split_between_pokemon(self, engine):
        """
        Split energy between active and bench.
        """
        state = create_evolution_state(
            active_card_id="sv4pt5-8",
            hand_cards=["svp-56"],
            deck_cards=["sve-2", "sve-2", "sve-2"],
            bench_cards=["sv3pt5-16", "sv4pt5-7"],  # Pidgey and Charmander on bench
        )
        state = engine.initialize_deck_knowledge(state)

        charmeleon = state.players[0].board.active_spot
        charizard_hand = state.players[0].hand.cards[0]
        bench_0_id = state.players[0].board.bench[0].id
        bench_1_id = state.players[0].board.bench[1].id

        state = evolve_pokemon(state, 0, charmeleon.id, charizard_hand.id, skip_stage=False)

        charizard_id = state.players[0].board.active_spot.id

        # Attach: 1 to Charizard, 1 to bench[0], 1 to bench[1]
        state = complete_infernal_reign_flow(
            engine, state,
            attach_targets=[charizard_id, bench_0_id, bench_1_id]
        )

        charizard = state.players[0].board.active_spot
        bench_0 = state.players[0].board.bench[0]
        bench_1 = state.players[0].board.bench[1]

        assert len(charizard.attached_energy) == 1, "Charizard should have 1 energy"
        assert len(bench_0.attached_energy) == 1, "Bench[0] should have 1 energy"
        assert len(bench_1.attached_energy) == 1, "Bench[1] should have 1 energy"


# =============================================================================
# TEST CLASS: KNOWLEDGE LAYER INTERACTIONS
# =============================================================================

class TestKnowledgeLayerInteractions:
    """Test Infernal Reign with and without deck knowledge initialized."""

    def test_with_deck_knowledge_initialized(self, engine):
        """
        With deck knowledge, Infernal Reign should work correctly.
        """
        state = create_evolution_state(
            active_card_id="sv4pt5-8",
            hand_cards=["svp-56"],
            deck_cards=["sve-2", "sve-2"],
        )
        # Initialize deck knowledge
        state = engine.initialize_deck_knowledge(state)

        # Verify deck knowledge is initialized via initial_deck_counts
        assert len(state.players[0].initial_deck_counts) > 0, "Deck knowledge should be initialized"

        charmeleon = state.players[0].board.active_spot
        charizard = state.players[0].hand.cards[0]

        state = evolve_pokemon(state, 0, charmeleon.id, charizard.id, skip_stage=False)

        # Complete flow
        state = complete_infernal_reign_flow(engine, state)

        charizard = state.players[0].board.active_spot
        assert len(charizard.attached_energy) == 2

        # Verify energy has correct card_id
        for energy in charizard.attached_energy:
            assert energy.card_id == "sve-2", f"Energy should have correct card_id, got {energy.card_id}"

    def test_without_deck_knowledge_initialized(self, engine):
        """
        Without deck knowledge, Infernal Reign should still work.
        """
        state = create_evolution_state(
            active_card_id="sv4pt5-8",
            hand_cards=["svp-56"],
            deck_cards=["sve-2", "sve-2"],
        )
        # Do NOT initialize deck knowledge
        assert len(state.players[0].initial_deck_counts) == 0, "Deck knowledge should not be initialized"

        charmeleon = state.players[0].board.active_spot
        charizard = state.players[0].hand.cards[0]

        state = evolve_pokemon(state, 0, charmeleon.id, charizard.id, skip_stage=False)

        # Should still trigger and work
        assert state.pending_interrupt is not None

        state = complete_infernal_reign_flow(engine, state)

        charizard = state.players[0].board.active_spot
        assert len(charizard.attached_energy) == 2


# =============================================================================
# TEST CLASS: BURNING DARKNESS ATTACK INTEGRATION
# =============================================================================

class TestBurningDarknessIntegration:
    """Test that Burning Darkness is available after Infernal Reign."""

    def test_attack_available_after_attaching_2_fire(self, engine):
        """
        Burning Darkness requires [F][F]. After attaching 2 Fire via Infernal Reign,
        the attack should be available.
        """
        state = create_evolution_state(
            active_card_id="sv4pt5-8",
            hand_cards=["svp-56"],
            deck_cards=["sve-2", "sve-2"],
        )
        state = engine.initialize_deck_knowledge(state)

        charmeleon = state.players[0].board.active_spot
        charizard = state.players[0].hand.cards[0]

        state = evolve_pokemon(state, 0, charmeleon.id, charizard.id, skip_stage=False)

        # Complete Infernal Reign
        state = complete_infernal_reign_flow(engine, state)

        # Get legal actions - Burning Darkness should be available
        actions = engine.get_legal_actions(state)
        attack_actions = [a for a in actions if a.action_type == ActionType.ATTACK]

        assert len(attack_actions) == 1, f"Should have 1 attack available, got {len(attack_actions)}"
        assert attack_actions[0].attack_name == "Burning Darkness"

    def test_attack_not_available_with_only_1_fire(self, engine):
        """
        With only 1 Fire Energy attached, Burning Darkness should NOT be available.
        """
        state = create_evolution_state(
            active_card_id="sv4pt5-8",
            hand_cards=["svp-56"],
            deck_cards=["sve-2"],  # Only 1 Fire Energy
        )
        state = engine.initialize_deck_knowledge(state)

        charmeleon = state.players[0].board.active_spot
        charizard = state.players[0].hand.cards[0]

        state = evolve_pokemon(state, 0, charmeleon.id, charizard.id, skip_stage=False)
        state = complete_infernal_reign_flow(engine, state)

        actions = engine.get_legal_actions(state)
        attack_actions = [a for a in actions if a.action_type == ActionType.ATTACK]

        assert len(attack_actions) == 0, "Should have no attacks with only 1 Fire Energy"

    def test_attack_not_available_after_declining(self, engine):
        """
        After declining Infernal Reign (0 energy), Burning Darkness should NOT be available.
        """
        state = create_evolution_state(
            active_card_id="sv4pt5-8",
            hand_cards=["svp-56"],
            deck_cards=["sv3pt5-16"],  # Non-energy cards (Pidgey) so search finds nothing
        )
        state = engine.initialize_deck_knowledge(state)

        charmeleon = state.players[0].board.active_spot
        charizard = state.players[0].hand.cards[0]

        state = evolve_pokemon(state, 0, charmeleon.id, charizard.id, skip_stage=False)

        # Infernal Reign should trigger (ability activates even if no valid targets)
        if state.pending_interrupt:
            # Decline by selecting count = 0
            actions = engine.get_legal_actions(state)
            count_actions = [a for a in actions if a.action_type == ActionType.SEARCH_SELECT_COUNT]
            if count_actions:
                decline_action = next(a for a in count_actions if a.choice_index == 0)
                state = engine.step(state, decline_action)

        actions = engine.get_legal_actions(state)
        attack_actions = [a for a in actions if a.action_type == ActionType.ATTACK]

        assert len(attack_actions) == 0, "Should have no attacks after declining (no energy attached)"


# =============================================================================
# TEST CLASS: EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Test edge cases and defensive scenarios."""

    def test_empty_deck_still_allows_decline(self, engine):
        """
        With completely empty deck, should still allow declining the ability.
        """
        state = create_evolution_state(
            active_card_id="sv4pt5-8",
            hand_cards=["svp-56"],
            deck_cards=[],  # Empty deck
        )

        charmeleon = state.players[0].board.active_spot
        charizard = state.players[0].hand.cards[0]

        state = evolve_pokemon(state, 0, charmeleon.id, charizard.id, skip_stage=False)

        if state.pending_interrupt:
            actions = engine.get_legal_actions(state)
            count_actions = [a for a in actions if a.action_type == ActionType.SEARCH_SELECT_COUNT]

            assert len(count_actions) >= 1, "Should have decline option even with empty deck"

            # Should be able to complete without error
            state = engine.step(state, count_actions[0])
            assert state.pending_interrupt is None

    def test_multiple_charizard_only_evolved_one_triggers(self, engine):
        """
        If multiple Charizard ex in play, only the one that evolved should trigger.
        """
        state = create_evolution_state(
            active_card_id="svp-56",  # Charizard ex already active
            hand_cards=["svp-56"],     # Another Charizard ex to evolve
            deck_cards=["sve-2", "sve-2", "sve-2"],
            bench_cards=["sv4pt5-8"],  # Charmeleon on bench
        )
        state = engine.initialize_deck_knowledge(state)

        existing_charizard = state.players[0].board.active_spot
        bench_charmeleon = state.players[0].board.bench[0]
        hand_charizard = state.players[0].hand.cards[0]

        # Evolve the bench Charmeleon
        state = evolve_pokemon(state, 0, bench_charmeleon.id, hand_charizard.id, skip_stage=False)

        # Should trigger for the newly evolved Charizard
        assert state.pending_interrupt is not None
        assert state.pending_interrupt.source_card_id == hand_charizard.id

        # The existing Charizard should not have its hook triggered
        # (source_card_id should match the newly evolved one)

    def test_partial_selection_via_count(self, engine):
        """
        Player can select fewer than max by choosing a lower count upfront.
        """
        state = create_evolution_state(
            active_card_id="sv4pt5-8",
            hand_cards=["svp-56"],
            deck_cards=["sve-2", "sve-2", "sve-2"],  # 3 available
        )
        state = engine.initialize_deck_knowledge(state)

        charmeleon = state.players[0].board.active_spot
        charizard = state.players[0].hand.cards[0]

        state = evolve_pokemon(state, 0, charmeleon.id, charizard.id, skip_stage=False)

        # Select count = 1 (partial selection)
        actions = engine.get_legal_actions(state)
        count_actions = [a for a in actions if a.action_type == ActionType.SEARCH_SELECT_COUNT]
        # Find the action with choice_index = 1
        select_one_action = next(a for a in count_actions if a.choice_index == 1)
        state = engine.step(state, select_one_action)

        # Should proceed to attach phase with just 1 energy
        assert state.pending_interrupt.phase == InterruptPhase.ATTACH_ENERGY
        assert len(state.pending_interrupt.cards_to_attach) == 1

        # Complete attachment
        actions = engine.get_legal_actions(state)
        attach_actions = [a for a in actions if a.action_type == ActionType.INTERRUPT_ATTACH_ENERGY]
        state = engine.step(state, attach_actions[0])

        assert state.pending_interrupt is None
        charizard = state.players[0].board.active_spot
        assert len(charizard.attached_energy) == 1


# =============================================================================
# TEST CLASS: ENERGY CARD_ID VERIFICATION (Regression test for bug fix)
# =============================================================================

class TestEnergyCardIdVerification:
    """
    Regression tests to ensure energy attached via Infernal Reign
    has correct card_id (not the invalid 'basic-fire-energy' fallback).
    """

    def test_attached_energy_has_valid_card_id(self, engine):
        """
        Energy attached via SearchAndAttachState should have valid card_id.
        """
        state = create_evolution_state(
            active_card_id="sv4pt5-8",
            hand_cards=["svp-56"],
            deck_cards=["sve-2", "sve-2"],
        )
        state = engine.initialize_deck_knowledge(state)

        charmeleon = state.players[0].board.active_spot
        charizard = state.players[0].hand.cards[0]

        state = evolve_pokemon(state, 0, charmeleon.id, charizard.id, skip_stage=False)
        state = complete_infernal_reign_flow(engine, state)

        charizard = state.players[0].board.active_spot

        for i, energy in enumerate(charizard.attached_energy):
            # Verify card_id is valid (can be looked up)
            card_def = create_card(energy.card_id)
            assert card_def is not None, f"Energy {i} card_id '{energy.card_id}' should be valid"
            assert card_def.name == "Basic Fire Energy", f"Energy should be Fire, got {card_def.name}"

    def test_calculate_provided_energy_works_after_infernal_reign(self, engine):
        """
        _calculate_provided_energy should correctly count energy attached via Infernal Reign.
        """
        state = create_evolution_state(
            active_card_id="sv4pt5-8",
            hand_cards=["svp-56"],
            deck_cards=["sve-2", "sve-2", "sve-2"],
        )
        state = engine.initialize_deck_knowledge(state)

        charmeleon = state.players[0].board.active_spot
        charizard = state.players[0].hand.cards[0]

        state = evolve_pokemon(state, 0, charmeleon.id, charizard.id, skip_stage=False)
        state = complete_infernal_reign_flow(engine, state)

        charizard = state.players[0].board.active_spot
        provided = engine._calculate_provided_energy(charizard)

        assert provided.get('Fire', 0) == 3, f"Should count 3 Fire energy, got {provided}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

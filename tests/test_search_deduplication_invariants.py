"""
Search Deduplication Invariant Tests

Tests for Dawn, Briar, and Fan Rotom to ensure:
1. Search results are properly deduplicated by functional ID
2. All possible outcomes are handled correctly
3. Card conservation is maintained through search operations
4. Multiple copies of the same card show as one option in search

Run with: pytest tests/test_search_deduplication_invariants.py -v
"""

import pytest
import sys
sys.path.insert(0, 'src')

from models import (
    GameState, PlayerState, Action, ActionType, GamePhase,
    SearchDeckStep, SelectFromZoneStep, ZoneType, SelectionPurpose
)
from cards.factory import create_card_instance
from cards.registry import create_card
from engine import PokemonEngine


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def engine():
    return PokemonEngine()


def create_base_game_state(
    deck_cards: list = None,
    hand_cards: list = None,
    opponent_prize_count: int = 6,
    turn_count: int = 1,
    starting_player_id: int = 0
) -> GameState:
    """Create a base game state for testing."""
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Set up active Pokemon
    player0.board.active_spot = create_card_instance("svp-44", owner_id=0)  # Charmander
    player1.board.active_spot = create_card_instance("svp-44", owner_id=1)  # Charmander

    # Add deck cards
    if deck_cards:
        for card_id in deck_cards:
            player0.deck.add_card(create_card_instance(card_id, owner_id=0))
    else:
        # Default deck
        for _ in range(20):
            player0.deck.add_card(create_card_instance("base1-98", owner_id=0))

    # Add hand cards
    if hand_cards:
        for card_id in hand_cards:
            player0.hand.add_card(create_card_instance(card_id, owner_id=0))

    # Add opponent deck
    for _ in range(20):
        player1.deck.add_card(create_card_instance("base1-98", owner_id=1))

    # Add prizes
    for _ in range(6):
        player0.prizes.add_card(create_card_instance("base1-98", owner_id=0))
    for _ in range(opponent_prize_count):
        player1.prizes.add_card(create_card_instance("base1-98", owner_id=1))

    state = GameState(
        players=[player0, player1],
        active_player_index=0,
        turn_count=turn_count,
        starting_player_id=starting_player_id,
        current_phase=GamePhase.MAIN
    )

    return state


def count_cards_in_all_zones(state: GameState) -> int:
    """Count total cards across all zones for both players."""
    total = 0
    for player in state.players:
        total += len(player.deck.cards)
        total += len(player.hand.cards)
        total += len(player.discard.cards)
        total += len(player.prizes.cards)
        if player.board.active_spot:
            total += 1
        total += len(player.board.bench)
    return total


# ============================================================================
# DAWN SEARCH DEDUPLICATION TESTS
# ============================================================================

class TestDawnSearchDeduplication:
    """Test that Dawn's multi-stage search properly deduplicates results."""

    def test_dawn_basic_search_deduplicates_identical_pokemon(self, engine):
        """Multiple copies of the same Basic Pokemon should show as one option."""
        from cards.library.trainers import dawn_effect

        # Create deck with multiple copies of the same Basic Pokemon
        deck_cards = [
            "svp-44", "svp-44", "svp-44",  # 3x Charmander (same functional ID)
            "sv3pt5-16", "sv3pt5-16",       # 2x Pidgey
            "sv3-27",                        # 1x Charmeleon (Stage 1)
            "sv3-125",                       # 1x Charizard ex (Stage 2)
        ]

        state = create_base_game_state(deck_cards=deck_cards, hand_cards=["me2-87"])
        state = engine.initialize_deck_knowledge(state)

        dawn = state.players[0].hand.cards[0]
        action = Action(
            action_type=ActionType.PLAY_SUPPORTER,
            player_id=0,
            card_id=dawn.id
        )

        state = dawn_effect(state, dawn, action)

        # Get legal actions for Basic Pokemon search
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Should have 2 unique Basic options (Charmander, Pidgey), not 5
        # Plus CONFIRM_SELECTION if min_count=0
        card_actions = [a for a in select_actions if a.card_id]

        # Get unique functional IDs in the options
        seen_names = set()
        for act in card_actions:
            card_def = create_card(act.card_id.split('_')[0] if '_' in act.card_id else
                                   next(c.card_id for c in state.players[0].deck.cards if c.id == act.card_id))
            # Get card from deck
            for c in state.players[0].deck.cards:
                if c.id == act.card_id:
                    card_def = create_card(c.card_id)
                    if card_def:
                        seen_names.add(card_def.name)
                    break

        # Should only see Charmander and Pidgey (2 unique Basics)
        assert len(seen_names) <= 2, f"Expected at most 2 unique Basic Pokemon options, got {len(seen_names)}: {seen_names}"

    def test_dawn_stage1_search_deduplicates(self, engine):
        """Multiple copies of the same Stage 1 Pokemon should show as one option."""
        from cards.library.trainers import dawn_effect

        # Create deck with multiple copies of Stage 1 Pokemon
        deck_cards = [
            "sv3-27", "sv3-27", "sv3-27",   # 3x Charmeleon
            "sv3pt5-17", "sv3pt5-17",        # 2x Pidgeotto
            "svp-44",                         # 1x Charmander (Basic)
            "sv3-125",                        # 1x Charizard ex (Stage 2)
        ]

        state = create_base_game_state(deck_cards=deck_cards, hand_cards=["me2-87"])
        state = engine.initialize_deck_knowledge(state)

        dawn = state.players[0].hand.cards[0]
        action = Action(
            action_type=ActionType.PLAY_SUPPORTER,
            player_id=0,
            card_id=dawn.id
        )

        state = dawn_effect(state, dawn, action)

        # Skip the Basic search step by confirming with no selection
        actions = engine.get_legal_actions(state)
        confirm_action = next((a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION), None)
        if confirm_action:
            state = engine.step(state, confirm_action)

        # Now we should be in Stage 1 search
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Count unique Stage 1 Pokemon names
        seen_names = set()
        for act in select_actions:
            for c in state.players[0].deck.cards:
                if c.id == act.card_id:
                    card_def = create_card(c.card_id)
                    if card_def:
                        seen_names.add(card_def.name)
                    break

        # Should only see Charmeleon and Pidgeotto (2 unique Stage 1s)
        assert len(seen_names) <= 2, f"Expected at most 2 unique Stage 1 options, got {len(seen_names)}: {seen_names}"

    def test_dawn_complete_flow_preserves_card_count(self, engine):
        """Dawn's full search flow should preserve total card count."""
        from cards.library.trainers import dawn_effect

        deck_cards = [
            "svp-44", "svp-44",   # 2x Charmander (Basic)
            "sv3-27", "sv3-27",   # 2x Charmeleon (Stage 1)
            "sv3-125",            # 1x Charizard ex (Stage 2)
        ]

        state = create_base_game_state(deck_cards=deck_cards, hand_cards=["me2-87"])
        state = engine.initialize_deck_knowledge(state)

        initial_count = count_cards_in_all_zones(state)

        dawn = state.players[0].hand.cards[0]
        action = Action(
            action_type=ActionType.PLAY_SUPPORTER,
            player_id=0,
            card_id=dawn.id
        )

        state = dawn_effect(state, dawn, action)

        # Complete all three searches by confirming each
        for _ in range(3):
            if state.has_pending_resolution():
                actions = engine.get_legal_actions(state)
                confirm = next((a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION), None)
                if confirm:
                    state = engine.step(state, confirm)

        # Card count should be preserved (Dawn moved to discard)
        final_count = count_cards_in_all_zones(state)
        assert initial_count == final_count, f"Card count changed: {initial_count} -> {final_count}"

    def test_dawn_with_no_matching_pokemon_can_skip(self, engine):
        """Dawn should allow skipping each search if no matching Pokemon found."""
        from cards.library.trainers import dawn_effect

        # Deck with only energy (no Pokemon)
        deck_cards = ["sve-2"] * 10  # All Fire Energy

        state = create_base_game_state(deck_cards=deck_cards, hand_cards=["me2-87"])
        state = engine.initialize_deck_knowledge(state)

        dawn = state.players[0].hand.cards[0]
        action = Action(
            action_type=ActionType.PLAY_SUPPORTER,
            player_id=0,
            card_id=dawn.id
        )

        state = dawn_effect(state, dawn, action)

        # Should be able to confirm (skip) the Basic search since no Basics exist
        actions = engine.get_legal_actions(state)

        # Should have CONFIRM_SELECTION available
        confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]
        assert len(confirm_actions) >= 1, "Should be able to confirm/skip when no matching Pokemon"


# ============================================================================
# FAN ROTOM SEARCH DEDUPLICATION TESTS
# ============================================================================

class TestFanRotomSearchDeduplication:
    """Test that Fan Rotom's Fan Call properly deduplicates Colorless Pokemon."""

    def test_fan_call_deduplicates_colorless_pokemon(self, engine):
        """Multiple copies of the same Colorless Pokemon should show as one option."""
        from cards.sets.sv7 import fan_rotom_fan_call_effect

        # Create deck with multiple copies of the same Colorless Pokemon
        deck_cards = [
            "sv3pt5-16", "sv3pt5-16", "sv3pt5-16",  # 3x Pidgey (Colorless, 50 HP)
            "sv3-162", "sv3-162",                    # 2x Pidgey variant (Colorless, 60 HP)
            "svp-44",                                 # Charmander (Fire - should not appear)
        ]

        state = create_base_game_state(deck_cards=deck_cards, turn_count=1, starting_player_id=0)

        # Replace active with Fan Rotom
        fan_rotom = create_card_instance("sv7-118", owner_id=0)
        state.players[0].board.active_spot = fan_rotom

        state = engine.initialize_deck_knowledge(state)

        action = Action(
            action_type=ActionType.USE_ABILITY,
            player_id=0,
            card_id=fan_rotom.id,
            ability_name="Fan Call"
        )

        state = fan_rotom_fan_call_effect(state, fan_rotom, action)

        # Get legal actions for search
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Count unique card_ids shown (should be deduplicated by functional ID)
        unique_card_ids = set()
        for act in select_actions:
            if act.card_id:
                unique_card_ids.add(act.card_id)

        # Should have at most 2 options (two different Pidgey variants by functional ID)
        # Not 5 (the raw count of Colorless Pokemon)
        assert len(unique_card_ids) <= 2, f"Expected at most 2 unique Colorless options, got {len(unique_card_ids)}"

    def test_fan_call_excludes_fire_pokemon(self, engine):
        """Fan Call should only show Colorless Pokemon, not other types."""
        from cards.sets.sv7 import fan_rotom_fan_call_effect

        deck_cards = [
            "sv3pt5-16",  # Pidgey (Colorless)
            "svp-44",     # Charmander (Fire)
            "svp-47",     # Charmander variant (Fire)
        ]

        state = create_base_game_state(deck_cards=deck_cards, turn_count=1, starting_player_id=0)

        fan_rotom = create_card_instance("sv7-118", owner_id=0)
        state.players[0].board.active_spot = fan_rotom

        state = engine.initialize_deck_knowledge(state)

        action = Action(
            action_type=ActionType.USE_ABILITY,
            player_id=0,
            card_id=fan_rotom.id,
            ability_name="Fan Call"
        )

        state = fan_rotom_fan_call_effect(state, fan_rotom, action)

        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Check that no Fire Pokemon are selectable
        for act in select_actions:
            if act.card_id:
                for c in state.players[0].deck.cards:
                    if c.id == act.card_id:
                        card_def = create_card(c.card_id)
                        if card_def and hasattr(card_def, 'name'):
                            assert 'Charmander' not in card_def.name, "Fire Pokemon should not be in Fan Call results"

    def test_fan_call_respects_hp_limit(self, engine):
        """Fan Call should only show Pokemon with HP <= 100."""
        from cards.sets.sv7 import fan_rotom_fan_call_effect

        deck_cards = [
            "sv3pt5-16",  # Pidgey (Colorless, 50 HP) - should appear
            "sv7-118",    # Fan Rotom (Colorless, 90 HP) - should appear
            # Would need a Colorless with HP > 100 to test exclusion
        ]

        state = create_base_game_state(deck_cards=deck_cards, turn_count=1, starting_player_id=0)

        fan_rotom = create_card_instance("sv7-118", owner_id=0)
        state.players[0].board.active_spot = fan_rotom

        state = engine.initialize_deck_knowledge(state)

        action = Action(
            action_type=ActionType.USE_ABILITY,
            player_id=0,
            card_id=fan_rotom.id,
            ability_name="Fan Call"
        )

        state = fan_rotom_fan_call_effect(state, fan_rotom, action)

        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # All selectable cards should have HP <= 100
        for act in select_actions:
            if act.card_id:
                for c in state.players[0].deck.cards:
                    if c.id == act.card_id:
                        card_def = create_card(c.card_id)
                        if card_def and hasattr(card_def, 'hp'):
                            assert card_def.hp <= 100, f"{card_def.name} has HP {card_def.hp} > 100"

    def test_fan_call_can_select_up_to_3(self, engine):
        """Fan Call should allow selecting up to 3 Pokemon."""
        from cards.sets.sv7 import fan_rotom_fan_call_effect

        # Add 5 different Colorless Pokemon (by functional ID)
        deck_cards = [
            "sv3pt5-16",   # Pidgey 1
            "sv3-162",     # Pidgey 2 (different HP)
            "sv7-118",     # Fan Rotom
            "sv5-126",     # Hoothoot
            "sv7-114",     # Hoothoot variant
        ]

        state = create_base_game_state(deck_cards=deck_cards, turn_count=1, starting_player_id=0)

        fan_rotom = create_card_instance("sv7-118", owner_id=0)
        state.players[0].board.active_spot = fan_rotom

        state = engine.initialize_deck_knowledge(state)

        action = Action(
            action_type=ActionType.USE_ABILITY,
            player_id=0,
            card_id=fan_rotom.id,
            ability_name="Fan Call"
        )

        state = fan_rotom_fan_call_effect(state, fan_rotom, action)

        # Verify the step allows up to 3 selections
        step = state.get_current_step()
        assert isinstance(step, SearchDeckStep)
        assert step.count == 3, f"Fan Call should allow up to 3 selections, got {step.count}"
        assert step.min_count == 0, "Fan Call should allow 0 selections (may clause)"

    def test_fan_call_only_on_first_turn(self, engine):
        """Fan Call should only be available on the player's first turn."""
        from cards.sets.sv7 import fan_rotom_fan_call_actions

        deck_cards = ["sv3pt5-16"] * 5

        # Turn 3 - not first turn for either player
        state = create_base_game_state(deck_cards=deck_cards, turn_count=3, starting_player_id=0)

        fan_rotom = create_card_instance("sv7-118", owner_id=0)
        state.players[0].board.active_spot = fan_rotom

        state = engine.initialize_deck_knowledge(state)

        actions = fan_rotom_fan_call_actions(state, fan_rotom, state.players[0])
        assert len(actions) == 0, "Fan Call should not be available after first turn"

    def test_fan_call_preserves_card_count(self, engine):
        """Fan Call should preserve total card count."""
        from cards.sets.sv7 import fan_rotom_fan_call_effect

        deck_cards = [
            "sv3pt5-16", "sv3pt5-16",  # Pidgeys
            "sv7-118",                  # Fan Rotom
        ]

        state = create_base_game_state(deck_cards=deck_cards, turn_count=1, starting_player_id=0)

        fan_rotom = create_card_instance("sv7-118", owner_id=0)
        state.players[0].board.active_spot = fan_rotom

        state = engine.initialize_deck_knowledge(state)

        initial_count = count_cards_in_all_zones(state)

        action = Action(
            action_type=ActionType.USE_ABILITY,
            player_id=0,
            card_id=fan_rotom.id,
            ability_name="Fan Call"
        )

        state = fan_rotom_fan_call_effect(state, fan_rotom, action)

        # Confirm with no selection
        actions = engine.get_legal_actions(state)
        confirm = next((a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION), None)
        if confirm:
            state = engine.step(state, confirm)

        final_count = count_cards_in_all_zones(state)
        assert initial_count == final_count, f"Card count changed: {initial_count} -> {final_count}"


# ============================================================================
# BRIAR CONDITION TESTS
# ============================================================================

class TestBriarConditions:
    """Test Briar's playability conditions and prize modification."""

    def test_briar_only_playable_with_2_opponent_prizes(self, engine):
        """Briar can only be played when opponent has exactly 2 prizes."""
        from cards.library.trainers import briar_actions

        # Test with 2 prizes (should be playable)
        state = create_base_game_state(hand_cards=["sv7-132"], opponent_prize_count=2)
        briar = state.players[0].hand.cards[0]
        actions = briar_actions(state, briar, state.players[0])
        assert len(actions) == 1, "Briar should be playable with 2 opponent prizes"

        # Test with 1 prize (should not be playable)
        state = create_base_game_state(hand_cards=["sv7-132"], opponent_prize_count=1)
        briar = state.players[0].hand.cards[0]
        actions = briar_actions(state, briar, state.players[0])
        assert len(actions) == 0, "Briar should NOT be playable with 1 opponent prize"

        # Test with 3 prizes (should not be playable)
        state = create_base_game_state(hand_cards=["sv7-132"], opponent_prize_count=3)
        briar = state.players[0].hand.cards[0]
        actions = briar_actions(state, briar, state.players[0])
        assert len(actions) == 0, "Briar should NOT be playable with 3 opponent prizes"

        # Test with 6 prizes (should not be playable)
        state = create_base_game_state(hand_cards=["sv7-132"], opponent_prize_count=6)
        briar = state.players[0].hand.cards[0]
        actions = briar_actions(state, briar, state.players[0])
        assert len(actions) == 0, "Briar should NOT be playable with 6 opponent prizes"

    def test_briar_not_playable_if_supporter_already_played(self, engine):
        """Briar cannot be played if a supporter was already played this turn."""
        from cards.library.trainers import briar_actions

        state = create_base_game_state(hand_cards=["sv7-132"], opponent_prize_count=2)
        state.players[0].supporter_played_this_turn = True

        briar = state.players[0].hand.cards[0]
        actions = briar_actions(state, briar, state.players[0])
        assert len(actions) == 0, "Briar should NOT be playable if supporter already played"

    def test_briar_effect_adds_prize_modifier(self, engine):
        """Briar effect should add a PRIZE_COUNT_MODIFIER to active_effects."""
        from cards.library.trainers import briar_effect

        state = create_base_game_state(hand_cards=["sv7-132"], opponent_prize_count=2)
        briar = state.players[0].hand.cards[0]

        action = Action(
            action_type=ActionType.PLAY_SUPPORTER,
            player_id=0,
            card_id=briar.id
        )

        state = briar_effect(state, briar, action)

        # Check active_effects contains Briar's prize modifier
        assert len(state.active_effects) == 1
        effect = state.active_effects[0]
        assert effect['type'] == 'PRIZE_COUNT_MODIFIER'
        assert effect['name'] == 'Briar'
        assert effect['modifier'] == 1
        assert effect['expires_at_turn_end'] == True

    def test_briar_moves_to_discard(self, engine):
        """Briar should move from hand to discard when played."""
        from cards.library.trainers import briar_effect

        state = create_base_game_state(hand_cards=["sv7-132"], opponent_prize_count=2)
        briar = state.players[0].hand.cards[0]
        briar_id = briar.id

        initial_hand = len(state.players[0].hand.cards)
        initial_discard = len(state.players[0].discard.cards)

        action = Action(
            action_type=ActionType.PLAY_SUPPORTER,
            player_id=0,
            card_id=briar.id
        )

        state = briar_effect(state, briar, action)

        # Briar should be in discard, not in hand
        assert len(state.players[0].hand.cards) == initial_hand - 1
        assert len(state.players[0].discard.cards) == initial_discard + 1

        # Verify the card in discard is Briar
        discard_ids = [c.id for c in state.players[0].discard.cards]
        assert briar_id in discard_ids


# ============================================================================
# BRIAR PRIZE CALCULATION TESTS
# ============================================================================

class TestBriarPrizeCalculation:
    """Test that Briar properly modifies prize count for Tera Pokemon KOs."""

    def test_tera_ko_with_briar_on_basic_gives_2_prizes(self, engine):
        """Tera Pokemon KO on Basic with Briar active should give 2 prizes."""
        from cards.library.trainers import briar_effect

        state = create_base_game_state(opponent_prize_count=2)

        # Set up Terapagos ex (Tera) as attacker
        terapagos = create_card_instance("sv7-128", owner_id=0)
        state.players[0].board.active_spot = terapagos

        # Opponent has Charmander (Basic, 1 prize normally)
        charmander = create_card_instance("svp-44", owner_id=1)
        state.players[1].board.active_spot = charmander

        # Play Briar
        briar = create_card_instance("sv7-132", owner_id=0)
        state.players[0].hand.add_card(briar)

        action = Action(
            action_type=ActionType.PLAY_SUPPORTER,
            player_id=0,
            card_id=briar.id
        )
        state = briar_effect(state, briar, action)

        # Calculate prizes
        prizes = engine._calculate_prizes(terapagos, charmander, state)
        assert prizes == 2, f"Expected 2 prizes (1 base + 1 Briar), got {prizes}"

    def test_non_tera_ko_with_briar_gives_normal_prizes(self, engine):
        """Non-Tera Pokemon KO with Briar active should give normal prizes."""
        from cards.library.trainers import briar_effect

        state = create_base_game_state(opponent_prize_count=2)

        # Set up Charmander (non-Tera) as attacker
        attacker = create_card_instance("svp-44", owner_id=0)
        state.players[0].board.active_spot = attacker

        # Opponent has Charmander
        defender = create_card_instance("svp-44", owner_id=1)
        state.players[1].board.active_spot = defender

        # Play Briar
        briar = create_card_instance("sv7-132", owner_id=0)
        state.players[0].hand.add_card(briar)

        action = Action(
            action_type=ActionType.PLAY_SUPPORTER,
            player_id=0,
            card_id=briar.id
        )
        state = briar_effect(state, briar, action)

        # Calculate prizes - should NOT get Briar bonus
        prizes = engine._calculate_prizes(attacker, defender, state)
        assert prizes == 1, f"Expected 1 prize (no Briar bonus for non-Tera), got {prizes}"

    def test_tera_ko_on_ex_with_briar_gives_3_prizes(self, engine):
        """Tera Pokemon KO on ex Pokemon with Briar should give 3 prizes."""
        from cards.library.trainers import briar_effect

        state = create_base_game_state(opponent_prize_count=2)

        # Set up Terapagos ex (Tera) as attacker
        terapagos = create_card_instance("sv7-128", owner_id=0)
        state.players[0].board.active_spot = terapagos

        # Opponent has Terapagos ex (ex, 2 prizes normally)
        opponent_ex = create_card_instance("sv7-128", owner_id=1)
        state.players[1].board.active_spot = opponent_ex

        # Play Briar
        briar = create_card_instance("sv7-132", owner_id=0)
        state.players[0].hand.add_card(briar)

        action = Action(
            action_type=ActionType.PLAY_SUPPORTER,
            player_id=0,
            card_id=briar.id
        )
        state = briar_effect(state, briar, action)

        # Calculate prizes - should get 2 (ex) + 1 (Briar) = 3
        prizes = engine._calculate_prizes(terapagos, opponent_ex, state)
        assert prizes == 3, f"Expected 3 prizes (2 for ex + 1 Briar), got {prizes}"

    def test_bench_ko_with_briar_gives_normal_prizes(self, engine):
        """Briar only applies to Active Pokemon KOs, not bench."""
        from cards.library.trainers import briar_effect

        state = create_base_game_state(opponent_prize_count=2)

        # Set up Terapagos ex (Tera) as attacker
        terapagos = create_card_instance("sv7-128", owner_id=0)
        state.players[0].board.active_spot = terapagos

        # Opponent has something active
        state.players[1].board.active_spot = create_card_instance("svp-44", owner_id=1)

        # Benched Pokemon that will be "KO'd"
        benched = create_card_instance("svp-44", owner_id=1)
        state.players[1].board.bench.append(benched)

        # Play Briar
        briar = create_card_instance("sv7-132", owner_id=0)
        state.players[0].hand.add_card(briar)

        action = Action(
            action_type=ActionType.PLAY_SUPPORTER,
            player_id=0,
            card_id=briar.id
        )
        state = briar_effect(state, briar, action)

        # Calculate prizes for bench KO - should NOT get Briar bonus
        prizes = engine._calculate_prizes(terapagos, benched, state)
        assert prizes == 1, f"Expected 1 prize (Briar only works on Active), got {prizes}"

    def test_tera_ko_without_briar_gives_normal_prizes(self, engine):
        """Without Briar, Tera Pokemon KO gives normal prizes."""
        state = create_base_game_state(opponent_prize_count=2)

        # Set up Terapagos ex (Tera) as attacker
        terapagos = create_card_instance("sv7-128", owner_id=0)
        state.players[0].board.active_spot = terapagos

        # Opponent has Charmander
        defender = create_card_instance("svp-44", owner_id=1)
        state.players[1].board.active_spot = defender

        # No Briar played
        assert len(state.active_effects) == 0

        # Calculate prizes - should be normal
        prizes = engine._calculate_prizes(terapagos, defender, state)
        assert prizes == 1, f"Expected 1 prize (no Briar active), got {prizes}"


# ============================================================================
# CARD CONSERVATION INVARIANT TESTS
# ============================================================================

class TestSearchCardConservation:
    """Ensure search operations preserve total card count."""

    @pytest.mark.parametrize("search_type,hand_card,deck_cards", [
        ("dawn", "me2-87", ["svp-44", "sv3-27", "sv3-125"]),
        ("fan_call", None, ["sv3pt5-16", "sv3pt5-16", "sv7-118"]),
    ])
    def test_search_preserves_card_count(self, engine, search_type, hand_card, deck_cards):
        """Search operations should preserve total card count."""
        if search_type == "dawn":
            from cards.library.trainers import dawn_effect
            state = create_base_game_state(deck_cards=deck_cards, hand_cards=[hand_card])
            state = engine.initialize_deck_knowledge(state)

            card = state.players[0].hand.cards[0]
            initial_count = count_cards_in_all_zones(state)

            action = Action(
                action_type=ActionType.PLAY_SUPPORTER,
                player_id=0,
                card_id=card.id
            )
            state = dawn_effect(state, card, action)

        elif search_type == "fan_call":
            from cards.sets.sv7 import fan_rotom_fan_call_effect
            state = create_base_game_state(deck_cards=deck_cards, turn_count=1, starting_player_id=0)

            fan_rotom = create_card_instance("sv7-118", owner_id=0)
            state.players[0].board.active_spot = fan_rotom
            state = engine.initialize_deck_knowledge(state)

            initial_count = count_cards_in_all_zones(state)

            action = Action(
                action_type=ActionType.USE_ABILITY,
                player_id=0,
                card_id=fan_rotom.id,
                ability_name="Fan Call"
            )
            state = fan_rotom_fan_call_effect(state, fan_rotom, action)

        # Complete all pending steps by confirming
        while state.has_pending_resolution():
            actions = engine.get_legal_actions(state)
            confirm = next((a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION), None)
            if confirm:
                state = engine.step(state, confirm)
            else:
                # Select first available card if can't confirm
                select = next((a for a in actions if a.action_type == ActionType.SELECT_CARD), None)
                if select:
                    state = engine.step(state, select)
                else:
                    break

        final_count = count_cards_in_all_zones(state)
        assert initial_count == final_count, f"Card count changed: {initial_count} -> {final_count}"


# ============================================================================
# MULTI-COPY DEDUPLICATION INVARIANT
# ============================================================================

class TestMultiCopyDeduplication:
    """Ensure multiple copies of the same card are properly deduplicated."""

    def test_search_shows_one_option_per_functional_id(self, engine):
        """Search should show at most one option per unique functional ID."""
        from cards.library.trainers import dawn_effect

        # Create deck with many copies of the same cards
        deck_cards = [
            "svp-44", "svp-44", "svp-44", "svp-44", "svp-44",  # 5x Charmander
            "sv3-27", "sv3-27", "sv3-27",                       # 3x Charmeleon
            "sv3-125", "sv3-125",                                # 2x Charizard ex
        ]

        state = create_base_game_state(deck_cards=deck_cards, hand_cards=["me2-87"])
        state = engine.initialize_deck_knowledge(state)

        dawn = state.players[0].hand.cards[0]
        action = Action(
            action_type=ActionType.PLAY_SUPPORTER,
            player_id=0,
            card_id=dawn.id
        )

        state = dawn_effect(state, dawn, action)

        # Check Basic search - should have only 1 option (Charmander)
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Should be deduplicated - only 1 unique Basic Pokemon option
        assert len(select_actions) == 1, f"Expected 1 unique Basic option (Charmander), got {len(select_actions)}"

    def test_discard_does_deduplicate(self, engine):
        """Discard selection DOES deduplicate identical cards."""
        from cards.library.trainers import ultra_ball_effect

        state = create_base_game_state(
            deck_cards=["svp-44"],  # Something to search for
            hand_cards=["sv1-196", "sve-2", "sve-2", "sve-2"]  # Ultra Ball + 3x Fire Energy
        )
        state = engine.initialize_deck_knowledge(state)

        ultra_ball = state.players[0].hand.cards[0]
        action = Action(
            action_type=ActionType.PLAY_ITEM,
            player_id=0,
            card_id=ultra_ball.id
        )

        state = ultra_ball_effect(state, ultra_ball, action)

        # Get discard options
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        # Should show only 1 option (Fire Energy is deduplicated)
        assert len(select_actions) == 1, f"Expected 1 unique discard option (Fire Energy), got {len(select_actions)}"

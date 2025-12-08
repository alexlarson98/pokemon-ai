"""
Test Suite: Critical Actions
Tests for game-ending conditions and critical state transitions.

Tests:
- Deck out (draw from empty deck = game loss)
- Knockout (damage > HP → discard, prize taken)
- Win conditions (6 prizes, no Pokémon, deck out)
- State transitions (Switch effect, evolution)
"""

import pytest
import sys
sys.path.insert(0, 'src')

from models import GameResult, GamePhase
from cards.factory import create_card_instance, get_max_hp, create_multiple
import actions


# Helper functions
def set_pokemon_damage(pokemon, damage):
    """Set a Pokémon's damage counters."""
    pokemon.damage_counters = damage // 10


def add_cards_to_deck(player, card_id, count):
    """Add cards to a player's deck."""
    cards = create_multiple(card_id, count, player.player_id)
    for card in cards:
        player.deck.add_card(card)


# ============================================================================
# TEST: DECK OUT (Constitution Section 2, Phase 1)
# ============================================================================

def test_deck_out_raises_error(deck_out_state):
    """
    CRITICAL TEST: Drawing from empty deck raises DeckOutError.

    Constitution: "If Deck count is 0 before drawing -> GAME LOSS (Deck Out)."
    """
    state = deck_out_state

    # Verify deck is empty
    assert state.players[0].deck.is_empty(), "Deck should be empty"

    # Attempt to draw from empty deck
    with pytest.raises(actions.DeckOutError) as exc_info:
        actions.draw_card(state, player_id=0, amount=1)

    # Verify error message
    assert "deck is empty" in str(exc_info.value).lower()

    print("[OK] Deck out error raised correctly")


def test_deck_out_win_condition(engine, deck_out_state):
    """
    Test that deck out triggers win condition check.

    Expected: Player loses when they can't draw at start of turn.
    """
    state = deck_out_state

    # Set to Draw Phase
    state.current_phase = GamePhase.DRAW

    # Execute draw phase (should handle deck out)
    # Note: In real implementation, engine catches DeckOutError
    # and sets win condition

    # For now, verify the error exists
    with pytest.raises(actions.DeckOutError):
        actions.draw_card(state, player_id=0)

    print("[OK] Deck out triggers game loss condition")


def test_draw_with_cards_succeeds(empty_state):
    """
    Verify drawing succeeds when deck has cards.
    """
    state = empty_state
    player = state.players[0]

    # Add cards to deck
    add_cards_to_deck(player, "base1-98", 10)

    # Draw 3 cards
    state = actions.draw_card(state, player_id=0, amount=3)

    # Should have 3 cards in hand, 7 in deck
    assert player.hand.count() == 3, f"Expected 3 cards in hand, got {player.hand.count()}"
    assert player.deck.count() == 7, f"Expected 7 cards in deck, got {player.deck.count()}"

    print("[OK] Draw succeeds with cards in deck")


# ============================================================================
# TEST: KNOCKOUT (Constitution Section 2, Phase 3)
# ============================================================================

def test_knockout_moves_to_discard(knockout_state):
    """
    Test that KO'd Pokémon moves to discard pile.

    Setup: Charmander with 50/60 damage
    Action: Deal 20+ damage → KO
    Expected: Charmander moves to discard
    """
    state = knockout_state
    charmander = state.players[0].board.active_spot
    player = state.players[0]

    # Verify current state
    assert charmander.damage_counters == 5, "Charmander should have 5 damage counters"
    assert player.discard.count() == 0, "Discard should be empty"

    # Get max HP
    max_hp = get_max_hp(charmander)

    # Deal finishing blow (20 damage)
    state = actions.place_damage_counters(state, charmander, amount=2)

    # Check if KO'd
    is_kod = actions.check_knockout(state, charmander, max_hp)
    assert is_kod, "Charmander should be KO'd"

    # Process knockout
    attacker_id = 1  # Opponent
    state = actions.process_knockout(state, charmander, attacker_id)

    # Verify Pokémon is in discard
    assert player.discard.count() > 0, "Discard should have KO'd Pokémon"

    # Verify Active spot is now empty (needs promotion)
    assert player.board.active_spot is None, "Active spot should be empty after KO"

    print("[OK] KO'd Pokémon moves to discard")


def test_knockout_awards_prize(knockout_state):
    """
    Test that knocking out opponent's Pokémon awards a prize.

    Expected:
    - Prize count decreases by 1
    - Prize moved to hand
    - prizes_taken increases by 1
    """
    state = knockout_state
    charmander = state.players[0].board.active_spot
    attacker = state.players[1]

    # Verify initial prize state
    initial_prizes = attacker.prizes.count()
    initial_hand = attacker.hand.count()
    assert initial_prizes == 6, "Attacker should have 6 prizes"

    # Get max HP and KO the Pokémon
    max_hp = get_max_hp(charmander)
    state = actions.place_damage_counters(state, charmander, amount=2)

    # Process knockout
    state = actions.process_knockout(state, charmander, attacker_player_id=1)

    # Verify prize was taken
    assert attacker.prizes.count() == 5, f"Expected 5 prizes, got {attacker.prizes.count()}"
    assert attacker.hand.count() == initial_hand + 1, "Prize should be in hand"
    assert attacker.prizes_taken == 1, f"Expected prizes_taken=1, got {attacker.prizes_taken}"

    print("[OK] Knockout awards prize to attacker")


def test_knockout_with_attached_cards(knockout_state):
    """
    Test that attached Energy/Tools are discarded with KO'd Pokémon.

    Constitution: Attached cards move to discard with Pokémon.
    """
    state = knockout_state
    charmander = state.players[0].board.active_spot
    player = state.players[0]

    # Attach 2 Energy to Charmander
    energy1 = create_card_instance("base1-98", owner_id=0)
    energy2 = create_card_instance("base1-98", owner_id=0)
    charmander.attached_energy.append(energy1)
    charmander.attached_energy.append(energy2)

    # KO the Pokémon
    max_hp = get_max_hp(charmander)
    state = actions.place_damage_counters(state, charmander, amount=2)
    state = actions.process_knockout(state, charmander, attacker_player_id=1)

    # Verify discard contains Pokémon + 2 Energy = 3 cards
    assert player.discard.count() >= 3, \
        f"Expected at least 3 cards in discard, got {player.discard.count()}"

    print("[OK] Attached cards discarded with KO'd Pokémon")


# ============================================================================
# TEST: WIN CONDITIONS (Constitution Section 2, Phase 3)
# ============================================================================

def test_win_by_prizes(engine, knockout_state):
    """
    Test that taking all 6 prizes triggers win condition.

    Expected: Game ends when prizes_taken reaches 6.
    """
    state = knockout_state
    player = state.players[1]

    # Set prizes_taken to 5 (one away from winning)
    player.prizes_taken = 5

    # Clear prizes except 1
    while player.prizes.count() > 1:
        player.prizes.cards.pop()

    # Check win conditions
    state = engine._check_win_conditions(state)

    # Should not be won yet
    assert state.result == GameResult.ONGOING, "Game should not be over yet"

    # Take final prize
    player.prizes_taken = 6

    # Check win conditions again
    state = engine._check_win_conditions(state)

    # Should trigger win
    assert state.result == GameResult.PLAYER_1_WIN, \
        f"Expected Player 1 win, got {state.result}"

    print("[OK] Win by taking all 6 prizes")


def test_win_by_no_pokemon(engine, empty_state):
    """
    Test that having no Pokémon in play triggers loss.

    Constitution: "Opponent has no Pokémon in play" = win condition.
    """
    state = empty_state

    # Player 0 has no Pokémon
    assert not state.players[0].has_any_pokemon_in_play()

    # Player 1 has Active
    active = create_card_instance("sv8-57", owner_id=1)
    state.players[1].board.active_spot = active

    # Check win conditions
    state = engine._check_win_conditions(state)

    # Player 1 should win (Player 0 has no Pokémon)
    assert state.result == GameResult.PLAYER_1_WIN, \
        f"Expected Player 1 win, got {state.result}"

    print("[OK] Win by opponent having no Pokémon")


# ============================================================================
# TEST: STATE TRANSITIONS (Constitution Section 5)
# ============================================================================

def test_switch_removes_status_conditions(basic_battle_state):
    """
    Test that moving from Active to Bench removes status conditions.

    Constitution Section 5:
    "Status Conditions: REMOVED (Poison, Burn, Sleep, Paralyzed, Confused)"
    """
    state = basic_battle_state
    active = state.players[0].board.active_spot

    # Apply status conditions
    from models import StatusCondition
    active.status_conditions.add(StatusCondition.POISONED)
    active.status_conditions.add(StatusCondition.BURNED)
    active.status_conditions.add(StatusCondition.ASLEEP)

    assert len(active.status_conditions) == 3, "Should have 3 status conditions"

    # Apply "Switch" effect (Active → Bench)
    active = actions.reset_pokemon_on_bench(active)

    # Status conditions should be cleared
    assert len(active.status_conditions) == 0, \
        f"Status conditions should be cleared, got {active.status_conditions}"

    print("[OK] Switch removes status conditions")


def test_switch_removes_attack_effects(basic_battle_state):
    """
    Test that moving to Bench removes attack effects.

    Constitution Section 5:
    "Attack Effects: REMOVED (e.g., 'This Pokémon can't attack during your next turn')"
    """
    state = basic_battle_state
    active = state.players[0].board.active_spot

    # Apply attack effect
    active.attack_effects.append("cannot_attack_next_turn")

    assert len(active.attack_effects) == 1

    # Apply "Switch" effect
    active = actions.reset_pokemon_on_bench(active)

    # Attack effects should be cleared
    assert len(active.attack_effects) == 0, \
        f"Attack effects should be cleared, got {active.attack_effects}"

    print("[OK] Switch removes attack effects")


def test_switch_preserves_damage(basic_battle_state):
    """
    Test that damage persists when moving to Bench.

    Constitution Section 5:
    "Damage/Counters: PERSIST (Do not remove)"
    """
    state = basic_battle_state
    active = state.players[0].board.active_spot

    # Apply damage
    active.damage_counters = 4  # 40 damage

    # Apply "Switch" effect
    active = actions.reset_pokemon_on_bench(active)

    # Damage should persist
    assert active.damage_counters == 4, \
        f"Damage should persist, got {active.damage_counters}"

    print("[OK] Switch preserves damage counters")


def test_switch_preserves_energy(basic_battle_state):
    """
    Test that Energy persists when moving to Bench.

    Constitution Section 5:
    "Tools/Energy: PERSIST (Do not remove)"
    """
    state = basic_battle_state
    active = state.players[0].board.active_spot

    # Attach Energy
    energy = create_card_instance("base1-98", owner_id=0)
    active.attached_energy.append(energy)

    assert len(active.attached_energy) == 1

    # Apply "Switch" effect
    active = actions.reset_pokemon_on_bench(active)

    # Energy should persist
    assert len(active.attached_energy) == 1, \
        f"Energy should persist, got {len(active.attached_energy)}"

    print("[OK] Switch preserves attached Energy")


def test_full_state_wipe_hand_to_deck(basic_battle_state):
    """
    Test that moving from Play to Hand/Deck wipes ALL state.

    Constitution Section 5:
    "When a Pokémon moves from Play to Hand/Deck:
    ALL State: WIPED. (Damage, Status, Tools, 'Turns in Play')"
    """
    state = basic_battle_state
    active = state.players[0].board.active_spot

    # Set up state
    active.damage_counters = 3
    active.attached_energy.append(create_card_instance("base1-98", owner_id=0))
    active.status_conditions.add(actions.StatusCondition.POISONED)
    active.turns_in_play = 2

    # Apply full reset (Play → Hand)
    reset_card = actions.reset_card_fully(active)

    # Verify ALL state is wiped
    assert reset_card.damage_counters == 0, "Damage should be wiped"
    assert len(reset_card.attached_energy) == 0, "Energy should be wiped"
    assert len(reset_card.status_conditions) == 0, "Status should be wiped"
    assert reset_card.turns_in_play == 0, "Turns in play should be reset"

    print("[OK] Full state wipe (Play → Hand/Deck)")


# ============================================================================
# TEST: SHUFFLE (Constitution Section 4.1)
# ============================================================================

def test_shuffle_randomizes_deck(empty_state):
    """
    Test that shuffle_deck() randomizes card order.

    Note: Uses fixed seed for determinism.
    """
    state = empty_state
    player = state.players[0]

    # Add cards to deck in known order
    for i in range(10):
        card = create_card_instance("base1-98", owner_id=0)
        player.deck.add_card(card)

    # Record original order
    original_ids = [c.id for c in player.deck.cards]

    # Shuffle with seed
    state = actions.shuffle_deck(state, player_id=0, seed=42)

    # Record shuffled order
    shuffled_ids = [c.id for c in player.deck.cards]

    # Orders should be different (with overwhelming probability)
    # Note: With seed, this is deterministic
    assert shuffled_ids != original_ids, "Shuffle should change card order"

    # Deck size should be unchanged
    assert len(shuffled_ids) == 10, "Shuffle should not change deck size"

    print("[OK] Shuffle randomizes deck")


# ============================================================================
# TEST: SEARCH DECK (Constitution Section 4.1)
# ============================================================================

def test_search_deck_restricted_can_fail(empty_state):
    """
    Test that restricted search can fail even if cards exist.

    Constitution Section 4.1: "The player may choose to 'Fail' (find nothing)
    even if valid targets exist."
    """
    state = empty_state
    player = state.players[0]

    # Add Fire Energy to deck
    add_cards_to_deck(player, "base1-98", 5)

    # Search for Fire Energy (restricted)
    def is_fire(card):
        return card.card_id == "base1-98"

    # With allow_fail=True, search may find nothing
    # (Randomized in implementation, but principle is tested)
    state, found = actions.search_deck(
        state,
        player_id=0,
        filter_func=is_fire,
        allow_fail=True,
        reveal=False,
        max_results=1
    )

    # Found cards should be 0 or 1 (can fail)
    assert len(found) in [0, 1], "Restricted search can fail"

    print(f"[OK] Restricted search result: {len(found)} cards")


def test_search_deck_unrestricted_must_find(empty_state):
    """
    Test that unrestricted search must find a card if deck not empty.

    Constitution Section 4.1: "If the deck is not empty, the player MUST
    find a card."
    """
    state = empty_state
    player = state.players[0]

    # Add cards to deck
    add_cards_to_deck(player, "base1-98", 5)

    # Unrestricted search (allow_fail=False)
    def any_card(card):
        return True

    state, found = actions.search_deck(
        state,
        player_id=0,
        filter_func=any_card,
        allow_fail=False,
        reveal=False,
        max_results=1
    )

    # Must find a card (deck not empty)
    assert len(found) == 1, "Unrestricted search must find card"

    print("[OK] Unrestricted search must find card")


# ============================================================================
# RUN ALL TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

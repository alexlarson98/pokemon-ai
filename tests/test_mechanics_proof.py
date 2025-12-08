"""
Pokémon TCG Engine - Mechanics Proof Tests
Tests complex card interactions to verify the engine is ready for AI automation.

These tests verify that the engine's atomic actions can compose into complex
card effects required for the competitive Charizard/Terapagos deck.

Test Coverage:
1. Iono - Hand manipulation (shuffle hand to bottom, draw based on prizes)
2. Rare Candy - Evolution stage skipping (Basic -> Stage 2)
3. Area Zero Underdepths - Rule bending (Bench size increase + collapse)

If these tests pass, the engine is proven ready for automated card logic.
If they fail, we must implement missing primitives in actions.py first.
"""

import pytest
import sys
sys.path.insert(0, 'src')

from models import GameState, CardInstance, GamePhase, PlayerState
from cards.factory import create_card_instance, get_card_definition, create_multiple
import actions


# ============================================================================
# HELPER FUNCTIONS FROM CONFTEST
# ============================================================================

def add_cards_to_hand(player: PlayerState, card_id: str, count: int):
    """Add cards to a player's hand."""
    cards = create_multiple(card_id, count, player.player_id)
    for card in cards:
        player.hand.add_card(card)


def add_cards_to_deck(player: PlayerState, card_id: str, count: int):
    """Add cards to a player's deck."""
    cards = create_multiple(card_id, count, player.player_id)
    for card in cards:
        player.deck.add_card(card)


# ============================================================================
# NOTE: All helper functions now moved to actions.py as official primitives:
# - actions.move_hand_to_deck()
# - actions.evolve_pokemon()
# - actions.check_bench_collapse()
# - actions.enforce_bench_limit()
# ============================================================================


# ============================================================================
# TEST 1: IONO MECHANISM (Hand Manipulation)
# ============================================================================

def test_iono_hand_shuffle_and_draw(empty_state):
    """
    Test the Iono supporter card mechanism.

    Iono Effect:
    "Each player shuffles their hand and puts it on the bottom of their deck.
    If either player put any cards on the bottom of their deck in this way,
    each player draws a card for each of their remaining Prize cards."

    Setup:
    - Player 0: 5 cards in hand, 6 prizes remaining
    - Player 1: 3 cards in hand, 4 prizes remaining

    Action:
    1. Shuffle both players' hands to bottom of deck
    2. Each player draws cards equal to their remaining prizes

    Expected:
    - Player 0 has 6 cards in hand (drew 6)
    - Player 1 has 4 cards in hand (drew 4)
    - Old hands are shuffled into decks
    """
    state = empty_state

    # Setup: Give players cards in hand
    # Player 0: 5 cards in hand, 6 prizes
    add_cards_to_hand(state.players[0], "base1-98", 5)  # Fire Energy
    add_cards_to_deck(state.players[0], "sv3-26", 20)  # Charmander in deck

    # Set up 6 prizes for Player 0
    for _ in range(6):
        prize = create_card_instance("base1-98", owner_id=0)
        state.players[0].prizes.add_card(prize)
    state.players[0].prizes_taken = 0  # 6 remaining

    # Player 1: 3 cards in hand, 4 prizes
    add_cards_to_hand(state.players[1], "base1-98", 3)  # Fire Energy
    add_cards_to_deck(state.players[1], "sv3-26", 20)  # Charmander in deck

    # Set up 6 prizes total, 2 taken (4 remaining)
    for _ in range(4):
        prize = create_card_instance("base1-98", owner_id=1)
        state.players[1].prizes.add_card(prize)
    state.players[1].prizes_taken = 2  # 4 remaining

    # Verify initial state
    assert state.players[0].hand.count() == 5, "Player 0 should have 5 cards in hand"
    assert state.players[1].hand.count() == 3, "Player 1 should have 3 cards in hand"

    print("[Setup] Player 0: 5 cards in hand, 6 prizes remaining")
    print("[Setup] Player 1: 3 cards in hand, 4 prizes remaining")

    # === EXECUTE IONO EFFECT ===

    # Step 1: Move Player 0's hand to bottom of deck and shuffle
    state = actions.move_hand_to_deck(state, player_id=0, bottom=True, shuffle=True)
    assert state.players[0].hand.count() == 0, "Player 0's hand should be empty after shuffle"

    # Step 2: Move Player 1's hand to bottom of deck and shuffle
    state = actions.move_hand_to_deck(state, player_id=1, bottom=True, shuffle=True)
    assert state.players[1].hand.count() == 0, "Player 1's hand should be empty after shuffle"

    print("[Action] Moved both hands to bottom of decks and shuffled")

    # Step 3: Each player draws cards equal to remaining prizes
    prizes_remaining_p0 = 6 - state.players[0].prizes_taken
    prizes_remaining_p1 = 6 - state.players[1].prizes_taken

    state = actions.draw_card(state, player_id=0, amount=prizes_remaining_p0)
    state = actions.draw_card(state, player_id=1, amount=prizes_remaining_p1)

    print(f"[Action] Player 0 drew {prizes_remaining_p0} cards")
    print(f"[Action] Player 1 drew {prizes_remaining_p1} cards")

    # === VERIFY RESULTS ===

    assert state.players[0].hand.count() == 6, \
        f"Player 0 should have 6 cards in hand, got {state.players[0].hand.count()}"

    assert state.players[1].hand.count() == 4, \
        f"Player 1 should have 4 cards in hand, got {state.players[1].hand.count()}"

    print("[OK] Iono mechanism verified!")
    print(f"  - Player 0: {state.players[0].hand.count()} cards (expected 6)")
    print(f"  - Player 1: {state.players[1].hand.count()} cards (expected 4)")


# ============================================================================
# TEST 2: RARE CANDY MECHANISM (Stage Skipping)
# ============================================================================

def test_rare_candy_stage_skip_evolution(empty_state):
    """
    Test the Rare Candy item card mechanism.

    Rare Candy Effect:
    "Choose 1 of your Basic Pokémon in play. If you have a Stage 2 card in
    your hand that evolves from that Pokémon, put that card on the Basic Pokémon
    to evolve it, skipping Stage 1."

    Setup:
    - Player 0 has Charmander (Basic) in Active spot
    - Player 0 has Charizard ex (Stage 2) in hand
    - Turn 2 (evolution normally allowed)

    Action:
    1. Use Rare Candy to evolve Charmander -> Charizard ex (skip Charmeleon)

    Expected:
    - Charmander is replaced by Charizard ex
    - Charizard ex inherits damage counters and energy
    - Evolution chain is tracked
    """
    state = empty_state
    state.turn_count = 2  # Turn 2, evolution allowed

    # Setup: Create Charmander in Active spot
    charmander = create_card_instance("sv3-26", owner_id=0)  # Basic Charmander
    charmander.turns_in_play = 1  # Played last turn
    charmander.damage_counters = 2  # Has 20 damage

    # Attach 2 Fire Energy
    fire1 = create_card_instance("base1-98", owner_id=0)
    fire2 = create_card_instance("base1-98", owner_id=0)
    charmander.attached_energy = [fire1, fire2]

    state.players[0].board.active_spot = charmander

    # Add Charizard ex to hand
    charizard = create_card_instance("sv3-125", owner_id=0)  # Stage 2 Charizard ex
    state.players[0].hand.add_card(charizard)

    # Verify initial state
    assert state.players[0].board.active_spot.card_id == "sv3-26", "Active should be Charmander"
    assert state.players[0].hand.count() == 1, "Should have Charizard ex in hand"

    charmander_def = get_card_definition(charmander)
    charizard_def = get_card_definition(charizard)

    print(f"[Setup] Charmander (Basic) in Active spot")
    print(f"  - HP: {charmander_def.hp}")
    print(f"  - Damage: {charmander.damage_counters * 10} HP")
    print(f"  - Energy: {len(charmander.attached_energy)} Fire")
    print(f"[Setup] Charizard ex (Stage 2) in hand")

    # === EXECUTE RARE CANDY EFFECT ===

    # Use actions.evolve_pokemon with skip_stage=True (Rare Candy)
    state = actions.evolve_pokemon(
        state,
        player_id=0,
        target_pokemon_id=charmander.id,
        evolution_card_id=charizard.id,
        skip_stage=True  # This is the Rare Candy magic!
    )

    print("[Action] Used Rare Candy to evolve Charmander -> Charizard ex")

    # === VERIFY RESULTS ===

    evolved = state.players[0].board.active_spot

    # Verify it's now Charizard ex
    assert evolved.card_id == "sv3-125", \
        f"Active should be Charizard ex (sv3-125), got {evolved.card_id}"

    # Verify damage counters transferred
    assert evolved.damage_counters == 2, \
        f"Charizard ex should have 2 damage counters (inherited), got {evolved.damage_counters}"

    # Verify energy transferred
    assert len(evolved.attached_energy) == 2, \
        f"Charizard ex should have 2 energy (inherited), got {len(evolved.attached_energy)}"

    # Verify evolution chain tracked
    assert "sv3-26" in evolved.evolution_chain, \
        "Evolution chain should include Charmander"

    print("[OK] Rare Candy mechanism verified!")
    print(f"  - Evolved: {evolved.card_id} (Charizard ex)")
    print(f"  - Damage counters: {evolved.damage_counters} (inherited from Charmander)")
    print(f"  - Energy: {len(evolved.attached_energy)} (inherited)")
    print(f"  - Evolution chain: {evolved.evolution_chain}")


# ============================================================================
# TEST 3: AREA ZERO UNDERDEPTHS MECHANISM (Rule Bending)
# ============================================================================

def test_area_zero_bench_expansion_and_collapse(empty_state):
    """
    Test the Area Zero Underdepths stadium card mechanism.

    Area Zero Underdepths Effect:
    "Each player may have up to 8 Pokémon on their Bench (instead of 5)."

    Critical Rule:
    When the Stadium is removed, the bench must collapse back to 5 Pokémon.
    The player chooses which Pokémon to discard.

    Setup:
    - Player 0 has Area Zero Underdepths in play
    - Player 0 fills bench to 8 Pokémon (Tera Pokémon benefit)

    Action:
    1. Place 8 Pokémon on bench (allowed while Stadium is active)
    2. Remove Stadium
    3. Enforce bench collapse to 5 Pokémon

    Expected:
    - While Stadium active: 8 Pokémon on bench (legal)
    - After Stadium removed: Forced discard down to 5 Pokémon
    - Attached cards also move to discard
    """
    state = empty_state
    player = state.players[0]

    # Setup: Area Zero Underdepths in play
    stadium = create_card_instance("sv6-139", owner_id=0)  # Area Zero Underdepths
    state.stadium = stadium

    print("[Setup] Area Zero Underdepths in play")
    print("  - Bench limit: 8 Pokémon (instead of 5)")

    # === PHASE 1: FILL BENCH TO 8 ===

    # Add 8 Pokémon to bench
    for i in range(8):
        bench_pokemon = create_card_instance("sv3-26", owner_id=0)  # Charmander
        bench_pokemon.id = f"bench_{i}"  # Unique IDs for tracking

        # Attach an energy to each (to verify attached cards are discarded)
        energy = create_card_instance("base1-98", owner_id=0)
        bench_pokemon.attached_energy.append(energy)

        player.board.bench.append(bench_pokemon)

    # Verify bench size
    assert len(player.board.bench) == 8, \
        f"Bench should have 8 Pokémon while Stadium is active, got {len(player.board.bench)}"

    print("[Phase 1] Filled bench to 8 Pokémon")
    print(f"  - Bench size: {len(player.board.bench)}")

    # Count total cards on board (for discard verification)
    initial_bench_count = len(player.board.bench)
    initial_energy_count = sum(len(p.attached_energy) for p in player.board.bench)

    print(f"  - Total energy attached: {initial_energy_count}")

    # === PHASE 2: REMOVE STADIUM ===

    # Remove Area Zero Underdepths
    state.stadium = None

    print("[Phase 2] Removed Area Zero Underdepths")
    print("  - Bench limit reverts to 5")

    # === PHASE 3: ENFORCE BENCH COLLAPSE ===

    # This is the critical test: Engine must force discard down to 5
    state = actions.enforce_bench_limit(state, player_id=0, max_size=5)

    print("[Phase 3] Enforced bench collapse to 5 Pokémon")

    # === VERIFY RESULTS ===

    # Verify bench size is now 5
    assert len(player.board.bench) == 5, \
        f"Bench should be reduced to 5 after Stadium removed, got {len(player.board.bench)}"

    # Verify 3 Pokémon were discarded
    expected_discarded = initial_bench_count - 5

    # Count cards in discard (3 Pokémon + 3 Energy = 6 cards)
    discard_count = player.discard.count()
    expected_discard_count = expected_discarded + expected_discarded  # Pokémon + Energy

    assert discard_count == expected_discard_count, \
        f"Discard should have {expected_discard_count} cards (3 Pokémon + 3 Energy), got {discard_count}"

    print("[OK] Area Zero bench collapse verified!")
    print(f"  - Final bench size: {len(player.board.bench)} (expected 5)")
    print(f"  - Pokémon discarded: {expected_discarded}")
    print(f"  - Total cards discarded: {discard_count} (Pokémon + attached cards)")


# ============================================================================
# EDGE CASE TESTS: Rule Enforcement
# ============================================================================

def test_edge_case_iono_hand_to_deck_ordering(empty_state):
    """
    Test A: Verify move_hand_to_deck maintains bottom ordering.

    Edge Case: Ensure cards go to the BOTTOM of the deck, not shuffled in.
    Critical for Iono vs Judge distinction.

    Setup:
    - Player has 3 specific cards in hand: [A, B, C]
    - Player has 5 cards in deck: [1, 2, 3, 4, 5]

    Action:
    - move_hand_to_deck(bottom=True, shuffle=False)

    Expected:
    - Deck becomes: [1, 2, 3, 4, 5, A, B, C] (or shuffled if shuffle=True)
    - Hand is empty
    """
    state = empty_state
    player = state.players[0]

    # Setup: Add 5 cards to deck
    add_cards_to_deck(player, "sv3-26", 5)  # Deck: 5 Charmander
    initial_deck_size = len(player.deck.cards)

    # Setup: Add 3 cards to hand
    add_cards_to_hand(player, "base1-98", 3)  # Hand: 3 Fire Energy
    initial_hand_size = len(player.hand.cards)

    print(f"[Setup] Deck: {initial_deck_size} cards, Hand: {initial_hand_size} cards")

    # Execute: Move hand to bottom of deck WITHOUT shuffling
    state = actions.move_hand_to_deck(state, player_id=0, bottom=True, shuffle=False)

    # Verify: Hand is empty
    assert player.hand.count() == 0, "Hand should be empty"

    # Verify: Deck size increased by hand size
    final_deck_size = len(player.deck.cards)
    assert final_deck_size == initial_deck_size + initial_hand_size, \
        f"Deck should have {initial_deck_size + initial_hand_size} cards, got {final_deck_size}"

    # Verify: Last 3 cards in deck are Fire Energy (were from hand)
    bottom_cards = player.deck.cards[-3:]
    for card in bottom_cards:
        assert card.card_id == "base1-98", \
            f"Bottom cards should be Fire Energy, got {card.card_id}"

    print("[OK] Hand moved to bottom of deck (ordered)")
    print(f"  - Final deck size: {final_deck_size}")
    print(f"  - Hand size: {player.hand.count()}")


def test_edge_case_evolution_sickness_turn_1(empty_state):
    """
    Test B: Verify evolution fails if Pokémon was played this turn.

    Edge Case: Evolution Sickness prevents evolution on turn 1 or turn played.

    Case 1: Turn 1 - Cannot evolve at all
    Case 2: Turn 2, Pokémon played this turn - Cannot evolve
    Case 3: Turn 2, Pokémon played last turn - CAN evolve
    """
    state = empty_state

    # === CASE 1: Turn 1 - Cannot evolve ===
    state.turn_count = 1
    state.active_player_index = 0

    charmander = create_card_instance("sv3-26", owner_id=0)
    charmander.turns_in_play = 1  # Even if played last turn
    state.players[0].board.active_spot = charmander

    charmeleon = create_card_instance("sv3-27", owner_id=0)
    state.players[0].hand.add_card(charmeleon)

    print("[Case 1] Turn 1 - Attempting evolution...")
    try:
        state = actions.evolve_pokemon(
            state,
            player_id=0,
            target_pokemon_id=charmander.id,
            evolution_card_id=charmeleon.id,
            skip_stage=False
        )
        assert False, "Should have raised ValueError for turn 1 evolution"
    except ValueError as e:
        assert "first turn" in str(e).lower()
        print(f"  [OK] Correctly blocked: {e}")

    # === CASE 2: Turn 2, but Pokémon played this turn ===
    state.turn_count = 2

    charmander2 = create_card_instance("sv3-26", owner_id=0)
    charmander2.turns_in_play = 0  # Just played this turn!
    state.players[0].board.active_spot = charmander2

    charmeleon2 = create_card_instance("sv3-27", owner_id=0)
    state.players[0].hand.add_card(charmeleon2)

    print("[Case 2] Turn 2, Pokémon played this turn - Attempting evolution...")
    try:
        state = actions.evolve_pokemon(
            state,
            player_id=0,
            target_pokemon_id=charmander2.id,
            evolution_card_id=charmeleon2.id,
            skip_stage=False
        )
        assert False, "Should have raised ValueError for evolution sickness"
    except ValueError as e:
        assert "played this turn" in str(e).lower()
        print(f"  [OK] Correctly blocked: {e}")

    # === CASE 3: Turn 2, Pokémon played LAST turn ===
    charmander3 = create_card_instance("sv3-26", owner_id=0)
    charmander3.turns_in_play = 1  # Played last turn
    state.players[0].board.active_spot = charmander3

    charmeleon3 = create_card_instance("sv3-27", owner_id=0)
    state.players[0].hand.add_card(charmeleon3)

    print("[Case 3] Turn 2, Pokémon played last turn - Attempting evolution...")
    state = actions.evolve_pokemon(
        state,
        player_id=0,
        target_pokemon_id=charmander3.id,
        evolution_card_id=charmeleon3.id,
        skip_stage=False
    )
    assert state.players[0].board.active_spot.card_id == "sv3-27"
    print("  [OK] Evolution succeeded!")

    print("[OK] Evolution sickness rules verified!")


def test_edge_case_bench_collapse_overflow_detection(empty_state):
    """
    Test C: Verify check_bench_collapse raises error when bench > max.

    Edge Case: Engine must FLAG invalid state (bench overflow) and force player choice.

    Setup:
    - Player has 5 Pokémon on bench (normal limit)
    - Stadium increases limit to 8
    - Player adds 3 more (now 8 total)
    - Stadium is removed

    Action:
    - check_bench_collapse(max_bench_size=5)

    Expected:
    - Raises BenchOverflowError
    - Error contains: current_size=8, max_size=5
    - Player must discard 3 Pokémon
    """
    state = empty_state
    player = state.players[0]

    # Setup: Add 5 Pokémon to bench (normal limit)
    for i in range(5):
        bench = create_card_instance("sv3-26", owner_id=0)
        bench.id = f"bench_{i}"
        player.board.bench.append(bench)

    print("[Setup] Bench: 5 Pokémon (at normal limit)")

    # Simulate Stadium: Area Zero Underdepths (max 8)
    state.stadium = create_card_instance("sv6-139", owner_id=0)
    print("[Setup] Stadium active: Bench limit = 8")

    # Add 3 more Pokémon (now 8 total)
    for i in range(5, 8):
        bench = create_card_instance("sv3-26", owner_id=0)
        bench.id = f"bench_{i}"
        player.board.bench.append(bench)

    assert len(player.board.bench) == 8
    print("[Setup] Added 3 more Pokémon (bench now 8)")

    # Remove Stadium
    state.stadium = None
    print("[Action] Removed Stadium - bench limit reverts to 5")

    # Attempt to check bench collapse - should raise error
    print("[Action] Checking bench collapse...")
    try:
        state = actions.check_bench_collapse(state, player_id=0, max_bench_size=5)
        assert False, "Should have raised BenchOverflowError"
    except actions.BenchOverflowError as e:
        # Verify error details
        assert e.current_size == 8, f"Expected current_size=8, got {e.current_size}"
        assert e.max_size == 5, f"Expected max_size=5, got {e.max_size}"
        assert e.player_id == 0, f"Expected player_id=0, got {e.player_id}"

        print(f"  [OK] Correctly raised BenchOverflowError:")
        print(f"    - Current: {e.current_size} Pokémon")
        print(f"    - Max: {e.max_size} Pokémon")
        print(f"    - Must discard: {e.current_size - e.max_size} Pokémon")

    # Now enforce the limit (simulate player choice)
    print("[Action] Enforcing bench limit (auto-discard 3)...")
    state = actions.enforce_bench_limit(state, player_id=0, max_size=5)

    # Verify bench is now legal
    assert len(player.board.bench) == 5
    state = actions.check_bench_collapse(state, player_id=0, max_bench_size=5)  # Should not raise
    print("[OK] Bench collapse detection and enforcement verified!")


# ============================================================================
# INTEGRATION TEST: All Three Mechanisms
# ============================================================================

def test_combined_mechanics_proof(empty_state):
    """
    Integration test combining all three mechanisms.

    This proves the engine can handle a realistic game scenario:
    1. Player evolves Charmander -> Charizard ex with Rare Candy
    2. Player plays Iono to disrupt opponent's hand
    3. Player uses Area Zero to expand bench, then collapses it

    If this test passes, the engine is ready for AI automation.
    """
    state = empty_state
    state.turn_count = 2

    # Setup Player 0
    charmander = create_card_instance("sv3-26", owner_id=0)
    charmander.turns_in_play = 1
    state.players[0].board.active_spot = charmander

    charizard = create_card_instance("sv3-125", owner_id=0)
    state.players[0].hand.add_card(charizard)

    # Setup Player 1 with cards in hand
    add_cards_to_hand(state.players[1], "base1-98", 7)  # 7 cards
    add_cards_to_deck(state.players[1], "sv3-26", 10)

    # Set up prizes
    for i in range(6):
        state.players[0].prizes.add_card(create_card_instance("base1-98", owner_id=0))
        state.players[1].prizes.add_card(create_card_instance("base1-98", owner_id=1))

    print("=== COMBINED MECHANICS TEST ===")
    print()

    # Mechanic 1: Rare Candy evolution
    print("1. Using Rare Candy...")
    state = actions.evolve_pokemon(
        state,
        player_id=0,
        target_pokemon_id=charmander.id,
        evolution_card_id=charizard.id,
        skip_stage=True
    )
    assert state.players[0].board.active_spot.card_id == "sv3-125"
    print("   OK Evolved Charmander -> Charizard ex")

    # Mechanic 2: Iono hand disruption
    print("2. Playing Iono...")
    state = actions.move_hand_to_deck(state, player_id=1, bottom=True, shuffle=True)
    state = actions.draw_card(state, player_id=1, amount=6)
    assert state.players[1].hand.count() == 6
    print("   OK Opponent drew 6 cards (6 prizes remaining)")

    # Mechanic 3: Area Zero bench manipulation
    print("3. Testing Area Zero...")
    state.stadium = create_card_instance("sv6-139", owner_id=0)
    for i in range(8):
        bench = create_card_instance("sv3-26", owner_id=0)
        state.players[0].board.bench.append(bench)
    assert len(state.players[0].board.bench) == 8
    print("   OK Bench expanded to 8 Pokémon")

    state.stadium = None
    state = actions.enforce_bench_limit(state, player_id=0, max_size=5)
    assert len(state.players[0].board.bench) == 5
    print("   OK Bench collapsed to 5 Pokémon")

    print()
    print("[OK] ALL MECHANICS VERIFIED!")
    print("The engine is ready for AI-driven card automation.")


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

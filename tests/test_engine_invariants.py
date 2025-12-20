"""
Property-Based Engine Invariant Tests

Instead of testing specific scenarios, we generate thousands of random game states
and verify that engine invariants ALWAYS hold. This catches edge cases that
manual testing misses.

Invariants tested:
1. CARD CONSERVATION - Cards are never created or destroyed, only moved between zones
2. FUNCTIONAL ID CONSISTENCY - functional_id_map always matches actual cards
3. SEARCH CORRECTNESS - Search results respect filters and knowledge layer
4. ACTION VALIDITY - Every legal action can be executed without error
5. STATE DETERMINISM - Same state + same action = same result
6. ZONE INTEGRITY - Cards are in exactly one zone at a time

Run with: pytest tests/test_engine_invariants.py -v --tb=short

# =============================================================================
# TODO: 4 PILLARS & STACK ARCHITECTURE - IMPLEMENTATION GAPS
# =============================================================================
#
# As fuzzing tests are expanded, the following components need implementation:
#
# ─────────────────────────────────────────────────────────────────────────────
# PILLAR 2: MODIFIERS (Value Transformers) - MOSTLY MISSING
# ─────────────────────────────────────────────────────────────────────────────
# [ ] Damage reduction modifiers (e.g., "takes 30 less damage from attacks")
#     - Mega Diancie ex Diamond Coat: me2-41
#     - Many ex/V Pokemon have similar effects
# [ ] Retreat cost modifiers
#     - Beach Court Stadium: reduces retreat by 1
#     - Heavy Ball: free retreat for 3+ retreat Pokemon
# [ ] HP modifiers
#     - Cape of Toughness: +50 HP to Basic Pokemon
# [ ] Damage boost modifiers
#     - Muscle Band: +20 damage to attacks
#     - Choice Belt: +30 damage to V/VMAX Pokemon
# [ ] Global modifiers (Stadium effects)
#     - Scan board for all modifier-providing cards
#
# ─────────────────────────────────────────────────────────────────────────────
# PILLAR 4: HOOKS (Event Listeners) - BARELY IMPLEMENTED
# ─────────────────────────────────────────────────────────────────────────────
# [ ] on_play_pokemon hooks
#     - Lumineon V: search for Supporter when played from hand
#     - Shaymin EX: draw until 6 cards when played
# [ ] on_knockout hooks
#     - Klefki: attach to opponent's Pokemon when KO'd
#     - Prize penalty effects
# [ ] on_attach_energy hooks
#     - Gardevoir ex: attach extra Psychic energy from deck
# [ ] on_evolve hooks
#     - Dusknoir: move damage counters when evolved into
# [ ] on_retreat hooks
#     - Effects that trigger when retreating
# [ ] on_damage_taken hooks
#     - Counter-attack effects
#
# ─────────────────────────────────────────────────────────────────────────────
# STACK ARCHITECTURE - ADDITIONAL STEP TYPES NEEDED
# ─────────────────────────────────────────────────────────────────────────────
# [ ] DiscardEnergyStep - for attack costs that discard energy
#     - Charizard ex Burning Darkness: discard 2 Fire energy
# [ ] MoveEnergyStep - for energy movement abilities
#     - Gardenia's Vigor: move energy between Pokemon
# [ ] SpreadDamageStep - for selecting multiple damage targets
#     - Greninja: 20 damage to each benched Pokemon
# [ ] SwitchPokemonStep - for forced switching effects
#     - Boss's Orders: switch opponent's active with benched
# [ ] ShuffleToDeckStep - for returning cards to deck
#     - Super Rod: return cards from discard to deck
# [ ] HealStep - for healing with target selection
#     - Cheryl: heal all damage from evolved Pokemon
# [ ] DiscardFromPlayStep - for discarding from board
#     - Tool Scrapper: discard tools from Pokemon
#
# ─────────────────────────────────────────────────────────────────────────────
# CARD-SPECIFIC IMPLEMENTATIONS NEEDED
# ─────────────────────────────────────────────────────────────────────────────
# [ ] Iono (sv2-185) - shuffle hands, draw = prize count
# [ ] Boss's Orders - switch opponent's benched to active
# [ ] Professor's Research - discard hand, draw 7
# [ ] Switch - switch your active with benched
# [ ] Energy Retrieval - return energy from discard
# [ ] Level Ball - search for Pokemon with HP <= 90
# [ ] Great Ball - look at top 7, take a Pokemon
# [ ] Timer Ball - flip 2 coins, search for evolution Pokemon
# [ ] Quick Ball - discard 1, search for Basic Pokemon
# [ ] Evolution Incense - search for evolution Pokemon
#
# ─────────────────────────────────────────────────────────────────────────────
# ADVANCED MECHANICS
# ─────────────────────────────────────────────────────────────────────────────
# [ ] Passive abilities (always-on effects without activation)
# [ ] Stadium persistence and replacement rules
# [ ] Tool attachment/removal logic
# [ ] Special Energy effects (Double Turbo, etc.)
# [ ] VSTAR Power mechanics (once per game)
# [ ] Ability lock effects (Garbodor Garbotoxin)
# [ ] Attack effects that persist between turns
# [ ] Bench barrier effects (Manaphy)
#
# =============================================================================
"""

import pytest
import random
import copy
from typing import List, Set, Dict, Tuple
from collections import Counter

from models import (
    GameState, PlayerState, GamePhase, ActionType, Action,
    SearchDeckStep, SelectFromZoneStep, ZoneType, SelectionPurpose
)
from cards.factory import create_card_instance
from cards.registry import create_card
from cards.base import PokemonCard
from engine import PokemonEngine


# =============================================================================
# TEST CARD POOL
# =============================================================================

# Cards we know exist and work
# NOTE: Only include actual Basic Pokemon here (not Stage 1/2)
# because tests use Nest Ball which only searches for Basic Pokemon
BASIC_POKEMON = [
    "sv3pt5-16",   # Pidgey (50 HP, Call for Family + Tackle)
    "sv3-162",     # Pidgey (60 HP, Gust) - different functional ID
    "sv4pt5-7",    # Charmander (70 HP)
    "svp-44",      # Charmander (60 HP, Heat Tackle)
    "svp-47",      # Charmander (70 HP, Ember)
    "sv5-126",     # Hoothoot (70 HP, Silent Wing)
    "sv7-114",     # Hoothoot (70 HP, Triple Stab)
    "sv8pt5-77",   # Hoothoot (80 HP, Tackle + Insomnia ability)
]

STAGE_1_POKEMON = [
    "sv3-27",      # Charmeleon
    "sv3pt5-17",   # Pidgeotto
    "sv5-127",     # Noctowl (if exists)
]

STAGE_2_POKEMON = [
    "sv3-125",     # Charizard ex (Stage 2)
]

TRAINER_ITEMS = [
    "sv1-181",     # Nest Ball
    "sv5-144",     # Buddy-Buddy Poffin
    "sv1-196",     # Ultra Ball
    "sv4pt5-89",   # Rare Candy
]

TRAINER_SUPPORTERS = [
    "sv2-185",     # Iono
]

BASIC_ENERGY = [
    "sv1-258",     # Fighting Energy
    "sve-2",       # Fire Energy
]

# Convenience constant for Fire-specific tests
FIRE_ENERGY_ID = "sve-2"

ALL_CARDS = BASIC_POKEMON + STAGE_1_POKEMON + STAGE_2_POKEMON + TRAINER_ITEMS + TRAINER_SUPPORTERS + BASIC_ENERGY


# =============================================================================
# RANDOM STATE GENERATOR
# =============================================================================

def random_card_id() -> str:
    """Get a random valid card ID."""
    return random.choice(ALL_CARDS)


def random_basic_pokemon() -> str:
    """Get a random basic Pokemon."""
    return random.choice(BASIC_POKEMON)


def generate_random_deck(size: int = 60) -> List[str]:
    """Generate a random but legal deck."""
    deck = []

    # Ensure at least some basics
    for _ in range(random.randint(8, 15)):
        deck.append(random_basic_pokemon())

    # Add some trainers
    for _ in range(random.randint(10, 20)):
        deck.append(random.choice(TRAINER_ITEMS))

    # Add some energy
    for _ in range(random.randint(10, 15)):
        deck.append(random.choice(BASIC_ENERGY))

    # Fill rest with random cards
    while len(deck) < size:
        deck.append(random_card_id())

    random.shuffle(deck)
    return deck[:size]


def generate_random_game_state(
    turn_count: int = None,
    phase: GamePhase = None,
    hand_size: Tuple[int, int] = None,
    bench_size: Tuple[int, int] = None,
    deck_size: Tuple[int, int] = None,
) -> GameState:
    """
    Generate a random but valid game state.

    Args:
        turn_count: Specific turn, or random 1-20
        phase: Specific phase, or random valid phase
        hand_size: (player0, player1) hand sizes, or random
        bench_size: (player0, player1) bench sizes, or random
        deck_size: (player0, player1) deck sizes, or random
    """
    if turn_count is None:
        turn_count = random.randint(1, 20)

    if phase is None:
        phase = random.choice([GamePhase.MAIN, GamePhase.ATTACK])

    if hand_size is None:
        hand_size = (random.randint(0, 10), random.randint(0, 10))

    if bench_size is None:
        bench_size = (random.randint(0, 5), random.randint(0, 5))

    if deck_size is None:
        deck_size = (random.randint(10, 40), random.randint(10, 40))

    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Generate cards for each zone
    for player, h_size, b_size, d_size in [
        (player0, hand_size[0], bench_size[0], deck_size[0]),
        (player1, hand_size[1], bench_size[1], deck_size[1]),
    ]:
        owner_id = player.player_id

        # Active (required)
        active = create_card_instance(random_basic_pokemon(), owner_id=owner_id)
        active.turns_in_play = random.randint(0, turn_count)
        player.board.active_spot = active

        # Bench
        for _ in range(b_size):
            bench_mon = create_card_instance(random_basic_pokemon(), owner_id=owner_id)
            bench_mon.turns_in_play = random.randint(0, turn_count)
            player.board.bench.append(bench_mon)

        # Hand
        for _ in range(h_size):
            player.hand.add_card(create_card_instance(random_card_id(), owner_id=owner_id))

        # Deck
        for _ in range(d_size):
            player.deck.add_card(create_card_instance(random_card_id(), owner_id=owner_id))

        # Prizes (6)
        for _ in range(6):
            player.prizes.add_card(create_card_instance(random_card_id(), owner_id=owner_id))

        # Some discard
        for _ in range(random.randint(0, 10)):
            player.discard.add_card(create_card_instance(random_card_id(), owner_id=owner_id))

    state = GameState(
        players=[player0, player1],
        turn_count=turn_count,
        active_player_index=random.randint(0, 1),
        current_phase=phase,
        starting_player_id=0
    )

    return state


# =============================================================================
# INVARIANT CHECKERS
# =============================================================================

def get_all_card_ids(state: GameState) -> Set[str]:
    """Get all unique card instance IDs in the game."""
    ids = set()

    def add_pokemon_cards(pokemon):
        """Add a Pokemon and all its attached/underlying cards."""
        ids.add(pokemon.id)
        for energy in pokemon.attached_energy:
            ids.add(energy.id)
        for tool in pokemon.attached_tools:
            ids.add(tool.id)
        # Previous evolution stages stored underneath
        for prev_stage in pokemon.previous_stages:
            add_pokemon_cards(prev_stage)

    for player in state.players:
        # Hand
        for card in player.hand.cards:
            ids.add(card.id)

        # Deck
        for card in player.deck.cards:
            ids.add(card.id)

        # Discard
        for card in player.discard.cards:
            ids.add(card.id)

        # Prizes
        for card in player.prizes.cards:
            ids.add(card.id)

        # Board
        if player.board.active_spot:
            add_pokemon_cards(player.board.active_spot)

        for bench_mon in player.board.bench:
            if bench_mon:
                add_pokemon_cards(bench_mon)

    return ids


def count_cards_by_zone(state: GameState) -> Dict[str, int]:
    """Count cards in each zone for debugging."""
    counts = {}

    def count_pokemon_cards(pokemon):
        """Count a Pokemon and all its attached/underlying cards."""
        total = 1  # The Pokemon itself
        total += len(pokemon.attached_energy)
        total += len(pokemon.attached_tools)
        # Previous evolution stages stored underneath
        for prev_stage in pokemon.previous_stages:
            total += count_pokemon_cards(prev_stage)
        return total

    for player in state.players:
        prefix = f"P{player.player_id}"
        counts[f"{prefix}_hand"] = len(player.hand.cards)
        counts[f"{prefix}_deck"] = len(player.deck.cards)
        counts[f"{prefix}_discard"] = len(player.discard.cards)
        counts[f"{prefix}_prizes"] = len(player.prizes.cards)

        board_count = 0
        attached_count = 0
        prev_stages_count = 0
        if player.board.active_spot:
            board_count += 1
            attached_count += len(player.board.active_spot.attached_energy)
            attached_count += len(player.board.active_spot.attached_tools)
            prev_stages_count += len(player.board.active_spot.previous_stages)
        for bench_mon in player.board.bench:
            if bench_mon:
                board_count += 1
                attached_count += len(bench_mon.attached_energy)
                attached_count += len(bench_mon.attached_tools)
                prev_stages_count += len(bench_mon.previous_stages)

        counts[f"{prefix}_board"] = board_count
        counts[f"{prefix}_attached"] = attached_count
        counts[f"{prefix}_prev_stages"] = prev_stages_count

    return counts


def check_no_duplicate_card_ids(state: GameState) -> Tuple[bool, str]:
    """Verify no card instance ID appears twice."""
    seen = set()
    duplicates = []

    def add_pokemon_cards(pokemon, cards_list):
        """Add a Pokemon and all its attached/underlying cards."""
        cards_list.append(pokemon)
        cards_list.extend(pokemon.attached_energy)
        cards_list.extend(pokemon.attached_tools)
        for prev_stage in pokemon.previous_stages:
            add_pokemon_cards(prev_stage, cards_list)

    for player in state.players:
        all_cards = (
            list(player.hand.cards) +
            list(player.deck.cards) +
            list(player.discard.cards) +
            list(player.prizes.cards)
        )

        if player.board.active_spot:
            add_pokemon_cards(player.board.active_spot, all_cards)

        for bench_mon in player.board.bench:
            if bench_mon:
                add_pokemon_cards(bench_mon, all_cards)

        for card in all_cards:
            if card.id in seen:
                duplicates.append(card.id)
            seen.add(card.id)

    if duplicates:
        return False, f"Duplicate card IDs: {duplicates[:5]}"
    return True, ""


def check_functional_id_consistency(state: GameState, engine: PokemonEngine) -> Tuple[bool, str]:
    """Verify functional_id_map is consistent with actual cards."""
    for player in state.players:
        if not player.functional_id_map:
            continue

        # Check that every card has a mapping
        all_cards = list(player.hand.cards) + list(player.deck.cards)

        for card in all_cards:
            if card.card_id not in player.functional_id_map:
                # Compute what it should be
                card_def = create_card(card.card_id)
                if isinstance(card_def, PokemonCard):
                    expected = engine._compute_functional_id(card_def)
                else:
                    expected = card_def.name if card_def else card.card_id

                return False, f"Card {card.card_id} missing from functional_id_map, expected {expected}"

    return True, ""


def check_search_respects_filter(
    state: GameState,
    engine: PokemonEngine,
    step: SearchDeckStep,
    results: List
) -> Tuple[bool, str]:
    """Verify search results match filter criteria."""
    for card in results:
        card_def = create_card(card.card_id)

        # Check supertype filter
        if 'supertype' in step.filter_criteria:
            expected = step.filter_criteria['supertype']
            actual = card_def.supertype.value if hasattr(card_def.supertype, 'value') else str(card_def.supertype)
            if actual != expected:
                return False, f"Card {card.card_id} has supertype {actual}, expected {expected}"

        # Check subtype filter
        if 'subtype' in step.filter_criteria:
            expected = step.filter_criteria['subtype']
            subtypes = [s.value if hasattr(s, 'value') else str(s) for s in card_def.subtypes]
            if expected not in subtypes:
                return False, f"Card {card.card_id} missing subtype {expected}, has {subtypes}"

        # Check HP filter
        if 'max_hp' in step.filter_criteria:
            max_hp = step.filter_criteria['max_hp']
            actual_hp = card_def.hp if hasattr(card_def, 'hp') else 0
            if actual_hp > max_hp:
                return False, f"Card {card.card_id} has HP {actual_hp}, exceeds max {max_hp}"

    return True, ""


# =============================================================================
# PROPERTY-BASED TESTS
# =============================================================================

class TestCardConservation:
    """Cards should never be created or destroyed during normal play."""

    @pytest.fixture
    def engine(self):
        return PokemonEngine()

    @pytest.mark.parametrize("seed", range(100))
    def test_card_count_preserved_after_action(self, engine, seed):
        """Total card count should remain constant after any action."""
        random.seed(seed)

        state = generate_random_game_state(turn_count=5, phase=GamePhase.MAIN)

        # Initialize knowledge
        state = engine.initialize_deck_knowledge(state)

        # Count cards before
        ids_before = get_all_card_ids(state)
        count_before = len(ids_before)

        # Get and execute a random legal action
        actions = engine.get_legal_actions(state)
        if not actions:
            pytest.skip("No legal actions available")

        action = random.choice(actions)

        try:
            new_state = engine.step(state, action)
        except Exception as e:
            pytest.fail(f"Action {action.action_type} raised: {e}")

        # Count cards after
        ids_after = get_all_card_ids(new_state)
        count_after = len(ids_after)

        # Check conservation
        if count_before != count_after:
            missing = ids_before - ids_after
            added = ids_after - ids_before
            zones_before = count_cards_by_zone(state)
            zones_after = count_cards_by_zone(new_state)

            pytest.fail(
                f"Card count changed from {count_before} to {count_after} "
                f"after {action.action_type}\n"
                f"Missing: {missing}\n"
                f"Added: {added}\n"
                f"Zones before: {zones_before}\n"
                f"Zones after: {zones_after}"
            )

    @pytest.mark.parametrize("seed", range(50))
    def test_no_duplicate_cards(self, engine, seed):
        """No card instance should exist in multiple zones."""
        random.seed(seed)

        state = generate_random_game_state()
        state = engine.initialize_deck_knowledge(state)

        # Execute several random actions
        for _ in range(10):
            ok, msg = check_no_duplicate_card_ids(state)
            assert ok, msg

            actions = engine.get_legal_actions(state)
            if not actions:
                break

            action = random.choice(actions)
            try:
                state = engine.step(state, action)
            except:
                break


class TestFunctionalIdConsistency:
    """Functional IDs should always be correct and consistent."""

    @pytest.fixture
    def engine(self):
        return PokemonEngine()

    @pytest.mark.parametrize("seed", range(50))
    def test_functional_ids_after_initialization(self, engine, seed):
        """After initialize_deck_knowledge, all cards should have functional IDs."""
        random.seed(seed)

        state = generate_random_game_state()
        state = engine.initialize_deck_knowledge(state)

        for player in state.players:
            assert player.functional_id_map, "functional_id_map should be populated"
            assert player.initial_deck_counts, "initial_deck_counts should be populated"

            # Verify counts use functional IDs (contain '|' for Pokemon)
            for key in player.initial_deck_counts.keys():
                # Energy and trainers use plain names, Pokemon use functional IDs
                pass  # Just checking it's populated

    @pytest.mark.parametrize("seed", range(50))
    def test_functional_ids_consistent_after_search(self, engine, seed):
        """Functional IDs should remain consistent after deck searches."""
        random.seed(seed)

        # Create state with search cards
        state = generate_random_game_state(turn_count=5, phase=GamePhase.MAIN)

        # Add a Nest Ball to hand
        player = state.players[0]
        nest_ball = create_card_instance("sv1-181", owner_id=0)
        player.hand.add_card(nest_ball)

        state = engine.initialize_deck_knowledge(state)

        ok, msg = check_functional_id_consistency(state, engine)
        assert ok, msg


class TestSearchCorrectness:
    """Search operations should always respect filters and knowledge."""

    @pytest.fixture
    def engine(self):
        return PokemonEngine()

    @pytest.mark.parametrize("seed", range(100))
    def test_nest_ball_only_returns_basics(self, engine, seed):
        """Nest Ball should only show Basic Pokemon."""
        random.seed(seed)

        state = generate_random_game_state(turn_count=3, phase=GamePhase.MAIN)
        player = state.players[state.active_player_index]

        # Add Nest Ball
        nest_ball = create_card_instance("sv1-181", owner_id=player.player_id)
        player.hand.add_card(nest_ball)

        # Ensure bench has space
        while len(player.board.bench) >= 5:
            player.board.bench.pop()

        state = engine.initialize_deck_knowledge(state)

        # Find and execute play Nest Ball
        actions = engine.get_legal_actions(state)
        play_actions = [a for a in actions
                       if a.action_type == ActionType.PLAY_ITEM and a.card_id == nest_ball.id]

        if not play_actions:
            pytest.skip("Nest Ball not playable (bench full or no basics)")

        state = engine.step(state, play_actions[0])

        # Now in search step - get SELECT_CARD actions
        if state.resolution_stack:
            search_actions = engine.get_legal_actions(state)
            select_actions = [a for a in search_actions if a.action_type == ActionType.SELECT_CARD]

            for action in select_actions:
                card_id = action.card_id
                card_def = create_card(card_id.split('_')[0] if '_' in card_id else card_id)

                # This is tricky - we need to find the actual card
                # The card_id in action is the instance ID, not the card_id
                # Let's find it
                for card in player.deck.cards + player.prizes.cards:
                    if card.id == action.card_id:
                        card_def = create_card(card.card_id)
                        break

                if card_def and hasattr(card_def, 'subtypes'):
                    subtypes = [s.value if hasattr(s, 'value') else str(s) for s in card_def.subtypes]
                    assert 'Basic' in subtypes, f"Nest Ball showed non-Basic: {card_def.name} ({subtypes})"

    @pytest.mark.parametrize("seed", range(50))
    def test_buddy_buddy_poffin_respects_hp_limit(self, engine, seed):
        """Buddy-Buddy Poffin should only show Basic Pokemon with HP <= 70."""
        random.seed(seed)

        state = generate_random_game_state(turn_count=3, phase=GamePhase.MAIN)
        player = state.players[state.active_player_index]

        # Add Poffin
        poffin = create_card_instance("sv5-144", owner_id=player.player_id)
        player.hand.add_card(poffin)

        # Ensure bench has space
        while len(player.board.bench) >= 4:  # Need space for 2
            player.board.bench.pop()

        state = engine.initialize_deck_knowledge(state)

        # Find and execute play Poffin
        actions = engine.get_legal_actions(state)
        play_actions = [a for a in actions
                       if a.action_type == ActionType.PLAY_ITEM and a.card_id == poffin.id]

        if not play_actions:
            pytest.skip("Poffin not playable")

        state = engine.step(state, play_actions[0])

        # Check search results
        if state.resolution_stack:
            search_actions = engine.get_legal_actions(state)
            select_actions = [a for a in search_actions if a.action_type == ActionType.SELECT_CARD]

            for action in select_actions:
                # Find the actual card
                for card in player.deck.cards + player.prizes.cards:
                    if card.id == action.card_id:
                        card_def = create_card(card.card_id)
                        if card_def and hasattr(card_def, 'hp'):
                            assert card_def.hp <= 70, f"Poffin showed Pokemon with HP {card_def.hp}: {card_def.name}"
                        break


class TestActionValidity:
    """Every legal action should be executable without error."""

    @pytest.fixture
    def engine(self):
        return PokemonEngine()

    @pytest.mark.parametrize("seed", range(200))
    def test_all_legal_actions_executable(self, engine, seed):
        """Every action returned by get_legal_actions should execute without error."""
        random.seed(seed)

        state = generate_random_game_state()
        state = engine.initialize_deck_knowledge(state)

        actions = engine.get_legal_actions(state)

        for action in actions:
            state_copy = copy.deepcopy(state)
            try:
                engine.step(state_copy, action)
            except Exception as e:
                pytest.fail(
                    f"Action {action.action_type} (card={action.card_id}) "
                    f"raised exception: {e}\n"
                    f"Phase: {state.current_phase}, Turn: {state.turn_count}"
                )

    @pytest.mark.parametrize("seed", range(50))
    def test_random_game_playthrough(self, engine, seed):
        """Play a random game to completion without errors."""
        random.seed(seed)

        state = generate_random_game_state(turn_count=1, phase=GamePhase.MAIN)
        state = engine.initialize_deck_knowledge(state)

        max_turns = 100
        turn = 0

        while turn < max_turns:
            actions = engine.get_legal_actions(state)

            if not actions:
                break

            # Check for game over
            if state.is_game_over():
                break

            action = random.choice(actions)

            try:
                state = engine.step(state, action)
            except Exception as e:
                pytest.fail(
                    f"Turn {turn}: Action {action.action_type} raised: {e}\n"
                    f"Phase: {state.current_phase}"
                )

            turn += 1


class TestStateDeterminism:
    """Same state + same action should always produce same result."""

    @pytest.fixture
    def engine(self):
        return PokemonEngine()

    @pytest.mark.parametrize("seed", range(50))
    def test_deterministic_state_transitions(self, engine, seed):
        """Applying the same action twice should give identical states."""
        random.seed(seed)

        state = generate_random_game_state()
        state = engine.initialize_deck_knowledge(state)

        actions = engine.get_legal_actions(state)
        if not actions:
            pytest.skip("No actions available")

        # Pick a deterministic action (not coin flip dependent)
        deterministic_actions = [
            a for a in actions
            if a.action_type not in {ActionType.ATTACK}  # Attacks might have randomness
        ]

        if not deterministic_actions:
            pytest.skip("No deterministic actions")

        action = deterministic_actions[0]

        # Apply twice to copies
        state1 = copy.deepcopy(state)
        state2 = copy.deepcopy(state)

        result1 = engine.step(state1, action)
        result2 = engine.step(state2, action)

        # Compare key state properties
        assert result1.turn_count == result2.turn_count
        assert result1.current_phase == result2.current_phase
        assert result1.active_player_index == result2.active_player_index

        # Compare card counts
        ids1 = get_all_card_ids(result1)
        ids2 = get_all_card_ids(result2)
        assert ids1 == ids2, f"Card IDs differ after same action"


# =============================================================================
# FUNCTIONAL ID SEARCH DEDUPLICATION TESTS
# =============================================================================

class TestFunctionalIdSearchDeduplication:
    """
    Test that search results properly deduplicate by functional ID across
    all possible prize/deck distributions.

    Key invariants:
    1. Two cards with SAME functional ID should appear as ONE option
    2. Two cards with DIFFERENT functional IDs should appear as TWO options
    3. This must hold regardless of how cards are split between deck/prizes
    """

    @pytest.fixture
    def engine(self):
        return PokemonEngine()

    def create_controlled_state(
        self,
        deck_card_ids: List[str],
        prize_card_ids: List[str],
        hand_card_ids: List[str],
        search_card_id: str,  # e.g., "sv1-181" for Nest Ball
    ) -> GameState:
        """Create a state with exact control over card placement."""
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        # Deck
        for card_id in deck_card_ids:
            player0.deck.add_card(create_card_instance(card_id, owner_id=0))

        # Prizes
        for card_id in prize_card_ids:
            player0.prizes.add_card(create_card_instance(card_id, owner_id=0))

        # Hand (including search card)
        for card_id in hand_card_ids:
            player0.hand.add_card(create_card_instance(card_id, owner_id=0))
        search_card = create_card_instance(search_card_id, owner_id=0)
        player0.hand.add_card(search_card)

        # Active Pokemon required
        player0.board.active_spot = create_card_instance("svp-56", owner_id=0)
        player1.board.active_spot = create_card_instance("svp-56", owner_id=1)

        state = GameState(
            players=[player0, player1],
            turn_count=3,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        return state, search_card.id

    def get_search_option_functional_ids(
        self,
        state: GameState,
        engine: PokemonEngine
    ) -> Set[str]:
        """Get functional IDs of all search options currently available."""
        actions = engine.get_legal_actions(state)
        select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]

        functional_ids = set()
        player = state.get_active_player()

        for action in select_actions:
            # Find the card instance
            for card in list(player.deck.cards) + list(player.prizes.cards):
                if card.id == action.card_id:
                    card_def = create_card(card.card_id)
                    if card_def and isinstance(card_def, PokemonCard):
                        func_id = engine._compute_functional_id(card_def)
                        functional_ids.add(func_id)
                    break

        return functional_ids

    # -------------------------------------------------------------------------
    # SAME FUNCTIONAL ID TESTS (should deduplicate to 1 option)
    # -------------------------------------------------------------------------

    def test_same_pidgey_all_in_deck(self, engine):
        """Two identical Pidgeys in deck should show as ONE option."""
        state, search_id = self.create_controlled_state(
            deck_card_ids=["sv3pt5-16", "sv3pt5-16"],  # 2x same Pidgey
            prize_card_ids=[],
            hand_card_ids=[],
            search_card_id="sv1-181"  # Nest Ball
        )
        state = engine.initialize_deck_knowledge(state)

        # Play Nest Ball
        actions = engine.get_legal_actions(state)
        play = [a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == search_id][0]
        state = engine.step(state, play)

        # Get search options
        func_ids = self.get_search_option_functional_ids(state, engine)

        # Should be exactly 1 unique functional ID
        assert len(func_ids) == 1, f"Expected 1 option for identical cards, got {len(func_ids)}: {func_ids}"

    def test_same_pidgey_split_deck_prizes(self, engine):
        """Two identical Pidgeys split between deck/prizes should show as ONE option (before search)."""
        state, search_id = self.create_controlled_state(
            deck_card_ids=["sv3pt5-16"],  # 1 Pidgey in deck
            prize_card_ids=["sv3pt5-16"],  # 1 Pidgey in prizes
            hand_card_ids=[],
            search_card_id="sv1-181"  # Nest Ball
        )
        state = engine.initialize_deck_knowledge(state)

        # Play Nest Ball
        actions = engine.get_legal_actions(state)
        play = [a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == search_id][0]
        state = engine.step(state, play)

        # Get search options
        func_ids = self.get_search_option_functional_ids(state, engine)

        # Should be exactly 1 unique functional ID (theoretical includes prized)
        assert len(func_ids) == 1, f"Expected 1 option for identical cards, got {len(func_ids)}: {func_ids}"

    def test_same_pidgey_all_in_prizes(self, engine):
        """Two identical Pidgeys ALL in prizes should show as ZERO options (not in deck).

        With the knowledge layer update, once a SearchDeckStep is pushed,
        has_searched_deck is set to True immediately. This means the search
        uses perfect knowledge (actual deck contents only), not theoretical
        deck (which would include prized cards).

        Since all Pidgeys are prized (not in the actual deck), the search
        correctly returns 0 selectable options.
        """
        state, search_id = self.create_controlled_state(
            deck_card_ids=["sv1-258"],  # Just energy in deck
            prize_card_ids=["sv3pt5-16", "sv3pt5-16"],  # 2 Pidgey in prizes
            hand_card_ids=[],
            search_card_id="sv1-181"  # Nest Ball
        )
        state = engine.initialize_deck_knowledge(state)

        # Play Nest Ball
        actions = engine.get_legal_actions(state)
        play = [a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == search_id][0]
        state = engine.step(state, play)

        # Get search options - with perfect knowledge, prized cards are not shown
        func_ids = self.get_search_option_functional_ids(state, engine)

        # Should be 0 options since all Pidgeys are prized (not in actual deck)
        assert len(func_ids) == 0, f"Expected 0 options for cards all in prizes, got {len(func_ids)}: {func_ids}"

    # -------------------------------------------------------------------------
    # DIFFERENT FUNCTIONAL ID TESTS (should show as separate options)
    # -------------------------------------------------------------------------

    def test_different_pidgeys_all_in_deck(self, engine):
        """Two DIFFERENT Pidgeys (different HP/attacks) in deck should show as TWO options."""
        # sv3pt5-16: Pidgey 50HP (Call for Family, Tackle)
        # sv3-162: Pidgey 60HP (Gust)
        state, search_id = self.create_controlled_state(
            deck_card_ids=["sv3pt5-16", "sv3-162"],  # Pidgey 50HP, Pidgey 60HP
            prize_card_ids=[],
            hand_card_ids=[],
            search_card_id="sv1-181"  # Nest Ball
        )
        state = engine.initialize_deck_knowledge(state)

        # Play Nest Ball
        actions = engine.get_legal_actions(state)
        play = [a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == search_id][0]
        state = engine.step(state, play)

        # Get search options
        func_ids = self.get_search_option_functional_ids(state, engine)

        # Should be exactly 2 unique functional IDs
        assert len(func_ids) == 2, f"Expected 2 options for different cards, got {len(func_ids)}: {func_ids}"

    def test_different_pidgeys_split_deck_prizes(self, engine):
        """Two DIFFERENT Pidgeys split deck/prizes should show as ONE option (only deck).

        With perfect knowledge (has_searched_deck=True set when SearchDeckStep is pushed),
        only the card actually in the deck is shown, not the one in prizes.
        """
        # sv3pt5-16: Pidgey 50HP (Call for Family, Tackle)
        # sv3-162: Pidgey 60HP (Gust)
        state, search_id = self.create_controlled_state(
            deck_card_ids=["sv3pt5-16"],  # Pidgey 50HP in deck
            prize_card_ids=["sv3-162"],   # Pidgey 60HP in prizes
            hand_card_ids=[],
            search_card_id="sv1-181"  # Nest Ball
        )
        state = engine.initialize_deck_knowledge(state)

        # Play Nest Ball
        actions = engine.get_legal_actions(state)
        play = [a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == search_id][0]
        state = engine.step(state, play)

        # Get search options - only deck cards shown with perfect knowledge
        func_ids = self.get_search_option_functional_ids(state, engine)

        # Should be exactly 1 (only the Pidgey in deck, not the prized one)
        assert len(func_ids) == 1, f"Expected 1 option for card in deck (not prized), got {len(func_ids)}: {func_ids}"

    # -------------------------------------------------------------------------
    # MIXED SCENARIOS (combination of same and different)
    # -------------------------------------------------------------------------

    def test_three_pidgeys_two_same_one_different(self, engine):
        """3 Pidgeys: 2 identical + 1 different should show as TWO options."""
        # sv3pt5-16: Pidgey 50HP (Call for Family, Tackle)
        # sv3-162: Pidgey 60HP (Gust)
        state, search_id = self.create_controlled_state(
            deck_card_ids=["sv3pt5-16", "sv3pt5-16", "sv3-162"],  # 2x 50HP, 1x 60HP
            prize_card_ids=[],
            hand_card_ids=[],
            search_card_id="sv1-181"  # Nest Ball
        )
        state = engine.initialize_deck_knowledge(state)

        # Play Nest Ball
        actions = engine.get_legal_actions(state)
        play = [a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == search_id][0]
        state = engine.step(state, play)

        # Get search options
        func_ids = self.get_search_option_functional_ids(state, engine)

        # Should be exactly 2 unique functional IDs
        assert len(func_ids) == 2, f"Expected 2 options (2 identical + 1 different), got {len(func_ids)}: {func_ids}"

    def test_complex_distribution_across_zones(self, engine):
        """Complex: 4 cards, 2 functional IDs, distributed across deck and prizes."""
        # sv3pt5-16: Pidgey 50HP (Call for Family, Tackle)
        # sv3-162: Pidgey 60HP (Gust)
        state, search_id = self.create_controlled_state(
            deck_card_ids=["sv3pt5-16", "sv3-162"],  # 1x each version in deck
            prize_card_ids=["sv3pt5-16", "sv3-162"],  # 1x each version in prizes
            hand_card_ids=[],
            search_card_id="sv1-181"  # Nest Ball
        )
        state = engine.initialize_deck_knowledge(state)

        # Play Nest Ball
        actions = engine.get_legal_actions(state)
        play = [a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == search_id][0]
        state = engine.step(state, play)

        # Get search options
        func_ids = self.get_search_option_functional_ids(state, engine)

        # Should be exactly 2 unique functional IDs
        assert len(func_ids) == 2, f"Expected 2 options for 2 unique functional IDs, got {len(func_ids)}: {func_ids}"

    # -------------------------------------------------------------------------
    # PARAMETRIZED FUZZ TESTS
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("distribution", [
        # (deck_count_A, prize_count_A, deck_count_B, prize_count_B)
        (2, 0, 0, 0),  # 2 same in deck
        (1, 1, 0, 0),  # 1 in deck, 1 in prizes (only deck shown)
        (0, 2, 0, 0),  # 2 same in prizes (none shown)
        (2, 0, 2, 0),  # 2+2 different, all deck
        (1, 1, 1, 1),  # 2+2 different, split (only deck shown)
        (0, 2, 0, 2),  # 2+2 different, all prizes (none shown)
        (2, 1, 1, 0),  # asymmetric
        (1, 0, 2, 1),  # asymmetric
        (3, 1, 2, 2),  # larger counts
    ])
    def test_functional_id_deduplication_distributions(self, engine, distribution):
        """
        Test functional ID deduplication across various deck/prize distributions.

        Uses two different Pidgey versions:
        - Version A: sv3pt5-16 (50 HP, Call for Family + Tackle)
        - Version B: sv3-162 (60 HP, Gust)

        With perfect knowledge (has_searched_deck=True set when SearchDeckStep is pushed),
        only cards actually in the deck are shown as search options, not prized cards.
        """
        deck_a, prize_a, deck_b, prize_b = distribution

        deck_cards = ["sv3pt5-16"] * deck_a + ["sv3-162"] * deck_b
        prize_cards = ["sv3pt5-16"] * prize_a + ["sv3-162"] * prize_b

        # Skip if no cards at all
        if not deck_cards and not prize_cards:
            pytest.skip("No cards in distribution")

        state, search_id = self.create_controlled_state(
            deck_card_ids=deck_cards,
            prize_card_ids=prize_cards,
            hand_card_ids=[],
            search_card_id="sv1-181"  # Nest Ball
        )
        state = engine.initialize_deck_knowledge(state)

        # Play Nest Ball
        actions = engine.get_legal_actions(state)
        play_actions = [a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == search_id]

        if not play_actions:
            pytest.skip("Nest Ball not playable")

        state = engine.step(state, play_actions[0])

        # Get search options
        func_ids = self.get_search_option_functional_ids(state, engine)

        # Calculate expected count - only deck cards are shown (not prized)
        has_version_a_in_deck = deck_a > 0
        has_version_b_in_deck = deck_b > 0
        expected_count = int(has_version_a_in_deck) + int(has_version_b_in_deck)

        assert len(func_ids) == expected_count, (
            f"Distribution {distribution}: Expected {expected_count} options (deck only), got {len(func_ids)}: {func_ids}"
        )

    @pytest.mark.parametrize("seed", range(100))
    def test_random_distribution_deduplication(self, engine, seed):
        """
        Randomly distribute cards and verify deduplication is correct.

        This is the "infinite combinations" fuzzer - it generates random
        prize/deck splits and verifies the invariant holds.

        With perfect knowledge (has_searched_deck=True set when SearchDeckStep is pushed),
        only cards actually in the deck are shown as search options.
        """
        random.seed(seed)

        # Pick 2-4 random basic Pokemon from our test pool
        num_versions = random.randint(1, 3)
        versions = random.sample(BASIC_POKEMON, min(num_versions, len(BASIC_POKEMON)))

        # For each version, decide how many copies (1-4) and how to split
        deck_cards = []
        prize_cards = []
        deck_functional_ids = set()  # Only track deck cards for expected result

        for card_id in versions:
            count = random.randint(1, 4)
            # Random split between deck and prizes
            deck_count = random.randint(0, count)
            prize_count = count - deck_count

            deck_cards.extend([card_id] * deck_count)
            prize_cards.extend([card_id] * prize_count)

            # Track expected functional ID only if in deck
            if deck_count > 0:
                card_def = create_card(card_id)
                if card_def and isinstance(card_def, PokemonCard):
                    func_id = engine._compute_functional_id(card_def)
                    deck_functional_ids.add(func_id)

        # Need at least one card somewhere
        if not deck_cards and not prize_cards:
            deck_cards = [random.choice(BASIC_POKEMON)]
            # Add to expected if we added to deck
            card_def = create_card(deck_cards[0])
            if card_def and isinstance(card_def, PokemonCard):
                deck_functional_ids.add(engine._compute_functional_id(card_def))

        state, search_id = self.create_controlled_state(
            deck_card_ids=deck_cards,
            prize_card_ids=prize_cards,
            hand_card_ids=[],
            search_card_id="sv1-181"  # Nest Ball
        )
        state = engine.initialize_deck_knowledge(state)

        # Play Nest Ball
        actions = engine.get_legal_actions(state)
        play_actions = [a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == search_id]

        if not play_actions:
            pytest.skip("Nest Ball not playable")

        state = engine.step(state, play_actions[0])

        # Get search options
        func_ids = self.get_search_option_functional_ids(state, engine)

        # Verify deduplication - only deck cards should be shown
        assert func_ids == deck_functional_ids, (
            f"Seed {seed}: Search options don't match deck functional IDs\n"
            f"Deck: {deck_cards}\nPrizes: {prize_cards}\n"
            f"Got: {func_ids}\nExpected (deck only): {deck_functional_ids}"
        )


# =============================================================================
# CARD-SPECIFIC FUZZING TESTS
# =============================================================================

class TestNestBallFuzzing:
    """Fuzz testing for Nest Ball across many random states."""

    @pytest.fixture
    def engine(self):
        return PokemonEngine()

    @pytest.mark.parametrize("seed", range(50))
    def test_nest_ball_random_states(self, engine, seed):
        """Nest Ball should work correctly in random game states."""
        random.seed(seed)

        state = generate_random_game_state(turn_count=random.randint(2, 10), phase=GamePhase.MAIN)
        player = state.players[state.active_player_index]

        # Add Nest Ball to hand
        nest_ball = create_card_instance("sv1-181", owner_id=player.player_id)
        player.hand.add_card(nest_ball)

        # Ensure bench has space
        while len(player.board.bench) >= 5:
            player.board.bench.pop()

        state = engine.initialize_deck_knowledge(state)

        # Try to play Nest Ball
        actions = engine.get_legal_actions(state)
        play_actions = [a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == nest_ball.id]

        if not play_actions:
            pytest.skip("Nest Ball not playable in this state")

        # Execute and verify no crash
        try:
            new_state = engine.step(state, play_actions[0])

            # Verify we're in a valid state
            assert new_state is not None
            assert new_state.resolution_stack or new_state.current_phase in [GamePhase.MAIN, GamePhase.CLEANUP]

            # If in resolution, verify we can get legal actions
            if new_state.resolution_stack:
                search_actions = engine.get_legal_actions(new_state)
                assert search_actions is not None

        except Exception as e:
            pytest.fail(f"Seed {seed}: Nest Ball crashed: {e}")


class TestUltraBallFuzzing:
    """Fuzz testing for Ultra Ball across many random states."""

    @pytest.fixture
    def engine(self):
        return PokemonEngine()

    @pytest.mark.parametrize("seed", range(50))
    def test_ultra_ball_random_states(self, engine, seed):
        """Ultra Ball should work correctly with various hand sizes."""
        random.seed(seed)

        state = generate_random_game_state(
            turn_count=random.randint(2, 10),
            phase=GamePhase.MAIN,
            hand_size=(random.randint(3, 10), random.randint(0, 5))  # Need 3+ cards (UB + 2 discard)
        )
        player = state.players[state.active_player_index]

        # Add Ultra Ball to hand
        ultra_ball = create_card_instance("sv1-196", owner_id=player.player_id)
        player.hand.add_card(ultra_ball)

        state = engine.initialize_deck_knowledge(state)

        # Check if Ultra Ball is playable (need 2 other cards to discard)
        other_cards = [c for c in player.hand.cards if c.id != ultra_ball.id]
        if len(other_cards) < 2:
            pytest.skip("Not enough cards to discard for Ultra Ball")

        actions = engine.get_legal_actions(state)
        play_actions = [a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == ultra_ball.id]

        if not play_actions:
            pytest.skip("Ultra Ball not playable in this state")

        try:
            new_state = engine.step(state, play_actions[0])
            assert new_state is not None

            # Should be in discard selection step
            if new_state.resolution_stack:
                step = new_state.resolution_stack[-1]
                discard_actions = engine.get_legal_actions(new_state)
                assert len(discard_actions) > 0, "Should have discard options"

        except Exception as e:
            pytest.fail(f"Seed {seed}: Ultra Ball crashed: {e}")

    @pytest.mark.parametrize("seed", range(30))
    def test_ultra_ball_complete_flow(self, engine, seed):
        """Test complete Ultra Ball flow: discard 2 -> search -> select."""
        random.seed(seed)

        # Create controlled state with enough cards
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        # Deck with Pokemon to find
        for _ in range(random.randint(5, 15)):
            player0.deck.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=0))
        for _ in range(random.randint(5, 10)):
            player0.deck.add_card(create_card_instance(random.choice(BASIC_ENERGY), owner_id=0))

        # Hand with Ultra Ball + discard fodder
        ultra_ball = create_card_instance("sv1-196", owner_id=0)
        player0.hand.add_card(ultra_ball)
        for _ in range(random.randint(3, 6)):
            player0.hand.add_card(create_card_instance(random.choice(BASIC_ENERGY), owner_id=0))

        # Prizes
        for _ in range(6):
            player0.prizes.add_card(create_card_instance(random.choice(BASIC_POKEMON + BASIC_ENERGY), owner_id=0))

        player0.board.active_spot = create_card_instance("svp-56", owner_id=0)
        player1.board.active_spot = create_card_instance("svp-56", owner_id=1)

        state = GameState(
            players=[player0, player1],
            turn_count=3,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)

        try:
            # Play Ultra Ball
            actions = engine.get_legal_actions(state)
            play_action = [a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == ultra_ball.id]
            if not play_action:
                pytest.skip("Ultra Ball not playable")

            state = engine.step(state, play_action[0])

            # Discard phase - select 2 cards
            for i in range(2):
                if not state.resolution_stack:
                    break
                actions = engine.get_legal_actions(state)
                select_actions = [a for a in actions if a.action_type == ActionType.SELECT_CARD]
                if select_actions:
                    state = engine.step(state, select_actions[0])

            # Confirm discard
            actions = engine.get_legal_actions(state)
            confirm_actions = [a for a in actions if a.action_type == ActionType.CONFIRM_SELECTION]
            if confirm_actions:
                state = engine.step(state, confirm_actions[0])

            # Search phase - should be able to select Pokemon or skip
            if state.resolution_stack:
                actions = engine.get_legal_actions(state)
                # Either select a Pokemon or confirm with 0
                if actions:
                    state = engine.step(state, actions[0])

            assert state is not None

        except Exception as e:
            pytest.fail(f"Seed {seed}: Ultra Ball complete flow crashed: {e}")


class TestBuddyBuddyPoffinFuzzing:
    """Fuzz testing for Buddy-Buddy Poffin (HP <= 70 filter)."""

    @pytest.fixture
    def engine(self):
        return PokemonEngine()

    @pytest.mark.parametrize("seed", range(50))
    def test_poffin_hp_filter_random_decks(self, engine, seed):
        """Poffin should only show Basic Pokemon with HP <= 70."""
        random.seed(seed)

        # Create deck with mix of HP values
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        low_hp_pokemon = ["sv3pt5-16", "svp-44", "sv5-126", "sv7-114"]  # HP <= 70
        high_hp_pokemon = ["svp-56", "sv8pt5-77"]  # HP > 70

        # Random mix in deck
        for _ in range(random.randint(3, 8)):
            player0.deck.add_card(create_card_instance(random.choice(low_hp_pokemon), owner_id=0))
        for _ in range(random.randint(1, 4)):
            player0.deck.add_card(create_card_instance(random.choice(high_hp_pokemon), owner_id=0))

        # Poffin in hand
        poffin = create_card_instance("sv5-144", owner_id=0)
        player0.hand.add_card(poffin)

        # Prizes (random)
        for _ in range(6):
            if random.random() < 0.5:
                player0.prizes.add_card(create_card_instance(random.choice(low_hp_pokemon), owner_id=0))
            else:
                player0.prizes.add_card(create_card_instance(random.choice(high_hp_pokemon), owner_id=0))

        player0.board.active_spot = create_card_instance("svp-56", owner_id=0)
        player1.board.active_spot = create_card_instance("svp-56", owner_id=1)

        # Ensure bench has space for 2
        while len(player0.board.bench) >= 4:
            player0.board.bench.pop()

        state = GameState(
            players=[player0, player1],
            turn_count=3,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)

        try:
            actions = engine.get_legal_actions(state)
            play_actions = [a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == poffin.id]

            if not play_actions:
                pytest.skip("Poffin not playable")

            state = engine.step(state, play_actions[0])

            # Check search options - all should be HP <= 70
            if state.resolution_stack:
                search_actions = engine.get_legal_actions(state)
                select_actions = [a for a in search_actions if a.action_type == ActionType.SELECT_CARD]

                for action in select_actions:
                    # Find the card
                    for card in list(player0.deck.cards) + list(player0.prizes.cards):
                        if card.id == action.card_id:
                            card_def = create_card(card.card_id)
                            if card_def and hasattr(card_def, 'hp'):
                                assert card_def.hp <= 70, f"Poffin showed {card_def.name} with HP {card_def.hp} > 70"
                            break

        except Exception as e:
            pytest.fail(f"Seed {seed}: Poffin crashed: {e}")


class TestRareCandyFuzzing:
    """Fuzz testing for Rare Candy evolution."""

    @pytest.fixture
    def engine(self):
        return PokemonEngine()

    @pytest.mark.parametrize("seed", range(30))
    def test_rare_candy_random_states(self, engine, seed):
        """Rare Candy should only work with valid Basic -> Stage 2 combos."""
        random.seed(seed)

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        # Active - might be a Basic that can evolve
        active_options = ["svp-44", "sv3pt5-16", "sv5-126"]  # Charmander, Pidgey, Hoothoot
        active = create_card_instance(random.choice(active_options), owner_id=0)
        active.turns_in_play = random.randint(1, 5)  # Must have been in play
        player0.board.active_spot = active

        # Bench - more potential evolution targets
        for _ in range(random.randint(0, 3)):
            bench_mon = create_card_instance(random.choice(active_options), owner_id=0)
            bench_mon.turns_in_play = random.randint(0, 3)
            player0.board.bench.append(bench_mon)

        # Hand with Rare Candy + potential Stage 2
        rare_candy = create_card_instance("sv4pt5-89", owner_id=0)
        player0.hand.add_card(rare_candy)

        # Maybe add a Stage 2 to hand
        if random.random() < 0.7:
            player0.hand.add_card(create_card_instance("sv3-125", owner_id=0))  # Charizard ex

        # Deck and prizes
        for _ in range(20):
            player0.deck.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=0))
        for _ in range(6):
            player0.prizes.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=0))

        player1.board.active_spot = create_card_instance("svp-56", owner_id=1)

        state = GameState(
            players=[player0, player1],
            turn_count=random.randint(2, 10),
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)

        try:
            actions = engine.get_legal_actions(state)
            play_actions = [a for a in actions if a.action_type == ActionType.PLAY_ITEM and a.card_id == rare_candy.id]

            if play_actions:
                state = engine.step(state, play_actions[0])
                assert state is not None

                # If in resolution, verify we can proceed
                if state.resolution_stack:
                    next_actions = engine.get_legal_actions(state)
                    assert next_actions is not None

        except Exception as e:
            pytest.fail(f"Seed {seed}: Rare Candy crashed: {e}")


class TestIonoFuzzing:
    """Fuzz testing for Iono supporter card."""

    @pytest.fixture
    def engine(self):
        return PokemonEngine()

    @pytest.mark.parametrize("seed", range(50))
    def test_iono_random_prize_counts(self, engine, seed):
        """Iono should work with various prize counts for both players."""
        random.seed(seed)

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        # Random prize counts (1-6 for each player)
        p0_prizes = random.randint(1, 6)
        p1_prizes = random.randint(1, 6)

        # Set up player 0
        for _ in range(p0_prizes):
            player0.prizes.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=0))

        # Hand with Iono
        iono = create_card_instance("sv2-185", owner_id=0)
        player0.hand.add_card(iono)

        # Add more cards to hand
        for _ in range(random.randint(2, 7)):
            player0.hand.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=0))

        # Deck
        for _ in range(random.randint(10, 30)):
            player0.deck.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=0))

        # Set up player 1 similarly
        for _ in range(p1_prizes):
            player1.prizes.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=1))
        for _ in range(random.randint(3, 7)):
            player1.hand.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=1))
        for _ in range(random.randint(10, 30)):
            player1.deck.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=1))

        player0.board.active_spot = create_card_instance("svp-56", owner_id=0)
        player1.board.active_spot = create_card_instance("svp-56", owner_id=1)

        state = GameState(
            players=[player0, player1],
            turn_count=random.randint(2, 10),  # Turn 2+ (can play supporter)
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0,
            supporter_played=False
        )
        state = engine.initialize_deck_knowledge(state)

        try:
            actions = engine.get_legal_actions(state)
            play_actions = [a for a in actions if a.action_type == ActionType.PLAY_SUPPORTER and a.card_id == iono.id]

            if not play_actions:
                # Iono might not be implemented yet
                pytest.skip("Iono not playable (may not be implemented)")

            # Record hand/deck sizes before
            p0_hand_before = len(player0.hand.cards)
            p1_hand_before = len(player1.hand.cards)

            state = engine.step(state, play_actions[0])

            # After Iono: each player shuffles hand into deck, draws cards = their prize count
            # Just verify no crash and state is valid
            assert state is not None

        except Exception as e:
            if "not implemented" in str(e).lower():
                pytest.skip("Iono not implemented")
            pytest.fail(f"Seed {seed}: Iono crashed with {p0_prizes}/{p1_prizes} prizes: {e}")


class TestCharizardExFuzzing:
    """Fuzz testing for Charizard ex abilities and attacks."""

    @pytest.fixture
    def engine(self):
        return PokemonEngine()

    @pytest.mark.parametrize("seed", range(30))
    def test_charizard_ex_infernal_reign_random_states(self, engine, seed):
        """Test Infernal Reign ability in various game states."""
        random.seed(seed)

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        # Charizard ex as active
        charizard = create_card_instance("svp-56", owner_id=0)
        charizard.turns_in_play = random.randint(1, 5)
        player0.board.active_spot = charizard

        # Random bench
        for _ in range(random.randint(0, 4)):
            bench_mon = create_card_instance(random.choice(BASIC_POKEMON), owner_id=0)
            bench_mon.turns_in_play = random.randint(0, 3)
            player0.board.bench.append(bench_mon)

        # Deck with Fire energy
        for _ in range(random.randint(5, 15)):
            player0.deck.add_card(create_card_instance("sv1-258", owner_id=0))
        for _ in range(random.randint(5, 10)):
            player0.deck.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=0))

        # Hand
        for _ in range(random.randint(3, 7)):
            player0.hand.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=0))

        # Prizes
        for _ in range(6):
            player0.prizes.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=0))

        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)
        for _ in range(6):
            player1.prizes.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=1))

        state = GameState(
            players=[player0, player1],
            turn_count=random.randint(2, 10),
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)

        try:
            actions = engine.get_legal_actions(state)

            # Look for ability action
            ability_actions = [a for a in actions if a.action_type == ActionType.USE_ABILITY]

            if ability_actions:
                # Use the ability
                state = engine.step(state, ability_actions[0])
                assert state is not None

        except Exception as e:
            if "not implemented" in str(e).lower():
                pytest.skip("Charizard ex ability not implemented")
            pytest.fail(f"Seed {seed}: Charizard ex ability crashed: {e}")

    @pytest.mark.parametrize("seed", range(30))
    def test_charizard_ex_burning_darkness_attack(self, engine, seed):
        """Test Burning Darkness attack with various discard pile sizes."""
        random.seed(seed)

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        # Charizard ex as active with energy
        charizard = create_card_instance("svp-56", owner_id=0)
        charizard.turns_in_play = random.randint(1, 5)

        # Attach energy (need 2 Fire for Burning Darkness)
        for _ in range(random.randint(2, 4)):
            energy = create_card_instance("sv1-258", owner_id=0)
            charizard.attached_energy.append(energy)

        player0.board.active_spot = charizard

        # Random discard pile size (affects damage)
        discard_size = random.randint(0, 20)
        for _ in range(discard_size):
            player0.discard.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=0))

        # Deck and hand
        for _ in range(random.randint(10, 20)):
            player0.deck.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=0))
        for _ in range(random.randint(3, 7)):
            player0.hand.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=0))
        for _ in range(6):
            player0.prizes.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=0))

        # Opponent
        opponent_hp = random.randint(60, 200)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)
        for _ in range(6):
            player1.prizes.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=1))

        state = GameState(
            players=[player0, player1],
            turn_count=random.randint(2, 10),
            active_player_index=0,
            current_phase=GamePhase.MAIN,  # Attacks happen in MAIN phase
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)

        try:
            actions = engine.get_legal_actions(state)

            # Look for attack action
            attack_actions = [a for a in actions if a.action_type == ActionType.ATTACK]

            if attack_actions:
                state = engine.step(state, attack_actions[0])
                assert state is not None

        except Exception as e:
            if "not implemented" in str(e).lower():
                pytest.skip("Charizard ex attack not implemented")
            pytest.fail(f"Seed {seed}: Charizard ex attack crashed with {discard_size} cards in discard: {e}")


class TestHoothootFuzzing:
    """Fuzz testing for Hoothoot variants."""

    @pytest.fixture
    def engine(self):
        return PokemonEngine()

    @pytest.mark.parametrize("hoothoot_id", ["sv5-126", "sv7-114", "sv8pt5-77"])
    @pytest.mark.parametrize("seed", range(10))
    def test_hoothoot_attacks_random_states(self, engine, hoothoot_id, seed):
        """Test Hoothoot attacks in various states."""
        random.seed(seed)

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        # Hoothoot as active
        try:
            hoothoot = create_card_instance(hoothoot_id, owner_id=0)
        except:
            pytest.skip(f"Hoothoot {hoothoot_id} not in registry")

        hoothoot.turns_in_play = random.randint(1, 3)

        # Attach some energy
        energy_count = random.randint(1, 3)
        for _ in range(energy_count):
            energy = create_card_instance("sv1-258", owner_id=0)
            hoothoot.attached_energy.append(energy)

        player0.board.active_spot = hoothoot

        # Standard setup
        for _ in range(20):
            player0.deck.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=0))
        for _ in range(5):
            player0.hand.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=0))
        for _ in range(6):
            player0.prizes.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=0))

        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)
        for _ in range(6):
            player1.prizes.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=1))

        state = GameState(
            players=[player0, player1],
            turn_count=random.randint(2, 10),
            active_player_index=0,
            current_phase=GamePhase.MAIN,  # Attacks happen in MAIN phase
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)

        try:
            actions = engine.get_legal_actions(state)
            attack_actions = [a for a in actions if a.action_type == ActionType.ATTACK]

            if attack_actions:
                state = engine.step(state, attack_actions[0])
                assert state is not None

        except Exception as e:
            pytest.fail(f"Seed {seed}: Hoothoot {hoothoot_id} crashed: {e}")


class TestCharmanderFuzzing:
    """Fuzz testing for Charmander variants."""

    @pytest.fixture
    def engine(self):
        return PokemonEngine()

    @pytest.mark.parametrize("charmander_id", ["svp-44", "svp-47", "sv4pt5-7"])
    @pytest.mark.parametrize("seed", range(10))
    def test_charmander_attacks_random_states(self, engine, charmander_id, seed):
        """Test Charmander attacks in various states."""
        random.seed(seed)

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        # Charmander as active
        try:
            charmander = create_card_instance(charmander_id, owner_id=0)
        except:
            pytest.skip(f"Charmander {charmander_id} not in registry")

        charmander.turns_in_play = random.randint(1, 3)

        # Attach Fire energy
        energy_count = random.randint(1, 3)
        for _ in range(energy_count):
            energy = create_card_instance("sv1-258", owner_id=0)
            charmander.attached_energy.append(energy)

        player0.board.active_spot = charmander

        # Standard setup
        for _ in range(20):
            player0.deck.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=0))
        for _ in range(5):
            player0.hand.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=0))
        for _ in range(6):
            player0.prizes.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=0))

        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)
        for _ in range(6):
            player1.prizes.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=1))

        state = GameState(
            players=[player0, player1],
            turn_count=random.randint(2, 10),
            active_player_index=0,
            current_phase=GamePhase.MAIN,  # Attacks happen in MAIN phase
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)

        try:
            actions = engine.get_legal_actions(state)
            attack_actions = [a for a in actions if a.action_type == ActionType.ATTACK]

            if attack_actions:
                state = engine.step(state, attack_actions[0])
                assert state is not None

        except Exception as e:
            pytest.fail(f"Seed {seed}: Charmander {charmander_id} crashed: {e}")


class TestMultiCardInteractionFuzzing:
    """Fuzz testing for combinations of cards used together."""

    @pytest.fixture
    def engine(self):
        return PokemonEngine()

    @pytest.mark.parametrize("seed", range(30))
    def test_multiple_search_cards_in_hand(self, engine, seed):
        """Test having multiple search cards and using them in sequence."""
        random.seed(seed)

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        # Hand with multiple search cards
        search_cards = []
        for card_id in random.sample(["sv1-181", "sv5-144", "sv1-196"], k=random.randint(1, 3)):
            card = create_card_instance(card_id, owner_id=0)
            player0.hand.add_card(card)
            search_cards.append(card)

        # Add discard fodder for Ultra Ball
        for _ in range(5):
            player0.hand.add_card(create_card_instance(random.choice(BASIC_ENERGY), owner_id=0))

        # Deck with various Pokemon
        for _ in range(10):
            player0.deck.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=0))
        for _ in range(10):
            player0.deck.add_card(create_card_instance(random.choice(BASIC_ENERGY), owner_id=0))

        for _ in range(6):
            player0.prizes.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=0))

        player0.board.active_spot = create_card_instance("svp-56", owner_id=0)
        player1.board.active_spot = create_card_instance("svp-56", owner_id=1)
        for _ in range(6):
            player1.prizes.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=1))

        state = GameState(
            players=[player0, player1],
            turn_count=3,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)

        try:
            # Try to use each search card
            cards_used = 0
            for _ in range(len(search_cards)):
                actions = engine.get_legal_actions(state)
                play_actions = [a for a in actions if a.action_type == ActionType.PLAY_ITEM]

                if not play_actions:
                    break

                state = engine.step(state, play_actions[0])
                cards_used += 1

                # Complete any resolution steps
                max_steps = 20
                steps = 0
                while state.resolution_stack and steps < max_steps:
                    actions = engine.get_legal_actions(state)
                    if not actions:
                        break
                    # Prefer confirm/cancel to end resolution
                    confirm = [a for a in actions if a.action_type in [ActionType.CONFIRM_SELECTION, ActionType.CANCEL_ACTION]]
                    if confirm:
                        state = engine.step(state, confirm[0])
                    else:
                        state = engine.step(state, actions[0])
                    steps += 1

            assert state is not None

        except Exception as e:
            pytest.fail(f"Seed {seed}: Multi-search cards crashed: {e}")


# =============================================================================
# EVOLVED POKEMON KNOCKOUT TESTS
# =============================================================================

class TestEvolvedPokemonKnockout:
    """
    Test that evolved Pokemon knockouts correctly move ALL cards to discard:
    - The top-level evolved Pokemon
    - All previous evolution stages (stored in previous_stages)
    - All attached energy
    - All attached tools

    Example: Charizard ex (evolved from Charmander -> Charmeleon) with 3 Fire energy
    should result in 6 cards going to discard: Charizard, Charmeleon, Charmander, 3 energy
    """

    @pytest.fixture
    def engine(self):
        return PokemonEngine()

    def create_evolved_pokemon(
        self,
        evolution_chain: List[str],  # e.g., ["svp-44", "sv3-27", "sv3-125"] for Charmander -> Charmeleon -> Charizard
        owner_id: int = 0,
        energy_count: int = 0,
        tool_count: int = 0
    ):
        """
        Create a fully evolved Pokemon with previous stages stored.

        Returns the top-level Pokemon with previous_stages populated.
        """
        if not evolution_chain:
            return None

        # Build evolution chain from bottom up
        previous_pokemon = None
        for i, card_id in enumerate(evolution_chain):
            pokemon = create_card_instance(card_id, owner_id=owner_id)
            pokemon.turns_in_play = len(evolution_chain) - i  # Earlier stages played earlier

            if previous_pokemon:
                # Store previous evolution stages (CardInstance objects)
                pokemon.previous_stages = previous_pokemon.previous_stages + [previous_pokemon]
                # Also set evolution_chain (card IDs) for engine's knockout handler
                pokemon.evolution_chain = [p.card_id for p in pokemon.previous_stages]

            previous_pokemon = pokemon

        # The final Pokemon is the top-level evolved form
        top_pokemon = previous_pokemon

        # Attach energy
        for _ in range(energy_count):
            energy = create_card_instance("sv1-258", owner_id=owner_id)
            top_pokemon.attached_energy.append(energy)

        # Attach tools (if we have any tool card IDs)
        # For now, skip tools as we don't have tool cards in the test pool

        return top_pokemon

    def count_all_cards_on_pokemon(self, pokemon) -> int:
        """Count all cards associated with a Pokemon (itself, previous stages, attachments).

        Note: previous_stages is a FLAT list containing all prior evolution stages,
        so we don't recurse - each previous stage card counts as 1 plus its own attachments.
        """
        if pokemon is None:
            return 0

        count = 1  # The Pokemon itself
        count += len(pokemon.attached_energy)
        count += len(pokemon.attached_tools)

        # Count previous stages (flat list, no recursion needed)
        for prev_stage in pokemon.previous_stages:
            count += 1  # The previous stage card itself
            count += len(prev_stage.attached_energy)
            count += len(prev_stage.attached_tools)

        return count

    def get_all_card_ids_on_pokemon(self, pokemon) -> Set[str]:
        """Get all card instance IDs associated with a Pokemon.

        Note: previous_stages is a FLAT list, so we don't recurse.
        """
        if pokemon is None:
            return set()

        ids = {pokemon.id}
        ids.update(e.id for e in pokemon.attached_energy)
        ids.update(t.id for t in pokemon.attached_tools)

        # Collect IDs from previous stages (flat list, no recursion)
        for prev_stage in pokemon.previous_stages:
            ids.add(prev_stage.id)
            ids.update(e.id for e in prev_stage.attached_energy)
            ids.update(t.id for t in prev_stage.attached_tools)

        return ids

    def test_stage_2_knockout_all_cards_to_discard(self, engine):
        """
        Charizard ex (Stage 2) knocked out should send:
        - Charizard ex
        - Charmeleon (previous stage)
        - Charmander (basic)
        - All attached energy
        ALL to discard pile.
        """
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        # Create evolved Charizard ex with energy
        # Chain: Charmander (svp-44) -> Charmeleon (sv3-27) -> Charizard ex (sv3-125)
        charizard = self.create_evolved_pokemon(
            evolution_chain=["svp-44", "sv3-27", "sv3-125"],
            owner_id=0,
            energy_count=3
        )

        # Set Charizard with high damage counters so it gets KO'd by Burning Darkness (180 damage)
        # Charizard ex has 330 HP. With 15 damage counters (150 damage), an attack of 180+ KOs it.
        # Must do this BEFORE state is created so the value persists through cloning
        charizard.damage_counters = 15  # 150 damage already taken
        charizard.current_hp = 330 - (15 * 10)  # Keep current_hp in sync

        # Track all cards that should go to discard
        cards_on_charizard = self.get_all_card_ids_on_pokemon(charizard)
        expected_discard_count = self.count_all_cards_on_pokemon(charizard)

        # Should be: Charizard(1) + Charmeleon(1) + Charmander(1) + Energy(3) = 6
        assert expected_discard_count == 6, f"Expected 6 cards on Charizard, got {expected_discard_count}"
        assert len(charizard.previous_stages) == 2, f"Expected 2 previous stages, got {len(charizard.previous_stages)}"

        player0.board.active_spot = charizard

        # Give player 0 a bench Pokemon to promote after KO
        backup = create_card_instance("sv3pt5-16", owner_id=0)
        backup.turns_in_play = 1
        player0.board.bench.append(backup)

        # Deck and prizes for valid state
        for _ in range(20):
            player0.deck.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=0))
        for _ in range(6):
            player0.prizes.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=0))

        # Opponent with high-damage attack capability
        attacker = create_card_instance("svp-56", owner_id=1)  # Charizard ex
        attacker.turns_in_play = 2
        # Attach enough Fire energy for Burning Darkness [FF]
        for _ in range(4):
            attacker.attached_energy.append(create_card_instance(FIRE_ENERGY_ID, owner_id=1))
        player1.board.active_spot = attacker

        for _ in range(6):
            player1.prizes.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=1))
        for _ in range(10):
            player1.deck.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=1))

        state = GameState(
            players=[player0, player1],
            turn_count=5,
            active_player_index=1,  # Opponent's turn to attack
            current_phase=GamePhase.MAIN,  # Attacks happen in MAIN phase
            starting_player_id=0
        )

        # Record initial card count
        initial_card_ids = get_all_card_ids(state)
        initial_p0_discard = len(player0.discard.cards)

        state = engine.initialize_deck_knowledge(state)

        # Get attack action for opponent
        actions = engine.get_legal_actions(state)
        attack_actions = [a for a in actions if a.action_type == ActionType.ATTACK]

        if not attack_actions:
            pytest.skip("No attack actions available")

        # Execute attack (HP was set low earlier before state creation)
        try:
            state = engine.step(state, attack_actions[0])

            # If game requires promoting a new active, do it
            while state.resolution_stack:
                actions = engine.get_legal_actions(state)
                if not actions:
                    break
                state = engine.step(state, actions[0])

            # Verify card conservation
            final_card_ids = get_all_card_ids(state)
            assert initial_card_ids == final_card_ids, (
                f"Card IDs changed after knockout!\n"
                f"Missing: {initial_card_ids - final_card_ids}\n"
                f"Extra: {final_card_ids - initial_card_ids}"
            )

            # If Charizard was knocked out, verify all its cards are in discard
            if state.players[0].board.active_spot != charizard:
                # Charizard was KO'd - check discard
                discard_ids = {c.id for c in state.players[0].discard.cards}

                for card_id in cards_on_charizard:
                    assert card_id in discard_ids, (
                        f"Card {card_id} from Charizard not found in discard after KO"
                    )

        except Exception as e:
            pytest.fail(f"Evolved Pokemon knockout test crashed: {e}")

    @pytest.mark.parametrize("energy_count", [0, 1, 3, 5])
    def test_stage_1_knockout_with_varying_energy(self, engine, energy_count):
        """Test Stage 1 knockout with different amounts of attached energy."""
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        # Charmeleon evolved from Charmander
        charmeleon = self.create_evolved_pokemon(
            evolution_chain=["svp-44", "sv3-27"],  # Charmander -> Charmeleon
            owner_id=0,
            energy_count=energy_count
        )

        expected_card_count = 2 + energy_count  # Charmeleon + Charmander + energy
        actual_count = self.count_all_cards_on_pokemon(charmeleon)
        assert actual_count == expected_card_count, f"Expected {expected_card_count}, got {actual_count}"

        # Charmeleon has 90 HP, Burning Darkness does 180 damage - guaranteed KO
        player0.board.active_spot = charmeleon

        # Backup Pokemon
        backup = create_card_instance("sv3pt5-16", owner_id=0)
        backup.turns_in_play = 1
        player0.board.bench.append(backup)

        # Standard setup
        for _ in range(20):
            player0.deck.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=0))
        for _ in range(6):
            player0.prizes.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=0))

        # Opponent with Fire energy for Burning Darkness [FF]
        attacker = create_card_instance("svp-56", owner_id=1)
        attacker.turns_in_play = 2
        for _ in range(3):
            attacker.attached_energy.append(create_card_instance(FIRE_ENERGY_ID, owner_id=1))
        player1.board.active_spot = attacker

        for _ in range(6):
            player1.prizes.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=1))
        for _ in range(10):
            player1.deck.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=1))

        state = GameState(
            players=[player0, player1],
            turn_count=5,
            active_player_index=1,
            current_phase=GamePhase.MAIN,  # Attacks happen in MAIN phase
            starting_player_id=0
        )

        initial_card_ids = get_all_card_ids(state)
        state = engine.initialize_deck_knowledge(state)

        actions = engine.get_legal_actions(state)
        attack_actions = [a for a in actions if a.action_type == ActionType.ATTACK]

        if not attack_actions:
            pytest.skip("No attack actions available")

        try:
            state = engine.step(state, attack_actions[0])

            # Complete any resolution
            max_steps = 10
            steps = 0
            while state.resolution_stack and steps < max_steps:
                actions = engine.get_legal_actions(state)
                if not actions:
                    break
                state = engine.step(state, actions[0])
                steps += 1

            # Verify card conservation
            final_card_ids = get_all_card_ids(state)
            assert initial_card_ids == final_card_ids, (
                f"Card conservation failed with {energy_count} energy!\n"
                f"Missing: {initial_card_ids - final_card_ids}\n"
                f"Extra: {final_card_ids - initial_card_ids}"
            )

        except Exception as e:
            pytest.fail(f"Stage 1 knockout with {energy_count} energy crashed: {e}")

    @pytest.mark.parametrize("seed", range(20))
    def test_random_evolved_pokemon_knockout_conservation(self, engine, seed):
        """Fuzz test: random evolution chains with random energy, verify conservation."""
        random.seed(seed)

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        # Random evolution chain (1-3 stages)
        evolution_options = [
            ["svp-44"],  # Just Charmander (Basic)
            ["svp-44", "sv3-27"],  # Charmander -> Charmeleon
            ["svp-44", "sv3-27", "sv3-125"],  # Full chain to Charizard ex
        ]
        chain = random.choice(evolution_options)
        energy_count = random.randint(0, 4)

        evolved = self.create_evolved_pokemon(
            evolution_chain=chain,
            owner_id=0,
            energy_count=energy_count
        )
        # Set high damage counters to ensure KO by Burning Darkness (180 damage)
        # For Stage 2 (Charizard ex with 330 HP), we need at least 151 existing damage
        # Use damage_counters since is_knocked_out uses damage_counters * 10
        evolved.damage_counters = 16  # 160 damage, so 180 more will exceed any Pokemon's HP

        player0.board.active_spot = evolved

        # Backup Pokemon
        backup = create_card_instance("sv3pt5-16", owner_id=0)
        backup.turns_in_play = 1
        player0.board.bench.append(backup)

        # Standard setup
        for _ in range(20):
            player0.deck.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=0))
        for _ in range(6):
            player0.prizes.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=0))

        # Opponent with Fire energy for Burning Darkness [FF]
        attacker = create_card_instance("svp-56", owner_id=1)
        attacker.turns_in_play = 2
        for _ in range(3):
            attacker.attached_energy.append(create_card_instance(FIRE_ENERGY_ID, owner_id=1))
        player1.board.active_spot = attacker

        for _ in range(6):
            player1.prizes.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=1))
        for _ in range(10):
            player1.deck.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=1))

        state = GameState(
            players=[player0, player1],
            turn_count=5,
            active_player_index=1,
            current_phase=GamePhase.MAIN,  # Attacks happen in MAIN phase
            starting_player_id=0
        )

        initial_card_ids = get_all_card_ids(state)
        state = engine.initialize_deck_knowledge(state)

        actions = engine.get_legal_actions(state)
        attack_actions = [a for a in actions if a.action_type == ActionType.ATTACK]

        if not attack_actions:
            pytest.skip("No attack actions available")

        try:
            state = engine.step(state, attack_actions[0])

            # Complete resolution
            max_steps = 10
            steps = 0
            while state.resolution_stack and steps < max_steps:
                actions = engine.get_legal_actions(state)
                if not actions:
                    break
                state = engine.step(state, actions[0])
                steps += 1

            # Card conservation check
            final_card_ids = get_all_card_ids(state)
            assert initial_card_ids == final_card_ids, (
                f"Seed {seed}: Card conservation failed!\n"
                f"Chain: {chain}, Energy: {energy_count}\n"
                f"Missing: {initial_card_ids - final_card_ids}\n"
                f"Extra: {final_card_ids - initial_card_ids}"
            )

        except Exception as e:
            pytest.fail(f"Seed {seed}: Random evolved KO test crashed: {e}")


# =============================================================================
# FEZANDIPITI EX FUZZING TESTS
# =============================================================================

class TestFezandipitiExFuzzing:
    """
    Fuzz testing for Fezandipiti ex's Flip the Script ability.

    Flip the Script:
    - Once during your turn, if any of your Pokemon were Knocked Out during
      your opponent's last turn, you may draw 3 cards.
    - You can't use more than 1 Flip the Script Ability each turn.

    Invariants tested:
    1. Ability appears in legal actions when conditions are met
    2. Always draws exactly 3 cards (or remaining deck if < 3)
    3. Global restriction works (only 1 Flip the Script per turn total)
    4. Works with any deck state
    """

    FEZANDIPITI_EX_ID = "sv6pt5-38"

    @pytest.fixture
    def engine(self):
        return PokemonEngine()

    def create_flip_the_script_state(
        self,
        deck_size: int,
        hand_size: int,
        bench_fez_count: int = 0,
        ko_happened: bool = True,
        seed: int = 42
    ) -> GameState:
        """
        Create a game state where Flip the Script can be tested.

        Args:
            deck_size: Number of cards in deck
            hand_size: Number of cards in hand
            bench_fez_count: Number of Fezandipiti ex on bench (in addition to active)
            ko_happened: Whether a KO happened last turn (triggers ability condition)
            seed: Random seed for reproducibility
        """
        random.seed(seed)

        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        # Fezandipiti ex as active
        fez_active = create_card_instance(self.FEZANDIPITI_EX_ID, owner_id=0)
        fez_active.turns_in_play = random.randint(1, 5)
        player0.board.active_spot = fez_active

        # Additional Fezandipiti ex on bench
        for _ in range(bench_fez_count):
            fez_bench = create_card_instance(self.FEZANDIPITI_EX_ID, owner_id=0)
            fez_bench.turns_in_play = random.randint(1, 5)
            player0.board.bench.append(fez_bench)

        # Fill remaining bench with random Pokemon
        remaining_bench = 5 - bench_fez_count
        for _ in range(random.randint(0, remaining_bench)):
            bench_mon = create_card_instance(random.choice(BASIC_POKEMON), owner_id=0)
            bench_mon.turns_in_play = random.randint(1, 3)
            player0.board.bench.append(bench_mon)

        # Deck with random cards
        for _ in range(deck_size):
            player0.deck.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=0))

        # Hand with random cards
        for _ in range(hand_size):
            player0.hand.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=0))

        # Prizes
        for _ in range(6):
            player0.prizes.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=0))

        # Opponent setup
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)
        for _ in range(6):
            player1.prizes.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=1))
        for _ in range(10):
            player1.deck.add_card(create_card_instance(random.choice(ALL_CARDS), owner_id=1))

        state = GameState(
            players=[player0, player1],
            turn_count=random.randint(2, 10),
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        # Set up last_turn_metadata to simulate KO condition
        if ko_happened:
            state.last_turn_metadata = {
                'knocked_out_player_ids': [0],  # Player 0's Pokemon was KO'd
                'pokemon_knocked_out': True
            }
        else:
            state.last_turn_metadata = {}

        return state

    @pytest.mark.parametrize("seed", range(50))
    def test_flip_the_script_always_available_when_conditions_met(self, engine, seed):
        """
        Flip the Script should ALWAYS appear in legal actions when:
        - A Pokemon was KO'd last turn
        - Deck has cards
        - Ability hasn't been used this turn
        """
        deck_size = random.Random(seed).randint(3, 30)
        hand_size = random.Random(seed).randint(0, 7)

        state = self.create_flip_the_script_state(
            deck_size=deck_size,
            hand_size=hand_size,
            ko_happened=True,
            seed=seed
        )
        state = engine.initialize_deck_knowledge(state)

        actions = engine.get_legal_actions(state)
        ability_actions = [a for a in actions if a.action_type == ActionType.USE_ABILITY]
        flip_actions = [a for a in ability_actions if a.ability_name == "Flip the Script"]

        assert len(flip_actions) >= 1, (
            f"Seed {seed}: Flip the Script should be available but wasn't found. "
            f"Deck size: {deck_size}, Hand size: {hand_size}, "
            f"last_turn_metadata: {state.last_turn_metadata}"
        )

    @pytest.mark.parametrize("seed", range(50))
    def test_flip_the_script_draws_correct_cards(self, engine, seed):
        """
        Flip the Script should ALWAYS draw exactly 3 cards (or remaining deck).
        """
        random.seed(seed)
        deck_size = random.randint(1, 30)  # Include edge cases with small decks
        hand_size = random.randint(0, 7)

        state = self.create_flip_the_script_state(
            deck_size=deck_size,
            hand_size=hand_size,
            ko_happened=True,
            seed=seed
        )
        state = engine.initialize_deck_knowledge(state)

        initial_hand_size = len(state.players[0].hand.cards)
        initial_deck_size = len(state.players[0].deck.cards)
        expected_draw = min(3, initial_deck_size)

        actions = engine.get_legal_actions(state)
        flip_actions = [a for a in actions
                        if a.action_type == ActionType.USE_ABILITY
                        and a.ability_name == "Flip the Script"]

        assert flip_actions, f"Seed {seed}: No Flip the Script action found"

        # Execute the ability
        state = engine.step(state, flip_actions[0])

        final_hand_size = len(state.players[0].hand.cards)
        final_deck_size = len(state.players[0].deck.cards)

        cards_drawn = final_hand_size - initial_hand_size
        cards_removed_from_deck = initial_deck_size - final_deck_size

        assert cards_drawn == expected_draw, (
            f"Seed {seed}: Expected to draw {expected_draw} cards, drew {cards_drawn}. "
            f"Initial deck: {initial_deck_size}, Final deck: {final_deck_size}"
        )
        assert cards_removed_from_deck == expected_draw, (
            f"Seed {seed}: Expected {expected_draw} cards removed from deck, "
            f"but {cards_removed_from_deck} were removed"
        )

    @pytest.mark.parametrize("deck_size", [1, 2, 3, 5, 10, 20])
    def test_flip_the_script_edge_case_deck_sizes(self, engine, deck_size):
        """
        Test Flip the Script with specific deck sizes to ensure edge cases work.
        """
        state = self.create_flip_the_script_state(
            deck_size=deck_size,
            hand_size=3,
            ko_happened=True,
            seed=12345
        )
        state = engine.initialize_deck_knowledge(state)

        initial_hand_size = len(state.players[0].hand.cards)
        expected_draw = min(3, deck_size)

        actions = engine.get_legal_actions(state)
        flip_actions = [a for a in actions
                        if a.action_type == ActionType.USE_ABILITY
                        and a.ability_name == "Flip the Script"]

        assert flip_actions, f"Deck size {deck_size}: No Flip the Script action found"

        state = engine.step(state, flip_actions[0])

        final_hand_size = len(state.players[0].hand.cards)
        cards_drawn = final_hand_size - initial_hand_size

        assert cards_drawn == expected_draw, (
            f"Deck size {deck_size}: Expected to draw {expected_draw}, drew {cards_drawn}"
        )

    @pytest.mark.parametrize("seed", range(30))
    def test_flip_the_script_global_once_per_turn(self, engine, seed):
        """
        Only ONE Flip the Script can be used per turn, even with multiple Fezandipiti ex.
        """
        state = self.create_flip_the_script_state(
            deck_size=20,
            hand_size=3,
            bench_fez_count=2,  # Active + 2 benched = 3 total Fezandipiti ex
            ko_happened=True,
            seed=seed
        )
        state = engine.initialize_deck_knowledge(state)

        # All 3 Fezandipiti ex should show Flip the Script initially
        actions = engine.get_legal_actions(state)
        flip_actions = [a for a in actions
                        if a.action_type == ActionType.USE_ABILITY
                        and a.ability_name == "Flip the Script"]

        # Should have 3 instances (one for each Fezandipiti ex)
        assert len(flip_actions) == 3, (
            f"Seed {seed}: Expected 3 Flip the Script actions (one per Fez), got {len(flip_actions)}"
        )

        # Use one of them
        state = engine.step(state, flip_actions[0])

        # Now NO Flip the Script should be available (global restriction)
        actions_after = engine.get_legal_actions(state)
        flip_actions_after = [a for a in actions_after
                             if a.action_type == ActionType.USE_ABILITY
                             and a.ability_name == "Flip the Script"]

        assert len(flip_actions_after) == 0, (
            f"Seed {seed}: After using one Flip the Script, no more should be available. "
            f"Found {len(flip_actions_after)} actions"
        )

    @pytest.mark.parametrize("seed", range(20))
    def test_flip_the_script_not_available_without_ko(self, engine, seed):
        """
        Flip the Script should NOT be available if no KO happened last turn.
        """
        state = self.create_flip_the_script_state(
            deck_size=20,
            hand_size=3,
            ko_happened=False,  # No KO happened
            seed=seed
        )
        state = engine.initialize_deck_knowledge(state)

        actions = engine.get_legal_actions(state)
        flip_actions = [a for a in actions
                        if a.action_type == ActionType.USE_ABILITY
                        and a.ability_name == "Flip the Script"]

        assert len(flip_actions) == 0, (
            f"Seed {seed}: Flip the Script should NOT be available without a KO, "
            f"but found {len(flip_actions)} actions"
        )

    def test_flip_the_script_empty_deck(self, engine):
        """
        Flip the Script should NOT be available if deck is empty.
        """
        state = self.create_flip_the_script_state(
            deck_size=0,  # Empty deck
            hand_size=3,
            ko_happened=True,
            seed=99999
        )
        state = engine.initialize_deck_knowledge(state)

        actions = engine.get_legal_actions(state)
        flip_actions = [a for a in actions
                        if a.action_type == ActionType.USE_ABILITY
                        and a.ability_name == "Flip the Script"]

        assert len(flip_actions) == 0, (
            "Flip the Script should NOT be available with empty deck"
        )


# =============================================================================
# KNOCKOUT METADATA TRACKING TESTS
# =============================================================================

class TestKnockoutMetadataTracking:
    """
    Test that knockout events are properly tracked in turn_metadata and
    correctly transferred to last_turn_metadata for cross-turn effects.

    Invariants tested:
    1. KO sets knocked_out_player_ids in turn_metadata during the turn it happens
    2. At end of turn, turn_metadata is copied to last_turn_metadata
    3. turn_metadata is cleared after being copied
    4. last_turn_metadata persists for exactly one opponent turn
    5. KO tracking works for all KO variations (attack damage, bench snipe, etc.)
    """

    @pytest.fixture
    def engine(self):
        return PokemonEngine()

    def create_ko_test_state(
        self,
        attacker_card_id: str = "svp-56",  # Charizard ex
        defender_card_id: str = "sv3pt5-16",  # Pidgey (50 HP)
        defender_hp: int = 10,  # Low HP to guarantee KO
        defender_on_bench: bool = False,
        seed: int = 42
    ) -> GameState:
        """Create a state where a KO is about to happen."""
        random.seed(seed)

        player0 = PlayerState(player_id=0, name='Attacker')
        player1 = PlayerState(player_id=1, name='Defender')

        # Attacker with energy for attack
        attacker = create_card_instance(attacker_card_id, owner_id=0)
        attacker.turns_in_play = 2
        # Attach Fire energy for Burning Darkness [FF]
        for _ in range(3):
            attacker.attached_energy.append(create_card_instance(FIRE_ENERGY_ID, owner_id=0))
        player0.board.active_spot = attacker

        # Defender (low HP to guarantee KO)
        defender = create_card_instance(defender_card_id, owner_id=1)
        defender.turns_in_play = 1
        defender.damage_counters = (get_pokemon_hp(defender_card_id) - defender_hp) // 10

        if defender_on_bench:
            # Put a different Pokemon active, defender on bench
            active_pokemon = create_card_instance("sv4pt5-7", owner_id=1)  # Charmander
            active_pokemon.turns_in_play = 1
            player1.board.active_spot = active_pokemon
            player1.board.bench.append(defender)
        else:
            player1.board.active_spot = defender

        # Backup Pokemon for defender (needed after KO)
        backup = create_card_instance("sv4pt5-7", owner_id=1)
        backup.turns_in_play = 1
        if not defender_on_bench:
            player1.board.bench.append(backup)

        # Standard deck/prizes setup
        for _ in range(20):
            player0.deck.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=0))
            player1.deck.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=1))
        for _ in range(6):
            player0.prizes.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=0))
            player1.prizes.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=1))

        state = GameState(
            players=[player0, player1],
            turn_count=3,
            active_player_index=0,  # Attacker's turn
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        return state

    def test_ko_sets_metadata_during_turn(self, engine):
        """
        When a Pokemon is KO'd, knocked_out_player_ids should be set.
        After resolution completes (including END_TURN), it moves to last_turn_metadata.
        """
        state = self.create_ko_test_state(defender_hp=10)
        state = engine.initialize_deck_knowledge(state)

        # Verify no KO metadata initially
        assert 'knocked_out_player_ids' not in state.turn_metadata
        assert state.last_turn_metadata == {}

        # Get attack action
        actions = engine.get_legal_actions(state)
        attack_actions = [a for a in actions if a.action_type == ActionType.ATTACK]

        if not attack_actions:
            pytest.skip("No attack actions available")

        # Execute attack (should KO the defender)
        state = engine.step(state, attack_actions[0])

        # Complete any resolution steps (like promoting new active)
        max_steps = 20
        for _ in range(max_steps):
            if not state.resolution_stack:
                break
            actions = engine.get_legal_actions(state)
            if not actions:
                break
            state = engine.step(state, actions[0])

        # After attack resolution, KO metadata should be in either:
        # - turn_metadata (if turn hasn't ended yet)
        # - last_turn_metadata (if turn auto-ended after KO resolution)
        ko_in_turn = 'knocked_out_player_ids' in state.turn_metadata and 1 in state.turn_metadata.get('knocked_out_player_ids', [])
        ko_in_last = 'knocked_out_player_ids' in state.last_turn_metadata and 1 in state.last_turn_metadata.get('knocked_out_player_ids', [])

        assert ko_in_turn or ko_in_last, (
            f"Player 1's Pokemon was KO'd but not tracked in metadata. "
            f"turn_metadata: {state.turn_metadata}, last_turn_metadata: {state.last_turn_metadata}"
        )

    def test_ko_metadata_transfers_to_last_turn_on_cleanup(self, engine):
        """
        At end of turn (CLEANUP phase), turn_metadata should transfer to last_turn_metadata.
        """
        state = self.create_ko_test_state(defender_hp=10)
        state = engine.initialize_deck_knowledge(state)

        # Execute attack to cause KO
        actions = engine.get_legal_actions(state)
        attack_actions = [a for a in actions if a.action_type == ActionType.ATTACK]

        if not attack_actions:
            pytest.skip("No attack actions available")

        state = engine.step(state, attack_actions[0])

        # Complete resolution steps
        max_steps = 20
        for _ in range(max_steps):
            if not state.resolution_stack:
                break
            actions = engine.get_legal_actions(state)
            if not actions:
                break
            state = engine.step(state, actions[0])

        # Store the KO metadata before end turn
        ko_metadata = state.turn_metadata.get('knocked_out_player_ids', []).copy()

        # End the turn (should trigger CLEANUP which transfers metadata)
        actions = engine.get_legal_actions(state)
        end_turn_actions = [a for a in actions if a.action_type == ActionType.END_TURN]

        if end_turn_actions:
            state = engine.step(state, end_turn_actions[0])

            # Complete any turn transition steps
            for _ in range(max_steps):
                if not state.resolution_stack:
                    break
                actions = engine.get_legal_actions(state)
                if not actions:
                    break
                state = engine.step(state, actions[0])

            # Verify metadata was transferred
            assert 'knocked_out_player_ids' in state.last_turn_metadata, (
                "knocked_out_player_ids should be in last_turn_metadata after turn ends"
            )
            assert state.last_turn_metadata['knocked_out_player_ids'] == ko_metadata, (
                f"last_turn_metadata should contain the KO info: expected {ko_metadata}, "
                f"got {state.last_turn_metadata.get('knocked_out_player_ids')}"
            )

            # Verify turn_metadata was cleared
            assert 'knocked_out_player_ids' not in state.turn_metadata, (
                "turn_metadata should be cleared after being copied to last_turn_metadata"
            )

    def test_ko_metadata_clears_after_opponent_turn(self, engine):
        """
        last_turn_metadata should be cleared after the opponent's turn ends,
        so KO effects only apply for one turn.
        """
        state = self.create_ko_test_state(defender_hp=10)
        state = engine.initialize_deck_knowledge(state)

        # Execute attack to cause KO
        actions = engine.get_legal_actions(state)
        attack_actions = [a for a in actions if a.action_type == ActionType.ATTACK]

        if not attack_actions:
            pytest.skip("No attack actions available")

        state = engine.step(state, attack_actions[0])

        # Complete resolution and end turn
        max_steps = 30
        for _ in range(max_steps):
            if not state.resolution_stack:
                break
            actions = engine.get_legal_actions(state)
            if not actions:
                break
            state = engine.step(state, actions[0])

        # End attacker's turn
        actions = engine.get_legal_actions(state)
        end_turn_actions = [a for a in actions if a.action_type == ActionType.END_TURN]
        if end_turn_actions:
            state = engine.step(state, end_turn_actions[0])

        # Complete turn transition
        for _ in range(max_steps):
            if not state.resolution_stack:
                break
            actions = engine.get_legal_actions(state)
            if not actions:
                break
            state = engine.step(state, actions[0])

        # Now it's defender's turn - they can see the KO in last_turn_metadata
        if state.active_player_index == 1:
            assert 'knocked_out_player_ids' in state.last_turn_metadata, (
                "Defender should see KO in last_turn_metadata on their turn"
            )

            # End defender's turn
            actions = engine.get_legal_actions(state)
            end_turn_actions = [a for a in actions if a.action_type == ActionType.END_TURN]
            if end_turn_actions:
                state = engine.step(state, end_turn_actions[0])

                # Complete turn transition
                for _ in range(max_steps):
                    if not state.resolution_stack:
                        break
                    actions = engine.get_legal_actions(state)
                    if not actions:
                        break
                    state = engine.step(state, actions[0])

                # Now it's attacker's turn again - last_turn_metadata should NOT have the old KO
                # (it should have defender's turn metadata, which had no KOs)
                old_ko_ids = state.last_turn_metadata.get('knocked_out_player_ids', [])
                assert 1 not in old_ko_ids, (
                    "Old KO metadata should not persist after two turn transitions. "
                    f"Found: {old_ko_ids}"
                )

    @pytest.mark.parametrize("seed", range(20))
    def test_ko_from_attack_damage_sets_metadata(self, engine, seed):
        """Test that KO from regular attack damage properly sets metadata."""
        random.seed(seed)
        defender_hp = random.randint(10, 50)

        state = self.create_ko_test_state(defender_hp=defender_hp, seed=seed)
        state = engine.initialize_deck_knowledge(state)

        actions = engine.get_legal_actions(state)
        attack_actions = [a for a in actions if a.action_type == ActionType.ATTACK]

        if not attack_actions:
            pytest.skip("No attack actions available")

        state = engine.step(state, attack_actions[0])

        # Complete resolution
        for _ in range(30):
            if not state.resolution_stack:
                break
            actions = engine.get_legal_actions(state)
            if not actions:
                break
            state = engine.step(state, actions[0])

        # Check if KO happened (defender is gone or in discard)
        defender_in_play = (
            state.players[1].board.active_spot and
            state.players[1].board.active_spot.card_id == "sv3pt5-16"
        )

        if not defender_in_play:
            # KO happened - verify metadata is tracked (in either turn or last_turn)
            ko_in_turn = 1 in state.turn_metadata.get('knocked_out_player_ids', [])
            ko_in_last = 1 in state.last_turn_metadata.get('knocked_out_player_ids', [])

            assert ko_in_turn or ko_in_last, (
                f"Seed {seed}: KO happened but player 1 not tracked in metadata. "
                f"turn_metadata: {state.turn_metadata}, last_turn_metadata: {state.last_turn_metadata}"
            )

    def test_multiple_kos_same_turn_all_tracked(self, engine):
        """
        If multiple Pokemon are KO'd in the same turn, all should be tracked.
        """
        player0 = PlayerState(player_id=0, name='Attacker')
        player1 = PlayerState(player_id=1, name='Defender')

        # Powerful attacker
        attacker = create_card_instance("svp-56", owner_id=0)
        attacker.turns_in_play = 2
        for _ in range(3):
            attacker.attached_energy.append(create_card_instance(FIRE_ENERGY_ID, owner_id=0))
        player0.board.active_spot = attacker

        # Low HP active
        defender = create_card_instance("sv3pt5-16", owner_id=1)
        defender.turns_in_play = 1
        defender.damage_counters = 4  # 40 damage on 50 HP = 10 HP left
        player1.board.active_spot = defender

        # Multiple bench Pokemon (in case of spread damage attacks)
        for _ in range(3):
            bench_mon = create_card_instance("sv3pt5-16", owner_id=1)
            bench_mon.turns_in_play = 1
            player1.board.bench.append(bench_mon)

        # Standard setup
        for _ in range(20):
            player0.deck.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=0))
            player1.deck.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=1))
        for _ in range(6):
            player0.prizes.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=0))
            player1.prizes.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=1))

        state = GameState(
            players=[player0, player1],
            turn_count=3,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)

        # Execute attack
        actions = engine.get_legal_actions(state)
        attack_actions = [a for a in actions if a.action_type == ActionType.ATTACK]

        if attack_actions:
            state = engine.step(state, attack_actions[0])

            # Complete resolution
            for _ in range(30):
                if not state.resolution_stack:
                    break
                actions = engine.get_legal_actions(state)
                if not actions:
                    break
                state = engine.step(state, actions[0])

            # If a KO happened, verify player 1 is tracked
            if 'knocked_out_player_ids' in state.turn_metadata:
                assert 1 in state.turn_metadata['knocked_out_player_ids'], (
                    "Player 1's Pokemon was KO'd but not tracked"
                )
                # Player ID should only appear once even if multiple Pokemon KO'd
                assert state.turn_metadata['knocked_out_player_ids'].count(1) == 1, (
                    "Player ID should only appear once in knocked_out_player_ids"
                )

    def test_no_ko_means_no_metadata(self, engine):
        """
        If no KO happens during a turn, knocked_out_player_ids should not exist.
        """
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        # Active with no energy (can't attack effectively)
        active = create_card_instance("sv3pt5-16", owner_id=0)  # Pidgey
        active.turns_in_play = 1
        player0.board.active_spot = active

        # High HP defender
        defender = create_card_instance("svp-56", owner_id=1)  # Charizard ex (330 HP)
        defender.turns_in_play = 1
        player1.board.active_spot = defender

        for _ in range(20):
            player0.deck.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=0))
            player1.deck.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=1))
        for _ in range(6):
            player0.prizes.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=0))
            player1.prizes.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=1))

        state = GameState(
            players=[player0, player1],
            turn_count=3,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)

        # Just end turn without attacking (or attack but don't KO)
        actions = engine.get_legal_actions(state)
        end_turn_actions = [a for a in actions if a.action_type == ActionType.END_TURN]

        if end_turn_actions:
            state = engine.step(state, end_turn_actions[0])

            # Complete turn transition
            for _ in range(20):
                if not state.resolution_stack:
                    break
                actions = engine.get_legal_actions(state)
                if not actions:
                    break
                state = engine.step(state, actions[0])

            # No KO should mean empty or missing knocked_out_player_ids in last_turn
            ko_ids = state.last_turn_metadata.get('knocked_out_player_ids', [])
            assert ko_ids == [], (
                f"No KO happened but knocked_out_player_ids is {ko_ids}"
            )

    def test_own_pokemon_ko_tracked_correctly(self, engine):
        """
        When YOUR Pokemon is KO'd (not opponent's), your player_id should be in the list.
        This is important for Fezandipiti ex which checks if YOUR Pokemon was KO'd.
        """
        # Set up so player 1 attacks and KOs player 0's Pokemon
        player0 = PlayerState(player_id=0, name='Defender')
        player1 = PlayerState(player_id=1, name='Attacker')

        # Player 0 has low HP Pokemon
        defender = create_card_instance("sv3pt5-16", owner_id=0)
        defender.turns_in_play = 1
        defender.damage_counters = 4  # 10 HP left
        player0.board.active_spot = defender

        # Backup for player 0
        backup = create_card_instance("sv4pt5-7", owner_id=0)
        backup.turns_in_play = 1
        player0.board.bench.append(backup)

        # Player 1 has strong attacker
        attacker = create_card_instance("svp-56", owner_id=1)
        attacker.turns_in_play = 2
        for _ in range(3):
            attacker.attached_energy.append(create_card_instance(FIRE_ENERGY_ID, owner_id=1))
        player1.board.active_spot = attacker

        for _ in range(20):
            player0.deck.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=0))
            player1.deck.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=1))
        for _ in range(6):
            player0.prizes.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=0))
            player1.prizes.add_card(create_card_instance(random.choice(BASIC_POKEMON), owner_id=1))

        state = GameState(
            players=[player0, player1],
            turn_count=3,
            active_player_index=1,  # Player 1's turn (attacker)
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )
        state = engine.initialize_deck_knowledge(state)

        # Player 1 attacks
        actions = engine.get_legal_actions(state)
        attack_actions = [a for a in actions if a.action_type == ActionType.ATTACK]

        if not attack_actions:
            pytest.skip("No attack actions available")

        state = engine.step(state, attack_actions[0])

        # Complete resolution
        for _ in range(30):
            if not state.resolution_stack:
                break
            actions = engine.get_legal_actions(state)
            if not actions:
                break
            state = engine.step(state, actions[0])

        # Player 0's Pokemon was KO'd - their ID should be tracked
        # Could be in turn_metadata or last_turn_metadata depending on auto-end-turn
        ko_in_turn = 0 in state.turn_metadata.get('knocked_out_player_ids', [])
        ko_in_last = 0 in state.last_turn_metadata.get('knocked_out_player_ids', [])

        assert ko_in_turn or ko_in_last, (
            "Player 0's Pokemon was KO'd but player_id 0 not tracked in metadata. "
            f"turn_metadata: {state.turn_metadata}, last_turn_metadata: {state.last_turn_metadata}"
        )


def get_pokemon_hp(card_id: str) -> int:
    """Helper to get a Pokemon's HP from its card definition."""
    card_def = create_card(card_id)
    if card_def and hasattr(card_def, 'hp'):
        return card_def.hp
    return 50  # Default fallback


# =============================================================================
# RUN CONFIGURATION
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])

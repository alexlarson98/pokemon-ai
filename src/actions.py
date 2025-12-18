"""
Pokémon TCG Engine - Action Primitives (actions.py)
Atomic state-modification functions called by engine.py.

These are the "vocabulary" of the game - the fundamental operations
that modify GameState. All functions operate on state immutably where possible.

Constitution Compliance:
- Section 4.2: Damage vs. Damage Counters distinction
- Section 4.7: Strict damage calculation pipeline
- Section 4.1: Search fidelity (Private vs. Public knowledge)
- Section 5: State reset rules
"""

from typing import List, Optional, Callable, Tuple, Set
import random
from copy import deepcopy

from models import (
    GameState,
    PlayerState,
    CardInstance,
    Zone,
    StatusCondition,
    EnergyType,
    Action,
    ActionType,
)


# ============================================================================
# 1. DECK MANIPULATION
# ============================================================================

class DeckOutError(Exception):
    """
    Raised when attempting to draw from an empty deck.
    Engine should catch this and award game loss.
    """
    pass


def draw_card(state: GameState, player_id: int, amount: int = 1) -> GameState:
    """
    Draw cards from deck to hand.

    Constitution Section 2, Phase 1:
    - If deck is empty before drawing, raise DeckOutError.

    Args:
        state: Current game state
        player_id: Player drawing cards (0 or 1)
        amount: Number of cards to draw

    Returns:
        Modified GameState

    Raises:
        DeckOutError: If deck has insufficient cards
    """
    player = state.get_player(player_id)

    for _ in range(amount):
        if player.deck.is_empty():
            raise DeckOutError(f"Player {player_id} cannot draw - deck is empty")

        # Move top card from deck to hand
        card = player.deck.cards.pop(0)
        player.hand.add_card(card)

    return state


def shuffle_deck(state: GameState, player_id: int, seed: Optional[int] = None) -> GameState:
    """
    Shuffle player's deck.

    Args:
        state: Current game state
        player_id: Player whose deck to shuffle
        seed: Optional RNG seed for deterministic shuffling

    Returns:
        Modified GameState
    """
    player = state.get_player(player_id)

    # Use seed if provided (for MCTS determinism)
    if seed is not None:
        random.seed(seed)

    random.shuffle(player.deck.cards)

    return state


def search_deck(
    state: GameState,
    player_id: int,
    filter_func: Callable[[CardInstance], bool],
    allow_fail: bool = True,
    reveal: bool = False,
    max_results: int = 1
) -> Tuple[GameState, List[CardInstance]]:
    """
    Search deck for cards matching criteria.

    Constitution Section 4.1: Search Fidelity
    - Restricted Search (allow_fail=True): Player may choose to "fail"
    - Unrestricted Search (allow_fail=False): Must find card if deck not empty

    Args:
        state: Current game state
        player_id: Player searching their deck
        filter_func: Function to test if card matches criteria
        allow_fail: Whether player can choose to find nothing
        reveal: Whether found cards are revealed to opponent
        max_results: Maximum number of cards to find

    Returns:
        (Modified GameState, List of found cards)
    """
    player = state.get_player(player_id)

    # Find all matching cards
    matching_cards = [card for card in player.deck.cards if filter_func(card)]

    found_cards = []

    if allow_fail:
        # Player may choose to fail even if cards exist (private knowledge)
        # For AI simulation, randomly choose whether to fail (50% chance)
        # In real game, this would be a player choice
        if matching_cards and random.choice([True, False]):
            # Choose to find cards
            found_cards = matching_cards[:max_results]
    else:
        # Must find cards if any exist (unrestricted search)
        if matching_cards:
            found_cards = matching_cards[:max_results]
        elif not player.deck.is_empty():
            # Deck not empty but no matching cards - this is a game rule violation
            # Should not happen in well-formed card effects
            pass

    # Remove found cards from deck and add to hand
    for card in found_cards:
        player.deck.remove_card(card.id)
        player.hand.add_card(card)

        if reveal:
            card.is_revealed = True

    # Shuffle deck after search (standard TCG rule)
    state = shuffle_deck(state, player_id)

    return state, found_cards


def reveal_cards(
    state: GameState,
    player_id: int,
    card_ids: List[str]
) -> GameState:
    """
    Reveal specific cards to opponent.

    Args:
        state: Current game state
        player_id: Player revealing cards
        card_ids: List of card instance IDs to reveal

    Returns:
        Modified GameState
    """
    player = state.get_player(player_id)

    # Mark cards as revealed (can be in any zone)
    for zone in [player.hand, player.deck, player.discard]:
        for card in zone.cards:
            if card.id in card_ids:
                card.is_revealed = True

    return state


# ============================================================================
# 2. DAMAGE CALCULATION (Constitution Section 4.7)
# ============================================================================

def calculate_damage(
    state: GameState,
    attacker: CardInstance,
    defender: CardInstance,
    base_damage: int,
    attack_name: str = ""
) -> int:
    """
    Calculate final damage using strict Constitution pipeline.

    Constitution Section 4.7: Damage Order of Operations (STRICT)
    1. Base Damage (from card value)
    2. Weakness (×2 if types match)
    3. Resistance (-30 if types match)
    4. Effects on Attacker (e.g., "Do 30 more damage")
    5. Effects on Defender (e.g., "Take 30 less damage")

    Args:
        state: Current game state
        attacker: Attacking Pokémon
        defender: Defending Pokémon
        base_damage: Base damage value from attack
        attack_name: Name of attack being used

    Returns:
        Final damage amount (integer, ≥ 0)
    """
    damage = base_damage

    # STEP 1: Base Damage (already provided)

    # STEP 2: Weakness (×2 if types match)
    # TODO: Get weakness/resistance from card definitions
    # For now, mock implementation
    weakness_type = _get_weakness_type(defender)
    attacker_type = _get_primary_type(attacker)

    if weakness_type and attacker_type == weakness_type:
        damage *= 2

    # STEP 3: Resistance (-30 if types match)
    resistance_type = _get_resistance_type(defender)

    if resistance_type and attacker_type == resistance_type:
        damage = max(0, damage - 30)

    # STEP 4: Effects on Attacker (e.g., "Do 30 more damage")
    attacker_modifiers = _get_damage_modifiers_attacker(state, attacker, attack_name)
    damage += attacker_modifiers

    # STEP 5: Effects on Defender (e.g., "Take 30 less damage")
    defender_modifiers = _get_damage_modifiers_defender(state, defender)
    damage += defender_modifiers  # Note: defender modifiers are typically negative

    # Ensure damage is non-negative
    damage = max(0, damage)

    return damage


def apply_damage(
    state: GameState,
    target: CardInstance,
    damage: int,
    is_attack_damage: bool = True,
    attacker: CardInstance = None
) -> GameState:
    """
    Apply damage to a Pokémon.

    Constitution Section 4.2: Damage vs. Damage Counters
    - Attack Damage: Affected by Weakness, Resistance, "Prevent Damage"
    - This function applies DAMAGE (not damage counters directly)

    Args:
        state: Current game state
        target: Pokémon receiving damage
        damage: Amount of damage to apply
        is_attack_damage: Whether this is from an attack (for prevention effects)
        attacker: Attacking Pokémon (for conditional prevention like Crown Opal)

    Returns:
        Modified GameState
    """
    if damage <= 0:
        return state

    # Check for "Prevent Damage" effects
    if is_attack_damage and _has_damage_prevention(state, target, attacker):
        # Damage is prevented
        return state

    # Convert damage to damage counters (10 damage = 1 counter)
    damage_counters = damage // 10

    # Apply damage counters
    target.damage_counters += damage_counters

    return state


def place_damage_counters(
    state: GameState,
    target: CardInstance,
    amount: int
) -> GameState:
    """
    Place damage counters directly on a Pokémon.

    Constitution Section 4.2: Damage Counters
    - NOT affected by Weakness, Resistance, or "Prevent Damage"
    - Only blocked by "Prevent Effects of Attacks"

    Args:
        state: Current game state
        target: Pokémon receiving damage counters
        amount: Number of damage counters to place

    Returns:
        Modified GameState
    """
    if amount <= 0:
        return state

    # Check for "Prevent Effects" (not "Prevent Damage")
    if _has_effect_prevention(target):
        return state

    # Place damage counters directly (bypass weakness/resistance)
    target.damage_counters += amount

    return state


def heal_damage(
    state: GameState,
    target: CardInstance,
    amount: int
) -> GameState:
    """
    Remove damage counters from a Pokémon.

    Args:
        state: Current game state
        target: Pokémon being healed
        amount: Amount of HP to heal

    Returns:
        Modified GameState
    """
    if amount <= 0:
        return state

    # Convert HP to damage counters
    counters_to_remove = amount // 10

    # Remove counters (cannot go below 0)
    target.damage_counters = max(0, target.damage_counters - counters_to_remove)

    return state


# ============================================================================
# 3. STATUS CONDITIONS (Constitution Section 5)
# ============================================================================

def apply_status_condition(
    state: GameState,
    target: CardInstance,
    condition: StatusCondition
) -> GameState:
    """
    Apply a status condition to a Pokémon.

    Rules:
    - A Pokémon can have multiple status conditions
    - Poison and Burn stack
    - Sleep, Paralysis, Confusion are mutually exclusive (replacing previous)
    - Guards can block specific status conditions (e.g., Insomnia blocks Asleep)

    Args:
        state: Current game state
        target: Pokémon receiving status condition
        condition: Status condition to apply

    Returns:
        Modified GameState (unchanged if guard blocks)
    """
    # Check if the target has a guard that blocks this status condition
    from cards.logic_registry import get_card_guard

    guard = get_card_guard(target.card_id, "status_condition")
    if guard:
        # Guard returns True if the condition should be blocked
        if guard(state, target, condition):
            # Status condition is blocked - return state unchanged
            return state

    # Special case: Asleep, Paralyzed, Confused are mutually exclusive
    exclusive_conditions = {
        StatusCondition.ASLEEP,
        StatusCondition.PARALYZED,
        StatusCondition.CONFUSED
    }

    if condition in exclusive_conditions:
        # Remove other exclusive conditions
        target.status_conditions -= exclusive_conditions

    # Add new condition
    target.status_conditions.add(condition)

    return state


def remove_status_condition(
    state: GameState,
    target: CardInstance,
    condition: StatusCondition
) -> GameState:
    """
    Remove a specific status condition from a Pokémon.

    Args:
        state: Current game state
        target: Pokémon to cure
        condition: Status condition to remove

    Returns:
        Modified GameState
    """
    target.status_conditions.discard(condition)
    return state


def clear_all_status_conditions(
    state: GameState,
    target: CardInstance
) -> GameState:
    """
    Remove all status conditions from a Pokémon.

    Used when Pokémon moves to bench (Constitution Section 5).

    Args:
        state: Current game state
        target: Pokémon to cure

    Returns:
        Modified GameState
    """
    target.status_conditions.clear()
    return state


# ============================================================================
# 3.5 PERMISSION CHECKS (4 Pillars: Global Guards)
# ============================================================================

def check_can_play_item(
    state: GameState,
    item_card: CardInstance,
    player: PlayerState
) -> bool:
    """
    Check if an Item card can be played.

    This checks for GLOBAL guards that block Item cards (e.g., Item Lock effects).
    Examples: Vileplume's "Allergy Panic", Seismitoad-EX's "Quaking Punch"

    Args:
        state: Current game state
        item_card: The Item card attempting to be played
        player: The player attempting to play the Item

    Returns:
        True if the Item can be played, False if blocked

    Example:
        >>> if not check_can_play_item(state, rare_candy, player):
        >>>     return []  # Item play is blocked, no actions available
    """
    from cards.logic_registry import check_global_block

    # Check for global Item lock effects
    context = {
        "item_card": item_card,
        "player": player,
        "player_id": player.player_id
    }

    # If any card on the board blocks Item play, return False
    if check_global_block(state, "global_play_item", context):
        return False

    return True


def check_can_play_supporter(
    state: GameState,
    supporter_card: CardInstance,
    player: PlayerState
) -> bool:
    """
    Check if a Supporter card can be played.

    This checks for GLOBAL guards that block Supporter cards.
    Examples: Some attack effects prevent Supporter use next turn.

    Args:
        state: Current game state
        supporter_card: The Supporter card attempting to be played
        player: The player attempting to play the Supporter

    Returns:
        True if the Supporter can be played, False if blocked
    """
    from cards.logic_registry import check_global_block

    # Check for global Supporter lock effects
    context = {
        "supporter_card": supporter_card,
        "player": player,
        "player_id": player.player_id
    }

    if check_global_block(state, "global_play_supporter", context):
        return False

    return True


def check_can_use_ability(
    state: GameState,
    pokemon: CardInstance,
    ability_name: str,
    player: PlayerState
) -> bool:
    """
    Check if an Ability can be used.

    This checks for GLOBAL guards that block Abilities.
    Examples: Path to the Peak (blocks Rule Box abilities), Klefki lock

    Args:
        state: Current game state
        pokemon: The Pokémon with the Ability
        ability_name: Name of the Ability being used
        player: The player attempting to use the Ability

    Returns:
        True if the Ability can be used, False if blocked
    """
    from cards.logic_registry import check_global_block

    # Check for global Ability lock effects
    context = {
        "pokemon": pokemon,
        "ability_name": ability_name,
        "player": player,
        "player_id": player.player_id
    }

    if check_global_block(state, "global_ability", context):
        return False

    return True


# ============================================================================
# 4. ENERGY MANIPULATION
# ============================================================================

def attach_energy(
    state: GameState,
    energy_card: CardInstance,
    target: CardInstance
) -> GameState:
    """
    Attach an Energy card to a Pokémon.

    Args:
        state: Current game state
        energy_card: Energy card to attach
        target: Pokémon receiving energy

    Returns:
        Modified GameState
    """
    target.attached_energy.append(energy_card)
    return state


def detach_energy(
    state: GameState,
    target: CardInstance,
    amount: int = 1,
    energy_type: Optional[EnergyType] = None
) -> Tuple[GameState, List[CardInstance]]:
    """
    Remove Energy cards from a Pokémon.

    Args:
        state: Current game state
        target: Pokémon losing energy
        amount: Number of energy cards to remove
        energy_type: Specific type to remove (None = any)

    Returns:
        (Modified GameState, List of detached energy cards)
    """
    detached = []

    # Filter energy by type if specified
    available_energy = target.attached_energy
    if energy_type:
        # TODO: Filter by energy type (requires card definitions)
        pass

    # Remove up to 'amount' energy cards
    for _ in range(min(amount, len(available_energy))):
        if available_energy:
            energy = available_energy.pop(0)
            detached.append(energy)

    return state, detached


def count_energy(
    target: CardInstance,
    energy_type: Optional[EnergyType] = None
) -> int:
    """
    Count energy attached to a Pokémon.

    Args:
        target: Pokémon to count energy on
        energy_type: Specific type to count (None = all)

    Returns:
        Number of energy cards
    """
    if energy_type is None:
        return len(target.attached_energy)

    # TODO: Count specific energy type (requires card definitions)
    return len(target.attached_energy)


# ============================================================================
# 5. ZONE TRANSFERS (Constitution Section 5)
# ============================================================================

def move_card(
    state: GameState,
    card: CardInstance,
    from_zone: Zone,
    to_zone: Zone,
    position: Optional[int] = None
) -> GameState:
    """
    Move a card between zones.

    Constitution Section 5: State Reset Rules
    - Moving from Play to Hand/Deck wipes ALL state
    - Moving from Active to Bench clears status/effects but keeps damage

    Args:
        state: Current game state
        card: Card to move
        from_zone: Source zone
        to_zone: Destination zone
        position: Position in destination zone (None = end)

    Returns:
        Modified GameState
    """
    # Remove from source zone
    from_zone.remove_card(card.id)

    # Check if moving from play to hand/deck (full state wipe)
    if _is_play_zone(from_zone) and _is_hand_or_deck_zone(to_zone):
        card = reset_card_fully(card)

    # Add to destination zone
    to_zone.add_card(card, position)

    return state


def reset_pokemon_on_bench(card: CardInstance) -> CardInstance:
    """
    Reset Pokémon state when moving from Active to Bench.

    Constitution Section 5: "Switch" Effect
    - REMOVED: Status Conditions
    - REMOVED: Attack Effects
    - PERSIST: Damage/Counters
    - PERSIST: Tools/Energy
    - PERSIST: Evolution chain

    Args:
        card: Pokémon moving to bench

    Returns:
        Modified CardInstance
    """
    # Clear status conditions
    card.status_conditions.clear()

    # Clear attack effects
    card.attack_effects.clear()

    # Damage, energy, tools, evolution chain all persist
    # (no changes needed)

    return card


def reset_card_fully(card: CardInstance) -> CardInstance:
    """
    Full state wipe when card moves from Play to Hand/Deck.

    Constitution Section 5:
    - ALL state is wiped
    - Becomes a "New Object" if played again

    Args:
        card: Card being moved

    Returns:
        New CardInstance with fresh state
    """
    # Create new instance with only identity preserved
    new_card = CardInstance(
        id=card.id,
        card_id=card.card_id,
        owner_id=card.owner_id,
        current_hp=None,
        damage_counters=0,
        status_conditions=set(),
        attached_energy=[],
        attached_tools=[],
        evolution_chain=[],
        turns_in_play=0,
        abilities_used_this_turn=set(),
        attack_effects=[],
        is_revealed=False
    )

    return new_card


# ============================================================================
# 6. KNOCKOUT HANDLING
# ============================================================================

def check_knockout(
    state: GameState,
    pokemon: CardInstance,
    max_hp: int
) -> bool:
    """
    Check if a Pokémon is knocked out.

    Args:
        state: Current game state
        pokemon: Pokémon to check
        max_hp: Maximum HP of the Pokémon

    Returns:
        True if knocked out, False otherwise
    """
    return pokemon.get_total_hp_loss() >= max_hp


def process_knockout(
    state: GameState,
    knocked_out: CardInstance,
    attacker_player_id: int
) -> GameState:
    """
    Process a Pokémon knockout.

    Steps (Constitution Section 2, Phase 3):
    1. Move KO'd Pokémon (and attached cards) to discard
    2. Attacker takes a prize card
    3. Owner must promote new Active (if bench exists)

    Args:
        state: Current game state
        knocked_out: Pokémon that was KO'd
        attacker_player_id: Player who gets the prize

    Returns:
        Modified GameState
    """
    owner = state.get_player(knocked_out.owner_id)
    attacker = state.get_player(attacker_player_id)

    # Step 1: Move Pokémon and attached cards to discard
    owner.discard.add_card(knocked_out)

    for energy in knocked_out.attached_energy:
        owner.discard.add_card(energy)

    for tool in knocked_out.attached_tools:
        owner.discard.add_card(tool)

    # Step 2: Attacker takes prize
    if not attacker.prizes.is_empty():
        prize = attacker.prizes.cards.pop(0)
        attacker.hand.add_card(prize)
        attacker.prizes_taken += 1

    # Step 3: Remove from board (promotion handled by engine interrupt)
    if owner.board.active_spot and owner.board.active_spot.id == knocked_out.id:
        owner.board.active_spot = None
    else:
        owner.board.remove_from_bench(knocked_out.id)

    return state


# ============================================================================
# 6. COMPLEX META ACTIONS (High-level compositions)
# ============================================================================

def move_hand_to_deck(
    state: GameState,
    player_id: int,
    bottom: bool = False,
    shuffle: bool = True
) -> GameState:
    """
    Move all cards from hand to deck.

    This is a critical primitive for cards like Iono and Judge that
    manipulate both players' hands.

    Args:
        state: Current game state
        player_id: Player whose hand to move
        bottom: If True, place cards at bottom of deck (ordered)
                If False, shuffle cards into deck
        shuffle: If True, shuffle deck after moving cards (default: True)
                 Only applies when bottom=False

    Returns:
        Modified GameState

    Examples:
        Iono: move_hand_to_deck(state, p_id, bottom=True)
        Judge: move_hand_to_deck(state, p_id, bottom=False, shuffle=True)
    """
    player = state.get_player(player_id)

    # Move all cards from hand to deck
    hand_cards = player.hand.cards.copy()

    if not hand_cards:
        return state  # Nothing to move

    for card in hand_cards:
        player.hand.remove_card(card.id)

        if bottom:
            # Add to bottom of deck (append to end)
            player.deck.cards.append(card)
        else:
            # Add to top/middle of deck
            player.deck.cards.insert(0, card)

    # Shuffle deck if requested
    if shuffle and not bottom:
        state = shuffle_deck(state, player_id)
    elif bottom and shuffle:
        # For bottom placement, shuffle the deck to randomize
        state = shuffle_deck(state, player_id)

    return state


def evolve_pokemon(
    state: GameState,
    player_id: int,
    target_pokemon_id: str,
    evolution_card_id: str,
    skip_stage: bool = False
) -> GameState:
    """
    Evolve a Pokémon by placing an evolution card on top of it.

    This handles all evolution rules including:
    - Evolution sickness (can't evolve turn 1 or turn played)
    - Stage validation (Basic -> Stage 1 -> Stage 2)
    - Property transfer (damage, energy, effects)
    - Rare Candy (skip_stage=True allows Basic -> Stage 2)

    Args:
        state: Current game state
        player_id: Player evolving
        target_pokemon_id: ID of Pokémon to evolve (on board)
        evolution_card_id: ID of evolution card (in hand)
        skip_stage: If True, allow stage skipping (Rare Candy)

    Returns:
        Modified GameState

    Raises:
        ValueError: If evolution is invalid (sickness, wrong stage, etc.)

    Constitution Rules:
    - Cannot evolve on turn 1
    - Cannot evolve a Pokémon that was played this turn
    - Must evolve from correct stage (unless Rare Candy)
    """
    player = state.get_player(player_id)

    # Rule 1: Cannot evolve on turn 1
    if state.turn_count == 1 and state.active_player_index == 0:
        raise ValueError("Cannot evolve on the first turn of the game")

    # Find target Pokémon on board
    target = None
    target_location = None  # 'active' or 'bench'

    if player.board.active_spot and player.board.active_spot.id == target_pokemon_id:
        target = player.board.active_spot
        target_location = 'active'
    else:
        for i, bench_pokemon in enumerate(player.board.bench):
            if bench_pokemon.id == target_pokemon_id:
                target = bench_pokemon
                target_location = ('bench', i)
                break

    if not target:
        raise ValueError(f"Target Pokémon {target_pokemon_id} not found on board")

    # Rule 2: Evolution sickness - cannot evolve Pokémon played this turn
    if target.turns_in_play == 0:
        raise ValueError(f"Cannot evolve Pokémon that was played this turn (evolution sickness)")

    # Remove evolution card from hand
    evolution_card = player.hand.remove_card(evolution_card_id)
    if not evolution_card:
        raise ValueError(f"Evolution card {evolution_card_id} not found in hand")

    # Get card definitions for validation
    from cards.factory import get_card_definition
    target_def = get_card_definition(target)
    evolution_def = get_card_definition(evolution_card)

    # Rule 3: Validate evolution chain (unless using Rare Candy)
    if not skip_stage:
        if hasattr(evolution_def, 'evolves_from'):
            if evolution_def.evolves_from != target_def.name:
                # Put evolution card back in hand if invalid
                player.hand.add_card(evolution_card)
                raise ValueError(
                    f"{evolution_def.name} cannot evolve from {target_def.name} "
                    f"(requires {evolution_def.evolves_from})"
                )

    # Transfer all properties from target to evolution
    evolution_card.damage_counters = target.damage_counters
    evolution_card.attached_energy = target.attached_energy.copy()
    evolution_card.attached_tools = target.attached_tools.copy()
    evolution_card.status_conditions = target.status_conditions.copy()
    evolution_card.turns_in_play = target.turns_in_play
    evolution_card.evolved_this_turn = True  # Mark as evolved this turn (blocks further evolution)
    evolution_card.evolution_chain = target.evolution_chain + [target.card_id]
    evolution_card.abilities_used_this_turn = target.abilities_used_this_turn.copy()

    # Store previous stage card(s) underneath the evolved Pokemon
    # This preserves card conservation - the basic/stage1 cards aren't destroyed
    # Clear the target's attached cards first (they're transferred, not kept on the basic)
    target.attached_energy = []
    target.attached_tools = []
    evolution_card.previous_stages = target.previous_stages + [target]

    # Transfer active effects that target this specific Pokémon
    for effect in state.active_effects:
        if effect.target_card_id == target.id:
            effect.target_card_id = evolution_card.id

    # Replace target with evolved Pokémon
    if target_location == 'active':
        player.board.active_spot = evolution_card
    else:
        bench_index = target_location[1]
        player.board.bench[bench_index] = evolution_card

    # 4 Pillars: Trigger "on_evolve" hooks
    # Example: Cards that respond to evolution events
    from cards.logic_registry import get_card_hooks
    for p in state.players:
        # Check active
        if p.board.active_spot:
            hook = get_card_hooks(p.board.active_spot.card_id, "on_evolve")
            if hook:
                hook_context = {
                    "evolved_pokemon": evolution_card,
                    "previous_stage": target,
                    "player_id": player_id,
                    "trigger_card": p.board.active_spot,
                    "trigger_player_id": p.player_id
                }
                hook(state, p.board.active_spot, hook_context)
        # Check bench
        for bench_pokemon in p.board.bench:
            if bench_pokemon:
                hook = get_card_hooks(bench_pokemon.card_id, "on_evolve")
                if hook:
                    hook_context = {
                        "evolved_pokemon": evolution_card,
                        "previous_stage": target,
                        "player_id": player_id,
                        "trigger_card": bench_pokemon,
                        "trigger_player_id": p.player_id
                    }
                    hook(state, bench_pokemon, hook_context)

    return state


class BenchOverflowError(Exception):
    """Raised when bench has more Pokémon than allowed."""
    def __init__(self, current_size: int, max_size: int, player_id: int):
        self.current_size = current_size
        self.max_size = max_size
        self.player_id = player_id
        super().__init__(
            f"Player {player_id} bench overflow: {current_size} Pokémon "
            f"(max {max_size}). Must discard down to {max_size}."
        )


def check_bench_collapse(
    state: GameState,
    player_id: Optional[int] = None,
    max_bench_size: int = 5
) -> GameState:
    """
    Check if any player's bench exceeds the maximum size.

    This is critical for Stadium removal (e.g., Area Zero Underdepths)
    and other effects that modify bench size limits.

    Args:
        state: Current game state
        player_id: If specified, only check this player. Otherwise check both.
        max_bench_size: Maximum allowed bench size (default 5)

    Returns:
        Modified GameState (if valid)

    Raises:
        BenchOverflowError: If bench size exceeds limit, requires player action

    Usage:
        try:
            state = check_bench_collapse(state, max_bench_size=5)
        except BenchOverflowError as e:
            # Trigger player choice: discard e.current_size - e.max_size Pokémon
            pass

    Constitution:
    When a Stadium is removed that increases bench size, players must
    immediately discard Pokémon down to the normal limit.
    """
    players_to_check = [player_id] if player_id is not None else [0, 1]

    for pid in players_to_check:
        player = state.get_player(pid)
        bench_size = len(player.board.bench)

        if bench_size > max_bench_size:
            raise BenchOverflowError(
                current_size=bench_size,
                max_size=max_bench_size,
                player_id=pid
            )

    return state


def enforce_bench_limit(
    state: GameState,
    player_id: int,
    max_size: int = 5
) -> GameState:
    """
    Enforce bench size limit by discarding excess Pokémon.

    This is a helper for automated enforcement (e.g., in tests).
    In a real game, this would trigger a player choice action.

    Args:
        state: Current game state
        player_id: Player whose bench to enforce
        max_size: Maximum bench size (default 5)

    Returns:
        Modified GameState with bench reduced to max_size

    Note:
        This automatically discards from the end of the bench.
        In a real implementation, the player should choose which Pokémon to discard.
    """
    player = state.get_player(player_id)

    while len(player.board.bench) > max_size:
        # Discard last Pokémon on bench
        discarded = player.board.bench.pop()

        # Move attached cards to discard
        for energy in discarded.attached_energy:
            player.discard.add_card(energy)
        for tool in discarded.attached_tools:
            player.discard.add_card(tool)

        # Move Pokémon to discard
        player.discard.add_card(discarded)

    return state


def switch_both_active(
    state: GameState,
    player_bench_idx: int,
    opp_bench_idx: int
) -> GameState:
    """
    Switch active Pokémon for BOTH players simultaneously.

    Required for: Prime Catcher (Ace Spec Item)

    Constitution: Switches both active Pokémon at the same time.
    Critical for cards like Prime Catcher that force symmetric switches.

    Args:
        state: Current game state
        player_bench_idx: Index of bench Pokémon for active player (0-4)
        opp_bench_idx: Index of bench Pokémon for opponent (0-4)

    Returns:
        Modified GameState

    Raises:
        ValueError: If bench indices are invalid
    """
    active_player = state.get_active_player()
    opponent = state.get_opponent()

    # Validate bench indices
    if player_bench_idx < 0 or player_bench_idx >= len(active_player.board.bench):
        raise ValueError(
            f"Invalid player bench index {player_bench_idx}. "
            f"Bench has {len(active_player.board.bench)} Pokémon."
        )

    if opp_bench_idx < 0 or opp_bench_idx >= len(opponent.board.bench):
        raise ValueError(
            f"Invalid opponent bench index {opp_bench_idx}. "
            f"Bench has {len(opponent.board.bench)} Pokémon."
        )

    # Perform both switches atomically
    # 1. Active player switch
    old_active_player = active_player.board.active_spot
    new_active_player = active_player.board.bench.pop(player_bench_idx)
    active_player.board.active_spot = new_active_player

    if old_active_player:
        active_player.board.bench.append(old_active_player)

    # 2. Opponent switch
    old_active_opp = opponent.board.active_spot
    new_active_opp = opponent.board.bench.pop(opp_bench_idx)
    opponent.board.active_spot = new_active_opp

    if old_active_opp:
        opponent.board.bench.append(old_active_opp)

    return state


def force_knockout(
    state: GameState,
    target_id: str
) -> GameState:
    """
    Instantly knock out a Pokémon, triggering KO resolution.

    Required for:
    - Dusknoir (Self-Sacrifice cost - KO self as attack cost)
    - Roaring Moon ex (KO effects)

    Constitution: Forces HP to 0 and triggers prize/discard logic.
    This bypasses damage calculation entirely.

    Args:
        state: Current game state
        target_id: CardInstance ID of Pokémon to KO

    Returns:
        Modified GameState with KO processed

    Note:
        This function sets damage counters to a value that guarantees KO.
        The engine's check_knockout() will handle prize logic.
    """
    from cards.factory import get_max_hp

    # Find target Pokémon (active or bench)
    target = None

    for player_id in [0, 1]:
        player = state.get_player(player_id)

        # Check active
        if player.board.active_spot and player.board.active_spot.id == target_id:
            target = player.board.active_spot
            break

        # Check bench
        for pokemon in player.board.bench:
            if pokemon.id == target_id:
                target = pokemon
                break

        if target:
            break

    if not target:
        raise ValueError(f"Target Pokémon {target_id} not found on board")

    # Force KO by setting damage counters to exceed max HP
    max_hp = get_max_hp(target)
    target.damage_counters = (max_hp // 10) + 1  # Guarantee KO

    return state


# ============================================================================
# 7. EFFECT HELPERS (Placeholder for card-specific logic)
# ============================================================================

def _get_weakness_type(pokemon: CardInstance) -> Optional[EnergyType]:
    """Get Pokémon's weakness type from card definition."""
    from cards.factory import get_card_definition
    card_def = get_card_definition(pokemon)
    if card_def and hasattr(card_def, 'weakness'):
        return card_def.weakness
    return None


def _get_resistance_type(pokemon: CardInstance) -> Optional[EnergyType]:
    """Get Pokémon's resistance type from card definition."""
    from cards.factory import get_card_definition
    card_def = get_card_definition(pokemon)
    if card_def and hasattr(card_def, 'resistance'):
        return card_def.resistance
    return None


def _get_primary_type(pokemon: CardInstance) -> Optional[EnergyType]:
    """Get Pokémon's primary type from card definition."""
    from cards.factory import get_card_definition
    card_def = get_card_definition(pokemon)
    if card_def and hasattr(card_def, 'types') and len(card_def.types) > 0:
        return card_def.types[0]
    return None


def _get_damage_modifiers_attacker(
    state: GameState,
    attacker: CardInstance,
    attack_name: str
) -> int:
    """
    Calculate damage modifiers from attacker effects.

    Examples:
    - "This attack does 30 more damage"
    - Abilities that boost damage
    - Attached Tools that boost damage
    - Double Turbo Energy: "-20 damage"

    Returns:
        Damage modifier (can be positive or negative)
    """
    modifier = 0

    # Check active effects for damage modifiers affecting this attacker
    for effect in state.active_effects:
        # Check if effect applies to this attacker
        if effect.target_card_id and effect.target_card_id != attacker.id:
            continue

        # Check for damage modifiers
        if "damage_modifier" in effect.params:
            modifier += effect.params["damage_modifier"]

        # Check for damage boost
        if "damage_boost" in effect.params:
            modifier += effect.params["damage_boost"]

    return modifier


def _get_damage_modifiers_defender(
    state: GameState,
    defender: CardInstance
) -> int:
    """
    Calculate damage modifiers from defender effects.

    Examples:
    - "This Pokémon takes 30 less damage"
    - Abilities that reduce damage
    - Attached Tools that reduce damage
    - Bravery Charm: Adds HP (doesn't reduce damage directly)

    Returns:
        Damage modifier (typically negative integer)
    """
    modifier = 0

    # Check active effects for damage reduction affecting this defender
    for effect in state.active_effects:
        # Check if effect applies to this defender
        if effect.target_card_id and effect.target_card_id != defender.id:
            continue

        # Check for damage reduction
        if "damage_reduction" in effect.params:
            modifier -= effect.params["damage_reduction"]

        # Check for damage resistance
        if "takes_less_damage" in effect.params:
            modifier -= effect.params["takes_less_damage"]

    return modifier


def _has_damage_prevention(state: GameState, pokemon: CardInstance, attacker: CardInstance = None) -> bool:
    """
    Check if Pokémon has 'Prevent all damage' effect.

    Examples:
    - Cornerstone Mask Ogerpon ex: "Prevent all damage from attacks"
    - Mew ex: "This Pokemon can't be damaged by attacks from your opponent's Pokemon ex"
    - Terapagos ex (Crown Opal): "Prevent damage from Basic Pokemon (except Colorless)"

    Args:
        state: Current game state
        pokemon: Pokemon to check
        attacker: Attacking Pokemon (for conditional prevention like Crown Opal)

    Returns:
        True if damage should be prevented
    """
    # Check active effects for damage immunity
    for effect in state.active_effects:
        # Check if effect applies to this Pokemon
        if effect.target_card_id and effect.target_card_id != pokemon.id:
            continue

        # Check for unconditional damage prevention
        if effect.params.get("prevents") == "all_damage":
            return True

        if effect.params.get("damage_immunity"):
            return True

        # Check for conditional damage prevention (Crown Opal)
        if effect.params.get("damage_prevention") and attacker:
            prevent_source_types = effect.params.get("prevent_source_types", [])
            exception_types = effect.params.get("exception_types", [])

            if prevent_source_types:
                # Get attacker's subtypes
                from cards.registry import create_card
                attacker_card = create_card(attacker.card_id)

                if attacker_card and hasattr(attacker_card, 'subtypes'):
                    attacker_subtypes = attacker_card.subtypes

                    # Check if attacker has a blocked subtype
                    for source_type in prevent_source_types:
                        if source_type in attacker_subtypes:
                            # Check if attacker has an exception type
                            has_exception = False
                            for exception_type in exception_types:
                                if exception_type in attacker_subtypes:
                                    has_exception = True
                                    break

                            if not has_exception:
                                return True  # Prevent damage

    return False


def _has_effect_prevention(pokemon: CardInstance) -> bool:
    """Check if Pokémon has 'Prevent all effects of attacks' effect."""
    # TODO: Check abilities and effects
    return False


def _is_play_zone(zone: Zone) -> bool:
    """Check if zone is a 'play' zone (Active/Bench)."""
    # TODO: Proper zone type checking
    # For now, simple heuristic
    return not zone.is_hidden


def _is_hand_or_deck_zone(zone: Zone) -> bool:
    """Check if zone is Hand or Deck."""
    # TODO: Proper zone type checking
    return zone.is_private or zone.is_hidden


# ============================================================================
# 8. COIN FLIP & RNG
# ============================================================================

def coin_flip(seed: Optional[int] = None) -> bool:
    """
    Flip a coin.

    Args:
        seed: Optional RNG seed for determinism

    Returns:
        True for Heads, False for Tails
    """
    if seed is not None:
        random.seed(seed)

    return random.choice([True, False])


def coin_flip_multiple(count: int, seed: Optional[int] = None) -> List[bool]:
    """
    Flip multiple coins.

    Args:
        count: Number of coins to flip
        seed: Optional RNG seed for determinism

    Returns:
        List of coin flip results (True = Heads, False = Tails)
    """
    if seed is not None:
        random.seed(seed)

    return [random.choice([True, False]) for _ in range(count)]


# ============================================================================
# 9. UTILITY FUNCTIONS
# ============================================================================

def count_pokemon_in_play(state: GameState, player_id: int) -> int:
    """
    Count total Pokémon in play for a player.

    Args:
        state: Current game state
        player_id: Player to count for

    Returns:
        Total number of Pokémon (Active + Bench)
    """
    player = state.get_player(player_id)
    count = 0

    if player.board.active_spot:
        count += 1

    count += player.board.get_bench_count()

    return count


def get_all_pokemon_in_play(state: GameState) -> List[CardInstance]:
    """
    Get all Pokémon in play from both players.

    Args:
        state: Current game state

    Returns:
        List of all Pokémon CardInstances
    """
    all_pokemon = []

    for player in state.players:
        all_pokemon.extend(player.board.get_all_pokemon())

    return all_pokemon


def validate_energy_cost(
    pokemon: CardInstance,
    required_energy: List[EnergyType]
) -> bool:
    """
    Check if Pokémon has sufficient energy to pay attack cost.

    Args:
        pokemon: Pokémon attempting to attack
        required_energy: List of required energy types

    Returns:
        True if cost can be paid, False otherwise
    """
    # TODO: Implement energy type matching with Colorless wildcards
    # For now, simple count check
    return len(pokemon.attached_energy) >= len(required_energy)


def get_all_attached_energy(
    state: GameState,
    player_id: int,
    energy_type: Optional[EnergyType] = None
) -> List[CardInstance]:
    """
    Get all energy attached to a player's Pokemon (Active + Bench).

    Required for attacks like Chien-Pao ex's "Hail Blade" that can discard
    energy from ANY of the player's Pokemon.

    Args:
        state: Current game state
        player_id: Player whose energy to count
        energy_type: Specific energy type to filter (None = all energy)

    Returns:
        List of all energy CardInstances matching the criteria

    Example:
        >>> # Get all Water Energy attached to player's Pokemon
        >>> water_energy = get_all_attached_energy(state, 0, EnergyType.WATER)
        >>> len(water_energy)  # Total Water Energy count
    """
    from cards.factory import get_card_definition
    player = state.get_player(player_id)
    all_energy = []

    # Get all Pokemon (active + bench)
    all_pokemon = player.board.get_all_pokemon()

    # Collect energy from all Pokemon
    for pokemon in all_pokemon:
        for energy_card in pokemon.attached_energy:
            # If filtering by type, check the energy type
            if energy_type is not None:
                energy_def = get_card_definition(energy_card)
                # Check if energy provides the requested type
                if hasattr(energy_def, 'provides') and energy_type in energy_def.provides:
                    all_energy.append(energy_card)
                # For basic energy, check the card name
                elif hasattr(energy_def, 'name') and energy_type.value in energy_def.name:
                    all_energy.append(energy_card)
            else:
                # No filter - add all energy
                all_energy.append(energy_card)

    return all_energy

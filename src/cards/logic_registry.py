"""
Pokémon TCG Engine - Card Logic Registry (Pure Router)

This module serves as a pure routing layer for card-specific logic.
All implementation functions are stored in set-based modules under cards/sets/.

================================================================================
UNIFIED ABILITY SCHEMA
================================================================================

Every attack and ability is registered under its EXACT NAME with a 'category' field:

Categories:
- "attack": Deals damage, has energy cost, generates actions
- "activatable": Player-triggered ability, generates actions
- "modifier": Continuously modifies values (retreat cost, damage, HP)
- "guard": Blocks effects/conditions (status, damage, trainer cards)
- "hook": Event-triggered (on_play, on_knockout, etc.)

Example:
    "sv8pt5-77": {
        "Tackle": {
            "category": "attack",
            "generator": hoothoot_tackle_actions,
            "effect": hoothoot_tackle_effect,
        },
        "Insomnia": {
            "category": "guard",
            "guard_type": "status_condition",
            "scope": "self",
            "effect": hoothoot_insomnia_guard,
        },
    }

Multi-Effect Abilities:
When an ability has multiple effects, use suffixed entries:
    "me2-41": {
        "Diamond Coat (Damage Reduction)": {
            "category": "modifier",
            "modifier_type": "damage_taken",
            "scope": "self",
            "effect": damage_modifier_fn,
        },
        "Diamond Coat (Status Immunity)": {
            "category": "guard",
            "guard_type": "status_condition",
            "scope": "self",
            "effect": status_guard_fn,
        },
    }

================================================================================
QUERY FUNCTIONS
================================================================================

Primary:
    get_ability_info(card_id, ability_name) -> dict with category and all fields
    get_all_effects_for_ability(card_id, ability_name) -> list for multi-effect

Helpers:
    get_card_logic(card_id, logic_type) -> generator/effect function
    get_card_modifier(card_id, modifier_type) -> modifier function
    get_card_guard(card_id, guard_type) -> guard function
    get_card_hooks(card_id, hook_type) -> hook function

Board Scanning:
    scan_global_modifiers(state, modifier_type) -> list of (card, fn) tuples
    scan_global_guards(state, guard_type, context) -> list of (card, fn, blocking) tuples
    check_global_block(state, guard_type, context) -> bool
"""

from typing import Optional, Callable, Dict, List, Any

# Import all set logic dictionaries
from cards.sets import (
    SV1_LOGIC,
    SV2_LOGIC,
    SV3_LOGIC,
    SV3PT5_LOGIC,
    SV4_LOGIC,
    SV4PT5_LOGIC,
    SV5_LOGIC,
    SV6_LOGIC,
    SV6PT5_LOGIC,
    SV7_LOGIC,
    SV8_LOGIC,
    SV8PT5_LOGIC,
    SV10_LOGIC,
    ME1_LOGIC,
    ME2_LOGIC,
    SVP_LOGIC,
)


# ============================================================================
# MASTER LOGIC REGISTRY
# ============================================================================

MASTER_LOGIC_REGISTRY: Dict[str, Callable] = {}

# Merge all set dictionaries into the master registry
for set_logic in [
    SV1_LOGIC,
    SV2_LOGIC,
    SV3_LOGIC,
    SV3PT5_LOGIC,
    SV4_LOGIC,
    SV4PT5_LOGIC,
    SV5_LOGIC,
    SV6_LOGIC,
    SV6PT5_LOGIC,
    SV7_LOGIC,
    SV8_LOGIC,
    SV8PT5_LOGIC,
    SV10_LOGIC,
    ME1_LOGIC,
    ME2_LOGIC,
    SVP_LOGIC,
]:
    MASTER_LOGIC_REGISTRY.update(set_logic)


# ============================================================================
# UNIFIED SCHEMA QUERY FUNCTIONS (New - Recommended)
# ============================================================================

def get_ability_info(card_id: str, ability_name: str) -> Optional[Dict[str, Any]]:
    """
    Get complete ability/attack information including category.

    This is the primary function for the unified schema. It returns the full
    dict entry for an ability, including 'category' and all relevant fields.

    Handles suffixed entries for multi-effect abilities:
    - First tries exact match: "Diamond Coat"
    - Then tries suffixed: "Diamond Coat (Modifier)", "Diamond Coat (Guard)"

    Args:
        card_id: The card's ID (e.g., "sv8pt5-77")
        ability_name: The ability/attack name (e.g., "Insomnia", "Tackle")

    Returns:
        Dict with 'category' and all relevant fields, or None if not found.

    Example:
        >>> info = get_ability_info("sv8pt5-77", "Insomnia")
        >>> if info and info.get('category') == 'guard':
        >>>     guard_fn = info['effect']
        >>>     blocked = guard_fn(state, card, condition)
    """
    card_data = MASTER_LOGIC_REGISTRY.get(card_id)
    if not isinstance(card_data, dict):
        return None

    # Exact match first
    if ability_name in card_data:
        entry = card_data[ability_name]
        if isinstance(entry, dict):
            # New schema: has 'category' field
            if 'category' in entry:
                return entry
            # Legacy schema: has 'generator'/'effect' but no category
            # Infer category as 'attack' or 'activatable'
            if 'generator' in entry or 'effect' in entry:
                # Return with inferred category for backwards compat
                return {**entry, 'category': 'attack'}  # or 'activatable'

    # Try common suffixes for multi-effect abilities
    suffixes = [
        '(Modifier)', '(Guard)', '(Hook)',
        '(Damage Reduction)', '(Status Immunity)', '(Damage Modifier)',
    ]
    for suffix in suffixes:
        key = f"{ability_name} {suffix}"
        if key in card_data:
            entry = card_data[key]
            if isinstance(entry, dict) and 'category' in entry:
                return entry

    return None


def get_all_effects_for_ability(card_id: str, ability_name: str) -> List[Dict[str, Any]]:
    """
    Get ALL effects registered for an ability (handles multi-effect abilities).

    For abilities that have multiple effects (e.g., both a modifier AND a guard),
    this returns all matching entries.

    Args:
        card_id: The card's ID
        ability_name: Base ability name (without suffixes)

    Returns:
        List of effect dicts, each with 'category' and relevant fields.
        Empty list if no effects found.

    Example:
        >>> # Diamond Coat has both damage reduction and status immunity
        >>> effects = get_all_effects_for_ability("me2-41", "Diamond Coat")
        >>> for effect in effects:
        >>>     if effect['category'] == 'modifier':
        >>>         # Handle modifier
        >>>     elif effect['category'] == 'guard':
        >>>         # Handle guard
    """
    card_data = MASTER_LOGIC_REGISTRY.get(card_id)
    if not isinstance(card_data, dict):
        return []

    results = []

    for key, value in card_data.items():
        if not isinstance(value, dict):
            continue

        # Match exact name or suffixed name
        if key == ability_name or key.startswith(f"{ability_name} ("):
            if 'category' in value:
                results.append(value)
            elif 'generator' in value or 'effect' in value:
                # Legacy format - infer category
                results.append({**value, 'category': 'attack'})

    return results


def get_ability_category(card_id: str, ability_name: str) -> Optional[str]:
    """
    Get the category of an ability ('attack', 'activatable', 'modifier', 'guard', 'hook').

    Convenience function that just returns the category string.

    Args:
        card_id: The card's ID
        ability_name: The ability name

    Returns:
        Category string or None if not found.

    Example:
        >>> category = get_ability_category("me2-11", "Agile")
        >>> if category == 'modifier':
        >>>     # This is a passive ability, don't generate actions
    """
    info = get_ability_info(card_id, ability_name)
    if info:
        return info.get('category')
    return None


def is_activatable_ability(card_id: str, ability_name: str) -> bool:
    """
    Check if an ability generates actions (is player-activatable).

    Returns True for 'attack' and 'activatable' categories.
    Returns False for 'modifier', 'guard', 'hook' categories.

    Args:
        card_id: The card's ID
        ability_name: The ability name

    Returns:
        True if ability generates actions, False otherwise.
    """
    category = get_ability_category(card_id, ability_name)
    return category in ('attack', 'activatable')


# ============================================================================
# CARD LOGIC ROUTER
# ============================================================================

def get_card_logic(card_id: str, logic_type: str) -> Optional[Callable]:
    """
    Get the implementation function for a card's logic.

    Args:
        card_id: The card's ID (e.g., "sv3-125" for Charizard ex, "me1-125" for Rare Candy)
        logic_type: Type of logic to retrieve (e.g., "effect", "generator", "Burning Darkness")

    Returns:
        Callable function, nested dict, or None if not found

    Example:
        >>> # Trainer card
        >>> logic_func = get_card_logic("me1-125", "effect")
        >>> generator = get_card_logic("me1-125", "generator")

        >>> # Pokémon card (2-level nested - returns nested dict)
        >>> attack_logic = get_card_logic("sv3-125", "Burning Darkness")
        >>> if isinstance(attack_logic, dict):
        >>>     effect = attack_logic.get("effect")
        >>>     generator = attack_logic.get("generator")
    """
    card_data = MASTER_LOGIC_REGISTRY.get(card_id)
    if isinstance(card_data, dict):
        # When looking up "generator" or "effect" for a Trainer, check activatable entries
        if logic_type in ('generator', 'effect'):
            for key, value in card_data.items():
                if isinstance(value, dict) and value.get('category') == 'activatable':
                    if key.startswith('Play '):
                        return value.get(logic_type)

        # For Pokémon attacks/abilities, return the nested dict
        return card_data.get(logic_type)

    return None


# ============================================================================
# 4 PILLARS HELPER FUNCTIONS
# ============================================================================

def get_card_modifier(card_id: str, modifier_type: str) -> Optional[Callable]:
    """
    Get a modifier function for a card.

    Modifiers continuously modify game values like retreat cost, damage, HP.
    They are checked by the physics engine (actions.py) when calculating values.

    Args:
        card_id: The card's ID (e.g., "me2-11" for Charmander with Agile)
        modifier_type: Type of modifier (e.g., "retreat_cost", "damage", "hp")

    Returns:
        Modifier function or None if not found.
        Function signature: fn(state, card, current_value) -> new_value

    Example:
        >>> # Charmander's Agile: If no Energy attached, retreat cost = 0
        >>> modifier = get_card_modifier("me2-11", "retreat_cost")
        >>> if modifier:
        >>>     new_cost = modifier(state, card, base_retreat_cost)
    """
    card_data = MASTER_LOGIC_REGISTRY.get(card_id)
    if isinstance(card_data, dict):
        for key, value in card_data.items():
            if isinstance(value, dict) and value.get('category') == 'modifier':
                if value.get('modifier_type') == modifier_type:
                    return value.get('effect')
    return None


def get_card_guard(card_id: str, guard_type: str) -> Optional[Callable]:
    """
    Get a guard function for a card.

    Guards block certain effects from applying (status conditions, damage, etc.).
    They are checked by the physics engine before applying effects.

    Args:
        card_id: The card's ID (e.g., "sv8pt5-77" for Hoothoot with Insomnia)
        guard_type: Type of guard (e.g., "status_condition", "damage", "effect")

    Returns:
        Guard function or None if not found.
        Function signature: fn(state, card, effect_context) -> bool (True = blocked)

    Example:
        >>> # Hoothoot's Insomnia: Can't be Asleep
        >>> guard = get_card_guard("sv8pt5-77", "status_condition")
        >>> if guard and guard(state, card, StatusCondition.ASLEEP):
        >>>     # Effect is blocked, don't apply
        >>>     return state
    """
    card_data = MASTER_LOGIC_REGISTRY.get(card_id)
    if isinstance(card_data, dict):
        for key, value in card_data.items():
            if isinstance(value, dict) and value.get('category') == 'guard':
                if value.get('guard_type') == guard_type:
                    return value.get('effect')
    return None


def get_card_hooks(card_id: str, hook_type: str) -> Optional[Callable]:
    """
    Get a hook function for a card.

    Hooks are triggered by specific game events (on_play_pokemon, on_knockout, etc.).
    They are called by the referee (engine.py) after major actions.

    Args:
        card_id: The card's ID (e.g., "sv4pt5-211" for Flamigo with Insta-Flock)
        hook_type: Type of hook (e.g., "on_play_pokemon", "on_knockout", "on_evolve")

    Returns:
        Hook function or None if not found.
        Function signature: fn(state, card, context) -> GameState or List[Action]

    Example:
        >>> # Flamigo's Insta-Flock: When played from hand, search for Flamigo
        >>> hook = get_card_hooks("sv4pt5-211", "on_play_pokemon")
        >>> if hook:
        >>>     triggered_actions = hook(state, card, {"source": "hand"})
    """
    card_data = MASTER_LOGIC_REGISTRY.get(card_id)
    if isinstance(card_data, dict):
        for key, value in card_data.items():
            if isinstance(value, dict) and value.get('category') == 'hook':
                if value.get('trigger') == hook_type:
                    return value.get('effect')
    return None


def get_all_modifiers_for_type(modifier_type: str) -> Dict[str, Callable]:
    """
    Get all modifier functions of a specific type from all registered cards.

    Useful for the physics engine to collect all active modifiers.

    Args:
        modifier_type: Type of modifier (e.g., "retreat_cost", "damage")

    Returns:
        Dictionary mapping card_id -> modifier function
    """
    result = {}
    for card_id, card_data in MASTER_LOGIC_REGISTRY.items():
        if isinstance(card_data, dict):
            for key, value in card_data.items():
                if isinstance(value, dict) and value.get('category') == 'modifier':
                    if value.get('modifier_type') == modifier_type:
                        result[card_id] = value.get('effect')
                        break
    return result


def get_all_guards_for_type(guard_type: str) -> Dict[str, Callable]:
    """
    Get all guard functions of a specific type from all registered cards.

    Useful for the physics engine to check all active guards.

    Args:
        guard_type: Type of guard (e.g., "status_condition", "damage")

    Returns:
        Dictionary mapping card_id -> guard function
    """
    result = {}
    for card_id, card_data in MASTER_LOGIC_REGISTRY.items():
        if isinstance(card_data, dict):
            for key, value in card_data.items():
                if isinstance(value, dict) and value.get('category') == 'guard':
                    if value.get('guard_type') == guard_type:
                        result[card_id] = value.get('effect')
                        break
    return result


def get_all_hooks_for_type(hook_type: str) -> Dict[str, Callable]:
    """
    Get all hook functions of a specific type from all registered cards.

    Useful for the referee to find all cards that respond to an event.

    Args:
        hook_type: Type of hook (e.g., "on_play_pokemon", "on_knockout")

    Returns:
        Dictionary mapping card_id -> hook function
    """
    result = {}
    for card_id, card_data in MASTER_LOGIC_REGISTRY.items():
        if isinstance(card_data, dict):
            for key, value in card_data.items():
                if isinstance(value, dict) and value.get('category') == 'hook':
                    if value.get('trigger') == hook_type:
                        result[card_id] = value.get('effect')
                        break
    return result


# ============================================================================
# GLOBAL EFFECTS - Board Scanning Functions
# ============================================================================

def scan_global_modifiers(state: 'GameState', modifier_type: str) -> List[tuple]:
    """
    Scan the board for cards with GLOBAL modifiers of the specified type.

    Global modifiers affect OTHER cards on the board (not just the card with the ability).
    Examples: Beach Court Stadium (-1 retreat for all Basic Pokémon)

    Args:
        state: Current game state
        modifier_type: Type of global modifier (e.g., "global_retreat_cost", "global_damage")

    Returns:
        List of (card_instance, modifier_function) tuples for all matching cards in play

    Example:
        >>> # Find all cards that modify retreat cost globally
        >>> modifiers = scan_global_modifiers(state, "global_retreat_cost")
        >>> for source_card, modifier_fn in modifiers:
        >>>     current_cost = modifier_fn(state, source_card, target_card, current_cost)
    """
    results = []

    # Scan both players' boards
    for player in state.players:
        # Check active Pokémon
        if player.board.active_spot:
            card = player.board.active_spot
            modifier = get_card_modifier(card.card_id, modifier_type)
            if modifier:
                results.append((card, modifier))

        # Check bench Pokémon
        for bench_card in player.board.bench:
            if bench_card:
                modifier = get_card_modifier(bench_card.card_id, modifier_type)
                if modifier:
                    results.append((bench_card, modifier))

    # Check Stadium card
    if state.stadium:
        modifier = get_card_modifier(state.stadium.card_id, modifier_type)
        if modifier:
            results.append((state.stadium, modifier))

    return results


def scan_global_guards(state: 'GameState', guard_type: str, context: dict = None) -> List[tuple]:
    """
    Scan the board for cards with GLOBAL guards of the specified type.

    Global guards can block effects for OTHER cards on the board.
    Examples: Item Lock (blocks all Item cards), Ability Lock (blocks abilities)

    Args:
        state: Current game state
        guard_type: Type of global guard (e.g., "global_play_item", "global_ability")
        context: Optional context dict with details about the effect being checked

    Returns:
        List of (card_instance, guard_function, is_blocking) tuples
        where is_blocking is True if the guard blocks the effect

    Example:
        >>> # Check if playing an Item is blocked
        >>> guards = scan_global_guards(state, "global_play_item", {"item": item_card})
        >>> for source_card, guard_fn, is_blocking in guards:
        >>>     if is_blocking:
        >>>         return False  # Item play is blocked
    """
    if context is None:
        context = {}

    results = []

    # Scan both players' boards
    for player in state.players:
        # Check active Pokémon
        if player.board.active_spot:
            card = player.board.active_spot
            guard = get_card_guard(card.card_id, guard_type)
            if guard:
                is_blocking = guard(state, card, context)
                results.append((card, guard, is_blocking))

        # Check bench Pokémon
        for bench_card in player.board.bench:
            if bench_card:
                guard = get_card_guard(bench_card.card_id, guard_type)
                if guard:
                    is_blocking = guard(state, bench_card, context)
                    results.append((bench_card, guard, is_blocking))

    # Check Stadium card
    if state.stadium:
        guard = get_card_guard(state.stadium.card_id, guard_type)
        if guard:
            is_blocking = guard(state, state.stadium, context)
            results.append((state.stadium, guard, is_blocking))

    return results


def check_global_block(state: 'GameState', guard_type: str, context: dict = None) -> bool:
    """
    Check if ANY card on the board blocks the specified effect.

    Convenience function that returns True if any global guard blocks.

    Args:
        state: Current game state
        guard_type: Type of global guard to check (e.g., "global_play_item")
        context: Optional context dict with details about the effect

    Returns:
        True if ANY card blocks the effect, False otherwise

    Example:
        >>> # Check if playing an Item is blocked by anything
        >>> if check_global_block(state, "global_play_item", {"item": item_card}):
        >>>     return []  # Can't play Items
    """
    guards = scan_global_guards(state, guard_type, context)
    return any(is_blocking for _, _, is_blocking in guards)


# ============================================================================
# EXCEPTIONS
# ============================================================================

class IllegalActionError(Exception):
    """Raised when an action cannot be legally performed."""
    pass

"""
Pokémon TCG Engine - Card Logic Registry (Pure Router)

This module serves as a pure routing layer for card-specific logic.
All implementation functions are stored in set-based modules under cards/sets/.

Architecture - The 4 Pillars of Card Logic:
================================
Each card entry in the registry uses attack/ability names as direct keys,
plus optional pillar keys for modifiers, guards, and hooks:

1. Attack/Ability Actions (direct keys using attack name):
   - Called to generate legal actions for MCTS
   - Format: {"Attack Name": {"generator": fn, "effect": fn}}
   - Example: {"Heat Tackle": {"generator": heat_tackle_actions, "effect": heat_tackle_effect}}

2. "modifiers": Dictionary of value-modifying functions
   - LOCAL modifiers: Affect only the card itself (e.g., Charmander's Agile)
   - GLOBAL modifiers: Affect other cards on the board (e.g., Beach Court Stadium)
   - Local: {"modifiers": {"retreat_cost": fn}}  # fn(state, card, current_cost) -> new_value
   - Global: {"modifiers": {"global_retreat_cost": fn}}  # fn(state, source, target, cost) -> new_cost

3. "guards": Dictionary of permission-blocking functions
   - LOCAL guards: Block effects on the card itself (e.g., Hoothoot's Insomnia)
   - GLOBAL guards: Block effects on other cards (e.g., Item Lock, Ability Lock)
   - Local: {"guards": {"status_condition": fn}}  # fn(state, card, condition) -> bool (blocked)
   - Global: {"guards": {"global_play_item": fn}}  # fn(state, source, context) -> bool (blocked)

4. "hooks": Dictionary of event-triggered functions
   - Called when specific game events occur (on_play_pokemon, on_knockout, etc.)
   - Example: {"hooks": {"on_play_pokemon": fn}}  # fn(state, card, context) -> GameState

Registry Entry Examples:
========================
# Pokemon with attack only:
"sv3-162": {
    "Gust": {"generator": pidgey_gust_actions, "effect": pidgey_gust_effect},
}

# Pokemon with multiple attacks:
"sv3pt5-16": {
    "Call for Family": {"generator": call_for_family_actions, "effect": call_for_family_effect},
    "Tackle": {"generator": tackle_actions, "effect": tackle_effect},
}

# Pokemon with attack + modifier (passive ability):
"me2-11": {
    "Live Coal": {"generator": live_coal_actions, "effect": live_coal_effect},
    "modifiers": {"retreat_cost": charmander_agile_modifier},
}

# Trainer card (uses actions wrapper with "play" action):
"me1-125": {
    "actions": {
        "play": {
            "generator": rare_candy_actions,
            "effect": rare_candy_effect,
        }
    }
}

Local vs Global Effects:
========================
- LOCAL: No prefix - affects only the card with the effect
  - get_card_modifier(), get_card_guard() - for checking a specific card
- GLOBAL: Prefixed with "global_" - affects other cards on the board
  - scan_global_modifiers(), scan_global_guards() - scans entire board

Usage:
    from cards.logic_registry import (
        get_card_logic,
        get_card_modifier, get_card_guard, get_card_hooks,
        scan_global_modifiers, scan_global_guards
    )

    # Get attack logic for a Pokemon
    attack_logic = get_card_logic("sv3-162", "Gust")
    # Returns: {"generator": fn, "effect": fn}

    # Check if a card modifies its own retreat cost (LOCAL)
    retreat_modifier = get_card_modifier("me2-11", "retreat_cost")

    # Scan board for cards that modify OTHER cards' retreat cost (GLOBAL)
    global_modifiers = scan_global_modifiers(state, "global_retreat_cost")

    # Check if playing an item is blocked by any card on the board (GLOBAL GUARD)
    blockers = scan_global_guards(state, "global_play_item", {"item": item, "player": player})
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
# ROUTER FUNCTION
# ============================================================================

def get_card_logic(card_id: str, logic_type: str) -> Optional[Callable]:
    """
    Get the implementation function for a card's logic.

    Supports multiple registry formats:
    - Trainer (new): {"actions": {"play": {"generator": fn, "effect": fn}}}
    - Pokémon: {"Attack Name": {"generator": fn, "effect": fn}}
    - Legacy flat: "card_id:effect_name" -> func

    Args:
        card_id: The card's ID (e.g., "sv3-125" for Charizard ex, "me1-125" for Rare Candy)
        logic_type: Type of logic to retrieve (e.g., "effect", "generator", "Burning Darkness")

    Returns:
        Callable function, nested dict, or None if not found

    Example:
        >>> # Trainer card (uses actions wrapper)
        >>> logic_func = get_card_logic("me1-125", "effect")
        >>> generator = get_card_logic("me1-125", "generator")

        >>> # Pokémon card (2-level nested - returns nested dict)
        >>> attack_logic = get_card_logic("sv3-125", "Burning Darkness")
        >>> if isinstance(attack_logic, dict):
        >>>     effect = attack_logic.get("effect")
        >>>     generator = attack_logic.get("generator")

        >>> # Legacy flat structure
        >>> logic_func = get_card_logic("sv3-125", "Burning Darkness")
    """
    # Try nested structure first (new format)
    card_data = MASTER_LOGIC_REGISTRY.get(card_id)
    if isinstance(card_data, dict):
        # Check for Trainer card format: {"actions": {"play": {"generator": fn, "effect": fn}}}
        # When looking up "generator" or "effect" for a Trainer, check inside actions.play
        if logic_type in ('generator', 'effect'):
            actions = card_data.get('actions')
            if isinstance(actions, dict):
                play_action = actions.get('play')
                if isinstance(play_action, dict):
                    return play_action.get(logic_type)

        # For Pokémon attacks/abilities or other lookups, return the nested dict
        # or a nested dict (for Pokémon: "Attack Name" -> {"effect": ..., "generator": ...})
        return card_data.get(logic_type)

    # Fall back to flat structure (legacy format)
    lookup_key = f"{card_id}:{logic_type}"
    return MASTER_LOGIC_REGISTRY.get(lookup_key)


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
        modifiers = card_data.get("modifiers")
        if isinstance(modifiers, dict):
            return modifiers.get(modifier_type)
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
        guards = card_data.get("guards")
        if isinstance(guards, dict):
            return guards.get(guard_type)
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
        hooks = card_data.get("hooks")
        if isinstance(hooks, dict):
            return hooks.get(hook_type)
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
            modifiers = card_data.get("modifiers")
            if isinstance(modifiers, dict) and modifier_type in modifiers:
                result[card_id] = modifiers[modifier_type]
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
            guards = card_data.get("guards")
            if isinstance(guards, dict) and guard_type in guards:
                result[card_id] = guards[guard_type]
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
            hooks = card_data.get("hooks")
            if isinstance(hooks, dict) and hook_type in hooks:
                result[card_id] = hooks[hook_type]
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
# LEGACY COMPATIBILITY (for existing tests)
# ============================================================================

# These registries are kept for backwards compatibility
# New code should use get_card_logic() instead
ABILITY_REGISTRY: Dict[str, Callable] = {}
ATTACK_DAMAGE_REGISTRY: Dict[str, Callable] = {}
ATTACK_EFFECT_REGISTRY: Dict[str, Callable] = {}
ATTACK_VALIDATOR_REGISTRY: Dict[str, Callable] = {}
LOGIC_MAP: Dict[str, Callable] = {}


def get_ability_function(ability_name: str) -> Optional[Callable]:
    """Legacy function for backwards compatibility."""
    return ABILITY_REGISTRY.get(ability_name)


def get_attack_damage_function(attack_name: str) -> Optional[Callable]:
    """Legacy function for backwards compatibility."""
    return ATTACK_DAMAGE_REGISTRY.get(attack_name)


def get_attack_effect_function(attack_name: str) -> Optional[Callable]:
    """Legacy function for backwards compatibility."""
    return ATTACK_EFFECT_REGISTRY.get(attack_name)


def get_attack_validator(attack_name: str) -> Optional[Callable]:
    """Legacy function for backwards compatibility."""
    return ATTACK_VALIDATOR_REGISTRY.get(attack_name)


# ============================================================================
# EXCEPTIONS
# ============================================================================

class IllegalActionError(Exception):
    """Raised when an action cannot be legally performed."""
    pass

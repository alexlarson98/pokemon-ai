"""
Pokémon TCG Engine - Effect Library (cards/logic_effects.py)
Standard library of effect application functions.

This module contains reusable effect functions that can be called by
card-specific logic to create ActiveEffect objects.

Examples:
- Manaphy: apply_bench_barrier (prevents bench damage)
- Iron Leaves ex: apply_cant_attack_self (locks this Pokemon from attacking)
- Bravery Charm: apply_hp_bonus (adds HP to this Pokemon)
- Float Stone: apply_retreat_cost_reduction (reduces retreat cost)
"""

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from models import GameState, CardInstance, ActiveEffect

from models import ActiveEffect, EffectSource


# ============================================================================
# DAMAGE PREVENTION EFFECTS
# ============================================================================

def apply_bench_barrier(
    state: 'GameState',
    source_card: 'CardInstance',
    affected_player_id: int
) -> 'GameState':
    """
    Apply "Bench Barrier" effect (Manaphy's "Wave Veil").

    Prevents all damage done to Benched Pokémon by attacks.

    Args:
        state: Current game state
        source_card: Card creating the effect (e.g., Manaphy)
        affected_player_id: Player whose bench is protected

    Returns:
        Modified GameState with effect added

    Example:
        >>> # Manaphy's Wave Veil Ability
        >>> state = apply_bench_barrier(state, manaphy_instance, player_id=0)
    """
    effect = ActiveEffect(
        name="Bench Barrier",
        source=EffectSource.ABILITY,
        source_card_id=source_card.id,
        target_player_id=affected_player_id,
        target_card_id=None,  # Applies to all benched Pokemon
        duration_turns=-1,  # Permanent (while Manaphy is in play)
        created_turn=state.turn_count,
        created_phase=state.current_phase.value,
        params={"prevents": "bench_damage"}
    )

    state.active_effects.append(effect)
    return state


def apply_damage_immunity(
    state: 'GameState',
    source_card: 'CardInstance',
    target_card: 'CardInstance',
    duration_turns: int = -1
) -> 'GameState':
    """
    Apply "Prevent all damage" effect to a specific Pokemon.

    Examples:
    - Cornerstone Mask Ogerpon ex: "Prevent all damage from attacks"

    Args:
        state: Current game state
        source_card: Card creating the effect
        target_card: Pokemon that becomes immune
        duration_turns: How long effect lasts (-1 = permanent)

    Returns:
        Modified GameState with effect added
    """
    effect = ActiveEffect(
        name="Damage Immunity",
        source=EffectSource.ABILITY,
        source_card_id=source_card.id,
        target_player_id=None,
        target_card_id=target_card.id,
        duration_turns=duration_turns,
        created_turn=state.turn_count,
        created_phase=state.current_phase.value,
        params={"prevents": "all_damage", "damage_immunity": True}
    )

    state.active_effects.append(effect)
    return state


# ============================================================================
# ATTACK LOCK EFFECTS
# ============================================================================

def apply_cant_attack_self(
    state: 'GameState',
    source_card: 'CardInstance',
    locked_card: 'CardInstance'
) -> 'GameState':
    """
    Apply "Can't attack during your next turn" effect (Iron Leaves ex).

    This is a self-lock effect applied after using a powerful attack.

    Args:
        state: Current game state
        source_card: Card creating the effect (same as locked_card for self-lock)
        locked_card: Pokemon that can't attack

    Returns:
        Modified GameState with effect added

    Example:
        >>> # Iron Leaves ex uses "Rapid Verdant" (220 damage)
        >>> # Effect: "This Pokemon can't attack during your next turn"
        >>> state = apply_cant_attack_self(state, iron_leaves, iron_leaves)
    """
    # Effect expires at end of player's next turn
    effect = ActiveEffect(
        name="Cant Attack (Self-Lock)",
        source=EffectSource.ATTACK,
        source_card_id=source_card.id,
        target_player_id=None,
        target_card_id=locked_card.id,
        duration_turns=1,  # Until end of next turn
        created_turn=state.turn_count,
        created_phase=state.current_phase.value,
        expires_on_player=locked_card.owner_id,  # Expires on this player's turn
        params={"prevents": "attack", "self_lock": True}
    )

    state.active_effects.append(effect)
    return state


def apply_cant_attack_opponent(
    state: 'GameState',
    source_card: 'CardInstance',
    locked_card: 'CardInstance'
) -> 'GameState':
    """
    Apply "Can't attack during opponent's next turn" effect.

    Examples:
    - Paralysis-like effects from attacks
    - Blocking effects from Abilities

    Args:
        state: Current game state
        source_card: Card creating the effect
        locked_card: Opponent's Pokemon that can't attack

    Returns:
        Modified GameState with effect added
    """
    effect = ActiveEffect(
        name="Cant Attack (Opponent Lock)",
        source=EffectSource.ATTACK,
        source_card_id=source_card.id,
        target_player_id=None,
        target_card_id=locked_card.id,
        duration_turns=1,  # Until end of next turn
        created_turn=state.turn_count,
        created_phase=state.current_phase.value,
        expires_on_player=locked_card.owner_id,  # Expires on their turn
        params={"prevents": "attack", "opponent_lock": True}
    )

    state.active_effects.append(effect)
    return state


# ============================================================================
# STAT MODIFIER EFFECTS
# ============================================================================

def apply_hp_bonus(
    state: 'GameState',
    source_card: 'CardInstance',
    target_card: 'CardInstance',
    hp_bonus: int
) -> 'GameState':
    """
    Apply HP bonus effect to a Pokemon.

    Examples:
    - Bravery Charm: "+50 HP"
    - Big Charm: "+30 HP"

    Args:
        state: Current game state
        source_card: Tool card providing HP
        target_card: Pokemon receiving HP bonus
        hp_bonus: Amount of HP to add

    Returns:
        Modified GameState with effect added
    """
    effect = ActiveEffect(
        name=f"HP Bonus +{hp_bonus}",
        source=EffectSource.TOOL,
        source_card_id=source_card.id,
        target_player_id=None,
        target_card_id=target_card.id,
        duration_turns=-1,  # Permanent while attached
        created_turn=state.turn_count,
        created_phase=state.current_phase.value,
        params={"hp_bonus": hp_bonus}
    )

    state.active_effects.append(effect)
    return state


def apply_retreat_cost_reduction(
    state: 'GameState',
    source_card: 'CardInstance',
    target_card: 'CardInstance',
    reduction: int
) -> 'GameState':
    """
    Apply retreat cost reduction effect.

    Examples:
    - Float Stone: "Retreat cost -2"
    - Air Balloon: "Retreat cost -1"

    Args:
        state: Current game state
        source_card: Tool card providing reduction
        target_card: Pokemon with reduced retreat cost
        reduction: Amount to reduce (positive number)

    Returns:
        Modified GameState with effect added
    """
    effect = ActiveEffect(
        name=f"Retreat Cost -{reduction}",
        source=EffectSource.TOOL,
        source_card_id=source_card.id,
        target_player_id=None,
        target_card_id=target_card.id,
        duration_turns=-1,  # Permanent while attached
        created_turn=state.turn_count,
        created_phase=state.current_phase.value,
        params={"retreat_cost_modifier": -reduction}
    )

    state.active_effects.append(effect)
    return state


def apply_damage_modifier(
    state: 'GameState',
    source_card: 'CardInstance',
    target_card: 'CardInstance',
    modifier: int
) -> 'GameState':
    """
    Apply damage modifier effect to attacker.

    Examples:
    - Double Turbo Energy: "-20 damage done by this Pokemon's attacks"
    - Muscle Band: "+20 damage to opponent's Active Pokemon"

    Args:
        state: Current game state
        source_card: Card providing modifier (Energy/Tool)
        target_card: Pokemon dealing modified damage
        modifier: Damage change (positive = boost, negative = reduction)

    Returns:
        Modified GameState with effect added
    """
    effect = ActiveEffect(
        name=f"Damage {'+' if modifier > 0 else ''}{modifier}",
        source=EffectSource.ENERGY if "Energy" in source_card.card_id else EffectSource.TOOL,
        source_card_id=source_card.id,
        target_player_id=None,
        target_card_id=target_card.id,
        duration_turns=-1,  # Permanent while attached
        created_turn=state.turn_count,
        created_phase=state.current_phase.value,
        params={"damage_modifier": modifier}
    )

    state.active_effects.append(effect)
    return state


# ============================================================================
# ABILITY LOCK EFFECTS
# ============================================================================

def apply_ability_lock(
    state: 'GameState',
    source_card: 'CardInstance',
    affected_player_id: Optional[int] = None,
    subtype_filter: Optional[str] = None
) -> 'GameState':
    """
    Apply ability lock effect.

    Examples:
    - Path to the Peak (Stadium): "Pokemon VSTAR Abilities can't be used"
    - Garbodor's Garbotoxin: "All other Pokemon's Abilities stop working"

    Args:
        state: Current game state
        source_card: Card creating the lock (Stadium/Pokemon)
        affected_player_id: Player whose abilities are locked (None = both players)
        subtype_filter: Only lock specific subtypes (e.g., "VSTAR", "ex")

    Returns:
        Modified GameState with effect added
    """
    params = {"prevents": "ability"}
    if subtype_filter:
        params["subtype"] = subtype_filter

    effect = ActiveEffect(
        name="Ability Lock",
        source=EffectSource.STADIUM if "Stadium" in source_card.card_id else EffectSource.ABILITY,
        source_card_id=source_card.id,
        target_player_id=affected_player_id,
        target_card_id=None,
        duration_turns=-1,  # Permanent while Stadium/Pokemon is in play
        created_turn=state.turn_count,
        created_phase=state.current_phase.value,
        params=params
    )

    state.active_effects.append(effect)
    return state


def apply_klefki_ability_lock(
    state: 'GameState',
    source_card: 'CardInstance'
) -> 'GameState':
    """
    Apply Klefki's "Mischievous Lock" ability.

    While this Pokémon is in the Active Spot, your opponent's Pokémon
    can't use Abilities.

    Args:
        state: Current game state
        source_card: Klefki card instance (must be in Active Spot)

    Returns:
        Modified GameState with effect added
    """
    effect = ActiveEffect(
        name="Mischievous Lock",
        source=EffectSource.ABILITY,
        source_card_id=source_card.id,
        target_player_id=None,  # Affects opponent (checked by engine)
        target_card_id=None,  # Affects all opponent's Pokémon
        duration_turns=-1,  # Permanent while Klefki is in Active Spot
        created_turn=state.turn_count,
        created_phase=state.current_phase.value,
        params={"blocks_opponent_abilities": True}
    )

    state.active_effects.append(effect)
    return state


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def remove_effects_by_source(state: 'GameState', source_card_id: str) -> 'GameState':
    """
    Remove all effects created by a specific card.

    Used when a card leaves play (e.g., Manaphy is KO'd, Float Stone discarded).

    Args:
        state: Current game state
        source_card_id: ID of card whose effects should be removed

    Returns:
        Modified GameState with effects removed
    """
    state.active_effects = [
        effect for effect in state.active_effects
        if effect.source_card_id != source_card_id
    ]
    return state


def has_effect_on_card(state: 'GameState', card_id: str, effect_name: str) -> bool:
    """
    Check if a specific card has a specific effect active.

    Args:
        state: Current game state
        card_id: Card instance ID to check
        effect_name: Name of effect to look for

    Returns:
        True if card has the effect active
    """
    for effect in state.active_effects:
        if effect.target_card_id == card_id and effect.name == effect_name:
            return True
    return False


# ============================================================================
# EFFECT LIBRARY EXPORT
# ============================================================================

EFFECT_LIBRARY = {
    # Damage prevention
    "bench_barrier": apply_bench_barrier,
    "damage_immunity": apply_damage_immunity,

    # Attack locks
    "cant_attack_self": apply_cant_attack_self,
    "cant_attack_opponent": apply_cant_attack_opponent,

    # Stat modifiers
    "hp_bonus": apply_hp_bonus,
    "retreat_cost_reduction": apply_retreat_cost_reduction,
    "damage_modifier": apply_damage_modifier,

    # Ability locks
    "ability_lock": apply_ability_lock,
    "klefki_ability_lock": apply_klefki_ability_lock,
}

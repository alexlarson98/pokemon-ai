"""
Pokémon TCG Engine - Card Logic Registry (Pure Router)

This module serves as a pure routing layer for card-specific logic.
All implementation functions are stored in set-based modules under cards/sets/.

Architecture:
- Each set module (sv1.py, sv2.py, etc.) exports a {SET}_LOGIC dictionary
- Keys: "{card_id}:{effect_name}" (e.g., "sv3-125:Burning Darkness")
- Values: Callable functions that implement the card logic

Usage:
    from cards.logic_registry import get_card_logic

    # Get logic for Charizard ex's Burning Darkness attack
    logic_func = get_card_logic("sv3-125", "Burning Darkness")
    if logic_func:
        result = logic_func(state, card, target)
"""

from typing import Optional, Callable, Dict

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

def get_card_logic(card_id: str, effect_name: str) -> Optional[Callable]:
    """
    Get the implementation function for a card's ability or attack.

    Args:
        card_id: The card's ID (e.g., "sv3-125" for Charizard ex)
        effect_name: The name of the ability or attack (e.g., "Burning Darkness")

    Returns:
        Callable function that implements the card logic, or None if not found

    Example:
        >>> logic_func = get_card_logic("sv3-125", "Burning Darkness")
        >>> if logic_func:
        >>>     damage = logic_func(state, attacker, target)
    """
    lookup_key = f"{card_id}:{effect_name}"
    return MASTER_LOGIC_REGISTRY.get(lookup_key)


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

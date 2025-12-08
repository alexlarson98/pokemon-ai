"""
Pokémon TCG Engine - Card Registry
Central lookup system for all card definitions.

The registry now supports both:
- Legacy: Class-based cards (for backwards compatibility)
- New: JSON-based cards (Data-Driven Factory Pattern)

Usage:
    # Create card from JSON
    card = create_card_from_data(TEST_DECK_DATA["sv3-123"])

    # Create card from ID (if registered)
    card = create_card("sv3-123")
"""

from typing import Dict, Type, Optional
from cards.base import Card, PokemonCard, TrainerCard, EnergyCard


# ============================================================================
# CARD DATABASE
# ============================================================================

# JSON database: Maps card IDs to card data from standard_cards.json
_JSON_DATABASE: Dict[str, Dict] = {}

# Legacy class-based database (deprecated, kept for backwards compatibility)
_CARD_DATABASE: Dict[str, Type[Card]] = {}


def _initialize_registry():
    """
    Initialize the card database with JSON data.

    Loads all cards from data/standard_cards.json
    """
    global _JSON_DATABASE
    import json
    import os

    # Load from standard_cards.json
    json_path = os.path.join(os.path.dirname(__file__), '..', '..',  'data', 'standard_cards.json')
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Index cards by ID
                for card in data.get('cards', []):
                    card_id = card.get('id')
                    if card_id:
                        _JSON_DATABASE[card_id] = card
            print(f"[Registry] Loaded {len(_JSON_DATABASE)} cards from standard_cards.json")
        except Exception as e:
            print(f"[Registry] Error loading standard_cards.json: {e}")
            raise RuntimeError(f"Failed to load card database: {e}")
    else:
        raise FileNotFoundError(f"Card database not found at {json_path}")


# Initialize registry on module load
_initialize_registry()


# ============================================================================
# REGISTRY FUNCTIONS
# ============================================================================

def get_card_class(card_id: str) -> Optional[Type[Card]]:
    """
    Get the card class for a given card ID.

    Args:
        card_id: Card identifier (e.g., "sv3-125", "generic-rare-candy")

    Returns:
        Card class, or None if not found

    Example:
        >>> charizard_class = get_card_class("sv3-125")
        >>> print(charizard_class)
        <class 'CharizardEx'>
    """
    return _CARD_DATABASE.get(card_id)


def create_card(card_id: str) -> Optional[Card]:
    """
    Create a card definition from a card ID.

    Loads card data from the JSON database (standard_cards.json).

    Args:
        card_id: Card identifier from Pokémon TCG API (e.g., "sv3-123", "sv2-185")

    Returns:
        Card definition object, or None if card ID not found

    Example:
        >>> raging_bolt = create_card("sv3-123")
        >>> print(raging_bolt.name)
        "Raging Bolt ex"
        >>> print(raging_bolt.hp)
        220

    Note:
        This function creates Card Definition objects (DataDrivenPokemon, etc.),
        not CardInstance objects. Use create_card_instance() for instances.
    """
    # Load from JSON database
    if card_id in _JSON_DATABASE:
        from cards.factory import create_card_from_json
        return create_card_from_json(_JSON_DATABASE[card_id])

    # Card not found in database
    return None


def get_card_data(card_id: str) -> Optional[Dict]:
    """
    Get basic card data as a dictionary.

    Useful for serialization and debugging.

    Args:
        card_id: Card identifier

    Returns:
        Dictionary with card data, or None if not found

    Example:
        >>> data = get_card_data("sv3-125")
        >>> print(data)
        {
            'card_id': 'sv3-125',
            'name': 'Charizard ex',
            'hp': 330,
            'types': ['Fire'],
            ...
        }
    """
    card = create_card(card_id)
    if card is None:
        return None

    data = {
        'card_id': card.card_id,
        'name': card.name,
        'subtypes': [str(subtype.value) for subtype in card.subtypes],
    }

    # Add type-specific data
    if isinstance(card, PokemonCard):
        data.update({
            'supertype': 'Pokemon',
            'hp': card.hp,
            'types': [str(t.value) for t in card.types],
            'weakness': str(card.base_weakness.value) if card.base_weakness else None,
            'resistance': str(card.base_resistance.value) if card.base_resistance else None,
            'retreat_cost': card.base_retreat_cost,
            'evolves_from': card.evolves_from,
        })
    elif isinstance(card, TrainerCard):
        data.update({
            'supertype': 'Trainer',
            'text': card.text,
        })
    elif isinstance(card, EnergyCard):
        data.update({
            'supertype': 'Energy',
            'energy_type': str(card.energy_type.value),
            'is_basic': card.is_basic,
        })

    return data


def card_exists(card_id: str) -> bool:
    """
    Check if a card ID exists in the registry.

    Checks both JSON database and legacy class-based database.

    Args:
        card_id: Card identifier

    Returns:
        True if card exists, False otherwise

    Example:
        >>> card_exists("sv6-128")
        True
        >>> card_exists("invalid-card")
        False
    """
    # Check JSON database first (new data-driven system)
    if card_id in _JSON_DATABASE:
        return True

    # Check legacy class-based database
    return card_id in _CARD_DATABASE


def get_all_card_ids() -> list[str]:
    """
    Get list of all registered card IDs.

    Returns:
        List of card ID strings

    Example:
        >>> ids = get_all_card_ids()
        >>> print(len(ids))
        19
        >>> print(ids[:3])
        ['sv3-026', 'sv3-027', 'sv3-125']
    """
    return list(_CARD_DATABASE.keys())


def get_cards_by_type(card_type: Type[Card]) -> Dict[str, Type[Card]]:
    """
    Get all cards of a specific type.

    Args:
        card_type: Card class to filter by (PokemonCard, TrainerCard, EnergyCard)

    Returns:
        Dictionary of card IDs to card classes

    Example:
        >>> pokemon_cards = get_cards_by_type(PokemonCard)
        >>> print(len(pokemon_cards))
        4
    """
    return {
        card_id: card_class
        for card_id, card_class in _CARD_DATABASE.items()
        if issubclass(card_class, card_type)
    }


def register_card(card_id: str, card_class: Type[Card]) -> None:
    """
    Register a new card in the database.

    Useful for dynamic card loading or testing.

    Args:
        card_id: Unique card identifier
        card_class: Card class to register

    Example:
        >>> class CustomCard(PokemonCard):
        ...     def __init__(self):
        ...         super().__init__(...)
        >>> register_card("custom-001", CustomCard)
    """
    _CARD_DATABASE[card_id] = card_class


def unregister_card(card_id: str) -> bool:
    """
    Remove a card from the registry.

    Args:
        card_id: Card identifier to remove

    Returns:
        True if card was removed, False if not found
    """
    if card_id in _CARD_DATABASE:
        del _CARD_DATABASE[card_id]
        return True
    return False


# ============================================================================
# REGISTRY STATISTICS
# ============================================================================

def get_registry_stats() -> Dict:
    """
    Get statistics about the card registry.

    Returns:
        Dictionary with registry statistics

    Example:
        >>> stats = get_registry_stats()
        >>> print(stats)
        {
            'total_cards': 13,
            'pokemon': 5,
            'trainers': 4,
            'energy': 5
        }
    """
    # Count JSON cards by supertype
    pokemon_count = 0
    trainer_count = 0
    energy_count = 0

    for card_data in _JSON_DATABASE.values():
        supertype = card_data.get('supertype', '').lower()
        if supertype in ['pokémon', 'pokemon']:
            pokemon_count += 1
        elif supertype == 'trainer':
            trainer_count += 1
        elif supertype == 'energy':
            energy_count += 1

    # Add legacy class-based cards
    total_legacy = len(_CARD_DATABASE)

    return {
        'total_cards': len(_JSON_DATABASE) + total_legacy,
        'pokemon': pokemon_count,
        'trainers': trainer_count,
        'energy': energy_count,
        'json_cards': len(_JSON_DATABASE),
        'legacy_cards': total_legacy,
    }


# ============================================================================
# DEBUGGING / PRETTY PRINT
# ============================================================================

def print_card_info(card_id: str) -> None:
    """
    Print detailed information about a card.

    Args:
        card_id: Card identifier

    Example:
        >>> print_card_info("sv3-125")
        Card ID: sv3-125
        Name: Charizard ex
        Type: Pokemon
        HP: 330
        Types: Fire
        ...
    """
    data = get_card_data(card_id)
    if data is None:
        print(f"Card '{card_id}' not found in registry.")
        return

    print(f"Card ID: {data['card_id']}")
    print(f"Name: {data['name']}")
    print(f"Type: {data['supertype']}")

    if data['supertype'] == 'Pokemon':
        print(f"HP: {data['hp']}")
        print(f"Types: {', '.join(data['types'])}")
        print(f"Weakness: {data['weakness']}")
        print(f"Resistance: {data['resistance']}")
        print(f"Retreat Cost: {data['retreat_cost']}")
        if data['evolves_from']:
            print(f"Evolves From: {data['evolves_from']}")

    elif data['supertype'] == 'Trainer':
        print(f"Text: {data['text']}")

    elif data['supertype'] == 'Energy':
        print(f"Energy Type: {data['energy_type']}")
        print(f"Basic: {data['is_basic']}")

    print(f"Subtypes: {', '.join(data['subtypes'])}")


def print_registry() -> None:
    """
    Print all cards in the registry.

    Example:
        >>> print_registry()
        === Card Registry ===
        Total Cards: 19

        SV3 Set (4 cards):
        - sv3-026: Charmander
        - sv3-027: Charmeleon
        - sv3-125: Charizard ex
        - sv3-123: Pikachu ex

        Generic Cards (15 cards):
        ...
    """
    stats = get_registry_stats()

    print("=== Card Registry ===")
    print(f"Total Cards: {stats['total_cards']}\n")

    # Print by set
    for set_name, count in stats['sets'].items():
        print(f"{set_name.upper()} Set ({count} cards):")
        for card_id in sorted(get_all_card_ids()):
            if (set_name == 'sv3' and card_id.startswith('sv3-')) or \
               (set_name == 'generics' and not card_id.startswith('sv3-')):
                card = create_card(card_id)
                if card:
                    print(f"  - {card_id}: {card.name}")
        print()


# ============================================================================
# CARD VALIDATION
# ============================================================================

def validate_deck(deck_card_ids: list[str]) -> Dict:
    """
    Validate a deck list.

    Checks:
    - All cards exist in registry
    - Deck has exactly 60 cards
    - No more than 4 copies of non-Basic Energy cards

    Args:
        deck_card_ids: List of card IDs in the deck

    Returns:
        Dictionary with validation results

    Example:
        >>> deck = ["sv3-125"] * 4 + ["energy-fire"] * 56
        >>> result = validate_deck(deck)
        >>> print(result['valid'])
        True
    """
    errors = []
    warnings = []

    # Check deck size
    if len(deck_card_ids) != 60:
        errors.append(f"Deck must have exactly 60 cards (has {len(deck_card_ids)})")

    # Check card existence
    missing_cards = [card_id for card_id in deck_card_ids if not card_exists(card_id)]
    if missing_cards:
        errors.append(f"Unknown cards: {set(missing_cards)}")

    # Check 4-copy rule
    from collections import Counter
    from models import Subtype
    card_counts = Counter(deck_card_ids)

    for card_id, count in card_counts.items():
        if count > 4:
            card = create_card(card_id)
            # Basic Energy exempt from 4-copy rule
            if card and isinstance(card, EnergyCard) and card.is_basic:
                continue
            errors.append(f"{card_id} appears {count} times (max 4)")

    # Check Ace Spec limit (max 1 per deck)
    ace_spec_cards = []
    for card_id in deck_card_ids:
        card = create_card(card_id)
        if card and Subtype.ACE_SPEC in card.subtypes:
            ace_spec_cards.append(card_id)

    if len(ace_spec_cards) > 1:
        unique_ace_specs = set(ace_spec_cards)
        errors.append(
            f"Deck contains {len(ace_spec_cards)} Ace Spec cards (max 1 allowed). "
            f"Found: {unique_ace_specs}"
        )

    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings,
        'card_count': len(deck_card_ids),
        'unique_cards': len(card_counts),
    }

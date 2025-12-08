"""
Pokémon TCG Engine - Card Factory
Creates CardInstance objects from card IDs or JSON data.

This module bridges the gap between:
- Card Definitions (JSON data or classes in cards/sets/)
- Card Instances (CardInstance objects in models.py)

Usage:
    # Create a CardInstance from card ID (old method)
    charizard = create_card_instance("sv3-125", owner_id=0)

    # Create a Card Definition from JSON (new data-driven method)
    card_def = create_card_from_json(json_data)

    # Create multiple copies (for deck building)
    fire_energies = create_multiple("energy-fire", count=10, owner_id=0)
"""

from typing import List, Optional, Dict
import uuid

from models import CardInstance, Subtype
from cards.registry import get_card_class, create_card
from cards.base import (
    Card, PokemonCard, TrainerCard, EnergyCard,
    DataDrivenPokemon, DataDrivenTrainer, DataDrivenEnergy
)


# ============================================================================
# JSON CARD CREATION (DATA-DRIVEN PATTERN)
# ============================================================================

def create_card_from_json(json_data: Dict) -> Optional[Card]:
    """
    Create a Card Definition from JSON data (Data-Driven Factory Pattern).

    This is the new JSON-based card loading system that replaces manual
    card classes for scalability.

    Args:
        json_data: Card data dictionary (e.g., from Pokémon TCG API)

    Returns:
        Card object (DataDrivenPokemon, DataDrivenTrainer, or DataDrivenEnergy),
        or None if invalid JSON

    Example:
        >>> json_data = {
        ...     "id": "sv3-123",
        ...     "name": "Pikachu ex",
        ...     "supertype": "Pokémon",
        ...     "hp": "120",
        ...     "types": ["Lightning"],
        ...     "attacks": [
        ...         {
        ...             "name": "Thunder Shock",
        ...             "cost": ["Lightning"],
        ...             "damage": "30",
        ...             "text": "Flip a coin. If heads, the Defending Pokémon is now Paralyzed."
        ...         }
        ...     ]
        ... }
        >>> pikachu = create_card_from_json(json_data)
        >>> print(pikachu.name)
        "Pikachu ex"
        >>> print(pikachu.hp)
        120
    """
    if not json_data or 'supertype' not in json_data:
        return None

    supertype = json_data.get('supertype', '').lower()

    # Detect supertype and instantiate appropriate DataDriven class
    if supertype == 'pokémon' or supertype == 'pokemon':
        return DataDrivenPokemon(json_data)

    elif supertype == 'trainer':
        return DataDrivenTrainer(json_data)

    elif supertype == 'energy':
        return DataDrivenEnergy(json_data)

    else:
        # Unknown supertype
        return None


# ============================================================================
# CARD INSTANCE CREATION
# ============================================================================

def create_card_instance(
    card_id: str,
    owner_id: int,
    instance_id: Optional[str] = None
) -> Optional[CardInstance]:
    """
    Create a CardInstance from a card definition.

    This is the main factory function used throughout the engine.

    Args:
        card_id: Card definition ID (e.g., "sv3-125")
        owner_id: Player ID who owns this card (0 or 1)
        instance_id: Optional custom instance ID (auto-generated if None)

    Returns:
        CardInstance object, or None if card_id not found

    Example:
        >>> charizard = create_card_instance("sv3-125", owner_id=0)
        >>> print(charizard.card_id)
        "sv3-125"
        >>> print(charizard.owner_id)
        0
        >>> print(charizard.current_hp)
        None  # Will be set when played
    """
    # Get card definition
    card_def = create_card(card_id)
    if card_def is None:
        return None

    # Generate unique instance ID
    if instance_id is None:
        instance_id = f"card_{uuid.uuid4().hex[:8]}"

    # Create CardInstance with appropriate defaults
    if isinstance(card_def, PokemonCard):
        # Pokémon cards track HP
        return CardInstance(
            id=instance_id,
            card_id=card_id,
            owner_id=owner_id,
            current_hp=card_def.hp,  # Initialize to max HP
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

    elif isinstance(card_def, (TrainerCard, EnergyCard)):
        # Trainer and Energy cards don't track HP
        return CardInstance(
            id=instance_id,
            card_id=card_id,
            owner_id=owner_id,
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

    return None


def create_multiple(
    card_id: str,
    count: int,
    owner_id: int
) -> List[CardInstance]:
    """
    Create multiple copies of a card.

    Useful for deck building (e.g., adding 10 Fire Energy).

    Args:
        card_id: Card definition ID
        count: Number of copies to create
        owner_id: Player ID who owns these cards

    Returns:
        List of CardInstance objects

    Example:
        >>> fire_energies = create_multiple("energy-fire", count=10, owner_id=0)
        >>> print(len(fire_energies))
        10
    """
    cards = []
    for _ in range(count):
        card = create_card_instance(card_id, owner_id)
        if card:
            cards.append(card)
    return cards


# ============================================================================
# DECK BUILDING
# ============================================================================

def create_deck_from_list(
    deck_list: List[tuple[str, int]],
    owner_id: int
) -> List[CardInstance]:
    """
    Create a deck from a list of (card_id, count) tuples.

    Args:
        deck_list: List of (card_id, count) tuples
        owner_id: Player ID who owns this deck

    Returns:
        List of 60 CardInstance objects

    Example:
        >>> deck_list = [
        ...     ("sv3-026", 4),      # 4 Charmander
        ...     ("sv3-125", 2),      # 2 Charizard ex
        ...     ("energy-fire", 20), # 20 Fire Energy
        ...     # ... (total 60)
        ... ]
        >>> deck = create_deck_from_list(deck_list, owner_id=0)
        >>> print(len(deck))
        60
    """
    deck = []

    for card_id, count in deck_list:
        cards = create_multiple(card_id, count, owner_id)
        deck.extend(cards)

    return deck


def create_starter_deck(owner_id: int) -> List[CardInstance]:
    """
    Create a simple starter deck for testing.

    Charizard ex Theme Deck:
    - 4 Charmander
    - 2 Charmeleon
    - 2 Charizard ex
    - 4 Pikachu ex
    - 10 Fire Energy
    - 10 Lightning Energy
    - 4 Professor's Research
    - 4 Boss's Orders
    - 4 Ultra Ball
    - 4 Rare Candy
    - 2 Switch
    - Total: 60 cards

    Args:
        owner_id: Player ID who owns this deck

    Returns:
        List of 60 CardInstance objects
    """
    deck_list = [
        # Pokémon (12)
        ("sv3-026", 4),      # Charmander
        ("sv3-027", 2),      # Charmeleon
        ("sv3-125", 2),      # Charizard ex
        ("sv3-123", 4),      # Pikachu ex

        # Energy (20)
        ("energy-fire", 12),
        ("energy-lightning", 8),

        # Supporters (8)
        ("generic-professors-research", 4),
        ("generic-boss-orders", 4),

        # Items (10)
        ("generic-ultra-ball", 4),
        ("generic-rare-candy", 4),
        ("generic-switch", 2),
    ]

    return create_deck_from_list(deck_list, owner_id)


# ============================================================================
# CARD INSTANCE UTILITIES
# ============================================================================

def get_card_definition(card_instance: CardInstance):
    """
    Get the card definition object for a CardInstance.

    Args:
        card_instance: CardInstance object

    Returns:
        Card definition (PokemonCard, TrainerCard, or EnergyCard)

    Example:
        >>> instance = create_card_instance("sv3-125", owner_id=0)
        >>> definition = get_card_definition(instance)
        >>> print(definition.name)
        "Charizard ex"
        >>> print(definition.hp)
        330
    """
    return create_card(card_instance.card_id)


def is_basic_pokemon(card_instance: CardInstance) -> bool:
    """
    Check if a CardInstance is a Basic Pokémon.

    Args:
        card_instance: CardInstance to check

    Returns:
        True if Basic Pokémon, False otherwise
    """
    card_def = get_card_definition(card_instance)
    if card_def and isinstance(card_def, PokemonCard):
        return Subtype.BASIC in card_def.subtypes
    return False


def is_evolution(card_instance: CardInstance) -> bool:
    """
    Check if a CardInstance is an evolution card.

    Args:
        card_instance: CardInstance to check

    Returns:
        True if Stage 1 or Stage 2, False otherwise
    """
    card_def = get_card_definition(card_instance)
    if card_def and isinstance(card_def, PokemonCard):
        return Subtype.STAGE_1 in card_def.subtypes or Subtype.STAGE_2 in card_def.subtypes
    return False


def is_energy(card_instance: CardInstance) -> bool:
    """
    Check if a CardInstance is an Energy card.

    Args:
        card_instance: CardInstance to check

    Returns:
        True if Energy card, False otherwise
    """
    card_def = get_card_definition(card_instance)
    return isinstance(card_def, EnergyCard)


def is_trainer(card_instance: CardInstance) -> bool:
    """
    Check if a CardInstance is a Trainer card.

    Args:
        card_instance: CardInstance to check

    Returns:
        True if Trainer card, False otherwise
    """
    card_def = get_card_definition(card_instance)
    return isinstance(card_def, TrainerCard)


def get_max_hp(card_instance: CardInstance) -> Optional[int]:
    """
    Get the maximum HP of a Pokémon CardInstance.

    Args:
        card_instance: CardInstance to check

    Returns:
        Maximum HP, or None if not a Pokémon
    """
    card_def = get_card_definition(card_instance)
    if card_def and isinstance(card_def, PokemonCard):
        return card_def.hp
    return None


def clone_card_instance(card_instance: CardInstance) -> CardInstance:
    """
    Create a deep copy of a CardInstance.

    Useful for state cloning in MCTS.

    Args:
        card_instance: CardInstance to clone

    Returns:
        New CardInstance with same state
    """
    return card_instance.model_copy(deep=True)


# ============================================================================
# DEBUGGING / TESTING
# ============================================================================

def print_card_instance(card_instance: CardInstance) -> None:
    """
    Print detailed information about a CardInstance.

    Args:
        card_instance: CardInstance to print

    Example:
        >>> instance = create_card_instance("sv3-125", owner_id=0)
        >>> print_card_instance(instance)
        === CardInstance ===
        Instance ID: card_abc123
        Card ID: sv3-125
        Name: Charizard ex
        Owner: Player 0
        HP: 330/330
        Status: None
        Energy: 0
        ...
    """
    card_def = get_card_definition(card_instance)

    print("=== CardInstance ===")
    print(f"Instance ID: {card_instance.id}")
    print(f"Card ID: {card_instance.card_id}")
    print(f"Owner: Player {card_instance.owner_id}")

    if card_def:
        print(f"Name: {card_def.name}")

        if isinstance(card_def, PokemonCard):
            current_hp = card_def.hp - (card_instance.damage_counters * 10)
            print(f"HP: {current_hp}/{card_def.hp}")
            if card_instance.status_conditions:
                print(f"Status: {', '.join([s.value for s in card_instance.status_conditions])}")
            else:
                print("Status: None")
            print(f"Energy: {len(card_instance.attached_energy)}")
            if card_instance.attached_tools:
                print(f"Tools: {len(card_instance.attached_tools)}")
            if card_instance.evolution_chain:
                print(f"Evolution Chain: {' -> '.join(card_instance.evolution_chain)}")
    else:
        print(f"[Unknown Card: {card_instance.card_id}]")

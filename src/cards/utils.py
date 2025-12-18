"""
Card Logic Utilities

Shared utility functions for card logic implementation.
This module provides helper functions that are used across multiple card implementations.
"""

# Cache for evolution chain lookups
_evolution_chain_cache = {}


def _check_evolution_chain(intermediate_name: str, base_name: str) -> bool:
    """
    Check if a valid evolution chain exists: base_name -> intermediate_name -> (Stage 2).

    Used by Rare Candy to validate that a Stage 2 can evolve from a Basic
    by checking if the intermediate Stage 1 exists in the card database.

    Args:
        intermediate_name: Name of the intermediate evolution (Stage 1)
        base_name: Name of the base Pokemon (Basic)

    Returns:
        True if intermediate_name is a valid Stage 1 that evolves from base_name

    Example:
        >>> _check_evolution_chain('Pidgeotto', 'Pidgey')  # True
        >>> _check_evolution_chain('Charmeleon', 'Pidgey')  # False
    """
    # Check cache first
    cache_key = (intermediate_name, base_name)
    if cache_key in _evolution_chain_cache:
        return _evolution_chain_cache[cache_key]

    # Load card data to check evolution chain
    import json
    import os

    # Get the correct path to standard_cards.json
    current_dir = os.path.dirname(os.path.abspath(__file__))
    cards_json_path = os.path.join(current_dir, '..', '..', 'data', 'standard_cards.json')

    try:
        with open(cards_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            all_cards = data.get('cards', [])

        # Check if there exists a card with name=intermediate_name that evolves from base_name
        for card_data in all_cards:
            if (card_data.get('name') == intermediate_name and
                card_data.get('evolvesFrom') == base_name):
                # Found valid intermediate evolution
                _evolution_chain_cache[cache_key] = True
                return True

        # No valid intermediate found
        _evolution_chain_cache[cache_key] = False
        return False

    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        # If we can't load the file, be conservative and return False
        return False


def find_stage_2_chain_for_basic(basic_def, stage_2_def) -> bool:
    """
    Check if a Stage 2 can evolve from a Basic via Rare Candy.

    This validates the evolution chain: Basic -> Stage 1 -> Stage 2
    where the Stage 2's evolves_from field points to the Stage 1,
    and that Stage 1 evolves from the given Basic.

    Args:
        basic_def: Card definition of the Basic Pokemon
        stage_2_def: Card definition of the Stage 2 Pokemon

    Returns:
        True if Rare Candy can evolve the Basic into the Stage 2

    Example:
        >>> find_stage_2_chain_for_basic(pidgey_def, pidgeot_ex_def)  # True
        >>> find_stage_2_chain_for_basic(charmander_def, pidgeot_ex_def)  # False
    """
    if not basic_def or not stage_2_def:
        return False

    # Stage 2 must have evolves_from pointing to a Stage 1
    if not hasattr(stage_2_def, 'evolves_from') or not stage_2_def.evolves_from:
        return False

    # Get the intermediate Stage 1 name
    intermediate_name = stage_2_def.evolves_from

    # The Basic's name
    basic_name = basic_def.name if hasattr(basic_def, 'name') else None
    if not basic_name:
        return False

    # Check if the intermediate Stage 1 evolves from the Basic
    return _check_evolution_chain(intermediate_name, basic_name)


def get_valid_basics_for_rare_candy(state, player) -> list:
    """
    Get all Basic Pokemon that are valid targets for Rare Candy.

    A Basic is valid if:
    1. It's on the bench or active spot (in play)
    2. It has been in play for at least 1 turn (evolution sickness)
    3. There exists a Stage 2 in the player's hand that can evolve from it

    Args:
        state: Current game state
        player: Player who would use Rare Candy

    Returns:
        List of CardInstance objects for valid Basic Pokemon
    """
    from cards.factory import get_card_definition
    from models import Subtype

    valid_basics = []

    # Get all Pokemon in play
    all_in_play = player.board.get_all_pokemon()

    # Get Stage 2 cards in hand
    stage_2_in_hand = []
    for hand_card in player.hand.cards:
        hand_def = get_card_definition(hand_card)
        if hand_def and hasattr(hand_def, 'subtypes') and Subtype.STAGE_2 in hand_def.subtypes:
            stage_2_in_hand.append((hand_card, hand_def))

    for pokemon in all_in_play:
        pokemon_def = get_card_definition(pokemon)
        if not pokemon_def:
            continue

        # Check if Basic
        if not (hasattr(pokemon_def, 'subtypes') and Subtype.BASIC in pokemon_def.subtypes):
            continue

        # Check evolution sickness (must have been in play at least 1 turn)
        if pokemon.turns_in_play < 1:
            continue

        # Check if any Stage 2 in hand can evolve from this Basic
        for stage_2_card, stage_2_def in stage_2_in_hand:
            if find_stage_2_chain_for_basic(pokemon_def, stage_2_def):
                valid_basics.append(pokemon)
                break

    return valid_basics



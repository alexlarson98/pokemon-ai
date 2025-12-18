"""
Card Logic Utilities

Shared utility functions for card logic implementation.
This module provides helper functions that are used across multiple card implementations.
"""

from typing import List, Callable, Optional
from itertools import combinations
from models import GameState, PlayerState, CardInstance, Action, ActionType
from cards.registry import create_card
from cards.factory import get_card_definition

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


def resolve_search_target(
    player: PlayerState,
    target_id: str,
    criteria_func: Optional[Callable] = None
) -> Optional[CardInstance]:
    """
    Resolve a search target ID to an actual card in the deck.

    Handles both:
    - Regular card IDs: Direct lookup by card.id
    - Belief-based IDs (format: 'belief:CardName'): Search by name and criteria

    This is the central utility for all deck search effect handlers, ensuring
    consistent behavior for ISMCTS belief-based searches.

    Args:
        player: Player performing the search
        target_id: Either a card instance ID or a belief placeholder ('belief:CardName')
        criteria_func: Optional criteria function to validate the card
                      (e.g., lambda c: Subtype.BASIC in c.subtypes)

    Returns:
        CardInstance if found, None if not found (expected for belief searches)

    Example:
        >>> # Regular search
        >>> card = resolve_search_target(player, 'card_abc123')

        >>> # Belief-based search
        >>> def is_basic(card_def):
        >>>     return Subtype.BASIC in card_def.subtypes
        >>> card = resolve_search_target(player, 'belief:Klefki', is_basic)
    """
    # Check if this is a belief-based search (ISMCTS)
    if target_id.startswith('belief:'):
        # Extract card name from belief placeholder
        card_name = target_id.split(':', 1)[1]

        # Try to find any card with this name in deck that meets criteria
        for deck_card in player.deck.cards:
            card_def = get_card_definition(deck_card)
            if not card_def or card_def.name != card_name:
                continue

            # If criteria provided, check it
            if criteria_func and not criteria_func(card_def):
                continue

            # Found matching card
            return deck_card

        # ISMCTS: Card not found (likely in prizes) - this is expected
        return None
    else:
        # Regular search: Find the card in the deck by exact ID
        return next((c for c in player.deck.cards if c.id == target_id), None)


def get_deck_search_candidates(
    state: GameState,
    player: PlayerState,
    criteria_func: Optional[Callable] = None
) -> List[str]:
    """
    Get list of searchable card names for DECK SEARCHES based on player's knowledge.

    This is the 'Belief Engine' for ISMCTS - generates search candidates based on what
    the player believes could be in the deck, not necessarily what is there.

    IMPORTANT: This is specifically for DECK searches (hidden information).
    The function intentionally EXCLUDES prizes from visibility calculations because
    they are hidden. It INCLUDES the discard pile in visibility because that's public.

    Args:
        state: Current game state
        player: Player performing the search
        criteria_func: Optional filter function that takes a CardDefinition
                      and returns True if it matches search criteria
                      (e.g., lambda c: Subtype.BASIC in c.subtypes)

    Returns:
        List of card names that could be searchable targets in the deck

    Example:
        >>> # Search for Basic Pokémon
        >>> from models import Subtype
        >>> def is_basic(card_def):
        >>>     return Subtype.BASIC in card_def.subtypes
        >>> candidates = get_deck_search_candidates(state, player, is_basic)
        >>> # Returns: ["Pidgey", "Dreepy", ...] based on beliefs
    """
    # Check knowledge state - Perfect Knowledge Mode
    if player.has_searched_deck:
        # Perfect knowledge - return actual deck contents
        searchable_cards = set()

        for card in player.deck.cards:
            card_def = create_card(card.card_id)
            card_name = card_def.name if card_def and hasattr(card_def, 'name') else card.card_id

            # Apply filter if provided
            if criteria_func is None or criteria_func(card_def):
                searchable_cards.add(card_name)

        return sorted(list(searchable_cards))

    # Imperfect knowledge - infer from public information
    # Start with initial deck counts
    theory_count = player.initial_deck_counts.copy()

    # Subtract visible cards from all zones EXCEPT prizes (hidden)
    visible_zones = [
        player.hand.cards,
        player.discard.cards,
        player.board.get_all_pokemon(),  # Active + Bench
    ]

    # Add attached cards (energy, tools, evolution history)
    for pokemon in player.board.get_all_pokemon():
        visible_zones.append(pokemon.attached_energy)
        visible_zones.append(pokemon.attached_tools)
        # Note: Evolution history not implemented yet

    # Count and subtract visible cards
    for zone in visible_zones:
        for card in zone:
            if card is None:
                continue  # Skip None entries
            card_def = create_card(card.card_id)
            card_name = card_def.name if card_def and hasattr(card_def, 'name') else card.card_id

            if card_name in theory_count:
                theory_count[card_name] -= 1
                if theory_count[card_name] <= 0:
                    del theory_count[card_name]

    # Filter candidates by criteria
    candidates = []

    for card_name, count in theory_count.items():
        if count > 0:
            # If no criteria function, include all candidates
            if criteria_func is None:
                candidates.append(card_name)
                continue

            # Need to find a card definition to apply criteria
            example_card = None

            # Try to find this card in visible zones to get its definition
            for zone in visible_zones:
                for card in zone:
                    if card is None:
                        continue  # Skip None entries
                    card_def = create_card(card.card_id)
                    if card_def and hasattr(card_def, 'name') and card_def.name == card_name:
                        example_card = card_def
                        break
                if example_card:
                    break

            # If found in visible zones, apply criteria
            if example_card:
                if criteria_func(example_card):
                    candidates.append(card_name)
            # If not found in visible zones, search the deck (this reveals information)
            else:
                # Check ALL cards with this name in the deck - any version that passes
                # the criteria makes this card name searchable
                for card in player.deck.cards:
                    card_def = create_card(card.card_id)
                    if card_def and hasattr(card_def, 'name') and card_def.name == card_name:
                        # Found a card with this name - check if it passes criteria
                        if criteria_func(card_def):
                            candidates.append(card_name)
                            break  # Found at least one valid version, include it
                        # Keep the first card def in case none pass (for error handling)
                        if not example_card:
                            example_card = card_def
                else:
                    # No card with this name passed criteria
                    # If we found at least one card with the name but none passed, don't include it
                    if not example_card:
                        # Can't find card definition, so we can't apply criteria
                        # Include it as a candidate anyway (conservative approach)
                        candidates.append(card_name)

    return sorted(candidates)


def generate_search_actions(
    state: GameState,
    player: PlayerState,
    card: CardInstance,
    criteria: Callable,
    count: int,
    label_template: str,
    parameter_key: str = 'target_pokemon_ids'
) -> List[Action]:
    """
    Generate atomic search actions for deck searches.

    This utility encapsulates the common pattern of:
    1. Getting searchable candidates using the Knowledge Layer
    2. Mapping those names to actual card instances in the deck
    3. Generating Action objects (including combinations if count > 1)

    Args:
        state: Current game state
        player: Player performing the search
        card: The card being played (e.g., Nest Ball, Buddy-Buddy Poffin)
        criteria: Filter function for valid search targets (e.g., is_basic_hp_70_or_less)
        count: Number of cards to search for (1 = single, 2 = pairs, etc.)
        label_template: Template for display_label. Use {name} for single,
                       {name1}, {name2} for pairs, etc.
        parameter_key: Key to use in action.parameters (default: 'target_pokemon_ids')

    Returns:
        List of Actions representing all valid search options

    Example:
        >>> # Nest Ball: Search for 1 Basic Pokémon
        >>> def is_basic(c):
        >>>     return Subtype.BASIC in c.subtypes
        >>> actions = generate_search_actions(
        >>>     state, player, nest_ball,
        >>>     criteria=is_basic,
        >>>     count=1,
        >>>     label_template="Nest Ball (Search {name})",
        >>>     parameter_key='target_pokemon_id'
        >>> )

        >>> # Buddy-Buddy Poffin: Search for up to 2 Basics with HP ≤ 70
        >>> def is_basic_hp_70_or_less(c):
        >>>     return Subtype.BASIC in c.subtypes and c.hp <= 70
        >>> actions = generate_search_actions(
        >>>     state, player, poffin,
        >>>     criteria=is_basic_hp_70_or_less,
        >>>     count=2,
        >>>     label_template="Buddy-Buddy Poffin (Search {names})"
        >>> )
    """
    actions = []

    # Check bench space (assumes this is for Pokémon search)
    bench_space = player.board.max_bench_size - player.board.get_bench_count()

    if bench_space <= 0 or player.deck.is_empty():
        return actions

    # Get searchable candidates using the Knowledge Layer (Belief Engine)
    candidate_names = get_deck_search_candidates(state, player, criteria)

    # Group cards by FUNCTIONAL ID (not just name)
    # This ensures that different versions of the same Pokemon create separate actions
    # Example: Charmander HP=70 and Charmander HP=80 get different actions
    # ISMCTS: Also include belief-based placeholders for candidates not in deck
    deck_cards_by_functional_id = {}
    for card_name in candidate_names:
        # Get all matching cards for this name that pass criteria
        matching_cards = [
            c for c in player.deck.cards
            if get_card_definition(c).name == card_name
            and criteria(get_card_definition(c))
        ]

        if matching_cards:
            # Card exists in deck - group by functional ID
            for card_instance in matching_cards:
                functional_id = player.functional_id_map.get(card_instance.card_id)

                if functional_id:
                    if functional_id not in deck_cards_by_functional_id:
                        deck_cards_by_functional_id[functional_id] = []
                    deck_cards_by_functional_id[functional_id].append(card_instance)
        elif not player.has_searched_deck:
            # ISMCTS: Belief says card might be searchable but it's not in deck
            # Only create placeholder if we can verify the card COULD pass criteria
            # (card might be in prizes - but we should verify it's the right type)
            #
            # Try to find ANY card with this name to check criteria
            # Search in order: deck, visible zones, functional_id_map
            sample_card_def = None

            # 1. Check deck (most likely location)
            for card in player.deck.cards:
                card_def = get_card_definition(card)
                if card_def and hasattr(card_def, 'name') and card_def.name == card_name:
                    sample_card_def = card_def
                    break

            # 2. Check visible zones if not found in deck
            if not sample_card_def:
                visible_zones = [
                    player.hand.cards,
                    player.discard.cards,
                    player.board.get_all_pokemon(),
                ]
                for zone in visible_zones:
                    for card in zone:
                        if card is None:
                            continue
                        card_def = get_card_definition(card)
                        if card_def and hasattr(card_def, 'name') and card_def.name == card_name:
                            sample_card_def = card_def
                            break
                    if sample_card_def:
                        break

            # 3. Check functional_id_map for any card_id that might give us the definition
            if not sample_card_def:
                for card_id, _ in player.functional_id_map.items():
                    from cards.registry import create_card
                    card_def = create_card(card_id)
                    if card_def and hasattr(card_def, 'name') and card_def.name == card_name:
                        sample_card_def = card_def
                        break

            # If we found a sample and it doesn't pass criteria, skip this belief
            if sample_card_def and not criteria(sample_card_def):
                continue  # Skip - this card type can never pass the criteria

            # Create placeholder for belief-based action (card likely in prizes)
            deck_cards_by_functional_id[card_name] = [None]

    # Generate actions based on count
    if count == 1:
        # Single search: One action per FUNCTIONAL type (not per name)
        for functional_id, deck_cards in deck_cards_by_functional_id.items():
            if deck_cards:
                target_card = deck_cards[0]

                if target_card is None:
                    # Belief-based action: card not in deck but believed to be searchable
                    # functional_id is actually the card name in this case
                    card_name = functional_id
                    target_id = f"belief:{card_name}"
                    label = label_template.replace('{name}', card_name)

                    # Build parameters with belief placeholder ID
                    if parameter_key.endswith('_ids'):
                        params = {
                            parameter_key: [target_id],
                            f'{parameter_key[:-4]}_name': card_name  # Remove '_ids', add '_name'
                        }
                    else:
                        params = {
                            parameter_key: target_id,
                            f'{parameter_key}_name': card_name  # Add name parameter for effect execution
                        }
                else:
                    # Real action: card is actually in deck
                    card_def = get_card_definition(target_card)
                    card_name = card_def.name if card_def else "Unknown"
                    label = label_template.replace('{name}', card_name)

                    # Build parameters - handle both single ID and list formats
                    if parameter_key.endswith('_ids'):
                        params = {parameter_key: [target_card.id]}
                    else:
                        params = {parameter_key: target_card.id}

                actions.append(Action(
                    action_type=ActionType.PLAY_ITEM,
                    player_id=player.player_id,
                    card_id=card.id,
                    parameters=params,
                    display_label=label
                ))

    elif count == 2:
        # Double search: Generate single + pair actions
        # Build a flat list of all valid card instances (including belief placeholders)
        all_valid_cards = []
        for functional_id, deck_cards in deck_cards_by_functional_id.items():
            all_valid_cards.extend(deck_cards)

        # Generate single search actions (search for just 1)
        # Need to handle both real cards and belief placeholders
        seen_functional_ids = set()

        for functional_id, deck_cards in deck_cards_by_functional_id.items():
            if functional_id in seen_functional_ids:
                continue
            seen_functional_ids.add(functional_id)

            target_card = deck_cards[0]

            if target_card is None:
                # Belief-based action
                card_name = functional_id
                target_id = f"belief:{card_name}"
                label = label_template.replace('{names}', card_name)

                actions.append(Action(
                    action_type=ActionType.PLAY_ITEM,
                    player_id=player.player_id,
                    card_id=card.id,
                    parameters={
                        parameter_key: [target_id],
                        f'{parameter_key[:-4]}_name': card_name
                    },
                    display_label=label
                ))
            else:
                # Real action
                card_def = get_card_definition(target_card)
                card_name = card_def.name if card_def else "Unknown"
                label = label_template.replace('{names}', card_name)

                actions.append(Action(
                    action_type=ActionType.PLAY_ITEM,
                    player_id=player.player_id,
                    card_id=card.id,
                    parameters={parameter_key: [target_card.id]},
                    display_label=label
                ))

        # Generate pair search actions (if bench has space for 2)
        if bench_space >= 2:
            # Build list of (functional_id, card_instance_or_none) tuples
            # This preserves the card name for belief placeholders
            functional_cards = []
            for functional_id, deck_cards in deck_cards_by_functional_id.items():
                for card_instance in deck_cards:
                    functional_cards.append((functional_id, card_instance))

            seen_functional_pairs = set()

            for card_pair in combinations(functional_cards, 2):
                (func_id1, card1), (func_id2, card2) = card_pair

                # Create a sorted tuple for de-duplication
                # (Charmander HP=70, Pidgey) and (Charmander HP=70, Pidgey) should be the same
                functional_pair = tuple(sorted([func_id1, func_id2]))

                # Skip if we've already created an action for this functional pair
                if functional_pair in seen_functional_pairs:
                    continue

                seen_functional_pairs.add(functional_pair)

                # Get display names and build parameters (handle belief placeholders)
                # For belief placeholders, func_id is the card name
                if card1 is None:
                    name1 = func_id1  # Card name
                    id1 = f"belief:{name1}"
                else:
                    card1_def = get_card_definition(card1)
                    name1 = card1_def.name if card1_def else "Unknown"
                    id1 = card1.id

                if card2 is None:
                    name2 = func_id2  # Card name
                    id2 = f"belief:{name2}"
                else:
                    card2_def = get_card_definition(card2)
                    name2 = card2_def.name if card2_def else "Unknown"
                    id2 = card2.id

                # Format display label
                if name1 == name2:
                    # Same name: show as "Name, Name" to indicate 2 copies
                    label = label_template.replace('{names}', f"{name1}, {name2}")
                else:
                    # Different names: sort for consistency
                    sorted_names = sorted([name1, name2])
                    label = label_template.replace('{names}', f"{sorted_names[0]}, {sorted_names[1]}")

                # Build parameters - add name hints for belief placeholders
                params = {parameter_key: [id1, id2]}
                if card1 is None or card2 is None:
                    # Add name parameters for effect execution to use
                    params[f'{parameter_key[:-4]}_names'] = [name1, name2]

                actions.append(Action(
                    action_type=ActionType.PLAY_ITEM,
                    player_id=player.player_id,
                    card_id=card.id,
                    parameters=params,
                    display_label=label
                ))

    else:
        # TODO: Implement count > 2 support using functional IDs
        # Currently no cards search for more than 2 Pokemon at once
        # When implementing, follow the same pattern:
        #   1. Generate combinations from all_valid_cards
        #   2. De-duplicate based on functional ID tuples
        #   3. Build display labels from card names
        pass

    return actions


def generate_evolution_actions(
    state: GameState,
    player: PlayerState,
    card: CardInstance,
    target_subtype: 'Subtype',
    evolution_subtype: 'Subtype',
    label_template: str,
    skip_stage: bool = False
) -> List[Action]:
    """
    Generate atomic evolution actions for evolution items (e.g., Rare Candy).

    This utility encapsulates the common pattern of:
    1. Finding valid Pokemon on the board that can evolve
    2. Finding evolution cards in hand
    3. Generating Action objects for each valid pair

    Args:
        state: Current game state
        player: Player performing the evolution
        card: The item card being played (e.g., Rare Candy)
        target_subtype: Subtype of Pokemon to evolve (e.g., Subtype.BASIC)
        evolution_subtype: Subtype of evolution card (e.g., Subtype.STAGE_2)
        label_template: Template for display_label. Use {target} and {evolution}.
        skip_stage: If True, allows skipping evolution stages (Rare Candy)

    Returns:
        List of Actions representing all valid evolution pairs

    Example:
        >>> # Rare Candy: Evolve Basic -> Stage 2
        >>> actions = generate_evolution_actions(
        >>>     state, player, rare_candy,
        >>>     target_subtype=Subtype.BASIC,
        >>>     evolution_subtype=Subtype.STAGE_2,
        >>>     label_template="Rare Candy: Evolve {target} into {evolution}",
        >>>     skip_stage=True
        >>> )
    """
    from models import Subtype
    from cards.base import PokemonCard

    actions = []

    # Get all Pokemon on board (active + bench)
    board_pokemon = player.board.get_all_pokemon()

    # Get all evolution cards of the specified subtype from hand
    # Group by functional ID to avoid duplicate actions for identical cards
    evolution_cards_by_functional_id = {}
    for hand_card in player.hand.cards:
        if hand_card.id == card.id:
            continue  # Skip the item card itself
        card_def = get_card_definition(hand_card)
        if (isinstance(card_def, PokemonCard) and
            hasattr(card_def, 'subtypes') and evolution_subtype in card_def.subtypes):
            # Use functional ID to deduplicate identical cards
            functional_id = player.functional_id_map.get(hand_card.card_id, hand_card.card_id)
            if functional_id not in evolution_cards_by_functional_id:
                evolution_cards_by_functional_id[functional_id] = (hand_card, card_def)

    # Convert to list for iteration
    evolution_cards = list(evolution_cards_by_functional_id.values())

    # Find valid (target, evolution) pairs
    for target_pokemon in board_pokemon:
        # Check evolution sickness (must have been in play for at least 1 turn)
        if target_pokemon.turns_in_play == 0:
            continue

        target_def = get_card_definition(target_pokemon)

        # Check if target is the correct subtype
        if not (isinstance(target_def, PokemonCard) and
                hasattr(target_def, 'subtypes') and target_subtype in target_def.subtypes):
            continue

        # Find evolution cards that can evolve from this target
        for evolution_card, evolution_def in evolution_cards:
            # Validate evolution chain
            if not hasattr(evolution_def, 'evolves_from') or not evolution_def.evolves_from:
                continue

            # Check if this evolution is valid for the target
            is_valid_evolution = False

            if skip_stage:
                # Rare Candy: Check if the Stage 2's intermediate stage can evolve from the target
                # Example: Pidgeot (Stage 2) evolves from Pidgeotto (Stage 1)
                #          We need to check if Pidgeotto can evolve from Pidgey (the target Basic)

                # The Stage 2's evolves_from field points to the Stage 1
                # We need to verify that Stage 1 can evolve from the target Basic

                # Since we're skipping a stage, evolution_def.evolves_from should NOT equal target_def.name
                # (if it did, it would be a direct evolution, not skipping)
                if evolution_def.evolves_from != target_def.name:
                    # Now check if there exists a card with name=evolution_def.evolves_from
                    # that evolves from target_def.name

                    # Check the evolution chain by looking for intermediate Stage 1
                    intermediate_name = evolution_def.evolves_from

                    # Use a helper function to check if the intermediate exists
                    is_valid_evolution = _check_evolution_chain(intermediate_name, target_def.name)
            else:
                # Normal evolution: Direct check
                is_valid_evolution = (evolution_def.evolves_from == target_def.name)

            if is_valid_evolution:
                label = label_template.format(
                    target=target_def.name,
                    evolution=evolution_def.name
                )

                actions.append(Action(
                    action_type=ActionType.PLAY_ITEM,
                    player_id=player.player_id,
                    card_id=card.id,
                    parameters={
                        'target_pokemon_id': target_pokemon.id,
                        'evolution_card_id': evolution_card.id
                    },
                    display_label=label
                ))

    return actions

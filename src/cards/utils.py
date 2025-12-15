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
    # Check knowledge state
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
                    card_def = create_card(card.card_id)
                    if card_def and hasattr(card_def, 'name') and card_def.name == card_name:
                        example_card = card_def
                        break
                if example_card:
                    break

            # If not found in visible zones, search the deck (this reveals information)
            if not example_card:
                for card in player.deck.cards:
                    card_def = create_card(card.card_id)
                    if card_def and hasattr(card_def, 'name') and card_def.name == card_name:
                        example_card = card_def
                        break

            # Apply filter if we found the card definition
            if example_card:
                if criteria_func(example_card):
                    candidates.append(card_name)
            else:
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

    # Map candidate names to actual card instances in deck
    deck_cards_by_name = {}
    for card_name in candidate_names:
        matching_cards = [
            c for c in player.deck.cards
            if get_card_definition(c).name == card_name
        ]
        if matching_cards:
            deck_cards_by_name[card_name] = matching_cards

    # Generate actions based on count
    if count == 1:
        # Single search: One action per candidate
        for card_name, deck_cards in deck_cards_by_name.items():
            if deck_cards:
                # For single searches, use the first matching card
                target_card = deck_cards[0]

                # Format label
                label = label_template.replace('{name}', card_name)

                # Build parameters - handle both single ID and list formats
                if parameter_key.endswith('_ids'):
                    # List format (e.g., 'target_pokemon_ids')
                    params = {parameter_key: [target_card.id]}
                else:
                    # Single ID format (e.g., 'target_pokemon_id')
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
        # First, generate single search actions (search for just 1)
        for card_name, deck_cards in deck_cards_by_name.items():
            if deck_cards:
                target_card = deck_cards[0]

                # Format label for single search
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
            for name_pair in combinations(candidate_names, 2):
                name1, name2 = name_pair

                # Get actual cards for each name
                card1 = deck_cards_by_name.get(name1, [None])[0]
                card2 = deck_cards_by_name.get(name2, [None])[0]

                if card1 and card2:
                    # Format label for pair search
                    label = label_template.replace('{names}', f"{name1}, {name2}")

                    actions.append(Action(
                        action_type=ActionType.PLAY_ITEM,
                        player_id=player.player_id,
                        card_id=card.id,
                        parameters={parameter_key: [card1.id, card2.id]},
                        display_label=label
                    ))

    else:
        # For count > 2, generate all possible combinations
        # (Not currently used, but included for completeness)
        for name_combo in combinations(candidate_names, min(count, len(candidate_names))):
            # Get actual cards for each name
            target_cards = []
            for name in name_combo:
                cards = deck_cards_by_name.get(name, [])
                if cards:
                    target_cards.append(cards[0])

            if len(target_cards) == len(name_combo):
                # All cards found - create action
                names_str = ', '.join(name_combo)
                label = label_template.replace('{names}', names_str)

                actions.append(Action(
                    action_type=ActionType.PLAY_ITEM,
                    player_id=player.player_id,
                    card_id=card.id,
                    parameters={parameter_key: [c.id for c in target_cards]},
                    display_label=label
                ))

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
    evolution_cards = []
    for hand_card in player.hand.cards:
        if hand_card.id == card.id:
            continue  # Skip the item card itself
        card_def = get_card_definition(hand_card)
        if (isinstance(card_def, PokemonCard) and
            hasattr(card_def, 'subtypes') and evolution_subtype in card_def.subtypes):
            evolution_cards.append((hand_card, card_def))

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
            # For now, create action for all evolution cards
            # (Engine will validate evolution chain)
            # TODO: Proper evolution chain validation
            if hasattr(evolution_def, 'evolves_from'):
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

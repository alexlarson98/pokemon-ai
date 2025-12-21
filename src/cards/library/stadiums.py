"""
Shared Stadium Card Logic Library

This module contains reusable stadium implementations using the
Unified Ability Schema and Stack Architecture.

Stadium cards have special behaviors:
1. Only one Stadium can be in play at a time
2. Playing a new Stadium discards the old one
3. Cannot play a Stadium with the same name as the current one
4. Stadiums can have passive effects, modifiers, and hooks

Each stadium typically has:
- Play action (activatable): Places the stadium
- Effect function: Called when stadium is played, may set up hooks/modifiers
- Optional: Continuous effects registered via active_effects
"""

from typing import List, Optional
from models import (
    GameState, CardInstance, Action, ActionType, Subtype, PlayerState,
    SelectFromZoneStep, ZoneType, SelectionPurpose, ActiveEffect, EffectSource
)
from cards.factory import get_card_definition


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def has_tera_pokemon_in_play(state: GameState, player_id: int) -> bool:
    """
    Check if a player has any Tera Pokemon in play (Active or Bench).

    Args:
        state: Current game state
        player_id: Player to check

    Returns:
        True if player has at least one Tera Pokemon in play
    """
    player = state.get_player(player_id)

    for pokemon in player.board.get_all_pokemon():
        card_def = get_card_definition(pokemon)
        if card_def and hasattr(card_def, 'subtypes'):
            if Subtype.TERA in card_def.subtypes:
                return True

    return False


def get_max_bench_size_for_player(state: GameState, player_id: int) -> int:
    """
    Calculate maximum bench size for a player considering Area Zero Underdepths.

    Default: 5
    With Area Zero Underdepths + Tera Pokemon in play: 8

    Args:
        state: Current game state
        player_id: Player to check

    Returns:
        Maximum bench size (5 or 8)
    """
    # Check if Area Zero Underdepths is in play
    if state.stadium is None:
        return 5

    card_def = get_card_definition(state.stadium)
    if card_def is None or card_def.name != "Area Zero Underdepths":
        return 5

    # Stadium is Area Zero Underdepths - check for Tera Pokemon
    if has_tera_pokemon_in_play(state, player_id):
        return 8

    return 5


# ============================================================================
# AREA ZERO UNDERDEPTHS
# ============================================================================

# Card IDs: sv7-131, sv7-174, sv8pt5-94

def area_zero_underdepths_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate Area Zero Underdepths play action.

    Stadium: Area Zero Underdepths
    - Each player who has any Tera Pokemon in play can have up to 8 Pokemon on their Bench.
    - If a player no longer has any Tera Pokemon in play, that player discards Pokemon
      from their Bench until they have 5.
    - When this card leaves play, both players discard Pokemon from their Bench until
      they have 5, and the player who played this card discards first.

    Playability: Can always be played (standard Stadium rules checked by engine)

    Args:
        state: Current game state
        card: Area Zero Underdepths CardInstance
        player: PlayerState of the player

    Returns:
        List with single play action
    """
    return [Action(
        action_type=ActionType.PLAY_STADIUM,
        player_id=player.player_id,
        card_id=card.id,
        display_label="Area Zero Underdepths (8-bench for Tera)"
    )]


def area_zero_underdepths_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Area Zero Underdepths placement effect.

    When played:
    1. Stadium is placed (handled by engine)
    2. Bench size limits are calculated dynamically via get_max_bench_size_for_player()

    The continuous effect (8-bench for Tera players) is an intrinsic state
    that is checked dynamically whenever bench space is queried.

    Args:
        state: Current game state
        card: Area Zero Underdepths CardInstance
        action: Play action

    Returns:
        Modified GameState (no immediate changes - effect is continuous)
    """
    # The stadium placement is handled by _apply_play_stadium in engine
    # The bench size modification is handled dynamically by get_max_bench_size_for_player()
    # which checks if Area Zero Underdepths is in play and if player has Tera Pokemon
    return state


def area_zero_underdepths_bench_check(state: GameState) -> GameState:
    """
    Check and enforce bench size limits when Tera status changes.

    Called by the engine when:
    1. A Tera Pokemon is knocked out
    2. A Tera Pokemon is returned to hand/deck
    3. Area Zero Underdepths leaves play

    If a player has no Tera Pokemon and more than 5 on bench,
    they must discard down to 5.

    Args:
        state: Current game state

    Returns:
        Modified GameState (may push SelectFromZoneStep for discard)
    """
    # Check if Area Zero Underdepths is in play
    if state.stadium is None:
        return state

    card_def = get_card_definition(state.stadium)
    if card_def is None or card_def.name != "Area Zero Underdepths":
        return state

    # Check each player
    for player in state.players:
        max_size = get_max_bench_size_for_player(state, player.player_id)
        current_count = player.board.get_bench_count()

        if current_count > max_size:
            # Player needs to discard Pokemon from bench
            discard_count = current_count - max_size

            # Push step for player to select Pokemon to discard
            discard_step = SelectFromZoneStep(
                source_card_id=state.stadium.id,
                source_card_name="Area Zero Underdepths",
                player_id=player.player_id,
                purpose=SelectionPurpose.DISCARD_FROM_PLAY,
                zone=ZoneType.BENCH,
                count=discard_count,
                min_count=discard_count,
                exact_count=True,
                filter_criteria={},  # Any Pokemon on bench
                on_complete_callback="area_zero_discard_bench"
            )

            state.push_step(discard_step)
            player.board.max_bench_size = max_size

    return state


def area_zero_underdepths_on_leave_hook(state: GameState, stadium: CardInstance) -> GameState:
    """
    Hook triggered when Area Zero Underdepths leaves play.

    This hook is registered with trigger='on_stadium_leave' and called
    by the engine when the stadium is replaced or discarded.

    When this stadium leaves play:
    1. Both players discard Pokemon from bench until they have 5
    2. The player who played this stadium discards first

    Args:
        state: Current game state
        stadium: The Area Zero Underdepths card that is leaving

    Returns:
        Modified GameState with discard steps pushed
    """
    stadium_owner_id = stadium.owner_id

    # Reset both players to 5 max bench
    for player in state.players:
        player.board.max_bench_size = 5

    # Determine order: stadium owner discards first
    player_order = [stadium_owner_id, 1 - stadium_owner_id]

    # Push steps in reverse order (LIFO stack)
    for player_id in reversed(player_order):
        player = state.get_player(player_id)
        current_count = player.board.get_bench_count()

        if current_count > 5:
            discard_count = current_count - 5

            discard_step = SelectFromZoneStep(
                source_card_id=stadium.id,
                source_card_name="Area Zero Underdepths",
                player_id=player_id,
                purpose=SelectionPurpose.DISCARD_FROM_PLAY,
                zone=ZoneType.BENCH,
                count=discard_count,
                min_count=discard_count,
                exact_count=True,
                filter_criteria={},
                on_complete_callback="area_zero_discard_bench"
            )

            state.push_step(discard_step)

    return state

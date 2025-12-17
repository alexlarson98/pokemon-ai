"""
Pokémon TCG Engine - Shrouded Fable Card Logic
Set Code: SFA (sv6pt5)
"""

from typing import List
from itertools import combinations
from models import GameState, CardInstance, Action, ActionType, PlayerState
from actions import apply_damage, calculate_damage
from cards.factory import get_card_definition


# ============================================================================
# DUSKULL - COME AND GET YOU & MUMBLE
# ============================================================================

def duskull_come_and_get_you_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Duskull's "Come and Get You" attack.

    Attack: Come and Get You [P]
    Put up to 3 Duskull from your discard pile onto your Bench.

    Args:
        state: Current game state
        card: Duskull CardInstance
        player: PlayerState of the attacking player

    Returns:
        List of attack actions with discard target options
    """
    actions = []

    # Check bench space
    bench_space = player.board.max_bench_size - player.board.get_bench_count()

    # Find Duskull cards in discard pile
    duskull_in_discard = []
    for discard_card in player.discard.cards:
        card_def = get_card_definition(discard_card)
        if card_def and card_def.name == "Duskull":
            duskull_in_discard.append(discard_card)

    # If no bench space or no Duskull in discard, attack can still be used (finds nothing)
    if bench_space <= 0 or not duskull_in_discard:
        return [Action(
            action_type=ActionType.ATTACK,
            player_id=player.player_id,
            card_id=card.id,
            attack_name="Come and Get You",
            parameters={'target_duskull_ids': []},
            display_label="Come and Get You (find nothing)"
        )]

    # Calculate max Duskull we can retrieve (min of bench space, discard count, and 3)
    max_targets = min(bench_space, len(duskull_in_discard), 3)

    # Option to find nothing (player may choose to fail)
    actions.append(Action(
        action_type=ActionType.ATTACK,
        player_id=player.player_id,
        card_id=card.id,
        attack_name="Come and Get You",
        parameters={'target_duskull_ids': []},
        display_label="Come and Get You (find nothing)"
    ))

    # Generate actions for 1, 2, or 3 Duskull
    # Since all Duskull are functionally identical, we only need one action per count
    for count in range(1, max_targets + 1):
        # Get the first 'count' Duskull from discard
        target_ids = [d.id for d in duskull_in_discard[:count]]

        if count == 1:
            label = "Come and Get You (1 Duskull)"
        else:
            label = f"Come and Get You ({count} Duskull)"

        actions.append(Action(
            action_type=ActionType.ATTACK,
            player_id=player.player_id,
            card_id=card.id,
            attack_name="Come and Get You",
            parameters={'target_duskull_ids': target_ids},
            display_label=label
        ))

    return actions


def duskull_come_and_get_you_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Duskull's "Come and Get You" attack effect.

    Put up to 3 Duskull from your discard pile onto your Bench.

    Args:
        state: Current game state
        card: Duskull CardInstance
        action: Attack action with target_duskull_ids parameter

    Returns:
        Modified GameState
    """
    player = state.get_player(action.player_id)

    # Get target Duskull IDs from action parameters
    target_ids = action.parameters.get('target_duskull_ids', [])

    # Put each target Duskull onto the bench
    for target_id in target_ids:
        # Check if bench is still available
        if player.board.get_bench_count() >= player.board.max_bench_size:
            break

        # Find the card in discard
        target_card = None
        for discard_card in player.discard.cards:
            if discard_card.id == target_id:
                target_card = discard_card
                break

        if target_card:
            # Remove from discard
            player.discard.remove_card(target_card.id)
            # Add to bench
            player.board.add_to_bench(target_card)
            # Initialize turns in play
            target_card.turns_in_play = 0

    return state


def duskull_mumble_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Duskull's "Mumble" attack.

    Attack: Mumble [PP]
    30 damage. No additional effects.

    Args:
        state: Current game state
        card: Duskull CardInstance
        player: PlayerState of the attacking player

    Returns:
        List with single attack action
    """
    return [Action(
        action_type=ActionType.ATTACK,
        player_id=player.player_id,
        card_id=card.id,
        attack_name="Mumble",
        display_label="Mumble - 30 Dmg"
    )]


def duskull_mumble_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Duskull's "Mumble" attack effect.

    Deals 30 damage to opponent's Active Pokémon.

    Args:
        state: Current game state
        card: Duskull CardInstance
        action: Attack action

    Returns:
        Modified GameState
    """
    opponent = state.get_opponent()

    # Deal 30 damage to opponent's Active Pokémon
    if opponent.board.active_spot:
        final_damage = calculate_damage(
            state=state,
            attacker=card,
            defender=opponent.board.active_spot,
            base_damage=30,
            attack_name="Mumble"
        )

        state = apply_damage(
            state=state,
            target=opponent.board.active_spot,
            damage=final_damage,
            is_attack_damage=True,
            attacker=card
        )

    return state


# ============================================================================
# SV6PT5 LOGIC REGISTRY
# ============================================================================

SV6PT5_LOGIC = {
    # Duskull - Come and Get You & Mumble
    "sv6pt5-18": {
        "Come and Get You": {
            "generator": duskull_come_and_get_you_actions,
            "effect": duskull_come_and_get_you_effect,
        },
        "Mumble": {
            "generator": duskull_mumble_actions,
            "effect": duskull_mumble_effect,
        },
    },
    "sv6pt5-68": {
        "Come and Get You": {
            "generator": duskull_come_and_get_you_actions,
            "effect": duskull_come_and_get_you_effect,
        },
        "Mumble": {
            "generator": duskull_mumble_actions,
            "effect": duskull_mumble_effect,
        },
    },
}

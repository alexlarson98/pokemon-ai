"""
Pokémon TCG Engine - Surging Sparks Card Logic
Set Code: SSP
"""

from typing import List
from models import (
    GameState, CardInstance, Action, ActionType, PlayerState,
    SelectFromZoneStep, ZoneType, SelectionPurpose
)
from actions import apply_damage, calculate_damage
from ..library.trainers import night_stretcher_actions, night_stretcher_effect


# ============================================================================
# KLEFKI - VERSION 2: STICK 'N' DRAW + HOOK (sv8-128)
# ============================================================================

def klefki_stick_n_draw_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Klefki's "Stick 'n' Draw" attack.

    Attack: Stick 'n' Draw [C]
    Discard a card from your hand. If you do, draw 2 cards.

    The attack always generates an action - the hand check happens during resolution.
    If hand is empty, player can still use the attack but nothing happens.

    Args:
        state: Current game state
        card: Klefki CardInstance
        player: PlayerState of the attacking player

    Returns:
        List with single attack action
    """
    return [Action(
        action_type=ActionType.ATTACK,
        player_id=player.player_id,
        card_id=card.id,
        attack_name="Stick 'n' Draw",
        display_label="Stick 'n' Draw (discard 1, draw 2)"
    )]


def klefki_stick_n_draw_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Klefki's "Stick 'n' Draw" attack effect.

    Discard a card from your hand. If you do, draw 2 cards.

    Uses Stack Architecture:
    1. Push SelectFromZoneStep to select a card to discard
    2. On complete callback draws 2 cards

    Args:
        state: Current game state
        card: Klefki CardInstance
        action: Attack action

    Returns:
        Modified GameState with SelectFromZoneStep pushed
    """
    player = state.get_player(action.player_id)

    # Check if player has cards in hand to discard
    if player.hand.is_empty():
        # No cards to discard - attack does nothing
        return state

    # Push SelectFromZoneStep to choose a card to discard
    select_step = SelectFromZoneStep(
        source_card_id=card.id,
        source_card_name="Stick 'n' Draw",
        player_id=player.player_id,
        purpose=SelectionPurpose.DISCARD_COST,
        zone=ZoneType.HAND,
        count=1,
        min_count=1,  # Must discard 1 to get the effect
        exact_count=True,
        filter_criteria={},  # Any card
        on_complete_callback="klefki_stick_n_draw_complete"
    )

    state.push_step(select_step)
    return state


def klefki_hook_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Klefki's "Hook" attack.

    Attack: Hook [C] 20
    No additional effects.

    Args:
        state: Current game state
        card: Klefki CardInstance
        player: PlayerState of the attacking player

    Returns:
        List with single attack action
    """
    return [Action(
        action_type=ActionType.ATTACK,
        player_id=player.player_id,
        card_id=card.id,
        attack_name="Hook",
        display_label="Hook - 20 Dmg"
    )]


def klefki_hook_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Klefki's "Hook" attack effect.

    Deals 20 damage to opponent's Active Pokemon. No additional effects.

    Args:
        state: Current game state
        card: Klefki CardInstance
        action: Attack action

    Returns:
        Modified GameState
    """
    opponent = state.get_opponent()

    if opponent.board.active_spot:
        final_damage = calculate_damage(
            state=state,
            attacker=card,
            defender=opponent.board.active_spot,
            base_damage=20,
            attack_name="Hook"
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
# SV8 LOGIC REGISTRY (Unified Schema)
# ============================================================================

SV8_LOGIC = {
    # Klefki - Version 2 (Stick 'n' Draw + Hook)
    "sv8-128": {
        "Stick 'n' Draw": {
            "category": "attack",
            "generator": klefki_stick_n_draw_actions,
            "effect": klefki_stick_n_draw_effect,
        },
        "Hook": {
            "category": "attack",
            "generator": klefki_hook_actions,
            "effect": klefki_hook_effect,
        },
    },

    # Night Stretcher - Item
    "sv8-251": {
        "Play Night Stretcher": {
            "category": "activatable",
            "generator": night_stretcher_actions,
            "effect": night_stretcher_effect,
        },
    },
}

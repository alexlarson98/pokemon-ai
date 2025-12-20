"""
Pokémon TCG Engine - Temporal Forces Card Logic
Set Code: TEF (sv5)
"""

from typing import List
from models import GameState, CardInstance, Action, ActionType, PlayerState
from actions import apply_damage, calculate_damage
from ..library.trainers import buddy_buddy_poffin_effect, buddy_buddy_poffin_actions


# ============================================================================
# HOOTHOOT - VERSION 1: SILENT WING (sv5-126)
# ============================================================================

def hoothoot_silent_wing_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Hoothoot's "Silent Wing" attack.

    Attack: Silent Wing [CC]
    20 damage. Your opponent reveals their hand.

    Args:
        state: Current game state
        card: Hoothoot CardInstance
        player: PlayerState of the attacking player

    Returns:
        List with single attack action
    """
    return [Action(
        action_type=ActionType.ATTACK,
        player_id=player.player_id,
        card_id=card.id,
        attack_name="Silent Wing",
        display_label="Silent Wing - 20 Dmg (Reveal Opponent's Hand)"
    )]


def hoothoot_silent_wing_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Hoothoot's "Silent Wing" attack effect.

    Deals 20 damage to opponent's Active Pokémon and reveals opponent's hand.

    Args:
        state: Current game state
        card: Hoothoot CardInstance
        action: Attack action

    Returns:
        Modified GameState
    """
    opponent = state.get_opponent()

    # Deal 20 damage to opponent's Active Pokémon
    if opponent.board.active_spot:
        final_damage = calculate_damage(
            state=state,
            attacker=card,
            defender=opponent.board.active_spot,
            base_damage=20,
            attack_name="Silent Wing"
        )

        state = apply_damage(
            state=state,
            target=opponent.board.active_spot,
            damage=final_damage,
            is_attack_damage=True,
            attacker=card
        )

    # Reveal opponent's hand (mark all cards as revealed)
    for hand_card in opponent.hand.cards:
        hand_card.is_revealed = True

    return state


# ============================================================================
# SV5 LOGIC REGISTRY
# ============================================================================

SV5_LOGIC = {
    # Buddy-Buddy Poffin (Trainer)
    "sv5-144": {
        "Play Buddy-Buddy Poffin": {
            "category": "activatable",
            "generator": buddy_buddy_poffin_actions,
            "effect": buddy_buddy_poffin_effect,
        },
    },

    # Hoothoot - Version 1 (Silent Wing)
    "sv5-126": {
        "Silent Wing": {
            "category": "attack",
            "generator": hoothoot_silent_wing_actions,
            "effect": hoothoot_silent_wing_effect,
        },
    },
}

"""
Pokémon TCG Engine - Stellar Crown Card Logic
Set Code: SCR (sv7)
"""

from typing import List
from models import GameState, CardInstance, Action, ActionType, PlayerState
from actions import apply_damage, calculate_damage, coin_flip_multiple


# ============================================================================
# HOOTHOOT - VERSION 2: TRIPLE STAB (sv7-114)
# ============================================================================

def hoothoot_triple_stab_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Hoothoot's "Triple Stab" attack.

    Attack: Triple Stab [C]
    Flip 3 coins. This attack does 10 damage for each heads.

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
        attack_name="Triple Stab",
        display_label="Triple Stab - 10x (Flip 3 coins)"
    )]


def hoothoot_triple_stab_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Hoothoot's "Triple Stab" attack effect.

    Flip 3 coins. This attack does 10 damage for each heads.

    Args:
        state: Current game state
        card: Hoothoot CardInstance
        action: Attack action

    Returns:
        Modified GameState
    """
    opponent = state.get_opponent()

    # Flip 3 coins
    coin_results = coin_flip_multiple(3)
    heads_count = sum(coin_results)

    # Calculate damage: 10 per heads
    base_damage = 10 * heads_count

    # Deal damage to opponent's Active Pokémon (if any damage)
    if base_damage > 0 and opponent.board.active_spot:
        final_damage = calculate_damage(
            state=state,
            attacker=card,
            defender=opponent.board.active_spot,
            base_damage=base_damage,
            attack_name="Triple Stab"
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
# SV7 LOGIC REGISTRY
# ============================================================================

SV7_LOGIC = {
    # Hoothoot - Version 2 (Triple Stab)
    "sv7-114": {
        "Triple Stab": {
            "category": "attack",
            "generator": hoothoot_triple_stab_actions,
            "effect": hoothoot_triple_stab_effect,
        },
    },
}

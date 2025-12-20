"""
Pokémon TCG Engine - Scarlet & Violet Base Set Card Logic
Set Code: SVI
"""

from typing import List
from models import GameState, CardInstance, Action, ActionType, PlayerState
from actions import apply_damage, calculate_damage
from cards.library.trainers import (
    nest_ball_effect,
    nest_ball_actions,
    ultra_ball_effect,
    ultra_ball_actions,
)


# ============================================================================
# KLEFKI - VERSION 1: MISCHIEVOUS LOCK (PASSIVE) + JOUST (sv1-96)
# ============================================================================

def klefki_mischievous_lock_condition(state: GameState, card: CardInstance) -> bool:
    """
    Condition checker for Klefki's "Mischievous Lock" ability.

    Ability: Mischievous Lock
    As long as this Pokemon is in the Active Spot, Basic Pokemon in play
    (both yours and your opponent's) have no Abilities, except for Mischievous Lock.

    Returns True if Klefki is in the Active Spot.

    Args:
        state: Current game state
        card: Klefki CardInstance

    Returns:
        True if Klefki is in the Active Spot, False otherwise
    """
    # Get the owner's active Pokemon
    owner = state.get_player(card.owner_id)
    if owner.board.active_spot and owner.board.active_spot.id == card.id:
        return True
    return False


def klefki_mischievous_lock_effect(
    state: GameState,
    klefki_card: CardInstance,
    target_card: CardInstance,
    ability_name: str
) -> bool:
    """
    Effect applier for Klefki's "Mischievous Lock" ability.

    Checks if a target Pokemon's ability should be locked.
    Returns True if the ability should be blocked.

    Args:
        state: Current game state
        klefki_card: The Klefki CardInstance with Mischievous Lock
        target_card: The Pokemon whose ability is being checked
        ability_name: The name of the ability being checked

    Returns:
        True if the ability should be blocked, False if allowed
    """
    from cards.registry import create_card

    # Mischievous Lock doesn't block itself
    if ability_name == "Mischievous Lock":
        return False

    # Get the target card's definition to check if it's a Basic Pokemon
    target_def = create_card(target_card.card_id)
    if not target_def:
        return False

    # Check if target is a Basic Pokemon
    subtypes = getattr(target_def, 'subtypes', [])
    if 'Basic' in subtypes:
        # Block this Basic Pokemon's ability
        return True

    # Not a Basic - ability is allowed
    return False


def klefki_joust_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Klefki's "Joust" attack.

    Attack: Joust [C] 10
    Before doing damage, discard all Pokemon Tools from your opponent's Active Pokemon.

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
        attack_name="Joust",
        display_label="Joust - 10 Dmg (discard opponent's tools)"
    )]


def klefki_joust_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Klefki's "Joust" attack effect.

    Before doing damage, discard all Pokemon Tools from opponent's Active Pokemon.
    Then deal 10 damage.

    Args:
        state: Current game state
        card: Klefki CardInstance
        action: Attack action

    Returns:
        Modified GameState
    """
    opponent = state.get_opponent()

    if opponent.board.active_spot:
        defender = opponent.board.active_spot

        # Step 1: Discard all Pokemon Tools from opponent's Active Pokemon
        if defender.attached_tools:
            for tool in defender.attached_tools:
                opponent.discard.add_card(tool)
            defender.attached_tools = []

        # Step 2: Deal 10 damage to opponent's Active Pokemon
        final_damage = calculate_damage(
            state=state,
            attacker=card,
            defender=defender,
            base_damage=10,
            attack_name="Joust"
        )

        state = apply_damage(
            state=state,
            target=defender,
            damage=final_damage,
            is_attack_damage=True,
            attacker=card
        )

    return state


# ============================================================================
# SV1 LOGIC REGISTRY (Unified Schema)
# ============================================================================

SV1_LOGIC = {
    # Klefki - Version 1 (Mischievous Lock passive + Joust attack)
    "sv1-96": {
        "Mischievous Lock": {
            "category": "passive",
            "condition_type": "in_active_spot",
            "effect_type": "ability_lock",
            "scope": "all_basic_pokemon",
            "condition": klefki_mischievous_lock_condition,
            "effect": klefki_mischievous_lock_effect,
        },
        "Joust": {
            "category": "attack",
            "generator": klefki_joust_actions,
            "effect": klefki_joust_effect,
        },
    },

    "sv1-181": {  # Nest Ball
        "Play Nest Ball": {
            "category": "activatable",
            "generator": nest_ball_actions,
            "effect": nest_ball_effect,
        },
    },
    "sv1-196": {  # Ultra Ball
        "Play Ultra Ball": {
            "category": "activatable",
            "generator": ultra_ball_actions,
            "effect": ultra_ball_effect,
        },
    },
}

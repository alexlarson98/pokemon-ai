"""
Pokémon TCG Engine - Stellar Crown Card Logic
Set Code: SCR (sv7)
"""

from typing import List
from models import (
    GameState, CardInstance, Action, ActionType, PlayerState,
    SearchDeckStep, ZoneType, SelectionPurpose
)
from actions import apply_damage, calculate_damage, coin_flip_multiple

# Import Noctowl Version 1 from svp (reprint)
from .svp import (
    noctowl_jewel_seeker_hook,
    noctowl_speed_wing_actions,
    noctowl_speed_wing_effect,
)

# Import Terapagos ex Version 1 from svp (reprint)
from .svp import (
    terapagos_ex_unified_beatdown_actions,
    terapagos_ex_unified_beatdown_effect,
    terapagos_ex_crown_opal_actions,
    terapagos_ex_crown_opal_effect,
)


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
# FAN ROTOM - FAN CALL + ASSAULT LANDING (sv7-118)
# ============================================================================

def fan_rotom_fan_call_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Fan Rotom's "Fan Call" ability.

    Ability: Fan Call
    Once during your first turn, you may search your deck for up to 3 Colorless
    Pokemon with 100 HP or less, reveal them, and put them into your hand.
    Then, shuffle your deck. You can't use more than 1 Fan Call Ability during your turn.

    RESTRICTIONS:
    1. Only usable on player's first turn (turn_count == 1 going first, or turn_count == 2 going second)
    2. Only one Fan Call can be used per turn globally
    3. Each Fan Rotom can only use Fan Call once per turn

    Args:
        state: Current game state
        card: Fan Rotom CardInstance
        player: PlayerState of the owner

    Returns:
        List with ability action if available, empty list otherwise
    """
    # Check if this is the player's first turn
    # Going first: turn 1. Going second: turn 2 (their first action turn)
    is_first_turn = False
    if state.starting_player_id == player.player_id:
        # This player went first - their first turn is turn_count == 1
        is_first_turn = state.turn_count == 1
    else:
        # This player went second - their first turn is turn_count == 2
        is_first_turn = state.turn_count == 2

    if not is_first_turn:
        return []

    # Check global restriction: Only one Fan Call per turn across ALL Fan Rotom
    if state.turn_metadata.get('fan_call_used', False):
        return []

    # Check if this specific card has already used Fan Call this turn
    if "Fan Call" in card.abilities_used_this_turn:
        return []

    # Check if deck is empty
    if player.deck.is_empty():
        return []

    return [Action(
        action_type=ActionType.USE_ABILITY,
        player_id=player.player_id,
        card_id=card.id,
        ability_name="Fan Call",
        display_label="Fan Call - Search up to 3 Colorless Pokemon (HP ≤ 100)"
    )]


def fan_rotom_fan_call_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Fan Rotom's "Fan Call" ability effect.

    Search your deck for up to 3 Colorless Pokemon with 100 HP or less,
    reveal them, and put them into your hand. Then, shuffle your deck.

    Args:
        state: Current game state
        card: Fan Rotom CardInstance
        action: Ability action

    Returns:
        Modified GameState with SearchDeckStep pushed
    """
    player = state.get_player(action.player_id)

    # Mark as used globally (no other Fan Call can be used this turn)
    state.turn_metadata['fan_call_used'] = True
    card.abilities_used_this_turn.add("Fan Call")

    # Push SearchDeckStep for up to 3 Colorless Pokemon with HP <= 100
    if not player.deck.is_empty():
        search_step = SearchDeckStep(
            source_card_id=card.id,
            source_card_name="Fan Call",
            player_id=player.player_id,
            purpose=SelectionPurpose.SEARCH_TARGET,
            count=3,
            min_count=0,  # "may" - can choose not to take any cards
            destination=ZoneType.HAND,
            filter_criteria={
                'supertype': 'Pokemon',
                'pokemon_type': 'Colorless',
                'max_hp': 100
            },
            shuffle_after=True,
            reveal_cards=True
        )

        state.push_step(search_step)

    return state


def fan_rotom_assault_landing_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Fan Rotom's "Assault Landing" attack.

    Attack: Assault Landing [C]
    70 damage. If there is no Stadium in play, this attack does nothing.

    Args:
        state: Current game state
        card: Fan Rotom CardInstance
        player: PlayerState of the attacking player

    Returns:
        List with single attack action
    """
    return [Action(
        action_type=ActionType.ATTACK,
        player_id=player.player_id,
        card_id=card.id,
        attack_name="Assault Landing",
        display_label="Assault Landing - 70 Dmg (requires Stadium)"
    )]


def fan_rotom_assault_landing_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Fan Rotom's "Assault Landing" attack effect.

    Deals 70 damage to opponent's Active Pokémon.
    If there is no Stadium in play, this attack does nothing.

    Args:
        state: Current game state
        card: Fan Rotom CardInstance
        action: Attack action

    Returns:
        Modified GameState
    """
    # Check if there is a Stadium in play
    if state.stadium is None:
        # No Stadium - attack does nothing
        return state

    opponent = state.get_opponent()

    # Deal 70 damage to opponent's Active Pokémon
    if opponent.board.active_spot:
        final_damage = calculate_damage(
            state=state,
            attacker=card,
            defender=opponent.board.active_spot,
            base_damage=70,
            attack_name="Assault Landing"
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

    # Fan Rotom - Fan Call + Assault Landing
    "sv7-118": {
        "Fan Call": {
            "category": "activatable",
            "generator": fan_rotom_fan_call_actions,
            "effect": fan_rotom_fan_call_effect,
        },
        "Assault Landing": {
            "category": "attack",
            "generator": fan_rotom_assault_landing_actions,
            "effect": fan_rotom_assault_landing_effect,
        },
    },

    # Noctowl - Version 1 (Reprint from svp-141)
    "sv7-115": {
        "Speed Wing": {
            "category": "attack",
            "generator": noctowl_speed_wing_actions,
            "effect": noctowl_speed_wing_effect,
        },
        "Jewel Seeker": {
            "category": "hook",
            "trigger": "on_evolve",
            "effect": noctowl_jewel_seeker_hook,
        },
    },

    # Terapagos ex - Version 1 (Reprint from svp-165)
    "sv7-128": {
        "Unified Beatdown": {
            "category": "attack",
            "generator": terapagos_ex_unified_beatdown_actions,
            "effect": terapagos_ex_unified_beatdown_effect,
        },
        "Crown Opal": {
            "category": "attack",
            "generator": terapagos_ex_crown_opal_actions,
            "effect": terapagos_ex_crown_opal_effect,
        },
    },
    "sv7-170": {
        "Unified Beatdown": {
            "category": "attack",
            "generator": terapagos_ex_unified_beatdown_actions,
            "effect": terapagos_ex_unified_beatdown_effect,
        },
        "Crown Opal": {
            "category": "attack",
            "generator": terapagos_ex_crown_opal_actions,
            "effect": terapagos_ex_crown_opal_effect,
        },
    },
    "sv7-173": {
        "Unified Beatdown": {
            "category": "attack",
            "generator": terapagos_ex_unified_beatdown_actions,
            "effect": terapagos_ex_unified_beatdown_effect,
        },
        "Crown Opal": {
            "category": "attack",
            "generator": terapagos_ex_crown_opal_actions,
            "effect": terapagos_ex_crown_opal_effect,
        },
    },
}

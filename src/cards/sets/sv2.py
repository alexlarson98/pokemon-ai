"""
Pokémon TCG Engine - Paldea Evolved Card Logic
Set Code: PAL (sv2)

This module contains card-specific logic for Paldea Evolved.

IMPORTANT PATTERN FOR POKEMON CARDS:
- Define card logic in the set where it was FIRST released
- Other sets that reprint the card should IMPORT the logic from here
- Example: Chien-Pao ex was first in sv2, so svp.py and sv4pt5.py import from here

Cards first released in this set should define their logic here.
"""

from typing import List
from models import GameState, CardInstance, Action, ActionType, EnergyType, PlayerState
from actions import apply_damage, calculate_damage, get_all_attached_energy
from ..library.trainers import iono_effect, iono_actions


# ============================================================================
# CHIEN-PAO EX (sv2-61) - First released in Paldea Evolved
# ============================================================================

def chien_pao_ex_hail_blade_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate atomic actions for Chien-Pao ex's "Hail Blade" attack.

    Attack: Hail Blade [WW]
    "You may discard any amount of Water Energy from your Pokémon.
    This attack does 60 damage for each card you discarded in this way."

    Atomic Action Generation:
    - Counts total Water Energy attached to ALL player's Pokémon
    - Generates one action per valid discard amount (0 to total)
    - Each action specifies exact damage upfront for MCTS evaluation

    Args:
        state: Current game state
        card: Chien-Pao ex CardInstance (active Pokémon)
        player: PlayerState of the attacking player

    Returns:
        List of atomic attack actions with specific discard counts
    """
    actions = []

    # Get all Water Energy attached to player's Pokémon (active + bench)
    water_energy = get_all_attached_energy(state, player.player_id, EnergyType.WATER)
    total_water = len(water_energy)

    # Generate actions for each valid discard amount (0 to total)
    for discard_count in range(total_water + 1):
        damage = 60 * discard_count

        # Select which specific energy cards to discard
        # For simplicity, we'll discard in order (first N energy found)
        energy_to_discard = [e.id for e in water_energy[:discard_count]]

        actions.append(Action(
            action_type=ActionType.ATTACK,
            player_id=player.player_id,
            card_id=card.id,
            attack_name="Hail Blade",
            parameters={
                'discard_energy_ids': energy_to_discard,
                'discard_count': discard_count,
                'calculated_damage': damage
            },
            display_label=f"Hail Blade (Discard {discard_count} Water Energy) - {damage} Dmg"
        ))

    return actions


def chien_pao_ex_hail_blade_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Chien-Pao ex's "Hail Blade" attack effect.

    Reads atomic parameters from action and:
    1. Discards the specified Water Energy cards
    2. Calculates damage (60 × count)
    3. Applies damage to opponent's Active Pokémon

    Args:
        state: Current game state
        card: Chien-Pao ex CardInstance
        action: Attack action with parameters

    Returns:
        Modified GameState
    """
    player = state.get_player(action.player_id)
    opponent = state.get_opponent()

    # Get parameters from atomic action
    energy_ids = action.parameters.get('discard_energy_ids', [])
    discard_count = action.parameters.get('discard_count', 0)

    # Step 1: Discard Water Energy from board
    all_pokemon = player.board.get_all_pokemon()

    for pokemon in all_pokemon:
        # Remove energy that matches our discard list
        energy_to_remove = [e for e in pokemon.attached_energy if e.id in energy_ids]

        for energy in energy_to_remove:
            pokemon.attached_energy.remove(energy)
            player.discard.add_card(energy)

    # Step 2: Calculate damage (60 × discard count)
    base_damage = 60 * discard_count

    # Step 3: Apply damage to opponent's Active Pokémon
    if opponent.board.active_spot:
        # Calculate final damage with weakness/resistance
        final_damage = calculate_damage(
            state=state,
            attacker=card,
            defender=opponent.board.active_spot,
            base_damage=base_damage,
            attack_name="Hail Blade"
        )

        # Apply damage
        state = apply_damage(
            state=state,
            target=opponent.board.active_spot,
            damage=final_damage,
            is_attack_damage=True,
            attacker=card
        )

    return state


# ============================================================================
# SV2 LOGIC REGISTRY
# ============================================================================

SV2_LOGIC = {
    "sv2-61": {  # Chien Pao ex
        "Hail Blade": {
            "generator": chien_pao_ex_hail_blade_actions,
            "effect": chien_pao_ex_hail_blade_effect,
        }
    },
    "sv2-236": {  # Chien Pao ex
        "Hail Blade": {
            "generator": chien_pao_ex_hail_blade_actions,
            "effect": chien_pao_ex_hail_blade_effect,
        }
    },
    "sv2-261": {  # Chien Pao ex
        "Hail Blade": {
            "generator": chien_pao_ex_hail_blade_actions,
            "effect": chien_pao_ex_hail_blade_effect,
        }
    },
    "sv2-274": {  # Chien Pao ex
        "Hail Blade": {
            "generator": chien_pao_ex_hail_blade_actions,
            "effect": chien_pao_ex_hail_blade_effect,
        }
    },
    
    "sv2-185": {  # Iono
        "actions": {
            "play": {
                "generator": iono_actions,
                "effect": iono_effect,
            }
        }
    },
    "sv2-254": {  # Iono
        "actions": {
            "play": {
                "generator": iono_actions,
                "effect": iono_effect,
            }
        }
    },
    "sv2-269": {  # Iono
        "actions": {
            "play": {
                "generator": iono_actions,
                "effect": iono_effect,
            }
        }
    },
}

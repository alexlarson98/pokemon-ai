"""
Pokémon TCG Engine - Shrouded Fable Card Logic
Set Code: SFA (sv6pt5)
"""

from typing import List
from itertools import combinations
from models import GameState, CardInstance, Action, ActionType, PlayerState, SelectFromZoneStep, ZoneType, SelectionPurpose
from actions import apply_damage, calculate_damage, place_damage_counters, force_knockout
from cards.factory import get_card_definition


# ============================================================================
# FEZANDIPITI EX - FLIP THE SCRIPT & CRUEL ARROW
# ============================================================================

def fezandipiti_ex_flip_the_script_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Fezandipiti ex's "Flip the Script" ability.

    Ability: Flip the Script
    Once during your turn, if any of your Pokemon were Knocked Out during your
    opponent's last turn, you may draw 3 cards. You can't use more than 1 Flip
    the Script Ability each turn.

    Conditions:
    1. Once per turn (globally - can't use multiple Fezandipiti ex)
    2. Any of YOUR Pokemon were KO'd during opponent's last turn
    3. Haven't used Flip the Script ability this turn

    Args:
        state: Current game state
        card: Fezandipiti ex CardInstance
        player: PlayerState of the owner

    Returns:
        List with single ability action if usable, empty otherwise
    """
    # Check if Flip the Script has already been used this turn (global flag)
    if state.turn_metadata.get('flip_the_script_used', False):
        return []

    # Check if this specific card has used any ability this turn
    if "Flip the Script" in card.abilities_used_this_turn:
        return []

    # Check if any of this player's Pokemon were KO'd during opponent's last turn
    # last_turn_metadata contains events from the opponent's most recent turn
    knocked_out_players = state.last_turn_metadata.get('knocked_out_player_ids', [])
    if player.player_id not in knocked_out_players:
        return []

    # Check deck has cards (can still draw 3 even if less available)
    if player.deck.is_empty():
        return []

    return [Action(
        action_type=ActionType.USE_ABILITY,
        player_id=player.player_id,
        card_id=card.id,
        ability_name="Flip the Script",
        display_label="Flip the Script - Draw 3 cards"
    )]


def fezandipiti_ex_flip_the_script_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Fezandipiti ex's "Flip the Script" ability effect.

    Draw 3 cards. Sets global flag preventing other Flip the Script uses this turn.

    Args:
        state: Current game state
        card: Fezandipiti ex CardInstance
        action: Ability action

    Returns:
        Modified GameState
    """
    player = state.get_player(action.player_id)

    # Draw 3 cards (or as many as remain in deck)
    cards_to_draw = min(3, len(player.deck.cards))
    for _ in range(cards_to_draw):
        if not player.deck.is_empty():
            drawn_card = player.deck.cards.pop(0)
            player.hand.add_card(drawn_card)

    print(f"[Flip the Script] Player {player.player_id} draws {cards_to_draw} cards")

    # Mark ability as used (global flag - no other Flip the Script can be used)
    state.turn_metadata['flip_the_script_used'] = True
    card.abilities_used_this_turn.add("Flip the Script")

    return state


def fezandipiti_ex_cruel_arrow_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Fezandipiti ex's "Cruel Arrow" attack.

    Attack: Cruel Arrow [CCC]
    This attack does 100 damage to 1 of your opponent's Pokemon.
    (Don't apply Weakness and Resistance for Benched Pokemon.)

    The attack targets ANY opponent Pokemon (Active or Benched).

    Args:
        state: Current game state
        card: Fezandipiti ex CardInstance
        player: PlayerState of the attacking player

    Returns:
        List of attack actions with target options
    """
    actions = []
    opponent = state.get_opponent()

    # Collect all opponent Pokemon that can be targeted
    targets = []

    if opponent.board.active_spot:
        targets.append(('active', opponent.board.active_spot))

    for i, bench_pokemon in enumerate(opponent.board.bench):
        targets.append(('bench', bench_pokemon))

    # Generate action for each target
    for location, target in targets:
        if location == 'active':
            label = f"Cruel Arrow -> {target.card_id} (Active) - 100 Dmg"
        else:
            label = f"Cruel Arrow -> {target.card_id} (Bench) - 100 Dmg"

        actions.append(Action(
            action_type=ActionType.ATTACK,
            player_id=player.player_id,
            card_id=card.id,
            attack_name="Cruel Arrow",
            target_id=target.id,
            parameters={'target_location': location},
            display_label=label
        ))

    return actions


def fezandipiti_ex_cruel_arrow_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Fezandipiti ex's "Cruel Arrow" attack effect.

    Deal 100 damage to target Pokemon.
    Don't apply Weakness/Resistance for Benched Pokemon.

    Args:
        state: Current game state
        card: Fezandipiti ex CardInstance
        action: Attack action with target_id

    Returns:
        Modified GameState
    """
    opponent = state.get_opponent()
    target_id = action.target_id
    target_location = action.parameters.get('target_location', 'active')

    # Find target Pokemon
    target = None
    if opponent.board.active_spot and opponent.board.active_spot.id == target_id:
        target = opponent.board.active_spot
    else:
        for bench_pokemon in opponent.board.bench:
            if bench_pokemon.id == target_id:
                target = bench_pokemon
                break

    if not target:
        return state

    # Calculate damage - apply Weakness/Resistance only for Active
    if target_location == 'active':
        final_damage = calculate_damage(
            state=state,
            attacker=card,
            defender=target,
            base_damage=100,
            attack_name="Cruel Arrow"
        )
    else:
        # Benched Pokemon: No Weakness/Resistance
        final_damage = 100

    # Apply damage
    state = apply_damage(
        state=state,
        target=target,
        damage=final_damage,
        is_attack_damage=True,
        attacker=card
    )

    return state


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
# DUSCLOPS - CURSED BLAST & WILL-O-WISP
# ============================================================================

def dusclops_cursed_blast_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Dusclops's "Cursed Blast" ability.

    Ability: Cursed Blast
    Once during your turn, you may put 5 damage counters on 1 of your opponent's
    Pokemon. If you use this Ability, this Pokemon is Knocked Out.

    Conditions:
    1. Must have valid targets (opponent has Pokemon on board)

    Args:
        state: Current game state
        card: Dusclops CardInstance
        player: PlayerState of the owner

    Returns:
        List of ability actions with target options
    """

    opponent = state.get_opponent()
    actions = []

    # Collect all opponent Pokemon that can be targeted
    targets = []

    if opponent.board.active_spot:
        targets.append(('active', opponent.board.active_spot))

    for bench_pokemon in opponent.board.bench:
        targets.append(('bench', bench_pokemon))

    # No targets = can't use ability
    if not targets:
        return []

    # Generate action for each target
    for location, target in targets:
        card_def = get_card_definition(target)
        target_name = card_def.name if card_def else target.card_id

        if location == 'active':
            label = f"Cursed Blast -> {target_name} (Active) - 5 damage counters (KO self)"
        else:
            label = f"Cursed Blast -> {target_name} (Bench) - 5 damage counters (KO self)"

        actions.append(Action(
            action_type=ActionType.USE_ABILITY,
            player_id=player.player_id,
            card_id=card.id,
            ability_name="Cursed Blast",
            target_id=target.id,
            parameters={'target_location': location},
            display_label=label
        ))

    return actions


def dusclops_cursed_blast_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Dusclops's "Cursed Blast" ability effect.

    Put 5 damage counters on target opponent's Pokemon, then KO self.

    Args:
        state: Current game state
        card: Dusclops CardInstance
        action: Ability action with target_id

    Returns:
        Modified GameState
    """
    opponent = state.get_opponent()
    target_id = action.target_id

    # Find target Pokemon
    target = None
    if opponent.board.active_spot and opponent.board.active_spot.id == target_id:
        target = opponent.board.active_spot
    else:
        for bench_pokemon in opponent.board.bench:
            if bench_pokemon.id == target_id:
                target = bench_pokemon
                break

    if target:
        # Place 5 damage counters on target (50 damage, but as counters - no W/R)
        state = place_damage_counters(
            state=state,
            target=target,
            amount=5
        )

    # KO self (Dusclops)
    state = force_knockout(state, card.id)

    return state


def dusclops_will_o_wisp_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """
    Generate actions for Dusclops's "Will-O-Wisp" attack.

    Attack: Will-O-Wisp [PP]
    50 damage. No additional effects.

    Args:
        state: Current game state
        card: Dusclops CardInstance
        player: PlayerState of the attacking player

    Returns:
        List with single attack action
    """
    return [Action(
        action_type=ActionType.ATTACK,
        player_id=player.player_id,
        card_id=card.id,
        attack_name="Will-O-Wisp",
        display_label="Will-O-Wisp - 50 Dmg"
    )]


def dusclops_will_o_wisp_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """
    Execute Dusclops's "Will-O-Wisp" attack effect.

    Deals 50 damage to opponent's Active Pokémon.

    Args:
        state: Current game state
        card: Dusclops CardInstance
        action: Attack action

    Returns:
        Modified GameState
    """
    opponent = state.get_opponent()

    # Deal 50 damage to opponent's Active Pokémon
    if opponent.board.active_spot:
        final_damage = calculate_damage(
            state=state,
            attacker=card,
            defender=opponent.board.active_spot,
            base_damage=50,
            attack_name="Will-O-Wisp"
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
    # Fezandipiti ex - Flip the Script & Cruel Arrow
    "sv6pt5-38": {
        "Flip the Script": {
            "category": "activatable",
            "generator": fezandipiti_ex_flip_the_script_actions,
            "effect": fezandipiti_ex_flip_the_script_effect,
        },
        "Cruel Arrow": {
            "category": "attack",
            "generator": fezandipiti_ex_cruel_arrow_actions,
            "effect": fezandipiti_ex_cruel_arrow_effect,
        },
    },
    "sv6pt5-84": {
        "Flip the Script": {
            "category": "activatable",
            "generator": fezandipiti_ex_flip_the_script_actions,
            "effect": fezandipiti_ex_flip_the_script_effect,
        },
        "Cruel Arrow": {
            "category": "attack",
            "generator": fezandipiti_ex_cruel_arrow_actions,
            "effect": fezandipiti_ex_cruel_arrow_effect,
        },
    },
    "sv6pt5-92": {
        "Flip the Script": {
            "category": "activatable",
            "generator": fezandipiti_ex_flip_the_script_actions,
            "effect": fezandipiti_ex_flip_the_script_effect,
        },
        "Cruel Arrow": {
            "category": "attack",
            "generator": fezandipiti_ex_cruel_arrow_actions,
            "effect": fezandipiti_ex_cruel_arrow_effect,
        },
    },
    # Duskull - Come and Get You & Mumble
    "sv6pt5-18": {
        "Come and Get You": {
            "category": "attack",
            "generator": duskull_come_and_get_you_actions,
            "effect": duskull_come_and_get_you_effect,
        },
        "Mumble": {
            "category": "attack",
            "generator": duskull_mumble_actions,
            "effect": duskull_mumble_effect,
        },
    },
    "sv6pt5-68": {
        "Come and Get You": {
            "category": "attack",
            "generator": duskull_come_and_get_you_actions,
            "effect": duskull_come_and_get_you_effect,
        },
        "Mumble": {
            "category": "attack",
            "generator": duskull_mumble_actions,
            "effect": duskull_mumble_effect,
        },
    },

    # Dusclops - Cursed Blast & Will-O-Wisp
    "sv6pt5-19": {
        "Cursed Blast": {
            "category": "activatable",
            "generator": dusclops_cursed_blast_actions,
            "effect": dusclops_cursed_blast_effect,
        },
        "Will-O-Wisp": {
            "category": "attack",
            "generator": dusclops_will_o_wisp_actions,
            "effect": dusclops_will_o_wisp_effect,
        },
    },
    "sv6pt5-69": {
        "Cursed Blast": {
            "category": "activatable",
            "generator": dusclops_cursed_blast_actions,
            "effect": dusclops_cursed_blast_effect,
        },
        "Will-O-Wisp": {
            "category": "attack",
            "generator": dusclops_will_o_wisp_actions,
            "effect": dusclops_will_o_wisp_effect,
        },
    },
}

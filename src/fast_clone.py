"""
Fast State Cloning for MCTS Simulations.

This module provides optimized cloning functions that bypass Pydantic's
deep copy mechanism, providing 10-50x speedup for MCTS rollouts.

The key insight: Pydantic's model_copy(deep=True) uses Python's deepcopy
which recursively calls __deepcopy__ on every nested object. For our
~200+ nested objects per GameState, this is extremely slow.

Our approach:
1. Use model_construct() to bypass validation (safe since we're copying valid data)
2. Manually clone only mutable fields (lists, dicts, sets)
3. Reference immutable primitives directly (str, int, bool, enum)
4. Use list/dict comprehensions instead of deepcopy
"""

from typing import Optional, List, Dict, Set
from models import (
    GameState, PlayerState, Board, Zone, CardInstance, ActiveEffect,
    ResolutionStep, SelectFromZoneStep, SearchDeckStep, AttachToTargetStep,
    EvolveTargetStep, SearchAndAttachState, StepType
)


def clone_card_instance(card: CardInstance) -> CardInstance:
    """Fast clone a CardInstance without deep copy."""
    return CardInstance.model_construct(
        id=card.id,
        card_id=card.card_id,
        owner_id=card.owner_id,
        current_hp=card.current_hp,
        damage_counters=card.damage_counters,
        status_conditions=set(card.status_conditions),  # Clone set
        attached_energy=[clone_card_instance(e) for e in card.attached_energy],
        attached_tools=[clone_card_instance(t) for t in card.attached_tools],
        evolution_chain=list(card.evolution_chain),  # Clone list of strings
        previous_stages=[clone_card_instance(p) for p in card.previous_stages],
        turns_in_play=card.turns_in_play,
        evolved_this_turn=card.evolved_this_turn,
        abilities_used_this_turn=set(card.abilities_used_this_turn),
        attack_effects=list(card.attack_effects),
        is_revealed=card.is_revealed,
    )


def clone_zone(zone: Zone) -> Zone:
    """Fast clone a Zone."""
    return Zone.model_construct(
        cards=[clone_card_instance(c) for c in zone.cards],
        is_ordered=zone.is_ordered,
        is_hidden=zone.is_hidden,
        is_private=zone.is_private,
    )


def clone_board(board: Board) -> Board:
    """Fast clone a Board."""
    return Board.model_construct(
        active_spot=clone_card_instance(board.active_spot) if board.active_spot else None,
        bench=[clone_card_instance(p) if p else None for p in board.bench],
        max_bench_size=board.max_bench_size,
    )


def clone_player_state(player: PlayerState) -> PlayerState:
    """Fast clone a PlayerState."""
    return PlayerState.model_construct(
        player_id=player.player_id,
        name=player.name,
        deck=clone_zone(player.deck),
        hand=clone_zone(player.hand),
        discard=clone_zone(player.discard),
        prizes=clone_zone(player.prizes),
        board=clone_board(player.board),
        vstar_power_used=player.vstar_power_used,
        gx_attack_used=player.gx_attack_used,
        supporter_played_this_turn=player.supporter_played_this_turn,
        energy_attached_this_turn=player.energy_attached_this_turn,
        retreated_this_turn=player.retreated_this_turn,
        stadium_played_this_turn=player.stadium_played_this_turn,
        prizes_taken=player.prizes_taken,
        initial_deck_counts=dict(player.initial_deck_counts),  # Shallow copy ok (str keys/values)
        functional_id_map=dict(player.functional_id_map),
        has_searched_deck=player.has_searched_deck,
    )


def clone_active_effect(effect):
    """Fast clone an ActiveEffect or dict effect."""
    # Handle dict effects (legacy format used by some cards like Briar)
    if isinstance(effect, dict):
        return dict(effect)  # Shallow copy of dict

    # Handle proper ActiveEffect objects
    return ActiveEffect.model_construct(
        name=effect.name,
        source=effect.source,
        source_card_id=effect.source_card_id,
        target_player_id=effect.target_player_id,
        target_card_id=effect.target_card_id,
        duration_turns=effect.duration_turns,
        created_turn=effect.created_turn,
        created_phase=effect.created_phase,
        expires_on_player=effect.expires_on_player,
        params=dict(effect.params),  # Shallow copy of params dict
    )


def clone_resolution_step(step: ResolutionStep) -> ResolutionStep:
    """Fast clone a ResolutionStep (and its subclasses)."""
    if isinstance(step, SelectFromZoneStep):
        return SelectFromZoneStep.model_construct(
            step_type=step.step_type,
            source_card_id=step.source_card_id,
            source_card_name=step.source_card_name,
            player_id=step.player_id,
            purpose=step.purpose,
            is_complete=step.is_complete,
            on_complete_callback=step.on_complete_callback,
            zone=step.zone,
            count=step.count,
            min_count=step.min_count,
            exact_count=step.exact_count,
            filter_criteria=dict(step.filter_criteria),
            exclude_card_ids=list(step.exclude_card_ids),
            selected_card_ids=list(step.selected_card_ids),
            context=dict(step.context),
        )
    elif isinstance(step, SearchDeckStep):
        return SearchDeckStep.model_construct(
            step_type=step.step_type,
            source_card_id=step.source_card_id,
            source_card_name=step.source_card_name,
            player_id=step.player_id,
            purpose=step.purpose,
            is_complete=step.is_complete,
            on_complete_callback=step.on_complete_callback,
            count=step.count,
            min_count=step.min_count,
            destination=step.destination,
            filter_criteria=dict(step.filter_criteria),
            selected_card_ids=list(step.selected_card_ids),
            shuffle_after=step.shuffle_after,
            reveal_cards=step.reveal_cards,
        )
    elif isinstance(step, AttachToTargetStep):
        return AttachToTargetStep.model_construct(
            step_type=step.step_type,
            source_card_id=step.source_card_id,
            source_card_name=step.source_card_name,
            player_id=step.player_id,
            purpose=step.purpose,
            is_complete=step.is_complete,
            on_complete_callback=step.on_complete_callback,
            card_to_attach_id=step.card_to_attach_id,
            card_to_attach_name=step.card_to_attach_name,
            valid_target_ids=list(step.valid_target_ids),
            selected_target_id=step.selected_target_id,
        )
    elif isinstance(step, EvolveTargetStep):
        return EvolveTargetStep.model_construct(
            step_type=step.step_type,
            source_card_id=step.source_card_id,
            source_card_name=step.source_card_name,
            player_id=step.player_id,
            purpose=step.purpose,
            is_complete=step.is_complete,
            on_complete_callback=step.on_complete_callback,
            base_pokemon_id=step.base_pokemon_id,
            evolution_card_id=step.evolution_card_id,
            skip_evolution_sickness=step.skip_evolution_sickness,
            skip_stage=step.skip_stage,
        )
    else:
        # Base ResolutionStep
        return ResolutionStep.model_construct(
            step_type=step.step_type,
            source_card_id=step.source_card_id,
            source_card_name=step.source_card_name,
            player_id=step.player_id,
            purpose=step.purpose,
            is_complete=step.is_complete,
            on_complete_callback=step.on_complete_callback,
        )


def clone_search_and_attach_state(state: SearchAndAttachState) -> SearchAndAttachState:
    """Fast clone a SearchAndAttachState (legacy interrupt)."""
    return SearchAndAttachState.model_construct(
        ability_name=state.ability_name,
        source_card_id=state.source_card_id,
        player_id=state.player_id,
        phase=state.phase,
        search_filter=dict(state.search_filter),
        max_select=state.max_select,
        selected_card_ids=list(state.selected_card_ids),
        cards_to_attach=list(state.cards_to_attach),
        current_attach_index=state.current_attach_index,
        card_definition_map=dict(state.card_definition_map),
        is_complete=state.is_complete,
    )


def fast_clone_game_state(state: GameState) -> GameState:
    """
    Fast clone a GameState for MCTS simulation.

    This is ~10-50x faster than state.clone() (model_copy with deep=True)
    because it:
    1. Uses model_construct() to bypass Pydantic validation
    2. Manually clones mutable structures (lists, dicts, sets)
    3. References immutable values directly (str, int, bool, enum)
    """
    return GameState.model_construct(
        # Players
        players=[clone_player_state(p) for p in state.players],

        # Turn tracking (all immutable primitives)
        turn_count=state.turn_count,
        active_player_index=state.active_player_index,
        starting_player_id=state.starting_player_id,
        current_phase=state.current_phase,

        # Global state
        stadium=clone_card_instance(state.stadium) if state.stadium else None,
        active_effects=[clone_active_effect(e) for e in state.active_effects],
        global_effects=[dict(e) for e in state.global_effects],  # List of dicts

        # Game result (immutable)
        result=state.result,
        winner_id=state.winner_id,

        # History tracking
        turn_metadata=dict(state.turn_metadata),
        last_turn_metadata=dict(state.last_turn_metadata),

        # Metadata
        random_seed=state.random_seed,
        move_history=list(state.move_history),  # Clone list

        # Resolution stack
        resolution_stack=[clone_resolution_step(s) for s in state.resolution_stack],

        # Legacy interrupt
        pending_interrupt=clone_search_and_attach_state(state.pending_interrupt) if state.pending_interrupt else None,

        # Attack tracking
        attack_resolution_pending=state.attack_resolution_pending,
    )

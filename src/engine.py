"""
Pokémon TCG Engine - Physics Engine (engine.py)
The "Referee" - Enforces the Constitution and manages state transitions.
Never guesses; only validates and executes.
"""

from typing import List, Optional, Set, Tuple, Dict
import random
from copy import deepcopy

from models import (
    GameState,
    PlayerState,
    Action,
    ActionType,
    GamePhase,
    GameResult,
    CardInstance,
    StatusCondition,
    Subtype,
)
from cards import logic_registry


class PokemonEngine:
    """
    The Physics Engine - Enforces Constitution rules.

    Core Responsibilities:
    1. get_legal_actions() - Generate all valid moves for MCTS
    2. step() - Apply action and return new state
    3. resolve_phase_transition() - Auto-advance turn structure
    """

    def __init__(self, random_seed: Optional[int] = None):
        """Initialize engine with optional RNG seed for deterministic simulation."""
        self.random_seed = random_seed
        if random_seed is not None:
            random.seed(random_seed)

    # ========================================================================
    # 1. LEGAL ACTION GENERATION (Critical for MCTS)
    # ========================================================================

    def get_legal_actions(self, state: GameState) -> List[Action]:
        """
        Generate all legal actions for the current state.

        This is the MOST CRITICAL function for MCTS.
        Returns empty list if player must make a forced choice (handled by interrupts).

        Constitution Enforcement:
        - Section 2: Turn Structure & Phase constraints
        - Section 3: Once-per-turn/game flags
        - Section 4.3: Bench size limits
        - Section 6: "Can't" priority rules
        """
        if state.is_game_over():
            return []

        player = state.get_active_player()

        # Handle interrupts first (forced actions take precedence)
        interrupt_actions = self._get_interrupt_actions(state)
        if interrupt_actions:
            return interrupt_actions

        # Phase-specific action generation
        if state.current_phase == GamePhase.SETUP:
            return self._get_setup_actions(state)
        elif state.current_phase == GamePhase.MULLIGAN:
            return self._get_mulligan_actions(state)
        elif state.current_phase == GamePhase.DRAW:
            return self._get_draw_actions(state)
        elif state.current_phase == GamePhase.MAIN:
            return self._get_main_phase_actions(state)
        elif state.current_phase == GamePhase.ATTACK:
            return self._get_attack_phase_actions(state)
        elif state.current_phase == GamePhase.CLEANUP:
            return []  # Auto-resolved by engine
        else:
            return []

    # ========================================================================
    # 2. INTERRUPT ACTIONS (State-forced choices)
    # ========================================================================

    def _get_interrupt_actions(self, state: GameState) -> List[Action]:
        """
        Handle interrupts that force player choices.

        Examples:
        - Active Pokémon KO'd -> Must promote from bench
        - Bench > max_size -> Must discard Pokémon
        - Prize card selection (if applicable)
        """
        player = state.get_active_player()
        actions = []

        # INTERRUPT 1: Must promote new Active (Constitution Section 2, Phase 3)
        if not player.has_active_pokemon() and player.board.get_bench_count() > 0:
            for i, pokemon in enumerate(player.board.bench):
                if pokemon is not None:
                    actions.append(Action(
                        action_type=ActionType.PROMOTE_ACTIVE,
                        player_id=player.player_id,
                        card_id=pokemon.id,
                        metadata={"bench_index": i}
                    ))
            return actions

        # INTERRUPT 2: Bench size collapse (Constitution Section 4.3)
        max_bench = self.get_max_bench_size(state, player)
        if player.board.get_bench_count() > max_bench:
            # Player must discard Pokémon until bench size is valid
            for i, pokemon in enumerate(player.board.bench):
                if pokemon is not None:
                    actions.append(Action(
                        action_type=ActionType.PROMOTE_ACTIVE,  # Reusing for discard
                        player_id=player.player_id,
                        card_id=pokemon.id,
                        metadata={"discard_to_fix_bench": True, "bench_index": i}
                    ))
            return actions

        return []

    # ========================================================================
    # 3. PHASE-SPECIFIC ACTION GENERATION
    # ========================================================================

    def _get_setup_actions(self, state: GameState) -> List[Action]:
        """
        Setup Phase (Constitution Section 2, Phase 0).

        Actions:
        - Place Active Pokémon (from Basic Pokémon in hand)
        - Place Bench Pokémon (up to 5)
        """
        player = state.get_active_player()
        actions = []

        # Get all Basic Pokémon in hand
        basic_pokemon = [
            card for card in player.hand.cards
            if Subtype.BASIC in self._get_card_subtypes(card)
        ]

        # Must place Active first
        if not player.has_active_pokemon():
            for card in basic_pokemon:
                actions.append(Action(
                    action_type=ActionType.PLACE_ACTIVE,
                    player_id=player.player_id,
                    card_id=card.id
                ))
        else:
            # Can place on Bench (up to max_bench_size)
            max_bench = self.get_max_bench_size(state, player)
            if player.board.get_bench_count() < max_bench:
                for card in basic_pokemon:
                    actions.append(Action(
                        action_type=ActionType.PLACE_BENCH,
                        player_id=player.player_id,
                        card_id=card.id
                    ))

            # Option to finish setup (if Active is placed)
            actions.append(Action(
                action_type=ActionType.END_TURN,
                player_id=player.player_id,
                metadata={"finish_setup": True}
            ))

        return actions

    def _get_mulligan_actions(self, state: GameState) -> List[Action]:
        """
        Mulligan Phase (Constitution Section 2, Phase 0).

        Opponent may draw 1 card per mulligan.
        """
        opponent = state.get_opponent()

        return [
            Action(
                action_type=ActionType.MULLIGAN_DRAW,
                player_id=opponent.player_id,
                metadata={"draw": True}
            ),
            Action(
                action_type=ActionType.MULLIGAN_DRAW,
                player_id=opponent.player_id,
                metadata={"draw": False}
            )
        ]

    def _get_draw_actions(self, state: GameState) -> List[Action]:
        """
        Draw Phase (Constitution Section 2, Phase 1).

        Forced action: Active player draws 1 card.
        Returns empty list (auto-resolved by engine).
        """
        # This phase is auto-resolved in step()
        return []

    def _get_main_phase_actions(self, state: GameState) -> List[Action]:
        """
        Main Phase (Constitution Section 2, Phase 2).

        Actions:
        - Attach Energy (once per turn)
        - Play Trainer (Item/Supporter/Stadium/Tool)
        - Evolve Pokémon (unlimited, subject to evolution sickness)
        - Use Abilities (unlimited, unless "once per turn")
        - Retreat (once per turn)
        - Advance to Attack Phase
        """
        player = state.get_active_player()
        actions = []

        # ACTION 1: Attach Energy (Constitution Section 2, Phase 2)
        if not player.energy_attached_this_turn:
            energy_actions = self._get_attach_energy_actions(state)
            actions.extend(energy_actions)

        # ACTION 2: Play Basic Pokémon to Bench
        max_bench = self.get_max_bench_size(state, player)
        if player.board.get_bench_count() < max_bench:
            basic_pokemon = [
                card for card in player.hand.cards
                if Subtype.BASIC in self._get_card_subtypes(card)
            ]
            for card in basic_pokemon:
                actions.append(Action(
                    action_type=ActionType.PLAY_BASIC,
                    player_id=player.player_id,
                    card_id=card.id
                ))

        # ACTION 3: Evolve Pokémon
        evolution_actions = self._get_evolution_actions(state)
        actions.extend(evolution_actions)

        # ACTION 4: Play Trainer cards
        trainer_actions = self._get_trainer_actions(state)
        actions.extend(trainer_actions)

        # ACTION 5: Use Abilities
        ability_actions = self._get_ability_actions(state)
        actions.extend(ability_actions)

        # ACTION 6: Retreat (Constitution Section 2, Phase 2)
        if not player.retreated_this_turn and player.has_active_pokemon():
            retreat_actions = self._get_retreat_actions(state)
            actions.extend(retreat_actions)

        # ACTION 7: Advance to Attack Phase
        actions.append(Action(
            action_type=ActionType.END_TURN,
            player_id=player.player_id,
            metadata={"advance_to_attack": True}
        ))

        return actions

    def _get_attack_phase_actions(self, state: GameState) -> List[Action]:
        """
        Attack Phase (Constitution Section 2, Phase 3).

        CRITICAL RULE: Player 1 (going first) cannot attack on Turn 1.
        """
        player = state.get_active_player()
        actions = []

        # CONSTITUTION ENFORCEMENT: Turn 1 Attack Restriction
        if state.turn_count == 1 and state.active_player_index == 0:
            # Player 1 cannot attack on Turn 1
            actions.append(Action(
                action_type=ActionType.END_TURN,
                player_id=player.player_id,
                metadata={"skip_attack": True}
            ))
            return actions

        # Check if player has Active Pokémon
        if not player.has_active_pokemon():
            # Cannot attack without Active
            actions.append(Action(
                action_type=ActionType.END_TURN,
                player_id=player.player_id,
                metadata={"no_active": True}
            ))
            return actions

        # Get available attacks from Active Pokémon
        active = player.board.active_spot
        attack_actions = self._get_attack_actions(state, active)
        actions.extend(attack_actions)

        # Option to skip attack
        actions.append(Action(
            action_type=ActionType.END_TURN,
            player_id=player.player_id,
            metadata={"skip_attack": True}
        ))

        return actions

    # ========================================================================
    # 4. ACTION HELPERS (Specific action type generation)
    # ========================================================================

    def _get_attach_energy_actions(self, state: GameState) -> List[Action]:
        """Generate energy attachment actions."""
        player = state.get_active_player()
        actions = []

        # Find energy cards in hand
        energy_cards = [
            card for card in player.hand.cards
            if card.card_id.startswith("energy-")  # Simple heuristic
        ]

        # Can attach to any Pokémon in play
        targets = player.board.get_all_pokemon()

        for energy in energy_cards:
            for target in targets:
                actions.append(Action(
                    action_type=ActionType.ATTACH_ENERGY,
                    player_id=player.player_id,
                    card_id=energy.id,
                    target_id=target.id
                ))

        return actions

    def _get_evolution_actions(self, state: GameState) -> List[Action]:
        """
        Generate evolution actions.

        Rules (Constitution Section 2, Phase 2):
        - Cannot evolve on Turn 1 (either player)
        - Cannot evolve on same turn Pokémon was played (evolution sickness)
        - Can evolve multiple Pokémon per turn
        """
        player = state.get_active_player()
        actions = []

        # Turn 1 restriction
        if state.turn_count == 1:
            return actions

        # Find evolution cards in hand
        evolution_cards = [
            card for card in player.hand.cards
            if Subtype.STAGE_1 in self._get_card_subtypes(card) or
               Subtype.STAGE_2 in self._get_card_subtypes(card)
        ]

        # Find valid targets (Pokémon that can be evolved)
        targets = player.board.get_all_pokemon()

        for evo_card in evolution_cards:
            for target in targets:
                # Check evolution sickness (turns_in_play > 0)
                if target.turns_in_play > 0:
                    # TODO: Check if evo_card can evolve from target
                    # This requires card definition data
                    actions.append(Action(
                        action_type=ActionType.EVOLVE,
                        player_id=player.player_id,
                        card_id=evo_card.id,
                        target_id=target.id
                    ))

        return actions

    def _get_trainer_actions(self, state: GameState) -> List[Action]:
        """
        Generate Trainer card actions.

        Rules (Constitution Section 2, Phase 2):
        - Item: Unlimited
        - Supporter: Once per turn (cannot play on Turn 1 going first)
        - Stadium: Once per turn (must have different name than current)
        - Tool: Attached to Pokémon
        """
        player = state.get_active_player()
        actions = []

        for card in player.hand.cards:
            subtypes = self._get_card_subtypes(card)

            # ITEM: Unlimited
            if Subtype.ITEM in subtypes:
                actions.append(Action(
                    action_type=ActionType.PLAY_ITEM,
                    player_id=player.player_id,
                    card_id=card.id
                ))

            # SUPPORTER: Once per turn, not on Turn 1 going first
            if Subtype.SUPPORTER in subtypes:
                if not player.supporter_played_this_turn:
                    # Constitution: No Supporter on Turn 1 going first
                    if not (state.turn_count == 1 and state.active_player_index == 0):
                        actions.append(Action(
                            action_type=ActionType.PLAY_SUPPORTER,
                            player_id=player.player_id,
                            card_id=card.id
                        ))

            # STADIUM: Once per turn, must have different name
            if Subtype.STADIUM in subtypes:
                if not player.stadium_played_this_turn:
                    # Check if different from current stadium
                    can_play = True
                    if state.stadium is not None:
                        # TODO: Check card names (requires card definition)
                        # For now, allow if different card_id
                        if state.stadium.card_id == card.card_id:
                            can_play = False

                    if can_play:
                        actions.append(Action(
                            action_type=ActionType.PLAY_STADIUM,
                            player_id=player.player_id,
                            card_id=card.id
                        ))

            # TOOL: Attach to Pokémon
            if Subtype.TOOL in subtypes:
                targets = player.board.get_all_pokemon()
                for target in targets:
                    # TODO: Check if target already has a Tool
                    actions.append(Action(
                        action_type=ActionType.ATTACH_TOOL,
                        player_id=player.player_id,
                        card_id=card.id,
                        target_id=target.id
                    ))

        return actions

    def _get_ability_actions(self, state: GameState) -> List[Action]:
        """
        Generate ability activation actions.

        Checks global permission for ability usage (Klefki blocks abilities).
        Uses logic_registry to validate card logic exists.
        """
        player = state.get_active_player()
        actions = []

        # Get all Pokémon in play
        pokemon_in_play = player.board.get_all_pokemon()

        for pokemon in pokemon_in_play:
            # Check if abilities are allowed for this Pokémon
            can_use_ability = self.check_global_permission(
                state,
                "ability",
                {"card_id": pokemon.id, "player_id": player.player_id}
            )

            if not can_use_ability:
                continue  # Abilities blocked (e.g., by Klefki)

            # TODO: Query card definition for abilities
            # For now, return empty (abilities implemented in cards/)
            # When implemented, create USE_ABILITY actions here
            # Validate using: logic_registry.get_card_logic(pokemon.card_id, ability_name)
            pass

        return actions

    def _get_retreat_actions(self, state: GameState) -> List[Action]:
        """
        Generate retreat actions.

        Rules:
        - Once per turn
        - Must discard Energy equal to Retreat Cost
        - Cannot retreat if Asleep or Paralyzed (Constitution Section 6)
        """
        player = state.get_active_player()
        actions = []

        if not player.has_active_pokemon():
            return actions

        active = player.board.active_spot

        # Check "Can't" conditions (Constitution Section 6)
        if StatusCondition.ASLEEP in active.status_conditions:
            return actions  # Can't retreat if Asleep
        if StatusCondition.PARALYZED in active.status_conditions:
            return actions  # Can't retreat if Paralyzed

        # Must have Bench to retreat to
        if player.board.get_bench_count() == 0:
            return actions

        # TODO: Check retreat cost and available energy
        # For now, generate retreat action if bench exists
        for i, pokemon in enumerate(player.board.bench):
            if pokemon is not None:
                actions.append(Action(
                    action_type=ActionType.RETREAT,
                    player_id=player.player_id,
                    card_id=active.id,
                    target_id=pokemon.id,
                    metadata={"bench_index": i}
                ))

        return actions

    def _get_attack_actions(self, state: GameState, active: CardInstance) -> List[Action]:
        """
        Generate attack actions for Active Pokémon.

        Rules:
        - Must have sufficient Energy to pay cost
        - Check for attack effects (e.g., "cannot attack next turn")
        - Validate attack logic exists in logic_registry
        """
        player = state.get_active_player()
        actions = []

        # Check if Pokémon can attack
        if "cannot_attack_next_turn" in active.attack_effects:
            return actions

        # Check status conditions (Constitution Section 5)
        if StatusCondition.ASLEEP in active.status_conditions:
            return actions  # Asleep Pokémon cannot attack
        if StatusCondition.PARALYZED in active.status_conditions:
            return actions  # Paralyzed Pokémon cannot attack

        # TODO: Query card definition for attacks and energy costs
        # For now, create placeholder attack action
        # When implemented, validate using: logic_registry.get_card_logic(active.card_id, attack_name)
        actions.append(Action(
            action_type=ActionType.ATTACK,
            player_id=player.player_id,
            card_id=active.id,
            attack_name="attack_1",  # Placeholder
            metadata={"target": "opponent_active"}
        ))

        return actions

    # ========================================================================
    # 5. STATE TRANSITION (The step function)
    # ========================================================================

    def step(self, state: GameState, action: Action) -> GameState:
        """
        Apply action to state and return new state.

        This is the Transition Function.
        Creates a deep copy, applies changes, and advances phases.

        Returns:
            New GameState after action application.
        """
        # Clone state for immutability (MCTS requirement)
        new_state = state.clone()

        # Apply action
        new_state = self._apply_action(new_state, action)

        # Check for game-ending conditions
        new_state = self._check_win_conditions(new_state)

        # Auto-resolve phase transitions if needed
        if new_state.current_phase == GamePhase.CLEANUP:
            new_state = self.resolve_phase_transition(new_state)

        # Record move in history
        new_state.move_history.append(str(action))

        return new_state

    def _apply_action(self, state: GameState, action: Action) -> GameState:
        """
        Apply the specific action to the state.

        Delegates to action-specific handlers.
        """
        if action.action_type == ActionType.PLACE_ACTIVE:
            return self._apply_place_active(state, action)
        elif action.action_type == ActionType.PLACE_BENCH:
            return self._apply_place_bench(state, action)
        elif action.action_type == ActionType.MULLIGAN_DRAW:
            return self._apply_mulligan_draw(state, action)
        elif action.action_type == ActionType.ATTACH_ENERGY:
            return self._apply_attach_energy(state, action)
        elif action.action_type == ActionType.PLAY_BASIC:
            return self._apply_play_basic(state, action)
        elif action.action_type == ActionType.EVOLVE:
            return self._apply_evolve(state, action)
        elif action.action_type == ActionType.PLAY_ITEM:
            return self._apply_play_item(state, action)
        elif action.action_type == ActionType.PLAY_SUPPORTER:
            return self._apply_play_supporter(state, action)
        elif action.action_type == ActionType.PLAY_STADIUM:
            return self._apply_play_stadium(state, action)
        elif action.action_type == ActionType.RETREAT:
            return self._apply_retreat(state, action)
        elif action.action_type == ActionType.ATTACK:
            return self._apply_attack(state, action)
        elif action.action_type == ActionType.PROMOTE_ACTIVE:
            return self._apply_promote_active(state, action)
        elif action.action_type == ActionType.END_TURN:
            return self._apply_end_turn(state, action)
        else:
            # Unknown action type
            return state

    # ========================================================================
    # 6. ACTION APPLICATION HANDLERS
    # ========================================================================

    def _apply_place_active(self, state: GameState, action: Action) -> GameState:
        """Place Basic Pokémon in Active spot during setup."""
        player = state.get_player(action.player_id)
        card = player.hand.remove_card(action.card_id)

        if card:
            player.board.active_spot = card

        return state

    def _apply_place_bench(self, state: GameState, action: Action) -> GameState:
        """Place Basic Pokémon on Bench during setup."""
        player = state.get_player(action.player_id)
        card = player.hand.remove_card(action.card_id)

        if card:
            player.board.add_to_bench(card)

        return state

    def _apply_mulligan_draw(self, state: GameState, action: Action) -> GameState:
        """Opponent draws 1 card during mulligan."""
        if action.metadata.get("draw", False):
            player = state.get_player(action.player_id)
            # TODO: Import draw_card from actions.py
            # For now, simple implementation
            if not player.deck.is_empty():
                card = player.deck.cards.pop(0)
                player.hand.add_card(card)

        # Advance to next phase
        state.current_phase = GamePhase.SETUP
        return state

    def _apply_attach_energy(self, state: GameState, action: Action) -> GameState:
        """Attach Energy card to Pokémon."""
        player = state.get_player(action.player_id)
        energy = player.hand.remove_card(action.card_id)

        if energy:
            # Find target Pokémon
            target = self._find_pokemon_by_id(player, action.target_id)
            if target:
                target.attached_energy.append(energy)
                player.energy_attached_this_turn = True

        return state

    def _apply_play_basic(self, state: GameState, action: Action) -> GameState:
        """Play Basic Pokémon to Bench during Main Phase."""
        player = state.get_player(action.player_id)
        card = player.hand.remove_card(action.card_id)

        if card:
            card.turns_in_play = 0  # Reset for evolution sickness
            player.board.add_to_bench(card)

        return state

    def _apply_evolve(self, state: GameState, action: Action) -> GameState:
        """Evolve a Pokémon."""
        player = state.get_player(action.player_id)
        evolution_card = player.hand.remove_card(action.card_id)

        if evolution_card:
            # Find target Pokémon
            target = self._find_pokemon_by_id(player, action.target_id)
            if target:
                # TODO: Implement evolution logic
                # - Transfer energy/tools/damage
                # - Update evolution chain
                # - Replace card
                pass

        return state

    def _apply_play_item(self, state: GameState, action: Action) -> GameState:
        """Play Item card."""
        player = state.get_player(action.player_id)
        card = player.hand.remove_card(action.card_id)

        if card:
            # TODO: Execute item effect (delegate to card logic)
            # Move to discard after use
            player.discard.add_card(card)

        return state

    def _apply_play_supporter(self, state: GameState, action: Action) -> GameState:
        """Play Supporter card."""
        player = state.get_player(action.player_id)
        card = player.hand.remove_card(action.card_id)

        if card:
            player.supporter_played_this_turn = True
            # TODO: Execute supporter effect (delegate to card logic)
            # Move to discard after use
            player.discard.add_card(card)

        return state

    def _apply_play_stadium(self, state: GameState, action: Action) -> GameState:
        """Play Stadium card."""
        player = state.get_player(action.player_id)
        card = player.hand.remove_card(action.card_id)

        if card:
            # Discard old stadium if exists
            if state.stadium is not None:
                # TODO: Determine owner and move to their discard
                pass

            state.stadium = card
            player.stadium_played_this_turn = True

        return state

    def _apply_retreat(self, state: GameState, action: Action) -> GameState:
        """
        Retreat Active Pokémon to Bench.

        Constitution Section 5: Removes status conditions and attack effects.
        """
        player = state.get_player(action.player_id)

        if player.board.active_spot:
            # TODO: Discard Energy equal to retreat cost

            # Apply "Switch" effect (Constitution Section 5)
            active = player.board.active_spot
            active.status_conditions.clear()  # Remove all status conditions
            active.attack_effects.clear()  # Remove attack effects

            # Move to bench
            player.board.add_to_bench(active)

            # Promote new Active
            new_active = player.board.remove_from_bench(action.target_id)
            player.board.active_spot = new_active

            player.retreated_this_turn = True

        return state

    def _apply_attack(self, state: GameState, action: Action) -> GameState:
        """
        Execute attack.

        Constitution Section 2, Phase 3:
        1. Validate attack logic exists in logic_registry
        2. Validate Energy Cost
        3. Calculate Damage (Section 4.7 pipeline)
        4. Apply Damage
        5. Check KO
        6. Advance to Cleanup
        """
        player = state.get_player(action.player_id)
        opponent = state.get_opponent()

        if player.board.active_spot and opponent.board.active_spot:
            attacker = player.board.active_spot
            defender = opponent.board.active_spot

            # Validate attack logic exists (Router check)
            attack_name = action.attack_name if hasattr(action, 'attack_name') else action.metadata.get('attack_name')
            if attack_name:
                attack_logic = logic_registry.get_card_logic(attacker.card_id, attack_name)
                if attack_logic is None:
                    # Attack logic not implemented - for now, skip validation
                    # In production, this should raise IllegalActionError
                    pass

            # TODO: Calculate damage using Section 4.7 pipeline
            # 1. Base Damage
            # 2. Weakness (x2)
            # 3. Resistance (-30)
            # 4. Effects on Attacker
            # 5. Effects on Defender

            base_damage = 60  # Placeholder
            final_damage = base_damage

            # Apply damage
            defender.damage_counters += final_damage // 10

            # Check for KO
            # TODO: Get max HP from card definition
            max_hp = 120  # Placeholder
            if defender.is_knocked_out(max_hp):
                # Handle KO (Constitution Section 2, Phase 3)
                state = self._handle_knockout(state, defender, player)

        # Advance to Cleanup phase
        state.current_phase = GamePhase.CLEANUP
        return state

    def _apply_promote_active(self, state: GameState, action: Action) -> GameState:
        """Promote Pokémon from Bench to Active (after KO)."""
        player = state.get_player(action.player_id)

        # Handle bench discard (Section 4.3)
        if action.metadata.get("discard_to_fix_bench", False):
            pokemon = player.board.remove_from_bench(action.card_id)
            if pokemon:
                player.discard.add_card(pokemon)
        else:
            # Normal promotion
            new_active = player.board.remove_from_bench(action.card_id)
            player.board.active_spot = new_active

        return state

    def _apply_end_turn(self, state: GameState, action: Action) -> GameState:
        """
        End turn and advance phase.

        Routes to different phase transitions based on metadata.
        """
        if action.metadata.get("finish_setup", False):
            # Setup complete, advance to draw phase
            state.current_phase = GamePhase.DRAW
            return state

        if action.metadata.get("advance_to_attack", False):
            # Main phase complete, advance to attack
            state.current_phase = GamePhase.ATTACK
            return state

        # Attack phase complete or skipped, advance to cleanup
        state.current_phase = GamePhase.CLEANUP
        return state

    # ========================================================================
    # 7. PHASE TRANSITION RESOLUTION
    # ========================================================================

    def resolve_phase_transition(self, state: GameState) -> GameState:
        """
        Auto-resolve phase transitions and cleanup.

        Constitution Section 2: Turn Structure
        - Apply status damage (Poison, Burn)
        - Check for KOs
        - Reset turn flags
        - Increment turn counters
        - Switch active player
        """
        if state.current_phase == GamePhase.CLEANUP:
            # Step 1: Apply status condition damage (between turns)
            state = self._apply_status_damage(state)

            # Step 2: Check for KOs
            state = self._check_all_knockouts(state)

            # Step 2.5: Remove expired effects
            state = self._resolve_effect_expiration(state)

            # Step 3: Move turn metadata to last_turn_metadata (for cards like Fezandipiti ex)
            state.last_turn_metadata = state.turn_metadata.copy()
            state.turn_metadata = {}

            # Step 4: Reset turn flags
            active_player = state.get_active_player()
            active_player.reset_turn_flags()

            # Step 5: Increment turns_in_play for all Pokémon
            for pokemon in active_player.board.get_all_pokemon():
                pokemon.turns_in_play += 1
                pokemon.abilities_used_this_turn.clear()

            # Step 6: Switch active player
            state.switch_active_player()

            # Step 7: Advance to Draw phase
            state.current_phase = GamePhase.DRAW
            state.turn_count += 1

            # Step 8: Auto-execute draw
            state = self._auto_draw_card(state)

        elif state.current_phase == GamePhase.DRAW:
            # Draw phase auto-resolves
            state = self._auto_draw_card(state)
            state.current_phase = GamePhase.MAIN

        return state

    def _resolve_effect_expiration(self, state: GameState) -> GameState:
        """
        Remove expired effects from active_effects list.

        Called during cleanup phase to remove effects that have expired.

        Args:
            state: Current game state

        Returns:
            Modified game state with expired effects removed
        """
        current_turn = state.turn_count
        current_player = state.active_player_index
        current_phase = state.current_phase.value

        # Filter out expired effects
        active_effects = []
        for effect in state.active_effects:
            if not effect.is_expired(current_turn, current_player, current_phase):
                active_effects.append(effect)

        state.active_effects = active_effects
        return state

    def check_global_permission(
        self,
        state: GameState,
        action_type: str,
        context: Optional[Dict] = None
    ) -> bool:
        """
        Check if an action is allowed given current active effects.

        This is a permission hook that checks active effects before allowing actions.

        Args:
            state: Current game state
            action_type: Type of action being attempted (e.g., "attack", "retreat", "bench_damage", "ability")
            context: Additional context (e.g., {"card_id": "card_123", "player_id": 0})

        Returns:
            True if action is allowed, False if blocked by an effect

        Examples:
            - Manaphy Wave Veil: Blocks "bench_damage"
            - Iron Leaves ex: Blocks "attack" for specific card
            - Path to the Peak: Blocks "ability" for VSTAR Pokémon
            - Klefki: Blocks "ability" for all Pokémon (from Active Spot)
        """
        if context is None:
            context = {}

        # SPECIAL CHECK: Klefki-style passive ability locks (from Active Spot)
        if action_type == "ability":
            acting_card_id = context.get("card_id")
            acting_player_id = context.get("player_id")

            if acting_card_id and acting_player_id is not None:
                # Check opponent's Active Spot for passive ability blockers
                opponent_id = 1 - acting_player_id
                opponent = state.get_player(opponent_id)

                if opponent.board.active_spot:
                    opponent_active = opponent.board.active_spot

                    # Check if opponent's Active has "Block Abilities" effect
                    # This is typically stored in card-specific logic or as an active effect
                    # For Klefki, it would check if the card has this passive ability
                    for effect in state.active_effects:
                        if (effect.source_card_id == opponent_active.id and
                            effect.params.get("blocks_opponent_abilities")):
                            return False

        # Check all active effects
        for effect in state.active_effects:
            prevents = effect.params.get("prevents")

            if prevents == action_type:
                # Check if effect applies to this specific action
                target_card_id = effect.target_card_id
                acting_card_id = context.get("card_id")

                # If effect has a specific target, check if it matches
                if target_card_id and acting_card_id:
                    if target_card_id != acting_card_id:
                        continue  # This effect doesn't apply to this card

                # If effect has a player target, check if it matches
                target_player_id = effect.target_player_id
                acting_player_id = context.get("player_id")

                if target_player_id is not None and acting_player_id is not None:
                    if target_player_id != acting_player_id:
                        continue  # This effect doesn't apply to this player

                # Effect blocks this action
                return False

        # No blocking effects found
        return True

    def _apply_status_damage(self, state: GameState) -> GameState:
        """
        Apply Poison and Burn damage between turns.

        Constitution Section 4.2: This is "Damage Counters", not "Damage".
        """
        for player_state in state.players:
            if player_state.board.active_spot:
                active = player_state.board.active_spot

                # Poison: 1 damage counter
                if StatusCondition.POISONED in active.status_conditions:
                    active.damage_counters += 1

                # Burn: 2 damage counters
                if StatusCondition.BURNED in active.status_conditions:
                    active.damage_counters += 2

        return state

    def _auto_draw_card(self, state: GameState) -> GameState:
        """
        Auto-draw card in Draw Phase.

        Constitution Section 2, Phase 1: Deck out = loss.
        """
        player = state.get_active_player()

        if player.deck.is_empty():
            # Deck out - player loses
            state.result = GameResult.PLAYER_1_WIN if player.player_id == 0 else GameResult.PLAYER_0_WIN
            state.winner_id = 1 - player.player_id
        else:
            # Draw 1 card
            card = player.deck.cards.pop(0)
            player.hand.add_card(card)

        return state

    # ========================================================================
    # 8. WIN CONDITION CHECKS
    # ========================================================================

    def _check_win_conditions(self, state: GameState) -> GameState:
        """
        Check for win conditions.

        Win conditions:
        1. All 6 prizes taken
        2. Opponent has no Pokémon in play
        3. Opponent deck out (checked in draw phase)

        Constitution Section 4.5: Simultaneous win = Sudden Death
        """
        p0 = state.players[0]
        p1 = state.players[1]

        p0_wins = False
        p1_wins = False

        # Check prizes
        if p0.prizes_taken >= 6:
            p0_wins = True
        if p1.prizes_taken >= 6:
            p1_wins = True

        # Check no Pokémon in play
        if not p0.has_any_pokemon_in_play():
            p1_wins = True
        if not p1.has_any_pokemon_in_play():
            p0_wins = True

        # Resolve win conditions
        if p0_wins and p1_wins:
            # Simultaneous win (Constitution Section 4.5)
            state.current_phase = GamePhase.SUDDEN_DEATH
            # TODO: Implement Sudden Death setup
        elif p0_wins:
            state.result = GameResult.PLAYER_0_WIN
            state.winner_id = 0
        elif p1_wins:
            state.result = GameResult.PLAYER_1_WIN
            state.winner_id = 1

        return state

    def _calculate_prizes(self, knocked_out: CardInstance) -> int:
        """
        Calculate number of prizes to award for knocking out a Pokémon.

        Constitution Prize Rules:
        - MEGA: 3 prizes (do NOT end turn when evolving)
        - ex, V, VMAX, VSTAR, GX: 2 prizes
        - Basic/Stage 1/Stage 2: 1 prize

        Args:
            knocked_out: The KO'd Pokémon

        Returns:
            Number of prizes to award (1, 2, or 3)
        """
        subtypes = self._get_card_subtypes(knocked_out)

        # MEGA Pokémon: 3 prizes
        if Subtype.MEGA in subtypes:
            return 3

        # ex, V, VMAX, VSTAR, GX: 2 prizes
        if any(st in subtypes for st in [Subtype.EX, Subtype.V, Subtype.VMAX, Subtype.VSTAR, Subtype.GX]):
            return 2

        # Default: 1 prize
        return 1

    def _handle_knockout(self, state: GameState, knocked_out: CardInstance, winner: PlayerState) -> GameState:
        """
        Handle Pokémon knockout.

        Steps:
        1. Move KO'd Pokémon to discard
        2. Award prize cards (dynamically based on card type)
        3. Set turn metadata flag (for cards like Fezandipiti ex)
        4. Force promotion if bench exists, else check win condition
        """
        owner = state.get_player(knocked_out.owner_id)

        # Move to discard (with all attached cards)
        owner.discard.add_card(knocked_out)
        for energy in knocked_out.attached_energy:
            owner.discard.add_card(energy)
        for tool in knocked_out.attached_tools:
            owner.discard.add_card(tool)

        # Remove from board
        if owner.board.active_spot and owner.board.active_spot.id == knocked_out.id:
            owner.board.active_spot = None
        else:
            owner.board.remove_from_bench(knocked_out.id)

        # Award prizes dynamically based on knocked out Pokémon
        num_prizes = self._calculate_prizes(knocked_out)
        for _ in range(num_prizes):
            if not winner.prizes.is_empty():
                prize = winner.prizes.cards.pop(0)
                winner.hand.add_card(prize)
                winner.prizes_taken += 1

        # Set metadata flag for history tracking (Fezandipiti ex)
        state.turn_metadata['pokemon_knocked_out'] = True

        return state

    def _check_all_knockouts(self, state: GameState) -> GameState:
        """Check all Pokémon for KO status."""
        # TODO: Implement with card definition data for max HP
        return state

    # ========================================================================
    # 9. HELPER METHODS
    # ========================================================================

    def get_max_bench_size(self, state: GameState, player: PlayerState) -> int:
        """
        Get maximum bench size for a player.

        Default: 5
        Area Zero Underdepths: 8 (if player has a Tera Pokémon in play)

        Args:
            state: Current game state
            player: Player to check bench size for

        Returns:
            Maximum number of Pokémon allowed on bench
        """
        default_size = 5

        # Check if Area Zero Underdepths is in play
        if state.stadium and "Area Zero Underdepths" in state.stadium.card_id:
            # Check if player has a Tera Pokémon in play
            has_tera = False
            for pokemon in player.board.get_all_pokemon():
                subtypes = self._get_card_subtypes(pokemon)
                if Subtype.TERA in subtypes:
                    has_tera = True
                    break

            if has_tera:
                return 8

        return default_size

    def _get_card_subtypes(self, card: CardInstance) -> Set[Subtype]:
        """Get subtypes for a card from the card registry."""
        from cards.factory import get_card_definition

        card_def = get_card_definition(card)
        if card_def:
            return set(card_def.subtypes)
        return set()

    def _find_pokemon_by_id(self, player: PlayerState, card_id: str) -> Optional[CardInstance]:
        """Find Pokémon by instance ID in player's board."""
        if player.board.active_spot and player.board.active_spot.id == card_id:
            return player.board.active_spot

        for pokemon in player.board.bench:
            if pokemon and pokemon.id == card_id:
                return pokemon

        return None

    def _coin_flip(self) -> bool:
        """
        Execute coin flip (chance node).

        Returns True for Heads, False for Tails.
        """
        return random.choice([True, False])

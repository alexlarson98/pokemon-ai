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
        elif state.current_phase == GamePhase.MAIN:
            return self._get_main_phase_actions(state)
        elif state.current_phase == GamePhase.DRAW:
            # DRAW phase is now atomic - should never pause here
            # If we reach this state, something is wrong
            return []
        elif state.current_phase == GamePhase.ATTACK:
            # ATTACK phase is now merged into MAIN phase
            # This should not be reached in normal gameplay
            return []
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

        MCTS Optimization: Deduplicates by card name.
        """
        from cards.registry import create_card

        player = state.get_active_player()
        actions = []

        # Get unique Basic Pokémon by name (MCTS deduplication)
        seen_names = set()
        unique_basic_pokemon = []

        for card in player.hand.cards:
            if Subtype.BASIC in self._get_card_subtypes(card):
                card_def = create_card(card.card_id)
                card_name = card_def.name if card_def and hasattr(card_def, 'name') else card.card_id

                if card_name not in seen_names:
                    seen_names.add(card_name)
                    unique_basic_pokemon.append(card)

        # Category 5 Fix: Mulligan deadlock - no basics in hand
        if len(unique_basic_pokemon) == 0:
            # Return REVEAL_HAND_MULLIGAN action to prevent empty action space
            return [Action(
                action_type=ActionType.REVEAL_HAND_MULLIGAN,
                player_id=player.player_id,
                metadata={"reason": "no_basics"}
            )]

        # Must place Active first
        if not player.has_active_pokemon():
            for card in unique_basic_pokemon:
                actions.append(Action(
                    action_type=ActionType.PLACE_ACTIVE,
                    player_id=player.player_id,
                    card_id=card.id
                ))
        else:
            # Can place on Bench (up to max_bench_size)
            max_bench = self.get_max_bench_size(state, player)
            if player.board.get_bench_count() < max_bench:
                for card in unique_basic_pokemon:
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

    def _get_main_phase_actions(self, state: GameState) -> List[Action]:
        """
        Main Phase (Constitution Section 2, Phase 2).

        Actions:
        - Attach Energy (once per turn)
        - Play Trainer (Item/Supporter/Stadium/Tool)
        - Evolve Pokémon (unlimited, subject to evolution sickness)
        - Use Abilities (unlimited, unless "once per turn")
        - Retreat (once per turn)
        - Attack (if able)
        - Pass Turn (end turn without attacking)
        """
        player = state.get_active_player()
        actions = []

        # ACTION 1: Attach Energy (Constitution Section 2, Phase 2)
        if not player.energy_attached_this_turn:
            energy_actions = self._get_attach_energy_actions(state)
            actions.extend(energy_actions)

        # ACTION 2: Play Basic Pokémon to Bench (with deduplication)
        max_bench = self.get_max_bench_size(state, player)
        if player.board.get_bench_count() < max_bench:
            # MCTS Optimization: Deduplicate by card name
            from cards.registry import create_card
            seen_basic_names = set()

            for card in player.hand.cards:
                if Subtype.BASIC in self._get_card_subtypes(card):
                    card_def = create_card(card.card_id)
                    card_name = card_def.name if card_def and hasattr(card_def, 'name') else card.card_id

                    # Only add one action per unique card name
                    if card_name not in seen_basic_names:
                        seen_basic_names.add(card_name)
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

        # ACTION 7: Attack Actions (squashed from ATTACK phase)
        if player.has_active_pokemon():
            active = player.board.active_spot
            attack_actions = self._get_attack_actions(state, active)
            actions.extend(attack_actions)

        # ACTION 8: Pass Turn (end turn without attacking)
        actions.append(Action(
            action_type=ActionType.END_TURN,
            player_id=player.player_id,
            metadata={"pass_turn": True}
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
        """
        Generate energy attachment actions.

        MCTS Optimization: Only one action per unique energy card name per target.
        This prevents action space explosion when holding multiple copies.
        """
        from cards.registry import create_card

        player = state.get_active_player()
        actions = []

        # Find unique energy cards by name (deduplication for MCTS)
        seen_energy_names = set()
        unique_energy_cards = []

        for card in player.hand.cards:
            card_def = create_card(card.card_id)
            if card_def:
                # Check supertype from json_data (for DataDrivenCards)
                supertype = None
                if hasattr(card_def, 'supertype'):
                    supertype = card_def.supertype
                elif hasattr(card_def, 'json_data') and 'supertype' in card_def.json_data:
                    supertype = card_def.json_data['supertype']

                if supertype and supertype.lower() == 'energy':
                    # Get card name for deduplication
                    card_name = card_def.name if hasattr(card_def, 'name') else card.card_id

                    # Only add one representative per unique card name
                    if card_name not in seen_energy_names:
                        seen_energy_names.add(card_name)
                        unique_energy_cards.append(card)

        # Can attach to any Pokémon in play
        targets = player.board.get_all_pokemon()

        # Generate one action per unique energy type per target
        for energy in unique_energy_cards:
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

        MCTS Optimization: Deduplicates source (hand) but preserves targets (board).
        2 Charmeleons in hand + 3 Charmanders on board = 3 actions (not 6).
        """
        from cards.registry import create_card

        player = state.get_active_player()
        actions = []

        # Turn 1 restriction
        if state.turn_count == 1:
            return actions

        # Deduplicate evolution cards by name (source deduplication)
        seen_evo_names = set()
        unique_evolution_cards = []

        for card in player.hand.cards:
            subtypes = self._get_card_subtypes(card)
            if Subtype.STAGE_1 in subtypes or Subtype.STAGE_2 in subtypes:
                card_def = create_card(card.card_id)
                card_name = card_def.name if card_def and hasattr(card_def, 'name') else card.card_id

                # Only add one representative per unique evolution card name
                if card_name not in seen_evo_names:
                    seen_evo_names.add(card_name)
                    unique_evolution_cards.append(card)

        # Find valid targets (Pokémon that can be evolved) - preserve ALL targets
        targets = player.board.get_all_pokemon()

        # Generate actions: 1 source card × all valid targets
        for evo_card in unique_evolution_cards:
            # Get evolution card definition and required pre-evolution name
            evo_card_def = create_card(evo_card.card_id)
            if not evo_card_def or not hasattr(evo_card_def, 'evolves_from'):
                continue  # Skip if no evolution data

            required_pre_evo = evo_card_def.evolves_from
            if not required_pre_evo:
                continue  # Skip if evolves_from is None/empty (data error)

            for target in targets:
                # Check evolution sickness (turns_in_play > 0)
                if target.turns_in_play > 0:
                    # Get target's card definition to check name
                    target_card_def = create_card(target.card_id)
                    if not target_card_def or not hasattr(target_card_def, 'name'):
                        continue  # Skip if target has no name

                    target_name = target_card_def.name

                    # CRITICAL: Only allow evolution if names match exactly
                    if target_name == required_pre_evo:
                        actions.append(Action(
                            action_type=ActionType.EVOLVE,
                            player_id=player.player_id,
                            card_id=evo_card.id,
                            target_id=target.id,
                            metadata={"evolves_from": required_pre_evo, "target_name": target_name}
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

        MCTS Optimization: Deduplicates source (hand) but preserves targets (Tools).
        2 Muscle Bands in hand + 3 Pokémon on board = 3 Tool actions (not 6).
        """
        from cards.registry import create_card

        player = state.get_active_player()
        actions = []

        # Deduplicate by card name for each subtype
        seen_items = set()
        seen_supporters = set()
        seen_stadiums = set()
        seen_tools = set()

        for card in player.hand.cards:
            subtypes = self._get_card_subtypes(card)
            card_def = create_card(card.card_id)
            card_name = card_def.name if card_def and hasattr(card_def, 'name') else card.card_id

            # ITEM: Unlimited (deduplicate by name)
            if Subtype.ITEM in subtypes and card_name not in seen_items:
                # Architecture Fix: Check global permissions (e.g., Item Lock)
                if self.check_global_permission(state, 'play_item', player.player_id):
                    seen_items.add(card_name)
                    actions.append(Action(
                        action_type=ActionType.PLAY_ITEM,
                        player_id=player.player_id,
                        card_id=card.id
                    ))

            # SUPPORTER: Once per turn, not on Turn 1 going first (deduplicate by name)
            if Subtype.SUPPORTER in subtypes and card_name not in seen_supporters:
                if not player.supporter_played_this_turn:
                    # Constitution: No Supporter on Turn 1 going first
                    if not (state.turn_count == 1 and state.active_player_index == 0):
                        # Architecture Fix: Check global permissions (e.g., Supporter Lock)
                        if self.check_global_permission(state, 'play_supporter', player.player_id):
                            seen_supporters.add(card_name)
                            actions.append(Action(
                                action_type=ActionType.PLAY_SUPPORTER,
                                player_id=player.player_id,
                                card_id=card.id
                            ))

            # STADIUM: Once per turn, must have different name (deduplicate by name)
            if Subtype.STADIUM in subtypes and card_name not in seen_stadiums:
                if not player.stadium_played_this_turn:
                    # Check if different from current stadium
                    can_play = True
                    if state.stadium is not None:
                        # TODO: Check card names (requires card definition)
                        # For now, allow if different card_id
                        if state.stadium.card_id == card.card_id:
                            can_play = False

                    if can_play:
                        seen_stadiums.add(card_name)
                        actions.append(Action(
                            action_type=ActionType.PLAY_STADIUM,
                            player_id=player.player_id,
                            card_id=card.id
                        ))

            # TOOL: Attach to Pokémon (deduplicate source, preserve targets)
            if Subtype.TOOL in subtypes and card_name not in seen_tools:
                seen_tools.add(card_name)
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
        - Once per turn (checked via retreated_this_turn flag)
        - Must have enough Energy attached to pay retreat cost
        - Cannot retreat if Asleep or Paralyzed (Constitution Section 6)
        """
        player = state.get_active_player()
        actions = []

        # Check if already retreated this turn
        if player.retreated_this_turn:
            return actions

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

        # Get dynamic retreat cost (accounts for Tools and Effects)
        retreat_cost = self.calculate_retreat_cost(state, active)

        # Calculate total energy provided by attached cards
        # Architecture Fix: Supports special energy cards (e.g., Double Turbo = 2 Colorless)
        provided_energy = self._calculate_provided_energy(active)
        total_energy_count = sum(provided_energy.values())

        # RULE: Must have enough energy to pay retreat cost
        if total_energy_count < retreat_cost:
            return actions  # Not enough energy to retreat

        # Generate retreat actions for each benched Pokémon
        for i, pokemon in enumerate(player.board.bench):
            if pokemon is not None:
                actions.append(Action(
                    action_type=ActionType.RETREAT,
                    player_id=player.player_id,
                    card_id=active.id,
                    target_id=pokemon.id,
                    metadata={"bench_index": i, "retreat_cost": retreat_cost}
                ))

        return actions

    def _get_attack_actions(self, state: GameState, active: CardInstance) -> List[Action]:
        """
        Generate attack actions for Active Pokémon.

        Rules:
        - Turn 1 Rule: Player going first cannot attack on turn 1
        - Must have sufficient Energy to pay cost
        - Check for attack effects (e.g., "cannot attack next turn")
        - Check status conditions (Asleep, Paralyzed)
        """
        player = state.get_active_player()
        actions = []

        # RULE: Turn 1 - Player going first cannot attack
        if state.turn_count == 1 and player.player_id == state.starting_player_id:
            return actions  # No attacks on turn 1 for player going first

        # Check if Pokémon can attack
        if "cannot_attack_next_turn" in active.attack_effects:
            return actions

        # Check status conditions (Constitution Section 5)
        if StatusCondition.ASLEEP in active.status_conditions:
            return actions  # Asleep Pokémon cannot attack
        if StatusCondition.PARALYZED in active.status_conditions:
            return actions  # Paralyzed Pokémon cannot attack

        # Get card definition to check attacks and energy costs
        from cards.registry import create_card
        card_def = create_card(active.card_id)

        if not card_def or not hasattr(card_def, 'attacks'):
            return actions

        # Check each attack for energy requirements
        for attack in card_def.attacks:
            # Calculate total energy provided by attached cards
            # Architecture Fix: Supports special energy cards (e.g., Double Turbo = 2 Colorless)
            provided_energy = self._calculate_provided_energy(active)

            # Get total energy count (sum all types)
            total_energy_count = sum(provided_energy.values())

            # Calculate attack cost with reductions (e.g., Radiant Charizard)
            # Architecture Fix: Supports cost reduction effects
            final_cost = self.calculate_attack_cost(state, active, attack)

            # RULE: Must have enough energy attached
            # Note: This is simplified - proper implementation would check specific energy types
            # For now, we just check total count (colorless energy rule)
            if total_energy_count >= final_cost:
                actions.append(Action(
                    action_type=ActionType.ATTACK,
                    player_id=player.player_id,
                    card_id=active.id,
                    attack_name=attack.name,
                    metadata={"target": "opponent_active", "energy_cost": final_cost}
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
        elif action.action_type == ActionType.REVEAL_HAND_MULLIGAN:
            return self._apply_reveal_hand_mulligan(state, action)
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

    def _apply_reveal_hand_mulligan(self, state: GameState, action: Action) -> GameState:
        """
        Handle mulligan when player has no Basic Pokémon in hand.

        Category 5 Fix: Prevents empty action space crash.

        According to official rules:
        1. Player reveals hand to opponent
        2. Player shuffles hand back into deck
        3. Player draws 7 new cards
        4. Opponent may draw 1 card
        5. Repeat until player has at least 1 Basic Pokémon
        """
        player = state.get_player(action.player_id)

        print(f"[Mulligan] Player {player.player_id} has no Basic Pokémon. Shuffling and redrawing...")

        # Shuffle hand back into deck
        while not player.hand.is_empty():
            card = player.hand.cards.pop(0)
            player.deck.add_card(card)

        # Shuffle deck
        import random
        if state.random_seed is not None:
            random.seed(state.random_seed + state.turn_count)
        random.shuffle(player.deck.cards)

        # Draw 7 new cards
        for _ in range(7):
            if not player.deck.is_empty():
                card = player.deck.cards.pop(0)
                player.hand.add_card(card)

        # Stay in SETUP phase (will check again for basics)
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
        from actions import evolve_pokemon

        try:
            state = evolve_pokemon(
                state=state,
                player_id=action.player_id,
                target_pokemon_id=action.target_id,
                evolution_card_id=action.card_id,
                skip_stage=False
            )
        except ValueError as e:
            # Evolution failed (invalid stage, etc.) - put card back in hand
            print(f"[Evolution Failed] {e}")

        return state

    def _apply_play_item(self, state: GameState, action: Action) -> GameState:
        """
        Play Item card.

        Category 3 Fix: Execute item effect before discarding.
        """
        player = state.get_player(action.player_id)
        card = player.hand.remove_card(action.card_id)

        if card:
            # Execute item effect (delegate to card logic)
            item_logic = logic_registry.get_card_logic(card.card_id, 'effect')
            if item_logic:
                try:
                    # Execute the item effect
                    # target from metadata if provided (e.g., target Pokémon)
                    target = action.metadata.get('target') if action.metadata else None
                    state = item_logic(state, card, target=target)
                except Exception as e:
                    print(f"[WARNING] Item effect failed for {card.card_id}: {e}")
            else:
                print(f"[WARNING] No effect logic found for Item: {card.card_id}")

            # Move to discard after use
            player.discard.add_card(card)

        return state

    def _apply_play_supporter(self, state: GameState, action: Action) -> GameState:
        """
        Play Supporter card.

        Category 3 Fix: Execute supporter effect before discarding.
        """
        player = state.get_player(action.player_id)
        card = player.hand.remove_card(action.card_id)

        if card:
            player.supporter_played_this_turn = True

            # Execute supporter effect (delegate to card logic)
            supporter_logic = logic_registry.get_card_logic(card.card_id, 'effect')
            if supporter_logic:
                try:
                    # Execute the supporter effect
                    # target from metadata if provided
                    target = action.metadata.get('target') if action.metadata else None
                    state = supporter_logic(state, card, target=target)
                except Exception as e:
                    print(f"[WARNING] Supporter effect failed for {card.card_id}: {e}")
            else:
                print(f"[WARNING] No effect logic found for Supporter: {card.card_id}")

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
        from cards.registry import create_card

        player = state.get_player(action.player_id)

        if player.board.active_spot:
            active = player.board.active_spot

            # Get retreat cost from card definition
            card_def = create_card(active.card_id)
            retreat_cost = 0

            if card_def and hasattr(card_def, 'get_retreat_cost'):
                retreat_cost = card_def.get_retreat_cost(state, active)
            elif card_def and hasattr(card_def, 'base_retreat_cost'):
                retreat_cost = card_def.base_retreat_cost
            elif card_def and hasattr(card_def, 'json_data') and 'retreatCost' in card_def.json_data:
                retreat_cost = len(card_def.json_data['retreatCost'])

            # Discard energy equal to retreat cost
            if retreat_cost > 0:
                energy_to_discard = min(retreat_cost, len(active.attached_energy))

                for _ in range(energy_to_discard):
                    if active.attached_energy:
                        energy = active.attached_energy.pop(0)
                        player.discard.add_card(energy)

            # Apply "Switch" effect (Constitution Section 5)
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

            # Category 4 Fix: Check Confusion status
            if StatusCondition.CONFUSED in attacker.status_conditions:
                # Flip coin for confusion check
                coin_result = self._coin_flip()
                if coin_result == "tails":
                    # Confusion damage: 3 damage counters (30 damage) to self
                    attacker.damage_counters += 3
                    print(f"[Confusion] {attacker.card_id} hurt itself in confusion! (30 damage)")

                    # Check if attacker knocked itself out
                    from cards.factory import get_max_hp
                    max_hp = get_max_hp(attacker)
                    if attacker.is_knocked_out(max_hp):
                        # Attacker KO'd itself - no killer for prize calculation
                        state = self._handle_knockout(state, attacker, opponent, killer=None)

                    # Attack fails, advance to cleanup
                    state.current_phase = GamePhase.CLEANUP
                    return state
                else:
                    # Heads: Attack proceeds normally
                    print(f"[Confusion] {attacker.card_id} snapped out of confusion!")

            # Category 2 Fix: Calculate damage dynamically using card logic
            attack_name = action.attack_name if hasattr(action, 'attack_name') else action.metadata.get('attack_name')
            base_damage = 0

            if attack_name:
                attack_logic = logic_registry.get_card_logic(attacker.card_id, attack_name)
                if attack_logic:
                    # Execute attack logic to get damage
                    try:
                        result = attack_logic(state, attacker, defender)
                        if isinstance(result, int):
                            base_damage = result
                        elif isinstance(result, dict) and 'damage' in result:
                            base_damage = result['damage']
                    except Exception as e:
                        # Attack logic failed - log warning and use 0 damage
                        print(f"[WARNING] Attack logic failed for {attack_name}: {e}")
                        base_damage = 0
                else:
                    # Attack logic not implemented - default to 0 damage (not 60)
                    print(f"[WARNING] No attack logic found for {attacker.card_id} - {attack_name}")
                    base_damage = 0

            # TODO: Apply full damage calculation pipeline (Section 4.7)
            # 1. Base Damage (from attack logic above)
            # 2. Weakness (x2)
            # 3. Resistance (-30)
            # 4. Effects on Attacker
            # 5. Effects on Defender

            final_damage = base_damage

            # Apply damage
            defender.damage_counters += final_damage // 10

            # Category 2 Fix: Get max HP from card definition (not hardcoded 120)
            from cards.factory import get_max_hp
            max_hp = get_max_hp(defender)
            if defender.is_knocked_out(max_hp):
                # Handle KO (Constitution Section 2, Phase 3)
                # Architecture Fix: Pass attacker as killer for prize calculation (Briar, Iron Hands ex, etc.)
                state = self._handle_knockout(state, defender, player, killer=attacker)

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

        if action.metadata.get("pass_turn", False):
            # Pass turn (no attack), advance to cleanup
            state.current_phase = GamePhase.CLEANUP
            return state

        # Legacy support: advance_to_attack is now obsolete (phase squashing)
        if action.metadata.get("advance_to_attack", False):
            # This should not happen with squashed phases, but handle gracefully
            state.current_phase = GamePhase.CLEANUP
            return state

        # Default: advance to cleanup
        state.current_phase = GamePhase.CLEANUP
        return state

    # ========================================================================
    # 7. PHASE TRANSITION RESOLUTION
    # ========================================================================

    def resolve_phase_transition(self, state: GameState) -> GameState:
        """
        Auto-resolve phase transitions with atomic fall-through logic.

        ATOMIC TURN CYCLE: Cleanup -> Draw -> Main Phase (single step)
        This ensures MCTS never sees an empty action space in DRAW phase.

        Constitution Section 2: Turn Structure
        - Apply status damage (Poison, Burn)
        - Check for KOs
        - Reset turn flags
        - Increment turn counters
        - Switch active player
        - Draw card (atomic)
        - Enter Main Phase
        """
        # Step 1: Handle CLEANUP phase
        if state.current_phase == GamePhase.CLEANUP:
            # Apply status condition damage (between turns)
            state = self._apply_status_damage(state)

            # Check for KOs
            state = self._check_all_knockouts(state)

            # Remove expired effects
            state = self._resolve_effect_expiration(state)

            # Move turn metadata to last_turn_metadata (for cards like Fezandipiti ex)
            state.last_turn_metadata = state.turn_metadata.copy()
            state.turn_metadata = {}

            # Reset turn flags
            active_player = state.get_active_player()
            active_player.reset_turn_flags()

            # Increment turns_in_play for all Pokémon
            for pokemon in active_player.board.get_all_pokemon():
                pokemon.turns_in_play += 1
                pokemon.abilities_used_this_turn.clear()

            # Switch active player
            state.switch_active_player()
            state.turn_count += 1

            # FALL THROUGH to Draw phase (do not return yet)
            state.current_phase = GamePhase.DRAW

        # Step 2: Handle DRAW phase (atomic - use 'if' not 'elif' for fall-through)
        if state.current_phase == GamePhase.DRAW:
            # Auto-execute draw
            state = self._auto_draw_card(state)

            # Automatically enter Main Phase
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
            print(f"\n[Deck Out] Player {player.player_id} cannot draw - deck is empty!")
        else:
            # Draw 1 card
            card = player.deck.cards.pop(0)
            player.hand.add_card(card)
            print(f"[Draw Phase] Player {player.player_id} draws 1 card (Hand: {len(player.hand.cards)} cards, Deck: {len(player.deck.cards)} remaining)")

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

    def _handle_knockout(self, state: GameState, knocked_out: CardInstance, winner: PlayerState, killer: Optional[CardInstance] = None) -> GameState:
        """
        Handle Pokémon knockout.

        Steps:
        1. Move KO'd Pokémon to discard
        2. Award prize cards (dynamically based on card type, killer, and global effects)
        3. Set turn metadata flag (for cards like Fezandipiti ex)
        4. Force promotion if bench exists, else check win condition

        Args:
            state: Current game state
            knocked_out: Pokémon that was knocked out
            winner: Player who gets the prizes
            killer: Pokémon that scored the KO (None if from damage counters/abilities)
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

        # Award prizes with multi-source modifiers
        # Architecture Fix: Checks victim, killer, and global effects (Briar, Iron Hands ex, etc.)
        num_prizes = self._calculate_prizes(killer, knocked_out, state)
        for _ in range(num_prizes):
            if not winner.prizes.is_empty():
                prize = winner.prizes.cards.pop(0)
                winner.hand.add_card(prize)
                winner.prizes_taken += 1

        # Set metadata flag for history tracking (Fezandipiti ex)
        state.turn_metadata['pokemon_knocked_out'] = True

        return state

    def _check_all_knockouts(self, state: GameState) -> GameState:
        """
        Check all Pokémon for KO status.

        Architecture Fix: Use calculate_max_hp for HP buffs (Tools, global effects).
        """
        for player in state.players:
            # Check active Pokémon
            if player.board.active_spot:
                max_hp = self.calculate_max_hp(state, player.board.active_spot)
                if player.board.active_spot.is_knocked_out(max_hp):
                    # Handle KO logic
                    pass  # KO handling is done elsewhere during attack resolution

            # Check bench Pokémon
            for pokemon in player.board.bench:
                if pokemon:
                    max_hp = self.calculate_max_hp(state, pokemon)
                    if pokemon.is_knocked_out(max_hp):
                        # Handle KO logic
                        pass  # KO handling is done elsewhere

        return state

    # ========================================================================
    # 9. HELPER METHODS
    # ========================================================================

    def get_max_bench_size(self, state: GameState, player: PlayerState) -> int:
        """
        Get maximum bench size for a player.

        Default: 5 (base rule)
        Modifiers applied from active_effects (e.g., Stadium cards like Area Zero Underdepths)

        Architecture: This function is now extensible - Stadium card logic
        (like Area Zero Underdepths) is handled via card-specific logic in the registry,
        not hardcoded string checks.

        Args:
            state: Current game state
            player: Player to check bench size for

        Returns:
            Maximum number of Pokémon allowed on bench
        """
        base_size = 5

        # Check for bench size modifiers in active effects
        # Future: Stadium cards will register effects via logic_registry
        # Example: Area Zero Underdepths sets BENCH_SIZE_MODIFIER effect

        if hasattr(state, 'active_effects') and state.active_effects:
            for effect in state.active_effects:
                if effect.get('type') == 'BENCH_SIZE_MODIFIER':
                    # Check if conditions are met (e.g., has_tera for Area Zero)
                    conditions = effect.get('conditions', {})

                    # Example condition: requires Tera Pokémon in play
                    if conditions.get('requires_tera', False):
                        has_tera = any(
                            Subtype.TERA in self._get_card_subtypes(pokemon)
                            for pokemon in player.board.get_all_pokemon()
                        )
                        if has_tera:
                            modifier = effect.get('modifier', 0)
                            base_size += modifier
                            break

        return base_size

    def calculate_retreat_cost(self, state: GameState, pokemon: CardInstance) -> int:
        """
        Calculate the dynamic retreat cost for a Pokémon, accounting for Tools and Effects.

        Category 2 Fix: Hardcoded Math (Retreat Cost)
        - Base cost from card definition
        - Apply modifiers from Tools (e.g., Float Stone, Air Balloon)
        - Apply modifiers from Effects (e.g., Beach Court Stadium)

        Args:
            state: Current game state
            pokemon: Pokémon to calculate retreat cost for

        Returns:
            Final retreat cost (minimum 0)
        """
        from cards.registry import create_card

        # Get base retreat cost from card definition
        card_def = create_card(pokemon.card_id)
        if not card_def:
            return 0

        base_cost = len(card_def.retreat_cost) if hasattr(card_def, 'retreat_cost') and card_def.retreat_cost else 0

        # Apply retreat cost modifiers from active effects
        modifier = 0
        for effect in state.active_effects:
            # Check if effect applies to this Pokémon
            if effect.target_card_id and effect.target_card_id != pokemon.id:
                continue

            # Apply retreat cost modifier (e.g., Float Stone: -2, Air Balloon: -1)
            if "retreat_cost_modifier" in effect.params:
                modifier += effect.params["retreat_cost_modifier"]

        # Final cost (minimum 0)
        final_cost = max(0, base_cost + modifier)
        return final_cost

    def _get_card_subtypes(self, card: CardInstance) -> Set[Subtype]:
        """Get subtypes for a card from the card registry."""
        from cards.factory import get_card_definition

        card_def = get_card_definition(card)
        if card_def:
            return set(card_def.subtypes)
        return set()

    def _calculate_provided_energy(self, pokemon: CardInstance) -> Dict[str, int]:
        """
        Calculate total energy units provided by attached energy cards.

        Architecture Fix: Energy cards can provide different amounts (e.g., Double Turbo = 2 Colorless).
        This method supports custom energy values via logic_registry.

        Args:
            pokemon: Pokémon with attached energy cards

        Returns:
            Dictionary mapping energy type to count (e.g., {'F': 2, 'C': 2})
        """
        from typing import Dict
        from cards.registry import create_card
        from cards.logic_registry import get_card_logic

        energy_totals: Dict[str, int] = {}

        if not pokemon.attached_energy:
            return energy_totals

        for energy_card in pokemon.attached_energy:
            # Get card definition to determine energy type
            card_def = create_card(energy_card.card_id)
            if not card_def:
                continue

            # Check for custom energy value logic (e.g., Double Turbo Energy)
            custom_logic = get_card_logic(energy_card.card_id, 'energy_value')

            if custom_logic:
                # Call custom logic to get energy value
                # Example: Double Turbo returns {'C': 2}
                try:
                    custom_value = custom_logic(energy_card, pokemon, None)
                    if isinstance(custom_value, dict):
                        for energy_type, amount in custom_value.items():
                            energy_totals[energy_type] = energy_totals.get(energy_type, 0) + amount
                except Exception:
                    # Fallback to default if custom logic fails
                    pass
            else:
                # Default: 1 unit of the card's defined type
                # Get energy type from card definition
                energy_type = getattr(card_def, 'provides', None)
                if energy_type:
                    # Handle both single type and list of types
                    if isinstance(energy_type, list):
                        # Multi-type energy (e.g., Rainbow Energy)
                        # For now, count as Colorless
                        energy_totals['C'] = energy_totals.get('C', 0) + 1
                    else:
                        # Single type energy
                        energy_totals[energy_type] = energy_totals.get(energy_type, 0) + 1

        return energy_totals

    def check_global_permission(self, state: GameState, action_type: str, player_id: int) -> bool:
        """
        Check if an action is permitted based on global effects (e.g., Item Lock).

        Architecture: This enables card abilities like "Your opponent can't play Item cards"
        to be implemented via active_effects, without hardcoding logic in the engine.

        Args:
            state: Current game state
            action_type: Type of action (e.g., 'play_item', 'play_supporter', 'attach_energy')
            player_id: Player attempting the action

        Returns:
            True if action is permitted, False if blocked
        """
        # Check for permission blocks in active effects
        if hasattr(state, 'active_effects') and state.active_effects:
            for effect in state.active_effects:
                # Check for action blocks (e.g., Item Lock)
                if effect.get('type') == 'ACTION_BLOCK':
                    blocked_action = effect.get('blocked_action')
                    affected_player = effect.get('affected_player')

                    # Check if this effect blocks the current action
                    if blocked_action == action_type:
                        # Check if it affects this player
                        # affected_player can be: 'opponent', 'all', specific player_id
                        if affected_player == 'all' or affected_player == player_id:
                            return False
                        if affected_player == 'opponent':
                            # Determine who set the effect (usually the other player)
                            effect_owner = effect.get('owner_id')
                            if effect_owner is not None and effect_owner != player_id:
                                return False

        return True  # Default: action is permitted

    def calculate_max_hp(self, state: GameState, pokemon: CardInstance) -> int:
        """
        Calculate maximum HP for a Pokémon, including buffs from Tools and global effects.

        Architecture: Enables HP buffs like "Bravery Charm (+50 HP)" and global effects
        like "+40 HP to all Grass Pokémon" without hardcoding in the engine.

        Args:
            state: Current game state
            pokemon: Pokémon to calculate HP for

        Returns:
            Maximum HP after applying all modifiers
        """
        from cards.factory import get_max_hp
        from cards.registry import create_card
        from cards.logic_registry import get_card_logic

        # Get base HP from card definition
        base_hp = get_max_hp(pokemon)

        total_modifier = 0

        # Check Tool cards attached to this Pokémon
        if hasattr(pokemon, 'attached_tools') and pokemon.attached_tools:
            for tool in pokemon.attached_tools:
                # Check for HP modification logic
                hp_logic = get_card_logic(tool.card_id, 'hp_modifier')
                if hp_logic:
                    try:
                        modifier = hp_logic(tool, pokemon, state)
                        if isinstance(modifier, int):
                            total_modifier += modifier
                    except Exception:
                        pass  # Ignore errors in custom logic

        # Check global effects (e.g., "+40 HP to all Grass Pokémon")
        if hasattr(state, 'active_effects') and state.active_effects:
            for effect in state.active_effects:
                if effect.get('type') == 'HP_MODIFIER':
                    # Check if conditions are met
                    conditions = effect.get('conditions', {})

                    # Example condition: type_required = 'Grass'
                    applies = True
                    if 'type_required' in conditions:
                        card_def = create_card(pokemon.card_id)
                        if card_def and hasattr(card_def, 'types'):
                            if conditions['type_required'] not in card_def.types:
                                applies = False

                    if applies:
                        total_modifier += effect.get('modifier', 0)

        return max(1, base_hp + total_modifier)  # Minimum 1 HP

    def calculate_attack_cost(self, state: GameState, pokemon: CardInstance, attack) -> int:
        """
        Calculate attack cost after applying reductions from abilities and effects.

        Architecture: Enables cost reduction like "Radiant Charizard: -2 energy for Fire attacks"
        without hardcoding in the engine.

        Args:
            state: Current game state
            pokemon: Pokémon using the attack
            attack: Attack object from card definition

        Returns:
            Final energy cost after reductions (minimum 0)
        """
        # Get base cost
        base_cost = getattr(attack, 'converted_energy_cost', 0)

        total_reduction = 0

        # Check global effects for cost reductions
        if hasattr(state, 'active_effects') and state.active_effects:
            for effect in state.active_effects:
                if effect.get('type') == 'ATTACK_COST_REDUCTION':
                    # Check if conditions are met
                    conditions = effect.get('conditions', {})

                    applies = True

                    # Example: Check attack type (e.g., "Fire attacks only")
                    if 'attack_type_required' in conditions:
                        attack_types = getattr(attack, 'cost', [])  # Energy types in cost
                        if conditions['attack_type_required'] not in attack_types:
                            applies = False

                    # Example: Check if attacker matches (e.g., "Basic Pokémon only")
                    if 'attacker_subtype' in conditions:
                        subtypes = self._get_card_subtypes(pokemon)
                        from models import Subtype
                        required = conditions['attacker_subtype']
                        if required == 'BASIC' and Subtype.BASIC not in subtypes:
                            applies = False

                    if applies:
                        total_reduction += effect.get('reduction', 0)

        return max(0, base_cost - total_reduction)

    def _calculate_prizes(self, killer: Optional[CardInstance], victim: CardInstance, state: GameState) -> int:
        """
        Calculate number of prizes to award for a knockout.

        Multi-source prize modifiers:
        1. Victim-based (2 for ex/V, 3 for VMAX, 1 for regular)
        2. Attack-based (e.g., Iron Hands ex: Take 1 extra prize)
        3. Global effects (e.g., Briar: +1 if Tera killer and opponent has 2 prizes left)

        Architecture: Effects register as PRIZE_COUNT_MODIFIER with their own condition checks.

        Args:
            killer: Pokémon that scored the KO (None if KO from damage counter placement)
            victim: Pokémon that was knocked out
            state: Current game state

        Returns:
            Number of prizes to award
        """
        from cards.registry import create_card

        # Base prizes from victim
        victim_def = create_card(victim.card_id)
        base_prizes = 1  # Default

        if victim_def and hasattr(victim_def, 'subtypes'):
            from models import Subtype
            # Determine base prize count from victim's rule box
            if Subtype.VMAX in victim_def.subtypes or Subtype.VSTAR in victim_def.subtypes:
                base_prizes = 3
            elif Subtype.V in victim_def.subtypes or Subtype.EX in victim_def.subtypes or Subtype.GX in victim_def.subtypes:
                base_prizes = 2

        total_modifier = 0

        # Check global effects for prize modifiers
        if hasattr(state, 'active_effects') and state.active_effects:
            for effect in state.active_effects:
                if effect.get('type') == 'PRIZE_COUNT_MODIFIER':
                    # The effect's condition logic determines if it applies
                    # Example: Briar checks "Is killer Tera?" and "Opponent has 2 prizes left?"
                    condition_func = effect.get('condition_check')

                    if condition_func:
                        # Call condition function with context
                        try:
                            if condition_func(killer, victim, state):
                                total_modifier += effect.get('modifier', 0)
                        except Exception:
                            pass  # Ignore errors in condition checks
                    else:
                        # No condition - always applies
                        total_modifier += effect.get('modifier', 0)

        # Attack-based modifiers (e.g., Iron Hands ex ability)
        # These should also be registered as effects during attack execution

        return max(1, base_prizes + total_modifier)

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

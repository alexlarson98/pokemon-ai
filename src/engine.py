"""
Pokémon TCG Engine - Physics Engine (engine.py)
The "Referee" - Enforces the Constitution and manages state transitions.
Never guesses; only validates and executes.
"""

from typing import List, Optional, Set, Tuple, Dict, Union
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
    SearchAndAttachState,
    InterruptPhase,
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

        Priority Order (highest first):
        1. Resolution Stack (NEW) - Sequential state machine for complex actions
        2. Legacy SearchAndAttachState - Old interrupt system (deprecated)
        3. Promote Active - Must promote when Active KO'd
        4. Bench Collapse - Must discard when bench exceeds max

        Examples:
        - Resolution Stack -> Ultra Ball discard selection, Rare Candy target selection
        - Active Pokémon KO'd -> Must promote from bench
        - Bench > max_size -> Must discard Pokémon
        """
        player = state.get_active_player()
        actions = []

        # INTERRUPT 0: Resolution Stack (HIGHEST PRIORITY - new sequential state machine)
        if state.resolution_stack:
            return self._get_resolution_stack_actions(state)

        # INTERRUPT 1: Legacy SearchAndAttachState (kept for backward compatibility)
        if state.pending_interrupt is not None:
            interrupt = state.pending_interrupt
            return self._get_search_and_attach_actions(state, interrupt)

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

    def _get_search_and_attach_actions(self, state: GameState, interrupt: SearchAndAttachState) -> List[Action]:
        """
        Generate actions for SearchAndAttachState interrupt.

        This handles multi-step abilities like Infernal Reign:
        1. SELECT_COUNT phase: Choose how many cards to search (0, 1, 2, ... up to available)
        2. ATTACH_ENERGY phase: Choose target for each selected card

        This design reduces branching factor for MCTS by collapsing the iterative
        "select card, select card, confirm" flow into a single upfront count decision.

        Args:
            state: Current game state
            interrupt: The SearchAndAttachState tracking this ability

        Returns:
            List of legal actions for current interrupt phase
        """
        from cards.registry import create_card
        from cards.base import EnergyCard
        from models import EnergyType

        actions = []
        player = state.get_player(interrupt.player_id)

        if interrupt.phase == InterruptPhase.SELECT_COUNT:
            # PHASE 1: Select how many cards to search (upfront count selection)
            # This replaces the iterative select-confirm flow with a single decision

            # Count how many cards in deck match the filter
            matching_cards = []
            for deck_card in player.deck.cards:
                if self._card_matches_search_filter(deck_card, interrupt.search_filter):
                    matching_cards.append(deck_card)

            # Available count is min(max_select, cards_in_deck_matching_filter)
            available_count = min(interrupt.max_select, len(matching_cards))

            # Get a display name for the card type being searched
            card_type_name = "card"
            if matching_cards:
                card_def = create_card(matching_cards[0].card_id)
                if card_def:
                    card_type_name = card_def.name

            # Generate actions for each valid count (0 to available_count)
            for count in range(available_count + 1):
                if count == 0:
                    label = f"Decline {interrupt.ability_name} (attach 0)"
                else:
                    label = f"Attach {count} {card_type_name}" if count == 1 else f"Attach {count} {card_type_name}"

                actions.append(Action(
                    action_type=ActionType.SEARCH_SELECT_COUNT,
                    player_id=interrupt.player_id,
                    choice_index=count,
                    metadata={
                        "ability_name": interrupt.ability_name,
                        "source_card_id": interrupt.source_card_id,
                        "selected_count": count
                    },
                    display_label=label
                ))

        elif interrupt.phase == InterruptPhase.SEARCH_SELECT:
            # LEGACY PHASE: Iterative card selection (kept for backward compatibility)
            # New code should use SELECT_COUNT phase instead

            # Get already selected count
            selected_count = len(interrupt.selected_card_ids)

            if selected_count < interrupt.max_select:
                # Can still select more cards - show selectable options
                # Deduplicate by card name (MCTS optimization - identical cards are equivalent)
                seen_card_names = set()

                for deck_card in player.deck.cards:
                    # Skip already selected cards
                    if deck_card.id in interrupt.selected_card_ids:
                        continue

                    # Check if card matches filter
                    if self._card_matches_search_filter(deck_card, interrupt.search_filter):
                        card_def = create_card(deck_card.card_id)
                        card_name = card_def.name if card_def else deck_card.card_id

                        # Only show one action per unique card name
                        if card_name in seen_card_names:
                            continue
                        seen_card_names.add(card_name)

                        actions.append(Action(
                            action_type=ActionType.SEARCH_SELECT_CARD,
                            player_id=interrupt.player_id,
                            card_id=deck_card.id,
                            metadata={
                                "ability_name": interrupt.ability_name,
                                "source_card_id": interrupt.source_card_id
                            },
                            display_label=f"Select {card_name} ({selected_count + 1}/{interrupt.max_select})"
                        ))

            # Always allow confirming selection (even with 0 selected - "decline" option)
            if selected_count == 0:
                confirm_label = f"Decline {interrupt.ability_name} (select 0 cards)"
            else:
                confirm_label = f"Confirm selection ({selected_count} card{'s' if selected_count != 1 else ''})"

            actions.append(Action(
                action_type=ActionType.SEARCH_CONFIRM,
                player_id=interrupt.player_id,
                metadata={
                    "ability_name": interrupt.ability_name,
                    "source_card_id": interrupt.source_card_id,
                    "selected_count": selected_count
                },
                display_label=confirm_label
            ))

        elif interrupt.phase == InterruptPhase.ATTACH_ENERGY:
            # PHASE 2: Attach each selected card to a target Pokemon
            if interrupt.cards_to_attach:
                current_card_id = interrupt.cards_to_attach[0]

                # Find the card in the "limbo" (it's been removed from deck but not attached yet)
                # For display purposes, get the card name
                card_name = "Energy"
                for deck_card in player.deck.cards:
                    if deck_card.id == current_card_id:
                        card_def = create_card(deck_card.card_id)
                        card_name = card_def.name if card_def else "Energy"
                        break

                # Generate one action per valid target Pokemon
                all_pokemon = player.board.get_all_pokemon()
                attach_num = interrupt.current_attach_index + 1
                total = len(interrupt.selected_card_ids)

                for pokemon in all_pokemon:
                    pokemon_def = create_card(pokemon.card_id)
                    pokemon_name = pokemon_def.name if pokemon_def else pokemon.card_id

                    actions.append(Action(
                        action_type=ActionType.INTERRUPT_ATTACH_ENERGY,
                        player_id=interrupt.player_id,
                        card_id=current_card_id,
                        target_id=pokemon.id,
                        metadata={
                            "ability_name": interrupt.ability_name,
                            "source_card_id": interrupt.source_card_id,
                            "attach_index": interrupt.current_attach_index
                        },
                        display_label=f"Attach {card_name} to {pokemon_name} ({attach_num}/{total})"
                    ))

        return actions

    def _card_matches_search_filter(self, card: CardInstance, search_filter: Dict) -> bool:
        """
        Check if a card matches the search filter criteria.

        Args:
            card: CardInstance to check
            search_filter: Dict with filter criteria (e.g., {'energy_type': 'Fire', 'subtype': 'Basic'})

        Returns:
            True if card matches all filter criteria
        """
        from cards.registry import create_card
        from cards.base import EnergyCard
        from models import EnergyType

        card_def = create_card(card.card_id)
        if not card_def:
            return False

        # Check energy_type filter
        if 'energy_type' in search_filter:
            if not isinstance(card_def, EnergyCard):
                return False
            required_type = search_filter['energy_type']
            if hasattr(card_def, 'energy_type'):
                if isinstance(required_type, str):
                    required_type = EnergyType(required_type)
                if card_def.energy_type != required_type:
                    return False
            else:
                return False

        # Check subtype filter (e.g., Basic energy)
        if 'subtype' in search_filter:
            required_subtype = search_filter['subtype']
            if hasattr(card_def, 'subtypes'):
                if isinstance(required_subtype, str):
                    required_subtype = Subtype(required_subtype)
                if required_subtype not in card_def.subtypes:
                    return False
            else:
                return False

        return True

    # ========================================================================
    # 2b. RESOLUTION STACK ACTIONS (Sequential State Machine)
    # ========================================================================

    def _get_resolution_stack_actions(self, state: GameState) -> List[Action]:
        """
        Generate actions for the current resolution stack step.

        The resolution stack is a LIFO structure where each step represents
        one atomic decision point. Only the TOP step generates actions.

        Returns:
            List of legal actions for the current step
        """
        from models import (
            StepType, SelectFromZoneStep, SearchDeckStep,
            AttachToTargetStep, EvolveTargetStep, ActionType,
            ZoneType, SelectionPurpose
        )
        from cards.registry import create_card
        from cards.base import PokemonCard

        if not state.resolution_stack:
            return []

        current_step = state.resolution_stack[-1]
        player = state.get_player(current_step.player_id)
        actions = []

        if current_step.step_type == StepType.SELECT_FROM_ZONE:
            actions = self._get_select_from_zone_actions(state, current_step, player)

        elif current_step.step_type == StepType.SEARCH_DECK:
            actions = self._get_search_deck_actions(state, current_step, player)

        elif current_step.step_type == StepType.ATTACH_TO_TARGET:
            actions = self._get_attach_to_target_actions(state, current_step, player)

        elif current_step.step_type == StepType.EVOLVE_TARGET:
            actions = self._get_evolve_target_actions(state, current_step, player)

        return actions

    def _get_select_from_zone_actions(
        self,
        state: GameState,
        step: 'SelectFromZoneStep',
        player: PlayerState
    ) -> List[Action]:
        """
        Generate SELECT_CARD actions for a SelectFromZoneStep.

        Used for:
        - Discarding cards from hand (Ultra Ball cost)
        - Selecting Pokemon on bench (Rare Candy base)
        - Selecting evolution card from hand (Rare Candy)
        - Selecting energy to attach (Attach Energy)

        For energy selection, identical cards are deduplicated by functional ID
        so players don't see "Basic Fire Energy" listed multiple times.
        """
        from models import ActionType, ZoneType, SelectionPurpose
        from cards.registry import create_card
        from cards.base import PokemonCard

        actions = []

        # Get cards from the specified zone
        zone_cards = self._get_zone_cards(player, step.zone)

        # Filter out excluded cards and already-selected cards
        available_cards = [
            card for card in zone_cards
            if card.id not in step.exclude_card_ids
            and card.id not in step.selected_card_ids
        ]

        # Apply filter criteria if specified
        if step.filter_criteria:
            available_cards = [
                card for card in available_cards
                if self._card_matches_step_filter(card, step.filter_criteria, state, player)
            ]

        # Calculate how many more selections are needed
        remaining_selections = step.count - len(step.selected_card_ids)

        # Generate SELECT_CARD action for each available card (only if we can still select more)
        if remaining_selections > 0:
            # Deduplicate by functional ID for certain purposes
            # so identical cards show as one option (reduces branching factor)
            should_deduplicate = step.purpose in (
                SelectionPurpose.ENERGY_TO_ATTACH,
                SelectionPurpose.EVOLUTION_STAGE,  # Rare Candy Stage 2 selection
                SelectionPurpose.DISCARD_COST,     # Ultra Ball discard - functionally identical
            )

            if should_deduplicate:
                # Group cards by functional ID
                seen_functional_ids = set()
                deduplicated_cards = []
                for card in available_cards:
                    # Use functional_id_map if available, otherwise use card_id
                    functional_id = player.functional_id_map.get(card.card_id, card.card_id)
                    if functional_id not in seen_functional_ids:
                        seen_functional_ids.add(functional_id)
                        deduplicated_cards.append(card)
                available_cards = deduplicated_cards

            for card in available_cards:
                card_def = create_card(card.card_id)
                card_name = card_def.name if card_def else card.card_id

                # Build descriptive label
                selection_num = len(step.selected_card_ids) + 1
                purpose_label = self._get_purpose_label(step.purpose)

                actions.append(Action(
                    action_type=ActionType.SELECT_CARD,
                    player_id=player.player_id,
                    card_id=card.id,
                    metadata={
                        "step_type": step.step_type.value,
                        "purpose": step.purpose.value,
                        "zone": step.zone.value,
                        "selection_number": selection_num,
                        "max_selections": step.count,
                        "source_card": step.source_card_name
                    },
                    display_label=f"{step.source_card_name}: Select {card_name} ({purpose_label} {selection_num}/{step.count})"
                ))

        # Add CONFIRM_SELECTION action if minimum selections reached
        if len(step.selected_card_ids) >= step.min_count:
            # Can confirm with current selection (or 0 if min_count is 0)
            if step.exact_count and len(step.selected_card_ids) < step.count:
                # Exact count required but not met - can only confirm if no more cards available
                if not available_cards:
                    actions.append(self._create_confirm_action(state, step, player))
            else:
                actions.append(self._create_confirm_action(state, step, player))

        return actions

    def _get_search_deck_actions(
        self,
        state: GameState,
        step: 'SearchDeckStep',
        player: PlayerState
    ) -> List[Action]:
        """
        Generate SELECT_CARD actions for a SearchDeckStep.

        Used for:
        - Nest Ball (search for Basic Pokemon)
        - Ultra Ball (search for any Pokemon)
        - Buddy-Buddy Poffin (search for Basic HP ≤ 70)
        - Call for Family (search for Basic Pokemon)

        Cards are deduplicated by functional ID so identical cards
        (e.g., two Charmanders with same stats) show as one option.

        Knowledge Layer:
        - If has_searched_deck=False: Generate options based on theoretical deck
          contents (initial_deck_counts minus known cards). This respects
          imperfect information - player doesn't know what's prized.
        - If has_searched_deck=True: Use actual deck contents (perfect knowledge).
        """
        from models import ActionType
        from cards.registry import create_card
        from cards.base import PokemonCard

        actions = []

        # Calculate remaining selections
        remaining_selections = step.count - len(step.selected_card_ids)

        if remaining_selections <= 0:
            # No more selections allowed, just add confirm if valid
            if len(step.selected_card_ids) >= step.min_count:
                actions.append(self._create_confirm_action(state, step, player))
            return actions

        # Determine available cards based on knowledge state
        if player.has_searched_deck or not player.initial_deck_counts:
            # Perfect knowledge: use actual deck contents
            available_cards = [
                card for card in player.deck.cards
                if card.id not in step.selected_card_ids
                and self._card_matches_step_filter(card, step.filter_criteria, state, player)
            ]
        else:
            # Imperfect knowledge: generate options from theoretical deck contents
            # Player knows initial_deck_counts but doesn't know which cards are prized
            available_cards = self._get_theoretical_deck_cards(
                player, step, state
            )

        # Deduplicate by functional ID so identical cards show as one option
        seen_functional_ids = set()
        deduplicated_cards = []
        for card in available_cards:
            # Use functional_id_map if available, otherwise compute
            functional_id = player.functional_id_map.get(card.card_id)
            if not functional_id:
                card_def = create_card(card.card_id)
                if card_def:
                    if isinstance(card_def, PokemonCard):
                        functional_id = self._compute_functional_id(card_def)
                    else:
                        functional_id = card_def.name if hasattr(card_def, 'name') else card.card_id
                else:
                    functional_id = card.card_id

            if functional_id not in seen_functional_ids:
                seen_functional_ids.add(functional_id)
                deduplicated_cards.append(card)

        for card in deduplicated_cards:
            card_def = create_card(card.card_id)
            card_name = card_def.name if card_def else card.card_id

            selection_num = len(step.selected_card_ids) + 1

            actions.append(Action(
                action_type=ActionType.SELECT_CARD,
                player_id=player.player_id,
                card_id=card.id,
                metadata={
                    "step_type": step.step_type.value,
                    "purpose": step.purpose.value,
                    "selection_number": selection_num,
                    "max_selections": step.count,
                    "source_card": step.source_card_name,
                    "destination": step.destination.value
                },
                display_label=f"{step.source_card_name}: Search {card_name} ({selection_num}/{step.count})"
            ))

        # Add CONFIRM_SELECTION action (can always confirm search, even with 0 results)
        if len(step.selected_card_ids) >= step.min_count:
            actions.append(self._create_confirm_action(state, step, player))

        # Always allow "fail search" option
        if len(step.selected_card_ids) == 0 and step.min_count == 0:
            # Already included via confirm action above
            pass

        return actions

    def _get_theoretical_deck_cards(
        self,
        player: 'PlayerState',
        step: 'SearchDeckStep',
        state: 'GameState'
    ) -> List['CardInstance']:
        """
        Generate theoretical deck contents based on imperfect information.

        Uses FUNCTIONAL IDs to distinguish between different card versions:
        - Pidgey 50HP and Pidgey 60HP are functionally different
        - Both should appear as separate options in search

        Logic:
        - Player knows initial_deck_counts (keyed by functional ID)
        - Player knows cards in hand (visible)
        - Available = initial_deck_counts minus cards in hand (by functional ID)

        The player doesn't know which cards are in deck vs prizes, so we show
        ALL cards that COULD be in the deck. If they select a prized card,
        the search fails but they gain knowledge of deck/prize contents.

        Returns CardInstance objects from deck+prizes combined, with one
        representative per unique FUNCTIONAL ID.
        """
        from cards.registry import create_card
        from cards.base import PokemonCard
        from collections import Counter

        # Count cards in hand by FUNCTIONAL ID
        hand_counts = Counter()
        for card in player.hand.cards:
            functional_id = player.functional_id_map.get(card.card_id)
            if not functional_id:
                # Compute it if not in map
                card_def = create_card(card.card_id)
                if isinstance(card_def, PokemonCard):
                    functional_id = self._compute_functional_id(card_def)
                else:
                    functional_id = card_def.name if card_def else card.card_id
            hand_counts[functional_id] += 1

        # Calculate theoretical available counts by FUNCTIONAL ID
        # Available = initial_deck_counts - hand_counts
        theoretical_counts = {}
        for functional_id, initial_count in player.initial_deck_counts.items():
            available = initial_count - hand_counts.get(functional_id, 0)
            if available > 0:
                theoretical_counts[functional_id] = available

        # Now find actual card instances from deck+prizes that match theoretical availability
        # We need real CardInstance objects so SELECT_CARD actions have valid card IDs
        result = []
        seen_functional_ids = set()

        # Combine deck and prizes - these are the "hidden zone"
        hidden_cards = list(player.deck.cards) + list(player.prizes.cards)

        for card in hidden_cards:
            if card.id in step.selected_card_ids:
                continue

            # Get functional ID for this card
            functional_id = player.functional_id_map.get(card.card_id)
            if not functional_id:
                card_def = create_card(card.card_id)
                if isinstance(card_def, PokemonCard):
                    functional_id = self._compute_functional_id(card_def)
                else:
                    functional_id = card_def.name if card_def else card.card_id

            # Only include if this functional ID is in theoretical available
            if functional_id not in theoretical_counts:
                continue

            # Only include if matches filter criteria
            if not self._card_matches_step_filter(card, step.filter_criteria, state, player):
                continue

            # Only add one representative per FUNCTIONAL ID
            if functional_id not in seen_functional_ids:
                seen_functional_ids.add(functional_id)
                result.append(card)

        return result

    def _get_attach_to_target_actions(
        self,
        state: GameState,
        step: 'AttachToTargetStep',
        player: PlayerState
    ) -> List[Action]:
        """
        Generate SELECT_CARD actions for AttachToTargetStep.

        Used for:
        - Infernal Reign (attach Fire Energy to Pokemon)
        """
        from models import ActionType
        from cards.registry import create_card

        actions = []

        # Get valid target Pokemon
        for target_id in step.valid_target_ids:
            # Find the Pokemon
            target_pokemon = self._find_pokemon_by_id(player, target_id)
            if not target_pokemon:
                continue

            target_def = create_card(target_pokemon.card_id)
            target_name = target_def.name if target_def else target_pokemon.card_id

            actions.append(Action(
                action_type=ActionType.SELECT_CARD,
                player_id=player.player_id,
                card_id=step.card_to_attach_id,
                target_id=target_id,
                metadata={
                    "step_type": step.step_type.value,
                    "purpose": step.purpose.value,
                    "source_card": step.source_card_name,
                    "card_to_attach": step.card_to_attach_name
                },
                display_label=f"Attach {step.card_to_attach_name} to {target_name}"
            ))

        return actions

    def _get_evolve_target_actions(
        self,
        state: GameState,
        step: 'EvolveTargetStep',
        player: PlayerState
    ) -> List[Action]:
        """
        Generate action for EvolveTargetStep.

        This step has predetermined targets (base + evolution), so it
        generates a single CONFIRM_SELECTION action to execute the evolution.
        No further selection is needed - just confirmation.
        """
        from models import ActionType
        from cards.registry import create_card

        base_pokemon = self._find_pokemon_by_id(player, step.base_pokemon_id)
        if not base_pokemon:
            return []

        evolution_card = player.hand.find_card(step.evolution_card_id)
        if not evolution_card:
            return []

        base_def = create_card(base_pokemon.card_id)
        evo_def = create_card(evolution_card.card_id)

        base_name = base_def.name if base_def else base_pokemon.card_id
        evo_name = evo_def.name if evo_def else evolution_card.card_id

        # Use CONFIRM_SELECTION since targets are already set
        return [Action(
            action_type=ActionType.CONFIRM_SELECTION,
            player_id=player.player_id,
            metadata={
                "step_type": step.step_type.value,
                "purpose": step.purpose.value,
                "source_card": step.source_card_name,
                "is_evolution": True,
                "base_pokemon_id": step.base_pokemon_id,
                "evolution_card_id": step.evolution_card_id
            },
            display_label=f"Evolve {base_name} into {evo_name}"
        )]

    def _create_confirm_action(
        self,
        state: GameState,
        step: 'ResolutionStep',
        player: PlayerState
    ) -> Action:
        """Create a CONFIRM_SELECTION action for the current step."""
        from models import ActionType

        selected_count = 0
        if hasattr(step, 'selected_card_ids'):
            selected_count = len(step.selected_card_ids)

        if selected_count == 0:
            label = f"{step.source_card_name}: Confirm (select nothing)"
        else:
            label = f"{step.source_card_name}: Confirm selection ({selected_count} card{'s' if selected_count != 1 else ''})"

        return Action(
            action_type=ActionType.CONFIRM_SELECTION,
            player_id=player.player_id,
            metadata={
                "step_type": step.step_type.value,
                "purpose": step.purpose.value,
                "source_card": step.source_card_name,
                "selected_count": selected_count
            },
            display_label=label
        )

    def _get_zone_cards(self, player: PlayerState, zone: 'ZoneType') -> List[CardInstance]:
        """Get cards from a player's zone."""
        from models import ZoneType

        if zone == ZoneType.HAND:
            return player.hand.cards
        elif zone == ZoneType.DECK:
            return player.deck.cards
        elif zone == ZoneType.DISCARD:
            return player.discard.cards
        elif zone == ZoneType.BENCH:
            return [p for p in player.board.bench if p is not None]
        elif zone == ZoneType.ACTIVE:
            return [player.board.active_spot] if player.board.active_spot else []
        elif zone == ZoneType.BOARD:
            return player.board.get_all_pokemon()
        return []

    def _card_matches_step_filter(self, card: CardInstance, filter_criteria: Dict, state: GameState = None, player: PlayerState = None) -> bool:
        """
        Check if a card matches step filter criteria.

        Supports filters:
        - supertype: 'Pokemon', 'Trainer', 'Energy'
        - subtype: 'Basic', 'Stage 1', 'Stage 2', 'Item', etc.
        - max_hp: Maximum HP for Pokemon
        - energy_type: For energy cards
        - name: Specific card name
        - evolves_from: For evolution filtering
        - rare_candy_target: Validate Basic has a matching Stage 2 in hand
        """
        from cards.registry import create_card
        from cards.base import PokemonCard, EnergyCard, TrainerCard
        from models import Subtype, Supertype

        if not filter_criteria:
            return True

        card_def = create_card(card.card_id)
        if not card_def:
            return False

        # Check supertype
        if 'supertype' in filter_criteria:
            required = filter_criteria['supertype']
            if required == 'Pokemon' and not isinstance(card_def, PokemonCard):
                return False
            elif required == 'Energy' and not isinstance(card_def, EnergyCard):
                return False
            elif required == 'Trainer' and not isinstance(card_def, TrainerCard):
                return False

        # Check subtype
        if 'subtype' in filter_criteria:
            required = filter_criteria['subtype']
            if isinstance(required, str):
                required = Subtype(required)
            if not hasattr(card_def, 'subtypes') or required not in card_def.subtypes:
                return False

        # Check max_hp (for Buddy-Buddy Poffin)
        if 'max_hp' in filter_criteria:
            if not isinstance(card_def, PokemonCard):
                return False
            if card_def.hp > filter_criteria['max_hp']:
                return False

        # Check energy_type
        if 'energy_type' in filter_criteria:
            if not isinstance(card_def, EnergyCard):
                return False
            if card_def.energy_type != filter_criteria['energy_type']:
                return False

        # Check name
        if 'name' in filter_criteria:
            if card_def.name != filter_criteria['name']:
                return False

        # Check evolves_from (for Rare Candy)
        if 'evolves_from' in filter_criteria:
            if not isinstance(card_def, PokemonCard):
                return False
            if not hasattr(card_def, 'evolves_from') or card_def.evolves_from != filter_criteria['evolves_from']:
                return False

        # Rare Candy: Check if this Basic Pokemon is a valid target
        # (has been in play 1+ turns AND a Stage 2 in hand can evolve from it)
        if 'rare_candy_target' in filter_criteria and filter_criteria['rare_candy_target']:
            # This is a Pokemon in play - check evolution sickness
            if card.turns_in_play < 1:
                return False

            # Must have state and player to validate Stage 2 availability
            if not state or not player:
                return False

            # Check if any Stage 2 in hand can evolve from this specific Basic
            from cards.utils import find_stage_2_chain_for_basic
            from cards.factory import get_card_definition

            has_matching_stage_2 = False
            for hand_card in player.hand.cards:
                hand_def = get_card_definition(hand_card)
                if hand_def and hasattr(hand_def, 'subtypes') and Subtype.STAGE_2 in hand_def.subtypes:
                    if find_stage_2_chain_for_basic(card_def, hand_def):
                        has_matching_stage_2 = True
                        break

            if not has_matching_stage_2:
                return False

        # Rare Candy: Check if this Stage 2 can evolve from the specified Basic
        if 'rare_candy_evolution_for' in filter_criteria:
            base_pokemon_id = filter_criteria['rare_candy_evolution_for']
            if not isinstance(card_def, PokemonCard):
                return False
            if not hasattr(card_def, 'subtypes') or Subtype.STAGE_2 not in card_def.subtypes:
                return False

            # Must have state and player to validate evolution chain
            if not state or not player:
                return False

            # Find the base Pokemon to get its definition
            base_pokemon = self._find_pokemon_by_id(player, base_pokemon_id)
            if not base_pokemon:
                return False

            base_def = create_card(base_pokemon.card_id)
            if not base_def:
                return False

            # Check if this Stage 2 can evolve from the selected Basic
            from cards.utils import find_stage_2_chain_for_basic
            if not find_stage_2_chain_for_basic(base_def, card_def):
                return False

        return True

    def _find_pokemon_by_id(self, player: PlayerState, pokemon_id: str) -> Optional[CardInstance]:
        """Find a Pokemon in play by its instance ID."""
        if player.board.active_spot and player.board.active_spot.id == pokemon_id:
            return player.board.active_spot
        for pokemon in player.board.bench:
            if pokemon and pokemon.id == pokemon_id:
                return pokemon
        return None

    def _get_purpose_label(self, purpose: 'SelectionPurpose') -> str:
        """Get a human-readable label for a selection purpose."""
        from models import SelectionPurpose

        labels = {
            SelectionPurpose.DISCARD_COST: "discard",
            SelectionPurpose.SEARCH_TARGET: "search",
            SelectionPurpose.EVOLUTION_BASE: "base",
            SelectionPurpose.EVOLUTION_STAGE: "evolution",
            SelectionPurpose.ATTACH_TARGET: "attach to",
            SelectionPurpose.BENCH_TARGET: "bench",
        }
        return labels.get(purpose, "select")

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
            if self._is_basic_pokemon(card):
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

        # ACTION 0: Pass Turn (end turn without attacking)
        actions.append(Action(
            action_type=ActionType.END_TURN,
            player_id=player.player_id,
            metadata={"pass_turn": True}
        ))

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
                if self._is_basic_pokemon(card):
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

        # ACTION 6: Use Stadium Effects
        stadium_actions = self._get_stadium_actions(state)
        actions.extend(stadium_actions)

        # ACTION 7: Retreat (Constitution Section 2, Phase 2)
        if not player.retreated_this_turn and player.has_active_pokemon():
            retreat_actions = self._get_retreat_actions(state)
            actions.extend(retreat_actions)

        # ACTION 8: Attack Actions (squashed from ATTACK phase)
        if player.has_active_pokemon():
            active = player.board.active_spot
            attack_actions = self._get_attack_actions(state, active)
            actions.extend(attack_actions)

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
        Generate energy attachment action using the Stack architecture.

        Stack-Based Approach:
        Instead of generating E×T actions (E energy types × T targets),
        this generates a SINGLE action that initiates the resolution stack.

        Stack Sequence:
        1. SelectFromZoneStep: Select energy from hand
        2. AttachToTargetStep: Select target Pokemon (via callback)

        Branching Factor Reduction: E×T → 1 + E + T
        Example: 3 energy types × 5 targets = 15 actions → 1 + 3 + 5 = 9 actions
        """
        from cards.registry import create_card

        player = state.get_active_player()

        # Check if there's any energy in hand
        has_energy = False
        for card in player.hand.cards:
            card_def = create_card(card.card_id)
            if card_def:
                supertype = None
                if hasattr(card_def, 'supertype'):
                    supertype = card_def.supertype
                elif hasattr(card_def, 'json_data') and 'supertype' in card_def.json_data:
                    supertype = card_def.json_data['supertype']

                if supertype and supertype.lower() == 'energy':
                    has_energy = True
                    break

        if not has_energy:
            return []

        # Check if there's any Pokemon to attach to
        targets = player.board.get_all_pokemon()
        if not targets:
            return []

        # Generate a single action to initiate energy attachment
        return [Action(
            action_type=ActionType.ATTACH_ENERGY,
            player_id=player.player_id,
            parameters={'use_stack': True},
            display_label="Attach Energy"
        )]

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
                # Check if already evolved this turn (blocks further evolution)
                if target.evolved_this_turn:
                    continue  # Cannot evolve again this turn

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

                    # Check if card has a custom action generator
                    generator = logic_registry.get_card_logic(card.card_id, 'generator')
                    if generator:
                        # Use generator to create specific actions
                        generated_actions = generator(state, card, player)
                        actions.extend(generated_actions)
                    else:
                        # Fall back to generic action
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

                            # Check if card has a custom action generator
                            generator = logic_registry.get_card_logic(card.card_id, 'generator')
                            if generator:
                                # Use generator to create specific actions
                                generated_actions = generator(state, card, player)
                                actions.extend(generated_actions)
                            else:
                                # Fall back to generic action
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
                    # Check if target has room for a tool (standard rule: max 1 tool)
                    max_tools = self.get_max_tool_capacity(target)
                    if len(target.attached_tools) < max_tools:
                        # Get target definition for name
                        target_def = create_card(target.card_id)
                        target_name = target_def.name if target_def and hasattr(target_def, 'name') else target.card_id

                        # Determine location label
                        if target == player.board.active_spot:
                            location_label = "Active"
                        else:
                            # Find bench index
                            bench_index = next((idx for idx, p in enumerate(player.board.bench) if p and p.id == target.id), -1)
                            location_label = f"Bench {bench_index + 1}"

                        # Create action with display label
                        actions.append(Action(
                            action_type=ActionType.ATTACH_TOOL,
                            player_id=player.player_id,
                            card_id=card.id,
                            target_id=target.id,
                            display_label=f"Attach {card_name} to {target_name} ({location_label})"
                        ))

        return actions

    def _get_ability_actions(self, state: GameState) -> List[Action]:
        """
        Generate ability activation actions.

        Checks global permission for ability usage (Klefki blocks abilities).
        Uses logic_registry to check for custom action generators.
        """
        from cards.registry import create_card
        from cards import logic_registry

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

            # Get card definition to check for abilities
            card_def = create_card(pokemon.card_id)
            if not card_def or not hasattr(card_def, 'abilities'):
                continue

            # Check each ability on the card
            for ability in card_def.abilities:
                # Use unified schema to get ability info
                ability_info = logic_registry.get_ability_info(pokemon.card_id, ability.name)

                if ability_info:
                    # Unified schema: check category to determine if it generates actions
                    category = ability_info.get('category')

                    if category in ('attack', 'activatable'):
                        # This ability generates actions
                        if 'generator' in ability_info:
                            generator = ability_info['generator']
                            generated_actions = generator(state, pokemon, player)
                            actions.extend(generated_actions)
                        else:
                            # Has category but no generator - create generic action
                            if ability.name not in pokemon.abilities_used_this_turn:
                                actions.append(Action(
                                    action_type=ActionType.USE_ABILITY,
                                    player_id=player.player_id,
                                    card_id=pokemon.id,
                                    ability_name=ability.name,
                                    metadata={"ability_name": ability.name}
                                ))
                    # else: modifier/guard/hook - don't generate actions

                else:
                    # No registry entry - check legacy format or infer from ability
                    card_logic = logic_registry.get_card_logic(pokemon.card_id, ability.name)

                    if isinstance(card_logic, dict) and 'generator' in card_logic:
                        # Legacy format with generator
                        generator = card_logic['generator']
                        generated_actions = generator(state, pokemon, player)
                        actions.extend(generated_actions)
                    else:
                        # No registry entry at all - use ability's category field
                        # or fall back to is_activatable for backwards compat
                        ability_category = getattr(ability, 'category', None)

                        if ability_category:
                            # Use category from ability definition
                            if ability_category not in ('activatable', 'attack'):
                                continue  # modifier/guard/hook - skip
                        else:
                            # Final fallback: use is_activatable flag
                            is_activatable = getattr(ability, 'is_activatable', None)
                            if is_activatable is None:
                                # Parse text as last resort
                                ability_text = getattr(ability, 'text', '').lower()
                                is_activatable = (
                                    'once during your turn' in ability_text or
                                    'you may use' in ability_text or
                                    'as often as you like during your turn' in ability_text
                                )

                            if not is_activatable:
                                continue  # Passive ability - skip

                        # Check 'Once Per Turn' restriction
                        if ability.name in pokemon.abilities_used_this_turn:
                            continue

                        # Create generic USE_ABILITY action
                        actions.append(Action(
                            action_type=ActionType.USE_ABILITY,
                            player_id=player.player_id,
                            card_id=pokemon.id,
                            ability_name=ability.name,
                            metadata={"ability_name": ability.name}
                        ))

        return actions

    def _get_stadium_actions(self, state: GameState) -> List[Action]:
        """
        Generate stadium activation actions.

        Checks if there's an active stadium with a 'once per turn' effect
        that can be activated (e.g., Artazon, PokéStop).

        Uses logic_registry to check for custom action generators.
        Most stadiums (like Temple of Sinnoh) are passive and have no actions.
        """
        from cards import logic_registry

        actions = []

        # Check if there's an active stadium
        if not state.stadium:
            return actions

        stadium = state.stadium
        player = state.get_active_player()

        # Check if stadium has a custom action generator
        # Treat stadium effect like a nameless ability - look up by card ID
        card_logic = logic_registry.get_card_logic(stadium.card_id, 'generator')

        if isinstance(card_logic, dict) and 'generator' in card_logic:
            # Stadium has nested structure (for abilities/effects)
            generator = card_logic['generator']
            generated_actions = generator(state, stadium, player)
            actions.extend(generated_actions)
        elif callable(card_logic):
            # Stadium has direct generator function
            generated_actions = card_logic(state, stadium, player)
            actions.extend(generated_actions)
        # else: No generator - stadium is passive (no actions)

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

        # Check attack effects that prevent retreat (e.g., Shadow Bind)
        for effect in active.attack_effects:
            if isinstance(effect, dict) and effect.get('effect_type') == 'prevent_retreat':
                return actions  # Can't retreat due to attack effect

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
        - Uses logic_registry to check for custom action generators
        """
        from cards.registry import create_card
        from cards import logic_registry

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
        card_def = create_card(active.card_id)

        if not card_def or not hasattr(card_def, 'attacks'):
            return actions

        # Check each attack for energy requirements
        for attack in card_def.attacks:
            # Calculate energy cost for this attack
            provided_energy = self._calculate_provided_energy(active)
            final_cost = self.calculate_attack_cost(state, active, attack)

            # RULE: Must have enough energy attached AND correct types
            if not self._can_pay_energy_cost(provided_energy, attack.cost, final_cost):
                continue  # Skip this attack if energy requirements not met

            # Check if card has a custom action generator for this attack
            card_logic = logic_registry.get_card_logic(active.card_id, attack.name)

            if isinstance(card_logic, dict) and 'generator' in card_logic:
                # Use custom generator to create specific actions
                # Generator is only called if energy cost is met
                generator = card_logic['generator']
                generated_actions = generator(state, active, player)
                actions.extend(generated_actions)
            else:
                # Fall back to default logic for attacks without custom generators
                # Energy cost already validated above
                actions.append(Action(
                    action_type=ActionType.ATTACK,
                    player_id=player.player_id,
                    card_id=active.id,
                    attack_name=attack.name,
                    metadata={"target": "opponent_active", "energy_cost": final_cost}
                ))

        return actions

    # ========================================================================
    # 4B. KNOWLEDGE LAYER (Belief-Based Action Generation for ISMCTS)
    # ========================================================================

    def initialize_deck_knowledge(self, state: GameState) -> GameState:
        """
        Initialize deck knowledge for both players at game start.

        Captures the composition of ALL 60 cards in the player's deck, regardless of
        where they are currently located (deck, hand, board, prizes, discard).

        This function should be called AFTER decks are loaded but ideally BEFORE
        any cards are moved to other zones. However, it's designed to handle cases
        where cards have already been moved (e.g., in test scenarios).

        Args:
            state: GameState with player decks loaded

        Returns:
            Modified GameState with knowledge layer initialized
        """
        from cards.registry import create_card
        from cards.base import PokemonCard

        for player in state.players:
            # Name-based counts for belief engine (ISMCTS)
            card_counts = {}

            # Functional ID mapping for action generation
            functional_map = {}

            # Collect ALL cards owned by this player from ALL zones
            all_player_cards = []

            # Deck
            all_player_cards.extend(player.deck.cards)

            # Hand
            all_player_cards.extend(player.hand.cards)

            # Discard
            all_player_cards.extend(player.discard.cards)

            # Prizes
            all_player_cards.extend(player.prizes.cards)

            # Board (active + bench)
            board_pokemon = player.board.get_all_pokemon()
            all_player_cards.extend([p for p in board_pokemon if p is not None])

            # Attached cards (energy, tools on Pokemon)
            for pokemon in board_pokemon:
                if pokemon:
                    all_player_cards.extend(pokemon.attached_energy)
                    all_player_cards.extend(pokemon.attached_tools)

            # Count all cards by FUNCTIONAL ID (not just name)
            # This ensures Pidgey 50HP and Pidgey 60HP are tracked separately
            for card in all_player_cards:
                if card is None:
                    continue

                card_def = create_card(card.card_id)

                # Compute functional ID for this card
                if isinstance(card_def, PokemonCard):
                    functional_id = self._compute_functional_id(card_def)
                else:
                    # Non-Pokemon cards: use name as functional ID
                    card_name = card_def.name if card_def and hasattr(card_def, 'name') else card.card_id
                    functional_id = card_name

                # Count by functional ID (not just name)
                if functional_id in card_counts:
                    card_counts[functional_id] += 1
                else:
                    card_counts[functional_id] = 1

                # Map this card instance to its functional ID
                functional_map[card.card_id] = functional_id

            player.initial_deck_counts = card_counts
            player.functional_id_map = functional_map

        return state

    def _compute_functional_id(self, card_def) -> str:
        """
        Compute a functional ID for a Pokemon card based on gameplay-relevant properties.

        Cards with the same functional ID are interchangeable for deck search purposes.

        Args:
            card_def: PokemonCard definition

        Returns:
            Functional ID string (e.g., "Charmander|70|[attack1,attack2]|[ability1]")
        """
        name = card_def.name
        hp = card_def.hp if hasattr(card_def, 'hp') else 0

        # Sort attacks by name for consistent ordering
        attacks = []
        if hasattr(card_def, 'attacks'):
            for attack in card_def.attacks:
                attack_sig = f"{attack.name}:{attack.damage if hasattr(attack, 'damage') else ''}"
                attacks.append(attack_sig)
        attacks_str = ','.join(sorted(attacks))

        # Sort abilities by name
        abilities = []
        if hasattr(card_def, 'abilities'):
            for ability in card_def.abilities:
                abilities.append(ability.name)
        abilities_str = ','.join(sorted(abilities))

        # Include subtypes for evolution stage differentiation
        subtypes = []
        if hasattr(card_def, 'subtypes'):
            subtypes = [str(s.value) if hasattr(s, 'value') else str(s) for s in card_def.subtypes]
        subtypes_str = ','.join(sorted(subtypes))

        return f"{name}|{hp}|{subtypes_str}|{attacks_str}|{abilities_str}"

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
        elif action.action_type == ActionType.ATTACH_TOOL:
            return self._apply_attach_tool(state, action)
        elif action.action_type == ActionType.RETREAT:
            return self._apply_retreat(state, action)
        elif action.action_type == ActionType.ATTACK:
            return self._apply_attack(state, action)
        elif action.action_type == ActionType.PROMOTE_ACTIVE:
            return self._apply_promote_active(state, action)
        elif action.action_type == ActionType.END_TURN:
            return self._apply_end_turn(state, action)
        # Interrupt Stack Actions
        elif action.action_type == ActionType.SEARCH_SELECT_COUNT:
            return self._apply_search_select_count(state, action)
        elif action.action_type == ActionType.SEARCH_SELECT_CARD:
            return self._apply_search_select_card(state, action)
        elif action.action_type == ActionType.SEARCH_CONFIRM:
            return self._apply_search_confirm(state, action)
        elif action.action_type == ActionType.INTERRUPT_ATTACH_ENERGY:
            return self._apply_interrupt_attach_energy(state, action)
        # Resolution Stack Actions (new sequential state machine)
        elif action.action_type == ActionType.SELECT_CARD:
            return self._apply_select_card(state, action)
        elif action.action_type == ActionType.CONFIRM_SELECTION:
            return self._apply_confirm_selection(state, action)
        elif action.action_type == ActionType.CANCEL_ACTION:
            return self._apply_cancel_action(state, action)
        elif action.action_type == ActionType.USE_ABILITY:
            return self._apply_use_ability(state, action)
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
        """
        Attach Energy card to Pokémon.

        Two modes:
        1. Stack mode (use_stack=True): Push SelectFromZoneStep to select energy
        2. Direct mode (card_id + target_id provided): Execute attachment immediately
        """
        from models import SelectFromZoneStep, ZoneType, SelectionPurpose

        # Check if this is a stack-based action
        if action.parameters and action.parameters.get('use_stack'):
            # Stack mode: Push a step to select energy from hand
            player = state.get_player(action.player_id)

            select_energy_step = SelectFromZoneStep(
                source_card_id="attach_energy",
                source_card_name="Attach Energy",
                player_id=action.player_id,
                purpose=SelectionPurpose.ENERGY_TO_ATTACH,
                zone=ZoneType.HAND,
                count=1,
                exact_count=True,
                filter_criteria={'supertype': 'Energy'},
                on_complete_callback="attach_energy_select_target"
            )

            state.push_step(select_energy_step)
            return state

        # Direct mode: Execute the attachment
        player = state.get_player(action.player_id)
        energy = player.hand.remove_card(action.card_id)

        if energy:
            # Find target Pokémon
            target = self._find_pokemon_by_id(player, action.target_id)
            if target:
                target.attached_energy.append(energy)
                player.energy_attached_this_turn = True

                # 4 Pillars: Trigger "on_attach_energy" hooks
                # Example: Cards that trigger when energy is attached
                self._check_triggers(state, "on_attach_energy", {
                    "energy_card": energy,
                    "target_pokemon": target,
                    "player_id": action.player_id,
                    "source": "hand"
                })

        return state

    def _apply_play_basic(self, state: GameState, action: Action) -> GameState:
        """Play Basic Pokémon to Bench during Main Phase."""
        player = state.get_player(action.player_id)
        card = player.hand.remove_card(action.card_id)

        if card:
            card.turns_in_play = 0  # Reset for evolution sickness
            player.board.add_to_bench(card)

            # Check for "on_play_pokemon" triggers (4 Pillars: Hooks)
            # This allows cards like Flamigo's Insta-Flock to activate
            triggered_actions = self._check_triggers(state, "on_play_pokemon", {
                "card": card,
                "player_id": action.player_id,
                "source": "hand"
            })
            # TODO: Full Interrupt Stack implementation would process these actions
            # For now, we just collect them - they can be processed by the caller

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

        Spark of Life: Uses new standard signature (state, card, action).
        """
        player = state.get_player(action.player_id)
        card = player.hand.remove_card(action.card_id)

        if card:
            # Execute item effect (delegate to card logic)
            item_logic = logic_registry.get_card_logic(card.card_id, 'effect')
            if item_logic:
                # New standard signature: (state, card, action)
                state = item_logic(state, card, action)
            else:
                print(f"[WARNING] No effect logic found for Item: {card.card_id}")

            # Move to discard after use
            player.discard.add_card(card)

        return state

    def _apply_play_supporter(self, state: GameState, action: Action) -> GameState:
        """
        Play Supporter card.

        Spark of Life: Uses new standard signature (state, card, action).
        """
        player = state.get_player(action.player_id)
        card = player.hand.remove_card(action.card_id)

        if card:
            player.supporter_played_this_turn = True

            # Execute supporter effect (delegate to card logic)
            supporter_logic = logic_registry.get_card_logic(card.card_id, 'effect')
            if supporter_logic:
                # New standard signature: (state, card, action)
                state = supporter_logic(state, card, action)
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

    def _apply_attach_tool(self, state: GameState, action: Action) -> GameState:
        """
        Attach a Pokemon Tool card to a Pokemon.

        Args:
            state: Current game state
            action: Action containing card_id (Tool) and target_id (Pokemon)

        Returns:
            Updated game state
        """
        player = state.get_player(action.player_id)

        # Remove tool from hand
        tool_card = player.hand.remove_card(action.card_id)
        if not tool_card:
            return state  # Card not in hand

        # Find target Pokemon
        target_pokemon = None
        if player.board.active_spot and player.board.active_spot.id == action.target_id:
            target_pokemon = player.board.active_spot
        else:
            for bench_pokemon in player.board.bench:
                if bench_pokemon.id == action.target_id:
                    target_pokemon = bench_pokemon
                    break

        if not target_pokemon:
            # Target not found - put card back in hand
            player.hand.add_card(tool_card)
            return state

        # Attach tool to target
        target_pokemon.attached_tools.append(tool_card)

        return state

    def _apply_use_ability(self, state: GameState, action: Action) -> GameState:
        """
        Apply a Pokémon ability effect.

        Looks up the ability's effect function in the logic registry and executes it.

        Args:
            state: Current game state
            action: USE_ABILITY action with card_id and ability_name

        Returns:
            Modified GameState after ability effect
        """
        from cards import logic_registry

        player = state.get_player(action.player_id)

        # Find the Pokemon using the ability
        pokemon = None
        for p in player.board.get_all_pokemon():
            if p.id == action.card_id:
                pokemon = p
                break

        if not pokemon:
            return state

        # Get ability name from action
        ability_name = action.ability_name or action.metadata.get('ability_name', '')

        if not ability_name:
            return state

        # Look up the effect function in logic registry
        card_logic = logic_registry.get_card_logic(pokemon.card_id, ability_name)

        if isinstance(card_logic, dict) and 'effect' in card_logic:
            effect_func = card_logic['effect']
            state = effect_func(state, pokemon, action)
        else:
            # No custom effect - mark as used for once-per-turn abilities
            pokemon.abilities_used_this_turn.add(ability_name)

        # Check for knockouts after ability effect (e.g., Cursed Blast self-KO, damage counter placement)
        # This mirrors the KO check in _apply_attack but handles ability-caused KOs
        from cards.factory import get_max_hp

        # Check all Pokemon on board for KOs (abilities can affect any Pokemon)
        for pid in [0, 1]:
            check_player = state.get_player(pid)
            opponent_player = state.get_player(1 - pid)

            # Check active spot
            if check_player.board.active_spot:
                active = check_player.board.active_spot
                max_hp = get_max_hp(active)
                if active.is_knocked_out(max_hp):
                    # For ability KOs: opponent of the KO'd Pokemon gets the prize
                    # No killer for ability-caused KOs (affects prize calculation)
                    state = self._handle_knockout(state, active, opponent_player, killer=None)

            # Check bench (iterate over copy since we may modify during iteration)
            for bench_pokemon in check_player.board.bench[:]:
                max_hp = get_max_hp(bench_pokemon)
                if bench_pokemon.is_knocked_out(max_hp):
                    # Benched Pokemon KO'd - opponent gets prize
                    state = self._handle_knockout(state, bench_pokemon, opponent_player, killer=None)

        return state

    def _apply_retreat(self, state: GameState, action: Action) -> GameState:
        """
        Retreat Active Pokémon to Bench.

        Constitution Section 5: Removes status conditions and attack effects.
        4 Pillars: Uses calculate_retreat_cost for LOCAL and GLOBAL modifiers.
        """
        player = state.get_player(action.player_id)

        if player.board.active_spot:
            active = player.board.active_spot

            # Use calculate_retreat_cost which handles all modifiers (4 Pillars architecture)
            retreat_cost = self.calculate_retreat_cost(state, active)

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

            # CRITICAL: Swap active and bench Pokemon in correct order
            # 1. Remove target from bench first (frees up a bench slot)
            new_active = player.board.remove_from_bench(action.target_id)

            # 2. Clear active spot
            player.board.active_spot = None

            # 3. Move old active to bench (now there's room)
            success = player.board.add_to_bench(active)
            if not success:
                # This should never happen since we just freed a bench slot
                raise ValueError(f"Failed to move retreating Pokemon to bench (bench full)")

            # 4. Set new active
            player.board.active_spot = new_active

            player.retreated_this_turn = True

            # 4 Pillars: Check for "on_retreat" triggers
            # Example: Cards that trigger when switching (e.g., some Stadium effects)
            self._check_triggers(state, "on_retreat", {
                "retreated_pokemon": active,
                "new_active": new_active,
                "player_id": action.player_id,
                "retreat_cost_paid": retreat_cost
            })

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

            # Execute attack effect (NEW: Nested Dictionary Format)
            attack_name = action.attack_name if hasattr(action, 'attack_name') else action.metadata.get('attack_name')

            if attack_name:
                attack_logic = logic_registry.get_card_logic(attacker.card_id, attack_name)

                if attack_logic:
                    # NEW FORMAT: Nested dictionary with 'effect' function
                    if isinstance(attack_logic, dict) and 'effect' in attack_logic:
                        effect_func = attack_logic['effect']
                        try:
                            # Call effect function with (state, card, action)
                            state = effect_func(state, attacker, action)
                        except Exception as e:
                            print(f"[ERROR] Attack effect failed for {attack_name}: {e}")
                            import traceback
                            traceback.print_exc()
                    # LEGACY FORMAT: Direct function that returns damage
                    elif callable(attack_logic):
                        try:
                            result = attack_logic(state, attacker, defender)
                            if isinstance(result, int):
                                base_damage = result
                            elif isinstance(result, dict) and 'damage' in result:
                                base_damage = result['damage']
                            # Apply legacy damage
                            defender.damage_counters += base_damage // 10
                        except Exception as e:
                            print(f"[WARNING] Legacy attack logic failed for {attack_name}: {e}")
                    else:
                        print(f"[WARNING] Invalid attack logic format for {attacker.card_id} - {attack_name}")
                else:
                    print(f"[WARNING] No attack logic found for {attacker.card_id} - {attack_name}")

            # Category 2 Fix: Get max HP from card definition (not hardcoded 120)
            from cards.factory import get_max_hp
            max_hp = get_max_hp(defender)
            if defender.is_knocked_out(max_hp):
                # Handle KO (Constitution Section 2, Phase 3)
                # Architecture Fix: Pass attacker as killer for prize calculation (Briar, Iron Hands ex, etc.)
                state = self._handle_knockout(state, defender, player, killer=attacker)

        # Check if attack pushed steps onto resolution stack (e.g., Call for Family search)
        # If so, stay in MAIN phase to process the stack before advancing to CLEANUP
        if state.resolution_stack:
            # Stack-based attack effect - don't advance to CLEANUP yet
            # Set flag so _apply_confirm_selection knows to advance to CLEANUP when stack clears
            state.attack_resolution_pending = True
            return state

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

    # ========================================================================
    # 6b. INTERRUPT STACK ACTION HANDLERS
    # ========================================================================

    def _apply_search_select_count(self, state: GameState, action: Action) -> GameState:
        """
        Handle selecting how many cards to search (upfront count selection).

        This is used for abilities like Infernal Reign where the player chooses
        how many matching cards to attach (0, 1, 2, 3) in a single decision,
        rather than iteratively selecting cards one by one.

        The selected count determines how many cards are automatically selected
        from the deck and queued for attachment.
        """
        from actions import shuffle_deck

        if state.pending_interrupt is None:
            return state

        interrupt = state.pending_interrupt
        player = state.get_player(interrupt.player_id)

        # Get the selected count from the action
        selected_count = action.choice_index if action.choice_index is not None else 0

        # If count is 0, decline the ability (same as legacy confirm with 0 selected)
        if selected_count == 0:
            # Mark has_searched_deck since player viewed deck
            player.has_searched_deck = True
            # Shuffle deck
            state = shuffle_deck(state, interrupt.player_id)
            # Clear the interrupt
            state.pending_interrupt = None
            return state

        # Find matching cards in deck and select the first N
        matching_cards = []
        for deck_card in player.deck.cards:
            if self._card_matches_search_filter(deck_card, interrupt.search_filter):
                matching_cards.append(deck_card)

        # Select up to selected_count cards
        cards_to_select = matching_cards[:selected_count]

        # Store selected card IDs
        interrupt.selected_card_ids = [card.id for card in cards_to_select]

        # Move selected cards from deck to cards_to_attach list
        interrupt.cards_to_attach = interrupt.selected_card_ids.copy()

        # Remove selected cards from deck and store their definition IDs
        for card_id in interrupt.selected_card_ids:
            for i, deck_card in enumerate(player.deck.cards):
                if deck_card.id == card_id:
                    # Store the card definition ID before removing
                    interrupt.card_definition_map[card_id] = deck_card.card_id
                    player.deck.cards.pop(i)
                    break

        # Transition to ATTACH_ENERGY phase
        interrupt.phase = InterruptPhase.ATTACH_ENERGY
        interrupt.current_attach_index = 0

        # Mark has_searched_deck since player viewed deck
        player.has_searched_deck = True

        return state

    def _apply_search_select_card(self, state: GameState, action: Action) -> GameState:
        """
        Handle selecting a card during search phase of an interrupt.

        This adds the selected card to the interrupt's selected_card_ids list.
        The card remains in the deck until SEARCH_CONFIRM is executed.
        """
        if state.pending_interrupt is None:
            return state

        interrupt = state.pending_interrupt

        # Add the selected card to the list
        if action.card_id and action.card_id not in interrupt.selected_card_ids:
            interrupt.selected_card_ids.append(action.card_id)

        return state

    def _apply_search_confirm(self, state: GameState, action: Action) -> GameState:
        """
        Handle confirming the search selection.

        This transitions from SEARCH_SELECT phase to ATTACH_ENERGY phase,
        or completes the interrupt if no cards were selected.
        """
        from actions import shuffle_deck

        if state.pending_interrupt is None:
            return state

        interrupt = state.pending_interrupt
        player = state.get_player(interrupt.player_id)

        # If no cards selected, complete the interrupt (ability declined)
        if not interrupt.selected_card_ids:
            # Mark has_searched_deck since player viewed deck
            player.has_searched_deck = True
            # Shuffle deck
            state = shuffle_deck(state, interrupt.player_id)
            # Clear the interrupt
            state.pending_interrupt = None
            return state

        # Move selected cards from deck to cards_to_attach list
        # Cards are removed from deck and held in "limbo" for attachment
        interrupt.cards_to_attach = interrupt.selected_card_ids.copy()

        # Remove selected cards from deck and store their definition IDs
        for card_id in interrupt.selected_card_ids:
            for i, deck_card in enumerate(player.deck.cards):
                if deck_card.id == card_id:
                    # Store the card definition ID before removing
                    interrupt.card_definition_map[card_id] = deck_card.card_id
                    player.deck.cards.pop(i)
                    break

        # Transition to ATTACH_ENERGY phase
        interrupt.phase = InterruptPhase.ATTACH_ENERGY
        interrupt.current_attach_index = 0

        # Mark has_searched_deck since player viewed deck
        player.has_searched_deck = True

        return state

    def _apply_interrupt_attach_energy(self, state: GameState, action: Action) -> GameState:
        """
        Handle attaching an energy card during interrupt attach phase.

        This attaches the current card to the target Pokemon and advances
        to the next card, or completes the interrupt if all cards attached.
        """
        from actions import shuffle_deck

        if state.pending_interrupt is None:
            return state

        interrupt = state.pending_interrupt
        player = state.get_player(interrupt.player_id)

        # Find the target Pokemon
        target = self._find_pokemon_by_id(player, action.target_id)
        if not target:
            return state

        # The card to attach is the first in cards_to_attach
        if not interrupt.cards_to_attach:
            return state

        card_id = interrupt.cards_to_attach.pop(0)

        # Create a CardInstance for the energy (it was removed from deck in SEARCH_CONFIRM)
        # We need to find it by id in the selected cards
        from models import CardInstance

        # Find the card's card_id (definition ID) from original deck search
        # Since the card was removed from deck, we need to reconstruct it
        # The action.card_id should match the card we're attaching
        energy_card = CardInstance(
            id=card_id,
            card_id=self._get_card_definition_id_from_interrupt(state, card_id),
            owner_id=interrupt.player_id
        )

        # Attach energy to target
        target.attached_energy.append(energy_card)

        # Advance to next card or complete interrupt
        interrupt.current_attach_index += 1

        if not interrupt.cards_to_attach:
            # All cards attached, complete the interrupt
            state = shuffle_deck(state, interrupt.player_id)
            state.pending_interrupt = None
        # else: more cards to attach, stay in ATTACH_ENERGY phase

        return state

    def _get_card_definition_id_from_interrupt(self, state: GameState, instance_id: str) -> str:
        """
        Get the card definition ID for a card instance ID from interrupt context.

        During interrupt processing, cards are removed from deck but we need
        their definition IDs to create proper CardInstances.
        """
        # First check the interrupt's card_definition_map (populated when cards were removed from deck)
        if state.pending_interrupt and hasattr(state.pending_interrupt, 'card_definition_map'):
            if instance_id in state.pending_interrupt.card_definition_map:
                return state.pending_interrupt.card_definition_map[instance_id]

        # Fallback: Search through all zones for the card
        for player in state.players:
            for card in player.deck.cards:
                if card.id == instance_id:
                    return card.card_id
            for card in player.discard.cards:
                if card.id == instance_id:
                    return card.card_id
            for card in player.hand.cards:
                if card.id == instance_id:
                    return card.card_id

        # Final fallback - should not happen in normal gameplay
        # Log warning since this indicates a bug
        return "unknown-card"

    # ========================================================================
    # RESOLUTION STACK ACTION HANDLERS (New Sequential State Machine)
    # ========================================================================

    def _apply_select_card(self, state: GameState, action: Action) -> GameState:
        """
        Handle selecting a card during resolution stack processing.

        This adds the selected card to the current step's selected_card_ids.
        The actual effect is deferred until CONFIRM_SELECTION is executed.

        Works with: SelectFromZoneStep, SearchDeckStep, AttachToTargetStep
        """
        from models import StepType, SelectFromZoneStep, SearchDeckStep, AttachToTargetStep, ActionType, Action

        if not state.resolution_stack:
            return state

        step = state.resolution_stack[-1]
        card_id = action.card_id

        if not card_id:
            return state

        # Handle based on step type
        if step.step_type == StepType.SELECT_FROM_ZONE:
            # SelectFromZoneStep - add to selected_card_ids
            if isinstance(step, SelectFromZoneStep):
                if card_id not in step.selected_card_ids:
                    step.selected_card_ids.append(card_id)

                # Auto-confirm when exact_count is True and we've reached the required count
                # This eliminates unnecessary confirm steps
                if step.exact_count and len(step.selected_card_ids) >= step.count:
                    # Create a synthetic confirm action and execute it
                    confirm_action = Action(
                        action_type=ActionType.CONFIRM_SELECTION,
                        player_id=step.player_id,
                        metadata={"step_type": step.step_type.value}
                    )
                    state = self._apply_confirm_selection(state, confirm_action)

        elif step.step_type == StepType.SEARCH_DECK:
            # SearchDeckStep - add to selected_card_ids
            if isinstance(step, SearchDeckStep):
                if card_id not in step.selected_card_ids:
                    step.selected_card_ids.append(card_id)
                # Note: SearchDeckStep doesn't auto-confirm - searches are always optional
                # (min_count can be 0), so players must manually confirm when ready.

        elif step.step_type == StepType.ATTACH_TO_TARGET:
            # AttachToTargetStep - set the selected_target_id and auto-execute
            if isinstance(step, AttachToTargetStep):
                step.selected_target_id = action.target_id  # Target is the Pokemon

                # Auto-execute: AttachToTargetStep is a single-selection step
                # Execute immediately rather than requiring CONFIRM_SELECTION
                player = state.get_player(step.player_id)
                state = self._execute_attach_to_target(state, step, player)

                # Mark complete and pop
                step.is_complete = True
                state.resolution_stack.pop()

                # Handle callback if present
                if step.on_complete_callback:
                    state = self._handle_step_callback(state, step)

        elif step.step_type == StepType.EVOLVE_TARGET:
            # EvolveTargetStep is auto-complete, no selection needed
            pass

        return state

    def _apply_confirm_selection(self, state: GameState, action: Action) -> GameState:
        """
        Confirm the current step's selection and execute its effect.

        This is where the actual game state changes happen:
        - SelectFromZoneStep: Move cards (e.g., discard from hand)
        - SearchDeckStep: Move cards to destination, shuffle deck
        - AttachToTargetStep: Attach card to Pokemon
        - EvolveTargetStep: Evolve the Pokemon

        After execution, the step is popped and any callback is triggered.
        """
        from models import (
            StepType, SelectFromZoneStep, SearchDeckStep,
            AttachToTargetStep, EvolveTargetStep, ZoneType, SelectionPurpose
        )
        from actions import shuffle_deck

        if not state.resolution_stack:
            return state

        step = state.resolution_stack[-1]
        player = state.get_player(step.player_id)

        # Execute based on step type
        if step.step_type == StepType.SELECT_FROM_ZONE:
            state = self._execute_select_from_zone(state, step, player)

        elif step.step_type == StepType.SEARCH_DECK:
            state = self._execute_search_deck(state, step, player)

        elif step.step_type == StepType.ATTACH_TO_TARGET:
            state = self._execute_attach_to_target(state, step, player)

        elif step.step_type == StepType.EVOLVE_TARGET:
            state = self._execute_evolve_target(state, step, player)

        # Mark step as complete and pop from stack
        step.is_complete = True
        state.resolution_stack.pop()

        # Handle callback if present (chain to next step)
        if step.on_complete_callback:
            state = self._handle_step_callback(state, step)

        # If stack is now empty and this was attack-initiated, advance to CLEANUP
        if not state.resolution_stack and state.attack_resolution_pending:
            state.attack_resolution_pending = False
            state.current_phase = GamePhase.CLEANUP

        return state

    def _apply_cancel_action(self, state: GameState, action: Action) -> GameState:
        """
        Cancel the current resolution and clear the stack.

        Used when player decides not to proceed with a multi-step action.
        Some cards may allow cancellation (costs not yet paid), others may not.
        """
        # For now, simply clear the resolution stack
        # In the future, we may want to validate whether cancellation is allowed
        state.clear_resolution_stack()

        # If canceling an attack-initiated stack, advance to CLEANUP
        if state.attack_resolution_pending:
            state.attack_resolution_pending = False
            state.current_phase = GamePhase.CLEANUP

        return state

    def _execute_select_from_zone(self, state: GameState, step, player) -> GameState:
        """
        Execute a SelectFromZoneStep - move selected cards based on purpose.

        Purpose determines what happens to selected cards:
        - DISCARD_COST: Move from hand to discard pile
        - EVOLUTION_BASE: Store in context for next step
        - EVOLUTION_STAGE: Store in context for next step
        """
        from models import ZoneType, SelectionPurpose, SelectFromZoneStep

        if not isinstance(step, SelectFromZoneStep):
            return state

        # Handle based on purpose
        if step.purpose == SelectionPurpose.DISCARD_COST:
            # Move selected cards from hand to discard
            for card_id in step.selected_card_ids:
                card = player.hand.remove_card(card_id)
                if card:
                    player.discard.add_card(card)

        elif step.purpose == SelectionPurpose.EVOLUTION_BASE:
            # Store the selected Pokemon ID in context for evolution step
            if step.selected_card_ids:
                step.context["evolution_base_id"] = step.selected_card_ids[0]

        elif step.purpose == SelectionPurpose.EVOLUTION_STAGE:
            # Store the selected evolution card ID in context
            if step.selected_card_ids:
                step.context["evolution_card_id"] = step.selected_card_ids[0]

        elif step.purpose == SelectionPurpose.BENCH_TARGET:
            # Store the selected bench Pokemon ID
            if step.selected_card_ids:
                step.context["bench_target_id"] = step.selected_card_ids[0]

        return state

    def _execute_search_deck(self, state: GameState, step, player) -> GameState:
        """
        Execute a SearchDeckStep - move selected cards to destination.

        Destination determines where cards go:
        - HAND: Move to hand
        - BENCH: Put Basic Pokemon onto bench
        - DISCARD: Move to discard pile

        Knowledge Layer:
        If a selected card is not in the deck (it's prized), the search for
        that card fails silently. The player still gains knowledge that they've
        searched the deck (has_searched_deck = True).
        """
        from models import ZoneType, SearchDeckStep
        from actions import shuffle_deck

        if not isinstance(step, SearchDeckStep):
            return state

        # Remove selected cards from deck
        # Cards that are prized won't be found - search fails for those
        selected_cards = []
        for card_id in step.selected_card_ids:
            for i, deck_card in enumerate(player.deck.cards):
                if deck_card.id == card_id:
                    selected_cards.append(player.deck.cards.pop(i))
                    break
            # If card not found, it's prized - search fails silently for that card

        # Move found cards to destination
        if step.destination == ZoneType.HAND:
            for card in selected_cards:
                player.hand.add_card(card)

        elif step.destination == ZoneType.BENCH:
            for card in selected_cards:
                card.turns_in_play = 0
                player.board.add_to_bench(card)

        elif step.destination == ZoneType.DISCARD:
            for card in selected_cards:
                player.discard.add_card(card)

        # Shuffle deck if required
        if step.shuffle_after:
            state = shuffle_deck(state, step.player_id)

        # Mark that player has searched deck - they now have perfect knowledge
        # This happens whether or not they found their cards
        player.has_searched_deck = True

        return state

    def _execute_attach_to_target(self, state: GameState, step, player) -> GameState:
        """
        Execute an AttachToTargetStep - attach card to target Pokemon.

        Handles two cases:
        1. Card from hand (Attach Energy action): Remove from hand and attach
        2. Card from deck/limbo (Infernal Reign): Create CardInstance and attach
        """
        from models import AttachToTargetStep, CardInstance

        if not isinstance(step, AttachToTargetStep):
            return state

        if not step.selected_target_id:
            return state

        # Find the target Pokemon
        target = self._find_pokemon_by_id(player, step.selected_target_id)
        if not target:
            return state

        card_id = step.card_to_attach_id

        # Check if the card is in hand (Attach Energy flow)
        energy_card = next((c for c in player.hand.cards if c.id == card_id), None)
        if energy_card:
            # Remove from hand and attach
            energy_card = player.hand.remove_card(card_id)
            if energy_card:
                target.attached_energy.append(energy_card)
                player.energy_attached_this_turn = True

                # Trigger "on_attach_energy" hooks
                self._check_triggers(state, "on_attach_energy", {
                    "energy_card": energy_card,
                    "target_pokemon": target,
                    "player_id": step.player_id,
                    "source": "hand"
                })
        else:
            # Card from deck/limbo (Infernal Reign or similar)
            # Create a CardInstance for it
            card_def_id = self._get_card_definition_id_for_attach(state, card_id, player)

            energy_card = CardInstance(
                id=card_id,
                card_id=card_def_id,
                owner_id=step.player_id
            )

            target.attached_energy.append(energy_card)

        return state

    def _execute_evolve_target(self, state: GameState, step, player) -> GameState:
        """
        Execute an EvolveTargetStep - evolve the base Pokemon.
        """
        from models import EvolveTargetStep
        from actions import evolve_pokemon

        if not isinstance(step, EvolveTargetStep):
            return state

        # Use the existing evolve_pokemon action
        # Pass skip_stage=True for Rare Candy evolutions
        state = evolve_pokemon(
            state,
            player.player_id,
            step.base_pokemon_id,
            step.evolution_card_id,
            skip_stage=step.skip_stage
        )

        return state

    def _get_card_definition_id_for_attach(self, state: GameState, instance_id: str, player) -> str:
        """
        Get the card definition ID for attaching a card.

        This searches the step context and game zones.
        """
        # First check if it's in the context of any pending steps
        for step in state.resolution_stack:
            if hasattr(step, 'context') and 'card_definitions' in step.context:
                if instance_id in step.context['card_definitions']:
                    return step.context['card_definitions'][instance_id]

        # Search zones
        for p in state.players:
            for card in p.deck.cards:
                if card.id == instance_id:
                    return card.card_id
            for card in p.discard.cards:
                if card.id == instance_id:
                    return card.card_id
            for card in p.hand.cards:
                if card.id == instance_id:
                    return card.card_id

        # Fallback
        return "basic-fire-energy"

    def _handle_step_callback(self, state: GameState, completed_step) -> GameState:
        """
        Handle the callback after a step completes.

        Callbacks allow chaining steps, e.g.:
        - Ultra Ball: After DISCARD_COST, push SEARCH_DECK step
        - Rare Candy: After selecting base, push select evolution step
        """
        from models import (
            SelectFromZoneStep, SearchDeckStep, AttachToTargetStep,
            ZoneType, SelectionPurpose
        )

        callback = completed_step.on_complete_callback

        if callback == "ultra_ball_search":
            # Push a search step for Ultra Ball
            search_step = SearchDeckStep(
                source_card_id=completed_step.source_card_id,
                source_card_name=completed_step.source_card_name,
                player_id=completed_step.player_id,
                purpose=SelectionPurpose.SEARCH_TARGET,
                count=1,
                min_count=0,
                destination=ZoneType.HAND,
                filter_criteria={"supertype": "Pokemon"},
                shuffle_after=True
            )
            state.push_step(search_step)

        elif callback == "rare_candy_select_evolution":
            # Push a step to select the Stage 2 evolution from hand
            base_id = completed_step.context.get("evolution_base_id")
            if base_id:
                # Create step to select Stage 2 from hand
                # The filter will ensure only Stage 2s that can evolve from the chosen Basic are shown
                select_stage_2_step = SelectFromZoneStep(
                    source_card_id=completed_step.source_card_id,
                    source_card_name=completed_step.source_card_name,
                    player_id=completed_step.player_id,
                    purpose=SelectionPurpose.EVOLUTION_STAGE,
                    zone=ZoneType.HAND,
                    count=1,
                    exact_count=True,
                    filter_criteria={
                        'supertype': 'Pokemon',
                        'subtype': 'Stage 2',
                        'rare_candy_evolution_for': base_id  # Custom filter: Stage 2s that can evolve from this Basic
                    },
                    context={'evolution_base_id': base_id},  # Pass forward the base Pokemon ID
                    on_complete_callback="rare_candy_evolve"
                )
                state.push_step(select_stage_2_step)

        elif callback == "rare_candy_evolve":
            # Execute the evolution directly (no need for another step)
            from actions import evolve_pokemon
            base_id = completed_step.context.get("evolution_base_id")
            evolution_id = completed_step.context.get("evolution_card_id")
            if base_id and evolution_id:
                state = evolve_pokemon(
                    state,
                    completed_step.player_id,
                    base_id,
                    evolution_id,
                    skip_stage=True  # Rare Candy allows skipping Stage 1
                )

        elif callback == "attach_energy_select_target":
            # Push an AttachToTargetStep after energy was selected
            # The selected energy ID is stored in the completed step's context
            energy_id = None
            if hasattr(completed_step, 'selected_card_ids') and completed_step.selected_card_ids:
                energy_id = completed_step.selected_card_ids[0]

            if energy_id:
                player = state.get_player(completed_step.player_id)

                # Get list of valid target Pokemon IDs
                valid_targets = [p.id for p in player.board.get_all_pokemon()]

                # Get energy name for display
                from cards.registry import create_card
                energy_card = next((c for c in player.hand.cards if c.id == energy_id), None)
                energy_name = "Energy"
                if energy_card:
                    energy_def = create_card(energy_card.card_id)
                    if energy_def and hasattr(energy_def, 'name'):
                        energy_name = energy_def.name

                attach_step = AttachToTargetStep(
                    source_card_id="attach_energy",
                    source_card_name="Attach Energy",
                    player_id=completed_step.player_id,
                    purpose=SelectionPurpose.ATTACH_TARGET,
                    card_to_attach_id=energy_id,
                    card_to_attach_name=energy_name,
                    valid_target_ids=valid_targets
                )
                state.push_step(attach_step)

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

        4 Pillars Architecture: Triggers on_turn_end and on_turn_start hooks
        """
        # Step 1: Handle CLEANUP phase
        if state.current_phase == GamePhase.CLEANUP:
            # 4 Pillars: Trigger "on_turn_end" for the player whose turn is ending
            ending_player = state.get_active_player()
            self._check_triggers(state, "on_turn_end", {
                "player_id": ending_player.player_id,
                "turn_count": state.turn_count
            })

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
                pokemon.evolved_this_turn = False  # Reset evolution flag for next turn
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

            # 4 Pillars: Trigger "on_turn_start" for the player whose turn is starting
            starting_player = state.get_active_player()
            self._check_triggers(state, "on_turn_start", {
                "player_id": starting_player.player_id,
                "turn_count": state.turn_count
            })

        return state

    def _resolve_effect_expiration(self, state: GameState) -> GameState:
        """
        Remove expired effects from active_effects list and per-Pokemon attack_effects.

        Called during cleanup phase to remove effects that have expired.

        Args:
            state: Current game state

        Returns:
            Modified game state with expired effects removed
        """
        current_turn = state.turn_count
        current_player = state.active_player_index
        current_phase = state.current_phase.value

        # Filter out expired effects from global active_effects
        active_effects = []
        for effect in state.active_effects:
            if not effect.is_expired(current_turn, current_player, current_phase):
                active_effects.append(effect)

        state.active_effects = active_effects

        # Filter out expired attack_effects on individual Pokemon
        # Effects with expires_at_end_of_turn=True and expires_player_id matching
        # the current player (whose turn is ending) should be removed
        ending_player_id = state.active_player_index
        for player in state.players:
            for pokemon in player.board.get_all_pokemon():
                if pokemon.attack_effects:
                    remaining_effects = []
                    for effect in pokemon.attack_effects:
                        if isinstance(effect, dict):
                            # Check if effect should expire
                            if effect.get('expires_at_end_of_turn') and effect.get('expires_player_id') == ending_player_id:
                                # This effect expires now - don't keep it
                                continue
                        remaining_effects.append(effect)
                    pokemon.attack_effects = remaining_effects

        return state

    def check_global_permission(
        self,
        state: GameState,
        action_type: str,
        context_or_player: Optional[Union[Dict, int]] = None
    ) -> bool:
        """
        Check if an action is allowed given current active effects.

        This is a permission hook that checks active effects before allowing actions.
        Supports two call patterns:
        1. check_global_permission(state, action_type, player_id)
        2. check_global_permission(state, action_type, {"card_id": ..., "player_id": ...})

        Args:
            state: Current game state
            action_type: Type of action being attempted (e.g., "attack", "retreat", "bench_damage", "ability", "play_item", "play_supporter")
            context_or_player: Either an int (player_id) or dict with context (card_id, player_id)

        Returns:
            True if action is allowed, False if blocked by an effect

        Examples:
            - Manaphy Wave Veil: Blocks "bench_damage"
            - Iron Leaves ex: Blocks "attack" for specific card
            - Path to the Peak: Blocks "ability" for VSTAR Pokémon
            - Klefki: Blocks "ability" for all Pokémon (from Active Spot)
            - Item Lock: Blocks "play_item"
        """
        # Normalize input to dict format
        if isinstance(context_or_player, int):
            context = {"player_id": context_or_player}
        elif context_or_player is None:
            context = {}
        else:
            context = context_or_player

        acting_player_id = context.get("player_id")

        # SPECIAL CHECK: Klefki-style passive ability locks (from Active Spot)
        if action_type == "ability":
            acting_card_id = context.get("card_id")

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

        # Check all active effects for action blocks
        if hasattr(state, 'active_effects') and state.active_effects:
            for effect in state.active_effects:
                # Check dict-style effects (e.g., Item Lock)
                if isinstance(effect, dict) and effect.get('type') == 'ACTION_BLOCK':
                    blocked_action = effect.get('blocked_action')
                    affected_player = effect.get('affected_player')

                    if blocked_action == action_type:
                        # Check if it affects this player
                        if affected_player == 'all' or affected_player == acting_player_id:
                            return False
                        if affected_player == 'opponent':
                            effect_owner = effect.get('owner_id')
                            if effect_owner is not None and effect_owner != acting_player_id:
                                return False

                # Check Effect object-style effects (e.g., bench_damage, attack blocks)
                if hasattr(effect, 'params'):
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
    # 8. EVENT TRIGGERS (4 Pillars: Hooks)
    # ========================================================================

    def _check_triggers(
        self,
        state: GameState,
        event_type: str,
        context: dict
    ) -> List[Action]:
        """
        Scan the board for cards with hooks that respond to the given event.

        This is part of the 4 Pillars architecture - Hooks are event-triggered
        functions that fire when specific game events occur.

        Supported event types:
        - "on_play_pokemon": When a Basic Pokémon is played from hand to bench
        - "on_evolve": When a Pokémon evolves
        - "on_knockout": When a Pokémon is knocked out
        - "on_attach_energy": When energy is attached to a Pokémon
        - "on_retreat": When a Pokémon retreats
        - "on_turn_start": At the start of a turn
        - "on_turn_end": At the end of a turn

        Args:
            state: Current game state
            event_type: Type of event that occurred (e.g., "on_play_pokemon")
            context: Event-specific context data (e.g., {"card": played_card, "player_id": 0})

        Returns:
            List of triggered Actions that need to be resolved.
            (For now, just returns the list - full Interrupt Stack not yet implemented)

        Example:
            >>> # Flamigo's Insta-Flock triggers when played from hand
            >>> triggered = self._check_triggers(state, "on_play_pokemon", {
            >>>     "card": flamigo_card,
            >>>     "player_id": 0,
            >>>     "source": "hand"
            >>> })
        """
        from cards.logic_registry import get_card_hooks

        triggered_actions = []

        # Scan both players' boards for cards with matching hooks
        for player in state.players:
            # Check active Pokémon
            if player.board.active_spot:
                hook = get_card_hooks(player.board.active_spot.card_id, event_type)
                if hook:
                    # Add context about which card triggered
                    hook_context = {
                        **context,
                        "trigger_card": player.board.active_spot,
                        "trigger_player_id": player.player_id
                    }
                    result = hook(state, player.board.active_spot, hook_context)
                    if isinstance(result, list):
                        triggered_actions.extend(result)
                    elif isinstance(result, Action):
                        triggered_actions.append(result)

            # Check bench Pokémon
            for bench_pokemon in player.board.bench:
                if bench_pokemon:
                    hook = get_card_hooks(bench_pokemon.card_id, event_type)
                    if hook:
                        hook_context = {
                            **context,
                            "trigger_card": bench_pokemon,
                            "trigger_player_id": player.player_id
                        }
                        result = hook(state, bench_pokemon, hook_context)
                        if isinstance(result, list):
                            triggered_actions.extend(result)
                        elif isinstance(result, Action):
                            triggered_actions.append(result)

        return triggered_actions

    # ========================================================================
    # 9. WIN CONDITION CHECKS
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

        # Move to discard (with all attached cards AND previous evolution stages)
        # First, discard all previous evolution stages (the Pokemon Stack)
        # Use previous_stages (actual CardInstance objects) to preserve card identity
        for prev_stage in knocked_out.previous_stages:
            owner.discard.add_card(prev_stage)
            # Also discard any energy/tools attached to previous stages
            for energy in prev_stage.attached_energy:
                owner.discard.add_card(energy)
            for tool in prev_stage.attached_tools:
                owner.discard.add_card(tool)

        # Then discard the top evolution (the current knocked_out card)
        owner.discard.add_card(knocked_out)

        # Finally, discard all attached cards on the top evolution
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

        # Set metadata flag for history tracking (Fezandipiti ex, Retaliate attacks, etc.)
        state.turn_metadata['pokemon_knocked_out'] = True
        # Track which player's Pokemon were knocked out (for "if any of YOUR Pokemon were KO'd" effects)
        # Using list instead of set for Pydantic serialization compatibility
        if 'knocked_out_player_ids' not in state.turn_metadata:
            state.turn_metadata['knocked_out_player_ids'] = []
        if knocked_out.owner_id not in state.turn_metadata['knocked_out_player_ids']:
            state.turn_metadata['knocked_out_player_ids'].append(knocked_out.owner_id)

        # 4 Pillars: Check for "on_knockout" triggers
        # Example: Retaliate attack bonus, Avenge attack bonus, knockout-triggered abilities
        triggered_actions = self._check_triggers(state, "on_knockout", {
            "knocked_out": knocked_out,
            "knocked_out_owner_id": knocked_out.owner_id,
            "killer": killer,
            "killer_owner_id": killer.owner_id if killer else None,
            "winner_player_id": winner.player_id
        })

        # TODO: Add triggered actions to interrupt stack when implemented
        # For now, store triggered actions in turn_metadata for cards that read knockout history
        if triggered_actions:
            if 'knockout_triggers' not in state.turn_metadata:
                state.turn_metadata['knockout_triggers'] = []
            state.turn_metadata['knockout_triggers'].extend(triggered_actions)

        return state

    def return_pokemon_to_hand(self, state: GameState, pokemon: CardInstance, owner: PlayerState) -> GameState:
        """
        Return a Pokémon (and its entire evolution stack) to the owner's hand.

        Used by: Scoop Up, Super Scoop Up, Acerola, etc.

        This moves:
        - All previous evolution stages (from evolution_chain)
        - The top evolution (the pokemon itself)
        - Does NOT move attached energy/tools (they go to discard)

        Args:
            state: Current game state
            pokemon: Pokémon to return to hand
            owner: Owner of the Pokémon

        Returns:
            Modified GameState
        """
        from cards.factory import create_card_instance

        # Discard all attached energy and tools
        for energy in pokemon.attached_energy:
            owner.discard.add_card(energy)
        for tool in pokemon.attached_tools:
            owner.discard.add_card(tool)

        # Clear attachments from pokemon
        pokemon.attached_energy = []
        pokemon.attached_tools = []

        # Return all previous evolution stages to hand
        for prev_card_id in pokemon.evolution_chain:
            prev_card = create_card_instance(prev_card_id, owner_id=pokemon.owner_id)
            owner.hand.add_card(prev_card)

        # Return the top evolution to hand
        owner.hand.add_card(pokemon)

        # Remove from board
        if owner.board.active_spot and owner.board.active_spot.id == pokemon.id:
            owner.board.active_spot = None
        else:
            owner.board.remove_from_bench(pokemon.id)

        return state

    def devolve_pokemon(self, state: GameState, pokemon: CardInstance, owner: PlayerState) -> GameState:
        """
        Devolve a Pokémon by one stage (remove top evolution, reveal previous stage).

        Used by: Devolution Spray, Mew ex (Genome Hacking devolution effect), etc.

        This:
        - Pops the last card from evolution_chain
        - Changes pokemon.card_id to that previous stage
        - Returns the current top evolution to owner's hand
        - Keeps damage counters, energy, and tools attached

        Args:
            state: Current game state
            pokemon: Pokémon to devolve
            owner: Owner of the Pokémon

        Returns:
            Modified GameState

        Raises:
            ValueError: If pokemon has no evolution_chain (cannot devolve Basic)
        """
        from cards.factory import create_card_instance

        # Check if Pokemon can be devolved
        if not pokemon.evolution_chain or len(pokemon.evolution_chain) == 0:
            raise ValueError(f"Cannot devolve Basic Pokémon (no evolution_chain)")

        # Get the previous stage
        prev_card_id = pokemon.evolution_chain.pop()  # Remove last item from chain

        # Create the current top evolution card to return to hand
        # (We need to preserve it as a separate card instance)
        devolved_card = create_card_instance(pokemon.card_id, owner_id=pokemon.owner_id)
        owner.hand.add_card(devolved_card)

        # Update the pokemon's card_id to the previous stage
        pokemon.card_id = prev_card_id

        # Keep all other properties (damage, energy, tools, status)
        # They stay attached to the Pokemon

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
        Calculate the dynamic retreat cost for a Pokémon, accounting for Tools, Effects, and Abilities.

        4 Pillars Architecture - Retreat Cost Calculation Order:
        1. Start with base retreat cost from card definition
        2. Apply active effects (Tools, legacy Stadium effects via effect system)
        3. Apply LOCAL modifiers (card's own abilities, e.g., Charmander's Agile)
        4. Apply GLOBAL modifiers (board-wide effects like Beach Court Stadium)

        Args:
            state: Current game state
            pokemon: Pokémon to calculate retreat cost for

        Returns:
            Final retreat cost (minimum 0)
        """
        from cards.registry import create_card
        from cards.logic_registry import get_card_modifier, scan_global_modifiers

        # Step 1: Get base retreat cost from card definition
        card_def = create_card(pokemon.card_id)
        if not card_def:
            return 0

        base_cost = card_def.base_retreat_cost if hasattr(card_def, 'base_retreat_cost') else 0
        current_cost = base_cost

        # Step 2: Apply retreat cost modifiers from active effects (Tools, legacy effects)
        modifier = 0
        for effect in state.active_effects:
            # Check if effect applies to this Pokémon
            if effect.target_card_id and effect.target_card_id != pokemon.id:
                continue

            # Apply retreat cost modifier (e.g., Float Stone: -2, Air Balloon: -1)
            if "retreat_cost_modifier" in effect.params:
                modifier += effect.params["retreat_cost_modifier"]

        current_cost = current_cost + modifier

        # Step 3: Apply LOCAL modifiers (4 Pillars: card's own abilities)
        # Example: Charmander's "Agile" - retreat cost = 0 if no Energy attached
        card_modifier = get_card_modifier(pokemon.card_id, "retreat_cost")
        if card_modifier:
            # Modifier function signature: fn(state, card, current_cost) -> new_cost
            current_cost = card_modifier(state, pokemon, current_cost)

        # Step 4: Apply GLOBAL modifiers (4 Pillars: board-wide effects)
        # Example: Beach Court Stadium - all Basic Pokémon retreat cost -1
        # Scans Stadium, active Pokémon, and benched Pokémon for global effects
        global_modifiers = scan_global_modifiers(state, "global_retreat_cost")
        for source_card, modifier_fn in global_modifiers:
            # Global modifier signature: fn(state, source_card, target_card, current_cost) -> new_cost
            current_cost = modifier_fn(state, source_card, pokemon, current_cost)

        # Final cost (minimum 0)
        final_cost = max(0, current_cost)
        return final_cost

    def get_max_tool_capacity(self, pokemon: CardInstance) -> int:
        """
        Get the maximum number of Tools this Pokemon can have attached.

        Standard rule: 1 Tool per Pokemon.
        Future-proofing: Some abilities may allow 2+ Tools (e.g., "Tool Box" ability).

        Args:
            pokemon: Pokemon to check

        Returns:
            Maximum number of Tools allowed (default: 1)
        """
        # Standard rule: Max 1 tool
        # TODO: Check for abilities that increase tool capacity (e.g., "Tool Box")
        return 1

    def _get_card_subtypes(self, card: CardInstance) -> Set[Subtype]:
        """Get subtypes for a card from the card registry."""
        from cards.factory import get_card_definition

        card_def = get_card_definition(card)
        if card_def:
            return set(card_def.subtypes)
        return set()

    def _is_basic_pokemon(self, card: CardInstance) -> bool:
        """
        Check if a card is a Basic Pokemon (not Basic Energy).

        Args:
            card: CardInstance to check

        Returns:
            True if card is a Basic Pokemon, False otherwise
        """
        from cards.factory import get_card_definition
        from cards.base import PokemonCard

        card_def = get_card_definition(card)
        if card_def and isinstance(card_def, PokemonCard):
            return Subtype.BASIC in card_def.subtypes
        return False

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
                        if len(energy_type) == 1:
                            # Basic energy (single type in a list)
                            # Extract the EnergyType and get its string value
                            single_type = energy_type[0]
                            type_key = single_type.value if hasattr(single_type, 'value') else str(single_type)
                            energy_totals[type_key] = energy_totals.get(type_key, 0) + 1
                        else:
                            # Multi-type energy (e.g., Rainbow Energy)
                            # For now, count as Colorless
                            energy_totals['C'] = energy_totals.get('C', 0) + 1
                    else:
                        # Single type energy (not in a list)
                        type_key = energy_type.value if hasattr(energy_type, 'value') else str(energy_type)
                        energy_totals[type_key] = energy_totals.get(type_key, 0) + 1

        return energy_totals

    def _can_pay_energy_cost(self, provided_energy: Dict[str, int], required_energy: List, total_cost: int) -> bool:
        """
        Check if the provided energy can pay for the attack cost.

        Implements the Pokémon TCG energy payment rules:
        - Specific energy types (e.g., Water, Fire) can only be paid with that type or Colorless
        - Colorless energy requirements can be paid with any energy type
        - After paying specific requirements, any remaining Colorless can be paid with leftover energy

        Args:
            provided_energy: Dict mapping energy type to count (e.g., {'Water': 2, 'Fire': 1})
            required_energy: List of required energy types from attack.cost
            total_cost: Total number of energy required (after reductions)

        Returns:
            True if cost can be paid, False otherwise

        Example:
            >>> # Attack requires [Water, Water, Colorless]
            >>> provided = {'Water': 2, 'Fire': 1}
            >>> required = [EnergyType.WATER, EnergyType.WATER, EnergyType.COLORLESS]
            >>> _can_pay_energy_cost(provided, required, 3)  # True - 2 Water + 1 Fire for Colorless
        """
        from models import EnergyType

        # Make a copy to track remaining energy as we "spend" it
        remaining = provided_energy.copy()

        # First, pay for specific (non-Colorless) energy requirements
        for energy_type in required_energy:
            if energy_type == EnergyType.COLORLESS:
                continue  # Handle Colorless last

            # Convert EnergyType to string key used in dictionary
            type_key = energy_type.value if hasattr(energy_type, 'value') else str(energy_type)

            # Check if we have this specific type
            if remaining.get(type_key, 0) > 0:
                remaining[type_key] -= 1
            else:
                # Can't pay for this specific energy requirement
                return False

        # Count how many Colorless requirements we have
        colorless_needed = sum(1 for e in required_energy if e == EnergyType.COLORLESS)

        # Check if we have enough total remaining energy for Colorless
        total_remaining = sum(remaining.values())
        if total_remaining < colorless_needed:
            return False

        # Also verify total energy count meets the final cost (after reductions)
        total_provided = sum(provided_energy.values())
        if total_provided < total_cost:
            return False

        return True


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
            if Subtype.MEGA in victim_def.subtypes:
                base_prizes = 3  # MEGA Pokemon award 3 prizes
            elif Subtype.VMAX in victim_def.subtypes or Subtype.VSTAR in victim_def.subtypes:
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

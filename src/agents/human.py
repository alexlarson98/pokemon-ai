"""
Pokémon TCG Engine - Human Agent

Interactive console-based player for human users.
Displays legal actions and prompts for input.
"""

from typing import List, TYPE_CHECKING
from agents.base import PlayerAgent

if TYPE_CHECKING:
    from models import GameState, Action


class HumanAgent(PlayerAgent):
    """
    Human player agent with console interface.

    Displays numbered list of legal actions and accepts user input.
    Validates input and re-prompts on invalid choices.

    Example:
        >>> agent = HumanAgent(name="Alice")
        >>> action = agent.choose_action(state, legal_actions)

        === ALICE'S TURN ===
        Legal Actions:
          [0] PLAY_BASIC: Charmander (sv3-26)
          [1] ATTACH_ENERGY: Fire Energy -> Charmander
          [2] END_TURN

        Choose action [0-2]: 1
    """

    def choose_action(self, state: 'GameState', legal_actions: List['Action']) -> 'Action':
        """
        Prompt human player to choose an action.

        Args:
            state: Current game state
            legal_actions: List of legal actions

        Returns:
            Selected action

        Raises:
            ValueError: If no legal actions available
        """
        if not legal_actions:
            raise ValueError("No legal actions available")

        # Single action - auto-select
        if len(legal_actions) == 1:
            action = legal_actions[0]
            print(f"\n[Auto-selected] {self._format_action(action, state)}")
            print("(Only one legal move available - Auto-playing)")
            return action

        # Display header
        print(f"\n{'=' * 60}")
        print(f"{self.name.upper()}'S TURN (Player {self.player_id})")
        print(f"{'=' * 60}")

        # Display game state summary
        self._display_state_summary(state)

        # Display legal actions
        print(f"\nLegal Actions:")
        for i, action in enumerate(legal_actions):
            print(f"  [{i}] {self._format_action(action, state)}")

        # Prompt for input
        while True:
            try:
                choice = input(f"\nChoose action [0-{len(legal_actions) - 1}]: ").strip()

                # Handle 'q' to quit
                if choice.lower() in ['q', 'quit', 'exit']:
                    print("\nGame aborted by user.")
                    raise KeyboardInterrupt

                idx = int(choice)

                if 0 <= idx < len(legal_actions):
                    selected_action = legal_actions[idx]
                    print(f"\n[Selected] {self._format_action(selected_action, state)}")
                    return selected_action
                else:
                    print(f"Invalid choice. Enter a number between 0 and {len(legal_actions) - 1}.")

            except ValueError:
                print("Invalid input. Enter a number.")
            except (KeyboardInterrupt, EOFError):
                print("\n\nGame interrupted by user.")
                raise

    def _display_state_summary(self, state: 'GameState'):
        """Display current game state summary."""
        from models import GamePhase
        from cards.registry import create_card

        player = state.get_player(self.player_id)
        opponent = state.get_player(1 - self.player_id)

        print(f"\nPhase: {state.current_phase.value.upper()}")
        print(f"Turn: {state.turn_count}")
        print(f"Deck: {len(player.deck.cards)} cards | Prizes: {len(player.prizes.cards)} remaining ({player.prizes_taken} taken)")

        # Display Active Pokémon
        print(f"\n{'YOUR ACTIVE POKEMON':=^60}")
        if player.board.active_spot:
            active = player.board.active_spot
            card_def = create_card(active.card_id)
            card_name = card_def.name if card_def else active.card_id

            from cards.factory import get_max_hp
            max_hp = get_max_hp(active)
            current_hp = max_hp - (active.damage_counters * 10)

            print(f"  {card_name} ({active.card_id})")
            print(f"  HP: {current_hp}/{max_hp}")

            if active.attached_energy:
                energy_names = []
                for energy in active.attached_energy:
                    e_def = create_card(energy.card_id)
                    e_name = e_def.name if e_def else energy.card_id
                    energy_names.append(e_name)
                print(f"  Energy: {', '.join(energy_names)} ({len(active.attached_energy)} total)")
        else:
            print(f"  (none)")

        # Display Bench
        print(f"\n{'YOUR BENCH':=^60}")
        if player.board.get_bench_count() > 0:
            for i, pokemon in enumerate(player.board.bench):
                if pokemon is not None:
                    card_def = create_card(pokemon.card_id)
                    card_name = card_def.name if card_def else pokemon.card_id

                    from cards.factory import get_max_hp
                    max_hp = get_max_hp(pokemon)
                    current_hp = max_hp - (pokemon.damage_counters * 10)

                    energy_count = len(pokemon.attached_energy) if pokemon.attached_energy else 0
                    print(f"  [{i}] {card_name} - {current_hp}/{max_hp} HP - {energy_count} Energy")
        else:
            print(f"  (empty)")

        # Display Hand
        print(f"\n{'YOUR HAND ({} cards)'.format(len(player.hand.cards)):=^60}")
        if player.hand.cards:
            # Group cards by name
            from collections import Counter
            card_counts = Counter()
            for card in player.hand.cards:
                card_def = create_card(card.card_id)
                card_name = card_def.name if card_def else card.card_id
                card_counts[card_name] += 1

            for card_name, count in sorted(card_counts.items()):
                if count > 1:
                    print(f"  {count}x {card_name}")
                else:
                    print(f"  {card_name}")
        else:
            print(f"  (empty)")

        # Display Opponent's Active
        print(f"\n{'OPPONENT ACTIVE POKEMON':=^60}")
        if opponent.board.active_spot:
            opp_active = opponent.board.active_spot
            card_def = create_card(opp_active.card_id)
            card_name = card_def.name if card_def else opp_active.card_id

            from cards.factory import get_max_hp
            max_hp = get_max_hp(opp_active)
            current_hp = max_hp - (opp_active.damage_counters * 10)

            print(f"  {card_name} ({opp_active.card_id})")
            print(f"  HP: {current_hp}/{max_hp}")

            if opp_active.attached_energy:
                print(f"  Energy: {len(opp_active.attached_energy)}")
        else:
            print(f"  (none)")

        # Display Opponent's Bench
        opp_bench_count = opponent.board.get_bench_count()
        print(f"\n{'OPPONENT BENCH':=^60}")
        if opp_bench_count > 0:
            for i, pokemon in enumerate(opponent.board.bench):
                if pokemon is not None:
                    card_def = create_card(pokemon.card_id)
                    card_name = card_def.name if card_def else pokemon.card_id

                    from cards.factory import get_max_hp
                    max_hp = get_max_hp(pokemon)
                    current_hp = max_hp - (pokemon.damage_counters * 10)

                    energy_count = len(pokemon.attached_energy) if pokemon.attached_energy else 0
                    print(f"  [{i}] {card_name} - {current_hp}/{max_hp} HP, Energy: {energy_count}")
        else:
            print(f"  (empty)")

    def _format_action(self, action: 'Action', state: 'GameState') -> str:
        """Format action for display with card names."""
        from models import ActionType
        from cards.registry import create_card

        def get_card_name(instance_id):
            """Helper to get card name from instance ID by looking up in state."""
            if not instance_id:
                return "(unknown)"

            # Look up the card instance in the current player's hand, board, etc.
            player = state.get_player(self.player_id)

            # Search in hand
            for card in player.hand.cards:
                if card.id == instance_id:
                    card_def = create_card(card.card_id)
                    return card_def.name if card_def else card.card_id

            # Search in board
            for pokemon in player.board.get_all_pokemon():
                if pokemon.id == instance_id:
                    card_def = create_card(pokemon.card_id)
                    return card_def.name if card_def else pokemon.card_id

            # If not found, try to create card from the ID directly (fallback)
            card_def = create_card(instance_id)
            return card_def.name if card_def else instance_id

        action_type = action.action_type.value.upper()

        # Format based on action type
        if action.action_type == ActionType.PLACE_ACTIVE:
            card_name = get_card_name(action.card_id)
            return f"{action_type}: {card_name}"

        elif action.action_type == ActionType.PLACE_BENCH:
            card_name = get_card_name(action.card_id)
            return f"{action_type}: {card_name}"

        elif action.action_type == ActionType.PLAY_BASIC:
            card_name = get_card_name(action.card_id)
            return f"Play {card_name} to Bench"

        elif action.action_type == ActionType.ATTACH_ENERGY:
            energy_name = get_card_name(action.card_id)
            target_name = get_card_name(action.target_id)
            target_location = self._get_pokemon_location(state, action.target_id)
            return f"Attach {energy_name} to {target_name} ({target_location})"

        elif action.action_type == ActionType.EVOLVE:
            evo_name = get_card_name(action.card_id)
            target_name = get_card_name(action.target_id)
            target_location = self._get_pokemon_location(state, action.target_id)
            return f"Evolve {target_name} ({target_location}) into {evo_name}"

        elif action.action_type == ActionType.ATTACK:
            attack_name = action.attack_name if hasattr(action, 'attack_name') else action.metadata.get('attack_name', 'Attack')
            return f"ATTACK: {attack_name}"

        elif action.action_type == ActionType.RETREAT:
            # target_id is a card instance ID, need to look it up from state
            bench_idx = action.metadata.get("bench_index") if action.metadata else None
            if bench_idx is not None:
                return f"Retreat (switch to Bench position {bench_idx})"
            else:
                target_name = get_card_name(action.target_id)
                return f"Retreat (switch to {target_name})"

        elif action.action_type == ActionType.PLAY_ITEM:
            card_name = get_card_name(action.card_id)
            return f"Play Item: {card_name}"

        elif action.action_type == ActionType.PLAY_SUPPORTER:
            card_name = get_card_name(action.card_id)
            return f"Play Supporter: {card_name}"

        elif action.action_type == ActionType.PLAY_STADIUM:
            card_name = get_card_name(action.card_id)
            return f"Play Stadium: {card_name}"

        elif action.action_type == ActionType.END_TURN:
            if action.metadata.get("finish_setup"):
                return "Finish Setup (End Turn)"
            elif action.metadata.get("pass_turn"):
                return "Pass Turn (End Turn)"
            elif action.metadata.get("advance_to_attack"):
                return "Go to Attack Phase"
            else:
                return "End Turn"

        elif action.action_type == ActionType.PROMOTE_ACTIVE:
            card_name = get_card_name(action.card_id)
            return f"Promote {card_name} to Active"

        elif action.action_type == ActionType.MULLIGAN_DRAW:
            if action.metadata.get("draw"):
                return "Draw 1 card (Mulligan bonus)"
            else:
                return "Skip draw (Mulligan)"

        else:
            card_name = get_card_name(action.card_id) if action.card_id else "(no card)"
            return f"{action_type}: {card_name}"

    def _get_pokemon_location(self, state: 'GameState', pokemon_id: str) -> str:
        """
        Get the location of a Pokémon (Active, Bench 1, Bench 2, etc.).

        Args:
            state: Current game state
            pokemon_id: Card instance ID of the Pokémon

        Returns:
            Location string (e.g., "Active", "Bench 1", "Bench 2")
        """
        player = state.get_active_player()

        # Check if it's the active Pokémon
        if player.board.active_spot and player.board.active_spot.id == pokemon_id:
            return "Active"

        # Check bench
        for i, pokemon in enumerate(player.board.bench):
            if pokemon.id == pokemon_id:
                return f"Bench {i + 1}"

        return "Unknown"

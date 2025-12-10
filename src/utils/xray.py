"""
X-Ray Logging System - Linear State Trace

Provides complete visibility into all game zones (including hidden information)
for debugging and verifying game physics integrity.

Format: Continuous stream of Action -> Game State transitions.
"""

import os
from datetime import datetime
from typing import Optional

from models import GameState, Action


class XRayLogger:
    """
    X-Ray Logger - Complete game state visibility for debugging.

    Logs all game state including hidden information (opponent hands, decks, prizes).
    Useful for auditing card movements and verifying game rules enforcement.
    """

    def __init__(self):
        """Initialize X-Ray logger and create log file."""
        # Create xrays directory if it doesn't exist
        xray_dir = os.path.join("src", "utils", "xrays")
        os.makedirs(xray_dir, exist_ok=True)

        # Create timestamped log file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_path = os.path.join(xray_dir, f"xray_game_{timestamp}.log")

        # Initialize log file with header
        with open(self.log_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("X-RAY GAME LOG - LINEAR STATE TRACE\n")
            f.write(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")

        print(f"[X-Ray Logger] Logging to: {self.log_path}")

    def _fmt(self, card) -> str:
        """
        Format card as 'CardName (1234)' using last 8 characters of ID (or full ID if shorter).

        Args:
            card: CardInstance or None

        Returns:
            Formatted string like "Charmander (a1b2c3d4)" or "(Empty)"
        """
        if card is None:
            return "(Empty)"

        from cards.registry import create_card

        # Get card name
        card_def = create_card(card.card_id)
        card_name = card_def.name if card_def and hasattr(card_def, 'name') else card.card_id

        # Get last 8 characters of card instance ID (or full ID if shorter)
        short_id = card.id[-8:] if len(card.id) >= 8 else card.id

        return f"{card_name} ({short_id})"

    def log_action(self, turn_count: int, player_name: str, action: Action) -> None:
        """
        Log an action header.

        Args:
            turn_count: Current turn number
            player_name: Name of player taking action
            action: Action object
        """
        from models import ActionType

        # Format action description
        action_desc = self._format_action_description(action)

        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write("#" * 80 + "\n")
            f.write(f"[TURN {turn_count} | PLAYER: {player_name}] ACTION: {action_desc}\n")
            f.write("#" * 80 + "\n\n")

    def _format_action_description(self, action: Action) -> str:
        """Format action description with card names and short IDs."""
        from models import ActionType
        from cards.registry import create_card

        def get_card_display(card_id):
            """Get card name and short ID."""
            if not card_id:
                return "Unknown"
            # For card_id, we need to find the actual card instance to get its ID
            # For now, just use the card_id itself
            card_def = create_card(card_id)
            card_name = card_def.name if card_def and hasattr(card_def, 'name') else card_id
            short_id = card_id[-8:] if len(card_id) >= 8 else card_id
            return f"{card_name} ({short_id})"

        action_type = action.action_type

        if action_type == ActionType.ATTACH_ENERGY:
            energy = get_card_display(action.card_id)
            target = get_card_display(action.target_id)
            # Get location from metadata if available
            location = action.metadata.get("location", "")
            if location:
                return f"Attach {energy} to {target} ({location})"
            else:
                return f"Attach {energy} to {target}"

        elif action_type == ActionType.EVOLVE:
            evo = get_card_display(action.card_id)
            target = get_card_display(action.target_id)
            location = action.metadata.get("location", "")
            if location:
                return f"Evolve {target} ({location}) into {evo}"
            else:
                return f"Evolve {target} into {evo}"

        elif action_type == ActionType.ATTACK:
            attack_name = action.attack_name if hasattr(action, 'attack_name') else 'Attack'
            return f"ATTACK: {attack_name}"

        elif action_type == ActionType.RETREAT:
            target = get_card_display(action.target_id)
            return f"Retreat (switch to {target})"

        elif action_type == ActionType.PLAY_BASIC:
            card = get_card_display(action.card_id)
            return f"Play {card} to Bench"

        elif action_type == ActionType.PLAY_ITEM:
            card = get_card_display(action.card_id)
            return f"Play Item: {card}"

        elif action_type == ActionType.PLAY_SUPPORTER:
            card = get_card_display(action.card_id)
            return f"Play Supporter: {card}"

        elif action_type == ActionType.END_TURN:
            return "END TURN"

        else:
            return action_type.value

    def log_state(self, state: GameState) -> None:
        """
        Log complete game state snapshot (including hidden zones).

        Format: Single-line entries for each category.

        Args:
            state: Current game state
        """
        from cards.registry import create_card
        from cards.factory import get_max_hp

        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")

            # Always show Player 0 first, then Player 1 (stable ordering)
            p0 = state.players[0]
            p1 = state.players[1]

            # === PLAYER 0 ===
            f.write(f"[PLAYER 0]\n")

            # ACTIVE
            if p0.board.active_spot:
                active_line = self._format_pokemon_line(p0.board.active_spot, "ACTIVE")
                f.write(active_line + "\n")
            else:
                f.write("ACTIVE:  (Empty)\n")

            # BENCH
            for i, pokemon in enumerate(p0.board.bench):
                bench_line = self._format_pokemon_line(pokemon, f"BENCH {i+1}")
                f.write(bench_line + "\n")

            # HAND
            hand_cards = ", ".join([self._fmt(card) for card in p0.hand.cards])
            f.write(f"HAND ({len(p0.hand.cards)}): [{hand_cards}]\n")

            # PRIZES
            prize_cards = ", ".join([self._fmt(card) for card in p0.prizes.cards])
            f.write(f"PRIZES ({len(p0.prizes.cards)}): [{prize_cards}]\n")

            # DECK (ALL cards in order)
            deck_cards = ", ".join([self._fmt(card) for card in p0.deck.cards])
            f.write(f"DECK ({len(p0.deck.cards)}): [{deck_cards}]\n")

            # === PLAYER 1 ===
            f.write(f"\n[PLAYER 1]\n")

            # ACTIVE
            if p1.board.active_spot:
                active_line = self._format_pokemon_line(p1.board.active_spot, "ACTIVE")
                f.write(active_line + "\n")
            else:
                f.write("ACTIVE:  (Empty)\n")

            # BENCH
            for i, pokemon in enumerate(p1.board.bench):
                bench_line = self._format_pokemon_line(pokemon, f"BENCH {i+1}")
                f.write(bench_line + "\n")

            # HAND
            hand_cards = ", ".join([self._fmt(card) for card in p1.hand.cards])
            f.write(f"HAND ({len(p1.hand.cards)}): [{hand_cards}]\n")

            # PRIZES
            prize_cards = ", ".join([self._fmt(card) for card in p1.prizes.cards])
            f.write(f"PRIZES ({len(p1.prizes.cards)}): [{prize_cards}]\n")

            # DECK (ALL cards in order)
            deck_cards = ", ".join([self._fmt(card) for card in p1.deck.cards])
            f.write(f"DECK ({len(p1.deck.cards)}): [{deck_cards}]\n")

            # === GLOBAL ===
            f.write("\n[GLOBAL]\n")
            if state.stadium:
                stadium_display = self._fmt(state.stadium)
                f.write(f"Stadium: {stadium_display}\n")
            else:
                f.write("Stadium: (None)\n")

            f.write("=" * 80 + "\n\n")

    def _format_pokemon_line(self, pokemon, label: str) -> str:
        """
        Format a single-line Pokemon display.

        Format: "ACTIVE:  Charmander (..a1b2) | HP: 60/60 | Energy: [R] | Tools: []"
        """
        from cards.registry import create_card
        from cards.factory import get_max_hp

        if pokemon is None:
            return f"{label}: (Empty)"

        # Card name and ID
        card_display = self._fmt(pokemon)

        # HP
        max_hp = get_max_hp(pokemon)
        current_hp = max_hp - (pokemon.damage_counters * 10)
        hp_str = f"HP: {current_hp}/{max_hp}"

        # Energy (show actual card objects)
        if pokemon.attached_energy:
            energy_cards = [self._fmt(energy) for energy in pokemon.attached_energy]
            energy_str = f"Energy: [{', '.join(energy_cards)}]"
        else:
            energy_str = "Energy: []"

        # Tools
        if pokemon.attached_tools:
            tools_list = [self._fmt(tool) for tool in pokemon.attached_tools]
            tools_str = f"Tools: [{', '.join(tools_list)}]"
        else:
            tools_str = "Tools: []"

        # Combine
        return f"{label}:  {card_display} | {hp_str} | {energy_str} | {tools_str}"

    def log_game_end(self, winner: Optional[int], reason: str) -> None:
        """
        Log game end result.

        Args:
            winner: Winning player index (None if draw)
            reason: Reason for game end
        """
        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write("\n" + "=" * 80 + "\n")
            f.write("GAME END\n")
            f.write("=" * 80 + "\n")
            if winner is not None:
                f.write(f"Winner: Player {winner}\n")
            else:
                f.write(f"Result: Draw\n")
            f.write(f"Reason: {reason}\n")
            f.write(f"Ended: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n")

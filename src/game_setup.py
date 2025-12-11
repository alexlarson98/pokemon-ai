"""
Pokémon TCG Engine - Game Setup Manager

Converts deck strings into playable GameState.
Automates pre-game setup (draw, place active, set prizes).

Usage:
    from game_setup import build_game_state, setup_initial_board

    # Load decks from strings
    state = build_game_state(deck1_text, deck2_text)

    # Setup board (draw 7, place active, set prizes)
    state = setup_initial_board(state)
"""

from typing import List, Tuple
import random

from models import GameState, PlayerState, GamePhase, CardInstance
from cards.factory import create_card_instance


def parse_deck_string(deck_text: str) -> List[str]:
    """
    Parse a deck string into list of card IDs.

    Supports two formats:
    1. Internal format: "4 Charmander sv3-26"
    2. PTCGL export format: "4 Charmander PAF 7" (converted to "paf-7")

    Args:
        deck_text: Deck string

    Returns:
        List of card IDs (expanded by count)

    Example:
        >>> parse_deck_string("4 Charmander sv3-26\\n2 Fire Energy base1-98")
        ["sv3-26", "sv3-26", "sv3-26", "sv3-26", "base1-98", "base1-98"]
        >>> parse_deck_string("4 Charmander PAF 7\\n2 Fire Energy MEE 2")
        ["paf-7", "paf-7", "paf-7", "paf-7", "mee-2", "mee-2"]
    """
    import re

    card_ids = []
    lines = deck_text.strip().split('\n')

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        # Skip PTCGL export headers (e.g., "Pokémon: 23", "Trainer: 30")
        if ':' in line and not re.search(r'\d+\s+\w', line):
            continue

        # Try PTCGL format first: {count} {name...} {SETCODE} {number}
        # Example: "4 Dreepy TWM 128" -> "sv6-128" (using set code mapping)
        ptcgl_match = re.search(r'(\d+)\s+.*?\s+([A-Z]+)\s+(\d+)$', line)
        if ptcgl_match:
            from utils.deck_import import normalize_set_code

            count = int(ptcgl_match.group(1))
            ptcgl_setcode = ptcgl_match.group(2)
            number = ptcgl_match.group(3)

            # Convert PTCGL setcode to internal format
            internal_setcode = normalize_set_code(ptcgl_setcode)
            if internal_setcode:
                card_id = f"{internal_setcode}-{number}"
            else:
                # Fallback: use lowercase PTCGL code
                card_id = f"{ptcgl_setcode.lower()}-{number}"

            for _ in range(count):
                card_ids.append(card_id)
            continue

        # Try internal format: {count} {name...} {setcode-number}
        # Example: "4 Charmander sv3-26" -> "sv3-26"
        internal_match = re.search(r'(\d+)\s+.*?\s+([\w\-]+)$', line)
        if internal_match:
            count = int(internal_match.group(1))
            card_id = internal_match.group(2)

            for _ in range(count):
                card_ids.append(card_id)

    return card_ids


def build_game_state(deck_text_1: str, deck_text_2: str, random_seed: int = None) -> GameState:
    """
    Build a GameState from two deck strings.

    Args:
        deck_text_1: Deck string for Player 0 (format: "4 Charmander sv3-26\\n...")
        deck_text_2: Deck string for Player 1
        random_seed: Random seed for shuffling (optional)

    Returns:
        GameState with decks loaded, ready for setup

    Example:
        >>> deck1 = "4 Charmander sv3-26\\n60 Fire Energy base1-98"
        >>> deck2 = "4 Pikachu sv8-57\\n60 Lightning Energy base1-100"
        >>> state = build_game_state(deck1, deck2)
    """
    if random_seed is not None:
        random.seed(random_seed)

    # Parse deck strings
    deck1_card_ids = parse_deck_string(deck_text_1)
    deck2_card_ids = parse_deck_string(deck_text_2)

    # Validate deck sizes
    if len(deck1_card_ids) != 60:
        raise ValueError(f"Deck 1 must have 60 cards, got {len(deck1_card_ids)}")
    if len(deck2_card_ids) != 60:
        raise ValueError(f"Deck 2 must have 60 cards, got {len(deck2_card_ids)}")

    # Create card instances
    deck1_cards = [create_card_instance(card_id, owner_id=0) for card_id in deck1_card_ids]
    deck2_cards = [create_card_instance(card_id, owner_id=1) for card_id in deck2_card_ids]

    # Shuffle decks
    random.shuffle(deck1_cards)
    random.shuffle(deck2_cards)

    # Create players
    player0 = PlayerState(player_id=0, name="Player 0")
    player1 = PlayerState(player_id=1, name="Player 1")

    # Add cards to decks
    for card in deck1_cards:
        player0.deck.add_card(card)

    for card in deck2_cards:
        player1.deck.add_card(card)

    # Create game state
    state = GameState(
        players=[player0, player1],
        turn_count=1,
        active_player_index=0,
        current_phase=GamePhase.SETUP
    )

    return state


def setup_initial_board(state: GameState, auto_mulligan: bool = True) -> GameState:
    """
    Setup the initial board for both players.

    Constitution Setup Phase (Section 2, Phase 0):
    1. Draw 7 cards
    2. Check for Basic Pokémon (mulligan if needed)
    3. Place Active Pokémon
    4. Place Bench Pokémon (optional)
    5. Set aside 6 Prize cards

    Args:
        state: GameState with decks loaded
        auto_mulligan: If True, automatically handle mulligans

    Returns:
        GameState ready to start (Main Phase, Turn 1)

    Raises:
        ValueError: If deck has no Basic Pokémon after multiple mulligans
    """
    # Draw 7 cards for each player
    for player in state.players:
        _draw_opening_hand(player)

    # Handle mulligans
    if auto_mulligan:
        _handle_mulligans(state)

    # Place Active Pokémon (interactive or auto)
    _place_initial_pokemon(state)

    # Set aside Prize cards
    _set_prizes(state)

    # Player 0 draws 1 card to start turn 1
    # (Every player draws at the start of their turn, including turn 1)
    active_player = state.get_active_player()
    if not active_player.deck.is_empty():
        card = active_player.deck.cards.pop(0)
        active_player.hand.add_card(card)
        print(f"[Draw Phase] Player {active_player.player_id} draws 1 card to start turn 1 (Hand: {len(active_player.hand.cards)} cards, Deck: {len(active_player.deck.cards)} remaining)")

    # Advance to Main Phase
    state.current_phase = GamePhase.MAIN
    state.turn_count = 1

    return state


def _draw_opening_hand(player: PlayerState):
    """Draw 7 cards from deck to hand."""
    for _ in range(7):
        if not player.deck.is_empty():
            card = player.deck.cards.pop(0)
            player.hand.add_card(card)


def _handle_mulligans(state: GameState, max_mulligans: int = 5):
    """
    Handle mulligan phase.

    If a player has no Basic Pokémon, shuffle hand into deck and redraw.
    Opponent may draw 1 card per mulligan.

    Args:
        state: Current game state
        max_mulligans: Maximum mulligans before error

    Raises:
        ValueError: If no Basic Pokémon after max mulligans
    """
    from models import Subtype

    for player in state.players:
        mulligan_count = 0

        while mulligan_count < max_mulligans:
            # Check for Basic Pokémon in hand
            has_basic = any(
                Subtype.BASIC in _get_card_subtypes(card)
                for card in player.hand.cards
            )

            if has_basic:
                break  # Valid hand

            # Mulligan: Shuffle hand into deck
            print(f"\n[Mulligan] Player {player.player_id} has no Basic Pokémon. Reshuffling...")

            while not player.hand.is_empty():
                card = player.hand.cards.pop(0)
                player.deck.add_card(card)

            # Shuffle deck
            random.shuffle(player.deck.cards)

            # Redraw 7 cards
            _draw_opening_hand(player)

            mulligan_count += 1

            # Opponent may draw 1 card (auto-draw for simplicity)
            opponent = state.get_player(1 - player.player_id)
            if not opponent.deck.is_empty():
                card = opponent.deck.cards.pop(0)
                opponent.hand.add_card(card)
                print(f"[Mulligan] Player {opponent.player_id} draws 1 card.")

        if mulligan_count >= max_mulligans:
            raise ValueError(f"Player {player.player_id} has no Basic Pokémon after {max_mulligans} mulligans.")


def _place_initial_pokemon(state: GameState):
    """
    Place Active Pokémon and optional Bench for both players.

    For now, automatically places the first Basic Pokémon as Active.
    Future: Make this interactive for HumanAgent.
    """
    from models import Subtype

    for player in state.players:
        # Find first Basic Pokémon in hand
        basic_pokemon = [
            card for card in player.hand.cards
            if Subtype.BASIC in _get_card_subtypes(card)
        ]

        if not basic_pokemon:
            raise ValueError(f"Player {player.player_id} has no Basic Pokémon in hand.")

        # Place first Basic as Active
        active_card = basic_pokemon[0]
        player.hand.remove_card(active_card.id)
        player.board.active_spot = active_card

        print(f"[Setup] Player {player.player_id} placed {active_card.card_id} as Active.")

        # Auto-place remaining Basics on Bench (up to 5)
        bench_placed = 0
        for card in basic_pokemon[1:]:
            if bench_placed >= 5:
                break

            player.hand.remove_card(card.id)
            player.board.add_to_bench(card)
            bench_placed += 1

            print(f"[Setup] Player {player.player_id} placed {card.card_id} on Bench.")


def _set_prizes(state: GameState):
    """Set aside 6 Prize cards for each player."""
    for player in state.players:
        for _ in range(6):
            if not player.deck.is_empty():
                prize_card = player.deck.cards.pop(0)
                player.prizes.add_card(prize_card)

        print(f"[Setup] Player {player.player_id} set aside 6 Prize cards.")


def _get_card_subtypes(card: CardInstance) -> List:
    """Get subtypes for a card instance."""
    from cards.registry import create_card

    card_def = create_card(card.card_id)
    if card_def and hasattr(card_def, 'subtypes'):
        return card_def.subtypes
    return []


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def quick_setup(deck1_text: str, deck2_text: str, random_seed: int = None) -> GameState:
    """
    Quick setup: Build game state and setup board in one call.

    Args:
        deck1_text: Deck string for Player 0
        deck2_text: Deck string for Player 1
        random_seed: Random seed for reproducibility

    Returns:
        GameState ready to play (Main Phase, Turn 1)

    Example:
        >>> state = quick_setup(deck1, deck2, seed=42)
        >>> # Game is ready to start
    """
    state = build_game_state(deck1_text, deck2_text, random_seed)
    state = setup_initial_board(state, auto_mulligan=True)
    return state


def load_deck_from_file(filepath: str) -> str:
    """
    Load deck string from file.

    Args:
        filepath: Path to deck file

    Returns:
        Deck string

    Example:
        >>> deck_text = load_deck_from_file("decks/charizard.txt")
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()

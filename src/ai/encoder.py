"""
Universal Action Encoder - Positional Action Space for Neural Networks.

This encoder translates Engine Action objects into fixed integer indices
suitable for neural network output heads and legal action masking.

Design Philosophy:
==================

1. POSITIONAL ENCODING: Actions are encoded by position (hand index, bench slot)
   rather than by card identity (card name, card ID). This creates a fixed-size
   action space that works regardless of which cards are in the game.

2. THEORETICAL MAXIMUMS: The action space is sized for the maximum possible
   game state, even if rare. This means "ghost buttons" exist for slots that
   may not always be available (e.g., bench slots 6-8 only unlocked by Area Zero).

3. BUCKET STRATEGY: Similar mechanical inputs share the same range:
   - PLAY_BASIC, PLAY_ITEM, ATTACH_ENERGY, etc. all use PLAY_HAND_CARD range
   - The Engine distinguishes the effect; the encoder just maps positions

4. SEMANTIC SEPARATION: Different logical operations get different ranges to
   avoid "semantic aliasing" where the same button means different things:
   - SELECT_LIST_ITEM: Deck search, discard pile selection (card lists)
   - SELECT_BOARD_SLOT: Targeting Pokemon on board (position-based)
   - SELECT_EFFECT_OPTION: Modal choices (effect A vs B)

5. LEGAL ACTION MASKING: The neural network outputs probabilities for ALL
   indices, but only legal actions (mask=1) are considered during sampling.

Action Space Layout:
====================

Range 0-59:      SELECT_LIST_ITEM - Selecting from a list (deck search, discard choice)
Range 60-659:    PLAY_HAND_CARD - Hand card -> Target (hand_idx * 10 + target_slot)
Range 660-667:   RETREAT - Retreat to bench slot
Range 668-703:   USE_ABILITY - Board Pokemon ability (board_idx * 4 + ability_idx)
Range 704-928:   ATTACK - Board Pokemon attack (board_idx * 25 + attack_idx)
Range 929-937:   TAKE_PRIZE - Take prize from position
Range 938-946:   PROMOTE_ACTIVE - Promote bench Pokemon to active
Range 947-955:   DISCARD_BENCH - Discard Pokemon from bench
Range 956:       END_TURN - End turn
Range 957:       CONFIRM_SELECTION - Confirm current selection
Range 958:       CANCEL_ACTION - Cancel multi-step action
Range 959:       MULLIGAN_DRAW - Draw for mulligan
Range 960:       REVEAL_HAND_MULLIGAN - Reveal hand (no basics)
Range 961:       COIN_FLIP - Flip coin
Range 962:       SHUFFLE - Shuffle deck
Range 963-1022:  SEARCH_SELECT_COUNT - Select count (0-59)
Range 1023-1082: SEARCH_SELECT_CARD - Legacy search select (deck position)
Range 1083:      SEARCH_CONFIRM - Legacy search confirm
Range 1084-1093: SELECT_BOARD_SLOT - Target board position (0=Active, 1-8=Bench, 9=Self)
Range 1094-1097: SELECT_EFFECT_OPTION - Modal choice (option 0-3)
Range 1098:      DECLINE_OPTIONAL - Decline optional selection ("fail to find")

Total Action Space: 1099 indices
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

from models import Action, ActionType, GameState


# =============================================================================
# CONSTANTS - Theoretical Maximums
# =============================================================================

MAX_HAND_SIZE = 60          # Theoretical max cards in hand
MAX_BENCH_SIZE = 8          # Maximum bench (Area Zero Underdepths)
MAX_BOARD_SIZE = 9          # 1 Active + 8 Bench
MAX_ATTACKS = 25            # Pokemon's own attacks + copied attacks (Metronome, Transform, etc.) + VSTAR/GX
MAX_ABILITIES = 4           # Pokemon's own abilities + tool-granted abilities (e.g., Survival Brace)
MAX_TARGETS = 10            # 9 board slots + 1 for self/no-target
MAX_PRIZES = 6              # Standard prize count
MAX_DECK_SIZE = 60          # Maximum deck size
MAX_EFFECT_OPTIONS = 4      # Maximum modal choices (e.g., "Choose 1 of 4 effects")


# =============================================================================
# ACTION SPACE OFFSETS
# =============================================================================

# Range 0-59: SELECT_LIST_ITEM (selecting from a generic list like deck search)
OFFSET_SELECT_LIST_ITEM = 0
SIZE_SELECT_LIST_ITEM = MAX_DECK_SIZE  # 60

# Range 60-659: PLAY_HAND_CARD (hand_index * MAX_TARGETS + target_slot)
# This covers: PLAY_BASIC, PLAY_ITEM, PLAY_SUPPORTER, PLAY_STADIUM,
#              ATTACH_ENERGY, ATTACH_TOOL, EVOLVE, PLACE_ACTIVE, PLACE_BENCH
OFFSET_PLAY_HAND_CARD = OFFSET_SELECT_LIST_ITEM + SIZE_SELECT_LIST_ITEM  # 60
SIZE_PLAY_HAND_CARD = MAX_HAND_SIZE * MAX_TARGETS  # 60 * 10 = 600

# Range 660-667: RETREAT (retreat to bench slot)
OFFSET_RETREAT = OFFSET_PLAY_HAND_CARD + SIZE_PLAY_HAND_CARD  # 660
SIZE_RETREAT = MAX_BENCH_SIZE  # 8

# Range 668-703: USE_ABILITY (board_index * MAX_ABILITIES + ability_index)
OFFSET_USE_ABILITY = OFFSET_RETREAT + SIZE_RETREAT  # 668
SIZE_USE_ABILITY = MAX_BOARD_SIZE * MAX_ABILITIES  # 9 * 4 = 36

# Range 704-928: ATTACK (board_index * MAX_ATTACKS + attack_index)
OFFSET_ATTACK = OFFSET_USE_ABILITY + SIZE_USE_ABILITY  # 704
SIZE_ATTACK = MAX_BOARD_SIZE * MAX_ATTACKS  # 9 * 25 = 225

# TAKE_PRIZE (prize position 0-5, extra slots for flexibility)
OFFSET_TAKE_PRIZE = OFFSET_ATTACK + SIZE_ATTACK  # 929
SIZE_TAKE_PRIZE = MAX_BOARD_SIZE  # 9 (using board size for consistency)

# PROMOTE_ACTIVE (promote bench slot to active)
OFFSET_PROMOTE_ACTIVE = OFFSET_TAKE_PRIZE + SIZE_TAKE_PRIZE  # 938
SIZE_PROMOTE_ACTIVE = MAX_BOARD_SIZE  # 9

# DISCARD_BENCH (discard from bench slot)
OFFSET_DISCARD_BENCH = OFFSET_PROMOTE_ACTIVE + SIZE_PROMOTE_ACTIVE  # 947
SIZE_DISCARD_BENCH = MAX_BOARD_SIZE  # 9

# END_TURN
OFFSET_END_TURN = OFFSET_DISCARD_BENCH + SIZE_DISCARD_BENCH  # 956

# CONFIRM_SELECTION
OFFSET_CONFIRM_SELECTION = OFFSET_END_TURN + 1  # 957

# CANCEL_ACTION
OFFSET_CANCEL_ACTION = OFFSET_CONFIRM_SELECTION + 1  # 958

# MULLIGAN_DRAW
OFFSET_MULLIGAN_DRAW = OFFSET_CANCEL_ACTION + 1  # 959

# REVEAL_HAND_MULLIGAN
OFFSET_REVEAL_HAND_MULLIGAN = OFFSET_MULLIGAN_DRAW + 1  # 960

# COIN_FLIP
OFFSET_COIN_FLIP = OFFSET_REVEAL_HAND_MULLIGAN + 1  # 961

# SHUFFLE
OFFSET_SHUFFLE = OFFSET_COIN_FLIP + 1  # 962

# SEARCH_SELECT_COUNT (legacy - count selection)
OFFSET_SEARCH_SELECT_COUNT = OFFSET_SHUFFLE + 1  # 963
SIZE_SEARCH_SELECT_COUNT = MAX_DECK_SIZE  # 60

# SEARCH_SELECT_CARD (legacy - card selection from deck)
OFFSET_SEARCH_SELECT_CARD = OFFSET_SEARCH_SELECT_COUNT + SIZE_SEARCH_SELECT_COUNT  # 1023
SIZE_SEARCH_SELECT_CARD = MAX_DECK_SIZE  # 60

# SEARCH_CONFIRM (legacy)
OFFSET_SEARCH_CONFIRM = OFFSET_SEARCH_SELECT_CARD + SIZE_SEARCH_SELECT_CARD  # 1083

# SELECT_BOARD_SLOT - Position-based targeting for board Pokemon
# Avoids "semantic aliasing" where button 0 meant both "deck card 0" and "active slot"
# Used when SELECT_CARD targets zone="bench" or zone="board"
OFFSET_SELECT_BOARD_SLOT = OFFSET_SEARCH_CONFIRM + 1  # 1084
SIZE_SELECT_BOARD_SLOT = MAX_TARGETS  # 10 (0=Active, 1-8=Bench, 9=Self/None)

# SELECT_EFFECT_OPTION - Modal choices ("Choose 1 of N effects")
# Used for cards like Colress's Experiment where you pick an abstract effect
OFFSET_SELECT_EFFECT_OPTION = OFFSET_SELECT_BOARD_SLOT + SIZE_SELECT_BOARD_SLOT  # 1094
SIZE_SELECT_EFFECT_OPTION = MAX_EFFECT_OPTIONS  # 4

# DECLINE_OPTIONAL - Explicit "I choose not to select" / "Fail to find"
# Different from CONFIRM_SELECTION (which confirms what you have selected)
# Used when you search deck and want nothing, or decline an optional selection
OFFSET_DECLINE_OPTIONAL = OFFSET_SELECT_EFFECT_OPTION + SIZE_SELECT_EFFECT_OPTION  # 1098

# Total action space size
TOTAL_ACTION_SPACE = OFFSET_DECLINE_OPTIONAL + 1  # 1099


# =============================================================================
# TARGET SLOT ENCODING
# =============================================================================

class TargetSlot(int, Enum):
    """
    Target slot indices for positional encoding.

    Slot 0: Active Pokemon
    Slots 1-8: Bench positions 0-7
    Slot 9: No target / Self target
    """
    ACTIVE = 0
    BENCH_0 = 1
    BENCH_1 = 2
    BENCH_2 = 3
    BENCH_3 = 4
    BENCH_4 = 5
    BENCH_5 = 6
    BENCH_6 = 7
    BENCH_7 = 8
    NO_TARGET = 9


# =============================================================================
# ENCODER CLASS
# =============================================================================

class UniversalActionEncoder:
    """
    Encodes game Actions to fixed integer indices and decodes back.

    This encoder uses positional information (hand index, bench slot) rather
    than card identity, creating a fixed-size action space suitable for
    neural network training.

    Usage:
        encoder = UniversalActionEncoder()

        # Encode an action
        index = encoder.encode(action, state)

        # Decode an index back to action info
        info = encoder.decode(index)

        # Get total action space size
        size = encoder.action_space_size
    """

    def __init__(self):
        """Initialize the encoder."""
        self._action_space_size = TOTAL_ACTION_SPACE

    @property
    def action_space_size(self) -> int:
        """Return the total size of the action space."""
        return self._action_space_size

    def encode(self, action: Action, state: GameState) -> int:
        """
        Encode an Action into a fixed integer index.

        Args:
            action: The Action to encode
            state: Current game state (needed for positional resolution)

        Returns:
            Integer index in range [0, action_space_size)

        Raises:
            ValueError: If action cannot be encoded
        """
        action_type = action.action_type
        player = state.get_player(action.player_id)

        # === HAND-BASED ACTIONS (PLAY_HAND_CARD bucket) ===
        if action_type in (
            ActionType.PLAY_BASIC,
            ActionType.PLAY_ITEM,
            ActionType.PLAY_SUPPORTER,
            ActionType.PLAY_STADIUM,
            ActionType.ATTACH_ENERGY,
            ActionType.ATTACH_TOOL,
            ActionType.EVOLVE,
            ActionType.PLACE_ACTIVE,
            ActionType.PLACE_BENCH,
        ):
            hand_index = self._get_hand_index(action.card_id, player)
            target_slot = self._get_target_slot(action, player, state)
            return OFFSET_PLAY_HAND_CARD + (hand_index * MAX_TARGETS) + target_slot

        # === SELECT_CARD (from resolution stack) ===
        if action_type == ActionType.SELECT_CARD:
            # Use zone metadata to route to appropriate range
            zone = action.metadata.get("zone", "")
            purpose = action.metadata.get("purpose", "")

            # Board-based selections use SELECT_BOARD_SLOT to avoid semantic aliasing
            if zone in ("bench", "board", "active"):
                board_index = self._get_board_slot_for_select(action, player, zone)
                return OFFSET_SELECT_BOARD_SLOT + board_index

            # Deck/hand/discard use SELECT_LIST_ITEM (list-based)
            if zone == "deck":
                deck_index = self._get_deck_index(action.card_id, player)
                return OFFSET_SELECT_LIST_ITEM + min(deck_index, SIZE_SELECT_LIST_ITEM - 1)
            elif zone == "hand":
                hand_index = self._get_hand_index(action.card_id, player)
                return OFFSET_SELECT_LIST_ITEM + min(hand_index, SIZE_SELECT_LIST_ITEM - 1)
            elif zone == "discard":
                discard_index = self._get_discard_index(action.card_id, player)
                return OFFSET_SELECT_LIST_ITEM + min(discard_index, SIZE_SELECT_LIST_ITEM - 1)
            else:
                # Fallback to list position based on selection_number
                selection_num = action.metadata.get("selection_number", 0)
                return OFFSET_SELECT_LIST_ITEM + min(selection_num, SIZE_SELECT_LIST_ITEM - 1)

        # === RETREAT ===
        if action_type == ActionType.RETREAT:
            bench_index = self._get_bench_index(action.target_id, player)
            return OFFSET_RETREAT + min(bench_index, SIZE_RETREAT - 1)

        # === USE_ABILITY ===
        if action_type == ActionType.USE_ABILITY:
            board_index = self._get_board_index(action.card_id, player)
            ability_index = self._get_ability_index(action.ability_name, action.card_id, state)
            return OFFSET_USE_ABILITY + (board_index * MAX_ABILITIES) + ability_index

        # === ATTACK ===
        if action_type == ActionType.ATTACK:
            board_index = self._get_board_index(action.card_id, player)
            attack_index = self._get_attack_index(action.attack_name, action.card_id, state)
            return OFFSET_ATTACK + (board_index * MAX_ATTACKS) + attack_index

        # === TAKE_PRIZE ===
        if action_type == ActionType.TAKE_PRIZE:
            prize_index = action.choice_index if action.choice_index is not None else 0
            return OFFSET_TAKE_PRIZE + min(prize_index, SIZE_TAKE_PRIZE - 1)

        # === PROMOTE_ACTIVE ===
        if action_type == ActionType.PROMOTE_ACTIVE:
            bench_index = self._get_bench_index(action.card_id, player)
            return OFFSET_PROMOTE_ACTIVE + min(bench_index, SIZE_PROMOTE_ACTIVE - 1)

        # === DISCARD_BENCH ===
        if action_type == ActionType.DISCARD_BENCH:
            bench_index = self._get_bench_index(action.card_id, player)
            return OFFSET_DISCARD_BENCH + min(bench_index, SIZE_DISCARD_BENCH - 1)

        # === SIMPLE ACTIONS (single index) ===
        if action_type == ActionType.END_TURN:
            return OFFSET_END_TURN

        if action_type == ActionType.CONFIRM_SELECTION:
            return OFFSET_CONFIRM_SELECTION

        if action_type == ActionType.CANCEL_ACTION:
            return OFFSET_CANCEL_ACTION

        if action_type == ActionType.MULLIGAN_DRAW:
            return OFFSET_MULLIGAN_DRAW

        if action_type == ActionType.REVEAL_HAND_MULLIGAN:
            return OFFSET_REVEAL_HAND_MULLIGAN

        if action_type == ActionType.COIN_FLIP:
            return OFFSET_COIN_FLIP

        if action_type == ActionType.SHUFFLE:
            return OFFSET_SHUFFLE

        # === LEGACY INTERRUPT ACTIONS ===
        if action_type == ActionType.SEARCH_SELECT_COUNT:
            count = action.choice_index if action.choice_index is not None else 0
            return OFFSET_SEARCH_SELECT_COUNT + min(count, SIZE_SEARCH_SELECT_COUNT - 1)

        if action_type == ActionType.SEARCH_SELECT_CARD:
            deck_index = self._get_deck_index(action.card_id, player)
            return OFFSET_SEARCH_SELECT_CARD + min(deck_index, SIZE_SEARCH_SELECT_CARD - 1)

        if action_type == ActionType.SEARCH_CONFIRM:
            return OFFSET_SEARCH_CONFIRM

        if action_type == ActionType.INTERRUPT_ATTACH_ENERGY:
            # Treat as hand card with target
            hand_index = self._get_hand_index(action.card_id, player)
            target_slot = self._get_target_slot(action, player, state)
            return OFFSET_PLAY_HAND_CARD + (hand_index * MAX_TARGETS) + target_slot

        raise ValueError(f"Cannot encode action type: {action_type}")

    def decode(self, index: int) -> Dict[str, Any]:
        """
        Decode an integer index back to action information.

        Args:
            index: Integer index in range [0, action_space_size)

        Returns:
            Dictionary with decoded action information:
            - action_category: str - General category of action
            - action_type: str - Specific action type if determinable
            - hand_index: int - Hand position (for hand-based actions)
            - target_slot: int - Target slot index
            - board_index: int - Board position (for board-based actions)
            - ability_index: int - Ability index
            - attack_index: int - Attack index
            - list_index: int - List selection index

        Raises:
            ValueError: If index is out of range
        """
        if index < 0 or index >= self._action_space_size:
            raise ValueError(f"Index {index} out of range [0, {self._action_space_size})")

        # SELECT_LIST_ITEM
        if index < OFFSET_PLAY_HAND_CARD:
            list_index = index - OFFSET_SELECT_LIST_ITEM
            return {
                "action_category": "SELECT_LIST_ITEM",
                "action_type": "select_card",
                "list_index": list_index,
            }

        # PLAY_HAND_CARD
        if index < OFFSET_RETREAT:
            offset = index - OFFSET_PLAY_HAND_CARD
            hand_index = offset // MAX_TARGETS
            target_slot = offset % MAX_TARGETS
            return {
                "action_category": "PLAY_HAND_CARD",
                "action_type": None,  # Could be PLAY_BASIC, ATTACH_ENERGY, etc.
                "hand_index": hand_index,
                "target_slot": target_slot,
            }

        # RETREAT
        if index < OFFSET_USE_ABILITY:
            bench_index = index - OFFSET_RETREAT
            return {
                "action_category": "RETREAT",
                "action_type": "retreat",
                "bench_index": bench_index,
            }

        # USE_ABILITY
        if index < OFFSET_ATTACK:
            offset = index - OFFSET_USE_ABILITY
            board_index = offset // MAX_ABILITIES
            ability_index = offset % MAX_ABILITIES
            return {
                "action_category": "USE_ABILITY",
                "action_type": "use_ability",
                "board_index": board_index,
                "ability_index": ability_index,
            }

        # ATTACK
        if index < OFFSET_TAKE_PRIZE:
            offset = index - OFFSET_ATTACK
            board_index = offset // MAX_ATTACKS
            attack_index = offset % MAX_ATTACKS
            return {
                "action_category": "ATTACK",
                "action_type": "attack",
                "board_index": board_index,
                "attack_index": attack_index,
            }

        # TAKE_PRIZE
        if index < OFFSET_PROMOTE_ACTIVE:
            prize_index = index - OFFSET_TAKE_PRIZE
            return {
                "action_category": "TAKE_PRIZE",
                "action_type": "take_prize",
                "prize_index": prize_index,
            }

        # PROMOTE_ACTIVE
        if index < OFFSET_DISCARD_BENCH:
            bench_index = index - OFFSET_PROMOTE_ACTIVE
            return {
                "action_category": "PROMOTE_ACTIVE",
                "action_type": "promote_active",
                "bench_index": bench_index,
            }

        # DISCARD_BENCH
        if index < OFFSET_END_TURN:
            bench_index = index - OFFSET_DISCARD_BENCH
            return {
                "action_category": "DISCARD_BENCH",
                "action_type": "discard_bench",
                "bench_index": bench_index,
            }

        # Simple actions
        if index == OFFSET_END_TURN:
            return {"action_category": "END_TURN", "action_type": "end_turn"}
        if index == OFFSET_CONFIRM_SELECTION:
            return {"action_category": "CONFIRM_SELECTION", "action_type": "confirm_selection"}
        if index == OFFSET_CANCEL_ACTION:
            return {"action_category": "CANCEL_ACTION", "action_type": "cancel_action"}
        if index == OFFSET_MULLIGAN_DRAW:
            return {"action_category": "MULLIGAN_DRAW", "action_type": "mulligan_draw"}
        if index == OFFSET_REVEAL_HAND_MULLIGAN:
            return {"action_category": "REVEAL_HAND_MULLIGAN", "action_type": "reveal_hand_mulligan"}
        if index == OFFSET_COIN_FLIP:
            return {"action_category": "COIN_FLIP", "action_type": "coin_flip"}
        if index == OFFSET_SHUFFLE:
            return {"action_category": "SHUFFLE", "action_type": "shuffle"}

        # SEARCH_SELECT_COUNT
        if index < OFFSET_SEARCH_SELECT_CARD:
            count = index - OFFSET_SEARCH_SELECT_COUNT
            return {
                "action_category": "SEARCH_SELECT_COUNT",
                "action_type": "search_select_count",
                "count": count,
            }

        # SEARCH_SELECT_CARD
        if index < OFFSET_SEARCH_CONFIRM:
            deck_index = index - OFFSET_SEARCH_SELECT_CARD
            return {
                "action_category": "SEARCH_SELECT_CARD",
                "action_type": "search_select_card",
                "deck_index": deck_index,
            }

        # SEARCH_CONFIRM
        if index == OFFSET_SEARCH_CONFIRM:
            return {"action_category": "SEARCH_CONFIRM", "action_type": "search_confirm"}

        # SELECT_BOARD_SLOT (NEW - position-based board targeting)
        if index < OFFSET_SELECT_EFFECT_OPTION:
            board_slot = index - OFFSET_SELECT_BOARD_SLOT
            slot_names = ["active", "bench_0", "bench_1", "bench_2", "bench_3",
                          "bench_4", "bench_5", "bench_6", "bench_7", "no_target"]
            slot_name = slot_names[board_slot] if board_slot < len(slot_names) else f"slot_{board_slot}"
            return {
                "action_category": "SELECT_BOARD_SLOT",
                "action_type": "select_card",
                "board_slot": board_slot,
                "slot_name": slot_name,
            }

        # SELECT_EFFECT_OPTION (NEW - modal choices)
        if index < OFFSET_DECLINE_OPTIONAL:
            option_index = index - OFFSET_SELECT_EFFECT_OPTION
            return {
                "action_category": "SELECT_EFFECT_OPTION",
                "action_type": "select_option",
                "option_index": option_index,
            }

        # DECLINE_OPTIONAL (NEW - soft pass / fail to find)
        if index == OFFSET_DECLINE_OPTIONAL:
            return {
                "action_category": "DECLINE_OPTIONAL",
                "action_type": "decline_optional",
            }

        raise ValueError(f"Index {index} could not be decoded")

    def get_legal_action_mask(self, legal_actions: List[Action], state: GameState) -> List[int]:
        """
        Create a binary mask for legal actions.

        Args:
            legal_actions: List of legal Action objects
            state: Current game state

        Returns:
            List of 0s and 1s, length = action_space_size
            1 = legal, 0 = illegal
        """
        mask = [0] * self._action_space_size

        for action in legal_actions:
            try:
                index = self.encode(action, state)
                if 0 <= index < self._action_space_size:
                    mask[index] = 1
            except ValueError:
                # Skip actions that can't be encoded
                pass

        return mask

    # =========================================================================
    # HELPER METHODS - Position Resolution
    # =========================================================================

    def _get_hand_index(self, card_id: Optional[str], player) -> int:
        """Get the index of a card in the player's hand."""
        if not card_id:
            return 0
        for i, card in enumerate(player.hand.cards):
            if card.id == card_id:
                return i
        return 0  # Default to 0 if not found

    def _get_bench_index(self, card_id: Optional[str], player) -> int:
        """Get the index of a Pokemon on the player's bench."""
        if not card_id:
            return 0
        for i, pokemon in enumerate(player.board.bench):
            if pokemon and pokemon.id == card_id:
                return i
        return 0  # Default to 0 if not found

    def _get_board_index(self, card_id: Optional[str], player) -> int:
        """
        Get the board index of a Pokemon (0=Active, 1-8=Bench).
        """
        if not card_id:
            return 0

        # Check active
        if player.board.active_spot and player.board.active_spot.id == card_id:
            return 0

        # Check bench (slots 1-8)
        for i, pokemon in enumerate(player.board.bench):
            if pokemon and pokemon.id == card_id:
                return i + 1  # Bench index + 1 for board index

        return 0  # Default to active

    def _get_board_slot_for_select(self, action: Action, player, zone: str) -> int:
        """
        Get the board slot for a SELECT_CARD action targeting board Pokemon.

        Args:
            action: The SELECT_CARD action
            player: The player making the selection
            zone: The zone ("bench", "board", "active")

        Returns:
            Board slot 0-9 (0=Active, 1-8=Bench, 9=Self/None)
        """
        card_id = action.card_id

        if not card_id:
            return TargetSlot.NO_TARGET

        if zone == "active":
            # Active only selection
            if player.board.active_spot and player.board.active_spot.id == card_id:
                return TargetSlot.ACTIVE
            return TargetSlot.NO_TARGET

        # Check active first
        if player.board.active_spot and player.board.active_spot.id == card_id:
            return TargetSlot.ACTIVE

        # Check bench
        for i, pokemon in enumerate(player.board.bench):
            if pokemon and pokemon.id == card_id:
                return 1 + i  # Bench slots are 1-8

        return TargetSlot.NO_TARGET

    def _get_deck_index(self, card_id: Optional[str], player) -> int:
        """Get the index of a card in the player's deck."""
        if not card_id:
            return 0
        for i, card in enumerate(player.deck.cards):
            if card.id == card_id:
                return i
        return 0

    def _get_discard_index(self, card_id: Optional[str], player) -> int:
        """Get the index of a card in the player's discard pile."""
        if not card_id:
            return 0
        for i, card in enumerate(player.discard.cards):
            if card.id == card_id:
                return i
        return 0

    def _get_target_slot(self, action: Action, player, state: GameState) -> int:
        """
        Determine the target slot for an action.

        Returns:
            Integer 0-9 representing target slot
            0 = Active
            1-8 = Bench slots
            9 = No target / Self
        """
        target_id = action.target_id

        if not target_id:
            # No explicit target - check action type for implicit targeting
            action_type = action.action_type

            if action_type == ActionType.PLAY_BASIC:
                # Playing basic goes to next bench slot
                return 1 + player.board.get_bench_count()
            elif action_type in (ActionType.PLAY_ITEM, ActionType.PLAY_SUPPORTER, ActionType.PLAY_STADIUM):
                # These don't target a Pokemon slot
                return TargetSlot.NO_TARGET
            elif action_type == ActionType.PLACE_ACTIVE:
                return TargetSlot.ACTIVE
            elif action_type == ActionType.PLACE_BENCH:
                return 1 + player.board.get_bench_count()
            else:
                return TargetSlot.NO_TARGET

        # Check if target is active
        if player.board.active_spot and player.board.active_spot.id == target_id:
            return TargetSlot.ACTIVE

        # Check if target is on bench
        for i, pokemon in enumerate(player.board.bench):
            if pokemon and pokemon.id == target_id:
                return 1 + i  # Bench slot = 1 + bench index

        # Check opponent's board
        opponent = state.get_player(1 - action.player_id)

        if opponent.board.active_spot and opponent.board.active_spot.id == target_id:
            return TargetSlot.ACTIVE  # Use same slot encoding for opponent

        for i, pokemon in enumerate(opponent.board.bench):
            if pokemon and pokemon.id == target_id:
                return 1 + i

        return TargetSlot.NO_TARGET

    def _get_attack_index(self, attack_name: Optional[str], card_id: str, state: GameState) -> int:
        """Get the index of an attack on a Pokemon (0-24)."""
        if not attack_name or not card_id:
            return 0

        from cards.factory import get_card_definition

        # Find the card instance
        for player in state.players:
            for pokemon in player.board.get_all_pokemon():
                if pokemon.id == card_id:
                    card_def = get_card_definition(pokemon)
                    if card_def and hasattr(card_def, 'attacks'):
                        for i, attack in enumerate(card_def.attacks or []):
                            if attack.name == attack_name:
                                return min(i, MAX_ATTACKS - 1)
        return 0

    def _get_ability_index(self, ability_name: Optional[str], card_id: str, state: GameState) -> int:
        """Get the index of an ability on a Pokemon (0-3)."""
        if not ability_name or not card_id:
            return 0

        from cards.factory import get_card_definition

        # Find the card instance
        for player in state.players:
            for pokemon in player.board.get_all_pokemon():
                if pokemon.id == card_id:
                    card_def = get_card_definition(pokemon)
                    if card_def and hasattr(card_def, 'abilities'):
                        for i, ability in enumerate(card_def.abilities or []):
                            # Ability can be a namedtuple, dict, or object with .name
                            if hasattr(ability, 'name'):
                                name = ability.name
                            elif isinstance(ability, dict):
                                name = ability.get('name', '')
                            else:
                                continue
                            if name == ability_name:
                                return min(i, MAX_ABILITIES - 1)
        return 0


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_action_space_info() -> Dict[str, Any]:
    """
    Get detailed information about the action space layout.

    Returns:
        Dictionary with range information for each action category
    """
    return {
        "total_size": TOTAL_ACTION_SPACE,
        "ranges": {
            "SELECT_LIST_ITEM": {
                "offset": OFFSET_SELECT_LIST_ITEM,
                "size": SIZE_SELECT_LIST_ITEM,
                "end": OFFSET_PLAY_HAND_CARD - 1,
                "description": "Selecting from card lists (deck search, discard)",
            },
            "PLAY_HAND_CARD": {
                "offset": OFFSET_PLAY_HAND_CARD,
                "size": SIZE_PLAY_HAND_CARD,
                "end": OFFSET_RETREAT - 1,
                "formula": "OFFSET + (hand_index * 10) + target_slot",
            },
            "RETREAT": {
                "offset": OFFSET_RETREAT,
                "size": SIZE_RETREAT,
                "end": OFFSET_USE_ABILITY - 1,
            },
            "USE_ABILITY": {
                "offset": OFFSET_USE_ABILITY,
                "size": SIZE_USE_ABILITY,
                "end": OFFSET_ATTACK - 1,
                "formula": "OFFSET + (board_index * 4) + ability_index",
            },
            "ATTACK": {
                "offset": OFFSET_ATTACK,
                "size": SIZE_ATTACK,
                "end": OFFSET_TAKE_PRIZE - 1,
                "formula": "OFFSET + (board_index * 25) + attack_index",
            },
            "TAKE_PRIZE": {
                "offset": OFFSET_TAKE_PRIZE,
                "size": SIZE_TAKE_PRIZE,
                "end": OFFSET_PROMOTE_ACTIVE - 1,
            },
            "PROMOTE_ACTIVE": {
                "offset": OFFSET_PROMOTE_ACTIVE,
                "size": SIZE_PROMOTE_ACTIVE,
                "end": OFFSET_DISCARD_BENCH - 1,
            },
            "DISCARD_BENCH": {
                "offset": OFFSET_DISCARD_BENCH,
                "size": SIZE_DISCARD_BENCH,
                "end": OFFSET_END_TURN - 1,
            },
            "END_TURN": {"offset": OFFSET_END_TURN, "size": 1},
            "CONFIRM_SELECTION": {"offset": OFFSET_CONFIRM_SELECTION, "size": 1},
            "CANCEL_ACTION": {"offset": OFFSET_CANCEL_ACTION, "size": 1},
            "MULLIGAN_DRAW": {"offset": OFFSET_MULLIGAN_DRAW, "size": 1},
            "REVEAL_HAND_MULLIGAN": {"offset": OFFSET_REVEAL_HAND_MULLIGAN, "size": 1},
            "COIN_FLIP": {"offset": OFFSET_COIN_FLIP, "size": 1},
            "SHUFFLE": {"offset": OFFSET_SHUFFLE, "size": 1},
            "SEARCH_SELECT_COUNT": {
                "offset": OFFSET_SEARCH_SELECT_COUNT,
                "size": SIZE_SEARCH_SELECT_COUNT,
                "end": OFFSET_SEARCH_SELECT_CARD - 1,
            },
            "SEARCH_SELECT_CARD": {
                "offset": OFFSET_SEARCH_SELECT_CARD,
                "size": SIZE_SEARCH_SELECT_CARD,
                "end": OFFSET_SEARCH_CONFIRM - 1,
            },
            "SEARCH_CONFIRM": {"offset": OFFSET_SEARCH_CONFIRM, "size": 1},
            "SELECT_BOARD_SLOT": {
                "offset": OFFSET_SELECT_BOARD_SLOT,
                "size": SIZE_SELECT_BOARD_SLOT,
                "end": OFFSET_SELECT_EFFECT_OPTION - 1,
                "description": "Position-based board targeting (0=Active, 1-8=Bench, 9=Self)",
            },
            "SELECT_EFFECT_OPTION": {
                "offset": OFFSET_SELECT_EFFECT_OPTION,
                "size": SIZE_SELECT_EFFECT_OPTION,
                "end": OFFSET_DECLINE_OPTIONAL - 1,
                "description": "Modal choices (Choose 1 of N effects)",
            },
            "DECLINE_OPTIONAL": {
                "offset": OFFSET_DECLINE_OPTIONAL,
                "size": 1,
                "description": "Decline optional selection / Fail to find",
            },
        },
        "constants": {
            "MAX_HAND_SIZE": MAX_HAND_SIZE,
            "MAX_BENCH_SIZE": MAX_BENCH_SIZE,
            "MAX_BOARD_SIZE": MAX_BOARD_SIZE,
            "MAX_ATTACKS": MAX_ATTACKS,
            "MAX_ABILITIES": MAX_ABILITIES,
            "MAX_TARGETS": MAX_TARGETS,
            "MAX_EFFECT_OPTIONS": MAX_EFFECT_OPTIONS,
        },
    }

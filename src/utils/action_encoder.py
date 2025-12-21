"""
Action Encoder - Encodes game actions with positional information for ML/RL.

This module provides semantic encoding of actions that includes:
- Source card zone and position (hand[0], bench[2], etc.)
- Target card zone and position
- Card category/subcategory (pokemon/basic, energy/basic, trainer/item, etc.)
- Context information (attack name, ability name, selection purpose, etc.)

This is separate from the neural network encoder (ai/encoder.py) which maps
actions to integer indices. This encoder provides human-readable, structured
representations useful for logging, debugging, and interpretable ML features.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum

from models import Action, ActionType, GameState
from cards.factory import get_card_definition
from cards.base import (
    PokemonCard, EnergyCard, TrainerCard,
    DataDrivenPokemon, DataDrivenEnergy, DataDrivenTrainer,
    Subtype
)


class CardCategory(Enum):
    """High-level card category."""
    POKEMON = "pokemon"
    TRAINER = "trainer"
    ENERGY = "energy"
    UNKNOWN = "unknown"


class CardSubcategory(Enum):
    """Card subcategory within its category."""
    # Pokemon
    BASIC = "basic"
    STAGE_1 = "stage_1"
    STAGE_2 = "stage_2"
    VSTAR = "vstar"
    VMAX = "vmax"
    EX = "ex"
    # Trainer
    ITEM = "item"
    SUPPORTER = "supporter"
    STADIUM = "stadium"
    TOOL = "tool"
    # Energy
    BASIC_ENERGY = "basic_energy"
    SPECIAL_ENERGY = "special_energy"
    # Unknown
    UNKNOWN = "unknown"


@dataclass
class EncodedAction:
    """
    Structured representation of an action with positional information.

    Attributes:
        action_type: String name of the action type (lowercase)
        source: Dict with zone, index, card_category, card_subcategory
        target: Dict with zone, index (if applicable)
        context: Dict with action-specific context (attack_name, ability_name, etc.)
        original_action: Reference to the original Action object
    """
    action_type: str
    source: Dict[str, Any] = field(default_factory=dict)
    target: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    original_action: Optional[Action] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a serializable dictionary."""
        return {
            "action_type": self.action_type,
            "source": self.source,
            "target": self.target,
            "context": self.context,
        }


class ActionEncoder:
    """
    Encodes game actions with positional and categorical information.

    Usage:
        encoder = ActionEncoder()
        encoder.set_state(game_state)
        encoded = encoder.encode(action)
    """

    def __init__(self):
        self.state: Optional[GameState] = None

    def set_state(self, state: GameState) -> None:
        """Set the current game state for encoding context."""
        self.state = state

    def encode(self, action: Action) -> EncodedAction:
        """
        Encode an action with positional information.

        Args:
            action: The Action to encode

        Returns:
            EncodedAction with structured position/category info

        Raises:
            ValueError: If state has not been set
        """
        if self.state is None:
            raise ValueError("State must be set before encoding actions")

        action_type = action.action_type.name.lower()
        source = {}
        target = {}
        context = {}

        # Get the player who is taking the action
        player = self.state.players[action.player_id]
        opponent = self.state.players[1 - action.player_id]

        # Encode based on action type
        if action.action_type == ActionType.END_TURN:
            pass  # No source or target

        elif action.action_type == ActionType.PLAY_BASIC:
            source = self._encode_card_in_hand(action.card_id, player)
            target = {"zone": "bench"}

        elif action.action_type == ActionType.ATTACH_ENERGY:
            source = self._encode_card_in_hand(action.card_id, player)
            target = self._encode_pokemon_position(action.target_id, player)

        elif action.action_type == ActionType.EVOLVE:
            source = self._encode_card_in_hand(action.card_id, player)
            target = self._encode_pokemon_position(action.target_id, player)

        elif action.action_type == ActionType.ATTACK:
            source = self._encode_pokemon_position(action.card_id, player)
            target = {"zone": "opponent_active", "index": 0}
            if action.attack_name:
                context["attack_name"] = action.attack_name

        elif action.action_type == ActionType.USE_ABILITY:
            source = self._encode_pokemon_position(action.card_id, player)
            if action.ability_name:
                context["ability_name"] = action.ability_name

        elif action.action_type == ActionType.RETREAT:
            source = {"zone": "active", "index": 0}
            if action.target_id:
                target = self._encode_pokemon_position(action.target_id, player)

        elif action.action_type in (ActionType.PLAY_ITEM, ActionType.PLAY_SUPPORTER, ActionType.PLAY_STADIUM):
            source = self._encode_card_in_hand(action.card_id, player)

        elif action.action_type == ActionType.ATTACH_TOOL:
            source = self._encode_card_in_hand(action.card_id, player)
            if action.target_id:
                target = self._encode_pokemon_position(action.target_id, player)

        elif action.action_type == ActionType.SELECT_CARD:
            source = self._encode_card_anywhere(action.card_id, player, action.metadata)
            if action.metadata:
                for key in ["purpose", "source_card", "selection_number", "max_selections", "zone"]:
                    if key in action.metadata:
                        context[key] = action.metadata[key]

        elif action.action_type == ActionType.SELECT_POKEMON:
            if action.card_id:
                # Try to find the pokemon
                pos = self._encode_pokemon_position(action.card_id, player)
                if not pos:
                    pos = self._encode_pokemon_position(action.card_id, opponent)
                source = pos or {}

        elif action.action_type == ActionType.SWITCH_ACTIVE:
            source = {"zone": "active", "index": 0}
            if action.target_id:
                target = self._encode_pokemon_position(action.target_id, player)

        return EncodedAction(
            action_type=action_type,
            source=source,
            target=target,
            context=context,
            original_action=action,
        )

    def _encode_card_in_hand(self, card_id: str, player) -> Dict[str, Any]:
        """Encode a card's position in hand with category info."""
        for i, card in enumerate(player.hand.cards):
            if card.id == card_id:
                category, subcategory = self._get_card_category(card)
                return {
                    "zone": "hand",
                    "index": i,
                    "card_category": category.value,
                    "card_subcategory": subcategory.value,
                }
        return {}

    def _encode_pokemon_position(self, card_id: str, player) -> Dict[str, Any]:
        """Encode a Pokemon's position on the board."""
        # Check active
        if player.board.active_spot and player.board.active_spot.id == card_id:
            return {"zone": "active", "index": 0}

        # Check bench
        for i, pokemon in enumerate(player.board.bench):
            if pokemon and pokemon.id == card_id:
                return {"zone": "bench", "index": i}

        return {}

    def _encode_card_anywhere(self, card_id: str, player, metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """Encode a card that could be in various zones."""
        # Check hand first
        for i, card in enumerate(player.hand.cards):
            if card.id == card_id:
                category, subcategory = self._get_card_category(card)
                return {
                    "zone": "hand",
                    "index": i,
                    "card_category": category.value,
                    "card_subcategory": subcategory.value,
                }

        # Check deck
        for i, card in enumerate(player.deck.cards):
            if card.id == card_id:
                category, subcategory = self._get_card_category(card)
                return {
                    "zone": "deck",
                    "index": i,
                    "card_category": category.value,
                    "card_subcategory": subcategory.value,
                }

        # Check discard
        for i, card in enumerate(player.discard.cards):
            if card.id == card_id:
                category, subcategory = self._get_card_category(card)
                return {
                    "zone": "discard",
                    "index": i,
                    "card_category": category.value,
                    "card_subcategory": subcategory.value,
                }

        # Check board positions
        board_pos = self._encode_pokemon_position(card_id, player)
        if board_pos:
            return board_pos

        return {}

    def _get_card_category(self, card) -> tuple:
        """Determine the category and subcategory of a card."""
        card_def = get_card_definition(card)
        if not card_def:
            return CardCategory.UNKNOWN, CardSubcategory.UNKNOWN

        # Check card type by class hierarchy
        is_pokemon = isinstance(card_def, (PokemonCard, DataDrivenPokemon))
        is_energy = isinstance(card_def, (EnergyCard, DataDrivenEnergy))
        is_trainer = isinstance(card_def, (TrainerCard, DataDrivenTrainer))

        subtypes = getattr(card_def, 'subtypes', []) or []

        # Helper to check if a Subtype enum is in the list
        def has_subtype(target: Subtype) -> bool:
            for s in subtypes:
                if s == target:
                    return True
                # Also check by value for string comparison
                if hasattr(s, 'value') and s.value == target.value:
                    return True
            return False

        if is_pokemon:
            if has_subtype(Subtype.VSTAR):
                return CardCategory.POKEMON, CardSubcategory.VSTAR
            elif has_subtype(Subtype.VMAX):
                return CardCategory.POKEMON, CardSubcategory.VMAX
            elif has_subtype(Subtype.EX):
                return CardCategory.POKEMON, CardSubcategory.EX
            elif has_subtype(Subtype.STAGE_2):
                return CardCategory.POKEMON, CardSubcategory.STAGE_2
            elif has_subtype(Subtype.STAGE_1):
                return CardCategory.POKEMON, CardSubcategory.STAGE_1
            else:
                return CardCategory.POKEMON, CardSubcategory.BASIC

        elif is_trainer:
            if has_subtype(Subtype.SUPPORTER):
                return CardCategory.TRAINER, CardSubcategory.SUPPORTER
            elif has_subtype(Subtype.STADIUM):
                return CardCategory.TRAINER, CardSubcategory.STADIUM
            elif has_subtype(Subtype.TOOL):
                return CardCategory.TRAINER, CardSubcategory.TOOL
            else:
                return CardCategory.TRAINER, CardSubcategory.ITEM

        elif is_energy:
            # Basic energy has Subtype.BASIC, special energy doesn't
            if has_subtype(Subtype.BASIC):
                return CardCategory.ENERGY, CardSubcategory.BASIC_ENERGY
            else:
                return CardCategory.ENERGY, CardSubcategory.SPECIAL_ENERGY

        return CardCategory.UNKNOWN, CardSubcategory.UNKNOWN


def encode_action(action: Action, state: GameState) -> EncodedAction:
    """
    Convenience function to encode a single action.

    Args:
        action: The action to encode
        state: The current game state

    Returns:
        EncodedAction with structured information
    """
    encoder = ActionEncoder()
    encoder.set_state(state)
    return encoder.encode(action)


def encode_actions(actions: List[Action], state: GameState) -> List[EncodedAction]:
    """
    Convenience function to encode multiple actions.

    Args:
        actions: List of actions to encode
        state: The current game state

    Returns:
        List of EncodedAction objects
    """
    encoder = ActionEncoder()
    encoder.set_state(state)
    return [encoder.encode(action) for action in actions]


def format_encoded_action(encoded: EncodedAction) -> str:
    """
    Format an encoded action as a human-readable string.

    Args:
        encoded: The EncodedAction to format

    Returns:
        Human-readable string representation
    """
    parts = [encoded.action_type.upper()]

    # Source
    if encoded.source:
        zone = encoded.source.get("zone", "?")
        index = encoded.source.get("index", "?")
        parts.append(f"{zone}[{index}]")

    # Arrow and target
    if encoded.target:
        zone = encoded.target.get("zone", "?")
        index = encoded.target.get("index", "")
        if index != "":
            parts.append(f"-> {zone}[{index}]")
        else:
            parts.append(f"-> {zone}")

    # Context
    if encoded.context:
        context_parts = []

        if "attack_name" in encoded.context:
            context_parts.append(encoded.context["attack_name"])
        if "ability_name" in encoded.context:
            context_parts.append(encoded.context["ability_name"])
        if "source_card" in encoded.context:
            context_parts.append(encoded.context["source_card"])
        if "purpose" in encoded.context:
            context_parts.append(encoded.context["purpose"])
        if "selection_number" in encoded.context and "max_selections" in encoded.context:
            context_parts.append(f"{encoded.context['selection_number']}/{encoded.context['max_selections']}")

        if context_parts:
            parts.append(f"({', '.join(context_parts)})")

    return " ".join(parts)

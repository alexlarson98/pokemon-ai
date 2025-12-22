"""
State Encoder - Comprehensive GameState to Neural Network Input Tensors.

This encoder transforms the game state into a structured set of tensors
suitable for neural network consumption. It provides the "eyes" of the AI.

Design Philosophy:
==================

1. PLAYER-RELATIVE: State is always from the active player's perspective.

2. EMBEDDING-READY: Card IDs are mapped to integers via CardIDRegistry.
   Reserved IDs:
   - 0: Empty/None (no card in slot)
   - 1: Hidden/Unknown (opponent's hidden cards)

3. POSITIONAL ALIGNMENT: Hand indices align with ActionEncoder.

4. SIMPLE HAND: Hand is just card IDs - the embedding layer learns properties.

Tensor Layout:
==============
- my_active:       (1, POKEMON_FEATURES)      - Active Pokemon
- my_bench:        (8, POKEMON_FEATURES)      - Bench Pokemon
- my_hand:         (60,)                      - Hand card IDs (index-aligned)
- my_discard:      (60,)                      - Discard pile card IDs
- my_prizes_known: (6,)                       - Known prize card IDs
- opp_active:      (1, POKEMON_FEATURES)      - Opponent's active
- opp_bench:       (8, POKEMON_FEATURES)      - Opponent's bench
- opp_hand_count:  (1,)                       - Opponent hand size
- opp_discard:     (60,)                      - Opponent's discard
- stadium:         (STADIUM_FEATURES,)        - Stadium info
- global_context:  (GLOBAL_FEATURES,)         - Game state features
"""

import json
import os
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import IntEnum
import numpy as np

import sys
script_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(script_dir)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from models import GameState, CardInstance, StatusCondition, EnergyType
from cards.factory import get_card_definition
from cards.base import (
    PokemonCard, EnergyCard, TrainerCard,
    DataDrivenPokemon, DataDrivenEnergy, DataDrivenTrainer,
    Subtype
)


# =============================================================================
# CONSTANTS
# =============================================================================

MAX_HAND_SIZE = 60
MAX_BENCH_SIZE = 8
MAX_PRIZES = 6
MAX_DECK_SIZE = 60
MAX_DISCARD_SIZE = 60
MAX_ENERGY_ATTACHED = 8

# Normalization constants
MAX_HP = 340
MAX_DAMAGE_COUNTERS = 34  # 340 HP / 10
MAX_TURNS = 100
MAX_RETREAT_COST = 5

# Energy types in order (9 types)
ENERGY_TYPES = [
    EnergyType.GRASS,
    EnergyType.FIRE,
    EnergyType.WATER,
    EnergyType.LIGHTNING,
    EnergyType.PSYCHIC,
    EnergyType.FIGHTING,
    EnergyType.DARKNESS,
    EnergyType.METAL,
    EnergyType.COLORLESS,
]
NUM_ENERGY_TYPES = len(ENERGY_TYPES)

# Status conditions in order
STATUS_CONDITIONS = [
    StatusCondition.ASLEEP,
    StatusCondition.BURNED,
    StatusCondition.CONFUSED,
    StatusCondition.PARALYZED,
    StatusCondition.POISONED,
]
NUM_STATUS_CONDITIONS = len(STATUS_CONDITIONS)


# =============================================================================
# FEATURE SIZES
# =============================================================================

# Pokemon features (22 total):
# [0]      card_id (int for embedding)
# [1]      hp_ratio (current/max, 0-1)
# [2]      damage_counters (normalized by 34)
# [3]      max_hp (normalized by 340)
# [4-12]   energy_counts (9 types, normalized by 8)
# [13]     total_energy (normalized by 8)
# [14]     tool_card_id (int for embedding)
# [15]     is_asleep (binary)
# [16]     is_burned (binary)
# [17]     is_confused (binary)
# [18]     is_paralyzed (binary)
# [19]     is_poisoned (binary)
# [20]     ability_used_this_turn (binary)
# [21]     evolved_this_turn (binary)
POKEMON_FEATURES = 22

# Stadium features:
# [0]      stadium_card_id (int for embedding)
# [1]      stadium_owner_is_me (binary)
STADIUM_FEATURES = 2

# Global context features (26 total):
# [0]      turn_number (normalized by 100)
# [1]      is_first_turn (binary)
# [2]      my_prizes_remaining (normalized by 6)
# [3]      opp_prizes_remaining (normalized by 6)
# [4]      my_prizes_taken (normalized by 6)
# [5]      opp_prizes_taken (normalized by 6)
# [6]      my_deck_count (normalized by 60)
# [7]      opp_deck_count (normalized by 60)
# [8]      my_hand_count (normalized by 60)
# [9]      opp_hand_count (normalized by 60)
# [10]     my_discard_count (normalized by 60)
# [11]     opp_discard_count (normalized by 60)
# [12]     my_bench_count (normalized by 8)
# [13]     opp_bench_count (normalized by 8)
# [14]     supporter_played_this_turn (binary)
# [15]     energy_attached_this_turn (binary)
# [16]     retreated_this_turn (binary)
# [17]     my_vstar_power_used (binary)
# [18]     my_gx_attack_used (binary)
# [19]     opp_vstar_power_used (binary)
# [20]     opp_gx_attack_used (binary)
# [21]     has_stadium (binary)
# [22]     i_own_stadium (binary)
# [23]     can_attack_this_turn (binary)
# [24]     my_active_can_ko_opp (binary)
# [25]     opp_active_can_ko_me (binary)
GLOBAL_FEATURES = 26


# =============================================================================
# CARD ID REGISTRY
# =============================================================================

class CardIDRegistry:
    """
    Maps card_id strings to unique integer IDs for embedding lookup.

    Reserved IDs:
    - 0: Empty/None (no card in slot)
    - 1: Hidden/Unknown (opponent's hidden cards)
    """

    EMPTY_ID = 0
    HIDDEN_ID = 1
    FIRST_CARD_ID = 2

    def __init__(self):
        self._card_to_id: Dict[str, int] = {}
        self._id_to_card: Dict[int, str] = {
            self.EMPTY_ID: "<EMPTY>",
            self.HIDDEN_ID: "<HIDDEN>",
        }
        self._next_id = self.FIRST_CARD_ID
        self._frozen = False

    def get_id(self, card_id: str) -> int:
        """Get the integer ID for a card_id string."""
        if card_id in self._card_to_id:
            return self._card_to_id[card_id]

        if self._frozen:
            return self.HIDDEN_ID

        new_id = self._next_id
        self._card_to_id[card_id] = new_id
        self._id_to_card[new_id] = card_id
        self._next_id += 1
        return new_id

    def get_card_id(self, int_id: int) -> Optional[str]:
        """Get the card_id string for an integer ID."""
        return self._id_to_card.get(int_id)

    def freeze(self) -> None:
        """Freeze the registry - no new cards can be added."""
        self._frozen = True

    def unfreeze(self) -> None:
        """Unfreeze the registry to allow new cards."""
        self._frozen = False

    @property
    def size(self) -> int:
        """Total number of unique IDs (including EMPTY and HIDDEN)."""
        return self._next_id

    @property
    def vocab_size(self) -> int:
        """Alias for size - vocabulary size for embeddings."""
        return self._next_id

    @property
    def num_cards(self) -> int:
        """Number of actual card mappings (excluding EMPTY and HIDDEN)."""
        return self._next_id - self.FIRST_CARD_ID

    def save(self, filepath: str) -> None:
        """Save the registry to a JSON file."""
        data = {
            "card_to_id": self._card_to_id,
            "next_id": self._next_id,
        }
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, filepath: str) -> 'CardIDRegistry':
        """Load a registry from a JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)

        registry = cls()
        registry._card_to_id = data["card_to_id"]
        registry._next_id = data["next_id"]

        for card_id, int_id in registry._card_to_id.items():
            registry._id_to_card[int_id] = card_id

        return registry

    def build_from_card_database(self, card_ids: List[str]) -> None:
        """Pre-populate the registry with all known card IDs."""
        for card_id in sorted(card_ids):
            self.get_id(card_id)


# Global registry instance
_global_registry: Optional[CardIDRegistry] = None


def get_global_registry() -> CardIDRegistry:
    """Get or create the global card ID registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = CardIDRegistry()
    return _global_registry


def set_global_registry(registry: CardIDRegistry) -> None:
    """Set the global card ID registry."""
    global _global_registry
    _global_registry = registry


# =============================================================================
# ENCODED STATE
# =============================================================================

@dataclass
class EncodedState:
    """Encoded game state as numpy arrays."""

    # Board state
    my_active: np.ndarray           # (1, POKEMON_FEATURES)
    my_bench: np.ndarray            # (MAX_BENCH_SIZE, POKEMON_FEATURES)
    opp_active: np.ndarray          # (1, POKEMON_FEATURES)
    opp_bench: np.ndarray           # (MAX_BENCH_SIZE, POKEMON_FEATURES)

    # Hand - just card IDs for embedding
    my_hand: np.ndarray             # (MAX_HAND_SIZE,) - int64 card IDs

    # Collections (card ID sequences)
    my_discard: np.ndarray          # (MAX_DISCARD_SIZE,)
    opp_discard: np.ndarray         # (MAX_DISCARD_SIZE,)
    my_prizes_known: np.ndarray     # (MAX_PRIZES,)
    opp_hand_count: np.ndarray      # (1,)

    # Stadium
    stadium: np.ndarray             # (STADIUM_FEATURES,)

    # Global context
    global_context: np.ndarray      # (GLOBAL_FEATURES,)

    def to_dict(self) -> Dict[str, np.ndarray]:
        """Convert to dictionary for model input."""
        return {
            "my_active": self.my_active,
            "my_bench": self.my_bench,
            "opp_active": self.opp_active,
            "opp_bench": self.opp_bench,
            "my_hand": self.my_hand,
            "my_discard": self.my_discard,
            "opp_discard": self.opp_discard,
            "my_prizes_known": self.my_prizes_known,
            "opp_hand_count": self.opp_hand_count,
            "stadium": self.stadium,
            "global_context": self.global_context,
        }

    def to_flat_vector(self) -> np.ndarray:
        """Flatten all arrays into a single vector."""
        return np.concatenate([
            self.my_active.flatten(),
            self.my_bench.flatten(),
            self.opp_active.flatten(),
            self.opp_bench.flatten(),
            self.my_hand.astype(np.float32).flatten(),
            self.my_discard.flatten(),
            self.opp_discard.flatten(),
            self.my_prizes_known.flatten(),
            self.opp_hand_count.flatten(),
            self.stadium.flatten(),
            self.global_context.flatten(),
        ])

    @staticmethod
    def get_input_shapes() -> Dict[str, Tuple[int, ...]]:
        """Get the shapes of all input tensors."""
        return {
            "my_active": (1, POKEMON_FEATURES),
            "my_bench": (MAX_BENCH_SIZE, POKEMON_FEATURES),
            "opp_active": (1, POKEMON_FEATURES),
            "opp_bench": (MAX_BENCH_SIZE, POKEMON_FEATURES),
            "my_hand": (MAX_HAND_SIZE,),
            "my_discard": (MAX_DISCARD_SIZE,),
            "opp_discard": (MAX_DISCARD_SIZE,),
            "my_prizes_known": (MAX_PRIZES,),
            "opp_hand_count": (1,),
            "stadium": (STADIUM_FEATURES,),
            "global_context": (GLOBAL_FEATURES,),
        }


# =============================================================================
# STATE ENCODER
# =============================================================================

class StateEncoder:
    """
    Encodes GameState into neural network-ready tensors.

    The encoding is always from the perspective of the active player.
    """

    def __init__(self, registry: Optional[CardIDRegistry] = None):
        """Initialize the encoder with a card registry."""
        self.registry = registry or get_global_registry()

    def encode(self, state: GameState) -> EncodedState:
        """Encode a game state into neural network tensors."""
        my_idx = state.active_player_index
        opp_idx = 1 - my_idx

        my_player = state.players[my_idx]
        opp_player = state.players[opp_idx]

        # Encode Pokemon
        my_active = self._encode_pokemon(my_player.board.active_spot)
        my_bench = self._encode_bench(my_player.board.bench)
        opp_active = self._encode_pokemon(opp_player.board.active_spot)
        opp_bench = self._encode_bench(opp_player.board.bench)

        # Encode hand as card IDs only
        my_hand = self._encode_hand(my_player.hand.cards)

        # Encode collections
        my_discard = self._encode_card_sequence(my_player.discard.cards, MAX_DISCARD_SIZE)
        opp_discard = self._encode_card_sequence(opp_player.discard.cards, MAX_DISCARD_SIZE)

        # Prize cards
        my_prizes_known = self._encode_prizes(my_player.prizes.cards)

        # Opponent hand count
        opp_hand_count = np.array([len(opp_player.hand.cards) / MAX_HAND_SIZE], dtype=np.float32)

        # Stadium
        stadium = self._encode_stadium(state.stadium, my_idx)

        # Global context
        global_context = self._encode_global_context(state, my_idx)

        return EncodedState(
            my_active=my_active.reshape(1, POKEMON_FEATURES),
            my_bench=my_bench,
            opp_active=opp_active.reshape(1, POKEMON_FEATURES),
            opp_bench=opp_bench,
            my_hand=my_hand,
            my_discard=my_discard,
            opp_discard=opp_discard,
            my_prizes_known=my_prizes_known,
            opp_hand_count=opp_hand_count,
            stadium=stadium,
            global_context=global_context,
        )

    def _encode_pokemon(self, pokemon: Optional[CardInstance]) -> np.ndarray:
        """Encode a single Pokemon into feature vector."""
        features = np.zeros(POKEMON_FEATURES, dtype=np.float32)

        if pokemon is None:
            return features

        card_def = get_card_definition(pokemon)

        # [0] Card ID
        features[0] = self.registry.get_id(pokemon.card_id)

        # [1-3] HP info
        max_hp = card_def.hp if card_def and hasattr(card_def, 'hp') else 100
        current_hp = max(0, max_hp - (pokemon.damage_counters * 10))
        features[1] = current_hp / max_hp if max_hp > 0 else 0
        features[2] = pokemon.damage_counters / MAX_DAMAGE_COUNTERS
        features[3] = max_hp / MAX_HP

        # [4-12] Energy counts by type (9 types)
        energy_counts = self._count_energy_by_type(pokemon.attached_energy)
        for i, etype in enumerate(ENERGY_TYPES):
            features[4 + i] = min(energy_counts.get(etype, 0), MAX_ENERGY_ATTACHED) / MAX_ENERGY_ATTACHED

        # [13] Total energy
        total_energy = len(pokemon.attached_energy)
        features[13] = min(total_energy, MAX_ENERGY_ATTACHED) / MAX_ENERGY_ATTACHED

        # [14] Tool card ID
        if pokemon.attached_tools:
            features[14] = self.registry.get_id(pokemon.attached_tools[0].card_id)

        # [15-19] Status conditions
        features[15] = 1.0 if StatusCondition.ASLEEP in pokemon.status_conditions else 0.0
        features[16] = 1.0 if StatusCondition.BURNED in pokemon.status_conditions else 0.0
        features[17] = 1.0 if StatusCondition.CONFUSED in pokemon.status_conditions else 0.0
        features[18] = 1.0 if StatusCondition.PARALYZED in pokemon.status_conditions else 0.0
        features[19] = 1.0 if StatusCondition.POISONED in pokemon.status_conditions else 0.0

        # [20] Ability used this turn
        features[20] = 1.0 if pokemon.abilities_used_this_turn else 0.0

        # [21] Evolved this turn
        features[21] = 1.0 if pokemon.evolved_this_turn else 0.0

        return features

    def _encode_bench(self, bench: List[Optional[CardInstance]]) -> np.ndarray:
        """Encode all bench slots."""
        result = np.zeros((MAX_BENCH_SIZE, POKEMON_FEATURES), dtype=np.float32)

        for i, pokemon in enumerate(bench[:MAX_BENCH_SIZE]):
            if pokemon is not None:
                result[i] = self._encode_pokemon(pokemon)

        return result

    def _encode_hand(self, cards: List[CardInstance]) -> np.ndarray:
        """
        Encode hand cards as a sequence of card IDs.

        CRITICAL: Index alignment with ActionEncoder - card at index i
        corresponds to "Play Hand Card i" action.
        """
        result = np.zeros(MAX_HAND_SIZE, dtype=np.int64)

        for i, card in enumerate(cards[:MAX_HAND_SIZE]):
            result[i] = self.registry.get_id(card.card_id)

        return result

    def _encode_card_sequence(self, cards: List[CardInstance], max_size: int) -> np.ndarray:
        """Encode a sequence of card IDs."""
        result = np.zeros(max_size, dtype=np.float32)

        for i, card in enumerate(cards[:max_size]):
            result[i] = self.registry.get_id(card.card_id)

        return result

    def _encode_prizes(self, prize_cards: List[CardInstance]) -> np.ndarray:
        """Encode known prize cards."""
        result = np.zeros(MAX_PRIZES, dtype=np.float32)

        for i, card in enumerate(prize_cards[:MAX_PRIZES]):
            if hasattr(card, 'is_revealed') and card.is_revealed:
                result[i] = self.registry.get_id(card.card_id)

        return result

    def _encode_stadium(self, stadium: Optional[CardInstance], my_idx: int) -> np.ndarray:
        """Encode stadium information."""
        features = np.zeros(STADIUM_FEATURES, dtype=np.float32)

        if stadium is not None:
            features[0] = self.registry.get_id(stadium.card_id)
            features[1] = 1.0 if stadium.owner_id == my_idx else 0.0

        return features

    def _encode_global_context(self, state: GameState, my_idx: int) -> np.ndarray:
        """Encode global game context."""
        my_player = state.players[my_idx]
        opp_player = state.players[1 - my_idx]

        features = np.zeros(GLOBAL_FEATURES, dtype=np.float32)

        # [0] Turn number
        features[0] = min(state.turn_count, MAX_TURNS) / MAX_TURNS

        # [1] Is first turn
        features[1] = 1.0 if state.turn_count <= 1 else 0.0

        # [2-3] Prizes remaining
        features[2] = len(my_player.prizes.cards) / MAX_PRIZES
        features[3] = len(opp_player.prizes.cards) / MAX_PRIZES

        # [4-5] Prizes taken
        features[4] = my_player.prizes_taken / MAX_PRIZES
        features[5] = opp_player.prizes_taken / MAX_PRIZES

        # [6-7] Deck counts
        features[6] = len(my_player.deck.cards) / MAX_DECK_SIZE
        features[7] = len(opp_player.deck.cards) / MAX_DECK_SIZE

        # [8-9] Hand counts
        features[8] = len(my_player.hand.cards) / MAX_HAND_SIZE
        features[9] = len(opp_player.hand.cards) / MAX_HAND_SIZE

        # [10-11] Discard counts
        features[10] = min(len(my_player.discard.cards), MAX_DECK_SIZE) / MAX_DECK_SIZE
        features[11] = min(len(opp_player.discard.cards), MAX_DECK_SIZE) / MAX_DECK_SIZE

        # [12-13] Bench counts
        my_bench_count = sum(1 for p in my_player.board.bench if p is not None)
        opp_bench_count = sum(1 for p in opp_player.board.bench if p is not None)
        features[12] = my_bench_count / MAX_BENCH_SIZE
        features[13] = opp_bench_count / MAX_BENCH_SIZE

        # [14-16] Turn action flags
        features[14] = 1.0 if my_player.supporter_played_this_turn else 0.0
        features[15] = 1.0 if my_player.energy_attached_this_turn else 0.0
        features[16] = 1.0 if my_player.retreated_this_turn else 0.0

        # [17-20] One-per-game flags
        features[17] = 1.0 if my_player.vstar_power_used else 0.0
        features[18] = 1.0 if my_player.gx_attack_used else 0.0
        features[19] = 1.0 if opp_player.vstar_power_used else 0.0
        features[20] = 1.0 if opp_player.gx_attack_used else 0.0

        # [21-22] Stadium info
        features[21] = 1.0 if state.stadium is not None else 0.0
        features[22] = 1.0 if state.stadium and state.stadium.owner_id == my_idx else 0.0

        # [23] Can attack this turn
        can_attack = not (state.turn_count == 1 and state.starting_player_id == my_idx)
        features[23] = 1.0 if can_attack else 0.0

        # [24-25] Rough KO potential
        my_active = my_player.board.active_spot
        opp_active = opp_player.board.active_spot

        if my_active and opp_active:
            my_max_dmg = self._get_max_attack_damage(get_card_definition(my_active))
            opp_max_dmg = self._get_max_attack_damage(get_card_definition(opp_active))

            opp_def = get_card_definition(opp_active)
            my_def = get_card_definition(my_active)

            opp_hp = opp_def.hp if opp_def and hasattr(opp_def, 'hp') else 100
            my_hp = my_def.hp if my_def and hasattr(my_def, 'hp') else 100

            opp_current = opp_hp - (opp_active.damage_counters * 10)
            my_current = my_hp - (my_active.damage_counters * 10)

            features[24] = 1.0 if my_max_dmg >= opp_current else 0.0
            features[25] = 1.0 if opp_max_dmg >= my_current else 0.0

        return features

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _count_energy_by_type(self, energy_cards: List[CardInstance]) -> Dict[EnergyType, int]:
        """Count attached energy by type."""
        counts: Dict[EnergyType, int] = {}

        for energy in energy_cards:
            card_def = get_card_definition(energy)
            if card_def and hasattr(card_def, 'energy_type'):
                etype = card_def.energy_type
                counts[etype] = counts.get(etype, 0) + 1
            elif card_def and hasattr(card_def, 'provides'):
                for etype in (card_def.provides or []):
                    counts[etype] = counts.get(etype, 0) + 1

        return counts

    def _get_max_attack_damage(self, card_def) -> int:
        """Get the maximum base damage from any attack."""
        if card_def is None or not hasattr(card_def, 'attacks'):
            return 0

        max_damage = 0
        for attack in (card_def.attacks or []):
            if hasattr(attack, 'damage'):
                damage = attack.damage
                if isinstance(damage, str):
                    damage = damage.replace('+', '').replace('x', '').replace('×', '')
                    try:
                        damage = int(damage) if damage else 0
                    except ValueError:
                        damage = 0
                max_damage = max(max_damage, damage or 0)

        return max_damage


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def encode_state(state: GameState, registry: Optional[CardIDRegistry] = None) -> EncodedState:
    """Convenience function to encode a game state."""
    encoder = StateEncoder(registry)
    return encoder.encode(state)


def get_input_shapes() -> Dict[str, Tuple[int, ...]]:
    """Get shapes of all input tensors."""
    return EncodedState.get_input_shapes()


def get_pokemon_feature_names() -> List[str]:
    """Get human-readable names for Pokemon features."""
    names = [
        "card_id", "hp_ratio", "damage_counters", "max_hp",
    ]
    for etype in ENERGY_TYPES:
        names.append(f"energy_{etype.name.lower()}")
    names.extend([
        "total_energy", "tool_card_id",
        "is_asleep", "is_burned", "is_confused", "is_paralyzed", "is_poisoned",
        "ability_used", "evolved_this_turn"
    ])
    return names


def get_global_feature_names() -> List[str]:
    """Get human-readable names for global context features."""
    return [
        "turn_number", "is_first_turn",
        "my_prizes_remaining", "opp_prizes_remaining",
        "my_prizes_taken", "opp_prizes_taken",
        "my_deck_count", "opp_deck_count",
        "my_hand_count", "opp_hand_count",
        "my_discard_count", "opp_discard_count",
        "my_bench_count", "opp_bench_count",
        "supporter_played", "energy_attached", "retreated",
        "my_vstar_used", "my_gx_used",
        "opp_vstar_used", "opp_gx_used",
        "has_stadium", "i_own_stadium",
        "can_attack_this_turn",
        "my_active_can_ko", "opp_active_can_ko",
    ]


# =============================================================================
# FEATURE SIZE EXPORTS
# =============================================================================

FEATURES_PER_SLOT = POKEMON_FEATURES
GLOBAL_CONTEXT_SIZE = GLOBAL_FEATURES

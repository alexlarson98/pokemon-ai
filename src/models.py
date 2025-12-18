"""
Pokémon TCG Engine - Data Layer (models.py)
Defines the immutable "Snapshot" of the game universe.
All models must be serializable (JSON) and clonable (Deep Copy).
"""

from typing import List, Optional, Set, Dict, Literal
from enum import Enum
from pydantic import BaseModel, Field, field_validator


# ============================================================================
# 1. CARD ATTRIBUTES (IMMUTABLE) - Constitution Section 1.1
# ============================================================================

class Supertype(str, Enum):
    """Card supertype classification."""
    POKEMON = "Pokemon"
    TRAINER = "Trainer"
    ENERGY = "Energy"


class Subtype(str, Enum):
    """Card subtype classification."""
    # Pokémon subtypes
    BASIC = "Basic"
    STAGE_1 = "Stage 1"
    STAGE_2 = "Stage 2"
    TERA = "Tera"
    EX = "ex"
    VSTAR = "VSTAR"
    MEGA = "MEGA"
    V = "V"
    VMAX = "VMAX"
    GX = "GX"
    ANCIENT = "Ancient"
    FUTURE = "Future"

    # Trainer subtypes
    ITEM = "Item"
    SUPPORTER = "Supporter"
    STADIUM = "Stadium"
    TOOL = "Pokemon Tool"
    ACE_SPEC = "ACE SPEC"


class EnergyClass(str, Enum):
    """Energy card classification."""
    BASIC = "Basic"
    SPECIAL = "Special"


class EnergyType(str, Enum):
    """Energy types for cost and weakness/resistance."""
    GRASS = "Grass"
    FIRE = "Fire"
    WATER = "Water"
    LIGHTNING = "Lightning"
    PSYCHIC = "Psychic"
    FIGHTING = "Fighting"
    DARKNESS = "Darkness"
    METAL = "Metal"
    COLORLESS = "Colorless"


class StatusCondition(str, Enum):
    """Status conditions (Constitution Section 5)."""
    POISONED = "Poisoned"
    BURNED = "Burned"
    ASLEEP = "Asleep"
    PARALYZED = "Paralyzed"
    CONFUSED = "Confused"


class EffectSource(str, Enum):
    """Source of active effects."""
    ATTACK = "attack"       # e.g., "During opponent's next turn..."
    ABILITY = "ability"     # e.g., Manaphy's Wave Veil
    TRAINER = "trainer"     # e.g., Bravery Charm (+50 HP)
    TOOL = "tool"           # e.g., Float Stone (retreat cost -2)
    STADIUM = "stadium"     # e.g., Path to the Peak (VSTAR disabled)
    ENERGY = "energy"       # e.g., Double Turbo Energy (-20 damage)


# ============================================================================
# 2. ACTIVE EFFECTS (BUFFS/DEBUFFS)
# ============================================================================

class ActiveEffect(BaseModel):
    """
    Represents an active effect/modifier on the game state.

    Examples:
    - Manaphy's "Wave Veil": Prevents bench damage
    - Iron Leaves ex: "This Pokemon can't attack during your next turn"
    - Bravery Charm: "+50 HP to this Pokemon"
    - Float Stone: "Retreat cost -2"
    """
    # Identity
    name: str = Field(..., description="Effect name (e.g., 'Wave Veil', 'Cant Attack')")
    source: EffectSource = Field(..., description="What created this effect")
    source_card_id: str = Field(..., description="Card ID that created the effect")

    # Target
    target_player_id: Optional[int] = Field(None, description="Affected player (None = global)")
    target_card_id: Optional[str] = Field(None, description="Specific card (None = all/player-wide)")

    # Duration
    duration_turns: int = Field(1, description="1 = This turn, 2 = Until end of next turn, -1 = Permanent")
    created_turn: int = Field(..., description="Turn number when effect was created")
    created_phase: str = Field(..., description="Phase when effect was created (GamePhase value)")
    expires_on_player: Optional[int] = Field(None, description="Expires at end of this player's turn (for asymmetric effects)")

    # Effect parameters
    params: Dict = Field(default_factory=dict, description="Effect-specific data")

    # Examples of params:
    # - {"prevents": "bench_damage"} - Manaphy Wave Veil
    # - {"prevents": "attacks", "self": True} - Iron Leaves ex self-lock
    # - {"hp_bonus": 50} - Bravery Charm
    # - {"retreat_cost_modifier": -2} - Float Stone
    # - {"damage_modifier": -20} - Double Turbo Energy
    # - {"prevents": "abilities", "subtype": "VSTAR"} - Path to the Peak

    def is_expired(self, current_turn: int, current_player: int, current_phase: str) -> bool:
        """
        Check if effect has expired.

        Args:
            current_turn: Current turn number
            current_player: Current active player ID
            current_phase: Current game phase (GamePhase value)

        Returns:
            True if effect should be removed
        """
        # Permanent effects never expire
        if self.duration_turns == -1:
            return False

        # Check if effect expires on specific player's turn
        if self.expires_on_player is not None:
            if current_player == self.expires_on_player and current_phase == "cleanup":
                return True

        # Check turn-based expiration
        turns_elapsed = current_turn - self.created_turn
        return turns_elapsed >= self.duration_turns


# ============================================================================
# 3. CARD INSTANCE (THE PHYSICAL OBJECT)
# ============================================================================

class CardInstance(BaseModel):
    """
    Represents a physical card in a zone.
    Mutable state wrapper around immutable card data.
    """
    # Identity
    id: str = Field(..., description="Unique instance ID (e.g., 'card_123')")
    card_id: str = Field(..., description="Card definition ID (e.g., 'sv3-125')")
    owner_id: int = Field(..., description="Player index (0 or 1)")

    # Pokémon-specific state
    current_hp: Optional[int] = Field(None, description="Current HP (None for non-Pokémon)")
    damage_counters: int = Field(0, description="Number of damage counters (10 HP each)")
    status_conditions: Set[StatusCondition] = Field(default_factory=set)

    # Attached cards
    attached_energy: List['CardInstance'] = Field(default_factory=list, description="Energy cards attached")
    attached_tools: List['CardInstance'] = Field(default_factory=list, description="Tool cards attached")
    evolution_chain: List[str] = Field(default_factory=list, description="Card IDs of evolution history")

    # Temporal state
    turns_in_play: int = Field(0, description="Number of turns since played (for evolution sickness)")
    evolved_this_turn: bool = Field(False, description="Whether this Pokémon evolved this turn (blocks further evolution)")
    abilities_used_this_turn: Set[str] = Field(default_factory=set, description="Ability names used this turn")
    attack_effects: List[str] = Field(default_factory=list, description="Active attack effects (e.g., 'cannot_attack_next_turn')")

    # Metadata
    is_revealed: bool = Field(False, description="Whether card is revealed to opponent")

    model_config = {"arbitrary_types_allowed": True}

    def get_total_hp_loss(self) -> int:
        """Calculate total HP lost from damage counters."""
        return self.damage_counters * 10

    def is_knocked_out(self, max_hp: int) -> bool:
        """Check if Pokémon is knocked out."""
        if self.current_hp is None:
            return False
        return self.get_total_hp_loss() >= max_hp


# ============================================================================
# 3. ZONES (CONTAINERS) - Constitution Section 1.2
# ============================================================================

class Zone(BaseModel):
    """
    Ordered container for cards.
    Supports all zone types defined in Constitution Section 1.2.
    """
    cards: List[CardInstance] = Field(default_factory=list)
    is_ordered: bool = Field(True, description="Whether card order matters (Deck, Discard)")
    is_hidden: bool = Field(False, description="Whether zone is hidden from opponent")
    is_private: bool = Field(False, description="Whether only owner can see contents")

    def add_card(self, card: CardInstance, position: Optional[int] = None) -> None:
        """Add card to zone at specific position (default: end)."""
        if position is None:
            self.cards.append(card)
        else:
            self.cards.insert(position, card)

    def remove_card(self, card_id: str) -> Optional[CardInstance]:
        """Remove and return card by instance ID."""
        for i, card in enumerate(self.cards):
            if card.id == card_id:
                return self.cards.pop(i)
        return None

    def find_card(self, card_id: str) -> Optional[CardInstance]:
        """Find card by instance ID without removing."""
        for card in self.cards:
            if card.id == card_id:
                return card
        return None

    def count(self) -> int:
        """Get number of cards in zone."""
        return len(self.cards)

    def is_empty(self) -> bool:
        """Check if zone is empty."""
        return len(self.cards) == 0


# ============================================================================
# 4. BOARD STATE (PLAY AREA)
# ============================================================================

class Board(BaseModel):
    """
    Represents a player's board (Active, Bench, Stadium).
    """
    active_spot: Optional[CardInstance] = Field(None, description="Active Pokémon")
    bench: List[Optional[CardInstance]] = Field(default_factory=list, description="Bench Pokémon (max 5, or 8)")
    max_bench_size: int = Field(5, description="Maximum bench size (5 default, 8 with Area Zero)")

    def get_bench_count(self) -> int:
        """Count non-None Pokémon on bench."""
        return sum(1 for slot in self.bench if slot is not None)

    def add_to_bench(self, pokemon: CardInstance) -> bool:
        """Add Pokémon to bench. Returns True if successful."""
        if self.get_bench_count() >= self.max_bench_size:
            return False
        self.bench.append(pokemon)
        return True

    def remove_from_bench(self, card_id: str) -> Optional[CardInstance]:
        """Remove Pokémon from bench by instance ID."""
        for i, pokemon in enumerate(self.bench):
            if pokemon and pokemon.id == card_id:
                return self.bench.pop(i)
        return None

    def get_all_pokemon(self) -> List[CardInstance]:
        """Get all Pokémon in play (Active + Bench)."""
        result = []
        if self.active_spot:
            result.append(self.active_spot)
        result.extend([p for p in self.bench if p is not None])
        return result


# ============================================================================
# 5. PLAYER STATE
# ============================================================================

class PlayerState(BaseModel):
    """
    Represents a single player's state.
    Tracks zones, board, and once-per-game flags (Constitution Section 3).
    """
    player_id: int = Field(..., description="Player index (0 or 1)")
    name: str = Field("Player", description="Player display name")

    # Zones (Constitution Section 1.2)
    deck: Zone = Field(default_factory=lambda: Zone(is_ordered=True, is_hidden=True))
    hand: Zone = Field(default_factory=lambda: Zone(is_ordered=False, is_private=True))
    discard: Zone = Field(default_factory=lambda: Zone(is_ordered=True, is_hidden=False))
    prizes: Zone = Field(default_factory=lambda: Zone(is_ordered=True, is_hidden=True))

    # Board
    board: Board = Field(default_factory=Board)

    # Global Flags (Constitution Section 3)
    vstar_power_used: bool = Field(False, description="VSTAR Power used this game")
    gx_attack_used: bool = Field(False, description="GX Attack used this game (legacy)")

    # Turn Flags (Reset each turn)
    supporter_played_this_turn: bool = Field(False, description="Supporter played this turn")
    energy_attached_this_turn: bool = Field(False, description="Energy attached this turn")
    retreated_this_turn: bool = Field(False, description="Retreated this turn")
    stadium_played_this_turn: bool = Field(False, description="Stadium played this turn")

    # Counters
    prizes_taken: int = Field(0, description="Number of prizes taken")

    # Knowledge Layer (for Belief-Based Action Generation / ISMCTS)
    initial_deck_counts: Dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Name-based card counts capturing all 60 cards at game start. "
            "Used by belief engine for ISMCTS - player doesn't know which functional "
            "versions exist, only card names. Example: {'Charmander': 2, 'Fire Energy': 12}"
        )
    )
    functional_id_map: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Maps card_id -> functional_id for ALL player's cards. Used by action generation "
            "to create separate actions for functionally different versions of the same card. "
            "Example: card_id='abc123' -> 'Charmander|70|Basic|Ember:30|'"
        )
    )
    has_searched_deck: bool = Field(
        False,
        description="Whether player has viewed deck contents (unlocks perfect knowledge)"
    )

    def reset_turn_flags(self) -> None:
        """Reset flags at end of turn (Constitution Section 3)."""
        self.supporter_played_this_turn = False
        self.energy_attached_this_turn = False
        self.retreated_this_turn = False
        self.stadium_played_this_turn = False

    def has_active_pokemon(self) -> bool:
        """Check if player has an Active Pokémon."""
        return self.board.active_spot is not None

    def has_any_pokemon_in_play(self) -> bool:
        """Check if player has any Pokémon in play."""
        return self.has_active_pokemon() or self.board.get_bench_count() > 0


# ============================================================================
# 6. GAME STATE (THE UNIVERSE)
# ============================================================================

class GamePhase(str, Enum):
    """Game phases (Constitution Section 2)."""
    SETUP = "setup"
    MULLIGAN = "mulligan"
    DRAW = "draw"
    MAIN = "main"
    ATTACK = "attack"
    CLEANUP = "cleanup"
    END = "end"
    SUDDEN_DEATH = "sudden_death"


class GameResult(str, Enum):
    """Game end conditions."""
    ONGOING = "ongoing"
    PLAYER_0_WIN = "player_0_win"
    PLAYER_1_WIN = "player_1_win"
    DRAW = "draw"


class GameState(BaseModel):
    """
    The root state object (Architecture Section 3).
    Represents the complete game snapshot - must be serializable and clonable.
    """
    # Players
    players: List[PlayerState] = Field(..., min_length=2, max_length=2)

    # Turn tracking
    turn_count: int = Field(1, description="Current turn number")
    active_player_index: int = Field(0, description="Index of active player (0 or 1)")
    starting_player_id: int = Field(0, description="Player who goes first (0 or 1)")
    current_phase: GamePhase = Field(GamePhase.SETUP, description="Current game phase")

    # Global state
    stadium: Optional[CardInstance] = Field(None, description="Active Stadium card")
    active_effects: List[ActiveEffect] = Field(default_factory=list, description="Active effects (buffs/debuffs/modifiers)")
    global_effects: List[Dict] = Field(default_factory=list, description="Legacy global effects (deprecated)")

    # Game result
    result: GameResult = Field(GameResult.ONGOING, description="Game outcome")
    winner_id: Optional[int] = Field(None, description="Winning player ID if game ended")

    # History Tracking (for cards like Fezandipiti ex)
    turn_metadata: Dict = Field(default_factory=dict, description="Events that happened this turn")
    last_turn_metadata: Dict = Field(default_factory=dict, description="Events from previous turn")

    # Metadata
    random_seed: Optional[int] = Field(None, description="RNG seed for deterministic simulation")
    move_history: List[str] = Field(default_factory=list, description="Action history for replay")

    # Interrupt Stack (for multi-step ability resolution)
    pending_interrupt: Optional['SearchAndAttachState'] = Field(
        None,
        description="Active interrupt state for multi-step abilities (e.g., Infernal Reign)"
    )

    @field_validator('players')
    @classmethod
    def validate_players(cls, v):
        """Ensure exactly 2 players with IDs 0 and 1."""
        if len(v) != 2:
            raise ValueError("Game must have exactly 2 players")
        if v[0].player_id != 0 or v[1].player_id != 1:
            raise ValueError("Player IDs must be 0 and 1")
        return v

    def get_active_player(self) -> PlayerState:
        """Get the current active player."""
        return self.players[self.active_player_index]

    def get_opponent(self) -> PlayerState:
        """Get the opponent of the active player."""
        return self.players[1 - self.active_player_index]

    def get_player(self, player_id: int) -> PlayerState:
        """Get player by ID."""
        return self.players[player_id]

    def switch_active_player(self) -> None:
        """Switch to the other player."""
        self.active_player_index = 1 - self.active_player_index

    def is_game_over(self) -> bool:
        """Check if game has ended."""
        return self.result != GameResult.ONGOING

    def clone(self) -> 'GameState':
        """Create a deep copy of the game state for MCTS simulation."""
        return self.model_copy(deep=True)


# ============================================================================
# 7. INTERRUPT STACK STATES (Multi-step ability resolution)
# ============================================================================

class InterruptPhase(str, Enum):
    """Phases for multi-step interrupt resolution."""
    SEARCH_SELECT = "search_select"     # Selecting cards from deck search
    ATTACH_ENERGY = "attach_energy"     # Choosing where to attach energy


class SearchAndAttachState(BaseModel):
    """
    Interrupt state for search-and-attach abilities like Infernal Reign.

    This enables MCTS to break down complex abilities into atomic choices:
    1. Search phase: Select up to N cards from deck
    2. Attach phase: Choose target for each selected card (one at a time)

    Example Flow (Infernal Reign):
    - Phase 1: Select 0-3 Fire Energy from deck
    - Phase 2: Attach Energy 1 to [target choices]
    - Phase 3: Attach Energy 2 to [target choices]
    - Phase 4: Attach Energy 3 to [target choices]
    - Complete: Shuffle deck, resume normal gameplay
    """
    # Identity
    ability_name: str = Field(..., description="Name of ability (e.g., 'Infernal Reign')")
    source_card_id: str = Field(..., description="Card ID that triggered this ability")
    player_id: int = Field(..., description="Player who controls this ability")

    # Current phase
    phase: InterruptPhase = Field(InterruptPhase.SEARCH_SELECT, description="Current interrupt phase")

    # Search parameters
    search_filter: Dict = Field(default_factory=dict, description="Filter for searchable cards (e.g., {'energy_type': 'Fire', 'subtype': 'Basic'})")
    max_select: int = Field(3, description="Maximum cards that can be selected")

    # State tracking
    selected_card_ids: List[str] = Field(default_factory=list, description="Cards selected during search phase")
    cards_to_attach: List[str] = Field(default_factory=list, description="Remaining cards to attach (in order)")
    current_attach_index: int = Field(0, description="Index of current card being attached")

    # Completion flag
    is_complete: bool = Field(False, description="Whether all steps are done")


# ============================================================================
# 8. ACTION REPRESENTATION
# ============================================================================

class ActionType(str, Enum):
    """All possible action types in the game."""
    # Setup
    MULLIGAN_DRAW = "mulligan_draw"
    REVEAL_HAND_MULLIGAN = "reveal_hand_mulligan"  # Category 5 Fix: No basics in hand
    PLACE_ACTIVE = "place_active"
    PLACE_BENCH = "place_bench"

    # Main phase
    PLAY_BASIC = "play_basic"
    EVOLVE = "evolve"
    ATTACH_ENERGY = "attach_energy"
    PLAY_ITEM = "play_item"
    PLAY_SUPPORTER = "play_supporter"
    PLAY_STADIUM = "play_stadium"
    ATTACH_TOOL = "attach_tool"
    USE_ABILITY = "use_ability"
    RETREAT = "retreat"

    # Attack phase
    ATTACK = "attack"
    END_TURN = "end_turn"

    # Reactions
    TAKE_PRIZE = "take_prize"
    PROMOTE_ACTIVE = "promote_active"

    # Interrupt Stack Actions (Multi-step ability resolution)
    SEARCH_SELECT_CARD = "search_select_card"     # Select a card during search phase
    SEARCH_CONFIRM = "search_confirm"             # Confirm search selection (done selecting)
    INTERRUPT_ATTACH_ENERGY = "interrupt_attach_energy"  # Attach energy during interrupt

    # Chance
    COIN_FLIP = "coin_flip"
    SHUFFLE = "shuffle"


class Action(BaseModel):
    """
    Represents a single game action.
    Used by Engine.get_legal_actions() and Engine.step().
    """
    action_type: ActionType
    player_id: int

    # Optional parameters based on action type
    card_id: Optional[str] = None
    target_id: Optional[str] = None
    attack_name: Optional[str] = None
    ability_name: Optional[str] = None
    choice_index: Optional[int] = None
    metadata: Dict = Field(default_factory=dict, description="Action-specific data")

    # 'Spark of Life' additions
    parameters: Dict = Field(default_factory=dict, description="Variable inputs (discard_ids, search_targets, etc.)")
    display_label: Optional[str] = Field(None, description="UI/Logging label (e.g., 'Attach Air Balloon to Active')")

    def __str__(self) -> str:
        """Human-readable action description."""
        # Use display_label if available
        if self.display_label:
            return self.display_label

        # Fallback to default format
        parts = [f"{self.action_type.value}"]
        if self.card_id:
            parts.append(f"card={self.card_id}")
        if self.target_id:
            parts.append(f"target={self.target_id}")
        if self.attack_name:
            parts.append(f"attack={self.attack_name}")
        return f"Action({', '.join(parts)})"

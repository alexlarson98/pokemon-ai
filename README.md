# Pokémon TCG Engine

A high-fidelity Pokémon Trading Card Game simulator designed for AI research, specifically MCTS (Monte Carlo Tree Search) and reinforcement learning agents. Built with a clean separation between game rules (the "Constitution"), state management, and AI agents.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Core Design Principles](#core-design-principles)
3. [System Layers](#system-layers)
4. [Key Subsystems](#key-subsystems)
5. [Data Flow](#data-flow)
6. [Getting Started](#getting-started)
7. [Testing](#testing)

---

## Architecture Overview

This engine is built around a **pure functional core** with **immutable state snapshots**, making it ideal for tree search algorithms that require cheap state cloning and rollback.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         AGENTS LAYER                        │
│  (AI Agents, Human Players, Random Bots)                   │
│                                                             │
│  • HumanAgent - Interactive console player                  │
│  • RandomAgent - Baseline for testing                       │
│  • MCTSAgent - Future: Tree search implementation          │
└─────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       ENGINE LAYER                          │
│  (PokemonEngine - The "Referee")                           │
│                                                             │
│  • get_legal_actions() - Generate valid moves              │
│  • step(action) - Apply action, return new state           │
│  • check_win_condition() - Detect game end                 │
│  • resolve_interrupts() - Handle forced choices            │
└─────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    CARD LOGIC LAYER                         │
│  (Unified Ability Schema - 5 Pillars Architecture)         │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │               MASTER_LOGIC_REGISTRY                  │  │
│  │  Maps card_id -> { "AbilityName": { category, ... }} │  │
│  └─────────────────────────────────────────────────────┘  │
│                          │                                  │
│    ┌─────────────────────┴─────────────────────┐           │
│    ▼                                           ▼           │
│  ┌───────────────────┐           ┌───────────────────┐    │
│  │   Set Modules     │           │   Card Library    │    │
│  │   (sv1..svp)      │           │   (Shared Logic)  │    │
│  │                   │           │                   │    │
│  │ • SV1_LOGIC       │           │ • trainers.py     │    │
│  │ • SV3_LOGIC       │◀──imports─│   - Nest Ball     │    │
│  │ • SVP_LOGIC       │           │   - Ultra Ball    │    │
│  │ • ME1_LOGIC       │           │   - Rare Candy    │    │
│  │ • ME2_LOGIC       │           │   - Iono          │    │
│  │   ...             │           │   - Poffin        │    │
│  └───────────────────┘           └───────────────────┘    │
│                                                             │
│  Categories (5 Pillars):                                   │
│  • attack      - Damage-dealing moves                      │
│  • activatable - Player-triggered (trainers, abilities)    │
│  • modifier    - Passive value changes (retreat, damage)   │
│  • guard       - Effect blockers (status immunity)         │
│  • hook        - Event triggers (on_evolve, on_knockout)   │
└─────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     KNOWLEDGE LAYER                         │
│  (ISMCTS Support - Imperfect Information Handling)         │
│                                                             │
│  • initial_deck_counts - Track deck composition            │
│  • has_searched_deck - Perfect vs imperfect knowledge      │
│  • get_deck_search_candidates() - Belief-based search      │
│                                                             │
│  Enables AI to reason about hidden information:            │
│  "What COULD be in my deck based on what I've seen?"       │
└─────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       DATA LAYER                            │
│  (Immutable State Snapshots - models.py)                   │
│                                                             │
│  • GameState - Complete game snapshot                      │
│  • PlayerState - Player-specific state                     │
│  • CardInstance - Runtime card state                       │
│  • Action - Player decisions                               │
│  • Board, Hand, Deck, Discard - Zone models                │
│                                                             │
│  All models are:                                            │
│  ✓ Pydantic-based (validated, serializable)                │
│  ✓ Deep-copyable (cheap MCTS rollouts)                     │
│  ✓ JSON-serializable (persistence, debugging)              │
└─────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    CARD REGISTRY                            │
│  (Static Card Database - 4000+ cards)                      │
│                                                             │
│  • standard_cards.json - Card definitions from PTCG API    │
│  • create_card() - Factory pattern                         │
│  • Immutable card templates                                │
└─────────────────────────────────────────────────────────────┘
```

---

## Core Design Principles

### 1. **The Constitution Philosophy**
The game rules are treated as a "Constitution" - an immutable set of laws that the engine enforces. The engine never guesses or makes assumptions; it only validates and executes based on the Constitution.

**Key Rules:**
- **Section 2**: Turn Structure & Phase constraints
- **Section 3**: Once-per-turn/game flags
- **Section 4**: Board state limits (bench size, hand size)
- **Section 5**: Status conditions
- **Section 6**: "Can't" priority rules (restrictions override permissions)

### 2. **Immutable State Snapshots**
Every `GameState` is a complete, immutable snapshot. State transitions create new states rather than mutating existing ones. This enables:
- **Cheap MCTS rollouts**: Clone state, simulate, discard
- **Time travel debugging**: Save/load any game state
- **Deterministic replays**: Reproduce exact game sequences

### 3. **Atomic Actions**
Actions are fully resolved units that contain all necessary information:

```python
Action(
    action_type=ActionType.PLAY_ITEM,
    player_id=0,
    card_id="nest_ball_instance_42",
    parameters={'target_pokemon_id': 'pidgey_instance_7'},
    display_label="Nest Ball (Search Pidgey)"
)
```

**Benefits:**
- AI agents make complete decisions upfront
- No mid-action user prompts
- Actions are self-documenting (display_label)
- Perfect for MCTS tree search

### 4. **Separation of Concerns**

```
Engine   → Enforces rules, generates legal actions
Cards    → Implement card-specific effects
Agents   → Make decisions (human, AI, random)
Models   → Store immutable state
Actions  → Reusable game mechanics (shuffle, draw, evolve)
```

Each layer has a single responsibility and communicates through well-defined interfaces.

---

## System Layers

### 1. **Engine Layer** (`engine.py`)

The **"Referee"** - enforces the Constitution and manages state transitions.

**Key Responsibilities:**
- `get_legal_actions(state)` → Generate all valid moves for MCTS
- `step(state, action)` → Apply action and return new state
- `resolve_phase_transition(state)` → Auto-advance turn structure
- `_get_interrupt_actions(state)` → Handle forced choices (e.g., KO promotion)

**Phase Management:**
```python
SETUP → MULLIGAN → MAIN → CLEANUP → [next player's turn]
```

**Critical for AI:**
- Legal action generation must be complete (no hidden moves)
- State transitions must be deterministic
- Interrupts must be handled elegantly

### 2. **Card Logic Layer**

#### **2a. Logic Registry** (`cards/logic_registry.py`)
Pure routing layer that maps card IDs to implementation functions using the **Unified Ability Schema**.

**Unified Schema Structure:**
Every attack and ability is registered under its **exact name** with a `category` field:

```python
{
    "sv8pt5-77": {  # Hoothoot
        "Tackle": {
            "category": "attack",
            "generator": hoothoot_tackle_actions,
            "effect": hoothoot_tackle_effect,
        },
        "Insomnia": {
            "category": "guard",
            "guard_type": "status_condition",
            "scope": "self",
            "effect": hoothoot_insomnia_guard,
        },
    },
    "me1-125": {  # Rare Candy (Trainer)
        "Play Rare Candy": {
            "category": "activatable",
            "generator": rare_candy_actions,
            "effect": rare_candy_effect,
        },
    },
}
```

**Categories (The 5 Pillars):**
| Category | Description | Examples |
|----------|-------------|----------|
| `attack` | Damage-dealing moves with energy cost | Tackle, Burning Darkness |
| `activatable` | Player-triggered abilities/actions | Trainer cards, activated abilities |
| `modifier` | Continuously modifies values | Agile (retreat cost), damage buffs |
| `guard` | Blocks effects/conditions | Insomnia (blocks Sleep), Flare Veil |
| `hook` | Event-triggered effects | Infernal Reign (on_evolve) |

**Multi-Effect Abilities:**
When an ability has multiple effects, use suffixed entries:
```python
"me2-41": {  # Glaceon with Diamond Coat
    "Diamond Coat (Damage Reduction)": {
        "category": "modifier",
        "modifier_type": "damage_taken",
        "scope": "self",
        "effect": damage_modifier_fn,
    },
    "Diamond Coat (Status Immunity)": {
        "category": "guard",
        "guard_type": "status_condition",
        "scope": "self",
        "effect": status_guard_fn,
    },
}
```

**Query Functions:**
```python
# Primary (Unified Schema)
get_ability_info(card_id, ability_name) -> dict  # Full ability info with category
get_all_effects_for_ability(card_id, ability_name) -> list  # Multi-effect support

# Helpers
get_card_logic(card_id, logic_type) -> Callable  # Generator/effect lookup
get_card_modifier(card_id, modifier_type) -> Callable
get_card_guard(card_id, guard_type) -> Callable
get_card_hooks(card_id, hook_type) -> Callable

# Board Scanning (Global Effects)
scan_global_modifiers(state, modifier_type) -> List[(card, fn)]
scan_global_guards(state, guard_type, context) -> List[(card, fn, blocking)]
check_global_block(state, guard_type, context) -> bool
```

#### **2b. Card Library** (`cards/library/`)
Reusable card logic implementations.

**trainers.py** - Shared trainer effects:
- Nest Ball, Ultra Ball, Buddy-Buddy Poffin
- Rare Candy, Iono
- Atomic action generation patterns

#### **2c. Set Modules** (`cards/sets/`)
Set-specific card implementations organized by set (sv1.py, sv2.py, sv3.py, etc.)

**Available Sets:**
- `sv1` - Scarlet & Violet Base
- `sv2` - Paldea Evolved
- `sv3` - Obsidian Flames
- `sv3pt5` - 151
- `sv4` - Paradox Rift
- `sv4pt5` - Paldean Fates
- `sv5` - Temporal Forces
- `sv6` - Twilight Masquerade
- `sv6pt5` - Shrouded Fable
- `sv7` - Stellar Crown
- `sv8` - Surging Sparks
- `sv8pt5` - Prismatic Evolutions
- `sv10` - Astral Radiance
- `me1` - Mega Evolution A
- `me2` - Phantasmal Flames
- `svp` - Promo Cards

Each module exports a `{SET}_LOGIC` dictionary using the unified schema:
```python
SV8PT5_LOGIC = {
    "sv8pt5-77": {  # Hoothoot
        "Tackle": {
            "category": "attack",
            "generator": hoothoot_tackle_actions,
            "effect": hoothoot_tackle_effect,
        },
        "Insomnia": {
            "category": "guard",
            "guard_type": "status_condition",
            "scope": "self",
            "effect": hoothoot_insomnia_guard,
        },
    },
}
```

### 3. **Knowledge Layer**

Supports **ISMCTS** (Information Set Monte Carlo Tree Search) by tracking what each player knows about hidden information.

**Key Fields (PlayerState):**
```python
class PlayerState:
    initial_deck_counts: Dict[str, int]  # "Pidgey": 4, "Nest Ball": 2
    has_searched_deck: bool               # Perfect vs imperfect knowledge
```

**Belief Engine:**
```python
def get_deck_search_candidates(state, player, criteria):
    """
    Returns what cards the player BELIEVES could be in their deck.

    If has_searched_deck=True:
        Return actual deck contents (perfect knowledge)
    Else:
        Calculate: initial_counts - visible_cards (belief-based)
    """
```

**Usage Example:**
```python
# AI plays Nest Ball without having searched deck
# Belief Engine calculates: "I started with 4 Pidgey, I've seen 1,
# so 3 could still be in my deck"
candidates = get_deck_search_candidates(state, player, is_basic)
# Returns: ["Pidgey", "Charmander"] (even if actual deck differs)
```

### 4. **Data Layer** (`models.py`)

Pydantic-based immutable state models.

**Core Models:**

#### **GameState** - Complete game snapshot
```python
class GameState:
    players: List[PlayerState]
    turn_count: int
    active_player_index: int
    current_phase: GamePhase
    active_effects: List[ActiveEffect]  # Global buffs/debuffs
    stadium_card: Optional[CardInstance]
```

#### **PlayerState** - Player-specific state
```python
class PlayerState:
    player_id: int
    hand: Hand
    deck: Deck
    discard: Discard
    prizes: Prizes
    board: Board

    # Game flags (Constitution Section 3)
    has_played_energy_this_turn: bool
    has_played_supporter_this_turn: bool
    has_attacked_this_turn: bool
    has_retreated_this_turn: bool

    # Knowledge Layer
    initial_deck_counts: Dict[str, int]
    has_searched_deck: bool
```

#### **CardInstance** - Runtime card state
```python
class CardInstance:
    id: str              # Unique instance ID
    card_id: str         # Template ID (e.g., "sv3-125")
    owner_id: int

    # Pokémon-specific state
    damage_counters: int
    attached_energy: List[CardInstance]
    attached_tools: List[CardInstance]
    status_conditions: List[StatusCondition]
    turns_in_play: int   # For evolution sickness
```

#### **Action** - Player decision
```python
class Action:
    action_type: ActionType
    player_id: int
    card_id: str         # Card being played/used
    target_id: Optional[str]
    parameters: Dict     # Atomic action data
    display_label: Optional[str]  # Human-readable description
    metadata: Dict       # Additional context
```

### 5. **Agent Layer** (`agents/`)

AI and human player implementations.

**Base Interface:**
```python
class PlayerAgent:
    def choose_action(self, state: GameState, legal_actions: List[Action]) -> Action:
        """Given state and legal actions, return chosen action."""
```

**Implementations:**
- `HumanAgent` - Interactive console player with formatted display
- `RandomAgent` - Uniform random baseline
- `MCTSAgent` - (Future) Tree search implementation

### 6. **Actions Layer** (`actions.py`)

Reusable game mechanics (not card-specific).

**Common Actions:**
```python
shuffle_deck(state, player_id) -> GameState
draw_card(state, player_id) -> GameState
evolve_pokemon(state, player_id, target_id, evolution_id) -> GameState
apply_damage(pokemon, amount) -> CardInstance
check_knockout(state, pokemon) -> bool
```

These are building blocks used by card effects.

---

## Key Subsystems

### **Atomic Action System**

Traditional card games require multi-step user interaction:
```
1. User: "I play Nest Ball"
2. Engine: "Which Pokémon do you want?"
3. User: "Pidgey"
4. Engine: Executes search
```

**Problem for MCTS:** Tree search requires knowing all possible futures upfront.

**Solution - Atomic Actions:**
```python
# Engine generates ALL possible Nest Ball plays:
[
    Action(PLAY_ITEM, card_id=nest_ball, params={'target': 'pidgey_1'}),
    Action(PLAY_ITEM, card_id=nest_ball, params={'target': 'pidgey_2'}),
    Action(PLAY_ITEM, card_id=nest_ball, params={'target': 'charmander_1'}),
]

# AI chooses ONE complete action
# Execution is deterministic - no mid-action choices
```

**Implementation Pattern:**

1. **Action Generator** (at action generation time):
```python
def nest_ball_actions(state, card, player) -> List[Action]:
    """Generate ALL valid Nest Ball plays."""
    candidates = get_deck_search_candidates(state, player, is_basic)

    actions = []
    for card_name in candidates:
        target = find_card_in_deck(player.deck, card_name)
        actions.append(Action(
            action_type=ActionType.PLAY_ITEM,
            card_id=card.id,
            parameters={'target_pokemon_id': target.id},
            display_label=f"Nest Ball (Search {card_name})"
        ))
    return actions
```

2. **Effect Executor** (at execution time):
```python
def nest_ball_effect(state, card, action) -> GameState:
    """Execute the SPECIFIC choice made during action generation."""
    target_id = action.parameters['target_pokemon_id']
    target = player.deck.get_card(target_id)  # Specific card

    player.deck.remove_card(target_id)
    player.board.add_to_bench(target)
    state = shuffle_deck(state, player.player_id)
    return state
```

**Benefits:**
- Complete decision trees for MCTS
- No user prompts during execution
- Self-documenting actions (display_label)
- Deterministic replay

### **Knowledge Layer (ISMCTS Support)**

Real Pokémon involves hidden information (opponent's hand, prize cards, deck contents). ISMCTS requires tracking what each player knows.

**Perfect Knowledge Scenario:**
```python
# Player plays "Arven" (searches deck, reveals hand)
player.has_searched_deck = True

# Now AI knows EXACTLY what's in deck
candidates = get_deck_search_candidates(state, player, is_basic)
# Returns: Actual deck contents
```

**Imperfect Knowledge Scenario:**
```python
# Player hasn't searched deck yet
player.has_searched_deck = False
player.initial_deck_counts = {"Pidgey": 4, "Charmander": 2}

# AI must INFER what COULD be in deck
# Calculation: initial_counts - visible_cards
# "I started with 4 Pidgey, I've seen 1 in hand,
#  so 3 COULD still be in deck"

candidates = get_deck_search_candidates(state, player, is_basic)
# Returns: ["Pidgey", "Charmander"] (belief-based)
```

**Key Insight:** The AI doesn't cheat. It uses the same information a human player would have.

### **Phase System**

Game progresses through well-defined phases:

```
SETUP
  ↓
MULLIGAN (if no Basic Pokémon in hand)
  ↓
MAIN PHASE
  • Play Basic Pokémon
  • Evolve Pokémon (once per turn per Pokémon)
  • Attach Energy (once per turn)
  • Play Trainer cards
  • Use Abilities
  • Retreat (once per turn)
  • Attack (ends turn)
  ↓
CLEANUP
  • Remove expired effects
  • Check knockouts
  • Auto-advance to next player's turn
```

**Implementation:**
```python
def get_legal_actions(state):
    if state.current_phase == GamePhase.SETUP:
        return setup_actions()
    elif state.current_phase == GamePhase.MAIN:
        return main_phase_actions()
    # ... etc
```

---

## Data Flow

### **Typical Game Loop**

```python
# 1. Game Setup
state = quick_setup(deck1_text, deck2_text, seed=42)

# 2. Game Loop
while not state.is_game_over():
    # 3. Get legal actions
    actions = engine.get_legal_actions(state)

    # 4. Agent chooses action
    agent = get_current_agent(state.active_player_index)
    action = agent.choose_action(state, actions)

    # 5. Apply action (state transition)
    state = engine.step(state, action)

    # 6. Auto-resolve phase transitions
    state = engine.resolve_phase_transition(state)

# 7. Check winner
result = state.check_win_condition()
print(f"Winner: Player {result.winner_id}")
```

### **Action Execution Flow**

```
1. Engine.get_legal_actions(state)
   ↓
2. For each card in hand:
   Check logic_registry for custom generator
   ↓
3. nest_ball_actions(state, card, player)
   → Uses Knowledge Layer to get candidates
   → Generates Action objects with specific targets
   ↓
4. Returns: List[Action] to agent
   ↓
5. Agent.choose_action(state, actions)
   → AI algorithm (MCTS, RL, etc.) chooses ONE action
   ↓
6. Engine.step(state, chosen_action)
   → Looks up nest_ball_effect in logic_registry
   → Executes effect with SPECIFIC parameters
   ↓
7. New GameState returned
```

### **State Immutability Pattern**

```python
# ❌ WRONG - Mutation
def bad_draw_card(state):
    card = state.players[0].deck.cards.pop()
    state.players[0].hand.cards.append(card)  # Mutates state!

# ✅ CORRECT - Copy-on-write
def draw_card(state, player_id):
    state = deepcopy(state)  # Clone entire state
    player = state.get_player(player_id)

    card = player.deck.cards.pop()
    player.hand.add_card(card)

    return state  # Return NEW state
```

**Why?** MCTS needs to simulate thousands of futures without affecting the current game state.

---

## Getting Started

### Installation

```bash
# Clone repository
git clone <repository-url>
cd pokemon-ai

# Install dependencies
pip install -r requirements.txt
```

### Quick Start - Console Game

```bash
python src/play_console.py
```

This launches an interactive game with human vs random bot.

### Quick Start - Programmatic

```python
from game_setup import quick_setup
from engine import PokemonEngine
from agents import HumanAgent, RandomAgent

# Load decks
deck1 = open("decks/charizard.txt").read()
deck2 = open("decks/pikachu.txt").read()

# Setup game
state = quick_setup(deck1, deck2, seed=42)
engine = PokemonEngine()

# Create agents
agents = [HumanAgent("Alice"), RandomAgent("Bob")]

# Game loop
while not state.is_game_over():
    actions = engine.get_legal_actions(state)
    agent = agents[state.active_player_index]
    action = agent.choose_action(state, actions)
    state = engine.step(state, action)

print(f"Winner: {state.check_win_condition().winner_id}")
```

### Implementing a Custom Card

#### Example 1: Trainer Card (Activatable)

```python
# 1. Create effect function (in cards/library/trainers.py or set module)
def my_trainer_effect(state: GameState, card: CardInstance, action: Action) -> GameState:
    """Execute trainer card effect."""
    player = state.get_player(action.player_id)
    state = draw_card(state, player.player_id)
    return state

# 2. Create action generator
def my_trainer_actions(state: GameState, card: CardInstance, player: PlayerState) -> List[Action]:
    """Generate valid actions for this trainer."""
    return [Action(
        action_type=ActionType.PLAY_ITEM,
        player_id=player.player_id,
        card_id=card.id,
        display_label="Play My Trainer"
    )]

# 3. Register in set module using unified schema
SV1_LOGIC = {
    "sv1-123": {
        "Play My Trainer": {
            "category": "activatable",
            "generator": my_trainer_actions,
            "effect": my_trainer_effect,
        },
    },
}
```

#### Example 2: Pokémon with Attack + Ability

```python
# Attack: Tackle [CC] - 30 damage
def my_pokemon_tackle_actions(state, card, player):
    return [Action(
        action_type=ActionType.ATTACK,
        player_id=player.player_id,
        card_id=card.id,
        attack_name="Tackle",
        display_label="Tackle - 30 Dmg"
    )]

def my_pokemon_tackle_effect(state, card, action):
    opponent = state.get_opponent()
    if opponent.board.active_spot:
        final_damage = calculate_damage(state, card, opponent.board.active_spot, 30, "Tackle")
        state = apply_damage(state, opponent.board.active_spot, final_damage, True, card)
    return state

# Guard: Immunity - Can't be Poisoned
def my_pokemon_immunity_guard(state, card, condition):
    return condition == StatusCondition.POISONED

# Register with unified schema
SV1_LOGIC = {
    "sv1-456": {
        "Tackle": {
            "category": "attack",
            "generator": my_pokemon_tackle_actions,
            "effect": my_pokemon_tackle_effect,
        },
        "Immunity": {
            "category": "guard",
            "guard_type": "status_condition",
            "scope": "self",
            "effect": my_pokemon_immunity_guard,
        },
    },
}
```

#### Example 3: Hook (Event-Triggered Ability)

```python
# Ability: Infernal Reign - When this Pokémon evolves, search deck for 3 Fire Energy
def infernal_reign_hook(state, card, context):
    """Triggered when this Pokémon evolves."""
    player = state.get_player(card.owner_id)
    # Search and attach logic...
    return state

# Register
SVP_LOGIC = {
    "svp-56": {
        "Infernal Reign": {
            "category": "hook",
            "trigger": "on_evolve",
            "effect": infernal_reign_hook,
        },
    },
}
```

#### Example 4: Modifier (Passive Value Change)

```python
# Ability: Agile - If no Energy attached, retreat cost is 0
def agile_modifier(state, card, current_cost):
    if not card.attached_energy:
        return 0
    return current_cost

# Register
ME2_LOGIC = {
    "me2-11": {
        "Agile": {
            "category": "modifier",
            "modifier_type": "retreat_cost",
            "scope": "self",
            "effect": agile_modifier,
        },
    },
}
```

---

## Testing

### Run All Tests
```bash
# Run all tests with pytest
python -m pytest tests/ -q

# Run specific test file
python -m pytest tests/test_pokemon_attacks.py -v

# Run with coverage
python -m pytest tests/ --cov=src
```

### Test Structure

```
tests/
├── test_knowledge_layer.py           # ISMCTS belief engine
├── test_atomic_integration.py        # Atomic action system
├── test_pokemon_attacks.py           # Attack implementations
├── test_pokemon_generators.py        # Card logic framework
├── test_engine_invariants.py         # Engine rule verification
├── test_status_conditions.py         # Status condition mechanics
├── test_retreat_mechanics.py         # Retreat cost & modifiers
├── test_stack_mechanics.py           # Damage calculation stack
├── test_nest_ball_comprehensive.py   # Nest Ball edge cases
├── test_ultra_ball_comprehensive.py  # Ultra Ball edge cases
├── test_rare_candy_comprehensive.py  # Rare Candy evolution
└── fixtures/                         # Test decks and states
```

### Writing Tests

```python
def test_nest_ball_atomic_actions():
    """Test that Nest Ball generates specific atomic actions."""
    engine = PokemonEngine()

    # Setup state
    player = PlayerState(player_id=0)
    player.deck.add_card(create_card_instance("sv3pt5-16"))  # Pidgey
    player.hand.add_card(create_card_instance("sv1-181"))     # Nest Ball

    state = GameState(players=[player, opponent], ...)
    state = engine.initialize_deck_knowledge(state)

    # Generate actions
    actions = engine.get_legal_actions(state)
    nest_ball_actions = [a for a in actions if "Nest Ball" in a.display_label]

    # Verify atomic actions generated
    assert len(nest_ball_actions) == 1
    assert "Pidgey" in nest_ball_actions[0].display_label
    assert nest_ball_actions[0].parameters['target_pokemon_id'] is not None
```

---

## Project Status

### Implemented Features
✅ Core engine with phase management
✅ Immutable state snapshots (MCTS-ready)
✅ Atomic action system
✅ Knowledge Layer (ISMCTS support)
✅ Card registry (4000+ cards from PTCG API)
✅ **Unified Ability Schema** (5 Pillars: attack, activatable, modifier, guard, hook)
✅ 16 set modules (sv1-sv10, svp, me1-me2)
✅ Trainer cards (Nest Ball, Ultra Ball, Rare Candy, Iono, Buddy-Buddy Poffin)
✅ Attack damage calculation with weakness/resistance
✅ Status conditions (Poisoned, Burned, Asleep, Confused, Paralyzed)
✅ Guard abilities (Insomnia, Flare Veil)
✅ Modifier abilities (Agile - retreat cost reduction)
✅ Hook abilities (Infernal Reign - on_evolve trigger)
✅ Human agent (console UI)
✅ Random agent (baseline)
✅ 1600+ tests passing

### In Progress
🚧 More Pokémon implementations
🚧 Stadium cards
🚧 Tool cards
🚧 Special Energy cards

### Planned Features
📋 MCTS agent implementation
📋 Reinforcement learning integration
📋 Web UI
📋 Network play
📋 Deck builder
📋 Tournament mode

---

## Contributing

Contributions welcome! Key areas:
- **Card Implementations**: Add more trainer/Pokémon cards
- **AI Agents**: Implement MCTS, RL, or heuristic agents
- **Testing**: Add integration tests for complex scenarios
- **Documentation**: Improve architecture docs

---

## License

MIT License - See `LICENSE` file for details.

---

## Architecture Design Credits

This engine's architecture is inspired by:
- **AlphaGo/AlphaZero** - MCTS with neural networks
- **ISMCTS** - Imperfect information tree search
- **Functional programming** - Immutable state, pure functions
- **Domain-driven design** - Separation of concerns, ubiquitous language

Built for AI research with ❤️ by the Pokémon AI community.

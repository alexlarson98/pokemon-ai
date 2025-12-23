# Pokemon TCG Engine - C++ Architecture

## Design Principles

### 1. Performance First
- **Target**: 20-50x speedup over Python for MCTS simulations
- **Key Optimizations**:
  - Value semantics with move operations (no shared_ptr overhead)
  - Bit flags for status conditions (O(1) operations)
  - Pre-reserved vectors to minimize allocations
  - COW (Copy-On-Write) strings from standard library
  - Inline cloning methods to enable compiler optimization

### 2. Memory Layout
- **Struct of Arrays (SoA)** where appropriate for cache efficiency
- **Data locality**: CardInstance keeps all mutable state together
- **No virtual dispatch** in hot paths (action generation/application)

### 3. API Compatibility
- Mirror Python API for seamless pybind11 integration
- Same method signatures: `get_legal_actions()`, `step()`, `step_inplace()`
- Same data structures: GameState, PlayerState, Action

### 4. Extensibility
- **Logic Registry Pattern**: Card effects as named functions, not virtual methods
- **Composition over Inheritance**: CardDef is data, not behavior
- **Plugin Architecture**: New cards added via JSON + logic functions

## File Structure

```
cpp_engine/
├── include/                 # Public headers
│   ├── pokemon_engine.hpp   # Main include (umbrella header)
│   ├── types.hpp           # Enums and type aliases
│   ├── card_instance.hpp   # Mutable card state
│   ├── zone.hpp            # Card containers
│   ├── board.hpp           # Active + Bench
│   ├── player_state.hpp    # Complete player state
│   ├── action.hpp          # Action representation
│   ├── resolution_step.hpp # Multi-step action state machine
│   ├── game_state.hpp      # Root state object
│   ├── card_database.hpp   # Immutable card definitions
│   └── engine.hpp          # Main engine interface
├── src/                    # Implementation
│   ├── engine.cpp          # Core engine logic
│   ├── card_database.cpp   # JSON loading
│   └── logic_registry.cpp  # Card effect functions
├── bindings/               # Python bindings
│   └── pybind_module.cpp   # pybind11 wrapper
└── CMakeLists.txt          # Build configuration
```

## Key Design Decisions

### 1. Value Semantics for State
**Why**: MCTS requires cloning states millions of times. Pointer-based structures with reference counting add overhead.

**Implementation**:
```cpp
// Every structure has a clone() method that does deep copy
GameState clone() const {
    GameState copy;
    copy.players[0] = players[0].clone();
    // ...
    return copy;
}
```

### 2. Status Conditions as Bit Flags
**Why**: Checking/modifying status is O(1) with bit operations vs O(n) with set lookup.

**Implementation**:
```cpp
uint8_t status_flags = 0;
static constexpr uint8_t STATUS_POISONED  = 1 << 0;
// ...

bool is_asleep_or_paralyzed() const {
    return (status_flags & (STATUS_ASLEEP | STATUS_PARALYZED)) != 0;
}
```

### 3. Separate CardDef (Immutable) from CardInstance (Mutable)
**Why**: Card definitions are shared across all instances. Only runtime state (damage, attached cards) changes.

**Implementation**:
- `CardDef`: Loaded from JSON, stored in `CardDatabase`, never modified
- `CardInstance`: Created per card in game, cloned with state

### 4. Resolution Stack for Multi-Step Actions
**Why**: Reduces branching factor for MCTS by breaking complex actions into sequential choices.

**Before** (atomic actions):
```
Ultra Ball action = Select 2 cards to discard (C(hand_size, 2)) × Select 1 from deck (deck_size)
= ~45 × 40 = 1800 combinations
```

**After** (resolution stack):
```
Step 1: Play Ultra Ball (1 action)
Step 2: Select card 1 (hand_size actions)
Step 3: Select card 2 (hand_size-1 actions)
Step 4: Select from deck (deck_size actions)
Total = 1 + ~7 + ~6 + ~40 = 54 sequential actions
```

### 5. Logic Registry Pattern for Card Effects
**Why**: Adding new cards shouldn't require modifying engine code.

**Implementation**:
```cpp
// Card effects registered by name
std::unordered_map<std::string, EffectFunction> attack_effects;
std::unordered_map<std::string, EffectFunction> ability_effects;
std::unordered_map<std::string, EffectFunction> trainer_effects;

// Card definition references function by name
AttackDef {
    .name = "Burning Darkness",
    .effect_function = "charizard_ex_burning_darkness"
};

// Engine looks up and calls
auto effect = logic_registry.get_attack_effect("charizard_ex_burning_darkness");
if (effect) effect(state, attacker, defender);
```

## Future Considerations

### 1. Parallel MCTS
- GameState is copyable, enabling parallel tree search
- Engine methods are const (read-only), thread-safe for action generation
- RNG should be per-thread for reproducibility

### 2. Neural Network Integration
- State encoding can be done in C++ for speed
- Batch multiple states for GPU inference
- Return raw pointers/views to Python for zero-copy tensor creation

### 3. Belief-Based MCTS (ISMCTS)
- `initial_deck_counts` and `functional_id_map` support imperfect information
- `has_searched_deck` tracks when player gains perfect knowledge
- Action generation handles both perfect and belief-based modes

### 4. Card Logic Hot-Loading
- Logic registry can be extended at runtime
- Python callbacks for prototyping new cards
- C++ implementations for performance-critical cards

## Performance Benchmarks (Expected)

| Operation | Python | C++ | Speedup |
|-----------|--------|-----|---------|
| GameState clone | ~50ms | <1ms | 50x |
| get_legal_actions | ~100ms | <5ms | 20x |
| step (single action) | ~20ms | <1ms | 20x |
| Full MCTS search (100 sims) | ~10s | <500ms | 20x |

## API Reference

### PokemonEngine

```cpp
class PokemonEngine {
public:
    // Core MCTS API
    std::vector<Action> get_legal_actions(const GameState& state) const;
    GameState step(const GameState& state, const Action& action) const;
    void step_inplace(GameState& state, const Action& action) const;

    // Game setup
    GameState create_game(const std::vector<CardDefID>& deck1,
                         const std::vector<CardDefID>& deck2) const;
    GameState setup_initial_board(GameState state) const;

    // Card database
    const CardDatabase& get_card_database() const;
};
```

### GameState

```cpp
struct GameState {
    // Core state
    std::array<PlayerState, 2> players;
    int turn_count;
    PlayerID active_player_index;
    GamePhase current_phase;
    GameResult result;

    // Helpers
    PlayerState& get_active_player();
    PlayerState& get_opponent();
    bool is_game_over() const;
    GameState clone() const;
};
```

### Action

```cpp
struct Action {
    ActionType action_type;
    PlayerID player_id;
    std::optional<CardID> card_id;
    std::optional<CardID> target_id;
    std::optional<std::string> attack_name;
    // ...

    // Factory methods
    static Action end_turn(PlayerID player);
    static Action attack(PlayerID player, const CardID& card, const std::string& attack);
    // ...
};
```

## Migration from Python

1. **Phase 1**: Core engine in C++, Python bindings for AI code
   - Python AI code calls C++ engine via pybind11
   - Gradual migration, no breaking changes

2. **Phase 2**: State encoding in C++
   - Move `StateEncoder` to C++ for faster tensor creation
   - Python receives numpy arrays directly

3. **Phase 3**: Full C++ training pipeline
   - MCTS in C++
   - Only neural network training in Python (PyTorch)

# C++ Engine Implementation: Iono

## Card Data
**Card IDs:** `svp-124, sv2-185, sv2-254, sv2-269, sv4pt5-80, sv4pt5-237`
**Type:** Trainer (Supporter)

### Card Text
> Each player shuffles their hand and puts it on the bottom of their deck. If either player put any cards on the bottom of their deck in this way, each player draws a card for each of their remaining Prize cards.
> You may play only 1 Supporter card during your turn.

## C++ Engine Architecture

### Key Files
- `cpp_engine/src/cards/trainers/items/{name}.cpp` - Item implementations
- `cpp_engine/src/cards/trainers/supporters/{name}.cpp` - Supporter implementations
- `cpp_engine/src/cards/trainer_registry.cpp` - Registration calls
- `cpp_engine/include/cards/effect_builders.hpp` - Effect primitives
- `cpp_engine/docs/CARD_INTEGRATION.md` - Full documentation

### Trainer Execution Lifecycle
Understanding the full flow is critical for correct implementation:

1. **Legal Action Generation** (`get_trainer_actions()`)
   - Engine finds Item/Supporter cards in hand
   - Calls `generator` callback to check if card can be played
   - If `generator.valid == true`, adds PLAY_TRAINER action to legal actions

2. **Effect Execution** (`process_action()` -> `execute_trainer()`)
   - Player selects PLAY_TRAINER action
   - Engine calls `handler` callback
   - Handler returns `TrainerResult` with success/requires_resolution flags

3. **Resolution Stack** (if `requires_resolution == true`)
   - Effect builders push `SearchDeckStep`, `SelectFromZoneStep`, etc. onto stack
   - Engine enters resolution mode, generates selection actions
   - Player makes selections -> step completes -> callback fires
   - Stack empties -> back to normal play

4. **Trainer Card Discarded** (automatic)
   - After handler returns, engine moves trainer to discard pile
   - You do NOT need to handle this - the engine does it

### Effect Builders Available
```cpp
namespace effects {
    // Search deck for cards
    EffectResult search_deck(state, source_card, player_id, filter,
        count=1, min_count=0, destination=HAND, shuffle_after=true, on_complete=nullptr);

    // Search deck directly to bench (for Nest Ball, Poffin)
    EffectResult search_deck_to_bench(state, source_card, player_id, filter,
        count=1, min_count=0, on_complete=nullptr);

    // Discard cards then do something (Ultra Ball)
    EffectResult discard_then(state, source_card, player_id, discard_count, filter, then_effect);

    // Draw cards
    EffectResult draw_cards(state, player_id, count);

    // Discard hand and draw (Professor's Research)
    EffectResult discard_hand_draw(state, player_id, draw_count);

    // Recover from discard to hand
    EffectResult recover_from_discard(state, source_card, player_id, filter, count, min_count=0);

    // Shuffle discard into deck - TWO VERSIONS:
    // 1. String-based filter (simple patterns)
    EffectResult shuffle_discard_to_deck(state, source_card, player_id, filter, count, min_count=0);
    // 2. Predicate-based filter (complex OR logic) - PREFERRED for compound filters
    EffectResult shuffle_discard_to_deck(state, source_card, player_id, filter_fn, count, min_count=0);

    // Switch active Pokemon
    EffectResult switch_active(state, source_card, player_id, opponent_also=false);

    // Heal damage
    EffectResult heal_damage(state, source_card, player_id, target_id, amount);

    // Validation helpers
    bool has_bench_space(state, player_id);
    bool can_discard_from_hand(state, player_id, count, filter={});
    int count_matching_cards(state, db, player_id, zone, filter);
}
```

### Filter Builder (Simple Patterns)
For simple AND filters, use FilterBuilder:
```cpp
auto filter = effects::FilterBuilder()
    .supertype("Pokemon")      // "Pokemon", "Trainer", "Energy"
    .subtype("Basic")          // "Basic", "Stage 1", "Stage 2", "Item", etc.
    .pokemon_type(EnergyType::FIGHTING)  // For type-specific searches
    .max_hp(70)                // For Buddy-Buddy Poffin
    .name("Pikachu")           // Specific card search
    .evolves_from("Charmander") // Evolution search
    .is_basic_energy()         // Basic Energy cards only
    .is_supporter()            // Supporter trainers (for Pal Pad)
    .pokemon_or_basic_energy() // Pokemon OR basic Energy (Super Rod shortcut)
    .build();
```

### Predicate Filters (Complex Patterns - PREFERRED)
For complex filter logic (especially OR conditions), use lambda predicates:
```cpp
#include "card_database.hpp"  // For CardDef

// Example: Super Rod - Pokemon OR basic Energy
auto effect_result = effects::shuffle_discard_to_deck(
    state, card, player_id,
    [](const CardDef& def) {
        return def.is_pokemon() || (def.is_energy() && def.is_basic_energy);
    },
    3,  // count
    0   // min_count
);

// Example: Night Stretcher - Pokemon only (could also use FilterBuilder)
auto effect_result = effects::shuffle_discard_to_deck(
    state, card, player_id,
    [](const CardDef& def) { return def.is_pokemon(); },
    1, 0
);
```

**When to use predicates vs FilterBuilder:**
- **FilterBuilder**: Simple AND patterns (Basic Pokemon, Pokemon with ≤70 HP, etc.)
- **Predicate**: Complex OR patterns, compound conditions, or any logic that FilterBuilder can't express

The predicate approach keeps filter logic with the card implementation rather than adding
card-specific keys to the engine, making the codebase more maintainable.

### Callbacks vs Default Behavior
**Use default behavior (no callback)** when:
- `search_deck_to_bench`: Selected cards go to bench, deck shuffles (default)
- `search_deck` with `destination=HAND`: Cards go to hand, deck shuffles (default)

**Provide a callback** when:
- Selected cards need special handling (attach to Pokemon, evolve, etc.)
- Additional steps must be pushed after selection
- Side effects occur (damage counters, status conditions, etc.)

### Search Semantics: Hidden vs Public Zones

**Deck (hidden zone)** - "Fail to find" is ALWAYS allowed:
- `min_count=0` lets player choose 0 cards even if valid targets exist
- This is intentional - opponent can't verify deck contents
- Player may strategically choose not to find anything

**Discard pile / Hand (public zones)** - NO fail to find:
- Both players can see these zones
- If valid targets exist, player MUST select them
- Use `min_count` equal to available targets or required count
- Generator should check `count_matching_cards()` for playability

Example - Energy Retrieval (recover 2 basic energy from discard):
```cpp
// Generator must verify discard has basic energy
auto generator = [](const GameState& state, const CardInstance& card) -> GeneratorResult {
    GeneratorResult result;
    auto filter = effects::FilterBuilder().is_basic_energy().build();
    int available = effects::count_matching_cards(state, db, player_id, ZoneType::DISCARD, filter);
    result.valid = available > 0;  // Must have at least 1 target
    return result;
};
```

### Registration Pattern
Cards register:
1. **TrainerCallback** - Execute the effect
2. **GeneratorCallback** - Check if card can be played (for legal actions)

```cpp
void register_{card_name}(LogicRegistry& registry) {
    // Handler - executes the effect
    auto handler = [](GameState& state, const CardInstance& card) -> TrainerResult {
        // Implementation
    };

    // Generator - checks playability (CRITICAL: prevents invalid actions)
    auto generator = [](const GameState& state, const CardInstance& card) -> GeneratorResult {
        GeneratorResult result;
        result.valid = /* can play? */;
        result.reason = "Reason if invalid";
        return result;
    };

    registry.register_trainer("{card_id}", handler);
    registry.register_generator("{card_id}", "trainer", generator);
}
```

---

## Reference Implementation: Nest Ball

This is a complete working example. Use it as your template.

**CRITICAL: Card IDs must match your card!**
The card IDs shown below (sv1-181, etc.) are for Nest Ball specifically.
YOU MUST use the **Card IDs listed in the "Card Data" section above** for your implementation.
These IDs come from standard_cards.json and are unique to each card printing.

```cpp
/**
 * Nest Ball - Trainer Item
 * "Search your deck for a Basic Pokemon and put it onto your Bench. Then, shuffle your deck."
 */

#include "cards/trainer_registry.hpp"
#include "cards/effect_builders.hpp"

namespace pokemon {
namespace trainers {

namespace {

/**
 * Check if Nest Ball can be played.
 * Requirements:
 * - Player must have bench space
 * - (Note: Deck having Basic Pokemon is NOT required - can "fail to find")
 */
bool can_play_nest_ball(const GameState& state, PlayerID player_id) {
    return effects::has_bench_space(state, player_id);
}

/**
 * Execute Nest Ball effect.
 * Creates a SearchDeckStep with filter for Basic Pokemon.
 * The selected card goes directly to bench.
 */
TrainerResult execute_nest_ball(GameState& state, const CardInstance& card) {
    TrainerResult result;
    PlayerID player_id = state.active_player_index;

    if (!can_play_nest_ball(state, player_id)) {
        result.success = false;
        result.effect_description = "No bench space available";
        return result;
    }

    // Build filter: Basic Pokemon only
    auto filter = effects::FilterBuilder()
        .supertype("Pokemon")
        .subtype("Basic")
        .build();

    // Search deck, put on bench
    // min_count = 0 because search can fail to find
    auto effect_result = effects::search_deck_to_bench(
        state, card, player_id, filter,
        1,      // count: select up to 1
        0       // min_count: can choose to find nothing
    );

    result.success = effect_result.success;
    result.requires_resolution = effect_result.requires_resolution;
    result.effect_description = "Search deck for a Basic Pokemon to put on bench";

    return result;
}

} // anonymous namespace

void register_nest_ball(LogicRegistry& registry) {
    auto handler = [](GameState& state, const CardInstance& card) -> TrainerResult {
        return execute_nest_ball(state, card);
    };

    auto generator = [](const GameState& state, const CardInstance& card) -> GeneratorResult {
        GeneratorResult result;
        result.valid = can_play_nest_ball(state, state.active_player_index);
        if (!result.valid) {
            result.reason = "No bench space";
        }
        return result;
    };

    // IMPORTANT: These are Nest Ball's IDs - use YOUR card's IDs from the Card Data section!
    registry.register_trainer("sv1-181", handler);
    registry.register_generator("sv1-181", "trainer", generator);
    registry.register_trainer("sv1-255", handler);
    registry.register_generator("sv1-255", "trainer", generator);
    registry.register_trainer("sv4pt5-84", handler);
    registry.register_generator("sv4pt5-84", "trainer", generator);
}

} // namespace trainers
} // namespace pokemon
```

## Implementation Template

**Note:** The card IDs below (`svp-124, sv2-185, sv2-254, sv2-269, sv4pt5-80, sv4pt5-237`) are from standard_cards.json for THIS card.
Use these exact IDs in your registration - do NOT copy IDs from the Nest Ball example above!

### File: `cpp_engine/src/cards/trainers/supporters/iono.cpp`

```cpp
/**
 * Iono - Trainer Supporter
 *
 * Card text:
 * "Each player shuffles their hand and puts it on the bottom of their deck. If either player put any cards on the bottom of their deck in this way, each player draws a card for each of their remaining Prize cards."
 * "You may play only 1 Supporter card during your turn."
 *
 * Card IDs: svp-124, sv2-185, sv2-254, sv2-269, sv4pt5-80, sv4pt5-237
 */

#include "cards/trainer_registry.hpp"
#include "cards/effect_builders.hpp"

namespace pokemon {
namespace trainers {

namespace {

/**
 * Check if Iono can be played.
 */
bool can_play_iono(const GameState& state, PlayerID player_id) {
    // TODO: Add playability checks
    // Example: return effects::has_bench_space(state, player_id);
    return true;
}

/**
 * Execute Iono effect.
 */
TrainerResult execute_iono(GameState& state, const CardInstance& card) {
    TrainerResult result;
    PlayerID player_id = state.active_player_index;

    if (!can_play_iono(state, player_id)) {
        result.success = false;
        result.effect_description = "Cannot play Iono";
        return result;
    }

    // TODO: Build filter criteria
    auto filter = effects::FilterBuilder()
        // .supertype("Pokemon")
        // .subtype("Basic")
        // .max_hp(70)
        .build();

    // TODO: Use appropriate effect builder
    // auto effect_result = effects::search_deck_to_bench(
    //     state, card, player_id, filter, count, min_count);

    // result.success = effect_result.success;
    // result.requires_resolution = effect_result.requires_resolution;
    result.effect_description = "Iono effect";

    return result;
}

} // anonymous namespace

void register_iono(LogicRegistry& registry) {
    auto handler = [](GameState& state, const CardInstance& card) -> TrainerResult {
        return execute_iono(state, card);
    };

    auto generator = [](const GameState& state, const CardInstance& card) -> GeneratorResult {
        GeneratorResult result;
        result.valid = can_play_iono(state, state.active_player_index);
        if (!result.valid) {
            result.reason = "Cannot play Iono";
        }
        return result;
    };

    // Register for all printings
    registry.register_trainer("svp-124", handler);
    registry.register_generator("svp-124", "trainer", generator);
    registry.register_trainer("sv2-185", handler);
    registry.register_generator("sv2-185", "trainer", generator);
    registry.register_trainer("sv2-254", handler);
    registry.register_generator("sv2-254", "trainer", generator);
    registry.register_trainer("sv2-269", handler);
    registry.register_generator("sv2-269", "trainer", generator);
    registry.register_trainer("sv4pt5-80", handler);
    registry.register_generator("sv4pt5-80", "trainer", generator);
    registry.register_trainer("sv4pt5-237", handler);
    registry.register_generator("sv4pt5-237", "trainer", generator);
}

} // namespace trainers
} // namespace pokemon
```

### Add to `trainer_registry.cpp`

```cpp
#include "cards/trainers/supporters/iono.cpp"

void register_all_trainers(LogicRegistry& registry) {
    // ... existing registrations ...
    trainers::register_iono(registry);
}
```

## Implementation Checklist

### Core Implementation
- [ ] Implement `can_play_iono()` with proper validation
  - Check bench space if putting Pokemon on bench
  - Check discard cost if card requires discarding
  - Do NOT check if deck has targets (fail-to-find is legal)
- [ ] Implement `execute_iono()` using effect builders
  - Use appropriate `effects::` helper
  - Set correct count/min_count
  - Build correct filter criteria
- [ ] Register all card IDs: `svp-124, sv2-185, sv2-254, sv2-269, sv4pt5-80, sv4pt5-237`
- [ ] Add registration call to `trainer_registry.cpp`

### Testing
- [ ] Build: `cmake --build build --config Release`
- [ ] Run console: `build/Release/pokemon_console.exe`
- [ ] Verify card appears in legal actions when playable
- [ ] Verify card does NOT appear when conditions aren't met
- [ ] Test the resolution flow (make selections)
- [ ] Verify deck is shuffled after search (if applicable)
- [ ] Verify card goes to discard after playing

### Common Issues
- **Card always shows as playable**: Generator not registered or not checking conditions
- **Card never shows as playable**: Generator returning false incorrectly
- **Crash on play**: Handler not handling edge cases (empty deck, etc.)
- **Resolution stuck**: Effect builder not pushing steps correctly

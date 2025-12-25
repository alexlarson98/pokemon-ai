# C++ Engine Implementation: Ultra Ball

## Card Data
**Card IDs:** `sv1-196`
**Type:** Trainer (Item)

### Card Text
> You can use this card only if you discard 2 other cards from your hand. Search your deck for a Pokemon, reveal it, and put it into your hand. Then, shuffle your deck.
> You may play any number of Item cards during your turn.

### Detected Effect Patterns
- **Effect Builders:** `search_deck`
- shuffle_after=true (default)

**Card IDs:** `sv4pt5-91`
**Type:** Trainer (Item)

### Card Text
> You can use this card only if you discard 2 other cards from your hand.
> Search your deck for a Pokemon, reveal it, and put it into your hand. Then, shuffle your deck.
> You may play any number of Item cards during your turn.

### Detected Effect Patterns
- **Effect Builders:** `search_deck`
- shuffle_after=true (default)

**Card IDs:** `me1-131`
**Type:** Trainer (Item)

### Card Text
> You can use this card only if you discard 2 other cards from your hand.  Search your deck for a Pokemon, reveal it, and put it into your hand. Then, shuffle your deck.
> You may play any number of Item cards during your turn.

### Detected Effect Patterns
- **Effect Builders:** `search_deck`
- shuffle_after=true (default)

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

    // Shuffle discard into deck (Super Rod)
    EffectResult shuffle_discard_to_deck(state, source_card, player_id, filter, count, min_count=0);

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

### Filter Builder
```cpp
auto filter = effects::FilterBuilder()
    .supertype("Pokemon")      // "Pokemon", "Trainer", "Energy"
    .subtype("Basic")          // "Basic", "Stage 1", "Stage 2", "Item", etc.
    .pokemon_type(EnergyType::FIGHTING)  // For type-specific searches
    .max_hp(70)                // For Buddy-Buddy Poffin
    .name("Pikachu")           // Specific card search
    .evolves_from("Charmander") // Evolution search
    .is_basic_energy()         // Basic Energy cards only
    .build();
```

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

    // Register for all printings
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

### File: `cpp_engine/src/cards/trainers/items/ultra_ball.cpp`

```cpp
/**
 * Ultra Ball - Trainer Item
 *
 * Card text:
 * "You can use this card only if you discard 2 other cards from your hand. Search your deck for a Pokemon, reveal it, and put it into your hand. Then, shuffle your deck."
 * "You may play any number of Item cards during your turn."
 *
 * Card IDs: sv1-196, sv4pt5-91, me1-131
 */

#include "cards/trainer_registry.hpp"
#include "cards/effect_builders.hpp"

namespace pokemon {
namespace trainers {

namespace {

/**
 * Check if Ultra Ball can be played.
 */
bool can_play_ultra_ball(const GameState& state, PlayerID player_id) {
    // TODO: Add playability checks
    // Example: return effects::has_bench_space(state, player_id);
    return true;
}

/**
 * Execute Ultra Ball effect.
 */
TrainerResult execute_ultra_ball(GameState& state, const CardInstance& card) {
    TrainerResult result;
    PlayerID player_id = state.active_player_index;

    if (!can_play_ultra_ball(state, player_id)) {
        result.success = false;
        result.effect_description = "Cannot play Ultra Ball";
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
    result.effect_description = "Ultra Ball effect";

    return result;
}

} // anonymous namespace

void register_ultra_ball(LogicRegistry& registry) {
    auto handler = [](GameState& state, const CardInstance& card) -> TrainerResult {
        return execute_ultra_ball(state, card);
    };

    auto generator = [](const GameState& state, const CardInstance& card) -> GeneratorResult {
        GeneratorResult result;
        result.valid = can_play_ultra_ball(state, state.active_player_index);
        if (!result.valid) {
            result.reason = "Cannot play Ultra Ball";
        }
        return result;
    };

    // Register for all printings
    registry.register_trainer("sv1-196", handler);
    registry.register_generator("sv1-196", "trainer", generator);
    registry.register_trainer("sv4pt5-91", handler);
    registry.register_generator("sv4pt5-91", "trainer", generator);
    registry.register_trainer("me1-131", handler);
    registry.register_generator("me1-131", "trainer", generator);
}

} // namespace trainers
} // namespace pokemon
```

### Add to `trainer_registry.cpp`

```cpp
#include "cards/trainers/items/ultra_ball.cpp"

void register_all_trainers(LogicRegistry& registry) {
    // ... existing registrations ...
    trainers::register_ultra_ball(registry);
}
```

## Implementation Checklist

### Core Implementation
- [ ] Implement `can_play_ultra_ball()` with proper validation
  - Check bench space if putting Pokemon on bench
  - Check discard cost if card requires discarding
  - Do NOT check if deck has targets (fail-to-find is legal)
- [ ] Implement `execute_ultra_ball()` using effect builders
  - Use appropriate `effects::` helper
  - Set correct count/min_count
  - Build correct filter criteria
- [ ] Register all card IDs: `sv1-196, sv4pt5-91, me1-131`
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

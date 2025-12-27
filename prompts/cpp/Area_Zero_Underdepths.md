# C++ Engine Implementation: Area Zero Underdepths

## Card Data
**Card IDs:** `sv7-131, sv7-174`
**Type:** Trainer (Stadium)

### Card Text
> Each player who has any Tera Pokemon in play can have up to 8 Pokemon on their Bench.    If a player no longer has any Tera Pokemon in play, that player discards Pokemon from their Bench until they have 5. When this card leaves play, both players discard Pokemon from their Bench until they have 5, and the player who played this card discards first.
> You may play only 1 Stadium card during your turn. Put it next to the Active Spot, and discard it if another Stadium comes into play. A Stadium with the same name can't be played.

**Card IDs:** `sv8pt5-94`
**Type:** Trainer (Stadium)

### Card Text
> Each player who has any Tera Pokemon in play can have up to 8 Pokemon on their Bench.  If a player no longer has any Tera Pokemon in play, that player discards Pokemon from their Bench until they have 5. When this card leaves play, both players discard Pokemon from their Bench until they have 5, and the player who played this card discards first.
> You may play only 1 Stadium card during your turn. Put it next to the Active Spot, and discard it if another Stadium comes into play. A Stadium with the same name can't be played.

## C++ Engine Architecture

### Key Files
- `cpp_engine/src/cards/trainers/items/{name}.cpp` - Item implementations
- `cpp_engine/src/cards/trainers/supporters/{name}.cpp` - Supporter implementations
- `cpp_engine/src/cards/trainer_registry.cpp` - Registration calls
- `cpp_engine/include/cards/effect_builders.hpp` - Effect primitives
- `cpp_engine/TRAINER_PATTERNS.md` - Full pattern documentation

---

## CRITICAL: Three Trainer Patterns

ALL trainer cards fit exactly one of these three patterns. Determine which pattern applies
BEFORE writing any code. This architecture is final - do not deviate from it.

| Pattern | Generator Mode | Resolution Stack | Example Cards |
|---------|---------------|------------------|---------------|
| **IMMEDIATE** | `VALIDITY_CHECK` | No | Iono, Professor's Research |
| **TARGETED** | `ACTION_GENERATION` | No | Rare Candy, Switch |
| **SEARCH** | `VALIDITY_CHECK` | Yes | Nest Ball, Ultra Ball |

### Decision Framework
```
Does the card require player choices?
├─ No → IMMEDIATE
└─ Yes → Are targets visible (board, hand)?
         ├─ Yes → TARGETED
         └─ No (deck, prizes) → SEARCH
```

---

## Pattern 1: IMMEDIATE

**Use when:** The effect is deterministic with no player choices.

**Characteristics:**
- No targeting required
- No hidden information revealed
- Effect executes immediately in handler
- Generator only validates playability (mode = VALIDITY_CHECK, the default)

**Examples:** Iono, Professor's Research, Judge

```cpp
// Generator: VALIDITY_CHECK mode (default)
auto generator = [](const GameState& state, const CardInstance& card) -> GeneratorResult {
    GeneratorResult result;
    result.valid = true;  // Iono can always be played
    // mode defaults to VALIDITY_CHECK
    return result;
};

// Handler: Direct effect using TrainerContext
auto handler = [](TrainerContext& ctx) -> TrainerResult {
    TrainerResult result;
    auto& state = ctx.state;
    // Execute effect directly on state
    // No resolution steps needed
    result.success = true;
    return result;
};
```

---

## Pattern 2: TARGETED

**Use when:** Player must choose from visible targets (board, hand - NOT hidden zones).

**Characteristics:**
- Targets are visible to player (board, hand)
- Generator enumerates all valid (card, target) combinations
- Generator sets `mode = GeneratorMode::ACTION_GENERATION`
- Each combination becomes a separate legal action
- Handler receives target info via `ctx.action.target_id` and `ctx.action.parameters`
- No resolution stack needed

**Examples:** Rare Candy, Switch, Boss's Orders

```cpp
// Generator: ACTION_GENERATION mode - provides complete actions with targets
auto generator = [](const GameState& state, const CardInstance& card) -> GeneratorResult {
    GeneratorResult result;

    auto pairs = get_valid_pairs(state, db, player_id);
    if (pairs.empty()) {
        result.valid = false;
        result.reason = "No valid targets";
        return result;
    }

    result.valid = true;
    result.mode = GeneratorMode::ACTION_GENERATION;  // CRITICAL!

    for (const auto& pair : pairs) {
        Action action = Action::play_item(player_id, card.id);
        action.target_id = pair.basic_id;
        action.parameters["stage2_id"] = pair.stage2_id;
        result.actions.push_back(action);
    }

    return result;
};

// Handler: Use targets from ctx.action
auto handler = [](TrainerContext& ctx) -> TrainerResult {
    TrainerResult result;
    const CardID& target = *ctx.action.target_id;
    const CardID& stage2 = ctx.action.parameters.at("stage2_id");
    // Execute effect with specific targets
    result.success = true;
    return result;
};
```

---

## Pattern 3: SEARCH

**Use when:** Player must select from hidden zones (deck, prizes).

**Characteristics:**
- Selection from hidden zone (deck search, etc.)
- Generator only validates playability (mode = VALIDITY_CHECK, the default)
- Handler pushes resolution steps to stack
- Engine handles step-by-step selection UI
- Handler sets `result.requires_resolution = true`

**Examples:** Nest Ball, Ultra Ball, Super Rod, Buddy-Buddy Poffin

```cpp
// Generator: VALIDITY_CHECK mode (default)
auto generator = [](const GameState& state, const CardInstance& card) -> GeneratorResult {
    GeneratorResult result;
    result.valid = has_bench_space(state, player_id);
    // mode defaults to VALIDITY_CHECK
    return result;
};

// Handler: Push resolution steps using TrainerContext
auto handler = [](TrainerContext& ctx) -> TrainerResult {
    TrainerResult result;
    auto& state = ctx.state;

    auto effect_result = effects::search_deck_to_bench(
        state, ctx.card, player_id, filter,
        1,    // count
        0     // min_count (can fail to find)
    );

    result.success = effect_result.success;
    result.requires_resolution = effect_result.requires_resolution;
    return result;
};
```

---

## TrainerContext (Unified Handler Signature)

ALL trainers use `TrainerHandler` which receives `TrainerContext&`:

```cpp
struct TrainerContext {
    GameState& state;           // Mutable game state
    const CardInstance& card;   // The trainer card being played
    const CardDatabase& db;     // Card definitions for lookups
    const Action& action;       // Contains target_id/parameters for TARGETED cards
};

using TrainerHandler = std::function<TrainerResult(TrainerContext&)>;
```

---

## Registration (Unified Pattern)

ALL trainers register with `register_trainer_handler()` and `register_generator()`:

```cpp
void register_{card_name}(LogicRegistry& registry) {
    // Unified handler using TrainerContext
    auto handler = [](TrainerContext& ctx) -> TrainerResult {
        return execute_{card_name}(ctx);
    };

    auto generator = [](const GameState& state, const CardInstance& card) -> GeneratorResult {
        GeneratorResult result;
        result.valid = can_play_{card_name}(state, state.active_player_index);
        if (!result.valid) {
            result.reason = "Cannot play";
        }
        // For TARGETED pattern only: result.mode = GeneratorMode::ACTION_GENERATION;
        return result;
    };

    // Register for all printings
    const std::vector<std::string> card_ids = {"sv1-xxx", "sv2-yyy"};
    for (const auto& id : card_ids) {
        registry.register_trainer_handler(id, handler);
        registry.register_generator(id, "trainer", generator);
    }
}
```

---

## Effect Builders Available

```cpp
namespace effects {
    // Search deck for cards
    EffectResult search_deck(state, source_card, player_id, filter,
        count=1, min_count=0, destination=HAND, shuffle_after=true);

    // Search deck directly to bench (for Nest Ball, Poffin)
    EffectResult search_deck_to_bench(state, source_card, player_id, filter,
        count=1, min_count=0);

    // Discard cards then do something (Ultra Ball)
    EffectResult discard_then(state, source_card, player_id, discard_count, filter, then_effect);

    // Draw cards
    EffectResult draw_cards(state, player_id, count);

    // Discard hand and draw (Professor's Research)
    EffectResult discard_hand_draw(state, player_id, draw_count);

    // Shuffle discard into deck (predicate filter for complex OR logic)
    EffectResult shuffle_discard_to_deck(state, source_card, player_id, filter_fn, count, min_count);

    // Switch active Pokemon
    EffectResult switch_active(state, source_card, player_id);

    // Validation helpers
    bool has_bench_space(state, player_id);
}
```

### Filter Builder
```cpp
auto filter = effects::FilterBuilder()
    .supertype("Pokemon")
    .subtype("Basic")
    .max_hp(70)
    .build();
```

### Predicate Filters (for complex OR logic)
```cpp
auto effect_result = effects::shuffle_discard_to_deck(
    state, ctx.card, player_id,
    [](const CardDef& def) {
        return def.is_pokemon() || (def.is_energy() && def.is_basic_energy);
    },
    3, 1  // count, min_count
);
```

---

## Search Semantics: Hidden vs Public Zones

**Deck (hidden zone)** - "Fail to find" is ALWAYS allowed:
- `min_count=0` lets player choose 0 cards even if valid targets exist

**Discard pile / Hand (public zones)** - NO fail to find:
- If valid targets exist, player MUST select them
- Use `min_count >= 1` for public zones

---

## Reference Implementation: Nest Ball (SEARCH Pattern)

**CRITICAL: Card IDs must match your card!**
Use the Card IDs from the Card Data section, NOT these example IDs.

```cpp
/**
 * Nest Ball - Trainer Item (SEARCH Pattern)
 *
 * Card text:
 * "Search your deck for a Basic Pokemon and put it onto your Bench.
 *  Then, shuffle your deck."
 *
 * Card IDs: sv1-181, sv1-255, sv4pt5-84
 */

#include "cards/trainer_registry.hpp"
#include "cards/effect_builders.hpp"

namespace pokemon {
namespace trainers {

namespace {

bool can_play_nest_ball(const GameState& state, PlayerID player_id) {
    return effects::has_bench_space(state, player_id);
}

TrainerResult execute_nest_ball(TrainerContext& ctx) {
    TrainerResult result;
    auto& state = ctx.state;
    PlayerID player_id = state.active_player_index;

    if (!can_play_nest_ball(state, player_id)) {
        result.success = false;
        result.effect_description = "No bench space available";
        return result;
    }

    auto filter = effects::FilterBuilder()
        .supertype("Pokemon")
        .subtype("Basic")
        .build();

    auto effect_result = effects::search_deck_to_bench(
        state, ctx.card, player_id, filter,
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
    // Unified handler using TrainerContext
    auto handler = [](TrainerContext& ctx) -> TrainerResult {
        return execute_nest_ball(ctx);
    };

    auto generator = [](const GameState& state, const CardInstance& /*card*/) -> GeneratorResult {
        GeneratorResult result;
        result.valid = can_play_nest_ball(state, state.active_player_index);
        if (!result.valid) {
            result.reason = "No bench space";
        }
        // SEARCH pattern: VALIDITY_CHECK mode (default)
        return result;
    };

    // Register for all printings using unified handler
    const std::vector<std::string> card_ids = {"sv1-181", "sv1-255", "sv4pt5-84"};
    for (const auto& id : card_ids) {
        registry.register_trainer_handler(id, handler);
        registry.register_generator(id, "trainer", generator);
    }
}

} // namespace trainers
} // namespace pokemon
```

## Implementation Template

**Pattern:** IMMEDIATE
IMMEDIATE pattern: Effect executes directly, no player choices

**Card IDs:** `sv7-131, sv7-174, sv8pt5-94`

### File: `cpp_engine/src/cards/trainers/stadiums/area_zero_underdepths.cpp`

```cpp
/**
 * Area Zero Underdepths - Trainer Stadium (IMMEDIATE Pattern)
 *
 * Card text:
 * "Each player who has any Tera Pokemon in play can have up to 8 Pokemon on their Bench.    If a player no longer has any Tera Pokemon in play, that player discards Pokemon from their Bench until they have 5. When this card leaves play, both players discard Pokemon from their Bench until they have 5, and the player who played this card discards first."
 * "You may play only 1 Stadium card during your turn. Put it next to the Active Spot, and discard it if another Stadium comes into play. A Stadium with the same name can't be played."
 *
 * Card IDs: sv7-131, sv7-174, sv8pt5-94
 *
 * Pattern: IMMEDIATE
 * - Generator mode: VALIDITY_CHECK (default)
 * - Uses resolution stack: No
 */

#include "cards/trainer_registry.hpp"
#include "cards/effect_builders.hpp"

namespace pokemon {
namespace trainers {

namespace {

/**
 * Check if Area Zero Underdepths can be played.
 */
bool can_play_area_zero_underdepths(const GameState& state, PlayerID player_id) {
    // TODO: Add playability checks
    // Example: return effects::has_bench_space(state, player_id);
    return true;
}

/**
 * Execute Area Zero Underdepths effect using TrainerContext.
 */
TrainerResult execute_area_zero_underdepths(TrainerContext& ctx) {
    TrainerResult result;
    auto& state = ctx.state;
    PlayerID player_id = state.active_player_index;

    if (!can_play_area_zero_underdepths(state, player_id)) {
        result.success = false;
        result.effect_description = "Cannot play Area Zero Underdepths";
        return result;
    }

    // IMMEDIATE pattern: Execute effect directly
    // TODO: Implement the immediate effect
    // Example: draw cards, shuffle hands, etc.

    result.success = true;
    result.effect_description = "Area Zero Underdepths effect";
    return result;
}

} // anonymous namespace

void register_area_zero_underdepths(LogicRegistry& registry) {
    // Unified handler using TrainerContext
    auto handler = [](TrainerContext& ctx) -> TrainerResult {
        return execute_area_zero_underdepths(ctx);
    };

    auto generator = [](const GameState& state, const CardInstance& /*card*/) -> GeneratorResult {
        GeneratorResult result;
        result.valid = can_play_area_zero_underdepths(state, state.active_player_index);
        if (!result.valid) {
            result.reason = "Cannot play Area Zero Underdepths";
        }
        // IMMEDIATE pattern: VALIDITY_CHECK mode (default)
        return result;
    };

    // Register for all printings using unified handler
    const std::vector<std::string> card_ids = {"sv7-131", "sv7-174", "sv8pt5-94"};
    for (const auto& id : card_ids) {
        registry.register_trainer_handler(id, handler);
        registry.register_generator(id, "trainer", generator);
    }
}

} // namespace trainers
} // namespace pokemon
```

### Add to `trainer_registry.cpp`

```cpp
#include "cards/trainers/stadiums/area_zero_underdepths.cpp"

void register_all_trainers(LogicRegistry& registry) {
    // ... existing registrations ...
    trainers::register_area_zero_underdepths(registry);
}
```

## Implementation Checklist

### Core Implementation
- [ ] Implement `can_play_area_zero_underdepths()` with proper validation
  - Check bench space if putting Pokemon on bench
  - Check discard cost if card requires discarding
  - Do NOT check if deck has targets (fail-to-find is legal)
- [ ] Implement `execute_area_zero_underdepths()` using effect builders
  - Use appropriate `effects::` helper
  - Set correct count/min_count
  - Build correct filter criteria
- [ ] Register all card IDs: `sv7-131, sv7-174, sv8pt5-94`
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

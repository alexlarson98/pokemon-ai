"""
Generate AI implementation prompts for Pokemon TCG cards (C++ Engine)

Creates comprehensive prompts for implementing cards in the C++ engine,
including card data, architecture patterns, and integration guidelines.

Usage:
    python generate_cpp_card_prompt.py "Buddy-Buddy Poffin"
    python generate_cpp_card_prompt.py "Charizard ex"
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict


def to_snake_case(name: str) -> str:
    """Convert card name to snake_case for C++ identifiers."""
    return (name.lower()
            .replace(' ', '_')
            .replace('-', '_')
            .replace("'", '')
            .replace('.', '')
            .replace('é', 'e'))


def format_energy_cost(cost: List[str]) -> str:
    """Format energy cost for display."""
    if not cost:
        return "Free"
    mapping = {
        'Colorless': 'C', 'Water': 'W', 'Fire': 'F', 'Grass': 'G',
        'Lightning': 'L', 'Psychic': 'P', 'Fighting': 'R', 'Darkness': 'D',
        'Metal': 'M', 'Dragon': 'N', 'Fairy': 'Y'
    }
    return ''.join(mapping.get(e, e[0]) for e in cost)


def get_energy_type_enum(type_str: str) -> str:
    """Convert Pokemon type string to C++ EnergyType enum."""
    mapping = {
        'Colorless': 'EnergyType::COLORLESS',
        'Water': 'EnergyType::WATER',
        'Fire': 'EnergyType::FIRE',
        'Grass': 'EnergyType::GRASS',
        'Lightning': 'EnergyType::LIGHTNING',
        'Psychic': 'EnergyType::PSYCHIC',
        'Fighting': 'EnergyType::FIGHTING',
        'Darkness': 'EnergyType::DARKNESS',
        'Metal': 'EnergyType::METAL',
        'Dragon': 'EnergyType::DRAGON',
        'Fairy': 'EnergyType::FAIRY',
    }
    return mapping.get(type_str, 'EnergyType::COLORLESS')


def detect_effect_pattern(text: str) -> Dict[str, Any]:
    """Detect which effect builders and patterns apply to this card text."""
    text_lower = text.lower()
    patterns = {
        'use_stack': False,
        'effect_builders': [],
        'filter_criteria': [],
        'notes': []
    }

    # Search deck patterns
    if 'search your deck' in text_lower:
        patterns['use_stack'] = True
        patterns['effect_builders'].append('search_deck')

        if 'basic pokémon' in text_lower or 'basic pokemon' in text_lower:
            patterns['filter_criteria'].append('.supertype("Pokemon").subtype("Basic")')
        if 'put it onto your bench' in text_lower or 'onto your bench' in text_lower:
            patterns['effect_builders'] = ['search_deck_to_bench']
        if 'shuffle' in text_lower:
            patterns['notes'].append('shuffle_after=true (default)')

    # HP filter (Buddy-Buddy Poffin)
    if 'hp or less' in text_lower:
        import re
        hp_match = re.search(r'(\d+)\s*hp or less', text_lower)
        if hp_match:
            patterns['filter_criteria'].append(f'.max_hp({hp_match.group(1)})')

    # Count detection
    import re
    count_patterns = [
        (r'up to (\d+)', 'count={}, min_count=0'),
        (r'search.+for (\d+)', 'count={}, min_count=0'),
    ]
    for pattern, template in count_patterns:
        match = re.search(pattern, text_lower)
        if match:
            patterns['notes'].append(template.format(match.group(1)))

    # Discard cost
    if 'discard' in text_lower and ('from your hand' in text_lower or 'card' in text_lower):
        discard_match = re.search(r'discard (\d+|a) card', text_lower)
        if discard_match:
            count = '1' if discard_match.group(1) == 'a' else discard_match.group(1)
            patterns['effect_builders'].append(f'discard_then (discard_count={count})')
            patterns['use_stack'] = True

    # Draw cards
    if 'draw' in text_lower and 'card' in text_lower:
        draw_match = re.search(r'draw (\d+) card', text_lower)
        if draw_match:
            patterns['effect_builders'].append(f'draw_cards (count={draw_match.group(1)})')

    # Discard hand and draw
    if 'discard your hand' in text_lower and 'draw' in text_lower:
        draw_match = re.search(r'draw (\d+) card', text_lower)
        if draw_match:
            patterns['effect_builders'].append(f'discard_hand_draw (draw_count={draw_match.group(1)})')

    # Switch
    if 'switch' in text_lower and 'active' in text_lower:
        patterns['effect_builders'].append('switch_active')
        patterns['use_stack'] = True

    # Recover from discard
    if 'from your discard pile' in text_lower:
        if 'into your hand' in text_lower:
            patterns['effect_builders'].append('recover_from_discard')
        elif 'shuffle' in text_lower and 'deck' in text_lower:
            patterns['effect_builders'].append('shuffle_discard_to_deck')
        patterns['use_stack'] = True

    # Heal
    if 'heal' in text_lower:
        heal_match = re.search(r'heal (\d+) damage', text_lower)
        if heal_match:
            patterns['effect_builders'].append(f'heal_damage (amount={heal_match.group(1)})')

    # Bench space requirement
    if 'onto your bench' in text_lower or 'bench' in text_lower:
        patterns['notes'].append('Requires bench space check in can_play')

    return patterns


def normalize_card(card: Dict[str, Any]) -> tuple:
    """Create a signature for grouping duplicate cards."""
    name = card.get('name', '')
    hp = card.get('hp', 0)
    supertype = card.get('supertype', '')
    subtypes = tuple(sorted(card.get('subtypes', [])))

    abilities = tuple(sorted(
        (ab.get('name', ''), ab.get('text', ''))
        for ab in card.get('abilities', [])
    ))

    attacks = tuple(sorted(
        (atk.get('name', ''), atk.get('text', ''), atk.get('damage', ''))
        for atk in card.get('attacks', [])
    ))

    rules = tuple(card.get('rules', []))

    return (name, hp, supertype, subtypes, abilities, attacks, rules)


def group_duplicates(cards: List[Dict[str, Any]]) -> Dict[tuple, List[Dict[str, Any]]]:
    """Group cards by their functional signature."""
    groups = defaultdict(list)
    for card in cards:
        signature = normalize_card(card)
        groups[signature].append(card)
    return dict(groups)


def get_trainer_architecture_section() -> str:
    """Return architecture documentation specific to Trainer cards."""
    return """## C++ Engine Architecture

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

"""


def get_pokemon_architecture_section(card: Dict[str, Any]) -> str:
    """Return architecture documentation specific to Pokemon cards."""
    has_abilities = bool(card.get('abilities', []))
    has_complex_attacks = any(atk.get('text', '') for atk in card.get('attacks', []))
    is_evolution = bool(card.get('evolvesFrom', ''))
    subtypes = card.get('subtypes', [])
    is_basic = 'Basic' in subtypes

    section = """## C++ Engine Architecture

### Key Files
- `cpp_engine/src/cards/pokemon/{name}.cpp` - Pokemon-specific logic (if needed)
- `cpp_engine/src/cards/pokemon_registry.cpp` - Registration calls
- `cpp_engine/include/logic_registry.hpp` - Registration interfaces
- `cpp_engine/docs/CARD_INTEGRATION.md` - Full documentation

### When Pokemon Need Custom Logic

**Most Pokemon require NO custom code** - the engine handles:
- Playing Basic Pokemon to bench
- Evolution (Stage 1/Stage 2)
- Retreat costs
- Standard attacks (just deal damage)
- Weakness/Resistance calculations

**Custom logic IS needed for:**
- Abilities (once-per-turn effects, passive effects)
- Attacks with special effects (coin flips, discard energy, status conditions)
- Attacks with variable damage (based on energy, cards in hand, etc.)

"""

    if has_abilities:
        section += """### Ability Registration

Abilities are registered with `LogicRegistry::register_ability()`:

```cpp
void register_{pokemon_name}(LogicRegistry& registry) {
    // Register ability handler
    registry.register_ability(
        "{card_id}",
        "{ability_name}",
        [](GameState& state, const CardInstance& source) -> AbilityResult {
            AbilityResult result;
            PlayerID player_id = source.owner_id;

            // Check if ability can be used (once per turn, conditions, etc.)
            // Implement ability effect
            // May push resolution steps for selections

            result.success = true;
            result.effect_description = "Ability effect description";
            return result;
        }
    );

    // Also register generator to check if ability can be activated
    registry.register_generator(
        "{card_id}",
        "ability:{ability_name}",
        [](const GameState& state, const CardInstance& card) -> GeneratorResult {
            GeneratorResult result;
            // Check conditions for ability activation
            result.valid = /* can activate? */;
            return result;
        }
    );
}
```

"""

    if has_complex_attacks:
        section += """### Attack Registration

Attacks with special effects are registered with `LogicRegistry::register_attack()`:

```cpp
void register_{pokemon_name}(LogicRegistry& registry) {
    registry.register_attack(
        "{card_id}",
        "{attack_name}",
        [](GameState& state, const CardInstance& attacker,
           CardInstance& defender, int base_damage) -> AttackResult {
            AttackResult result;
            result.damage = base_damage;

            // Add special effects:
            // - Coin flips: state.flip_coin()
            // - Discard energy: state.discard_attached_energy(...)
            // - Status conditions: defender.apply_status(...)
            // - Self damage: attacker.add_damage(...)

            result.effect_description = "Attack effect";
            return result;
        }
    );
}
```

### Common Attack Patterns

**Coin flip for effect:**
```cpp
if (state.flip_coin()) {
    // Effect happens
}
```

**Discard energy from self:**
```cpp
// Discard 2 energy attached to this Pokemon
state.discard_attached_energy(attacker, 2);
```

**Apply status condition:**
```cpp
defender.apply_status(StatusCondition::PARALYZED);
```

**Variable damage based on conditions:**
```cpp
int energy_count = attacker.attached_energy.size();
result.damage = base_damage + (20 * energy_count);
```

"""

    if is_evolution:
        section += """### Evolution Notes

This is an evolution Pokemon. The engine handles:
- Checking `evolvesFrom` matches a Pokemon in play
- Evolution sickness (can't evolve same turn played)
- Moving the evolution card onto the basic

No custom registration needed for standard evolution behavior.

"""
    elif is_basic:
        section += """### Basic Pokemon Notes

This is a Basic Pokemon. The engine handles:
- Playing from hand to bench
- No evolution requirements

No custom registration needed for standard play behavior.

"""

    return section


def generate_prompt(card_name: str, cards_data: Dict[str, Any]) -> str:
    """Generate a comprehensive C++ implementation prompt for a card."""

    # Find matching cards
    matching_cards = [
        c for c in cards_data['cards']
        if c.get('name', '').lower() == card_name.lower()
    ]

    if not matching_cards:
        return f"ERROR: No cards found with name '{card_name}'"

    card_groups = group_duplicates(matching_cards)
    card_snake = to_snake_case(card_name)

    # Start building prompt
    prompt = f"""# C++ Engine Implementation: {card_name}

## Card Data
"""

    for version_num, (signature, duplicate_cards) in enumerate(card_groups.items(), 1):
        first_card = duplicate_cards[0]
        supertype = first_card.get('supertype', '')
        subtypes = first_card.get('subtypes', [])

        # Card IDs
        card_ids = [c.get('id', '') for c in duplicate_cards]
        prompt += f"**Card IDs:** `{', '.join(card_ids)}`\n"
        prompt += f"**Type:** {supertype} ({', '.join(subtypes)})\n"

        if supertype == 'Pokemon':
            prompt += f"**HP:** {first_card.get('hp', 'N/A')}\n"
            types = first_card.get('types', [])
            if types:
                prompt += f"**Pokemon Type:** {', '.join(types)}\n"
            evolves_from = first_card.get('evolvesFrom', '')
            if evolves_from:
                prompt += f"**Evolves From:** {evolves_from}\n"
            retreat = first_card.get('retreatCost', [])
            prompt += f"**Retreat Cost:** {len(retreat)} ({format_energy_cost(retreat)})\n"

        prompt += "\n"

        # Card text/rules
        if supertype == 'Trainer':
            rules = first_card.get('rules', [])
            if rules:
                prompt += "### Card Text\n"
                for rule in rules:
                    prompt += f"> {rule}\n"
                prompt += "\n"

                # Detect patterns
                full_text = ' '.join(rules)
                patterns = detect_effect_pattern(full_text)

                if patterns['effect_builders']:
                    prompt += "### Detected Effect Patterns\n"
                    prompt += f"- **Effect Builders:** `{', '.join(patterns['effect_builders'])}`\n"
                    if patterns['filter_criteria']:
                        # Join filter methods - they already start with '.'
                        filter_chain = ''.join(patterns['filter_criteria'])
                        prompt += f"- **Filter Criteria:** `FilterBuilder(){filter_chain}.build()`\n"
                    if patterns['notes']:
                        for note in patterns['notes']:
                            prompt += f"- {note}\n"
                    prompt += "\n"

        elif supertype == 'Pokemon':
            # Abilities
            abilities = first_card.get('abilities', [])
            if abilities:
                prompt += "### Abilities\n"
                for ab in abilities:
                    prompt += f"**{ab.get('name', '')}** ({ab.get('type', 'Ability')})\n"
                    prompt += f"> {ab.get('text', '')}\n\n"

            # Attacks
            attacks = first_card.get('attacks', [])
            if attacks:
                prompt += "### Attacks\n"
                for atk in attacks:
                    cost = format_energy_cost(atk.get('cost', []))
                    damage = atk.get('damage', '')
                    prompt += f"**{atk.get('name', '')}** [{cost}] - {damage}\n"
                    text = atk.get('text', '')
                    if text:
                        prompt += f"> {text}\n"
                    prompt += "\n"

    # Get card info for architecture section
    first_card = list(card_groups.values())[0][0]
    supertype = first_card.get('supertype', '')
    subtypes = first_card.get('subtypes', [])
    all_card_ids = [c.get('id', '') for cards in card_groups.values() for c in cards]

    # Architecture guidance - different for Trainer vs Pokemon
    if supertype == 'Trainer':
        prompt += get_trainer_architecture_section()
    elif supertype == 'Pokemon':
        prompt += get_pokemon_architecture_section(first_card)

    if supertype == 'Trainer':
        subtype_folder = 'items' if 'Item' in subtypes else 'supporters' if 'Supporter' in subtypes else 'stadiums'

        prompt += f"""## Implementation Template

**Note:** The card IDs below (`{', '.join(all_card_ids)}`) are from standard_cards.json for THIS card.
Use these exact IDs in your registration - do NOT copy IDs from the Nest Ball example above!

### File: `cpp_engine/src/cards/trainers/{subtype_folder}/{card_snake}.cpp`

```cpp
/**
 * {card_name} - Trainer {'Item' if 'Item' in subtypes else 'Supporter' if 'Supporter' in subtypes else 'Stadium'}
 *
 * Card text:
"""
        rules = first_card.get('rules', [])
        for rule in rules:
            prompt += f' * "{rule}"\n'
        prompt += f""" *
 * Card IDs: {', '.join(all_card_ids)}
 */

#include "cards/trainer_registry.hpp"
#include "cards/effect_builders.hpp"

namespace pokemon {{
namespace trainers {{

namespace {{

/**
 * Check if {card_name} can be played.
 */
bool can_play_{card_snake}(const GameState& state, PlayerID player_id) {{
    // TODO: Add playability checks
    // Example: return effects::has_bench_space(state, player_id);
    return true;
}}

/**
 * Execute {card_name} effect.
 */
TrainerResult execute_{card_snake}(GameState& state, const CardInstance& card) {{
    TrainerResult result;
    PlayerID player_id = state.active_player_index;

    if (!can_play_{card_snake}(state, player_id)) {{
        result.success = false;
        result.effect_description = "Cannot play {card_name}";
        return result;
    }}

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
    result.effect_description = "{card_name} effect";

    return result;
}}

}} // anonymous namespace

void register_{card_snake}(LogicRegistry& registry) {{
    auto handler = [](GameState& state, const CardInstance& card) -> TrainerResult {{
        return execute_{card_snake}(state, card);
    }};

    auto generator = [](const GameState& state, const CardInstance& card) -> GeneratorResult {{
        GeneratorResult result;
        result.valid = can_play_{card_snake}(state, state.active_player_index);
        if (!result.valid) {{
            result.reason = "Cannot play {card_name}";
        }}
        return result;
    }};

    // Register for all printings
"""
        for card_id in all_card_ids:
            prompt += f'    registry.register_trainer("{card_id}", handler);\n'
            prompt += f'    registry.register_generator("{card_id}", "trainer", generator);\n'

        prompt += f"""}}

}} // namespace trainers
}} // namespace pokemon
```

### Add to `trainer_registry.cpp`

```cpp
#include "cards/trainers/{subtype_folder}/{card_snake}.cpp"

void register_all_trainers(LogicRegistry& registry) {{
    // ... existing registrations ...
    trainers::register_{card_snake}(registry);
}}
```

## Implementation Checklist

### Core Implementation
- [ ] Implement `can_play_{card_snake}()` with proper validation
  - Check bench space if putting Pokemon on bench
  - Check discard cost if card requires discarding
  - Do NOT check if deck has targets (fail-to-find is legal)
- [ ] Implement `execute_{card_snake}()` using effect builders
  - Use appropriate `effects::` helper
  - Set correct count/min_count
  - Build correct filter criteria
- [ ] Register all card IDs: `{', '.join(all_card_ids)}`
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
"""

    elif supertype == 'Pokemon':
        # Determine what custom logic this Pokemon needs
        has_abilities = bool(first_card.get('abilities', []))
        has_complex_attacks = any(atk.get('text', '') for atk in first_card.get('attacks', []))
        needs_custom_logic = has_abilities or has_complex_attacks

        if needs_custom_logic:
            prompt += f"""## Implementation Template

### File: `cpp_engine/src/cards/pokemon/{card_snake}.cpp`

```cpp
/**
 * {card_name} - Pokemon
 *
 * Card IDs: {', '.join(all_card_ids)}
 */

#include "logic_registry.hpp"
#include "game_state.hpp"

namespace pokemon {{
namespace cards {{

void register_{card_snake}(LogicRegistry& registry) {{
"""
            # Add ability registration if needed
            for ability in first_card.get('abilities', []):
                ability_name = ability.get('name', 'Unknown')
                ability_text = ability.get('text', '')
                prompt += f"""
    // Ability: {ability_name}
    // "{ability_text}"
    registry.register_ability(
        "{all_card_ids[0]}",
        "{ability_name}",
        [](GameState& state, const CardInstance& source) -> AbilityResult {{
            AbilityResult result;
            // TODO: Implement ability logic
            result.success = true;
            return result;
        }}
    );
"""

            # Add attack registration if needed
            for attack in first_card.get('attacks', []):
                if attack.get('text', ''):  # Only complex attacks
                    attack_name = attack.get('name', 'Unknown')
                    attack_text = attack.get('text', '')
                    attack_damage = attack.get('damage', '0')
                    prompt += f"""
    // Attack: {attack_name} - {attack_damage}
    // "{attack_text}"
    registry.register_attack(
        "{all_card_ids[0]}",
        "{attack_name}",
        [](GameState& state, const CardInstance& attacker,
           CardInstance& defender, int base_damage) -> AttackResult {{
            AttackResult result;
            result.damage = base_damage;
            // TODO: Implement attack special effect
            return result;
        }}
    );
"""

            prompt += f"""
    // Register for all printings
"""
            for card_id in all_card_ids[1:]:  # Skip first, already used above
                prompt += f'    // Also register for: {card_id}\n'

            prompt += f"""}}

}} // namespace cards
}} // namespace pokemon
```

### Add to `pokemon_registry.cpp`

```cpp
#include "cards/pokemon/{card_snake}.cpp"

void register_all_pokemon(LogicRegistry& registry) {{
    // ... existing registrations ...
    cards::register_{card_snake}(registry);
}}
```

## Implementation Checklist

### Core Implementation
"""
            if has_abilities:
                prompt += f"""- [ ] Implement ability handler(s)
  - Check once-per-turn restrictions if applicable
  - Implement the ability effect
  - Register generator for ability activation check
"""
            if has_complex_attacks:
                prompt += f"""- [ ] Implement attack handler(s) with special effects
  - Handle coin flips, energy discards, status conditions
  - Calculate variable damage if applicable
"""
            prompt += f"""- [ ] Register all card IDs: `{', '.join(all_card_ids)}`
- [ ] Add registration call to `pokemon_registry.cpp`

### Testing
- [ ] Build: `cmake --build build --config Release`
- [ ] Run console: `build/Release/pokemon_console.exe`
"""
            if has_abilities:
                prompt += """- [ ] Verify ability appears in legal actions when conditions are met
- [ ] Verify ability does NOT appear when already used this turn (if once-per-turn)
- [ ] Test ability effect resolves correctly
"""
            if has_complex_attacks:
                prompt += """- [ ] Verify attack special effects trigger correctly
- [ ] Test coin flips, energy discards, status conditions as applicable
"""

        else:
            # No custom logic needed
            prompt += f"""## Implementation Notes

**This Pokemon requires NO custom code.**

The engine automatically handles:
- Playing to bench (Basic) / Evolution
- Standard attacks (damage only)
- Retreat costs
- Weakness/Resistance

Card IDs: `{', '.join(all_card_ids)}`

Simply ensure the card data exists in the card database JSON.
"""

    return prompt


def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_cpp_card_prompt.py \"Card Name\"")
        print("\nExample:")
        print("  python generate_cpp_card_prompt.py \"Buddy-Buddy Poffin\"")
        print("  python generate_cpp_card_prompt.py \"Nest Ball\"")
        sys.exit(1)

    card_name = sys.argv[1]
    data_file = Path("data/standard_cards.json")

    if not data_file.exists():
        print(f"ERROR: {data_file} not found")
        sys.exit(1)

    with open(data_file, 'r', encoding='utf-8') as f:
        cards_data = json.load(f)

    prompt = generate_prompt(card_name, cards_data)

    # Save to file
    output_dir = Path("prompts/cpp")
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = card_name.replace(' ', '_').replace('/', '_').replace('\\', '_')
    output_file = output_dir / f"{safe_name}.md"

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(prompt)

    print(f"Generated prompt for '{card_name}' at {output_file}")
    print("\n" + "=" * 60 + "\n")
    # Handle unicode characters on Windows console
    try:
        print(prompt)
    except UnicodeEncodeError:
        print(prompt.encode('utf-8', errors='replace').decode('utf-8'))


if __name__ == '__main__':
    main()

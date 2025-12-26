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

        # Detect pattern for this card
        rules = first_card.get('rules', [])
        full_text = ' '.join(rules).lower()

        # Determine pattern
        if 'search' in full_text and ('deck' in full_text or 'discard' in full_text):
            pattern = 'SEARCH'
            pattern_comment = 'SEARCH pattern: Uses resolution stack for hidden zone selection'
        elif any(word in full_text for word in ['switch', 'evolve', 'attach', 'move']):
            pattern = 'TARGETED'
            pattern_comment = 'TARGETED pattern: Generator provides actions with visible targets'
        else:
            pattern = 'IMMEDIATE'
            pattern_comment = 'IMMEDIATE pattern: Effect executes directly, no player choices'

        prompt += f"""## Implementation Template

**Pattern:** {pattern}
{pattern_comment}

**Card IDs:** `{', '.join(all_card_ids)}`

### File: `cpp_engine/src/cards/trainers/{subtype_folder}/{card_snake}.cpp`

```cpp
/**
 * {card_name} - Trainer {'Item' if 'Item' in subtypes else 'Supporter' if 'Supporter' in subtypes else 'Stadium'} ({pattern} Pattern)
 *
 * Card text:
"""
        for rule in rules:
            prompt += f' * "{rule}"\n'
        prompt += f""" *
 * Card IDs: {', '.join(all_card_ids)}
 *
 * Pattern: {pattern}
 * - {"Generator mode: VALIDITY_CHECK (default)" if pattern != 'TARGETED' else "Generator mode: ACTION_GENERATION"}
 * - {"Uses resolution stack: Yes" if pattern == 'SEARCH' else "Uses resolution stack: No"}
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
 * Execute {card_name} effect using TrainerContext.
 */
TrainerResult execute_{card_snake}(TrainerContext& ctx) {{
    TrainerResult result;
    auto& state = ctx.state;
    PlayerID player_id = state.active_player_index;

    if (!can_play_{card_snake}(state, player_id)) {{
        result.success = false;
        result.effect_description = "Cannot play {card_name}";
        return result;
    }}
"""
        if pattern == 'TARGETED':
            prompt += f"""
    // TARGETED pattern: Get target info from ctx.action
    if (!ctx.action.target_id.has_value()) {{
        result.success = false;
        result.effect_description = "No target specified";
        return result;
    }}
    const CardID& target = *ctx.action.target_id;
    // const auto& param = ctx.action.parameters.at("param_name");

    // TODO: Execute effect with specific targets
"""
        elif pattern == 'SEARCH':
            prompt += f"""
    // SEARCH pattern: Build filter and use effect builder
    auto filter = effects::FilterBuilder()
        // .supertype("Pokemon")
        // .subtype("Basic")
        .build();

    // TODO: Use appropriate effect builder
    auto effect_result = effects::search_deck_to_bench(
        state, ctx.card, player_id, filter,
        1,      // count
        0       // min_count (can fail to find in hidden zones)
    );

    result.success = effect_result.success;
    result.requires_resolution = effect_result.requires_resolution;
"""
        else:  # IMMEDIATE
            prompt += f"""
    // IMMEDIATE pattern: Execute effect directly
    // TODO: Implement the immediate effect
    // Example: draw cards, shuffle hands, etc.
"""

        prompt += f"""
    result.success = true;
    result.effect_description = "{card_name} effect";
    return result;
}}

}} // anonymous namespace

void register_{card_snake}(LogicRegistry& registry) {{
    // Unified handler using TrainerContext
    auto handler = [](TrainerContext& ctx) -> TrainerResult {{
        return execute_{card_snake}(ctx);
    }};

    auto generator = [](const GameState& state, const CardInstance& {"card" if pattern == 'TARGETED' else "/*card*/"}) -> GeneratorResult {{
        GeneratorResult result;
"""
        if pattern == 'TARGETED':
            prompt += f"""
        // TARGETED pattern: Generate actions with target info
        // TODO: Find all valid targets
        // auto targets = find_valid_targets(state, player_id);
        // if (targets.empty()) {{
        //     result.valid = false;
        //     result.reason = "No valid targets";
        //     return result;
        // }}

        result.valid = true;
        result.mode = GeneratorMode::ACTION_GENERATION;  // CRITICAL for TARGETED!

        // TODO: Create an action for each valid target
        // for (const auto& target : targets) {{
        //     Action action = Action::play_item(state.active_player_index, card.id);
        //     action.target_id = target.id;
        //     result.actions.push_back(action);
        // }}
"""
        else:
            prompt += f"""        result.valid = can_play_{card_snake}(state, state.active_player_index);
        if (!result.valid) {{
            result.reason = "Cannot play {card_name}";
        }}
        // {pattern} pattern: VALIDITY_CHECK mode (default)
"""
        prompt += f"""        return result;
    }};

    // Register for all printings using unified handler
    const std::vector<std::string> card_ids = {{{', '.join(f'"{id}"' for id in all_card_ids)}}};
    for (const auto& id : card_ids) {{
        registry.register_trainer_handler(id, handler);
        registry.register_generator(id, "trainer", generator);
    }}
}}

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

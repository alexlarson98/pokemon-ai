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
                        prompt += f"- **Filter Criteria:** `FilterBuilder(){'.'.join(patterns['filter_criteria'])}.build()`\n"
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

    # Architecture guidance
    prompt += """## C++ Engine Architecture

### Key Files
- `cpp_engine/src/cards/trainers/items/{name}.cpp` - Item implementations
- `cpp_engine/src/cards/trainers/supporters/{name}.cpp` - Supporter implementations
- `cpp_engine/src/cards/trainer_registry.cpp` - Registration calls
- `cpp_engine/include/cards/effect_builders.hpp` - Effect primitives
- `cpp_engine/docs/CARD_INTEGRATION.md` - Full documentation

### Callback-Based Step Completion
The engine uses **callbacks** for step completion, NOT string-based dispatch:

```cpp
// Callback signature
using StepCompletionCallback = std::function<void(
    GameState& state,
    const std::vector<CardID>& selected_cards,
    PlayerID player_id
)>;

// Usage in effect builders
step.on_complete = CompletionCallback([](GameState& state,
    const std::vector<CardID>& selected, PlayerID player) {
    // Card-specific completion logic
});
```

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
    .max_hp(70)                // For Buddy-Buddy Poffin
    .name("Pikachu")           // Specific card search
    .evolves_from("Charmander") // Evolution search
    .is_basic_energy()         // Basic Energy cards only
    .build();
```

### Registration Pattern
Cards register:
1. **TrainerCallback** - Execute the effect
2. **GeneratorCallback** - Check if card can be played (for legal actions)

```cpp
void register_{card_name}(LogicRegistry& registry) {{
    // Handler - executes the effect
    auto handler = [](GameState& state, const CardInstance& card) -> TrainerResult {{
        // Implementation
    }};

    // Generator - checks playability
    auto generator = [](const GameState& state, const CardInstance& card) -> GeneratorResult {{
        GeneratorResult result;
        result.valid = /* can play? */;
        result.reason = "Reason if invalid";
        return result;
    }};

    registry.register_trainer("{card_id}", handler);
    registry.register_generator("{card_id}", "trainer", generator);
}}
```

"""

    # Implementation template
    first_card = list(card_groups.values())[0][0]
    supertype = first_card.get('supertype', '')
    subtypes = first_card.get('subtypes', [])
    all_card_ids = [c.get('id', '') for cards in card_groups.values() for c in cards]

    if supertype == 'Trainer':
        subtype_folder = 'items' if 'Item' in subtypes else 'supporters' if 'Supporter' in subtypes else 'stadiums'

        prompt += f"""## Implementation Template

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
"""

    prompt += f"""
## Checklist
- [ ] Implement `can_play_{card_snake}()` with proper validation
- [ ] Implement `execute_{card_snake}()` using effect builders
- [ ] Register all card IDs: `{', '.join(all_card_ids)}`
- [ ] Add registration call to `trainer_registry.cpp`
- [ ] Build and test with console
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
    print(prompt)


if __name__ == '__main__':
    main()

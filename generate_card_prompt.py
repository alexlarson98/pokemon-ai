"""
Generate AI implementation prompts for Pokemon TCG cards (Pokemon & Trainers)

Features:
- UNIFIED ABILITY SCHEMA with explicit 'category' field
- Categories: attack, activatable, modifier, guard, hook
- Multi-effect abilities use suffixed entries: "Ability (Modifier)", "Ability (Guard)"
- Stack Architecture for multi-step effects (SearchDeckStep, SelectFromZoneStep, etc.)
- Automatic Reprints handling

Usage:
    python generate_card_prompt.py "Charmander"
    python generate_card_prompt.py "Iono"
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Any
from collections import defaultdict

# --- STACK ARCHITECTURE DETECTION ---

def detect_stack_pattern(text: str) -> dict:
    """
    Detect if card text requires Stack Architecture for multi-step resolution.

    Stack Architecture is used when effects require:
    - Sequential user decisions (search deck -> select cards -> place them)
    - Costs that must be paid before effects resolve (discard 2 cards -> search)
    - Multiple targets that need individual selection

    Returns dict with:
        'use_stack': bool - Whether to use stack architecture
        'pattern': str - The detected pattern type
        'steps': list - Suggested resolution steps
    """
    text_lower = text.lower()

    result = {'use_stack': False, 'pattern': None, 'steps': []}

    # Pattern 1: Search deck effects
    search_keywords = ['search your deck', 'look at your deck', 'search your discard']
    if any(k in text_lower for k in search_keywords):
        result['use_stack'] = True
        result['pattern'] = 'SEARCH_DECK'
        result['steps'].append('SearchDeckStep')

        # Check for shuffle requirement
        if 'shuffle' in text_lower:
            result['steps'].append('shuffle_after=True')

    # Pattern 2: Discard cost before effect
    discard_cost_patterns = [
        'discard 2', 'discard 3', 'discard a card', 'discard cards from your hand'
    ]
    if any(p in text_lower for p in discard_cost_patterns):
        if result['use_stack']:
            # Discard is a cost before search
            result['steps'].insert(0, 'SelectFromZoneStep (DISCARD_COST)')
        else:
            result['use_stack'] = True
            result['pattern'] = 'DISCARD_COST'
            result['steps'].append('SelectFromZoneStep (DISCARD_COST)')

    # Pattern 3: Select target Pokemon
    select_target_patterns = [
        'choose a pokemon', 'choose one of your', 'select a pokemon',
        'put onto', 'evolve', '1 of your'
    ]
    if any(p in text_lower for p in select_target_patterns):
        if not result['use_stack']:
            result['use_stack'] = True
            result['pattern'] = 'SELECT_TARGET'
        result['steps'].append('SelectFromZoneStep (target selection)')

    # Pattern 4: Energy attachment from deck/discard
    if ('attach' in text_lower and
        ('from your deck' in text_lower or 'from your discard' in text_lower)):
        result['use_stack'] = True
        result['pattern'] = 'SEARCH_AND_ATTACH'
        result['steps'] = ['SearchAndAttachState (use InterruptPhase.SELECT_COUNT for upfront selection)']

    # Pattern 5: Move/switch Pokemon
    if 'switch' in text_lower and 'your active pokemon' in text_lower:
        result['use_stack'] = True
        result['pattern'] = 'SWITCH_POKEMON'
        result['steps'].append('SelectFromZoneStep (BENCH -> ACTIVE)')

    return result


# --- CLASSIFICATION LOGIC ---

def classify_text_pillar(text: str, subtypes: tuple) -> str:
    """Classify logic into one of the 4 Architectural Pillars."""
    text_lower = text.lower()

    # 0. HOOKS (Triggered Events - check FIRST for "when you play" patterns)
    # These take priority over "once during your turn" because they're triggered events
    # Example: "Once during your turn, when you play this Pokemon..." = HOOK (not ACTION)
    hook_keywords = [
        'when you play this pokemon',
        'when this pokemon is knocked out',
        'when you attach',
        'put this card into'
    ]
    for k in hook_keywords:
        if k in text_lower:
            return 'HOOK'

    # 1. ACTIONS (Player-activated abilities)
    # "Once during your turn, you may..." WITHOUT a trigger is a player-activated ability
    action_keywords = [
        'once during your turn',
        'you may use',
        'as often as you like during your turn',
    ]
    for k in action_keywords:
        if k in text_lower:
            return 'ACTION'

    # 2. MODIFIERS (Changes Numbers)
    # Note: Some patterns have numbers in between (e.g., "takes 30 less damage")
    modifier_keywords = [
        'retreat cost is', 'less retreat cost', 'more retreat cost',
        'takes less damage', 'takes more damage', 'maximum hp', 'get +',
        'attacks do', 'deal more damage', 'hp is', 'bench size', 'have no retreat cost',
        'has no retreat cost',  # Charmander's Agile
        'no retreat cost',  # General pattern
        'less damage from attacks', 'more damage from attacks',  # Handles "takes X less damage from attacks"
        'damage done to this', 'damage from attacks',  # Other damage modifier patterns
    ]
    for k in modifier_keywords:
        if k in text_lower:
            return 'MODIFIER'

    # 3. GUARDS (Blocks Permissions/Rules)
    guard_keywords = [
        'prevent all damage', 'prevent all effects', "can't be affected",
        "can't be asleep", "can't be paralyzed", "can't be confused",
        "can't be burned", "can't be poisoned", "opponent can't play",
        "cannot play", "prevent all damage"
    ]
    for k in guard_keywords:
        if k in text_lower:
            return 'GUARD'

    # 4. Additional HOOKS (lower priority triggered events)
    # These are checked after modifiers/guards but still represent automatic triggers
    additional_hook_keywords = [
        'whenever',
        'after you',
    ]
    for k in additional_hook_keywords:
        if k in text_lower:
            return 'HOOK'

    # 5. ACTIONS (Default)
    return 'ACTION'


# --- NORMALIZATION & HELPERS ---

def normalize_card(card: Dict[str, Any]) -> tuple:
    name = card.get('name', '')
    hp = card.get('hp', 0)
    supertype = card.get('supertype', '')
    subtypes = tuple(sorted(card.get('subtypes', [])))
    
    abilities = []
    for ab in card.get('abilities', []):
        abilities.append((ab.get('name', ''), ab.get('text', '')))
    abilities = tuple(sorted(abilities))

    attacks = []
    for atk in card.get('attacks', []):
        attacks.append((atk.get('name', ''), atk.get('text', '')))
    attacks = tuple(sorted(attacks))

    rules = tuple(card.get('rules', []))

    return (name, hp, supertype, subtypes, abilities, attacks, rules)


def group_duplicates(cards: List[Dict[str, Any]]) -> Dict[tuple, List[Dict[str, Any]]]:
    groups = defaultdict(list)
    for card in cards:
        signature = normalize_card(card)
        groups[signature].append(card)
    return dict(groups)


def extract_set_info(card: Dict[str, Any]) -> tuple:
    card_id = card.get('id', '')
    set_id = card_id.split('-')[0] if '-' in card_id else 'unknown'
    return set_id


def find_first_release(cards: List[Dict[str, Any]]) -> Dict[str, Any]:
    return cards[0]


def to_snake_case(name: str) -> str:
    return name.lower().replace(' ', '_').replace('-', '_').replace("'", '').replace('.', '')


def format_energy_cost(cost: List[str]) -> str:
    if not cost: return "[]"
    mapping = {'Colorless':'C','Water':'W','Fire':'F','Grass':'G','Lightning':'L',
               'Psychic':'P','Fighting':'R','Darkness':'D','Metal':'M','Dragon':'N','Fairy':'Y'}
    return '[' + ''.join(mapping.get(e, e[0]) for e in cost) + ']'


# --- PROMPT GENERATION ---

def generate_prompt(card_name: str, cards_data: Dict[str, Any]) -> str:
    matching_cards = [c for c in cards_data['cards'] if c.get('name', '').lower() == card_name.lower()]
    
    if not matching_cards:
        return f"ERROR: No cards found with name '{card_name}'"

    card_groups = group_duplicates(matching_cards)
    card_snake = to_snake_case(card_name)
    
    prompt = f"# {card_name} Implementation\n\n"
    prompt += "Implement this card using the **Unified Ability Schema** and **Stack Architecture** (when applicable).\n\n"
    prompt += "## Architecture Overview\n\n"
    prompt += "### Unified Ability Schema\n"
    prompt += "Every attack/ability is registered under its exact name with a `category` field:\n"
    prompt += "- **attack**: Deals damage, has energy cost, generates actions\n"
    prompt += "- **activatable**: Player-triggered ability, generates actions\n"
    prompt += "- **modifier**: Continuously modifies values (retreat cost, damage, HP)\n"
    prompt += "- **guard**: Blocks effects/conditions (status, damage, trainer cards)\n"
    prompt += "- **hook**: Event-triggered (on_play, on_knockout, etc.)\n\n"
    prompt += "### Multi-Effect Abilities\n"
    prompt += "When an ability has multiple effects, use suffixed entries:\n"
    prompt += "```python\n"
    prompt += '"Ability Name (Modifier)": {"category": "modifier", ...},\n'
    prompt += '"Ability Name (Guard)": {"category": "guard", ...},\n'
    prompt += "```\n\n"
    prompt += "### Stack Architecture (for multi-step effects)\n"
    prompt += "Use when effects require sequential decisions or costs:\n"
    prompt += "- **SearchDeckStep**: Search deck for cards matching filter criteria\n"
    prompt += "- **SelectFromZoneStep**: Select cards from hand/bench/board with filters\n"
    prompt += "- Push steps onto `state.push_step(step)` - they resolve in LIFO order\n"
    prompt += "- Use `on_complete_callback` for chaining steps\n\n"
    prompt += "### Registry Structure\n"
    prompt += "- **Pokemon Attacks/Abilities:** Use the exact name as the dictionary key.\n"
    prompt += "- **Trainers:** Use `\"actions\": {\"play\": ...}`.\n\n"

    for version_num, (signature, duplicate_cards) in enumerate(card_groups.items(), 1):
        first_card = find_first_release(duplicate_cards)
        original_set_id = extract_set_info(first_card)
        supertype = first_card.get('supertype', '')
        subtypes = first_card.get('subtypes', [])
        subtype_str = f"({', '.join(subtypes)})" if subtypes else ""
        
        if len(card_groups) > 1:
            prompt += f"## Version {version_num}\n\n"

        # Headers
        hp = first_card.get('hp', 'N/A')
        card_ids = [c.get('id', '') for c in duplicate_cards]
        prompt += f"**Card IDs:** {', '.join(card_ids)} | **Type:** {supertype} {subtype_str} | **HP:** {hp}\n\n"

        # Track functions to import later
        generated_functions = []

        # --- CONTENT EXTRACTION ---
        features = []

        if supertype == 'Trainer':
            text_lines = first_card.get('rules', [])
            full_text = " ".join(text_lines)

            # Decide Pillar
            if any(s in subtypes for s in ['Supporter', 'Item']):
                pillar = 'ACTION'
            else:
                pillar = classify_text_pillar(full_text, subtypes)

            # Detect Stack Architecture needs
            stack_info = detect_stack_pattern(full_text)

            features.append({
                'name': 'play' if pillar == 'ACTION' else card_snake,
                'snake': card_snake,
                'pillar': pillar,
                'text': full_text,
                'is_attack': False,
                'stack_info': stack_info
            })

        else: # Pokémon
            for ab in first_card.get('abilities', []):
                ab_text = ab.get('text', '')
                features.append({
                    'name': ab.get('name', ''),
                    'snake': to_snake_case(ab.get('name', '')),
                    'pillar': classify_text_pillar(ab_text, subtypes),
                    'text': ab_text,
                    'is_attack': False,
                    'stack_info': detect_stack_pattern(ab_text)
                })
            for atk in first_card.get('attacks', []):
                atk_text = atk.get('text', '')
                features.append({
                    'name': atk.get('name', ''),
                    'snake': to_snake_case(atk.get('name', '')),
                    'pillar': 'ACTION',
                    'text': atk_text,
                    'cost': format_energy_cost(atk.get('cost', [])),
                    'damage': atk.get('damage', ''),
                    'is_attack': True,
                    'stack_info': detect_stack_pattern(atk_text)
                })

        # --- PROMPT GENERATION LOOP ---
        for f in features:
            stack_info = f.get('stack_info', {'use_stack': False})

            if f['is_attack']:
                # Attack
                gen_func = f"{card_snake}_{f['snake']}_actions"
                eff_func = f"{card_snake}_{f['snake']}_effect"
                generated_functions.extend([gen_func, eff_func])

                prompt += f"### Attack: {f['name']} {f['cost']} {f['damage']}\n"
                if f['text']: prompt += f"_{f['text']}_\n"
                prompt += f"- Implement `{gen_func}` and `{eff_func}`.\n"

                # Add Stack Architecture guidance if detected
                if stack_info['use_stack']:
                    prompt += f"\n**Stack Architecture Required** (Pattern: `{stack_info['pattern']}`)\n"
                    prompt += "Resolution Steps:\n"
                    for step in stack_info['steps']:
                        prompt += f"  - `{step}`\n"
                prompt += "\n"
            else:
                # Ability / Trainer
                prompt += f"### Feature: {f['name']} ({f['pillar']})\n"
                if f['text']: prompt += f"_{f['text']}_\n\n"

                if f['pillar'] == 'MODIFIER':
                    func = f"{card_snake}_modifier" if supertype == 'Trainer' else f"{card_snake}_{f['snake']}_modifier"
                    generated_functions.append(func)
                    prompt += f"- Implement `{func}(state, card, current_value)`\n"

                elif f['pillar'] == 'GUARD':
                    func = f"{card_snake}_guard" if supertype == 'Trainer' else f"{card_snake}_{f['snake']}_guard"
                    generated_functions.append(func)
                    prompt += f"- Implement `{func}(state, card, context)`\n"

                elif f['pillar'] == 'HOOK':
                    func = f"{card_snake}_hook" if supertype == 'Trainer' else f"{card_snake}_{f['snake']}_hook"
                    generated_functions.append(func)
                    prompt += f"- Implement `{func}(state, card, context)`\n"

                    # Add Stack Architecture guidance for hooks if detected
                    if stack_info['use_stack']:
                        prompt += f"\n**Stack Architecture Required** (Pattern: `{stack_info['pattern']}`)\n"
                        prompt += "Resolution Steps:\n"
                        for step in stack_info['steps']:
                            prompt += f"  - `{step}`\n"

                else: # ACTION
                    if supertype == 'Trainer':
                        gen_func = f"{card_snake}_actions"
                        eff_func = f"{card_snake}_effect"
                    else:
                        gen_func = f"{card_snake}_{f['snake']}_actions"
                        eff_func = f"{card_snake}_{f['snake']}_effect"

                    generated_functions.extend([gen_func, eff_func])

                    prompt += f"- Implement `{gen_func}(state, card, player)` (Generator)\n"
                    prompt += f"- Implement `{eff_func}(state, card, action)` (Effect)\n"

                    if "once during your turn" in f['text'].lower():
                        prompt += f"  - **Requirement:** Check usage flags for Once Per Turn.\n"

                    # Add Stack Architecture guidance for actions if detected
                    if stack_info['use_stack']:
                        prompt += f"\n**Stack Architecture Required** (Pattern: `{stack_info['pattern']}`)\n"
                        prompt += "The effect function should push resolution steps onto the stack:\n"
                        prompt += "```python\n"
                        prompt += "def effect(state, card, action):\n"
                        prompt += "    from models import SearchDeckStep, SelectFromZoneStep, ZoneType, SelectionPurpose\n"
                        prompt += "    # Push steps in reverse order (LIFO)\n"
                        for step in reversed(stack_info['steps']):
                            prompt += f"    # {step}\n"
                        prompt += "    state.push_step(step)\n"
                        prompt += "    return state\n"
                        prompt += "```\n"
                        prompt += "Resolution Steps:\n"
                        for step in stack_info['steps']:
                            prompt += f"  - `{step}`\n"

                prompt += "\n"


        # --- HELPER: LOGIC DICT GENERATOR (Unified Schema) ---
        def generate_logic_dict(set_label, target_ids):
            out = f"### Registry (`{set_label}.py`)\n"

            # Imports
            if set_label != original_set_id:
                out += "```python\n"
                out += f"from cards.sets.{original_set_id} import (\n"
                for fn in generated_functions:
                    out += f"    {fn},\n"
                out += ")\n\n"
            else:
                out += "```python\n"

            out += f"{set_label.upper().replace('-', '_')}_LOGIC = {{\n"

            for cid in target_ids:
                out += f'    "{cid}": {{\n'

                # Process all features with unified schema (category field)
                for f in features:
                    if f['is_attack']:
                        # Attack with category
                        gen = f"{card_snake}_{f['snake']}_actions"
                        eff = f"{card_snake}_{f['snake']}_effect"
                        out += f'        "{f["name"]}": {{\n'
                        out += f'            "category": "attack",\n'
                        out += f'            "generator": {gen},\n'
                        out += f'            "effect": {eff},\n'
                        out += f'        }},\n'

                    elif f['pillar'] == 'ACTION':
                        # Activatable ability
                        if supertype == 'Trainer':
                            gen = f"{card_snake}_actions"
                            eff = f"{card_snake}_effect"
                            out += '        "actions": {\n'
                            out += f'            "play": {{"category": "activatable", "generator": {gen}, "effect": {eff}}},\n'
                            out += '        },\n'
                        else:
                            gen = f"{card_snake}_{f['snake']}_actions"
                            eff = f"{card_snake}_{f['snake']}_effect"
                            out += f'        "{f["name"]}": {{\n'
                            out += f'            "category": "activatable",\n'
                            out += f'            "generator": {gen},\n'
                            out += f'            "effect": {eff},\n'
                            out += f'        }},\n'

                    elif f['pillar'] == 'MODIFIER':
                        # Modifier ability
                        modifier_type = "retreat_cost" if "retreat" in f['text'].lower() else "damage_taken"
                        if "hp" in f['text'].lower(): modifier_type = "max_hp"

                        func = f"{card_snake}_modifier" if supertype == 'Trainer' else f"{card_snake}_{f['snake']}_modifier"
                        out += f'        "{f["name"]}": {{\n'
                        out += f'            "category": "modifier",\n'
                        out += f'            "modifier_type": "{modifier_type}",\n'
                        out += f'            "scope": "self",\n'
                        out += f'            "effect": {func},\n'
                        out += f'        }},\n'

                    elif f['pillar'] == 'GUARD':
                        # Guard ability
                        guard_type = "status_condition" if any(s in f['text'].lower() for s in ["asleep", "paralyzed", "confused", "burned", "poisoned"]) else "damage"

                        func = f"{card_snake}_guard" if supertype == 'Trainer' else f"{card_snake}_{f['snake']}_guard"
                        out += f'        "{f["name"]}": {{\n'
                        out += f'            "category": "guard",\n'
                        out += f'            "guard_type": "{guard_type}",\n'
                        out += f'            "scope": "self",\n'
                        out += f'            "effect": {func},\n'
                        out += f'        }},\n'

                    elif f['pillar'] == 'HOOK':
                        # Hook ability
                        trigger = "on_play" if "play" in f['text'].lower() else "on_knockout" if "knocked out" in f['text'].lower() else "on_event"

                        func = f"{card_snake}_hook" if supertype == 'Trainer' else f"{card_snake}_{f['snake']}_hook"
                        out += f'        "{f["name"]}": {{\n'
                        out += f'            "category": "hook",\n'
                        out += f'            "trigger": "{trigger}",\n'
                        out += f'            "effect": {func},\n'
                        out += f'        }},\n'

                out += f'    }},\n'

            out += "}\n```\n\n"
            return out

        # --- GENERATE ORIGINAL SET ---
        original_ids = [c.get('id', '') for c in duplicate_cards if extract_set_info(c) == original_set_id]
        prompt += generate_logic_dict(original_set_id, original_ids)

        # --- GENERATE REPRINTS ---
        other_sets = sorted(list(set(extract_set_info(c) for c in duplicate_cards if extract_set_info(c) != original_set_id)))
        
        if other_sets:
            prompt += "**Reprints:**\n\n"
            for reprint_set in other_sets:
                reprint_ids = [c.get('id', '') for c in duplicate_cards if extract_set_info(c) == reprint_set]
                prompt += generate_logic_dict(reprint_set, reprint_ids)

    return prompt

def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_card_prompt.py \"Card Name\"")
        sys.exit(1)

    card_name = sys.argv[1]
    data_file = Path("data/standard_cards.json")
    
    if not data_file.exists():
        print(f"ERROR: {data_file} not found")
        sys.exit(1)

    with open(data_file, 'r', encoding='utf-8') as f:
        cards_data = json.load(f)

    prompt = generate_prompt(card_name, cards_data)

    output_dir = Path("prompts")
    output_dir.mkdir(exist_ok=True)
    safe_name = card_name.replace(' ', '_').replace('/', '_').replace('\\', '_')
    output_file = output_dir / f"{safe_name}.txt"

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(prompt)

    print(f"[OK] Generated prompt for {card_name} at {output_file}")
    print("\n" + prompt)

if __name__ == '__main__':
    main()
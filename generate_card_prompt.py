"""
Generate AI implementation prompts for Pokemon TCG cards (Pokemon & Trainers)

Features:
- "4 Pillars" Architecture (Actions, Modifiers, Guards, Hooks)
- HYBRID DICT STRUCTURE:
    - Pokemon: "Attack Name": {generator, effect}
    - Trainers: "actions": {"play": {generator, effect}}
- Automatic Reprints handling
- Fixes formatting issues

Usage:
    python generate_card_prompt.py "Charmander"
    python generate_card_prompt.py "Iono"
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Any
from collections import defaultdict

# --- CLASSIFICATION LOGIC ---

def classify_text_pillar(text: str, subtypes: tuple) -> str:
    """Classify logic into one of the 4 Architectural Pillars."""
    text_lower = text.lower()

    # 1. MODIFIERS (Changes Numbers)
    modifier_keywords = [
        'retreat cost is', 'less retreat cost', 'more retreat cost',
        'takes less damage', 'takes more damage', 'maximum hp', 'get +',
        'attacks do', 'deal more damage', 'hp is', 'bench size', 'have no retreat cost'
    ]
    for k in modifier_keywords:
        if k in text_lower:
            return 'MODIFIER'

    # 2. GUARDS (Blocks Permissions/Rules)
    guard_keywords = [
        'prevent all damage', 'prevent all effects', "can't be affected",
        "can't be asleep", "can't be paralyzed", "can't be confused",
        "can't be burned", "can't be poisoned", "opponent can't play",
        "cannot play", "prevent all damage"
    ]
    for k in guard_keywords:
        if k in text_lower:
            return 'GUARD'

    # 3. HOOKS (Triggered Events)
    hook_keywords = [
        'when you play this pokemon', 'when this pokemon is knocked out',
        'whenever', 'after you', 'when you attach', 'if this pokemon is in the active spot',
        'put this card into' 
    ]
    for k in hook_keywords:
        if k in text_lower:
            return 'HOOK'

    # 4. ACTIONS (Default)
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
    prompt += "Implement this card using the **4 Pillars Architecture**.\n"
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

            features.append({
                'name': 'play' if pillar == 'ACTION' else card_snake, 
                'snake': card_snake,
                'pillar': pillar,
                'text': full_text,
                'is_attack': False
            })

        else: # Pokémon
            for ab in first_card.get('abilities', []):
                features.append({
                    'name': ab.get('name', ''),
                    'snake': to_snake_case(ab.get('name', '')),
                    'pillar': classify_text_pillar(ab.get('text', ''), subtypes),
                    'text': ab.get('text', ''),
                    'is_attack': False
                })
            for atk in first_card.get('attacks', []):
                features.append({
                    'name': atk.get('name', ''),
                    'snake': to_snake_case(atk.get('name', '')),
                    'pillar': 'ACTION',
                    'text': atk.get('text', ''),
                    'cost': format_energy_cost(atk.get('cost', [])),
                    'damage': atk.get('damage', ''),
                    'is_attack': True
                })

        # --- PROMPT GENERATION LOOP ---
        for f in features:
            if f['is_attack']:
                # Attack
                gen_func = f"{card_snake}_{f['snake']}_actions"
                eff_func = f"{card_snake}_{f['snake']}_effect"
                generated_functions.extend([gen_func, eff_func])
                
                prompt += f"### Attack: {f['name']} {f['cost']} {f['damage']}\n"
                if f['text']: prompt += f"_{f['text']}_\n"
                prompt += f"- Implement `{gen_func}` and `{eff_func}`.\n\n"
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
                
                prompt += "\n"


        # --- HELPER: LOGIC DICT GENERATOR ---
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
                
                # 1. POKEMON ACTIONS (Top Level Keys)
                if supertype != 'Trainer':
                    for f in features:
                        if f['pillar'] == 'ACTION':
                            # Use NAME as key (Title Case)
                            gen = f"{card_snake}_{f['snake']}_actions"
                            eff = f"{card_snake}_{f['snake']}_effect"
                            out += f'        "{f["name"]}": {{"generator": {gen}, "effect": {eff}}},\n'

                # 2. TRAINER ACTIONS (Nested in 'actions')
                if supertype == 'Trainer':
                    trainer_actions = [f for f in features if f['pillar'] == 'ACTION']
                    if trainer_actions:
                        out += '        "actions": {\n'
                        for f in trainer_actions:
                            gen = f"{card_snake}_actions"
                            eff = f"{card_snake}_effect"
                            out += f'            "play": {{"generator": {gen}, "effect": {eff}}},\n'
                        out += '        },\n'

                # 3. MODIFIERS (Standard Key)
                modifiers = [f for f in features if f['pillar'] == 'MODIFIER']
                if modifiers:
                    out += '        "modifiers": {\n'
                    for mod in modifiers:
                        key = "retreat_cost" if "retreat" in mod['text'].lower() else "damage"
                        if "hp" in mod['text'].lower(): key = "max_hp"
                        
                        func = f"{card_snake}_modifier" if supertype == 'Trainer' else f"{card_snake}_{mod['snake']}_modifier"
                        out += f'            "{key}": {func},\n'
                    out += '        },\n'

                # 4. GUARDS (Standard Key)
                guards = [f for f in features if f['pillar'] == 'GUARD']
                if guards:
                    out += '        "guards": {\n'
                    for g in guards:
                        key = "status_condition" if "asleep" in g['text'].lower() else "effect_prevention"
                        func = f"{card_snake}_guard" if supertype == 'Trainer' else f"{card_snake}_{g['snake']}_guard"
                        out += f'            "{key}": {func},\n'
                    out += '        },\n'

                # 5. HOOKS (Standard Key)
                hooks = [f for f in features if f['pillar'] == 'HOOK']
                if hooks:
                    out += '        "hooks": {\n'
                    for h in hooks:
                        key = "on_play_pokemon" if "play" in h['text'].lower() else "on_knockout"
                        func = f"{card_snake}_hook" if supertype == 'Trainer' else f"{card_snake}_{h['snake']}_hook"
                        out += f'            "{key}": {func},\n'
                    out += '        },\n'

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
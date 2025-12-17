"""
Generate AI implementation prompts for Pokemon TCG cards

Creates concise implementation prompts aligned with the "4 Pillars" Architecture.
Ensures reprints are explicitly handled with correct imports and set IDs.

Usage:
    python generate_card_prompt.py "Teal Mask Ogerpon ex"
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Any
from collections import defaultdict

# --- CLASSIFICATION LOGIC ---

def classify_ability_pillar(text: str) -> str:
    """Classify ability into one of the 4 Architectural Pillars."""
    text_lower = text.lower()

    # 1. MODIFIERS (Changes Numbers)
    modifier_keywords = [
        'retreat cost is', 'less retreat cost', 'more retreat cost',
        'takes less damage', 'takes more damage', 'maximum hp',
        'attacks do', 'deal more damage', 'hp is', 'bench size'
    ]
    for k in modifier_keywords:
        if k in text_lower:
            return 'MODIFIER'

    # 2. GUARDS (Blocks Permissions/Rules)
    guard_keywords = [
        'prevent all damage', 'prevent all effects', "can't be affected",
        "can't be asleep", "can't be paralyzed", "can't be confused",
        "can't be burned", "can't be poisoned", "opponent can't play",
        "cannot play", "no retreat cost" 
    ]
    for k in guard_keywords:
        if k in text_lower:
            if "no retreat cost" in k: return 'MODIFIER'
            return 'GUARD'

    # 3. HOOKS (Triggered Events)
    hook_keywords = [
        'when you play this pokemon', 'when this pokemon is knocked out',
        'whenever', 'after you', 'when you attach', 'if this pokemon is in the active spot'
    ]
    for k in hook_keywords:
        if k in text_lower:
            return 'HOOK'

    # 4. ACTIONS (Default - Active User Choice)
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

    return (name, hp, supertype, subtypes, abilities, attacks)


def group_duplicates(cards: List[Dict[str, Any]]) -> Dict[tuple, List[Dict[str, Any]]]:
    groups = defaultdict(list)
    for card in cards:
        signature = normalize_card(card)
        groups[signature].append(card)
    return dict(groups)


def extract_set_info(card: Dict[str, Any]) -> tuple:
    card_id = card.get('id', '')
    set_id = card_id.split('-')[0] if '-' in card_id else 'unknown'
    release_date = card.get('set', {}).get('releaseDate', '9999-99-99')
    return set_id, release_date


def find_first_release(cards: List[Dict[str, Any]]) -> Dict[str, Any]:
    return min(cards, key=lambda c: extract_set_info(c)[1])


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
    prompt += "Implement this card using the **4 Pillars Architecture**.\n\n"

    for version_num, (signature, duplicate_cards) in enumerate(card_groups.items(), 1):
        first_card = find_first_release(duplicate_cards)
        original_set_id, _ = extract_set_info(first_card)
        
        if len(card_groups) > 1:
            prompt += f"## Version {version_num}\n\n"

        # Headers
        hp = first_card.get('hp', 'N/A')
        card_ids = [c.get('id', '') for c in duplicate_cards]
        prompt += f"**Card IDs:** {', '.join(card_ids)} | **HP:** {hp}\n\n"

        # Track functions to import later
        generated_functions = []

        # --- ABILITIES ---
        abilities_info = [] 
        
        if first_card.get('abilities'):
            for ab in first_card['abilities']:
                ab_name = ab.get('name', '')
                ab_text = ab.get('text', '')
                ab_snake = to_snake_case(ab_name)
                pillar = classify_ability_pillar(ab_text)
                
                abilities_info.append({'name': ab_name, 'snake': ab_snake, 'pillar': pillar, 'text': ab_text})

                prompt += f"### Ability: {ab_name} ({pillar})\n_{ab_text}_\n\n"
                
                if pillar == 'MODIFIER':
                    func = f"{card_snake}_{ab_snake}_modifier"
                    generated_functions.append(func)
                    prompt += f"- Implement `{func}(state, card, current_value)`\n"
                elif pillar == 'GUARD':
                    func = f"{card_snake}_{ab_snake}_guard"
                    generated_functions.append(func)
                    prompt += f"- Implement `{func}(state, card, context)`\n"
                elif pillar == 'HOOK':
                    func = f"{card_snake}_{ab_snake}_hook"
                    generated_functions.append(func)
                    prompt += f"- Implement `{func}(state, card, context)`\n"
                else: # ACTION
                    gen_func = f"{card_snake}_{ab_snake}_actions"
                    eff_func = f"{card_snake}_{ab_snake}_effect"
                    generated_functions.extend([gen_func, eff_func])
                    
                    prompt += f"- Implement `{gen_func}(state, card, player)` (Generator)\n"
                    # Safety Checks
                    if "once during your turn" in ab_text.lower():
                         prompt += f"  - **Requirement:** Check `'{ab_snake}' not in card.abilities_used_this_turn`\n"
                         prompt += f"  - **Requirement:** Check card is in play (Active/Bench)\n"
                    prompt += f"- Implement `{eff_func}(state, card, action)` (Effect)\n"
                    if "once during your turn" in ab_text.lower():
                        prompt += f"  - **Update:** Add `'{ab_snake}'` to `card.abilities_used_this_turn`\n"
                
                prompt += "\n"

        # --- ATTACKS ---
        attacks_info = []
        if first_card.get('attacks'):
            for atk in first_card['attacks']:
                atk_name = atk.get('name', '')
                atk_snake = to_snake_case(atk_name)
                cost = format_energy_cost(atk.get('cost', []))
                dmg = atk.get('damage', '')
                text = atk.get('text', '')
                
                attacks_info.append({'name': atk_name, 'snake': atk_snake})
                
                gen_func = f"{card_snake}_{atk_snake}_actions"
                eff_func = f"{card_snake}_{atk_snake}_effect"
                generated_functions.extend([gen_func, eff_func])

                prompt += f"### Attack: {atk_name} {cost} {dmg}\n_{text}_\n"
                prompt += f"- Implement `{gen_func}` and `{eff_func}`.\n\n"

        # --- HELPER: LOGIC DICT GENERATOR ---
        def generate_logic_dict(set_label, target_ids):
            out = f"### Registry (`{set_label}.py`)\n"
            
            # Add Imports for reprints
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
                
                # 1. ACTIONS
                actions_entries = []
                for atk in attacks_info:
                    actions_entries.append(f'            "{atk["snake"]}": {{"generator": {card_snake}_{atk["snake"]}_actions, "effect": {card_snake}_{atk["snake"]}_effect}}')
                for ab in abilities_info:
                    if ab['pillar'] == 'ACTION':
                        actions_entries.append(f'            "{ab["snake"]}": {{"generator": {card_snake}_{ab["snake"]}_actions, "effect": {card_snake}_{ab["snake"]}_effect}}')

                if actions_entries:
                    out += '        "actions": {\n'
                    out += ",\n".join(actions_entries) + "\n"
                    out += '        },\n'

                # 2. MODIFIERS
                modifiers = [ab for ab in abilities_info if ab['pillar'] == 'MODIFIER']
                if modifiers:
                    out += '        "modifiers": {\n'
                    for mod in modifiers:
                        key = "retreat_cost" if "retreat" in mod['text'].lower() else "damage"
                        out += f'            "{key}": {card_snake}_{mod["snake"]}_modifier,\n'
                    out += '        },\n'

                # 3. GUARDS
                guards = [ab for ab in abilities_info if ab['pillar'] == 'GUARD']
                if guards:
                    out += '        "guards": {\n'
                    for g in guards:
                        key = "status_condition" if "asleep" in g['text'].lower() else "effect_prevention"
                        out += f'            "{key}": {card_snake}_{g["snake"]}_guard,\n'
                    out += '        },\n'

                # 4. HOOKS
                hooks = [ab for ab in abilities_info if ab['pillar'] == 'HOOK']
                if hooks:
                    out += '        "hooks": {\n'
                    for h in hooks:
                        key = "on_play_pokemon" if "play" in h['text'].lower() else "on_knockout"
                        out += f'            "{key}": {card_snake}_{h["snake"]}_hook,\n'
                    out += '        },\n'

                out += f'    }},\n'
                
            out += "}\n```\n\n"
            return out

        # --- GENERATE ORIGINAL SET ---
        original_ids = [c.get('id', '') for c in duplicate_cards if extract_set_info(c)[0] == original_set_id]
        prompt += generate_logic_dict(original_set_id, original_ids)

        # --- GENERATE REPRINTS ---
        other_sets = sorted(list(set(extract_set_info(c)[0] for c in duplicate_cards if extract_set_info(c)[0] != original_set_id)))
        
        if other_sets:
            prompt += "**Reprints:**\n\n"
            for reprint_set in other_sets:
                reprint_ids = [c.get('id', '') for c in duplicate_cards if extract_set_info(c)[0] == reprint_set]
                prompt += generate_logic_dict(reprint_set, reprint_ids)

    return prompt

# --- MAIN ---

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
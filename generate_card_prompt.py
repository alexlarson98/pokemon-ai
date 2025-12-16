"""
Generate AI implementation prompts for Pokemon TCG cards

This script analyzes cards from standard_cards.json and creates a detailed prompt
for implementing card logic following the architecture pattern:
- Define logic in the set where the card was FIRST released
- Other sets import the logic from the first set

Usage:
    python generate_card_prompt.py "Charmander"
    python generate_card_prompt.py "Pikachu ex"
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Any
from collections import defaultdict


def normalize_card(card: Dict[str, Any]) -> tuple:
    """
    Create a normalized tuple for comparing cards.
    Cards with same name, HP, abilities, attacks, subtypes, and supertype are duplicates.
    """
    name = card.get('name', '')
    hp = card.get('hp', 0)
    supertype = card.get('supertype', '')
    subtypes = tuple(sorted(card.get('subtypes', [])))

    # Normalize abilities
    abilities = []
    for ability in card.get('abilities', []):
        abilities.append((
            ability.get('name', ''),
            ability.get('type', ''),
            ability.get('text', '')
        ))
    abilities = tuple(sorted(abilities))

    # Normalize attacks
    attacks = []
    for attack in card.get('attacks', []):
        attacks.append((
            attack.get('name', ''),
            tuple(attack.get('cost', [])),
            attack.get('convertedEnergyCost', 0),
            attack.get('damage', ''),
            attack.get('text', '')
        ))
    attacks = tuple(sorted(attacks))

    return (name, hp, supertype, subtypes, abilities, attacks)


def group_duplicates(cards: List[Dict[str, Any]]) -> Dict[tuple, List[Dict[str, Any]]]:
    """
    Group cards by their normalized signature.
    Returns a dict mapping signature -> list of duplicate cards.
    """
    groups = defaultdict(list)

    for card in cards:
        signature = normalize_card(card)
        groups[signature].append(card)

    return dict(groups)


def extract_set_info(card: Dict[str, Any]) -> tuple:
    """Extract set ID from a card."""
    card_id = card.get('id', '')
    set_id = card_id.split('-')[0] if '-' in card_id else 'unknown'
    release_date = card.get('set', {}).get('releaseDate', '9999-99-99')  # For sorting

    return set_id, release_date


def find_first_release(cards: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Find the first released card among duplicates."""
    return min(cards, key=lambda c: extract_set_info(c)[1])


def format_energy_cost(cost: List[str]) -> str:
    """Format energy cost as [WW], [FC], etc."""
    if not cost:
        return "[]"

    # Map energy types to shorthand
    energy_map = {
        'Colorless': 'C',
        'Water': 'W',
        'Fire': 'F',
        'Grass': 'G',
        'Lightning': 'L',
        'Psychic': 'P',
        'Fighting': 'F',
        'Darkness': 'D',
        'Metal': 'M',
        'Dragon': 'N',
        'Fairy': 'Y'
    }

    shorthand = [energy_map.get(e, e[0].upper()) for e in cost]
    return '[' + ''.join(shorthand) + ']'


def generate_prompt(card_name: str, cards_data: Dict[str, Any]) -> str:
    """Generate the implementation prompt for a card."""

    # Find all cards with matching name
    matching_cards = [
        card for card in cards_data['cards']
        if card.get('name', '').lower() == card_name.lower()
    ]

    if not matching_cards:
        return f"ERROR: No cards found with name '{card_name}'"

    # Group duplicates
    card_groups = group_duplicates(matching_cards)

    # Build prompt
    prompt = f"# {card_name} - Implementation Guide\n\n"

    # Process each unique version
    for version_num, (signature, duplicate_cards) in enumerate(card_groups.items(), 1):
        if len(card_groups) > 1:
            prompt += f"## Version {version_num}\n\n"

        # Get representative card (first release)
        first_card = find_first_release(duplicate_cards)
        set_id, _ = extract_set_info(first_card)

        # Abilities
        if first_card.get('abilities'):
            prompt += "### Abilities\n\n"
            for ability in first_card['abilities']:
                ability_name = ability.get('name', 'Unknown')
                ability_type = ability.get('type', 'Unknown')
                ability_text = ability.get('text', '')

                prompt += f"**{ability_name}** ({ability_type})  \n"
                prompt += f"{ability_text}\n\n"

        # Attacks
        if first_card.get('attacks'):
            prompt += "### Attacks\n\n"
            for attack in first_card['attacks']:
                attack_name = attack.get('name', 'Unknown')
                energy_cost = attack.get('cost', [])
                damage = attack.get('damage', '')
                text = attack.get('text', '')

                prompt += f"**{attack_name}**  \n"

                # Explicitly state energy requirements
                if energy_cost:
                    # Count energy types
                    from collections import Counter
                    energy_counts = Counter(energy_cost)

                    energy_parts = []
                    for energy_type, count in sorted(energy_counts.items()):
                        if count == 1:
                            energy_parts.append(f"{count} {energy_type} energy")
                        else:
                            energy_parts.append(f"{count} {energy_type} energy")

                    prompt += f"Requires: {', '.join(energy_parts)}  \n"
                else:
                    prompt += f"Requires: No energy  \n"

                if damage:
                    prompt += f"Damage: {damage}  \n"
                if text:
                    prompt += f"Effect: {text}  \n"
                prompt += "\n"

        # Implementation section
        prompt += "---\n\n"
        prompt += "## Implementation\n\n"

        # Generate function names
        card_name_snake = card_name.lower().replace(' ', '_').replace('-', '_')
        ability_functions = []
        attack_functions = []

        if first_card.get('abilities'):
            for ability in first_card['abilities']:
                ability_name = ability.get('name', '').lower().replace(' ', '_').replace('-', '_')
                ability_functions.append(f"{card_name_snake}_{ability_name}_actions")
                ability_functions.append(f"{card_name_snake}_{ability_name}_effect")

        if first_card.get('attacks'):
            for attack in first_card['attacks']:
                attack_name = attack.get('name', '').lower().replace(' ', '_').replace('-', '_')
                attack_functions.append(f"{card_name_snake}_{attack_name}_actions")
                attack_functions.append(f"{card_name_snake}_{attack_name}_effect")

        # Function list
        prompt += f"### Define in: `src/cards/sets/{set_id}.py`\n\n"

        if ability_functions:
            prompt += "**Ability Functions:**\n"
            for func in ability_functions:
                prompt += f"- `{func}()`\n"
            prompt += "\n"

        if attack_functions:
            prompt += "**Attack Functions:**\n"
            for func in attack_functions:
                prompt += f"- `{func}()`\n"
            prompt += "\n"

        # Registry for primary set
        primary_set_cards = [c for c in duplicate_cards if extract_set_info(c)[0] == set_id]

        if primary_set_cards:
            prompt += f"**Registry ({set_id}.py):**\n```python\n"
            for card in primary_set_cards:
                cid = card.get('id', '')
                prompt += f'"{cid}": {{\n'

                if first_card.get('abilities'):
                    for ability in first_card['abilities']:
                        ability_name = ability.get('name', '')
                        ability_snake = ability_name.lower().replace(' ', '_').replace('-', '_')
                        prompt += f'    "{ability_name}": {{\n'
                        prompt += f'        "generator": {card_name_snake}_{ability_snake}_actions,\n'
                        prompt += f'        "effect": {card_name_snake}_{ability_snake}_effect,\n'
                        prompt += f'    }},\n'

                if first_card.get('attacks'):
                    for attack in first_card['attacks']:
                        attack_name = attack.get('name', '')
                        attack_snake = attack_name.lower().replace(' ', '_').replace('-', '_')
                        prompt += f'    "{attack_name}": {{\n'
                        prompt += f'        "generator": {card_name_snake}_{attack_snake}_actions,\n'
                        prompt += f'        "effect": {card_name_snake}_{attack_snake}_effect,\n'
                        prompt += f'    }},\n'

                prompt += "},\n"
            prompt += "```\n\n"

        # Reprint sets
        other_sets = sorted(set(extract_set_info(c)[0] for c in duplicate_cards if extract_set_info(c)[0] != set_id))

        if other_sets:
            prompt += "### Reprints (import from " + set_id + ".py):\n\n"

            for other_set_id in other_sets:
                other_set_cards = [c for c in duplicate_cards if extract_set_info(c)[0] == other_set_id]
                card_ids = [c.get('id', '') for c in other_set_cards]

                prompt += f"**{other_set_id}.py:** `{', '.join(card_ids)}`\n"

            prompt += "\n"

        prompt += "\n"

    return prompt


def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_card_prompt.py \"Card Name\"")
        print("Example: python generate_card_prompt.py \"Charmander\"")
        sys.exit(1)

    card_name = sys.argv[1]

    # Load card data
    data_file = Path("data/standard_cards.json")
    if not data_file.exists():
        print(f"ERROR: {data_file} not found")
        sys.exit(1)

    print(f"Loading card data from {data_file}...")
    with open(data_file, 'r', encoding='utf-8') as f:
        cards_data = json.load(f)

    print(f"Searching for '{card_name}'...")

    # Generate prompt
    prompt = generate_prompt(card_name, cards_data)

    # Save to file
    output_dir = Path("prompts")
    output_dir.mkdir(exist_ok=True)

    # Sanitize filename
    safe_filename = card_name.replace(' ', '_').replace('/', '_').replace('\\', '_')
    output_file = output_dir / f"{safe_filename}.txt"

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(prompt)

    print(f"\n[OK] Prompt generated: {output_file}")
    print(f"  Total length: {len(prompt)} characters")

    # Also print to console
    print("\n" + "=" * 80)
    print(prompt)


if __name__ == '__main__':
    main()

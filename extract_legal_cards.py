"""
Extract all Standard-legal cards from pokemon-tcg-data

Process:
1. Read all sets from sets/en.json
2. For each set, read cards/en/{setId}.json
3. Filter cards by regulation mark G, H, I (current Standard format)
4. Combine all Standard cards into a single standard_cards.json file
"""

import json
from pathlib import Path
from typing import Any
from datetime import datetime


def extract_standard_cards() -> None:
    """Extract all Standard-legal cards and save to data/standard_cards.json"""

    print("Starting Standard card extraction (Regulation G, H, I)...\n")

    # Paths
    project_root = Path(__file__).parent
    data_root = project_root.parent / project_root / "pokemon-tcg-data"
    sets_file = data_root / "sets" / "en.json"
    cards_dir = data_root / "cards" / "en"
    output_file = project_root / "data" / "standard_cards.json"

    # Step 1: Load all sets
    print(f"Reading sets from: {sets_file}")
    with open(sets_file, 'r', encoding='utf-8') as f:
        sets_data = json.load(f)
    print(f"   Found {len(sets_data)} total sets\n")

    # Step 2: We'll filter by regulation mark instead of set legalities
    print("Using regulation marks G, H, I for Standard legality")
    print("   (This is more accurate than set-level legalities)\n")

    # Step 3: Extract cards from each set
    # Filter by regulation mark G, H, I (current Standard format)
    all_cards = []
    stats = {
        'total_sets': len(sets_data),
        'sets_with_standard_cards': 0,
        'total_cards': 0,
        'cards_by_type': {'Pokémon': 0, 'Trainer': 0, 'Energy': 0},
        'cards_by_regulation': {},
        'set_ids': []
    }

    print("Extracting cards with regulation marks G, H, I...")
    for set_info in sets_data:
        cards_file = cards_dir / f"{set_info['id']}.json"

        if not cards_file.exists():
            continue

        with open(cards_file, 'r', encoding='utf-8') as f:
            set_cards = json.load(f)

        # Filter for cards with regulation mark G, H, or I (current Standard)
        # Also include basic energy (no regulation mark)
        standard_cards = []
        for card in set_cards:
            reg_mark = card.get('regulationMark')
            is_basic_energy = (
                card.get('supertype') == 'Energy' and
                'Basic' in card.get('subtypes', [])
            )

            if reg_mark in ['G', 'H', 'I'] or is_basic_energy:
                standard_cards.append(card)

        if len(standard_cards) > 0:
            all_cards.extend(standard_cards)
            stats['sets_with_standard_cards'] += 1
            if set_info['id'] not in stats['set_ids']:
                stats['set_ids'].append(set_info['id'])

            # Update stats
            for card in standard_cards:
                supertype = card.get('supertype', 'Unknown')
                stats['cards_by_type'][supertype] = stats['cards_by_type'].get(supertype, 0) + 1

                # Track regulation marks
                reg_mark = card.get('regulationMark', 'Basic Energy')
                stats['cards_by_regulation'][reg_mark] = stats['cards_by_regulation'].get(reg_mark, 0) + 1

            print(f"   OK {set_info['id']:12} {set_info.get('name', 'Unknown')[:30]:30} : {len(standard_cards):4} cards")

    stats['total_cards'] = len(all_cards)
    print()

    # Step 4: Write to output file
    print(f"Writing {len(all_cards)} cards to: {output_file.relative_to(project_root)}")

    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    output_data = {
        'metadata': {
            'extracted_at': datetime.now().isoformat(),
            'format': 'Standard (Regulation G, H, I)',
            'regulation_marks': ['G', 'H', 'I'],
            'stats': stats
        },
        'cards': all_cards
    }

    # Convert to JSON string first so we can clean unicode characters
    json_string = json.dumps(output_data, indent=2, ensure_ascii=True)

    # Replace escaped Unicode sequences in the JSON string
    json_string = json_string.replace('\\u00e9', 'e')  # é -> e
    json_string = json_string.replace('\\u00d7', 'x')  # × -> x
    json_string = json_string.replace('\\u00a0', ' ')  # non-breaking space -> space

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(json_string)

    # Step 5: Print summary
    print('\nExtraction complete!\n')
    print('Summary:')
    print(f"   Total cards: {stats['total_cards']}")
    print(f"   - Pokémon:   {stats['cards_by_type'].get('Pokémon', 0)}")
    print(f"   - Trainer:   {stats['cards_by_type'].get('Trainer', 0)}")
    print(f"   - Energy:    {stats['cards_by_type'].get('Energy', 0)}")
    print(f"\n   By Regulation Mark:")
    for mark in ['G', 'H', 'I', 'Basic Energy']:
        count = stats['cards_by_regulation'].get(mark, 0)
        if count > 0:
            print(f"   - {mark}: {count}")
    print(f"\n   Sets with Standard cards: {stats['sets_with_standard_cards']}")
    print(f"   Output file: {output_file.relative_to(project_root)}")
    print()


if __name__ == '__main__':
    try:
        extract_standard_cards()
    except Exception as e:
        print(f"ERROR: Error during extraction: {e}")
        raise

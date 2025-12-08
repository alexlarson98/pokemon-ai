"""
Pokémon TCG Engine - Card Audit Tool
Analyzes all cards in the database and categorizes them by logic requirements.

Updates:
- Added 'immediate_parent' column to verify raw JSON data.
- Validates evolution chains.
"""

import sys
import os
import json
import csv
import re
from collections import defaultdict, Counter
from typing import Dict, List, Optional, Set, Tuple

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cards.registry import _JSON_DATABASE


# ============================================================================
# KEYWORD DETECTION (Effect Triggers)
# ============================================================================

EFFECT_KEYWORDS = {
    'search': ['search', 'look at', 'reveal'],
    'draw': ['draw', 'put.*into.*hand'],
    'heal': ['heal', 'remove.*damage'],
    'damage': ['damage', 'place.*damage counter', 'put.*damage counter'],
    'switch': ['switch', 'retreat'],
    'discard': ['discard'],
    'attach': ['attach.*energy', 'attach.*card'],
    'evolve': ['evolve', 'evolution'],
    'prevent': ['prevent', 'protect', 'can.*t.*damage'],
    'lock': ['can.*t.*use', 'can.*t.*attack', 'can.*t.*retreat'],
    'coin_flip': ['flip.*coin'],
    'prize': ['prize', 'prize card'],
    'knockout': ['knock.*out', 'knocked out', 'ko'],
    'copy': ['copy', 'use.*attack'],
    'boost': ['\\+.*damage', 'more damage', 'does.*more'],
    'reduce': ['-.*damage', 'less damage', 'reduced'],
    'status': ['paralyze', 'poison', 'burn', 'confuse', 'asleep'],
    'special_condition': ['special condition'],
}


def detect_effect_triggers(text: str) -> List[str]:
    """Detect effect keywords in card text."""
    if not text:
        return []

    text_lower = text.lower()
    triggers = []

    for category, patterns in EFFECT_KEYWORDS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                triggers.append(category)
                break  # Only count each category once

    return triggers


# ============================================================================
# BATTLE STYLE / TAG DETECTION
# ============================================================================

def extract_battle_styles(card_data: Dict) -> List[str]:
    """Extract special tags/battle styles from card."""
    tags = []

    # Check subtypes
    subtypes = card_data.get('subtypes', [])
    if isinstance(subtypes, list):
        for subtype in subtypes:
            subtype_str = str(subtype).strip()

            # Special mechanics
            if 'ACE SPEC' in subtype_str.upper():
                tags.append('ACE SPEC')
            if 'Radiant' in subtype_str:
                tags.append('Radiant')
            if 'Ancient' in subtype_str:
                tags.append('Ancient')
            if 'Future' in subtype_str:
                tags.append('Future')

            # Evolution markers
            if 'ex' in subtype_str.lower() and subtype_str.lower() != 'basic':
                tags.append('ex')
            if subtype_str in ['V', 'VMAX', 'VSTAR']:
                tags.append(subtype_str)
            if 'GX' in subtype_str:
                tags.append('GX')

    # Check name for Tera
    name = card_data.get('name', '')
    if 'Tera' in name or 'Terastal' in name:
        tags.append('Tera')

    # Check rules for additional mechanics
    rules = card_data.get('rules', [])
    if isinstance(rules, list):
        rules_text = ' '.join(rules)
        if 'ACE SPEC' in rules_text:
            tags.append('ACE SPEC')
        if 'Radiant' in rules_text:
            tags.append('Radiant')

    return sorted(list(set(tags)))


# ============================================================================
# EVOLUTION CHAIN DETECTION
# ============================================================================

def find_evolution_root(card_data: Dict, all_cards: Dict[str, Dict]) -> Optional[str]:
    """Trace evolvesFrom chain to find the Basic Pokémon."""
    if card_data.get('supertype', '').lower() not in ['pokémon', 'pokemon']:
        return None

    subtypes = card_data.get('subtypes', [])
    if 'Basic' in subtypes:
        return card_data.get('name')  # This IS the root

    # Trace back through evolution chain
    evolves_from = card_data.get('evolvesFrom')
    if not evolves_from:
        return card_data.get('name')

    # Search for the Basic in the database
    visited = set()
    current_name = evolves_from

    while current_name and current_name not in visited:
        visited.add(current_name)

        # Find card by name
        found_card = None
        for card in all_cards.values():
            if card.get('name') == current_name:
                found_card = card
                break

        if not found_card:
            return current_name  # Can't find it, return the name we have

        # Check if Basic
        if 'Basic' in found_card.get('subtypes', []):
            return current_name

        # Continue tracing
        next_evolves_from = found_card.get('evolvesFrom')
        if not next_evolves_from:
            return current_name

        current_name = next_evolves_from

    return evolves_from  # Fallback


# ============================================================================
# LOGIC CATEGORY CLASSIFICATION
# ============================================================================

def classify_pokemon(card_data: Dict) -> str:
    """Classify Pokémon into logic categories."""
    abilities = card_data.get('abilities', [])
    attacks = card_data.get('attacks', [])
    rules = card_data.get('rules', [])

    if abilities:
        return 'complex'

    if rules:
        rules_text = ' '.join(rules) if isinstance(rules, list) else str(rules)
        if 'Ancient' in rules_text or 'Future' in rules_text:
            return 'complex'

    has_attack_text = False
    if attacks:
        for attack in attacks:
            attack_text = attack.get('text', '').strip()
            if attack_text:
                has_attack_text = True
                break

    if has_attack_text:
        return 'simple'

    return 'vanilla'


def classify_trainer(card_data: Dict) -> str:
    """Classify Trainer into logic categories."""
    subtypes = card_data.get('subtypes', [])
    if not subtypes:
        return 'unknown'
    subtype_str = ' '.join(subtypes).lower()

    if 'supporter' in subtype_str:
        return 'supporter'
    if 'stadium' in subtype_str:
        return 'stadium'
    if 'tool' in subtype_str or 'pokémon tool' in subtype_str:
        return 'tool'
    if 'item' in subtype_str:
        return 'item'
    return 'unknown'


def classify_energy(card_data: Dict) -> str:
    """Classify Energy into logic categories."""
    subtypes = card_data.get('subtypes', [])
    if 'Basic' in subtypes:
        return 'basic'
    if 'Special' in subtypes:
        return 'special'
    return 'unknown'


def classify_card(card_data: Dict) -> str:
    """Classify card into primary logic category."""
    supertype = card_data.get('supertype', '').lower()
    if supertype in ['pokémon', 'pokemon']:
        return classify_pokemon(card_data)
    elif supertype == 'trainer':
        return classify_trainer(card_data)
    elif supertype == 'energy':
        return classify_energy(card_data)
    return 'unknown'


# ============================================================================
# CARD ANALYSIS
# ============================================================================

def analyze_card(card_id: str, card_data: Dict, all_cards: Dict[str, Dict]) -> Dict:
    """Perform comprehensive analysis on a single card."""
    name = card_data.get('name', 'Unknown')
    supertype = card_data.get('supertype', 'Unknown')
    subtypes = card_data.get('subtypes', [])
    subtype_str = ', '.join(subtypes) if subtypes else 'None'
    
    # Logic category
    logic_category = classify_card(card_data)

    # Battle styles
    battle_styles = extract_battle_styles(card_data)
    battle_styles_str = ', '.join(battle_styles) if battle_styles else 'None'

    # Evolution info
    immediate_parent = 'N/A'
    evolution_root = 'N/A'
    
    if supertype.lower() in ['pokémon', 'pokemon']:
        immediate_parent = card_data.get('evolvesFrom', 'None')
        evolution_root = find_evolution_root(card_data, all_cards)
        if evolution_root:
            evolution_root_str = evolution_root
        else:
            evolution_root_str = 'N/A'
    else:
        evolution_root_str = 'N/A'

    # --- TEXT EXTRACTION WITH TAGS ---
    text_sources = []

    # 1. Pokémon Abilities
    abilities = card_data.get('abilities', [])
    if abilities:
        for ability in abilities:
            text = ability.get('text', '')
            if text:
                # Add Tag: [Ability: Name]
                text_sources.append(f"[Ability: {ability.get('name', 'Unknown')}] {text}")

    # 2. Pokémon Attacks
    attacks = card_data.get('attacks', [])
    if attacks:
        for attack in attacks:
            text = attack.get('text', '')
            if text:
                # Add Tag: [Attack: Name]
                text_sources.append(f"[Attack: {attack.get('name', 'Unknown')}] {text}")

    # 3. Trainer/Energy Rules (The Fix)
    # Check 'rules' list first (common for trainers)
    rules = card_data.get('rules', [])
    if rules:
        for rule in rules:
            # Filter out generic rule box text
            if 'You may play any number of Item cards' in rule: continue
            if 'rule:' in rule.lower() and 'Prize cards' in rule: continue
            text_sources.append(f"[Rule] {rule}")
    
    # Check legacy 'text' field
    card_text = card_data.get('text', '')
    if card_text:
        if isinstance(card_text, list):
            for t in card_text: text_sources.append(f"[Text] {t}")
        else:
            text_sources.append(f"[Text] {card_text}")

    # Combine
    combined_text = ' | '.join(text_sources)
    
    # Detect triggers
    effect_triggers = detect_effect_triggers(combined_text)
    effect_triggers_str = ', '.join(effect_triggers) if effect_triggers else 'None'

    # Snippet (Longer limit for easier reading)
    text_snippet = combined_text.replace('\n', ' ').replace('"', "'")


    hp = card_data.get('hp', 'N/A')
    retreat_cost = card_data.get('retreatCost', [])
    retreat_cost_str = str(len(retreat_cost)) if retreat_cost else '0'
    if supertype.lower() not in ['pokémon', 'pokemon']:
        retreat_cost_str = 'N/A'

    return {
        'id': card_id,
        'name': name,
        'supertype': supertype,
        'subtype': subtype_str,
        'logic_category': logic_category,
        'battle_styles': battle_styles_str,
        'immediate_parent': immediate_parent,
        'evolution_root': evolution_root_str,
        'effect_triggers': effect_triggers_str,
        'hp': hp,
        'retreat_cost': retreat_cost_str,
        'text_snippet': text_snippet,
    }


# ============================================================================
# MAIN AUDIT FUNCTION
# ============================================================================

def audit_all_cards(output_csv: str = 'audit_master.csv', output_summary: str = 'audit_summary.txt'):
    """Audit all cards in the database and generate CSV + summary."""
    print("=" * 70)
    print("POKÉMON TCG ENGINE - CARD AUDIT TOOL")
    print("=" * 70)
    print()

    # Load database
    all_cards = _JSON_DATABASE
    print(f"Loaded {len(all_cards)} cards from database")
    print()

    # Analyze all cards
    print("Analyzing cards...")
    analyzed_cards = []

    for card_id, card_data in all_cards.items():
        analysis = analyze_card(card_id, card_data, all_cards)
        analyzed_cards.append(analysis)

    print(f"Analyzed {len(analyzed_cards)} cards")
    print()

    # Sort
    analyzed_cards.sort(key=lambda x: (
        x['supertype'],
        x['logic_category'],
        x['name']
    ))

    # Write CSV
    print(f"Writing CSV to {output_csv}...")
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        fieldnames = [
            'id',
            'name',
            'supertype',
            'subtype',
            'logic_category',
            'battle_styles',
            'immediate_parent', # NEW COLUMN
            'evolution_root',
            'effect_triggers',
            'hp',
            'retreat_cost',
            'text_snippet',
        ]

        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(analyzed_cards)

    print(f"[OK] CSV written: {output_csv}")
    print()

    # Generate statistics
    print("Generating statistics...")
    supertype_counts = Counter(card['supertype'] for card in analyzed_cards)
    logic_counts = Counter(card['logic_category'] for card in analyzed_cards)

    # Write summary
    print(f"Writing summary to {output_summary}...")
    with open(output_summary, 'w', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write("POKÉMON TCG ENGINE - CARD AUDIT SUMMARY\n")
        f.write("=" * 70 + "\n\n")

        f.write(f"Total Cards: {len(analyzed_cards)}\n\n")

        f.write("SUPERTYPE BREAKDOWN\n")
        f.write("-" * 70 + "\n")
        for supertype, count in sorted(supertype_counts.items()):
            f.write(f"{supertype:20} {count:5} cards\n")
        f.write("\n")

        f.write("LOGIC CATEGORY BREAKDOWN\n")
        f.write("-" * 70 + "\n")
        for category, count in sorted(logic_counts.items(), key=lambda x: -x[1]):
            f.write(f"{category:20} {count:5} cards\n")
        f.write("\n")
        
        f.write("NOTE: Check 'audit_master.csv' column 'immediate_parent' to verify JSON data integrity.\n")

    print(f"[OK] Summary written: {output_summary}")
    print(f"[OK] Audit complete!")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Audit all cards in the database')
    parser.add_argument('--output', '-o', default='audit_master.csv', help='Output CSV file path')
    parser.add_argument('--summary', '-s', default='audit_summary.txt', help='Output summary file path')
    args = parser.parse_args()
    audit_all_cards(args.output, args.summary)
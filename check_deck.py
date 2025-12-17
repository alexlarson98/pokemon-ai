"""
Deck Import Verification Script
Tests the PTCGL deck import pipeline with a real Dragapult deck list.

Usage:
    python check_deck.py
"""

import sys
sys.path.insert(0, 'src')

from utils.deck_import import parse_ptcgl_export, validate_deck_list
from cards.factory import create_card
from cards.registry import get_registry_stats

# ============================================================================
# SAMPLE DECK: Dragapult ex (Standard Format)
# ============================================================================

SAMPLE_DECK_TEXT = """
Pokémon: 26
2 Charmander PAF 7
1 Charmander PFL 11
1 Charmeleon PFL 12
2 Charizard ex OBF 125
3 Hoothoot SCR 114
3 Noctowl SCR 115
1 Pidgey MEW 16
1 Pidgey OBF 162
2 Pidgeot ex OBF 164
2 Duskull PRE 35
1 Dusclops PRE 36
1 Dusknoir PRE 37
2 Terapagos ex SCR 128
2 Fan Rotom SCR 118
1 Fezandipiti ex SFA 38
1 Klefki SVI 96

Trainer: 27
4 Dawn PFL 87
2 Iono PAL 185
2 Boss's Orders MEG 114
1 Briar SCR 132
4 Buddy-Buddy Poffin TEF 144
4 Nest Ball SVI 181
4 Rare Candy MEG 125
4 Ultra Ball MEG 131
2 Area Zero Underdepths SCR 131

Energy: 7
5 Fire Energy MEE 2
2 Jet Energy PAL 190
"""


# ============================================================================
# VERIFICATION SCRIPT
# ============================================================================

def main():
    """Main verification function."""
    # Force registry initialization first
    _ = get_registry_stats()

    print("=" * 70)
    print("POKEMON TCG DECK IMPORT TOOL - VERIFICATION")
    print("=" * 70)
    print()

    # Step 1: Show registry stats
    print("=== CARD REGISTRY STATUS ===")
    stats = get_registry_stats()
    print(f"Total cards in database: {stats['total_cards']}")
    print(f"  - Pokémon: {stats['pokemon']}")
    print(f"  - Trainers: {stats['trainers']}")
    print(f"  - Energy: {stats['energy']}")
    print(f"  - JSON cards: {stats['json_cards']}")
    print()

    # Step 2: Parse the deck
    print("=== PARSING DECK LIST ===")
    print("Deck: Dragapult ex (Standard Format)")
    print()

    deck_list = parse_ptcgl_export(SAMPLE_DECK_TEXT, validate=True)
    print()

    # Step 3: Validate deck
    print("=== DECK VALIDATION ===")
    validation = validate_deck_list(deck_list)

    print(f"Total cards: {validation['total_cards']}/60")
    print(f"Unique cards: {validation['unique_cards']}")
    print(f"Valid: {validation['valid']}")

    if validation['errors']:
        print("\nErrors:")
        for error in validation['errors']:
            print(f"  - {error}")

    if validation['warnings']:
        print("\nWarnings:")
        for warning in validation['warnings']:
            print(f"  - {warning}")

    print()

    # Step 4: Test card instantiation
    print("=== TESTING CARD INSTANTIATION ===")
    if deck_list:
        # Test first 5 cards
        print("Attempting to instantiate all cards:")
        for card_id, count in deck_list:
            card = create_card(card_id)
            if card:
                print(f"  [OK] {card_id}: {card.name} (x{count})")
            else:
                print(f"  [FAIL] {card_id}: Failed to instantiate")
        print()

    # Step 5: Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    found_count = len(deck_list)
    total_lines = len([line for line in SAMPLE_DECK_TEXT.strip().split('\n')
                      if line.strip() and ':' not in line])
    missing_count = total_lines - found_count

    print(f"Successfully imported: {found_count} card types")
    print(f"Missing from registry: {missing_count} card types")
    print()

    if missing_count == 0:
        print("[OK] All cards found! Deck is fully importable.")
    else:
        print("[FAIL] Some cards are missing. Check logs above for [MISSING] entries.")

    print("=" * 70)


if __name__ == "__main__":
    main()

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
Pokémon: 21
2 Hoothoot SCR 114
1 Hoothoot TEF 126
1 Hoothoot PRE 77
3 Noctowl SCR 115
2 Chien-Pao ex PAL 61
2 Fan Rotom SCR 118
2 Terapagos ex SCR 128
2 Wellspring Mask Ogerpon ex TWM 64
1 Ditto MEW 132
1 Latias ex SSP 76
1 Mew ex MEW 151
1 Bloodmoon Ursaluna ex TWM 141
1 Volcanion ex JTG 31
1 Fezandipiti ex SFA 38

Trainer: 32
2 Professor's Research JTG 155
2 Boss's Orders PAL 172
1 Judge DRI 167
1 N's Plan BLK 83
1 Briar SCR 132
1 Professor Turo's Scenario PAR 171
4 Ultra Ball SVI 196
4 Nest Ball SVI 181
4 Glass Trumpet SCR 135
4 Energy Switch SVI 173
2 Night Stretcher SFA 61
1 Earthen Vessel PAR 163
1 Prime Catcher TEF 157
1 Pal Pad SVI 182
3 Area Zero Underdepths SCR 131

Energy: 7
7 Water Energy SVE 3
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

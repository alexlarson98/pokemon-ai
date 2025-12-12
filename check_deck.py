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
Pokémon: 15
4 Gimmighoul SSP 97
4 Gholdengo ex PAR 139
2 Solrock MEG 75
2 Lunatone MEG 74
1 Genesect ex BLK 67
1 Fezandipiti ex SFA 38
1 Munkidori TWM 95

Trainer: 34
4 Arven OBF 186
3 Boss's Orders MEG 114
2 Professor Turo's Scenario PAR 171
1 Lana's Aid TWM 155
4 Superior Energy Retrieval PAL 189
4 Nest Ball SVI 181
4 Fighting Gong MEG 116
3 Earthen Vessel PAR 163
1 Super Rod PAL 188
1 Buddy-Buddy Poffin TEF 144
1 Premium Power Pro MEG 124
1 Prime Catcher TEF 157
2 Air Balloon BLK 79
1 Vitality Band SVI 197
2 Artazon PAL 171

Energy: 11
7 Fighting Energy MEE 6
3 Metal Energy MEE 8
1 Darkness Energy MEE 7
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

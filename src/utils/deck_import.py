"""
Pokémon TCG Deck Import Tool
Parses PTCGL (Pokémon TCG Live) export format into deck lists.

Format Example:
    Pokémon: 23
    4 Dreepy TWM 128
    1 Bloodmoon Ursaluna ex TWM 141

    Trainer: 30
    4 Iono PAL 185

    Energy: 7
    1 Neo Upper Energy TEF 162

Output:
    List[tuple[str, int]] - (card_id, count) pairs
    e.g., [("sv6-128", 4), ("sv6-141", 1), ...]
"""

import re
from typing import List, Tuple, Optional, Dict
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


# ============================================================================
# SET CODE MAPPING (PTCGL → Internal Database)
# ============================================================================

# Maps PTCGL set codes to internal database set codes
SET_CODE_MAP: Dict[str, str] = {
    # Scarlet & Violet Series
    "SVI": "sv1",        # Scarlet & Violet Base
    "PAL": "sv2",        # Paldea Evolved
    "OBF": "sv3",        # Obsidian Flames
    "MEW": "sv3pt5",     # 151
    "PAR": "sv4",        # Paradox Rift
    "PAF": "sv4pt5",     # Paldean Fates
    "TEF": "sv5",        # Temporal Forces
    "TWM": "sv6",        # Twilight Masquerade
    "SFA": "sv6pt5",     # Shrouded Fable
    "SCR": "sv7",        # Stellar Crown
    "SSP": "sv8",        # Surging Sparks
    "PTM": "sv8pt5",     # Prismatic Evolutions (tentative)

    # Sword & Shield Series (still in Standard)
    "BRS": "swsh9",      # Brilliant Stars
    "ASR": "swsh10",     # Astral Radiance
    "LOR": "swsh11",     # Lost Origin
    "SIT": "swsh12",     # Silver Tempest
    "CRZ": "swsh12pt5",  # Crown Zenith

    # Promo cards
    "SVP": "svp",        # Scarlet & Violet Promos
    "PR-SV": "svp",      # Alternative promo code

    # Mystery/Special sets
    "MEX": "me1",        # Mythical Island
    "DRI": "sv10",       # Destined Rivals
    "MEG": "me1",        # Mega Evolution
    "PRE": "sv8pt5",     # Mega Evolution
    "MEE": "sve",        # Mega Evolution
    "PFL": "me2",        # Mega Evolution
    "WHT": "rsv10pt5",   # White Flare
    "JTG": "sv9",        # Journey Together
    "BLK": "zsv10pt5",   # Black Bolt

    # Add more mappings as needed
}


# ============================================================================
# PARSING FUNCTIONS
# ============================================================================

def normalize_set_code(ptcgl_code: str) -> Optional[str]:
    """
    Convert PTCGL set code to internal database format.

    Args:
        ptcgl_code: Set code from PTCGL export (e.g., "TWM", "PAL")

    Returns:
        Internal set code (e.g., "sv6", "sv2"), or None if unknown

    Example:
        >>> normalize_set_code("TWM")
        "sv6"
        >>> normalize_set_code("PAL")
        "sv2"
    """
    # Try direct lookup
    if ptcgl_code in SET_CODE_MAP:
        return SET_CODE_MAP[ptcgl_code]

    # Try case-insensitive lookup
    for key, value in SET_CODE_MAP.items():
        if key.lower() == ptcgl_code.lower():
            return value

    # Unknown set code
    logger.warning(f"Unknown set code: {ptcgl_code}")
    return None


def parse_card_line(line: str) -> Optional[Tuple[str, str, str, str]]:
    """
    Parse a single card line from PTCGL export.

    Format: {Count} {Name} {SetCode} {Number}
    Example: "4 Dreepy TWM 128"

    Args:
        line: Single line from deck export

    Returns:
        Tuple of (count, name, set_code, number), or None if invalid

    Example:
        >>> parse_card_line("4 Dreepy TWM 128")
        ("4", "Dreepy", "TWM", "128")
        >>> parse_card_line("1 Bloodmoon Ursaluna ex TWM 141")
        ("1", "Bloodmoon Ursaluna ex", "TWM", "141")
    """
    # Strip whitespace
    line = line.strip()

    # Skip empty lines or section headers
    if not line or ':' in line:
        return None

    # Pattern: {Count} {Name} {SetCode} {Number}
    # Use regex to capture count, then set code and number at the end
    # Name is everything in between
    pattern = r'^(\d+)\s+(.+?)\s+([A-Z\-]+)\s+(\d+)$'
    match = re.match(pattern, line)

    if match:
        count = match.group(1)
        name = match.group(2).strip()
        set_code = match.group(3)
        number = match.group(4)
        return (count, name, set_code, number)

    # If pattern doesn't match, log warning
    logger.debug(f"Could not parse line: {line}")
    return None


def construct_card_id(set_code: str, number: str) -> str:
    """
    Construct internal card ID from set code and number.

    Args:
        set_code: Internal set code (e.g., "sv6")
        number: Card number (e.g., "128")

    Returns:
        Card ID (e.g., "sv6-128")

    Example:
        >>> construct_card_id("sv6", "128")
        "sv6-128"
    """
    return f"{set_code}-{number}"


def parse_ptcgl_export(text: str, validate: bool = True) -> List[Tuple[str, int]]:
    """
    Parse PTCGL deck export text into a list of (card_id, count) tuples.

    Args:
        text: Raw PTCGL export text
        validate: Whether to validate cards against registry (default: True)

    Returns:
        List of (card_id, count) tuples

    Example:
        >>> text = '''
        ... Pokémon: 23
        ... 4 Dreepy TWM 128
        ... 1 Bloodmoon Ursaluna ex TWM 141
        ...
        ... Trainer: 30
        ... 4 Iono PAL 185
        ... '''
        >>> deck_list = parse_ptcgl_export(text)
        >>> print(deck_list)
        [("sv6-128", 4), ("sv6-141", 1), ("sv2-185", 4)]
    """
    deck_list: List[Tuple[str, int]] = []
    missing_cards: List[Tuple[str, str]] = []  # (card_id, name)
    unknown_sets: List[str] = []

    lines = text.strip().split('\n')

    for line in lines:
        # Parse the line
        parsed = parse_card_line(line)
        if parsed is None:
            continue

        count_str, name, ptcgl_set_code, number = parsed
        count = int(count_str)

        # Normalize set code
        internal_set_code = normalize_set_code(ptcgl_set_code)
        if internal_set_code is None:
            unknown_sets.append(ptcgl_set_code)
            logger.warning(f"[UNKNOWN SET] {ptcgl_set_code} - Skipping '{name}'")
            continue

        # Construct card ID
        card_id = construct_card_id(internal_set_code, number)

        # Validate if requested
        if validate:
            from cards.registry import card_exists
            if card_exists(card_id):
                deck_list.append((card_id, count))
                logger.info(f"[FOUND] {card_id} ({name}) x{count}")
            else:
                missing_cards.append((card_id, name))
                logger.warning(f"[MISSING] Could not find '{card_id}' ({name}) in registry.")
        else:
            deck_list.append((card_id, count))

    # Summary
    logger.info(f"\n=== IMPORT SUMMARY ===")
    logger.info(f"Successfully imported: {len(deck_list)} unique cards")
    logger.info(f"Missing from registry: {len(missing_cards)} cards")
    if unknown_sets:
        logger.info(f"Unknown set codes: {set(unknown_sets)}")

    return deck_list


def validate_deck_list(deck_list: List[Tuple[str, int]]) -> Dict:
    """
    Validate a deck list against Pokémon TCG rules.

    Args:
        deck_list: List of (card_id, count) tuples

    Returns:
        Dictionary with validation results

    Example:
        >>> deck_list = [("sv6-128", 4), ("sv6-141", 1)]
        >>> result = validate_deck_list(deck_list)
        >>> print(result['valid'])
        False  # Not 60 cards
    """
    from cards.registry import create_card
    from cards.base import EnergyCard

    errors = []
    warnings = []

    # Calculate total cards
    total_cards = sum(count for _, count in deck_list)

    # Check deck size
    if total_cards != 60:
        errors.append(f"Deck must have exactly 60 cards (has {total_cards})")

    # Check 4-copy rule
    for card_id, count in deck_list:
        if count > 4:
            card = create_card(card_id)
            # Basic Energy exempt from 4-copy rule
            if card and isinstance(card, EnergyCard) and card.is_basic:
                continue
            errors.append(f"{card_id} appears {count} times (max 4)")

    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings,
        'total_cards': total_cards,
        'unique_cards': len(deck_list),
    }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def add_set_code_mapping(ptcgl_code: str, internal_code: str) -> None:
    """
    Add a new set code mapping dynamically.

    Args:
        ptcgl_code: PTCGL set code (e.g., "TEF")
        internal_code: Internal database code (e.g., "sv5")

    Example:
        >>> add_set_code_mapping("TEF", "sv5")
    """
    SET_CODE_MAP[ptcgl_code] = internal_code
    logger.info(f"Added set code mapping: {ptcgl_code} → {internal_code}")


def get_set_code_mappings() -> Dict[str, str]:
    """
    Get all set code mappings.

    Returns:
        Dictionary of PTCGL codes → internal codes
    """
    return SET_CODE_MAP.copy()


def print_set_code_mappings() -> None:
    """
    Print all set code mappings for reference.
    """
    print("=== SET CODE MAPPINGS ===")
    print("PTCGL Code → Internal Code")
    print("-" * 30)
    for ptcgl_code, internal_code in sorted(SET_CODE_MAP.items()):
        print(f"{ptcgl_code:10} → {internal_code}")

"""
Pokémon TCG Engine - Set-Based Card Logic Modules

Each set module contains card-specific logic functions for that expansion.
Logic is organized by set code (sv1, sv2, etc.) for maintainability.

Module Structure:
- Each set file exports a {SET}_LOGIC dictionary
- Keys: "{card_id}:{effect_name}" (e.g., "sv3-125:Burning Darkness")
- Values: Callable functions that implement the card logic

Example:
    from cards.sets.sv3 import SV3_LOGIC
    burning_darkness = SV3_LOGIC.get("sv3-125:Burning Darkness")
"""

# Import all set logic dictionaries
from cards.sets.sv1 import SV1_LOGIC
from cards.sets.sv2 import SV2_LOGIC
from cards.sets.sv3 import SV3_LOGIC
from cards.sets.sv3pt5 import SV3PT5_LOGIC
from cards.sets.sv4 import SV4_LOGIC
from cards.sets.sv4pt5 import SV4PT5_LOGIC
from cards.sets.sv5 import SV5_LOGIC
from cards.sets.sv6 import SV6_LOGIC
from cards.sets.sv6pt5 import SV6PT5_LOGIC
from cards.sets.sv7 import SV7_LOGIC
from cards.sets.sv8 import SV8_LOGIC
from cards.sets.sv8pt5 import SV8PT5_LOGIC
from cards.sets.sv9 import SV9_LOGIC
from cards.sets.sv10 import SV10_LOGIC
from cards.sets.zsv10pt5 import ZSV10PT5_LOGIC
from cards.sets.me1 import ME1_LOGIC
from cards.sets.me2 import ME2_LOGIC
from cards.sets.svp import SVP_LOGIC

__all__ = [
    'SV1_LOGIC',
    'SV2_LOGIC',
    'SV3_LOGIC',
    'SV3PT5_LOGIC',
    'SV4_LOGIC',
    'SV4PT5_LOGIC',
    'SV5_LOGIC',
    'SV6_LOGIC',
    'SV6PT5_LOGIC',
    'SV7_LOGIC',
    'SV8_LOGIC',
    'SV8PT5_LOGIC',
    'SV9_LOGIC',
    'SV10_LOGIC',
    'ZSV10PT5_LOGIC',
    'ME1_LOGIC',
    'ME2_LOGIC',
    'SVP_LOGIC',
]

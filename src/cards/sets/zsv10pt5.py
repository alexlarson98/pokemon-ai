"""
Pokémon TCG Engine - Supercharged Surge Card Logic
Set Code: zsv10pt5

This module contains card-specific logic for Supercharged Surge.
For reprints, this module imports logic from the set where the card was first released.
"""

from cards.library.trainers import (
    professors_research_actions,
    professors_research_effect,
)


# ============================================================================
# ZSV10PT5 LOGIC REGISTRY (Unified Schema)
# ============================================================================

ZSV10PT5_LOGIC = {
    # Professor's Research reprint
    "zsv10pt5-85": {
        "Play Professor's Research": {
            "category": "activatable",
            "generator": professors_research_actions,
            "effect": professors_research_effect,
        },
    },
}

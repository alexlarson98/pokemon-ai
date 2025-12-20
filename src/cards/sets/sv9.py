"""
Pokémon TCG Engine - Journey Together Card Logic
Set Code: JTG (sv9)

This module contains card-specific logic for Journey Together.
For reprints, this module imports logic from the set where the card was first released.
"""

from cards.library.trainers import (
    professors_research_actions,
    professors_research_effect,
)


# ============================================================================
# SV9 LOGIC REGISTRY (Unified Schema)
# ============================================================================

SV9_LOGIC = {
    # Professor's Research reprint
    "sv9-155": {
        "Play Professor's Research": {
            "category": "activatable",
            "generator": professors_research_actions,
            "effect": professors_research_effect,
        },
    },
}

/**
 * Super Rod - Trainer Item
 *
 * Card text:
 * "Shuffle up to 3 in any combination of Pokemon and Basic Energy cards
 *  from your discard pile into your deck."
 *
 * Card IDs: sv2-188, sv2-276
 *
 * Key mechanics:
 * - Discard pile is a PUBLIC zone - opponent can see it
 * - MUST have at least 1 valid target (Pokemon or basic Energy) to play
 * - MUST select at least 1 card (min_count=1)
 * - Can select up to 3 cards total
 * - Filter: Pokemon OR basic Energy (compound filter)
 */

#include "cards/trainer_registry.hpp"
#include "cards/effect_builders.hpp"
#include "card_database.hpp"  // For CardDef

namespace pokemon {

// External global card database pointer (defined in trainer_registry.cpp)
extern const CardDatabase* g_card_db;

namespace trainers {

// Filter predicate for Super Rod: Pokemon OR basic Energy
// Note: NOT in anonymous namespace so it can be used by generator
static bool super_rod_filter(const CardDef& def) {
    return def.is_pokemon() || (def.is_energy() && def.is_basic_energy);
}

/**
 * Check if Super Rod can be played.
 *
 * Requirements:
 * - Discard pile must contain at least 1 Pokemon OR basic Energy card
 * - Since discard is public, we can verify this
 */
static bool can_play_super_rod(const GameState& state, PlayerID player_id) {
    if (!g_card_db) {
        return false;  // Can't check without card database
    }

    const auto& player = state.get_player(player_id);

    // Check if discard has at least 1 valid target
    for (const auto& card : player.discard.cards) {
        const CardDef* def = g_card_db->get_card(card.card_id);
        if (def && super_rod_filter(*def)) {
            return true;  // Found at least 1 valid target
        }
    }

    return false;  // No valid targets in discard
}

namespace {

/**
 * Execute Super Rod effect using TrainerContext.
 *
 * Creates a SelectFromZoneStep for the discard pile with:
 * - Filter: Pokemon OR basic Energy (using predicate for clarity)
 * - count=3, min_count=1 (must select at least 1, up to 3)
 * - Purpose: RECOVER_TO_DECK
 */
TrainerResult execute_super_rod(TrainerContext& ctx) {
    TrainerResult result;
    auto& state = ctx.state;
    PlayerID player_id = state.active_player_index;

    // Use predicate filter: Pokemon OR basic Energy
    // This keeps the filter logic with the card, not scattered in engine.cpp
    auto effect_result = effects::shuffle_discard_to_deck(
        state,
        ctx.card,
        player_id,
        super_rod_filter,
        3,      // count: select up to 3
        1       // min_count: MUST select at least 1 (public zone rule)
    );

    result.success = effect_result.success;
    result.requires_resolution = effect_result.requires_resolution;
    result.effect_description = "Shuffle up to 3 Pokemon and/or basic Energy from discard into deck";

    return result;
}

} // anonymous namespace

void register_super_rod(LogicRegistry& registry) {
    // Unified handler using TrainerContext
    auto handler = [](TrainerContext& ctx) -> TrainerResult {
        return execute_super_rod(ctx);
    };

    auto generator = [](const GameState& state, const CardInstance& card) -> GeneratorResult {
        GeneratorResult result;
        result.valid = can_play_super_rod(state, state.active_player_index);
        if (!result.valid) {
            result.reason = "No Pokemon or basic Energy in discard pile";
        }
        // SEARCH pattern: VALIDITY_CHECK mode (default)
        return result;
    };

    // Register for all printings using unified handler
    const std::vector<std::string> card_ids = {"sv2-188", "sv2-276"};
    for (const auto& id : card_ids) {
        registry.register_trainer_handler(id, handler);
        registry.register_generator(id, "trainer", generator);
    }
}

} // namespace trainers
} // namespace pokemon

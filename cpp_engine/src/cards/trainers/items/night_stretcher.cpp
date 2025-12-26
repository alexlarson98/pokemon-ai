/**
 * Night Stretcher - Trainer Item
 *
 * Card text:
 * "Put a Pokemon or a Basic Energy card from your discard pile into your hand."
 *
 * Card IDs: sv6pt5-61, sv8-251, me1-173
 *
 * Pattern: SEARCH (uses resolution stack for discard selection)
 * - Generator mode: VALIDITY_CHECK (default)
 * - Uses resolution stack: Yes
 *
 * Key mechanics:
 * - Discard pile is a PUBLIC zone - opponent can see it
 * - MUST have at least 1 valid target (Pokemon or basic Energy) to play
 * - Selects exactly 1 card
 * - Filter: Pokemon OR basic Energy (compound filter)
 * - Destination: Hand (not deck like Super Rod)
 */

#include "cards/trainer_registry.hpp"
#include "cards/effect_builders.hpp"
#include "card_database.hpp"

namespace pokemon {

// External global card database pointer (defined in trainer_registry.cpp)
extern const CardDatabase* g_card_db;

namespace trainers {

// Filter predicate for Night Stretcher: Pokemon OR basic Energy
// Note: NOT in anonymous namespace so it can be used by generator
static bool night_stretcher_filter(const CardDef& def) {
    return def.is_pokemon() || (def.is_energy() && def.is_basic_energy);
}

/**
 * Check if Night Stretcher can be played.
 *
 * Requirements:
 * - Discard pile must contain at least 1 Pokemon OR basic Energy card
 * - Since discard is public, we can verify this
 */
static bool can_play_night_stretcher(const GameState& state, PlayerID player_id) {
    if (!g_card_db) {
        return false;  // Can't check without card database
    }

    const auto& player = state.get_player(player_id);

    // Check if discard has at least 1 valid target
    for (const auto& card : player.discard.cards) {
        const CardDef* def = g_card_db->get_card(card.card_id);
        if (def && night_stretcher_filter(*def)) {
            return true;  // Found at least 1 valid target
        }
    }

    return false;  // No valid targets in discard
}

namespace {

/**
 * Execute Night Stretcher effect using TrainerContext.
 *
 * Uses recover_from_discard effect builder with:
 * - Filter: Pokemon OR basic Energy
 * - count=1, min_count=1 (must select exactly 1)
 * - Purpose: RECOVER_TO_HAND
 */
TrainerResult execute_night_stretcher(TrainerContext& ctx) {
    TrainerResult result;
    auto& state = ctx.state;
    PlayerID player_id = state.active_player_index;

    if (!can_play_night_stretcher(state, player_id)) {
        result.success = false;
        result.effect_description = "No Pokemon or basic Energy in discard pile";
        return result;
    }

    // Build filter for Pokemon OR basic Energy
    // Use the compound filter that FilterBuilder supports
    auto filter = effects::FilterBuilder()
        .pokemon_or_basic_energy()
        .build();

    // Recover from discard to hand
    auto effect_result = effects::recover_from_discard(
        state,
        ctx.card,
        player_id,
        filter,
        1,      // count: select exactly 1
        1       // min_count: MUST select 1 (public zone rule)
    );

    result.success = effect_result.success;
    result.requires_resolution = effect_result.requires_resolution;
    result.effect_description = "Put a Pokemon or basic Energy from discard into hand";

    return result;
}

} // anonymous namespace

void register_night_stretcher(LogicRegistry& registry) {
    // Unified handler using TrainerContext
    auto handler = [](TrainerContext& ctx) -> TrainerResult {
        return execute_night_stretcher(ctx);
    };

    auto generator = [](const GameState& state, const CardInstance& /*card*/) -> GeneratorResult {
        GeneratorResult result;
        result.valid = can_play_night_stretcher(state, state.active_player_index);
        if (!result.valid) {
            result.reason = "No Pokemon or basic Energy in discard pile";
        }
        // SEARCH pattern: VALIDITY_CHECK mode (default)
        return result;
    };

    // Register for all printings using unified handler
    const std::vector<std::string> card_ids = {"sv6pt5-61", "sv8-251", "me1-173"};
    for (const auto& id : card_ids) {
        registry.register_trainer_handler(id, handler);
        registry.register_generator(id, "trainer", generator);
    }
}

} // namespace trainers
} // namespace pokemon

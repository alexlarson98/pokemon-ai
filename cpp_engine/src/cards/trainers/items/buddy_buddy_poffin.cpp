/**
 * Buddy-Buddy Poffin - Trainer Item
 *
 * Card text:
 * "Search your deck for up to 2 Basic Pokemon with 70 HP or less and put them
 *  onto your Bench. Then, shuffle your deck."
 *
 * Card IDs: sv5-144, sv6-223, sv8pt5-101, me1-167
 */

#include "cards/trainer_registry.hpp"
#include "cards/effect_builders.hpp"

namespace pokemon {
namespace trainers {

namespace {

/**
 * Check if Buddy-Buddy Poffin can be played.
 *
 * Requirements:
 * - Player must have bench space (at least 1 open slot)
 * - (Note: Deck having valid targets is NOT required - can "fail to find")
 */
bool can_play_buddy_buddy_poffin(const GameState& state, PlayerID player_id) {
    return effects::has_bench_space(state, player_id);
}

/**
 * Execute Buddy-Buddy Poffin effect using TrainerContext.
 *
 * Creates a SearchDeckStep with filter for Basic Pokemon with 70 HP or less.
 * Player can select up to 2 matching Pokemon to put directly on bench.
 */
TrainerResult execute_buddy_buddy_poffin(TrainerContext& ctx) {
    TrainerResult result;
    auto& state = ctx.state;
    PlayerID player_id = state.active_player_index;

    if (!can_play_buddy_buddy_poffin(state, player_id)) {
        result.success = false;
        result.effect_description = "No bench space available";
        return result;
    }

    // Build filter: Basic Pokemon with 70 HP or less
    auto filter = effects::FilterBuilder()
        .supertype("Pokemon")
        .subtype("Basic")
        .max_hp(70)
        .build();

    // Calculate available bench space
    const auto& player = state.get_player(player_id);
    int available_space = player.board.max_bench_size - static_cast<int>(player.board.bench.size());

    // Cap count at available bench space (up to 2)
    int count = std::min(2, available_space);

    // Search deck, put on bench
    // min_count = 0: can choose to find nothing (deck is hidden zone)
    auto effect_result = effects::search_deck_to_bench(
        state,
        ctx.card,
        player_id,
        filter,
        count,  // count: select up to min(2, available_space)
        0       // min_count: can choose to find nothing
    );

    result.success = effect_result.success;
    result.requires_resolution = effect_result.requires_resolution;
    result.effect_description = "Search deck for up to 2 Basic Pokemon (70 HP or less) to put on bench";

    return result;
}

} // anonymous namespace

void register_buddy_buddy_poffin(LogicRegistry& registry) {
    // Unified handler using TrainerContext
    auto handler = [](TrainerContext& ctx) -> TrainerResult {
        return execute_buddy_buddy_poffin(ctx);
    };

    auto generator = [](const GameState& state, const CardInstance& /*card*/) -> GeneratorResult {
        GeneratorResult result;
        result.valid = can_play_buddy_buddy_poffin(state, state.active_player_index);
        if (!result.valid) {
            result.reason = "No bench space";
        }
        // SEARCH pattern: VALIDITY_CHECK mode (default)
        return result;
    };

    // Register for all printings using unified handler
    const std::vector<std::string> card_ids = {"sv5-144", "sv6-223", "sv8pt5-101", "me1-167"};
    for (const auto& id : card_ids) {
        registry.register_trainer_handler(id, handler);
        registry.register_generator(id, "trainer", generator);
    }
}

} // namespace trainers
} // namespace pokemon

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
 * Execute Buddy-Buddy Poffin effect.
 *
 * Creates a SearchDeckStep with filter for Basic Pokemon with 70 HP or less.
 * Player can select up to 2 matching Pokemon to put directly on bench.
 */
TrainerResult execute_buddy_buddy_poffin(GameState& state, const CardInstance& card) {
    TrainerResult result;
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
        card,
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
    auto handler = [](GameState& state, const CardInstance& card) -> TrainerResult {
        return execute_buddy_buddy_poffin(state, card);
    };

    auto generator = [](const GameState& state, const CardInstance& card) -> GeneratorResult {
        GeneratorResult result;
        result.valid = can_play_buddy_buddy_poffin(state, state.active_player_index);
        if (!result.valid) {
            result.reason = "No bench space";
        }
        return result;
    };

    // Register for all printings
    registry.register_trainer("sv5-144", handler);
    registry.register_generator("sv5-144", "trainer", generator);
    registry.register_trainer("sv6-223", handler);
    registry.register_generator("sv6-223", "trainer", generator);
    registry.register_trainer("sv8pt5-101", handler);
    registry.register_generator("sv8pt5-101", "trainer", generator);
    registry.register_trainer("me1-167", handler);
    registry.register_generator("me1-167", "trainer", generator);
}

} // namespace trainers
} // namespace pokemon

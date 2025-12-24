/**
 * Nest Ball - Trainer Item
 *
 * Card text:
 * "Search your deck for a Basic Pokemon and put it onto your Bench.
 *  Then, shuffle your deck."
 *
 * Card IDs: sv1-181, sv1-255, sv4pt5-84
 */

#include "cards/trainer_registry.hpp"
#include "cards/effect_builders.hpp"

namespace pokemon {
namespace trainers {

namespace {

/**
 * Check if Nest Ball can be played.
 *
 * Requirements:
 * - Player must have bench space
 * - Deck must have at least one Basic Pokemon (optional - can fail to find)
 */
bool can_play_nest_ball(const GameState& state, PlayerID player_id) {
    return effects::has_bench_space(state, player_id);
}

/**
 * Execute Nest Ball effect.
 *
 * Creates a SearchDeckStep with filter for Basic Pokemon.
 * The selected card goes directly to bench.
 */
TrainerResult execute_nest_ball(GameState& state, const CardInstance& card) {
    TrainerResult result;
    PlayerID player_id = state.active_player_index;

    // Check precondition
    if (!can_play_nest_ball(state, player_id)) {
        result.success = false;
        result.effect_description = "No bench space available";
        return result;
    }

    // Build filter: Basic Pokemon only
    auto filter = effects::FilterBuilder()
        .supertype("Pokemon")
        .subtype("Basic")
        .build();

    // Search deck, put on bench
    // min_count = 0 because search can fail to find
    auto effect_result = effects::search_deck_to_bench(
        state,
        card,
        player_id,
        filter,
        1,      // count: select up to 1
        0       // min_count: can choose to find nothing
    );

    result.success = effect_result.success;
    result.requires_resolution = effect_result.requires_resolution;
    result.effect_description = "Search deck for a Basic Pokemon to put on bench";

    return result;
}

} // anonymous namespace

void register_nest_ball(LogicRegistry& registry) {
    // Register handler for all Nest Ball printings
    // The card name is the same, so use a single handler

    auto handler = [](GameState& state, const CardInstance& card) -> TrainerResult {
        return execute_nest_ball(state, card);
    };

    // Register for known Nest Ball card IDs
    registry.register_trainer("sv1-181", handler);
    registry.register_trainer("sv1-255", handler);
    registry.register_trainer("sv4pt5-84", handler);

    // Also register a generator to check if Nest Ball can be played
    auto generator = [](const GameState& state, const CardInstance& card) -> GeneratorResult {
        GeneratorResult result;

        // Check if we can play Nest Ball
        if (can_play_nest_ball(state, state.active_player_index)) {
            // Generate action for this card
            result.valid = true;
        } else {
            result.valid = false;
            result.reason = "No bench space";
        }

        return result;
    };

    registry.register_generator("sv1-181", "trainer", generator);
    registry.register_generator("sv1-255", "trainer", generator);
    registry.register_generator("sv4pt5-84", "trainer", generator);
}

} // namespace trainers
} // namespace pokemon

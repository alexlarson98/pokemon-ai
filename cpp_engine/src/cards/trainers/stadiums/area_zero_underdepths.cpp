/**
 * Area Zero Underdepths - Stadium (sv8-186, sv8-228, sv8pt5-123)
 *
 * Card text:
 * "If a player has a Tera Pokemon in play, that player's Bench holds up to 8
 *  Pokemon instead of 5."
 *
 * Pattern: PASSIVE_CONTINUOUS (Bench Size Modifier)
 * - No on_enter/on_leave effects
 * - Continuous bench size calculation based on Tera Pokemon condition
 * - Affects each player independently
 *
 * Key mechanics:
 * - Check if the player has ANY Tera Pokemon in play (Active + Bench)
 * - If yes, bench size is 8; otherwise, bench size is 5
 * - When stadium leaves play, bench shrinks back to 5
 *   (handled by engine's update_bench_sizes)
 */

#include "cards/trainer_registry.hpp"

namespace pokemon {
namespace trainers {

namespace {

constexpr int EXPANDED_BENCH_SIZE = 8;
constexpr int DEFAULT_BENCH_SIZE = 5;

/**
 * Check if player has any Tera Pokemon in play.
 *
 * Checks both Active and Bench positions.
 */
bool player_has_tera_pokemon(const GameState& state,
                              const CardDatabase& db,
                              PlayerID player_id) {
    const auto& player = state.get_player(player_id);

    // Check active Pokemon
    if (player.board.active_spot.has_value()) {
        const CardDef* def = db.get_card(player.board.active_spot->card_id);
        if (def && def->is_tera()) {
            return true;
        }
    }

    // Check bench Pokemon
    for (const auto& pokemon : player.board.bench) {
        const CardDef* def = db.get_card(pokemon.card_id);
        if (def && def->is_tera()) {
            return true;
        }
    }

    return false;
}

/**
 * Calculate bench size for a player based on Tera condition.
 */
int calculate_bench_size(const GameState& state,
                          const CardDatabase& db,
                          PlayerID player_id) {
    if (player_has_tera_pokemon(state, db, player_id)) {
        return EXPANDED_BENCH_SIZE;
    }
    return DEFAULT_BENCH_SIZE;
}

} // anonymous namespace

void register_area_zero_underdepths(LogicRegistry& registry) {
    // Create the stadium handler
    StadiumHandler handler;
    handler.name = "Area Zero Underdepths";

    // No special on-enter effect
    handler.on_enter = nullptr;

    // No special on-leave effect (engine handles bench shrinking)
    handler.on_leave = nullptr;

    // Bench size modifier: 8 if player has Tera, otherwise 5
    handler.bench_size = [](const GameState& state,
                            const CardDatabase& db,
                            PlayerID player_id) -> int {
        return calculate_bench_size(state, db, player_id);
    };

    // Condition checker: returns true if player has Tera Pokemon
    handler.condition = [](const GameState& state,
                           const CardDatabase& db,
                           PlayerID player_id) -> bool {
        return player_has_tera_pokemon(state, db, player_id);
    };

    // Register for all printings
    // IDs from standard_cards.json: sv7-131, sv7-174, sv8pt5-94
    const std::vector<std::string> card_ids = {"sv7-131", "sv7-174", "sv8pt5-94"};
    for (const auto& id : card_ids) {
        registry.register_stadium(id, handler);
    }
}

} // namespace trainers
} // namespace pokemon

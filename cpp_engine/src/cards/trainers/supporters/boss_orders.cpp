/**
 * Boss's Orders - Trainer Supporter (TARGETED Pattern)
 *
 * Card text:
 * "Switch in 1 of your opponent's Benched Pokemon to the Active Spot."
 * "You may play only 1 Supporter card during your turn."
 *
 * Card IDs: me1-114, sv1-172, sv4-172
 *
 * Pattern: TARGETED
 * - Generator mode: ACTION_GENERATION
 * - Uses resolution stack: No
 *
 * Key mechanics:
 * - Target is opponent's benched Pokemon (visible zone)
 * - Swaps opponent's active with selected bench Pokemon
 * - Cannot be played if opponent has no benched Pokemon
 */

#include "cards/trainer_registry.hpp"
#include "cards/effect_builders.hpp"

namespace pokemon {
namespace trainers {

namespace {

/**
 * Get list of opponent's benched Pokemon IDs.
 */
std::vector<CardID> get_opponent_bench_targets(const GameState& state, PlayerID player_id) {
    std::vector<CardID> targets;
    PlayerID opponent_id = 1 - player_id;
    const auto& opponent = state.get_player(opponent_id);

    for (const auto& pokemon : opponent.board.bench) {
        targets.push_back(pokemon.id);
    }

    return targets;
}

/**
 * Check if Boss's Orders can be played.
 * Requires opponent to have at least one benched Pokemon.
 */
bool can_play_boss_orders(const GameState& state, PlayerID player_id) {
    return !get_opponent_bench_targets(state, player_id).empty();
}

/**
 * Execute Boss's Orders effect using TrainerContext.
 * Switches opponent's active with the targeted benched Pokemon.
 */
TrainerResult execute_boss_orders(TrainerContext& ctx) {
    TrainerResult result;
    auto& state = ctx.state;
    PlayerID player_id = state.active_player_index;
    PlayerID opponent_id = 1 - player_id;

    // TARGETED pattern: Get target info from ctx.action
    if (!ctx.action.target_id.has_value()) {
        result.success = false;
        result.effect_description = "No target specified";
        return result;
    }
    const CardID& target_id = *ctx.action.target_id;

    // Perform the switch on opponent's board using the built-in switch_active method
    auto& opponent = state.get_player(opponent_id);

    if (!opponent.board.switch_active(target_id)) {
        result.success = false;
        result.effect_description = "Failed to switch opponent's Active Pokemon";
        return result;
    }

    result.success = true;
    result.effect_description = "Switched opponent's Active Pokemon";
    return result;
}

} // anonymous namespace

void register_boss_orders(LogicRegistry& registry) {
    // Unified handler using TrainerContext
    auto handler = [](TrainerContext& ctx) -> TrainerResult {
        return execute_boss_orders(ctx);
    };

    auto generator = [](const GameState& state, const CardInstance& card) -> GeneratorResult {
        GeneratorResult result;
        PlayerID player_id = state.active_player_index;

        // TARGETED pattern: Generate actions with target info
        auto targets = get_opponent_bench_targets(state, player_id);
        if (targets.empty()) {
            result.valid = false;
            result.reason = "Opponent has no benched Pokemon";
            return result;
        }

        result.valid = true;
        result.mode = GeneratorMode::ACTION_GENERATION;  // CRITICAL for TARGETED!

        // Create an action for each valid target
        for (const auto& target_id : targets) {
            Action action = Action::play_supporter(player_id, card.id);
            action.target_id = target_id;
            result.actions.push_back(action);
        }

        return result;
    };

    // Register for all printings using unified handler
    const std::vector<std::string> card_ids = {"me1-114", "sv1-172", "sv4-172"};
    for (const auto& id : card_ids) {
        registry.register_trainer_handler(id, handler);
        registry.register_generator(id, "trainer", generator);
    }
}

} // namespace trainers
} // namespace pokemon

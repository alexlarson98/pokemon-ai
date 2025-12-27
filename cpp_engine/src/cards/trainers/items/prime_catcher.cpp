/**
 * Prime Catcher - Trainer Item ACE SPEC (TARGETED + Resolution Pattern)
 *
 * Card text:
 * "Switch in 1 of your opponent's Benched Pokemon to the Active Spot.
 *  If you do, switch your Active Pokemon with 1 of your Benched Pokemon."
 * "You may play any number of Item cards during your turn."
 * "ACE SPEC: You can't have more than 1 ACE SPEC card in your deck."
 *
 * Card IDs: sv5-157, sv8pt5-119
 *
 * Pattern: TARGETED (opponent's bench) + Resolution Step (player's bench)
 * - Generator mode: ACTION_GENERATION (for opponent bench selection)
 * - Uses resolution stack: Yes (for player bench selection)
 *
 * Key mechanics:
 * - Requires opponent to have at least one benched Pokemon
 * - Requires player to have at least one benched Pokemon
 * - First: Player selects opponent's benched Pokemon (via TARGETED action)
 * - Then: Opponent's switch happens immediately
 * - Then: Resolution step for player to choose their own bench Pokemon to switch
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
 * Check if Prime Catcher can be played.
 * Requires opponent to have at least one benched Pokemon.
 * Requires player to have at least one benched Pokemon.
 */
bool can_play_prime_catcher(const GameState& state, PlayerID player_id) {
    // Opponent must have benched Pokemon
    PlayerID opponent_id = 1 - player_id;
    const auto& opponent = state.get_player(opponent_id);
    if (opponent.board.bench.empty()) {
        return false;
    }

    // Player must have benched Pokemon
    const auto& player = state.get_player(player_id);
    if (player.board.bench.empty()) {
        return false;
    }

    return true;
}

/**
 * Execute Prime Catcher effect using TrainerContext.
 *
 * 1. Switch opponent's active with the targeted bench Pokemon (immediate)
 * 2. Push resolution step for player to choose their bench Pokemon to switch
 */
TrainerResult execute_prime_catcher(TrainerContext& ctx) {
    TrainerResult result;
    auto& state = ctx.state;
    PlayerID player_id = state.active_player_index;
    PlayerID opponent_id = 1 - player_id;

    // TARGETED pattern: Get opponent bench target from ctx.action
    if (!ctx.action.target_id.has_value()) {
        result.success = false;
        result.effect_description = "No opponent target specified";
        return result;
    }

    const CardID& opponent_target = *ctx.action.target_id;

    // Step 1: Switch opponent's active with their selected bench Pokemon (immediate)
    auto& opponent = state.get_player(opponent_id);
    if (!opponent.board.switch_active(opponent_target)) {
        result.success = false;
        result.effect_description = "Failed to switch opponent's Active Pokemon";
        return result;
    }

    // Step 2: Push resolution step for player to select their bench Pokemon
    // Only if player has benched Pokemon (which we already verified in generator)
    const auto& player = state.get_player(player_id);
    if (!player.board.bench.empty()) {
        SelectFromZoneStep step;
        step.source_card_id = ctx.card.id;
        step.source_card_name = "Prime Catcher";
        step.player_id = player_id;
        step.purpose = SelectionPurpose::SWITCH_TARGET;
        step.zone = ZoneType::BENCH;
        step.count = 1;
        step.min_count = 1;
        step.exact_count = true;

        // Completion callback to perform the switch
        step.on_complete = CompletionCallback([](
            GameState& callback_state,
            const std::vector<CardID>& selected_cards,
            PlayerID callback_player_id
        ) {
            if (selected_cards.empty()) return;

            auto& callback_player = callback_state.get_player(callback_player_id);
            callback_player.board.switch_active(selected_cards[0]);
        });

        state.push_step(step);

        result.requires_resolution = true;
    }

    result.success = true;
    result.effect_description = "Switched opponent's Active Pokemon, now choose your Pokemon to switch";
    return result;
}

} // anonymous namespace

void register_prime_catcher(LogicRegistry& registry) {
    // Unified handler using TrainerContext
    auto handler = [](TrainerContext& ctx) -> TrainerResult {
        return execute_prime_catcher(ctx);
    };

    auto generator = [](const GameState& state, const CardInstance& card) -> GeneratorResult {
        GeneratorResult result;
        PlayerID player_id = state.active_player_index;

        // Check playability: both players need benched Pokemon
        if (!can_play_prime_catcher(state, player_id)) {
            result.valid = false;
            result.reason = "Opponent or you have no benched Pokemon";
            return result;
        }

        // TARGETED pattern: Generate actions for opponent bench targets only
        auto opponent_targets = get_opponent_bench_targets(state, player_id);

        result.valid = true;
        result.mode = GeneratorMode::ACTION_GENERATION;  // CRITICAL for TARGETED!

        // Create an action for each opponent bench target
        for (const auto& opp_target : opponent_targets) {
            Action action = Action::play_item(player_id, card.id);
            action.target_id = opp_target;
            result.actions.push_back(action);
        }

        return result;
    };

    // Register for all printings using unified handler
    const std::vector<std::string> card_ids = {"sv5-157", "sv8pt5-119"};
    for (const auto& id : card_ids) {
        registry.register_trainer_handler(id, handler);
        registry.register_generator(id, "trainer", generator);
    }
}

} // namespace trainers
} // namespace pokemon

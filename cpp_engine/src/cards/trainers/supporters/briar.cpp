/**
 * Briar - Trainer Supporter (IMMEDIATE Pattern)
 *
 * Card text:
 * "You can use this card only if your opponent has exactly 2 Prize cards remaining.
 *  During this turn, if your opponent's Active Pokemon is Knocked Out by damage
 *  from an attack used by your Tera Pokemon, take 1 more Prize card."
 * "You may play only 1 Supporter card during your turn."
 *
 * Card IDs: sv7-132, sv7-163, sv7-171, sv8pt5-100
 *
 * Pattern: IMMEDIATE
 * - Generator mode: VALIDITY_CHECK (checks opponent's prize count)
 * - Uses resolution stack: No
 * - Uses ActiveEffect system: Yes (for turn-based prize modifier)
 *
 * Key mechanics:
 * - Can only be played when opponent has exactly 2 prizes remaining
 * - Creates an ActiveEffect that grants +1 prize on KO by Tera Pokemon
 * - Effect expires at end of turn (duration = 1)
 * - Effect params: "tera_required" = "true" for engine to check
 */

#include "cards/trainer_registry.hpp"
#include "cards/effect_builders.hpp"

namespace pokemon {
namespace trainers {

namespace {

/**
 * Check if Briar can be played.
 * Requires opponent to have exactly 2 Prize cards remaining.
 */
bool can_play_briar(const GameState& state, PlayerID player_id) {
    PlayerID opponent_id = 1 - player_id;
    const auto& opponent = state.get_player(opponent_id);

    // Opponent must have exactly 2 prizes remaining
    return opponent.prizes.count() == 2;
}

/**
 * Execute Briar effect using TrainerContext.
 * Creates an ActiveEffect that modifies prize taking for this turn.
 */
TrainerResult execute_briar(TrainerContext& ctx) {
    TrainerResult result;
    auto& state = ctx.state;
    PlayerID player_id = state.active_player_index;

    if (!can_play_briar(state, player_id)) {
        result.success = false;
        result.effect_description = "Opponent must have exactly 2 Prize cards remaining";
        return result;
    }

    // Create an ActiveEffect for the extra prize condition
    ActiveEffect briar_effect;
    briar_effect.name = "briar_extra_prize";
    briar_effect.source = EffectSource::TRAINER;
    briar_effect.source_card_id = ctx.card.id;
    briar_effect.target_player_id = player_id;  // Affects this player's prize taking
    briar_effect.duration_turns = 1;  // This turn only
    briar_effect.created_turn = state.turn_count;
    briar_effect.created_phase = "main";
    briar_effect.expires_on_player = player_id;  // Expires at end of this player's turn

    // Parameters for the engine to check when processing KOs
    briar_effect.params["extra_prizes"] = "1";
    briar_effect.params["requires_tera"] = "true";
    briar_effect.params["requires_attack_ko"] = "true";

    // Add the effect to the game state
    state.active_effects.push_back(briar_effect);

    result.success = true;
    result.effect_description = "If your Tera Pokemon KOs opponent's Active this turn, take 1 more Prize";
    return result;
}

} // anonymous namespace

void register_briar(LogicRegistry& registry) {
    // Unified handler using TrainerContext
    auto handler = [](TrainerContext& ctx) -> TrainerResult {
        return execute_briar(ctx);
    };

    auto generator = [](const GameState& state, const CardInstance& /*card*/) -> GeneratorResult {
        GeneratorResult result;
        result.valid = can_play_briar(state, state.active_player_index);
        if (!result.valid) {
            result.reason = "Opponent must have exactly 2 Prize cards remaining";
        }
        // IMMEDIATE pattern: VALIDITY_CHECK mode (default)
        return result;
    };

    // Register for all printings using unified handler
    const std::vector<std::string> card_ids = {"sv7-132", "sv7-163", "sv7-171", "sv8pt5-100"};
    for (const auto& id : card_ids) {
        registry.register_trainer_handler(id, handler);
        registry.register_generator(id, "trainer", generator);
    }
}

} // namespace trainers
} // namespace pokemon

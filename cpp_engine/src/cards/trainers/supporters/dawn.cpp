/**
 * Dawn - Trainer Supporter (SEARCH Pattern)
 *
 * Card text:
 * "Search your deck for a Basic Pokemon, a Stage 1 Pokemon, and a Stage 2 Pokemon,
 *  reveal them, and put them into your hand. Then, shuffle your deck."
 * "You may play only 1 Supporter card during your turn."
 *
 * Card IDs: me2-87, me2-118, me2-129
 *
 * Pattern: SEARCH
 * - Generator mode: VALIDITY_CHECK (default)
 * - Uses resolution stack: Yes (3 sequential search steps)
 *
 * Key mechanics:
 * - Search deck for 3 different Pokemon types (Basic, Stage 1, Stage 2)
 * - Each type is a separate search (can fail-to-find on any)
 * - All go to hand (not bench)
 * - Deck is shuffled once at the end
 *
 * Implementation approach:
 * - Push 3 SearchDeckStep entries onto resolution stack (LIFO order)
 * - Each step searches for one evolution stage
 * - Only the last step shuffles the deck
 */

#include "cards/trainer_registry.hpp"
#include "cards/effect_builders.hpp"

namespace pokemon {
namespace trainers {

namespace {

/**
 * Check if Dawn can be played.
 * Dawn is a Supporter - can always be played if supporter hasn't been used this turn.
 * (Supporter check is done in can_play_trainer())
 */
bool can_play_dawn(const GameState& /*state*/, PlayerID /*player_id*/) {
    // Dawn can always be played - fail-to-find is allowed for deck searches
    return true;
}

/**
 * Execute Dawn effect using TrainerContext.
 *
 * Creates 3 search steps in LIFO order:
 * 1. Stage 2 (pushed first, resolves last)
 * 2. Stage 1 (pushed second)
 * 3. Basic (pushed last, resolves first)
 *
 * Only the Stage 2 search (first pushed) shuffles the deck.
 */
TrainerResult execute_dawn(TrainerContext& ctx) {
    TrainerResult result;
    auto& state = ctx.state;
    PlayerID player_id = state.active_player_index;

    // Build filters for each evolution stage
    auto basic_filter = effects::FilterBuilder()
        .supertype("Pokemon")
        .subtype("Basic")
        .build();

    auto stage1_filter = effects::FilterBuilder()
        .supertype("Pokemon")
        .subtype("Stage 1")
        .build();

    auto stage2_filter = effects::FilterBuilder()
        .supertype("Pokemon")
        .subtype("Stage 2")
        .build();

    // Push steps in LIFO order (last pushed = first resolved)
    // Step 3: Search for Stage 2 (resolves last, shuffles deck)
    {
        SearchDeckStep step;
        step.source_card_id = ctx.card.id;
        step.source_card_name = "Dawn";
        step.player_id = player_id;
        step.purpose = SelectionPurpose::SEARCH_TARGET;
        step.count = 1;
        step.min_count = 0;  // Can fail to find
        step.destination = ZoneType::HAND;
        step.filter_criteria = stage2_filter;
        step.shuffle_after = true;  // Shuffle after the final search
        state.push_step(step);
    }

    // Step 2: Search for Stage 1 (resolves second, no shuffle)
    {
        SearchDeckStep step;
        step.source_card_id = ctx.card.id;
        step.source_card_name = "Dawn";
        step.player_id = player_id;
        step.purpose = SelectionPurpose::SEARCH_TARGET;
        step.count = 1;
        step.min_count = 0;  // Can fail to find
        step.destination = ZoneType::HAND;
        step.filter_criteria = stage1_filter;
        step.shuffle_after = false;  // Don't shuffle yet
        state.push_step(step);
    }

    // Step 1: Search for Basic (resolves first, no shuffle)
    {
        SearchDeckStep step;
        step.source_card_id = ctx.card.id;
        step.source_card_name = "Dawn";
        step.player_id = player_id;
        step.purpose = SelectionPurpose::SEARCH_TARGET;
        step.count = 1;
        step.min_count = 0;  // Can fail to find
        step.destination = ZoneType::HAND;
        step.filter_criteria = basic_filter;
        step.shuffle_after = false;  // Don't shuffle yet
        state.push_step(step);
    }

    result.success = true;
    result.requires_resolution = true;
    result.effect_description = "Search deck for a Basic, Stage 1, and Stage 2 Pokemon";

    return result;
}

} // anonymous namespace

void register_dawn(LogicRegistry& registry) {
    // Unified handler using TrainerContext
    auto handler = [](TrainerContext& ctx) -> TrainerResult {
        return execute_dawn(ctx);
    };

    auto generator = [](const GameState& state, const CardInstance& /*card*/) -> GeneratorResult {
        GeneratorResult result;
        result.valid = can_play_dawn(state, state.active_player_index);
        if (!result.valid) {
            result.reason = "Cannot play Dawn";
        }
        // SEARCH pattern: VALIDITY_CHECK mode (default)
        return result;
    };

    // Register for all printings using unified handler
    const std::vector<std::string> card_ids = {"me2-87", "me2-118", "me2-129"};
    for (const auto& id : card_ids) {
        registry.register_trainer_handler(id, handler);
        registry.register_generator(id, "trainer", generator);
    }
}

} // namespace trainers
} // namespace pokemon

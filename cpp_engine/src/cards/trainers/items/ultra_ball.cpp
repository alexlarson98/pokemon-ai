/**
 * Ultra Ball - Trainer Item
 *
 * Card text:
 * "You can use this card only if you discard 2 other cards from your hand.
 *  Search your deck for a Pokemon, reveal it, and put it into your hand.
 *  Then, shuffle your deck."
 *
 * Card IDs: sv1-196, sv4pt5-91, me1-131
 */

#include "cards/trainer_registry.hpp"
#include "cards/effect_builders.hpp"

namespace pokemon {
namespace trainers {

namespace {

/**
 * Check if Ultra Ball can be played.
 *
 * Requirements:
 * - Player must have at least 2 OTHER cards in hand to discard
 *   (Ultra Ball itself doesn't count toward the discard requirement)
 * - (Note: Deck having Pokemon is NOT required - can "fail to find")
 */
bool can_play_ultra_ball(const GameState& state, PlayerID player_id) {
    const auto& player = state.get_player(player_id);
    // Need at least 2 other cards in hand (excluding Ultra Ball itself)
    // Hand size must be >= 3 (Ultra Ball + 2 cards to discard)
    return player.hand.cards.size() >= 3;
}

/**
 * Execute Ultra Ball effect.
 *
 * Two-step resolution:
 * 1. Discard 2 cards from hand
 * 2. Search deck for any Pokemon, add to hand
 */
TrainerResult execute_ultra_ball(GameState& state, const CardInstance& card) {
    TrainerResult result;
    PlayerID player_id = state.active_player_index;

    if (!can_play_ultra_ball(state, player_id)) {
        result.success = false;
        result.effect_description = "Need at least 2 other cards in hand to discard";
        return result;
    }

    // Build filter: Any Pokemon
    auto pokemon_filter = effects::FilterBuilder()
        .supertype("Pokemon")
        .build();

    // Use discard_then to handle the two-step process:
    // 1. First, player discards 2 cards
    // 2. Then, search deck for a Pokemon
    auto effect_result = effects::discard_then(
        state,
        card,
        player_id,
        2,      // discard_count: must discard exactly 2 cards
        {},     // discard_filter: any cards can be discarded
        [pokemon_filter](GameState& s) {
            // After discard completes, search deck for Pokemon
            PlayerID pid = s.active_player_index;

            // Create a dummy source card for the search step
            // (The original Ultra Ball is already being processed)
            CardInstance dummy_source;
            dummy_source.id = "ultra_ball_search";
            dummy_source.card_id = "sv1-196";

            effects::search_deck(
                s,
                dummy_source,
                pid,
                pokemon_filter,
                1,      // count: select up to 1 Pokemon
                0,      // min_count: can fail to find
                ZoneType::HAND,  // destination: hand
                true    // shuffle_after: yes
            );
        }
    );

    result.success = effect_result.success;
    result.requires_resolution = effect_result.requires_resolution;
    result.effect_description = "Discard 2 cards, then search deck for a Pokemon";

    return result;
}

} // anonymous namespace

void register_ultra_ball(LogicRegistry& registry) {
    auto handler = [](GameState& state, const CardInstance& card) -> TrainerResult {
        return execute_ultra_ball(state, card);
    };

    auto generator = [](const GameState& state, const CardInstance& card) -> GeneratorResult {
        GeneratorResult result;
        result.valid = can_play_ultra_ball(state, state.active_player_index);
        if (!result.valid) {
            result.reason = "Need 2 other cards to discard";
        }
        return result;
    };

    // Register for all printings
    registry.register_trainer("sv1-196", handler);
    registry.register_generator("sv1-196", "trainer", generator);
    registry.register_trainer("sv4pt5-91", handler);
    registry.register_generator("sv4pt5-91", "trainer", generator);
    registry.register_trainer("me1-131", handler);
    registry.register_generator("me1-131", "trainer", generator);
}

} // namespace trainers
} // namespace pokemon

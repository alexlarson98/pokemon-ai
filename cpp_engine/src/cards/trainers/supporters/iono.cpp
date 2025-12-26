/**
 * Iono - Trainer Supporter
 *
 * Card text:
 * "Each player shuffles their hand and puts it on the bottom of their deck.
 *  If either player put any cards on the bottom of their deck in this way,
 *  each player draws a card for each of their remaining Prize cards."
 *
 * Card IDs: svp-124, sv2-185, sv2-254, sv2-269, sv4pt5-80, sv4pt5-237
 *
 * Key mechanics:
 * - Affects BOTH players simultaneously
 * - Hand goes to BOTTOM of deck (not shuffled into deck)
 * - Draw count = remaining prize cards (not taken prizes)
 * - Only draws if at least one player had cards in hand
 * - No resolution needed - immediate effect
 */

#include "cards/trainer_registry.hpp"
#include "cards/effect_builders.hpp"

namespace pokemon {
namespace trainers {

namespace {

/**
 * Check if Iono can be played.
 *
 * Iono can always be played - even with empty hands, the effect
 * still "attempts" to shuffle hands. The draw only happens if
 * either player put cards on deck, but playing is always legal.
 */
bool can_play_iono(const GameState& /*state*/, PlayerID /*player_id*/) {
    // Supporters can always be played (the engine checks supporter_played_this_turn)
    return true;
}

/**
 * Execute Iono effect using TrainerContext.
 *
 * 1. Both players shuffle their hands and put them on bottom of deck
 * 2. If either player had cards, both draw cards equal to remaining prizes
 *
 * This is an immediate effect - no resolution stack needed.
 */
TrainerResult execute_iono(TrainerContext& ctx) {
    TrainerResult result;
    auto& state = ctx.state;

    auto& player = state.get_active_player();
    auto& opponent = state.get_opponent();

    // Track if either player had cards in hand
    bool player_had_cards = !player.hand.cards.empty();
    bool opponent_had_cards = !opponent.hand.cards.empty();
    bool any_cards_moved = player_had_cards || opponent_had_cards;

    // Step 1: Both players shuffle hands and put on bottom of deck
    // "Shuffle hand" means randomize the order before placing
    // "Put on bottom" means insert at position 0 (front of vector = bottom of deck)

    // Player's hand -> shuffle -> bottom of deck
    if (player_had_cards) {
        // Shuffle the hand cards
        std::shuffle(player.hand.cards.begin(), player.hand.cards.end(), state.rng);

        // Insert at bottom of deck (beginning of vector)
        player.deck.cards.insert(
            player.deck.cards.begin(),
            std::make_move_iterator(player.hand.cards.begin()),
            std::make_move_iterator(player.hand.cards.end())
        );
        player.hand.cards.clear();
    }

    // Opponent's hand -> shuffle -> bottom of deck
    if (opponent_had_cards) {
        std::shuffle(opponent.hand.cards.begin(), opponent.hand.cards.end(), state.rng);

        opponent.deck.cards.insert(
            opponent.deck.cards.begin(),
            std::make_move_iterator(opponent.hand.cards.begin()),
            std::make_move_iterator(opponent.hand.cards.end())
        );
        opponent.hand.cards.clear();
    }

    // Step 2: If either player put cards on deck, both draw equal to remaining prizes
    if (any_cards_moved) {
        // Remaining prizes = cards still in prize pile (not taken)
        int player_prizes_remaining = static_cast<int>(player.prizes.cards.size());
        int opponent_prizes_remaining = static_cast<int>(opponent.prizes.cards.size());

        // Player draws (from top of deck = end of vector)
        for (int i = 0; i < player_prizes_remaining && !player.deck.cards.empty(); i++) {
            player.hand.cards.push_back(std::move(player.deck.cards.back()));
            player.deck.cards.pop_back();
        }

        // Opponent draws
        for (int i = 0; i < opponent_prizes_remaining && !opponent.deck.cards.empty(); i++) {
            opponent.hand.cards.push_back(std::move(opponent.deck.cards.back()));
            opponent.deck.cards.pop_back();
        }
    }

    result.success = true;
    result.requires_resolution = false;  // Immediate effect, no selections needed
    result.effect_description = "Both players shuffle hands to bottom of deck, then draw for remaining prizes";

    return result;
}

} // anonymous namespace

void register_iono(LogicRegistry& registry) {
    // Unified handler using TrainerContext
    auto handler = [](TrainerContext& ctx) -> TrainerResult {
        return execute_iono(ctx);
    };

    auto generator = [](const GameState& state, const CardInstance& /*card*/) -> GeneratorResult {
        GeneratorResult result;
        result.valid = can_play_iono(state, state.active_player_index);
        if (!result.valid) {
            result.reason = "Cannot play Iono";
        }
        // IMMEDIATE pattern: VALIDITY_CHECK mode (default)
        return result;
    };

    // Register for all printings using unified handler
    const std::vector<std::string> card_ids = {
        "svp-124", "sv2-185", "sv2-254", "sv2-269", "sv4pt5-80", "sv4pt5-237"
    };
    for (const auto& id : card_ids) {
        registry.register_trainer_handler(id, handler);
        registry.register_generator(id, "trainer", generator);
    }
}

} // namespace trainers
} // namespace pokemon

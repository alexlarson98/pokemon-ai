/**
 * Pokemon TCG Engine - Effect Builders
 *
 * Reusable building blocks for card effects.
 * These map to Python's common trainer patterns but with C++ efficiency.
 *
 * Design principle: Effects are built from composable primitives that
 * push resolution steps onto the stack. This matches the Python resolution
 * stack approach but with type-safe C++ callbacks.
 *
 * ARCHITECTURE (2024-12):
 * Effect builders now support optional completion callbacks. When provided,
 * the callback is invoked when the resolution step completes, allowing
 * card-specific logic to be defined alongside the card rather than in the engine.
 *
 * See cpp_engine/docs/CARD_INTEGRATION.md for full documentation.
 */

#pragma once

#include "../types.hpp"
#include "../game_state.hpp"
#include "../resolution_step.hpp"
#include "../logic_registry.hpp"
#include "../card_database.hpp"
#include <functional>
#include <string>
#include <unordered_map>

namespace pokemon {
namespace effects {

// ============================================================================
// FILTER CRITERIA BUILDERS
// ============================================================================

/**
 * FilterBuilder - Fluent interface for building filter criteria maps.
 *
 * Usage:
 *   auto filter = FilterBuilder()
 *       .supertype("Pokemon")
 *       .subtype("Basic")
 *       .build();
 */
class FilterBuilder {
public:
    FilterBuilder& supertype(const std::string& type);
    FilterBuilder& subtype(const std::string& type);
    FilterBuilder& pokemon_type(EnergyType type);
    FilterBuilder& energy_type(EnergyType type);
    FilterBuilder& max_hp(int hp);
    FilterBuilder& name(const std::string& name);
    FilterBuilder& evolves_from(const std::string& pokemon_name);
    FilterBuilder& is_basic(bool value = true);
    FilterBuilder& rare_candy_target(bool value = true);
    FilterBuilder& super_rod_target(bool value = true);

    std::unordered_map<std::string, std::string> build() const;

private:
    std::unordered_map<std::string, std::string> criteria_;
};

// ============================================================================
// EFFECT RESULT STRUCTURES
// ============================================================================

/**
 * EffectResult - Result of executing a trainer/ability effect.
 */
struct EffectResult {
    bool success = false;
    bool requires_resolution = false;  // True if resolution steps were pushed
    std::string message;
};

// ============================================================================
// CORE EFFECT BUILDERS
// ============================================================================

/**
 * Search player's deck for cards matching filter, add to destination zone.
 *
 * @param state The game state to modify
 * @param source_card The trainer/ability card creating this effect
 * @param player_id The player performing the search
 * @param filter Filter criteria for valid cards
 * @param count Max number of cards to select
 * @param min_count Minimum cards required (0 = optional)
 * @param destination Where cards go after selection (default: HAND)
 * @param shuffle_after Whether to shuffle deck after (default: true)
 * @param on_complete Optional callback for card-specific completion logic
 * @return EffectResult indicating success and whether resolution is needed
 */
EffectResult search_deck(
    GameState& state,
    const CardInstance& source_card,
    PlayerID player_id,
    const std::unordered_map<std::string, std::string>& filter,
    int count = 1,
    int min_count = 0,
    ZoneType destination = ZoneType::HAND,
    bool shuffle_after = true,
    StepCompletionCallback on_complete = nullptr
);

/**
 * Search deck and put cards directly onto bench (for Nest Ball).
 *
 * @param on_complete Optional callback for card-specific completion logic.
 *                    If not provided, uses default behavior (move to bench, shuffle).
 */
EffectResult search_deck_to_bench(
    GameState& state,
    const CardInstance& source_card,
    PlayerID player_id,
    const std::unordered_map<std::string, std::string>& filter,
    int count = 1,
    int min_count = 0,
    StepCompletionCallback on_complete = nullptr
);

/**
 * Discard cards from hand, then perform an effect.
 * Used by Ultra Ball, Superior Energy Retrieval, etc.
 *
 * @param state The game state
 * @param source_card The trainer card
 * @param player_id The player
 * @param discard_count Number of cards to discard
 * @param discard_filter Optional filter for what can be discarded
 * @param then_effect Callback to execute after discard completes
 */
EffectResult discard_then(
    GameState& state,
    const CardInstance& source_card,
    PlayerID player_id,
    int discard_count,
    const std::unordered_map<std::string, std::string>& discard_filter,
    std::function<void(GameState&)> then_effect
);

/**
 * Draw cards from deck to hand.
 */
EffectResult draw_cards(
    GameState& state,
    PlayerID player_id,
    int count
);

/**
 * Discard hand, draw new cards.
 * Used by Professor's Research.
 */
EffectResult discard_hand_draw(
    GameState& state,
    PlayerID player_id,
    int draw_count
);

/**
 * Shuffle cards from discard pile into deck.
 * Used by Super Rod, Night Stretcher.
 *
 * @param filter Filter for what can be shuffled back
 * @param count Number of cards to shuffle back
 */
EffectResult shuffle_discard_to_deck(
    GameState& state,
    const CardInstance& source_card,
    PlayerID player_id,
    const std::unordered_map<std::string, std::string>& filter,
    int count,
    int min_count = 0
);

/**
 * Recover cards from discard to hand.
 * Used by Pal Pad, Energy Retrieval.
 */
EffectResult recover_from_discard(
    GameState& state,
    const CardInstance& source_card,
    PlayerID player_id,
    const std::unordered_map<std::string, std::string>& filter,
    int count,
    int min_count = 0
);

/**
 * Switch active Pokemon with benched Pokemon.
 * Used by Switch, Escape Rope.
 */
EffectResult switch_active(
    GameState& state,
    const CardInstance& source_card,
    PlayerID player_id,
    bool opponent_also = false
);

/**
 * Heal damage from a Pokemon.
 *
 * @param target_id Specific target, or empty to select
 * @param amount Amount of damage to heal (in HP, not counters)
 */
EffectResult heal_damage(
    GameState& state,
    const CardInstance& source_card,
    PlayerID player_id,
    const CardID& target_id,
    int amount
);

/**
 * Add damage counters to a Pokemon.
 * Used by some attack effects.
 */
EffectResult add_damage_counters(
    GameState& state,
    const CardID& target_id,
    int counters
);

// ============================================================================
// SELECTION HELPERS
// ============================================================================

/**
 * Select a Pokemon from the player's bench.
 */
EffectResult select_bench_pokemon(
    GameState& state,
    const CardInstance& source_card,
    PlayerID player_id,
    SelectionPurpose purpose,
    const std::unordered_map<std::string, std::string>& filter = {}
);

/**
 * Select a Pokemon from the player's board (active + bench).
 */
EffectResult select_board_pokemon(
    GameState& state,
    const CardInstance& source_card,
    PlayerID player_id,
    SelectionPurpose purpose,
    const std::unordered_map<std::string, std::string>& filter = {}
);

// ============================================================================
// VALIDATION HELPERS
// ============================================================================

/**
 * Check if player has enough cards in hand to discard.
 */
bool can_discard_from_hand(
    const GameState& state,
    PlayerID player_id,
    int count,
    const std::unordered_map<std::string, std::string>& filter = {}
);

/**
 * Check if player has space on bench.
 */
bool has_bench_space(const GameState& state, PlayerID player_id);

/**
 * Check if player's deck has cards matching filter.
 */
bool deck_has_matching_cards(
    const GameState& state,
    const CardDatabase& db,
    PlayerID player_id,
    const std::unordered_map<std::string, std::string>& filter
);

/**
 * Count matching cards in a zone.
 */
int count_matching_cards(
    const GameState& state,
    const CardDatabase& db,
    PlayerID player_id,
    ZoneType zone,
    const std::unordered_map<std::string, std::string>& filter
);

// ============================================================================
// CARD MATCHING
// ============================================================================

/**
 * Check if a card matches filter criteria.
 * This is the C++ equivalent of Python's card_matches_filter().
 */
bool card_matches_filter(
    const CardDef& card_def,
    const std::unordered_map<std::string, std::string>& filter
);

} // namespace effects
} // namespace pokemon

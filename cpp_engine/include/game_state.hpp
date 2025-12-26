/**
 * Pokemon TCG Engine - Game State
 *
 * The root state object representing the complete game snapshot.
 * Must be fast to clone for MCTS simulations.
 */

#pragma once

#include "player_state.hpp"
#include "resolution_step.hpp"
#include "action.hpp"
#include <array>
#include <random>

namespace pokemon {

/**
 * ActiveEffect - Represents a buff/debuff on the game state.
 */
struct ActiveEffect {
    std::string name;
    EffectSource source;
    CardID source_card_id;

    std::optional<PlayerID> target_player_id;
    std::optional<CardID> target_card_id;

    int duration_turns = 1;  // 1 = this turn, 2 = until end of next turn, -1 = permanent
    int created_turn = 0;
    std::string created_phase;
    std::optional<PlayerID> expires_on_player;

    std::unordered_map<std::string, std::string> params;

    bool is_expired(int current_turn, PlayerID current_player, const std::string& current_phase) const {
        // Permanent effects never expire
        if (duration_turns == -1) {
            return false;
        }

        // Check if effect expires on specific player's turn
        if (expires_on_player.has_value()) {
            if (current_player == *expires_on_player && current_phase == "cleanup") {
                return true;
            }
        }

        // Check turn-based expiration
        int turns_elapsed = current_turn - created_turn;
        return turns_elapsed >= duration_turns;
    }

    ActiveEffect clone() const {
        return *this;  // Struct copy
    }
};

/**
 * GameState - The complete game snapshot.
 *
 * This is the root data structure for MCTS. It must be:
 * - Fast to clone (called on every tree node expansion)
 * - Complete (contains all information needed to continue the game)
 * - Serializable (for debugging and replay)
 */
struct GameState {
    // Players (always exactly 2)
    std::array<PlayerState, 2> players;

    // Turn tracking
    int turn_count = 1;
    PlayerID active_player_index = 0;
    PlayerID starting_player_id = 0;
    GamePhase current_phase = GamePhase::SETUP;

    // Global state
    std::optional<CardInstance> stadium;
    std::vector<ActiveEffect> active_effects;

    // Game result
    GameResult result = GameResult::ONGOING;
    std::optional<PlayerID> winner_id;

    // History tracking
    std::unordered_map<std::string, std::string> turn_metadata;
    std::unordered_map<std::string, std::string> last_turn_metadata;

    // Metadata
    std::optional<uint64_t> random_seed;
    std::vector<std::string> move_history;

    // RNG for game randomness (mutable since it changes state when used)
    mutable std::mt19937 rng;

    // Resolution stack (LIFO)
    std::vector<ResolutionStep> resolution_stack;

    // Attack tracking
    bool attack_resolution_pending = false;

    // ========================================================================
    // CONSTRUCTORS
    // ========================================================================

    GameState() {
        players[0] = PlayerState(0);
        players[1] = PlayerState(1);
    }

    // ========================================================================
    // PLAYER ACCESS
    // ========================================================================

    PlayerState& get_active_player() {
        return players[active_player_index];
    }

    const PlayerState& get_active_player() const {
        return players[active_player_index];
    }

    PlayerState& get_opponent() {
        return players[1 - active_player_index];
    }

    const PlayerState& get_opponent() const {
        return players[1 - active_player_index];
    }

    PlayerState& get_player(PlayerID id) {
        return players[id];
    }

    const PlayerState& get_player(PlayerID id) const {
        return players[id];
    }

    void switch_active_player() {
        active_player_index = 1 - active_player_index;
    }

    // ========================================================================
    // GAME STATUS
    // ========================================================================

    bool is_game_over() const {
        return result != GameResult::ONGOING;
    }

    // ========================================================================
    // RESOLUTION STACK
    // ========================================================================

    bool has_pending_resolution() const {
        return !resolution_stack.empty();
    }

    ResolutionStep* get_current_step() {
        if (resolution_stack.empty()) {
            return nullptr;
        }
        return &resolution_stack.back();
    }

    const ResolutionStep* get_current_step() const {
        if (resolution_stack.empty()) {
            return nullptr;
        }
        return &resolution_stack.back();
    }

    void push_step(ResolutionStep step) {
        // When a search step is pushed, mark that player has searched deck
        if (auto* search_step = std::get_if<SearchDeckStep>(&step)) {
            players[search_step->player_id].has_searched_deck = true;
        }
        resolution_stack.push_back(std::move(step));
    }

    std::optional<ResolutionStep> pop_step() {
        if (resolution_stack.empty()) {
            return std::nullopt;
        }
        ResolutionStep step = std::move(resolution_stack.back());
        resolution_stack.pop_back();
        return step;
    }

    void clear_resolution_stack() {
        resolution_stack.clear();
    }

    // ========================================================================
    // CLONING (Critical for MCTS performance)
    // ========================================================================

    GameState clone() const {
        GameState copy;

        // Clone players
        copy.players[0] = players[0].clone();
        copy.players[1] = players[1].clone();

        // Copy turn tracking
        copy.turn_count = turn_count;
        copy.active_player_index = active_player_index;
        copy.starting_player_id = starting_player_id;
        copy.current_phase = current_phase;

        // Clone stadium
        if (stadium.has_value()) {
            copy.stadium = stadium->clone();
        }

        // Clone active effects
        copy.active_effects.reserve(active_effects.size());
        for (const auto& effect : active_effects) {
            copy.active_effects.push_back(effect.clone());
        }

        // Copy result
        copy.result = result;
        copy.winner_id = winner_id;

        // Copy metadata (shallow copy is fine - strings are COW)
        copy.turn_metadata = turn_metadata;
        copy.last_turn_metadata = last_turn_metadata;
        copy.random_seed = random_seed;
        copy.move_history = move_history;
        copy.rng = rng;  // Copy RNG state for deterministic cloning

        // Clone resolution stack
        copy.resolution_stack.reserve(resolution_stack.size());
        for (const auto& step : resolution_stack) {
            copy.resolution_stack.push_back(clone_step(step));
        }

        copy.attack_resolution_pending = attack_resolution_pending;

        return copy;
    }

    // ========================================================================
    // UTILITY
    // ========================================================================

    // Find a card anywhere in the game (either player)
    CardInstance* find_card(const CardID& card_id) {
        if (auto* c = players[0].find_card_anywhere(card_id)) return c;
        if (auto* c = players[1].find_card_anywhere(card_id)) return c;
        if (stadium.has_value() && stadium->id == card_id) {
            return &stadium.value();
        }
        return nullptr;
    }

    const CardInstance* find_card(const CardID& card_id) const {
        if (auto* c = players[0].find_card_anywhere(card_id)) return c;
        if (auto* c = players[1].find_card_anywhere(card_id)) return c;
        if (stadium.has_value() && stadium->id == card_id) {
            return &stadium.value();
        }
        return nullptr;
    }
};

} // namespace pokemon

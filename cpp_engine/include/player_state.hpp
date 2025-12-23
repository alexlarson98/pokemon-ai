/**
 * Pokemon TCG Engine - Player State
 *
 * Represents a single player's complete state including zones, board, and flags.
 */

#pragma once

#include "zone.hpp"
#include "board.hpp"

namespace pokemon {

/**
 * PlayerState - Complete state for one player.
 *
 * Contains all zones, board, and game/turn flags.
 */
struct PlayerState {
    PlayerID player_id;
    std::string name = "Player";

    // Zones (Constitution Section 1.2)
    Zone deck{true, true, false};     // ordered, hidden, not private
    Zone hand{false, false, true};    // not ordered, not hidden, private
    Zone discard{true, false, false}; // ordered, not hidden, not private
    Zone prizes{true, true, false};   // ordered, hidden, not private

    // Board
    Board board;

    // Global Flags (Constitution Section 3) - persist entire game
    bool vstar_power_used = false;
    bool gx_attack_used = false;

    // Turn Flags - reset each turn
    bool supporter_played_this_turn = false;
    bool energy_attached_this_turn = false;
    bool retreated_this_turn = false;
    bool stadium_played_this_turn = false;

    // Counters
    int prizes_taken = 0;

    // Knowledge Layer (for Belief-Based Action Generation / ISMCTS)
    std::unordered_map<std::string, int> initial_deck_counts;  // functional_id -> count
    std::unordered_map<std::string, std::string> functional_id_map;  // card_id -> functional_id
    bool has_searched_deck = false;

    // ========================================================================
    // CONSTRUCTORS
    // ========================================================================

    PlayerState() = default;

    explicit PlayerState(PlayerID id) : player_id(id) {}

    // ========================================================================
    // TURN MANAGEMENT
    // ========================================================================

    void reset_turn_flags() {
        supporter_played_this_turn = false;
        energy_attached_this_turn = false;
        retreated_this_turn = false;
        stadium_played_this_turn = false;

        // Reset ability usage on all Pokemon
        if (board.active_spot.has_value()) {
            board.active_spot->abilities_used_this_turn.clear();
        }
        for (auto& pokemon : board.bench) {
            pokemon.abilities_used_this_turn.clear();
        }
    }

    void increment_turns_in_play() {
        // Increment turns_in_play for all Pokemon in play
        if (board.active_spot.has_value()) {
            board.active_spot->turns_in_play++;
            board.active_spot->evolved_this_turn = false;
        }
        for (auto& pokemon : board.bench) {
            pokemon.turns_in_play++;
            pokemon.evolved_this_turn = false;
        }
    }

    // ========================================================================
    // QUERIES
    // ========================================================================

    bool has_active_pokemon() const {
        return board.has_active();
    }

    bool has_any_pokemon_in_play() const {
        return board.has_any_pokemon();
    }

    int count_pokemon_in_play() const {
        int count = board.has_active() ? 1 : 0;
        count += board.get_bench_count();
        return count;
    }

    // Find Pokemon across all locations (active + bench)
    CardInstance* find_pokemon(const CardID& card_id) {
        return board.find_pokemon(card_id);
    }

    const CardInstance* find_pokemon(const CardID& card_id) const {
        return board.find_pokemon(card_id);
    }

    // Find card in any zone
    CardInstance* find_card_anywhere(const CardID& card_id) {
        // Check board first (most common case)
        if (auto* p = board.find_pokemon(card_id)) return p;

        // Check zones
        if (auto* c = hand.find_card(card_id)) return c;
        if (auto* c = deck.find_card(card_id)) return c;
        if (auto* c = discard.find_card(card_id)) return c;
        if (auto* c = prizes.find_card(card_id)) return c;

        return nullptr;
    }

    // ========================================================================
    // CLONING
    // ========================================================================

    PlayerState clone() const {
        PlayerState copy;
        copy.player_id = player_id;
        copy.name = name;

        // Clone zones
        copy.deck = deck.clone();
        copy.hand = hand.clone();
        copy.discard = discard.clone();
        copy.prizes = prizes.clone();

        // Clone board
        copy.board = board.clone();

        // Copy flags
        copy.vstar_power_used = vstar_power_used;
        copy.gx_attack_used = gx_attack_used;
        copy.supporter_played_this_turn = supporter_played_this_turn;
        copy.energy_attached_this_turn = energy_attached_this_turn;
        copy.retreated_this_turn = retreated_this_turn;
        copy.stadium_played_this_turn = stadium_played_this_turn;
        copy.prizes_taken = prizes_taken;

        // Copy knowledge layer (shallow copy is fine - strings are COW)
        copy.initial_deck_counts = initial_deck_counts;
        copy.functional_id_map = functional_id_map;
        copy.has_searched_deck = has_searched_deck;

        return copy;
    }
};

} // namespace pokemon

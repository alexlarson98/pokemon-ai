/**
 * Pokemon TCG Engine - Board State
 *
 * Represents a player's board (Active Pokemon + Bench).
 */

#pragma once

#include "card_instance.hpp"
#include <optional>

namespace pokemon {

/**
 * Board - Player's play area.
 *
 * Contains active spot and bench slots.
 */
struct Board {
    std::optional<CardInstance> active_spot;
    std::vector<CardInstance> bench;
    int max_bench_size = 5;  // Default 5, can be 8 with Area Zero Underdepths

    // ========================================================================
    // BASIC OPERATIONS
    // ========================================================================

    int get_bench_count() const {
        return static_cast<int>(bench.size());
    }

    bool can_add_to_bench() const {
        return get_bench_count() < max_bench_size;
    }

    bool add_to_bench(CardInstance pokemon) {
        if (!can_add_to_bench()) {
            return false;
        }
        bench.push_back(std::move(pokemon));
        return true;
    }

    std::optional<CardInstance> remove_from_bench(const CardID& card_id) {
        for (auto it = bench.begin(); it != bench.end(); ++it) {
            if (it->id == card_id) {
                CardInstance removed = std::move(*it);
                bench.erase(it);
                return removed;
            }
        }
        return std::nullopt;
    }

    CardInstance* find_on_bench(const CardID& card_id) {
        for (auto& pokemon : bench) {
            if (pokemon.id == card_id) {
                return &pokemon;
            }
        }
        return nullptr;
    }

    const CardInstance* find_on_bench(const CardID& card_id) const {
        for (const auto& pokemon : bench) {
            if (pokemon.id == card_id) {
                return &pokemon;
            }
        }
        return nullptr;
    }

    // ========================================================================
    // ALL POKEMON ACCESS
    // ========================================================================

    std::vector<CardInstance*> get_all_pokemon() {
        std::vector<CardInstance*> result;
        if (active_spot.has_value()) {
            result.push_back(&active_spot.value());
        }
        for (auto& pokemon : bench) {
            result.push_back(&pokemon);
        }
        return result;
    }

    std::vector<const CardInstance*> get_all_pokemon() const {
        std::vector<const CardInstance*> result;
        if (active_spot.has_value()) {
            result.push_back(&active_spot.value());
        }
        for (const auto& pokemon : bench) {
            result.push_back(&pokemon);
        }
        return result;
    }

    CardInstance* find_pokemon(const CardID& card_id) {
        if (active_spot.has_value() && active_spot->id == card_id) {
            return &active_spot.value();
        }
        return find_on_bench(card_id);
    }

    const CardInstance* find_pokemon(const CardID& card_id) const {
        if (active_spot.has_value() && active_spot->id == card_id) {
            return &active_spot.value();
        }
        return find_on_bench(card_id);
    }

    bool has_active() const {
        return active_spot.has_value();
    }

    bool has_any_pokemon() const {
        return has_active() || !bench.empty();
    }

    // ========================================================================
    // SWITCH OPERATIONS
    // ========================================================================

    // Switch active with a benched Pokemon
    bool switch_active(const CardID& bench_pokemon_id) {
        auto* bench_pokemon = find_on_bench(bench_pokemon_id);
        if (!bench_pokemon || !active_spot.has_value()) {
            return false;
        }

        // Find and remove from bench
        for (auto it = bench.begin(); it != bench.end(); ++it) {
            if (it->id == bench_pokemon_id) {
                // Swap active with bench
                CardInstance old_active = std::move(*active_spot);
                *active_spot = std::move(*it);
                *it = std::move(old_active);
                return true;
            }
        }
        return false;
    }

    // Promote a benched Pokemon to active (when active is KO'd)
    bool promote_to_active(const CardID& bench_pokemon_id) {
        if (active_spot.has_value()) {
            return false;  // Active spot not empty
        }

        for (auto it = bench.begin(); it != bench.end(); ++it) {
            if (it->id == bench_pokemon_id) {
                active_spot = std::move(*it);
                bench.erase(it);
                return true;
            }
        }
        return false;
    }

    // ========================================================================
    // CLONING
    // ========================================================================

    Board clone() const {
        Board copy;
        copy.max_bench_size = max_bench_size;

        if (active_spot.has_value()) {
            copy.active_spot = active_spot->clone();
        }

        copy.bench.reserve(bench.size());
        for (const auto& pokemon : bench) {
            copy.bench.push_back(pokemon.clone());
        }

        return copy;
    }
};

} // namespace pokemon

/**
 * Pokemon TCG Engine - Card Instance
 *
 * Represents a physical card in a zone with mutable runtime state.
 * This is the core data structure that gets cloned frequently during MCTS.
 */

#pragma once

#include "types.hpp"
#include <memory>

namespace pokemon {

/**
 * CardInstance - A physical card in the game.
 *
 * This wraps immutable card definition data with mutable runtime state.
 * Optimized for fast cloning in MCTS simulations.
 */
struct CardInstance {
    // Identity (immutable after creation)
    CardID id;                    // Unique instance ID (e.g., "card_123")
    CardDefID card_id;            // Card definition ID (e.g., "sv3-125")
    PlayerID owner_id;            // Player index (0 or 1)

    // Pokemon-specific state (mutable)
    int16_t current_hp = 0;       // Current HP (0 for non-Pokemon, but stored for all)
    int16_t damage_counters = 0;  // Number of damage counters (10 HP each)

    // Status conditions (bit flags for efficiency)
    uint8_t status_flags = 0;
    static constexpr uint8_t STATUS_POISONED  = 1 << 0;
    static constexpr uint8_t STATUS_BURNED    = 1 << 1;
    static constexpr uint8_t STATUS_ASLEEP    = 1 << 2;
    static constexpr uint8_t STATUS_PARALYZED = 1 << 3;
    static constexpr uint8_t STATUS_CONFUSED  = 1 << 4;

    // Attached cards (vectors of card instances)
    std::vector<CardInstance> attached_energy;
    std::vector<CardInstance> attached_tools;
    std::vector<CardID> evolution_chain;           // Card IDs of evolution history
    std::vector<CardInstance> previous_stages;     // Previous stage Pokemon cards

    // Temporal state
    uint8_t turns_in_play = 0;                     // For evolution sickness
    bool evolved_this_turn = false;                // Blocks further evolution
    std::unordered_set<std::string> abilities_used_this_turn;
    std::vector<std::string> attack_effects;       // Active attack effects

    // Metadata
    bool is_revealed = false;

    // ========================================================================
    // CONSTRUCTORS
    // ========================================================================

    CardInstance() = default;

    CardInstance(CardID id_, CardDefID card_id_, PlayerID owner_id_)
        : id(std::move(id_))
        , card_id(std::move(card_id_))
        , owner_id(owner_id_)
    {}

    // ========================================================================
    // STATUS CONDITION HELPERS
    // ========================================================================

    bool has_status(StatusCondition status) const {
        switch (status) {
            case StatusCondition::POISONED:  return status_flags & STATUS_POISONED;
            case StatusCondition::BURNED:    return status_flags & STATUS_BURNED;
            case StatusCondition::ASLEEP:    return status_flags & STATUS_ASLEEP;
            case StatusCondition::PARALYZED: return status_flags & STATUS_PARALYZED;
            case StatusCondition::CONFUSED:  return status_flags & STATUS_CONFUSED;
            default: return false;
        }
    }

    void add_status(StatusCondition status) {
        switch (status) {
            case StatusCondition::POISONED:  status_flags |= STATUS_POISONED; break;
            case StatusCondition::BURNED:    status_flags |= STATUS_BURNED; break;
            case StatusCondition::ASLEEP:    status_flags |= STATUS_ASLEEP; break;
            case StatusCondition::PARALYZED: status_flags |= STATUS_PARALYZED; break;
            case StatusCondition::CONFUSED:  status_flags |= STATUS_CONFUSED; break;
        }
    }

    void remove_status(StatusCondition status) {
        switch (status) {
            case StatusCondition::POISONED:  status_flags &= ~STATUS_POISONED; break;
            case StatusCondition::BURNED:    status_flags &= ~STATUS_BURNED; break;
            case StatusCondition::ASLEEP:    status_flags &= ~STATUS_ASLEEP; break;
            case StatusCondition::PARALYZED: status_flags &= ~STATUS_PARALYZED; break;
            case StatusCondition::CONFUSED:  status_flags &= ~STATUS_CONFUSED; break;
        }
    }

    void clear_all_status() {
        status_flags = 0;
    }

    bool is_asleep_or_paralyzed() const {
        return (status_flags & (STATUS_ASLEEP | STATUS_PARALYZED)) != 0;
    }

    // ========================================================================
    // HP / DAMAGE HELPERS
    // ========================================================================

    int get_total_hp_loss() const {
        return damage_counters * 10;
    }

    bool is_knocked_out(int max_hp) const {
        return get_total_hp_loss() >= max_hp;
    }

    // ========================================================================
    // ENERGY HELPERS
    // ========================================================================

    int total_attached_energy() const {
        return static_cast<int>(attached_energy.size());
    }

    // ========================================================================
    // CLONING (Optimized for MCTS)
    // ========================================================================

    CardInstance clone() const {
        CardInstance copy;
        copy.id = id;
        copy.card_id = card_id;
        copy.owner_id = owner_id;
        copy.current_hp = current_hp;
        copy.damage_counters = damage_counters;
        copy.status_flags = status_flags;

        // Clone attached cards (deep copy)
        copy.attached_energy.reserve(attached_energy.size());
        for (const auto& e : attached_energy) {
            copy.attached_energy.push_back(e.clone());
        }

        copy.attached_tools.reserve(attached_tools.size());
        for (const auto& t : attached_tools) {
            copy.attached_tools.push_back(t.clone());
        }

        copy.evolution_chain = evolution_chain;  // Strings are COW

        copy.previous_stages.reserve(previous_stages.size());
        for (const auto& p : previous_stages) {
            copy.previous_stages.push_back(p.clone());
        }

        copy.turns_in_play = turns_in_play;
        copy.evolved_this_turn = evolved_this_turn;
        copy.abilities_used_this_turn = abilities_used_this_turn;
        copy.attack_effects = attack_effects;
        copy.is_revealed = is_revealed;

        return copy;
    }
};

} // namespace pokemon

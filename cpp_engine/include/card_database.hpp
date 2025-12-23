/**
 * Pokemon TCG Engine - Card Database
 *
 * Stores immutable card definitions loaded from JSON.
 * Provides fast lookup by card_id.
 */

#pragma once

#include "types.hpp"
#include <unordered_map>

namespace pokemon {

/**
 * Attack definition (immutable).
 */
struct AttackDef {
    std::string name;
    std::vector<EnergyType> cost;
    int converted_energy_cost = 0;
    int base_damage = 0;
    std::string damage_modifier;  // "", "+", "x" for variable damage
    std::string text;

    // Logic function names (looked up in logic registry)
    std::string effect_function;
    std::string generator_function;
};

/**
 * Ability definition (immutable).
 */
struct AbilityDef {
    std::string name;
    std::string text;
    std::string ability_type;  // "Ability", "VSTAR Power", etc.
    std::string category;      // "activatable", "modifier", "guard", "hook"
    bool is_activatable = false;

    // Logic function name
    std::string effect_function;
};

/**
 * Card definition (immutable).
 *
 * Base class for all card types.
 */
struct CardDef {
    CardDefID card_id;
    std::string name;
    Supertype supertype;
    std::vector<Subtype> subtypes;

    // Pokemon-specific
    int hp = 0;
    std::vector<EnergyType> types;
    std::optional<EnergyType> weakness;
    std::optional<EnergyType> resistance;
    int retreat_cost = 0;
    std::optional<std::string> evolves_from;
    std::vector<AttackDef> attacks;
    std::vector<AbilityDef> abilities;

    // Energy-specific
    bool is_basic_energy = false;
    EnergyType energy_type = EnergyType::COLORLESS;
    std::vector<EnergyType> provides;

    // Trainer-specific
    std::string rules_text;

    // Helper methods
    bool is_pokemon() const { return supertype == Supertype::POKEMON; }
    bool is_trainer() const { return supertype == Supertype::TRAINER; }
    bool is_energy() const { return supertype == Supertype::ENERGY; }

    bool is_basic_pokemon() const {
        return is_pokemon() && std::find(subtypes.begin(), subtypes.end(), Subtype::BASIC) != subtypes.end();
    }

    bool is_stage_1() const {
        return is_pokemon() && std::find(subtypes.begin(), subtypes.end(), Subtype::STAGE_1) != subtypes.end();
    }

    bool is_stage_2() const {
        return is_pokemon() && std::find(subtypes.begin(), subtypes.end(), Subtype::STAGE_2) != subtypes.end();
    }

    bool is_ex() const {
        return std::find(subtypes.begin(), subtypes.end(), Subtype::EX) != subtypes.end();
    }

    bool is_item() const {
        return std::find(subtypes.begin(), subtypes.end(), Subtype::ITEM) != subtypes.end();
    }

    bool is_supporter() const {
        return std::find(subtypes.begin(), subtypes.end(), Subtype::SUPPORTER) != subtypes.end();
    }

    bool is_stadium() const {
        return std::find(subtypes.begin(), subtypes.end(), Subtype::STADIUM) != subtypes.end();
    }

    bool is_tool() const {
        return std::find(subtypes.begin(), subtypes.end(), Subtype::TOOL) != subtypes.end();
    }

    // Check if this card can evolve from another
    bool can_evolve_from(const std::string& pokemon_name) const {
        return evolves_from.has_value() && *evolves_from == pokemon_name;
    }

    // Get prize cards for KO (ex gives 2, VSTAR gives 2, etc.)
    int get_prize_value() const {
        if (is_ex()) return 2;
        if (std::find(subtypes.begin(), subtypes.end(), Subtype::VSTAR) != subtypes.end()) return 2;
        if (std::find(subtypes.begin(), subtypes.end(), Subtype::V) != subtypes.end()) return 2;
        if (std::find(subtypes.begin(), subtypes.end(), Subtype::VMAX) != subtypes.end()) return 3;
        if (std::find(subtypes.begin(), subtypes.end(), Subtype::GX) != subtypes.end()) return 2;
        return 1;
    }
};

/**
 * CardDatabase - Central card lookup.
 *
 * Loads cards from JSON and provides fast lookup.
 * Card definitions are immutable and shared.
 */
class CardDatabase {
public:
    CardDatabase();
    ~CardDatabase() = default;

    /**
     * Load cards from a JSON file.
     */
    bool load_from_json(const std::string& filepath);

    /**
     * Get a card definition by ID.
     *
     * Returns nullptr if card not found.
     */
    const CardDef* get_card(const CardDefID& card_id) const;

    /**
     * Check if a card exists.
     */
    bool has_card(const CardDefID& card_id) const;

    /**
     * Get all card IDs.
     */
    std::vector<CardDefID> get_all_card_ids() const;

    /**
     * Get card count.
     */
    size_t card_count() const { return cards_.size(); }

private:
    std::unordered_map<CardDefID, CardDef> cards_;

    // Parse helpers
    static Supertype parse_supertype(const std::string& s);
    static Subtype parse_subtype(const std::string& s);
    static EnergyType parse_energy_type(const std::string& s);
};

} // namespace pokemon

/**
 * Pokemon TCG Engine - Card Database
 *
 * Stores immutable card definitions loaded from JSON.
 * Provides fast lookup by card_id.
 */

#pragma once

#include "types.hpp"
#include <unordered_map>
#include <nlohmann/json_fwd.hpp>

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
 *
 * Categories match Python's logic_registry.py:
 * - "activatable": Player-triggered ability, generates actions (e.g., Infernal Reign)
 * - "modifier": Continuously modifies values (retreat cost, damage, HP) (e.g., Agile)
 * - "guard": Blocks effects/conditions (status, damage) (e.g., Insomnia)
 * - "hook": Event-triggered (on_play, on_knockout, on_evolve) (e.g., Insta-Flock)
 * - "passive": Passive ability lock that blocks other abilities (e.g., Mischievous Lock)
 */
struct AbilityDef {
    std::string name;
    std::string text;
    std::string ability_type;  // "Ability", "VSTAR Power", "Poke-Power", etc.
    std::string category;      // "activatable", "modifier", "guard", "hook", "passive"
    bool is_activatable = false;

    // For modifiers
    std::string modifier_type;  // "retreat_cost", "damage", "hp", "global_retreat_cost"

    // For guards
    std::string guard_type;     // "status_condition", "damage", "effect", "global_play_item"

    // For hooks
    std::string trigger;        // "on_play", "on_knockout", "on_evolve", "on_attach_energy"

    // For passives
    std::string effect_type;    // "ability_lock", "item_lock"

    // Scope: "self", "all", "opponent", "active"
    std::string scope = "self";

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
    int weakness_multiplier = 2;  // Default x2
    std::optional<EnergyType> resistance;
    int resistance_value = -30;   // Default -30
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

    bool is_tera() const {
        return std::find(subtypes.begin(), subtypes.end(), Subtype::TERA) != subtypes.end();
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

    /**
     * Compute functional ID for deduplication.
     *
     * Two cards with the same name but different HP, attacks, or abilities
     * will have different functional IDs. This is critical for MCTS as
     * Charmander 80HP with an ability is functionally different from
     * Charmander 70HP with no ability.
     *
     * Format: "name|hp|attack1_cost_damage|attack2_cost_damage|ability1_name"
     */
    std::string get_functional_id() const {
        std::string fid = name;

        if (is_pokemon()) {
            fid += "|" + std::to_string(hp);

            // Add attack signatures
            for (const auto& attack : attacks) {
                fid += "|" + attack.name + "_" +
                       std::to_string(attack.converted_energy_cost) + "_" +
                       std::to_string(attack.base_damage);
            }

            // Add ability names
            for (const auto& ability : abilities) {
                fid += "|A:" + ability.name;
            }
        } else if (is_energy()) {
            fid += "|E:" + std::to_string(static_cast<int>(energy_type));
            if (is_basic_energy) fid += "_basic";
        } else if (is_trainer()) {
            // For trainers, include the card_id since same-name trainers
            // could have different effects in different sets
            fid += "|T:" + card_id;
        }

        return fid;
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

    /**
     * Static parsing utilities - public for use by other components.
     */
    static Supertype parse_supertype(const std::string& s);
    static Subtype parse_subtype(const std::string& s);
    static EnergyType parse_energy_type(const std::string& s);

private:
    std::unordered_map<CardDefID, CardDef> cards_;

    // Parse helpers
    CardDef parse_card(const nlohmann::json& card_json) const;
    void parse_pokemon_fields(const nlohmann::json& card_json, CardDef& card) const;
    void parse_energy_fields(const nlohmann::json& card_json, CardDef& card) const;
    void parse_trainer_fields(const nlohmann::json& card_json, CardDef& card) const;
    AttackDef parse_attack(const nlohmann::json& attack_json) const;
    AbilityDef parse_ability(const nlohmann::json& ability_json) const;
};

} // namespace pokemon

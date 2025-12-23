/**
 * Pokemon TCG Engine - Action Representation
 *
 * Defines the Action struct used by get_legal_actions() and step().
 */

#pragma once

#include "types.hpp"
#include <optional>

namespace pokemon {

/**
 * Action - A single game action.
 *
 * Used by Engine::get_legal_actions() and Engine::step().
 * Designed for fast comparison and hashing.
 */
struct Action {
    ActionType action_type;
    PlayerID player_id;

    // Optional parameters based on action type
    std::optional<CardID> card_id;
    std::optional<CardID> target_id;
    std::optional<std::string> attack_name;
    std::optional<std::string> ability_name;
    std::optional<int> choice_index;

    // Additional metadata (for complex actions)
    std::unordered_map<std::string, std::string> metadata;

    // Parameters for multi-step actions
    std::unordered_map<std::string, std::string> parameters;

    // Display label for UI/logging
    std::string display_label;

    // ========================================================================
    // CONSTRUCTORS
    // ========================================================================

    Action() = default;

    Action(ActionType type, PlayerID player)
        : action_type(type)
        , player_id(player)
    {}

    // ========================================================================
    // FACTORY METHODS
    // ========================================================================

    static Action end_turn(PlayerID player) {
        return Action(ActionType::END_TURN, player);
    }

    static Action place_active(PlayerID player, const CardID& card) {
        Action a(ActionType::PLACE_ACTIVE, player);
        a.card_id = card;
        return a;
    }

    static Action place_bench(PlayerID player, const CardID& card) {
        Action a(ActionType::PLACE_BENCH, player);
        a.card_id = card;
        return a;
    }

    static Action play_basic(PlayerID player, const CardID& card) {
        Action a(ActionType::PLAY_BASIC, player);
        a.card_id = card;
        return a;
    }

    static Action evolve(PlayerID player, const CardID& evo_card, const CardID& target) {
        Action a(ActionType::EVOLVE, player);
        a.card_id = evo_card;
        a.target_id = target;
        return a;
    }

    static Action attach_energy(PlayerID player, const CardID& energy, const CardID& target) {
        Action a(ActionType::ATTACH_ENERGY, player);
        a.card_id = energy;
        a.target_id = target;
        return a;
    }

    static Action attack(PlayerID player, const CardID& attacker, const std::string& attack) {
        Action a(ActionType::ATTACK, player);
        a.card_id = attacker;
        a.attack_name = attack;
        return a;
    }

    static Action use_ability(PlayerID player, const CardID& card, const std::string& ability) {
        Action a(ActionType::USE_ABILITY, player);
        a.card_id = card;
        a.ability_name = ability;
        return a;
    }

    static Action retreat(PlayerID player, const CardID& active, const CardID& replacement) {
        Action a(ActionType::RETREAT, player);
        a.card_id = active;
        a.target_id = replacement;
        return a;
    }

    static Action play_item(PlayerID player, const CardID& card) {
        Action a(ActionType::PLAY_ITEM, player);
        a.card_id = card;
        return a;
    }

    static Action play_supporter(PlayerID player, const CardID& card) {
        Action a(ActionType::PLAY_SUPPORTER, player);
        a.card_id = card;
        return a;
    }

    static Action play_stadium(PlayerID player, const CardID& card) {
        Action a(ActionType::PLAY_STADIUM, player);
        a.card_id = card;
        return a;
    }

    static Action attach_tool(PlayerID player, const CardID& tool, const CardID& target) {
        Action a(ActionType::ATTACH_TOOL, player);
        a.card_id = tool;
        a.target_id = target;
        return a;
    }

    static Action take_prize(PlayerID player, int prize_index) {
        Action a(ActionType::TAKE_PRIZE, player);
        a.choice_index = prize_index;
        return a;
    }

    static Action promote_active(PlayerID player, const CardID& bench_pokemon) {
        Action a(ActionType::PROMOTE_ACTIVE, player);
        a.card_id = bench_pokemon;
        return a;
    }

    static Action select_card(PlayerID player, const CardID& card) {
        Action a(ActionType::SELECT_CARD, player);
        a.card_id = card;
        return a;
    }

    static Action confirm_selection(PlayerID player) {
        return Action(ActionType::CONFIRM_SELECTION, player);
    }

    // ========================================================================
    // STRING REPRESENTATION
    // ========================================================================

    std::string to_string() const {
        if (!display_label.empty()) {
            return display_label;
        }

        std::string result = "Action(";
        result += std::to_string(static_cast<int>(action_type));

        if (card_id.has_value()) {
            result += ", card=" + *card_id;
        }
        if (target_id.has_value()) {
            result += ", target=" + *target_id;
        }
        if (attack_name.has_value()) {
            result += ", attack=" + *attack_name;
        }
        if (ability_name.has_value()) {
            result += ", ability=" + *ability_name;
        }
        result += ")";
        return result;
    }

    // ========================================================================
    // COMPARISON
    // ========================================================================

    bool operator==(const Action& other) const {
        return action_type == other.action_type
            && player_id == other.player_id
            && card_id == other.card_id
            && target_id == other.target_id
            && attack_name == other.attack_name
            && ability_name == other.ability_name
            && choice_index == other.choice_index;
    }

    bool operator!=(const Action& other) const {
        return !(*this == other);
    }
};

} // namespace pokemon

// Hash function for Action (for use in unordered_set/map)
namespace std {
    template<>
    struct hash<pokemon::Action> {
        size_t operator()(const pokemon::Action& a) const {
            size_t h = hash<int>()(static_cast<int>(a.action_type));
            h ^= hash<int>()(a.player_id) << 1;
            if (a.card_id) h ^= hash<string>()(*a.card_id) << 2;
            if (a.target_id) h ^= hash<string>()(*a.target_id) << 3;
            if (a.attack_name) h ^= hash<string>()(*a.attack_name) << 4;
            if (a.ability_name) h ^= hash<string>()(*a.ability_name) << 5;
            if (a.choice_index) h ^= hash<int>()(*a.choice_index) << 6;
            return h;
        }
    };
}

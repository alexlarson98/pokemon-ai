/**
 * Pokemon TCG Engine - Resolution Step
 *
 * Implements the resolution stack for multi-step actions.
 * This replaces atomic actions with a sequence of simple choices.
 */

#pragma once

#include "types.hpp"
#include <variant>

namespace pokemon {

/**
 * SelectFromZoneStep - Select cards from a specific zone.
 *
 * Used for discarding from hand, selecting Pokemon on bench, etc.
 */
struct SelectFromZoneStep {
    StepType step_type = StepType::SELECT_FROM_ZONE;
    CardID source_card_id;
    std::string source_card_name;
    PlayerID player_id;
    SelectionPurpose purpose;
    bool is_complete = false;
    std::optional<std::string> on_complete_callback;

    // Selection parameters
    ZoneType zone;
    int count = 1;
    int min_count = 0;
    bool exact_count = false;

    // Filtering
    std::unordered_map<std::string, std::string> filter_criteria;
    std::vector<CardID> exclude_card_ids;

    // State tracking
    std::vector<CardID> selected_card_ids;

    // Context for chained steps
    std::unordered_map<std::string, std::string> context;
};

/**
 * SearchDeckStep - Search deck and select cards.
 *
 * Used for Nest Ball, Ultra Ball, etc.
 */
struct SearchDeckStep {
    StepType step_type = StepType::SEARCH_DECK;
    CardID source_card_id;
    std::string source_card_name;
    PlayerID player_id;
    SelectionPurpose purpose;
    bool is_complete = false;
    std::optional<std::string> on_complete_callback;

    // Search parameters
    int count = 1;
    int min_count = 0;
    ZoneType destination = ZoneType::HAND;

    // Filtering
    std::unordered_map<std::string, std::string> filter_criteria;

    // State tracking
    std::vector<CardID> selected_card_ids;

    // Options
    bool shuffle_after = true;
    bool reveal_cards = false;
};

/**
 * AttachToTargetStep - Attach a card to a target Pokemon.
 *
 * Used for Infernal Reign, energy attachment effects, etc.
 */
struct AttachToTargetStep {
    StepType step_type = StepType::ATTACH_TO_TARGET;
    CardID source_card_id;
    std::string source_card_name;
    PlayerID player_id;
    SelectionPurpose purpose;
    bool is_complete = false;
    std::optional<std::string> on_complete_callback;

    // What to attach
    CardID card_to_attach_id;
    std::string card_to_attach_name;

    // Valid targets
    std::vector<CardID> valid_target_ids;

    // Selected target
    std::optional<CardID> selected_target_id;
};

/**
 * EvolveTargetStep - Evolve a specific Pokemon.
 *
 * Used for Rare Candy, evolution effects, etc.
 */
struct EvolveTargetStep {
    StepType step_type = StepType::EVOLVE_TARGET;
    CardID source_card_id;
    std::string source_card_name;
    PlayerID player_id;
    SelectionPurpose purpose;
    bool is_complete = false;
    std::optional<std::string> on_complete_callback;

    // Evolution details
    CardID base_pokemon_id;
    CardID evolution_card_id;

    // Validation
    bool skip_evolution_sickness = false;
    bool skip_stage = false;
};

// Variant type for all resolution steps
using ResolutionStep = std::variant<
    SelectFromZoneStep,
    SearchDeckStep,
    AttachToTargetStep,
    EvolveTargetStep
>;

// Helper functions for ResolutionStep

inline StepType get_step_type(const ResolutionStep& step) {
    return std::visit([](const auto& s) { return s.step_type; }, step);
}

inline PlayerID get_step_player(const ResolutionStep& step) {
    return std::visit([](const auto& s) { return s.player_id; }, step);
}

inline bool is_step_complete(const ResolutionStep& step) {
    return std::visit([](const auto& s) { return s.is_complete; }, step);
}

inline CardID get_step_source_card(const ResolutionStep& step) {
    return std::visit([](const auto& s) { return s.source_card_id; }, step);
}

// Clone a resolution step
inline ResolutionStep clone_step(const ResolutionStep& step) {
    return std::visit([](const auto& s) -> ResolutionStep {
        return s;  // Struct copy
    }, step);
}

/**
 * Legacy SearchAndAttachState - For backward compatibility.
 *
 * Used for Infernal Reign and similar multi-step abilities.
 */
struct SearchAndAttachState {
    std::string ability_name;
    CardID source_card_id;
    PlayerID player_id;

    enum class Phase : uint8_t {
        SELECT_COUNT,
        SEARCH_SELECT,
        ATTACH_ENERGY
    };
    Phase phase = Phase::SELECT_COUNT;

    // Search parameters
    std::unordered_map<std::string, std::string> search_filter;
    int max_select = 3;

    // State tracking
    std::vector<CardID> selected_card_ids;
    std::vector<CardID> cards_to_attach;
    int current_attach_index = 0;
    std::unordered_map<CardID, CardDefID> card_definition_map;

    bool is_complete = false;

    // Clone
    SearchAndAttachState clone() const {
        return *this;  // Struct copy
    }
};

} // namespace pokemon

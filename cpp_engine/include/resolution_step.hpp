/**
 * Pokemon TCG Engine - Resolution Step
 *
 * Implements the resolution stack for multi-step actions.
 * This replaces atomic actions with a sequence of simple choices.
 *
 * ARCHITECTURE NOTE (2024-12):
 * Step completion uses a callback-based system rather than string identifiers.
 * Each step carries its own completion logic, keeping card-specific behavior
 * with the card definition rather than scattered in the engine.
 *
 * When creating a new trainer/ability that uses resolution steps:
 * 1. Create the appropriate step type (SearchDeckStep, SelectFromZoneStep, etc.)
 * 2. Set the on_complete callback with the card-specific completion logic
 * 3. The engine will invoke the callback when the step completes
 *
 * See cpp_engine/docs/CARD_INTEGRATION.md for full documentation.
 */

#pragma once

#include "types.hpp"
#include <variant>
#include <functional>
#include <memory>

namespace pokemon {

// Forward declarations
struct GameState;
struct SelectFromZoneStep;
struct SearchDeckStep;
struct AttachToTargetStep;
struct EvolveTargetStep;

// ============================================================================
// STEP COMPLETION CALLBACK
// ============================================================================

/**
 * StepCompletionCallback - Function called when a resolution step completes.
 *
 * Parameters:
 * - GameState& state: The current game state (mutable)
 * - const std::vector<CardID>& selected: Cards selected during this step
 * - PlayerID player: The player who owns this step
 *
 * The callback is responsible for:
 * - Moving cards to their destination zones
 * - Shuffling decks if needed
 * - Pushing any follow-up steps onto the resolution stack
 * - Any card-specific side effects
 *
 * NOTE: The step has already been popped from the stack when this is called.
 */
using StepCompletionCallback = std::function<void(
    GameState& state,
    const std::vector<CardID>& selected_cards,
    PlayerID player_id
)>;

/**
 * Wrapper to make callbacks copyable for use in variant types.
 * Uses shared_ptr internally so copies share the same callback.
 */
struct CompletionCallback {
    std::shared_ptr<StepCompletionCallback> callback;

    CompletionCallback() = default;

    explicit CompletionCallback(StepCompletionCallback cb)
        : callback(std::make_shared<StepCompletionCallback>(std::move(cb))) {}

    bool has_value() const { return callback && *callback; }

    void invoke(GameState& state, const std::vector<CardID>& selected, PlayerID player) const {
        if (has_value()) {
            (*callback)(state, selected, player);
        }
    }

    // For compatibility with existing code checking .has_value()
    explicit operator bool() const { return has_value(); }
};

// ============================================================================
// RESOLUTION STEP TYPES
// ============================================================================

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

    // NEW: Callback-based completion (replaces string on_complete_callback)
    CompletionCallback on_complete;

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

    // Context for chained steps (generic key-value storage)
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

    // NEW: Callback-based completion (replaces string on_complete_callback)
    CompletionCallback on_complete;

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

    // NEW: Callback-based completion (replaces string on_complete_callback)
    CompletionCallback on_complete;

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

    // NEW: Callback-based completion (replaces string on_complete_callback)
    CompletionCallback on_complete;

    // Evolution details
    CardID base_pokemon_id;
    CardID evolution_card_id;

    // Validation
    bool skip_evolution_sickness = false;
    bool skip_stage = false;
};

// ============================================================================
// VARIANT TYPE
// ============================================================================

// Variant type for all resolution steps
using ResolutionStep = std::variant<
    SelectFromZoneStep,
    SearchDeckStep,
    AttachToTargetStep,
    EvolveTargetStep
>;

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

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

inline bool has_completion_callback(const ResolutionStep& step) {
    return std::visit([](const auto& s) { return s.on_complete.has_value(); }, step);
}

/**
 * Get selected cards from a step (works for all step types that track selections)
 */
inline std::vector<CardID> get_selected_cards(const ResolutionStep& step) {
    return std::visit([](const auto& s) -> std::vector<CardID> {
        using T = std::decay_t<decltype(s)>;
        if constexpr (std::is_same_v<T, SelectFromZoneStep> ||
                      std::is_same_v<T, SearchDeckStep>) {
            return s.selected_card_ids;
        }
        else if constexpr (std::is_same_v<T, AttachToTargetStep>) {
            if (s.selected_target_id.has_value()) {
                return {*s.selected_target_id};
            }
            return {};
        }
        else {
            return {};
        }
    }, step);
}

/**
 * Invoke the completion callback for a step
 */
inline void invoke_completion_callback(
    const ResolutionStep& step,
    GameState& state
) {
    std::visit([&](const auto& s) {
        if (s.on_complete.has_value()) {
            auto selected = get_selected_cards(step);
            s.on_complete.invoke(state, selected, s.player_id);
        }
    }, step);
}

// Clone a resolution step
inline ResolutionStep clone_step(const ResolutionStep& step) {
    return std::visit([](const auto& s) -> ResolutionStep {
        return s;  // Struct copy (callback shared_ptr is copied)
    }, step);
}

} // namespace pokemon

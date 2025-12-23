/**
 * Pokemon TCG Engine - Core Type Definitions
 *
 * This file defines all enums and basic types used throughout the engine.
 * These map directly to the Python models.py enums.
 */

#pragma once

#include <cstdint>
#include <string>
#include <vector>
#include <unordered_set>
#include <unordered_map>
#include <optional>
#include <memory>

namespace pokemon {

// ============================================================================
// ENUMS - Match Python models.py exactly
// ============================================================================

enum class Supertype : uint8_t {
    POKEMON,
    TRAINER,
    ENERGY
};

enum class Subtype : uint8_t {
    // Pokemon subtypes
    BASIC,
    STAGE_1,
    STAGE_2,
    TERA,
    EX,
    VSTAR,
    MEGA,
    V,
    VMAX,
    GX,
    ANCIENT,
    FUTURE,
    // Trainer subtypes
    ITEM,
    SUPPORTER,
    STADIUM,
    TOOL,
    ACE_SPEC
};

enum class EnergyType : uint8_t {
    GRASS,
    FIRE,
    WATER,
    LIGHTNING,
    PSYCHIC,
    FIGHTING,
    DARKNESS,
    METAL,
    COLORLESS
};

enum class StatusCondition : uint8_t {
    POISONED,
    BURNED,
    ASLEEP,
    PARALYZED,
    CONFUSED
};

enum class GamePhase : uint8_t {
    SETUP,
    MULLIGAN,
    DRAW,
    MAIN,
    ATTACK,
    CLEANUP,
    END,
    SUDDEN_DEATH
};

enum class GameResult : uint8_t {
    ONGOING,
    PLAYER_0_WIN,
    PLAYER_1_WIN,
    DRAW
};

enum class ActionType : uint8_t {
    // Setup
    MULLIGAN_DRAW,
    REVEAL_HAND_MULLIGAN,
    PLACE_ACTIVE,
    PLACE_BENCH,

    // Main phase
    PLAY_BASIC,
    EVOLVE,
    ATTACH_ENERGY,
    PLAY_ITEM,
    PLAY_SUPPORTER,
    PLAY_STADIUM,
    ATTACH_TOOL,
    USE_ABILITY,
    RETREAT,

    // Attack phase
    ATTACK,
    END_TURN,

    // Reactions
    TAKE_PRIZE,
    PROMOTE_ACTIVE,
    DISCARD_BENCH,

    // Legacy interrupt actions
    SEARCH_SELECT_COUNT,
    SEARCH_SELECT_CARD,
    SEARCH_CONFIRM,
    INTERRUPT_ATTACH_ENERGY,

    // Resolution stack actions
    SELECT_CARD,
    CONFIRM_SELECTION,
    CANCEL_ACTION,

    // Chance
    COIN_FLIP,
    SHUFFLE
};

enum class StepType : uint8_t {
    SELECT_FROM_ZONE,
    SEARCH_DECK,
    ATTACH_TO_TARGET,
    EVOLVE_TARGET
};

enum class SelectionPurpose : uint8_t {
    DISCARD_COST,
    SEARCH_TARGET,
    EVOLUTION_BASE,
    EVOLUTION_STAGE,
    ATTACH_TARGET,
    BENCH_TARGET,
    ENERGY_TO_ATTACH,
    SWITCH_TARGET,
    RECOVER_TO_DECK,
    RECOVER_TO_HAND,
    DISCARD_FROM_PLAY
};

enum class ZoneType : uint8_t {
    HAND,
    DECK,
    BENCH,
    ACTIVE,
    BOARD,
    DISCARD
};

enum class EffectSource : uint8_t {
    ATTACK,
    ABILITY,
    TRAINER,
    TOOL,
    STADIUM,
    ENERGY
};

// ============================================================================
// TYPE ALIASES
// ============================================================================

using CardID = std::string;           // Unique instance ID (e.g., "card_123")
using CardDefID = std::string;        // Card definition ID (e.g., "sv3-125")
using PlayerID = uint8_t;             // 0 or 1
using EnergyCost = std::vector<EnergyType>;

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

inline const char* to_string(GamePhase phase) {
    switch (phase) {
        case GamePhase::SETUP: return "setup";
        case GamePhase::MULLIGAN: return "mulligan";
        case GamePhase::DRAW: return "draw";
        case GamePhase::MAIN: return "main";
        case GamePhase::ATTACK: return "attack";
        case GamePhase::CLEANUP: return "cleanup";
        case GamePhase::END: return "end";
        case GamePhase::SUDDEN_DEATH: return "sudden_death";
        default: return "unknown";
    }
}

inline const char* to_string(GameResult result) {
    switch (result) {
        case GameResult::ONGOING: return "ongoing";
        case GameResult::PLAYER_0_WIN: return "player_0_win";
        case GameResult::PLAYER_1_WIN: return "player_1_win";
        case GameResult::DRAW: return "draw";
        default: return "unknown";
    }
}

inline const char* to_string(EnergyType type) {
    switch (type) {
        case EnergyType::GRASS: return "Grass";
        case EnergyType::FIRE: return "Fire";
        case EnergyType::WATER: return "Water";
        case EnergyType::LIGHTNING: return "Lightning";
        case EnergyType::PSYCHIC: return "Psychic";
        case EnergyType::FIGHTING: return "Fighting";
        case EnergyType::DARKNESS: return "Darkness";
        case EnergyType::METAL: return "Metal";
        case EnergyType::COLORLESS: return "Colorless";
        default: return "Unknown";
    }
}

} // namespace pokemon

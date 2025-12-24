/**
 * Pokemon TCG Engine - C++ Implementation
 *
 * High-performance game engine for MCTS-based AI.
 * Designed for 20-50x speedup over Python implementation.
 *
 * Include this header to get access to the complete engine API.
 */

#pragma once

// Core types
#include "types.hpp"

// Data structures
#include "card_instance.hpp"
#include "zone.hpp"
#include "board.hpp"
#include "player_state.hpp"
#include "action.hpp"
#include "resolution_step.hpp"
#include "game_state.hpp"

// Card database
#include "card_database.hpp"

// Logic registry
#include "logic_registry.hpp"

// Engine
#include "engine.hpp"

namespace pokemon {

/**
 * Version information.
 */
constexpr int VERSION_MAJOR = 1;
constexpr int VERSION_MINOR = 0;
constexpr int VERSION_PATCH = 0;

inline std::string get_version() {
    return std::to_string(VERSION_MAJOR) + "." +
           std::to_string(VERSION_MINOR) + "." +
           std::to_string(VERSION_PATCH);
}

} // namespace pokemon

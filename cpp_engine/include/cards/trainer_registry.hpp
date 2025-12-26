/**
 * Pokemon TCG Engine - Trainer Registry
 *
 * Central registration point for all trainer card effects.
 * Provides a clean interface to register trainer handlers
 * and a function to register all known trainers at startup.
 */

#pragma once

#include "../logic_registry.hpp"
#include "../card_database.hpp"
#include "effect_builders.hpp"
#include <string>
#include <vector>

namespace pokemon {
namespace trainers {

// ============================================================================
// TRAINER INFO STRUCTURE
// ============================================================================

/**
 * TrainerInfo - Metadata about a registered trainer.
 */
struct TrainerInfo {
    CardDefID card_id;
    std::string name;
    std::string category;      // "item", "supporter", "stadium", "tool"
    std::string description;   // What the trainer does
    bool implemented = false;
};

// ============================================================================
// REGISTRATION FUNCTIONS
// ============================================================================

/**
 * Register all implemented trainer effects.
 *
 * Call this once at startup to populate the LogicRegistry
 * with all trainer handlers.
 */
void register_all_trainers(LogicRegistry& registry);

/**
 * Get list of all known trainers and their implementation status.
 */
std::vector<TrainerInfo> get_trainer_info();

/**
 * Check if a specific trainer is implemented.
 */
bool is_trainer_implemented(const CardDefID& card_id);

// ============================================================================
// INDIVIDUAL TRAINER REGISTRATIONS
// ============================================================================

// Items
void register_nest_ball(LogicRegistry& registry);
void register_buddy_buddy_poffin(LogicRegistry& registry);
void register_ultra_ball(LogicRegistry& registry);
void register_rare_candy(LogicRegistry& registry);
void register_switch(LogicRegistry& registry);
void register_potion(LogicRegistry& registry);
void register_super_rod(LogicRegistry& registry);
void register_energy_retrieval(LogicRegistry& registry);
void register_professors_letter(LogicRegistry& registry);
void register_night_stretcher(LogicRegistry& registry);
void register_max_potion(LogicRegistry& registry);
void register_full_heal(LogicRegistry& registry);
void register_pokegear(LogicRegistry& registry);
void register_pal_pad(LogicRegistry& registry);
void register_escape_rope(LogicRegistry& registry);

// Supporters
void register_iono(LogicRegistry& registry);
void register_professors_research(LogicRegistry& registry);
void register_boss_orders(LogicRegistry& registry);
void register_judge(LogicRegistry& registry);
void register_marnie(LogicRegistry& registry);

// Stadiums
void register_training_court(LogicRegistry& registry);
void register_artazon(LogicRegistry& registry);

// Tools
void register_exp_share(LogicRegistry& registry);
void register_choice_belt(LogicRegistry& registry);

// ============================================================================
// GENERATOR FUNCTIONS
// ============================================================================

/**
 * Check if a trainer can currently be played.
 *
 * Returns empty if trainer can't be played,
 * otherwise returns the TrainerResult with any pre-checks.
 */
std::optional<TrainerResult> can_play_trainer(
    const GameState& state,
    const CardDatabase& db,
    const CardInstance& trainer_card,
    PlayerID player_id
);

} // namespace trainers
} // namespace pokemon

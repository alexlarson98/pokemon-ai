/**
 * Pokemon TCG Engine - Trainer Registry Implementation
 *
 * Central registration point for all trainer card effects.
 */

#include "cards/trainer_registry.hpp"
#include <algorithm>

namespace pokemon {
namespace trainers {

// ============================================================================
// TRAINER INFO DATABASE
// ============================================================================

namespace {

// Static list of all known trainers for tracking implementation status
std::vector<TrainerInfo> g_trainer_info = {
    // Items - Implemented
    {"sv1-181", "Nest Ball", "item", "Search deck for Basic Pokemon to bench", true},
    {"sv1-255", "Nest Ball", "item", "Search deck for Basic Pokemon to bench", true},
    {"sv4pt5-84", "Nest Ball", "item", "Search deck for Basic Pokemon to bench", true},
    {"sv5-144", "Buddy-Buddy Poffin", "item", "Search deck for up to 2 Basic Pokemon (70 HP or less) to bench", true},
    {"sv6-223", "Buddy-Buddy Poffin", "item", "Search deck for up to 2 Basic Pokemon (70 HP or less) to bench", true},
    {"sv8pt5-101", "Buddy-Buddy Poffin", "item", "Search deck for up to 2 Basic Pokemon (70 HP or less) to bench", true},
    {"me1-167", "Buddy-Buddy Poffin", "item", "Search deck for up to 2 Basic Pokemon (70 HP or less) to bench", true},

    // Items - Not Yet Implemented
    {"sv1-196", "Ultra Ball", "item", "Discard 2, search any Pokemon to hand", false},
    {"sv4pt5-91", "Ultra Ball", "item", "Discard 2, search any Pokemon to hand", false},
    {"sv1-191", "Rare Candy", "item", "Evolve Basic to Stage 2 directly", false},
    {"sv4pt5-89", "Rare Candy", "item", "Evolve Basic to Stage 2 directly", false},
    {"sv1-194", "Switch", "item", "Switch Active with Benched", false},
    {"sv4-173", "Super Rod", "item", "Shuffle 3 Pokemon/Energy from discard to deck", false},
    {"sv4pt5-90", "Super Rod", "item", "Shuffle 3 Pokemon/Energy from discard to deck", false},
    {"sv1-171", "Energy Retrieval", "item", "Recover 2 basic Energy from discard", false},
    {"sv3-178", "Night Stretcher", "item", "Recover Pokemon or Energy from discard", false},
    {"sv1-188", "Potion", "item", "Heal 30 damage from 1 Pokemon", false},
    {"sv3-179", "Pal Pad", "item", "Shuffle 2 Supporters from discard to deck", false},

    // Supporters - Not Yet Implemented
    {"sv1-189", "Professor's Research", "supporter", "Discard hand, draw 7", false},
    {"sv3-181", "Professor's Research", "supporter", "Discard hand, draw 7", false},
    {"sv1-172", "Boss's Orders", "supporter", "Switch opponent's Active with Benched", false},
    {"sv4-172", "Boss's Orders", "supporter", "Switch opponent's Active with Benched", false},
    {"sv1-176", "Judge", "supporter", "Both shuffle hand, draw 4", false},

    // Stadiums - Not Yet Implemented
    {"sv1-169", "Artazon", "stadium", "Once per turn, search Basic non-Rule Box Pokemon", false},
};

bool g_registry_initialized = false;

} // anonymous namespace

// ============================================================================
// REGISTRATION
// ============================================================================

void register_all_trainers(LogicRegistry& registry) {
    if (g_registry_initialized) {
        return;  // Already registered
    }

    // Register all implemented trainers
    register_nest_ball(registry);
    register_buddy_buddy_poffin(registry);
    // register_ultra_ball(registry);
    // register_rare_candy(registry);
    // register_switch(registry);
    // ...

    g_registry_initialized = true;
}

std::vector<TrainerInfo> get_trainer_info() {
    return g_trainer_info;
}

bool is_trainer_implemented(const CardDefID& card_id) {
    for (const auto& info : g_trainer_info) {
        if (info.card_id == card_id) {
            return info.implemented;
        }
    }
    return false;
}

// ============================================================================
// VALIDATION
// ============================================================================

std::optional<TrainerResult> can_play_trainer(
    const GameState& state,
    const CardDatabase& db,
    const CardInstance& trainer_card,
    PlayerID player_id
) {
    // Get card definition
    const CardDef* def = db.get_card(trainer_card.card_id);
    if (!def) {
        return std::nullopt;
    }

    // Check if it's a trainer
    if (!def->is_trainer()) {
        return std::nullopt;
    }

    // Check if supporter already used this turn
    if (def->is_supporter()) {
        const auto& player = state.get_player(player_id);
        if (player.supporter_played_this_turn) {
            TrainerResult result;
            result.success = false;
            result.effect_description = "Already used a Supporter this turn";
            return result;
        }
    }

    // Check if stadium of same name already in play
    // Compare by card_id since CardInstance doesn't store name directly
    if (def->is_stadium() && state.stadium.has_value()) {
        if (state.stadium->card_id == trainer_card.card_id) {
            TrainerResult result;
            result.success = false;
            result.effect_description = "Same stadium already in play";
            return result;
        }
    }

    // Trainer can be played (further checks may be needed per-card)
    TrainerResult result;
    result.success = true;
    return result;
}

// ============================================================================
// STUB IMPLEMENTATIONS FOR UNIMPLEMENTED TRAINERS
// ============================================================================

// These will be implemented in separate files as we build them out

void register_ultra_ball(LogicRegistry& registry) {
    // TODO: Implement in ultra_ball.cpp
}

void register_rare_candy(LogicRegistry& registry) {
    // TODO: Implement in rare_candy.cpp
}

void register_switch(LogicRegistry& registry) {
    // TODO: Implement in switch.cpp
}

void register_potion(LogicRegistry& registry) {
    // TODO: Implement in potion.cpp
}

void register_super_rod(LogicRegistry& registry) {
    // TODO: Implement in super_rod.cpp
}

void register_energy_retrieval(LogicRegistry& registry) {
    // TODO: Implement in energy_retrieval.cpp
}

void register_professors_letter(LogicRegistry& registry) {
    // TODO: Implement in professors_letter.cpp
}

void register_night_stretcher(LogicRegistry& registry) {
    // TODO: Implement in night_stretcher.cpp
}

void register_max_potion(LogicRegistry& registry) {
    // TODO: Implement in max_potion.cpp
}

void register_full_heal(LogicRegistry& registry) {
    // TODO: Implement in full_heal.cpp
}

void register_pokegear(LogicRegistry& registry) {
    // TODO: Implement in pokegear.cpp
}

void register_pal_pad(LogicRegistry& registry) {
    // TODO: Implement in pal_pad.cpp
}

void register_escape_rope(LogicRegistry& registry) {
    // TODO: Implement in escape_rope.cpp
}

void register_professors_research(LogicRegistry& registry) {
    // TODO: Implement in professors_research.cpp
}

void register_boss_orders(LogicRegistry& registry) {
    // TODO: Implement in boss_orders.cpp
}

void register_judge(LogicRegistry& registry) {
    // TODO: Implement in judge.cpp
}

void register_marnie(LogicRegistry& registry) {
    // TODO: Implement in marnie.cpp
}

void register_training_court(LogicRegistry& registry) {
    // TODO: Implement in training_court.cpp
}

void register_artazon(LogicRegistry& registry) {
    // TODO: Implement in artazon.cpp
}

void register_exp_share(LogicRegistry& registry) {
    // TODO: Implement in exp_share.cpp
}

void register_choice_belt(LogicRegistry& registry) {
    // TODO: Implement in choice_belt.cpp
}

} // namespace trainers
} // namespace pokemon

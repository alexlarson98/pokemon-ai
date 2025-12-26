/**
 * Rare Candy - Trainer Item (TARGETED Pattern)
 *
 * Card text:
 * "Choose 1 of your Basic Pokemon in play. If you have a Stage 2 card in your
 *  hand that evolves from that Pokemon, put that card onto the Basic Pokemon
 *  to evolve it, skipping the Stage 1. You can't use this card during your
 *  first turn or on a Basic Pokemon that was put into play this turn."
 *
 * Card IDs: sv1-191, sv1-256, sv4pt5-89, me1-125, me1-175
 *
 * Pattern: TARGETED
 * - Targets are visible (Basic Pokemon in play, Stage 2 in hand)
 * - Generator mode: ACTION_GENERATION - provides complete actions with targets
 * - Handler receives targets via TrainerContext.action
 * - No resolution stack needed
 */

#include "cards/trainer_registry.hpp"
#include "cards/effect_builders.hpp"
#include "card_database.hpp"

namespace pokemon {

// External global card database pointer (defined in trainer_registry.cpp)
extern const CardDatabase* g_card_db;

namespace trainers {

namespace {

/**
 * Find all Stage 1 names that evolve from a given Basic Pokemon name.
 */
std::vector<std::string> find_stage1_names_for_basic(
    const CardDatabase& db,
    const std::string& basic_name
) {
    std::vector<std::string> stage1_names;

    for (const auto& card_id : db.get_all_card_ids()) {
        const CardDef* def = db.get_card(card_id);
        if (def && def->is_stage_1() && def->evolves_from == basic_name) {
            if (std::find(stage1_names.begin(), stage1_names.end(), def->name) == stage1_names.end()) {
                stage1_names.push_back(def->name);
            }
        }
    }

    return stage1_names;
}

/**
 * Check if a Stage 2 card can be Rare Candy'd onto a specific Basic.
 *
 * For Rare Candy, the Stage 2 must evolve from a Stage 1 that evolves from the Basic.
 * Example: Charizard (Stage 2) evolves from Charmeleon (Stage 1) which evolves from Charmander (Basic)
 */
bool stage2_can_evolve_from_basic(
    const CardDatabase& db,
    const CardDef& stage2_def,
    const std::string& basic_name
) {
    if (!stage2_def.is_stage_2()) return false;
    if (!stage2_def.evolves_from.has_value()) return false;

    const std::string& stage1_name = *stage2_def.evolves_from;
    auto stage1_names = find_stage1_names_for_basic(db, basic_name);

    return std::find(stage1_names.begin(), stage1_names.end(), stage1_name) != stage1_names.end();
}

/**
 * Valid (Basic Pokemon, Stage 2) pair for Rare Candy.
 */
struct RareCandyPair {
    CardID basic_id;            // Instance ID of Basic Pokemon in play
    CardID stage2_instance_id;  // Instance ID of Stage 2 in hand
    std::string stage2_card_id; // Card definition ID (for functional dedup)
};

/**
 * Collect all valid (Basic Pokemon, Stage 2) pairs.
 */
std::vector<RareCandyPair> get_valid_pairs(
    const GameState& state,
    const CardDatabase& db,
    PlayerID player_id
) {
    std::vector<RareCandyPair> pairs;

    if (state.turn_count == 1) return pairs;  // Cannot use on turn 1

    const auto& player = state.get_player(player_id);

    // Collect valid Basic Pokemon in play (must have been in play 1+ turns)
    std::vector<const CardInstance*> valid_basics;

    if (player.board.active_spot.has_value()) {
        const auto& active = *player.board.active_spot;
        if (active.turns_in_play > 0) {
            const CardDef* def = db.get_card(active.card_id);
            if (def && def->is_basic_pokemon()) {
                valid_basics.push_back(&active);
            }
        }
    }

    for (const auto& benched : player.board.bench) {
        if (benched.turns_in_play > 0) {
            const CardDef* def = db.get_card(benched.card_id);
            if (def && def->is_basic_pokemon()) {
                valid_basics.push_back(&benched);
            }
        }
    }

    // For each valid Basic, find matching Stage 2s in hand
    for (const CardInstance* basic : valid_basics) {
        const CardDef* basic_def = db.get_card(basic->card_id);
        if (!basic_def) continue;

        // Deduplicate Stage 2s by functional ID
        std::unordered_set<std::string> seen_stage2_fids;

        for (const auto& hand_card : player.hand.cards) {
            const CardDef* hand_def = db.get_card(hand_card.card_id);
            if (!hand_def) continue;

            if (stage2_can_evolve_from_basic(db, *hand_def, basic_def->name)) {
                std::string fid = hand_def->get_functional_id();
                if (seen_stage2_fids.count(fid) > 0) continue;
                seen_stage2_fids.insert(fid);

                pairs.push_back({basic->id, hand_card.id, hand_card.card_id});
            }
        }
    }

    return pairs;
}

/**
 * Execute Rare Candy effect using TrainerContext.
 */
TrainerResult execute_rare_candy(TrainerContext& ctx) {
    TrainerResult result;
    auto& state = ctx.state;
    const auto& action = ctx.action;
    const auto& db = ctx.db;
    PlayerID player_id = state.active_player_index;

    // Get target info from action
    if (!action.target_id.has_value()) {
        result.success = false;
        result.effect_description = "No target specified for Rare Candy";
        return result;
    }

    auto stage2_it = action.parameters.find("stage2_id");
    if (stage2_it == action.parameters.end()) {
        result.success = false;
        result.effect_description = "No Stage 2 specified for Rare Candy";
        return result;
    }

    const CardID& basic_id = *action.target_id;
    const CardID& stage2_instance_id = stage2_it->second;

    auto& player = state.get_player(player_id);

    // Find the Basic Pokemon
    CardInstance* basic_pokemon = player.find_pokemon(basic_id);
    if (!basic_pokemon) {
        result.success = false;
        result.effect_description = "Target Basic Pokemon not found";
        return result;
    }

    // Take the Stage 2 from hand
    auto stage2_opt = player.hand.take_card(stage2_instance_id);
    if (!stage2_opt.has_value()) {
        result.success = false;
        result.effect_description = "Stage 2 card not found in hand";
        return result;
    }

    CardInstance stage2_card = std::move(*stage2_opt);

    // Validate the evolution
    const CardDef* basic_def = db.get_card(basic_pokemon->card_id);
    const CardDef* stage2_def = db.get_card(stage2_card.card_id);

    if (!basic_def || !stage2_def || !stage2_can_evolve_from_basic(db, *stage2_def, basic_def->name)) {
        player.hand.add_card(std::move(stage2_card));
        result.success = false;
        result.effect_description = "Invalid evolution combination";
        return result;
    }

    // Perform the evolution
    CardInstance basic_copy = basic_pokemon->clone();
    basic_pokemon->previous_stages.push_back(std::move(basic_copy));
    basic_pokemon->evolution_chain.push_back(basic_pokemon->card_id);
    basic_pokemon->card_id = stage2_card.card_id;
    basic_pokemon->clear_all_status();
    basic_pokemon->evolved_this_turn = true;
    basic_pokemon->turns_in_play = 0;

    result.success = true;
    result.effect_description = "Evolved " + basic_def->name + " into " + stage2_def->name + " using Rare Candy";

    return result;
}

} // anonymous namespace

void register_rare_candy(LogicRegistry& registry) {
    // Unified handler using TrainerContext
    auto handler = [](TrainerContext& ctx) -> TrainerResult {
        return execute_rare_candy(ctx);
    };

    // Generator: ACTION_GENERATION mode - provides complete actions with targets
    auto generator = [](const GameState& state, const CardInstance& card) -> GeneratorResult {
        GeneratorResult result;

        if (state.turn_count == 1) {
            result.valid = false;
            result.reason = "Cannot use Rare Candy on turn 1";
            return result;
        }

        // Need card database for validation - use global for generator
        // (Handler uses ctx.db which is cleaner)
        if (!g_card_db) {
            result.valid = false;
            result.reason = "Card database not available";
            return result;
        }

        auto pairs = get_valid_pairs(state, *g_card_db, state.active_player_index);

        if (pairs.empty()) {
            result.valid = false;
            result.reason = "No valid Basic Pokemon with matching Stage 2 in hand";
            return result;
        }

        // TARGETED pattern: provide complete actions with targets
        result.valid = true;
        result.mode = GeneratorMode::ACTION_GENERATION;

        for (const auto& pair : pairs) {
            Action action = Action::play_item(state.active_player_index, card.id);
            action.target_id = pair.basic_id;
            action.parameters["stage2_id"] = pair.stage2_instance_id;
            result.actions.push_back(action);
        }

        return result;
    };

    // Register for all printings using unified handler
    const std::vector<std::string> card_ids = {
        "sv1-191", "sv1-256", "sv4pt5-89", "me1-125", "me1-175"
    };

    for (const auto& id : card_ids) {
        registry.register_trainer_handler(id, handler);
        registry.register_generator(id, "trainer", generator);
    }
}

} // namespace trainers
} // namespace pokemon

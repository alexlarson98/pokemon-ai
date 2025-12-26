/**
 * Rare Candy - Trainer Item
 *
 * Card text:
 * "Choose 1 of your Basic Pokemon in play. If you have a Stage 2 card in your
 *  hand that evolves from that Pokemon, put that card onto the Basic Pokemon
 *  to evolve it, skipping the Stage 1. You can't use this card during your
 *  first turn or on a Basic Pokemon that was put into play this turn."
 *
 * Card IDs: sv1-191, sv1-256, sv4pt5-89, me1-125, me1-175
 *
 * Key mechanics:
 * - Cannot be used on turn 1
 * - Cannot target Basic Pokemon with turns_in_play == 0 (played this turn)
 * - Stage 2 must evolve from a Stage 1 that evolves from the Basic
 *
 * Implementation approach:
 * - Generator returns list of valid (Basic, Stage 2) pairs
 * - Each pair becomes a separate PLAY_ITEM action with target_id=Basic and
 *   parameters["stage2_id"]=Stage2 instance ID
 * - Handler receives target info and performs evolution directly
 * - NO resolution stack needed
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
 * Returns empty vector if card database not loaded.
 */
std::vector<std::string> find_stage1_names_for_basic(const std::string& basic_name) {
    std::vector<std::string> stage1_names;

    if (!g_card_db) return stage1_names;

    // Scan all cards in database to find Stage 1s that evolve from this Basic
    for (const auto& card_id : g_card_db->get_all_card_ids()) {
        const CardDef* def = g_card_db->get_card(card_id);
        if (def && def->is_stage_1() && def->evolves_from == basic_name) {
            // Add unique Stage 1 names
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
bool stage2_can_evolve_from_basic(const CardDef& stage2_def, const std::string& basic_name) {
    if (!stage2_def.is_stage_2()) return false;
    if (!stage2_def.evolves_from.has_value()) return false;

    // The Stage 2's evolves_from is the Stage 1 name
    const std::string& stage1_name = *stage2_def.evolves_from;

    // Find Stage 1s that evolve from this Basic
    auto stage1_names = find_stage1_names_for_basic(basic_name);

    // Check if this Stage 2's Stage 1 is in the list
    return std::find(stage1_names.begin(), stage1_names.end(), stage1_name) != stage1_names.end();
}

/**
 * Collect all valid (Basic Pokemon ID, Stage 2 instance ID) pairs.
 * Used by both generator and handler.
 */
struct RareCandyPair {
    CardID basic_id;           // Instance ID of Basic Pokemon in play
    CardID stage2_instance_id; // Instance ID of Stage 2 in hand
    std::string stage2_card_id; // Card definition ID of Stage 2 (for functional dedup)
};

std::vector<RareCandyPair> get_valid_rare_candy_pairs(
    const GameState& state,
    PlayerID player_id
) {
    std::vector<RareCandyPair> pairs;

    if (!g_card_db) return pairs;
    if (state.turn_count == 1) return pairs;  // Cannot use on turn 1

    const auto& player = state.get_player(player_id);

    // Collect all valid Basic Pokemon in play
    std::vector<const CardInstance*> valid_basics;

    // Check active
    if (player.board.active_spot.has_value()) {
        const auto& active = *player.board.active_spot;
        if (active.turns_in_play > 0) {
            const CardDef* def = g_card_db->get_card(active.card_id);
            if (def && def->is_basic_pokemon()) {
                valid_basics.push_back(&active);
            }
        }
    }

    // Check bench
    for (const auto& benched : player.board.bench) {
        if (benched.turns_in_play > 0) {
            const CardDef* def = g_card_db->get_card(benched.card_id);
            if (def && def->is_basic_pokemon()) {
                valid_basics.push_back(&benched);
            }
        }
    }

    // For each valid Basic, find matching Stage 2s in hand
    for (const CardInstance* basic : valid_basics) {
        const CardDef* basic_def = g_card_db->get_card(basic->card_id);
        if (!basic_def) continue;

        // Track seen Stage 2 functional IDs to deduplicate
        std::unordered_set<std::string> seen_stage2_fids;

        for (const auto& hand_card : player.hand.cards) {
            const CardDef* hand_def = g_card_db->get_card(hand_card.card_id);
            if (!hand_def) continue;

            if (stage2_can_evolve_from_basic(*hand_def, basic_def->name)) {
                // Deduplicate by functional ID
                std::string fid = hand_def->get_functional_id();
                if (seen_stage2_fids.count(fid) > 0) continue;
                seen_stage2_fids.insert(fid);

                RareCandyPair pair;
                pair.basic_id = basic->id;
                pair.stage2_instance_id = hand_card.id;
                pair.stage2_card_id = hand_card.card_id;
                pairs.push_back(pair);
            }
        }
    }

    return pairs;
}

/**
 * Execute Rare Candy effect.
 *
 * The action should have:
 * - card_id = Rare Candy instance ID (for discarding)
 * - target_id = Basic Pokemon instance ID (evolution target)
 * - parameters["stage2_id"] = Stage 2 instance ID from hand
 */
TrainerResult execute_rare_candy(GameState& state, const CardInstance& card, const Action& action) {
    TrainerResult result;
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

    // Validate the Stage 2 can actually evolve from this Basic
    if (!g_card_db) {
        player.hand.add_card(std::move(stage2_card));
        result.success = false;
        result.effect_description = "Card database not available";
        return result;
    }

    const CardDef* basic_def = g_card_db->get_card(basic_pokemon->card_id);
    const CardDef* stage2_def = g_card_db->get_card(stage2_card.card_id);

    if (!basic_def || !stage2_def || !stage2_can_evolve_from_basic(*stage2_def, basic_def->name)) {
        player.hand.add_card(std::move(stage2_card));
        result.success = false;
        result.effect_description = "Invalid evolution combination";
        return result;
    }

    // Perform the evolution!
    // Save the Basic as a previous stage
    CardInstance basic_copy = basic_pokemon->clone();
    basic_pokemon->previous_stages.push_back(std::move(basic_copy));
    basic_pokemon->evolution_chain.push_back(basic_pokemon->card_id);

    // Update the Pokemon to the Stage 2
    basic_pokemon->card_id = stage2_card.card_id;

    // Evolution removes special conditions
    basic_pokemon->clear_all_status();

    // Mark as evolved this turn (prevents further evolution)
    basic_pokemon->evolved_this_turn = true;

    // Reset turns_in_play for evolution
    basic_pokemon->turns_in_play = 0;

    result.success = true;
    result.effect_description = "Evolved " + basic_def->name + " into " + stage2_def->name + " using Rare Candy";

    return result;
}

} // anonymous namespace

void register_rare_candy(LogicRegistry& registry) {
    // Handler receives the action with target info already set
    auto handler = [](GameState& state, const CardInstance& card, const Action& action) -> TrainerResult {
        return execute_rare_candy(state, card, action);
    };

    // Generator returns valid pairs as action variants
    auto generator = [](const GameState& state, const CardInstance& card) -> GeneratorResult {
        GeneratorResult result;

        if (state.turn_count == 1) {
            result.valid = false;
            result.reason = "Cannot use Rare Candy on turn 1";
            return result;
        }

        auto pairs = get_valid_rare_candy_pairs(state, state.active_player_index);

        if (pairs.empty()) {
            result.valid = false;
            result.reason = "No valid Basic Pokemon with matching Stage 2 in hand";
            return result;
        }

        // Return valid with action variants for each pair
        result.valid = true;

        for (const auto& pair : pairs) {
            Action action = Action::play_item(state.active_player_index, card.id);
            action.target_id = pair.basic_id;
            action.parameters["stage2_id"] = pair.stage2_instance_id;
            result.actions.push_back(action);
        }

        return result;
    };

    // Register for all printings
    registry.register_trainer_with_action("sv1-191", handler);
    registry.register_generator("sv1-191", "trainer", generator);
    registry.register_trainer_with_action("sv1-256", handler);
    registry.register_generator("sv1-256", "trainer", generator);
    registry.register_trainer_with_action("sv4pt5-89", handler);
    registry.register_generator("sv4pt5-89", "trainer", generator);
    registry.register_trainer_with_action("me1-125", handler);
    registry.register_generator("me1-125", "trainer", generator);
    registry.register_trainer_with_action("me1-175", handler);
    registry.register_generator("me1-175", "trainer", generator);
}

} // namespace trainers
} // namespace pokemon

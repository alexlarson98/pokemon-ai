/**
 * Pokemon TCG Engine - Effect Builders Implementation
 */

#include "cards/effect_builders.hpp"
#include <algorithm>
#include <sstream>

namespace pokemon {
namespace effects {

// ============================================================================
// FILTER BUILDER
// ============================================================================

FilterBuilder& FilterBuilder::supertype(const std::string& type) {
    criteria_["supertype"] = type;
    return *this;
}

FilterBuilder& FilterBuilder::subtype(const std::string& type) {
    criteria_["subtype"] = type;
    return *this;
}

FilterBuilder& FilterBuilder::pokemon_type(EnergyType type) {
    criteria_["pokemon_type"] = to_string(type);
    return *this;
}

FilterBuilder& FilterBuilder::max_hp(int hp) {
    criteria_["max_hp"] = std::to_string(hp);
    return *this;
}

FilterBuilder& FilterBuilder::name(const std::string& name) {
    criteria_["name"] = name;
    return *this;
}

FilterBuilder& FilterBuilder::evolves_from(const std::string& pokemon_name) {
    criteria_["evolves_from"] = pokemon_name;
    return *this;
}

FilterBuilder& FilterBuilder::is_basic_energy(bool value) {
    criteria_["is_basic_energy"] = value ? "true" : "false";
    return *this;
}

std::unordered_map<std::string, std::string> FilterBuilder::build() const {
    return criteria_;
}

// ============================================================================
// CARD MATCHING
// ============================================================================

bool card_matches_filter(
    const CardDef& card_def,
    const std::unordered_map<std::string, std::string>& filter
) {
    for (const auto& [key, value] : filter) {
        if (key == "supertype") {
            if (value == "Pokemon" && !card_def.is_pokemon()) return false;
            if (value == "Trainer" && !card_def.is_trainer()) return false;
            if (value == "Energy" && !card_def.is_energy()) return false;
        }
        else if (key == "subtype") {
            if (value == "Basic" && !card_def.is_basic_pokemon()) return false;
            if (value == "Stage 1" && !card_def.is_stage_1()) return false;
            if (value == "Stage 2" && !card_def.is_stage_2()) return false;
            if (value == "Item" && !card_def.is_item()) return false;
            if (value == "Supporter" && !card_def.is_supporter()) return false;
            if (value == "Stadium" && !card_def.is_stadium()) return false;
            if (value == "Tool" && !card_def.is_tool()) return false;
            if (value == "ex" && !card_def.is_ex()) return false;
        }
        else if (key == "pokemon_type") {
            // Check if the card's types include the specified type
            bool found = false;
            for (EnergyType t : card_def.types) {
                if (to_string(t) == value) {
                    found = true;
                    break;
                }
            }
            if (!found) return false;
        }
        else if (key == "max_hp") {
            int max_hp = std::stoi(value);
            if (card_def.hp > max_hp) return false;
        }
        else if (key == "name") {
            if (card_def.name != value) return false;
        }
        else if (key == "evolves_from") {
            if (!card_def.evolves_from.has_value() ||
                *card_def.evolves_from != value) {
                return false;
            }
        }
        else if (key == "is_basic_energy") {
            bool should_be_basic = (value == "true");
            if (card_def.is_basic_energy != should_be_basic) return false;
        }
    }
    return true;
}

// ============================================================================
// VALIDATION HELPERS
// ============================================================================

bool can_discard_from_hand(
    const GameState& state,
    PlayerID player_id,
    int count,
    const std::unordered_map<std::string, std::string>& filter
) {
    const auto& player = state.get_player(player_id);

    if (filter.empty()) {
        // Any card can be discarded
        return static_cast<int>(player.hand.cards.size()) >= count;
    }

    // Count cards matching filter (would need CardDatabase for full check)
    // For now, just check hand size
    return static_cast<int>(player.hand.cards.size()) >= count;
}

bool has_bench_space(const GameState& state, PlayerID player_id) {
    const auto& player = state.get_player(player_id);
    return player.board.can_add_to_bench();
}

bool deck_has_matching_cards(
    const GameState& state,
    const CardDatabase& db,
    PlayerID player_id,
    const std::unordered_map<std::string, std::string>& filter
) {
    const auto& player = state.get_player(player_id);

    for (const auto& card : player.deck.cards) {
        const CardDef* def = db.get_card(card.card_id);
        if (def && card_matches_filter(*def, filter)) {
            return true;
        }
    }
    return false;
}

int count_matching_cards(
    const GameState& state,
    const CardDatabase& db,
    PlayerID player_id,
    ZoneType zone,
    const std::unordered_map<std::string, std::string>& filter
) {
    const auto& player = state.get_player(player_id);
    int count = 0;

    const std::vector<CardInstance>* zone_cards = nullptr;

    switch (zone) {
        case ZoneType::HAND:
            zone_cards = &player.hand.cards;
            break;
        case ZoneType::DECK:
            zone_cards = &player.deck.cards;
            break;
        case ZoneType::DISCARD:
            zone_cards = &player.discard.cards;
            break;
        default:
            return 0;
    }

    for (const auto& card : *zone_cards) {
        const CardDef* def = db.get_card(card.card_id);
        if (def && card_matches_filter(*def, filter)) {
            count++;
        }
    }

    return count;
}

// ============================================================================
// CORE EFFECT IMPLEMENTATIONS
// ============================================================================

EffectResult search_deck(
    GameState& state,
    const CardInstance& source_card,
    PlayerID player_id,
    const std::unordered_map<std::string, std::string>& filter,
    int count,
    int min_count,
    ZoneType destination,
    bool shuffle_after,
    StepCompletionCallback on_complete
) {
    EffectResult result;

    // Create search step
    SearchDeckStep step;
    step.source_card_id = source_card.id;
    step.source_card_name = source_card.card_id;  // Using card_id since CardInstance has no name
    step.player_id = player_id;
    step.purpose = SelectionPurpose::SEARCH_TARGET;
    step.count = count;
    step.min_count = min_count;
    step.destination = destination;
    step.filter_criteria = filter;
    step.shuffle_after = shuffle_after;

    // Set completion callback if provided
    if (on_complete) {
        step.on_complete = CompletionCallback(std::move(on_complete));
    }

    // Push onto resolution stack
    state.push_step(step);

    result.success = true;
    result.requires_resolution = true;
    result.message = "Search deck for " + std::to_string(count) + " card(s)";

    return result;
}

EffectResult search_deck_to_bench(
    GameState& state,
    const CardInstance& source_card,
    PlayerID player_id,
    const std::unordered_map<std::string, std::string>& filter,
    int count,
    int min_count,
    StepCompletionCallback on_complete
) {
    // For bench placement, destination is BENCH
    // If no custom callback provided, use default behavior (engine handles it)
    return search_deck(state, source_card, player_id, filter, count, min_count,
                       ZoneType::BENCH, true, std::move(on_complete));
}

EffectResult discard_then(
    GameState& state,
    const CardInstance& source_card,
    PlayerID player_id,
    int discard_count,
    const std::unordered_map<std::string, std::string>& discard_filter,
    std::function<void(GameState&)> then_effect
) {
    EffectResult result;

    // Check if player can discard required cards
    if (!can_discard_from_hand(state, player_id, discard_count, discard_filter)) {
        result.success = false;
        result.message = "Not enough cards to discard";
        return result;
    }

    // Create discard step
    SelectFromZoneStep step;
    step.source_card_id = source_card.id;
    step.source_card_name = source_card.card_id;  // Using card_id since CardInstance has no name
    step.player_id = player_id;
    step.purpose = SelectionPurpose::DISCARD_COST;
    step.zone = ZoneType::HAND;
    step.count = discard_count;
    step.min_count = discard_count;
    step.exact_count = true;
    step.filter_criteria = discard_filter;

    // Exclude the source card from being discarded
    step.exclude_card_ids.push_back(source_card.id);

    // Set completion callback to discard selected cards, then execute the then_effect
    if (then_effect) {
        step.on_complete = CompletionCallback([then_effect = std::move(then_effect)](
            GameState& state,
            const std::vector<CardID>& selected,
            PlayerID player
        ) {
            // Move selected cards from hand to discard pile
            auto& player_state = state.get_player(player);
            for (const auto& card_id : selected) {
                auto card_opt = player_state.hand.take_card(card_id);
                if (card_opt.has_value()) {
                    player_state.discard.add_card(std::move(*card_opt));
                }
            }

            // Then execute the follow-up effect
            then_effect(state);
        });
    } else {
        // Even without a then_effect, we still need to discard the selected cards
        step.on_complete = CompletionCallback([](
            GameState& state,
            const std::vector<CardID>& selected,
            PlayerID player
        ) {
            auto& player_state = state.get_player(player);
            for (const auto& card_id : selected) {
                auto card_opt = player_state.hand.take_card(card_id);
                if (card_opt.has_value()) {
                    player_state.discard.add_card(std::move(*card_opt));
                }
            }
        });
    }

    state.push_step(step);

    result.success = true;
    result.requires_resolution = true;
    result.message = "Discard " + std::to_string(discard_count) + " card(s)";

    return result;
}

EffectResult draw_cards(
    GameState& state,
    PlayerID player_id,
    int count
) {
    EffectResult result;

    auto& player = state.get_player(player_id);
    int actual_draw = std::min(count, static_cast<int>(player.deck.cards.size()));

    for (int i = 0; i < actual_draw; i++) {
        if (!player.deck.cards.empty()) {
            player.hand.cards.push_back(std::move(player.deck.cards.back()));
            player.deck.cards.pop_back();
        }
    }

    result.success = true;
    result.requires_resolution = false;
    result.message = "Drew " + std::to_string(actual_draw) + " card(s)";

    return result;
}

EffectResult discard_hand_draw(
    GameState& state,
    PlayerID player_id,
    int draw_count
) {
    EffectResult result;

    auto& player = state.get_player(player_id);

    // Move all cards from hand to discard
    for (auto& card : player.hand.cards) {
        player.discard.cards.push_back(std::move(card));
    }
    player.hand.cards.clear();

    // Draw new cards
    return draw_cards(state, player_id, draw_count);
}

EffectResult shuffle_discard_to_deck(
    GameState& state,
    const CardInstance& source_card,
    PlayerID player_id,
    const std::unordered_map<std::string, std::string>& filter,
    int count,
    int min_count
) {
    EffectResult result;

    // Create selection step for discard pile
    SelectFromZoneStep step;
    step.source_card_id = source_card.id;
    step.source_card_name = source_card.card_id;  // Using card_id since CardInstance has no name
    step.player_id = player_id;
    step.purpose = SelectionPurpose::RECOVER_TO_DECK;
    step.zone = ZoneType::DISCARD;
    step.count = count;
    step.min_count = min_count;
    step.filter_criteria = filter;

    state.push_step(step);

    result.success = true;
    result.requires_resolution = true;
    result.message = "Select up to " + std::to_string(count) + " card(s) from discard";

    return result;
}

EffectResult recover_from_discard(
    GameState& state,
    const CardInstance& source_card,
    PlayerID player_id,
    const std::unordered_map<std::string, std::string>& filter,
    int count,
    int min_count
) {
    EffectResult result;

    // Create selection step for discard pile
    SelectFromZoneStep step;
    step.source_card_id = source_card.id;
    step.source_card_name = source_card.card_id;  // Using card_id since CardInstance has no name
    step.player_id = player_id;
    step.purpose = SelectionPurpose::RECOVER_TO_HAND;
    step.zone = ZoneType::DISCARD;
    step.count = count;
    step.min_count = min_count;
    step.filter_criteria = filter;

    state.push_step(step);

    result.success = true;
    result.requires_resolution = true;
    result.message = "Select up to " + std::to_string(count) + " card(s) from discard";

    return result;
}

EffectResult switch_active(
    GameState& state,
    const CardInstance& source_card,
    PlayerID player_id,
    bool opponent_also
) {
    EffectResult result;

    auto& player = state.get_player(player_id);

    // Check if player has benched Pokemon to switch to
    if (player.board.bench.empty()) {
        result.success = false;
        result.message = "No benched Pokemon to switch to";
        return result;
    }

    // Create selection step for bench
    SelectFromZoneStep step;
    step.source_card_id = source_card.id;
    step.source_card_name = source_card.card_id;  // Using card_id since CardInstance has no name
    step.player_id = player_id;
    step.purpose = SelectionPurpose::SWITCH_TARGET;
    step.zone = ZoneType::BENCH;
    step.count = 1;
    step.min_count = 1;
    step.exact_count = true;

    state.push_step(step);

    // If opponent also switches, add their step first (LIFO order)
    if (opponent_also) {
        PlayerID opp_id = 1 - player_id;
        auto& opponent = state.get_player(opp_id);

        if (!opponent.board.bench.empty()) {
            SelectFromZoneStep opp_step;
            opp_step.source_card_id = source_card.id;
            opp_step.source_card_name = source_card.card_id;  // Using card_id since CardInstance has no name
            opp_step.player_id = opp_id;
            opp_step.purpose = SelectionPurpose::SWITCH_TARGET;
            opp_step.zone = ZoneType::BENCH;
            opp_step.count = 1;
            opp_step.min_count = 1;
            opp_step.exact_count = true;

            // Push opponent step first so player resolves last
            state.push_step(opp_step);
        }
    }

    result.success = true;
    result.requires_resolution = true;
    result.message = "Select a Pokemon to switch to";

    return result;
}

EffectResult heal_damage(
    GameState& state,
    const CardInstance& source_card,
    PlayerID player_id,
    const CardID& target_id,
    int amount
) {
    EffectResult result;

    CardInstance* target = state.find_card(target_id);
    if (!target) {
        result.success = false;
        result.message = "Target not found";
        return result;
    }

    // Heal damage (amount is in HP, counters are HP/10)
    int counters_to_remove = amount / 10;
    target->damage_counters = std::max(0, target->damage_counters - counters_to_remove);

    result.success = true;
    result.requires_resolution = false;
    result.message = "Healed " + std::to_string(amount) + " damage";

    return result;
}

EffectResult add_damage_counters(
    GameState& state,
    const CardID& target_id,
    int counters
) {
    EffectResult result;

    CardInstance* target = state.find_card(target_id);
    if (!target) {
        result.success = false;
        result.message = "Target not found";
        return result;
    }

    target->damage_counters += counters;

    result.success = true;
    result.requires_resolution = false;
    result.message = "Added " + std::to_string(counters) + " damage counters";

    return result;
}

// ============================================================================
// SELECTION HELPERS
// ============================================================================

EffectResult select_bench_pokemon(
    GameState& state,
    const CardInstance& source_card,
    PlayerID player_id,
    SelectionPurpose purpose,
    const std::unordered_map<std::string, std::string>& filter
) {
    EffectResult result;

    SelectFromZoneStep step;
    step.source_card_id = source_card.id;
    step.source_card_name = source_card.card_id;  // Using card_id since CardInstance has no name
    step.player_id = player_id;
    step.purpose = purpose;
    step.zone = ZoneType::BENCH;
    step.count = 1;
    step.min_count = 1;
    step.filter_criteria = filter;

    state.push_step(step);

    result.success = true;
    result.requires_resolution = true;
    result.message = "Select a benched Pokemon";

    return result;
}

EffectResult select_board_pokemon(
    GameState& state,
    const CardInstance& source_card,
    PlayerID player_id,
    SelectionPurpose purpose,
    const std::unordered_map<std::string, std::string>& filter
) {
    EffectResult result;

    SelectFromZoneStep step;
    step.source_card_id = source_card.id;
    step.source_card_name = source_card.card_id;  // Using card_id since CardInstance has no name
    step.player_id = player_id;
    step.purpose = purpose;
    step.zone = ZoneType::BOARD;  // Active + Bench
    step.count = 1;
    step.min_count = 1;
    step.filter_criteria = filter;

    state.push_step(step);

    result.success = true;
    result.requires_resolution = true;
    result.message = "Select a Pokemon";

    return result;
}

} // namespace effects
} // namespace pokemon

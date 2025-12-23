/**
 * Pokemon TCG Engine - Engine Implementation
 *
 * Core game engine logic: get_legal_actions() and step().
 */

#include "engine.hpp"
#include <algorithm>
#include <chrono>

namespace pokemon {

PokemonEngine::PokemonEngine() {
    // Seed RNG with current time
    auto seed = std::chrono::high_resolution_clock::now().time_since_epoch().count();
    rng_.seed(static_cast<std::mt19937::result_type>(seed));
}

// ============================================================================
// CORE API
// ============================================================================

std::vector<Action> PokemonEngine::get_legal_actions(const GameState& state) const {
    // Check for game over
    if (state.is_game_over()) {
        return {};
    }

    // Priority 1: Resolution stack (must complete before normal actions)
    if (!state.resolution_stack.empty()) {
        return get_resolution_stack_actions(state);
    }

    // Priority 2: Legacy interrupt (backward compatibility)
    if (state.pending_interrupt.has_value()) {
        return get_interrupt_actions(state);
    }

    // Priority 3: Phase-specific actions
    switch (state.current_phase) {
        case GamePhase::SETUP:
            return get_setup_actions(state);

        case GamePhase::MULLIGAN:
            return get_mulligan_actions(state);

        case GamePhase::MAIN:
            return get_main_phase_actions(state);

        case GamePhase::DRAW:
        case GamePhase::ATTACK:
        case GamePhase::CLEANUP:
            // These phases are auto-resolved
            return {};

        case GamePhase::END:
            return {};

        case GamePhase::SUDDEN_DEATH:
            // Handle sudden death like main phase
            return get_main_phase_actions(state);

        default:
            return {};
    }
}

GameState PokemonEngine::step(const GameState& state, const Action& action) const {
    // Clone state
    GameState new_state = state.clone();

    // Apply action
    step_inplace(new_state, action);

    return new_state;
}

void PokemonEngine::step_inplace(GameState& state, const Action& action) const {
    // Apply the action
    apply_action(state, action);

    // Check win conditions
    check_win_conditions(state);

    // Auto-advance through non-interactive phases
    if (state.current_phase == GamePhase::CLEANUP && !state.has_pending_resolution()) {
        advance_phase(state);
    }
}

// ============================================================================
// SETUP PHASE ACTIONS
// ============================================================================

std::vector<Action> PokemonEngine::get_setup_actions(const GameState& state) const {
    std::vector<Action> actions;
    const auto& player = state.get_active_player();

    // Check if player needs to place active
    if (!player.has_active_pokemon()) {
        // Find basic Pokemon in hand
        for (const auto& card : player.hand.cards) {
            const CardDef* def = card_db_.get_card(card.card_id);
            if (def && def->is_basic_pokemon()) {
                actions.push_back(Action::place_active(player.player_id, card.id));
            }
        }

        // If no basics, must mulligan
        if (actions.empty()) {
            Action mulligan(ActionType::REVEAL_HAND_MULLIGAN, player.player_id);
            actions.push_back(mulligan);
        }
    } else {
        // Active placed, can place bench or pass
        // Find remaining basics in hand
        for (const auto& card : player.hand.cards) {
            const CardDef* def = card_db_.get_card(card.card_id);
            if (def && def->is_basic_pokemon() && player.board.can_add_to_bench()) {
                actions.push_back(Action::place_bench(player.player_id, card.id));
            }
        }

        // Can always pass (done placing bench)
        actions.push_back(Action::end_turn(player.player_id));
    }

    return actions;
}

// ============================================================================
// MULLIGAN PHASE ACTIONS
// ============================================================================

std::vector<Action> PokemonEngine::get_mulligan_actions(const GameState& state) const {
    std::vector<Action> actions;
    const auto& player = state.get_active_player();

    // Opponent decides whether to draw for each mulligan
    Action draw(ActionType::MULLIGAN_DRAW, player.player_id);
    actions.push_back(draw);

    return actions;
}

// ============================================================================
// MAIN PHASE ACTIONS
// ============================================================================

std::vector<Action> PokemonEngine::get_main_phase_actions(const GameState& state) const {
    std::vector<Action> actions;
    const auto& player = state.get_active_player();

    // Check for forced actions first

    // Must promote if no active
    if (!player.has_active_pokemon() && player.board.get_bench_count() > 0) {
        for (const auto& pokemon : player.board.bench) {
            actions.push_back(Action::promote_active(player.player_id, pokemon.id));
        }
        return actions;
    }

    // Collect all possible actions

    // 1. End turn (always available)
    actions.push_back(Action::end_turn(player.player_id));

    // 2. Attach energy (once per turn)
    auto energy_actions = get_energy_attach_actions(state);
    actions.insert(actions.end(), energy_actions.begin(), energy_actions.end());

    // 3. Play basic Pokemon to bench
    auto basic_actions = get_play_basic_actions(state);
    actions.insert(actions.end(), basic_actions.begin(), basic_actions.end());

    // 4. Evolve Pokemon
    auto evolve_actions = get_evolution_actions(state);
    actions.insert(actions.end(), evolve_actions.begin(), evolve_actions.end());

    // 5. Play trainers
    auto trainer_actions = get_trainer_actions(state);
    actions.insert(actions.end(), trainer_actions.begin(), trainer_actions.end());

    // 6. Use abilities
    auto ability_actions = get_ability_actions(state);
    actions.insert(actions.end(), ability_actions.begin(), ability_actions.end());

    // 7. Retreat
    auto retreat_actions = get_retreat_actions(state);
    actions.insert(actions.end(), retreat_actions.begin(), retreat_actions.end());

    // 8. Attack (ends turn)
    auto attack_actions = get_attack_actions(state);
    actions.insert(actions.end(), attack_actions.begin(), attack_actions.end());

    return actions;
}

// ============================================================================
// ENERGY ATTACH ACTIONS
// ============================================================================

std::vector<Action> PokemonEngine::get_energy_attach_actions(const GameState& state) const {
    std::vector<Action> actions;
    const auto& player = state.get_active_player();

    // Check once-per-turn restriction
    if (player.energy_attached_this_turn) {
        return actions;
    }

    // Find energy cards in hand
    for (const auto& card : player.hand.cards) {
        const CardDef* def = card_db_.get_card(card.card_id);
        if (def && def->is_energy()) {
            // Can attach to any Pokemon in play
            auto pokemon_list = player.board.get_all_pokemon();
            for (const auto* pokemon : pokemon_list) {
                actions.push_back(Action::attach_energy(
                    player.player_id, card.id, pokemon->id));
            }
        }
    }

    return actions;
}

// ============================================================================
// PLAY BASIC ACTIONS
// ============================================================================

std::vector<Action> PokemonEngine::get_play_basic_actions(const GameState& state) const {
    std::vector<Action> actions;
    const auto& player = state.get_active_player();

    // Check bench space
    if (!player.board.can_add_to_bench()) {
        return actions;
    }

    // Find basic Pokemon in hand (deduplicate by name)
    std::unordered_set<std::string> seen_names;

    for (const auto& card : player.hand.cards) {
        const CardDef* def = card_db_.get_card(card.card_id);
        if (def && def->is_basic_pokemon()) {
            // Deduplicate by name
            if (seen_names.find(def->name) == seen_names.end()) {
                seen_names.insert(def->name);
                actions.push_back(Action::play_basic(player.player_id, card.id));
            }
        }
    }

    return actions;
}

// ============================================================================
// EVOLUTION ACTIONS
// ============================================================================

std::vector<Action> PokemonEngine::get_evolution_actions(const GameState& state) const {
    std::vector<Action> actions;
    const auto& player = state.get_active_player();

    // Cannot evolve on turn 1
    if (state.turn_count == 1) {
        return actions;
    }

    // Find evolution cards in hand
    std::unordered_set<std::string> seen_evolutions;

    for (const auto& card : player.hand.cards) {
        const CardDef* def = card_db_.get_card(card.card_id);
        if (!def || !def->evolves_from.has_value()) {
            continue;  // Not an evolution card
        }

        // Find valid targets in play
        auto pokemon_list = player.board.get_all_pokemon();
        for (const auto* pokemon : pokemon_list) {
            const CardDef* target_def = card_db_.get_card(pokemon->card_id);
            if (!target_def) continue;

            // Check evolution rules
            if (can_evolve(state, *pokemon, *def)) {
                // Deduplicate by (evolution_name, target_id)
                std::string key = def->name + ":" + pokemon->id;
                if (seen_evolutions.find(key) == seen_evolutions.end()) {
                    seen_evolutions.insert(key);
                    actions.push_back(Action::evolve(
                        player.player_id, card.id, pokemon->id));
                }
            }
        }
    }

    return actions;
}

// ============================================================================
// TRAINER ACTIONS
// ============================================================================

std::vector<Action> PokemonEngine::get_trainer_actions(const GameState& state) const {
    std::vector<Action> actions;
    const auto& player = state.get_active_player();

    // Track seen cards for deduplication
    std::unordered_set<std::string> seen_items;
    std::unordered_set<std::string> seen_supporters;
    std::unordered_set<std::string> seen_stadiums;

    for (const auto& card : player.hand.cards) {
        const CardDef* def = card_db_.get_card(card.card_id);
        if (!def || !def->is_trainer()) {
            continue;
        }

        // Item cards
        if (def->is_item()) {
            if (seen_items.find(def->name) == seen_items.end()) {
                seen_items.insert(def->name);
                actions.push_back(Action::play_item(player.player_id, card.id));
            }
        }
        // Supporter cards
        else if (def->is_supporter()) {
            // Check once-per-turn and turn 1 restrictions
            if (player.supporter_played_this_turn) {
                continue;
            }
            if (state.turn_count == 1 && state.active_player_index == state.starting_player_id) {
                continue;  // Cannot play supporter on turn 1 going first
            }

            if (seen_supporters.find(def->name) == seen_supporters.end()) {
                seen_supporters.insert(def->name);
                actions.push_back(Action::play_supporter(player.player_id, card.id));
            }
        }
        // Stadium cards
        else if (def->is_stadium()) {
            // Check once-per-turn restriction
            if (player.stadium_played_this_turn) {
                continue;
            }

            // Cannot play same stadium as current
            if (state.stadium.has_value()) {
                const CardDef* current_stadium = card_db_.get_card(state.stadium->card_id);
                if (current_stadium && current_stadium->name == def->name) {
                    continue;
                }
            }

            if (seen_stadiums.find(def->name) == seen_stadiums.end()) {
                seen_stadiums.insert(def->name);
                actions.push_back(Action::play_stadium(player.player_id, card.id));
            }
        }
        // Tool cards
        else if (def->is_tool()) {
            // Find Pokemon without tools
            auto pokemon_list = player.board.get_all_pokemon();
            for (const auto* pokemon : pokemon_list) {
                if (pokemon->attached_tools.empty()) {
                    actions.push_back(Action::attach_tool(
                        player.player_id, card.id, pokemon->id));
                }
            }
        }
    }

    return actions;
}

// ============================================================================
// ABILITY ACTIONS
// ============================================================================

std::vector<Action> PokemonEngine::get_ability_actions(const GameState& state) const {
    std::vector<Action> actions;
    const auto& player = state.get_active_player();

    // Check all Pokemon in play
    auto pokemon_list = player.board.get_all_pokemon();

    for (const auto* pokemon : pokemon_list) {
        const CardDef* def = card_db_.get_card(pokemon->card_id);
        if (!def) continue;

        for (const auto& ability : def->abilities) {
            // Check if ability is activatable
            if (!ability.is_activatable) {
                continue;
            }

            // Check once-per-turn restriction
            if (pokemon->abilities_used_this_turn.count(ability.name) > 0) {
                continue;
            }

            actions.push_back(Action::use_ability(
                player.player_id, pokemon->id, ability.name));
        }
    }

    return actions;
}

// ============================================================================
// RETREAT ACTIONS
// ============================================================================

std::vector<Action> PokemonEngine::get_retreat_actions(const GameState& state) const {
    std::vector<Action> actions;
    const auto& player = state.get_active_player();

    // Check once-per-turn restriction
    if (player.retreated_this_turn) {
        return actions;
    }

    // Must have active and bench
    if (!player.has_active_pokemon() || player.board.get_bench_count() == 0) {
        return actions;
    }

    const auto& active = *player.board.active_spot;

    // Check status conditions
    if (active.is_asleep_or_paralyzed()) {
        return actions;
    }

    // Check retreat cost
    int retreat_cost = calculate_retreat_cost(state, active);
    if (active.total_attached_energy() < retreat_cost) {
        return actions;
    }

    // Generate actions for each bench Pokemon
    for (const auto& bench_pokemon : player.board.bench) {
        actions.push_back(Action::retreat(
            player.player_id, active.id, bench_pokemon.id));
    }

    return actions;
}

// ============================================================================
// ATTACK ACTIONS
// ============================================================================

std::vector<Action> PokemonEngine::get_attack_actions(const GameState& state) const {
    std::vector<Action> actions;
    const auto& player = state.get_active_player();

    // Must have active Pokemon
    if (!player.has_active_pokemon()) {
        return actions;
    }

    const auto& active = *player.board.active_spot;

    // Check status conditions
    if (active.is_asleep_or_paralyzed()) {
        return actions;
    }

    // Check attack effects
    for (const auto& effect : active.attack_effects) {
        if (effect == "cannot_attack_next_turn") {
            return actions;
        }
    }

    // Cannot attack on turn 1 going first
    if (state.turn_count == 1 && state.active_player_index == state.starting_player_id) {
        return actions;
    }

    const CardDef* def = card_db_.get_card(active.card_id);
    if (!def) {
        return actions;
    }

    // Generate attack actions
    for (const auto& attack : def->attacks) {
        if (has_energy_for_attack(active, attack.cost)) {
            actions.push_back(Action::attack(
                player.player_id, active.id, attack.name));
        }
    }

    return actions;
}

// ============================================================================
// RESOLUTION STACK ACTIONS
// ============================================================================

std::vector<Action> PokemonEngine::get_resolution_stack_actions(const GameState& state) const {
    std::vector<Action> actions;

    if (state.resolution_stack.empty()) {
        return actions;
    }

    const auto& step = state.resolution_stack.back();

    // Generate actions based on step type
    std::visit([&](const auto& s) {
        using T = std::decay_t<decltype(s)>;

        if constexpr (std::is_same_v<T, SelectFromZoneStep>) {
            // Generate select actions for each valid card
            const auto& player = state.get_player(s.player_id);

            const Zone* zone = nullptr;
            switch (s.zone) {
                case ZoneType::HAND: zone = &player.hand; break;
                case ZoneType::DECK: zone = &player.deck; break;
                case ZoneType::DISCARD: zone = &player.discard; break;
                default: break;
            }

            if (zone) {
                for (const auto& card : zone->cards) {
                    // Skip excluded cards
                    bool excluded = std::find(s.exclude_card_ids.begin(),
                        s.exclude_card_ids.end(), card.id) != s.exclude_card_ids.end();
                    if (excluded) continue;

                    // Skip already selected cards
                    bool selected = std::find(s.selected_card_ids.begin(),
                        s.selected_card_ids.end(), card.id) != s.selected_card_ids.end();
                    if (selected) continue;

                    // TODO: Apply filter_criteria

                    actions.push_back(Action::select_card(s.player_id, card.id));
                }
            }

            // Can confirm if minimum reached
            if (static_cast<int>(s.selected_card_ids.size()) >= s.min_count) {
                actions.push_back(Action::confirm_selection(s.player_id));
            }
        }
        else if constexpr (std::is_same_v<T, SearchDeckStep>) {
            const auto& player = state.get_player(s.player_id);

            for (const auto& card : player.deck.cards) {
                // Skip already selected
                bool selected = std::find(s.selected_card_ids.begin(),
                    s.selected_card_ids.end(), card.id) != s.selected_card_ids.end();
                if (selected) continue;

                // TODO: Apply filter_criteria

                if (static_cast<int>(s.selected_card_ids.size()) < s.count) {
                    actions.push_back(Action::select_card(s.player_id, card.id));
                }
            }

            // Can confirm if minimum reached
            if (static_cast<int>(s.selected_card_ids.size()) >= s.min_count) {
                actions.push_back(Action::confirm_selection(s.player_id));
            }
        }
        else if constexpr (std::is_same_v<T, AttachToTargetStep>) {
            // Select from valid targets
            for (const auto& target_id : s.valid_target_ids) {
                actions.push_back(Action::select_card(s.player_id, target_id));
            }
        }
        else if constexpr (std::is_same_v<T, EvolveTargetStep>) {
            // Single action - evolve
            Action a(ActionType::EVOLVE, s.player_id);
            a.card_id = s.evolution_card_id;
            a.target_id = s.base_pokemon_id;
            actions.push_back(a);
        }
    }, step);

    return actions;
}

// ============================================================================
// INTERRUPT ACTIONS (Legacy)
// ============================================================================

std::vector<Action> PokemonEngine::get_interrupt_actions(const GameState& state) const {
    std::vector<Action> actions;

    if (!state.pending_interrupt.has_value()) {
        return actions;
    }

    const auto& interrupt = *state.pending_interrupt;

    switch (interrupt.phase) {
        case SearchAndAttachState::Phase::SELECT_COUNT:
            // Generate count selection actions
            for (int i = 0; i <= interrupt.max_select; ++i) {
                Action a(ActionType::SEARCH_SELECT_COUNT, interrupt.player_id);
                a.choice_index = i;
                actions.push_back(a);
            }
            break;

        case SearchAndAttachState::Phase::ATTACH_ENERGY:
            // Generate attach target actions
            {
                const auto& player = state.get_player(interrupt.player_id);
                auto pokemon_list = player.board.get_all_pokemon();

                for (const auto* pokemon : pokemon_list) {
                    Action a(ActionType::INTERRUPT_ATTACH_ENERGY, interrupt.player_id);
                    a.target_id = pokemon->id;
                    actions.push_back(a);
                }
            }
            break;

        default:
            break;
    }

    return actions;
}

// ============================================================================
// ACTION APPLICATION
// ============================================================================

void PokemonEngine::apply_action(GameState& state, const Action& action) const {
    switch (action.action_type) {
        case ActionType::PLACE_ACTIVE:
            apply_place_active(state, action);
            break;
        case ActionType::PLACE_BENCH:
            apply_place_bench(state, action);
            break;
        case ActionType::PLAY_BASIC:
            apply_play_basic(state, action);
            break;
        case ActionType::EVOLVE:
            apply_evolve(state, action);
            break;
        case ActionType::ATTACH_ENERGY:
            apply_attach_energy(state, action);
            break;
        case ActionType::PLAY_ITEM:
            apply_play_item(state, action);
            break;
        case ActionType::PLAY_SUPPORTER:
            apply_play_supporter(state, action);
            break;
        case ActionType::PLAY_STADIUM:
            apply_play_stadium(state, action);
            break;
        case ActionType::ATTACH_TOOL:
            apply_attach_tool(state, action);
            break;
        case ActionType::USE_ABILITY:
            apply_use_ability(state, action);
            break;
        case ActionType::RETREAT:
            apply_retreat(state, action);
            break;
        case ActionType::ATTACK:
            apply_attack(state, action);
            break;
        case ActionType::END_TURN:
            apply_end_turn(state, action);
            break;
        case ActionType::TAKE_PRIZE:
            apply_take_prize(state, action);
            break;
        case ActionType::PROMOTE_ACTIVE:
            apply_promote_active(state, action);
            break;
        case ActionType::SELECT_CARD:
            apply_select_card(state, action);
            break;
        case ActionType::CONFIRM_SELECTION:
            apply_confirm_selection(state, action);
            break;
        default:
            // Unknown action type
            break;
    }
}

void PokemonEngine::apply_place_active(GameState& state, const Action& action) const {
    auto& player = state.get_player(action.player_id);

    auto card_opt = player.hand.take_card(*action.card_id);
    if (card_opt.has_value()) {
        const CardDef* def = card_db_.get_card(card_opt->card_id);
        if (def) {
            card_opt->current_hp = def->hp;
        }
        player.board.active_spot = std::move(*card_opt);
    }
}

void PokemonEngine::apply_place_bench(GameState& state, const Action& action) const {
    auto& player = state.get_player(action.player_id);

    auto card_opt = player.hand.take_card(*action.card_id);
    if (card_opt.has_value()) {
        const CardDef* def = card_db_.get_card(card_opt->card_id);
        if (def) {
            card_opt->current_hp = def->hp;
        }
        player.board.add_to_bench(std::move(*card_opt));
    }
}

void PokemonEngine::apply_play_basic(GameState& state, const Action& action) const {
    apply_place_bench(state, action);
}

void PokemonEngine::apply_evolve(GameState& state, const Action& action) const {
    auto& player = state.get_player(action.player_id);

    // Find the evolution card in hand
    auto evo_opt = player.hand.take_card(*action.card_id);
    if (!evo_opt.has_value()) return;

    // Find the target Pokemon
    auto* target = player.find_pokemon(*action.target_id);
    if (!target) return;

    const CardDef* evo_def = card_db_.get_card(evo_opt->card_id);
    if (!evo_def) return;

    // Save old card for evolution chain
    CardInstance old_pokemon = std::move(*target);

    // Set up evolved Pokemon
    evo_opt->current_hp = evo_def->hp;
    evo_opt->damage_counters = old_pokemon.damage_counters;
    evo_opt->attached_energy = std::move(old_pokemon.attached_energy);
    evo_opt->attached_tools = std::move(old_pokemon.attached_tools);
    evo_opt->turns_in_play = old_pokemon.turns_in_play;
    evo_opt->evolved_this_turn = true;
    evo_opt->evolution_chain = old_pokemon.evolution_chain;
    evo_opt->evolution_chain.push_back(old_pokemon.card_id);
    evo_opt->previous_stages.push_back(std::move(old_pokemon));

    // Clear status on evolution
    evo_opt->clear_all_status();
    evo_opt->attack_effects.clear();

    *target = std::move(*evo_opt);
}

void PokemonEngine::apply_attach_energy(GameState& state, const Action& action) const {
    auto& player = state.get_player(action.player_id);

    auto energy_opt = player.hand.take_card(*action.card_id);
    if (!energy_opt.has_value()) return;

    auto* target = player.find_pokemon(*action.target_id);
    if (!target) return;

    target->attached_energy.push_back(std::move(*energy_opt));
    player.energy_attached_this_turn = true;
}

void PokemonEngine::apply_play_item(GameState& state, const Action& action) const {
    auto& player = state.get_player(action.player_id);

    auto card_opt = player.hand.take_card(*action.card_id);
    if (!card_opt.has_value()) return;

    // TODO: Execute item effect via logic registry

    // Move to discard
    player.discard.add_card(std::move(*card_opt));
}

void PokemonEngine::apply_play_supporter(GameState& state, const Action& action) const {
    auto& player = state.get_player(action.player_id);

    auto card_opt = player.hand.take_card(*action.card_id);
    if (!card_opt.has_value()) return;

    player.supporter_played_this_turn = true;

    // TODO: Execute supporter effect via logic registry

    // Move to discard
    player.discard.add_card(std::move(*card_opt));
}

void PokemonEngine::apply_play_stadium(GameState& state, const Action& action) const {
    auto& player = state.get_player(action.player_id);

    auto card_opt = player.hand.take_card(*action.card_id);
    if (!card_opt.has_value()) return;

    // Discard old stadium
    if (state.stadium.has_value()) {
        PlayerID stadium_owner = state.stadium->owner_id;
        state.get_player(stadium_owner).discard.add_card(std::move(*state.stadium));
    }

    state.stadium = std::move(*card_opt);
    player.stadium_played_this_turn = true;
}

void PokemonEngine::apply_attach_tool(GameState& state, const Action& action) const {
    auto& player = state.get_player(action.player_id);

    auto tool_opt = player.hand.take_card(*action.card_id);
    if (!tool_opt.has_value()) return;

    auto* target = player.find_pokemon(*action.target_id);
    if (!target) return;

    target->attached_tools.push_back(std::move(*tool_opt));
}

void PokemonEngine::apply_use_ability(GameState& state, const Action& action) const {
    auto& player = state.get_player(action.player_id);

    auto* pokemon = player.find_pokemon(*action.card_id);
    if (!pokemon) return;

    // Mark ability as used
    pokemon->abilities_used_this_turn.insert(*action.ability_name);

    // TODO: Execute ability effect via logic registry
}

void PokemonEngine::apply_retreat(GameState& state, const Action& action) const {
    auto& player = state.get_player(action.player_id);

    if (!player.board.active_spot.has_value()) return;

    // Discard energy for retreat cost
    int retreat_cost = calculate_retreat_cost(state, *player.board.active_spot);

    // Remove energy cards (simple implementation - just remove from front)
    for (int i = 0; i < retreat_cost && !player.board.active_spot->attached_energy.empty(); ++i) {
        auto energy = std::move(player.board.active_spot->attached_energy.back());
        player.board.active_spot->attached_energy.pop_back();
        player.discard.add_card(std::move(energy));
    }

    // Switch with bench Pokemon
    player.board.switch_active(*action.target_id);

    // Clear status on new active (from bench)
    if (player.board.active_spot.has_value()) {
        // Status is NOT cleared when switching TO active
        // But it IS cleared when going TO bench
    }

    player.retreated_this_turn = true;
}

void PokemonEngine::apply_attack(GameState& state, const Action& action) const {
    auto& player = state.get_player(action.player_id);
    auto& opponent = state.get_opponent();

    if (!player.board.active_spot.has_value() || !opponent.board.active_spot.has_value()) {
        return;
    }

    auto& attacker = *player.board.active_spot;
    auto& defender = *opponent.board.active_spot;

    const CardDef* attacker_def = card_db_.get_card(attacker.card_id);
    if (!attacker_def) return;

    // Find the attack
    const AttackDef* attack = nullptr;
    for (const auto& a : attacker_def->attacks) {
        if (a.name == *action.attack_name) {
            attack = &a;
            break;
        }
    }

    if (!attack) return;

    // Calculate and apply damage
    int base_damage = attack->base_damage;

    // TODO: Execute attack effect via logic registry (may modify damage)

    if (base_damage > 0) {
        int final_damage = calculate_damage(state, attacker, defender, base_damage);
        apply_damage(state, defender, final_damage);
    }

    // Check for knockout
    const CardDef* defender_def = card_db_.get_card(defender.card_id);
    if (defender_def && defender.is_knocked_out(defender_def->hp)) {
        // KO handling
        // Move to discard
        opponent.discard.add_card(std::move(*opponent.board.active_spot));
        opponent.board.active_spot.reset();

        // Player takes prizes
        int prizes_to_take = defender_def->get_prize_value();
        // TODO: Push prize taking onto resolution stack
    }

    // Advance to cleanup
    state.current_phase = GamePhase::CLEANUP;
}

void PokemonEngine::apply_end_turn(GameState& state, const Action& action) const {
    end_turn(state);
}

void PokemonEngine::apply_take_prize(GameState& state, const Action& action) const {
    auto& player = state.get_player(action.player_id);

    if (player.prizes.is_empty()) return;

    int index = action.choice_index.value_or(0);
    if (index < 0 || index >= player.prizes.count()) {
        index = 0;
    }

    // Take prize card to hand
    if (index < static_cast<int>(player.prizes.cards.size())) {
        auto prize = std::move(player.prizes.cards[index]);
        player.prizes.cards.erase(player.prizes.cards.begin() + index);
        player.hand.add_card(std::move(prize));
        player.prizes_taken++;
    }
}

void PokemonEngine::apply_promote_active(GameState& state, const Action& action) const {
    auto& player = state.get_player(action.player_id);

    player.board.promote_to_active(*action.card_id);
}

void PokemonEngine::apply_select_card(GameState& state, const Action& action) const {
    if (state.resolution_stack.empty()) return;

    auto& step = state.resolution_stack.back();

    std::visit([&](auto& s) {
        using T = std::decay_t<decltype(s)>;

        if constexpr (std::is_same_v<T, SelectFromZoneStep> || std::is_same_v<T, SearchDeckStep>) {
            s.selected_card_ids.push_back(*action.card_id);
        }
        else if constexpr (std::is_same_v<T, AttachToTargetStep>) {
            s.selected_target_id = *action.card_id;
            s.is_complete = true;
        }
    }, step);
}

void PokemonEngine::apply_confirm_selection(GameState& state, const Action& action) const {
    if (state.resolution_stack.empty()) return;

    auto& step = state.resolution_stack.back();

    std::visit([&](auto& s) {
        s.is_complete = true;
    }, step);

    // Pop completed step
    if (is_step_complete(step)) {
        // TODO: Execute step completion callback
        state.pop_step();
    }
}

// ============================================================================
// PHASE TRANSITIONS
// ============================================================================

void PokemonEngine::advance_phase(GameState& state) const {
    switch (state.current_phase) {
        case GamePhase::SETUP:
            if (state.active_player_index == 1) {
                // Both players done with setup
                state.current_phase = GamePhase::DRAW;
                state.active_player_index = state.starting_player_id;
                start_turn(state);
            } else {
                // Switch to other player for setup
                state.switch_active_player();
            }
            break;

        case GamePhase::DRAW:
            state.current_phase = GamePhase::MAIN;
            break;

        case GamePhase::MAIN:
            // Should not auto-advance from MAIN
            break;

        case GamePhase::ATTACK:
            state.current_phase = GamePhase::CLEANUP;
            break;

        case GamePhase::CLEANUP:
            end_turn(state);
            break;

        default:
            break;
    }
}

void PokemonEngine::start_turn(GameState& state) const {
    auto& player = state.get_active_player();

    // Reset turn flags
    player.reset_turn_flags();

    // Draw a card (except turn 1)
    if (!player.deck.is_empty()) {
        auto card = player.deck.draw_top();
        if (card.has_value()) {
            player.hand.add_card(std::move(*card));
        }
    }

    // Advance to main phase
    state.current_phase = GamePhase::MAIN;
}

void PokemonEngine::end_turn(GameState& state) const {
    auto& player = state.get_active_player();

    // Increment turns in play for Pokemon
    player.increment_turns_in_play();

    // Clear attack effects that expire
    if (player.board.active_spot.has_value()) {
        player.board.active_spot->attack_effects.clear();
    }

    // Switch active player
    state.switch_active_player();
    state.turn_count++;

    // Start new turn
    start_turn(state);
}

// ============================================================================
// WIN CONDITIONS
// ============================================================================

void PokemonEngine::check_win_conditions(GameState& state) const {
    if (state.is_game_over()) return;

    // Check each player
    for (int player_id = 0; player_id < 2; ++player_id) {
        const auto& player = state.get_player(player_id);
        int opponent_id = 1 - player_id;

        // Win condition 1: Opponent has no Pokemon in play
        if (!state.get_player(opponent_id).has_any_pokemon_in_play() &&
            state.current_phase != GamePhase::SETUP) {
            state.result = player_id == 0 ? GameResult::PLAYER_0_WIN : GameResult::PLAYER_1_WIN;
            state.winner_id = player_id;
            return;
        }

        // Win condition 2: Took all prizes
        if (player.prizes.is_empty() && player.prizes_taken > 0) {
            state.result = player_id == 0 ? GameResult::PLAYER_0_WIN : GameResult::PLAYER_1_WIN;
            state.winner_id = player_id;
            return;
        }

        // Win condition 3: Opponent can't draw (deck out)
        if (state.get_player(opponent_id).deck.is_empty() &&
            state.current_phase == GamePhase::DRAW) {
            state.result = player_id == 0 ? GameResult::PLAYER_0_WIN : GameResult::PLAYER_1_WIN;
            state.winner_id = player_id;
            return;
        }
    }
}

// ============================================================================
// DAMAGE CALCULATION
// ============================================================================

int PokemonEngine::calculate_damage(const GameState& state,
                                    const CardInstance& attacker,
                                    const CardInstance& defender,
                                    int base_damage) const {
    int damage = base_damage;

    const CardDef* attacker_def = card_db_.get_card(attacker.card_id);
    const CardDef* defender_def = card_db_.get_card(defender.card_id);

    if (!attacker_def || !defender_def) {
        return damage;
    }

    // Apply weakness (x2)
    if (defender_def->weakness.has_value()) {
        for (const auto& type : attacker_def->types) {
            if (type == *defender_def->weakness) {
                damage *= 2;
                break;
            }
        }
    }

    // Apply resistance (-30)
    if (defender_def->resistance.has_value()) {
        for (const auto& type : attacker_def->types) {
            if (type == *defender_def->resistance) {
                damage -= 30;
                break;
            }
        }
    }

    // TODO: Apply modifier effects from active_effects

    return std::max(0, damage);
}

void PokemonEngine::apply_damage(GameState& state, CardInstance& defender, int damage) const {
    int counters = damage / 10;
    defender.damage_counters += counters;
}

void PokemonEngine::check_knockout(GameState& state, PlayerID player_id, const CardID& pokemon_id) const {
    auto& player = state.get_player(player_id);
    auto* pokemon = player.find_pokemon(pokemon_id);

    if (!pokemon) return;

    const CardDef* def = card_db_.get_card(pokemon->card_id);
    if (!def) return;

    if (pokemon->is_knocked_out(def->hp)) {
        // Move to discard
        // This needs to handle active vs bench appropriately
        // TODO: Implement full KO handling
    }
}

// ============================================================================
// UTILITY
// ============================================================================

bool PokemonEngine::has_energy_for_attack(const CardInstance& pokemon,
                                          const std::vector<EnergyType>& cost) const {
    // Simple check: total energy >= cost length
    // TODO: Implement proper energy matching with Colorless wildcards
    return pokemon.total_attached_energy() >= static_cast<int>(cost.size());
}

int PokemonEngine::calculate_retreat_cost(const GameState& state,
                                          const CardInstance& pokemon) const {
    const CardDef* def = card_db_.get_card(pokemon.card_id);
    if (!def) return 0;

    int cost = def->retreat_cost;

    // TODO: Apply modifiers from tools, abilities, stadium

    return std::max(0, cost);
}

bool PokemonEngine::can_evolve(const GameState& state,
                              const CardInstance& base,
                              const CardDef& evolution) const {
    // Must have evolves_from
    if (!evolution.evolves_from.has_value()) {
        return false;
    }

    // Get base Pokemon definition
    const CardDef* base_def = card_db_.get_card(base.card_id);
    if (!base_def) return false;

    // Name must match
    if (base_def->name != *evolution.evolves_from) {
        return false;
    }

    // Cannot evolve if just played (evolution sickness)
    if (base.turns_in_play < 1) {
        return false;
    }

    // Cannot evolve twice in one turn
    if (base.evolved_this_turn) {
        return false;
    }

    return true;
}

} // namespace pokemon

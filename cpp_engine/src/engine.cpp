/**
 * Pokemon TCG Engine - Engine Implementation
 *
 * Core game engine logic: get_legal_actions() and step().
 */

#include "engine.hpp"
#include "resolution_step.hpp"
#include <algorithm>
#include <chrono>
#include <unordered_set>

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
// ENERGY ATTACH ACTIONS (Atomic - optimal for MCTS)
// ============================================================================

std::vector<Action> PokemonEngine::get_energy_attach_actions(const GameState& state) const {
    std::vector<Action> actions;
    const auto& player = state.get_active_player();

    // Check once-per-turn restriction
    if (player.energy_attached_this_turn) {
        return actions;
    }

    // Check if player has any Pokemon in play
    if (!player.has_any_pokemon_in_play()) {
        return actions;
    }

    // Get all Pokemon targets (active + bench)
    auto pokemon_list = player.board.get_all_pokemon();
    if (pokemon_list.empty()) {
        return actions;
    }

    // Deduplicate energy by functional ID
    // We generate E × P atomic actions (energy × pokemon targets)
    std::unordered_set<std::string> seen_energy_fids;

    for (const auto& card : player.hand.cards) {
        const CardDef* def = card_db_.get_card(card.card_id);
        if (!def || !def->is_energy()) {
            continue;
        }

        // Deduplicate by functional ID
        std::string fid = def->get_functional_id();
        if (seen_energy_fids.count(fid) > 0) {
            continue;
        }
        seen_energy_fids.insert(fid);

        // Generate one action per target Pokemon
        for (const auto* target : pokemon_list) {
            Action attach_action(ActionType::ATTACH_ENERGY, player.player_id);
            attach_action.card_id = card.id;      // Energy card instance ID
            attach_action.target_id = target->id; // Pokemon instance ID
            actions.push_back(attach_action);
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

    // Find basic Pokemon in hand (deduplicate by functional ID, NOT name)
    // Example: Charmander 80HP with ability vs Charmander 70HP without ability
    std::unordered_set<std::string> seen_functional_ids;

    for (const auto& card : player.hand.cards) {
        const CardDef* def = card_db_.get_card(card.card_id);
        if (def && def->is_basic_pokemon()) {
            // Deduplicate by functional ID
            std::string fid = def->get_functional_id();
            if (seen_functional_ids.find(fid) == seen_functional_ids.end()) {
                seen_functional_ids.insert(fid);
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
    // Deduplicate by (functional_id, target_id) to handle same-name evolutions with different stats
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
                // Deduplicate by (functional_id, target_id)
                std::string key = def->get_functional_id() + ":" + pokemon->id;
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

    // Check global permission: Item Lock
    // This is set by passives like Klefki's Mischievous Lock or abilities like Vileplume's Allergy Flower
    bool items_locked = logic_registry_.check_global_block(state, "global_play_item");

    // Track seen cards for deduplication by functional ID
    // Trainers with same name from different sets may have different effects
    std::unordered_set<std::string> seen_items;
    std::unordered_set<std::string> seen_supporters;
    std::unordered_set<std::string> seen_stadiums;

    for (const auto& card : player.hand.cards) {
        const CardDef* def = card_db_.get_card(card.card_id);
        if (!def || !def->is_trainer()) {
            continue;
        }

        std::string fid = def->get_functional_id();

        // Item cards
        if (def->is_item()) {
            // Check Item Lock
            if (items_locked) {
                continue;  // Cannot play items when locked
            }

            if (seen_items.find(fid) == seen_items.end()) {
                seen_items.insert(fid);
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

            if (seen_supporters.find(fid) == seen_supporters.end()) {
                seen_supporters.insert(fid);
                actions.push_back(Action::play_supporter(player.player_id, card.id));
            }
        }
        // Stadium cards
        else if (def->is_stadium()) {
            // Check once-per-turn restriction
            if (player.stadium_played_this_turn) {
                continue;
            }

            // Cannot play same stadium as current (by name, not functional ID)
            if (state.stadium.has_value()) {
                const CardDef* current_stadium = card_db_.get_card(state.stadium->card_id);
                if (current_stadium && current_stadium->name == def->name) {
                    continue;
                }
            }

            if (seen_stadiums.find(fid) == seen_stadiums.end()) {
                seen_stadiums.insert(fid);
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

            // Check if ability is blocked by a passive ability lock (e.g., Klefki)
            // This matches Python's is_ability_blocked_by_passive()
            if (logic_registry_.is_ability_blocked_by_passive(state, *pokemon, ability.name)) {
                continue;  // Ability is blocked
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
                // Deduplicate by functional ID (NOT name - cards with same name can differ)
                // Example: Charmander 80HP with ability vs Charmander 70HP without ability
                std::unordered_set<std::string> seen_functional_ids;

                for (const auto& card : zone->cards) {
                    // Skip excluded cards
                    bool excluded = std::find(s.exclude_card_ids.begin(),
                        s.exclude_card_ids.end(), card.id) != s.exclude_card_ids.end();
                    if (excluded) continue;

                    // Skip already selected cards
                    bool selected = std::find(s.selected_card_ids.begin(),
                        s.selected_card_ids.end(), card.id) != s.selected_card_ids.end();
                    if (selected) continue;

                    // Apply filter_criteria
                    if (!s.filter_criteria.empty()) {
                        if (!card_matches_filter(card, s.filter_criteria, state, player)) {
                            continue;
                        }
                    }

                    // Deduplicate by functional ID
                    const CardDef* def = card_db_.get_card(card.card_id);
                    if (def) {
                        std::string fid = def->get_functional_id();
                        if (seen_functional_ids.count(fid) > 0) continue;
                        seen_functional_ids.insert(fid);
                    }

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

            // Deduplicate by functional ID (NOT name - cards with same name can differ)
            // Example: Charmander 80HP with ability vs Charmander 70HP without ability
            std::unordered_set<std::string> seen_functional_ids;

            for (const auto& card : player.deck.cards) {
                // Skip already selected
                bool selected = std::find(s.selected_card_ids.begin(),
                    s.selected_card_ids.end(), card.id) != s.selected_card_ids.end();
                if (selected) continue;

                // Apply filter_criteria
                if (!s.filter_criteria.empty()) {
                    if (!card_matches_filter(card, s.filter_criteria, state, player)) {
                        continue;
                    }
                }

                // Deduplicate by functional ID
                const CardDef* def = card_db_.get_card(card.card_id);
                if (def) {
                    std::string fid = def->get_functional_id();
                    if (seen_functional_ids.count(fid) > 0) continue;
                    seen_functional_ids.insert(fid);
                }

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
    auto& player = state.get_player(action.player_id);

    auto card_opt = player.hand.take_card(*action.card_id);
    if (!card_opt.has_value()) return;

    const CardDef* def = card_db_.get_card(card_opt->card_id);
    if (def) {
        card_opt->current_hp = def->hp;
    }

    // Add to bench
    player.board.add_to_bench(std::move(*card_opt));

    // Trigger on_play hooks for the newly placed Pokemon
    // This is for abilities like Flamigo's Insta-Flock
    if (def) {
        // Get the pokemon we just placed (it's at the end of the bench)
        const auto& placed_pokemon = player.board.bench.back();

        for (const auto& ability : def->abilities) {
            if (ability.category == "hook" && ability.trigger == "on_play") {
                // Check if ability is blocked
                if (!logic_registry_.is_ability_blocked_by_passive(state, placed_pokemon, ability.name)) {
                    // Trigger the hook
                    logic_registry_.trigger_hooks(state, "on_play");
                }
            }
        }
    }
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

    // Trigger on_evolve hooks for the evolved Pokemon
    // This is for abilities like Charizard ex's Infernal Reign
    for (const auto& ability : evo_def->abilities) {
        if (ability.category == "hook" && ability.trigger == "on_evolve") {
            // Check if ability is blocked
            if (!logic_registry_.is_ability_blocked_by_passive(state, *target, ability.name)) {
                // Trigger the hook
                logic_registry_.trigger_hooks(state, "on_evolve");
            }
        }
    }
}

void PokemonEngine::apply_attach_energy(GameState& state, const Action& action) const {
    auto& player = state.get_player(action.player_id);

    // Stack-based approach: Push resolution steps to select energy and target
    auto it = action.parameters.find("use_stack");
    if (it != action.parameters.end() && it->second == "true") {
        // Push SelectFromZoneStep to pick energy from hand
        SelectFromZoneStep select_energy;
        select_energy.source_card_id = "";  // No source card, it's a game action
        select_energy.source_card_name = "Attach Energy";
        select_energy.player_id = action.player_id;
        select_energy.purpose = SelectionPurpose::ENERGY_TO_ATTACH;
        select_energy.zone = ZoneType::HAND;
        select_energy.count = 1;
        select_energy.min_count = 1;
        select_energy.exact_count = true;
        select_energy.filter_criteria["supertype"] = "Energy";
        select_energy.on_complete_callback = "attach_energy_select_target";

        state.push_step(select_energy);
        return;
    }

    // Direct attachment (when card_id and target_id are specified)
    if (!action.card_id.has_value() || !action.target_id.has_value()) {
        return;
    }

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

    // Execute item effect via logic registry
    if (logic_registry_.has_trainer(card_opt->card_id)) {
        TrainerResult result = logic_registry_.invoke_trainer(
            card_opt->card_id, state, *card_opt);

        // Push any resolution steps
        for (auto& step : result.push_steps) {
            state.push_step(step);
        }
    }

    // Move to discard
    player.discard.add_card(std::move(*card_opt));
}

void PokemonEngine::apply_play_supporter(GameState& state, const Action& action) const {
    auto& player = state.get_player(action.player_id);

    auto card_opt = player.hand.take_card(*action.card_id);
    if (!card_opt.has_value()) return;

    player.supporter_played_this_turn = true;

    // Execute supporter effect via logic registry
    if (logic_registry_.has_trainer(card_opt->card_id)) {
        TrainerResult result = logic_registry_.invoke_trainer(
            card_opt->card_id, state, *card_opt);

        // Push any resolution steps
        for (auto& step : result.push_steps) {
            state.push_step(step);
        }
    }

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

    // Execute ability effect via logic registry
    if (logic_registry_.has_ability(pokemon->card_id, *action.ability_name)) {
        AbilityResult result = logic_registry_.invoke_ability(
            pokemon->card_id, *action.ability_name, state, *pokemon);

        // Push any resolution steps
        for (auto& step : result.push_steps) {
            state.push_step(step);
        }
    }
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

    // Calculate base damage
    int base_damage = attack->base_damage;

    // Execute attack effect via logic registry (may modify damage or add effects)
    AttackResult attack_result;
    if (logic_registry_.has_attack(attacker.card_id, attack->name)) {
        attack_result = logic_registry_.invoke_attack(
            attacker.card_id, attack->name, state, attacker, &defender);

        // If the logic returned damage, use that instead
        if (attack_result.damage_dealt > 0) {
            base_damage = attack_result.damage_dealt;
        }
    }

    // Apply damage
    if (base_damage > 0) {
        int final_damage = calculate_damage(state, attacker, defender, base_damage);
        apply_damage(state, defender, final_damage);
    }

    // Apply any additional effects from attack result
    for (const auto& [target_id, status] : attack_result.add_status) {
        auto* target = player.find_pokemon(target_id);
        if (!target) {
            target = opponent.find_pokemon(target_id);
        }
        if (target) {
            target->add_status(status);
        }
    }

    // Check for knockout
    const CardDef* defender_def = card_db_.get_card(defender.card_id);
    if (defender_def && defender.is_knocked_out(defender_def->hp)) {
        // KO handling
        // Move to discard (along with attached cards)
        for (auto& energy : defender.attached_energy) {
            opponent.discard.add_card(std::move(energy));
        }
        for (auto& tool : defender.attached_tools) {
            opponent.discard.add_card(std::move(tool));
        }
        opponent.discard.add_card(std::move(*opponent.board.active_spot));
        opponent.board.active_spot.reset();

        // Player takes prizes - push onto resolution stack
        int prizes_to_take = defender_def->get_prize_value();
        for (int i = 0; i < prizes_to_take && !player.prizes.is_empty(); ++i) {
            // For now, take first available prize (simplified)
            if (!player.prizes.cards.empty()) {
                auto prize = std::move(player.prizes.cards.back());
                player.prizes.cards.pop_back();
                player.hand.add_card(std::move(prize));
                player.prizes_taken++;
            }
        }
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
    bool should_auto_complete = false;

    std::visit([&](auto& s) {
        using T = std::decay_t<decltype(s)>;

        if constexpr (std::is_same_v<T, SelectFromZoneStep>) {
            s.selected_card_ids.push_back(*action.card_id);
            // Auto-complete when exact count reached (MCTS optimization - no meaningless confirm step)
            if (s.exact_count && static_cast<int>(s.selected_card_ids.size()) == s.count) {
                s.is_complete = true;
                should_auto_complete = true;
            }
        }
        else if constexpr (std::is_same_v<T, SearchDeckStep>) {
            s.selected_card_ids.push_back(*action.card_id);
            // Auto-complete when max count reached (MCTS optimization - no meaningless confirm step)
            if (static_cast<int>(s.selected_card_ids.size()) == s.count) {
                s.is_complete = true;
                should_auto_complete = true;
            }
        }
        else if constexpr (std::is_same_v<T, AttachToTargetStep>) {
            s.selected_target_id = *action.card_id;
            s.is_complete = true;
            should_auto_complete = true;
        }
    }, step);

    // If auto-completed, process the step completion immediately
    if (should_auto_complete) {
        process_step_completion(state);
    }
}

void PokemonEngine::process_step_completion(GameState& state) const {
    if (state.resolution_stack.empty()) return;

    auto step = state.resolution_stack.back();  // Copy for callback processing

    std::visit([&](const auto& s) {
        using T = std::decay_t<decltype(s)>;

        if constexpr (std::is_same_v<T, SelectFromZoneStep>) {
            // Handle energy attachment workflow
            if (s.on_complete_callback.has_value() &&
                *s.on_complete_callback == "attach_energy_select_target") {
                // Pop the selection step
                state.pop_step();

                // Get selected energy and push target selection
                if (!s.selected_card_ids.empty()) {
                    auto& player = state.get_player(s.player_id);

                    // Collect valid Pokemon targets
                    std::vector<CardID> target_ids;
                    auto pokemon_list = player.board.get_all_pokemon();
                    for (const auto* pokemon : pokemon_list) {
                        target_ids.push_back(pokemon->id);
                    }

                    // Push AttachToTargetStep
                    AttachToTargetStep attach_step;
                    attach_step.source_card_id = s.selected_card_ids[0];
                    attach_step.source_card_name = "Attach Energy";
                    attach_step.player_id = s.player_id;
                    attach_step.purpose = SelectionPurpose::ATTACH_TARGET;
                    attach_step.card_to_attach_id = s.selected_card_ids[0];
                    attach_step.valid_target_ids = std::move(target_ids);
                    attach_step.on_complete_callback = "attach_energy_complete";

                    state.push_step(attach_step);
                }
                return;  // Early return, don't pop again
            }
            // Default: just pop the step
            state.pop_step();
        }
        else if constexpr (std::is_same_v<T, AttachToTargetStep>) {
            if (s.on_complete_callback.has_value() &&
                *s.on_complete_callback == "attach_energy_complete") {
                // Pop the step
                state.pop_step();

                // Perform the actual energy attachment
                if (s.selected_target_id.has_value()) {
                    auto& player = state.get_player(s.player_id);

                    auto energy_opt = player.hand.take_card(s.card_to_attach_id);
                    if (energy_opt.has_value()) {
                        auto* target = player.find_pokemon(*s.selected_target_id);
                        if (target) {
                            target->attached_energy.push_back(std::move(*energy_opt));
                            player.energy_attached_this_turn = true;
                        }
                    }
                }
                return;  // Early return, don't pop again
            }
            // Default: just pop the step
            state.pop_step();
        }
        else if constexpr (std::is_same_v<T, SearchDeckStep>) {
            // Pop and process search result
            state.pop_step();

            // Move selected cards to destination
            auto& player = state.get_player(s.player_id);
            for (const auto& card_id : s.selected_card_ids) {
                auto card_opt = player.deck.take_card(card_id);
                if (card_opt.has_value()) {
                    switch (s.destination) {
                        case ZoneType::HAND:
                            player.hand.add_card(std::move(*card_opt));
                            break;
                        case ZoneType::BENCH:
                            if (player.board.can_add_to_bench()) {
                                const CardDef* def = card_db_.get_card(card_opt->card_id);
                                if (def) card_opt->current_hp = def->hp;
                                player.board.add_to_bench(std::move(*card_opt));
                            }
                            break;
                        default:
                            // For other destinations, just add to hand as fallback
                            player.hand.add_card(std::move(*card_opt));
                            break;
                    }
                }
            }

            // Shuffle deck if required
            if (s.shuffle_after) {
                player.deck.shuffle(rng_);
            }
        }
        else {
            // Default: just pop the step
            state.pop_step();
        }
    }, step);
}

void PokemonEngine::apply_confirm_selection(GameState& state, const Action& action) const {
    if (state.resolution_stack.empty()) return;

    std::visit([&](auto& s) {
        s.is_complete = true;
    }, state.resolution_stack.back());

    // Process step completion
    process_step_completion(state);
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

    // Step 1: Apply damage modifiers (before weakness/resistance)
    // These include attack bonuses from abilities, effects, etc.
    damage = logic_registry_.apply_modifiers(state, "damage_dealt", damage);

    // Step 2: Apply weakness (x2)
    if (defender_def->weakness.has_value()) {
        for (const auto& type : attacker_def->types) {
            if (type == *defender_def->weakness) {
                damage *= defender_def->weakness_multiplier;
                break;
            }
        }
    }

    // Step 3: Apply resistance (-30)
    if (defender_def->resistance.has_value()) {
        for (const auto& type : attacker_def->types) {
            if (type == *defender_def->resistance) {
                damage += defender_def->resistance_value;  // Usually -30
                break;
            }
        }
    }

    // Step 4: Apply damage reduction modifiers (after weakness/resistance)
    // These include abilities like Diamond Coat that reduce incoming damage
    damage = logic_registry_.apply_modifiers(state, "damage_taken", damage);

    // Step 5: Apply global damage modifiers (stadium effects, etc.)
    auto global_modifiers = logic_registry_.scan_global_modifiers(state, "global_damage");
    for (const auto& [card_id, source_ptr, modifier_fn] : global_modifiers) {
        damage = modifier_fn(state, "global_damage", damage);
    }

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
// UTILITY - ENERGY COST VALIDATION
// ============================================================================

std::unordered_map<EnergyType, int> PokemonEngine::calculate_provided_energy(
    const CardInstance& pokemon) const {
    std::unordered_map<EnergyType, int> provided;

    for (const auto& energy_card : pokemon.attached_energy) {
        const CardDef* energy_def = card_db_.get_card(energy_card.card_id);
        if (!energy_def) continue;

        if (energy_def->is_basic_energy) {
            // Basic energy provides 1 of its type
            provided[energy_def->energy_type]++;
        } else {
            // Special energy - use provides list
            for (const auto& type : energy_def->provides) {
                provided[type]++;
            }

            // If no provides specified, default to 1 colorless
            if (energy_def->provides.empty()) {
                provided[EnergyType::COLORLESS]++;
            }
        }
    }

    return provided;
}

bool PokemonEngine::can_pay_energy_cost(
    const std::unordered_map<EnergyType, int>& provided_energy,
    const std::vector<EnergyType>& cost) const {

    if (cost.empty()) {
        return true;
    }

    // Copy provided energy so we can modify it
    std::unordered_map<EnergyType, int> available = provided_energy;

    // Count specific type requirements vs colorless
    int colorless_needed = 0;
    std::unordered_map<EnergyType, int> specific_needed;

    for (const auto& type : cost) {
        if (type == EnergyType::COLORLESS) {
            colorless_needed++;
        } else {
            specific_needed[type]++;
        }
    }

    // Step 1: Pay specific type requirements first
    for (const auto& [type, count] : specific_needed) {
        auto it = available.find(type);
        int have = (it != available.end()) ? it->second : 0;
        if (have < count) {
            return false;  // Not enough of this specific type
        }
        available[type] -= count;
    }

    // Step 2: Pay colorless with any remaining energy
    int total_remaining = 0;
    for (const auto& [type, count] : available) {
        total_remaining += count;
    }

    return total_remaining >= colorless_needed;
}

bool PokemonEngine::has_energy_for_attack(const CardInstance& pokemon,
                                          const std::vector<EnergyType>& cost) const {
    // Calculate provided energy with type awareness
    auto provided = calculate_provided_energy(pokemon);
    return can_pay_energy_cost(provided, cost);
}

int PokemonEngine::calculate_retreat_cost(const GameState& state,
                                          const CardInstance& pokemon) const {
    const CardDef* def = card_db_.get_card(pokemon.card_id);
    if (!def) return 0;

    int cost = def->retreat_cost;

    // Apply modifiers from LogicRegistry
    // 1. Check Pokemon's own modifier (e.g., Agile ability)
    cost = logic_registry_.apply_modifiers(state, "retreat_cost", cost);

    // 2. Check global modifiers (e.g., Beach Court Stadium)
    auto global_modifiers = logic_registry_.scan_global_modifiers(state, "global_retreat_cost");
    for (const auto& [card_id, source_ptr, modifier_fn] : global_modifiers) {
        cost = modifier_fn(state, "global_retreat_cost", cost);
    }

    // 3. Check attached tools (e.g., Float Stone)
    for (const auto& tool : pokemon.attached_tools) {
        const CardDef* tool_def = card_db_.get_card(tool.card_id);
        if (tool_def) {
            // Look up tool modifier in registry
            // TODO: Add tool-specific modifier lookup
        }
    }

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

// ============================================================================
// FILTER CRITERIA MATCHING
// ============================================================================

bool PokemonEngine::card_matches_filter(
    const CardInstance& card,
    const std::unordered_map<std::string, std::string>& filter,
    const GameState& state,
    const PlayerState& player) const {

    if (filter.empty()) {
        return true;  // No filter = match all
    }

    const CardDef* def = card_db_.get_card(card.card_id);
    if (!def) return false;

    // Check each filter criterion
    for (const auto& [key, value] : filter) {
        // Supertype filter
        if (key == "supertype") {
            bool match = false;
            if (value == "Pokemon" && def->is_pokemon()) match = true;
            if (value == "Trainer" && def->is_trainer()) match = true;
            if (value == "Energy" && def->is_energy()) match = true;
            if (!match) return false;
        }
        // Subtype filter
        else if (key == "subtype") {
            Subtype target_subtype = CardDatabase::parse_subtype(value);
            bool found = std::find(def->subtypes.begin(), def->subtypes.end(),
                                   target_subtype) != def->subtypes.end();
            if (!found) return false;
        }
        // Max HP filter (for Buddy-Buddy Poffin)
        else if (key == "max_hp") {
            if (!def->is_pokemon()) return false;
            int max_hp = std::stoi(value);
            if (def->hp > max_hp) return false;
        }
        // Pokemon type filter
        else if (key == "pokemon_type") {
            if (!def->is_pokemon()) return false;
            EnergyType target_type = CardDatabase::parse_energy_type(value);
            bool found = std::find(def->types.begin(), def->types.end(),
                                   target_type) != def->types.end();
            if (!found) return false;
        }
        // Energy type filter
        else if (key == "energy_type") {
            if (!def->is_energy()) return false;
            EnergyType target_type = CardDatabase::parse_energy_type(value);
            if (def->energy_type != target_type) return false;
        }
        // Name filter (exact match)
        else if (key == "name") {
            if (def->name != value) return false;
        }
        // Evolves from filter
        else if (key == "evolves_from") {
            if (!def->evolves_from.has_value()) return false;
            if (*def->evolves_from != value) return false;
        }
        // Rare Candy target filter (Stage 2 that evolves from a bench Pokemon)
        else if (key == "rare_candy_target" && value == "true") {
            if (!def->is_stage_2()) return false;
            if (!def->evolves_from.has_value()) return false;

            // Must have a valid Stage 1 that evolves from a Basic on bench
            // This requires checking the evolution chain
            // Simplified: just check if it's Stage 2
        }
        // Super Rod target filter (Pokemon or basic Energy)
        else if (key == "super_rod_target" && value == "true") {
            if (!def->is_pokemon() && !(def->is_energy() && def->is_basic_energy)) {
                return false;
            }
        }
        // Night Stretcher target (Pokemon)
        else if (key == "night_stretcher_target" && value == "true") {
            if (!def->is_pokemon()) return false;
        }
        // Basic Pokemon filter
        else if (key == "is_basic" && value == "true") {
            if (!def->is_basic_pokemon()) return false;
        }
    }

    return true;
}

} // namespace pokemon

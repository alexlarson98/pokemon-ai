/**
 * Pokemon TCG Engine - Logic Registry Implementation
 */

#include "logic_registry.hpp"
#include "card_database.hpp"
#include <iostream>
#include <tuple>

namespace pokemon {

// ============================================================================
// REGISTRATION
// ============================================================================

void LogicRegistry::register_attack(const CardDefID& card_id,
                                    const std::string& attack_name,
                                    AttackCallback callback) {
    std::string key = make_key(card_id, attack_name);
    attacks_[key] = std::move(callback);
}

void LogicRegistry::register_ability(const CardDefID& card_id,
                                     const std::string& ability_name,
                                     AbilityCallback callback) {
    std::string key = make_key(card_id, ability_name);
    abilities_[key] = std::move(callback);
}

// ============================================================================
// UNIFIED TRAINER REGISTRATION
// ============================================================================

void LogicRegistry::register_trainer_handler(const CardDefID& card_id,
                                              TrainerHandler handler) {
    trainer_handlers_[card_id] = std::move(handler);
}

bool LogicRegistry::has_trainer_handler(const CardDefID& card_id) const {
    return trainer_handlers_.find(card_id) != trainer_handlers_.end();
}

TrainerResult LogicRegistry::invoke_trainer_handler(const CardDefID& card_id,
                                                     TrainerContext& ctx) const {
    auto it = trainer_handlers_.find(card_id);
    if (it != trainer_handlers_.end()) {
        return it->second(ctx);
    }
    // Default: trainer has no special effect
    return TrainerResult{};
}

void LogicRegistry::register_generator(const CardDefID& card_id,
                                       const std::string& logic_type,
                                       GeneratorCallback callback) {
    std::string key = make_key(card_id, logic_type);
    generators_[key] = std::move(callback);
}

void LogicRegistry::register_guard(const CardDefID& card_id,
                                   const std::string& ability_name,
                                   GuardCallback callback) {
    std::string key = make_key(card_id, ability_name);
    guards_[key] = std::move(callback);
}

void LogicRegistry::register_modifier(const CardDefID& card_id,
                                      const std::string& ability_name,
                                      const std::string& context,
                                      ModifierCallback callback) {
    std::string key = card_id + ":" + ability_name + ":" + context;
    modifiers_[key] = std::move(callback);
}

void LogicRegistry::register_hook(const CardDefID& card_id,
                                  const std::string& ability_name,
                                  const std::string& event_type,
                                  HookCallback callback) {
    std::string key = card_id + ":" + ability_name + ":" + event_type;
    hooks_[key] = std::move(callback);
}

void LogicRegistry::register_passive(const CardDefID& card_id,
                                     const std::string& ability_name,
                                     PassiveConditionCallback condition_callback,
                                     PassiveCallback effect_callback) {
    std::string key = make_key(card_id, ability_name);
    passives_[key] = PassiveEntry{std::move(condition_callback), std::move(effect_callback)};
}

// ============================================================================
// STADIUM REGISTRATION AND INVOCATION
// ============================================================================

void LogicRegistry::register_stadium(const CardDefID& card_id, StadiumHandler handler) {
    stadium_handlers_[card_id] = std::move(handler);
}

bool LogicRegistry::has_stadium_handler(const CardDefID& card_id) const {
    return stadium_handlers_.find(card_id) != stadium_handlers_.end();
}

const StadiumHandler* LogicRegistry::get_stadium_handler(const CardDefID& card_id) const {
    auto it = stadium_handlers_.find(card_id);
    if (it != stadium_handlers_.end()) {
        return &it->second;
    }
    return nullptr;
}

StadiumResult LogicRegistry::invoke_stadium_on_enter(const CardDefID& card_id,
                                                      StadiumContext& ctx) const {
    auto it = stadium_handlers_.find(card_id);
    if (it != stadium_handlers_.end() && it->second.on_enter) {
        return it->second.on_enter(ctx);
    }
    // Default: no special on-enter effect
    StadiumResult result;
    result.success = true;
    return result;
}

StadiumResult LogicRegistry::invoke_stadium_on_leave(const CardDefID& card_id,
                                                      StadiumContext& ctx,
                                                      PlayerID new_stadium_owner) const {
    auto it = stadium_handlers_.find(card_id);
    if (it != stadium_handlers_.end() && it->second.on_leave) {
        return it->second.on_leave(ctx, new_stadium_owner);
    }
    // Default: no special on-leave effect
    StadiumResult result;
    result.success = true;
    return result;
}

int LogicRegistry::get_stadium_bench_size(const GameState& state,
                                           const CardDatabase& db,
                                           PlayerID player_id) const {
    // Default bench size
    constexpr int DEFAULT_BENCH_SIZE = 5;

    // Check if there's a stadium in play with a bench size modifier
    if (!state.stadium.has_value()) {
        return DEFAULT_BENCH_SIZE;
    }

    const auto& stadium_card = state.stadium.value();
    auto it = stadium_handlers_.find(stadium_card.card_id);
    if (it != stadium_handlers_.end() && it->second.bench_size) {
        return it->second.bench_size(state, db, player_id);
    }

    return DEFAULT_BENCH_SIZE;
}

bool LogicRegistry::check_stadium_condition(const GameState& state,
                                             const CardDatabase& db,
                                             PlayerID player_id) const {
    // Check if there's a stadium in play with a condition
    if (!state.stadium.has_value()) {
        return false;
    }

    const auto& stadium_card = state.stadium.value();
    auto it = stadium_handlers_.find(stadium_card.card_id);
    if (it != stadium_handlers_.end() && it->second.condition) {
        return it->second.condition(state, db, player_id);
    }

    return false;
}

// ============================================================================
// LOOKUP
// ============================================================================

bool LogicRegistry::has_attack(const CardDefID& card_id,
                               const std::string& attack_name) const {
    std::string key = make_key(card_id, attack_name);
    return attacks_.find(key) != attacks_.end();
}

bool LogicRegistry::has_ability(const CardDefID& card_id,
                                const std::string& ability_name) const {
    std::string key = make_key(card_id, ability_name);
    return abilities_.find(key) != abilities_.end();
}

// ============================================================================
// INVOCATION
// ============================================================================

AttackResult LogicRegistry::invoke_attack(const CardDefID& card_id,
                                          const std::string& attack_name,
                                          GameState& state,
                                          const CardInstance& attacker,
                                          CardInstance* target) const {
    std::string key = make_key(card_id, attack_name);
    auto it = attacks_.find(key);

    if (it != attacks_.end()) {
        return it->second(state, attacker, attack_name, target);
    }

    // Default: return empty result (caller will apply base damage)
    return AttackResult{};
}

AbilityResult LogicRegistry::invoke_ability(const CardDefID& card_id,
                                            const std::string& ability_name,
                                            GameState& state,
                                            const CardInstance& pokemon) const {
    std::string key = make_key(card_id, ability_name);
    auto it = abilities_.find(key);

    if (it != abilities_.end()) {
        return it->second(state, pokemon, ability_name);
    }

    // Default: ability has no effect
    return AbilityResult{};
}

GeneratorResult LogicRegistry::invoke_generator(const CardDefID& card_id,
                                                const std::string& logic_type,
                                                const GameState& state,
                                                const CardInstance& card) const {
    std::string key = make_key(card_id, logic_type);
    auto it = generators_.find(key);

    if (it != generators_.end()) {
        return it->second(state, card);
    }

    return GeneratorResult{};
}

bool LogicRegistry::check_guards(const GameState& state, const Action& action) const {
    // Check all registered guards
    for (const auto& [key, callback] : guards_) {
        if (!callback(state, action)) {
            return false;  // Action blocked
        }
    }
    return true;  // Action allowed
}

int LogicRegistry::apply_modifiers(const GameState& state,
                                   const std::string& context,
                                   int base_value) const {
    int value = base_value;

    // Apply all modifiers for this context
    for (const auto& [key, callback] : modifiers_) {
        // Check if this modifier applies to the context
        if (key.find(":" + context) != std::string::npos) {
            value = callback(state, context, value);
        }
    }

    return value;
}

bool LogicRegistry::trigger_hooks(GameState& state, const std::string& event_type) const {
    bool cancel = false;

    for (const auto& [key, callback] : hooks_) {
        if (key.find(":" + event_type) != std::string::npos) {
            if (callback(state, event_type)) {
                cancel = true;
            }
        }
    }

    return cancel;
}

// ============================================================================
// PASSIVE ABILITY LOCK CHECKING
// ============================================================================

bool LogicRegistry::is_ability_blocked_by_passive(const GameState& state,
                                                   const CardInstance& target_pokemon,
                                                   const std::string& ability_name) const {
    // Check BOTH players' Active Spots for passive ability blockers (e.g., Klefki)
    // This matches Python's is_ability_blocked_by_passive()
    for (const auto& player : state.players) {
        if (player.board.active_spot.has_value()) {
            const CardInstance& active_pokemon = player.board.active_spot.value();

            // Check all registered passives for this card
            for (const auto& [key, entry] : passives_) {
                // Key format is "card_id:ability_name"
                // Check if this passive belongs to the active pokemon's card
                if (key.find(active_pokemon.card_id + ":") == 0) {
                    // Check if condition is met (e.g., has tool attached)
                    if (entry.condition && entry.condition(state, active_pokemon)) {
                        // Check if this passive blocks the target ability
                        if (entry.effect && entry.effect(state, active_pokemon, target_pokemon, ability_name)) {
                            return true;  // Ability is blocked
                        }
                    }
                }
            }
        }
    }

    return false;  // Ability is allowed
}

// ============================================================================
// BOARD SCANNING FUNCTIONS
// ============================================================================

std::vector<std::tuple<CardDefID, const CardInstance*, ModifierCallback>>
LogicRegistry::scan_global_modifiers(const GameState& state, const std::string& modifier_type) const {
    std::vector<std::tuple<CardDefID, const CardInstance*, ModifierCallback>> results;

    // Helper to check a single card
    auto check_card = [&](const CardInstance& card) {
        // Check all registered modifiers for this card and type
        for (const auto& [key, callback] : modifiers_) {
            // Key format is "card_id:ability_name:context"
            // Check if this modifier belongs to this card and matches the type
            if (key.find(card.card_id + ":") == 0 &&
                key.find(":" + modifier_type) != std::string::npos) {
                results.emplace_back(card.card_id, &card, callback);
            }
        }
    };

    // Scan both players' boards
    for (const auto& player : state.players) {
        // Check active Pokemon
        if (player.board.active_spot.has_value()) {
            check_card(player.board.active_spot.value());
        }

        // Check bench Pokemon
        for (const auto& bench_card : player.board.bench) {
            check_card(bench_card);
        }
    }

    // Check Stadium card
    if (state.stadium.has_value()) {
        check_card(state.stadium.value());
    }

    return results;
}

std::vector<std::tuple<CardDefID, const CardInstance*, bool>>
LogicRegistry::scan_global_guards(const GameState& state, const std::string& guard_type) const {
    std::vector<std::tuple<CardDefID, const CardInstance*, bool>> results;

    // Create a dummy action for guard checking
    Action dummy_action;

    // Helper to check a single card
    auto check_card = [&](const CardInstance& card) {
        // Check all registered guards for this card and type
        for (const auto& [key, callback] : guards_) {
            // Key format is "card_id:ability_name"
            // Check if this guard belongs to this card
            if (key.find(card.card_id + ":") == 0) {
                // Call the guard to check if it's blocking
                bool is_blocking = !callback(state, dummy_action);  // Guard returns true if allowed
                results.emplace_back(card.card_id, &card, is_blocking);
            }
        }
    };

    // Scan both players' boards
    for (const auto& player : state.players) {
        // Check active Pokemon
        if (player.board.active_spot.has_value()) {
            check_card(player.board.active_spot.value());
        }

        // Check bench Pokemon
        for (const auto& bench_card : player.board.bench) {
            check_card(bench_card);
        }
    }

    // Check Stadium card
    if (state.stadium.has_value()) {
        check_card(state.stadium.value());
    }

    return results;
}

bool LogicRegistry::check_global_block(const GameState& state, const std::string& guard_type) const {
    auto guards = scan_global_guards(state, guard_type);
    for (const auto& [card_id, card_ptr, is_blocking] : guards) {
        if (is_blocking) {
            return true;  // Found a blocking guard
        }
    }
    return false;  // No guards blocking
}

// ============================================================================
// PYTHON CALLBACK SUPPORT
// ============================================================================

void LogicRegistry::register_python_attack(const CardDefID& card_id,
                                           const std::string& attack_name,
                                           std::function<void(void*)> py_callback) {
    // Wrap Python callback in C++ callback
    register_attack(card_id, attack_name,
        [py_callback](GameState& state, const CardInstance& attacker,
                      const std::string& attack_name, CardInstance* target) -> AttackResult {
            // Create context struct for Python
            struct PythonContext {
                GameState* state;
                const CardInstance* attacker;
                const std::string* attack_name;
                CardInstance* target;
                AttackResult result;
            };

            PythonContext ctx{&state, &attacker, &attack_name, target, AttackResult{}};
            py_callback(&ctx);

            return ctx.result;
        });
}

void LogicRegistry::register_python_trainer(const CardDefID& card_id,
                                            std::function<void(void*)> py_callback) {
    // Note: Python trainer support requires a CardDatabase to create TrainerContext.
    // This is a stub - Python trainers should be registered via a different mechanism
    // that provides the necessary CardDatabase reference.
    // TODO: Implement proper Python trainer registration with CardDatabase access
    (void)card_id;
    (void)py_callback;
}

// ============================================================================
// DEFAULT HANDLERS
// ============================================================================

AttackResult default_attack_handler(
    GameState& state,
    const CardInstance& attacker,
    const std::string& attack_name,
    CardInstance* target,
    int base_damage) {

    AttackResult result;
    result.damage_dealt = base_damage;

    if (target && base_damage > 0) {
        // Calculate damage counters
        int counters = base_damage / 10;
        target->damage_counters += counters;

        // TODO: Get card def to check for knockout
    }

    return result;
}

TrainerResult default_trainer_handler(
    GameState& state,
    const CardInstance& card) {

    TrainerResult result;
    result.success = true;
    result.effect_description = "No special effect";
    return result;
}

// ============================================================================
// GLOBAL REGISTRY
// ============================================================================

LogicRegistry& get_logic_registry() {
    static LogicRegistry instance;
    return instance;
}

} // namespace pokemon

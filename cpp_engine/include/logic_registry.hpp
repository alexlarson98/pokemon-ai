/**
 * Pokemon TCG Engine - Logic Registry
 *
 * Central registry for card-specific logic (attacks, abilities, items).
 * Supports both C++ native implementations and Python callbacks via pybind11.
 *
 * Architecture:
 * - Each card can have multiple logic handlers (attack, ability, effect, etc.)
 * - Logic is looked up by card_id + logic_type + optional name
 * - If no specific logic exists, falls back to default behavior
 * - Python callbacks can be registered at runtime for prototyping
 *
 * Example usage:
 *   // Register C++ attack handler
 *   registry.register_attack("sv3-125", "Burning Darkness", burning_darkness_attack);
 *
 *   // Invoke attack
 *   auto result = registry.invoke_attack("sv3-125", "Burning Darkness", state, attacker);
 */

#pragma once

#include "types.hpp"
#include "game_state.hpp"
#include <functional>
#include <unordered_map>
#include <variant>

namespace pokemon {

// Forward declarations
class PokemonEngine;

// ============================================================================
// EFFECT RESULT TYPES
// ============================================================================

/**
 * Result of applying an attack effect.
 */
struct AttackResult {
    int damage_dealt = 0;
    bool target_knocked_out = false;
    bool requires_coin_flip = false;
    std::string effect_description;

    // Modifications to apply
    std::vector<std::pair<CardID, int>> additional_damage;  // (target, damage)
    std::vector<std::pair<CardID, StatusCondition>> add_status;
    std::vector<std::pair<CardID, std::string>> add_effect;
};

/**
 * Result of applying an ability effect.
 */
struct AbilityResult {
    bool activated = false;
    std::string effect_description;

    // Follow-up resolution steps
    std::vector<ResolutionStep> push_steps;
};

/**
 * Result of applying a trainer effect.
 */
struct TrainerResult {
    bool success = false;
    bool requires_resolution = false;
    std::string effect_description;

    // Follow-up resolution steps
    std::vector<ResolutionStep> push_steps;
};

/**
 * Action generator result - returns additional legal actions.
 */
struct GeneratorResult {
    bool valid = true;
    std::string reason;
    std::vector<Action> actions;
};

// ============================================================================
// CALLBACK TYPES
// ============================================================================

// Attack: (state, attacker, attack_name, target) -> AttackResult
using AttackCallback = std::function<AttackResult(
    GameState&,
    const CardInstance&,
    const std::string&,
    CardInstance*
)>;

// Ability: (state, pokemon, ability_name) -> AbilityResult
using AbilityCallback = std::function<AbilityResult(
    GameState&,
    const CardInstance&,
    const std::string&
)>;

// Trainer (Item/Supporter): (state, card) -> TrainerResult
using TrainerCallback = std::function<TrainerResult(
    GameState&,
    const CardInstance&
)>;

// Trainer with action context: (state, card, action) -> TrainerResult
// Used when the trainer needs target info from the action (e.g., Rare Candy)
using TrainerWithActionCallback = std::function<TrainerResult(
    GameState&,
    const CardInstance&,
    const Action&
)>;

// Action generator: (state, card) -> GeneratorResult
using GeneratorCallback = std::function<GeneratorResult(
    const GameState&,
    const CardInstance&
)>;

// Guard check: (state, action) -> bool (can perform action?)
using GuardCallback = std::function<bool(
    const GameState&,
    const Action&
)>;

// Modifier: (state, context, value) -> modified value
using ModifierCallback = std::function<int(
    const GameState&,
    const std::string&,  // context (e.g., "damage", "retreat_cost")
    int
)>;

// Hook: (state, event_type) -> bool (should cancel event?)
using HookCallback = std::function<bool(
    GameState&,
    const std::string&  // event type
)>;

// Passive ability lock: (state, source_pokemon, target_pokemon, ability_name) -> bool (is blocked?)
// Used for passive ability blockers like Klefki's Mischievous Lock
using PassiveCallback = std::function<bool(
    const GameState&,
    const CardInstance&,  // source pokemon with the passive ability
    const CardInstance&,  // target pokemon whose ability is being checked
    const std::string&    // ability name being checked
)>;

// Passive condition: (state, source_pokemon) -> bool (is condition met?)
// Used to check if passive ability should be active (e.g., has tool attached)
using PassiveConditionCallback = std::function<bool(
    const GameState&,
    const CardInstance&  // source pokemon with the passive ability
)>;

// ============================================================================
// LOGIC REGISTRY
// ============================================================================

/**
 * LogicRegistry - Central registry for card-specific logic.
 *
 * Thread-safe for read operations (lookup).
 * Not thread-safe for registration (call before game starts).
 */
class LogicRegistry {
public:
    LogicRegistry() = default;
    ~LogicRegistry() = default;

    // ========================================================================
    // REGISTRATION
    // ========================================================================

    /**
     * Register an attack effect handler.
     *
     * @param card_id Card definition ID (e.g., "sv3-125")
     * @param attack_name Attack name (e.g., "Burning Darkness")
     * @param callback Effect handler function
     */
    void register_attack(const CardDefID& card_id,
                        const std::string& attack_name,
                        AttackCallback callback);

    /**
     * Register an ability effect handler.
     */
    void register_ability(const CardDefID& card_id,
                         const std::string& ability_name,
                         AbilityCallback callback);

    /**
     * Register a trainer (Item/Supporter) effect handler.
     */
    void register_trainer(const CardDefID& card_id,
                         TrainerCallback callback);

    /**
     * Register a trainer that needs action context (target info).
     * Used for cards like Rare Candy that need to know which target was selected.
     */
    void register_trainer_with_action(const CardDefID& card_id,
                                      TrainerWithActionCallback callback);

    /**
     * Register an action generator (for cards with complex choices).
     */
    void register_generator(const CardDefID& card_id,
                           const std::string& logic_type,
                           GeneratorCallback callback);

    /**
     * Register a guard check (for abilities that block actions).
     */
    void register_guard(const CardDefID& card_id,
                       const std::string& ability_name,
                       GuardCallback callback);

    /**
     * Register a modifier (for passive effects that change values).
     */
    void register_modifier(const CardDefID& card_id,
                          const std::string& ability_name,
                          const std::string& context,
                          ModifierCallback callback);

    /**
     * Register a hook (for abilities that trigger on events).
     */
    void register_hook(const CardDefID& card_id,
                      const std::string& ability_name,
                      const std::string& event_type,
                      HookCallback callback);

    /**
     * Register a passive ability lock (e.g., Klefki's Mischievous Lock).
     *
     * Passive ability locks block other Pokemon's abilities when a condition is met.
     * They are checked from the Active Spot only.
     *
     * @param card_id Card with the passive ability (e.g., "sv6-96" for Klefki)
     * @param ability_name Name of the ability (e.g., "Mischievous Lock")
     * @param condition_callback Returns true if the passive is active (e.g., has tool)
     * @param effect_callback Returns true if target ability is blocked
     */
    void register_passive(const CardDefID& card_id,
                         const std::string& ability_name,
                         PassiveConditionCallback condition_callback,
                         PassiveCallback effect_callback);

    // ========================================================================
    // LOOKUP
    // ========================================================================

    /**
     * Check if attack logic exists for a card.
     */
    bool has_attack(const CardDefID& card_id, const std::string& attack_name) const;

    /**
     * Check if ability logic exists.
     */
    bool has_ability(const CardDefID& card_id, const std::string& ability_name) const;

    /**
     * Check if trainer logic exists.
     */
    bool has_trainer(const CardDefID& card_id) const;

    /**
     * Check if trainer with action logic exists.
     */
    bool has_trainer_with_action(const CardDefID& card_id) const;

    // ========================================================================
    // INVOCATION
    // ========================================================================

    /**
     * Invoke attack effect.
     *
     * @return AttackResult with damage and effects, or default if no handler
     */
    AttackResult invoke_attack(const CardDefID& card_id,
                               const std::string& attack_name,
                               GameState& state,
                               const CardInstance& attacker,
                               CardInstance* target) const;

    /**
     * Invoke ability effect.
     */
    AbilityResult invoke_ability(const CardDefID& card_id,
                                 const std::string& ability_name,
                                 GameState& state,
                                 const CardInstance& pokemon) const;

    /**
     * Invoke trainer effect.
     */
    TrainerResult invoke_trainer(const CardDefID& card_id,
                                 GameState& state,
                                 const CardInstance& card) const;

    /**
     * Invoke trainer effect with action context.
     */
    TrainerResult invoke_trainer_with_action(const CardDefID& card_id,
                                             GameState& state,
                                             const CardInstance& card,
                                             const Action& action) const;

    /**
     * Invoke action generator.
     */
    GeneratorResult invoke_generator(const CardDefID& card_id,
                                     const std::string& logic_type,
                                     const GameState& state,
                                     const CardInstance& card) const;

    /**
     * Check all guards for an action.
     *
     * @return true if action is allowed, false if blocked
     */
    bool check_guards(const GameState& state, const Action& action) const;

    /**
     * Apply all modifiers for a context.
     *
     * @return Modified value after all applicable modifiers
     */
    int apply_modifiers(const GameState& state,
                       const std::string& context,
                       int base_value) const;

    /**
     * Trigger all hooks for an event.
     *
     * @return true if event should be cancelled
     */
    bool trigger_hooks(GameState& state, const std::string& event_type) const;

    // ========================================================================
    // PASSIVE ABILITY LOCK CHECKING
    // ========================================================================

    /**
     * Check if an ability is blocked by a passive ability lock.
     *
     * Scans BOTH players' Active Spots for passive ability blockers (e.g., Klefki).
     * This matches Python's is_ability_blocked_by_passive().
     *
     * @param state Current game state
     * @param target_pokemon Pokemon whose ability is being checked
     * @param ability_name Name of the ability to check
     * @return true if the ability is BLOCKED, false if allowed
     */
    bool is_ability_blocked_by_passive(const GameState& state,
                                       const CardInstance& target_pokemon,
                                       const std::string& ability_name) const;

    // ========================================================================
    // BOARD SCANNING FUNCTIONS
    // ========================================================================

    /**
     * Scan the board for cards with global modifiers of the specified type.
     *
     * Global modifiers affect OTHER cards (e.g., Beach Court Stadium).
     *
     * @param state Current game state
     * @param modifier_type Type of modifier (e.g., "global_retreat_cost")
     * @return Vector of (card_id, card_instance_ptr, modifier_callback) tuples
     */
    std::vector<std::tuple<CardDefID, const CardInstance*, ModifierCallback>>
    scan_global_modifiers(const GameState& state, const std::string& modifier_type) const;

    /**
     * Scan the board for cards with global guards of the specified type.
     *
     * Global guards can block effects for OTHER cards (e.g., Item Lock).
     *
     * @param state Current game state
     * @param guard_type Type of guard (e.g., "global_play_item")
     * @return Vector of (card_id, card_instance_ptr, is_blocking) tuples
     */
    std::vector<std::tuple<CardDefID, const CardInstance*, bool>>
    scan_global_guards(const GameState& state, const std::string& guard_type) const;

    /**
     * Check if ANY card on the board blocks the specified effect.
     *
     * @param state Current game state
     * @param guard_type Type of global guard (e.g., "global_play_item")
     * @return true if ANY card blocks the effect
     */
    bool check_global_block(const GameState& state, const std::string& guard_type) const;

    // ========================================================================
    // PYTHON CALLBACK SUPPORT
    // ========================================================================

    /**
     * Register a Python callback for an attack.
     *
     * Called from pybind11 wrapper.
     */
    void register_python_attack(const CardDefID& card_id,
                                const std::string& attack_name,
                                std::function<void(void*)> py_callback);

    /**
     * Register a Python callback for a trainer effect.
     */
    void register_python_trainer(const CardDefID& card_id,
                                 std::function<void(void*)> py_callback);

    // ========================================================================
    // STATISTICS
    // ========================================================================

    size_t attack_count() const { return attacks_.size(); }
    size_t ability_count() const { return abilities_.size(); }
    size_t trainer_count() const { return trainers_.size(); }

private:
    // Key: card_id + ":" + name
    std::unordered_map<std::string, AttackCallback> attacks_;
    std::unordered_map<std::string, AbilityCallback> abilities_;
    std::unordered_map<CardDefID, TrainerCallback> trainers_;
    std::unordered_map<CardDefID, TrainerWithActionCallback> trainers_with_action_;
    std::unordered_map<std::string, GeneratorCallback> generators_;
    std::unordered_map<std::string, GuardCallback> guards_;
    std::unordered_map<std::string, ModifierCallback> modifiers_;
    std::unordered_map<std::string, HookCallback> hooks_;

    // Passive ability locks (e.g., Klefki's Mischievous Lock)
    struct PassiveEntry {
        PassiveConditionCallback condition;
        PassiveCallback effect;
    };
    std::unordered_map<std::string, PassiveEntry> passives_;

    // Helper to make composite key
    static std::string make_key(const CardDefID& card_id, const std::string& name) {
        return card_id + ":" + name;
    }
};

// ============================================================================
// DEFAULT HANDLERS
// ============================================================================

/**
 * Default attack handler - just applies base damage.
 */
AttackResult default_attack_handler(
    GameState& state,
    const CardInstance& attacker,
    const std::string& attack_name,
    CardInstance* target,
    int base_damage);

/**
 * Default trainer handler - just discards the card.
 */
TrainerResult default_trainer_handler(
    GameState& state,
    const CardInstance& card);

// ============================================================================
// GLOBAL REGISTRY
// ============================================================================

/**
 * Get the global logic registry singleton.
 */
LogicRegistry& get_logic_registry();

} // namespace pokemon

/**
 * Pokemon TCG Engine - Main Engine Interface
 *
 * This is the primary interface for the game engine.
 * Provides get_legal_actions() and step() methods for MCTS.
 */

#pragma once

#include "game_state.hpp"
#include "card_database.hpp"
#include "logic_registry.hpp"
#include <random>

namespace pokemon {

/**
 * PokemonEngine - The game engine.
 *
 * Thread-safe for read operations (get_legal_actions).
 * Not thread-safe for mutations (step) - use clone for parallel MCTS.
 */
class PokemonEngine {
public:
    PokemonEngine();
    ~PokemonEngine() = default;

    // ========================================================================
    // CORE API (matches Python engine.py)
    // ========================================================================

    /**
     * Get all legal actions from the current state.
     *
     * This is the main entry point for MCTS action generation.
     * Returns a vector of actions that can be passed to step().
     */
    std::vector<Action> get_legal_actions(const GameState& state) const;

    /**
     * Apply an action to a state and return the new state.
     *
     * Creates a clone of the state, applies the action, and returns it.
     * The original state is not modified.
     */
    GameState step(const GameState& state, const Action& action) const;

    /**
     * Apply an action to a state in-place.
     *
     * Modifies the state directly without cloning.
     * Use this for rollouts where you don't need the original state.
     */
    void step_inplace(GameState& state, const Action& action) const;

    // ========================================================================
    // GAME SETUP
    // ========================================================================

    /**
     * Create a new game state from two deck lists.
     */
    GameState create_game(const std::vector<CardDefID>& deck1,
                         const std::vector<CardDefID>& deck2) const;

    /**
     * Set up the initial board (shuffle, draw hands, place prizes).
     */
    GameState setup_initial_board(GameState state) const;

    // ========================================================================
    // WIN CONDITION CHECKS
    // ========================================================================

    /**
     * Check if the game has ended and update the result.
     */
    void check_win_conditions(GameState& state) const;

    // ========================================================================
    // CARD DATABASE ACCESS
    // ========================================================================

    const CardDatabase& get_card_database() const { return card_db_; }

    /**
     * Load card database from JSON file.
     * Must be called before using the engine.
     */
    bool load_card_database(const std::string& filepath) {
        return card_db_.load_from_json(filepath);
    }

    // ========================================================================
    // LOGIC REGISTRY ACCESS
    // ========================================================================

    LogicRegistry& get_logic_registry() { return logic_registry_; }
    const LogicRegistry& get_logic_registry() const { return logic_registry_; }

private:
    CardDatabase card_db_;
    LogicRegistry logic_registry_;
    mutable std::mt19937 rng_;  // For shuffling

    // ========================================================================
    // ACTION GENERATION (by phase)
    // ========================================================================

    std::vector<Action> get_setup_actions(const GameState& state) const;
    std::vector<Action> get_mulligan_actions(const GameState& state) const;
    std::vector<Action> get_main_phase_actions(const GameState& state) const;
    std::vector<Action> get_resolution_stack_actions(const GameState& state) const;
    std::vector<Action> get_interrupt_actions(const GameState& state) const;

    // Main phase sub-generators
    std::vector<Action> get_energy_attach_actions(const GameState& state) const;
    std::vector<Action> get_play_basic_actions(const GameState& state) const;
    std::vector<Action> get_evolution_actions(const GameState& state) const;
    std::vector<Action> get_trainer_actions(const GameState& state) const;
    std::vector<Action> get_ability_actions(const GameState& state) const;
    std::vector<Action> get_retreat_actions(const GameState& state) const;
    std::vector<Action> get_attack_actions(const GameState& state) const;

    // ========================================================================
    // ACTION APPLICATION
    // ========================================================================

    void apply_action(GameState& state, const Action& action) const;

    // Action handlers
    void apply_place_active(GameState& state, const Action& action) const;
    void apply_place_bench(GameState& state, const Action& action) const;
    void apply_play_basic(GameState& state, const Action& action) const;
    void apply_evolve(GameState& state, const Action& action) const;
    void apply_attach_energy(GameState& state, const Action& action) const;
    void apply_play_item(GameState& state, const Action& action) const;
    void apply_play_supporter(GameState& state, const Action& action) const;
    void apply_play_stadium(GameState& state, const Action& action) const;
    void apply_attach_tool(GameState& state, const Action& action) const;
    void apply_use_ability(GameState& state, const Action& action) const;
    void apply_retreat(GameState& state, const Action& action) const;
    void apply_attack(GameState& state, const Action& action) const;
    void apply_end_turn(GameState& state, const Action& action) const;
    void apply_take_prize(GameState& state, const Action& action) const;
    void apply_promote_active(GameState& state, const Action& action) const;
    void apply_select_card(GameState& state, const Action& action) const;
    void apply_confirm_selection(GameState& state, const Action& action) const;
    void process_step_completion(GameState& state) const;

    // ========================================================================
    // PHASE TRANSITIONS
    // ========================================================================

    void advance_phase(GameState& state) const;
    void start_turn(GameState& state) const;
    void end_turn(GameState& state) const;

    // ========================================================================
    // DAMAGE AND KNOCKOUT
    // ========================================================================

    int calculate_damage(const GameState& state,
                        const CardInstance& attacker,
                        const CardInstance& defender,
                        int base_damage) const;

    void apply_damage(GameState& state,
                     CardInstance& defender,
                     int damage) const;

    void check_knockout(GameState& state,
                       PlayerID player_id,
                       const CardID& pokemon_id) const;

    // ========================================================================
    // UTILITY
    // ========================================================================

    /**
     * Check if Pokemon has energy to pay attack cost with proper type matching.
     *
     * Energy matching rules:
     * - Specific types (Fire, Water, etc.) must match exactly
     * - Colorless can be paid with any energy type
     * - Uses greedy matching: specific requirements first, then colorless
     */
    bool has_energy_for_attack(const CardInstance& pokemon,
                               const std::vector<EnergyType>& cost) const;

    /**
     * Check if provided energy can pay a specific cost.
     *
     * @param provided_energy Map of energy type -> count
     * @param cost Attack cost (list of energy types)
     * @return true if cost can be paid
     */
    bool can_pay_energy_cost(const std::unordered_map<EnergyType, int>& provided_energy,
                             const std::vector<EnergyType>& cost) const;

    /**
     * Calculate provided energy from a Pokemon's attached energy cards.
     *
     * Handles:
     * - Basic energy (provides 1 of its type)
     * - Special energy (may provide multiple or different types)
     *
     * @param pokemon Pokemon with attached energy
     * @return Map of energy type -> count
     */
    std::unordered_map<EnergyType, int> calculate_provided_energy(
        const CardInstance& pokemon) const;

    int calculate_retreat_cost(const GameState& state,
                              const CardInstance& pokemon) const;

    bool can_evolve(const GameState& state,
                   const CardInstance& base,
                   const CardDef& evolution) const;

    // ========================================================================
    // FILTER CRITERIA MATCHING
    // ========================================================================

    /**
     * Check if a card matches filter criteria (for resolution steps).
     *
     * Supports filters matching Python's _card_matches_step_filter():
     * - supertype: "Pokemon", "Trainer", "Energy"
     * - subtype: "Basic", "Stage 1", "Item", etc.
     * - max_hp: Maximum HP (for Buddy-Buddy Poffin)
     * - pokemon_type: EnergyType filter
     * - energy_type: For energy cards
     * - name: Exact name match
     * - evolves_from: For evolution cards
     * - rare_candy_target: Stage 2 that evolves from bench Pokemon
     * - super_rod_target: Pokemon or basic Energy
     */
    bool card_matches_filter(const CardInstance& card,
                            const std::unordered_map<std::string, std::string>& filter,
                            const GameState& state,
                            const PlayerState& player) const;
};

} // namespace pokemon

/**
 * Pokemon TCG Engine - X-Ray Logger
 *
 * Complete game state visibility for debugging.
 * Logs all game state including hidden zones (decks, prizes).
 * Shows card IDs so exact card movement can be tracked.
 *
 * Format matches Python xray.py for consistency.
 */

#pragma once

#include "game_state.hpp"
#include "action.hpp"
#include <string>
#include <fstream>
#include <functional>

namespace pokemon {

// Forward declaration
class CardDatabase;

/**
 * XRayLogger - Complete game state visibility for debugging.
 *
 * Logs all game state including hidden information (opponent hands, decks, prizes).
 * Useful for auditing card movements and verifying game rules enforcement.
 */
class XRayLogger {
public:
    /**
     * Constructor - creates timestamped log file.
     *
     * @param card_db Optional card database for resolving card names
     * @param output_dir Directory for log files (default: cpp_engine/xrays)
     */
    explicit XRayLogger(const CardDatabase* card_db = nullptr,
                        const std::string& output_dir = "cpp_engine/xrays");

    ~XRayLogger();

    /**
     * Set the card database for name resolution.
     */
    void set_card_database(const CardDatabase* card_db);

    /**
     * Log an action header.
     *
     * @param turn_count Current turn number
     * @param player_id Player taking action
     * @param action Action being taken
     */
    void log_action(int turn_count, PlayerID player_id, const Action& action);

    /**
     * Log complete game state snapshot (including hidden zones).
     *
     * @param state Current game state
     */
    void log_state(const GameState& state);

    /**
     * Log game end result.
     *
     * @param winner Winning player ID (nullopt if draw)
     * @param reason Reason for game end
     */
    void log_game_end(std::optional<PlayerID> winner, const std::string& reason);

    /**
     * Get the log file path.
     */
    const std::string& get_log_path() const { return log_path_; }

    /**
     * Check if logging is enabled.
     */
    bool is_enabled() const { return enabled_; }

    /**
     * Enable/disable logging.
     */
    void set_enabled(bool enabled) { enabled_ = enabled; }

private:
    std::string log_path_;
    std::ofstream log_file_;
    const CardDatabase* card_db_ = nullptr;
    bool enabled_ = true;

    /**
     * Format card as "CardName (short_id)".
     * Uses last 8 characters of instance ID for brevity.
     */
    std::string fmt_card(const CardInstance& card) const;

    /**
     * Format card ID only as "(short_id)" for when we only have the ID.
     */
    std::string fmt_id(const std::string& id) const;

    /**
     * Format a Pokemon line with HP, energy, tools.
     * Format: "ACTIVE:  Charmander (..a1b2) | HP: 60/60 | Energy: [...] | Tools: [...]"
     */
    std::string format_pokemon_line(const CardInstance& pokemon, const std::string& label) const;

    /**
     * Format action description.
     */
    std::string format_action_description(const Action& action) const;

    /**
     * Get action type as string.
     */
    static std::string action_type_str(ActionType type);
};

} // namespace pokemon

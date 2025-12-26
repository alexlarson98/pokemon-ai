/**
 * Pokemon TCG Engine - X-Ray Logger Implementation
 */

#include "xray_logger.hpp"
#include "card_database.hpp"
#include <filesystem>
#include <chrono>
#include <iomanip>
#include <sstream>
#include <iostream>

namespace pokemon {

XRayLogger::XRayLogger(const CardDatabase* card_db, const std::string& output_dir)
    : card_db_(card_db) {

    // Create output directory if it doesn't exist
    std::filesystem::create_directories(output_dir);

    // Create timestamped log file
    auto now = std::chrono::system_clock::now();
    auto time_t = std::chrono::system_clock::to_time_t(now);
    std::tm tm = *std::localtime(&time_t);

    std::ostringstream filename;
    filename << output_dir << "/xray_game_"
             << std::put_time(&tm, "%Y%m%d_%H%M%S") << ".log";
    log_path_ = filename.str();

    log_file_.open(log_path_);
    if (!log_file_.is_open()) {
        std::cerr << "[X-Ray Logger] Failed to open log file: " << log_path_ << std::endl;
        enabled_ = false;
        return;
    }

    // Write header
    log_file_ << std::string(80, '=') << "\n";
    log_file_ << "X-RAY GAME LOG - LINEAR STATE TRACE (C++ Engine)\n";

    std::ostringstream timestamp;
    timestamp << std::put_time(&tm, "%Y-%m-%d %H:%M:%S");
    log_file_ << "Started: " << timestamp.str() << "\n";
    log_file_ << std::string(80, '=') << "\n\n";

    std::cout << "[X-Ray Logger] Logging to: " << log_path_ << std::endl;
}

XRayLogger::~XRayLogger() {
    if (log_file_.is_open()) {
        log_file_.close();
    }
}

void XRayLogger::set_card_database(const CardDatabase* card_db) {
    card_db_ = card_db;
}

std::string XRayLogger::fmt_card(const CardInstance& card) const {
    std::string name = card.card_id;

    // Try to get card name from database
    if (card_db_) {
        const CardDef* def = card_db_->get_card(card.card_id);
        if (def) {
            name = def->name;
        }
    }

    // Get short instance ID (last 8 chars)
    std::string short_id = card.id;
    if (short_id.length() > 8) {
        short_id = short_id.substr(short_id.length() - 8);
    }

    return name + " (" + short_id + ")";
}

std::string XRayLogger::fmt_id(const std::string& id) const {
    std::string short_id = id;
    if (short_id.length() > 8) {
        short_id = short_id.substr(short_id.length() - 8);
    }
    return "(" + short_id + ")";
}

std::string XRayLogger::format_pokemon_line(const CardInstance& pokemon, const std::string& label) const {
    std::ostringstream line;

    // Card name and short ID
    line << label << ":  " << fmt_card(pokemon);

    // HP - get max HP from database
    int max_hp = 0;
    if (card_db_) {
        const CardDef* def = card_db_->get_card(pokemon.card_id);
        if (def) {
            max_hp = def->hp;
        }
    }
    int damage = pokemon.damage_counters * 10;
    int current_hp = std::max(0, max_hp - damage);

    if (max_hp > 0) {
        line << " | HP: " << current_hp << "/" << max_hp;
    } else {
        line << " | HP: ?/?";
    }

    // Energy
    line << " | Energy: [";
    for (size_t i = 0; i < pokemon.attached_energy.size(); i++) {
        if (i > 0) line << ", ";
        line << fmt_card(pokemon.attached_energy[i]);
    }
    line << "]";

    // Tools
    line << " | Tools: [";
    for (size_t i = 0; i < pokemon.attached_tools.size(); i++) {
        if (i > 0) line << ", ";
        line << fmt_card(pokemon.attached_tools[i]);
    }
    line << "]";

    return line.str();
}

std::string XRayLogger::action_type_str(ActionType type) {
    switch (type) {
        case ActionType::MULLIGAN_DRAW: return "MULLIGAN_DRAW";
        case ActionType::REVEAL_HAND_MULLIGAN: return "REVEAL_HAND_MULLIGAN";
        case ActionType::PLACE_ACTIVE: return "PLACE_ACTIVE";
        case ActionType::PLACE_BENCH: return "PLACE_BENCH";
        case ActionType::PLAY_BASIC: return "PLAY_BASIC";
        case ActionType::EVOLVE: return "EVOLVE";
        case ActionType::ATTACH_ENERGY: return "ATTACH_ENERGY";
        case ActionType::PLAY_ITEM: return "PLAY_ITEM";
        case ActionType::PLAY_SUPPORTER: return "PLAY_SUPPORTER";
        case ActionType::PLAY_STADIUM: return "PLAY_STADIUM";
        case ActionType::ATTACH_TOOL: return "ATTACH_TOOL";
        case ActionType::USE_ABILITY: return "USE_ABILITY";
        case ActionType::RETREAT: return "RETREAT";
        case ActionType::ATTACK: return "ATTACK";
        case ActionType::END_TURN: return "END_TURN";
        case ActionType::TAKE_PRIZE: return "TAKE_PRIZE";
        case ActionType::PROMOTE_ACTIVE: return "PROMOTE_ACTIVE";
        case ActionType::DISCARD_BENCH: return "DISCARD_BENCH";
        case ActionType::SELECT_CARD: return "SELECT_CARD";
        case ActionType::CONFIRM_SELECTION: return "CONFIRM_SELECTION";
        case ActionType::CANCEL_ACTION: return "CANCEL_ACTION";
        case ActionType::COIN_FLIP: return "COIN_FLIP";
        case ActionType::SHUFFLE: return "SHUFFLE";
        default: return "UNKNOWN";
    }
}

std::string XRayLogger::format_action_description(const Action& action) const {
    std::ostringstream desc;

    desc << action_type_str(action.action_type);

    // Add card info if present
    if (action.card_id.has_value()) {
        desc << " - " << *action.card_id;

        // Try to get card name
        if (card_db_) {
            const CardDef* def = card_db_->get_card(*action.card_id);
            if (def) {
                desc << " (" << def->name << ")";
            }
        }
    }

    // Add target info if present
    if (action.target_id.has_value()) {
        desc << " -> " << *action.target_id;

        if (card_db_) {
            const CardDef* def = card_db_->get_card(*action.target_id);
            if (def) {
                desc << " (" << def->name << ")";
            }
        }
    }

    // Add attack name if present
    if (action.attack_name.has_value()) {
        desc << " [" << *action.attack_name << "]";
    }

    // Add ability name if present
    if (action.ability_name.has_value()) {
        desc << " {" << *action.ability_name << "}";
    }

    return desc.str();
}

void XRayLogger::log_action(int turn_count, PlayerID player_id, const Action& action) {
    if (!enabled_ || !log_file_.is_open()) return;

    std::string action_desc = format_action_description(action);

    log_file_ << std::string(80, '#') << "\n";
    log_file_ << "[TURN " << turn_count << " | PLAYER: P" << static_cast<int>(player_id)
              << "] ACTION: " << action_desc << "\n";
    log_file_ << std::string(80, '#') << "\n\n";

    log_file_.flush();
}

void XRayLogger::log_state(const GameState& state) {
    if (!enabled_ || !log_file_.is_open()) return;

    log_file_ << std::string(80, '=') << "\n";

    // Player 0
    const auto& p0 = state.players[0];
    log_file_ << "[PLAYER 0]\n";

    // Active
    if (p0.board.active_spot.has_value()) {
        log_file_ << format_pokemon_line(*p0.board.active_spot, "ACTIVE") << "\n";
    } else {
        log_file_ << "ACTIVE:  (Empty)\n";
    }

    // Bench
    for (size_t i = 0; i < p0.board.bench.size(); i++) {
        std::string label = "BENCH " + std::to_string(i + 1);
        log_file_ << format_pokemon_line(p0.board.bench[i], label) << "\n";
    }

    // Hand
    log_file_ << "HAND (" << p0.hand.cards.size() << "): [";
    for (size_t i = 0; i < p0.hand.cards.size(); i++) {
        if (i > 0) log_file_ << ", ";
        log_file_ << fmt_card(p0.hand.cards[i]);
    }
    log_file_ << "]\n";

    // Prizes
    log_file_ << "PRIZES (" << p0.prizes.cards.size() << "): [";
    for (size_t i = 0; i < p0.prizes.cards.size(); i++) {
        if (i > 0) log_file_ << ", ";
        log_file_ << fmt_card(p0.prizes.cards[i]);
    }
    log_file_ << "]\n";

    // Deck
    log_file_ << "DECK (" << p0.deck.cards.size() << "): [";
    for (size_t i = 0; i < p0.deck.cards.size(); i++) {
        if (i > 0) log_file_ << ", ";
        log_file_ << fmt_card(p0.deck.cards[i]);
    }
    log_file_ << "]\n";

    // Discard
    log_file_ << "DISCARD (" << p0.discard.cards.size() << "): [";
    for (size_t i = 0; i < p0.discard.cards.size(); i++) {
        if (i > 0) log_file_ << ", ";
        log_file_ << fmt_card(p0.discard.cards[i]);
    }
    log_file_ << "]\n";

    // Player 1
    const auto& p1 = state.players[1];
    log_file_ << "\n[PLAYER 1]\n";

    // Active
    if (p1.board.active_spot.has_value()) {
        log_file_ << format_pokemon_line(*p1.board.active_spot, "ACTIVE") << "\n";
    } else {
        log_file_ << "ACTIVE:  (Empty)\n";
    }

    // Bench
    for (size_t i = 0; i < p1.board.bench.size(); i++) {
        std::string label = "BENCH " + std::to_string(i + 1);
        log_file_ << format_pokemon_line(p1.board.bench[i], label) << "\n";
    }

    // Hand
    log_file_ << "HAND (" << p1.hand.cards.size() << "): [";
    for (size_t i = 0; i < p1.hand.cards.size(); i++) {
        if (i > 0) log_file_ << ", ";
        log_file_ << fmt_card(p1.hand.cards[i]);
    }
    log_file_ << "]\n";

    // Prizes
    log_file_ << "PRIZES (" << p1.prizes.cards.size() << "): [";
    for (size_t i = 0; i < p1.prizes.cards.size(); i++) {
        if (i > 0) log_file_ << ", ";
        log_file_ << fmt_card(p1.prizes.cards[i]);
    }
    log_file_ << "]\n";

    // Deck
    log_file_ << "DECK (" << p1.deck.cards.size() << "): [";
    for (size_t i = 0; i < p1.deck.cards.size(); i++) {
        if (i > 0) log_file_ << ", ";
        log_file_ << fmt_card(p1.deck.cards[i]);
    }
    log_file_ << "]\n";

    // Discard
    log_file_ << "DISCARD (" << p1.discard.cards.size() << "): [";
    for (size_t i = 0; i < p1.discard.cards.size(); i++) {
        if (i > 0) log_file_ << ", ";
        log_file_ << fmt_card(p1.discard.cards[i]);
    }
    log_file_ << "]\n";

    // Global
    log_file_ << "\n[GLOBAL]\n";
    if (state.stadium.has_value()) {
        log_file_ << "Stadium: " << fmt_card(*state.stadium) << "\n";
    } else {
        log_file_ << "Stadium: (None)\n";
    }

    log_file_ << "Phase: " << to_string(state.current_phase)
              << " | Turn: " << state.turn_count
              << " | Active Player: P" << static_cast<int>(state.active_player_index) << "\n";

    // Resolution stack
    if (!state.resolution_stack.empty()) {
        log_file_ << "Resolution Stack: " << state.resolution_stack.size() << " step(s) pending\n";
    }

    log_file_ << std::string(80, '=') << "\n\n";

    log_file_.flush();
}

void XRayLogger::log_game_end(std::optional<PlayerID> winner, const std::string& reason) {
    if (!enabled_ || !log_file_.is_open()) return;

    auto now = std::chrono::system_clock::now();
    auto time_t = std::chrono::system_clock::to_time_t(now);
    std::tm tm = *std::localtime(&time_t);

    log_file_ << "\n" << std::string(80, '=') << "\n";
    log_file_ << "GAME END\n";
    log_file_ << std::string(80, '=') << "\n";

    if (winner.has_value()) {
        log_file_ << "Winner: Player " << static_cast<int>(*winner) << "\n";
    } else {
        log_file_ << "Result: Draw\n";
    }

    log_file_ << "Reason: " << reason << "\n";

    std::ostringstream timestamp;
    timestamp << std::put_time(&tm, "%Y-%m-%d %H:%M:%S");
    log_file_ << "Ended: " << timestamp.str() << "\n";

    log_file_ << std::string(80, '=') << "\n";

    log_file_.flush();
}

} // namespace pokemon

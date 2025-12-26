/**
 * Pokemon TCG Engine - Interactive Test Console
 *
 * Simple REPL for manual testing of game mechanics.
 * Implements proper setup: coin flip, mulligan handling, prize setup.
 */

#include <iostream>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <algorithm>
#include <regex>
#include <unordered_map>
#include <unordered_set>
#include <random>
#include <chrono>
#include <memory>

#include <nlohmann/json.hpp>
#include "pokemon_engine.hpp"
#include "cards/trainer_registry.hpp"
#include "cards/effect_builders.hpp"
#include "xray_logger.hpp"

using namespace pokemon;
using namespace pokemon::trainers;
using namespace pokemon::effects;

// ============================================================================
// SET CODE MAPPING (PTCGL -> Internal)
// ============================================================================

const std::unordered_map<std::string, std::string> SET_CODE_MAP = {
    // Scarlet & Violet Series
    {"SVI", "sv1"},        // Scarlet & Violet Base
    {"PAL", "sv2"},        // Paldea Evolved
    {"OBF", "sv3"},        // Obsidian Flames
    {"MEW", "sv3pt5"},     // 151
    {"PAR", "sv4"},        // Paradox Rift
    {"PAF", "sv4pt5"},     // Paldean Fates
    {"TEF", "sv5"},        // Temporal Forces
    {"TWM", "sv6"},        // Twilight Masquerade
    {"SFA", "sv6pt5"},     // Shrouded Fable
    {"SCR", "sv7"},        // Stellar Crown
    {"SSP", "sv8"},        // Surging Sparks

    // Special sets
    {"MEX", "me1"},
    {"DRI", "sv10"},
    {"MEG", "me1"},
    {"PRE", "sv8pt5"},
    {"MEE", "sve"},
    {"PFL", "me2"},
    {"JTG", "sv9"},
    {"SVE", "sve"},
};

std::string normalize_set_code(const std::string& ptcgl_code) {
    auto it = SET_CODE_MAP.find(ptcgl_code);
    if (it != SET_CODE_MAP.end()) {
        return it->second;
    }
    // Fallback: lowercase
    std::string lower = ptcgl_code;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
    return lower;
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

std::vector<std::string> split(const std::string& s, char delim = ' ') {
    std::vector<std::string> tokens;
    std::istringstream iss(s);
    std::string token;
    while (std::getline(iss, token, delim)) {
        if (!token.empty()) {
            tokens.push_back(token);
        }
    }
    return tokens;
}

std::string action_type_to_string(ActionType type) {
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
        case ActionType::CONFIRM_SELECTION: return "CONFIRM";
        case ActionType::CANCEL_ACTION: return "CANCEL";
        case ActionType::COIN_FLIP: return "COIN_FLIP";
        case ActionType::SHUFFLE: return "SHUFFLE";
        default: return "UNKNOWN";
    }
}

std::string phase_to_string(GamePhase phase) {
    switch (phase) {
        case GamePhase::SETUP: return "SETUP";
        case GamePhase::MULLIGAN: return "MULLIGAN";
        case GamePhase::DRAW: return "DRAW";
        case GamePhase::MAIN: return "MAIN";
        case GamePhase::ATTACK: return "ATTACK";
        case GamePhase::CLEANUP: return "CLEANUP";
        case GamePhase::END: return "END";
        case GamePhase::SUDDEN_DEATH: return "SUDDEN_DEATH";
        default: return "UNKNOWN";
    }
}

// ============================================================================
// DECK PARSING
// ============================================================================

struct DeckCard {
    std::string card_id;      // e.g., "sv4pt5-7"
    std::string name;         // e.g., "Charmander"
    int count;
    bool is_pokemon = false;
    bool is_basic = false;
    bool is_energy = false;
    bool is_trainer = false;
};

// ============================================================================
// CARD DATABASE (loaded from standard_cards.json)
// ============================================================================

struct CardInfo {
    std::string id;
    std::string name;
    std::string supertype;           // "Pokemon", "Trainer", "Energy"
    std::vector<std::string> subtypes;  // "Basic", "Stage 1", "Stage 2", "Item", etc.
    std::string evolves_from;
    int hp = 0;
    std::vector<std::string> types;  // Energy types

    bool is_pokemon() const { return supertype == "Pokemon"; }
    bool is_trainer() const { return supertype == "Trainer"; }
    bool is_energy() const { return supertype == "Energy"; }

    bool is_basic_pokemon() const {
        if (!is_pokemon()) return false;
        // A Pokemon is Basic if it has no evolvesFrom field
        return evolves_from.empty();
    }

    bool has_subtype(const std::string& sub) const {
        return std::find(subtypes.begin(), subtypes.end(), sub) != subtypes.end();
    }
};

class ConsoleCardDatabase {
public:
    std::unordered_map<std::string, CardInfo> cards_by_id;   // "sv3-125" -> CardInfo
    std::unordered_map<std::string, std::vector<std::string>> cards_by_name;  // "Charmander" -> ["sv1-4", "sv4pt5-7", ...]
    bool loaded = false;

    bool load_from_json(const std::string& filepath) {
        std::ifstream file(filepath);
        if (!file.is_open()) {
            std::cerr << "Failed to open card database: " << filepath << std::endl;
            return false;
        }

        try {
            nlohmann::json j;
            file >> j;

            if (!j.contains("cards") || !j["cards"].is_array()) {
                std::cerr << "Invalid card database format" << std::endl;
                return false;
            }

            for (const auto& card_json : j["cards"]) {
                CardInfo info;
                info.id = card_json.value("id", "");
                info.name = card_json.value("name", "");
                info.supertype = card_json.value("supertype", "");
                info.evolves_from = card_json.value("evolvesFrom", "");

                if (card_json.contains("hp") && card_json["hp"].is_string()) {
                    try {
                        info.hp = std::stoi(card_json["hp"].get<std::string>());
                    } catch (...) {
                        info.hp = 0;
                    }
                }

                if (card_json.contains("subtypes") && card_json["subtypes"].is_array()) {
                    for (const auto& sub : card_json["subtypes"]) {
                        if (sub.is_string()) {
                            info.subtypes.push_back(sub.get<std::string>());
                        }
                    }
                }

                if (card_json.contains("types") && card_json["types"].is_array()) {
                    for (const auto& t : card_json["types"]) {
                        if (t.is_string()) {
                            info.types.push_back(t.get<std::string>());
                        }
                    }
                }

                if (!info.id.empty()) {
                    cards_by_id[info.id] = info;
                    cards_by_name[info.name].push_back(info.id);
                }
            }

            loaded = true;
            std::cout << "Card database loaded: " << cards_by_id.size() << " cards" << std::endl;
            return true;

        } catch (const std::exception& e) {
            std::cerr << "Error parsing card database: " << e.what() << std::endl;
            return false;
        }
    }

    const CardInfo* get_card(const std::string& card_id) const {
        auto it = cards_by_id.find(card_id);
        if (it != cards_by_id.end()) {
            return &it->second;
        }
        return nullptr;
    }

    bool is_basic_pokemon(const std::string& card_id) const {
        const CardInfo* info = get_card(card_id);
        return info && info->is_basic_pokemon();
    }
};

// Global card database instance
ConsoleCardDatabase g_card_db;

std::vector<DeckCard> parse_deck_file(const std::string& filepath) {
    std::vector<DeckCard> cards;

    std::ifstream file(filepath);
    if (!file.is_open()) {
        std::cerr << "Failed to open deck file: " << filepath << std::endl;
        return cards;
    }

    std::string line;
    // Match: "2 Charmander PAF 7" -> count=2, name=Charmander, set=PAF, num=7
    std::regex ptcgl_regex(R"((\d+)\s+(.+?)\s+([A-Z]+)\s+(\d+)$)");

    enum class Section { UNKNOWN, POKEMON, TRAINER, ENERGY };
    Section current_section = Section::UNKNOWN;

    while (std::getline(file, line)) {
        // Trim
        line.erase(0, line.find_first_not_of(" \t\r\n"));
        if (line.empty()) continue;
        size_t end = line.find_last_not_of(" \t\r\n");
        if (end != std::string::npos) {
            line.erase(end + 1);
        }

        if (line.empty() || line[0] == '#') continue;

        // Check for section headers
        if (line.find("Pok") != std::string::npos && line.find(':') != std::string::npos) {
            current_section = Section::POKEMON;
            continue;
        }
        if (line.find("Trainer") != std::string::npos && line.find(':') != std::string::npos) {
            current_section = Section::TRAINER;
            continue;
        }
        if (line.find("Energy") != std::string::npos && line.find(':') != std::string::npos) {
            current_section = Section::ENERGY;
            continue;
        }

        std::smatch match;
        if (std::regex_search(line, match, ptcgl_regex)) {
            int count = std::stoi(match[1].str());
            std::string name = match[2].str();
            std::string set_code = match[3].str();
            std::string number = match[4].str();

            std::string internal_code = normalize_set_code(set_code);
            std::string card_id = internal_code + "-" + number;

            DeckCard dc;
            dc.card_id = card_id;
            dc.name = name;
            dc.count = count;
            dc.is_pokemon = (current_section == Section::POKEMON);
            dc.is_trainer = (current_section == Section::TRAINER);
            dc.is_energy = (current_section == Section::ENERGY);

            // Use card database to determine if basic pokemon
            // A Pokemon is basic if it has no evolvesFrom field
            if (dc.is_pokemon && g_card_db.loaded) {
                dc.is_basic = g_card_db.is_basic_pokemon(card_id);
            } else {
                // Fallback: assume all Pokemon section cards are basic if DB not loaded
                dc.is_basic = dc.is_pokemon;
            }

            cards.push_back(dc);
        }
    }

    return cards;
}

// ============================================================================
// PRINT HELP
// ============================================================================

void print_help() {
    std::cout << R"(
=== Pokemon TCG C++ Test Console ===

Commands:
  help                    - Show this help
  quit / exit             - Exit console

Game Setup:
  load [deck_path]        - Load deck for both players (default: charizard_ex.txt)
  setup                   - Initialize game with loaded decks (full setup flow)
  show                    - Show current game state

Legal Actions:
  actions / a             - Show all legal actions (numbered)
  do <number>             - Execute action by number
  do <number> <number>... - Execute multiple actions sequentially

Trainer Testing:
  trainers                - List implemented trainers
  play <card_id>          - Play a trainer card directly

Resolution Stack:
  stack                   - Show resolution stack

Examples:
  load                    # Load charizard_ex.txt
  setup                   # Initialize game with coin flip, mulligans, etc.
  actions                 # See legal actions
  do 0                    # Execute action #0
)" << std::endl;
}

// ============================================================================
// GAME STATE DISPLAY
// ============================================================================

void show_zone(const std::string& name, const Zone& zone, const std::unordered_map<std::string, std::string>& name_map, int max_show = 10) {
    std::cout << "  " << name << " (" << zone.cards.size() << "):" << std::endl;
    for (size_t i = 0; i < zone.cards.size() && i < static_cast<size_t>(max_show); i++) {
        const auto& card = zone.cards[i];
        std::cout << "    [" << i << "] " << card.card_id;
        auto it = name_map.find(card.card_id);
        if (it != name_map.end()) {
            std::cout << " (" << it->second << ")";
        }
        std::cout << std::endl;
    }
    if (zone.cards.size() > static_cast<size_t>(max_show)) {
        std::cout << "    ... +" << (zone.cards.size() - max_show) << " more" << std::endl;
    }
}

void show_pokemon_detailed(const std::string& label, const CardInstance& pokemon,
                           const std::unordered_map<std::string, std::string>& name_map,
                           int hp = 0) {
    std::cout << "  " << label << ": " << pokemon.card_id;
    auto it = name_map.find(pokemon.card_id);
    if (it != name_map.end()) {
        std::cout << " (" << it->second << ")";
    }
    std::cout << std::endl;

    // HP and damage
    int damage = pokemon.damage_counters * 10;
    if (hp > 0) {
        std::cout << "    HP: " << (hp - damage) << "/" << hp;
    } else {
        std::cout << "    Damage: " << damage;
    }

    // Energy
    if (!pokemon.attached_energy.empty()) {
        std::cout << " | Energy: ";
        for (const auto& e : pokemon.attached_energy) {
            std::cout << e.card_id << " ";
        }
    }

    // Tools
    if (!pokemon.attached_tools.empty()) {
        std::cout << " | Tools: ";
        for (const auto& t : pokemon.attached_tools) {
            std::cout << t.card_id << " ";
        }
    }

    std::cout << std::endl;
}

// Helper to get HP display string (current/max)
std::string get_hp_display(const CardInstance& pokemon) {
    // Get max HP from card database
    const CardInfo* info = g_card_db.get_card(pokemon.card_id);
    int max_hp = info ? info->hp : 0;
    int damage = pokemon.damage_counters * 10;
    int current_hp = std::max(0, max_hp - damage);

    if (max_hp > 0) {
        return std::to_string(current_hp) + "/" + std::to_string(max_hp);
    }
    return "?/?";
}

void show_state_for_player(const GameState& state, int player_id,
                           const std::unordered_map<std::string, std::string>& name_map) {
    const auto& player = state.players[player_id];
    const auto& opponent = state.players[1 - player_id];

    std::cout << "\n";
    std::cout << "+================================================================+" << std::endl;
    std::cout << "|  TURN " << state.turn_count << " - P" << static_cast<int>(state.active_player_index) << "'s turn";
    std::cout << " | Phase: " << phase_to_string(state.current_phase);
    std::cout << std::string(20 - phase_to_string(state.current_phase).length(), ' ') << "|" << std::endl;
    std::cout << "+================================================================+" << std::endl;

    // Opponent's side (top)
    std::cout << "|  OPPONENT (P" << (1 - player_id) << ")";
    std::cout << " | Deck: " << opponent.deck.cards.size();
    std::cout << " | Hand: " << opponent.hand.cards.size();
    std::cout << " | Prizes: " << opponent.prizes.cards.size() << std::endl;

    if (opponent.board.active_spot.has_value()) {
        const auto& active = *opponent.board.active_spot;
        auto it = name_map.find(active.card_id);
        std::string name = (it != name_map.end()) ? it->second : active.card_id;
        std::cout << "|  Active: " << name << " [HP:" << get_hp_display(active) << "]";
        if (!active.attached_energy.empty()) {
            std::cout << " E:" << active.attached_energy.size();
        }
        std::cout << std::endl;
    }

    if (!opponent.board.bench.empty()) {
        std::cout << "|  Bench: ";
        for (size_t i = 0; i < opponent.board.bench.size(); i++) {
            if (i > 0) std::cout << ", ";
            const auto& b = opponent.board.bench[i];
            auto it = name_map.find(b.card_id);
            if (it != name_map.end()) {
                std::cout << it->second;
            } else {
                std::cout << b.card_id;
            }
        }
        std::cout << std::endl;
    }

    std::cout << "+----------------------------------------------------------------+" << std::endl;

    // Player's side (bottom)
    std::cout << "|  YOU (P" << player_id << ")";
    std::cout << " | Deck: " << player.deck.cards.size();
    std::cout << " | Prizes: " << player.prizes.cards.size() << std::endl;

    // Player's active
    if (player.board.active_spot.has_value()) {
        const auto& active = *player.board.active_spot;
        auto it = name_map.find(active.card_id);
        std::string name = (it != name_map.end()) ? it->second : active.card_id;
        std::cout << "|  Active: " << name << " [HP:" << get_hp_display(active) << "]";
        if (!active.attached_energy.empty()) {
            std::cout << " Energy:";
            for (const auto& e : active.attached_energy) {
                auto eit = name_map.find(e.card_id);
                std::cout << " " << ((eit != name_map.end()) ? eit->second : e.card_id);
            }
        }
        std::cout << std::endl;
    } else {
        std::cout << "|  Active: (none)" << std::endl;
    }

    // Player's bench
    if (!player.board.bench.empty()) {
        std::cout << "|  Bench (" << player.board.bench.size() << "/5):" << std::endl;
        for (size_t i = 0; i < player.board.bench.size(); i++) {
            const auto& b = player.board.bench[i];
            auto it = name_map.find(b.card_id);
            std::string name = (it != name_map.end()) ? it->second : b.card_id;
            std::cout << "|    [" << i << "] " << name << " [HP:" << get_hp_display(b) << "]";
            if (!b.attached_energy.empty()) {
                std::cout << " E:" << b.attached_energy.size();
            }
            std::cout << std::endl;
        }
    } else {
        std::cout << "|  Bench: (empty)" << std::endl;
    }

    std::cout << "+----------------------------------------------------------------+" << std::endl;

    // Player's hand
    std::cout << "|  HAND (" << player.hand.cards.size() << " cards):" << std::endl;
    for (size_t i = 0; i < player.hand.cards.size(); i++) {
        const auto& card = player.hand.cards[i];
        auto it = name_map.find(card.card_id);
        std::string name = (it != name_map.end()) ? it->second : card.card_id;
        std::cout << "|    [" << i << "] " << name << std::endl;
    }

    std::cout << "+================================================================+" << std::endl;

    // Flags
    if (player.supporter_played_this_turn) {
        std::cout << "  [!] Supporter already played this turn" << std::endl;
    }
    if (player.energy_attached_this_turn) {
        std::cout << "  [!] Energy already attached this turn" << std::endl;
    }

    // Resolution stack
    if (!state.resolution_stack.empty()) {
        std::cout << "\n  [Resolution pending: " << state.resolution_stack.size() << " step(s)]" << std::endl;
    }
}

// Helper to resolve instance ID to card name
std::string resolve_card_name(const std::string& instance_id,
                              const GameState& state,
                              const std::unordered_map<std::string, std::string>& name_map) {
    // First try direct lookup (for functional IDs)
    auto it = name_map.find(instance_id);
    if (it != name_map.end()) {
        return it->second;
    }

    // Try to find the card instance in game state and get its functional card_id
    for (int p = 0; p < 2; p++) {
        const auto* card = state.players[p].find_card_anywhere(instance_id);
        if (card) {
            auto it2 = name_map.find(card->card_id);
            if (it2 != name_map.end()) {
                return it2->second;
            }
            return card->card_id;  // Return functional ID if no name found
        }
    }

    return instance_id;  // Fallback to original ID
}

void show_actions(const std::vector<Action>& actions,
                  const GameState& state,
                  const std::unordered_map<std::string, std::string>& name_map) {
    std::cout << "\n+-------------------------------------------------------------+" << std::endl;
    std::cout << "|  LEGAL ACTIONS (" << actions.size() << "):" << std::endl;
    std::cout << "+-------------------------------------------------------------+" << std::endl;

    for (size_t i = 0; i < actions.size(); i++) {
        const auto& a = actions[i];
        std::cout << "   [" << i << "] " << action_type_to_string(a.action_type);

        if (a.card_id.has_value()) {
            std::cout << " - " << resolve_card_name(*a.card_id, state, name_map);
        }
        if (a.target_id.has_value()) {
            std::cout << " -> " << resolve_card_name(*a.target_id, state, name_map);
        }
        if (a.attack_name.has_value()) {
            std::cout << " [" << *a.attack_name << "]";
        }
        if (a.ability_name.has_value()) {
            std::cout << " {" << *a.ability_name << "}";
        }

        std::cout << std::endl;
    }
    std::cout << "+-------------------------------------------------------------+" << std::endl;
    std::cout << "\nEnter action number (e.g., 'do 0') or 'help' for commands." << std::endl;
}

void show_stack(const GameState& state) {
    std::cout << "\n=== Resolution Stack ===" << std::endl;
    if (state.resolution_stack.empty()) {
        std::cout << "(empty)" << std::endl;
        return;
    }

    for (size_t i = 0; i < state.resolution_stack.size(); i++) {
        std::cout << "[" << i << "] ";
        std::visit([](const auto& step) {
            using T = std::decay_t<decltype(step)>;
            if constexpr (std::is_same_v<T, SearchDeckStep>) {
                std::cout << "SearchDeck: " << step.source_card_name
                          << " | count=" << step.count
                          << " | min=" << step.min_count;
                std::cout << " | filter: ";
                for (const auto& [k, v] : step.filter_criteria) {
                    std::cout << k << "=" << v << " ";
                }
            } else if constexpr (std::is_same_v<T, SelectFromZoneStep>) {
                std::cout << "SelectFromZone: " << step.source_card_name
                          << " | zone=" << static_cast<int>(step.zone)
                          << " | count=" << step.count;
            } else if constexpr (std::is_same_v<T, AttachToTargetStep>) {
                std::cout << "AttachToTarget: " << step.card_to_attach_id;
            } else if constexpr (std::is_same_v<T, EvolveTargetStep>) {
                std::cout << "EvolveTarget";
            }
        }, state.resolution_stack[i]);
        std::cout << std::endl;
    }
    std::cout << std::endl;
}

void show_trainers() {
    std::cout << "\n=== Implemented Trainers ===" << std::endl;
    auto info = get_trainer_info();
    for (const auto& t : info) {
        std::cout << "  " << (t.implemented ? "[x]" : "[ ]") << " "
                  << t.card_id << " - " << t.name
                  << " (" << t.category << ")" << std::endl;
    }
    std::cout << std::endl;
}

// ============================================================================
// SETUP PHASES
// ============================================================================

enum class SetupPhase {
    COIN_FLIP,                  // Flip coin to decide who chooses first/second
    CHOOSE_FIRST_SECOND,        // Winner chooses to go first or second
    DEAL_HANDS,                 // Deal 7 cards to each player
    CHECK_MULLIGANS,            // Check if any player needs mulligan
    PLACE_BASICS,               // Place basics to active/bench
    SET_PRIZES,                 // Set 6 prize cards
    MULLIGAN_DRAWS,             // Handle extra draws from mulligans
    COMPLETE                    // Setup done, start game
};

// ============================================================================
// CONSOLE CLASS
// ============================================================================

class Console {
public:
    GameState state;
    PokemonEngine engine;
    std::vector<DeckCard> deck_cards;
    std::vector<Action> current_actions;
    std::string deck_path = "c:/Users/alexl/Desktop/Projects/pokemon-ai/src/decks/charizard_ex.txt";

    // Card name map (card_id -> name)
    std::unordered_map<std::string, std::string> card_name_map;
    // Track which card_ids are basic pokemon
    std::unordered_set<std::string> basic_pokemon_ids;

    // RNG
    std::mt19937 rng;

    // X-Ray logger for debugging
    std::unique_ptr<XRayLogger> xray_logger;

    // Setup state
    SetupPhase setup_phase = SetupPhase::COIN_FLIP;
    bool p0_assigned_heads = false;  // Which player is assigned heads
    bool coin_result_heads = false;  // Result of coin flip
    int p0_mulligans = 0;
    int p1_mulligans = 0;
    bool p0_has_basics = false;
    bool p1_has_basics = false;
    bool p0_setup_complete = false;
    bool p1_setup_complete = false;
    bool game_started = false;

    Console() {
        // Register trainers to the ENGINE's logic registry (not a separate one!)
        register_all_trainers(engine.get_logic_registry());
        // Seed RNG with current time
        auto seed = std::chrono::high_resolution_clock::now().time_since_epoch().count();
        rng.seed(static_cast<unsigned int>(seed));

        // Load card database from standard_cards.json
        std::string db_path = "c:/Users/alexl/Desktop/Projects/pokemon-ai/data/standard_cards.json";

        // Load into console's database (for basic Pokemon detection during deck parsing)
        if (!g_card_db.load_from_json(db_path)) {
            std::cerr << "Warning: Failed to load console card database." << std::endl;
        }

        // Load into engine's database (for legal action generation)
        if (!engine.load_card_database(db_path)) {
            std::cerr << "Warning: Failed to load engine card database. Trainer cards won't work." << std::endl;
        } else {
            std::cout << "Engine card database loaded: " << engine.get_card_database().card_count() << " cards" << std::endl;
        }

        // Initialize X-Ray logger with card database for name resolution
        // Use absolute path so logs go to the right place regardless of working directory
        std::string xray_dir = "c:/Users/alexl/Desktop/Projects/pokemon-ai/cpp_engine/xrays";
        xray_logger = std::make_unique<XRayLogger>(&engine.get_card_database(), xray_dir);
    }

    bool flip_coin() {
        std::uniform_int_distribution<int> dist(0, 1);
        return dist(rng) == 1;  // true = heads
    }

    void cmd_load(const std::vector<std::string>& args) {
        if (args.size() > 1) {
            deck_path = args[1];
        }

        deck_cards = parse_deck_file(deck_path);

        if (deck_cards.empty()) {
            std::cout << "Failed to load deck from: " << deck_path << std::endl;
            return;
        }

        // Build card name map and basic pokemon set
        // Prefer names from card database if available, fall back to deck file names
        card_name_map.clear();
        basic_pokemon_ids.clear();
        int total = 0;
        int basic_count = 0;
        for (const auto& dc : deck_cards) {
            // Try to get name from card database first (more reliable)
            const CardInfo* info = g_card_db.get_card(dc.card_id);
            if (info) {
                card_name_map[dc.card_id] = info->name;
            } else {
                card_name_map[dc.card_id] = dc.name;
            }

            if (dc.is_basic) {
                basic_pokemon_ids.insert(dc.card_id);
                basic_count += dc.count;
            }
            total += dc.count;
        }

        std::cout << "Loaded " << total << " cards (" << deck_cards.size() << " unique, " << basic_count << " basic pokemon)" << std::endl;

        // Debug: List basic Pokemon found
        if (basic_count > 0) {
            std::cout << "Basic Pokemon in deck: ";
            bool first = true;
            for (const auto& id : basic_pokemon_ids) {
                if (!first) std::cout << ", ";
                auto it = card_name_map.find(id);
                if (it != card_name_map.end()) {
                    std::cout << it->second;
                } else {
                    std::cout << id;
                }
                first = false;
            }
            std::cout << std::endl;
        }
    }

    void create_deck_for_player(int player_id) {
        int card_num = 0;
        std::string prefix = "p" + std::to_string(player_id) + "_";

        for (const auto& dc : deck_cards) {
            for (int i = 0; i < dc.count; i++) {
                CardInstance card;
                card.id = prefix + "card_" + std::to_string(card_num++);
                card.card_id = dc.card_id;
                card.owner_id = player_id;
                state.players[player_id].deck.cards.push_back(card);

                // Track functional IDs for knowledge layer
                state.players[player_id].functional_id_map[card.id] = dc.card_id;
            }
            // Track initial deck counts
            state.players[player_id].initial_deck_counts[dc.card_id] += dc.count;
        }
    }

    void shuffle_deck(int player_id) {
        std::shuffle(
            state.players[player_id].deck.cards.begin(),
            state.players[player_id].deck.cards.end(),
            rng
        );
    }

    void draw_cards(int player_id, int count) {
        auto& player = state.players[player_id];
        for (int i = 0; i < count && !player.deck.cards.empty(); i++) {
            player.hand.cards.push_back(std::move(player.deck.cards.back()));
            player.deck.cards.pop_back();
        }
    }

    bool has_basic_in_hand(int player_id) {
        const auto& hand = state.players[player_id].hand;
        for (const auto& card : hand.cards) {
            if (basic_pokemon_ids.count(card.card_id) > 0) {
                return true;
            }
        }
        return false;
    }

    void place_all_basics(int player_id) {
        auto& player = state.players[player_id];
        std::vector<CardInstance> non_basics;

        for (auto& card : player.hand.cards) {
            bool is_basic = basic_pokemon_ids.count(card.card_id) > 0;
            if (is_basic) {
                // Get card name for display
                std::string display_name = card.card_id;
                auto it = card_name_map.find(card.card_id);
                if (it != card_name_map.end()) {
                    display_name = it->second;
                }

                // First basic goes to active, rest to bench (up to 5)
                if (!player.board.active_spot.has_value()) {
                    player.board.active_spot = std::move(card);
                    std::cout << "  P" << player_id << " placed " << display_name << " as Active" << std::endl;
                } else if (player.board.bench.size() < 5) {
                    std::cout << "  P" << player_id << " placed " << display_name << " on Bench" << std::endl;
                    player.board.bench.push_back(std::move(card));
                } else {
                    // Bench full, keep in hand
                    non_basics.push_back(std::move(card));
                }
            } else {
                non_basics.push_back(std::move(card));
            }
        }

        player.hand.cards = std::move(non_basics);
    }

    void set_prizes(int player_id) {
        auto& player = state.players[player_id];
        for (int i = 0; i < 6 && !player.deck.cards.empty(); i++) {
            player.prizes.cards.push_back(std::move(player.deck.cards.back()));
            player.deck.cards.pop_back();
        }
        std::cout << "  P" << player_id << " set " << player.prizes.cards.size() << " prize cards" << std::endl;
    }

    void return_hand_to_deck(int player_id) {
        auto& player = state.players[player_id];
        while (!player.hand.cards.empty()) {
            player.deck.cards.push_back(std::move(player.hand.cards.back()));
            player.hand.cards.pop_back();
        }
    }

    void cmd_setup() {
        if (deck_cards.empty()) {
            std::cout << "No deck loaded. Use 'load' first." << std::endl;
            return;
        }

        // Reset state
        state = GameState();
        state.current_phase = GamePhase::SETUP;
        p0_mulligans = 0;
        p1_mulligans = 0;
        p0_has_basics = false;
        p1_has_basics = false;
        p0_setup_complete = false;
        p1_setup_complete = false;

        std::cout << "\n========== GAME SETUP ==========" << std::endl;

        // Step 1: Create decks for both players
        std::cout << "\n[1] Creating decks..." << std::endl;
        create_deck_for_player(0);
        create_deck_for_player(1);
        std::cout << "  P0 deck: " << state.players[0].deck.cards.size() << " cards" << std::endl;
        std::cout << "  P1 deck: " << state.players[1].deck.cards.size() << " cards" << std::endl;

        // Step 2: Coin flip to decide who chooses
        std::cout << "\n[2] Coin flip..." << std::endl;

        // Randomly assign heads/tails to players
        p0_assigned_heads = flip_coin();
        std::cout << "  P0 is assigned: " << (p0_assigned_heads ? "HEADS" : "TAILS") << std::endl;
        std::cout << "  P1 is assigned: " << (p0_assigned_heads ? "TAILS" : "HEADS") << std::endl;

        // Flip the coin
        coin_result_heads = flip_coin();
        std::cout << "  Coin flip result: " << (coin_result_heads ? "HEADS" : "TAILS") << std::endl;

        // Determine winner
        bool p0_wins = (p0_assigned_heads == coin_result_heads);
        int winner = p0_wins ? 0 : 1;
        std::cout << "  P" << winner << " wins the coin flip!" << std::endl;

        // For simplicity, winner always chooses to go first
        // In a full implementation, this would be a legal action
        state.starting_player_id = winner;
        state.active_player_index = winner;
        std::cout << "  P" << winner << " chooses to go FIRST" << std::endl;

        // Step 3: Shuffle decks and deal initial hands
        std::cout << "\n[3] Shuffling decks and dealing hands..." << std::endl;
        shuffle_deck(0);
        shuffle_deck(1);
        draw_cards(0, 7);
        draw_cards(1, 7);
        std::cout << "  P0 drew 7 cards" << std::endl;
        std::cout << "  P1 drew 7 cards" << std::endl;

        // Step 4: Check for basics and handle mulligans
        std::cout << "\n[4] Checking for Basic Pokemon..." << std::endl;

        // Loop until both players have basics
        while (true) {
            p0_has_basics = has_basic_in_hand(0);
            p1_has_basics = has_basic_in_hand(1);

            std::cout << "  P0 has basics: " << (p0_has_basics ? "YES" : "NO") << std::endl;
            std::cout << "  P1 has basics: " << (p1_has_basics ? "YES" : "NO") << std::endl;

            if (p0_has_basics && p1_has_basics) {
                break;  // Both have basics, proceed
            }

            // Handle mulligans
            if (!p0_has_basics) {
                p0_mulligans++;
                std::cout << "  P0 mulligans (count: " << p0_mulligans << ")" << std::endl;
                return_hand_to_deck(0);
                shuffle_deck(0);
                draw_cards(0, 7);
            }

            if (!p1_has_basics) {
                p1_mulligans++;
                std::cout << "  P1 mulligans (count: " << p1_mulligans << ")" << std::endl;
                return_hand_to_deck(1);
                shuffle_deck(1);
                draw_cards(1, 7);
            }
        }

        // Step 5: Place all basics
        std::cout << "\n[5] Placing Basic Pokemon..." << std::endl;
        place_all_basics(0);
        place_all_basics(1);

        // Step 6: Set prize cards
        std::cout << "\n[6] Setting prize cards..." << std::endl;
        set_prizes(0);
        set_prizes(1);

        // Step 7: Handle mulligan draws
        // The player who mulliganed fewer times gets extra draws
        int mulligan_diff = std::abs(p0_mulligans - p1_mulligans);
        if (mulligan_diff > 0) {
            std::cout << "\n[7] Mulligan draws..." << std::endl;
            std::cout << "  P0 mulligans: " << p0_mulligans << ", P1 mulligans: " << p1_mulligans << std::endl;

            if (p0_mulligans < p1_mulligans) {
                std::cout << "  P0 draws " << mulligan_diff << " extra card(s)" << std::endl;
                draw_cards(0, mulligan_diff);
            } else {
                std::cout << "  P1 draws " << mulligan_diff << " extra card(s)" << std::endl;
                draw_cards(1, mulligan_diff);
            }
        } else {
            std::cout << "\n[7] No mulligan draws (equal mulligans: " << p0_mulligans << ")" << std::endl;
        }

        // Step 8: Start the game - first player draws a card
        std::cout << "\n[8] Game starting!" << std::endl;
        state.current_phase = GamePhase::MAIN;
        state.turn_count = 1;
        game_started = true;

        // First player draws a card at start of turn
        draw_cards(state.active_player_index, 1);
        std::cout << "  P" << static_cast<int>(state.active_player_index) << " goes first and draws 1 card" << std::endl;
        std::cout << "  Note: First player cannot attack on turn 1" << std::endl;

        std::cout << "\n========== SETUP COMPLETE ==========\n" << std::endl;

        // Log initial state to X-Ray
        if (xray_logger) {
            xray_logger->log_state(state);
        }

        // Show game state and legal actions
        show_game_state_and_actions();
    }

    void show_game_state_and_actions() {
        show_state_for_player(state, state.active_player_index, card_name_map);
        refresh_actions();
        show_actions(current_actions, state, card_name_map);
    }

    void refresh_actions() {
        current_actions = engine.get_legal_actions(state);
    }

    void cmd_do(const std::vector<std::string>& args) {
        if (args.size() < 2) {
            std::cout << "Usage: do <action_number> [action_number...]" << std::endl;
            return;
        }

        for (size_t i = 1; i < args.size(); i++) {
            int idx = std::stoi(args[i]);

            if (idx < 0 || idx >= static_cast<int>(current_actions.size())) {
                std::cout << "Invalid action index: " << idx << std::endl;
                continue;
            }

            const auto& action = current_actions[idx];
            std::cout << "\n>>> Executing: " << action_type_to_string(action.action_type);
            if (action.card_id.has_value()) {
                auto it = card_name_map.find(*action.card_id);
                if (it != card_name_map.end()) {
                    std::cout << " - " << it->second;
                } else {
                    std::cout << " - " << *action.card_id;
                }
            }
            if (action.target_id.has_value()) {
                auto it = card_name_map.find(*action.target_id);
                if (it != card_name_map.end()) {
                    std::cout << " -> " << it->second;
                } else {
                    std::cout << " -> " << *action.target_id;
                }
            }
            std::cout << std::endl;

            // Log action to X-Ray before executing
            if (xray_logger) {
                xray_logger->log_action(state.turn_count, state.active_player_index, action);
            }

            state = engine.step(state, action);

            // Log resulting state to X-Ray after executing
            if (xray_logger) {
                xray_logger->log_state(state);
            }
        }

        // Show updated state and actions
        show_game_state_and_actions();
    }

    void cmd_play_trainer(const std::vector<std::string>& args) {
        if (args.size() < 2) {
            std::cout << "Usage: play <card_id>" << std::endl;
            return;
        }

        const std::string& card_id = args[1];

        if (!is_trainer_implemented(card_id)) {
            std::cout << "Trainer " << card_id << " is not implemented." << std::endl;
            return;
        }

        CardInstance trainer_card;
        trainer_card.id = "played_trainer";
        trainer_card.card_id = card_id;

        auto& registry = engine.get_logic_registry();
        if (!registry.has_trainer(card_id)) {
            std::cout << "Trainer " << card_id << " not registered in registry." << std::endl;
            return;
        }

        auto result = registry.invoke_trainer(card_id, state, trainer_card);

        std::cout << "Result: " << (result.success ? "SUCCESS" : "FAILED") << std::endl;
        if (!result.effect_description.empty()) {
            std::cout << "Effect: " << result.effect_description << std::endl;
        }
        if (result.requires_resolution) {
            std::cout << "Requires resolution - check 'stack'" << std::endl;
        }

        refresh_actions();
    }

    void run() {
        std::cout << "Pokemon TCG C++ Test Console" << std::endl;
        std::cout << "=====================================\n" << std::endl;

        // Auto-load default deck and start game
        std::vector<std::string> load_args = {"load"};
        cmd_load(load_args);

        if (!deck_cards.empty()) {
            cmd_setup();
        }

        std::string line;
        while (true) {
            std::cout << "\n> ";
            if (!std::getline(std::cin, line)) {
                break;
            }

            auto args = split(line);
            if (args.empty()) continue;

            const std::string& cmd = args[0];

            // Allow just typing a number as shorthand for "do <number>"
            if (std::isdigit(cmd[0])) {
                std::vector<std::string> do_args = {"do"};
                do_args.insert(do_args.end(), args.begin(), args.end());
                cmd_do(do_args);
                continue;
            }

            if (cmd == "quit" || cmd == "exit" || cmd == "q") {
                break;
            } else if (cmd == "help" || cmd == "h" || cmd == "?") {
                print_help();
            } else if (cmd == "load") {
                cmd_load(args);
            } else if (cmd == "setup" || cmd == "reset" || cmd == "restart") {
                cmd_setup();
            } else if (cmd == "show" || cmd == "s") {
                show_game_state_and_actions();
            } else if (cmd == "actions" || cmd == "a") {
                show_actions(current_actions, state, card_name_map);
            } else if (cmd == "do" || cmd == "d") {
                cmd_do(args);
            } else if (cmd == "trainers") {
                show_trainers();
            } else if (cmd == "play") {
                cmd_play_trainer(args);
            } else if (cmd == "stack") {
                show_stack(state);
            } else {
                std::cout << "Unknown command: '" << cmd << "'. Type 'help' for commands." << std::endl;
            }
        }

        std::cout << "Goodbye!" << std::endl;
    }
};

// ============================================================================
// MAIN
// ============================================================================

int main() {
    Console console;
    console.run();
    return 0;
}

/**
 * Pokemon TCG Engine - Card Database Implementation
 *
 * Loads card definitions from JSON files.
 */

#include "card_database.hpp"
#include <fstream>
#include <sstream>
#include <iostream>

// Simple JSON parsing (for minimal dependencies)
// In production, use nlohmann/json or rapidjson

namespace pokemon {

namespace {

// Trim whitespace
std::string trim(const std::string& s) {
    size_t start = s.find_first_not_of(" \t\n\r");
    if (start == std::string::npos) return "";
    size_t end = s.find_last_not_of(" \t\n\r");
    return s.substr(start, end - start + 1);
}

// Extract string value from JSON-like text
std::string extract_string(const std::string& json, const std::string& key) {
    std::string search = "\"" + key + "\"";
    size_t pos = json.find(search);
    if (pos == std::string::npos) return "";

    pos = json.find(':', pos);
    if (pos == std::string::npos) return "";

    pos = json.find('"', pos + 1);
    if (pos == std::string::npos) return "";

    size_t end = json.find('"', pos + 1);
    if (end == std::string::npos) return "";

    return json.substr(pos + 1, end - pos - 1);
}

// Extract integer value
int extract_int(const std::string& json, const std::string& key, int default_val = 0) {
    std::string search = "\"" + key + "\"";
    size_t pos = json.find(search);
    if (pos == std::string::npos) return default_val;

    pos = json.find(':', pos);
    if (pos == std::string::npos) return default_val;

    // Skip whitespace and find number
    while (pos < json.size() && !std::isdigit(json[pos]) && json[pos] != '-') {
        pos++;
    }

    if (pos >= json.size()) return default_val;

    int result = 0;
    int sign = 1;
    if (json[pos] == '-') {
        sign = -1;
        pos++;
    }

    while (pos < json.size() && std::isdigit(json[pos])) {
        result = result * 10 + (json[pos] - '0');
        pos++;
    }

    return sign * result;
}

// Extract array of strings
std::vector<std::string> extract_string_array(const std::string& json, const std::string& key) {
    std::vector<std::string> result;

    std::string search = "\"" + key + "\"";
    size_t pos = json.find(search);
    if (pos == std::string::npos) return result;

    pos = json.find('[', pos);
    if (pos == std::string::npos) return result;

    size_t end = json.find(']', pos);
    if (end == std::string::npos) return result;

    std::string array_content = json.substr(pos + 1, end - pos - 1);

    // Parse strings in array
    size_t i = 0;
    while (i < array_content.size()) {
        size_t quote_start = array_content.find('"', i);
        if (quote_start == std::string::npos) break;

        size_t quote_end = array_content.find('"', quote_start + 1);
        if (quote_end == std::string::npos) break;

        result.push_back(array_content.substr(quote_start + 1, quote_end - quote_start - 1));
        i = quote_end + 1;
    }

    return result;
}

} // anonymous namespace

CardDatabase::CardDatabase() {}

bool CardDatabase::load_from_json(const std::string& filepath) {
    std::ifstream file(filepath);
    if (!file.is_open()) {
        std::cerr << "[CardDatabase] Failed to open: " << filepath << std::endl;
        return false;
    }

    // Read entire file
    std::stringstream buffer;
    buffer << file.rdbuf();
    std::string content = buffer.str();

    // Find cards array
    size_t cards_pos = content.find("\"cards\"");
    if (cards_pos == std::string::npos) {
        std::cerr << "[CardDatabase] No 'cards' array found" << std::endl;
        return false;
    }

    size_t array_start = content.find('[', cards_pos);
    if (array_start == std::string::npos) return false;

    // Parse each card object
    size_t pos = array_start + 1;
    int card_count = 0;

    while (pos < content.size()) {
        // Find next card object
        size_t obj_start = content.find('{', pos);
        if (obj_start == std::string::npos) break;

        // Find matching closing brace (simple nesting)
        int depth = 1;
        size_t obj_end = obj_start + 1;
        while (obj_end < content.size() && depth > 0) {
            if (content[obj_end] == '{') depth++;
            else if (content[obj_end] == '}') depth--;
            obj_end++;
        }

        std::string card_json = content.substr(obj_start, obj_end - obj_start);

        // Parse card
        CardDef card;
        card.card_id = extract_string(card_json, "id");
        card.name = extract_string(card_json, "name");

        if (card.card_id.empty()) {
            pos = obj_end;
            continue;
        }

        // Parse supertype
        std::string supertype_str = extract_string(card_json, "supertype");
        card.supertype = parse_supertype(supertype_str);

        // Parse subtypes
        auto subtype_strs = extract_string_array(card_json, "subtypes");
        for (const auto& s : subtype_strs) {
            card.subtypes.push_back(parse_subtype(s));
        }

        // Pokemon-specific
        if (card.supertype == Supertype::POKEMON) {
            card.hp = extract_int(card_json, "hp", 0);

            // Types
            auto type_strs = extract_string_array(card_json, "types");
            for (const auto& t : type_strs) {
                card.types.push_back(parse_energy_type(t));
            }

            // Evolves from
            std::string evolves = extract_string(card_json, "evolvesFrom");
            if (!evolves.empty()) {
                card.evolves_from = evolves;
            }

            // Retreat cost
            auto retreat_strs = extract_string_array(card_json, "retreatCost");
            card.retreat_cost = static_cast<int>(retreat_strs.size());

            // TODO: Parse attacks and abilities
        }
        // Energy-specific
        else if (card.supertype == Supertype::ENERGY) {
            card.is_basic_energy = std::find(subtype_strs.begin(), subtype_strs.end(), "Basic")
                                   != subtype_strs.end();

            // Infer energy type from name
            if (card.name.find("Fire") != std::string::npos) {
                card.energy_type = EnergyType::FIRE;
            } else if (card.name.find("Water") != std::string::npos) {
                card.energy_type = EnergyType::WATER;
            } else if (card.name.find("Grass") != std::string::npos) {
                card.energy_type = EnergyType::GRASS;
            } else if (card.name.find("Lightning") != std::string::npos) {
                card.energy_type = EnergyType::LIGHTNING;
            } else if (card.name.find("Psychic") != std::string::npos) {
                card.energy_type = EnergyType::PSYCHIC;
            } else if (card.name.find("Fighting") != std::string::npos) {
                card.energy_type = EnergyType::FIGHTING;
            } else if (card.name.find("Darkness") != std::string::npos) {
                card.energy_type = EnergyType::DARKNESS;
            } else if (card.name.find("Metal") != std::string::npos) {
                card.energy_type = EnergyType::METAL;
            }

            card.provides.push_back(card.energy_type);
        }
        // Trainer-specific
        else if (card.supertype == Supertype::TRAINER) {
            // Parse rules text
            auto rules = extract_string_array(card_json, "rules");
            for (const auto& r : rules) {
                if (!card.rules_text.empty()) card.rules_text += " ";
                card.rules_text += r;
            }
        }

        // Add to database
        cards_[card.card_id] = std::move(card);
        card_count++;

        pos = obj_end;
    }

    std::cout << "[CardDatabase] Loaded " << card_count << " cards" << std::endl;
    return true;
}

const CardDef* CardDatabase::get_card(const CardDefID& card_id) const {
    auto it = cards_.find(card_id);
    if (it == cards_.end()) {
        return nullptr;
    }
    return &it->second;
}

bool CardDatabase::has_card(const CardDefID& card_id) const {
    return cards_.find(card_id) != cards_.end();
}

std::vector<CardDefID> CardDatabase::get_all_card_ids() const {
    std::vector<CardDefID> ids;
    ids.reserve(cards_.size());
    for (const auto& [id, _] : cards_) {
        ids.push_back(id);
    }
    return ids;
}

Supertype CardDatabase::parse_supertype(const std::string& s) {
    if (s == "Pokémon" || s == "Pokemon") return Supertype::POKEMON;
    if (s == "Trainer") return Supertype::TRAINER;
    if (s == "Energy") return Supertype::ENERGY;
    return Supertype::POKEMON;  // Default
}

Subtype CardDatabase::parse_subtype(const std::string& s) {
    if (s == "Basic") return Subtype::BASIC;
    if (s == "Stage 1") return Subtype::STAGE_1;
    if (s == "Stage 2") return Subtype::STAGE_2;
    if (s == "ex") return Subtype::EX;
    if (s == "VSTAR") return Subtype::VSTAR;
    if (s == "V") return Subtype::V;
    if (s == "VMAX") return Subtype::VMAX;
    if (s == "GX") return Subtype::GX;
    if (s == "Item") return Subtype::ITEM;
    if (s == "Supporter") return Subtype::SUPPORTER;
    if (s == "Stadium") return Subtype::STADIUM;
    if (s == "Pokémon Tool" || s == "Pokemon Tool") return Subtype::TOOL;
    if (s == "ACE SPEC") return Subtype::ACE_SPEC;
    if (s == "Tera") return Subtype::TERA;
    if (s == "Ancient") return Subtype::ANCIENT;
    if (s == "Future") return Subtype::FUTURE;
    return Subtype::BASIC;  // Default
}

EnergyType CardDatabase::parse_energy_type(const std::string& s) {
    if (s == "Grass") return EnergyType::GRASS;
    if (s == "Fire") return EnergyType::FIRE;
    if (s == "Water") return EnergyType::WATER;
    if (s == "Lightning") return EnergyType::LIGHTNING;
    if (s == "Psychic") return EnergyType::PSYCHIC;
    if (s == "Fighting") return EnergyType::FIGHTING;
    if (s == "Darkness") return EnergyType::DARKNESS;
    if (s == "Metal") return EnergyType::METAL;
    if (s == "Colorless") return EnergyType::COLORLESS;
    if (s == "Dragon") return EnergyType::COLORLESS;  // Dragon uses Colorless
    return EnergyType::COLORLESS;  // Default
}

} // namespace pokemon

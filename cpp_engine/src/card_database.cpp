/**
 * Pokemon TCG Engine - Card Database Implementation
 *
 * Loads card definitions from JSON files using nlohmann/json.
 * Parses complete card data including attacks, abilities, weakness/resistance.
 */

#include "card_database.hpp"
#include <nlohmann/json.hpp>
#include <fstream>
#include <iostream>

using json = nlohmann::json;

namespace pokemon {

CardDatabase::CardDatabase() {}

bool CardDatabase::load_from_json(const std::string& filepath) {
    std::ifstream file(filepath);
    if (!file.is_open()) {
        std::cerr << "[CardDatabase] Failed to open: " << filepath << std::endl;
        return false;
    }

    try {
        json data = json::parse(file);

        if (!data.contains("cards") || !data["cards"].is_array()) {
            std::cerr << "[CardDatabase] No 'cards' array found" << std::endl;
            return false;
        }

        int card_count = 0;

        for (const auto& card_json : data["cards"]) {
            CardDef card = parse_card(card_json);

            if (!card.card_id.empty()) {
                cards_[card.card_id] = std::move(card);
                card_count++;
            }
        }

        std::cout << "[CardDatabase] Loaded " << card_count << " cards" << std::endl;
        return true;

    } catch (const json::parse_error& e) {
        std::cerr << "[CardDatabase] JSON parse error: " << e.what() << std::endl;
        return false;
    } catch (const std::exception& e) {
        std::cerr << "[CardDatabase] Error: " << e.what() << std::endl;
        return false;
    }
}

CardDef CardDatabase::parse_card(const json& card_json) const {
    CardDef card;

    // Required fields
    card.card_id = card_json.value("id", "");
    card.name = card_json.value("name", "");

    if (card.card_id.empty()) {
        return card;  // Invalid card
    }

    // Parse supertype
    std::string supertype_str = card_json.value("supertype", "");
    card.supertype = parse_supertype(supertype_str);

    // Parse subtypes
    if (card_json.contains("subtypes") && card_json["subtypes"].is_array()) {
        for (const auto& s : card_json["subtypes"]) {
            card.subtypes.push_back(parse_subtype(s.get<std::string>()));
        }
    }

    // Pokemon-specific parsing
    if (card.supertype == Supertype::POKEMON) {
        parse_pokemon_fields(card_json, card);
    }
    // Energy-specific parsing
    else if (card.supertype == Supertype::ENERGY) {
        parse_energy_fields(card_json, card);
    }
    // Trainer-specific parsing
    else if (card.supertype == Supertype::TRAINER) {
        parse_trainer_fields(card_json, card);
    }

    return card;
}

void CardDatabase::parse_pokemon_fields(const json& card_json, CardDef& card) const {
    // HP (can be string or int in JSON)
    if (card_json.contains("hp")) {
        if (card_json["hp"].is_string()) {
            try {
                card.hp = std::stoi(card_json["hp"].get<std::string>());
            } catch (...) {
                card.hp = 0;
            }
        } else if (card_json["hp"].is_number()) {
            card.hp = card_json["hp"].get<int>();
        }
    }

    // Types (Pokemon types like Fire, Water)
    if (card_json.contains("types") && card_json["types"].is_array()) {
        for (const auto& t : card_json["types"]) {
            card.types.push_back(parse_energy_type(t.get<std::string>()));
        }
    }

    // Evolves from
    if (card_json.contains("evolvesFrom") && !card_json["evolvesFrom"].is_null()) {
        card.evolves_from = card_json["evolvesFrom"].get<std::string>();
    }

    // Retreat cost (array of energy types)
    if (card_json.contains("retreatCost") && card_json["retreatCost"].is_array()) {
        card.retreat_cost = static_cast<int>(card_json["retreatCost"].size());
    }

    // Weakness - parse as object with type and value
    if (card_json.contains("weaknesses") && card_json["weaknesses"].is_array() &&
        !card_json["weaknesses"].empty()) {
        const auto& weakness = card_json["weaknesses"][0];
        if (weakness.contains("type")) {
            card.weakness = parse_energy_type(weakness["type"].get<std::string>());
        }
        // Note: weakness multiplier (usually x2) is standard in modern TCG
        card.weakness_multiplier = 2;  // Default x2
        if (weakness.contains("value")) {
            std::string val = weakness["value"].get<std::string>();
            if (val.find("×") != std::string::npos || val.find("x") != std::string::npos) {
                // Parse multiplier like "×2" or "x2"
                size_t pos = val.find_first_of("0123456789");
                if (pos != std::string::npos) {
                    card.weakness_multiplier = std::stoi(val.substr(pos));
                }
            }
        }
    }

    // Resistance - parse as object with type and value
    if (card_json.contains("resistances") && card_json["resistances"].is_array() &&
        !card_json["resistances"].empty()) {
        const auto& resistance = card_json["resistances"][0];
        if (resistance.contains("type")) {
            card.resistance = parse_energy_type(resistance["type"].get<std::string>());
        }
        // Note: resistance reduction (usually -30) is standard
        card.resistance_value = -30;  // Default -30
        if (resistance.contains("value")) {
            std::string val = resistance["value"].get<std::string>();
            // Parse value like "-30"
            size_t pos = val.find_first_of("-0123456789");
            if (pos != std::string::npos) {
                card.resistance_value = std::stoi(val.substr(pos));
            }
        }
    }

    // Parse attacks
    if (card_json.contains("attacks") && card_json["attacks"].is_array()) {
        for (const auto& attack_json : card_json["attacks"]) {
            card.attacks.push_back(parse_attack(attack_json));
        }
    }

    // Parse abilities
    if (card_json.contains("abilities") && card_json["abilities"].is_array()) {
        for (const auto& ability_json : card_json["abilities"]) {
            card.abilities.push_back(parse_ability(ability_json));
        }
    }

    // Parse rules (for special Pokemon like ex, VSTAR)
    if (card_json.contains("rules") && card_json["rules"].is_array()) {
        for (const auto& rule : card_json["rules"]) {
            if (!card.rules_text.empty()) card.rules_text += " ";
            card.rules_text += rule.get<std::string>();
        }
    }
}

AttackDef CardDatabase::parse_attack(const json& attack_json) const {
    AttackDef attack;

    attack.name = attack_json.value("name", "");
    attack.text = attack_json.value("text", "");

    // Parse energy cost
    if (attack_json.contains("cost") && attack_json["cost"].is_array()) {
        for (const auto& c : attack_json["cost"]) {
            attack.cost.push_back(parse_energy_type(c.get<std::string>()));
        }
    }
    attack.converted_energy_cost = static_cast<int>(attack.cost.size());

    // Parse damage (can be string like "30", "30+", "30×", or empty)
    if (attack_json.contains("damage") && !attack_json["damage"].is_null()) {
        std::string damage_str = attack_json["damage"].get<std::string>();
        if (!damage_str.empty()) {
            // Check for variable damage modifiers
            if (damage_str.back() == '+') {
                attack.damage_modifier = "+";
                damage_str.pop_back();
            } else if (damage_str.find("×") != std::string::npos ||
                       damage_str.find("x") != std::string::npos) {
                attack.damage_modifier = "x";
                size_t pos = damage_str.find_first_of("×x");
                damage_str = damage_str.substr(0, pos);
            } else if (damage_str.back() == '-') {
                attack.damage_modifier = "-";
                damage_str.pop_back();
            }

            // Parse base damage number
            try {
                attack.base_damage = std::stoi(damage_str);
            } catch (...) {
                attack.base_damage = 0;
            }
        }
    }

    // Generate effect function name from card_id and attack name
    // This matches how Python logic_registry works
    // e.g., "sv3-125" + "Burning Darkness" -> effect lookup in registry
    attack.effect_function = attack.name;  // Logic registry uses attack name

    return attack;
}

AbilityDef CardDatabase::parse_ability(const json& ability_json) const {
    AbilityDef ability;

    ability.name = ability_json.value("name", "");
    ability.text = ability_json.value("text", "");
    ability.ability_type = ability_json.value("type", "Ability");

    // Convert text to lowercase for pattern matching
    std::string text_lower = ability.text;
    std::transform(text_lower.begin(), text_lower.end(), text_lower.begin(), ::tolower);

    // Determine category based on ability type and text
    // This matches Python logic_registry categories:
    // - attack, activatable, modifier, guard, hook, passive

    if (ability.ability_type == "VSTAR Power") {
        ability.is_activatable = true;
        ability.category = "activatable";
    }
    // PASSIVE: Ability locks that block other abilities when active in Active Spot
    // Examples: Klefki's "Mischievous Lock", Garbodor's "Garbotoxin"
    // Pattern: "Abilities of all [opponent's] Pokémon... have no Abilities" or similar
    else if ((text_lower.find("abilities") != std::string::npos &&
              text_lower.find("have no abilities") != std::string::npos) ||
             (text_lower.find("abilities") != std::string::npos &&
              text_lower.find("can't use") != std::string::npos) ||
             (text_lower.find("abilities") != std::string::npos &&
              text_lower.find("are blocked") != std::string::npos)) {
        ability.is_activatable = false;
        ability.category = "passive";
        ability.effect_type = "ability_lock";

        // Determine scope
        if (text_lower.find("opponent") != std::string::npos) {
            ability.scope = "opponent";
        } else if (text_lower.find("both players") != std::string::npos ||
                   text_lower.find("all") != std::string::npos) {
            ability.scope = "all";
        } else {
            ability.scope = "opponent";  // Default for ability locks
        }
    }
    // GUARD: Blocks effects/conditions from affecting this Pokemon
    // Examples: Insomnia (can't be Asleep), Safeguard (prevent damage)
    else if (text_lower.find("can't be") != std::string::npos ||
             text_lower.find("prevent") != std::string::npos ||
             text_lower.find("protected") != std::string::npos ||
             text_lower.find("unaffected") != std::string::npos) {
        ability.is_activatable = false;
        ability.category = "guard";
        ability.scope = "self";

        // Determine guard type
        if (text_lower.find("asleep") != std::string::npos ||
            text_lower.find("paralyzed") != std::string::npos ||
            text_lower.find("confused") != std::string::npos ||
            text_lower.find("poisoned") != std::string::npos ||
            text_lower.find("burned") != std::string::npos ||
            text_lower.find("special conditions") != std::string::npos) {
            ability.guard_type = "status_condition";
        } else if (text_lower.find("damage") != std::string::npos) {
            ability.guard_type = "damage";
        } else if (text_lower.find("effects") != std::string::npos) {
            ability.guard_type = "effect";
        } else {
            ability.guard_type = "status_condition";  // Default
        }
    }
    // HOOK: Event-triggered abilities
    // Examples: Infernal Reign (when evolves), Insta-Flock (when played)
    else if (text_lower.find("when you play") != std::string::npos ||
             text_lower.find("when this pokémon") != std::string::npos ||
             text_lower.find("when this pokemon") != std::string::npos ||
             text_lower.find("when you attach") != std::string::npos ||
             text_lower.find("when your opponent") != std::string::npos) {
        ability.is_activatable = false;
        ability.category = "hook";
        ability.scope = "self";

        // Determine trigger type
        if (text_lower.find("evolves") != std::string::npos ||
            text_lower.find("evolve") != std::string::npos) {
            ability.trigger = "on_evolve";
        } else if (text_lower.find("play this") != std::string::npos ||
                   text_lower.find("play from your hand") != std::string::npos ||
                   text_lower.find("when you play") != std::string::npos) {
            ability.trigger = "on_play";
        } else if (text_lower.find("attach") != std::string::npos &&
                   text_lower.find("energy") != std::string::npos) {
            ability.trigger = "on_attach_energy";
        } else if (text_lower.find("knocked out") != std::string::npos) {
            ability.trigger = "on_knockout";
        } else {
            ability.trigger = "on_play";  // Default
        }
    }
    // ACTIVATABLE: Player-triggered abilities
    // Examples: Infernal Reign (once per turn choice)
    else if (text_lower.find("you may") != std::string::npos ||
             text_lower.find("once during your turn") != std::string::npos ||
             text_lower.find("you can use this ability") != std::string::npos ||
             text_lower.find("once per turn") != std::string::npos) {
        ability.is_activatable = true;
        ability.category = "activatable";
        ability.scope = "self";
    }
    // MODIFIER: Continuously modifies values
    // Examples: Agile (retreat cost), Big Charm (HP)
    else if (text_lower.find("retreat cost") != std::string::npos ||
             text_lower.find("has no retreat") != std::string::npos) {
        ability.is_activatable = false;
        ability.category = "modifier";
        ability.modifier_type = "retreat_cost";
        ability.scope = "self";
    } else if (text_lower.find("maximum hp") != std::string::npos ||
               text_lower.find("max hp") != std::string::npos ||
               (text_lower.find("hp") != std::string::npos &&
                text_lower.find("more") != std::string::npos)) {
        ability.is_activatable = false;
        ability.category = "modifier";
        ability.modifier_type = "hp";
        ability.scope = "self";
    } else if (text_lower.find("damage") != std::string::npos &&
               (text_lower.find("more") != std::string::npos ||
                text_lower.find("less") != std::string::npos ||
                text_lower.find("+") != std::string::npos ||
                text_lower.find("-") != std::string::npos)) {
        ability.is_activatable = false;
        ability.category = "modifier";
        ability.modifier_type = "damage";
        ability.scope = "self";
    } else {
        // Default: treat as modifier (passive effect)
        ability.is_activatable = false;
        ability.category = "modifier";
        ability.scope = "self";
    }

    ability.effect_function = ability.name;

    return ability;
}

void CardDatabase::parse_energy_fields(const json& card_json, CardDef& card) const {
    // Check if basic energy (from subtypes)
    card.is_basic_energy = std::find(card.subtypes.begin(), card.subtypes.end(),
                                      Subtype::BASIC) != card.subtypes.end();

    // Infer energy type from name
    std::string name_lower = card.name;
    std::transform(name_lower.begin(), name_lower.end(), name_lower.begin(), ::tolower);

    if (name_lower.find("fire") != std::string::npos) {
        card.energy_type = EnergyType::FIRE;
    } else if (name_lower.find("water") != std::string::npos) {
        card.energy_type = EnergyType::WATER;
    } else if (name_lower.find("grass") != std::string::npos) {
        card.energy_type = EnergyType::GRASS;
    } else if (name_lower.find("lightning") != std::string::npos) {
        card.energy_type = EnergyType::LIGHTNING;
    } else if (name_lower.find("psychic") != std::string::npos) {
        card.energy_type = EnergyType::PSYCHIC;
    } else if (name_lower.find("fighting") != std::string::npos) {
        card.energy_type = EnergyType::FIGHTING;
    } else if (name_lower.find("darkness") != std::string::npos ||
               name_lower.find("dark") != std::string::npos) {
        card.energy_type = EnergyType::DARKNESS;
    } else if (name_lower.find("metal") != std::string::npos ||
               name_lower.find("steel") != std::string::npos) {
        card.energy_type = EnergyType::METAL;
    } else {
        card.energy_type = EnergyType::COLORLESS;
    }

    // Default provides (basic energy provides its type)
    if (card.is_basic_energy) {
        card.provides.push_back(card.energy_type);
    }

    // Special energy - parse from rules text
    if (!card.is_basic_energy && card_json.contains("rules") && card_json["rules"].is_array()) {
        for (const auto& rule : card_json["rules"]) {
            std::string rule_text = rule.get<std::string>();
            if (!card.rules_text.empty()) card.rules_text += " ";
            card.rules_text += rule_text;

            // Parse "provides X energy" patterns
            // e.g., "Double Turbo Energy provides 2 Colorless Energy"
            // This is simplified - real parsing would need more logic
        }
    }
}

void CardDatabase::parse_trainer_fields(const json& card_json, CardDef& card) const {
    // Parse rules text
    if (card_json.contains("rules") && card_json["rules"].is_array()) {
        for (const auto& rule : card_json["rules"]) {
            if (!card.rules_text.empty()) card.rules_text += " ";
            card.rules_text += rule.get<std::string>();
        }
    }

    // Effect text (for Item/Supporter effect description)
    if (card_json.contains("text") && !card_json["text"].is_null()) {
        if (!card.rules_text.empty()) card.rules_text += " ";
        card.rules_text += card_json["text"].get<std::string>();
    }
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
    if (s == "Special") return Subtype::SPECIAL;
    return Subtype::BASIC;
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
    if (s == "Fairy") return EnergyType::PSYCHIC;     // Fairy merged into Psychic
    return EnergyType::COLORLESS;  // Default
}

} // namespace pokemon

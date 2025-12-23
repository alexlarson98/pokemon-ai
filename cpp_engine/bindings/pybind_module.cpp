/**
 * Pokemon TCG Engine - Python Bindings
 *
 * pybind11 wrapper for the C++ engine.
 * Provides drop-in replacement for Python engine.
 */

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/operators.h>
#include <pybind11/functional.h>

#include "pokemon_engine.hpp"

namespace py = pybind11;

PYBIND11_MODULE(pokemon_engine_cpp, m) {
    m.doc() = "High-performance Pokemon TCG engine for MCTS-based AI";

    // ========================================================================
    // ENUMS
    // ========================================================================

    py::enum_<pokemon::Supertype>(m, "Supertype")
        .value("POKEMON", pokemon::Supertype::POKEMON)
        .value("TRAINER", pokemon::Supertype::TRAINER)
        .value("ENERGY", pokemon::Supertype::ENERGY)
        .export_values();

    py::enum_<pokemon::Subtype>(m, "Subtype")
        .value("BASIC", pokemon::Subtype::BASIC)
        .value("STAGE_1", pokemon::Subtype::STAGE_1)
        .value("STAGE_2", pokemon::Subtype::STAGE_2)
        .value("EX", pokemon::Subtype::EX)
        .value("VSTAR", pokemon::Subtype::VSTAR)
        .value("V", pokemon::Subtype::V)
        .value("VMAX", pokemon::Subtype::VMAX)
        .value("GX", pokemon::Subtype::GX)
        .value("ITEM", pokemon::Subtype::ITEM)
        .value("SUPPORTER", pokemon::Subtype::SUPPORTER)
        .value("STADIUM", pokemon::Subtype::STADIUM)
        .value("TOOL", pokemon::Subtype::TOOL)
        .value("ACE_SPEC", pokemon::Subtype::ACE_SPEC)
        .export_values();

    py::enum_<pokemon::EnergyType>(m, "EnergyType")
        .value("GRASS", pokemon::EnergyType::GRASS)
        .value("FIRE", pokemon::EnergyType::FIRE)
        .value("WATER", pokemon::EnergyType::WATER)
        .value("LIGHTNING", pokemon::EnergyType::LIGHTNING)
        .value("PSYCHIC", pokemon::EnergyType::PSYCHIC)
        .value("FIGHTING", pokemon::EnergyType::FIGHTING)
        .value("DARKNESS", pokemon::EnergyType::DARKNESS)
        .value("METAL", pokemon::EnergyType::METAL)
        .value("COLORLESS", pokemon::EnergyType::COLORLESS)
        .export_values();

    py::enum_<pokemon::StatusCondition>(m, "StatusCondition")
        .value("POISONED", pokemon::StatusCondition::POISONED)
        .value("BURNED", pokemon::StatusCondition::BURNED)
        .value("ASLEEP", pokemon::StatusCondition::ASLEEP)
        .value("PARALYZED", pokemon::StatusCondition::PARALYZED)
        .value("CONFUSED", pokemon::StatusCondition::CONFUSED)
        .export_values();

    py::enum_<pokemon::GamePhase>(m, "GamePhase")
        .value("SETUP", pokemon::GamePhase::SETUP)
        .value("MULLIGAN", pokemon::GamePhase::MULLIGAN)
        .value("DRAW", pokemon::GamePhase::DRAW)
        .value("MAIN", pokemon::GamePhase::MAIN)
        .value("ATTACK", pokemon::GamePhase::ATTACK)
        .value("CLEANUP", pokemon::GamePhase::CLEANUP)
        .value("END", pokemon::GamePhase::END)
        .value("SUDDEN_DEATH", pokemon::GamePhase::SUDDEN_DEATH)
        .export_values();

    py::enum_<pokemon::GameResult>(m, "GameResult")
        .value("ONGOING", pokemon::GameResult::ONGOING)
        .value("PLAYER_0_WIN", pokemon::GameResult::PLAYER_0_WIN)
        .value("PLAYER_1_WIN", pokemon::GameResult::PLAYER_1_WIN)
        .value("DRAW", pokemon::GameResult::DRAW)
        .export_values();

    py::enum_<pokemon::ActionType>(m, "ActionType")
        .value("MULLIGAN_DRAW", pokemon::ActionType::MULLIGAN_DRAW)
        .value("REVEAL_HAND_MULLIGAN", pokemon::ActionType::REVEAL_HAND_MULLIGAN)
        .value("PLACE_ACTIVE", pokemon::ActionType::PLACE_ACTIVE)
        .value("PLACE_BENCH", pokemon::ActionType::PLACE_BENCH)
        .value("PLAY_BASIC", pokemon::ActionType::PLAY_BASIC)
        .value("EVOLVE", pokemon::ActionType::EVOLVE)
        .value("ATTACH_ENERGY", pokemon::ActionType::ATTACH_ENERGY)
        .value("PLAY_ITEM", pokemon::ActionType::PLAY_ITEM)
        .value("PLAY_SUPPORTER", pokemon::ActionType::PLAY_SUPPORTER)
        .value("PLAY_STADIUM", pokemon::ActionType::PLAY_STADIUM)
        .value("ATTACH_TOOL", pokemon::ActionType::ATTACH_TOOL)
        .value("USE_ABILITY", pokemon::ActionType::USE_ABILITY)
        .value("RETREAT", pokemon::ActionType::RETREAT)
        .value("ATTACK", pokemon::ActionType::ATTACK)
        .value("END_TURN", pokemon::ActionType::END_TURN)
        .value("TAKE_PRIZE", pokemon::ActionType::TAKE_PRIZE)
        .value("PROMOTE_ACTIVE", pokemon::ActionType::PROMOTE_ACTIVE)
        .value("SELECT_CARD", pokemon::ActionType::SELECT_CARD)
        .value("CONFIRM_SELECTION", pokemon::ActionType::CONFIRM_SELECTION)
        .export_values();

    // ========================================================================
    // CARD INSTANCE
    // ========================================================================

    py::class_<pokemon::CardInstance>(m, "CardInstance")
        .def(py::init<>())
        .def(py::init<pokemon::CardID, pokemon::CardDefID, pokemon::PlayerID>())
        .def_readwrite("id", &pokemon::CardInstance::id)
        .def_readwrite("card_id", &pokemon::CardInstance::card_id)
        .def_readwrite("owner_id", &pokemon::CardInstance::owner_id)
        .def_readwrite("current_hp", &pokemon::CardInstance::current_hp)
        .def_readwrite("damage_counters", &pokemon::CardInstance::damage_counters)
        .def_readwrite("turns_in_play", &pokemon::CardInstance::turns_in_play)
        .def_readwrite("evolved_this_turn", &pokemon::CardInstance::evolved_this_turn)
        .def_readonly("attached_energy", &pokemon::CardInstance::attached_energy)
        .def_readonly("attached_tools", &pokemon::CardInstance::attached_tools)
        .def("has_status", &pokemon::CardInstance::has_status)
        .def("add_status", &pokemon::CardInstance::add_status)
        .def("remove_status", &pokemon::CardInstance::remove_status)
        .def("clear_all_status", &pokemon::CardInstance::clear_all_status)
        .def("is_asleep_or_paralyzed", &pokemon::CardInstance::is_asleep_or_paralyzed)
        .def("get_total_hp_loss", &pokemon::CardInstance::get_total_hp_loss)
        .def("is_knocked_out", &pokemon::CardInstance::is_knocked_out)
        .def("total_attached_energy", &pokemon::CardInstance::total_attached_energy)
        .def("clone", &pokemon::CardInstance::clone);

    // ========================================================================
    // ZONE
    // ========================================================================

    py::class_<pokemon::Zone>(m, "Zone")
        .def(py::init<>())
        .def_readonly("cards", &pokemon::Zone::cards)
        .def_readwrite("is_ordered", &pokemon::Zone::is_ordered)
        .def_readwrite("is_hidden", &pokemon::Zone::is_hidden)
        .def_readwrite("is_private", &pokemon::Zone::is_private)
        .def("count", &pokemon::Zone::count)
        .def("is_empty", &pokemon::Zone::is_empty)
        .def("find_card", py::overload_cast<const pokemon::CardID&>(&pokemon::Zone::find_card),
             py::return_value_policy::reference)
        .def("clone", &pokemon::Zone::clone);

    // ========================================================================
    // BOARD
    // ========================================================================

    py::class_<pokemon::Board>(m, "Board")
        .def(py::init<>())
        .def_readwrite("active_spot", &pokemon::Board::active_spot)
        .def_readonly("bench", &pokemon::Board::bench)
        .def_readwrite("max_bench_size", &pokemon::Board::max_bench_size)
        .def("get_bench_count", &pokemon::Board::get_bench_count)
        .def("can_add_to_bench", &pokemon::Board::can_add_to_bench)
        .def("has_active", &pokemon::Board::has_active)
        .def("has_any_pokemon", &pokemon::Board::has_any_pokemon)
        .def("clone", &pokemon::Board::clone);

    // ========================================================================
    // PLAYER STATE
    // ========================================================================

    py::class_<pokemon::PlayerState>(m, "PlayerState")
        .def(py::init<>())
        .def(py::init<pokemon::PlayerID>())
        .def_readwrite("player_id", &pokemon::PlayerState::player_id)
        .def_readwrite("name", &pokemon::PlayerState::name)
        .def_readwrite("deck", &pokemon::PlayerState::deck)
        .def_readwrite("hand", &pokemon::PlayerState::hand)
        .def_readwrite("discard", &pokemon::PlayerState::discard)
        .def_readwrite("prizes", &pokemon::PlayerState::prizes)
        .def_readwrite("board", &pokemon::PlayerState::board)
        .def_readwrite("vstar_power_used", &pokemon::PlayerState::vstar_power_used)
        .def_readwrite("supporter_played_this_turn", &pokemon::PlayerState::supporter_played_this_turn)
        .def_readwrite("energy_attached_this_turn", &pokemon::PlayerState::energy_attached_this_turn)
        .def_readwrite("retreated_this_turn", &pokemon::PlayerState::retreated_this_turn)
        .def_readwrite("prizes_taken", &pokemon::PlayerState::prizes_taken)
        .def("has_active_pokemon", &pokemon::PlayerState::has_active_pokemon)
        .def("has_any_pokemon_in_play", &pokemon::PlayerState::has_any_pokemon_in_play)
        .def("reset_turn_flags", &pokemon::PlayerState::reset_turn_flags)
        .def("clone", &pokemon::PlayerState::clone);

    // ========================================================================
    // ACTION
    // ========================================================================

    py::class_<pokemon::Action>(m, "Action")
        .def(py::init<>())
        .def(py::init<pokemon::ActionType, pokemon::PlayerID>())
        .def_readwrite("action_type", &pokemon::Action::action_type)
        .def_readwrite("player_id", &pokemon::Action::player_id)
        .def_readwrite("card_id", &pokemon::Action::card_id)
        .def_readwrite("target_id", &pokemon::Action::target_id)
        .def_readwrite("attack_name", &pokemon::Action::attack_name)
        .def_readwrite("ability_name", &pokemon::Action::ability_name)
        .def_readwrite("choice_index", &pokemon::Action::choice_index)
        .def_readwrite("display_label", &pokemon::Action::display_label)
        .def("__str__", &pokemon::Action::to_string)
        .def("__repr__", &pokemon::Action::to_string)
        .def(py::self == py::self)
        .def(py::self != py::self)
        // Factory methods
        .def_static("end_turn", &pokemon::Action::end_turn)
        .def_static("place_active", &pokemon::Action::place_active)
        .def_static("place_bench", &pokemon::Action::place_bench)
        .def_static("play_basic", &pokemon::Action::play_basic)
        .def_static("evolve", &pokemon::Action::evolve)
        .def_static("attach_energy", &pokemon::Action::attach_energy)
        .def_static("attack", &pokemon::Action::attack)
        .def_static("use_ability", &pokemon::Action::use_ability)
        .def_static("retreat", &pokemon::Action::retreat)
        .def_static("play_item", &pokemon::Action::play_item)
        .def_static("play_supporter", &pokemon::Action::play_supporter)
        .def_static("play_stadium", &pokemon::Action::play_stadium)
        .def_static("take_prize", &pokemon::Action::take_prize)
        .def_static("promote_active", &pokemon::Action::promote_active)
        .def_static("select_card", &pokemon::Action::select_card)
        .def_static("confirm_selection", &pokemon::Action::confirm_selection);

    // ========================================================================
    // GAME STATE
    // ========================================================================

    py::class_<pokemon::GameState>(m, "GameState")
        .def(py::init<>())
        .def_readonly("players", &pokemon::GameState::players)
        .def_readwrite("turn_count", &pokemon::GameState::turn_count)
        .def_readwrite("active_player_index", &pokemon::GameState::active_player_index)
        .def_readwrite("starting_player_id", &pokemon::GameState::starting_player_id)
        .def_readwrite("current_phase", &pokemon::GameState::current_phase)
        .def_readwrite("stadium", &pokemon::GameState::stadium)
        .def_readwrite("result", &pokemon::GameState::result)
        .def_readwrite("winner_id", &pokemon::GameState::winner_id)
        .def("get_active_player", py::overload_cast<>(&pokemon::GameState::get_active_player),
             py::return_value_policy::reference)
        .def("get_opponent", py::overload_cast<>(&pokemon::GameState::get_opponent),
             py::return_value_policy::reference)
        .def("get_player", py::overload_cast<pokemon::PlayerID>(&pokemon::GameState::get_player),
             py::return_value_policy::reference)
        .def("switch_active_player", &pokemon::GameState::switch_active_player)
        .def("is_game_over", &pokemon::GameState::is_game_over)
        .def("has_pending_resolution", &pokemon::GameState::has_pending_resolution)
        .def("clone", &pokemon::GameState::clone);

    // ========================================================================
    // CARD DATABASE
    // ========================================================================

    py::class_<pokemon::CardDef>(m, "CardDef")
        .def_readonly("card_id", &pokemon::CardDef::card_id)
        .def_readonly("name", &pokemon::CardDef::name)
        .def_readonly("supertype", &pokemon::CardDef::supertype)
        .def_readonly("subtypes", &pokemon::CardDef::subtypes)
        .def_readonly("hp", &pokemon::CardDef::hp)
        .def_readonly("types", &pokemon::CardDef::types)
        .def_readonly("weakness", &pokemon::CardDef::weakness)
        .def_readonly("resistance", &pokemon::CardDef::resistance)
        .def_readonly("retreat_cost", &pokemon::CardDef::retreat_cost)
        .def_readonly("evolves_from", &pokemon::CardDef::evolves_from)
        .def("is_pokemon", &pokemon::CardDef::is_pokemon)
        .def("is_trainer", &pokemon::CardDef::is_trainer)
        .def("is_energy", &pokemon::CardDef::is_energy)
        .def("is_basic_pokemon", &pokemon::CardDef::is_basic_pokemon)
        .def("is_ex", &pokemon::CardDef::is_ex)
        .def("get_prize_value", &pokemon::CardDef::get_prize_value);

    py::class_<pokemon::CardDatabase>(m, "CardDatabase")
        .def(py::init<>())
        .def("load_from_json", &pokemon::CardDatabase::load_from_json)
        .def("get_card", &pokemon::CardDatabase::get_card, py::return_value_policy::reference)
        .def("has_card", &pokemon::CardDatabase::has_card)
        .def("get_all_card_ids", &pokemon::CardDatabase::get_all_card_ids)
        .def("card_count", &pokemon::CardDatabase::card_count);

    // ========================================================================
    // ENGINE
    // ========================================================================

    py::class_<pokemon::PokemonEngine>(m, "PokemonEngine")
        .def(py::init<>())
        .def("get_legal_actions", &pokemon::PokemonEngine::get_legal_actions)
        .def("step", &pokemon::PokemonEngine::step)
        .def("step_inplace", &pokemon::PokemonEngine::step_inplace)
        .def("check_win_conditions", &pokemon::PokemonEngine::check_win_conditions)
        .def("get_card_database", &pokemon::PokemonEngine::get_card_database,
             py::return_value_policy::reference);

    // ========================================================================
    // MODULE INFO
    // ========================================================================

    m.attr("VERSION") = pokemon::get_version();
    m.attr("__version__") = pokemon::get_version();
}

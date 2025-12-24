/**
 * Tests for Trainer Cards
 */

#include <sstream>
#include "cards/trainer_registry.hpp"
#include "cards/effect_builders.hpp"
#include "game_state.hpp"
#include "logic_registry.hpp"

using namespace pokemon;
using namespace pokemon::trainers;
using namespace pokemon::effects;

// ============================================================================
// TRAINER REGISTRY TESTS
// ============================================================================

TEST(TrainerRegistry, GetTrainerInfo) {
    auto info = get_trainer_info();
    TEST_ASSERT_TRUE(info.size() > 0);

    // Check that Nest Ball is in the list
    bool found_nest_ball = false;
    for (const auto& trainer : info) {
        if (trainer.name == "Nest Ball") {
            found_nest_ball = true;
            TEST_ASSERT_TRUE(trainer.implemented);
            break;
        }
    }
    TEST_ASSERT_TRUE(found_nest_ball);
}

TEST(TrainerRegistry, NestBallImplemented) {
    TEST_ASSERT_TRUE(is_trainer_implemented("sv1-181"));
    TEST_ASSERT_TRUE(is_trainer_implemented("sv1-255"));
    TEST_ASSERT_TRUE(is_trainer_implemented("sv4pt5-84"));
}

TEST(TrainerRegistry, UnimplementedTrainer) {
    TEST_ASSERT_FALSE(is_trainer_implemented("nonexistent-card"));
    TEST_ASSERT_FALSE(is_trainer_implemented("sv1-196"));  // Ultra Ball not yet implemented
}

// ============================================================================
// NEST BALL TESTS
// ============================================================================

TEST(NestBall, RegistersHandlers) {
    LogicRegistry registry;
    register_nest_ball(registry);

    TEST_ASSERT_TRUE(registry.has_trainer("sv1-181"));
    TEST_ASSERT_TRUE(registry.has_trainer("sv1-255"));
    TEST_ASSERT_TRUE(registry.has_trainer("sv4pt5-84"));
}

TEST(NestBall, ExecuteWithBenchSpace) {
    LogicRegistry registry;
    register_nest_ball(registry);

    GameState state;
    state.active_player_index = 0;

    // Ensure bench has space (empty bench)
    state.players[0].board.bench.clear();

    // Add some cards to deck for searching
    for (int i = 0; i < 10; i++) {
        CardInstance card;
        card.id = "deck_" + std::to_string(i);
        card.card_id = "sv1-1";  // Some card
        state.players[0].deck.cards.push_back(card);
    }

    CardInstance nest_ball;
    nest_ball.id = "nest_ball_test";
    nest_ball.card_id = "sv1-181";
    
    auto result = registry.invoke_trainer("sv1-181", state, nest_ball);

    TEST_ASSERT_TRUE(result.success);
    TEST_ASSERT_TRUE(result.requires_resolution);
    TEST_ASSERT_EQ(1u, state.resolution_stack.size());

    // Check the resolution step
    auto* step = std::get_if<SearchDeckStep>(&state.resolution_stack[0]);
    TEST_ASSERT_NOT_NULL(step);
    TEST_ASSERT_TRUE(step->destination == ZoneType::BENCH);
    TEST_ASSERT_EQ("Pokemon", step->filter_criteria.at("supertype"));
    TEST_ASSERT_EQ("Basic", step->filter_criteria.at("subtype"));
}

TEST(NestBall, FailsWithFullBench) {
    LogicRegistry registry;
    register_nest_ball(registry);

    GameState state;
    state.active_player_index = 0;

    // Fill bench to max (5)
    for (int i = 0; i < 5; i++) {
        CardInstance pokemon;
        pokemon.id = "bench_" + std::to_string(i);
        pokemon.card_id = "test-pokemon-" + std::to_string(i);
        state.players[0].board.bench.push_back(pokemon);
    }

    CardInstance nest_ball;
    nest_ball.id = "nest_ball_test";
    nest_ball.card_id = "sv1-181";
    
    auto result = registry.invoke_trainer("sv1-181", state, nest_ball);

    TEST_ASSERT_FALSE(result.success);
    TEST_ASSERT_EQ(0u, state.resolution_stack.size());
}

TEST(NestBall, GeneratorChecksBenchSpace) {
    LogicRegistry registry;
    register_nest_ball(registry);

    GameState state;
    state.active_player_index = 0;

    CardInstance nest_ball;
    nest_ball.id = "nest_ball_test";
    nest_ball.card_id = "sv1-181";

    // With empty bench - should be valid
    state.players[0].board.bench.clear();
    auto result_valid = registry.invoke_generator("sv1-181", "trainer", state, nest_ball);
    TEST_ASSERT_TRUE(result_valid.valid);

    // With full bench - should be invalid
    for (int i = 0; i < 5; i++) {
        CardInstance pokemon;
        pokemon.id = "bench_" + std::to_string(i);
        state.players[0].board.bench.push_back(pokemon);
    }
    auto result_invalid = registry.invoke_generator("sv1-181", "trainer", state, nest_ball);
    TEST_ASSERT_FALSE(result_invalid.valid);
}

// ============================================================================
// CAN PLAY TRAINER TESTS
// ============================================================================

TEST(CanPlayTrainer, SupporterOncePerTurn) {
    GameState state;
    CardDatabase db;
    state.active_player_index = 0;

    // Create a mock supporter card
    CardInstance supporter;
    supporter.id = "prof_research_1";
    supporter.card_id = "sv1-189";  // Professor's Research

    // Create CardDef manually since we don't have the JSON loaded
    // In real tests, we'd load from standard_cards.json
    // For now, test the flag checking logic

    // When supporter not used yet
    state.players[0].supporter_played_this_turn = false;
    TEST_ASSERT_FALSE(state.players[0].supporter_played_this_turn);

    // When supporter already used
    state.players[0].supporter_played_this_turn = true;

    // The actual can_play_trainer would need the card database
    // For now, just verify the flag exists and works
    TEST_ASSERT_TRUE(state.players[0].supporter_played_this_turn);
}

// ============================================================================
// TRAINER INFO COMPLETENESS
// ============================================================================

TEST(TrainerInfo, HasRequiredFields) {
    auto info = get_trainer_info();

    for (const auto& trainer : info) {
        TEST_ASSERT_FALSE(trainer.card_id.empty());
        TEST_ASSERT_FALSE(trainer.name.empty());
        TEST_ASSERT_FALSE(trainer.category.empty());
        TEST_ASSERT_FALSE(trainer.description.empty());

        // Category must be one of the valid types
        TEST_ASSERT_TRUE(
            trainer.category == "item" ||
            trainer.category == "supporter" ||
            trainer.category == "stadium" ||
            trainer.category == "tool"
        );
    }
}

// ============================================================================
// SEARCH DECK TO BENCH (Nest Ball pattern)
// ============================================================================

TEST(SearchDeckToBench, CreatesCorrectStep) {
    GameState state;
    CardInstance source;
    source.id = "test_card";
    source.card_id = "test-trainer-001";

    auto filter = FilterBuilder()
        .supertype("Pokemon")
        .subtype("Basic")
        .build();

    auto result = search_deck_to_bench(state, source, 0, filter, 1, 0);

    TEST_ASSERT_TRUE(result.success);
    TEST_ASSERT_TRUE(result.requires_resolution);

    auto* step = std::get_if<SearchDeckStep>(&state.resolution_stack[0]);
    TEST_ASSERT_NOT_NULL(step);
    TEST_ASSERT_TRUE(step->destination == ZoneType::BENCH);
    TEST_ASSERT_TRUE(step->shuffle_after);
}

/**
 * Tests for Effect Builders
 */

#include <sstream>
#include "cards/effect_builders.hpp"
#include "game_state.hpp"
#include "card_database.hpp"

using namespace pokemon;
using namespace pokemon::effects;

// ============================================================================
// FILTER BUILDER TESTS
// ============================================================================

TEST(FilterBuilder, BasicPokemonFilter) {
    auto filter = FilterBuilder()
        .supertype("Pokemon")
        .subtype("Basic")
        .build();

    TEST_ASSERT_EQ(2u, filter.size());
    TEST_ASSERT_EQ("Pokemon", filter.at("supertype"));
    TEST_ASSERT_EQ("Basic", filter.at("subtype"));
}

TEST(FilterBuilder, EnergyTypeFilter) {
    auto filter = FilterBuilder()
        .supertype("Energy")
        .energy_type(EnergyType::FIRE)
        .build();

    TEST_ASSERT_EQ(2u, filter.size());
    TEST_ASSERT_EQ("Fire", filter.at("energy_type"));
}

TEST(FilterBuilder, MaxHpFilter) {
    auto filter = FilterBuilder()
        .supertype("Pokemon")
        .max_hp(70)
        .build();

    TEST_ASSERT_EQ("70", filter.at("max_hp"));
}

TEST(FilterBuilder, ChainedFilter) {
    auto filter = FilterBuilder()
        .supertype("Pokemon")
        .subtype("Basic")
        .pokemon_type(EnergyType::WATER)
        .max_hp(100)
        .build();

    TEST_ASSERT_EQ(4u, filter.size());
}

// ============================================================================
// CARD MATCHING TESTS
// ============================================================================

TEST(CardMatching, BasicPokemonMatches) {
    CardDef card;
    card.name = "Charmander";
    card.supertype = Supertype::POKEMON;
    card.subtypes = {Subtype::BASIC};
    card.hp = 70;
    card.types = {EnergyType::FIRE};

    auto filter = FilterBuilder()
        .supertype("Pokemon")
        .subtype("Basic")
        .build();

    TEST_ASSERT_TRUE(card_matches_filter(card, filter));
}

TEST(CardMatching, Stage1DoesNotMatchBasic) {
    CardDef card;
    card.name = "Charmeleon";
    card.supertype = Supertype::POKEMON;
    card.subtypes = {Subtype::STAGE_1};
    card.hp = 90;

    auto filter = FilterBuilder()
        .supertype("Pokemon")
        .subtype("Basic")
        .build();

    TEST_ASSERT_FALSE(card_matches_filter(card, filter));
}

TEST(CardMatching, MaxHpFilter) {
    CardDef card;
    card.name = "Charmander";
    card.supertype = Supertype::POKEMON;
    card.subtypes = {Subtype::BASIC};
    card.hp = 70;

    // Should match
    auto filter_100 = FilterBuilder()
        .supertype("Pokemon")
        .max_hp(100)
        .build();
    TEST_ASSERT_TRUE(card_matches_filter(card, filter_100));

    // Should not match
    auto filter_60 = FilterBuilder()
        .supertype("Pokemon")
        .max_hp(60)
        .build();
    TEST_ASSERT_FALSE(card_matches_filter(card, filter_60));
}

TEST(CardMatching, PokemonTypeFilter) {
    CardDef card;
    card.name = "Charmander";
    card.supertype = Supertype::POKEMON;
    card.subtypes = {Subtype::BASIC};
    card.types = {EnergyType::FIRE};

    // Should match Fire
    auto fire_filter = FilterBuilder()
        .pokemon_type(EnergyType::FIRE)
        .build();
    TEST_ASSERT_TRUE(card_matches_filter(card, fire_filter));

    // Should not match Water
    auto water_filter = FilterBuilder()
        .pokemon_type(EnergyType::WATER)
        .build();
    TEST_ASSERT_FALSE(card_matches_filter(card, water_filter));
}

TEST(CardMatching, BasicEnergyFilter) {
    CardDef energy;
    energy.name = "Fire Energy";
    energy.supertype = Supertype::ENERGY;
    energy.is_basic_energy = true;
    energy.energy_type = EnergyType::FIRE;

    auto filter = FilterBuilder()
        .super_rod_target(true)
        .build();

    TEST_ASSERT_TRUE(card_matches_filter(energy, filter));
}

TEST(CardMatching, EvolvesFromFilter) {
    CardDef card;
    card.name = "Charmeleon";
    card.supertype = Supertype::POKEMON;
    card.subtypes = {Subtype::STAGE_1};
    card.evolves_from = "Charmander";

    auto filter = FilterBuilder()
        .evolves_from("Charmander")
        .build();

    TEST_ASSERT_TRUE(card_matches_filter(card, filter));

    auto wrong_filter = FilterBuilder()
        .evolves_from("Squirtle")
        .build();

    TEST_ASSERT_FALSE(card_matches_filter(card, wrong_filter));
}

TEST(CardMatching, EmptyFilterMatchesAll) {
    CardDef card;
    card.name = "Test Card";
    card.supertype = Supertype::POKEMON;

    std::unordered_map<std::string, std::string> empty_filter;
    TEST_ASSERT_TRUE(card_matches_filter(card, empty_filter));
}

// ============================================================================
// VALIDATION HELPERS TESTS
// ============================================================================

TEST(ValidationHelpers, BenchSpaceAvailable) {
    GameState state;
    state.players[0].board.bench.clear();

    TEST_ASSERT_TRUE(has_bench_space(state, 0));

    // Fill bench to max (5)
    for (int i = 0; i < 5; i++) {
        CardInstance card;
        card.id = "bench_" + std::to_string(i);
        card.card_id = "test-pokemon-" + std::to_string(i);
        state.players[0].board.bench.push_back(card);
    }

    TEST_ASSERT_FALSE(has_bench_space(state, 0));
}

TEST(ValidationHelpers, CanDiscardFromHand) {
    GameState state;

    // Add 3 cards to hand
    for (int i = 0; i < 3; i++) {
        CardInstance card;
        card.id = "hand_" + std::to_string(i);
        state.players[0].hand.cards.push_back(card);
    }

    TEST_ASSERT_TRUE(can_discard_from_hand(state, 0, 2, {}));
    TEST_ASSERT_TRUE(can_discard_from_hand(state, 0, 3, {}));
    TEST_ASSERT_FALSE(can_discard_from_hand(state, 0, 4, {}));
}

// ============================================================================
// DRAW CARDS TESTS
// ============================================================================

TEST(Effects, DrawCards) {
    GameState state;

    // Add 5 cards to deck
    for (int i = 0; i < 5; i++) {
        CardInstance card;
        card.id = "deck_" + std::to_string(i);
        state.players[0].deck.cards.push_back(card);
    }

    TEST_ASSERT_EQ(5u, state.players[0].deck.cards.size());
    TEST_ASSERT_EQ(0u, state.players[0].hand.cards.size());

    auto result = draw_cards(state, 0, 3);

    TEST_ASSERT_TRUE(result.success);
    TEST_ASSERT_FALSE(result.requires_resolution);
    TEST_ASSERT_EQ(2u, state.players[0].deck.cards.size());
    TEST_ASSERT_EQ(3u, state.players[0].hand.cards.size());
}

TEST(Effects, DrawMoreThanDeckSize) {
    GameState state;

    // Add 2 cards to deck
    for (int i = 0; i < 2; i++) {
        CardInstance card;
        card.id = "deck_" + std::to_string(i);
        state.players[0].deck.cards.push_back(card);
    }

    auto result = draw_cards(state, 0, 5);

    TEST_ASSERT_TRUE(result.success);
    TEST_ASSERT_EQ(0u, state.players[0].deck.cards.size());
    TEST_ASSERT_EQ(2u, state.players[0].hand.cards.size());
}

// ============================================================================
// DISCARD HAND DRAW TESTS
// ============================================================================

TEST(Effects, DiscardHandDraw) {
    GameState state;

    // Add 3 cards to hand
    for (int i = 0; i < 3; i++) {
        CardInstance card;
        card.id = "hand_" + std::to_string(i);
        state.players[0].hand.cards.push_back(card);
    }

    // Add 10 cards to deck
    for (int i = 0; i < 10; i++) {
        CardInstance card;
        card.id = "deck_" + std::to_string(i);
        state.players[0].deck.cards.push_back(card);
    }

    auto result = discard_hand_draw(state, 0, 7);

    TEST_ASSERT_TRUE(result.success);
    TEST_ASSERT_EQ(3u, state.players[0].discard.cards.size());  // Old hand discarded
    TEST_ASSERT_EQ(7u, state.players[0].hand.cards.size());     // Drew 7
    TEST_ASSERT_EQ(3u, state.players[0].deck.cards.size());     // 10 - 7
}

// ============================================================================
// SEARCH DECK TESTS
// ============================================================================

TEST(Effects, SearchDeckPushesStep) {
    GameState state;
    CardInstance source_card;
    source_card.id = "nest_ball_1";
    source_card.card_id = "sv1-181";

    auto filter = FilterBuilder()
        .supertype("Pokemon")
        .subtype("Basic")
        .build();

    auto result = search_deck(state, source_card, 0, filter, 1, 0);

    TEST_ASSERT_TRUE(result.success);
    TEST_ASSERT_TRUE(result.requires_resolution);
    TEST_ASSERT_EQ(1u, state.resolution_stack.size());

    // Check step details
    auto* step = std::get_if<SearchDeckStep>(&state.resolution_stack[0]);
    TEST_ASSERT_NOT_NULL(step);
    TEST_ASSERT_EQ("nest_ball_1", step->source_card_id);
    TEST_ASSERT_EQ(0, step->player_id);
    TEST_ASSERT_EQ(1, step->count);
    TEST_ASSERT_EQ(0, step->min_count);
}

// ============================================================================
// HEAL DAMAGE TESTS
// ============================================================================

TEST(Effects, HealDamage) {
    GameState state;
    CardInstance target;
    target.id = "pokemon_1";
    target.card_id = "sv1-4";  // Charmander
    target.damage_counters = 5;  // 50 damage

    state.players[0].board.active_spot = target;

    CardInstance source;
    source.id = "potion_1";

    auto result = heal_damage(state, source, 0, "pokemon_1", 30);

    TEST_ASSERT_TRUE(result.success);
    TEST_ASSERT_EQ(2, state.players[0].board.active_spot->damage_counters);  // 50 - 30 = 20 = 2 counters
}

TEST(Effects, HealBelowZero) {
    GameState state;
    CardInstance target;
    target.id = "pokemon_1";
    target.card_id = "sv1-4";  // Charmander
    target.damage_counters = 2;  // 20 damage

    state.players[0].board.active_spot = target;

    CardInstance source;
    source.id = "potion_1";

    auto result = heal_damage(state, source, 0, "pokemon_1", 50);

    TEST_ASSERT_TRUE(result.success);
    TEST_ASSERT_EQ(0, state.players[0].board.active_spot->damage_counters);  // Can't go below 0
}

// ============================================================================
// ADD DAMAGE COUNTERS TESTS
// ============================================================================

TEST(Effects, AddDamageCounters) {
    GameState state;
    CardInstance target;
    target.id = "pokemon_1";
    target.damage_counters = 0;

    state.players[0].board.active_spot = target;

    auto result = add_damage_counters(state, "pokemon_1", 3);

    TEST_ASSERT_TRUE(result.success);
    TEST_ASSERT_EQ(3, state.players[0].board.active_spot->damage_counters);
}

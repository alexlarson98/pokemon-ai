"""
Comprehensive pytest suite for deck search cards.

Tests:
- Ultra Ball (discard 2, search any Pokemon)
- Nest Ball (search Basic Pokemon to bench)
- Buddy-Buddy Poffin (search up to 2 Basic Pokemon with HP <= 70)
- Fail search options
- Search with belief placeholders
- Perfect knowledge integration

NOTE: Tests use action.parameters to verify search targets, NOT display_label strings.
This ensures we're testing actual data, not just UI text.
"""

import pytest
import sys
sys.path.insert(0, 'src')

from models import GameState, PlayerState, GamePhase, Action, ActionType
from engine import PokemonEngine
from cards.factory import create_card_instance
from cards.library.trainers import (
    ultra_ball_actions, ultra_ball_effect,
    nest_ball_actions, nest_ball_effect,
    buddy_buddy_poffin_actions, buddy_buddy_poffin_effect
)
from cards.base import Subtype
from cards.registry import create_card


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_search_target_id(action):
    """Extract search target ID from an action, handling different parameter names."""
    if not action.parameters:
        return None
    # Ultra Ball uses 'search_target_id', Nest Ball uses 'target_pokemon_id'
    return action.parameters.get('search_target_id') or action.parameters.get('target_pokemon_id')


def get_actions_targeting_card_name(actions, card_name, deck_cards):
    """
    Get actions that target a specific Pokemon by name using parameter data.

    Args:
        actions: List of actions to filter
        card_name: Name of the Pokemon to find (e.g., "Pidgey")
        deck_cards: List of card instances in the deck

    Returns:
        List of actions that target the given Pokemon name
    """
    # Build map of instance_id -> card_name for deck cards
    deck_id_to_name = {}
    for card in deck_cards:
        card_def = create_card(card.card_id)
        if card_def:
            deck_id_to_name[card.id] = card_def.name

    matching_actions = []
    for action in actions:
        target_id = get_search_target_id(action)
        if target_id and target_id in deck_id_to_name:
            if deck_id_to_name[target_id] == card_name:
                matching_actions.append(action)
        elif target_id and target_id.startswith('belief:'):
            # Belief placeholder format: 'belief:CardName'
            belief_name = target_id.split(':', 1)[1]
            if belief_name == card_name:
                matching_actions.append(action)

    return matching_actions


def has_fail_search_action(actions):
    """Check if there's a fail search action (target_id is None)."""
    for action in actions:
        target_id = get_search_target_id(action)
        if target_id is None:
            return True
    return False


def get_poffin_target_ids(action):
    """Get target Pokemon IDs from Buddy-Buddy Poffin action."""
    if not action.parameters:
        return []
    return action.parameters.get('target_pokemon_ids', [])


@pytest.fixture
def engine():
    """Create PokemonEngine instance."""
    return PokemonEngine()


@pytest.fixture
def basic_game_state():
    """Create basic game state for testing."""
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
    player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

    # Add Pokemon to deck
    player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))  # Pidgey (Basic)
    player0.deck.add_card(create_card_instance("sv4pt5-7", owner_id=0))   # Charmander (Basic)

    return GameState(
        players=[player0, player1],
        turn_count=1,
        active_player_index=0,
        current_phase=GamePhase.MAIN,
        starting_player_id=0
    )


class TestUltraBall:
    """Test Ultra Ball card mechanics."""

    def test_ultra_ball_requires_two_discard_cards(self, basic_game_state):
        """Ultra Ball requires 2 cards in hand to discard."""
        state = basic_game_state
        player = state.players[0]

        ultra_ball = create_card_instance("sv5-162", owner_id=0)
        player.hand.add_card(ultra_ball)

        # Only add 1 card (need 2)
        player.hand.add_card(create_card_instance("sv5-163", owner_id=0))

        actions = ultra_ball_actions(state, ultra_ball, player)

        # Should return empty list (not enough cards to discard)
        assert len(actions) == 0, "Ultra Ball requires 2 cards to discard"

    def test_ultra_ball_action_generation(self, engine, basic_game_state):
        """Ultra Ball should generate search actions for Pokemon in deck."""
        state = basic_game_state
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        ultra_ball = create_card_instance("sv5-162", owner_id=0)
        player.hand.add_card(ultra_ball)

        # Add 2 discard cards
        player.hand.add_card(create_card_instance("sv5-163", owner_id=0))
        player.hand.add_card(create_card_instance("sv5-191", owner_id=0))

        actions = ultra_ball_actions(state, ultra_ball, player)

        # Should generate actions for Pidgey and Charmander
        assert len(actions) > 0, "Should generate Ultra Ball actions"

        # Use parameter data to verify search targets, not display_label strings
        pidgey_actions = get_actions_targeting_card_name(actions, "Pidgey", player.deck.cards)
        charmander_actions = get_actions_targeting_card_name(actions, "Charmander", player.deck.cards)

        assert len(pidgey_actions) > 0, "Should have action to search Pidgey"
        assert len(charmander_actions) > 0, "Should have action to search Charmander"

    def test_ultra_ball_fail_search_option(self, engine, basic_game_state):
        """Ultra Ball should have a 'fail search' option."""
        state = basic_game_state
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        ultra_ball = create_card_instance("sv5-162", owner_id=0)
        player.hand.add_card(ultra_ball)

        player.hand.add_card(create_card_instance("sv5-163", owner_id=0))
        player.hand.add_card(create_card_instance("sv5-191", owner_id=0))

        actions = ultra_ball_actions(state, ultra_ball, player)

        # Should have fail search option (target_id is None)
        assert has_fail_search_action(actions), "Should have fail search option"

    def test_ultra_ball_effect_discards_cards(self, engine, basic_game_state):
        """Ultra Ball effect should discard 2 cards."""
        state = basic_game_state
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        ultra_ball = create_card_instance("sv5-162", owner_id=0)
        discard1 = create_card_instance("sv5-163", owner_id=0)
        discard2 = create_card_instance("sv5-191", owner_id=0)

        player.hand.add_card(discard1)
        player.hand.add_card(discard2)

        pidgey = player.deck.cards[0]

        # Create action with discard IDs
        action = Action(
            action_type=ActionType.PLAY_ITEM,
            player_id=0,
            card_id=ultra_ball.id,
            parameters={
                'discard_ids': [discard1.id, discard2.id],
                'search_target_id': pidgey.id
            }
        )

        initial_discard_count = player.discard.count()

        # Execute effect
        state = ultra_ball_effect(state, ultra_ball, action)
        player = state.players[0]

        # Should have discarded 2 cards
        assert player.discard.count() == initial_discard_count + 2, "Should discard 2 cards"


class TestNestBall:
    """Test Nest Ball card mechanics."""

    def test_nest_ball_searches_basic_pokemon(self, engine, basic_game_state):
        """Nest Ball should search for Basic Pokemon."""
        state = basic_game_state
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        nest_ball = create_card_instance("sv1-181", owner_id=0)
        player.hand.add_card(nest_ball)

        actions = nest_ball_actions(state, nest_ball, player)

        # Should generate actions for Basic Pokemon
        assert len(actions) > 0, "Should generate Nest Ball actions"

        # Use parameter data to verify search targets
        pidgey_actions = get_actions_targeting_card_name(actions, "Pidgey", player.deck.cards)
        assert len(pidgey_actions) > 0, "Should have action to search Basic Pokemon"

    def test_nest_ball_adds_to_bench(self, engine, basic_game_state):
        """Nest Ball should add Pokemon to bench."""
        state = basic_game_state
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        nest_ball = create_card_instance("sv1-181", owner_id=0)
        pidgey = player.deck.cards[0]

        initial_bench_count = player.board.get_bench_count()

        action = Action(
            action_type=ActionType.PLAY_ITEM,
            player_id=0,
            card_id=nest_ball.id,
            parameters={'target_pokemon_id': pidgey.id}
        )

        state = nest_ball_effect(state, nest_ball, action)
        player = state.players[0]

        # Should have added Pokemon to bench
        assert player.board.get_bench_count() == initial_bench_count + 1, \
            "Should add Pokemon to bench"

    def test_nest_ball_fail_search(self, engine, basic_game_state):
        """Nest Ball should support fail search (target_pokemon_id=None)."""
        state = basic_game_state
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        nest_ball = create_card_instance("sv1-181", owner_id=0)

        action = Action(
            action_type=ActionType.PLAY_ITEM,
            player_id=0,
            card_id=nest_ball.id,
            parameters={'target_pokemon_id': None}  # Fail search
        )

        initial_bench_count = player.board.get_bench_count()

        # Execute effect (should not fail)
        state = nest_ball_effect(state, nest_ball, action)
        player = state.players[0]

        # Bench count should not change
        assert player.board.get_bench_count() == initial_bench_count


class TestBuddyBuddyPoffin:
    """Test Buddy-Buddy Poffin card mechanics."""

    def test_poffin_searches_basic_hp_70_or_less(self, engine):
        """Buddy-Buddy Poffin should search for Basic Pokemon with HP <= 70."""
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        # Add Pokemon with HP <= 70
        player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))  # Pidgey HP=50
        player0.deck.add_card(create_card_instance("sv4pt5-7", owner_id=0))   # Charmander HP=70

        state = GameState(
            players=[player0, player1],
            turn_count=1,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        poffin = create_card_instance("sv3pt5-144", owner_id=0)
        player.hand.add_card(poffin)

        actions = buddy_buddy_poffin_actions(state, poffin, player)

        # Should generate pair actions
        assert len(actions) > 0, "Should generate Buddy-Buddy Poffin actions"

        # Build deck map for verification
        deck_id_to_name = {c.id: create_card(c.card_id).name for c in player.deck.cards}

        # Verify at least one action targets Pidgey and/or Charmander using parameter data
        found_valid_pair = False
        for action in actions:
            target_ids = get_poffin_target_ids(action)
            target_names = [deck_id_to_name.get(tid) for tid in target_ids if tid in deck_id_to_name]
            if "Pidgey" in target_names or "Charmander" in target_names:
                found_valid_pair = True
                break

        assert found_valid_pair, "Should have pair actions targeting Pidgey or Charmander"

    def test_poffin_adds_up_to_two_pokemon(self, engine):
        """Buddy-Buddy Poffin should add up to 2 Pokemon to bench."""
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv3pt5-16", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        pidgey1 = create_card_instance("sv3pt5-16", owner_id=0)
        pidgey2 = create_card_instance("sv3pt5-16", owner_id=0)
        player0.deck.add_card(pidgey1)
        player0.deck.add_card(pidgey2)

        state = GameState(
            players=[player0, player1],
            turn_count=1,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        player = state.players[0]
        poffin = create_card_instance("sv3pt5-144", owner_id=0)

        initial_bench_count = player.board.get_bench_count()

        action = Action(
            action_type=ActionType.PLAY_ITEM,
            player_id=0,
            card_id=poffin.id,
            parameters={'target_pokemon_ids': [pidgey1.id, pidgey2.id]}
        )

        state = buddy_buddy_poffin_effect(state, poffin, action)
        player = state.players[0]

        # Should add 2 Pokemon to bench
        assert player.board.get_bench_count() == initial_bench_count + 2, \
            "Should add 2 Pokemon to bench"


class TestSearchCardsWithBeliefSystem:
    """Test deck search cards with belief system integration."""

    def test_ultra_ball_with_belief_placeholder(self, engine):
        """Ultra Ball should work with belief placeholders."""
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        player0.board.active_spot = create_card_instance("sv4pt5-7", owner_id=0)
        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        # Add Klefki to prizes (hidden)
        klefki = create_card_instance("sv1-96", owner_id=0)
        player0.prizes.add_card(klefki)

        # Add Pidgey to deck
        player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))

        state = GameState(
            players=[player0, player1],
            turn_count=1,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        ultra_ball = create_card_instance("sv5-162", owner_id=0)
        player.hand.add_card(ultra_ball)
        player.hand.add_card(create_card_instance("sv5-163", owner_id=0))
        player.hand.add_card(create_card_instance("sv5-191", owner_id=0))

        actions = ultra_ball_actions(state, ultra_ball, player)

        # Should create action for Klefki (via belief placeholder)
        # Use parameter data to find belief placeholder targeting Klefki
        klefki_actions = get_actions_targeting_card_name(actions, "Klefki", player.deck.cards)
        assert len(klefki_actions) > 0, "Should create belief-based action for Klefki"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

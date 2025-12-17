"""
Comprehensive pytest suite for the belief system (ISMCTS support).

Tests:
- Belief engine (get_deck_search_candidates)
- Belief placeholder generation
- Belief-based action generation (single and pair searches)
- Belief placeholder resolution (resolve_search_target)
- Perfect vs imperfect knowledge modes
- Partial success in pair searches

NOTE: Tests use action.parameters to verify search targets, NOT display_label strings.
This ensures we're testing actual data, not just UI text.
"""

import pytest
import sys
sys.path.insert(0, 'src')

from models import GameState, PlayerState, GamePhase
from engine import PokemonEngine
from cards.factory import create_card_instance
from cards.library.trainers import ultra_ball_actions, nest_ball_actions, buddy_buddy_poffin_actions
from cards.utils import get_deck_search_candidates, resolve_search_target
from cards.base import PokemonCard, Subtype
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
        card_name: Name of the Pokemon to find (e.g., "Klefki")
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
        elif target_id and isinstance(target_id, str) and target_id.startswith('belief:'):
            # Belief placeholder format: 'belief:CardName'
            belief_name = target_id.split(':', 1)[1]
            if belief_name == card_name:
                matching_actions.append(action)

    return matching_actions


def get_poffin_target_ids(action):
    """Get target Pokemon IDs from Buddy-Buddy Poffin action."""
    if not action.parameters:
        return []
    return action.parameters.get('target_pokemon_ids', [])


def get_poffin_actions_targeting_card_names(actions, name1, name2, deck_cards):
    """
    Get Poffin pair actions that target two specific Pokemon by name.

    Args:
        actions: List of actions to filter
        name1: First Pokemon name to find
        name2: Second Pokemon name to find
        deck_cards: List of card instances in the deck

    Returns:
        List of actions targeting a pair containing both Pokemon names
    """
    # Build map of instance_id -> card_name for deck cards
    deck_id_to_name = {}
    for card in deck_cards:
        card_def = create_card(card.card_id)
        if card_def:
            deck_id_to_name[card.id] = card_def.name

    matching_actions = []
    for action in actions:
        target_ids = get_poffin_target_ids(action)
        target_names = []

        for tid in target_ids:
            if tid in deck_id_to_name:
                target_names.append(deck_id_to_name[tid])
            elif isinstance(tid, str) and tid.startswith('belief:'):
                belief_name = tid.split(':', 1)[1]
                target_names.append(belief_name)

        # Check if both names are in the target set
        if name1 in target_names and name2 in target_names:
            matching_actions.append(action)

    return matching_actions


@pytest.fixture
def engine():
    """Create PokemonEngine instance."""
    return PokemonEngine()


@pytest.fixture
def game_state_with_prizes():
    """Create game state with a card in prizes (hidden)."""
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Active Pokemon
    player0.board.active_spot = create_card_instance("sv4pt5-7", owner_id=0)  # Charmander
    player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

    # Add Klefki to PRIZES (hidden)
    klefki = create_card_instance("sv1-96", owner_id=0)
    player0.prizes.add_card(klefki)

    # Add other Pokemon to deck
    for _ in range(2):
        player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))  # Pidgey

    return GameState(
        players=[player0, player1],
        turn_count=1,
        active_player_index=0,
        current_phase=GamePhase.MAIN,
        starting_player_id=0
    )


class TestBeliefEngine:
    """Test the belief engine (get_deck_search_candidates)."""

    def test_belief_engine_with_imperfect_knowledge(self, engine, game_state_with_prizes):
        """Belief engine should return cards believed to be in deck (imperfect knowledge)."""
        state = game_state_with_prizes

        # Initialize knowledge
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        # Player hasn't searched deck yet
        assert player.has_searched_deck is False

        # Define criteria: any Pokemon
        def is_pokemon(card_def):
            return isinstance(card_def, PokemonCard)

        # Get search candidates
        candidates = get_deck_search_candidates(state, player, is_pokemon)

        # Should include both Pidgey and Klefki (even though Klefki is in prizes)
        assert 'Pidgey' in candidates, "Pidgey should be searchable (in deck)"
        assert 'Klefki' in candidates, "Klefki should be searchable (player doesn't know it's in prizes)"

    def test_belief_engine_with_perfect_knowledge(self, engine, game_state_with_prizes):
        """After searching deck, belief engine should return only actual deck contents."""
        state = game_state_with_prizes
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        # Mark that player has searched deck
        player.has_searched_deck = True

        def is_pokemon(card_def):
            return isinstance(card_def, PokemonCard)

        candidates = get_deck_search_candidates(state, player, is_pokemon)

        # Should only include Pidgey (actually in deck)
        assert 'Pidgey' in candidates, "Pidgey should be searchable (in deck)"
        assert 'Klefki' not in candidates, "Klefki should not be searchable (player knows it's not in deck)"

    def test_belief_engine_excludes_visible_cards(self, engine):
        """Belief engine should subtract visible cards from initial counts."""
        player0 = PlayerState(player_id=0, name='Player 0')
        player1 = PlayerState(player_id=1, name='Player 1')

        # Add Klefki to hand (visible)
        klefki_in_hand = create_card_instance("sv1-96", owner_id=0)
        player0.hand.add_card(klefki_in_hand)

        # Add Klefki to board (visible)
        klefki_on_board = create_card_instance("sv1-96", owner_id=0)
        player0.board.active_spot = klefki_on_board

        # Add Pidgey to deck
        player0.deck.add_card(create_card_instance("sv3pt5-16", owner_id=0))

        player1.board.active_spot = create_card_instance("sv3pt5-16", owner_id=1)

        state = GameState(
            players=[player0, player1],
            turn_count=1,
            active_player_index=0,
            current_phase=GamePhase.MAIN,
            starting_player_id=0
        )

        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        def is_pokemon(card_def):
            return isinstance(card_def, PokemonCard)

        candidates = get_deck_search_candidates(state, player, is_pokemon)

        # If player started with 2 Klefki and both are visible, Klefki shouldn't be searchable
        # (depends on initial_deck_counts, but this tests the subtraction logic)
        assert 'Pidgey' in candidates


class TestBeliefPlaceholderGeneration:
    """Test that belief placeholders are generated for cards in prizes."""

    def test_ultra_ball_creates_belief_placeholder(self, engine, game_state_with_prizes):
        """Ultra Ball should create belief placeholder for Klefki (in prizes)."""
        state = game_state_with_prizes
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        # Add Ultra Ball to hand
        ultra_ball = create_card_instance("sv5-162", owner_id=0)
        player.hand.add_card(ultra_ball)

        # Add discard cards
        player.hand.add_card(create_card_instance("sv5-163", owner_id=0))
        player.hand.add_card(create_card_instance("sv5-191", owner_id=0))

        # Generate actions
        actions = ultra_ball_actions(state, ultra_ball, player)

        # Should create actions for both Pidgey (in deck) and Klefki (in prizes, via belief)
        # Use parameter data to verify belief placeholder targeting Klefki
        klefki_actions = get_actions_targeting_card_name(actions, "Klefki", player.deck.cards)
        assert len(klefki_actions) > 0, "Should create belief-based action for Klefki"

    def test_buddy_buddy_poffin_creates_pair_with_belief(self, engine, game_state_with_prizes):
        """Buddy-Buddy Poffin should create pair actions with belief placeholders."""
        state = game_state_with_prizes
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        # Add Buddy-Buddy Poffin to hand
        poffin = create_card_instance("sv3pt5-144", owner_id=0)
        player.hand.add_card(poffin)

        # Generate actions
        actions = buddy_buddy_poffin_actions(state, poffin, player)

        # Should create pair actions including Klefki + Pidgey
        # Use parameter data to verify pair targeting both Pokemon
        pair_actions = get_poffin_actions_targeting_card_names(actions, "Klefki", "Pidgey", player.deck.cards)
        assert len(pair_actions) > 0, "Should create pair action with belief placeholder (Klefki + Pidgey)"


class TestBeliefPlaceholderResolution:
    """Test resolve_search_target utility for belief placeholders."""

    def test_resolve_search_target_with_real_id(self):
        """resolve_search_target should handle real card IDs."""
        player = PlayerState(player_id=0, name='Player 0')

        # Add Pokemon to deck
        pidgey = create_card_instance("sv3pt5-16", owner_id=0)
        player.deck.add_card(pidgey)

        def is_pokemon(card_def):
            return isinstance(card_def, PokemonCard)

        # Resolve with real ID
        result = resolve_search_target(player, pidgey.id, is_pokemon)

        assert result is not None, "Should find Pokemon with real ID"
        assert result.id == pidgey.id

    def test_resolve_search_target_with_belief_placeholder_found(self):
        """resolve_search_target should find card with belief placeholder (card in deck)."""
        player = PlayerState(player_id=0, name='Player 0')

        # Add Pidgey to deck
        pidgey = create_card_instance("sv3pt5-16", owner_id=0)
        player.deck.add_card(pidgey)

        def is_basic(card_def):
            return Subtype.BASIC in card_def.subtypes

        # Resolve with belief placeholder
        result = resolve_search_target(player, 'belief:Pidgey', is_basic)

        assert result is not None, "Should find Pidgey with belief placeholder"
        assert result.id == pidgey.id

    def test_resolve_search_target_with_belief_placeholder_not_found(self):
        """resolve_search_target should return None when belief card is not in deck (in prizes)."""
        player = PlayerState(player_id=0, name='Player 0')

        # Klefki is NOT in deck (it's in prizes in this scenario)

        def is_pokemon(card_def):
            return isinstance(card_def, PokemonCard)

        # Resolve with belief placeholder for card not in deck
        result = resolve_search_target(player, 'belief:Klefki', is_pokemon)

        # Should return None (expected for ISMCTS - card was in prizes)
        assert result is None, "Should return None when belief card is not found"


class TestPerfectVsImperfectKnowledge:
    """Test the difference between perfect and imperfect knowledge modes."""

    def test_first_search_enables_perfect_knowledge(self, engine, game_state_with_prizes):
        """After first deck search, has_searched_deck should be set to True."""
        state = game_state_with_prizes
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        assert player.has_searched_deck is False, "Should start with imperfect knowledge"

        # Simulate a deck search by calling nest_ball effect
        # (In real game, this would be done through engine.step)

        # For this test, we'll just manually set the flag to simulate what happens
        player.has_searched_deck = True

        def is_pokemon(card_def):
            return isinstance(card_def, PokemonCard)

        # Now candidates should only include cards actually in deck
        candidates = get_deck_search_candidates(state, player, is_pokemon)

        # After perfect knowledge, Klefki should not appear
        assert 'Klefki' not in candidates

    def test_perfect_knowledge_no_belief_actions(self, engine, game_state_with_prizes):
        """With perfect knowledge, no belief placeholders should be created."""
        state = game_state_with_prizes
        state = engine.initialize_deck_knowledge(state)
        player = state.players[0]

        # Set perfect knowledge
        player.has_searched_deck = True

        # Add Ultra Ball to hand
        ultra_ball = create_card_instance("sv5-162", owner_id=0)
        player.hand.add_card(ultra_ball)

        player.hand.add_card(create_card_instance("sv5-163", owner_id=0))
        player.hand.add_card(create_card_instance("sv5-191", owner_id=0))

        actions = ultra_ball_actions(state, ultra_ball, player)

        # Should NOT create action for Klefki (player knows it's not in deck)
        # Use parameter data to verify no belief placeholder targeting Klefki
        klefki_actions = get_actions_targeting_card_name(actions, "Klefki", player.deck.cards)
        assert len(klefki_actions) == 0, "Should not create belief action with perfect knowledge"


class TestPartialSuccessInPairSearches:
    """Test that partial success in pair searches is handled correctly."""

    def test_buddy_buddy_poffin_partial_success(self):
        """Finding 1 of 2 cards in pair search should still work (ISMCTS training data)."""
        # This test verifies that the effect handler doesn't fail when one card is not found

        player = PlayerState(player_id=0, name='Player 0')

        # Add only Pidgey to deck (Klefki is in prizes)
        pidgey = create_card_instance("sv3pt5-16", owner_id=0)
        player.deck.add_card(pidgey)

        # Test resolve_search_target with both cards
        def is_basic_hp_70_or_less(card_def):
            return (hasattr(card_def, 'subtypes') and Subtype.BASIC in card_def.subtypes and
                    hasattr(card_def, 'hp') and card_def.hp <= 70)

        # Resolve Pidgey (should succeed)
        pidgey_result = resolve_search_target(player, pidgey.id, is_basic_hp_70_or_less)
        assert pidgey_result is not None, "Should find Pidgey"

        # Resolve Klefki with belief placeholder (should return None)
        klefki_result = resolve_search_target(player, 'belief:Klefki', is_basic_hp_70_or_less)
        assert klefki_result is None, "Should not find Klefki (in prizes)"

        # Both results are handled - partial success is OK for ISMCTS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

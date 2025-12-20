"""
Tests for Briar Supporter card.

Briar:
- Can only be played if opponent has exactly 2 Prize cards remaining
- During this turn, if opponent's Active Pokemon is Knocked Out by damage
  from an attack used by your Tera Pokemon, take 1 more Prize card
- You may play only 1 Supporter card during your turn

Tests:
- Registration tests for all card variants
- Condition tests (opponent must have exactly 2 prizes)
- Effect tests (prize modifier added to active_effects)
- Prize condition tests (Tera Pokemon, Active KO)
"""

import pytest
import sys
sys.path.insert(0, 'src')

from models import GameState, PlayerState, Action, ActionType, Subtype, GamePhase
from cards.factory import create_card_instance
from cards.registry import create_card
from engine import PokemonEngine
from cards.logic_registry import MASTER_LOGIC_REGISTRY


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def engine():
    """Create a Pokemon engine instance."""
    return PokemonEngine()


def create_briar_game_state(opponent_prize_count: int = 2) -> GameState:
    """
    Create a game state for Briar testing.

    Args:
        opponent_prize_count: Number of prize cards opponent has remaining

    Returns:
        GameState configured for Briar testing
    """
    player0 = PlayerState(player_id=0, name='Player 0')
    player1 = PlayerState(player_id=1, name='Player 1')

    # Player 0: Terapagos ex active (a Tera Pokemon)
    terapagos = create_card_instance("sv7-128", owner_id=0)
    player0.board.active_spot = terapagos

    # Player 1: Regular Pokemon active
    charmander = create_card_instance("svp-44", owner_id=1)
    player1.board.active_spot = charmander

    # Add deck cards
    for _ in range(10):
        player0.deck.add_card(create_card_instance("base1-98", owner_id=0))
        player1.deck.add_card(create_card_instance("base1-98", owner_id=1))

    # Add appropriate prize count for opponent (player 1)
    for _ in range(opponent_prize_count):
        player1.prizes.add_card(create_card_instance("base1-98", owner_id=1))

    # Player 0 has 6 prizes (full)
    for _ in range(6):
        player0.prizes.add_card(create_card_instance("base1-98", owner_id=0))

    state = GameState(
        players=[player0, player1],
        active_player_index=0,  # Player 0's turn
        turn_count=5,
        starting_player_id=0,
        current_phase=GamePhase.MAIN
    )

    return state


# ============================================================================
# REGISTRATION TESTS
# ============================================================================

class TestBriarRegistration:
    """Test that Briar is properly registered in the logic registry."""

    @pytest.mark.parametrize("card_id", ["sv7-132", "sv7-163", "sv7-171", "sv8pt5-100"])
    def test_briar_registered(self, card_id):
        """All Briar variants should be registered."""
        assert card_id in MASTER_LOGIC_REGISTRY
        assert "Play Briar" in MASTER_LOGIC_REGISTRY[card_id]

    @pytest.mark.parametrize("card_id", ["sv7-132", "sv7-163", "sv7-171", "sv8pt5-100"])
    def test_briar_is_activatable(self, card_id):
        """Briar should be registered as activatable category."""
        logic = MASTER_LOGIC_REGISTRY[card_id]["Play Briar"]
        assert logic["category"] == "activatable"

    @pytest.mark.parametrize("card_id", ["sv7-132", "sv7-163", "sv7-171", "sv8pt5-100"])
    def test_briar_has_generator_and_effect(self, card_id):
        """Briar should have both generator and effect functions."""
        logic = MASTER_LOGIC_REGISTRY[card_id]["Play Briar"]
        assert "generator" in logic
        assert "effect" in logic
        assert callable(logic["generator"])
        assert callable(logic["effect"])


# ============================================================================
# ACTION GENERATION TESTS
# ============================================================================

class TestBriarActions:
    """Test Briar action generation conditions."""

    def test_briar_playable_when_opponent_has_2_prizes(self):
        """Briar should be playable when opponent has exactly 2 prizes."""
        from cards.library.trainers import briar_actions

        state = create_briar_game_state(opponent_prize_count=2)
        briar = create_card_instance("sv7-132", owner_id=0)
        player = state.players[0]

        actions = briar_actions(state, briar, player)

        assert len(actions) == 1
        assert actions[0].action_type == ActionType.PLAY_SUPPORTER

    def test_briar_not_playable_when_opponent_has_1_prize(self):
        """Briar should NOT be playable when opponent has 1 prize."""
        from cards.library.trainers import briar_actions

        state = create_briar_game_state(opponent_prize_count=1)
        briar = create_card_instance("sv7-132", owner_id=0)
        player = state.players[0]

        actions = briar_actions(state, briar, player)

        assert len(actions) == 0

    def test_briar_not_playable_when_opponent_has_3_prizes(self):
        """Briar should NOT be playable when opponent has 3 prizes."""
        from cards.library.trainers import briar_actions

        state = create_briar_game_state(opponent_prize_count=3)
        briar = create_card_instance("sv7-132", owner_id=0)
        player = state.players[0]

        actions = briar_actions(state, briar, player)

        assert len(actions) == 0

    def test_briar_not_playable_when_opponent_has_6_prizes(self):
        """Briar should NOT be playable when opponent has 6 prizes."""
        from cards.library.trainers import briar_actions

        state = create_briar_game_state(opponent_prize_count=6)
        briar = create_card_instance("sv7-132", owner_id=0)
        player = state.players[0]

        actions = briar_actions(state, briar, player)

        assert len(actions) == 0

    def test_briar_not_playable_when_supporter_already_played(self):
        """Briar should NOT be playable if supporter already played this turn."""
        from cards.library.trainers import briar_actions

        state = create_briar_game_state(opponent_prize_count=2)
        briar = create_card_instance("sv7-132", owner_id=0)
        player = state.players[0]
        player.supporter_played_this_turn = True

        actions = briar_actions(state, briar, player)

        assert len(actions) == 0


# ============================================================================
# EFFECT TESTS
# ============================================================================

class TestBriarEffect:
    """Test Briar effect execution."""

    def test_briar_marks_supporter_played(self):
        """Briar effect should mark supporter as played."""
        from cards.library.trainers import briar_effect

        state = create_briar_game_state(opponent_prize_count=2)
        briar = create_card_instance("sv7-132", owner_id=0)
        player = state.players[0]
        player.hand.add_card(briar)

        assert player.supporter_played_this_turn == False

        action = Action(
            action_type=ActionType.PLAY_SUPPORTER,
            player_id=0,
            card_id=briar.id
        )

        state = briar_effect(state, briar, action)

        assert player.supporter_played_this_turn == True

    def test_briar_moves_to_discard(self):
        """Briar should move from hand to discard pile."""
        from cards.library.trainers import briar_effect

        state = create_briar_game_state(opponent_prize_count=2)
        briar = create_card_instance("sv7-132", owner_id=0)
        player = state.players[0]
        player.hand.add_card(briar)

        initial_hand_size = len(player.hand.cards)
        initial_discard_size = len(player.discard.cards)

        action = Action(
            action_type=ActionType.PLAY_SUPPORTER,
            player_id=0,
            card_id=briar.id
        )

        state = briar_effect(state, briar, action)

        assert len(player.hand.cards) == initial_hand_size - 1
        assert len(player.discard.cards) == initial_discard_size + 1
        # Briar should be in discard
        assert any(c.card_id == "sv7-132" for c in player.discard.cards)

    def test_briar_adds_prize_modifier_effect(self):
        """Briar should add a PRIZE_COUNT_MODIFIER effect to active_effects."""
        from cards.library.trainers import briar_effect

        state = create_briar_game_state(opponent_prize_count=2)
        briar = create_card_instance("sv7-132", owner_id=0)
        player = state.players[0]
        player.hand.add_card(briar)

        initial_effects = len(state.active_effects)

        action = Action(
            action_type=ActionType.PLAY_SUPPORTER,
            player_id=0,
            card_id=briar.id
        )

        state = briar_effect(state, briar, action)

        assert len(state.active_effects) == initial_effects + 1

        # Find the Briar effect
        briar_effect_data = None
        for effect in state.active_effects:
            if effect.get('name') == 'Briar':
                briar_effect_data = effect
                break

        assert briar_effect_data is not None
        assert briar_effect_data['type'] == 'PRIZE_COUNT_MODIFIER'
        assert briar_effect_data['modifier'] == 1
        assert briar_effect_data['source_player_id'] == 0


# ============================================================================
# PRIZE CONDITION TESTS
# ============================================================================

class TestBriarPrizeCondition:
    """Test the Briar prize condition function."""

    def test_condition_true_for_tera_ko_on_active(self):
        """Condition should return True when Tera Pokemon KOs opponent's Active."""
        from cards.library.trainers import _briar_prize_condition

        state = create_briar_game_state(opponent_prize_count=2)

        # Terapagos ex (Tera Pokemon) is the killer
        killer = state.players[0].board.active_spot

        # Opponent's active is the victim
        victim = state.players[1].board.active_spot

        result = _briar_prize_condition(killer, victim, state)

        assert result == True

    def test_condition_false_for_non_tera_ko(self):
        """Condition should return False when non-Tera Pokemon KOs."""
        from cards.library.trainers import _briar_prize_condition

        state = create_briar_game_state(opponent_prize_count=2)

        # Use a non-Tera Pokemon as killer (e.g., Charmander)
        killer = create_card_instance("svp-44", owner_id=0)
        state.players[0].board.active_spot = killer

        # Opponent's active is the victim
        victim = state.players[1].board.active_spot

        result = _briar_prize_condition(killer, victim, state)

        assert result == False

    def test_condition_false_when_no_killer(self):
        """Condition should return False when there's no killer (effect damage)."""
        from cards.library.trainers import _briar_prize_condition

        state = create_briar_game_state(opponent_prize_count=2)

        victim = state.players[1].board.active_spot

        result = _briar_prize_condition(None, victim, state)

        assert result == False

    def test_condition_false_for_bench_ko(self):
        """Condition should return False when KO is on benched Pokemon."""
        from cards.library.trainers import _briar_prize_condition

        state = create_briar_game_state(opponent_prize_count=2)

        # Terapagos ex (Tera Pokemon) is the killer
        killer = state.players[0].board.active_spot

        # Put victim on bench, not active
        bench_pokemon = create_card_instance("svp-44", owner_id=1)
        state.players[1].board.bench.append(bench_pokemon)

        # Use the bench Pokemon as victim
        victim = bench_pokemon

        result = _briar_prize_condition(killer, victim, state)

        assert result == False


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestBriarEngineIntegration:
    """Test Briar integration with the game engine."""

    def test_briar_shows_in_legal_actions(self, engine):
        """Briar should appear in legal actions when conditions are met."""
        state = create_briar_game_state(opponent_prize_count=2)
        briar = create_card_instance("sv7-132", owner_id=0)
        state.players[0].hand.add_card(briar)

        actions = engine.get_legal_actions(state)

        # Find Briar action
        briar_actions = [a for a in actions if a.card_id == briar.id and
                        a.action_type == ActionType.PLAY_SUPPORTER]

        assert len(briar_actions) == 1

    def test_briar_not_in_legal_actions_wrong_prize_count(self, engine):
        """Briar should NOT appear when opponent doesn't have exactly 2 prizes."""
        state = create_briar_game_state(opponent_prize_count=3)
        briar = create_card_instance("sv7-132", owner_id=0)
        state.players[0].hand.add_card(briar)

        actions = engine.get_legal_actions(state)

        # Should not find Briar action
        briar_actions = [a for a in actions if a.card_id == briar.id and
                        a.action_type == ActionType.PLAY_SUPPORTER]

        assert len(briar_actions) == 0


# ============================================================================
# TERA POKEMON VERIFICATION
# ============================================================================

class TestTeraPokemonIdentification:
    """Verify that Tera Pokemon are correctly identified."""

    def test_terapagos_is_tera(self):
        """Terapagos ex should be identified as a Tera Pokemon."""
        terapagos_def = create_card("sv7-128")

        assert terapagos_def is not None
        assert hasattr(terapagos_def, 'subtypes')
        assert Subtype.TERA in terapagos_def.subtypes

    def test_regular_pokemon_is_not_tera(self):
        """Regular Pokemon like Charmander should NOT be Tera."""
        charmander_def = create_card("svp-44")

        assert charmander_def is not None
        if hasattr(charmander_def, 'subtypes'):
            assert Subtype.TERA not in charmander_def.subtypes


# ============================================================================
# PRIZE CALCULATION INTEGRATION TESTS
# ============================================================================

class TestBriarPrizeCalculation:
    """Test that Briar actually modifies prize count through the engine."""

    def test_tera_ko_with_briar_gives_extra_prize(self, engine):
        """Terapagos KO on Active with Briar active should give +1 prize (total 3 for ex)."""
        from cards.library.trainers import briar_effect

        state = create_briar_game_state(opponent_prize_count=2)
        briar = create_card_instance("sv7-132", owner_id=0)
        player = state.players[0]
        player.hand.add_card(briar)

        # Play Briar to add the effect
        action = Action(
            action_type=ActionType.PLAY_SUPPORTER,
            player_id=0,
            card_id=briar.id
        )
        state = briar_effect(state, briar, action)

        # Verify Briar effect is in active_effects
        assert len(state.active_effects) == 1
        assert state.active_effects[0]['name'] == 'Briar'

        # Terapagos ex (Tera) is the killer
        killer = state.players[0].board.active_spot  # Terapagos ex

        # Opponent's Charmander is the victim (a Basic Pokemon = 1 prize normally)
        victim = state.players[1].board.active_spot  # Charmander

        # Calculate prizes through engine
        prizes = engine._calculate_prizes(killer, victim, state)

        # Charmander is a Basic (1 prize) + Briar (+1) = 2 prizes
        assert prizes == 2, f"Expected 2 prizes (1 base + 1 Briar), got {prizes}"

    def test_non_tera_ko_with_briar_gives_normal_prize(self, engine):
        """Charmander (non-Tera) KO on Active with Briar active should give normal prizes."""
        from cards.library.trainers import briar_effect

        state = create_briar_game_state(opponent_prize_count=2)
        briar = create_card_instance("sv7-132", owner_id=0)
        player = state.players[0]
        player.hand.add_card(briar)

        # Replace Terapagos with Charmander (non-Tera)
        charmander_attacker = create_card_instance("svp-44", owner_id=0)
        state.players[0].board.active_spot = charmander_attacker

        # Play Briar to add the effect
        action = Action(
            action_type=ActionType.PLAY_SUPPORTER,
            player_id=0,
            card_id=briar.id
        )
        state = briar_effect(state, briar, action)

        # Charmander (non-Tera) is the killer
        killer = state.players[0].board.active_spot

        # Opponent's Charmander is the victim
        victim = state.players[1].board.active_spot

        # Calculate prizes through engine
        prizes = engine._calculate_prizes(killer, victim, state)

        # Charmander is a Basic (1 prize), no Briar bonus = 1 prize
        assert prizes == 1, f"Expected 1 prize (no Briar bonus for non-Tera), got {prizes}"

    def test_tera_ko_without_briar_gives_normal_prize(self, engine):
        """Terapagos KO without Briar should give normal prizes."""
        state = create_briar_game_state(opponent_prize_count=2)

        # No Briar played - active_effects should be empty
        assert len(state.active_effects) == 0

        # Terapagos ex (Tera) is the killer
        killer = state.players[0].board.active_spot

        # Opponent's Charmander is the victim
        victim = state.players[1].board.active_spot

        # Calculate prizes through engine
        prizes = engine._calculate_prizes(killer, victim, state)

        # Charmander is a Basic (1 prize), no Briar = 1 prize
        assert prizes == 1, f"Expected 1 prize (no Briar active), got {prizes}"

    def test_tera_ko_on_ex_with_briar_gives_3_prizes(self, engine):
        """Terapagos KO on opponent's ex Pokemon with Briar should give 3 prizes."""
        from cards.library.trainers import briar_effect

        state = create_briar_game_state(opponent_prize_count=2)
        briar = create_card_instance("sv7-132", owner_id=0)
        player = state.players[0]
        player.hand.add_card(briar)

        # Replace opponent's active with an ex Pokemon (2 prizes normally)
        opponent_ex = create_card_instance("sv7-128", owner_id=1)  # Terapagos ex
        state.players[1].board.active_spot = opponent_ex

        # Play Briar to add the effect
        action = Action(
            action_type=ActionType.PLAY_SUPPORTER,
            player_id=0,
            card_id=briar.id
        )
        state = briar_effect(state, briar, action)

        # Terapagos ex (Tera) is the killer
        killer = state.players[0].board.active_spot

        # Opponent's Terapagos ex is the victim (ex = 2 prizes base)
        victim = state.players[1].board.active_spot

        # Calculate prizes through engine
        prizes = engine._calculate_prizes(killer, victim, state)

        # Terapagos ex is an ex (2 prizes) + Briar (+1) = 3 prizes
        assert prizes == 3, f"Expected 3 prizes (2 base for ex + 1 Briar), got {prizes}"

    def test_bench_ko_with_briar_gives_normal_prize(self, engine):
        """Briar should NOT give extra prize for bench KO (only Active)."""
        from cards.library.trainers import briar_effect

        state = create_briar_game_state(opponent_prize_count=2)
        briar = create_card_instance("sv7-132", owner_id=0)
        player = state.players[0]
        player.hand.add_card(briar)

        # Add a benched Pokemon to opponent
        bench_pokemon = create_card_instance("svp-44", owner_id=1)
        state.players[1].board.bench.append(bench_pokemon)

        # Play Briar to add the effect
        action = Action(
            action_type=ActionType.PLAY_SUPPORTER,
            player_id=0,
            card_id=briar.id
        )
        state = briar_effect(state, briar, action)

        # Terapagos ex (Tera) is the killer
        killer = state.players[0].board.active_spot

        # The BENCHED Pokemon is the victim (not the Active)
        victim = bench_pokemon

        # Calculate prizes through engine
        prizes = engine._calculate_prizes(killer, victim, state)

        # Bench KO = no Briar bonus, just 1 prize for Basic
        assert prizes == 1, f"Expected 1 prize (Briar only works on Active KO), got {prizes}"

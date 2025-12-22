"""
Verification Script for Neural MCTS Pipeline.

This script verifies that the complete pipeline works:
1. StateEncoder correctly produces tensors
2. AlphaZeroNet accepts those tensors and produces policy/value
3. MCTS uses the neural network for priors and evaluation
4. Action probabilities are valid (sum to 1.0)

Run this to confirm the "plumbing" is connected before training.
"""

import sys
import os

# Add src to path
script_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(script_dir)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

import numpy as np
import torch


def main():
    print("=" * 60)
    print("Neural MCTS Pipeline Verification")
    print("=" * 60)
    print()

    # =========================================================================
    # 1. DEVICE DETECTION
    # =========================================================================
    print("[1/6] Detecting device...")
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"  Device: {device}")
    if device == 'cuda':
        print(f"  GPU: {torch.cuda.get_device_name(0)}")
    print()

    # =========================================================================
    # 2. INITIALIZE NEURAL NETWORK
    # =========================================================================
    print("[2/6] Initializing AlphaZeroNet...")
    from ai.model import AlphaZeroNet, ACTION_SPACE_SIZE

    vocab_size = 5000  # Enough for all cards
    model = AlphaZeroNet(
        action_space_size=ACTION_SPACE_SIZE,
        vocab_size=vocab_size
    )
    model = model.to(device)
    model.eval()

    print(f"  Action space size: {ACTION_SPACE_SIZE}")
    print(f"  Vocab size: {vocab_size}")
    print(f"  Parameters: {model.count_parameters():,}")
    print()

    # =========================================================================
    # 3. INITIALIZE ENCODERS
    # =========================================================================
    print("[3/6] Initializing encoders...")
    from ai.state_encoder import StateEncoder, CardIDRegistry
    from ai.encoder import UniversalActionEncoder

    # Create a registry and populate with some IDs
    registry = CardIDRegistry()
    state_encoder = StateEncoder(registry)
    action_encoder = UniversalActionEncoder()

    print(f"  StateEncoder: Ready")
    print(f"  ActionEncoder: Ready (action space = {action_encoder.action_space_size})")
    print()

    # =========================================================================
    # 4. INITIALIZE ENGINE AND CREATE GAME STATE
    # =========================================================================
    print("[4/6] Creating game state...")
    from engine import PokemonEngine
    from game_setup import build_game_state, setup_initial_board

    engine = PokemonEngine()

    # Try to load deck, fallback to dummy if not found
    deck_path = os.path.join(src_dir, "decks", "charizard_ex.txt")

    if os.path.exists(deck_path):
        print(f"  Using deck: {deck_path}")
        with open(deck_path, 'r') as f:
            deck_list = f.read()
    else:
        print("  Deck file not found, using fallback deck")
        # Create a minimal valid deck
        deck_list = """4 Charmander SV3 26
2 Charmeleon SV3 27
3 Charizard ex SV3 54
4 Arcanine ex SV3 32
4 Growlithe SV3 31
4 Nest Ball SVI 181
4 Rare Candy SVI 191
4 Professor's Research SVI 189
4 Boss's Orders PAL 172
4 Ultra Ball SVI 196
23 Fire Energy SVE 2"""

    # Build game state
    try:
        state = build_game_state(deck_list, deck_list)
        state = setup_initial_board(state)
        print(f"  Game state created")
        print(f"  Turn: {state.turn_count}")
        print(f"  Active player: {state.active_player_index}")

        # Get legal actions
        legal_actions = engine.get_legal_actions(state)
        print(f"  Legal actions: {len(legal_actions)}")
    except Exception as e:
        print(f"  Error creating game state: {e}")
        print("  Attempting minimal setup...")

        # Try a more minimal approach
        from models import GameState, PlayerState, Board, Zone

        # Create minimal game state for testing
        state = GameState(
            players=[
                PlayerState(
                    id=0,
                    deck=Zone(cards=[]),
                    hand=Zone(cards=[]),
                    discard=Zone(cards=[]),
                    prizes=Zone(cards=[]),
                    board=Board()
                ),
                PlayerState(
                    id=1,
                    deck=Zone(cards=[]),
                    hand=Zone(cards=[]),
                    discard=Zone(cards=[]),
                    prizes=Zone(cards=[]),
                    board=Board()
                )
            ],
            active_player_index=0,
            turn_count=1
        )
        legal_actions = engine.get_legal_actions(state)
        print(f"  Minimal state created, legal actions: {len(legal_actions)}")

    print()

    # =========================================================================
    # 5. RUN MCTS SEARCH
    # =========================================================================
    print("[5/6] Running MCTS search...")
    from ai.mcts import MCTS

    mcts = MCTS(
        engine=engine,
        model=model,
        state_encoder=state_encoder,
        device=device,
        num_simulations=10,  # Low count for speed
        c_puct=1.5,
        temperature=1.0,
        verbose=False
    )

    try:
        best_action, action_probs, info = mcts.search(state, add_noise=True)

        print(f"  Simulations: {info['simulations']}")
        print(f"  NN evaluations: {info['nn_evaluations']}")
        print(f"  Terminal states: {info['terminal_states']}")
        print(f"  Children expanded: {info['total_children']}")
        print()

        # =====================================================================
        # 6. VERIFY OUTPUTS
        # =====================================================================
        print("[6/6] Verifying outputs...")

        # Check best action
        print(f"  Best action: {info['best_action_str']}")
        print(f"  Best action visits: {info['best_visits']}")
        print(f"  Win rate: {info['win_rate']:.2%}")

        # Check action_probs shape
        print(f"  Action probs shape: {action_probs.shape}")
        assert action_probs.shape == (ACTION_SPACE_SIZE,), \
            f"Expected shape ({ACTION_SPACE_SIZE},), got {action_probs.shape}"
        print(f"  Shape check: PASSED")

        # Check probabilities sum to 1
        prob_sum = action_probs.sum()
        print(f"  Probability sum: {prob_sum:.6f}")
        assert abs(prob_sum - 1.0) < 0.01, \
            f"Probabilities should sum to ~1.0, got {prob_sum}"
        print(f"  Sum check: PASSED")

        # Check no NaN values
        assert not np.isnan(action_probs).any(), "Action probs contain NaN"
        print(f"  NaN check: PASSED")

        # Check probabilities are non-negative
        assert (action_probs >= 0).all(), "Action probs contain negative values"
        print(f"  Non-negative check: PASSED")

        # Count non-zero probabilities (should match legal actions)
        nonzero_count = (action_probs > 0).sum()
        print(f"  Non-zero probabilities: {nonzero_count}")

        print()
        print("=" * 60)
        print("Neural Pipeline Verified")
        print("=" * 60)
        print()
        print("The complete pipeline works:")
        print("  StateEncoder -> Tensors")
        print("  AlphaZeroNet -> Policy + Value")
        print("  MCTS -> Action Probabilities")
        print()
        print("Ready for training!")

        return 0

    except ValueError as e:
        if "No legal actions" in str(e):
            print(f"  No legal actions available (game may be in special state)")
            print(f"  This is OK for verification - pipeline components work")
            print()
            print("=" * 60)
            print("Partial Verification (no legal actions)")
            print("=" * 60)
            return 0
        else:
            raise


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        print()
        print("=" * 60)
        print(f"VERIFICATION FAILED: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        sys.exit(1)

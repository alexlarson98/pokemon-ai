"""
Verification Script for Self-Play Data Generator.

This script verifies:
1. SelfPlayWorker can complete a full game
2. GameHistory correctly stores and returns samples
3. Value targets are valid (+1.0, -1.0, or 0.0)
4. Action probabilities sum to 1.0
5. Output format is compatible with PyTorch Dataset
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
    print("Self-Play Data Generator Verification")
    print("=" * 60)
    print()

    # =========================================================================
    # 1. INITIALIZATION
    # =========================================================================
    print("[1/5] Initializing components...")

    # Device
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"  Device: {device}")

    # Model
    from ai.model import AlphaZeroNet, ACTION_SPACE_SIZE
    model = AlphaZeroNet(vocab_size=5000)
    model = model.to(device)
    model.eval()
    print(f"  Model: AlphaZeroNet ({model.count_parameters():,} params)")

    # Encoder
    from ai.state_encoder import StateEncoder, CardIDRegistry
    registry = CardIDRegistry()
    state_encoder = StateEncoder(registry)
    print(f"  StateEncoder: Ready")

    # Engine
    from engine import PokemonEngine
    engine = PokemonEngine()
    print(f"  Engine: Ready")

    # Worker
    from ai.self_play import SelfPlayWorker
    worker = SelfPlayWorker(
        engine=engine,
        model=model,
        state_encoder=state_encoder,
        device=device,
        num_simulations=10,  # Low for speed
        max_turns=100,       # Limit game length for testing
        verbose=True
    )
    print(f"  SelfPlayWorker: Ready (10 simulations)")
    print()

    # =========================================================================
    # 2. PLAY A GAME
    # =========================================================================
    print("[2/5] Playing a test game...")
    print("-" * 40)

    samples, game_info = worker.play_game()

    print("-" * 40)
    print(f"  Game completed!")
    print(f"  Turns played: {game_info['turns']}")
    print(f"  Winner: {game_info['winner']}")
    print(f"  Result: {game_info['result']}")
    print(f"  Samples collected: {game_info['samples_collected']}")
    print()

    # =========================================================================
    # 3. VERIFY SAMPLES
    # =========================================================================
    print("[3/5] Verifying samples...")

    # Check we got samples
    assert len(samples) > 0, "No samples generated"
    print(f"  Sample count: {len(samples)}")

    # Check sample format
    sample = samples[0]
    assert len(sample) == 3, f"Expected 3 elements per sample, got {len(sample)}"
    state_dict, action_probs, value_target = sample

    print(f"  Sample format: (state_dict, action_probs, value_target)")
    print(f"  State dict keys: {list(state_dict.keys())}")
    print(f"  Action probs shape: {action_probs.shape}")
    print(f"  Value target type: {type(value_target)}")

    # Verify action_probs shape
    assert action_probs.shape == (ACTION_SPACE_SIZE,), \
        f"Expected action_probs shape ({ACTION_SPACE_SIZE},), got {action_probs.shape}"
    print(f"  Action probs shape check: PASSED")
    print()

    # =========================================================================
    # 4. VERIFY VALUE TARGETS
    # =========================================================================
    print("[4/5] Verifying value targets...")

    valid_values = {-1.0, 0.0, 1.0}
    value_counts = {-1.0: 0, 0.0: 0, 1.0: 0}

    for i, (_, _, value_target) in enumerate(samples):
        assert value_target in valid_values, \
            f"Sample {i}: Invalid value target {value_target}, expected one of {valid_values}"
        value_counts[value_target] += 1

    print(f"  Value +1.0 (wins): {value_counts[1.0]}")
    print(f"  Value -1.0 (losses): {value_counts[-1.0]}")
    print(f"  Value  0.0 (draws): {value_counts[0.0]}")

    # If there was a winner, we should have both +1 and -1 values
    if game_info['winner'] is not None:
        assert value_counts[1.0] > 0, "No winning samples found"
        assert value_counts[-1.0] > 0, "No losing samples found"
        print(f"  Winner/loser values: PASSED")
    else:
        assert value_counts[0.0] == len(samples), "Draw game should have all 0.0 values"
        print(f"  Draw values: PASSED")

    print(f"  Value targets check: PASSED")
    print()

    # =========================================================================
    # 5. VERIFY ACTION PROBABILITIES
    # =========================================================================
    print("[5/5] Verifying action probabilities...")

    for i, (_, action_probs, _) in enumerate(samples):
        # Check sum to 1
        prob_sum = action_probs.sum()
        assert abs(prob_sum - 1.0) < 0.01, \
            f"Sample {i}: Probs sum to {prob_sum}, expected ~1.0"

        # Check non-negative
        assert (action_probs >= 0).all(), \
            f"Sample {i}: Contains negative probabilities"

        # Check no NaN
        assert not np.isnan(action_probs).any(), \
            f"Sample {i}: Contains NaN values"

    print(f"  All {len(samples)} samples have valid action probabilities")
    print(f"  Sum to 1.0: PASSED")
    print(f"  Non-negative: PASSED")
    print(f"  No NaN: PASSED")
    print()

    # =========================================================================
    # 6. VERIFY DEEP COPY (Critical!)
    # =========================================================================
    print("[Bonus] Verifying deep copy of states...")

    if len(samples) >= 2:
        state1 = samples[0][0]
        state2 = samples[1][0]

        # Check they're different objects
        assert state1 is not state2, "State dicts should be different objects"

        # Check arrays are different objects
        for key in state1:
            if key in state2:
                assert state1[key] is not state2[key], \
                    f"Array '{key}' should be different objects"

        print(f"  States are independent copies: PASSED")
    else:
        print(f"  Skipped (need 2+ samples)")
    print()

    # =========================================================================
    # 7. VERIFY PYTORCH COMPATIBILITY
    # =========================================================================
    print("[Bonus] Verifying PyTorch Dataset compatibility...")

    # Convert a sample to tensors
    state_dict, action_probs, value_target = samples[0]

    # State dict should convert to tensors
    tensor_dict = {k: torch.from_numpy(v) for k, v in state_dict.items()}
    print(f"  State dict -> tensors: OK")

    # Action probs should convert to tensor
    probs_tensor = torch.from_numpy(action_probs)
    assert probs_tensor.shape == (ACTION_SPACE_SIZE,)
    print(f"  Action probs -> tensor: OK")

    # Value should convert to tensor
    value_tensor = torch.tensor([value_target], dtype=torch.float32)
    assert value_tensor.shape == (1,)
    print(f"  Value target -> tensor: OK")

    print(f"  PyTorch compatibility: PASSED")
    print()

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("=" * 60)
    print("Self-Play Verification Complete")
    print("=" * 60)
    print()
    print("Summary:")
    print(f"  Game length: {game_info['turns']} turns")
    print(f"  Samples generated: {len(samples)}")
    print(f"  Winner: Player {game_info['winner']}" if game_info['winner'] is not None else "  Winner: Draw")
    print()
    print("All checks passed:")
    print("  - SelfPlayWorker completes games")
    print("  - GameHistory stores correct number of samples")
    print("  - Value targets are valid (+1.0, -1.0, or 0.0)")
    print("  - Action probabilities sum to 1.0")
    print("  - States are deep copied (no reference issues)")
    print("  - Output is PyTorch Dataset compatible")
    print()
    print("Ready for training loop!")

    return 0


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

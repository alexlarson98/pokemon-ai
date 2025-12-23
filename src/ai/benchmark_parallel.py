"""
Benchmark: Sequential vs Parallel Self-Play

Compares timing of:
1. Sequential: Run N games one at a time
2. Parallel: Run N games with batched NN inference

Run with: python src/ai/benchmark_parallel.py
"""

import time
import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(script_dir)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)


def main():
    import torch
    from engine import PokemonEngine
    from ai.state_encoder import StateEncoder, CardIDRegistry
    from ai.model import AlphaZeroNet, ACTION_SPACE_SIZE
    from ai.self_play import run_self_play_games
    from ai.parallel_self_play import run_parallel_self_play

    print("=" * 60)
    print("PARALLEL VS SEQUENTIAL BENCHMARK")
    print("=" * 60)

    # Setup
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"Device: {device}")

    engine = PokemonEngine()
    registry = CardIDRegistry()
    state_encoder = StateEncoder(registry)
    model = AlphaZeroNet(
        action_space_size=ACTION_SPACE_SIZE,
        vocab_size=5000,
        embedding_dim=64,
        backbone_dim=512,
        num_residual_blocks=6
    )
    model = model.to(device)
    model.eval()

    # Test parameters
    num_games = 8
    num_sims = 35

    print(f"\nTest: {num_games} games, {num_sims} MCTS simulations each")
    print("-" * 60)

    # Sequential benchmark
    print("\n[1] SEQUENTIAL MODE (one game at a time)...")
    seq_start = time.time()
    seq_samples, seq_stats = run_self_play_games(
        engine=engine,
        model=model,
        state_encoder=state_encoder,
        device=device,
        num_games=num_games,
        num_simulations=num_sims,
        verbose=False
    )
    seq_time = time.time() - seq_start
    print(f"    Time: {seq_time:.1f}s")
    print(f"    Samples: {len(seq_samples)}")
    print(f"    Games/sec: {num_games / seq_time:.2f}")

    # Parallel benchmark
    print("\n[2] PARALLEL BATCHED MODE (all games together)...")
    par_start = time.time()
    par_samples, par_stats = run_parallel_self_play(
        engine=engine,
        model=model,
        state_encoder=state_encoder,
        device=device,
        num_games=num_games,
        num_simulations=num_sims,
        verbose=False
    )
    par_time = time.time() - par_start
    print(f"    Time: {par_time:.1f}s")
    print(f"    Samples: {len(par_samples)}")
    print(f"    Games/sec: {num_games / par_time:.2f}")

    # Results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    speedup = seq_time / par_time if par_time > 0 else 0
    print(f"Sequential: {seq_time:.1f}s")
    print(f"Parallel:   {par_time:.1f}s")
    print(f"Speedup:    {speedup:.2f}x")

    if speedup > 1:
        print(f"\nParallel is {speedup:.1f}x FASTER")
    elif speedup < 1:
        print(f"\nParallel is {1/speedup:.1f}x SLOWER (bottleneck is game engine)")
    else:
        print("\nNo difference")

    print("=" * 60)


if __name__ == '__main__':
    main()

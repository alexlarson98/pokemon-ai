"""
MCTS Performance Benchmark and Profiling Script.

This script profiles the MCTS implementation to identify bottlenecks
and provides baseline metrics for optimization comparison.

Usage:
    # Basic benchmark (100 simulations)
    python src/ai/benchmark_mcts.py

    # With profiling output
    python src/ai/benchmark_mcts.py --profile

    # More simulations for accurate timing
    python src/ai/benchmark_mcts.py --simulations 500

    # Test with PyPy (run with pypy3 instead of python)
    pypy3 src/ai/benchmark_mcts.py
"""

import sys
import os
import time
import argparse
import cProfile
import pstats
from io import StringIO

# Add src to path
script_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(script_dir)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from engine import PokemonEngine
from game_setup import build_game_state, setup_initial_board, load_deck_from_file
from ai.mcts import MCTS, suppress_stdout


def print_header(text):
    print(f"\n{'='*60}")
    print(f" {text}")
    print('='*60)


def create_test_state(seed=12345):
    """Create a test game state for benchmarking."""
    decks_dir = os.path.join(src_dir, 'decks')
    deck_path = os.path.join(decks_dir, 'charizard_ex.txt')

    deck_text = load_deck_from_file(deck_path)
    engine = PokemonEngine()

    with suppress_stdout():
        state = build_game_state(deck_text, deck_text, random_seed=seed)
        state = setup_initial_board(state, engine)

    return engine, state


def benchmark_simulations(engine, state, num_sims, num_runs=3):
    """
    Benchmark MCTS simulations.

    Returns:
        dict with timing statistics
    """
    times = []
    total_rollout_depth = 0
    total_children = 0

    for run in range(num_runs):
        mcts = MCTS(engine, num_simulations=num_sims, max_rollout_depth=50)

        # Clone state for each run
        test_state = state.clone()

        start = time.perf_counter()
        with suppress_stdout():
            action, info = mcts.search(test_state)
        end = time.perf_counter()

        elapsed = end - start
        times.append(elapsed)
        total_rollout_depth += info['avg_rollout_depth']
        total_children += info['total_children']

    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)
    sims_per_sec = num_sims / avg_time

    return {
        'num_simulations': num_sims,
        'num_runs': num_runs,
        'avg_time': avg_time,
        'min_time': min_time,
        'max_time': max_time,
        'sims_per_second': sims_per_sec,
        'avg_rollout_depth': total_rollout_depth / num_runs,
        'avg_children': total_children / num_runs,
    }


def profile_mcts(engine, state, num_sims=100):
    """
    Profile MCTS with cProfile to identify hotspots.

    Returns:
        Profiling statistics string
    """
    mcts = MCTS(engine, num_simulations=num_sims, max_rollout_depth=50)
    test_state = state.clone()

    # Profile the search
    profiler = cProfile.Profile()
    profiler.enable()

    with suppress_stdout():
        action, info = mcts.search(test_state)

    profiler.disable()

    # Get stats
    stream = StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.sort_stats('cumulative')
    stats.print_stats(30)  # Top 30 functions by cumulative time

    return stream.getvalue()


def profile_by_function(engine, state, num_sims=100):
    """
    Profile MCTS and group by function for clearer analysis.

    Returns:
        dict of function -> time spent
    """
    mcts = MCTS(engine, num_simulations=num_sims, max_rollout_depth=50)
    test_state = state.clone()

    # Profile
    profiler = cProfile.Profile()
    profiler.enable()

    with suppress_stdout():
        action, info = mcts.search(test_state)

    profiler.disable()

    # Collect stats by function name
    stats = pstats.Stats(profiler)

    # Group by key function categories
    categories = {
        'MCTS Core': ['search', '_simulate', '_select', '_expand', '_rollout', '_backpropagate'],
        'Engine': ['step', 'get_legal_actions', 'clone', 'resolve_action'],
        'State/Model': ['__init__', '__copy__', 'deepcopy', 'copy'],
        'Evaluation': ['_evaluate_heuristic', '_get_result_value', 'is_game_over'],
        'Other': []
    }

    function_times = {}
    for func_info, data in stats.stats.items():
        filename, line, func_name = func_info
        cumtime = data[3]  # Cumulative time

        # Skip very small times
        if cumtime < 0.001:
            continue

        function_times[f"{func_name} ({os.path.basename(filename)}:{line})"] = cumtime

    # Sort by time
    sorted_times = sorted(function_times.items(), key=lambda x: x[1], reverse=True)

    return sorted_times[:20]


def run_scaling_test(engine, state):
    """Test how performance scales with simulation count."""
    print_header("SCALING TEST")
    print("Testing how performance scales with simulation count...\n")

    sim_counts = [10, 25, 50, 100, 200]
    results = []

    for num_sims in sim_counts:
        stats = benchmark_simulations(engine, state, num_sims, num_runs=3)
        results.append(stats)
        print(f"  {num_sims:4d} sims: {stats['avg_time']:.3f}s ({stats['sims_per_second']:.1f} sims/sec)")

    # Check if scaling is linear
    print("\n  Expected: O(n) scaling - time should increase linearly")
    base_sps = results[0]['sims_per_second']
    print(f"  Baseline: {base_sps:.1f} sims/sec at {results[0]['num_simulations']} sims")

    for stats in results[1:]:
        ratio = stats['sims_per_second'] / base_sps
        print(f"  At {stats['num_simulations']:4d} sims: {ratio:.2f}x of baseline rate")

    return results


def main():
    parser = argparse.ArgumentParser(description='MCTS Performance Benchmark')
    parser.add_argument('--simulations', '-s', type=int, default=100,
                        help='Number of MCTS simulations (default: 100)')
    parser.add_argument('--runs', '-r', type=int, default=5,
                        help='Number of benchmark runs (default: 5)')
    parser.add_argument('--profile', '-p', action='store_true',
                        help='Enable detailed profiling')
    parser.add_argument('--scaling', action='store_true',
                        help='Run scaling test')
    parser.add_argument('--seed', type=int, default=12345,
                        help='Random seed (default: 12345)')

    args = parser.parse_args()

    print_header("MCTS PERFORMANCE BENCHMARK")

    # Check Python implementation
    import platform
    impl = platform.python_implementation()
    version = platform.python_version()
    print(f"\n  Python: {impl} {version}")
    print(f"  Simulations: {args.simulations}")
    print(f"  Runs: {args.runs}")

    # Setup
    print("\n  Setting up test state...")
    engine, state = create_test_state(args.seed)
    print(f"  Active: {state.players[0].board.active_spot.card_id if state.players[0].board.active_spot else 'None'}")

    # Basic benchmark
    print_header("BASIC BENCHMARK")
    stats = benchmark_simulations(engine, state, args.simulations, args.runs)

    print(f"\n  Results for {stats['num_simulations']} simulations ({stats['num_runs']} runs):")
    print(f"    Average time: {stats['avg_time']:.3f}s")
    print(f"    Min time:     {stats['min_time']:.3f}s")
    print(f"    Max time:     {stats['max_time']:.3f}s")
    print(f"    Sims/second:  {stats['sims_per_second']:.1f}")
    print(f"    Avg rollout:  {stats['avg_rollout_depth']:.1f} steps")
    print(f"    Avg children: {stats['avg_children']:.1f}")

    # Time per component estimate
    time_per_sim = stats['avg_time'] / stats['num_simulations'] * 1000  # ms
    print(f"\n  Time per simulation: {time_per_sim:.2f}ms")

    # Scaling test
    if args.scaling:
        run_scaling_test(engine, state)

    # Profiling
    if args.profile:
        print_header("PROFILING - TOP FUNCTIONS BY TIME")

        function_times = profile_by_function(engine, state, args.simulations)

        print("\n  Top 20 functions by cumulative time:\n")
        for i, (func, time_spent) in enumerate(function_times, 1):
            pct = (time_spent / stats['avg_time']) * 100
            print(f"  {i:2d}. {func}")
            print(f"      {time_spent:.4f}s ({pct:.1f}%)")

        print_header("DETAILED PROFILE")
        profile_output = profile_mcts(engine, state, args.simulations)
        print(profile_output)

    # Summary
    print_header("OPTIMIZATION RECOMMENDATIONS")

    if stats['sims_per_second'] < 50:
        print("\n  [!] Current speed is slow (<50 sims/sec)")
    else:
        print(f"\n  Current speed: {stats['sims_per_second']:.1f} sims/sec")

    print("""
  Potential optimizations (in order of impact):

  1. PyPy: Run with 'pypy3 benchmark_mcts.py'
     Expected: 2-10x speedup with no code changes

  2. Reduce object creation in rollouts:
     - Use lightweight state representation
     - Avoid deep copies when possible

  3. Cython for hot paths:
     - _rollout() loop
     - _evaluate_heuristic()
     - Engine.get_legal_actions()

  4. Multiprocessing:
     - Run rollouts in parallel
     - Share root node across workers

  5. C++ rewrite (most effort):
     - Expected: 10-50x speedup
     - Consider for production use
""")

    return stats


if __name__ == '__main__':
    main()

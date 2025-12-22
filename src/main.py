"""
Pokemon AI Command Center - AlphaZero Training CLI.

This is the main entry point for training and managing the Pokemon AI.

Usage:
    python src/main.py train --iterations 100 --games 50
    python src/main.py verify
    python src/main.py benchmark

Commands:
    train     - Run AlphaZero training loop
    verify    - Run neural MCTS pipeline verification
    benchmark - Run MCTS benchmark
"""

import argparse
import os
import sys

# =============================================================================
# PATH SETUP - Ensure imports work from any directory
# =============================================================================

script_dir = os.path.dirname(os.path.abspath(__file__))
# If running from src/, script_dir is already correct
# If running from root, we need to add src/ to path
if os.path.basename(script_dir) == 'src':
    src_dir = script_dir
else:
    src_dir = os.path.join(script_dir, 'src')

if src_dir not in sys.path:
    sys.path.insert(0, src_dir)


# =============================================================================
# BANNER
# =============================================================================

BANNER = """
================================================================================

    POKEMON AI - AlphaZero Training System

    ____       _                              _    ___
   |  _ \\ ___ | | _____ _ __ ___   ___  _ __ | |  / _ \\
   | |_) / _ \\| |/ / _ \\ '_ ` _ \\ / _ \\| '_ \\| | | | | |
   |  __/ (_) |   <  __/ | | | | | (_) | | | |_| | |_| |
   |_|   \\___/|_|\\_\\___|_| |_| |_|\\___/|_| |_(_)  \\___/


================================================================================"""


# =============================================================================
# TRAIN COMMAND
# =============================================================================

def cmd_train(args):
    """Run AlphaZero training loop."""
    import torch

    print(BANNER)
    print("=" * 80)
    print("INITIALIZING TRAINING SYSTEM")
    print("=" * 80)
    print()

    # -------------------------------------------------------------------------
    # Device Detection
    # -------------------------------------------------------------------------
    print("[1/5] Detecting compute device...")

    if torch.cuda.is_available():
        device = 'cuda'
        gpu_name = torch.cuda.get_device_name(0)
        gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        print()
        print("  " + "=" * 60)
        print("  " + " " * 15 + ">>> RUNNING ON GPU <<<")
        print("  " + "=" * 60)
        print(f"  GPU: {gpu_name}")
        print(f"  Memory: {gpu_memory:.1f} GB")
        print("  " + "=" * 60)
        print()
    else:
        device = 'cpu'
        print()
        print("  " + "!" * 60)
        print("  WARNING: CUDA NOT AVAILABLE - USING CPU")
        print("  Training will be SIGNIFICANTLY slower!")
        print("  Consider using a machine with a GPU for training.")
        print("  " + "!" * 60)
        print()

    # -------------------------------------------------------------------------
    # Initialize Components
    # -------------------------------------------------------------------------
    print("[2/5] Initializing game engine...")
    from engine import PokemonEngine
    engine = PokemonEngine()
    print("  [OK] PokemonEngine ready")

    print()
    print("[3/5] Initializing encoders...")
    from ai.state_encoder import StateEncoder, CardIDRegistry
    from ai.encoder import UniversalActionEncoder, TOTAL_ACTION_SPACE

    registry = CardIDRegistry()
    state_encoder = StateEncoder(registry)
    action_encoder = UniversalActionEncoder()

    print(f"  [OK] CardIDRegistry ready")
    print(f"  [OK] StateEncoder ready")
    print(f"  [OK] UniversalActionEncoder ready (action space: {TOTAL_ACTION_SPACE})")

    # -------------------------------------------------------------------------
    # Initialize Neural Network
    # -------------------------------------------------------------------------
    print()
    print("[4/5] Initializing neural network...")
    from ai.model import AlphaZeroNet, ACTION_SPACE_SIZE

    model = AlphaZeroNet(
        action_space_size=ACTION_SPACE_SIZE,
        vocab_size=5000,  # Enough for all cards
        embedding_dim=64,
        backbone_dim=512,
        num_residual_blocks=6
    )
    model = model.to(device)

    print(f"  [OK] AlphaZeroNet initialized")
    print(f"    - Action space: {ACTION_SPACE_SIZE}")
    print(f"    - Parameters: {model.count_parameters():,}")
    print(f"    - Device: {device}")

    # Load checkpoint if provided
    if args.resume:
        print()
        print(f"  Loading checkpoint: {args.resume}")
        if os.path.exists(args.resume):
            checkpoint = torch.load(args.resume, map_location=device)
            if 'model_state_dict' in checkpoint:
                model.load_state_dict(checkpoint['model_state_dict'])
                iteration = checkpoint.get('iteration', 0)
                print(f"  [OK] Loaded checkpoint from iteration {iteration}")
            else:
                # Assume it's just the state dict
                model.load_state_dict(checkpoint)
                print(f"  [OK] Loaded model weights")
        else:
            print(f"  [ERROR] Checkpoint not found: {args.resume}")
            sys.exit(1)

    # -------------------------------------------------------------------------
    # Ensure Checkpoints Directory Exists
    # -------------------------------------------------------------------------
    print()
    print("[5/5] Setting up checkpoints directory...")

    checkpoint_dir = os.path.join(src_dir, '..', 'checkpoints')
    checkpoint_dir = os.path.abspath(checkpoint_dir)

    if not os.path.exists(checkpoint_dir):
        os.makedirs(checkpoint_dir)
        print(f"  [OK] Created: {checkpoint_dir}")
    else:
        print(f"  [OK] Using existing: {checkpoint_dir}")

    # -------------------------------------------------------------------------
    # Print Training Configuration
    # -------------------------------------------------------------------------
    print()
    print("=" * 80)
    print("TRAINING CONFIGURATION")
    print("=" * 80)
    print(f"  Iterations:       {args.iterations}")
    print(f"  Games/Iteration:  {args.games}")
    print(f"  Epochs/Iteration: {args.epochs}")
    print(f"  MCTS Simulations: {args.sims}")
    print(f"  Batch Size:       {args.batch_size}")
    print(f"  Learning Rate:    {args.lr}")
    print(f"  Device:           {device}")
    print(f"  Checkpoint Dir:   {checkpoint_dir}")
    print("=" * 80)
    print()

    # -------------------------------------------------------------------------
    # Start Training
    # -------------------------------------------------------------------------
    print("Starting training loop...")
    print()

    from ai.train import train_loop

    train_loop(
        engine=engine,
        model=model,
        state_encoder=state_encoder,
        device=device,
        num_iterations=args.iterations,
        games_per_iter=args.games,
        epochs_per_iter=args.epochs,
        num_simulations=args.sims,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        checkpoint_dir=checkpoint_dir,
        verbose=True,
        verbose_games=args.verbose
    )

    print()
    print("=" * 80)
    print("TRAINING COMPLETE")
    print("=" * 80)


# =============================================================================
# VERIFY COMMAND
# =============================================================================

def cmd_verify(args):
    """Run neural MCTS pipeline verification."""
    print(BANNER)
    print("Running Neural MCTS Pipeline Verification...")
    print()

    # Import and run the verification script
    from ai.verify_neural_mcts import main as verify_main
    exit_code = verify_main()

    sys.exit(exit_code)


# =============================================================================
# BENCHMARK COMMAND
# =============================================================================

def cmd_benchmark(args):
    """Run MCTS benchmark."""
    print(BANNER)
    print("Running MCTS Benchmark...")
    print()

    try:
        from ai.benchmark_mcts import main as benchmark_main
        benchmark_main()
    except ImportError:
        print("Benchmark script not found. Running basic benchmark...")
        print()

        import torch
        import time

        from engine import PokemonEngine
        from ai.state_encoder import StateEncoder, CardIDRegistry
        from ai.model import AlphaZeroNet, ACTION_SPACE_SIZE
        from ai.mcts import MCTS
        from game_setup import build_game_state, setup_initial_board

        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"Device: {device}")

        # Initialize
        engine = PokemonEngine()
        registry = CardIDRegistry()
        state_encoder = StateEncoder(registry)
        model = AlphaZeroNet(action_space_size=ACTION_SPACE_SIZE, vocab_size=5000)
        model = model.to(device)
        model.eval()

        # Load deck
        deck_path = os.path.join(src_dir, "decks", "charizard_ex.txt")
        with open(deck_path, 'r') as f:
            deck_list = f.read()

        state = build_game_state(deck_list, deck_list)
        state = setup_initial_board(state)

        # Benchmark
        sims_list = [10, 50, 100, 200]

        print()
        print(f"{'Simulations':<15} {'Time (s)':<12} {'Sims/sec':<12}")
        print("-" * 40)

        for num_sims in sims_list:
            mcts = MCTS(
                engine=engine,
                model=model,
                state_encoder=state_encoder,
                device=device,
                num_simulations=num_sims
            )

            start = time.time()
            mcts.search(state, add_noise=True)
            elapsed = time.time() - start

            sims_per_sec = num_sims / elapsed
            print(f"{num_sims:<15} {elapsed:<12.3f} {sims_per_sec:<12.1f}")


# =============================================================================
# QUICK TEST COMMAND
# =============================================================================

def cmd_test(args):
    """Run quick training test."""
    import torch

    print(BANNER)
    print("Running Quick Training Test...")
    print()

    # Initialize components
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"Device: {device}")
    print()

    from engine import PokemonEngine
    from ai.state_encoder import StateEncoder, CardIDRegistry
    from ai.model import AlphaZeroNet, ACTION_SPACE_SIZE
    from ai.train import quick_training_test

    engine = PokemonEngine()
    registry = CardIDRegistry()
    state_encoder = StateEncoder(registry)
    model = AlphaZeroNet(action_space_size=ACTION_SPACE_SIZE, vocab_size=5000)
    model = model.to(device)

    quick_training_test(engine, model, state_encoder, device)


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Pokemon AI Command Center - AlphaZero Training System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/main.py train --iterations 100 --games 50
  python src/main.py train --resume checkpoints/iteration_10.pt
  python src/main.py verify
  python src/main.py benchmark
  python src/main.py test
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # -------------------------------------------------------------------------
    # Train subcommand
    # -------------------------------------------------------------------------
    train_parser = subparsers.add_parser('train', help='Run AlphaZero training loop')
    train_parser.add_argument(
        '--iterations', type=int, default=10,
        help='Number of full training cycles (default: 10)'
    )
    train_parser.add_argument(
        '--games', type=int, default=50,
        help='Number of self-play games per iteration (default: 50)'
    )
    train_parser.add_argument(
        '--epochs', type=int, default=5,
        help='Training epochs per iteration (default: 5)'
    )
    train_parser.add_argument(
        '--sims', type=int, default=100,
        help='MCTS simulations per move (default: 100)'
    )
    train_parser.add_argument(
        '--batch-size', type=int, default=64,
        help='Batch size for training (default: 64)'
    )
    train_parser.add_argument(
        '--lr', type=float, default=0.001,
        help='Learning rate (default: 0.001)'
    )
    train_parser.add_argument(
        '--resume', type=str, default=None,
        help='Path to checkpoint to resume from'
    )
    train_parser.add_argument(
        '--verbose', '-v', action='store_true',
        help='Show detailed action logs during self-play'
    )
    train_parser.set_defaults(func=cmd_train)

    # -------------------------------------------------------------------------
    # Verify subcommand
    # -------------------------------------------------------------------------
    verify_parser = subparsers.add_parser('verify', help='Run neural MCTS pipeline verification')
    verify_parser.set_defaults(func=cmd_verify)

    # -------------------------------------------------------------------------
    # Benchmark subcommand
    # -------------------------------------------------------------------------
    benchmark_parser = subparsers.add_parser('benchmark', help='Run MCTS benchmark')
    benchmark_parser.set_defaults(func=cmd_benchmark)

    # -------------------------------------------------------------------------
    # Test subcommand
    # -------------------------------------------------------------------------
    test_parser = subparsers.add_parser('test', help='Run quick training test')
    test_parser.set_defaults(func=cmd_test)

    # -------------------------------------------------------------------------
    # Parse and execute
    # -------------------------------------------------------------------------
    args = parser.parse_args()

    if args.command is None:
        # No command provided, show help
        parser.print_help()
        print()
        print("Run 'python src/main.py <command> --help' for more info on a command.")
        sys.exit(0)

    # Execute the command
    args.func(args)


if __name__ == '__main__':
    main()

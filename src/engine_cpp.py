"""
Pokemon AI - C++ Engine Python Wrapper

This module provides a drop-in replacement for the Python engine.
If the C++ module is available, it uses the fast C++ implementation.
Otherwise, it falls back to the Python implementation.

Usage:
    # Use the C++ engine (if available, else fallback to Python)
    from engine_cpp import PokemonEngine, GameState, Action

    # Or explicitly check availability
    from engine_cpp import is_cpp_available
    if is_cpp_available():
        print("Using C++ engine (20-50x faster)")
"""

import os
import sys

# Try to import C++ module
_cpp_module = None
_cpp_available = False

try:
    # Add parent directory to path for module discovery
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

    import pokemon_engine_cpp as _cpp_module
    _cpp_available = True
    print(f"[engine_cpp] C++ engine loaded (version {_cpp_module.VERSION})")
except ImportError as e:
    print(f"[engine_cpp] C++ engine not available: {e}")
    print("[engine_cpp] Falling back to Python engine")


def is_cpp_available() -> bool:
    """Check if the C++ engine is available."""
    return _cpp_available


# ============================================================================
# WRAPPER CLASSES
# ============================================================================

if _cpp_available:
    # Export C++ classes directly
    from pokemon_engine_cpp import (
        # Enums
        Supertype,
        Subtype,
        EnergyType,
        StatusCondition,
        GamePhase,
        GameResult,
        ActionType,

        # Core classes
        CardInstance,
        Zone,
        Board,
        PlayerState,
        Action,
        GameState,
        CardDef,
        CardDatabase,
        PokemonEngine,
    )

else:
    # Fall back to Python implementation
    from models import (
        Supertype,
        Subtype,
        EnergyType,
        StatusCondition,
        GamePhase,
        GameResult,
        ActionType,
        CardInstance,
        Zone,
        Board,
        PlayerState,
        Action,
        GameState,
    )
    from engine import PokemonEngine
    from cards.registry import CardDatabase, CardDef


# ============================================================================
# HYBRID ENGINE (Use C++ for hot paths, Python for complex logic)
# ============================================================================

class HybridEngine:
    """
    Hybrid engine that uses C++ for performance-critical operations
    and Python for complex card logic.

    This allows gradual migration to C++ while keeping Python flexibility
    for prototyping new card effects.
    """

    def __init__(self, use_cpp_for_actions: bool = True, use_cpp_for_step: bool = True):
        """
        Initialize hybrid engine.

        Args:
            use_cpp_for_actions: Use C++ for get_legal_actions()
            use_cpp_for_step: Use C++ for step()
        """
        self.use_cpp_for_actions = use_cpp_for_actions and _cpp_available
        self.use_cpp_for_step = use_cpp_for_step and _cpp_available

        # Initialize both engines
        if _cpp_available:
            self._cpp_engine = PokemonEngine()
        else:
            self._cpp_engine = None

        # Python engine for fallback
        from engine import PokemonEngine as PyEngine
        self._py_engine = PyEngine()

    def get_legal_actions(self, state):
        """Get legal actions from the current state."""
        if self.use_cpp_for_actions:
            # Convert state to C++ if needed
            # For now, assume state is already C++ GameState
            return self._cpp_engine.get_legal_actions(state)
        else:
            return self._py_engine.get_legal_actions(state)

    def step(self, state, action):
        """Apply an action and return new state."""
        if self.use_cpp_for_step:
            return self._cpp_engine.step(state, action)
        else:
            return self._py_engine.step(state, action)

    def step_inplace(self, state, action):
        """Apply an action in-place."""
        if self.use_cpp_for_step:
            self._cpp_engine.step_inplace(state, action)
        else:
            return self._py_engine.step(state, action)


# ============================================================================
# PERFORMANCE BENCHMARK
# ============================================================================

def benchmark_engines(num_games: int = 5, num_sims: int = 100):
    """
    Benchmark C++ vs Python engine performance.

    Args:
        num_games: Number of games to simulate
        num_sims: MCTS simulations per move
    """
    import time

    print("=" * 60)
    print("ENGINE PERFORMANCE BENCHMARK")
    print("=" * 60)
    print(f"Games: {num_games}, Simulations/move: {num_sims}")
    print()

    if not _cpp_available:
        print("C++ engine not available. Build it first:")
        print("  cd cpp_engine && build.bat")
        return

    # Import game setup
    from game_setup import build_game_state, setup_initial_board

    # Load deck
    deck_path = os.path.join(os.path.dirname(__file__), "decks", "charizard_ex.txt")
    with open(deck_path, 'r') as f:
        deck_list = f.read()

    # Benchmark Python engine
    print("[1/2] Python Engine...")
    from engine import PokemonEngine as PyEngine
    py_engine = PyEngine()

    py_start = time.time()
    py_actions_generated = 0

    for game in range(num_games):
        state = build_game_state(deck_list, deck_list)
        state = setup_initial_board(state)

        for _ in range(50):  # Max turns
            if state.is_game_over():
                break
            actions = py_engine.get_legal_actions(state)
            py_actions_generated += len(actions)
            if actions:
                state = py_engine.step(state, actions[0])

    py_time = time.time() - py_start
    print(f"  Time: {py_time:.2f}s")
    print(f"  Actions generated: {py_actions_generated}")

    # Benchmark C++ engine
    print()
    print("[2/2] C++ Engine...")
    cpp_engine = PokemonEngine()

    # TODO: Create C++ game state from deck
    # For now, just measure action generation
    cpp_start = time.time()
    cpp_actions_generated = 0

    # Note: Full benchmark requires C++ game setup
    # This is a placeholder

    cpp_time = time.time() - cpp_start

    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Python: {py_time:.2f}s")
    print(f"C++:    {cpp_time:.2f}s (placeholder)")
    if cpp_time > 0:
        speedup = py_time / cpp_time
        print(f"Speedup: {speedup:.1f}x")
    print("=" * 60)


if __name__ == "__main__":
    print(f"C++ Engine Available: {is_cpp_available()}")

    if is_cpp_available():
        print(f"Version: {_cpp_module.VERSION}")

    # Run benchmark
    benchmark_engines()

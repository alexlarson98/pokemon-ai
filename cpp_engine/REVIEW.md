# C++ Engine Architectural Review

## Status: ✅ BLOCKING ISSUES FIXED

This document tracks the architectural review of the C++ engine against the Python reference implementation.

## Fixed Issues (Phase 1 Complete)

### 1. ✅ Logic Registry Integration

**Status**: FIXED
- Created `logic_registry.hpp` and `logic_registry.cpp`
- Supports C++ native callbacks and Python callbacks via pybind11
- Attack, ability, and trainer effects can be registered
- Guards, modifiers, and hooks architecture in place

### 2. ✅ Energy Cost Validation

**Status**: FIXED
- Implemented `calculate_provided_energy()` - properly handles basic and special energy
- Implemented `can_pay_energy_cost()` - validates type matching with Colorless wildcard
- Updated `has_energy_for_attack()` to use the new validation

### 3. ✅ Stack-Based Energy Attachment

**Status**: FIXED
- Changed from E×T actions to single "Attach Energy" action
- Uses resolution stack with SelectFromZoneStep + AttachToTargetStep
- Matches Python engine's `use_stack=True` approach

### 4. ✅ Filter Criteria Matching

**Status**: FIXED
- Implemented `card_matches_filter()` in engine.cpp
- Supports all Python filter types: supertype, subtype, max_hp, pokemon_type, energy_type, name, evolves_from, rare_candy_target, super_rod_target, is_basic

### 5. ✅ JSON Parsing (nlohmann/json)

**Status**: FIXED
- Integrated nlohmann/json via FetchContent
- Rewrote CardDatabase with proper JSON parsing
- Full attack/ability/weakness/resistance parsing

### 6. ✅ Attack/Ability Parsing

**Status**: FIXED
- `parse_attack()` - extracts cost, damage, text, damage modifiers
- `parse_ability()` - extracts name, text, type, category detection
- Weakness/resistance with multiplier/value

---

## Fixed Issues (Phase 2 Complete)

### 7. ✅ Global Permission Checks

**Status**: FIXED
- Added `is_ability_blocked_by_passive()` to LogicRegistry
- Added `check_global_block()` for global guards (Item Lock, etc.)
- Added `scan_global_modifiers()` and `scan_global_guards()` for board scanning
- Integrated into `get_trainer_actions()` and `get_ability_actions()`
- Matches Python's `is_ability_blocked_by_passive()` and `check_global_block()`

### 8. ✅ Passive Ability Category

**Status**: FIXED
- Added "passive" category to AbilityDef (6 categories: attack, activatable, modifier, guard, hook, passive)
- Added `PassiveCallback` and `PassiveConditionCallback` types
- Added `register_passive()` method to LogicRegistry
- Ability parsing now detects passive ability locks (e.g., Klefki's Mischievous Lock)

### 9. ✅ Modifier Application

**Status**: FIXED
- `calculate_damage()` now applies damage modifiers (damage_dealt, damage_taken, global_damage)
- `calculate_retreat_cost()` now applies retreat modifiers (retreat_cost, global_retreat_cost)
- Uses proper weakness multiplier from CardDef

### 10. ✅ Hook Triggering

**Status**: FIXED
- Added hook triggering in `apply_play_basic()` for on_play hooks
- Added hook triggering in `apply_evolve()` for on_evolve hooks
- Hooks check ability block before triggering

---

## Remaining Issues (Phase 3 - Nice to Have)

### 11. ⚠️ Mulligan Phase Logic

**Python**: Opponent chooses to draw or decline

**C++ Status**: Needs update to provide draw/decline choice

**Impact**: LOW - Mulligan handling incomplete

---

### 12. ⚠️ Theoretical Deck Cards (ISMCTS)

**Python**: Handles imperfect information for deck searches

**C++ Status**: Not implemented - uses actual deck contents only

**Impact**: MEDIUM - ISMCTS won't work correctly with hidden information

---

### 13. ✅ Functional ID Deduplication

**Status**: FIXED
- Added `get_functional_id()` to CardDef
- All deduplication now uses functional ID (not name)
- Properly handles same-name cards with different stats (e.g., Charmander 80HP with ability vs 70HP)

---

### 14. ⚠️ Attack Cost Reduction

**Status**: Not implemented
**Impact**: LOW - Cards that reduce attack costs won't work

---

### 15. ⚠️ Stadium Actions

**Status**: Not implemented
**Impact**: LOW - Activatable stadiums won't work

---

### 16. ⚠️ Tool Capacity Check

**Status**: Assumes max 1 tool per Pokemon
**Impact**: LOW - Tool Box, etc. won't work

---

## Architecture Summary

### Files Created/Updated

1. **CMakeLists.txt** - Added nlohmann/json via FetchContent
2. **card_database.hpp/cpp** - Full JSON parsing with attacks/abilities
3. **logic_registry.hpp/cpp** - Card effect registration system
4. **engine.hpp/cpp** - Energy validation, filter matching, stack-based attachment
5. **pybind_module.cpp** - Exposed LogicRegistry to Python

### Key Design Decisions

1. **Python Callback Support**: LogicRegistry can accept Python functions via pybind11, allowing gradual migration of card logic

2. **Stack-Based Approach**: Energy attachment and item effects use resolution stack to minimize action space

3. **Reusable Filter System**: `card_matches_filter()` can be used by any resolution step

4. **Type-Safe Energy Validation**: Proper matching of specific types with Colorless wildcard

### Usage Example

```python
from pokemon_engine_cpp import PokemonEngine, AttackResult

engine = PokemonEngine()

# Register Python attack handler
def burning_darkness(state, attacker, attack_name, target):
    result = AttackResult()
    # Count opponent's benched Pokemon with damage
    bench_with_damage = sum(1 for p in target.owner.board.bench if p.damage_counters > 0)
    result.damage_dealt = 180 + (20 * bench_with_damage)
    return result

engine.get_logic_registry().register_attack("sv3-125", "Burning Darkness", burning_darkness)

# Now attacks will use the registered handler
actions = engine.get_legal_actions(state)
```

---

## Build Instructions

```batch
cd cpp_engine
build.bat
```

Or manually:
```batch
mkdir build && cd build
cmake -G "Visual Studio 17 2022" -A x64 -DCMAKE_BUILD_TYPE=Release -DBUILD_PYTHON_BINDINGS=ON ..
cmake --build . --config Release --parallel
```

---

## Next Steps for Full Parity

1. Register all Charizard EX deck card effects in logic registry
2. Implement ISMCTS theoretical deck support
3. Update mulligan to provide draw/decline choice
4. Add integration tests comparing Python vs C++ engine results
5. Add Python bindings for new passive/hook/modifier functions

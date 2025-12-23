# C++ Engine Architectural Review

## Critical Issues Found

### 1. **Missing Logic Registry Integration**

**Python**: Uses `logic_registry` extensively for card-specific behavior:
```python
# Custom action generators for cards
generator = logic_registry.get_card_logic(card.card_id, 'generator')
if generator:
    generated_actions = generator(state, card, player)
```

**C++ Status**: ❌ **NOT IMPLEMENTED**
- `engine.cpp` has TODO comments but no logic registry
- Card effects, attack effects, ability effects all hardcoded or missing
- Without this, **no card logic will work** (Infernal Reign, Ultra Ball, Rare Candy, etc.)

**Impact**: HIGH - Core functionality broken

---

### 2. **Missing Energy Cost Validation**

**Python**: Proper energy matching with type validation:
```python
def _can_pay_energy_cost(self, provided_energy: Dict, cost: List[EnergyType], converted_cost: int) -> bool:
    # Complex matching: Fire requires Fire, Colorless is wild
```

**C++ Status**: ❌ **INCOMPLETE**
```cpp
bool PokemonEngine::has_energy_for_attack(const CardInstance& pokemon,
                                          const std::vector<EnergyType>& cost) const {
    // Simple check: total energy >= cost length
    return pokemon.total_attached_energy() >= static_cast<int>(cost.size());
}
```

**Impact**: HIGH - Attacks validated incorrectly (could attack without proper energy types)

---

### 3. **Missing Stack-Based Energy Attachment**

**Python**: Uses resolution stack for energy attachment:
```python
def _get_attach_energy_actions(self, state: GameState) -> List[Action]:
    # Returns SINGLE action that initiates resolution stack
    return [Action(
        action_type=ActionType.ATTACH_ENERGY,
        player_id=player.player_id,
        parameters={'use_stack': True},
        display_label="Attach Energy"
    )]
```

**C++ Status**: ❌ **WRONG APPROACH**
```cpp
std::vector<Action> PokemonEngine::get_energy_attach_actions(const GameState& state) const {
    // Generates E×T actions directly (old approach)
    for (const auto& card : player.hand.cards) {
        for (const auto* pokemon : pokemon_list) {
            actions.push_back(Action::attach_energy(...));
        }
    }
}
```

**Impact**: MEDIUM - Higher branching factor than necessary

---

### 4. **Missing Global Permission Checks**

**Python**: Checks for Item Lock, Ability Lock, etc.:
```python
if self.check_global_permission(state, 'play_item', player.player_id):
    # Can play item
```

**C++ Status**: ❌ **NOT IMPLEMENTED**
- No `check_global_permission()` method
- No active effects parsing for locks/blocks

**Impact**: MEDIUM - Cards like Klefki's Mischievous Lock won't work

---

### 5. **Missing Mulligan Phase Logic**

**Python**: Opponent chooses to draw or decline:
```python
def _get_mulligan_actions(self, state: GameState) -> List[Action]:
    return [
        Action(action_type=ActionType.MULLIGAN_DRAW, metadata={"draw": True}),
        Action(action_type=ActionType.MULLIGAN_DRAW, metadata={"draw": False})
    ]
```

**C++ Status**: ❌ **INCORRECT**
```cpp
std::vector<Action> PokemonEngine::get_mulligan_actions(const GameState& state) const {
    // Only generates one action, missing the choice
    Action draw(ActionType::MULLIGAN_DRAW, player.player_id);
    actions.push_back(draw);
    return actions;
}
```

**Impact**: LOW - Mulligan handling incomplete

---

### 6. **Missing Theoretical Deck Cards (ISMCTS)**

**Python**: Handles imperfect information for deck searches:
```python
def _get_theoretical_deck_cards(self, player, step, state):
    # Uses initial_deck_counts minus hand to show valid search options
    # Essential for belief-based MCTS
```

**C++ Status**: ❌ **NOT IMPLEMENTED**
- No `_get_theoretical_deck_cards()` equivalent
- Resolution stack actions use actual deck contents only

**Impact**: MEDIUM - ISMCTS won't work correctly with hidden information

---

### 7. **Missing Filter Criteria Matching**

**Python**: Rich filter system for card selection:
```python
def _card_matches_step_filter(self, card, filter_criteria, state, player):
    # Supports: supertype, subtype, max_hp, pokemon_type, energy_type,
    # name, evolves_from, rare_candy_target, super_rod_target
```

**C++ Status**: ❌ **STUB ONLY**
```cpp
// Resolution stack has TODO: Apply filter_criteria
// No actual filtering implemented
```

**Impact**: HIGH - Complex cards (Buddy-Buddy Poffin, Rare Candy) won't filter correctly

---

### 8. **Missing Functional ID Deduplication**

**Python**: Deduplicates by functional ID for MCTS optimization:
```python
# Pidgey 50HP and Pidgey 60HP are different functional IDs
functional_id = self._compute_functional_id(card_def)
```

**C++ Status**: ❌ **NOT IMPLEMENTED**
- Uses card name only for deduplication
- Different card versions treated as identical

**Impact**: MEDIUM - Sub-optimal MCTS branching

---

### 9. **Missing Dynamic Retreat Cost Calculation**

**Python**: Accounts for tools and effects:
```python
def calculate_retreat_cost(self, state: GameState, pokemon: CardInstance) -> int:
    # Base cost - tool modifiers - effect modifiers
```

**C++ Status**: ⚠️ **PARTIAL**
```cpp
int PokemonEngine::calculate_retreat_cost(const GameState& state,
                                          const CardInstance& pokemon) const {
    // Only returns base cost, no modifiers
    return def->retreat_cost;
}
```

**Impact**: LOW - Float Stone, Jet Energy retreat reduction won't work

---

### 10. **Missing Attack Cost Calculation**

**Python**: Dynamic attack cost (for cards that reduce cost):
```python
def calculate_attack_cost(self, state: GameState, pokemon: CardInstance, attack: 'Attack') -> int:
    # Base cost modified by effects
```

**C++ Status**: ❌ **NOT IMPLEMENTED**

**Impact**: LOW - Cards that reduce attack costs won't work

---

### 11. **Missing Stadium Actions**

**Python**: Some stadiums have activatable effects:
```python
def _get_stadium_actions(self, state: GameState) -> List[Action]:
    # Check if stadium has generator
```

**C++ Status**: ❌ **NOT IMPLEMENTED**
- No `get_stadium_actions()` method
- Stadium generators not checked

**Impact**: LOW - Activatable stadiums won't work

---

### 12. **Missing Tool Capacity Check**

**Python**: Some Pokemon can hold multiple tools:
```python
max_tools = self.get_max_tool_capacity(target)
if len(target.attached_tools) < max_tools:
```

**C++ Status**: ❌ **NOT IMPLEMENTED**
- Assumes max 1 tool per Pokemon

**Impact**: LOW - Tool Box, etc. won't work

---

### 13. **Missing Provided Energy Calculation**

**Python**: Handles special energy providing multiple types:
```python
def _calculate_provided_energy(self, pokemon: CardInstance) -> Dict[EnergyType, int]:
    # Double Turbo provides 2 Colorless
    # Reversal Energy provides different amounts
```

**C++ Status**: ❌ **NOT IMPLEMENTED**
- Just counts number of attached energy cards

**Impact**: MEDIUM - Special energy cards won't work correctly

---

## Structural Issues

### 14. **CardDatabase JSON Parsing is Fragile**

Current implementation uses custom string parsing:
```cpp
std::string extract_string(const std::string& json, const std::string& key) {
    // Simple substring search - breaks on nested objects
}
```

**Recommendation**: Use nlohmann/json or rapidjson for robust parsing

---

### 15. **Missing Attack/Ability Parsing in CardDatabase**

```cpp
// TODO: Parse attacks and abilities
```

Without this, CardDef won't have attacks/abilities populated.

---

### 16. **No RNG Integration for Shuffling**

Python passes RNG seed for deterministic simulation:
```python
def __init__(self, random_seed: Optional[int] = None):
    if random_seed is not None:
        random.seed(random_seed)
```

C++ has RNG but:
- No way to pass seed from Python
- Shuffle not integrated into game operations

---

## Summary Prioritization

### Must Fix Before Use (Blocking)

1. **Logic Registry** - No card effects work
2. **Energy Cost Validation** - Attacks broken
3. **Filter Criteria Matching** - Complex cards broken
4. **Attack/Ability Parsing** - CardDef incomplete

### Should Fix (Functionality Gaps)

5. Stack-Based Energy Attachment
6. Global Permission Checks
7. Theoretical Deck Cards (ISMCTS)
8. Functional ID Deduplication
9. Provided Energy Calculation

### Nice to Have (Edge Cases)

10. Mulligan Phase Logic
11. Dynamic Retreat Cost
12. Attack Cost Calculation
13. Stadium Actions
14. Tool Capacity Check

---

## Recommended Action Plan

### Phase 1: Core Fixes (Essential for basic operation)
1. Integrate nlohmann/json for proper JSON parsing
2. Complete CardDef parsing (attacks, abilities)
3. Implement basic logic registry (start with Python callbacks)
4. Fix energy cost validation

### Phase 2: MCTS Optimization
5. Implement stack-based energy attachment
6. Add filter criteria matching
7. Add functional ID deduplication

### Phase 3: Full Feature Parity
8. Add ISMCTS support (theoretical deck)
9. Add global permission checks
10. Complete effect modifier system

---

## Architecture Recommendations

### 1. Use Python Callbacks Initially

Rather than reimplementing all card logic in C++, use pybind11 to call Python functions:

```cpp
// C++ calls Python for complex card logic
py::function effect_func = logic_registry.attr("get_effect")(card_id, effect_name);
if (!effect_func.is_none()) {
    state = effect_func(state, attacker, defender).cast<GameState>();
}
```

This allows incremental migration while maintaining correctness.

### 2. Keep Python Engine as Reference

Don't remove Python engine - use it as:
- Reference implementation for tests
- Fallback for unimplemented features
- Validation against C++ results

### 3. Test at Boundaries

Create integration tests that compare:
- `py_engine.get_legal_actions(state)` vs `cpp_engine.get_legal_actions(state)`
- `py_engine.step(state, action)` vs `cpp_engine.step(state, action)`

Any deviation indicates a bug.

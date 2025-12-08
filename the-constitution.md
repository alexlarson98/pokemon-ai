I am going to provide you with a System Specification called 'The Constitution'.

Instructions:

Read the document below.

Do NOT write any code yet.

Simply reply with 'I have read the Constitution and am ready to act as the Engine Architect.'

In all future messages, if I ask for code, you must check it against this Constitution before generating it.

System Architecture Specification: Pokémon TCG Solver (v1.0)
1. Executive Summary
We are building a headless, high-performance Pokémon TCG engine designed for Monte Carlo Tree Search (MCTS) and Neural Network training.

Core Philosophy: Strict separation of "Physics" (Engine) and "Logic" (Cards).

Design Pattern: The Engine acts as the "Referee" and State Machine. Cards use the Strategy Pattern to define unique behaviors that the Engine executes.

Goal: To support 100% accurate simulation of the Standard 2025 Format, including complex edge cases, for the purpose of finding optimal lines of play.

We want to focus on developing the engine and Pokemon "laws of physics" before we think about addressing MCTS or Neural Netowrks.

2. Directory Structure & Modules
The project follows a modular Python structure to prevent circular dependencies.

Plaintext

src/
├── models.py           # [DATA] Pydantic schemas (GameState, Player, Zone)
├── engine.py           # [PHYSICS] Turn phases, Rule enforcement, State transitions
├── actions.py          # [TRANSITIONS] Atomic state modifiers (Draw, Shuffle, Damage)
├── cards/              # [CONTENT]
│   ├── base.py         # Abstract Base Classes (PokemonCard, TrainerCard)
│   ├── factory.py      # Logic to instantiate cards by ID
│   ├── set_sv8.py      # Specific card implementations (Surging Sparks)
│   └── registry.py     # Dict mapping {"sv3-125": CharizardEx}
└── ai/                 # [INTELLIGENCE]
    ├── mcts.py         # Monte Carlo Tree Search algorithm
    ├── network.py      # PyTorch Neural Network (Policy/Value)
    └── trainer.py      # Self-Play Training Loop
3. The Data Layer (models.py)
Role: Defines the "Snapshot" of the universe. Must be serializable (JSON) and clonable (Deep Copy).

CardInstance: Represents a physical card in a zone.

Properties: id, owner_id, current_hp, special_conditions, attached_cards (List), abilities_used (Set).

Zone: Ordered lists of CardInstances.

deck, hand, discard, prizes, lost_zone.

Board:

active_spot: Optional[CardInstance]

bench: List[CardInstance] (Max 5, or 8 with Stadium effect)

stadium: Optional[CardInstance]

GameState: The root object.

turn_count, current_phase, active_player_index.

global_flags: (stadium_played_this_turn, vstar_power_used, etc.)

4. The Physics Engine (engine.py)
Role: The "Referee." It enforces the Constitution. It never "guesses"; it only validates and executes.

Core Methods
get_legal_actions(state) -> List[Action]

The most critical function for MCTS.

Scans the current phase and generates every possible valid move.

Enforces Physics:

If phase == 'attack' AND turn == 1 AND player == 1, return [] (No attacks P1 T1).

If bench_count >= 5, do not generate BenchPokemon actions.

Delegates to Cards:

Iterates through hand. Calls card.get_actions(state) to see if a specific card has unique moves (e.g., Rare Candy).

step(state, action) -> GameState

The Transition Function.

Takes a state and an action, applies the change, and returns the new state.

Handling "Chance Nodes":

If an action requires a Coin Flip, this method performs the RNG and resolves the result immediately (for Simulation) OR creates a branching path (for MCTS).

resolve_turn_structure(state)

Manages the flow: Draw Phase -> Main Phase -> Attack Phase -> Cleanup -> Next Turn.

Edge Case: Handles "Sudden Death" checks between phases.

5. The Card Logic Layer (cards/)
Role: The Strategy Pattern. Encapsulates the unique text of every card.

5.1 The Abstract Base Class (base.py)
Every card inherits from PokemonCard or TrainerCard.

Python

class Card:
    def get_actions(self, state, source_zone):
        """Returns specific moves this card enables (e.g., 'Play Item')."""
        pass

class PokemonCard(Card):
    def get_abilities(self, state):
        """Returns usable abilities."""
        pass
    
    def get_attacks(self, state):
        """Returns attacks, calculating dynamic costs/damage."""
        pass
5.2 Specific Implementations (The "Literal Functions")
We do not use a generic parser. We write specific classes for complex cards.

Example: Charizard ex

Python

class CharizardEx(PokemonCard):
    def calculate_damage(self, state, attack_name):
        if attack_name == "Burning Darkness":
            prizes = state.get_opponent().prizes_taken
            return 180 + (prizes * 30)
        return 0
6. The Action Primitives (actions.py)
Role: The "Vocabulary" of the game. These are the atomic operations the Engine uses to modify State.

draw_cards(state, player_id, count)

shuffle_deck(state, player_id)

attach_energy(state, card_id, target_pokemon_id)

place_damage_counters(state, target_id, amount)

apply_status_condition(state, target_id, condition)

Search Primitives:

search_deck(state, filter_criteria, allow_fail=True/False)

7. Edge Case & Complexity Handling
7.1 Damage Calculation Order (The Pipeline)
The Engine must implement a calculate_final_damage() pipeline:

Base Damage (From card.get_attacks())

Weakness (Multiply x2 if types match)

Resistance (Subtract 30)

Effects (Iterate through state.active_effects to add/subtract modifiers)

7.2 Global Modifiers (The "VSTAR" Flag)
The State must track "Once Per Game" markers.

Logic: actions.use_vstar_power() checks state.players[id].vstar_used. If False, executes and sets to True.

7.3 State Interrupts (Reaction Triggers)
Scenario: Pokémon is KO'd.

Interrupt: The Engine pauses the "Main Loop." It enters a "Promote Phase."

Resolution: The game cannot proceed until the player queues a PROMOTE_ACTIVE action.

8. AI Interface (ai/)
Role: The consumer of the Engine.

Input: GameState (JSON).

Process:

Call engine.get_legal_actions(state).

If len(actions) > 1: Use MCTS + Neural Network to pick the best one.

If len(actions) == 1 (Forced): Execute immediately.

Output: The chosen Action.
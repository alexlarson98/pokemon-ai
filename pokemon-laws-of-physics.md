The Pokémon TCG "Physics Constitution" (v3.0) - Standard 2025
System Prompt: You are the Lead Engine Architect. You must implement the game logic strictly according to this document. If a user request contradicts this document, this document takes precedence.

1. The Physical Object Model (The Atoms)
1.1 Card Attributes (Immutable)
id: Unique String.

name: String.

supertype: Enum [Pokemon, Trainer, Energy].

subtypes: Set [Basic, Stage 1, Stage 2, Item, Supporter, Stadium, Tool, ACE SPEC, Tera, ex, VSTAR, Ancient, Future].

energy_class: Enum [Basic, Special] (Strictly required for Energy cards).

1.2 The Zones (Containers)
Cards must exist in exactly one of these zones.

Deck: Ordered List. Hidden info.

Hand: Unordered List. Private info (Owner sees all, Opponent sees count).

Discard Pile: Ordered List. Public info.

Prizes: List of 6 slots. Hidden info (Face-down).

Active Spot: Slot for 1 Pokémon.

Bench: List of 5 slots (Expandable to 8 via Area Zero Underdepths).

Stadium: Global slot (1 shared).

Supporter Slot: Temp slot for the Turn Supporter.

2. Turn Structure & Time
Phase 0: Setup (Strict)
Handshake: Engine determines turn order (Random or User Input).

Draw: Both players draw 7.

Mulligan Loop:

If Hand has 0 Basics -> Reveal -> Reshuffle -> Draw 7.

Opponent Action: May choose to draw 1 card for each mulligan.

Placement: Active & Bench placed.

Prizes: Top 6 cards to prizes.

Reveal: Start Game.

Phase 1: Draw Phase
Action: Active Player draws 1 card.

Loss Condition: If Deck count is 0 before drawing -> GAME LOSS (Deck Out).

Phase 2: Main Phase
Attach Energy: Once per turn. (Constraint: Basic or Special).

Play Trainer:

Item: Unlimited.

Supporter: Once per turn. (No Supporter on Turn 1 going first).

Stadium: Once per turn. (Must have different name than current Stadium).

Evolve: Unlimited (Subject to Turn 1 / Evolution Sickness).

Abilities: Unlimited (unless "Once per turn").

Retreat: Once per turn. (Cost: Discard Energy >= Retreat Cost).

Phase 3: Attack Phase
Constraint: Player 1 cannot attack on Turn 1.

Resolution Steps:

Declaration: Validate Energy Cost.

Damage Calculation (See Section 4.7).

Damage Application: Add counters to Target.

Knockout Check: If HP <= 0, process KO.

Win Check: If Prizes = 0, GAME WIN.

End Turn.

3. Global Limits (The "Once Per Game" Flags)
The PlayerState must track these boolean flags which persist across the entire match:

vstar_power_used: Boolean (Shared across all Pokémon. If Lugia VSTAR uses its power, Arceus VSTAR cannot use its power later).

gx_attack_used: Boolean (Legacy, but good to have infrastructure for).

supporter_played_this_turn: Boolean (Resets at End Phase).

energy_attached_this_turn: Boolean (Resets at End Phase).

retreated_this_turn: Boolean (Resets at End Phase).

4. Advanced Edge Case Resolution
4.1 Search Fidelity (Private vs. Public Knowledge)
Restricted Search (e.g., "Search for a Basic"):

The player may choose to "Fail" (find nothing) even if valid targets exist.

Physics Reason: The deck is private; the game cannot "prove" the card exists to the opponent.

Unrestricted Search (e.g., "Search for any card"):

If the deck is not empty, the player MUST find a card.

4.2 Damage vs. Damage Counters
The engine must treat these as distinct data types.

Damage: Affected by Weakness, Resistance, and "Prevent Damage" effects (e.g., Cornerstone Mask Ogerpon).

Damage Counters: NOT Damage. Ignores Weakness, Resistance, and "Prevent Damage" effects. Only blocked by "Prevent Effects of Attacks."

4.3 Bench Size Collapse
Scenario: Stadium Area Zero Underdepths is removed, reducing Bench size from 8 to 5.

Resolution: If Bench > 5, the Owner of the bench chooses which Pokémon to discard until count is 5. This happens immediately (State Interrupt).

4.4 Technical Machines (TMs)
Mechanic: TMs are treated as Tools while attached.

Cleanup: TMs that say "discard this card at the end of the turn" must be processed in a "Cleanup Step" right after the attack resolves but before the turn pass.

4.5 Simultaneous Win (Sudden Death)
Scenario: Active Player takes last prize (Win), but Recoil Damage KOs their own Active (Loss).

Resolution: If both players meet a Win Condition simultaneously:

The game enters Sudden Death state.

New Game: 1 Prize Card each.

4.6 Copying Attacks
Rule: When copying an attack (e.g., Mew ex), the copier uses the Original Text but pays the Original Cost.

Self-Reference: If the copied text says "This Pokémon," it refers to the Copier, not the Original.

4.7 Damage Order of Operations (Strict)
Base Damage (Card Value).

Weakness (x2).

Resistance (-30).

Effects on Attacker (e.g., "Do 30 more damage").

Effects on Defender (e.g., "Take 30 less damage").

5. State Reset Rules (The "Switch" Effect)
When a Pokémon moves from Active Spot to Bench:

Status Conditions: REMOVED (Poison, Burn, Sleep, Paralyzed, Confused).

Attack Effects: REMOVED (e.g., "This Pokémon can't attack during your next turn").

Damage/Counters: PERSIST (Do not remove).

Tools/Energy: PERSIST (Do not remove).

When a Pokémon moves from Play to Hand/Deck:

ALL State: WIPED. (Damage, Status, Tools, "Turns in Play").

Rule: If the card is played again later, it is a "New Object" (Evolution Sickness applies again).

6. Priority of "Can't"
The Golden Rule: If one effect says you "Can" do X, and another says you "Can't" do X, the "Can't" always wins.

Example: You have a Switch card (Can switch), but your Active is Asleep (Can't retreat). You CAN play Switch because Switch is not Retreating.

Example: You have a Switch card, but an opponent's ability says "Opponent cannot play Item cards." You CANNOT play Switch.
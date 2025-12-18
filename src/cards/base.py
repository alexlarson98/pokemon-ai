"""
Pokémon TCG Engine - Card Base Classes (cards/base.py)
Abstract Base Classes implementing the Strategy Pattern.

The Engine delegates to these classes for card-specific behavior.
All specific cards (e.g., CharizardEx, ProfessorResearch) inherit from these.

Architecture Pattern:
- Engine = Referee (knows rules)
- Cards = Strategy (know their own unique behavior)
- Separation of Physics (Engine) and Logic (Cards)

NEW: Data-Driven Factory Pattern
- DataDrivenPokemon/Trainer/Energy: Generic classes that load from JSON
- logic_registry.py: Contains card-specific logic functions
- Enables loading thousands of cards from JSON files
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, TYPE_CHECKING, Callable
from enum import Enum

# Avoid circular imports
if TYPE_CHECKING:
    from models import GameState, CardInstance, Action, Zone, PlayerState

from models import EnergyType, Subtype, ActionType


# ============================================================================
# 1. BASE CARD CLASS (All cards inherit from this)
# ============================================================================

class Card(ABC):
    """
    Abstract base class for all Pokémon TCG cards.

    The Engine queries cards for available actions through this interface.
    Subclasses override methods to implement card-specific behavior.
    """

    def __init__(
        self,
        card_id: str,
        name: str,
        subtypes: List[Subtype]
    ):
        """
        Initialize card definition.

        Args:
            card_id: Unique card identifier (e.g., "sv3-125")
            name: Card name (e.g., "Charizard ex")
            subtypes: List of card subtypes
        """
        self.card_id = card_id
        self.name = name
        self.subtypes = subtypes

    def get_actions(
        self,
        state: 'GameState',
        card_instance: 'CardInstance',
        source_zone: 'Zone'
    ) -> List['Action']:
        """
        Get available actions for this card in the current state.

        The Engine calls this on cards to check for special actions.

        Default behavior: Return [] (most cards don't provide passive actions)

        Override examples:
        - Rare Candy: Allows skipping evolution stages
        - Switch: Allows retreating without paying cost

        Args:
            state: Current game state
            card_instance: The specific card instance
            source_zone: Zone containing the card

        Returns:
            List of Action objects this card enables
        """
        return []

    @abstractmethod
    def can_play(self, state: 'GameState', card_instance: 'CardInstance') -> bool:
        """
        Check if this card can be played in the current state.

        Override to implement card-specific play restrictions.

        Args:
            state: Current game state
            card_instance: The specific card instance

        Returns:
            True if card can be played, False otherwise
        """
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.card_id}, name={self.name})"


# ============================================================================
# 2. POKEMON CARD BASE CLASS
# ============================================================================

class PokemonCard(Card):
    """
    Base class for all Pokémon cards.

    Defines the interface for Pokémon-specific mechanics:
    - Attacks (with dynamic damage calculation)
    - Abilities (with usage tracking)
    - HP, Weakness, Resistance, Retreat Cost
    """

    def __init__(
        self,
        card_id: str,
        name: str,
        subtypes: List[Subtype],
        hp: int,
        types: List[EnergyType],
        weakness: Optional[EnergyType] = None,
        resistance: Optional[EnergyType] = None,
        retreat_cost: int = 0,
        evolves_from: Optional[str] = None
    ):
        """
        Initialize Pokémon card definition.

        Args:
            card_id: Unique card identifier
            name: Pokémon name
            subtypes: Card subtypes (Basic, Stage 1, ex, VSTAR, etc.)
            hp: Maximum HP
            types: Pokémon types (can have multiple)
            weakness: Weakness type (×2 damage)
            resistance: Resistance type (-30 damage)
            retreat_cost: Number of energy to discard for retreat
            evolves_from: Name of Pokémon this evolves from
        """
        super().__init__(card_id, name, subtypes)
        self.hp = hp
        self.types = types
        self.base_weakness = weakness
        self.base_resistance = resistance
        self.base_retreat_cost = retreat_cost
        self.evolves_from = evolves_from

    def can_play(self, state: 'GameState', card_instance: 'CardInstance') -> bool:
        """
        Check if this Pokémon can be played.

        Default rules:
        - Basic Pokémon: Can play to Bench if space available
        - Evolution: Must have valid evolution target

        Returns:
            True if can be played
        """
        player = state.get_player(card_instance.owner_id)

        # Basic Pokémon: Check bench space
        if Subtype.BASIC in self.subtypes:
            return player.board.get_bench_count() < player.board.max_bench_size

        # Evolution: Check for valid targets (handled by engine)
        # This is a simplified check - full logic in engine
        return True

    # ========================================================================
    # ATTACKS
    # ========================================================================

    def get_attacks(
        self,
        state: 'GameState',
        card_instance: 'CardInstance'
    ) -> List[Dict]:
        """
        Get available attacks for this Pokémon.

        Returns attack data with DYNAMIC values (crucial for cards like
        Charizard ex that calculate damage based on game state).

        Override this method to implement specific attacks.

        Args:
            state: Current game state
            card_instance: The specific Pokémon instance

        Returns:
            List of attack dictionaries with structure:
            {
                'name': str,
                'cost': List[EnergyType],
                'damage': int,  # Can be calculated dynamically
                'text': str,
                'effects': List[callable]  # Effect functions
            }
        """
        return []

    def calculate_attack_damage(
        self,
        state: 'GameState',
        card_instance: 'CardInstance',
        attack_name: str
    ) -> int:
        """
        Calculate dynamic damage for a specific attack.

        Override for cards with variable damage (e.g., Charizard ex).

        Example:
            Charizard ex "Burning Darkness": 180 + (prizes_taken * 30)

        Args:
            state: Current game state
            card_instance: The attacking Pokémon
            attack_name: Name of the attack

        Returns:
            Base damage amount (before weakness/resistance)
        """
        # Default: Return base damage from attack definition
        for attack in self.get_attacks(state, card_instance):
            if attack['name'] == attack_name:
                return attack['damage']
        return 0

    def can_attack(
        self,
        state: 'GameState',
        card_instance: 'CardInstance',
        attack_name: str
    ) -> bool:
        """
        Check if this Pokémon can use a specific attack.

        Validates:
        - Energy cost requirement
        - Attack effects/restrictions
        - Status conditions

        Args:
            state: Current game state
            card_instance: The attacking Pokémon
            attack_name: Name of the attack

        Returns:
            True if attack can be used
        """
        # Check for blocking status conditions
        from models import StatusCondition
        if StatusCondition.ASLEEP in card_instance.status_conditions:
            return False
        if StatusCondition.PARALYZED in card_instance.status_conditions:
            return False

        # Check for attack effects
        if "cannot_attack_next_turn" in card_instance.attack_effects:
            return False

        # Check energy cost
        for attack in self.get_attacks(state, card_instance):
            if attack['name'] == attack_name:
                return self._has_sufficient_energy(card_instance, attack['cost'])

        return False

    def _has_sufficient_energy(
        self,
        card_instance: 'CardInstance',
        required_cost: List[EnergyType]
    ) -> bool:
        """
        Check if Pokémon has sufficient energy to pay attack cost.

        Handles Colorless energy wildcards.

        Args:
            card_instance: The Pokémon instance
            required_cost: Required energy cost

        Returns:
            True if cost can be paid
        """
        # TODO: Implement proper energy matching with Colorless wildcards
        # For now, simple count check
        return len(card_instance.attached_energy) >= len(required_cost)

    # ========================================================================
    # ABILITIES
    # ========================================================================

    def get_abilities(
        self,
        state: 'GameState',
        card_instance: 'CardInstance'
    ) -> List[Dict]:
        """
        Get available abilities for this Pokémon.

        Returns ability data, checking for usage restrictions.

        Override this method to implement specific abilities.

        Args:
            state: Current game state
            card_instance: The Pokémon instance

        Returns:
            List of ability dictionaries with structure:
            {
                'name': str,
                'type': str,  # 'passive', 'activated', 'once_per_turn'
                'text': str,
                'effect': callable  # Effect function
            }
        """
        return []

    def can_use_ability(
        self,
        state: 'GameState',
        card_instance: 'CardInstance',
        ability_name: str
    ) -> bool:
        """
        Check if an ability can be activated.

        Checks:
        - "Once per turn" restrictions
        - Special conditions (e.g., must be Active)

        Args:
            state: Current game state
            card_instance: The Pokémon instance
            ability_name: Name of the ability

        Returns:
            True if ability can be used
        """
        # Check if already used this turn
        if ability_name in card_instance.abilities_used_this_turn:
            return False

        # Additional checks can be added by subclasses
        return True

    # ========================================================================
    # STATS (with dynamic modification support)
    # ========================================================================

    def get_max_hp(
        self,
        state: 'GameState',
        card_instance: 'CardInstance'
    ) -> int:
        """
        Get maximum HP (supports dynamic modification).

        Override for effects like "This Pokémon has +50 HP".

        Args:
            state: Current game state
            card_instance: The Pokémon instance

        Returns:
            Maximum HP
        """
        return self.hp

    def get_weakness(
        self,
        state: 'GameState',
        card_instance: 'CardInstance'
    ) -> Optional[EnergyType]:
        """
        Get weakness type (supports dynamic modification).

        Override for effects like "This Pokémon has no Weakness".

        Args:
            state: Current game state
            card_instance: The Pokémon instance

        Returns:
            Weakness type or None
        """
        return self.base_weakness

    def get_resistance(
        self,
        state: 'GameState',
        card_instance: 'CardInstance'
    ) -> Optional[EnergyType]:
        """
        Get resistance type (supports dynamic modification).

        Override for effects like "This Pokémon has no Resistance".

        Args:
            state: Current game state
            card_instance: The Pokémon instance

        Returns:
            Resistance type or None
        """
        return self.base_resistance

    def get_retreat_cost(
        self,
        state: 'GameState',
        card_instance: 'CardInstance'
    ) -> int:
        """
        Get retreat cost (supports dynamic modification).

        Override for effects like "This Pokémon's retreat cost is 0".

        Example: Ability reduces retreat cost if condition met.

        Args:
            state: Current game state
            card_instance: The Pokémon instance

        Returns:
            Retreat cost (number of energy to discard)
        """
        return self.base_retreat_cost

    def get_types(
        self,
        state: 'GameState',
        card_instance: 'CardInstance'
    ) -> List[EnergyType]:
        """
        Get Pokémon types (supports dynamic modification).

        Override for effects that add/change types.

        Args:
            state: Current game state
            card_instance: The Pokémon instance

        Returns:
            List of energy types
        """
        return self.types

    # ========================================================================
    # EVOLUTION
    # ========================================================================

    def can_evolve_from(
        self,
        target: 'CardInstance',
        target_card: 'PokemonCard'
    ) -> bool:
        """
        Check if this card can evolve from the target Pokémon.

        Args:
            target: Target Pokémon instance
            target_card: Target Pokémon card definition

        Returns:
            True if evolution is valid
        """
        if self.evolves_from is None:
            return False

        return target_card.name == self.evolves_from


# ============================================================================
# 3. TRAINER CARD BASE CLASS
# ============================================================================

class TrainerCard(Card):
    """
    Base class for all Trainer cards (Item, Supporter, Stadium, Tool).

    Implements the play() method that executes card effects.
    """

    def __init__(
        self,
        card_id: str,
        name: str,
        subtypes: List[Subtype],
        text: str
    ):
        """
        Initialize Trainer card definition.

        Args:
            card_id: Unique card identifier
            name: Card name
            subtypes: Card subtypes (Item, Supporter, Stadium, Tool, ACE SPEC)
            text: Card text (effect description)
        """
        super().__init__(card_id, name, subtypes)
        self.text = text

    def can_play(self, state: 'GameState', card_instance: 'CardInstance') -> bool:
        """
        Check if this Trainer card can be played.

        Default checks for Supporter/Stadium restrictions.
        Override for card-specific restrictions.

        Args:
            state: Current game state
            card_instance: The card instance

        Returns:
            True if can be played
        """
        player = state.get_player(card_instance.owner_id)

        # Supporter: Check once-per-turn restriction
        if Subtype.SUPPORTER in self.subtypes:
            if player.supporter_played_this_turn:
                return False

            # Cannot play Supporter on Turn 1 going first
            if state.turn_count == 1 and state.active_player_index == 0:
                return False

        # Stadium: Check once-per-turn restriction
        if Subtype.STADIUM in self.subtypes:
            if player.stadium_played_this_turn:
                return False

            # Cannot play Stadium with same name as current Stadium
            if state.stadium is not None:
                # TODO: Compare card names (requires card registry)
                pass

        return True

    @abstractmethod
    def play(
        self,
        state: 'GameState',
        card_instance: 'CardInstance',
        targets: Optional[Dict] = None
    ) -> 'GameState':
        """
        Execute the Trainer card's effect.

        This is the core Strategy Pattern method - each Trainer implements
        its own unique effect.

        Args:
            state: Current game state
            card_instance: The card being played
            targets: Optional target selection (for interactive effects)

        Returns:
            Modified GameState after effect resolution

        Example implementations:
        - Professor's Research: Draw 7 cards, discard hand
        - Ultra Ball: Search deck for a Pokémon
        - Boss's Orders: Switch opponent's Active Pokémon
        """
        pass


# ============================================================================
# 4. ENERGY CARD BASE CLASS
# ============================================================================

class EnergyCard(Card):
    """
    Base class for Energy cards (Basic and Special).

    Energy cards are simpler - they provide energy when attached.
    """

    def __init__(
        self,
        card_id: str,
        name: str,
        energy_type: EnergyType,
        is_basic: bool,
        provides: Optional[List[EnergyType]] = None,
        special_effect: Optional[str] = None
    ):
        """
        Initialize Energy card definition.

        Args:
            card_id: Unique card identifier
            name: Energy name
            energy_type: Primary energy type
            is_basic: True if Basic Energy, False if Special
            provides: Energy types this card provides (for Special Energy)
            special_effect: Text description of special effect
        """
        from models import Subtype
        # Set subtypes based on is_basic flag
        # Note: Subtype.BASIC is used for Basic Pokemon AND Basic Energy
        # Special Energy doesn't have a Subtype entry, so we leave it empty
        subtypes = [Subtype.BASIC] if is_basic else []
        super().__init__(card_id, name, subtypes)

        self.energy_type = energy_type
        self.is_basic = is_basic
        self.provides = provides if provides else [energy_type]
        self.special_effect = special_effect

    def can_play(self, state: 'GameState', card_instance: 'CardInstance') -> bool:
        """
        Check if this Energy can be attached.

        Default: Check once-per-turn restriction.

        Args:
            state: Current game state
            card_instance: The Energy card instance

        Returns:
            True if can be attached
        """
        player = state.get_player(card_instance.owner_id)
        return not player.energy_attached_this_turn

    def get_energy_provided(
        self,
        state: 'GameState',
        card_instance: 'CardInstance'
    ) -> List[EnergyType]:
        """
        Get energy types this card provides.

        Override for Special Energy with conditional effects.

        Example: Double Turbo Energy provides 2 Colorless (but reduces damage)

        Args:
            state: Current game state
            card_instance: The Energy card instance

        Returns:
            List of energy types provided
        """
        return self.provides

    def get_special_effect(
        self,
        state: 'GameState',
        card_instance: 'CardInstance'
    ) -> Optional[Dict]:
        """
        Get special effect of this Energy (if any).

        Override for Special Energy with additional effects.

        Example: Reversal Energy has different effect if Prize count condition met

        Args:
            state: Current game state
            card_instance: The Energy card instance

        Returns:
            Effect dictionary or None
        """
        return None


# ============================================================================
# 5. HELPER CLASSES FOR ATTACK/ABILITY EFFECTS
# ============================================================================

class AttackEffect:
    """
    Represents an attack's effect.

    Separates damage from additional effects (status, energy removal, etc.)
    """

    def __init__(
        self,
        name: str,
        effect_function: callable,
        description: str
    ):
        """
        Initialize attack effect.

        Args:
            name: Effect name
            effect_function: Function that applies the effect
            description: Text description
        """
        self.name = name
        self.effect_function = effect_function
        self.description = description

    def apply(
        self,
        state: 'GameState',
        attacker: 'CardInstance',
        defender: 'CardInstance'
    ) -> 'GameState':
        """
        Apply the effect to the game state.

        Args:
            state: Current game state
            attacker: Attacking Pokémon
            defender: Defending Pokémon

        Returns:
            Modified GameState
        """
        return self.effect_function(state, attacker, defender)


class AbilityEffect:
    """
    Represents an ability's effect.

    Handles both passive and activated abilities.
    """

    def __init__(
        self,
        name: str,
        ability_type: str,  # 'passive', 'activated', 'once_per_turn'
        effect_function: callable,
        description: str,
        activation_condition: Optional[callable] = None
    ):
        """
        Initialize ability effect.

        Args:
            name: Ability name
            ability_type: Type of ability
            effect_function: Function that applies the effect
            description: Text description
            activation_condition: Optional condition check function
        """
        self.name = name
        self.ability_type = ability_type
        self.effect_function = effect_function
        self.description = description
        self.activation_condition = activation_condition

    def can_activate(
        self,
        state: 'GameState',
        card_instance: 'CardInstance'
    ) -> bool:
        """
        Check if ability can be activated.

        Args:
            state: Current game state
            card_instance: Pokémon with the ability

        Returns:
            True if ability can activate
        """
        if self.activation_condition:
            return self.activation_condition(state, card_instance)
        return True

    def apply(
        self,
        state: 'GameState',
        card_instance: 'CardInstance'
    ) -> 'GameState':
        """
        Apply the ability effect to the game state.

        Args:
            state: Current game state
            card_instance: Pokémon using the ability

        Returns:
            Modified GameState
        """
        return self.effect_function(state, card_instance)


# ============================================================================
# 6. DATA-DRIVEN CARD CLASSES (NEW - JSON-based cards)
# ============================================================================

class DataDrivenPokemon(PokemonCard):
    """
    Generic Pokémon card class that loads from JSON data.

    Enables loading thousands of cards without writing Python classes.
    Card-specific logic is looked up in logic_registry.py.

    Example JSON:
    {
        "id": "sv3-pt5-006",
        "name": "Raging Bolt ex",
        "hp": 280,
        "types": ["Lightning", "Dragon"],
        "retreatCost": ["Colorless", "Colorless"],
        "weaknesses": [{"type": "Grass", "value": "×2"}],
        "attacks": [
            {"name": "Burst Roar", "cost": ["Lightning"], "text": "..."},
            {"name": "Bellowing Thunder", "cost": ["Lightning", "Lightning", "Dragon"], "damage": "70×", "text": "..."}
        ]
    }
    """

    def __init__(self, json_data: Dict):
        """
        Initialize Pokémon from JSON data.

        Args:
            json_data: Card data from JSON file
        """
        # Parse subtypes
        subtypes = []
        for subtype_str in json_data.get('subtypes', []):
            try:
                subtypes.append(Subtype(subtype_str))
            except ValueError:
                # Handle unmapped subtypes
                if subtype_str.lower() == "basic":
                    subtypes.append(Subtype.BASIC)
                elif "stage 1" in subtype_str.lower():
                    subtypes.append(Subtype.STAGE_1)
                elif "stage 2" in subtype_str.lower():
                    subtypes.append(Subtype.STAGE_2)
                elif subtype_str.lower() == "ex":
                    subtypes.append(Subtype.EX)

        # Parse types
        types = []
        for type_str in json_data.get('types', []):
            try:
                types.append(EnergyType(type_str))
            except ValueError:
                # Handle "Dragon", "Colorless", etc.
                if type_str == "Dragon":
                    types.append(EnergyType.COLORLESS)  # Map Dragon to Colorless for now
                elif type_str == "Colorless":
                    types.append(EnergyType.COLORLESS)

        # Parse weakness
        weakness = None
        if json_data.get('weaknesses'):
            weakness_data = json_data['weaknesses'][0]
            try:
                weakness = EnergyType(weakness_data['type'])
            except (ValueError, KeyError):
                pass

        # Parse resistance
        resistance = None
        if json_data.get('resistances'):
            resistance_data = json_data['resistances'][0]
            try:
                resistance = EnergyType(resistance_data['type'])
            except (ValueError, KeyError):
                pass

        # Parse retreat cost
        retreat_cost = len(json_data.get('retreatCost', []))

        # Parse evolution
        evolves_from = json_data.get('evolvesFrom')

        # Initialize base class
        super().__init__(
            card_id=json_data['id'],
            name=json_data['name'],
            subtypes=subtypes,
            hp=int(json_data.get('hp', 0)),
            types=types,
            weakness=weakness,
            resistance=resistance,
            retreat_cost=retreat_cost,
            evolves_from=evolves_from
        )

        # Store raw JSON for attacks/abilities lookup
        self.json_data = json_data

    @property
    def attacks(self) -> List:
        """
        Get attacks as simple objects for engine compatibility.

        Returns a list of attack objects with name and cost attributes.
        """
        from collections import namedtuple
        Attack = namedtuple('Attack', ['name', 'cost', 'converted_energy_cost', 'damage', 'text'])

        attacks = []
        for attack_data in self.json_data.get('attacks', []):
            # Parse cost
            cost = []
            for cost_str in attack_data.get('cost', []):
                try:
                    cost.append(EnergyType(cost_str))
                except ValueError:
                    if cost_str == "Colorless":
                        cost.append(EnergyType.COLORLESS)

            # Get converted energy cost (total number of energy required)
            converted_cost = attack_data.get('convertedEnergyCost', len(cost))

            attacks.append(Attack(
                name=attack_data.get('name', ''),
                cost=cost,
                converted_energy_cost=converted_cost,
                damage=attack_data.get('damage', ''),
                text=attack_data.get('text', '')
            ))

        return attacks

    def get_attacks(self, state: 'GameState', card_instance: 'CardInstance') -> List[Dict]:
        """
        Get attacks from JSON, with logic from registry.

        Returns:
            List of attack dictionaries
        """
        from cards.logic_registry import LOGIC_MAP

        attacks = []

        for attack_data in self.json_data.get('attacks', []):
            attack_name = attack_data['name']

            # Parse cost
            cost = []
            for cost_str in attack_data.get('cost', []):
                try:
                    cost.append(EnergyType(cost_str))
                except ValueError:
                    if cost_str == "Colorless":
                        cost.append(EnergyType.COLORLESS)

            # Get damage (could be "70×", "60+", or just "60")
            damage_str = attack_data.get('damage', '0')
            if '×' in damage_str or '+' in damage_str:
                # Variable damage - look up logic in registry
                if attack_name in LOGIC_MAP:
                    damage = LOGIC_MAP[attack_name](state, card_instance, 'calculate')
                else:
                    damage = 0  # Unknown variable damage
            else:
                # Fixed damage
                damage = int(damage_str) if damage_str and damage_str != '' else 0

            # Look up effect logic
            effect_func = LOGIC_MAP.get(attack_name)
            effects = [effect_func] if effect_func else []

            attacks.append({
                'name': attack_name,
                'cost': cost,
                'damage': damage,
                'text': attack_data.get('text', ''),
                'effects': effects
            })

        return attacks

    def get_abilities(self, state: 'GameState', card_instance: 'CardInstance') -> List[Dict]:
        """
        Get abilities from JSON, with logic from registry.

        Returns:
            List of ability dictionaries
        """
        from cards.logic_registry import LOGIC_MAP

        abilities = []

        for ability_data in self.json_data.get('abilities', []):
            ability_name = ability_data['name']

            # Look up logic in registry
            effect_func = LOGIC_MAP.get(ability_name)

            if effect_func:
                abilities.append({
                    'name': ability_name,
                    'type': ability_data.get('type', 'activated'),
                    'text': ability_data.get('text', ''),
                    'effect': effect_func
                })

        return abilities


class DataDrivenTrainer(TrainerCard):
    """
    Generic Trainer card class that loads from JSON data.

    Card-specific logic is looked up in logic_registry.py by card name.

    Example JSON:
    {
        "id": "sv3-163",
        "name": "Professor's Research",
        "supertype": "Trainer",
        "subtypes": ["Supporter"],
        "rules": ["Discard your hand and draw 7 cards."]
    }
    """

    def __init__(self, json_data: Dict):
        """
        Initialize Trainer from JSON data.

        Args:
            json_data: Card data from JSON file
        """

        # Parse subtypes
        subtypes = []
        for subtype_str in json_data.get('subtypes', []):
            # Normalize the subtype string

            try:
                subtypes.append(Subtype(subtype_str))
            except ValueError:
                # Handle unmapped subtypes (fallback if normalization doesn't match enum)
                if subtype_str == "Item":
                    subtypes.append(Subtype.ITEM)
                elif subtype_str == "Supporter":
                    subtypes.append(Subtype.SUPPORTER)
                elif subtype_str == "Stadium":
                    subtypes.append(Subtype.STADIUM)
                elif subtype_str == "Pokemon Tool":
                    subtypes.append(Subtype.TOOL)

        # Get card text
        text = ' '.join(json_data.get('rules', []))

        # Initialize base class
        super().__init__(
            card_id=json_data['id'],
            name=json_data['name'],
            subtypes=subtypes,
            text=text
        )

        self.json_data = json_data

    def play(
        self,
        state: 'GameState',
        card_instance: 'CardInstance',
        targets: Optional[Dict] = None
    ) -> 'GameState':
        """
        Execute Trainer effect by looking up logic in registry.

        Raises:
            NotImplementedError: If card logic not found in registry
        """
        from cards.logic_registry import LOGIC_MAP

        # Look up logic by card name
        logic_func = LOGIC_MAP.get(self.name)

        if logic_func:
            return logic_func(state, card_instance, targets)
        else:
            raise NotImplementedError(
                f"Logic for '{self.name}' not found in logic_registry. "
                f"Add implementation to LOGIC_MAP."
            )


class DataDrivenEnergy(EnergyCard):
    """
    Generic Energy card class that loads from JSON data.

    Handles both Basic and Special Energy.
    Special Energy logic is looked up in logic_registry.py.

    Example JSON (Basic):
    {
        "id": "energy-fire",
        "name": "Fire Energy",
        "supertype": "Energy",
        "subtypes": ["Basic"]
    }

    Example JSON (Special):
    {
        "id": "sv2-190",
        "name": "Jet Energy",
        "supertype": "Energy",
        "subtypes": ["Special"],
        "rules": ["Provides Colorless Energy. When attached from hand to Bench, switch."]
    }
    """

    def __init__(self, json_data: Dict):
        """
        Initialize Energy from JSON data.

        Args:
            json_data: Card data from JSON file
        """
        # Determine if Basic or Special
        is_basic = "Basic" in json_data.get('subtypes', [])

        # Infer energy type from name (for Basic Energy)
        name = json_data['name']
        energy_type = EnergyType.COLORLESS  # Default

        if "Fire" in name:
            energy_type = EnergyType.FIRE
        elif "Water" in name:
            energy_type = EnergyType.WATER
        elif "Grass" in name:
            energy_type = EnergyType.GRASS
        elif "Lightning" in name:
            energy_type = EnergyType.LIGHTNING
        elif "Psychic" in name:
            energy_type = EnergyType.PSYCHIC
        elif "Fighting" in name:
            energy_type = EnergyType.FIGHTING
        elif "Darkness" in name:
            energy_type = EnergyType.DARKNESS
        elif "Metal" in name:
            energy_type = EnergyType.METAL

        # Special Energy provides Colorless by default (can be overridden)
        provides = [energy_type] if is_basic else [EnergyType.COLORLESS]

        # Get special effect text
        special_effect = ' '.join(json_data.get('rules', [])) if not is_basic else None

        # Initialize base class
        super().__init__(
            card_id=json_data['id'],
            name=name,
            energy_type=energy_type,
            is_basic=is_basic,
            provides=provides,
            special_effect=special_effect
        )

        self.json_data = json_data

    def on_attach(
        self,
        state: 'GameState',
        target_pokemon_id: str
    ) -> 'GameState':
        """
        Execute on-attach effect (for Special Energy like Jet Energy).

        This is called immediately when the Energy is attached.

        Args:
            state: Current game state
            target_pokemon_id: ID of Pokémon receiving the Energy

        Returns:
            Modified GameState
        """
        from cards.logic_registry import LOGIC_MAP

        # Look up on-attach logic by card name
        attach_func = LOGIC_MAP.get(self.name)

        if attach_func:
            return attach_func(state, target_pokemon_id)

        # No special effect - return state unchanged
        return state

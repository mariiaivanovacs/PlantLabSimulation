"""
Watering Tool
Adds water to soil, respecting physical constraints
"""
from typing import Dict, Any
from .base import BaseTool, ToolAction, ToolResult, ToolType


class WateringTool(BaseTool):
    """
    Watering System Tool

    Adds water to the soil, respecting:
    - Maximum flow rate
    - Saturation limits (excess runs off)

    Primary effects:
    - Increases soil_water

    Secondary effects:
    - Reduces water_stress
    - Enables damage recovery
    """

    tool_type = ToolType.WATERING

    def __init__(self, max_flow_rate: float = 2.0):
        """
        Initialize watering tool

        Args:
            max_flow_rate: Maximum water delivery rate (L/h)
        """
        self.max_flow_rate = max_flow_rate

    @property
    def description(self) -> str:
        return "Add water to soil to maintain hydration"

    @property
    def parameter_schema(self) -> Dict[str, Any]:
        return {
            'volume_L': {
                'type': 'float',
                'description': 'Amount of water to add (liters)',
                'min': 0,
                'max': 10,
                'required': True
            },
            'flow_rate_L_per_h': {
                'type': 'float',
                'description': 'Water delivery rate (L/h)',
                'min': 0.1,
                'max': self.max_flow_rate,
                'default': 1.0
            }
        }

    def validate_parameters(self, parameters: Dict[str, Any]) -> tuple[bool, str]:
        """Validate watering parameters"""
        if 'volume_L' not in parameters:
            return False, "Missing required parameter: volume_L"

        volume = parameters['volume_L']
        if not isinstance(volume, (int, float)) or volume < 0:
            return False, f"Invalid volume_L: {volume}. Must be non-negative number."

        if volume > 10:
            return False, f"volume_L ({volume}) exceeds maximum (10L)"

        flow_rate = parameters.get('flow_rate_L_per_h', 1.0)
        if flow_rate > self.max_flow_rate:
            return False, f"flow_rate ({flow_rate}) exceeds maximum ({self.max_flow_rate})"

        return True, ""

    def apply(self, state: Any, action: ToolAction) -> ToolResult:
        """
        Apply watering action

        Update logic:
        actual_added = min(volume_L, flow_rate_L_per_h × 1h)
        soil_water_new = soil_water + (actual_added / pot_volume) × 100
        if soil_water_new > saturation → runoff occurs
        """
        is_valid, error = self.validate_parameters(action.parameters)
        if not is_valid:
            return ToolResult(
                success=False,
                tool_type=self.tool_type,
                action_id=action.action_id,
                changes={},
                message=f"Validation failed: {error}"
            )

        volume_L = action.parameters['volume_L']
        flow_rate = action.parameters.get('flow_rate_L_per_h', 1.0)

        # Calculate actual water added (limited by flow rate for 1 hour)
        actual_added = min(volume_L, flow_rate)

        # Store before values
        before_water = state.soil_water

        # Calculate new soil water percentage
        # soil_water is in %, pot_volume is in L
        water_added_percent = (actual_added / state.pot_volume) * 100
        new_soil_water = state.soil_water + water_added_percent

        # Handle saturation and runoff
        # Get saturation from profile if available, otherwise use 55%
        saturation = getattr(state, '_saturation', 55.0)
        runoff = 0.0
        if new_soil_water > saturation:
            runoff = new_soil_water - saturation
            new_soil_water = saturation

        # Apply change
        state.soil_water = new_soil_water

        # Track watering event for stress recovery
        # When water is supplied, the stress recovery mechanism kicks in
        state.last_watering_hour = state.hour

        return ToolResult(
            success=True,
            tool_type=self.tool_type,
            action_id=action.action_id,
            changes={
                'soil_water': {'before': before_water, 'after': new_soil_water},
                'water_added_L': actual_added,
                'runoff_percent': runoff
            },
            message=f"Added {actual_added:.2f}L water. Soil water: {before_water:.1f}% → {new_soil_water:.1f}%"
        )

    def calculate_required_water(
        self,
        current_soil_water: float,
        target_soil_water: float,
        pot_volume: float
    ) -> float:
        """
        Calculate water needed to reach target soil moisture

        Args:
            current_soil_water: Current soil water (%)
            target_soil_water: Target soil water (%)
            pot_volume: Pot volume (L)

        Returns:
            Required water in liters
        """
        if target_soil_water <= current_soil_water:
            return 0.0

        water_percent_needed = target_soil_water - current_soil_water
        water_L = (water_percent_needed / 100) * pot_volume

        return max(0, water_L)

    def calculate_adaptive_water_amount(
        self,
        state: Any,
        wilting_point: float = 15.0,
        optimal_min: float = 30.0,
        field_capacity: float = 35.0,
        growth_strategy: str = "leaf_first",
        root_fraction: float = 0.1,
        previous_water_stress: float = 0.0
    ) -> float:
        """
        Calculate adaptive watering amount based on plant size, growth strategy,
        and water stress trends.

        STRATEGY-AWARE WATERING:
        - LEAF_FIRST (lettuce): Higher water needs (1.3x base)
          - High leaf area = high transpiration
          - Shallow roots = less efficient water use
        - STRUCTURE_FIRST (tomato): Lower water needs (0.7x base)
          - Lower leaf area = lower transpiration initially
          - Deep roots = better water efficiency

        STRESS-RESPONSIVE WATERING:
        - If water stress is increasing (current > previous), increase water amount
        - Prevents stress from escalating to damaging levels
        - More aggressive intervention for leaf-first plants

        IMPORTANT: Seedlings need LESS water than mature plants!
        - Overwatering seedlings causes root rot and fungal growth
        - Small root systems can't absorb large water volumes
        - Gradually increase water as plant grows

        Args:
            state: Current PlantState with biomass, leaf_area, phenological_stage, water_stress
            wilting_point: Permanent wilting point (%)
            optimal_min: Lower bound of optimal range (%)
            field_capacity: Field capacity (%)
            growth_strategy: "leaf_first" or "structure_first"
            root_fraction: Fraction of biomass in roots (0-1)
            previous_water_stress: Water stress from previous timestep (0-1)

        Returns:
            Recommended water amount in liters
        """
        import logging
        logger = logging.getLogger(__name__)

        biomass = state.biomass
        leaf_area = state.leaf_area
        current_soil_water = state.soil_water
        pot_volume = state.pot_volume
        current_water_stress = getattr(state, 'water_stress', 0.0)

        # Get phenological stage if available
        stage = getattr(state, 'phenological_stage', None)
        stage_name = stage.value if stage else 'unknown'

        # STRATEGY MULTIPLIER: Adjusts base water needs
        # Leaf-first: Higher water needs (more transpiration)
        # Structure-first: Lower water needs (root efficiency)
        if growth_strategy == "leaf_first":
            strategy_multiplier = 1.3
        elif growth_strategy == "structure_first":
            # Root efficiency reduces water needs
            # Higher root fraction = lower multiplier
            base_multiplier = 0.7
            root_efficiency_bonus = min(0.15, (root_fraction - 0.1) * 0.5) if root_fraction > 0.1 else 0
            strategy_multiplier = base_multiplier - root_efficiency_bonus  # 0.55 - 0.7
        else:
            strategy_multiplier = 1.0

        # STRESS-RESPONSIVE ADJUSTMENT
        # If water stress is increasing, boost water amount
        stress_boost = 1.0
        stress_increasing = current_water_stress > previous_water_stress + 0.02  # 2% threshold

        if stress_increasing:
            # Calculate stress increase rate
            stress_delta = current_water_stress - previous_water_stress

            # Boost water proportionally to stress increase
            # More aggressive for leaf-first plants
            if growth_strategy == "leaf_first":
                stress_boost = 1.0 + min(0.8, stress_delta * 4.0)  # Up to 80% boost
            else:
                stress_boost = 1.0 + min(0.5, stress_delta * 2.5)  # Up to 50% boost

            logger.info(f"Stress increasing ({previous_water_stress:.2f} → {current_water_stress:.2f}), "
                       f"applying {stress_boost:.2f}x water boost")

        # HIGH STRESS EMERGENCY WATERING
        # If stress is already high, intervene more aggressively
        if current_water_stress > 0.5:
            # High stress: increase target and max water
            emergency_boost = 1.0 + (current_water_stress - 0.5) * 0.6  # Up to 30% additional
            stress_boost *= emergency_boost
            logger.warning(f"High water stress ({current_water_stress:.2f}), emergency boost {emergency_boost:.2f}x")

        # ADAPTIVE WATERING BASED ON BIOMASS
        # Strategy: Adjust both target moisture AND maximum water amount
        # FIX: Use field_capacity as target for medium/large plants to prevent stress

        if biomass < 1.0:
            # SEED / TINY SEEDLING: Minimal water
            # Risk: Root rot, damping off, fungal growth
            # Strategy: Keep soil slightly moist, not saturated
            target_water = optimal_min - 3.0  # ~27% for lettuce (slightly higher)
            max_water_per_day = 0.08 * strategy_multiplier  # Max 0.08L (80ml) per day

        elif biomass < 5.0:
            # SMALL SEEDLING: Light watering
            # Risk: Overwatering still dangerous
            # Strategy: Gradual increase as roots develop
            target_water = optimal_min + 2.0  # 32% for lettuce
            max_water_per_day = (0.15 + (biomass - 1.0) * 0.05) * strategy_multiplier  # 0.15-0.35L

        elif biomass < 15.0:
            # MEDIUM SEEDLING: Moderate watering
            # Risk: Reduced, but still avoid saturation
            # Strategy: Water to near field capacity
            target_water = optimal_min + (field_capacity - optimal_min) * 0.5  # Midpoint
            max_water_per_day = (0.4 + (biomass - 5.0) * 0.04) * strategy_multiplier  # 0.4-0.8L

        elif biomass < 30.0:
            # LARGER SEEDLING: More aggressive watering
            # Strategy: Water to field capacity
            target_water = field_capacity  # 45% for lettuce
            max_water_per_day = (0.8 + (biomass - 15.0) * 0.05) * strategy_multiplier  # 0.8-1.55L

        else:
            # MATURE PLANT: Full watering based on ET
            # Risk: Low, established root system
            # Strategy: Maintain field capacity, large volumes allowed
            target_water = field_capacity  # 45% for lettuce

            # Calculate water need based on leaf area (proxy for ET)
            # Larger leaf area = more transpiration = more water needed
            # FIX: Use realistic ET rate for indoor plants: 0.15 L/h/m² × 14h light = 2.1 L/day/m²
            estimated_daily_et = leaf_area * 2.5  # L/day (conservative)
            max_water_per_day = max(1.5, estimated_daily_et * 1.5) * strategy_multiplier  # Min 1.5L, +50% safety

        # Apply stress boost to max water
        max_water_per_day *= stress_boost

        # STRESS-RESPONSIVE TARGET ADJUSTMENT
        # If stress is increasing, raise the target moisture level
        if stress_increasing and current_water_stress > 0.2:
            # Raise target by up to 5% when stress is increasing
            target_boost = min(5.0, (current_water_stress - 0.2) * 10.0)
            target_water = min(field_capacity, target_water + target_boost)
            logger.debug(f"Raised target water to {target_water:.1f}% due to stress")

        # Calculate water needed to reach target
        if current_soil_water >= target_water:
            # Already at or above target - no watering needed
            # UNLESS stress is high and increasing
            if not (stress_increasing and current_water_stress > 0.3):
                logger.debug(f"Adaptive watering: NO WATER - soil {current_soil_water:.1f}% >= target {target_water:.1f}%")
                return 0.0

        water_deficit_percent = target_water - current_soil_water
        water_needed_L = (water_deficit_percent / 100) * pot_volume

        # Apply maximum limit based on plant size
        water_amount = min(water_needed_L, max_water_per_day)

        # Never water if soil is already very wet (> field capacity)
        # UNLESS stress is somehow still high (possible waterlogging issue)
        if current_soil_water > field_capacity and current_water_stress < 0.3:
            logger.debug(f"Adaptive watering: NO WATER - soil {current_soil_water:.1f}% > field capacity {field_capacity:.1f}%")
            return 0.0

        # Minimum threshold: don't water if deficit is tiny
        if water_needed_L < 0.01 and not stress_increasing:  # Less than 10ml
            logger.debug(f"Adaptive watering: NO WATER - deficit too small ({water_needed_L*1000:.1f}ml)")
            return 0.0

        logger.debug(f"Adaptive watering: {water_amount:.3f}L (biomass={biomass:.2f}g, "
                    f"soil={current_soil_water:.1f}%, target={target_water:.1f}%, "
                    f"strategy={growth_strategy}, stress_boost={stress_boost:.2f}x)")

        return max(0.0, water_amount)

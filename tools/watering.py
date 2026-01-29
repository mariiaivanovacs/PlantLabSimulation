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
        field_capacity: float = 35.0
    ) -> float:
        """
        Calculate adaptive watering amount based on plant size and growth stage

        IMPORTANT: Seedlings need LESS water than mature plants!
        - Overwatering seedlings causes root rot and fungal growth
        - Small root systems can't absorb large water volumes
        - Gradually increase water as plant grows

        Strategy:
        1. Seed/tiny seedling (< 1g): Minimal water, keep soil slightly moist
        2. Small seedling (1-5g): Light watering, avoid saturation
        3. Medium seedling (5-30g): Moderate watering as roots develop
        4. Mature plant (> 30g): Full watering based on ET and leaf area

        Args:
            state: Current PlantState with biomass, leaf_area, phenological_stage
            wilting_point: Permanent wilting point (%)
            optimal_min: Lower bound of optimal range (%)
            field_capacity: Field capacity (%)

        Returns:
            Recommended water amount in liters
        """
        biomass = state.biomass
        leaf_area = state.leaf_area
        current_soil_water = state.soil_water
        pot_volume = state.pot_volume

        # Get phenological stage if available
        stage = getattr(state, 'phenological_stage', None)
        stage_name = stage.value if stage else 'unknown'

        # ADAPTIVE WATERING BASED ON BIOMASS
        # Strategy: Adjust both target moisture AND maximum water amount

        if biomass < 1.0:
            # SEED / TINY SEEDLING: Minimal water
            # Risk: Root rot, damping off, fungal growth
            # Strategy: Keep soil slightly moist, not saturated
            # Target: Lower than optimal to prevent overwatering
            target_water = optimal_min - 5.0  # ~25% for tomato
            max_water_per_day = 0.05  # Max 0.05L (50ml) per day

        elif biomass < 5.0:
            # SMALL SEEDLING: Light watering
            # Risk: Overwatering still dangerous
            # Strategy: Gradual increase as roots develop
            target_water = optimal_min  # 30% for tomato
            max_water_per_day = 0.1 + (biomass - 1.0) * 0.025  # 0.1-0.2L

        elif biomass < 30.0:
            # MEDIUM SEEDLING: Moderate watering
            # Risk: Reduced, but still avoid saturation
            # Strategy: Increase proportionally to biomass
            target_water = optimal_min + 2.5  # 32.5% for tomato
            max_water_per_day = 0.2 + (biomass - 5.0) * 0.012  # 0.2-0.5L

        else:
            # MATURE PLANT: Full watering based on ET
            # Risk: Low, established root system
            # Strategy: Maintain optimal moisture, can handle larger volumes
            target_water = field_capacity  # 35% for tomato

            # Calculate water need based on leaf area (proxy for ET)
            # Larger leaf area = more transpiration = more water needed
            # Typical ET: 0.3 L/h/m² × 24h = 7.2 L/day/m²
            estimated_daily_et = leaf_area * 7.2  # L/day
            max_water_per_day = estimated_daily_et * 1.2  # +20% safety margin

        # Calculate water needed to reach target
        if current_soil_water >= target_water:
            # Already at or above target - no watering needed
            # DEBUG
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"Adaptive watering: NO WATER - soil {current_soil_water:.1f}% >= target {target_water:.1f}%")
            return 0.0

        water_deficit_percent = target_water - current_soil_water
        water_needed_L = (water_deficit_percent / 100) * pot_volume

        # Apply maximum limit based on plant size
        water_amount = min(water_needed_L, max_water_per_day)

        # Never water if soil is already very wet (> field capacity)
        if current_soil_water > field_capacity:
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"Adaptive watering: NO WATER - soil {current_soil_water:.1f}% > field capacity {field_capacity:.1f}%")
            return 0.0

        # Minimum threshold: don't water if deficit is tiny
        if water_needed_L < 0.01:  # Less than 10ml
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"Adaptive watering: NO WATER - deficit too small ({water_needed_L*1000:.1f}ml)")
            return 0.0

        # DEBUG
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"Adaptive watering: {water_amount:.3f}L (biomass={biomass:.2f}g, soil={current_soil_water:.1f}%, target={target_water:.1f}%)")

        return max(0.0, water_amount)

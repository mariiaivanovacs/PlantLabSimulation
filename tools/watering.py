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

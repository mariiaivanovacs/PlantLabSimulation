"""
HVAC Tool
Controls air temperature via heating/cooling
"""
from typing import Dict, Any
from .base import BaseTool, ToolAction, ToolResult, ToolType


class HVACTool(BaseTool):
    """
    HVAC (Heating, Ventilation, Air Conditioning) Tool

    Controls air temperature in the growing environment.

    Primary effects:
    - Adjusts air_temp toward target
    - Soil temperature follows (with lag)

    Secondary effects:
    - Temperature affects f_temp growth multiplier
    - Temperature affects ET rate
    - Extreme temps cause damage accumulation
    """

    tool_type = ToolType.HVAC

    def __init__(
        self,
        min_temp: float = 5.0,
        max_temp: float = 40.0,
        max_rate_C_per_h: float = 5.0
    ):
        """
        Initialize HVAC tool

        Args:
            min_temp: Minimum achievable temperature (°C)
            max_temp: Maximum achievable temperature (°C)
            max_rate_C_per_h: Maximum temperature change per hour
        """
        self.min_temp = min_temp
        self.max_temp = max_temp
        self.max_rate_C_per_h = max_rate_C_per_h

    @property
    def description(self) -> str:
        return "Control air temperature via heating/cooling"

    @property
    def parameter_schema(self) -> Dict[str, Any]:
        return {
            'target_temp_C': {
                'type': 'float',
                'description': 'Target air temperature (°C)',
                'min': self.min_temp,
                'max': self.max_temp,
                'required': True
            },
            'max_rate_C_per_h': {
                'type': 'float',
                'description': 'Maximum temperature change rate (°C/h)',
                'min': 0.1,
                'max': self.max_rate_C_per_h,
                'default': self.max_rate_C_per_h
            }
        }

    def validate_parameters(self, parameters: Dict[str, Any]) -> tuple[bool, str]:
        """Validate HVAC parameters"""
        if 'target_temp_C' not in parameters:
            return False, "Missing required parameter: target_temp_C"

        target = parameters['target_temp_C']
        if not isinstance(target, (int, float)):
            return False, f"Invalid target_temp_C: {target}"

        if target < self.min_temp or target > self.max_temp:
            return False, f"target_temp_C ({target}) outside range [{self.min_temp}, {self.max_temp}]"

        return True, ""

    def apply(self, state: Any, action: ToolAction) -> ToolResult:
        """
        Apply HVAC action

        Update logic:
        temp_error = target_temp_C - air_temp
        temp_change = clamp(temp_error, -max_rate, max_rate)
        air_temp += temp_change
        soil_temp += 0.2 × temp_change (soil lags behind)
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

        target_temp = action.parameters['target_temp_C']
        max_rate = action.parameters.get('max_rate_C_per_h', self.max_rate_C_per_h)

        # Store before values
        before_air_temp = state.air_temp
        before_soil_temp = state.soil_temp

        # Calculate temperature change
        temp_error = target_temp - state.air_temp
        temp_change = max(-max_rate, min(max_rate, temp_error))

        # Apply changes
        state.air_temp += temp_change
        state.soil_temp += 0.2 * temp_change  # Soil lags behind

        return ToolResult(
            success=True,
            tool_type=self.tool_type,
            action_id=action.action_id,
            changes={
                'air_temp': {'before': before_air_temp, 'after': state.air_temp},
                'soil_temp': {'before': before_soil_temp, 'after': state.soil_temp},
                'temp_change': temp_change,
                'target_reached': abs(state.air_temp - target_temp) < 0.1
            },
            message=f"Air temp: {before_air_temp:.1f}°C → {state.air_temp:.1f}°C (target: {target_temp:.1f}°C)"
        )

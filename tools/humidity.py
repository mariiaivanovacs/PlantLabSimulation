"""
Humidity Control Tool
Adjusts relative humidity via humidifier/dehumidifier
"""
from typing import Dict, Any
import math
from .base import BaseTool, ToolAction, ToolResult, ToolType


class HumidityTool(BaseTool):
    """
    Humidity Control Tool

    Controls relative humidity using humidifier/dehumidifier.

    Primary effects:
    - Adjusts relative_humidity toward target
    - VPD is recalculated automatically

    Secondary effects:
    - VPD affects ET rate
    - High VPD (low RH) increases water stress if soil is dry
    """

    tool_type = ToolType.HUMIDITY

    def __init__(
        self,
        min_RH: float = 20.0,
        max_RH: float = 95.0,
        max_rate_RH_per_h: float = 10.0
    ):
        """
        Initialize humidity tool

        Args:
            min_RH: Minimum achievable RH (%)
            max_RH: Maximum achievable RH (%)
            max_rate_RH_per_h: Maximum RH change per hour
        """
        self.min_RH = min_RH
        self.max_RH = max_RH
        self.max_rate_RH_per_h = max_rate_RH_per_h

    @property
    def description(self) -> str:
        return "Control relative humidity via humidifier/dehumidifier"

    @property
    def parameter_schema(self) -> Dict[str, Any]:
        return {
            'target_RH': {
                'type': 'float',
                'description': 'Target relative humidity (%)',
                'min': self.min_RH,
                'max': self.max_RH,
                'required': True
            },
            'max_rate_RH_per_h': {
                'type': 'float',
                'description': 'Maximum RH change rate (%/h)',
                'min': 1.0,
                'max': self.max_rate_RH_per_h,
                'default': self.max_rate_RH_per_h
            }
        }

    def validate_parameters(self, parameters: Dict[str, Any]) -> tuple[bool, str]:
        """Validate humidity parameters"""
        if 'target_RH' not in parameters:
            return False, "Missing required parameter: target_RH"

        target = parameters['target_RH']
        if not isinstance(target, (int, float)):
            return False, f"Invalid target_RH: {target}"

        if target < self.min_RH or target > self.max_RH:
            return False, f"target_RH ({target}) outside range [{self.min_RH}, {self.max_RH}]"

        return True, ""

    def _calculate_vpd(self, air_temp: float, RH: float) -> float:
        """Calculate VPD from temperature and humidity"""
        # Saturation Vapor Pressure (Tetens formula)
        SVP = 0.6108 * math.exp(17.27 * air_temp / (air_temp + 237.3))
        # Vapor Pressure Deficit
        VPD = SVP * (1 - RH / 100)
        return max(0, VPD)

    def apply(self, state: Any, action: ToolAction) -> ToolResult:
        """
        Apply humidity control action

        Update logic:
        RH_error = target_RH - relative_humidity
        RH_change = clamp(RH_error, -max_rate, max_rate)
        relative_humidity += RH_change
        VPD = calculated from temp and RH
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

        target_RH = action.parameters['target_RH']
        max_rate = action.parameters.get('max_rate_RH_per_h', self.max_rate_RH_per_h)

        # Store before values
        before_RH = state.relative_humidity
        before_VPD = state.VPD

        # Calculate RH change
        RH_error = target_RH - state.relative_humidity
        RH_change = max(-max_rate, min(max_rate, RH_error))

        # Apply changes
        state.relative_humidity += RH_change
        state.relative_humidity = max(self.min_RH, min(self.max_RH, state.relative_humidity))

        # Recalculate VPD
        state.VPD = self._calculate_vpd(state.air_temp, state.relative_humidity)

        return ToolResult(
            success=True,
            tool_type=self.tool_type,
            action_id=action.action_id,
            changes={
                'relative_humidity': {'before': before_RH, 'after': state.relative_humidity},
                'VPD': {'before': before_VPD, 'after': state.VPD},
                'RH_change': RH_change,
                'target_reached': abs(state.relative_humidity - target_RH) < 1.0
            },
            message=f"RH: {before_RH:.1f}% → {state.relative_humidity:.1f}% (VPD: {state.VPD:.2f} kPa)"
        )

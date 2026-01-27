"""
Ventilation Tool
Exchanges air to cool, dehumidify, and adjust CO2
"""
from typing import Dict, Any
import math
from .base import BaseTool, ToolAction, ToolResult, ToolType


class VentilationTool(BaseTool):
    """
    Ventilation Tool

    Exchanges indoor air with outside air.

    Primary effects:
    - Modulates air_temp toward outside temp
    - Modulates relative_humidity toward outside RH
    - Modulates CO2 toward ambient levels

    Secondary effects:
    - Cooling effect reduces heat stress
    - Brings conditions toward ambient
    """

    tool_type = ToolType.VENTILATION

    def __init__(
        self,
        max_exchange_rate: float = 0.5,  # 50% air exchange per hour at full speed
        ambient_temp: float = 20.0,
        ambient_RH: float = 50.0,
        ambient_CO2: float = 400.0
    ):
        """
        Initialize ventilation tool

        Args:
            max_exchange_rate: Max air exchange rate (0-1)
            ambient_temp: Default outside temperature (°C)
            ambient_RH: Default outside RH (%)
            ambient_CO2: Default outside CO2 (ppm)
        """
        self.max_exchange_rate = max_exchange_rate
        self.default_ambient_temp = ambient_temp
        self.default_ambient_RH = ambient_RH
        self.default_ambient_CO2 = ambient_CO2

    @property
    def description(self) -> str:
        return "Exchange air with outside to cool and adjust atmosphere"

    @property
    def parameter_schema(self) -> Dict[str, Any]:
        return {
            'fan_speed': {
                'type': 'float',
                'description': 'Fan speed (0-100%)',
                'min': 0,
                'max': 100,
                'required': True
            },
            'outside_temp_C': {
                'type': 'float',
                'description': 'Outside temperature (°C)',
                'min': -10,
                'max': 45,
                'default': self.default_ambient_temp
            },
            'outside_RH': {
                'type': 'float',
                'description': 'Outside relative humidity (%)',
                'min': 10,
                'max': 100,
                'default': self.default_ambient_RH
            },
            'outside_CO2': {
                'type': 'float',
                'description': 'Outside CO2 level (ppm)',
                'min': 350,
                'max': 500,
                'default': self.default_ambient_CO2
            }
        }

    def validate_parameters(self, parameters: Dict[str, Any]) -> tuple[bool, str]:
        """Validate ventilation parameters"""
        if 'fan_speed' not in parameters:
            return False, "Missing required parameter: fan_speed"

        fan_speed = parameters['fan_speed']
        if not isinstance(fan_speed, (int, float)) or fan_speed < 0 or fan_speed > 100:
            return False, f"Invalid fan_speed: {fan_speed}. Must be 0-100."

        return True, ""

    def _calculate_vpd(self, air_temp: float, RH: float) -> float:
        """Calculate VPD from temperature and humidity"""
        SVP = 0.6108 * math.exp(17.27 * air_temp / (air_temp + 237.3))
        VPD = SVP * (1 - RH / 100)
        return max(0, VPD)

    def apply(self, state: Any, action: ToolAction) -> ToolResult:
        """
        Apply ventilation action

        Update logic:
        exchange_rate = fan_speed / 100 × max_exchange_rate
        air_temp = air_temp × (1 - exchange_rate) + outside_temp × exchange_rate
        relative_humidity = RH × (1 - exchange_rate) + outside_RH × exchange_rate
        CO2 = CO2 × (1 - exchange_rate) + outside_CO2 × exchange_rate
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

        fan_speed = action.parameters['fan_speed']
        outside_temp = action.parameters.get('outside_temp_C', self.default_ambient_temp)
        outside_RH = action.parameters.get('outside_RH', self.default_ambient_RH)
        outside_CO2 = action.parameters.get('outside_CO2', self.default_ambient_CO2)

        # Calculate exchange rate
        exchange_rate = (fan_speed / 100) * self.max_exchange_rate

        # Store before values
        before_temp = state.air_temp
        before_RH = state.relative_humidity
        before_VPD = state.VPD
        before_CO2 = state.CO2

        # Apply air exchange (weighted average with outside)
        state.air_temp = state.air_temp * (1 - exchange_rate) + outside_temp * exchange_rate
        state.relative_humidity = state.relative_humidity * (1 - exchange_rate) + outside_RH * exchange_rate
        state.CO2 = state.CO2 * (1 - exchange_rate) + outside_CO2 * exchange_rate

        # Recalculate VPD
        state.VPD = self._calculate_vpd(state.air_temp, state.relative_humidity)

        return ToolResult(
            success=True,
            tool_type=self.tool_type,
            action_id=action.action_id,
            changes={
                'air_temp': {'before': before_temp, 'after': state.air_temp},
                'relative_humidity': {'before': before_RH, 'after': state.relative_humidity},
                'VPD': {'before': before_VPD, 'after': state.VPD},
                'CO2': {'before': before_CO2, 'after': state.CO2},
                'exchange_rate': exchange_rate,
                'fan_speed': fan_speed
            },
            message=f"Ventilation at {fan_speed:.0f}%: Temp {before_temp:.1f}→{state.air_temp:.1f}°C, CO2 {before_CO2:.0f}→{state.CO2:.0f}ppm"
        )

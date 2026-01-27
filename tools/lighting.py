"""
Lighting Tool
Controls photosynthetically active radiation (PAR)
"""
from typing import Dict, Any
from .base import BaseTool, ToolAction, ToolResult, ToolType


class LightingTool(BaseTool):
    """
    Lighting System Tool

    Controls light intensity (PAR) for photosynthesis.

    Primary effects:
    - Sets light_PAR level

    Secondary effects:
    - Increased PAR → more photosynthesis → more growth
    - Increased PAR → more ET (transpiration)
    - Lamp heat → increases air_temp
    """

    tool_type = ToolType.LIGHTING

    def __init__(
        self,
        max_PAR: float = 2000.0,
        max_power_W: float = 1000.0,
        heat_coefficient: float = 0.7
    ):
        """
        Initialize lighting tool

        Args:
            max_PAR: Maximum PAR output (µmol/m²/s)
            max_power_W: Maximum lamp power (W)
            heat_coefficient: Fraction of power converted to heat
        """
        self.max_PAR = max_PAR
        self.max_power_W = max_power_W
        self.heat_coefficient = heat_coefficient

    @property
    def description(self) -> str:
        return "Control light intensity for photosynthesis"

    @property
    def parameter_schema(self) -> Dict[str, Any]:
        return {
            'target_PAR': {
                'type': 'float',
                'description': 'Target PAR level (µmol/m²/s)',
                'min': 0,
                'max': self.max_PAR,
                'required': True
            },
            'power_W': {
                'type': 'float',
                'description': 'Lamp power (W) - for heat calculation',
                'min': 0,
                'max': self.max_power_W,
                'default': None  # Auto-calculated from PAR if not provided
            }
        }

    def validate_parameters(self, parameters: Dict[str, Any]) -> tuple[bool, str]:
        """Validate lighting parameters"""
        if 'target_PAR' not in parameters:
            return False, "Missing required parameter: target_PAR"

        target_PAR = parameters['target_PAR']
        if not isinstance(target_PAR, (int, float)) or target_PAR < 0:
            return False, f"Invalid target_PAR: {target_PAR}. Must be non-negative."

        if target_PAR > self.max_PAR:
            return False, f"target_PAR ({target_PAR}) exceeds maximum ({self.max_PAR})"

        return True, ""

    def apply(self, state: Any, action: ToolAction) -> ToolResult:
        """
        Apply lighting action

        Update logic:
        light_PAR = target_PAR
        heat_added = power_W × heat_coeff × 1h / (room_volume × air_heat_capacity)
        air_temp += heat_added
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

        target_PAR = action.parameters['target_PAR']

        # Auto-calculate power if not provided (linear approximation)
        power_W = action.parameters.get('power_W')
        if power_W is None:
            # Approximate: 400W lamp gives ~600 PAR
            power_W = (target_PAR / 600) * 400

        # Store before values
        before_PAR = state.light_PAR
        before_temp = state.air_temp

        # Set new PAR
        state.light_PAR = target_PAR

        # Calculate heat added to room
        # Air heat capacity ≈ 1.005 kJ/(kg·K), air density ≈ 1.2 kg/m³
        # So room heat capacity ≈ 1.2 kJ/(m³·K)
        air_heat_capacity = 1.2  # kJ/(m³·K)

        if state.room_volume > 0:
            # Convert power to kJ (W × h = Wh, Wh × 0.0036 = kJ... but we want temp change)
            # Actually: power_W × 1h × 3600s/h = J, /1000 = kJ
            # heat_kJ = power_W × heat_coeff × 3600 / 1000
            # temp_change = heat_kJ / (room_volume × air_heat_capacity)

            # Simplified: temp change per hour ≈ (power_W × heat_coeff) / (room_volume × 100)
            heat_added = (power_W * self.heat_coefficient) / (state.room_volume * 100)
            state.air_temp += heat_added
        else:
            heat_added = 0

        return ToolResult(
            success=True,
            tool_type=self.tool_type,
            action_id=action.action_id,
            changes={
                'light_PAR': {'before': before_PAR, 'after': target_PAR},
                'air_temp': {'before': before_temp, 'after': state.air_temp},
                'power_W': power_W,
                'heat_added_C': heat_added
            },
            message=f"Set PAR to {target_PAR:.0f} µmol/m²/s (was {before_PAR:.0f})"
        )

    def calculate_optimal_PAR(
        self,
        plant_optimal_PAR: float,
        current_stress_level: float
    ) -> float:
        """
        Calculate recommended PAR level

        Args:
            plant_optimal_PAR: Plant's optimal PAR from profile
            current_stress_level: Current combined stress (0-1)

        Returns:
            Recommended PAR level
        """
        if current_stress_level > 0.5:
            # Reduce light during high stress
            return plant_optimal_PAR * 0.7
        return plant_optimal_PAR

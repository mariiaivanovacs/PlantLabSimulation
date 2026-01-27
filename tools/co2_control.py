"""
CO2 Control Tool
Enriches or controls CO2 levels in the growing environment
"""
from typing import Dict, Any
from .base import BaseTool, ToolAction, ToolResult, ToolType

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from physics.co2 import co2_grams_to_ppm, AMBIENT_CO2_PPM, OPTIMAL_CO2_MIN, OPTIMAL_CO2_MAX


class CO2ControlTool(BaseTool):
    """
    CO2 Enrichment/Control Tool

    Injects CO2 into the growing environment to enhance photosynthesis.
    Controlled environments often maintain 800-1200 ppm for optimal growth.

    Primary effects:
    - Increases CO2 level in the room

    Secondary effects:
    - Higher CO2 → enhanced photosynthesis (up to 30% more)
    - Too high CO2 (>2000 ppm) can be harmful
    """

    tool_type = ToolType.CO2_CONTROL

    def __init__(
        self,
        max_injection_rate_g_per_h: float = 50.0,
        min_co2_ppm: float = 200.0,
        max_co2_ppm: float = 2000.0
    ):
        """
        Initialize CO2 control tool

        Args:
            max_injection_rate_g_per_h: Maximum CO2 injection rate (g/h)
            min_co2_ppm: Minimum safe CO2 level (ppm)
            max_co2_ppm: Maximum safe CO2 level (ppm)
        """
        self.max_injection_rate = max_injection_rate_g_per_h
        self.min_co2_ppm = min_co2_ppm
        self.max_co2_ppm = max_co2_ppm

    @property
    def description(self) -> str:
        return "Inject CO2 to enhance photosynthesis"

    @property
    def parameter_schema(self) -> Dict[str, Any]:
        return {
            'target_co2_ppm': {
                'type': 'float',
                'description': 'Target CO2 level (ppm)',
                'min': self.min_co2_ppm,
                'max': self.max_co2_ppm,
                'default': OPTIMAL_CO2_MIN
            },
            'injection_g': {
                'type': 'float',
                'description': 'Amount of CO2 to inject (g)',
                'min': 0,
                'max': self.max_injection_rate,
                'default': None  # Auto-calculated from target if not provided
            },
            'maintain_hours': {
                'type': 'int',
                'description': 'Hours to maintain target level',
                'min': 1,
                'max': 24,
                'default': 1
            }
        }

    def validate_parameters(self, parameters: Dict[str, Any]) -> tuple[bool, str]:
        """Validate CO2 control parameters"""
        target = parameters.get('target_co2_ppm')
        injection = parameters.get('injection_g')

        if target is None and injection is None:
            return False, "Must specify either target_co2_ppm or injection_g"

        if target is not None:
            if target < self.min_co2_ppm or target > self.max_co2_ppm:
                return False, f"target_co2_ppm ({target}) outside range [{self.min_co2_ppm}, {self.max_co2_ppm}]"

        if injection is not None:
            if injection < 0 or injection > self.max_injection_rate:
                return False, f"injection_g ({injection}) outside range [0, {self.max_injection_rate}]"

        return True, ""

    def calculate_injection_needed(
        self,
        current_co2_ppm: float,
        target_co2_ppm: float,
        room_volume_m3: float,
        air_temp: float
    ) -> float:
        """
        Calculate CO2 injection needed to reach target level

        Args:
            current_co2_ppm: Current CO2 level
            target_co2_ppm: Target CO2 level
            room_volume_m3: Room volume in cubic meters
            air_temp: Air temperature (°C)

        Returns:
            CO2 to inject in grams
        """
        if target_co2_ppm <= current_co2_ppm:
            return 0.0

        ppm_needed = target_co2_ppm - current_co2_ppm

        # Convert ppm to grams
        # Reverse of co2_grams_to_ppm
        molar_volume = 22.4 * (273.15 + air_temp) / 273.15  # L/mol
        room_volume_L = room_volume_m3 * 1000

        # volume_co2_L = (ppm / 1_000_000) * room_volume_L
        volume_co2_L = (ppm_needed / 1_000_000) * room_volume_L

        # moles = volume / molar_volume
        moles_co2 = volume_co2_L / molar_volume

        # grams = moles * 44 (MW of CO2)
        co2_grams = moles_co2 * 44.0

        return max(0, co2_grams)

    def apply(self, state: Any, action: ToolAction) -> ToolResult:
        """
        Apply CO2 enrichment action

        Update logic:
        - Calculate injection needed (if target specified)
        - Add CO2 to room (converted from g to ppm)
        - Clamp to safe limits
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

        target = action.parameters.get('target_co2_ppm')
        injection_g = action.parameters.get('injection_g')

        # Store before value
        before_CO2 = state.CO2

        # Calculate injection if target specified
        if target is not None and injection_g is None:
            injection_g = self.calculate_injection_needed(
                state.CO2,
                target,
                state.room_volume,
                state.air_temp
            )

        # Limit to max injection rate
        if injection_g is not None:
            injection_g = min(injection_g, self.max_injection_rate)
        else:
            injection_g = 0

        # Convert injection to ppm and add
        if injection_g > 0:
            injection_ppm = co2_grams_to_ppm(injection_g, state.room_volume, state.air_temp)
            state.CO2 += injection_ppm

        # Clamp to safe range
        state.CO2 = max(self.min_co2_ppm, min(self.max_co2_ppm, state.CO2))

        # Check if target was reached
        target_reached = False
        if target is not None:
            target_reached = abs(state.CO2 - target) < 10  # Within 10 ppm

        return ToolResult(
            success=True,
            tool_type=self.tool_type,
            action_id=action.action_id,
            changes={
                'CO2': {'before': before_CO2, 'after': state.CO2},
                'injection_g': injection_g,
                'target_ppm': target,
                'target_reached': target_reached
            },
            message=f"CO2: {before_CO2:.0f} → {state.CO2:.0f} ppm (injected {injection_g:.1f}g)"
        )

    def calculate_optimal_co2(
        self,
        light_PAR: float,
        current_stress: float
    ) -> float:
        """
        Calculate recommended CO2 level based on conditions

        Args:
            light_PAR: Current light level
            current_stress: Current combined stress level

        Returns:
            Recommended CO2 target (ppm)
        """
        # Only enrich CO2 if lights are on and plant is not too stressed
        if light_PAR < 100:
            # Dark period - don't waste CO2
            return AMBIENT_CO2_PPM

        if current_stress > 0.5:
            # High stress - normal CO2 is fine
            return AMBIENT_CO2_PPM

        # Good conditions - enrich CO2 for better growth
        if light_PAR > 400:
            return OPTIMAL_CO2_MAX  # 1200 ppm
        else:
            return OPTIMAL_CO2_MIN  # 800 ppm

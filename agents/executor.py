"""
Executor Agent - Applies tool actions to the simulation environment

Receives the SimulationEngine instance and uses its tools to execute
caring actions. Supports both planned actions and a default caring regime
(HVAC, watering, ventilation, CO2 enrichment) consistent with docs/tools.md.

Tool categories (from docs/tools.md):
  Core Control:        watering, lighting, nutrients
  Environmental:       hvac, humidity, ventilation, co2_control
"""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, TYPE_CHECKING

from tools.base import ToolAction, ToolResult, ToolType

if TYPE_CHECKING:
    from models.engine import SimulationEngine

logger = logging.getLogger(__name__)


class ExecutorAgent:
    """
    Executor agent that applies tool actions through the SimulationEngine.

    The engine is passed at init so the executor can:
      - call engine.apply_tool() to apply ToolActions
      - read engine.state / engine.plant_profile for adaptive decisions
      - access engine.tools for helper calculations (e.g. adaptive watering)
    """

    def __init__(
        self,
        engine: "SimulationEngine",
        regime_config: Optional[Dict[str, Any]] = None,
    ):
        self.engine = engine
        self.execution_log: List[Dict[str, Any]] = []

        # Default caring-regime config (same defaults as engine.set_daily_regime)
        cfg = regime_config or {}
        self.watering_hour: int = cfg.get("watering_hour", 7)
        self.ventilation_hour: int = cfg.get("ventilation_hour", 12)
        self.daily_water_amount: float = cfg.get("daily_water_amount", 0.3)
        self.fan_speed: float = cfg.get("fan_speed", 20.0)
        self.co2_enrichment_enabled: bool = cfg.get("co2_enrichment", True)
        self.co2_target_ppm: float = cfg.get("co2_target_ppm", 1000.0)
        self.co2_enrichment_hours: tuple = cfg.get("co2_enrichment_hours", (6, 20))
        self.temp_tolerance: float = cfg.get("temp_tolerance", 2.0)

    # ------------------------------------------------------------------
    # Low-level: execute a single tool action
    # ------------------------------------------------------------------

    def execute_action(
        self,
        tool_type: ToolType,
        parameters: Dict[str, Any],
        source: str = "agent",
    ) -> ToolResult:
        """
        Build a ToolAction, apply it via the engine, and log the result.

        Args:
            tool_type: one of ToolType enum values
            parameters: tool-specific parameters dict
            source: 'manual' (user-initiated) or 'agent' (automated regime/plan)

        Returns:
            ToolResult from engine.apply_tool()
        """
        action = ToolAction(tool_type=tool_type, parameters=parameters)
        result = self.engine.apply_tool(action)
        self._log(tool_type, parameters, result, source=source)
        return result

    # ------------------------------------------------------------------
    # Mid-level: execute a list of planned actions
    # ------------------------------------------------------------------

    def execute_plan(
        self,
        actions: List[Dict[str, Any]],
        source: str = "agent",
    ) -> List[ToolResult]:
        """
        Execute a list of planned actions.

        Each element should be a dict with:
          - 'tool_type': str or ToolType  (e.g. 'watering' or ToolType.WATERING)
          - 'parameters': dict of tool parameters

        Args:
            source: 'manual' (user-initiated) or 'agent' (automated)

        Returns:
            List of ToolResults
        """
        results: List[ToolResult] = []
        for action_spec in actions:
            tt = action_spec["tool_type"]
            if isinstance(tt, str):
                tt = ToolType(tt)
            result = self.execute_action(tt, action_spec.get("parameters", {}), source=source)
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # Default caring regime (mirrors engine._execute_daily_regime)
    # ------------------------------------------------------------------

    def execute_caring_regime(self) -> None:
        """
        Execute the default automated caring regime for the current hour.

        Covers all tool categories from docs/tools.md:
          1. HVAC temperature control  (every hour)
          2. Multi-time adaptive watering (scheduled + proactive + emergency)
          3. Ventilation                (daily at ventilation_hour)
          4. CO2 enrichment            (during daylight window)
        """
        hour_of_day = self.engine.state.hour % 24

        # ---- 1. HVAC temperature control (every hour) ----
        self._regime_hvac(hour_of_day)

        # ---- 2. Watering (scheduled + proactive + emergency) ----
        self._regime_watering(hour_of_day)

        # ---- 3. Daily ventilation ----
        self._regime_ventilation(hour_of_day)

        # ---- 4. CO2 enrichment during daylight ----
        self._regime_co2(hour_of_day)

    # ------------------------------------------------------------------
    # Regime sub-routines
    # ------------------------------------------------------------------

    def _regime_hvac(self, _hour_of_day: int) -> None:
        """HVAC: maintain optimal temperature (ToolType.HVAC)"""
        target_temp = self.engine.plant_profile.temperature.T_opt

        if abs(self.engine.state.air_temp - target_temp) > self.temp_tolerance:
            result = self.execute_action(
                ToolType.HVAC,
                {"target_temp_C": target_temp, "max_rate_C_per_h": 5.0},
            )
            logger.debug(f"Executor regime - HVAC: {result.message}")

    def _regime_watering(self, hour_of_day: int) -> None:
        """
        Adaptive watering strategy (ToolType.WATERING).

        Three layers:
          a) Scheduled multi-time watering based on plant biomass
          b) Proactive watering when soil drops below threshold
          c) Emergency watering when water stress is rising
        """
        state = self.engine.state
        profile = self.engine.plant_profile
        growth_strategy = profile.growth.growth_strategy.value
        total_biomass = state.biomass
        root_fraction = state.root_biomass / total_biomass if total_biomass > 0 else 0.1
        previous_stress = getattr(self.engine, "_previous_water_stress", 0.0)
        current_stress = state.water_stress

        watering_tool = self.engine.tools[ToolType.WATERING]

        # --- a) Scheduled watering based on plant size ---
        if total_biomass < 5.0:
            watering_hours = [self.watering_hour]
        elif total_biomass < 20.0:
            watering_hours = [self.watering_hour, 18]
        else:
            watering_hours = [self.watering_hour, 12, 18]

        if hour_of_day in watering_hours:
            adaptive_amount = watering_tool.calculate_adaptive_water_amount(
                state=state,
                wilting_point=profile.water.wilting_point,
                optimal_min=profile.water.optimal_range_min,
                field_capacity=profile.water.field_capacity,
                growth_strategy=growth_strategy,
                root_fraction=root_fraction,
                previous_water_stress=previous_stress,
            )
            if adaptive_amount > 0:
                result = self.execute_action(
                    ToolType.WATERING, {"volume_L": adaptive_amount}
                )
                if result.success:
                    self.engine.total_water_supplied_L += adaptive_amount
                    self.engine.water_applications += 1
                logger.info(
                    f"Scheduled watering at hour {hour_of_day}: {result.message} "
                    f"(biomass: {state.biomass:.2f}g, adaptive: {adaptive_amount:.3f}L)"
                )

        # --- b) Proactive watering ---
        soil_water = state.soil_water
        optimal_min = profile.water.optimal_range_min
        proactive_threshold = optimal_min - 3.0

        if soil_water < proactive_threshold and hour_of_day not in watering_hours:
            proactive_amount = watering_tool.calculate_adaptive_water_amount(
                state=state,
                wilting_point=profile.water.wilting_point,
                optimal_min=profile.water.optimal_range_min,
                field_capacity=profile.water.field_capacity,
                growth_strategy=growth_strategy,
                root_fraction=root_fraction,
                previous_water_stress=previous_stress,
            )
            if proactive_amount > 0:
                result = self.execute_action(
                    ToolType.WATERING, {"volume_L": proactive_amount}
                )
                if result.success:
                    self.engine.total_water_supplied_L += proactive_amount
                    self.engine.water_applications += 1
                logger.info(
                    f"Proactive watering: soil {soil_water:.1f}% < threshold "
                    f"{proactive_threshold:.1f}%, applied {proactive_amount:.3f}L"
                )

        # --- c) Emergency stress-responsive watering ---
        stress_increasing = current_stress > previous_stress + 0.02
        stress_moderate = current_stress > 0.1

        if (stress_increasing and stress_moderate) or current_stress > 0.2:
            emergency_amount = watering_tool.calculate_adaptive_water_amount(
                state=state,
                wilting_point=profile.water.wilting_point,
                optimal_min=profile.water.optimal_range_min,
                field_capacity=profile.water.field_capacity,
                growth_strategy=growth_strategy,
                root_fraction=root_fraction,
                previous_water_stress=previous_stress,
            )
            if emergency_amount > 0:
                result = self.execute_action(
                    ToolType.WATERING, {"volume_L": emergency_amount}
                )
                if result.success:
                    self.engine.total_water_supplied_L += emergency_amount
                    self.engine.water_applications += 1
                logger.warning(
                    f"EMERGENCY watering: stress {previous_stress:.2f} -> "
                    f"{current_stress:.2f}, applied {emergency_amount:.3f}L"
                )

    def _regime_ventilation(self, hour_of_day: int) -> None:
        """Daily ventilation at scheduled hour (ToolType.VENTILATION)"""
        if hour_of_day == self.ventilation_hour:
            result = self.execute_action(
                ToolType.VENTILATION,
                {"fan_speed": self.fan_speed, "duration_hours": 1},
            )
            logger.info(f"Executor regime - Ventilation: {result.message}")

    def _regime_co2(self, hour_of_day: int) -> None:
        """CO2 enrichment during daylight hours (ToolType.CO2_CONTROL)"""
        if not self.co2_enrichment_enabled:
            return

        start_hour, end_hour = self.co2_enrichment_hours
        if start_hour <= hour_of_day < end_hour:
            if self.engine.state.CO2 < self.co2_target_ppm:
                result = self.execute_action(
                    ToolType.CO2_CONTROL,
                    {"target_co2_ppm": self.co2_target_ppm},
                )
                if result.success and "co2_injected_g" in result.changes:
                    co2_amount = result.changes["co2_injected_g"]
                    self.engine.total_co2_injected_g += co2_amount
                    self.engine.co2_injections += 1
                logger.debug(f"Executor regime - CO2 enrichment: {result.message}")

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log(
        self,
        tool_type: ToolType,
        parameters: Dict[str, Any],
        result: ToolResult,
        source: str = "agent",
    ) -> None:
        """Append an entry to the execution log."""
        self.execution_log.append(
            {
                "hour": self.engine.state.hour,
                "tool_type": tool_type.value,
                "parameters": parameters,
                "success": result.success,
                "message": result.message,
                "source": source,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def get_log(self) -> List[Dict[str, Any]]:
        """Return the full execution log."""
        return self.execution_log

    def reset(self) -> None:
        """Clear execution log."""
        self.execution_log = []

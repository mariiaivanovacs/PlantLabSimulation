"""
Simulation Engine
Main engine that orchestrates all physics calculations for each timestep
Supports autonomous tools and CO2 dynamics
"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import uuid
import logging

from .state import PlantState, PhenologicalStage
from .plant_profile import PlantProfile

# Import physics modules
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from physics.water_balance import (
    calculate_vpd,
    calculate_et,
    calculate_drainage,
    update_soil_water,
    calculate_water_stress
)
from physics.temperature import (
    calculate_temperature_response,
    calculate_thermal_time,
    calculate_temperature_stress,
    update_soil_temperature
)
from physics.growth import (
    calculate_nutrient_factor,
    calculate_photosynthesis,
    calculate_respiration,
    calculate_growth,
    update_biomass,
    partition_biomass,
    calculate_leaf_area_from_biomass,
    decay_biomass,
    is_daytime,
    get_light_factor,
    calculate_RGR,
    calculate_doubling_time,
    calculate_growth_saturation,
    apply_logistic_growth_factor,
    apply_structure_first_growth_factor,
    calculate_strategy_growth_modifier,
    calculate_root_water_efficiency,
    increase_leaf_area,
)
from physics.damage import (
    calculate_damage_rate,
    apply_damage,
    apply_damage_recovery,
    check_death,
    check_death_comprehensive
)
from physics.nutrients import (
    calculate_nutrient_uptake,
    update_soil_nutrients,
    calculate_nutrient_stress,
    calculate_soil_ec
)
from physics.co2 import (
    update_room_co2,
    calculate_co2_growth_factor,
    calculate_co2_stress,
    AMBIENT_CO2_PPM
)

# Import tools
from tools.base import ToolAction, ToolResult, ToolType
from tools.watering import WateringTool
from tools.lighting import LightingTool
from tools.nutrients import NutrientTool
from tools.hvac import HVACTool
from tools.humidity import HumidityTool
from tools.ventilation import VentilationTool
from tools.co2_control import CO2ControlTool

# Setup logging
logger = logging.getLogger(__name__)


class SimulationEngine:
    """
    Main simulation engine that runs 1-hour timesteps

    Orchestrates all physics calculations, CO2 dynamics, and tool execution.
    """

    def __init__(
        self,
        plant_profile: PlantProfile,
        simulation_id: Optional[str] = None,
        plant_id: Optional[str] = None,
        start_time: Optional[datetime] = None
    ):
        """
        Initialize simulation with a plant profile

        Args:
            plant_profile: PlantProfile defining species characteristics
            simulation_id: Unique simulation identifier (auto-generated if None)
            plant_id: Unique plant identifier (auto-generated if None)
            start_time: Simulation start time (defaults to now)
        """
        self.plant_profile = plant_profile
        self.simulation_id = simulation_id or str(uuid.uuid4())[:8]
        self.plant_id = plant_id or str(uuid.uuid4())[:8]
        self.start_time = start_time or datetime.now()

        # Initialize state from profile
        self.state = self._create_initial_state()

        # History for checkpoints
        self.history: List[Dict[str, Any]] = []

        # Action history
        self.action_history: List[Dict[str, Any]] = []

        # Scheduled actions (for future execution)
        self.scheduled_actions: List[ToolAction] = []

        # Initialize tools
        self._init_tools()

        # CO2 fluxes tracking
        self.co2_fluxes: Dict[str, float] = {}

        # Ventilation state (for CO2 exchange)
        self.ventilation_rate: float = 0.0

        # Daily regime settings
        self.daily_regime_enabled: bool = False
        self.watering_hour: int = 7       # Water at 7:00 AM
        self.ventilation_hour: int = 12   # Ventilate at noon
        self.daily_water_amount: float = 0.3  # Liters per day
        self.daily_ventilation_speed: float = 20.0  # Fan speed 0-100%

        # CO2 enrichment settings
        self.co2_enrichment_enabled: bool = True
        self.co2_target_ppm: float = 1000.0  # Target CO2 level for enrichment
        self.co2_enrichment_hours: tuple = (6, 20)  # Only enrich during daylight

        # Seedling LUE boost (updated hourly in daily regime)
        # Small seedlings have proportionally more photosynthetic area (cotyledons + first leaves)
        # This gives them higher effective LUE, allowing survival at moderate temperatures
        self.seedling_lue_multiplier: float = 1.0  # 1.0 = no boost, >1.0 = boost for seedlings

        # Resource usage tracking (for final summary)
        self.total_water_supplied_L: float = 0.0  # Total water supplied via daily regime (L)
        self.total_co2_injected_g: float = 0.0    # Total CO2 injected via daily regime (g)
        self.water_applications: int = 0          # Number of times water was applied
        self.co2_injections: int = 0              # Number of times CO2 was injected

        # Post-step hooks: callables invoked after each hourly step
        # External code (e.g. AgentOrchestrator) registers hooks here
        self._post_step_hooks: list = []

        logger.info(f"Initialized simulation {self.simulation_id} with plant {self.plant_id}")

    def _init_tools(self) -> None:
        """Initialize all available tools"""
        self.tools = {
            ToolType.WATERING: WateringTool(),
            ToolType.LIGHTING: LightingTool(),
            ToolType.NUTRIENTS: NutrientTool(),
            ToolType.HVAC: HVACTool(),
            ToolType.HUMIDITY: HumidityTool(),
            ToolType.VENTILATION: VentilationTool(),
            ToolType.CO2_CONTROL: CO2ControlTool(),
        }

    def register_post_step_hook(self, hook) -> None:
        """Register a callable to run after each hourly step.

        Hook signature: hook(engine: SimulationEngine) -> None
        """
        self._post_step_hooks.append(hook)

    def _create_initial_state(self) -> PlantState:
        """Create initial plant state from profile"""
        # Start with ambient CO2 (mimicking natural conditions)
        initial_co2 = AMBIENT_CO2_PPM

        # Initialize organ biomasses based on growth strategy
        # Use early-stage fractions to partition initial biomass
        initial_biomass = self.plant_profile.initial_biomass
        leaf_frac = self.plant_profile.growth.leaf_fraction_early
        stem_frac = self.plant_profile.growth.stem_fraction_early
        root_frac = self.plant_profile.growth.root_fraction_early

        # Normalize fractions
        total_frac = leaf_frac + stem_frac + root_frac
        if total_frac > 0:
            leaf_frac /= total_frac
            stem_frac /= total_frac
            root_frac /= total_frac

        initial_leaf_biomass = initial_biomass * leaf_frac
        initial_stem_biomass = initial_biomass * stem_frac
        initial_root_biomass = initial_biomass * root_frac

        return PlantState(
            plant_id=self.plant_id,
            simulation_id=self.simulation_id,
            timestamp=self.start_time,
            hour=0,
            biomass=self.plant_profile.initial_biomass,

            # Initialize organ biomasses
            leaf_biomass=initial_leaf_biomass,
            stem_biomass=initial_stem_biomass,
            root_biomass=initial_root_biomass,

            leaf_area=self.plant_profile.initial_leaf_area,
            phenological_stage=PhenologicalStage.SEEDLING,
            thermal_time=0,
            is_alive=True,
            cumulative_damage=0,
            water_stress=0,
            temp_stress=0,
            nutrient_stress=0,
            soil_water=self.plant_profile.water.optimal_range_min + 5,
            soil_temp=self.plant_profile.temperature.T_opt - 2,
            soil_N=self.plant_profile.nutrients.optimal_N,
            soil_P=self.plant_profile.nutrients.optimal_P,
            soil_K=self.plant_profile.nutrients.optimal_K,
            soil_EC=calculate_soil_ec(
                self.plant_profile.nutrients.optimal_N,
                self.plant_profile.nutrients.optimal_P,
                self.plant_profile.nutrients.optimal_K
            ),
            soil_pH=6.5,
            # air_temp=self.plant_profile.temperature.T_opt,
            air_temp=self.plant_profile.temperature.T_opt,
            # air_temp = 30,

            relative_humidity=(self.plant_profile.optimal_RH_min + self.plant_profile.optimal_RH_max) / 2,
            VPD=1.0,
            light_PAR=self.plant_profile.growth.optimal_PAR,
            # light_PAR=,

            CO2=initial_co2,
            ET=0,
            photosynthesis=0,
            respiration=0,
            growth_rate=0,
            pot_volume=5,
            room_volume=50
        )

    def step(self, hours: int = 1, irrigation: float = 0.0) -> PlantState:
        """
        Advance simulation by specified hours

        Args:
            hours: Number of hourly timesteps to run
            irrigation: Water added this timestep (L) - legacy parameter

        Returns:
            Updated PlantState
        """
        for _ in range(hours):
            self._step_one_hour(irrigation)

        return self.state

    def apply_tool(self, action: ToolAction) -> ToolResult:
        """
        Apply a tool action immediately

        Args:
            action: ToolAction to execute

        Returns:
            ToolResult with outcome
        """
        tool = self.tools.get(action.tool_type)
        if tool is None:
            return ToolResult(
                success=False,
                tool_type=action.tool_type,
                action_id=action.action_id,
                changes={},
                message=f"Unknown tool type: {action.tool_type}"
            )

        # Store saturation for watering tool
        self.state._saturation = self.plant_profile.water.saturation

        result = tool.apply(self.state, action)

        # Track action in history
        self.action_history.append({
            'hour': self.state.hour,
            'action': action.tool_type.value,
            'parameters': action.parameters,
            'result': result.to_dict()
        })

        logger.info(f"Tool {action.tool_type.value}: {result.message}")

        return result

    def schedule_action(self, action: ToolAction, hour: int) -> None:
        """
        Schedule a tool action for future execution

        Args:
            action: ToolAction to schedule
            hour: Hour at which to execute
        """
        action.scheduled_hour = hour
        self.scheduled_actions.append(action)
        logger.info(f"Scheduled {action.tool_type.value} for hour {hour}")

    def _execute_scheduled_actions(self) -> None:
        """Execute any actions scheduled for current hour"""
        current_hour = self.state.hour
        to_execute = [a for a in self.scheduled_actions if a.scheduled_hour == current_hour]

        for action in to_execute:
            self.apply_tool(action)
            self.scheduled_actions.remove(action)

    def _execute_daily_regime(self) -> None:
        """
        Execute daily automated maintenance regime

        Runs once per day at specified hours:
        - Watering at watering_hour (default 7:00 AM)
        - Ventilation at ventilation_hour (default 12:00 noon)
        - CO2 enrichment during daylight hours (maintains target ppm)
        - HVAC temperature control every hour (maintains optimal temperature)

        Note: Seedling LUE boost is updated in _step_one_hour() every hour
        """
        if not self.daily_regime_enabled:
            return

        hour_of_day = self.state.hour % 24

        # HVAC temperature control (every hour to maintain optimal temperature)
        # Target the plant's optimal temperature (T_opt)
        target_temp = self.plant_profile.temperature.T_opt
        temp_tolerance = 2.0  # Only adjust if more than 2°C away from target

        if abs(self.state.air_temp - target_temp) > temp_tolerance:
            action = ToolAction(
                tool_type=ToolType.HVAC,
                parameters={
                    'target_temp_C': target_temp,
                    'max_rate_C_per_h': 5.0  # Max 5°C change per hour
                }
            )
            result = self.apply_tool(action)
            logger.debug(f"Daily regime - HVAC: {result.message}")
        
        # implement smooth temp control towards target temp
        # temp_diff = target_temp - self.state.air_temp
        

        # MULTI-TIME WATERING (morning, midday, evening) based on plant size
        # FIX: Large plants need water multiple times per day to keep up with ET
        growth_strategy = self.plant_profile.growth.growth_strategy.value
        total_biomass = self.state.biomass
        root_fraction = self.state.root_biomass / total_biomass if total_biomass > 0 else 0.1
        previous_stress = getattr(self, '_previous_water_stress', 0.0)
        current_stress = self.state.water_stress

        # Determine watering schedule based on plant size
        # Small plants: once per day (morning)
        # Medium plants: twice per day (morning, evening)
        # Large plants: three times per day (morning, midday, evening)
        if total_biomass < 5.0:
            watering_hours = [self.watering_hour]  # Once per day
        elif total_biomass < 20.0:
            watering_hours = [self.watering_hour, 18]  # Twice per day
        else:
            watering_hours = [self.watering_hour, 12, 18]  # Three times per day

        # Check if it's watering time
        if hour_of_day in watering_hours:
            watering_tool = self.tools[ToolType.WATERING]
            adaptive_amount = watering_tool.calculate_adaptive_water_amount(
                state=self.state,
                wilting_point=self.plant_profile.water.wilting_point,
                optimal_min=self.plant_profile.water.optimal_range_min,
                field_capacity=self.plant_profile.water.field_capacity,
                growth_strategy=growth_strategy,
                root_fraction=root_fraction,
                previous_water_stress=previous_stress
            )

            # Only water if adaptive amount > 0
            if adaptive_amount > 0:
                action = ToolAction(
                    tool_type=ToolType.WATERING,
                    parameters={'volume_L': adaptive_amount}
                )
                result = self.apply_tool(action)

                if result.success:
                    self.total_water_supplied_L += adaptive_amount
                    self.water_applications += 1

                logger.info(f"Scheduled watering at hour {hour_of_day}: {result.message} "
                           f"(biomass: {self.state.biomass:.2f}g, adaptive: {adaptive_amount:.3f}L)")

        # PROACTIVE WATERING: Check soil water level every hour
        # FIX: Don't wait for stress - water proactively when soil drops below threshold
        soil_water = self.state.soil_water
        optimal_min = self.plant_profile.water.optimal_range_min

        # Proactive threshold: water when soil drops 3% below optimal
        # This prevents stress from ever building up
        proactive_threshold = optimal_min - 3.0

        if soil_water < proactive_threshold and hour_of_day not in watering_hours:
            watering_tool = self.tools[ToolType.WATERING]
            proactive_amount = watering_tool.calculate_adaptive_water_amount(
                state=self.state,
                wilting_point=self.plant_profile.water.wilting_point,
                optimal_min=self.plant_profile.water.optimal_range_min,
                field_capacity=self.plant_profile.water.field_capacity,
                growth_strategy=growth_strategy,
                root_fraction=root_fraction,
                previous_water_stress=previous_stress
            )

            if proactive_amount > 0:
                action = ToolAction(
                    tool_type=ToolType.WATERING,
                    parameters={'volume_L': proactive_amount}
                )
                result = self.apply_tool(action)

                if result.success:
                    self.total_water_supplied_L += proactive_amount
                    self.water_applications += 1

                logger.info(f"Proactive watering: soil {soil_water:.1f}% < threshold {proactive_threshold:.1f}%, "
                           f"applied {proactive_amount:.3f}L")

        # STRESS-RESPONSIVE EMERGENCY WATERING (runs every hour)
        # FIX: Lower thresholds - intervene earlier before stress causes damage
        # Stress increasing > 2% OR stress > 10% triggers emergency watering
        stress_increasing = current_stress > previous_stress + 0.02  # 2% increase (was 5%)
        stress_moderate = current_stress > 0.1  # 10% stress (was 30%)

        if (stress_increasing and stress_moderate) or current_stress > 0.2:  # OR high stress
            watering_tool = self.tools[ToolType.WATERING]
            emergency_amount = watering_tool.calculate_adaptive_water_amount(
                state=self.state,
                wilting_point=self.plant_profile.water.wilting_point,
                optimal_min=self.plant_profile.water.optimal_range_min,
                field_capacity=self.plant_profile.water.field_capacity,
                growth_strategy=growth_strategy,
                root_fraction=root_fraction,
                previous_water_stress=previous_stress
            )

            if emergency_amount > 0:
                action = ToolAction(
                    tool_type=ToolType.WATERING,
                    parameters={'volume_L': emergency_amount}
                )
                result = self.apply_tool(action)

                if result.success:
                    self.total_water_supplied_L += emergency_amount
                    self.water_applications += 1

                logger.warning(f"EMERGENCY watering: stress {previous_stress:.2f} → {current_stress:.2f}, "
                              f"applied {emergency_amount:.3f}L")

        # Daily ventilation
        if hour_of_day == self.ventilation_hour:
            action = ToolAction(
                tool_type=ToolType.VENTILATION,
                parameters={
                    'fan_speed': self.daily_ventilation_speed,
                    'duration_hours': 1
                }
            )
            result = self.apply_tool(action)
            logger.info(f"Daily regime - Ventilation: {result.message}")

        # CO2 enrichment during daylight hours
        if self.co2_enrichment_enabled:
            start_hour, end_hour = self.co2_enrichment_hours
            if start_hour <= hour_of_day < end_hour:
                # Inject CO2 if below target level
                if self.state.CO2 < self.co2_target_ppm:
                    # Use target-based injection (tool calculates required amount)
                    action = ToolAction(
                        tool_type=ToolType.CO2_CONTROL,
                        parameters={'target_co2_ppm': self.co2_target_ppm}
                    )
                    result = self.apply_tool(action)

                    # Track CO2 usage for final summary
                    if result.success and 'co2_injected_g' in result.changes:
                        co2_amount = result.changes['co2_injected_g']
                        self.total_co2_injected_g += co2_amount
                        self.co2_injections += 1

                    logger.debug(f"Daily regime - CO2 enrichment: {result.message}")

    def _update_seedling_lue_boost(self) -> None:
        """
        Update seedling LUE boost based on current biomass and GROWTH STRATEGY

        STRATEGY-AWARE LUE BOOST:

        LEAF_FIRST (lettuce):
        - High boost for rapid early canopy development
        - Very small seedlings (< 1g): 3.0x boost
        - Transitions quickly to normal LUE

        STRUCTURE_FIRST (tomato):
        - Lower boost because energy goes to root development
        - Very small seedlings (< 1g): 1.5x boost (max)
        - Slower transition, growth constrained in early weeks
        - This keeps biomass low (~5g by week 2) as roots develop

        Small seedlings have proportionally more photosynthetic area relative to biomass:
        - Cotyledons provide significant photosynthetic capacity
        - First true leaves have high surface area to mass ratio
        """
        biomass = self.state.biomass

        # Get growth strategy from profile
        growth_strategy = self.plant_profile.growth.growth_strategy.value

        if growth_strategy == "leaf_first":
            # LEAF_FIRST: High boost for rapid canopy development
            # FIX: Extended boost to support continued growth beyond 14 days
            # Maintain minimum 1.5x boost throughout vegetative stage
            max_biomass = self.plant_profile.growth.max_biomass  # ~300g for lettuce

            if biomass < 1.0:
                self.seedling_lue_multiplier = 3.0
            elif biomass < 5.0:
                # Linear interpolation from 3.0 to 2.5
                self.seedling_lue_multiplier = 3.0 - (biomass - 1.0) / 4.0 * 0.5
            elif biomass < 20.0:
                # Linear interpolation from 2.5 to 2.0
                self.seedling_lue_multiplier = 2.5 - (biomass - 5.0) / 15.0 * 0.5
            elif biomass < 50.0:
                # Extended vegetative boost: 2.0 to 1.8
                self.seedling_lue_multiplier = 2.0 - (biomass - 20.0) / 30.0 * 0.2
            elif biomass < 100.0:
                # Larger plant: 1.8 to 1.5
                self.seedling_lue_multiplier = 1.8 - (biomass - 50.0) / 50.0 * 0.3
            elif biomass < max_biomass * 0.7:
                # Approaching maturity: maintain 1.5x minimum
                self.seedling_lue_multiplier = 1.5
            else:
                # Near max biomass: gradual decline to 1.0
                remaining_fraction = (max_biomass - biomass) / (max_biomass * 0.3)
                self.seedling_lue_multiplier = 1.0 + 0.5 * max(0, remaining_fraction)

        elif growth_strategy == "structure_first":
            # STRUCTURE_FIRST: Lower boost - energy goes to root development
            # This keeps visible biomass low in first 2 weeks
            if biomass < 1.0:
                # Very small: modest boost (roots developing)
                self.seedling_lue_multiplier = 1.5
            elif biomass < 5.0:
                # Small seedling (week 1-2): minimal boost
                # Linear interpolation from 1.5 to 1.3
                self.seedling_lue_multiplier = 1.5 - (biomass - 1.0) / 4.0 * 0.2
            elif biomass < 15.0:
                # Medium seedling (week 2-3): transitioning
                # Linear interpolation from 1.3 to 1.1
                self.seedling_lue_multiplier = 1.3 - (biomass - 5.0) / 10.0 * 0.2
            elif biomass < 30.0:
                # Larger seedling: approaching normal
                # Linear interpolation from 1.1 to 1.0
                self.seedling_lue_multiplier = 1.1 - (biomass - 15.0) / 15.0 * 0.1
            else:
                # Mature plant: no boost
                self.seedling_lue_multiplier = 1.0
        else:
            # Default: moderate boost
            if biomass < 1.0:
                self.seedling_lue_multiplier = 2.0
            elif biomass < 30.0:
                self.seedling_lue_multiplier = 2.0 - (biomass / 30.0)
            else:
                self.seedling_lue_multiplier = 1.0

    def set_daily_regime(
        self,
        enabled: str = "True",
        watering_hour: int = 7,
        ventilation_hour: int = 12,
        water_amount: float = 0.3,
        fan_speed: float = 20.0,
        co2_enrichment: bool = True,
        co2_target: float = 1000.0
    ) -> None:
        """
        Configure the daily automated regime

        Args:
            enabled: Enable/disable daily regime
            watering_hour: Hour of day to water (0-23)
            ventilation_hour: Hour of day to ventilate (0-23)
            water_amount: Amount of water per day (L)
            fan_speed: Ventilation fan speed (0-100%)
            co2_enrichment: Enable CO2 enrichment during daylight
            co2_target: Target CO2 level in ppm (default 1000)
        """

        if enabled == "False":
            logger.info("Daily regime disabled")
            return

        self.daily_regime_enabled = enabled
        self.watering_hour = watering_hour % 24
        self.ventilation_hour = ventilation_hour % 24
        self.daily_water_amount = water_amount
        self.daily_ventilation_speed = fan_speed
        self.co2_enrichment_enabled = co2_enrichment
        self.co2_target_ppm = co2_target

        logger.info(f"Daily regime {'enabled' if enabled else 'disabled'}: "
                   f"water at {watering_hour}:00 ({water_amount}L), "
                   f"ventilate at {ventilation_hour}:00 ({fan_speed}%), "
                   f"CO2 enrichment {'enabled' if co2_enrichment else 'disabled'} (target: {co2_target}ppm)")


    def _step_one_hour(self, irrigation: float = 0.0) -> None:
        """Run one hourly timestep"""
        # Execute scheduled actions first
        self._execute_scheduled_actions()

        # ALWAYS update seedling LUE boost (every hour, regardless of daily regime)
        # This is critical for seedling survival at moderate temperatures
        self._update_seedling_lue_boost()

        # Pre-physics hooks (executor caring regime runs here via orchestrator)
        for hook in self._post_step_hooks:
            if getattr(hook, '_pre_physics', False):
                hook(self)
            
        # if self.state.hour % 4 == 0:
            
        # # add record to the txt file - data/records/logs.txt
        # with open(file_name, 'a') as f:
        #     # need to record if the engine.state.hour % 24 == 0: -> every 24 hours
        #     # need to record -> biomass, pheno stage, relative humidity, air temperature, CO2
        #     f.write(f"{state.hour / 24},{state.biomass},{state.phenological_stage.value},{state.relative_humidity},{state.air_temp},{state.CO2}, {state.RGR}\n")  
        
            


        if not self.state.is_alive:
            self._handle_dead_plant()
            self._update_co2_dead()
            self._increment_time()
            return

        # 1. Calculate environmental factors
        self._update_vpd()

        # 2. Update soil temperature (lags behind air)
        self._update_soil_temperature()

        # 3. Calculate all stress factors (including CO2 stress)
        self._calculate_stresses()

        # 4. Update water balance
        self._update_water_balance(irrigation)

        # 5. Calculate and apply growth (with CO2 enhancement)
        self._update_growth()

        # 6. Update CO2 (after growth calculates photosynthesis/respiration)
        self._update_co2()

        # 7. Update nutrients
        self._update_nutrients()

        # 8. Calculate and apply damage
        self._update_damage()

        # 9. Check for damage recovery
        self._apply_recovery()

        # 10. Update thermal time
        self._update_thermal_time()

        # 11. Check death condition
        self._check_death()

        # 12. Update phenological stage
        self._update_phenology()

        # 13. Increment time
        self._increment_time()

        # 14. Save checkpoint
        self._save_checkpoint()

        # 15. Run post-step hooks (monitor, reasoning, etc.)
        for hook in self._post_step_hooks:
            if not getattr(hook, '_pre_physics', False):
                hook(self)

    def _update_vpd(self) -> None:
        """Calculate and update VPD"""
        self.state.VPD = calculate_vpd(
            self.state.air_temp,
            self.state.relative_humidity
        )

    def _update_soil_temperature(self) -> None:
        """Update soil temperature (lags behind air)"""
        self.state.soil_temp = update_soil_temperature(
            self.state.soil_temp,
            self.state.air_temp,
            coupling_factor=0.2
        )

    def _calculate_stresses(self) -> None:
        """Calculate all stress factors"""
        # Water stress with TIME-BASED EXPONENTIAL ACCUMULATION
        # Stress accumulates exponentially when water is inadequate
        # Stress recovers gradually when water is supplied
        new_stress, new_hours_without_water = calculate_water_stress(
            soil_water=self.state.soil_water,
            wilting_point=self.plant_profile.water.wilting_point,
            optimal_min=self.plant_profile.water.optimal_range_min,
            optimal_max=self.plant_profile.water.optimal_range_max,
            saturation=self.plant_profile.water.saturation,
            hours_without_water=self.state.hours_without_adequate_water,
            previous_stress=self.state.accumulated_water_stress,
            dt=1.0  # 1 hour timestep
        )

        # Update state with new stress values
        self.state.water_stress = new_stress
        self.state.accumulated_water_stress = new_stress
        self.state.hours_without_adequate_water = new_hours_without_water

        # Temperature stress
        self.state.temp_stress = calculate_temperature_stress(
            self.state.air_temp,
            self.plant_profile.temperature.T_min,
            self.plant_profile.temperature.T_opt,
            self.plant_profile.temperature.T_max
        )

        # Nutrient stress
        self.state.nutrient_stress = calculate_nutrient_stress(
            self.state.soil_N,
            self.state.soil_P,
            self.state.soil_K,
            self.plant_profile.nutrients.optimal_N,
            self.plant_profile.nutrients.optimal_P,
            self.plant_profile.nutrients.optimal_K
        )

    def _update_water_balance(self, irrigation: float = 0.0) -> None:
        """Update soil water content"""
        # Calculate ET
        self.state.ET = calculate_et(
            self.state.leaf_area,
            self.state.light_PAR,
            self.state.soil_water,
            self.state.VPD,
            self.plant_profile.water.wilting_point,
            self.plant_profile.water.field_capacity,
            self.plant_profile.optimal_VPD
        )

        # Calculate drainage
        drainage = calculate_drainage(
            self.state.soil_water,
            self.plant_profile.water.field_capacity
        )

        # Update soil water
        self.state.soil_water, _ = update_soil_water(
            self.state.soil_water,
            self.state.ET,
            drainage,
            irrigation,
            self.state.pot_volume,
            self.plant_profile.water.saturation
        )

    def _update_growth(self) -> None:
        """
        Calculate and apply growth with CO2 enhancement and day/night cycle

        Day/night cycle:
        - Photosynthesis only occurs during daylight (6:00-20:00)
        - Respiration continues 24/7
        - At night: biomass DECREASES (respiration > photosynthesis)
        """
        # Get light factor based on time of day
        light_factor = get_light_factor(self.state.hour)
        is_day = is_daytime(self.state.hour)

        # Temperature response factor
        f_temp = calculate_temperature_response(
            self.state.air_temp,
            self.plant_profile.temperature.T_min,
            self.plant_profile.temperature.T_opt,
            self.plant_profile.temperature.T_max
        )

        # Nutrient factor
        f_nutrient = calculate_nutrient_factor(
            self.state.soil_N,
            self.state.soil_P,
            self.state.soil_K,
            self.plant_profile.nutrients.optimal_N,
            self.plant_profile.nutrients.optimal_P,
            self.plant_profile.nutrients.optimal_K
        )

        # CO2 growth enhancement factor
        f_co2 = calculate_co2_growth_factor(self.state.CO2)

        # Photosynthesis: only during daytime
        # Apply light factor from day/night cycle
        effective_PAR = self.state.light_PAR * light_factor
        print(f"Effective PAR: {effective_PAR}")
        
        # with open('data/records/photosynthesis.txt', 'a') as f:
        #     f.write(f"{effective_PAR}, {self.state.light_PAR}, {light_factor}\n")   

        # Calculate ground area based on plant size (scales with growth)
        # Starts at 0.0025 m² (5x5cm) for seedlings, grows to 0.04 m² (20x20cm) at maturity
        min_ground_area = 0.0025  # 5x5 cm for tiny seedling
        max_ground_area = 0.04   # 20x20 cm for mature plant
        # Ground area scales with biomass^0.5 (area scales with sqrt of mass)
        ground_area_factor = min(1.0, (self.state.biomass / 50.0) ** 0.5)
        ground_area = min_ground_area + (max_ground_area - min_ground_area) * ground_area_factor

        # Calculate heat stress for photosynthesis down-regulation
        heat_stress = self.state.temp_stress

        # Get phenological stage as string (handle both Enum and string)
        pheno_stage = self.state.phenological_stage.value if hasattr(self.state.phenological_stage, 'value') else str(self.state.phenological_stage)

        # NEW: Apply seedling LUE boost for small seedlings
        # Small seedlings have proportionally more photosynthetic area (cotyledons + first leaves)
        # This allows them to survive at moderate temperatures (e.g., 30°C)
        effective_LUE = self.plant_profile.growth.LUE * self.seedling_lue_multiplier

        # NEW: Pass stress parameters and phenological stage for realistic stress response
        base_photosynthesis = calculate_photosynthesis(
            effective_PAR,
            self.state.biomass,
            f_temp,
            f_nutrient,
            water_stress=self.state.water_stress,  # NEW: Down-regulate under water stress
            heat_stress=heat_stress,  # NEW: Down-regulate under heat stress
            phenological_stage=pheno_stage,  # NEW: Reduced efficiency during germination
            LUE=effective_LUE,  # NEW: Use boosted LUE for seedlings
            leaf_area_ratio=self.plant_profile.growth.leaf_area_ratio,
            ground_area=ground_area
        )

        # Apply CO2 enhancement (only matters during day)
        self.state.photosynthesis = base_photosynthesis * f_co2

        # NEW: Temperature-dependent respiration with Q10 effect
        # Respiration increases exponentially with temperature
        # This makes heat stress more damaging (plants burn through reserves faster)
        self.state.respiration = calculate_respiration(
            biomass=self.state.biomass,
            air_temp=self.state.air_temp,  # NEW: Q10 temperature dependence
            r_base=self.plant_profile.growth.r_base,
            T_ref=20.0,  # Reference temperature (°C)
            Q10=2.0  # Respiration doubles every 10°C
        )

        # NEW: Net growth with reserve depletion mechanism
        # Reserves buffer against biomass loss when photosynthesis < respiration
        delta_biomass, reserve_depletion = calculate_growth(
            self.state.photosynthesis,
            self.state.respiration,
            self.state.water_stress,
            self.state.cumulative_damage,
            biomass=self.state.biomass,
            seed_reserves=self.state.seed_reserves,  # NEW: Use reserves before losing biomass
            hour=self.state.hour
        )

        # Update seed reserves
        self.state.seed_reserves = max(0, self.state.seed_reserves - reserve_depletion)

        # Get growth strategy for strategy-aware growth constraint
        growth_strategy = self.plant_profile.growth.growth_strategy.value

        # Apply STRATEGY-AWARE growth constraint
        # LEAF_FIRST: Standard logistic growth (fast early growth)
        # STRUCTURE_FIRST: Delayed sigmoid growth (slow early, rapid weeks 3-5)
        delta_biomass_constrained = calculate_strategy_growth_modifier(
            growth_strategy=growth_strategy,
            delta_biomass=delta_biomass,
            biomass=self.state.biomass,
            max_biomass=self.plant_profile.growth.max_biomass,
            hour=self.state.hour
        )

        # NEW: Partition biomass growth into organs (leaf, stem, root)
        # This implements growth strategy (leaf-first vs structure-first)
        if delta_biomass_constrained > 0:
            # Growing: partition new biomass
            leaf_delta, stem_delta, root_delta = partition_biomass(
                delta_biomass=delta_biomass_constrained,
                biomass=self.state.biomass,
                max_biomass=self.plant_profile.growth.max_biomass,
                leaf_fraction_early=self.plant_profile.growth.leaf_fraction_early,
                stem_fraction_early=self.plant_profile.growth.stem_fraction_early,
                root_fraction_early=self.plant_profile.growth.root_fraction_early,
                leaf_fraction_late=self.plant_profile.growth.leaf_fraction_late,
                stem_fraction_late=self.plant_profile.growth.stem_fraction_late,
                root_fraction_late=self.plant_profile.growth.root_fraction_late
            )

            # Update organ biomasses
            self.state.leaf_biomass += leaf_delta
            self.state.stem_biomass += stem_delta
            self.state.root_biomass += root_delta
        elif delta_biomass_constrained < 0:
            # Losing biomass: proportionally reduce all organs
            loss_fraction = abs(delta_biomass_constrained) / max(self.state.biomass, 0.001)
            loss_fraction = min(loss_fraction, 1.0)  # Cap at 100%

            self.state.leaf_biomass *= (1 - loss_fraction)
            self.state.stem_biomass *= (1 - loss_fraction)
            self.state.root_biomass *= (1 - loss_fraction)

        # Update total biomass (handles both growth and loss)
        self.state.biomass, actual_change = update_biomass(
            self.state.biomass,
            delta_biomass_constrained,  # Use constrained value
            self.plant_profile.growth.max_biomass,
            self.state.cumulative_damage
        )

        # Store growth rate (can be negative at night)
        self.state.growth_rate = actual_change

        # Track CO2 uptake (net CO2 consumption = photosynthesis - respiration)
        # Positive = net CO2 consumption (healthy photosynthesis)
        # Negative = net CO2 production (no photosynthesis, only respiration)
        self.state.co2_uptake = self.state.photosynthesis - self.state.respiration

        # Calculate growth metrics (RGR, doubling time, saturation)
        # IMPROVED: Pass soil water parameters for water stress scaling
        self.state.RGR = calculate_RGR(
            self.state.biomass,
            actual_change,
            hour=self.state.hour,
            water_stress=self.state.water_stress,  # FIXED: Pass water stress to make boost water-dependent
            soil_water=self.state.soil_water,  # IMPROVED: For water stress scaling
            wilting_point=self.plant_profile.water.wilting_point,  # IMPROVED
            optimal_min=self.plant_profile.water.optimal_range_min,  # IMPROVED
            dt=1.0, # 1 hour timestep
            seedling_boost=0.002,  # g/h, adjustable
            boost_hours=168,  # FIXED: Extended to 168 hours (7 days) for full seedling stage
            boost_biomass_threshold=self.plant_profile.phenology.seed_to_seedling_biomass , # apply boost if biomass below this
            plant_boost= self.plant_profile.boost_hours
        )

        self.state.doubling_time = calculate_doubling_time(self.state.RGR)

        self.state.growth_saturation = calculate_growth_saturation(
            self.state.biomass,
            self.plant_profile.growth.max_biomass
        )

        # NEW: Calculate leaf area from leaf biomass using SLA (Specific Leaf Area)
        # This replaces the old LAR-based approach
        # Different strategies have different SLA values (lettuce: high, tomato: low)
        previous_leaf_area = self.state.leaf_area
        self.state.leaf_area = calculate_leaf_area_from_biomass(
            leaf_biomass=self.state.leaf_biomass,
            SLA=self.plant_profile.growth.SLA,
            water_stress=self.state.water_stress,  # Cap expansion under water stress
            heat_stress=heat_stress,  # Cap expansion under heat stress
            previous_leaf_area=previous_leaf_area  # Track previous area
        )
        
        if self.state.biomass > 3 and self.state.hour > 200: 
            # call increase_leaf_area function to log data
            self.state.leaf_area = increase_leaf_area(
                previous_leaf_area=self.state.leaf_area,
                leaf_biomass=self.state.leaf_biomass,
                SLA=self.plant_profile.growth.SLA,
                water_stress=self.state.water_stress,
                heat_stress=heat_stress,
                hours_since_emergence=self.state.hour,
                biomass=self.state.biomass
            )
        # with open('data/records/leaf.txt', 'a') as f:
        #     f.write(f"{self.state.hour},{self.state.leaf_area}\n")
        

    def _update_co2(self) -> None:
        """Update room CO2 level based on plant activity"""
        self.state.CO2, self.co2_fluxes = update_room_co2(
            current_co2_ppm=self.state.CO2,
            photosynthesis_rate=self.state.photosynthesis,
            respiration_rate=self.state.respiration,
            room_volume_m3=self.state.room_volume,
            air_temp=self.state.air_temp,
            ventilation_rate=self.ventilation_rate,
            co2_injection_g=0.0,  # Handled by CO2 tool
            ambient_co2_ppm=AMBIENT_CO2_PPM
        )

    def _update_co2_dead(self) -> None:
        """Update CO2 for dead plant (only respiration from decomposition)"""
        # Small CO2 release from decomposition
        decomp_respiration = self.state.biomass * 0.001  # Very slow decomposition
        self.state.CO2, self.co2_fluxes = update_room_co2(
            current_co2_ppm=self.state.CO2,
            photosynthesis_rate=0,
            respiration_rate=decomp_respiration,
            room_volume_m3=self.state.room_volume,
            air_temp=self.state.air_temp,
            ventilation_rate=self.ventilation_rate,
            co2_injection_g=0.0,
            ambient_co2_ppm=AMBIENT_CO2_PPM
        )

    def _update_nutrients(self) -> None:
        """Update nutrient uptake and soil depletion"""
        # Calculate uptake based on growth
        uptake_N, uptake_P, uptake_K = calculate_nutrient_uptake(
            self.state.growth_rate,
            self.plant_profile.nutrients.N_ratio,
            self.plant_profile.nutrients.P_ratio,
            self.plant_profile.nutrients.K_ratio
        )

        # Update soil nutrients
        self.state.soil_N, self.state.soil_P, self.state.soil_K = update_soil_nutrients(
            self.state.soil_N,
            self.state.soil_P,
            self.state.soil_K,
            uptake_N,
            uptake_P,
            uptake_K
        )

        # Update EC
        self.state.soil_EC = calculate_soil_ec(
            self.state.soil_N,
            self.state.soil_P,
            self.state.soil_K
        )

    def _update_damage(self) -> None:
        """Calculate and apply damage"""
        damage_rate, _ = calculate_damage_rate(
            self.state.soil_water,
            self.state.air_temp,
            self.state.soil_EC,
            self.plant_profile.water.wilting_point,
            self.plant_profile.water.saturation,
            self.plant_profile.temperature.T_min,
            self.plant_profile.temperature.T_max,
            self.plant_profile.EC_toxicity_threshold
        )

        # Add CO2 stress damage (minor)
        co2_stress = calculate_co2_stress(self.state.CO2)
        if co2_stress > 0.5:
            damage_rate += co2_stress * 0.5  # Max 0.5% per hour from CO2

        self.state.cumulative_damage = apply_damage(
            self.state.cumulative_damage,
            damage_rate
        )

    def _apply_recovery(self) -> None:
        """Apply damage recovery if conditions are favorable"""
        self.state.cumulative_damage = apply_damage_recovery(
            self.state.cumulative_damage,
            self.state.water_stress,
            self.state.temp_stress,
            self.state.nutrient_stress
        )

    def _update_thermal_time(self) -> None:
        """Accumulate thermal time for phenology"""
        self.state.thermal_time = calculate_thermal_time(
            self.state.air_temp,
            self.state.soil_temp,
            self.state.thermal_time,
            self.plant_profile.temperature.T_base,
            self.plant_profile.temperature.T_opt,
            self.plant_profile.temperature.air_weight,
            self.plant_profile.temperature.soil_weight
        )

    def _check_death(self) -> None:
        """
        Comprehensive death check with multiple conditions

        Plant is dead if ANY of these conditions are met:
        1. Cumulative damage >= 95%
        2. Biomass <= 0.01 g (essentially nothing left)
        3. Net RGR <= 0 for > 48 hours consecutively
        4. CO2 uptake <= 0 for > 24 hours consecutively
        """
        is_dead, death_reason = check_death_comprehensive(
            cumulative_damage=self.state.cumulative_damage,
            biomass=self.state.biomass,
            history=self.history,
            current_hour=self.state.hour,
            damage_threshold=95.0,
            min_biomass=0.01,
            negative_rgr_hours=48,
            zero_co2_uptake_hours=48,
            state=self.state
        )

        if is_dead:
            self.state.is_alive = False
            self.state.phenological_stage = PhenologicalStage.DEAD
            self.state.death_reason = death_reason
            logger.warning(f"Plant {self.plant_id} died at hour {self.state.hour}: {death_reason}")

    # def _update_phenology(self) -> None:
    #     """Update phenological stage based on thermal time"""
    #     if not self.state.is_alive:
    #         return

    #     p = self.plant_profile.phenology
    #     tt = self.state.thermal_time
    #     b = self.state.biomass

    #     current = self.state.phenological_stage

    #     if current == PhenologicalStage.SEED:
    #         if tt >= p.seed_to_seedling_GDD and b >= p.seed_to_seedling_biomass:
    #             self.state.phenological_stage = PhenologicalStage.SEEDLING

    #     elif current == PhenologicalStage.SEEDLING:
    #         if tt >= p.seedling_to_vegetative_GDD:
    #             self.state.phenological_stage = PhenologicalStage.VEGETATIVE

    #     elif current == PhenologicalStage.VEGETATIVE:
    #         if tt >= p.vegetative_to_flowering_GDD:
    #             self.state.phenological_stage = PhenologicalStage.FLOWERING

    #     elif current == PhenologicalStage.FLOWERING:
    #         if tt >= p.flowering_to_fruiting_GDD:
    #             self.state.phenological_stage = PhenologicalStage.FRUITING

    #     elif current == PhenologicalStage.FRUITING:
    #         if tt >= p.fruiting_to_mature_GDD:
    #             self.state.phenological_stage = PhenologicalStage.MATURE



    def _update_phenology(self) -> None:
        """Update phenological stage based on thermal time and optional biomass check"""
        if not self.state.is_alive:
            return

        p = self.plant_profile.phenology
        tt = self.state.thermal_time
        b = self.state.biomass

        changed = True
        while changed:  # Allow multiple stage jumps if thresholds are exceeded
            changed = False
            current = self.state.phenological_stage

            if current == PhenologicalStage.SEED:
                if tt >= p.seed_to_seedling_GDD and b >= p.seed_to_seedling_biomass:
                    self.state.phenological_stage = PhenologicalStage.SEEDLING
                    changed = True
                    
            elif current == PhenologicalStage.SEEDLING:
                if tt >= p.seedling_to_vegetative_GDD and b >= p.seedling_to_vegetative_biomass:
                    self.state.phenological_stage = PhenologicalStage.VEGETATIVE
                    changed = True

            elif current == PhenologicalStage.VEGETATIVE:
                if tt >= p.vegetative_to_flowering_GDD and b >= p.vegetative_to_flowering_biomass:
                    self.state.phenological_stage = PhenologicalStage.FLOWERING
                    changed = True

            elif current == PhenologicalStage.FLOWERING:
                if tt >= p.flowering_to_fruiting_GDD and b >= p.flowering_to_fruiting_biomass:
                    self.state.phenological_stage = PhenologicalStage.FRUITING
                    changed = True

            elif current == PhenologicalStage.FRUITING:
                if tt >= p.fruiting_to_mature_GDD and b >= p.fruiting_to_mature_biomass:
                    self.state.phenological_stage = PhenologicalStage.MATURE
                    changed = True


            # elif current == PhenologicalStage.SEEDLING:
            #     if tt >= p.seedling_to_vegetative_GDD:  # optional: add biomass check
            #         self.state.phenological_stage = PhenologicalStage.VEGETATIVE
            #         changed = True

            # elif current == PhenologicalStage.VEGETATIVE:
            #     if tt >= p.vegetative_to_flowering_GDD:
            #         self.state.phenological_stage = PhenologicalStage.FLOWERING
            #         changed = True

            # elif current == PhenologicalStage.FLOWERING:
            #     if tt >= p.flowering_to_fruiting_GDD:
            #         self.state.phenological_stage = PhenologicalStage.FRUITING
            #         changed = True

            # elif current == PhenologicalStage.FRUITING:
            #     if tt >= p.fruiting_to_mature_GDD:
            #         self.state.phenological_stage = PhenologicalStage.MATURE
            #         changed = True

            # Optionally log stage changes
            if changed:
                print(f"[Phenology] Hour: {self.state.hour}, Stage changed: {current} -> {self.state.phenological_stage}")


    def _handle_dead_plant(self) -> None:
        """Handle dead plant - apply decay"""
        self.state.biomass = decay_biomass(self.state.biomass)

        # Decay organ biomasses proportionally
        decay_factor = self.state.biomass / max(self.state.leaf_biomass + self.state.stem_biomass + self.state.root_biomass, 0.001)
        self.state.leaf_biomass *= decay_factor
        self.state.stem_biomass *= decay_factor
        self.state.root_biomass *= decay_factor

        # Update leaf area using SLA-based calculation
        previous_leaf_area = self.state.leaf_area
        self.state.leaf_area = calculate_leaf_area_from_biomass(
            leaf_biomass=self.state.leaf_biomass,
            SLA=self.plant_profile.growth.SLA,
            water_stress=1.0,  # Dead plant has max stress
            heat_stress=0.0,
            previous_leaf_area=previous_leaf_area
        )

        self.state.growth_rate = 0
        self.state.photosynthesis = 0
        self.state.respiration = 0
        self.state.ET = 0
        self.state.seed_reserves = 0  # No reserves left

    def _increment_time(self) -> None:
        """Increment hour counter and timestamp"""
        self.state.hour += 1
        self.state.timestamp = self.start_time + timedelta(hours=self.state.hour)

    def _save_checkpoint(self) -> None:
        """Save current state to history"""
        checkpoint = self.state.to_dict()
        checkpoint['co2_fluxes'] = self.co2_fluxes.copy()
        self.history.append(checkpoint)

    def get_state(self) -> PlantState:
        """Get current plant state"""
        return self.state

    def get_history(self) -> List[Dict[str, Any]]:
        """Get all historical checkpoints"""
        return self.history

    def get_action_history(self) -> List[Dict[str, Any]]:
        """Get history of all tool actions"""
        return self.action_history

    def get_state_at_hour(self, hour: int) -> Optional[Dict[str, Any]]:
        """Get state at specific hour from history"""
        if 0 <= hour < len(self.history):
            return self.history[hour]
        return None

    def reset(self) -> None:
        """Reset simulation to initial state"""
        self.state = self._create_initial_state()
        self.history = []
        self.action_history = []
        self.scheduled_actions = []
        self.co2_fluxes = {}
        self.ventilation_rate = 0.0

        # Hooks are preserved — orchestrator handles its own reset

    def get_summary(self) -> Dict[str, Any]:
        """Get simulation summary"""
        return {
            'simulation_id': self.simulation_id,
            'plant_id': self.plant_id,
            'profile': self.plant_profile.profile_id,
            'hours_elapsed': self.state.hour,
            'is_alive': self.state.is_alive,
            'biomass': self.state.biomass,
            'CO2': self.state.CO2,
            'cumulative_damage': self.state.cumulative_damage,
            'phenological_stage': self.state.phenological_stage.value,
            'checkpoints_saved': len(self.history),
            'actions_applied': len(self.action_history)
        }

    def get_available_tools(self) -> List[str]:
        """Get list of available tool types"""
        return [t.value for t in self.tools.keys()]

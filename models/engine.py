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
    update_leaf_area,
    decay_biomass,
    is_daytime,
    get_light_factor,
    calculate_RGR,
    calculate_doubling_time,
    calculate_growth_saturation,
    apply_logistic_growth_factor
)
from physics.damage import (
    calculate_damage_rate,
    apply_damage,
    apply_damage_recovery,
    check_death
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
        self.daily_regime_enabled: bool = True
        self.watering_hour: int = 7       # Water at 7:00 AM
        self.ventilation_hour: int = 12   # Ventilate at noon
        self.daily_water_amount: float = 0.3  # Liters per day
        self.daily_ventilation_speed: float = 20.0  # Fan speed 0-100%

        # CO2 enrichment settings
        self.co2_enrichment_enabled: bool = True
        self.co2_target_ppm: float = 1000.0  # Target CO2 level for enrichment
        self.co2_enrichment_hours: tuple = (6, 20)  # Only enrich during daylight

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

    def _create_initial_state(self) -> PlantState:
        """Create initial plant state from profile"""
        # Start with ambient CO2 (mimicking natural conditions)
        initial_co2 = AMBIENT_CO2_PPM

        return PlantState(
            plant_id=self.plant_id,
            simulation_id=self.simulation_id,
            timestamp=self.start_time,
            hour=0,
            biomass=self.plant_profile.initial_biomass,
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
            air_temp=self.plant_profile.temperature.T_opt,
            relative_humidity=(self.plant_profile.optimal_RH_min + self.plant_profile.optimal_RH_max) / 2,
            VPD=1.0,
            light_PAR=self.plant_profile.growth.optimal_PAR,
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
        """
        if not self.daily_regime_enabled:
            return

        hour_of_day = self.state.hour % 24

        # Daily watering
        if hour_of_day == self.watering_hour:
            action = ToolAction(
                tool_type=ToolType.WATERING,
                parameters={'volume_L': self.daily_water_amount}
            )
            result = self.apply_tool(action)
            logger.info(f"Daily regime - Watering: {result.message}")

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
                    logger.debug(f"Daily regime - CO2 enrichment: {result.message}")

    def set_daily_regime(
        self,
        enabled: bool = True,
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

        if not enabled:
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

        # Execute daily automated regime (watering, ventilation)
        # self._execute_daily_regime()

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
        # Water stress
        self.state.water_stress = calculate_water_stress(
            self.state.soil_water,
            self.plant_profile.water.wilting_point,
            self.plant_profile.water.optimal_range_min,
            self.plant_profile.water.optimal_range_max,
            self.plant_profile.water.saturation
        )

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
        
        with open('data/records/photosynthesis.txt', 'a') as f:
            f.write(f"{effective_PAR}, {self.state.light_PAR}, {light_factor}\n")   

        # Calculate ground area based on plant size (scales with growth)
        # Starts at 0.0025 m² (5x5cm) for seedlings, grows to 0.04 m² (20x20cm) at maturity
        min_ground_area = 0.0025  # 5x5 cm for tiny seedling
        max_ground_area = 0.04   # 20x20 cm for mature plant
        # Ground area scales with biomass^0.5 (area scales with sqrt of mass)
        ground_area_factor = min(1.0, (self.state.biomass / 50.0) ** 0.5)
        ground_area = min_ground_area + (max_ground_area - min_ground_area) * ground_area_factor

        # FIX: Pass biomass as 2nd parameter and ground_area for proper LAI calculation
        base_photosynthesis = calculate_photosynthesis(
            effective_PAR,
            self.state.biomass,
            f_temp,
            f_nutrient,
            self.plant_profile.growth.LUE,
            self.plant_profile.growth.leaf_area_ratio,
            ground_area
        )

        # Apply CO2 enhancement (only matters during day)
        self.state.photosynthesis = base_photosynthesis * f_co2

        # Respiration: continues 24/7 (slightly reduced at night due to lower temp)
        night_respiration_factor = 0.7 if not is_day else 1.0
        self.state.respiration = calculate_respiration(
            self.state.biomass,
            self.plant_profile.growth.r_base
        ) * night_respiration_factor

        # Net growth (can be NEGATIVE at night!)
        delta_biomass = calculate_growth(
            self.state.photosynthesis,
            self.state.respiration,
            self.state.water_stress,
            self.state.cumulative_damage,
            hour=self.state.hour
        )

        # Apply logistic growth constraint
        # This prevents unrealistic exponential growth as plant approaches max size
        # Early growth (B << K): minimal constraint, ~exponential
        # Near max (B → K): strong constraint, growth slows to zero
        delta_biomass_constrained = apply_logistic_growth_factor(
            delta_biomass,
            self.state.biomass,
            self.plant_profile.growth.max_biomass
        )

        # Update biomass (handles both growth and loss)
        self.state.biomass, actual_change = update_biomass(
            self.state.biomass,
            delta_biomass_constrained,  # Use constrained value
            self.plant_profile.growth.max_biomass,
            self.state.cumulative_damage
        )

        # Store growth rate (can be negative at night)
        self.state.growth_rate = actual_change

        # Calculate growth metrics (RGR, doubling time, saturation)
        self.state.RGR = calculate_RGR(
            self.state.biomass,
            actual_change,
            hour=self.state.hour,
            dt=1.0, # 1 hour timestep
            # CURRENTLY HARDCODED _ WILL HAVE TO CHANGE
            seedling_boost=0.002,  # g/h, adjustable
            boost_hours=24,          # apply boost for first 24 hours
            boost_biomass_threshold=self.plant_profile.phenology.seed_to_seedling_biomass  # apply boost if biomass below this
        )

        self.state.doubling_time = calculate_doubling_time(self.state.RGR)

        self.state.growth_saturation = calculate_growth_saturation(
            self.state.biomass,
            self.plant_profile.growth.max_biomass
        )

        # Update leaf area based on current biomass
        self.state.leaf_area = update_leaf_area(
            self.state.biomass,
            self.plant_profile.growth.leaf_area_ratio
        )

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
        """Check if plant has died"""
        if check_death(self.state.cumulative_damage):
            self.state.is_alive = False
            self.state.phenological_stage = PhenologicalStage.DEAD
            logger.warning(f"Plant {self.plant_id} died at hour {self.state.hour}")

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
        self.state.leaf_area = update_leaf_area(
            self.state.biomass,
            self.plant_profile.growth.leaf_area_ratio
        )
        self.state.growth_rate = 0
        self.state.photosynthesis = 0
        self.state.respiration = 0
        self.state.ET = 0

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

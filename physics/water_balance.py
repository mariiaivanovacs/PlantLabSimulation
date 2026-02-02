"""
Water Balance Physics
Handles evapotranspiration, drainage, and soil moisture dynamics

Equations from plant_simulator_focused_implementation.pdf Section 4.1
"""
import math
from typing import Tuple


def calculate_vpd(air_temp: float, relative_humidity: float) -> float:
    """
    Calculate Vapor Pressure Deficit (VPD)

    VPD affects transpiration rate - higher VPD = more water loss

    Args:
        air_temp: Air temperature in Celsius
        relative_humidity: Relative humidity (0-100%)

    Returns:
        VPD in kPa
    """
    # Saturation Vapor Pressure (Tetens formula)
    SVP = 0.6108 * math.exp(17.27 * air_temp / (air_temp + 237.3))
    # Vapor Pressure Deficit
    VPD = SVP * (1 - relative_humidity / 100)
    return max(0, VPD)


# def calculate_et(
#     leaf_area: float,
#     light_PAR: float,
#     soil_water: float,
#     VPD: float,
#     wilting_point: float,
#     field_capacity: float,
#     optimal_VPD: float = 1.2
# ) -> float:
#     """
#     Calculate Evapotranspiration (ET) rate

#     ET represents water loss through plant transpiration + soil evaporation.
#     Includes baseline soil evaporation that occurs even when plant cannot transpire.

#     Args:
#         leaf_area: Plant leaf area in m^2
#         light_PAR: Photosynthetically Active Radiation in umol/m^2/s
#         soil_water: Current soil water content (%)
#         VPD: Vapor Pressure Deficit in kPa
#         wilting_point: Soil water at wilting point (%)
#         field_capacity: Soil water at field capacity (%)
#         optimal_VPD: Optimal VPD for transpiration (default 1.2 kPa)

#     Returns:
#         ET rate in L/hour
#     """
#     # Base ET rate: 0.3 L/h per m^2 of leaf area index
#     # FIXED: Increased from 0.02 to 0.3 for realistic transpiration rates
#     # Typical plant transpiration: 2-5 mm/day per m² → ~0.3 L/h/m² with light enhancement
#     ET_BASE = 0.3  # L/h/m^2 LAI

#     # Baseline soil evaporation (always occurs, even when plant can't transpire)
#     # This represents direct soil surface evaporation
#     # FIXED: Increased from 0.002 to 0.01 for realistic soil evaporation
#     # Adds ~0.24 L/day baseline evaporation, ensuring small seedlings experience drought stress
#     SOIL_EVAP_BASE = 0.01  # L/h baseline

#     # Potential ET increases with light (stomata open more under light)
#     ET_pot = ET_BASE * leaf_area * (1 + 0.001 * light_PAR)

#     # Water availability factor (0-1)
#     # Plant can only transpire if soil has available water
#     if field_capacity <= wilting_point:
#         f_water = 0.0
#     else:
#         f_water = max(0, min(1, (soil_water - wilting_point) / (field_capacity - wilting_point)))

#     # VPD factor: higher VPD drives more transpiration
#     # f_VPD ranges from 0.5 (low VPD) to 1.0 (optimal/high VPD)
#     f_VPD = 0.5 + 0.5 * min(1, VPD / optimal_VPD)

#     # Plant transpiration (depends on water availability)
#     ET_plant = ET_pot * f_water * f_VPD

#     # Soil evaporation (always occurs if soil has water, scaled by soil moisture)
#     # Even dry soil loses some water to evaporation
#     soil_evap_factor = min(1, soil_water / 50)  # Scales from 0-50% soil water
#     ET_soil = SOIL_EVAP_BASE * soil_evap_factor * (0.5 + 0.5 * VPD)

#     # Total ET
#     ET = ET_plant + ET_soil

#     return max(0, ET)

import math
from typing import Tuple, Union

def calculate_et(
    leaf_area: float,
    light_PAR: float,
    soil_water: float,
    VPD: float,
    wilting_point: float,
    field_capacity: float,
    optimal_VPD: float = 1.2,
    *,
    ET_BASE: float = 0.12,        # L / h / m^2  (realistic lettuce baseline)
    SOIL_EVAP_BASE: float = 0.004,# L / h baseline soil evaporation
    seedling_leaf_area_cap: float = 0.02,  # m^2; typical leaf area where seedling transitions to normal ET
    min_f_VPD: float = 0.2,       # minimum fraction for VPD effect (at humid conditions)
    light_sensitivity: float = 0.0004, # how much PAR multiplies ET_pot
    debug: bool = False
) -> Union[float, Tuple[float, float, float]]:
    """
    Calculate Evapotranspiration (ET) rate for a potted plant (L/hour).

    Improvements vs previous version:
      - ET_BASE scaled to realistic lettuce numbers (L/h/m^2)
      - Light multiplier reduced so PAR doesn't overly amplify ET
      - Seedling cap prevents tiny plants from having mature-plant ET
      - VPD factor can go very low (humid) but not zero
      - Soil evaporation reduced to a small baseline more appropriate for indoor pots
      - Optionally returns (ET_total, ET_plant, ET_soil) when debug=True

    Args:
        leaf_area: leaf area (m^2)
        light_PAR: PAR (umol/m^2/s)
        soil_water: current soil water as percent (0-100)
        VPD: vapor pressure deficit (kPa)
        wilting_point: soil WP as percent (0-100)
        field_capacity: soil FC as percent (0-100)
        optimal_VPD: VPD (kPa) considered "optimal" for stomatal opening
        ET_BASE: base transpiration rate per m^2 (L/h/m^2)
        SOIL_EVAP_BASE: baseline soil evaporation (L/h)
        seedling_leaf_area_cap: leaf area below which seedling ET is scaled down
        min_f_VPD: minimum VPD multiplier (0-1)
        light_sensitivity: multiplier for PAR effect on ET_pot
        debug: if True, return tuple (ET_total, ET_plant, ET_soil)

    Returns:
        ET (L/hour) or (ET, ET_plant, ET_soil) when debug=True
    """

    # --- Safety / units checks ---
    leaf_area = max(0.0, float(leaf_area))
    light_PAR = max(0.0, float(light_PAR))
    soil_water = max(0.0, float(soil_water))
    VPD = max(0.0, float(VPD))
    wilting_point = float(wilting_point)
    field_capacity = float(field_capacity)

    # --- potential/transpiration baseline (depends on leaf area & light) ---
    # Light increases stomatal opening, but we use a modest multiplier so PAR doesn't dominate.
    ET_pot = ET_BASE * leaf_area * (1.0 + light_sensitivity * light_PAR)

    # --- water availability factor (0..1) ---
    if field_capacity <= wilting_point:
        f_water = 0.0
    else:
        f_water = (soil_water - wilting_point) / (field_capacity - wilting_point)
        f_water = max(0.0, min(1.0, f_water))

    # --- VPD factor: scales with VPD but bounded ---
    if optimal_VPD <= 0:
        f_VPD = 1.0
    else:
        f_VPD = VPD / optimal_VPD
        # clamp and give a nonzero lower bound so night/humid conditions reduce ET strongly
        f_VPD = max(min_f_VPD, min(1.0, f_VPD))

    # --- seedling/size limit: small plants cannot transpire like big ones ---
    # avoids tiny seedlings producing large ET just because leaf_area is nonzero
    if seedling_leaf_area_cap > 0:
        size_factor = min(1.0, leaf_area / seedling_leaf_area_cap)
    else:
        size_factor = 1.0

    # Plant transpiration (L/h)
    ET_plant = ET_pot * f_water * f_VPD * size_factor

    # --- soil evaporation (L/h) ---
    # scales with soil moisture as percent (0..100). If soil is almost dry, evaporation is small.
    soil_evap_factor = min(1.0, soil_water / 50.0)  # 50% soil water => full soil evaporation
    # scale soil evap by VPD effect but less sensitive than plant transpiration
    ET_soil = SOIL_EVAP_BASE * soil_evap_factor * (0.3 + 0.7 * f_VPD)

    # --- total ET ---
    ET_total = ET_plant + ET_soil

    # ensure non-negative
    ET_total = max(0.0, ET_total)
    ET_plant = max(0.0, ET_plant)
    ET_soil = max(0.0, ET_soil)

    if debug:
        return ET_total, ET_plant, ET_soil

    return ET_total

def calculate_drainage(
    soil_water: float,
    field_capacity: float,
    drainage_rate: float = 0.5
) -> float:
    """
    Calculate drainage rate when soil is above field capacity

    Water above field capacity drains due to gravity.

    Args:
        soil_water: Current soil water content (%)
        field_capacity: Soil water at field capacity (%)
        drainage_rate: Fraction that drains per hour (default 0.5 = 50%)

    Returns:
        Drainage in % per hour
    """
    if soil_water > field_capacity:
        # 50% of excess water drains per hour
        drainage = drainage_rate * (soil_water - field_capacity)
        return drainage
    return 0.0


def update_soil_water(
    soil_water: float,
    ET: float,
    drainage: float,
    irrigation: float,
    pot_volume: float,
    saturation: float
) -> Tuple[float, float]:
    """
    Update soil water content for one timestep (1 hour)

    Water balance: new_water = current + irrigation - ET - drainage

    Args:
        soil_water: Current soil water content (%)
        ET: Evapotranspiration this hour (L)
        drainage: Drainage this hour (% of soil volume)
        irrigation: Water added this hour (L)
        pot_volume: Volume of pot/container (L)
        saturation: Maximum soil water content (%)

    Returns:
        Tuple of (new_soil_water, runoff)
        - new_soil_water: Updated soil water (%)
        - runoff: Water that ran off due to saturation (L)
    """
    # Convert ET from liters to % of pot volume
    ET_percent = (ET / pot_volume) * 100 if pot_volume > 0 else 0

    # Convert irrigation from liters to % of pot volume
    irrigation_percent = (irrigation / pot_volume) * 100 if pot_volume > 0 else 0

    # Water balance equation
    new_soil_water = soil_water + irrigation_percent - ET_percent - drainage
    
    # with open("data/records/soil_water.txt", "a") as f:
    #     f.write(f"{soil_water},{new_soil_water},{irrigation_percent},{ET_percent},{drainage}\n")

    # Handle runoff (water above saturation runs off)
    runoff = 0.0
    if new_soil_water > saturation:
        runoff_percent = new_soil_water - saturation
        runoff = (runoff_percent / 100) * pot_volume  # Convert back to liters
        new_soil_water = saturation

    # Clamp to valid range
    new_soil_water = max(0, min(saturation, new_soil_water))

    return new_soil_water, runoff


# def calculate_water_stress(
#     soil_water: float,
#     wilting_point: float,
#     optimal_min: float,
#     optimal_max: float,
#     saturation: float
# ) -> float:
#     """
#     Calculate water stress factor (0 = no stress, 1 = maximum stress)

#     Stress occurs when soil water is:
#     - Below optimal range (drought stress)
#     - Above optimal range (waterlogging stress)

#     Args:
#         soil_water: Current soil water content (%)
#         wilting_point: Permanent wilting point (%)
#         optimal_min: Lower bound of optimal range (%)
#         optimal_max: Upper bound of optimal range (%)
#         saturation: Saturation point (%)

#     Returns:
#         Water stress factor (0-1)
#     """
#     if soil_water <= wilting_point:
#         # Complete stress at or below wilting point
#         return 1.0
#     elif soil_water < optimal_min:
#         # Drought stress (linear interpolation)
#         if optimal_min <= wilting_point:
#             return 1.0
#         return (optimal_min - soil_water) / (optimal_min - wilting_point)
#     elif soil_water <= optimal_max:
#         # Optimal range - no stress
#         return 0.0
#     elif soil_water < saturation:
#         # Waterlogging stress (linear interpolation)
#         if saturation <= optimal_max:
#             return 0.0
#         return (soil_water - optimal_max) / (saturation - optimal_max)
#     else:
#         # At saturation - significant waterlogging stress
#         return 0.8  # Not quite 1.0 as plant can survive briefly


def calculate_water_stress(
    soil_water: float,
    wilting_point: float,
    optimal_min: float,
    optimal_max: float,
    saturation: float,
    hours_without_water: float = 0.0,
    previous_stress: float = 0.0,
    dt: float = 1.0,
    root_fraction: float = 0.0,
    growth_strategy: str = "leaf_first"
) -> tuple[float, float]:
    """
    Calculate water stress factor with TIME-BASED EXPONENTIAL ACCUMULATION

    KEY IMPROVEMENTS:
    1. Stress accumulates EXPONENTIALLY when water is inadequate (non-linear)
    2. Stress reduces GRADUALLY when water is supplied (bit by bit recovery)
    3. Tracks time without adequate water for realistic stress dynamics

    STRESS DYNAMICS:
    - When soil water < optimal: Stress accumulates exponentially over time
    - When soil water >= optimal: Stress recovers gradually (slower than accumulation)
    - Longer without water = faster stress accumulation (exponential growth)
    - Recovery is slower than accumulation (realistic plant physiology)

    Args:
        soil_water: Current soil water content (%)
        wilting_point: Permanent wilting point (%)
        optimal_min: Lower bound of optimal range (%)
        optimal_max: Upper bound of optimal range (%)
        saturation: Saturation point (%)
        hours_without_water: Hours since soil water dropped below optimal
        previous_stress: Previous accumulated stress level (0-1)
        dt: Time step in hours (default 1.0)

    Returns:
        Tuple of (new_stress, new_hours_without_water)
    """
    import math

    # Calculate instantaneous stress from current soil water
    # This is the "potential" stress level based on current conditions
    if soil_water <= wilting_point:
        instantaneous_stress = 1.0
    elif soil_water < optimal_min:
        if optimal_min <= wilting_point:
            instantaneous_stress = 1.0
        else:
            # Linear increase from optimal to wilting point
            instantaneous_stress = (optimal_min - soil_water) / (optimal_min - wilting_point)
    elif soil_water <= optimal_max:
        instantaneous_stress = 0.0
    elif soil_water < saturation:
        if saturation <= optimal_max:
            instantaneous_stress = 0.0
        else:
            # Waterlogging stress
            instantaneous_stress = (soil_water - optimal_max) / (saturation - optimal_max)
    else:
        instantaneous_stress = 0.8  # Near saturation waterlogging stress

    # ROOT EFFICIENCY MODULATION
    # Structure-first plants with higher root fraction experience reduced stress
    # because they can extract water more efficiently from soil
    if root_fraction > 0.1 and growth_strategy == "structure_first":
        # Root efficiency bonus: 0-30% stress reduction based on root fraction
        # root_fraction 0.1 → 0% reduction (baseline)
        # root_fraction 0.2 → 15% reduction
        # root_fraction 0.3+ → 30% reduction
        root_efficiency_factor = min(0.3, (root_fraction - 0.1) * 1.5)
        instantaneous_stress *= (1.0 - root_efficiency_factor)

    # GROWTH STRATEGY MODULATION
    # Leaf-first plants are more vulnerable to water stress (shallow roots, high transpiration)
    # Structure-first plants are more resilient (deep roots, lower transpiration)
    if growth_strategy == "leaf_first":
        # Leaf-first: 10% more vulnerable to stress
        instantaneous_stress *= 1.1
    elif growth_strategy == "structure_first":
        # Structure-first: 15% more resilient to stress
        instantaneous_stress *= 0.85

    # Clamp to [0, 1] after modulation
    instantaneous_stress = max(0.0, min(1.0, instantaneous_stress))

    # Update hours without adequate water
    if soil_water < optimal_min:
        # Water is inadequate - increment time counter
        new_hours_without_water = hours_without_water + dt
    else:
        # Water is adequate - reset counter
        new_hours_without_water = 0.0

    # EXPONENTIAL STRESS ACCUMULATION when water is inadequate
    if soil_water < optimal_min:
        # Stress accumulates exponentially with time
        # Formula: stress(t) = stress_max * (1 - exp(-k * t))
        # where k controls accumulation rate

        # Accumulation rate depends on severity of water deficit
        if soil_water <= wilting_point:
            # Critical stress - very fast accumulation
            k_accumulation = 0.15  # Reaches 90% stress in ~15 hours
        else:
            # Moderate stress - slower accumulation
            # Scale k based on how far below optimal
            deficit_ratio = (optimal_min - soil_water) / (optimal_min - wilting_point)
            k_accumulation = 0.05 + 0.10 * deficit_ratio  # 0.05-0.15 range

        # Exponential accumulation towards instantaneous stress level
        # New stress approaches instantaneous stress exponentially
        stress_increment = (instantaneous_stress - previous_stress) * (1 - math.exp(-k_accumulation * dt))
        new_stress = previous_stress + stress_increment

    # GRADUAL STRESS RECOVERY when water is supplied
    else:
        # Stress recovers gradually (slower than accumulation)
        # Recovery rate is slower to reflect plant physiology
        k_recovery = 0.03  # Slower than accumulation (takes ~30 hours to recover 90%)

        # Exponential decay towards instantaneous stress (which is 0 or low)
        stress_decrement = (previous_stress - instantaneous_stress) * (1 - math.exp(-k_recovery * dt))
        new_stress = previous_stress - stress_decrement

    # Clamp to [0, 1]
    new_stress = max(0.0, min(1.0, new_stress))

    # Log to file
    # try:
    #     with open("data/records/water_stress.txt", "a") as f:
    #         f.write(
    #             f"{soil_water},{wilting_point},{optimal_min},{optimal_max},{saturation},"
    #             f"{instantaneous_stress:.4f},{new_stress:.4f},{hours_without_water:.1f},{new_hours_without_water:.1f}\n"
    #         )
    # except Exception as e:
    #     print(f"[WaterStress Log Error] {e}")

    return new_stress, new_hours_without_water


def calculate_water_stress_factor(
    soil_water: float,
    wilting_point: float,
    optimal_min: float,
    biomass: float,
    min_biomass: float = 0.5
) -> float:
    """
    Calculate water stress factor for RGR scaling with biomass dependency

    IMPROVED: Smaller seedlings are more vulnerable to water stress.
    This creates gradual stress accumulation rather than instant collapse.

    Formula:
    - Base stress from soil water
    - Biomass vulnerability factor: smaller plants = higher stress multiplier
    - Gradual transition prevents instant collapse

    Args:
        soil_water: Current soil water content (%)
        wilting_point: Permanent wilting point (%)
        optimal_min: Lower bound of optimal range (%)
        biomass: Current plant biomass (g)
        min_biomass: Minimum biomass for stress calculation (g, default 0.5)

    Returns:
        Water stress factor for RGR (0-1, where 1 = maximum stress)
    """
    # Base stress from soil water
    if soil_water >= optimal_min:
        base_stress = 0.0
    elif soil_water <= wilting_point:
        base_stress = 1.0
    else:
        # Linear increase from optimal to wilting point
        base_stress = (optimal_min - soil_water) / (optimal_min - wilting_point)

    # Biomass vulnerability factor
    # Smaller seedlings (< 1g) are MORE vulnerable to stress
    # Larger plants (> 10g) are LESS vulnerable
    if biomass < min_biomass:
        # Very small seedlings: 2x stress multiplier
        vulnerability = 2.0
    elif biomass < 1.0:
        # Small seedlings: 1.5-2x stress multiplier (gradual)
        vulnerability = 1.5 + 0.5 * (1.0 - biomass) / (1.0 - min_biomass)
    elif biomass < 10.0:
        # Medium plants: 1.0-1.5x stress multiplier (gradual)
        vulnerability = 1.0 + 0.5 * (10.0 - biomass) / 9.0
    else:
        # Large plants: 1.0x stress multiplier (baseline)
        vulnerability = 1.0

    # Combined stress with vulnerability
    stress_factor = base_stress * vulnerability

    # Clamp to [0, 1]
    return min(1.0, max(0.0, stress_factor))

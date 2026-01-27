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


def calculate_et(
    leaf_area: float,
    light_PAR: float,
    soil_water: float,
    VPD: float,
    wilting_point: float,
    field_capacity: float,
    optimal_VPD: float = 1.2
) -> float:
    """
    Calculate Evapotranspiration (ET) rate

    ET represents water loss through plant transpiration + soil evaporation.
    Includes baseline soil evaporation that occurs even when plant cannot transpire.

    Args:
        leaf_area: Plant leaf area in m^2
        light_PAR: Photosynthetically Active Radiation in umol/m^2/s
        soil_water: Current soil water content (%)
        VPD: Vapor Pressure Deficit in kPa
        wilting_point: Soil water at wilting point (%)
        field_capacity: Soil water at field capacity (%)
        optimal_VPD: Optimal VPD for transpiration (default 1.2 kPa)

    Returns:
        ET rate in L/hour
    """
    # Base ET rate: 0.02 L/h per m^2 of leaf area index
    ET_BASE = 0.02  # L/h/m^2 LAI

    # Baseline soil evaporation (always occurs, even when plant can't transpire)
    # This represents direct soil surface evaporation
    SOIL_EVAP_BASE = 0.002  # L/h baseline

    # Potential ET increases with light (stomata open more under light)
    ET_pot = ET_BASE * leaf_area * (1 + 0.001 * light_PAR)

    # Water availability factor (0-1)
    # Plant can only transpire if soil has available water
    if field_capacity <= wilting_point:
        f_water = 0.0
    else:
        f_water = max(0, min(1, (soil_water - wilting_point) / (field_capacity - wilting_point)))

    # VPD factor: higher VPD drives more transpiration
    # f_VPD ranges from 0.5 (low VPD) to 1.0 (optimal/high VPD)
    f_VPD = 0.5 + 0.5 * min(1, VPD / optimal_VPD)

    # Plant transpiration (depends on water availability)
    ET_plant = ET_pot * f_water * f_VPD

    # Soil evaporation (always occurs if soil has water, scaled by soil moisture)
    # Even dry soil loses some water to evaporation
    soil_evap_factor = min(1, soil_water / 50)  # Scales from 0-50% soil water
    ET_soil = SOIL_EVAP_BASE * soil_evap_factor * (0.5 + 0.5 * VPD)

    # Total ET
    ET = ET_plant + ET_soil

    return max(0, ET)


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

    # Handle runoff (water above saturation runs off)
    runoff = 0.0
    if new_soil_water > saturation:
        runoff_percent = new_soil_water - saturation
        runoff = (runoff_percent / 100) * pot_volume  # Convert back to liters
        new_soil_water = saturation

    # Clamp to valid range
    new_soil_water = max(0, min(saturation, new_soil_water))

    return new_soil_water, runoff


def calculate_water_stress(
    soil_water: float,
    wilting_point: float,
    optimal_min: float,
    optimal_max: float,
    saturation: float
) -> float:
    """
    Calculate water stress factor (0 = no stress, 1 = maximum stress)

    Stress occurs when soil water is:
    - Below optimal range (drought stress)
    - Above optimal range (waterlogging stress)

    Args:
        soil_water: Current soil water content (%)
        wilting_point: Permanent wilting point (%)
        optimal_min: Lower bound of optimal range (%)
        optimal_max: Upper bound of optimal range (%)
        saturation: Saturation point (%)

    Returns:
        Water stress factor (0-1)
    """
    if soil_water <= wilting_point:
        # Complete stress at or below wilting point
        return 1.0
    elif soil_water < optimal_min:
        # Drought stress (linear interpolation)
        if optimal_min <= wilting_point:
            return 1.0
        return (optimal_min - soil_water) / (optimal_min - wilting_point)
    elif soil_water <= optimal_max:
        # Optimal range - no stress
        return 0.0
    elif soil_water < saturation:
        # Waterlogging stress (linear interpolation)
        if saturation <= optimal_max:
            return 0.0
        return (soil_water - optimal_max) / (saturation - optimal_max)
    else:
        # At saturation - significant waterlogging stress
        return 0.8  # Not quite 1.0 as plant can survive briefly

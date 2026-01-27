"""
Damage Accumulation & Death Mechanics
Handles stress-induced damage, recovery, and death conditions

Equations from plant_simulator_focused_implementation.pdf Section 5
"""
from typing import Tuple


def calculate_damage_rate(
    soil_water: float,
    air_temp: float,
    soil_EC: float,
    wilting_point: float,
    saturation: float,
    T_min: float,
    T_max: float,
    EC_toxicity_threshold: float = 3.5
) -> Tuple[float, dict]:
    """
    Calculate hourly damage rate from all stress sources

    Damage accumulates from:
    1. Water stress (drought or waterlogging)
    2. Temperature extremes (cold or heat)
    3. Nutrient toxicity (high EC/salts)

    Args:
        soil_water: Current soil water content (%)
        air_temp: Air temperature (C)
        soil_EC: Soil electrical conductivity (mS/cm)
        wilting_point: Soil water at wilting point (%)
        saturation: Soil water at saturation (%)
        T_min: Minimum temperature for growth (C)
        T_max: Maximum temperature for growth (C)
        EC_toxicity_threshold: EC level causing damage (mS/cm)

    Returns:
        Tuple of (total_damage_rate, damage_breakdown)
        - total_damage_rate: Total damage % per hour
        - damage_breakdown: Dict with individual damage sources
    """
    damage_rate = 0.0
    damage_breakdown = {
        'water_drought': 0.0,
        'water_flood': 0.0,
        'temp_cold': 0.0,
        'temp_heat': 0.0,
        'nutrient_toxicity': 0.0
    }

    # Source 1: Water stress damage
    # Damage starts when at or below wilting point (with small margin for numerical stability)
    if soil_water <= wilting_point + 0.5:  # Small margin to catch rounding at wilting point
        # 5% damage per hour when wilting (drought)
        damage_breakdown['water_drought'] = 5.0
        damage_rate += 5.0
    elif soil_water > saturation * 0.95:
        # 2% damage per hour when waterlogged (root hypoxia)
        damage_breakdown['water_flood'] = 2.0
        damage_rate += 2.0

    # Source 2: Temperature extremes damage
    if air_temp < T_min:
        # Cold damage - proportional to how far below T_min
        # 3% base rate, scaled by deviation / 5 degrees
        cold_damage = 3.0 * (T_min - air_temp) / 5.0
        damage_breakdown['temp_cold'] = cold_damage
        damage_rate += cold_damage
    elif air_temp > T_max:
        # Heat damage - proportional to how far above T_max
        # 3% base rate, scaled by deviation / 5 degrees
        heat_damage = 3.0 * (air_temp - T_max) / 5.0
        damage_breakdown['temp_heat'] = heat_damage
        damage_rate += heat_damage

    # Source 3: Nutrient toxicity damage
    if soil_EC > EC_toxicity_threshold:
        # 1.5% damage per hour from salt toxicity
        damage_breakdown['nutrient_toxicity'] = 1.5
        damage_rate += 1.5

    return damage_rate, damage_breakdown


def apply_damage(
    cumulative_damage: float,
    damage_rate: float
) -> float:
    """
    Apply damage for one timestep

    Args:
        cumulative_damage: Current accumulated damage (%)
        damage_rate: Damage rate this hour (%)

    Returns:
        Updated cumulative damage (0-100%)
    """
    new_damage = cumulative_damage + damage_rate
    return max(0, min(100, new_damage))


def apply_damage_recovery(
    cumulative_damage: float,
    water_stress: float,
    temp_stress: float,
    nutrient_stress: float,
    recovery_rate: float = 0.5
) -> float:
    """
    Apply damage recovery when conditions are favorable

    Recovery only occurs when all stress factors are low.
    Recovery is much slower than damage accumulation (asymmetric).

    Args:
        cumulative_damage: Current accumulated damage (%)
        water_stress: Water stress factor (0-1)
        temp_stress: Temperature stress factor (0-1)
        nutrient_stress: Nutrient stress factor (0-1)
        recovery_rate: Recovery % per hour when conditions good (default 0.5)

    Returns:
        Updated cumulative damage (%)
    """
    # Recovery only when all stresses are low
    if water_stress < 0.3 and temp_stress < 0.2 and nutrient_stress < 0.3:
        new_damage = cumulative_damage - recovery_rate
        return max(0, new_damage)

    return cumulative_damage


def check_death(
    cumulative_damage: float,
    death_threshold: float = 95.0
) -> bool:
    """
    Check if plant has died from accumulated damage

    Args:
        cumulative_damage: Current accumulated damage (%)
        death_threshold: Damage level causing death (%, default 95)

    Returns:
        True if plant is dead, False otherwise
    """
    return cumulative_damage >= death_threshold


def apply_growth_penalty(
    max_biomass: float,
    cumulative_damage: float,
    penalty_rate: float = 0.005
) -> float:
    """
    Calculate effective maximum biomass with damage penalty

    Accumulated damage permanently reduces growth potential.

    Args:
        max_biomass: Genetic maximum biomass (g)
        cumulative_damage: Current accumulated damage (%)
        penalty_rate: Biomass reduction per % damage (default 0.005 = 0.5%)

    Returns:
        Effective maximum biomass (g)
    """
    # Each 1% damage reduces max biomass by 0.5%
    penalty_factor = 1 - penalty_rate * cumulative_damage
    penalty_factor = max(0, penalty_factor)

    return max_biomass * penalty_factor


def calculate_combined_stress(
    water_stress: float,
    temp_stress: float,
    nutrient_stress: float
) -> float:
    """
    Calculate combined stress level from all sources

    Uses multiplicative combination - stresses compound each other.

    Args:
        water_stress: Water stress factor (0-1)
        temp_stress: Temperature stress factor (0-1)
        nutrient_stress: Nutrient stress factor (0-1)

    Returns:
        Combined stress factor (0-1)
    """
    # Multiplicative: (1-combined) = (1-water)*(1-temp)*(1-nutrient)
    # combined = 1 - (1-water)*(1-temp)*(1-nutrient)
    healthy_factor = (1 - water_stress) * (1 - temp_stress) * (1 - nutrient_stress)
    combined_stress = 1 - healthy_factor

    return max(0, min(1, combined_stress))

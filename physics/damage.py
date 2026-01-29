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
    # FIXED: Graduated damage system - damage starts earlier with lower severity
    # Damage starts when soil water drops below wilting point + 5% (more realistic)
    if soil_water <= wilting_point + 5.0:  # Start damage earlier (20% for tomato)
        if soil_water <= wilting_point:
            # Severe damage when at or below permanent wilting point
            damage_breakdown['water_drought'] = 5.0
            damage_rate += 5.0
        else:
            # Moderate damage between wilting point and wilting point + 5%
            # This represents the transition zone where plants show stress
            damage_breakdown['water_drought'] = 2.0
            damage_rate += 2.0
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


def check_death_comprehensive(
    cumulative_damage: float,
    biomass: float,
    history: list,
    current_hour: int,
    damage_threshold: float = 95.0,
    min_biomass: float = 0.01,
    negative_rgr_hours: int = 48,
    zero_co2_uptake_hours: int = 24
) -> tuple[bool, str]:
    """
    Comprehensive death check with multiple conditions

    Plant is dead if ANY of these conditions are met:
    1. Cumulative damage >= 95%
    2. Biomass <= 0.01 g (essentially nothing left)
    3. Net RGR <= 0 for > 48 hours consecutively
    4. CO2 uptake <= 0 for > 24 hours consecutively

    IMPORTANT: Handles variable tick rates by checking actual measurements
    in history, not just counting ticks. This prevents bias when tick size
    varies (e.g., 24-hour ticks would only measure at night).

    Args:
        cumulative_damage: Current accumulated damage (%)
        biomass: Current biomass (g)
        history: List of historical state checkpoints
        current_hour: Current simulation hour
        damage_threshold: Damage level causing death (%, default 95)
        min_biomass: Minimum viable biomass (g, default 0.01)
        negative_rgr_hours: Hours of negative RGR before death (default 48)
        zero_co2_uptake_hours: Hours of zero CO2 uptake before death (default 24)

    Returns:
        Tuple of (is_dead: bool, death_reason: str)
    """
    # Condition 1: Cumulative damage
    if cumulative_damage >= damage_threshold:
        return True, f"Cumulative damage ({cumulative_damage:.1f}%) >= {damage_threshold}%"

    # Condition 2: Biomass depletion
    if biomass <= min_biomass:
        return True, f"Biomass ({biomass:.4f}g) <= minimum viable ({min_biomass}g)"

    # For conditions 3 and 4, we need sufficient history
    if len(history) < 2:
        return False, ""

    # Condition 3: Negative RGR for extended period
    # Check actual measurements, not just tick count
    negative_rgr_duration = _check_consecutive_condition(
        history,
        current_hour,
        lambda state: state.get('RGR', 0) <= 0,
        negative_rgr_hours
    )

    if negative_rgr_duration >= negative_rgr_hours:
        return True, f"Negative/zero RGR for {negative_rgr_duration:.0f} consecutive hours (threshold: {negative_rgr_hours}h)"

    # Condition 4: Zero CO2 uptake for extended period
    # CO2 uptake = photosynthesis - respiration (net CO2 consumption)
    # Negative means plant is producing more CO2 than consuming (no photosynthesis)
    zero_co2_duration = _check_consecutive_condition(
        history,
        current_hour,
        lambda state: (state.get('photosynthesis', 0) - state.get('respiration', 0)) <= 0,
        zero_co2_uptake_hours
    )

    if zero_co2_duration >= zero_co2_uptake_hours:
        return True, f"Zero/negative CO2 uptake for {zero_co2_duration:.0f} consecutive hours (threshold: {zero_co2_uptake_hours}h)"

    return False, ""


def _check_consecutive_condition(
    history: list,
    current_hour: int,
    condition_func: callable,
    required_hours: int
) -> float:
    """
    Check how long a condition has been true consecutively

    This function properly handles variable tick rates by checking actual
    hour timestamps in the history, not just counting entries.

    Args:
        history: List of historical state checkpoints
        current_hour: Current simulation hour
        condition_func: Function that takes a state dict and returns bool
        required_hours: Number of consecutive hours required

    Returns:
        Number of consecutive hours the condition has been true
    """
    if len(history) < 2:
        return 0.0

    # Start from the most recent state and work backwards
    consecutive_hours = 0.0

    for i in range(len(history) - 1, -1, -1):
        state = history[i]

        # Check if condition is met
        if condition_func(state):
            # Calculate time span this state represents
            if i > 0:
                # Time between this state and previous state
                prev_hour = history[i - 1].get('hour', 0)
                curr_hour = state.get('hour', 0)
                time_span = curr_hour - prev_hour
            else:
                # First state - assume 1 hour
                time_span = 1.0

            consecutive_hours += time_span

            # If we've accumulated enough hours, we can stop
            if consecutive_hours >= required_hours:
                break
        else:
            # Condition broken - reset counter
            break

    return consecutive_hours


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

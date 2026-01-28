"""
Plant Growth Physics
Handles photosynthesis, respiration, and biomass accumulation

Equations from plant_simulator_focused_implementation.pdf Section 4.2

Key formulas:
- P_effective = P_gross * (1 - water_stress)
- net_carbon = P_effective - R_maint
- delta_biomass = net_carbon * (1 - 0.01 * cumulative_damage)

Day/night cycle:
- Photosynthesis only occurs during daylight hours (6:00-20:00)
- Respiration occurs 24 hours
- At night: net_carbon is negative → biomass loss
"""
from typing import Tuple
import math


# Day/night cycle constants
DAY_START_HOUR = 6   # 6:00 AM
DAY_END_HOUR = 20    # 8:00 PM (14 hours of light)


def is_daytime(hour: int) -> bool:
    """
    Determine if it's daytime based on hour of day

    Uses a 24-hour cycle where:
    - Day: 6:00 - 20:00 (14 hours of light)
    - Night: 20:00 - 6:00 (10 hours of darkness)

    Args:
        hour: Simulation hour (0, 1, 2, ...)

    Returns:
        True if daytime, False if nighttime
    """
    hour_of_day = hour % 24
    return DAY_START_HOUR <= hour_of_day < DAY_END_HOUR


def get_light_factor(hour: int) -> float:
    """
    Get light availability factor based on time of day

    Simulates natural light cycle:
    - Night (20:00-6:00): 0.0 (no light)
    - Dawn/Dusk: gradual transition
    - Midday: 1.0 (full light)

    Args:
        hour: Simulation hour

    Returns:
        Light factor (0-1), 0 = night, 1 = full daylight
    """
    hour_of_day = hour % 24

    if hour_of_day < DAY_START_HOUR or hour_of_day >= DAY_END_HOUR:
        # Night time
        return 0.0

    # Calculate position within day (0 = dawn, 1 = dusk)
    day_length = DAY_END_HOUR - DAY_START_HOUR
    day_progress = (hour_of_day - DAY_START_HOUR) / day_length

    # Sinusoidal light curve (peaks at solar noon)
    import math
    light_factor = math.sin(day_progress * math.pi)

    return max(0, light_factor)


def calculate_nutrient_factor(
    soil_N: float,
    soil_P: float,
    soil_K: float,
    optimal_N: float,
    optimal_P: float,
    optimal_K: float
) -> float:
    """
    Calculate nutrient limitation factor

    Growth is limited by the most deficient nutrient (Liebig's law of minimum).

    f_nutrient = min(f_N, f_P, f_K) where f_X = min(1, soil_X / optimal_X)

    Args:
        soil_N: Current soil nitrogen (ppm)
        soil_P: Current soil phosphorus (ppm)
        soil_K: Current soil potassium (ppm)
        optimal_N: Optimal nitrogen level (ppm)
        optimal_P: Optimal phosphorus level (ppm)
        optimal_K: Optimal potassium level (ppm)

    Returns:
        Nutrient factor (0-1), 1 = no limitation
    """
    # Calculate individual nutrient factors
    f_N = min(1.0, soil_N / optimal_N) if optimal_N > 0 else 1.0
    f_P = min(1.0, soil_P / optimal_P) if optimal_P > 0 else 1.0
    f_K = min(1.0, soil_K / optimal_K) if optimal_K > 0 else 1.0

    # Limiting factor (minimum of all)
    f_nutrient = min(f_N, f_P, f_K)

    return max(0, f_nutrient)


def calculate_photosynthesis(
    light_PAR: float,
    biomass: float,
    f_temp: float,
    f_nutrient: float,
    LUE: float = 0.003,
    leaf_area_ratio: float = 0.004,
) -> float:
    """
    Calculate gross photosynthetic production

    P_gross = LUE * PAR_absorbed * f_temp * f_nutrient

    Where:
    - LUE = Light Use Efficiency (g/umol, typically 0.003)
    - PAR_absorbed = light_PAR * light_interception * 3600 s/h

    Args:
        light_PAR: Photosynthetically Active Radiation (umol/m^2/s)
        biomass: Current biomass (g) - used to calculate leaf area
        f_temp: Temperature response factor (0-1)
        f_nutrient: Nutrient limitation factor (0-1)
        LUE: Light Use Efficiency (g/umol, default 0.003)
        leaf_area_ratio: Leaf area per biomass (m^2/g, default 0.004)

    Returns:
        Gross photosynthesis this hour (g)
    """
    # Calculate leaf area from biomass
    leaf_area = biomass * leaf_area_ratio  # m² leaf per plant

    # Light interception using Beer-Lambert law
    k = 0.7  # light extinction coefficient for lettuce
    light_interception = 1 - math.exp(-k * leaf_area)

    # PAR absorbed per hour (umol/h)
    # FIX: Must multiply by 3600 to convert umol/m²/s to umol/h
    PAR_absorbed = light_PAR * light_interception * 3600

    # Boost LUE for early growth (small plants are more efficient)
    if biomass < 0.3:
        LUE_effective = LUE * 3  # 3x boost for seedlings
    else:
        LUE_effective = LUE

    # Calculate gross photosynthesis
    P_gross = LUE_effective * PAR_absorbed * f_temp * f_nutrient

    # Additional boost for very small plants to overcome initial growth barrier
    if biomass < 0.1:
        P_gross *= 2

    # Debug logging
    with open('data/records/photosynthesis.txt', 'a') as f:
        f.write(f"{light_PAR},{biomass},{leaf_area},{f_temp},{f_nutrient},{P_gross}\n")

    return max(0, P_gross)


def calculate_respiration(
    biomass: float,
    r_base: float = 0.000026  # FIX: 0.0625% per hour = 1.5% per day
) -> float:
    """
    Calculate maintenance respiration

    R_maint = r_base * biomass

    Respiration is the metabolic cost of maintaining living tissue.

    IMPORTANT: This is called EVERY HOUR, so r_base must be per-hour rate!
    - Daily respiration: ~1.5% of biomass per day
    - Hourly respiration: 1.5% / 24 = 0.0625% per hour = 0.000625 / 24 = 0.000026

    Args:
        biomass: Current plant biomass (g)
        r_base: Base respiration rate (fraction/hour, default 0.000026 = 0.0625%/h = 1.5%/day)

    Returns:
        Maintenance respiration this hour (g)
    """
    R_maint = r_base * biomass
    return max(0, R_maint)


def calculate_growth(
    P_gross: float,
    R_maint: float,
    water_stress: float,
    cumulative_damage: float,
    hour: int = 0
) -> float:
    """
    Calculate net biomass growth with stress factors and day/night cycle

    Formulas:
    - P_effective = P_gross * (1 - water_stress) * (1 - damage_factor)
    - net_carbon = P_effective - R_maint
    - delta_biomass = net_carbon

    IMPORTANT:
    - P_gross ALREADY includes day/night cycle (calculated with light_PAR)
    - Do NOT apply light_factor again here!
    - Respiration > photosynthesis at night → NEGATIVE delta_biomass

    Args:
        P_gross: Gross photosynthesis this hour (g) - already includes light availability
        R_maint: Maintenance respiration this hour (g)
        water_stress: Water stress factor (0-1, where 1 = maximum stress)
        cumulative_damage: Accumulated damage (%)
        hour: Current simulation hour (for logging/debugging only)

    Returns:
        Biomass change this hour (g) - can be NEGATIVE if respiration > photosynthesis
    """
    # Damage factor reduces photosynthetic efficiency
    damage_factor = 0.01 * cumulative_damage
    damage_factor = min(1.0, max(0, damage_factor))

    # Effective photosynthesis: reduced by water stress and damage
    # NOTE: Do NOT apply light_factor here - P_gross already accounts for light!
    P_effective = P_gross * (1 - water_stress) * (1 - damage_factor)

    # Net carbon balance (photosynthesis - respiration)
    # Can be negative at night when P_gross = 0 but R_maint > 0
    net_carbon = P_effective - R_maint

    # Delta biomass equals net carbon (no additional factors)
    delta_biomass = net_carbon

    return delta_biomass


def update_biomass(
    current_biomass: float,
    delta_biomass: float,
    max_biomass: float,
    cumulative_damage: float,
    min_biomass: float = 0.01
) -> Tuple[float, float]:
    """
    Update plant biomass with growth or loss

    Accounts for:
    - Maximum biomass limit (genetic potential)
    - Growth penalty from accumulated damage
    - Biomass LOSS when respiration > photosynthesis (e.g., at night)
    - Minimum biomass threshold (plant dies below this)

    Args:
        current_biomass: Current biomass (g)
        delta_biomass: Biomass change this hour (g) - CAN BE NEGATIVE
        max_biomass: Maximum genetic potential biomass (g)
        cumulative_damage: Accumulated damage (%)
        min_biomass: Minimum viable biomass (g, default 0.1)

    Returns:
        Tuple of (new_biomass, actual_change)
    """
    # Effective max biomass reduced by damage
    # Each 1% damage reduces max by 0.5%
    max_biomass_effective = max_biomass * (1 - 0.005 * cumulative_damage)
    max_biomass_effective = max(0, max_biomass_effective)

    # Apply biomass change (can be positive OR negative)
    new_biomass = current_biomass + delta_biomass

    # Cap at effective maximum (only applies to growth)
    if new_biomass > max_biomass_effective:
        new_biomass = max_biomass_effective

    # Floor at minimum biomass (plant can't go below survival threshold)
    if new_biomass < min_biomass:
        new_biomass = min_biomass

    # Calculate actual change achieved
    actual_change = new_biomass - current_biomass

    return new_biomass, actual_change


def update_leaf_area(
    biomass: float,
    leaf_area_ratio: float = 0.004
) -> float:
    """
    Update leaf area based on biomass

    leaf_area = alpha * biomass

    Args:
        biomass: Current plant biomass (g)
        leaf_area_ratio: Leaf area per unit biomass (m^2/g, default 0.004)

    Returns:
        Leaf area (m^2)
    """
    leaf_area = leaf_area_ratio * biomass
    return max(0, leaf_area)


def decay_biomass(
    biomass: float,
    decay_rate: float = 0.01
) -> float:
    """
    Apply biomass decay for dead plants

    Dead plants lose biomass over time due to decomposition.

    Args:
        biomass: Current biomass (g)
        decay_rate: Fraction lost per hour (default 0.01 = 1%)

    Returns:
        New biomass after decay (g)
    """
    new_biomass = biomass * (1 - decay_rate)
    return max(0, new_biomass)

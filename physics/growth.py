"""
Plant Growth Physics
Handles photosynthesis, respiration, and biomass accumulation

Equations from plant_simulator_focused_implementation.pdf Section 4.2
"""
from typing import Tuple


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
    leaf_area: float,
    f_temp: float,
    f_nutrient: float,
    LUE: float = 0.003
) -> float:
    """
    Calculate gross photosynthetic production

    P_gross = LUE * PAR_absorbed * f_temp * f_nutrient

    Where:
    - LUE = Light Use Efficiency (g/umol, typically 0.003)
    - PAR_absorbed = light_PAR * leaf_area * 1h * 3600 s/h

    Args:
        light_PAR: Photosynthetically Active Radiation (umol/m^2/s)
        leaf_area: Plant leaf area (m^2)
        f_temp: Temperature response factor (0-1)
        f_nutrient: Nutrient limitation factor (0-1)
        LUE: Light Use Efficiency (g/umol, default 0.003)

    Returns:
        Gross photosynthesis this hour (g)
    """
    # Convert PAR to absorbed photons per hour
    # PAR (umol/m^2/s) * leaf_area (m^2) * 3600 (s/h) = umol/h
    PAR_absorbed = light_PAR * leaf_area * 3600

    # Gross photosynthesis
    P_gross = LUE * PAR_absorbed * f_temp * f_nutrient

    return max(0, P_gross)


def calculate_respiration(
    biomass: float,
    r_base: float = 0.000625
) -> float:
    """
    Calculate maintenance respiration

    R_maint = r_base * biomass

    Respiration is the metabolic cost of maintaining living tissue.

    Args:
        biomass: Current plant biomass (g)
        r_base: Base respiration rate (g/g/h, default 0.000625 = 1.5%/day)

    Returns:
        Maintenance respiration this hour (g)
    """
    R_maint = r_base * biomass
    return max(0, R_maint)


def calculate_growth(
    P_gross: float,
    R_maint: float,
    water_stress: float,
    cumulative_damage: float
) -> float:
    """
    Calculate net biomass growth with stress factors

    growth_factor = (1 - water_stress) * (1 - 0.01 * cumulative_damage)
    delta_biomass = max(0, (P_gross - R_maint) * growth_factor)

    Args:
        P_gross: Gross photosynthesis this hour (g)
        R_maint: Maintenance respiration this hour (g)
        water_stress: Water stress factor (0-1)
        cumulative_damage: Accumulated damage (%)

    Returns:
        Biomass growth this hour (g)
    """
    # Net carbon balance
    net_carbon = P_gross - R_maint

    # Growth factor accounts for stress and damage
    # Water stress reduces growth efficiency
    # Accumulated damage permanently reduces growth potential
    growth_factor = (1 - water_stress) * (1 - 0.01 * cumulative_damage)
    growth_factor = max(0, growth_factor)

    # Net growth (cannot be negative - plant doesn't shrink from respiration alone)
    delta_biomass = max(0, net_carbon * growth_factor)

    return delta_biomass


def update_biomass(
    current_biomass: float,
    delta_biomass: float,
    max_biomass: float,
    cumulative_damage: float
) -> Tuple[float, float]:
    """
    Update plant biomass with growth

    Accounts for:
    - Maximum biomass limit (genetic potential)
    - Growth penalty from accumulated damage

    Args:
        current_biomass: Current biomass (g)
        delta_biomass: Growth this hour (g)
        max_biomass: Maximum genetic potential biomass (g)
        cumulative_damage: Accumulated damage (%)

    Returns:
        Tuple of (new_biomass, actual_growth)
    """
    # Effective max biomass reduced by damage
    # Each 1% damage reduces max by 0.5%
    max_biomass_effective = max_biomass * (1 - 0.005 * cumulative_damage)
    max_biomass_effective = max(0, max_biomass_effective)

    # Add growth
    new_biomass = current_biomass + delta_biomass

    # Cap at effective maximum
    if new_biomass > max_biomass_effective:
        new_biomass = max_biomass_effective

    # Calculate actual growth achieved
    actual_growth = new_biomass - current_biomass

    return new_biomass, actual_growth


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

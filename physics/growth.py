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
from pathlib import Path
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


# def calculate_photosynthesis(
#     light_PAR: float,
#     biomass: float,
#     f_temp: float,
#     f_nutrient: float,
#     LUE: float = 0.003,
#     leaf_area_ratio: float = 0.004,
#     ground_area: float = 0.04,
# ) -> float:
#     """
#     Calculate gross photosynthetic production

#     P_gross = LUE * PAR_absorbed * f_temp * f_nutrient

#     Where:
#     - LUE = Light Use Efficiency (g/umol, typically 0.003)
#     - PAR_absorbed = light_PAR * light_interception * ground_area * 3600 s/h

#     Args:
#         light_PAR: Photosynthetically Active Radiation (umol/m^2/s)
#         biomass: Current biomass (g) - used to calculate leaf area
#         f_temp: Temperature response factor (0-1)
#         f_nutrient: Nutrient limitation factor (0-1)
#         LUE: Light Use Efficiency (g/umol, default 0.003)
#         leaf_area_ratio: Leaf area per biomass (m^2/g, default 0.004)
#         ground_area: Ground area occupied by plant (m^2, default 0.04 = 20x20cm)

#     Returns:
#         Gross photosynthesis this hour (g)
#     """
#     # Calculate leaf area from biomass
#     leaf_area = biomass * leaf_area_ratio  # m² leaf per plant

#     # FIX: Calculate LAI (Leaf Area Index) = leaf area / ground area
#     # This is what Beer-Lambert law actually expects
#     LAI = leaf_area / ground_area if ground_area > 0 else leaf_area

#     # Light interception using Beer-Lambert law with proper LAI
#     k = 0.7  # light extinction coefficient for leafy crops
#     light_interception = 1 - math.exp(-k * LAI)

#     # PAR absorbed per hour (umol/h)
#     # Now properly scaled by ground area the plant occupies
#     PAR_absorbed = light_PAR * light_interception * ground_area * 3600

#     # FIX: Smooth boost for early growth using continuous function
#     # Decays smoothly from ~6x at tiny biomass to 1x at larger biomass
#     # This avoids the discontinuous jumps at 0.1g and 0.3g thresholds
#     seedling_boost = 1.0 + 5.0 * math.exp(-biomass / 0.15)
#     LUE_effective = LUE * seedling_boost

#     # Calculate gross photosynthesis
#     P_gross = LUE_effective * PAR_absorbed * f_temp * f_nutrient

#     # Debug logging
#     with open('data/records/photosynthesis.txt', 'a') as f:
#         f.write(f"{light_PAR},{biomass},{leaf_area},{LAI:.4f},{light_interception:.4f},{seedling_boost:.2f},{f_temp},{f_nutrient},{P_gross}\n")

#     return max(0, P_gross)


import math

def calculate_photosynthesis(
    light_PAR: float,        # µmol m⁻² s⁻¹
    biomass: float,          # g
    f_temp: float,           # 0–1
    f_nutrient: float,       # 0–1
    water_stress: float = 0.0,  # 0-1 (NEW: for stress down-regulation)
    heat_stress: float = 0.0,   # 0-1 (NEW: for heat stress down-regulation)
    phenological_stage: str = "vegetative",  # (NEW: for germination handling)
    LUE: float = 4e-7,       # g biomass per µmol PAR (realistic)
    leaf_area_ratio: float = 0.004,
    ground_area: float = 0.04,  # m² (plant spacing area)
) -> float:
    """
    Calculate gross hourly photosynthesis (g biomass per hour)
    using Beer-Lambert light interception and realistic LUE.

    NEW: Includes stress-based down-regulation:
    - Heat stress reduces photosynthetic efficiency
    - Water stress reduces photosynthetic efficiency
    - Germination/seed stage has reduced photosynthetic capacity
    """

    # --- 1. Dynamic Leaf Area Ratio (biologically realistic) ---
    # Young plants: high leaf area per gram
    # Mature plants: thicker leaves → lower ratio
    leaf_area_ratio = 0.008 + 0.012 * math.exp(-biomass / 15)
    leaf_area = biomass * leaf_area_ratio  # m² leaf

    # --- 2. Leaf Area Index (LAI) ---
    LAI = leaf_area / ground_area if ground_area > 0 else 0

    # --- 3. Light interception (Beer-Lambert Law) ---
    k = 0.7  # extinction coefficient for leafy crops
    light_interception = 1 - math.exp(-k * LAI)

    # --- 4. Absorbed PAR per hour (µmol) ---
    PAR_absorbed = light_PAR * light_interception * ground_area * 3600

    # --- 5. Stress-based down-regulation of LUE ---
    # Heat stress reduces photosynthetic efficiency
    # High temperatures damage photosystem II and reduce enzyme activity
    heat_stress_factor = 1.0 - (0.7 * heat_stress)  # Up to 70% reduction at max heat stress

    # Water stress reduces photosynthetic efficiency
    # Stomatal closure reduces CO2 uptake
    water_stress_factor = 1.0 - (0.6 * water_stress)  # Up to 60% reduction at max water stress

    # Germination/seed stage has reduced photosynthetic capacity
    # Cotyledons are less efficient than true leaves
    if phenological_stage.lower() in ["seed", "seedling"]:
        germination_factor = 0.5  # 50% efficiency during germination
    else:
        germination_factor = 1.0

    # Combined stress factor
    stress_factor = heat_stress_factor * water_stress_factor * germination_factor
    LUE_effective = LUE * stress_factor

    # --- 6. Gross photosynthesis ---
    P_gross = LUE_effective * PAR_absorbed * f_temp * f_nutrient

    Path('data/records').mkdir(parents=True, exist_ok=True)
    with open('data/records/photosynthesis.txt', 'a') as f:
        f.write(f"{P_gross}, {light_PAR}, {light_interception}, {stress_factor:.3f}\n")

    return max(0.0, P_gross)



def calculate_respiration(
    biomass: float,
    air_temp: float = 23.0,
    r_base: float = 0.000625,  # 0.0625% per hour = 1.5% per day at 20°C
    T_ref: float = 20.0,       # Reference temperature (°C)
    Q10: float = 2.0           # Respiration doubles every 10°C
) -> float:
    """
    Calculate maintenance respiration with Q10 temperature dependence

    R_maint = r_base * biomass * Q10^((T - T_ref) / 10)

    Respiration is the metabolic cost of maintaining living tissue.
    It increases exponentially with temperature (Q10 effect).

    Q10 Effect:
    - At 10°C: respiration = 0.5x baseline (half)
    - At 20°C: respiration = 1.0x baseline (reference)
    - At 30°C: respiration = 2.0x baseline (double)
    - At 40°C: respiration = 4.0x baseline (quadruple)

    This makes heat stress more damaging because plants burn through
    reserves faster at high temperatures.

    IMPORTANT: This is called EVERY HOUR, so r_base must be per-hour rate!
    - Daily respiration: ~1.5% of biomass per day at 20°C
    - Hourly respiration: 1.5% / 24 = 0.0625% per hour = 0.000625

    Args:
        biomass: Current plant biomass (g)
        air_temp: Current air temperature (°C)
        r_base: Base respiration rate at T_ref (fraction/hour, default 0.000625)
        T_ref: Reference temperature (°C, default 20)
        Q10: Temperature coefficient (default 2.0 = doubles every 10°C)

    Returns:
        Maintenance respiration this hour (g)
    """
    # Calculate Q10 temperature factor
    # Q10^((T - T_ref) / 10)
    temp_factor = Q10 ** ((air_temp - T_ref) / 10.0)

    # Temperature-dependent respiration
    R_maint = r_base * biomass * temp_factor
    Path('data/records').mkdir(parents=True, exist_ok=True)
    with open('data/records/respiration.txt', 'a') as f:
        f.write(f"{R_maint}, {biomass}, {air_temp}, {temp_factor:.3f}\n")

    return max(0, R_maint)


def partition_biomass(
    delta_biomass: float,
    biomass: float,
    max_biomass: float,
    leaf_fraction_early: float = 0.50,
    stem_fraction_early: float = 0.30,
    root_fraction_early: float = 0.20,
    leaf_fraction_late: float = 0.30,
    stem_fraction_late: float = 0.40,
    root_fraction_late: float = 0.30
) -> tuple[float, float, float]:
    """
    Partition new biomass into leaf, stem, and root components

    Uses growth strategy to control allocation:
    - Early growth (biomass < 30% of max): Use early fractions
    - Late growth (biomass > 70% of max): Use late fractions
    - Transition zone (30-70%): Linear interpolation

    This allows:
    - Leaf-first strategy: High leaf fraction early (e.g., 80% leaf, 10% stem, 10% root)
    - Structure-first strategy: Balanced allocation (e.g., 50% leaf, 30% stem, 20% root)

    Args:
        delta_biomass: Total new biomass to partition (g)
        biomass: Current total biomass (g)
        max_biomass: Maximum biomass (g)
        leaf_fraction_early: Fraction to leaves in early growth
        stem_fraction_early: Fraction to stem in early growth
        root_fraction_early: Fraction to roots in early growth
        leaf_fraction_late: Fraction to leaves in late growth
        stem_fraction_late: Fraction to stem in late growth
        root_fraction_late: Fraction to roots in late growth

    Returns:
        Tuple of (leaf_biomass, stem_biomass, root_biomass)
    """
    if delta_biomass <= 0:
        return 0.0, 0.0, 0.0

    # Calculate growth stage (0 = early, 1 = late)
    growth_stage = biomass / max_biomass if max_biomass > 0 else 0
    growth_stage = min(1.0, max(0.0, growth_stage))

    # Interpolate fractions based on growth stage
    # Early stage (0-30%): use early fractions
    # Late stage (70-100%): use late fractions
    # Transition (30-70%): linear interpolation
    if growth_stage < 0.3:
        # Early growth
        leaf_frac = leaf_fraction_early
        stem_frac = stem_fraction_early
        root_frac = root_fraction_early
    elif growth_stage > 0.7:
        # Late growth
        leaf_frac = leaf_fraction_late
        stem_frac = stem_fraction_late
        root_frac = root_fraction_late
    else:
        # Transition zone - linear interpolation
        t = (growth_stage - 0.3) / 0.4  # 0 at 30%, 1 at 70%
        leaf_frac = leaf_fraction_early * (1 - t) + leaf_fraction_late * t
        stem_frac = stem_fraction_early * (1 - t) + stem_fraction_late * t
        root_frac = root_fraction_early * (1 - t) + root_fraction_late * t

    # Normalize fractions to sum to 1.0
    total_frac = leaf_frac + stem_frac + root_frac
    if total_frac > 0:
        leaf_frac /= total_frac
        stem_frac /= total_frac
        root_frac /= total_frac

    # Partition biomass
    leaf_biomass = delta_biomass * leaf_frac
    stem_biomass = delta_biomass * stem_frac
    root_biomass = delta_biomass * root_frac

    return leaf_biomass, stem_biomass, root_biomass


def calculate_growth(
    P_gross: float,
    R_maint: float,
    water_stress: float,
    cumulative_damage: float,
    biomass: float = 1.0,
    seed_reserves: float = 0.0,
    hour: int = 0
) -> tuple[float, float]:
    """
    Calculate net biomass growth with stress factors, day/night cycle, and reserve depletion

    NEW FEATURES:
    - Seed reserves buffer against biomass loss when photosynthesis < respiration
    - Reserves deplete slowly before biomass loss occurs
    - Allows low but positive biomass gain if reserves exist
    - Stress reduces RGR proportionally rather than forcing negative growth

    IMPROVED:
    - Gradual stress accumulation (not instant collapse)
    - Biomass-dependent respiration increase under stress
    - Photosynthesis reduction scales with stress severity

    Formulas:
    - P_effective = P_gross * (1 - water_stress) * (1 - damage_factor)
    - R_stress = R_maint * (1 + stress_respiration_factor)
    - net_carbon = P_effective - R_stress
    - If net_carbon < 0 and reserves > 0: deplete reserves first
    - delta_biomass = net_carbon (or buffered by reserves)

    IMPORTANT:
    - P_gross ALREADY includes day/night cycle (calculated with light_PAR)
    - Do NOT apply light_factor again here!
    - Respiration > photosynthesis at night → use reserves or lose biomass

    Args:
        P_gross: Gross photosynthesis this hour (g) - already includes light availability
        R_maint: Maintenance respiration this hour (g)
        water_stress: Water stress factor (0-1, where 1 = maximum stress)
        cumulative_damage: Accumulated damage (%)
        biomass: Current biomass (g) - for biomass-dependent stress
        seed_reserves: Remaining seed energy reserves (g)
        hour: Current simulation hour (for logging/debugging only)

    Returns:
        Tuple of (delta_biomass, reserve_depletion):
        - delta_biomass: Biomass change this hour (g)
        - reserve_depletion: Amount of reserves used this hour (g)
    """
    # Damage factor reduces photosynthetic efficiency
    damage_factor = 0.01 * cumulative_damage
    damage_factor = min(1.0, max(0, damage_factor))

    # IMPROVED: Gradual photosynthesis reduction under stress
    # Use exponential decay instead of linear to prevent instant collapse
    # stress_factor = exp(-2 * water_stress) gives:
    # - 0% stress → 100% photosynthesis
    # - 50% stress → 37% photosynthesis
    # - 100% stress → 14% photosynthesis (not 0%, allows gradual decline)
    import math
    stress_photosynthesis_factor = math.exp(-2 * water_stress)

    # Effective photosynthesis: reduced by water stress and damage
    P_effective = P_gross * stress_photosynthesis_factor * (1 - damage_factor)

    # IMPROVED: Biomass-dependent stress respiration
    # Smaller seedlings lose biomass faster under stress
    # Larger plants can maintain themselves better
    if biomass < 1.0:
        # Small seedlings: 50% increase in respiration under full stress
        stress_respiration_multiplier = 1.0 + 0.5 * water_stress
    elif biomass < 10.0:
        # Medium plants: 30% increase in respiration under full stress
        stress_respiration_multiplier = 1.0 + 0.3 * water_stress
    else:
        # Large plants: 20% increase in respiration under full stress
        stress_respiration_multiplier = 1.0 + 0.2 * water_stress

    R_stress = R_maint * stress_respiration_multiplier

    # Net carbon balance (photosynthesis - respiration)
    # Can be negative at night when P_gross = 0 but R_maint > 0
    net_carbon = P_effective - R_stress

    # NEW: Reserve depletion mechanism
    # If net_carbon is negative, use seed reserves to buffer biomass loss
    reserve_depletion = 0.0
    delta_biomass = net_carbon

    if net_carbon < 0 and seed_reserves > 0:
        # Deficit that needs to be covered
        deficit = abs(net_carbon)

        # Use reserves to cover deficit (up to 80% of deficit)
        # This allows slow reserve depletion rather than immediate biomass loss
        reserve_usage = min(seed_reserves, deficit * 0.8)
        reserve_depletion = reserve_usage

        # Reduce biomass loss by amount covered by reserves
        delta_biomass = net_carbon + reserve_usage

        # If reserves fully cover deficit, allow small positive growth
        # This represents conversion of reserves to structural biomass
        if reserve_usage >= deficit * 0.8:
            # Small positive growth from reserve conversion (10% efficiency)
            delta_biomass = reserve_usage * 0.1

    return delta_biomass, reserve_depletion


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


def calculate_leaf_area_from_biomass(
    leaf_biomass: float,
    SLA: float = 0.020,
    water_stress: float = 0.0,
    heat_stress: float = 0.0,
    previous_leaf_area: float = 0.0
) -> float:
    """
    Calculate leaf area from leaf biomass using Specific Leaf Area (SLA)

    NEW APPROACH: Uses biomass partitioning and SLA instead of fixed LAR
    - Leaf biomass is calculated by partitioning total biomass
    - SLA converts leaf biomass to leaf area
    - Different strategies have different SLA values

    SLA (Specific Leaf Area) = leaf area / leaf biomass (m²/g)
    - Lettuce (thin leaves): SLA ~ 0.025-0.035 m²/g
    - Tomato (thicker leaves): SLA ~ 0.015-0.020 m²/g

    Stress reduces leaf expansion but doesn't shrink existing leaves

    FIX: Reduced stress penalties and added catch-up mechanism
    - Less aggressive stress capping (40% instead of 70% for water)
    - Minimum expansion factor of 0.3 so leaves always grow somewhat
    - Catch-up bonus when stress is low (allows faster recovery)

    Args:
        leaf_biomass: Current leaf biomass (g)
        SLA: Specific Leaf Area (m²/g leaf biomass)
        water_stress: Water stress factor (0-1, where 1 = maximum stress)
        heat_stress: Heat stress factor (0-1, where 1 = maximum stress)
        previous_leaf_area: Leaf area from previous timestep (m²)

    Returns:
        Leaf area (m²)
    """
    # Calculate potential leaf area from leaf biomass
    potential_leaf_area = leaf_biomass * SLA

    # Calculate stress-based expansion factor
    # FIX: Reduced penalties and added minimum expansion
    # Under stress, leaf expansion is reduced but existing leaves remain
    heat_expansion_factor = 1.0 - (0.5 * heat_stress)  # Up to 50% reduction (was 80%)
    water_expansion_factor = 1.0 - (0.4 * water_stress)  # Up to 40% reduction (was 70%)

    combined_expansion_factor = heat_expansion_factor * water_expansion_factor

    # FIX: Minimum expansion factor - leaves always grow at least 30% of potential
    combined_expansion_factor = max(0.3, combined_expansion_factor)

    # FIX: Catch-up mechanism when stress is low
    # If current leaf area is significantly behind potential and stress is low,
    # allow faster expansion to catch up
    if water_stress < 0.1 and heat_stress < 0.1:
        # Low stress: check if we need to catch up
        lag_ratio = previous_leaf_area / potential_leaf_area if potential_leaf_area > 0 else 1.0
        if lag_ratio < 0.8:  # More than 20% behind
            # Bonus expansion to catch up (up to 50% extra)
            catch_up_bonus = (1.0 - lag_ratio) * 0.5
            combined_expansion_factor = min(1.5, combined_expansion_factor + catch_up_bonus)

    # Calculate new leaf area growth
    if potential_leaf_area > previous_leaf_area:
        # Growing: apply stress factor to new growth only
        new_growth = (potential_leaf_area - previous_leaf_area) * combined_expansion_factor
        leaf_area = previous_leaf_area + new_growth
    else:
        # Shrinking (biomass loss): allow leaf area to decrease
        leaf_area = potential_leaf_area

    return max(0, leaf_area)


def update_leaf_area(
    biomass: float,
    leaf_area_ratio: float = 0.004,
    water_stress: float = 0.0,
    heat_stress: float = 0.0,
    previous_leaf_area: float = 0.0
) -> float:
    """
    Update leaf area based on biomass with stress-based expansion capping

    DEPRECATED: Use calculate_leaf_area_from_biomass with SLA instead
    This function is kept for backward compatibility

    NEW: Leaf area expansion is capped under stress conditions:
    - Heat stress reduces leaf expansion rate
    - Water stress reduces leaf expansion rate
    - Existing leaves don't shrink, but new growth is limited

    leaf_area = alpha * biomass * expansion_factor

    Args:
        biomass: Current plant biomass (g)
        leaf_area_ratio: Leaf area per unit biomass (m^2/g, default 0.004)
        water_stress: Water stress factor (0-1, where 1 = maximum stress)
        heat_stress: Heat stress factor (0-1, where 1 = maximum stress)
        previous_leaf_area: Leaf area from previous timestep (m^2)

    Returns:
        Leaf area (m^2)
    """
    # Calculate potential leaf area (no stress)
    potential_leaf_area = leaf_area_ratio * biomass

    # Calculate stress-based expansion factor
    # Under stress, leaf expansion is reduced but existing leaves remain
    heat_expansion_factor = 1.0 - (0.8 * heat_stress)  # Up to 80% reduction
    water_expansion_factor = 1.0 - (0.7 * water_stress)  # Up to 70% reduction

    combined_expansion_factor = heat_expansion_factor * water_expansion_factor

    # Calculate new leaf area growth
    if potential_leaf_area > previous_leaf_area:
        # Growing: apply stress factor to new growth only
        new_growth = (potential_leaf_area - previous_leaf_area) * combined_expansion_factor
        leaf_area = previous_leaf_area + new_growth
    else:
        # Shrinking (biomass loss): allow leaf area to decrease
        leaf_area = potential_leaf_area
        
    Path('data/records').mkdir(parents=True, exist_ok=True)
    with open('data/records/leaf.txt', 'a') as f:
        f.write(f"{biomass},{leaf_area}, {combined_expansion_factor}\n")

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


# def calculate_RGR(
#     biomass: float,
#     delta_biomass: float,
#     dt: float = 1.0
# ) -> float:
#     """
#     Calculate Relative Growth Rate (RGR)

#     RGR = (1/B) · dB/dt

#     This measures the growth rate relative to current size.
#     - High RGR (>0.1/h): Exponential growth phase (small plants)
#     - Medium RGR (0.01-0.1/h): Active growth
#     - Low RGR (<0.01/h): Approaching saturation

#     Args:
#         biomass: Current biomass (g)
#         delta_biomass: Change in biomass this timestep (g)
#         dt: Time step (hours, default 1.0)

#     Returns:
#         RGR in units of 1/hour (per hour)
#     """
#     if biomass <= 0:
#         return 0.0

#     # RGR = (1/B) · (dB/dt)
#     RGR = (delta_biomass / dt) / biomass
    
#     with open('data/records/RGR.txt', 'a') as f:
#         f.write(f"{biomass}, {delta_biomass}, {RGR}\n")

#     # RGR can be negative if plant is losing mass
#     return RGR


def calculate_RGR(
    biomass: float,
    delta_biomass: float,
    hour: int,
    water_stress: float = 0.0,
    soil_water: float = 35.0,
    wilting_point: float = 15.0,
    optimal_min: float = 30.0,
    dt: float = 1.0,
    seedling_boost: float = 0.002,  # g/h, adjustable
    boost_hours: int = 168,         # apply boost for first 168 hours (7 days)
    boost_biomass_threshold: float = 0.2, # apply boost if biomass below this
    plant_boost: int = 168
) -> float:
    """
    Calculate Relative Growth Rate (RGR) with water stress scaling and seedling boost.

    RGR = (1/B) · dB/dt

    IMPROVED:
    - Water stress scaling applied to RGR (gradual decline, not instant collapse)
    - Biomass-dependent vulnerability (smaller seedlings more affected)
    - Seedling boost depends on water availability and decays over time
    - Can reach 0 or negative RGR early for unwatered seedlings

    Args:
        biomass: Current biomass (g)
        delta_biomass: Change in biomass this timestep (g)
        hour: Current simulation hour
        water_stress: Water stress factor (0-1, where 1 = maximum stress)
        soil_water: Current soil water content (%)
        wilting_point: Permanent wilting point (%)
        optimal_min: Lower bound of optimal range (%)
        dt: Time step (hours, default 1.0)
        seedling_boost: Small biomass added per hour for seedlings (g/h)
        boost_hours: Number of hours to apply seedling boost (default 168 = 7 days)
        boost_biomass_threshold: Only apply boost if biomass below this

    Returns:
        RGR in units of 1/hour (per hour) - can be NEGATIVE
    """
    if biomass <= 0:
        return 0.0

    # Apply seedling boost only when water conditions are favorable
    # FIXED: Boost now depends on water availability and decays over time
    boost = 0.0
    if hour < boost_hours and biomass < boost_biomass_threshold:
        # Time decay factor (72-hour half-life)
        # This simulates depletion of seed energy reserves over time
        time_factor = math.exp(-hour / plant_boost)

        # Water factor (no boost under stress)
        # Seedlings can't use energy reserves effectively without water
        water_factor = max(0, 1 - water_stress)

        # Combined boost
        boost = seedling_boost * time_factor * water_factor

    # Total delta including boost
    total_delta = delta_biomass + boost

    # Calculate base RGR
    RGR_base = total_delta / dt / biomass

    # IMPROVED: Apply water stress scaling to RGR
    # This creates gradual decline rather than instant collapse
    # Smaller seedlings are more vulnerable (calculated in water_stress_factor)

    # Calculate biomass-dependent water stress factor
    if soil_water >= optimal_min:
        stress_factor = 0.0
    elif soil_water <= wilting_point:
        stress_factor = 1.0
    else:
        # Base stress from soil water
        base_stress = (optimal_min - soil_water) / (optimal_min - wilting_point)

        # Biomass vulnerability factor
        # Smaller seedlings (< 1g) are MORE vulnerable to stress
        if biomass < 0.5:
            vulnerability = 2.0  # 2x stress multiplier
        elif biomass < 1.0:
            vulnerability = 1.5 + 0.5 * (1.0 - biomass) / 0.5
        elif biomass < 10.0:
            vulnerability = 1.0 + 0.5 * (10.0 - biomass) / 9.0
        else:
            vulnerability = 1.0  # Baseline

        stress_factor = min(1.0, base_stress * vulnerability)

    # Apply stress scaling to RGR
    # Use exponential decay for gradual transition
    # stress_factor = 0 → multiplier = 1.0 (no effect)
    # stress_factor = 0.5 → multiplier = 0.61 (moderate reduction)
    # stress_factor = 1.0 → multiplier = 0.37 (severe reduction, but not 0)
    stress_multiplier = math.exp(-stress_factor)

    # Final RGR with stress scaling
    # FIXED: Use stress_multiplier (exponential decay) instead of subtracting constant
    # This prevents RGR from dropping to 0 as biomass grows
    RGR_actual = RGR_base * stress_multiplier
    
    if stress_factor < 0.2 and biomass < 5: 
        RGR_actual = 0.0015

    Path('data/records').mkdir(parents=True, exist_ok=True)
    with open('data/records/RGR.txt', 'a') as f:
        f.write(f"{hour}, {biomass}, {delta_biomass}, {boost}, {water_stress}, {stress_factor:.3f}, {stress_multiplier:.3f}, {RGR_actual}\n")

    return RGR_actual


def calculate_doubling_time(RGR: float) -> float:
    """
    Calculate doubling time from RGR

    T_d = ln(2) / RGR

    Time it takes for biomass to double at current growth rate.

    Args:
        RGR: Relative Growth Rate (1/h)

    Returns:
        Doubling time in hours (inf if RGR <= 0)
    """
    if RGR <= 0:
        return float('inf')

    # T_d = ln(2) / RGR
    doubling_time = math.log(2) / RGR

    return doubling_time


def calculate_growth_saturation(
    biomass: float,
    max_biomass: float
) -> float:
    """
    Calculate growth saturation factor

    Saturation = B / K

    Where:
    - B = current biomass
    - K = carrying capacity (max_biomass)

    This ratio indicates how close the plant is to its maximum size:
    - 0.0-0.3: Early growth, minimal saturation
    - 0.3-0.7: Active growth, moderate saturation
    - 0.7-1.0: Approaching maximum, high saturation

    Args:
        biomass: Current biomass (g)
        max_biomass: Maximum biomass / carrying capacity (g)

    Returns:
        Saturation factor (0-1)
    """
    if max_biomass <= 0:
        return 1.0

    saturation = biomass / max_biomass
    return min(1.0, max(0.0, saturation))


def apply_logistic_growth_factor(
    delta_biomass: float,
    biomass: float,
    max_biomass: float
) -> float:
    """
    Apply logistic growth constraint to biomass change (LEAF_FIRST strategy)

    Logistic growth: dB/dt = r·B·(1 - B/K)

    Where:
    - r = intrinsic growth rate
    - B = current biomass
    - K = carrying capacity (max_biomass)
    - (1 - B/K) = saturation factor

    Early on (B << K): factor ≈ 1, exponential growth
    Near max (B → K): factor → 0, growth slows

    This prevents unrealistic exponential growth as plants approach
    their genetic maximum size.

    Args:
        delta_biomass: Unconstrained biomass change (g)
        biomass: Current biomass (g)
        max_biomass: Maximum biomass / carrying capacity (g)

    Returns:
        Constrained biomass change (g)
    """
    if max_biomass <= 0:
        return 0.0

    # Calculate saturation factor: (1 - B/K)
    saturation_factor = 1.0 - (biomass / max_biomass)
    saturation_factor = max(0.0, min(1.0, saturation_factor))

    # Apply logistic constraint
    # When B is small: saturation_factor ≈ 1 → full growth
    # When B → K: saturation_factor → 0 → growth stops
    constrained_delta = delta_biomass * saturation_factor

    return constrained_delta


def apply_structure_first_growth_factor(
    delta_biomass: float,
    biomass: float,
    max_biomass: float,
    hour: int,
    root_development_hours: int = 336  # 2 weeks
) -> float:
    """
    Apply delayed sigmoid growth constraint for STRUCTURE_FIRST strategy (e.g., tomato)

    Growth pattern:
    - Weeks 1-2 (0-336h): Moderate visible growth (energy → root development)
      - Growth suppressed to 50-70% of potential
      - Biomass reaches ~8-10g by end of week 2
    - Weeks 3-5 (336-840h): Rapid compensatory growth (vegetative/fruiting)
      - Growth accelerates significantly
      - Can reach ~200g by week 4-5
    - After week 5: Approaches max biomass with logistic saturation

    This models the biological reality where structure-first plants invest
    heavily in root systems early, then explode in above-ground growth later.

    Args:
        delta_biomass: Unconstrained biomass change (g)
        biomass: Current biomass (g)
        max_biomass: Maximum biomass / carrying capacity (g)
        hour: Current simulation hour
        root_development_hours: Hours of root development phase (default 336 = 2 weeks)

    Returns:
        Constrained biomass change (g)
    """
    if max_biomass <= 0:
        return 0.0

    # Phase 1: Root development (weeks 1-2)
    # Suppress visible biomass gain - energy goes to roots
    if hour < root_development_hours:
        # Gradual increase from 0.5 to 0.7 over the 2 weeks
        # This allows more visible growth (~8-10g by end of week 2)
        # Previous: 0.3 → 0.5 was too aggressive, causing unrealistic slow growth
        phase_progress = hour / root_development_hours
        early_suppression = 0.5 + 0.2 * phase_progress  # 0.5 → 0.7

        # Also apply logistic saturation
        saturation_factor = 1.0 - (biomass / max_biomass)
        saturation_factor = max(0.0, min(1.0, saturation_factor))

        return delta_biomass * early_suppression * saturation_factor

    # Phase 2: Rapid compensatory growth (weeks 3-6)
    # Plants "catch up" after root establishment
    # This phase models the explosive above-ground growth after roots are established
    rapid_growth_end = root_development_hours + 672  # 4 more weeks (672h) for sustained growth

    if hour < rapid_growth_end:
        # Calculate progress through rapid growth phase (0 → 1)
        rapid_progress = (hour - root_development_hours) / 672  # 4 weeks duration

        # IMPROVED: Plateau boost with sustained high growth for weeks 3-4
        # Use trapezoidal shape: ramp up quickly, sustain, then gradual decline
        # This enables reaching 100-200g by weeks 4-5

        if rapid_progress < 0.10:
            # Early ramp-up (first few days of week 3)
            boost = 3.0 + 4.0 * (rapid_progress / 0.10)  # 3.0 → 7.0
        elif rapid_progress < 0.75:
            # Sustained very high boost (weeks 3-5)
            # This is the critical window for rapid biomass accumulation
            # Structure-first plants need aggressive catch-up growth
            boost = 7.0  # Maximum sustained boost for explosive growth
        elif rapid_progress < 0.90:
            # Gradual decline (late week 5, week 6)
            decline_progress = (rapid_progress - 0.75) / 0.15
            boost = 7.0 - 3.5 * decline_progress  # 7.0 → 3.5
        else:
            # Transition to normal growth (end of rapid phase)
            final_progress = (rapid_progress - 0.90) / 0.10
            boost = 3.5 - 1.5 * final_progress  # 3.5 → 2.0

        # Additional boost from accumulated biomass (positive feedback)
        # Larger plants with more leaf area generate more photosynthate
        # This creates the exponential-like growth characteristic of tomato
        if biomass > 10.0:
            # Biomass-driven acceleration (up to +2.0 bonus for very large plants)
            biomass_boost = min(2.0, (biomass - 10.0) / 30.0)
            boost += biomass_boost

        # Apply logistic saturation (very soft during rapid phase)
        saturation_factor = 1.0 - (biomass / max_biomass)
        saturation_factor = max(0.0, min(1.0, saturation_factor))

        # IMPROVED: Minimal saturation penalty during rapid growth phase
        # Structure-first plants need to catch up, so don't penalize heavily
        if saturation_factor > 0.6:
            # Far from max (< 40% of max): essentially no penalty
            saturation_factor = 0.98
        elif saturation_factor > 0.3:
            # Medium distance (30-60% of max): gradual penalty
            saturation_factor = 0.85 + 0.13 * ((saturation_factor - 0.3) / 0.3)
        # Below 30% of max, use actual saturation factor

        # CRITICAL FIX: Only apply boost to POSITIVE growth
        # At night, delta_biomass is negative (respiration > 0, photosynthesis = 0)
        # Boosting negative values would amplify losses, which is wrong
        if delta_biomass > 0:
            return delta_biomass * boost * saturation_factor
        else:
            # Negative delta (night losses) - return as-is without boost
            # Optionally reduce night losses slightly for structure-first plants
            # (their established root systems help maintain biomass)
            return delta_biomass * 0.7  # 30% reduced night losses

    # Phase 3: Normal logistic growth (after week 5)
    # Standard saturation as plant approaches max biomass
    saturation_factor = 1.0 - (biomass / max_biomass)
    saturation_factor = max(0.0, min(1.0, saturation_factor))

    return delta_biomass * saturation_factor


def calculate_strategy_growth_modifier(
    growth_strategy: str,
    delta_biomass: float,
    biomass: float,
    max_biomass: float,
    hour: int
) -> float:
    """
    Apply growth strategy-specific constraints to biomass change

    Unified function that applies the appropriate growth curve based on strategy.
    Both strategies use the same function signature but different internal logic.

    LEAF_FIRST (e.g., lettuce):
    - Standard logistic growth
    - Fast early biomass accumulation
    - Visible growth matches actual growth

    STRUCTURE_FIRST (e.g., tomato):
    - Delayed sigmoid growth
    - Slow early growth (root development phase)
    - Rapid compensatory growth after week 2

    Args:
        growth_strategy: "leaf_first" or "structure_first"
        delta_biomass: Unconstrained biomass change (g)
        biomass: Current biomass (g)
        max_biomass: Maximum biomass / carrying capacity (g)
        hour: Current simulation hour

    Returns:
        Strategy-adjusted biomass change (g)
    """
    if growth_strategy == "leaf_first":
        return apply_logistic_growth_factor(delta_biomass, biomass, max_biomass)
    elif growth_strategy == "structure_first":
        return apply_structure_first_growth_factor(
            delta_biomass, biomass, max_biomass, hour
        )
    else:
        # Default to logistic if unknown strategy
        return apply_logistic_growth_factor(delta_biomass, biomass, max_biomass)


def calculate_root_water_efficiency(
    root_biomass: float,
    total_biomass: float,
    soil_water: float,
    wilting_point: float,
    optimal_min: float
) -> float:
    """
    Calculate root-based water uptake efficiency bonus

    Plants with higher root fraction can extract water more efficiently,
    especially from drier soil. This benefits STRUCTURE_FIRST plants
    that invest heavily in root development.

    Mechanism:
    - Root fraction > 0.15: Better water extraction from dry soil
    - Root fraction > 0.25: Significantly better drought tolerance
    - Effect strongest when soil water is between wilting point and optimal

    Args:
        root_biomass: Current root biomass (g)
        total_biomass: Current total biomass (g)
        soil_water: Current soil water content (%)
        wilting_point: Permanent wilting point (%)
        optimal_min: Lower bound of optimal range (%)

    Returns:
        Water efficiency multiplier (1.0 - 1.5)
        1.0 = no bonus, 1.5 = 50% better water extraction
    """
    if total_biomass <= 0:
        return 1.0

    root_fraction = root_biomass / total_biomass

    # Base efficiency (no bonus below 15% root fraction)
    if root_fraction <= 0.15:
        return 1.0

    # Calculate root bonus (0 → 0.5 as root fraction goes 0.15 → 0.35)
    # Higher root fraction = better water extraction
    root_bonus = min(0.5, (root_fraction - 0.15) / 0.20 * 0.5)

    # Bonus is most effective in dry soil (between wilting and optimal)
    # When soil is wet, roots don't provide much advantage
    if soil_water >= optimal_min:
        # Wet soil: minimal root advantage
        soil_factor = 0.2
    elif soil_water <= wilting_point:
        # Very dry: roots help but limited by physics
        soil_factor = 0.8
    else:
        # Dry but not critical: roots provide maximum advantage
        # Linear interpolation
        dryness = (optimal_min - soil_water) / (optimal_min - wilting_point)
        soil_factor = 0.2 + 0.6 * dryness

    efficiency = 1.0 + root_bonus * soil_factor

    return efficiency

def increase_leaf_area(
    previous_leaf_area: float,
    leaf_biomass: float,
    SLA: float = 0.017,
    water_stress: float = 0.0,
    heat_stress: float = 0.0,
    hours_since_emergence: int = 0,
    biomass: float = 0.0,
) -> float:
    """
    Increase leaf area for tomato (m²).
    - SLA: m² leaf per g leaf biomass (tomato ~0.015-0.02)
    - Early tomato (structure-first) suppresses leaf expansion until ~2 weeks or biomass >= 2 g
    - Simple stress penalties, minimum expansion, small catch-up when low stress
    - Caps relative hourly growth to avoid runaway LAR

    Returns new_leaf_area (m²).
    """
    # potential area from current leaf biomass
    potential = max(0.0, leaf_biomass * SLA)

    # stress-driven expansion factors (reduced penalties for realism)
    heat_factor = 1.0 - 0.5 * max(0.0, min(1.0, heat_stress))
    water_factor = 1.0 - 0.4 * max(0.0, min(1.0, water_stress))
    combined = heat_factor * water_factor
    combined = max(0.3, combined)  # always allow some expansion

    # suppress early leaf expansion for structure-first tomato
    early_threshold_h = 14 * 24  # 14 days
    if hours_since_emergence < early_threshold_h and biomass < 2.0:
        combined *= 0.5  # slower leaf expansion early

    # catch-up bonus when low stress and leaf area lags behind potential
    if water_stress < 0.1 and heat_stress < 0.1 and potential > 0:
        lag = previous_leaf_area / potential
        if lag < 0.9:
            catch_up = (1.0 - lag) * 0.4  # up to +40% bonus
            combined = min(1.5, combined + catch_up)

    # compute desired new area (apply stress only to new growth)
    if potential > previous_leaf_area:
        growth = (potential - previous_leaf_area) * combined
        desired = previous_leaf_area + growth
    else:
        # biomass loss -> shrink to potential
        desired = potential

    # cap relative hourly increase to prevent spikes (e.g., max 2% per hour)
    max_rel_increase = 0.02
    if previous_leaf_area > 1e-8:
        rel = (desired - previous_leaf_area) / previous_leaf_area
        if rel > max_rel_increase:
            desired = previous_leaf_area * (1.0 + max_rel_increase)

    # never exceed the potential area
    new_area = min(desired, potential)
    return max(0.0, new_area)

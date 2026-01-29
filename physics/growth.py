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
    LUE: float = 4e-7,       # g biomass per µmol PAR (realistic)
    leaf_area_ratio: float = 0.004,
    ground_area: float = 0.04,  # m² (plant spacing area)
) -> float:
    """
    Calculate gross hourly photosynthesis (g biomass per hour)
    using Beer-Lambert light interception and realistic LUE.
    """

    # --- 1. Dynamic Leaf Area Ratio (biologically realistic) ---
    # Young plants: high leaf area per gram
    # Mature plants: thicker leaves → lower ratio
    # if biomass < 5:
    #     leaf_area_ratio = 0.02   # m²/g (seedling)
    # elif biomass < 50:
    #     leaf_area_ratio = 0.012  # vegetative
    # else:
    #     leaf_area_ratio = 0.008  # mature lettuce

    # leaf_area = biomass * leaf_area_ratio  # m² leaf
    
    leaf_area_ratio = 0.008 + 0.012 * math.exp(-biomass / 15)

    leaf_area = biomass * leaf_area_ratio  # m² leaf

    # --- 2. Leaf Area Index (LAI) ---
    LAI = leaf_area / ground_area if ground_area > 0 else 0

    # --- 3. Light interception (Beer-Lambert Law) ---
    k = 0.7  # extinction coefficient for leafy crops
    light_interception = 1 - math.exp(-k * LAI)

    # --- 4. Absorbed PAR per hour (µmol) ---
    PAR_absorbed = light_PAR * light_interception * ground_area * 3600

    # --- 5. Gross photosynthesis ---
    P_gross = LUE * PAR_absorbed * f_temp * f_nutrient
    with open('data/records/photosynthesis.txt', 'a') as f:
        f.write(f"{P_gross}, {light_PAR}, {light_interception}")

    return max(0.0, P_gross)



def calculate_respiration(
    biomass: float,
    r_base: float = 0.000625  # 0.0625% per hour = 1.5% per day
) -> float:
    """
    Calculate maintenance respiration

    R_maint = r_base * biomass

    Respiration is the metabolic cost of maintaining living tissue.

    IMPORTANT: This is called EVERY HOUR, so r_base must be per-hour rate!
    - Daily respiration: ~1.5% of biomass per day
    - Hourly respiration: 1.5% / 24 = 0.0625% per hour = 0.000625

    Args:
        biomass: Current plant biomass (g)
        r_base: Base respiration rate (fraction/hour, default 0.000625 = 0.0625%/h = 1.5%/day)

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
    dt: float = 1.0,
    seedling_boost: float = 0.002,  # g/h, adjustable
    boost_hours: int = 24,          # apply boost for first 24 hours
    boost_biomass_threshold: float = 0.2  # apply boost if biomass below this
) -> float:
    """
    Calculate Relative Growth Rate (RGR) with optional seedling boost.

    RGR = (1/B) · dB/dt

    Args:
        biomass: Current biomass (g)
        delta_biomass: Change in biomass this timestep (g)
        hour: Current simulation hour
        dt: Time step (hours, default 1.0)
        seedling_boost: Small biomass added per hour for seedlings (g/h)
        boost_hours: Number of hours to apply seedling boost
        boost_biomass_threshold: Only apply boost if biomass below this

    Returns:
        RGR in units of 1/hour (per hour)
    """
    if biomass <= 0:
        return 0.0

    # Apply seedling boost under defined conditions
    boost = 0.0
    if hour < boost_hours and biomass < boost_biomass_threshold:
        boost = seedling_boost

    # Total delta including boost
    total_delta = delta_biomass + boost

    # Calculate RGR
    RGR = total_delta / dt / biomass

    # Log for debugging
    with open('data/records/RGR.txt', 'a') as f:
        f.write(f"{hour}, {biomass}, {delta_biomass}, {boost}, {RGR}\n")

    return RGR


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
    Apply logistic growth constraint to biomass change

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

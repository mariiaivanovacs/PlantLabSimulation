"""
CO2 Physics
Handles carbon dioxide dynamics in the controlled environment

CO2 is consumed during photosynthesis and produced during respiration.
Natural outdoor CO2 levels are ~400 ppm. Controlled environments can
maintain higher levels (800-1500 ppm) for enhanced growth.
"""
from typing import Tuple


# Constants
AMBIENT_CO2_PPM = 400.0  # Outdoor/natural CO2 level
OPTIMAL_CO2_MIN = 800.0  # Optimal range for plant growth
OPTIMAL_CO2_MAX = 1200.0
MAX_CO2_PPM = 2000.0  # Above this, can be harmful
MIN_CO2_PPM = 150.0  # Below this, photosynthesis stops


def calculate_co2_consumption(
    photosynthesis_rate: float,
    conversion_factor: float = 1.83
) -> float:
    """
    Calculate CO2 consumed by photosynthesis

    Plants consume CO2 during photosynthesis to produce glucose.
    Stoichiometry: 6CO2 + 6H2O -> C6H12O6 + 6O2

    For every gram of glucose (biomass), ~1.47g of CO2 is consumed.
    With inefficiencies, use ~1.83g CO2 per g biomass.

    Args:
        photosynthesis_rate: Gross photosynthesis (g/h of biomass produced)
        conversion_factor: g CO2 consumed per g biomass (default 1.83)

    Returns:
        CO2 consumption rate in g/h
    """
    co2_consumed = photosynthesis_rate * conversion_factor
    # with open('data/records/co2_consumption.txt', 'a') as f:
    #     f.write(f"{co2_consumed}\n")
    return max(0, co2_consumed)


def calculate_co2_production(
    respiration_rate: float,
    conversion_factor: float = 1.47
) -> float:
    """
    Calculate CO2 produced by plant respiration

    Plants respire 24/7, producing CO2 as they break down glucose
    for energy. This is the reverse of photosynthesis.

    Args:
        respiration_rate: Maintenance respiration (g/h of biomass consumed)
        conversion_factor: g CO2 produced per g biomass respired (default 1.47)

    Returns:
        CO2 production rate in g/h
    """
    co2_produced = respiration_rate * conversion_factor
    return max(0, co2_produced)


def co2_grams_to_ppm(
    co2_grams: float,
    room_volume_m3: float,
    temperature_c: float = 25.0
) -> float:
    """
    Convert CO2 mass to concentration in ppm

    Uses ideal gas law approximation.
    At 25°C, 1 mole CO2 (44g) occupies ~24.5L

    Args:
        co2_grams: Mass of CO2 in grams
        room_volume_m3: Room volume in cubic meters
        temperature_c: Temperature in Celsius (affects gas volume)

    Returns:
        CO2 concentration change in ppm
    """
    if room_volume_m3 <= 0:
        return 0.0

    # Molar volume at temperature (L/mol)
    molar_volume = 22.4 * (273.15 + temperature_c) / 273.15

    # Moles of CO2
    moles_co2 = co2_grams / 44.0  # MW of CO2 = 44 g/mol

    # Volume of CO2 in liters
    volume_co2_L = moles_co2 * molar_volume

    # Room volume in liters
    room_volume_L = room_volume_m3 * 1000

    # ppm = (volume CO2 / total volume) * 1,000,000
    ppm = (volume_co2_L / room_volume_L) * 1_000_000
    
    # with open('data/records/co2_grams_to_ppm.txt', 'a') as f:
    #     f.write(f"{co2_grams}, {room_volume_m3}, {temperature_c}, {ppm}\n")

    return ppm


def ppm_to_co2_grams(
    ppm: float,
    room_volume_m3: float,
    temperature_c: float = 25.0
) -> float:
    """
    Convert CO2 concentration (ppm) to mass (grams)

    Args:
        ppm: CO2 concentration in ppm
        room_volume_m3: Room volume in cubic meters
        temperature_c: Temperature in Celsius

    Returns:
        CO2 mass in grams
    """
    if room_volume_m3 <= 0:
        return 0.0

    # Molar volume at temperature (L/mol)
    molar_volume = 22.4 * (273.15 + temperature_c) / 273.15

    # Room volume in liters
    room_volume_L = room_volume_m3 * 1000

    # Volume of CO2 in liters
    volume_co2_L = (ppm / 1_000_000) * room_volume_L

    # Moles of CO2
    moles_co2 = volume_co2_L / molar_volume

    # Mass in grams
    co2_grams = moles_co2 * 44.0

    return co2_grams


def update_room_co2(
    current_co2_ppm: float,
    photosynthesis_rate: float,
    respiration_rate: float,
    room_volume_m3: float,
    air_temp: float,
    ventilation_rate: float = 0.0,
    co2_injection_g: float = 0.0,
    ambient_co2_ppm: float = AMBIENT_CO2_PPM
) -> Tuple[float, dict]:
    """
    Update room CO2 level for one hour

    CO2 balance:
    new_CO2 = current + production - consumption + injection - ventilation_loss + ventilation_gain

    Args:
        current_co2_ppm: Current CO2 level (ppm)
        photosynthesis_rate: Gross photosynthesis this hour (g biomass)
        respiration_rate: Respiration this hour (g biomass)
        room_volume_m3: Room volume (m³)
        air_temp: Air temperature (°C)
        ventilation_rate: Air exchange rate (0-1, fraction replaced per hour)
        co2_injection_g: CO2 added by enrichment system (g)
        ambient_co2_ppm: Outside CO2 level (ppm)

    Returns:
        Tuple of (new_co2_ppm, co2_fluxes)
        - new_co2_ppm: Updated CO2 level
        - co2_fluxes: Dict with production, consumption, etc. in ppm
    """
    # Calculate CO2 fluxes in grams
    co2_consumed_g = calculate_co2_consumption(photosynthesis_rate)
    co2_produced_g = calculate_co2_production(respiration_rate)

    # Convert to ppm changes
    consumption_ppm = co2_grams_to_ppm(co2_consumed_g, room_volume_m3, air_temp)
    production_ppm = co2_grams_to_ppm(co2_produced_g, room_volume_m3, air_temp)
    injection_ppm = co2_grams_to_ppm(co2_injection_g, room_volume_m3, air_temp)

    # Ventilation exchanges air with outside
    # CO2 moves toward ambient level proportional to ventilation rate
    ventilation_exchange_ppm = ventilation_rate * (ambient_co2_ppm - current_co2_ppm)

    # Natural air leakage (small baseline exchange even without ventilation)
    natural_leakage_rate = 0.02  # 2% per hour baseline
    leakage_ppm = natural_leakage_rate * (ambient_co2_ppm - current_co2_ppm)

    # Net change
    net_change = production_ppm - consumption_ppm + injection_ppm + ventilation_exchange_ppm + leakage_ppm

    # Update CO2 level
    new_co2_ppm = current_co2_ppm + net_change

    # Clamp to physical limits
    new_co2_ppm = max(MIN_CO2_PPM, min(MAX_CO2_PPM, new_co2_ppm))

    # Return fluxes for logging
    co2_fluxes = {
        'production_ppm': production_ppm,
        'consumption_ppm': consumption_ppm,
        'injection_ppm': injection_ppm,
        'ventilation_ppm': ventilation_exchange_ppm,
        'leakage_ppm': leakage_ppm,
        'net_change_ppm': net_change
    }

    return new_co2_ppm, co2_fluxes


def calculate_co2_growth_factor(
    co2_ppm: float,
    optimal_min: float = OPTIMAL_CO2_MIN,
    optimal_max: float = OPTIMAL_CO2_MAX
) -> float:
    """
    Calculate growth enhancement factor from CO2 level

    CO2 above ambient enhances photosynthesis up to saturation.
    - Below 150 ppm: No photosynthesis
    - 150-400 ppm: Reduced photosynthesis
    - 400-800 ppm: Normal (factor = 1.0)
    - 800-1200 ppm: Enhanced (up to 1.3x)
    - Above 1200 ppm: Saturated (no additional benefit)

    Args:
        co2_ppm: Current CO2 level (ppm)
        optimal_min: Start of optimal range (default 800)
        optimal_max: End of optimal range (default 1200)

    Returns:
        CO2 growth factor (0-1.3)
    """
    if co2_ppm < MIN_CO2_PPM:
        # No photosynthesis possible
        return 0.0
    elif co2_ppm < AMBIENT_CO2_PPM:
        # Below ambient - reduced photosynthesis
        # Linear from 0 at 150ppm to 1.0 at 400ppm
        return (co2_ppm - MIN_CO2_PPM) / (AMBIENT_CO2_PPM - MIN_CO2_PPM)
    elif co2_ppm < optimal_min:
        # Normal range - factor = 1.0
        return 1.0
    elif co2_ppm <= optimal_max:
        # Enhanced range - linear increase up to 1.3
        enhancement = 0.3 * (co2_ppm - optimal_min) / (optimal_max - optimal_min)
        return 1.0 + enhancement
    else:
        # Saturated - max benefit
        return 1.3


def calculate_co2_stress(
    co2_ppm: float,
    stress_threshold_low: float = 200.0,
    stress_threshold_high: float = 1800.0
) -> float:
    """
    Calculate CO2-related stress

    Plants experience stress at very low or very high CO2 levels.

    Args:
        co2_ppm: Current CO2 level (ppm)
        stress_threshold_low: Below this, increasing stress
        stress_threshold_high: Above this, increasing stress

    Returns:
        CO2 stress factor (0-1)
    """
    if co2_ppm < stress_threshold_low:
        # Low CO2 stress
        stress = (stress_threshold_low - co2_ppm) / stress_threshold_low
        return min(1.0, stress)
    elif co2_ppm > stress_threshold_high:
        # High CO2 stress (less severe)
        excess = co2_ppm - stress_threshold_high
        stress = excess / 500  # Takes 500ppm above threshold to reach full stress
        return min(1.0, stress * 0.5)  # High CO2 stress is less severe
    else:
        return 0.0

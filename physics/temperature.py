"""
Temperature Response Physics
Handles cardinal temperature model, thermal time accumulation, and temperature stress

Equations from plant_simulator_focused_implementation.pdf Section 4.4-4.5
"""


def calculate_temperature_response(
    temperature: float,
    T_min: float,
    T_opt: float,
    T_max: float
) -> float:
    """
    Calculate temperature response factor using cardinal temperature model

    Uses quadratic approximation for growth response to temperature.
    Growth is:
    - Zero below T_min or above T_max
    - Maximum (1.0) at T_opt
    - Varies quadratically between these points

    Args:
        temperature: Current temperature (C)
        T_min: Minimum temperature for growth (C)
        T_opt: Optimal temperature (C)
        T_max: Maximum temperature for growth (C)

    Returns:
        Temperature response factor (0-1)
    """
    if temperature < T_min or temperature > T_max:
        # No growth outside cardinal range
        return 0.0

    if T_min <= temperature <= T_opt:
        # Rising limb (below optimal)
        if T_opt == T_min:
            return 1.0
        f_temp = ((temperature - T_min) / (T_opt - T_min)) ** 2
    else:
        # Falling limb (above optimal)
        if T_max == T_opt:
            return 1.0
        f_temp = ((T_max - temperature) / (T_max - T_opt)) ** 2

    return max(0, min(1, f_temp))


def calculate_temperature_response_beta(
    temperature: float,
    T_min: float,
    T_opt: float,
    T_max: float,
    alpha: float = 2.0,
    beta: float = 2.0
) -> float:
    """
    Calculate temperature response using beta-like function (more realistic)

    f_temp = ((T - T_min)/(T_opt - T_min))^alpha * ((T_max - T)/(T_max - T_opt))^beta

    Args:
        temperature: Current temperature (C)
        T_min: Minimum temperature for growth (C)
        T_opt: Optimal temperature (C)
        T_max: Maximum temperature for growth (C)
        alpha: Shape parameter for rising limb (default 2.0)
        beta: Shape parameter for falling limb (default 2.0)

    Returns:
        Temperature response factor (0-1)
    """
    if temperature <= T_min or temperature >= T_max:
        return 0.0

    if T_opt == T_min or T_max == T_opt:
        return 0.0

    try:
        term1 = ((temperature - T_min) / (T_opt - T_min)) ** alpha
        term2 = ((T_max - temperature) / (T_max - T_opt)) ** beta
        f_temp = term1 * term2

        # Normalize so maximum is 1.0 (occurs at T_opt for alpha=beta)
        max_response = 1.0  # For alpha=beta=2, max is at T_opt
        return max(0, min(1, f_temp / max_response))
    except (ValueError, ZeroDivisionError):
        return 0.0


# def calculate_thermal_time(
#     air_temp: float,
#     soil_temp: float,
#     T_base: float,
#     current_thermal_time: float
# ) -> float:
#     """
#     Calculate accumulated thermal time (Growing Degree Hours)

#     Thermal time is used to track phenological development.
#     GDD accumulates hourly based on average temperature.

#     GDD = max(0, (air_temp + soil_temp)/2 - T_base)

#     Args:
#         air_temp: Air temperature (C)
#         soil_temp: Soil temperature (C)
#         T_base: Base temperature (C) - no development below this
#         current_thermal_time: Current accumulated thermal time (C*h)

#     Returns:
#         Updated thermal time (C*h)
#     """
#     # Average of air and soil temperature
#     T_avg = (air_temp + soil_temp) / 2

#     # GDD for this hour (only accumulates above base temperature)
#     GDD_hour = max(0, T_avg - T_base)

#     # Accumulate
#     new_thermal_time = current_thermal_time + GDD_hour

#     return new_thermal_time



def calculate_thermal_time(
    air_temp: float,
    soil_temp: float,
    current_thermal_time: float,
    T_base: float = 5.0,
    T_opt: float = 25.0,
    air_weight: float = 0.7,
    soil_weight: float = 0.3
) -> float:
    """
    Calculate accumulated thermal time (Growing Degree Hours) for crop development.

    Thermal time tracks phenological development.
    GDD accumulates hourly based on temperature, with optional air/soil weighting 
    and heat cap for upper temperature limits.

    Formula:
        T_avg = air_weight * air_temp + soil_weight * soil_temp
        T_avg_capped = min(T_avg, T_opt)
        GDD_hour = max(0, T_avg_capped - T_base)
        new_thermal_time = current_thermal_time + GDD_hour

    Args:
        air_temp (float): Air temperature in °C
        soil_temp (float): Soil temperature in °C
        current_thermal_time (float): Current accumulated thermal time (°C·h)
        T_base (float, optional): Base temperature below which no development occurs. Default 5°C for lettuce
        T_opt (float, optional): Optimal temperature cap for development. Above this, growth slows. Default 25°C for lettuce
        air_weight (float, optional): Weight of air temperature in averaging (0-1). Default 0.7
        soil_weight (float, optional): Weight of soil temperature in averaging (0-1). Default 0.3

    Returns:
        float: Updated thermal time (°C·h)
    """
    # Weighted average temperature
    T_avg = air_weight * air_temp + soil_weight * soil_temp

    # Apply upper temperature cap
    T_capped = min(T_avg, T_opt)

    # Hourly GDD
    GDD_hour = max(0, T_capped - T_base)

    # Accumulate thermal time
    new_thermal_time = current_thermal_time + GDD_hour

    return new_thermal_time

def calculate_temperature_stress(
    air_temp: float,
    T_min: float,
    T_opt: float,
    T_max: float
) -> float:
    """
    Calculate temperature stress factor (0 = no stress, 1 = maximum stress)

    Stress is inversely related to growth response.
    Stress is high when temperature is far from optimal.

    Args:
        air_temp: Air temperature (C)
        T_min: Minimum temperature for growth (C)
        T_opt: Optimal temperature (C)
        T_max: Maximum temperature for growth (C)

    Returns:
        Temperature stress factor (0-1)
    """
    if air_temp < T_min or air_temp > T_max:
        # Complete stress outside cardinal range
        return 1.0

    if air_temp <= T_opt:
        # Below optimal - stress decreases as temp approaches optimal
        if T_opt == T_min:
            return 0.0
        stress = 1 - ((air_temp - T_min) / (T_opt - T_min))
    else:
        # Above optimal - stress increases as temp moves away from optimal
        if T_max == T_opt:
            return 0.0
        stress = (air_temp - T_opt) / (T_max - T_opt)

    return max(0, min(1, stress))


def update_soil_temperature(
    soil_temp: float,
    air_temp: float,
    coupling_factor: float = 0.2
) -> float:
    """
    Update soil temperature (lags behind air temperature)

    Soil temperature changes more slowly than air due to thermal mass.

    Args:
        soil_temp: Current soil temperature (C)
        air_temp: Current air temperature (C)
        coupling_factor: How quickly soil responds to air temp (default 0.2)

    Returns:
        Updated soil temperature (C)
    """
    # Soil temperature moves toward air temperature
    temp_diff = air_temp - soil_temp
    new_soil_temp = soil_temp + coupling_factor * temp_diff

    return new_soil_temp

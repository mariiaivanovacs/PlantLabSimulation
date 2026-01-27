"""
Nutrient Uptake & Depletion Physics
Handles nutrient consumption, soil depletion, and EC calculation

Equations from plant_simulator_focused_implementation.pdf Section 4.3
"""
from typing import Tuple


def calculate_nutrient_uptake(
    delta_biomass: float,
    N_ratio: float,
    P_ratio: float,
    K_ratio: float
) -> Tuple[float, float, float]:
    """
    Calculate nutrient uptake proportional to growth

    Plants consume nutrients in fixed ratios as they grow.
    uptake_X = delta_biomass * X_demand_ratio

    Args:
        delta_biomass: Biomass growth this hour (g)
        N_ratio: Nitrogen demand ratio (g N / g biomass, e.g., 0.03)
        P_ratio: Phosphorus demand ratio (g P / g biomass, e.g., 0.005)
        K_ratio: Potassium demand ratio (g K / g biomass, e.g., 0.02)

    Returns:
        Tuple of (uptake_N, uptake_P, uptake_K) in g
    """
    uptake_N = delta_biomass * N_ratio
    uptake_P = delta_biomass * P_ratio
    uptake_K = delta_biomass * K_ratio

    return max(0, uptake_N), max(0, uptake_P), max(0, uptake_K)


def update_soil_nutrients(
    soil_N: float,
    soil_P: float,
    soil_K: float,
    uptake_N: float,
    uptake_P: float,
    uptake_K: float
) -> Tuple[float, float, float]:
    """
    Update soil nutrient levels after plant uptake

    Args:
        soil_N: Current soil nitrogen (ppm)
        soil_P: Current soil phosphorus (ppm)
        soil_K: Current soil potassium (ppm)
        uptake_N: Nitrogen taken up (g, converted to ppm equivalent)
        uptake_P: Phosphorus taken up (g, converted to ppm equivalent)
        uptake_K: Potassium taken up (g, converted to ppm equivalent)

    Returns:
        Tuple of (new_soil_N, new_soil_P, new_soil_K) in ppm
    """
    # Note: In a real system, we'd convert g to ppm based on soil volume
    # For simplicity, we treat uptake values as ppm-equivalent depletion
    # This is a simplification - actual conversion depends on soil mass/volume

    # Scale factor to convert uptake (g) to ppm depletion
    # Calibrated so nutrients deplete over ~2-3 weeks of growth
    # With ~5L pot, ~5kg soil, and typical growth rates
    UPTAKE_TO_PPM = 5.0

    new_soil_N = soil_N - (uptake_N * UPTAKE_TO_PPM)
    new_soil_P = soil_P - (uptake_P * UPTAKE_TO_PPM)
    new_soil_K = soil_K - (uptake_K * UPTAKE_TO_PPM)

    # Clamp to >= 0
    return max(0, new_soil_N), max(0, new_soil_P), max(0, new_soil_K)


def calculate_nutrient_stress(
    soil_N: float,
    soil_P: float,
    soil_K: float,
    optimal_N: float,
    optimal_P: float,
    optimal_K: float
) -> float:
    """
    Calculate nutrient stress factor

    Stress is based on the most deficient nutrient (Liebig's law).

    Args:
        soil_N: Current soil nitrogen (ppm)
        soil_P: Current soil phosphorus (ppm)
        soil_K: Current soil potassium (ppm)
        optimal_N: Optimal nitrogen level (ppm)
        optimal_P: Optimal phosphorus level (ppm)
        optimal_K: Optimal potassium level (ppm)

    Returns:
        Nutrient stress factor (0-1), 0 = no stress, 1 = complete deficiency
    """
    # Calculate individual nutrient availability factors
    f_N = min(1.0, soil_N / optimal_N) if optimal_N > 0 else 1.0
    f_P = min(1.0, soil_P / optimal_P) if optimal_P > 0 else 1.0
    f_K = min(1.0, soil_K / optimal_K) if optimal_K > 0 else 1.0

    # Limiting factor (minimum)
    f_nutrient = min(f_N, f_P, f_K)

    # Stress is inverse of availability
    nutrient_stress = 1 - f_nutrient

    return max(0, min(1, nutrient_stress))


def calculate_soil_ec(
    soil_N: float,
    soil_P: float,
    soil_K: float,
    conversion_factor: float = 0.001
) -> float:
    """
    Calculate soil electrical conductivity from nutrient levels

    EC approximation: EC = conversion_factor * (N + P + K)

    Higher EC indicates more dissolved salts/nutrients.
    Very high EC can cause toxicity damage.

    Args:
        soil_N: Soil nitrogen (ppm)
        soil_P: Soil phosphorus (ppm)
        soil_K: Soil potassium (ppm)
        conversion_factor: ppm to mS/cm conversion (default 0.001)

    Returns:
        Soil EC in mS/cm
    """
    total_nutrients = soil_N + soil_P + soil_K
    EC = conversion_factor * total_nutrients

    return max(0, EC)


def add_fertilizer(
    soil_N: float,
    soil_P: float,
    soil_K: float,
    N_dose: float,
    P_dose: float,
    K_dose: float
) -> Tuple[float, float, float]:
    """
    Add fertilizer to soil (Phase 2 - tool action)

    Args:
        soil_N: Current soil nitrogen (ppm)
        soil_P: Current soil phosphorus (ppm)
        soil_K: Current soil potassium (ppm)
        N_dose: Nitrogen to add (ppm)
        P_dose: Phosphorus to add (ppm)
        K_dose: Potassium to add (ppm)

    Returns:
        Tuple of (new_soil_N, new_soil_P, new_soil_K) in ppm
    """
    return (
        soil_N + N_dose,
        soil_P + P_dose,
        soil_K + K_dose
    )

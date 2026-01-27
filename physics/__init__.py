"""
Physics Module
Core physics calculations for plant simulation
All equations run every hour (dt = 1 hour)
"""

from .water_balance import (
    calculate_et,
    calculate_drainage,
    update_soil_water,
    calculate_vpd,
    calculate_water_stress
)
from .temperature import (
    calculate_temperature_response,
    calculate_thermal_time,
    calculate_temperature_stress,
    update_soil_temperature
)
from .growth import (
    calculate_photosynthesis,
    calculate_respiration,
    calculate_growth,
    update_leaf_area,
    calculate_nutrient_factor,
    update_biomass,
    decay_biomass
)
from .damage import (
    calculate_damage_rate,
    apply_damage,
    apply_damage_recovery,
    check_death,
    apply_growth_penalty,
    calculate_combined_stress
)
from .nutrients import (
    calculate_nutrient_uptake,
    update_soil_nutrients,
    calculate_nutrient_stress,
    calculate_soil_ec,
    add_fertilizer
)
from .co2 import (
    calculate_co2_consumption,
    calculate_co2_production,
    update_room_co2,
    calculate_co2_growth_factor,
    calculate_co2_stress,
    co2_grams_to_ppm,
    ppm_to_co2_grams,
    AMBIENT_CO2_PPM,
    OPTIMAL_CO2_MIN,
    OPTIMAL_CO2_MAX
)

__all__ = [
    # Water balance
    'calculate_et',
    'calculate_drainage',
    'update_soil_water',
    'calculate_vpd',
    'calculate_water_stress',
    # Temperature
    'calculate_temperature_response',
    'calculate_thermal_time',
    'calculate_temperature_stress',
    'update_soil_temperature',
    # Growth
    'calculate_photosynthesis',
    'calculate_respiration',
    'calculate_growth',
    'update_leaf_area',
    'calculate_nutrient_factor',
    'update_biomass',
    'decay_biomass',
    # Damage
    'calculate_damage_rate',
    'apply_damage',
    'apply_damage_recovery',
    'check_death',
    'apply_growth_penalty',
    'calculate_combined_stress',
    # Nutrients
    'calculate_nutrient_uptake',
    'update_soil_nutrients',
    'calculate_nutrient_stress',
    'calculate_soil_ec',
    'add_fertilizer',
    # CO2
    'calculate_co2_consumption',
    'calculate_co2_production',
    'update_room_co2',
    'calculate_co2_growth_factor',
    'calculate_co2_stress',
    'co2_grams_to_ppm',
    'ppm_to_co2_grams',
    'AMBIENT_CO2_PPM',
    'OPTIMAL_CO2_MIN',
    'OPTIMAL_CO2_MAX',
]

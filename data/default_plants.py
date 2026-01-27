"""Default plant profiles"""

DEFAULT_PLANTS = {
    'tomato': {
        'name': 'tomato',
        'max_height_cm': 200.0,
        'max_biomass_g': 1000.0,
        'growth_rate': 1.0,
        'optimal_soil_moisture': 0.6,
        'optimal_ec': 2.0,
        'optimal_ppfd': 400.0
    },
    'lettuce': {
        'name': 'lettuce',
        'max_height_cm': 30.0,
        'max_biomass_g': 200.0,
        'growth_rate': 0.8,
        'optimal_soil_moisture': 0.7,
        'optimal_ec': 1.5,
        'optimal_ppfd': 300.0
    },
    'basil': {
        'name': 'basil',
        'max_height_cm': 60.0,
        'max_biomass_g': 300.0,
        'growth_rate': 1.2,
        'optimal_soil_moisture': 0.5,
        'optimal_ec': 1.8,
        'optimal_ppfd': 350.0
    }
}

def get_plant_profile(plant_name):
    """Get plant profile by name"""
    return DEFAULT_PLANTS.get(plant_name, DEFAULT_PLANTS['tomato'])


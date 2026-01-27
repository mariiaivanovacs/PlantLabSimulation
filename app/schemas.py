"""Request/response validation schemas"""

# Optional: Add Pydantic or marshmallow schemas here

PLANT_STATE_SCHEMA = {
    'height_cm': float,
    'biomass_g': float,
    'water_stress': float
}

SIMULATION_REQUEST_SCHEMA = {
    'plant_type': str,
    'duration_days': int
}


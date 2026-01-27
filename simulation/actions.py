"""Irrigation, light, and nutrient action effects"""

def apply_irrigation(environment, amount_ml):
    """Apply irrigation action"""
    # Convert ml to soil moisture increase
    moisture_increase = amount_ml / 1000.0
    environment['soil_moisture'] = min(1.0, environment['soil_moisture'] + moisture_increase)
    return environment

def apply_light_control(environment, ppfd_value):
    """Apply light intensity control"""
    environment['light_ppfd'] = ppfd_value
    return environment

def apply_fertilizer(environment, ec_increase):
    """Apply fertilizer"""
    environment['soil_ec'] += ec_increase
    return environment

def apply_temperature_control(environment, target_temp):
    """Apply temperature control"""
    environment['temperature_c'] = target_temp
    return environment


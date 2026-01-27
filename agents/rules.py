"""Heuristics and control strategies"""

def evaluate_rules(state, environment):
    """Evaluate control rules and return actions"""
    actions = []
    
    # Rule 1: Water if soil moisture is low
    if environment.get('soil_moisture', 0.5) < 0.3:
        actions.append({
            'type': 'irrigate',
            'amount': 500,  # ml
            'reason': 'Low soil moisture'
        })
    
    # Rule 2: Fertilize if EC is low
    if environment.get('soil_ec', 2.0) < 1.0:
        actions.append({
            'type': 'fertilize',
            'amount': 0.5,
            'reason': 'Low nutrient level'
        })
    
    # Rule 3: Adjust light if below optimal
    if environment.get('light_ppfd', 0) < 200:
        actions.append({
            'type': 'light',
            'value': 400,
            'reason': 'Insufficient light'
        })
    
    return actions


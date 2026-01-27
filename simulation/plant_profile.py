"""Plant profile/species characteristics"""

from dataclasses import dataclass

@dataclass
class PlantProfile:
    """Species-specific plant characteristics"""
    
    name: str = "tomato"
    
    # Growth parameters
    max_height_cm: float = 200.0
    max_biomass_g: float = 1000.0
    growth_rate: float = 1.0
    
    # Water requirements
    optimal_soil_moisture: float = 0.6
    wilting_point: float = 0.2
    
    # Nutrient requirements
    optimal_ec: float = 2.0
    optimal_ph: float = 6.5
    
    # Light requirements
    optimal_ppfd: float = 400.0
    photoperiod_hours: float = 16.0
    
    def to_dict(self):
        return {
            'name': self.name,
            'max_height_cm': self.max_height_cm,
            'growth_rate': self.growth_rate
        }


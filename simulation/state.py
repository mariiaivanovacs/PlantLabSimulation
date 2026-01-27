"""Plant state representation"""

from dataclasses import dataclass
from datetime import datetime

@dataclass
class PlantState:
    """Current state of the plant"""
    
    # Growth metrics
    height_cm: float = 5.0
    biomass_g: float = 1.0
    leaf_area_cm2: float = 10.0
    root_depth_cm: float = 3.0
    
    # Physiological state
    water_stress: float = 0.0
    nutrient_stress: float = 0.0
    health_score: float = 100.0
    
    # Environmental response
    photosynthesis_rate: float = 0.0
    transpiration_rate: float = 0.0
    
    # Metadata
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
    
    def to_dict(self):
        return {
            'height_cm': self.height_cm,
            'biomass_g': self.biomass_g,
            'leaf_area_cm2': self.leaf_area_cm2,
            'water_stress': self.water_stress,
            'health_score': self.health_score
        }


"""Main simulation engine"""

from .state import PlantState
from .plant_profile import PlantProfile

class SimulationEngine:
    """Main simulation engine class"""
    
    def __init__(self, plant_profile: PlantProfile):
        self.plant_profile = plant_profile
        self.state = PlantState()
        self.time_step = 0
    
    def step(self, hours=1.0):
        """Advance simulation by time step"""
        self.time_step += 1
        # Update state logic here
        pass
    
    def get_state(self):
        """Get current state"""
        return self.state
    
    def reset(self):
        """Reset simulation"""
        self.state = PlantState()
        self.time_step = 0


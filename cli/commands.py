"""CLI commands"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models.engine import SimulationEngine
from models.plant_profile import PlantProfile
from data.default_plants import get_plant_profile

def run_simulation(plant_name='tomato', days=30):
    """Run simulation from CLI"""
    print(f"Starting simulation for {plant_name} ({days} days)...")
    
    profile_data = get_plant_profile(plant_name)
    profile = PlantProfile(**profile_data)
    
    engine = SimulationEngine(profile)
    
    for day in range(days):
        for hour in range(24):
            engine.step(hours=1.0)
        
        if day % 7 == 0:
            state = engine.get_state()
            print(f"Day {day}: Height={state.height_cm:.1f}cm, Biomass={state.biomass_g:.1f}g")
    
    print("Simulation complete!")

def list_plants():
    """List available plant profiles"""
    from data.default_plants import DEFAULT_PLANTS
    print("Available plant profiles:")
    for name in DEFAULT_PLANTS.keys():
        print(f"  - {name}")

if __name__ == '__main__':
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == 'list':
            list_plants()
        elif command == 'run':
            plant = sys.argv[2] if len(sys.argv) > 2 else 'tomato'
            days = int(sys.argv[3]) if len(sys.argv) > 3 else 30
            run_simulation(plant, days)
    else:
        print("Usage: python cli/commands.py [list|run] [plant_name] [days]")


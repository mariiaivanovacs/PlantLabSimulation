"""Test script to verify the structure works"""

import sys
import os

# Test imports
print("Testing PlantLabSimulation2 structure...")
print("="*60)

try:
    # Test Flask app
    from app import create_app
    app = create_app()
    print("✓ Flask app created successfully")
    
    # Test simulation engine
    from models.engine import SimulationEngine
    from models.plant_profile import PlantProfile
    from models.state import PlantState
    print("✓ Simulation engine imports successful")
    
    # Test agents
    from agents.planner import Planner
    from agents.executor import Executor
    from agents.memory import Memory
    print("✓ Agent imports successful")
    
    # Test services
    from services.firebase_service import FirebaseService
    from services.logging_service import LoggingService
    print("✓ Service imports successful")
    
    # Test data
    from data.default_plants import get_plant_profile, DEFAULT_PLANTS
    print("✓ Data imports successful")
    
    # Test config
    from config.settings import FLASK_ENV, PORT
    print("✓ Config imports successful")
    
    print("="*60)
    print("All imports successful! ✓")
    print("\nAvailable plants:")
    for plant_name in DEFAULT_PLANTS.keys():
        print(f"  - {plant_name}")
    
    print("\nTo run Flask server:")
    print("  python run.py")
    
    print("\nTo run CLI:")
    print("  python main.py list")
    print("  python main.py run tomato 30")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()


"""Data initialization utilities"""

from .default_plants import DEFAULT_PLANTS

def initialize_default_data():
    """Initialize default plant data"""
    print("Initializing default plant profiles...")
    for plant_name, profile in DEFAULT_PLANTS.items():
        print(f"  - {plant_name}: {profile['name']}")
    print("Initialization complete!")
    return DEFAULT_PLANTS

def load_custom_plants(file_path):
    """Load custom plant profiles from file"""
    # Load from JSON/YAML file
    pass


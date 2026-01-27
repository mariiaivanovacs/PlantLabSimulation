# """Data initialization utilities"""

# from .default_plants import DEFAULT_PLANTS

# def initialize_default_data():
#     """Initialize default plant data"""
#     print("Initializing default plant profiles...")
#     for plant_name, profile in DEFAULT_PLANTS.items():
#         print(f"  - {plant_name}: {profile['name']}")
#     print("Initialization complete!")
#     return DEFAULT_PLANTS

# def load_custom_plants(file_path):
#     """Load custom plant profiles from file"""
#     # Load from JSON/YAML file
#     pass



"""
Data Initialization and Seeding
Handles loading default data into Firebase
"""
import json
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from models import PlantProfile
from database.firebase_manager import db_manager
from data.default_plants import get_default_profiles


class DataInitializer:
    """Handles initial data loading and seeding"""
    
    def __init__(self):
        self.db = db_manager
    
    def seed_default_plants(self, force: bool = False) -> dict:
        """
        Seed database with default plant profiles
        
        Args:
            force: If True, overwrite existing profiles
        
        Returns:
            dict with status of each profile
        """
        results = {
            'success': [],
            'skipped': [],
            'failed': []
        }
        
        default_profiles = get_default_profiles()
        
        print(f"\n🌱 Seeding {len(default_profiles)} default plant profiles...")
        
        for profile_id, profile in default_profiles.items():
            # Check if already exists
            if not force:
                existing = self.db.get_plant_profile(profile_id)
                if existing:
                    print(f"  ⊘ {profile_id}: Already exists (use --force to overwrite)")
                    results['skipped'].append(profile_id)
                    continue
            
            # Save profile
            success = self.db.save_plant_profile(profile)
            
            if success:
                print(f"  ✓ {profile_id}: {profile.species_name}")
                results['success'].append(profile_id)
            else:
                print(f"  ✗ {profile_id}: Failed to save")
                results['failed'].append(profile_id)
        
        print(f"\n✓ Seeding complete: {len(results['success'])} added, "
              f"{len(results['skipped'])} skipped, {len(results['failed'])} failed")
        
        return results
    
    def import_custom_profile(self, profile_data: dict) -> Optional[PlantProfile]:
        """
        Import a custom plant profile from dictionary
        
        Args:
            profile_data: Dictionary with plant profile data
        
        Returns:
            PlantProfile if successful, None otherwise
        """
        try:
            # Validate and create profile
            profile = PlantProfile.from_dict(profile_data)
            
            # Validate compatibility
            issues = profile.validate_compatibility()
            if issues:
                print(f"⚠ Profile validation warnings:")
                for issue in issues:
                    print(f"  - {issue}")
            
            # Save to database
            success = self.db.save_plant_profile(profile)
            
            if success:
                print(f"✓ Imported custom profile: {profile.profile_id}")
                return profile
            else:
                print(f"✗ Failed to save custom profile")
                return None
                
        except Exception as e:
            print(f"✗ Error importing profile: {e}")
            return None
    
    def import_from_json_file(self, filepath: str) -> Optional[PlantProfile]:
        """
        Import plant profile from JSON file
        
        Args:
            filepath: Path to JSON file
        
        Returns:
            PlantProfile if successful, None otherwise
        """
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            return self.import_custom_profile(data)
            
        except FileNotFoundError:
            print(f"✗ File not found: {filepath}")
            return None
        except json.JSONDecodeError as e:
            print(f"✗ Invalid JSON: {e}")
            return None
    
    def export_profile_to_json(self, profile_id: str, output_path: str) -> bool:
        """
        Export a plant profile to JSON file
        
        Args:
            profile_id: ID of profile to export
            output_path: Where to save the file
        
        Returns:
            True if successful
        """
        try:
            profile = self.db.get_plant_profile(profile_id)
            
            if not profile:
                print(f"✗ Profile {profile_id} not found")
                return False
            
            with open(output_path, 'w') as f:
                json.dump(profile.to_dict(), f, indent=2, default=str)
            
            print(f"✓ Exported {profile_id} to {output_path}")
            return True
            
        except Exception as e:
            print(f"✗ Error exporting profile: {e}")
            return False
    
    def create_profile_template(self, output_path: str = "custom_plant_template.json") -> bool:
        """
        Create a template JSON file for custom plant profiles
        
        Args:
            output_path: Where to save template
        
        Returns:
            True if successful
        """
        try:
            # Use tomato as template
            from data.default_plants import get_tomato_profile
            
            template = get_tomato_profile()
            template.profile_id = "custom_plant_id"
            template.species_name = "Species name here"
            template.common_names = ["Common name"]
            template.description = "Description of your plant"
            template.is_default = False
            template.created_by = "user"
            
            with open(output_path, 'w') as f:
                json.dump(template.to_dict(), f, indent=2, default=str)
            
            print(f"✓ Created template at {output_path}")
            print(f"  Edit this file and use 'import-profile' command to load it")
            return True
            
        except Exception as e:
            print(f"✗ Error creating template: {e}")
            return False
    
    def list_all_profiles(self) -> List[PlantProfile]:
        """List all available profiles in database"""
        profiles = self.db.list_plant_profiles()
        
        if profiles:
            print(f"\n📋 Available Plant Profiles ({len(profiles)}):")
            print("-" * 80)
            
            for profile in profiles:
                default_marker = " [DEFAULT]" if profile.is_default else ""
                print(f"\n  ID: {profile.profile_id}{default_marker}")
                print(f"  Species: {profile.species_name}")
                if profile.common_names:
                    print(f"  Common: {', '.join(profile.common_names)}")
                if profile.description:
                    print(f"  Desc: {profile.description}")
                print(f"  Temp: {profile.temperature.T_min}°C - "
                      f"{profile.temperature.T_opt}°C - {profile.temperature.T_max}°C")
        else:
            print("\n⚠ No plant profiles found in database")
            print("  Run 'seed-defaults' command to load default plants")
        
        return profiles


# Global initializer instance
data_initializer = DataInitializer()
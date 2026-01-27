# """Default plant profiles"""

# DEFAULT_PLANTS = {
#     'tomato': {
#         'name': 'tomato',
#         'max_height_cm': 200.0,
#         'max_biomass_g': 1000.0,
#         'growth_rate': 1.0,
#         'optimal_soil_moisture': 0.6,
#         'optimal_ec': 2.0,
#         'optimal_ppfd': 400.0
#     },
#     'lettuce': {
#         'name': 'lettuce',
#         'max_height_cm': 30.0,
#         'max_biomass_g': 200.0,
#         'growth_rate': 0.8,
#         'optimal_soil_moisture': 0.7,
#         'optimal_ec': 1.5,
#         'optimal_ppfd': 300.0
#     },
#     'basil': {
#         'name': 'basil',
#         'max_height_cm': 60.0,
#         'max_biomass_g': 300.0,
#         'growth_rate': 1.2,
#         'optimal_soil_moisture': 0.5,
#         'optimal_ec': 1.8,
#         'optimal_ppfd': 350.0
#     }
# }

# def get_plant_profile(plant_name):
#     """Get plant profile by name"""
#     return DEFAULT_PLANTS.get(plant_name, DEFAULT_PLANTS['tomato'])




"""
Default Plant Profiles
Pre-configured profiles for common plants
"""
from datetime import datetime
from models import (
    PlantProfile,
    TemperatureResponse,
    WaterRequirements,
    NutrientDemand,
    GrowthParameters,
    PhenologyThresholds
)


def get_tomato_profile() -> PlantProfile:
    """
    Tomato plant profile (Solanum lycopersicum)
    Reference profile from documentation
    """
    return PlantProfile(
        profile_id="tomato_standard",
        species_name="Solanum lycopersicum",
        common_names=["Tomato", "Garden Tomato"],
        description="Standard indeterminate tomato cultivar for controlled environment",
        
        temperature=TemperatureResponse(
            T_min=10.0,
            T_opt=25.0,
            T_max=35.0,
            T_base=10.0
        ),
        
        water=WaterRequirements(
            wilting_point=15.0,
            field_capacity=35.0,
            saturation=55.0,
            optimal_range_min=30.0,
            optimal_range_max=40.0
        ),
        
        nutrients=NutrientDemand(
            N_ratio=0.03,
            P_ratio=0.005,
            K_ratio=0.02,
            optimal_N=200.0,
            optimal_P=50.0,
            optimal_K=250.0
        ),
        
        growth=GrowthParameters(
            LUE=0.003,
            r_base=0.000625,  # 0.015 g/g/day = 0.000625 g/g/h
            max_biomass=500.0,
            leaf_area_ratio=0.004,
            optimal_PAR=600.0,
            PAR_saturation=1200.0
        ),
        
        phenology=PhenologyThresholds(
            seed_to_seedling_GDD=50.0,
            seedling_to_vegetative_GDD=500.0,
            vegetative_to_flowering_GDD=2000.0,
            flowering_to_fruiting_GDD=3500.0,
            fruiting_to_mature_GDD=5000.0,
            seed_to_seedling_biomass=0.1
        ),
        
        optimal_RH_min=50.0,
        optimal_RH_max=70.0,
        optimal_VPD=1.0,
        optimal_pH_min=6.0,
        optimal_pH_max=7.0,
        EC_toxicity_threshold=3.5,
        
        initial_biomass=0.5,
        initial_leaf_area=0.002,
        
        created_at=datetime.now().isoformat(),
        created_by="system",
        is_default=True
    )


def get_lettuce_profile() -> PlantProfile:
    """
    Lettuce plant profile (Lactuca sativa)
    Fast-growing leafy green
    """
    return PlantProfile(
        profile_id="lettuce_butterhead",
        species_name="Lactuca sativa",
        common_names=["Lettuce", "Butterhead Lettuce"],
        description="Fast-growing butterhead lettuce for hydroponic/indoor growing",
        
        temperature=TemperatureResponse(
            T_min=5.0,
            T_opt=18.0,
            T_max=28.0,
            T_base=5.0
        ),
        
        water=WaterRequirements(
            wilting_point=12.0,
            field_capacity=30.0,
            saturation=50.0,
            optimal_range_min=25.0,
            optimal_range_max=35.0
        ),
        
        nutrients=NutrientDemand(
            N_ratio=0.04,  # Higher N for leafy greens
            P_ratio=0.004,
            K_ratio=0.025,
            optimal_N=180.0,
            optimal_P=40.0,
            optimal_K=200.0
        ),
        
        growth=GrowthParameters(
            LUE=0.0035,  # Slightly higher efficiency
            r_base=0.0005,  # Lower respiration
            max_biomass=150.0,  # Smaller plant
            leaf_area_ratio=0.006,  # Higher leaf area ratio
            optimal_PAR=350.0,  # Lower light needs
            PAR_saturation=800.0
        ),
        
        phenology=PhenologyThresholds(
            seed_to_seedling_GDD=30.0,
            seedling_to_vegetative_GDD=200.0,
            vegetative_to_flowering_GDD=1500.0,  # Typically harvested before flowering
            flowering_to_fruiting_GDD=2000.0,
            fruiting_to_mature_GDD=2500.0,
            seed_to_seedling_biomass=0.05
        ),
        
        optimal_RH_min=60.0,
        optimal_RH_max=80.0,
        optimal_VPD=0.8,
        optimal_pH_min=5.5,
        optimal_pH_max=6.5,
        EC_toxicity_threshold=2.5,  # More sensitive to salts
        
        initial_biomass=0.3,
        initial_leaf_area=0.0018,
        
        created_at=datetime.now().isoformat(),
        created_by="system",
        is_default=True
    )


def get_basil_profile() -> PlantProfile:
    """
    Basil plant profile (Ocimum basilicum)
    Aromatic herb for indoor growing
    """
    return PlantProfile(
        profile_id="basil_sweet",
        species_name="Ocimum basilicum",
        common_names=["Sweet Basil", "Genovese Basil"],
        description="Sweet basil cultivar for culinary use, excellent for indoor growing",
        
        temperature=TemperatureResponse(
            T_min=15.0,
            T_opt=24.0,
            T_max=32.0,
            T_base=12.0
        ),
        
        water=WaterRequirements(
            wilting_point=18.0,
            field_capacity=38.0,
            saturation=58.0,
            optimal_range_min=32.0,
            optimal_range_max=45.0
        ),
        
        nutrients=NutrientDemand(
            N_ratio=0.035,
            P_ratio=0.006,
            K_ratio=0.022,
            optimal_N=150.0,
            optimal_P=45.0,
            optimal_K=180.0
        ),
        
        growth=GrowthParameters(
            LUE=0.0028,
            r_base=0.0007,
            max_biomass=100.0,
            leaf_area_ratio=0.005,
            optimal_PAR=450.0,
            PAR_saturation=1000.0
        ),
        
        phenology=PhenologyThresholds(
            seed_to_seedling_GDD=40.0,
            seedling_to_vegetative_GDD=300.0,
            vegetative_to_flowering_GDD=1200.0,
            flowering_to_fruiting_GDD=1800.0,
            fruiting_to_mature_GDD=2200.0,
            seed_to_seedling_biomass=0.08
        ),
        
        optimal_RH_min=45.0,
        optimal_RH_max=65.0,
        optimal_VPD=1.1,
        optimal_pH_min=6.0,
        optimal_pH_max=7.5,
        EC_toxicity_threshold=2.8,
        
        initial_biomass=0.4,
        initial_leaf_area=0.002,
        
        created_at=datetime.now().isoformat(),
        created_by="system",
        is_default=True
    )


# Export all default profiles
DEFAULT_PROFILES = {
    "tomato_standard": get_tomato_profile(),
    "lettuce_butterhead": get_lettuce_profile(),
    "basil_sweet": get_basil_profile()
}


def get_default_profiles() -> dict[str, PlantProfile]:
    """Get all default plant profiles"""
    return DEFAULT_PROFILES.copy()


def load_default_profile(profile_id: str) -> PlantProfile:
    """Load a specific default profile"""
    if profile_id in DEFAULT_PROFILES:
        return DEFAULT_PROFILES[profile_id]
    else:
        raise ValueError(f"Unknown profile ID: {profile_id}. Available: {list(DEFAULT_PROFILES.keys())}")
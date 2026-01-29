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
            T_base=10.0, 
            air_weight=0.8,
            soil_weight=0.2
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
            LUE=0.000015,     # Light Use Efficiency (g/umol)
            r_base=0.000625,  # FIX: Realistic 1.5% per day / 24 hours = 0.0625% per hour
            max_biomass=500.0,
            leaf_area_ratio=0.004,
            optimal_PAR=600.0,
            PAR_saturation=1200.0
        ),
        
        # phenology=PhenologyThresholds(
        #     seed_to_seedling_GDD=50.0,
        #     seedling_to_vegetative_GDD=500.0,
        #     vegetative_to_flowering_GDD=2000.0,
        #     flowering_to_fruiting_GDD=3500.0,
        #     fruiting_to_mature_GDD=5000.0,
        #     seed_to_seedling_biomass=0.1
        # ),
        
        phenology = PhenologyThresholds(
            # Thermal time thresholds (GDD)
            seed_to_seedling_GDD=100.0,             # tomato seeds take longer to germinate
            seedling_to_vegetative_GDD=500.0,       # true leaves formed
            vegetative_to_flowering_GDD=1500.0,     # flower buds start forming
            flowering_to_fruiting_GDD=2000.0,       # fruit set occurs
            fruiting_to_mature_GDD=3000.0,          # fruits fully mature

            # Corresponding biomass thresholds (grams)
            seed_to_seedling_biomass=0.1,           # tiny germinated seedling
            seedling_to_vegetative_biomass=1.0,     # small seedling with leaves
            vegetative_to_flowering_biomass=50.0,   # enough vegetative growth for flowering
            flowering_to_fruiting_biomass=150.0,    # enough plant mass to support fruits
            fruiting_to_mature_biomass=300.0        # fully grown plant with ripe fruits
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
    Lettuce plant profile (Lactuca sativa) — corrected/default values for butterhead lettuce.
    """
    return PlantProfile(
        profile_id="lettuce_butterhead",
        species_name="Lactuca sativa",
        common_names=["Lettuce", "Butterhead Lettuce"],
        description="Fast-growing butterhead lettuce for hydroponic/indoor growing",
        
        temperature=TemperatureResponse(
            T_min=4.0,    # lower threshold for growth
            T_opt=20.0,   # optimal temperature for lettuce leaves
            T_max=28.0,   # upper threshold before rapid heat stress
            T_base=4.0,
            air_weight=0.7,
            soil_weight=0.3
        ),
        
        water=WaterRequirements(
            wilting_point=10.0,        # volumetric % or relative scale used by your model
            field_capacity=45.0,
            saturation=60.0,
            optimal_range_min=45.0,   # keep soil/hydro moisture in this comfortable range
            optimal_range_max=75.0
        ),
        
        nutrients=NutrientDemand(
            N_ratio=0.035,  # fraction used in allocation scheme (keeps higher N demand)
            P_ratio=0.005,
            K_ratio=0.03,
            optimal_N=150.0,   # ppm range commonly targeted for lettuce
            optimal_P=40.0,
            optimal_K=200.0
        ),
        
        growth=GrowthParameters(
            LUE=0.000008,     # Light Use Efficiency - slightly increased for realistic growth
            r_base=0.0005,    # FIX: Realistic 1.2% per day / 24 hours = 0.05% per hour
            max_biomass=300.0, # genetic potential (fresh mass, g) for a mature head
            leaf_area_ratio=0.004,  # Realistic leaf area ratio (m²/g)
            optimal_PAR=800.0,     # lower light needs (µmol m-2 s-1 scale)
            PAR_saturation=600.0
        ),
        
        # phenology=PhenologyThresholds(
        #     seed_to_seedling_GDD=50.0,
        #     seedling_to_vegetative_GDD=200.0,
        #     vegetative_to_flowering_GDD=2500.0,  # usually harvested before flowering
        #     flowering_to_fruiting_GDD=3000.0,
        #     fruiting_to_mature_GDD=3500.0,
        #     seed_to_seedling_biomass=0.05
        # ),
        
        phenology = PhenologyThresholds(
            # Thermal time thresholds (GDD)
            seed_to_seedling_GDD=50.0,               # 2–3 days germination
            seedling_to_vegetative_GDD=200.0,       # ~10 days to true leaves
            vegetative_to_flowering_GDD=2500.0,     # usually harvested before flowering
            flowering_to_fruiting_GDD=3000.0,       
            fruiting_to_mature_GDD=3500.0,          

            # Corresponding biomass thresholds (grams)
            seed_to_seedling_biomass=0.05,          # tiny seedling just germinated
            seedling_to_vegetative_biomass=0.1,     # needs some leaves to be "vegetative"
            vegetative_to_flowering_biomass=150.0,  # leafy mass before bolting
            flowering_to_fruiting_biomass=200.0,    # only relevant for seed production
            fruiting_to_mature_biomass=250.0        # mature seed production
        ),

        
        optimal_RH_min=60.0,
        optimal_RH_max=80.0,
        optimal_VPD=0.6,
        optimal_pH_min=5.5,
        optimal_pH_max=6.5,
        EC_toxicity_threshold=1.8,  # lettuce is fairly salt-sensitive; lower threshold
        
        initial_biomass=0.05,       # realistic tiny seedling start (g fresh mass)
        initial_leaf_area=0.0005,   # small starting leaf area
        
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
            T_base=12.0,
            air_weight=0.8,
            soil_weight=0.2
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
            LUE=0.000014,     # Light Use Efficiency (g/umol)
            r_base=0.0007,    # FIX: Realistic 1.7% per day / 24 hours = 0.07% per hour
            max_biomass=100.0,
            leaf_area_ratio=0.004,  # Realistic leaf area ratio
            optimal_PAR=450.0,
            PAR_saturation=1000.0
        ),
        
        # phenology=PhenologyThresholds(
        #     seed_to_seedling_GDD=40.0,
        #     seedling_to_vegetative_GDD=300.0,
        #     vegetative_to_flowering_GDD=1200.0,
        #     flowering_to_fruiting_GDD=1800.0,
        #     fruiting_to_mature_GDD=2200.0,
        #     seed_to_seedling_biomass=0.08
        # ),
        
        phenology = PhenologyThresholds(
            # Thermal time thresholds (GDD)
            seed_to_seedling_GDD=40.0,               # quick germination
            seedling_to_vegetative_GDD=300.0,       # true leaves formed
            vegetative_to_flowering_GDD=1200.0,     # flower buds start forming
            flowering_to_fruiting_GDD=1800.0,       # full flowering / seed set
            fruiting_to_mature_GDD=2200.0,          # mature plant, seeds ripe

            # Corresponding biomass thresholds (grams)
            seed_to_seedling_biomass=0.08,          # tiny germinated seedling
            seedling_to_vegetative_biomass=0.5,     # small seedling with leaves
            vegetative_to_flowering_biomass=20.0,   # enough leaf mass to flower
            flowering_to_fruiting_biomass=50.0,     # enough plant mass for full flowering
            fruiting_to_mature_biomass=80.0         # mature plant, seed/fruit production
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
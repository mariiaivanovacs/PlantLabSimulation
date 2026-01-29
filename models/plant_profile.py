"""
Plant Profile Model
Defines species-specific characteristics and parameters
"""
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class TemperatureResponse(BaseModel):
    """Cardinal temperature parameters"""
    T_min: float = Field(description="Minimum temperature for growth (°C)")
    T_opt: float = Field(description="Optimal temperature (°C)")
    T_max: float = Field(description="Maximum temperature for growth (°C)")
    T_base: float = Field(description="Base temperature for thermal time (°C)"),
    air_weight: float = Field(default=0.7, description="Weight of air temperature in averaging (0-1)")
    soil_weight: float = Field(default=0.3, description="Weight of soil temperature in averaging (0-1)")


class WaterRequirements(BaseModel):
    """Soil water parameters"""
    wilting_point: float = Field(description="Permanent wilting point (%)", ge=0, le=100)
    field_capacity: float = Field(description="Field capacity (%)", ge=0, le=100)
    saturation: float = Field(description="Saturation point (%)", ge=0, le=100)
    optimal_range_min: float = Field(description="Optimal range minimum (%)")
    optimal_range_max: float = Field(description="Optimal range maximum (%)")


class NutrientDemand(BaseModel):
    """Nutrient uptake ratios"""
    N_ratio: float = Field(description="g N per g biomass", ge=0)
    P_ratio: float = Field(description="g P per g biomass", ge=0)
    K_ratio: float = Field(description="g K per g biomass", ge=0)
    optimal_N: float = Field(description="Optimal soil N (ppm)", ge=0)
    optimal_P: float = Field(description="Optimal soil P (ppm)", ge=0)
    optimal_K: float = Field(description="Optimal soil K (ppm)", ge=0)


class GrowthParameters(BaseModel):
    """Growth and photosynthesis parameters"""
    LUE: float = Field(description="Light use efficiency (g/µmol)", ge=0)
    r_base: float = Field(description="Maintenance respiration rate (g/g/h)", ge=0)
    max_biomass: float = Field(description="Maximum biomass (g)", ge=0)
    leaf_area_ratio: float = Field(description="Leaf area per biomass (m²/g)", ge=0)
    optimal_PAR: float = Field(description="Optimal PAR (µmol/m²/s)", ge=0)
    PAR_saturation: float = Field(description="PAR saturation point", ge=0)


class PhenologyThresholds(BaseModel):
    """Thermal time requirements for stage transitions"""
    seed_to_seedling_GDD: float = Field(default=50, description="°C·h")
    seedling_to_vegetative_GDD: float = Field(default=500, description="°C·h")
    vegetative_to_flowering_GDD: float = Field(default=2000, description="°C·h")
    flowering_to_fruiting_GDD: float = Field(default=3500, description="°C·h")
    fruiting_to_mature_GDD: float = Field(default=5000, description="°C·h")
    seed_to_seedling_biomass: float = Field(default=0.1, description="Minimum biomass (g)"),
    seedling_to_vegetative_biomass: float = Field(default=0.1, description="Minimum biomass (g)")
    vegetative_to_flowering_biomass: float = Field(default=0.1, description="Minimum biomass (g)")
    flowering_to_fruiting_biomass: float = Field(default=0.1, description="Minimum biomass (g)")
    fruiting_to_mature_biomass: float = Field(default=0.1, description="Minimum biomass (g)")


class PlantProfile(BaseModel):
    """
    Complete plant profile defining species-specific characteristics
    Used to initialize simulations and define expected behaviors
    """
    # Identification
    profile_id: str = Field(description="Unique profile identifier")
    species_name: str = Field(description="Scientific or common name")
    common_names: list[str] = Field(default_factory=list)
    description: Optional[str] = Field(default=None)
    
    # Growth parameters
    temperature: TemperatureResponse
    water: WaterRequirements
    nutrients: NutrientDemand
    growth: GrowthParameters
    phenology: PhenologyThresholds = Field(default_factory=PhenologyThresholds)
    
    # Environmental preferences
    optimal_RH_min: float = Field(default=50, description="Optimal RH minimum (%)")
    optimal_RH_max: float = Field(default=70, description="Optimal RH maximum (%)")
    optimal_VPD: float = Field(default=1.0, description="Optimal VPD (kPa)")
    optimal_pH_min: float = Field(default=6.0, description="Optimal pH minimum")
    optimal_pH_max: float = Field(default=7.0, description="Optimal pH maximum")
    EC_toxicity_threshold: float = Field(default=3.5, description="EC causing damage (mS/cm)")
    
    # Initial conditions
    initial_biomass: float = Field(default=0.5, description="Starting biomass (g)")
    initial_leaf_area: float = Field(default=0.002, description="Starting leaf area (m²)")
    
    # Metadata
    created_at: Optional[str] = Field(default=None)
    created_by: Optional[str] = Field(default="system")
    is_default: bool = Field(default=False)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Firebase storage"""
        return self.model_dump()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PlantProfile':
        """Create from dictionary (Firebase retrieval)"""
        return cls(**data)
    
    def validate_compatibility(self) -> list[str]:
        """Validate profile parameters for consistency"""
        issues = []
        
        # Check temperature ordering
        if not (self.temperature.T_min < self.temperature.T_opt < self.temperature.T_max):
            issues.append("Temperature cardinal points must satisfy: T_min < T_opt < T_max")
        
        # Check water ordering
        if not (self.water.wilting_point < self.water.field_capacity < self.water.saturation):
            issues.append("Water points must satisfy: wilting < field_capacity < saturation")
        
        # Check optimal ranges
        if self.water.optimal_range_min >= self.water.optimal_range_max:
            issues.append("Water optimal range invalid")
        
        if self.optimal_RH_min >= self.optimal_RH_max:
            issues.append("RH optimal range invalid")
        
        if self.optimal_pH_min >= self.optimal_pH_max:
            issues.append("pH optimal range invalid")
        
        return issues
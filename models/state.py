"""
Core State Vector Model
Represents the complete hidden state S(t) at any given hour
"""
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class PhenologicalStage(str, Enum):
    """Plant growth stages"""
    SEED = "seed"
    SEEDLING = "seedling"
    VEGETATIVE = "vegetative"
    FLOWERING = "flowering"
    FRUITING = "fruiting"
    MATURE = "mature"
    DEAD = "dead"


class PlantState(BaseModel):
    """
    Complete state vector for a plant at time t
    All values updated every hour (Δt = 1 hour)
    """
    # Identification
    plant_id: str = Field(description="Unique plant identifier")
    simulation_id: str = Field(description="Simulation run identifier")
    timestamp: datetime = Field(description="Current simulation time")
    hour: int = Field(default=0, description="Hour counter from start")
    
    # Plant physiological state
    biomass: float = Field(default=0.5, description="Total biomass (g)", ge=0)
    leaf_area: float = Field(default=0.002, description="Leaf area (m²)", ge=0)
    phenological_stage: PhenologicalStage = Field(default=PhenologicalStage.SEEDLING)
    thermal_time: float = Field(default=0, description="Accumulated growing degree hours (°C·h)", ge=0)
    is_alive: bool = Field(default=True)
    
    # Damage and stress
    cumulative_damage: float = Field(default=0, description="Irreversible damage (%)", ge=0, le=100)
    water_stress: float = Field(default=0, description="Current water stress (0-1)", ge=0, le=1)
    temp_stress: float = Field(default=0, description="Temperature stress (0-1)", ge=0, le=1)
    nutrient_stress: float = Field(default=0, description="Nutrient stress (0-1)", ge=0, le=1)
    
    # Soil state
    soil_water: float = Field(default=40, description="Volumetric soil water content (%)", ge=0, le=100)
    soil_temp: float = Field(default=22, description="Soil temperature (°C)")
    soil_N: float = Field(default=200, description="Available nitrogen (ppm)", ge=0)
    soil_P: float = Field(default=50, description="Available phosphorus (ppm)", ge=0)
    soil_K: float = Field(default=150, description="Available potassium (ppm)", ge=0)
    soil_EC: float = Field(default=1.5, description="Electrical conductivity (mS/cm)", ge=0)
    soil_pH: float = Field(default=6.5, description="Soil pH", ge=0, le=14)
    
    # Environmental state
    air_temp: float = Field(default=23, description="Air temperature (°C)")
    relative_humidity: float = Field(default=60, description="Relative humidity (%)", ge=0, le=100)
    VPD: float = Field(default=1.0, description="Vapor pressure deficit (kPa)", ge=0)
    light_PAR: float = Field(default=400, description="Photosynthetically active radiation (µmol/m²/s)", ge=0)
    CO2: float = Field(default=400, description="CO2 concentration (ppm)", ge=0)
    
    # Fluxes (calculated each timestep)
    ET: float = Field(default=0, description="Evapotranspiration this hour (L)", ge=0)
    photosynthesis: float = Field(default=0, description="Gross photosynthesis this hour (g)", ge=0)
    respiration: float = Field(default=0, description="Maintenance respiration this hour (g)", ge=0)
    growth_rate: float = Field(default=0, description="Biomass growth this hour (g/h)")
    
    # Room/container properties
    pot_volume: float = Field(default=5, description="Pot volume (L)", ge=0)
    room_volume: float = Field(default=50, description="Room volume (m³)", ge=0)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Firebase storage"""
        data = self.model_dump()
        # Convert datetime to ISO string
        if isinstance(data['timestamp'], datetime):
            data['timestamp'] = data['timestamp'].isoformat()
        # Convert enum to string
        if isinstance(data['phenological_stage'], PhenologicalStage):
            data['phenological_stage'] = data['phenological_stage'].value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PlantState':
        """Create from dictionary (Firebase retrieval)"""
        if isinstance(data.get('timestamp'), str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        if isinstance(data.get('phenological_stage'), str):
            data['phenological_stage'] = PhenologicalStage(data['phenological_stage'])
        return cls(**data)
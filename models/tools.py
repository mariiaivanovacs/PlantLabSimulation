"""
Tool Definitions and Actions
Defines the 6 autonomous tools and their action records
PHASE 1: Just data models - no execution logic yet
"""
from datetime import datetime
from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
from enum import Enum


class ToolType(str, Enum):
    """Six autonomous tools"""
    WATERING = "watering"
    LIGHTING = "lighting"
    NUTRIENTS = "nutrients"
    HVAC = "hvac"
    HUMIDITY = "humidity"
    VENTILATION = "ventilation"


class WateringAction(BaseModel):
    """Watering system parameters"""
    volume_L: float = Field(description="Water volume to add (liters)", ge=0)
    flow_rate_L_per_h: float = Field(default=2.0, description="Maximum flow rate (L/h)", ge=0)


class LightingAction(BaseModel):
    """Lighting system parameters"""
    target_PAR: float = Field(description="Target PAR (µmol/m²/s)", ge=0, le=2000)
    power_W: float = Field(description="Lamp electrical power (W)", ge=0)


class NutrientAction(BaseModel):
    """Nutrient dosing parameters"""
    N_dose_ppm: float = Field(default=0, description="Nitrogen dose (ppm)", ge=0)
    P_dose_ppm: float = Field(default=0, description="Phosphorus dose (ppm)", ge=0)
    K_dose_ppm: float = Field(default=0, description="Potassium dose (ppm)", ge=0)


class HVACAction(BaseModel):
    """HVAC temperature control parameters"""
    target_temp_C: float = Field(description="Target air temperature (°C)")
    max_rate_C_per_h: float = Field(default=5.0, description="Max temp change rate (°C/h)", ge=0)


class HumidityAction(BaseModel):
    """Humidity control parameters"""
    target_RH: float = Field(description="Target relative humidity (%)", ge=0, le=100)
    max_rate_RH_per_h: float = Field(default=10.0, description="Max RH change rate (%/h)", ge=0)


class VentilationAction(BaseModel):
    """Ventilation system parameters"""
    fan_speed: float = Field(description="Fan speed (%)", ge=0, le=100)
    outside_temp_C: float = Field(description="Outside air temperature (°C)")
    outside_RH: float = Field(description="Outside relative humidity (%)", ge=0, le=100)
    max_exchange_rate: float = Field(default=0.5, description="Max air exchange fraction per hour")


class ToolAction(BaseModel):
    """
    Generic tool action record
    Stores when a tool was scheduled/applied
    """
    action_id: str = Field(description="Unique action identifier")
    simulation_id: str = Field(description="Simulation this belongs to")
    plant_id: str = Field(description="Target plant")
    tool_type: ToolType
    scheduled_hour: int = Field(description="Hour to apply action")
    applied_hour: Optional[int] = Field(default=None, description="When actually applied")
    timestamp: datetime = Field(default_factory=datetime.now)
    
    # Tool-specific parameters (only one will be populated)
    watering_params: Optional[WateringAction] = None
    lighting_params: Optional[LightingAction] = None
    nutrient_params: Optional[NutrientAction] = None
    hvac_params: Optional[HVACAction] = None
    humidity_params: Optional[HumidityAction] = None
    ventilation_params: Optional[VentilationAction] = None
    
    # Execution metadata
    is_executed: bool = Field(default=False)
    execution_notes: Optional[str] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Firebase"""
        data = self.model_dump(exclude_none=True)
        if isinstance(data.get('timestamp'), datetime):
            data['timestamp'] = data['timestamp'].isoformat()
        if isinstance(data.get('tool_type'), ToolType):
            data['tool_type'] = data['tool_type'].value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ToolAction':
        """Create from dictionary"""
        if isinstance(data.get('timestamp'), str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        if isinstance(data.get('tool_type'), str):
            data['tool_type'] = ToolType(data['tool_type'])
        return cls(**data)


class ToolConfiguration(BaseModel):
    """
    Tool configuration/capabilities
    Defines what each tool can do
    """
    tool_type: ToolType
    is_enabled: bool = Field(default=True)
    auto_mode: bool = Field(default=False, description="Reserved for Phase 2")
    
    # Physical constraints
    min_activation_interval_hours: int = Field(default=1, description="Minimum time between activations")
    max_daily_activations: Optional[int] = Field(default=None)
    
    # Tool-specific limits (for validation)
    watering_max_volume_L: Optional[float] = None
    lighting_max_PAR: Optional[float] = None
    hvac_temp_range: Optional[tuple[float, float]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = self.model_dump()
        if isinstance(data.get('tool_type'), ToolType):
            data['tool_type'] = data['tool_type'].value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ToolConfiguration':
        """Create from dictionary"""
        if isinstance(data.get('tool_type'), str):
            data['tool_type'] = ToolType(data['tool_type'])
        return cls(**data)
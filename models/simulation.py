"""
Simulation Model
Tracks simulation runs and metadata
"""
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class SimulationStatus(str, Enum):
    """Simulation execution status"""
    INITIALIZED = "initialized"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class Simulation(BaseModel):
    """
    Simulation run metadata
    Tracks a complete simulation instance
    """
    simulation_id: str = Field(description="Unique simulation identifier")
    plant_id: str = Field(description="Plant being simulated")
    profile_id: str = Field(description="Plant profile used")
    
    # Timing
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    current_hour: int = Field(default=0, description="Current simulation hour")
    target_hours: Optional[int] = Field(default=None, description="Planned duration")
    
    # Status
    status: SimulationStatus = Field(default=SimulationStatus.INITIALIZED)
    is_fast_forward: bool = Field(default=False, description="Running in fast-forward mode")
    
    # Configuration
    timestep_hours: float = Field(default=1.0, description="Always 1.0 hour per step")
    checkpoint_interval: int = Field(default=24, description="Save state every N hours")
    
    # Results summary
    final_biomass: Optional[float] = None
    final_damage: Optional[float] = None
    plant_survived: Optional[bool] = None
    total_actions_applied: int = Field(default=0)
    
    # Metadata
    description: Optional[str] = None
    created_by: str = Field(default="user")
    notes: Optional[str] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Firebase"""
        data = self.model_dump()
        # Convert datetime fields
        for field in ['start_time', 'end_time']:
            if data.get(field) and isinstance(data[field], datetime):
                data[field] = data[field].isoformat()
        # Convert enum
        if isinstance(data.get('status'), SimulationStatus):
            data['status'] = data['status'].value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Simulation':
        """Create from dictionary"""
        # Convert datetime fields
        for field in ['start_time', 'end_time']:
            if data.get(field) and isinstance(data[field], str):
                data[field] = datetime.fromisoformat(data[field])
        # Convert enum
        if isinstance(data.get('status'), str):
            data['status'] = SimulationStatus(data['status'])
        return cls(**data)
    
    def mark_completed(self, final_state: 'PlantState'):
        """Mark simulation as completed and record final state"""
        from .state import PlantState
        
        self.status = SimulationStatus.COMPLETED
        self.end_time = datetime.now()
        self.final_biomass = final_state.biomass
        self.final_damage = final_state.cumulative_damage
        self.plant_survived = final_state.is_alive
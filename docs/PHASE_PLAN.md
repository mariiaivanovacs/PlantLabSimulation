# 🌱 PLANT SIMULATOR - 3-PHASE IMPLEMENTATION PLAN

## Overview

This document outlines the complete 3-phase development plan for the Autonomous Plant Growth Simulator.

---

## ✅ PHASE 1: Core Foundation & Data Layer (COMPLETE)

**Goal**: Establish data models, database connectivity, and management tools

### Completed Components

#### 1. Data Models (`models/`)
- ✅ `state.py` - PlantState (complete state vector at time t)
- ✅ `plant_profile.py` - PlantProfile (species-specific parameters)
- ✅ `tools.py` - Tool definitions and action records
- ✅ `simulation.py` - Simulation metadata and tracking

#### 2. Database Layer (`database/`)
- ✅ `firebase_manager.py` - Firestore integration
  - Save/retrieve plant profiles
  - Simulation metadata management
  - State snapshot storage
  - Tool action logging
  - Query capabilities

#### 3. Default Data (`data/`)
- ✅ `default_plants.py` - Pre-configured plant profiles
  - Tomato (Solanum lycopersicum)
  - Lettuce (Lactuca sativa)
  - Basil (Ocimum basilicum)
- ✅ `initializer.py` - Data seeding and import/export utilities

#### 4. Configuration (`config/`)
- ✅ `settings.py` - Environment-based configuration
- ✅ `.env.example` - Configuration template

#### 5. CLI Interface (`cli/`)
- ✅ `commands.py` - Command-line interface
  - Setup commands (init, check)
  - Profile management (list, show, import, export, delete)
  - Simulation listing (preview)
  - Version info

#### 6. Documentation
- ✅ `README.md` - Comprehensive user guide
- ✅ `PHASE_PLAN.md` - This implementation roadmap
- ✅ `example.py` - Usage examples

### Deliverables

```
plant_simulator/
├── models/              # ✅ Complete data models
├── database/            # ✅ Firebase integration
├── data/                # ✅ Default plants & utilities
├── cli/                 # ✅ CLI interface
├── config/              # ✅ Configuration
├── main.py              # ✅ Entry point
├── example.py           # ✅ Examples
├── requirements.txt     # ✅ Dependencies
├── README.md            # ✅ Documentation
└── .env.example         # ✅ Config template
```

### Testing Phase 1

```bash
# Install dependencies
pip install -r requirements.txt --break-system-packages

# Run examples
python example.py

# Initialize database
python main.py setup init

# List profiles
python main.py profile list

# View profile details
python main.py profile show tomato_standard
```

---

## ⏳ PHASE 2: Physics Engine & Simulation Core (NEXT)

**Goal**: Implement core physics equations, tools, and hourly simulation loop

### Components to Build

#### 1. Physics Engine (`physics/`)

**File: `water_balance.py`**
```python
def calculate_ET(state: PlantState, profile: PlantProfile) -> float:
    """Calculate evapotranspiration for current hour"""
    # ET_base = 0.02 L/h/m² LAI
    # f_water, f_VPD calculations
    # Return ET in liters

def update_soil_water(state: PlantState, irrigation: float, ET: float) -> float:
    """Update soil water content"""
    # New water = current + irrigation - ET - drainage
    # Respect field capacity and saturation
```

**File: `growth.py`**
```python
def calculate_photosynthesis(state: PlantState, profile: PlantProfile) -> float:
    """Gross photosynthesis this hour"""
    # P_gross = LUE × PAR_absorbed × f_temp × f_nutrient

def calculate_respiration(biomass: float, r_base: float) -> float:
    """Maintenance respiration"""
    # R_maint = r_base × biomass

def update_biomass(state: PlantState, profile: PlantProfile) -> float:
    """Net biomass growth this hour"""
    # ΔBiomass = (P_gross - R_maint) × growth_factor
```

**File: `temperature.py`**
```python
def temperature_response(T: float, T_min: float, T_opt: float, T_max: float) -> float:
    """Cardinal temperature function"""
    # Quadratic or beta function
    # Returns f_temp (0-1)

def calculate_thermal_time(air_temp: float, soil_temp: float, T_base: float) -> float:
    """Growing degree hours"""
    # GDD = max(0, (air_temp + soil_temp)/2 - T_base)
```

**File: `damage.py`**
```python
def calculate_damage_rate(state: PlantState, profile: PlantProfile) -> float:
    """Damage accumulation this hour"""
    # Water stress damage
    # Temperature damage
    # Nutrient toxicity damage

def apply_damage(state: PlantState, damage_rate: float) -> PlantState:
    """Update cumulative damage and check death"""
    # Accumulate damage
    # Check if damage >= 95% → death
```

**File: `nutrients.py`**
```python
def calculate_uptake(delta_biomass: float, nutrient_ratios: dict) -> dict:
    """Calculate N-P-K uptake based on growth"""
    # uptake_N = ΔBiomass × N_ratio

def update_nutrient_pools(state: PlantState, uptake: dict) -> PlantState:
    """Deplete soil nutrients"""
```

**File: `phenology.py`**
```python
def check_stage_transition(thermal_time: float, biomass: float, 
                          thresholds: PhenologyThresholds) -> PhenologicalStage:
    """Determine phenological stage"""
```

#### 2. Tool Implementations (`tools/`)

**File: `watering.py`**
```python
class WateringTool:
    def apply(self, state: PlantState, action: WateringAction) -> PlantState:
        """Apply watering action to state"""
        # Add water respecting flow rate
        # Update soil_water
        # Check for runoff
```

**File: `lighting.py`**
```python
class LightingTool:
    def apply(self, state: PlantState, action: LightingAction) -> PlantState:
        """Set lighting parameters"""
        # Update light_PAR
        # Calculate heat contribution
```

**File: `nutrients.py`** (tools)
```python
class NutrientTool:
    def apply(self, state: PlantState, action: NutrientAction) -> PlantState:
        """Dose nutrients"""
        # Add N-P-K to soil
        # Update EC
```

**File: `hvac.py`**
```python
class HVACTool:
    def apply(self, state: PlantState, action: HVACAction) -> PlantState:
        """Control temperature"""
        # Adjust air_temp toward target
        # Respect max rate
```

**File: `humidity.py`**
```python
class HumidityTool:
    def apply(self, state: PlantState, action: HumidityAction) -> PlantState:
        """Control humidity"""
        # Adjust RH toward target
        # Recalculate VPD
```

**File: `ventilation.py`**
```python
class VentilationTool:
    def apply(self, state: PlantState, action: VentilationAction) -> PlantState:
        """Ventilation/air exchange"""
        # Mix indoor/outdoor air
```

#### 3. Simulation Engine (`engine/`)

**File: `simulator.py`**
```python
class PlantSimulator:
    def __init__(self, simulation_id: str, profile: PlantProfile, 
                 initial_state: PlantState):
        """Initialize simulator"""
    
    def step(self, scheduled_actions: List[ToolAction]) -> PlantState:
        """Execute one hour timestep"""
        # 1. Apply scheduled tool actions
        # 2. Update physics (water, growth, temp, damage)
        # 3. Update nutrients
        # 4. Check phenology
        # 5. Save state snapshot
        # 6. Return new state
    
    def run(self, hours: int, action_schedule: List[ToolAction]) -> List[PlantState]:
        """Run simulation for N hours"""
        # Loop: call step() each hour
        # Return history
```

#### 4. Integration

**File: `engine/coordinator.py`**
```python
class SimulationCoordinator:
    def create_simulation(self, profile_id: str, initial_conditions: dict) -> str:
        """Create new simulation"""
    
    def schedule_action(self, simulation_id: str, hour: int, 
                       tool_type: ToolType, params: dict):
        """Schedule a tool action"""
    
    def run_simulation(self, simulation_id: str, target_hours: int):
        """Execute simulation"""
```

### Phase 2 CLI Commands (New)

```bash
# Create new simulation
python main.py simulation create --profile tomato_standard --hours 168

# Schedule a watering action
python main.py simulation schedule-action <sim_id> \
    --hour 24 --tool watering --volume 2.0

# Run simulation
python main.py simulation run <sim_id>

# Get current state
python main.py simulation state <sim_id> --hour 72
```

### Phase 2 Testing

```python
# Test scenario: Plant dies without water
sim = create_simulation("tomato_standard", hours=168)
# Don't schedule any watering
run_simulation(sim.simulation_id)
# Should show: damage ~100%, is_alive=False

# Test scenario: Plant survives with regular watering
sim2 = create_simulation("tomato_standard", hours=168)
schedule_action(sim2, hour=0, tool=watering, volume=3.0)
schedule_action(sim2, hour=48, tool=watering, volume=3.0)
schedule_action(sim2, hour=96, tool=watering, volume=3.0)
schedule_action(sim2, hour=144, tool=watering, volume=3.0)
run_simulation(sim2.simulation_id)
# Should show: damage <20%, is_alive=True
```

### Success Criteria for Phase 2

- ✅ Plant dies in 7-14 days without watering
- ✅ All 6 tools can be applied and affect state correctly
- ✅ Growth equations produce realistic biomass curves
- ✅ Temperature outside range causes damage
- ✅ Can run 168-hour simulation and query any hour
- ✅ Damage accumulates under stress, recovers under good conditions

---

## ⏳ PHASE 3: API, Time Acceleration & Integration (FINAL)

**Goal**: REST API, fast-forward simulation, and production readiness

### Components to Build

#### 1. REST API (`api/`)

**File: `main.py`** (FastAPI)
```python
from fastapi import FastAPI

app = FastAPI(title="Plant Simulator API")

# Profile endpoints
@app.get("/api/profiles")
async def list_profiles() -> List[PlantProfile]:
    """List all plant profiles"""

@app.post("/api/profiles")
async def create_profile(profile: PlantProfile):
    """Create new profile"""

# Simulation endpoints
@app.post("/api/simulations")
async def create_simulation(request: CreateSimulationRequest):
    """Start new simulation"""

@app.post("/api/simulations/{sim_id}/actions")
async def schedule_action(sim_id: str, action: ToolAction):
    """Schedule tool action"""

@app.post("/api/simulations/{sim_id}/run")
async def run_simulation(sim_id: str, hours: int):
    """Run simulation"""

@app.get("/api/simulations/{sim_id}/state")
async def get_state(sim_id: str, hour: int):
    """Get state at specific hour"""

@app.get("/api/simulations/{sim_id}/history")
async def get_history(sim_id: str, start_hour: int, end_hour: int):
    """Get state history"""
```

#### 2. Fast-Forward System (`engine/fast_forward.py`)

```python
def simulate_forward(
    initial_state: PlantState,
    profile: PlantProfile,
    target_hours: int,
    actions_list: List[ToolAction],
    checkpoint_interval: int = 24
) -> Tuple[PlantState, List[PlantState]]:
    """
    Run many hours quickly in background
    - No rate scaling (always Δt = 1 hour)
    - Save checkpoints every N hours
    - Return final state + history
    """
    current_hour = 0
    state = initial_state.copy()
    history = []
    
    while current_hour < target_hours:
        # Get actions scheduled for this hour
        hour_actions = [a for a in actions_list if a.scheduled_hour == current_hour]
        
        # Run physics for 1 hour
        state = simulator.step(state, hour_actions)
        
        # Save checkpoint
        if current_hour % checkpoint_interval == 0:
            history.append(state.copy())
            db_manager.save_plant_state(state)
        
        current_hour += 1
    
    return state, history
```

#### 3. Checkpoint System

```python
class CheckpointManager:
    def save_checkpoint(self, simulation_id: str, hour: int, state: PlantState):
        """Save state snapshot"""
    
    def load_checkpoint(self, simulation_id: str, hour: int) -> PlantState:
        """Load state from specific hour"""
    
    def get_nearest_checkpoint(self, simulation_id: str, target_hour: int) -> Tuple[int, PlantState]:
        """Get closest saved checkpoint"""
```

#### 4. Query System

```python
def query_state_at_hour(simulation_id: str, hour: int) -> PlantState:
    """
    Get state at any hour:
    1. Check if exact checkpoint exists
    2. If not, load nearest earlier checkpoint
    3. Simulate forward to target hour
    """
```

### Phase 3 API Endpoints

```bash
# Start API server
uvicorn api.main:app --reload

# API Examples
curl -X POST http://localhost:8000/api/simulations \
  -H "Content-Type: application/json" \
  -d '{"profile_id": "tomato_standard", "target_hours": 168}'

curl -X POST http://localhost:8000/api/simulations/{sim_id}/run

curl http://localhost:8000/api/simulations/{sim_id}/state?hour=72
```

### Phase 3 Features

- **Fast-Forward**: Run 1000+ hours in seconds
- **Time Travel**: Query state at any past hour
- **Webhooks**: Notify when simulation completes
- **Batch**: Run multiple simulations in parallel
- **Export**: Download complete simulation data

### Success Criteria for Phase 3

- ✅ API serves all core functionality
- ✅ Can fast-forward 1 week (168 hours) in <2 seconds
- ✅ Can query any hour from checkpoint system
- ✅ WebSocket support for real-time updates
- ✅ Complete API documentation
- ✅ Production-ready deployment config

---

## Development Timeline

| Phase | Duration | Status |
|-------|----------|--------|
| Phase 1 | 2-3 days | ✅ COMPLETE |
| Phase 2 | 4-5 days | ⏳ PENDING |
| Phase 3 | 3-4 days | ⏳ PENDING |
| **Total** | **~10 days** | **33% Complete** |

---

## Integration Testing (All Phases)

### End-to-End Test Scenario

```python
# 1. Load tomato profile (Phase 1)
profile = db_manager.get_plant_profile("tomato_standard")

# 2. Create simulation (Phase 2)
sim = create_simulation(profile_id="tomato_standard", hours=336)  # 2 weeks

# 3. Schedule automated care
schedule_watering_every(sim.id, interval_hours=48, volume=3.0)
schedule_lighting(sim.id, PAR=600, start_hour=8, duration=16)
schedule_hvac(sim.id, target_temp=24)

# 4. Run fast-forward (Phase 3)
final_state, history = simulate_forward(
    sim.id, 
    target_hours=336,
    checkpoint_interval=24
)

# 5. Analyze results
assert final_state.is_alive == True
assert final_state.cumulative_damage < 30
assert final_state.biomass > 50.0

# 6. Query specific moments
day3_state = query_state_at_hour(sim.id, hour=72)
day7_state = query_state_at_hour(sim.id, hour=168)
```

---

## Next Steps

**To continue to Phase 2:**
```bash
# User says: "Proceed with Phase 2"
# Then implement:
1. Physics engine (water, growth, temperature, damage)
2. All 6 tool implementations
3. Simulation loop
4. Updated CLI commands
```

**To skip to Phase 3:**
```bash
# User says: "Skip to Phase 3"
# (Requires Phase 2 complete first)
```

---

**Current Status**: ✅ Phase 1 Complete, Ready for Phase 2

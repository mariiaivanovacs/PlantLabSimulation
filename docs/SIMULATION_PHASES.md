# Plant Simulation Implementation Phases

## Overview

This document defines the two-phase implementation plan for the plant life simulation
physics engine. All mechanisms are based on the equations from `plant_simulator_focused_implementation.pdf`.

---

## PHASE 1: Core Physics Engine (Current Implementation)

**Goal**: Create a standalone simulation that can run without the Flask app, displaying
plant metrics every 5 seconds in the terminal.

### 1.1 Water Balance System

**Files**: `physics/water_balance.py`

**Equations**:
```
soil_water(t+1h) = soil_water(t) + irrigation - ET×1h - drainage×1h
```

**ET (Evapotranspiration) Calculation**:
```python
ET_base = 0.02  # L/h/m² LAI (baseline rate)
ET_pot = ET_base × leaf_area × (1 + 0.001 × light_PAR)
f_water = max(0, min(1, (soil_water - wilting_point) / (field_capacity - wilting_point)))
f_VPD = 0.5 + 0.5 × min(1, VPD / 1.2)  # optimal VPD ≈ 1.2 kPa
ET = ET_pot × f_water × f_VPD
```

**Drainage Calculation**:
```python
if soil_water > field_capacity:
    drainage = 0.5 × (soil_water - field_capacity)  # 50% drains per hour
else:
    drainage = 0
```

**Constraints**:
```python
soil_water = clamp(soil_water, 0, saturation)
```

---

### 1.2 Temperature Response System

**Files**: `physics/temperature.py`

**Cardinal Temperature Model** (quadratic approximation):
```python
# Define: T_min, T_opt, T_max from plant profile
if T < T_min or T > T_max:
    f_temp = 0  # no growth
elif T_min <= T <= T_opt:
    f_temp = ((T - T_min) / (T_opt - T_min))²
elif T_opt < T <= T_max:
    f_temp = ((T_max - T) / (T_max - T_opt))²
```

**VPD Calculation** (automatic):
```python
SVP = 0.6108 × exp(17.27 × air_temp / (air_temp + 237.3))
VPD = SVP × (1 - relative_humidity/100)
```

**Thermal Time (Growing Degree Hours)**:
```python
GDD = max(0, (air_temp + soil_temp)/2 - T_base)  # T_base typically 10°C
thermal_time(t+1h) = thermal_time(t) + GDD × 1h
```

---

### 1.3 Plant Growth System

**Files**: `physics/growth.py`

**Step 1: Photosynthetic Production**
```python
P_gross = LUE × PAR_absorbed × f_temp × f_nutrient
```
Where:
- `LUE = 0.003 g/µmol` (light use efficiency from profile)
- `PAR_absorbed = light_PAR × leaf_area × 1h × 3600 s/h`
- `f_temp`: temperature response function (Section 1.2)
- `f_nutrient = min(f_N, f_P, f_K)` where `f_X = min(1, soil_X / optimal_X)`

**Step 2: Maintenance Respiration**
```python
R_maint = r_base × biomass
```
Where `r_base = 0.000625 g/g/h` (1.5%/day)

**Step 3: Net Growth with Stress**
```python
growth_factor = (1 - water_stress) × (1 - 0.01 × cumulative_damage)
Δbiomass = max(0, (P_gross - R_maint) × growth_factor)
biomass(t+1h) = biomass(t) + Δbiomass
```

**Leaf Area Update**:
```python
leaf_area = α × biomass  # α = 0.004 m²/g (from profile.growth.leaf_area_ratio)
```

---

### 1.4 Nutrient Uptake & Depletion

**Files**: `physics/nutrients.py`

**Nutrient Consumption** (proportional to growth):
```python
uptake_N = Δbiomass × N_demand_ratio  # e.g., 0.03 g N / g biomass
uptake_P = Δbiomass × P_demand_ratio  # e.g., 0.005 g P / g biomass
uptake_K = Δbiomass × K_demand_ratio  # e.g., 0.02 g K / g biomass

soil_N -= uptake_N
soil_P -= uptake_P
soil_K -= uptake_K
```

**EC Calculation**:
```python
soil_EC = 0.001 × (soil_N + soil_P + soil_K)  # approximation
```

**Nutrient Stress Factor**:
```python
f_N = min(1, soil_N / optimal_N)
f_P = min(1, soil_P / optimal_P)
f_K = min(1, soil_K / optimal_K)
nutrient_stress = 1 - min(f_N, f_P, f_K)
```

---

### 1.5 Damage Accumulation & Death Mechanics (CRITICAL)

**Files**: `physics/damage.py`

**Damage Accumulation Rules** (each hour):
```python
damage_rate = 0  # initialize

# Source 1: Water stress
if soil_water < wilting_point:
    damage_rate += 5.0  # 5% damage per hour when wilting
elif soil_water > saturation × 0.95:  # waterlogged
    damage_rate += 2.0  # 2% damage per hour (root hypoxia)

# Source 2: Temperature extremes
if air_temp < T_min:
    damage_rate += 3.0 × (T_min - air_temp) / 5  # cold damage
elif air_temp > T_max:
    damage_rate += 3.0 × (air_temp - T_max) / 5  # heat damage

# Source 3: Nutrient toxicity
if soil_EC > 3.5:  # excessive salts
    damage_rate += 1.5  # 1.5% per hour

# Update damage
cumulative_damage(t+1h) = cumulative_damage(t) + damage_rate
cumulative_damage = clamp(cumulative_damage, 0, 100)
```

**Damage Recovery** (slow healing when conditions favorable):
```python
if water_stress < 0.3 AND temp_stress < 0.2 AND nutrient_stress < 0.3:
    cumulative_damage -= 0.5  # recover 0.5% per hour
```

**Growth Penalty from Damage**:
```python
max_biomass_effective = max_biomass × (1 - 0.005 × cumulative_damage)
if biomass > max_biomass_effective:
    biomass = max_biomass_effective  # cap growth
```

**Death Condition**:
```python
if cumulative_damage >= 95%:
    is_alive = False
    phenological_stage = DEAD
    # Biomass begins to decay
    biomass -= 0.01 × biomass  # 1% decay per hour
```

**Example Timeline Without Care**:
- Hour 0: soil_water = 30%, damage = 0%
- Hour 24: soil_water = 15% (wilting point), damage = 0%
- Hour 48: soil_water = 10%, damage starts accumulating (5%/h)
- Hour 168 (7 days): damage approaches 100%, plant dies

---

### 1.6 Stress Factor Calculations

**Water Stress**:
```python
if soil_water < wilting_point:
    water_stress = 1.0
elif soil_water < optimal_min:
    water_stress = (optimal_min - soil_water) / (optimal_min - wilting_point)
elif soil_water > optimal_max:
    water_stress = (soil_water - optimal_max) / (saturation - optimal_max)
else:
    water_stress = 0.0
```

**Temperature Stress**:
```python
if air_temp < T_min or air_temp > T_max:
    temp_stress = 1.0
elif air_temp < T_opt:
    temp_stress = 1 - ((air_temp - T_min) / (T_opt - T_min))
else:
    temp_stress = 1 - ((T_max - air_temp) / (T_max - T_opt))
temp_stress = max(0, temp_stress)
```

---

### 1.7 Simulation Engine

**Files**: `models/engine.py`

**1-Hour Timestep Loop**:
```python
def step(self, hours=1):
    for _ in range(hours):
        if not self.state.is_alive:
            self._decay_biomass()
            continue

        # 1. Calculate environmental factors
        self._update_vpd()

        # 2. Calculate stress factors
        self._calculate_stresses()

        # 3. Update water balance
        self._update_water_balance()

        # 4. Update growth
        self._update_growth()

        # 5. Update nutrients
        self._update_nutrients()

        # 6. Calculate and apply damage
        self._update_damage()

        # 7. Update thermal time
        self._update_thermal_time()

        # 8. Check death condition
        self._check_death()

        # 9. Increment hour counter
        self.state.hour += 1
```

---

### 1.8 Standalone Runner

**Files**: `run_simulation.py`

**Features**:
- Select plant from default profiles (tomato, lettuce, basil)
- Run simulation in real-time with 1-hour timesteps
- Display metrics every 5 seconds in terminal
- Show: biomass, leaf_area, soil_water, damage, stress levels, is_alive

---

## PHASE 2: Tools & Advanced Features (Future Implementation)

**Goal**: Add autonomous tools and advanced features like fast-forward.

### 2.1 Autonomous Tools (6 Tools)

| Tool | Primary Parameters | Secondary Effects |
|------|-------------------|-------------------|
| **Watering** | soil_moisture (direct) | stress ↓, growth ↑, damage ↓ (recovery) |
| **Lighting** | light_PAR (direct) | biomass ↑, ET ↑, air_temp ↑ (heat from lights) |
| **Nutrients** | soil_N, soil_P, soil_K, soil_EC (direct) | growth_efficiency ↑, stress ↓ |
| **Temperature (HVAC)** | air_temp (direct) | f_temp affects growth, ET ↑/↓, damage if extreme |
| **Humidity** | relative_humidity (direct) | VPD ↑/↓ (calculated), ET ↑/↓ |
| **Ventilation** | relative_humidity, air_temp (modulation) | Cools air, reduces RH |

### 2.2 Tool Implementation Details

**Watering System**:
```python
actual_added = min(volume_L, flow_rate_L_per_h × 1h)
soil_water_new = soil_water + (actual_added / pot_volume) × 100
if soil_water_new > saturation:
    runoff = soil_water_new - saturation
soil_water = min(soil_water_new, saturation)
```

**Lighting System**:
```python
light_PAR = target_PAR
heat_added = power_W × 0.7 × 1h / (room_volume × air_heat_capacity)
air_temp += heat_added
```

**HVAC System**:
```python
temp_error = target_temp_C - air_temp
temp_change = clamp(temp_error, -max_rate_C_per_h, max_rate_C_per_h)
air_temp += temp_change
soil_temp += 0.2 × temp_change  # soil lags behind air
```

### 2.3 Fast-Forward System

```python
def simulate_forward(target_hours, actions_list):
    current_hour = 0
    state = current_state.copy()
    history = []  # store checkpoints

    while current_hour < target_hours:
        # Apply scheduled actions
        for action in actions_list:
            if action.scheduled_hour == current_hour:
                apply_action(state, action)

        # Run physics update
        update_water_balance(state, dt=1h)
        update_growth(state, dt=1h)
        update_damage(state, dt=1h)
        update_thermal_time(state, dt=1h)

        # Save checkpoint
        history.append(state.copy())
        current_hour += 1

    return state, history
```

### 2.4 Phenological Stage Transitions

```python
# Stage transitions based on thermal time:
# seed → seedling: thermal_time > 50°C·h AND biomass > 0.1g
# seedling → vegetative: thermal_time > 500°C·h
# vegetative → flowering: thermal_time > 2000°C·h
# flowering → fruiting: thermal_time > 3500°C·h
# fruiting → mature: thermal_time > 5000°C·h
```

### 2.5 Firebase Integration
- Hourly state snapshots saved to Firebase
- Checkpoint history for replay
- Profile management

### 2.6 Agent Planning & Execution
- Rule-based decision algorithms
- Autonomous tool scheduling
- Memory and learning from history

---

## Success Criteria

### Phase 1 Complete When:
- [ ] Running 168 hours (1 week) with no actions → plant dies (damage >95%)
- [ ] Soil moisture decreases over time due to ET
- [ ] Biomass stops growing under stress conditions
- [ ] Temperature outside [T_min, T_max] causes damage accumulation
- [ ] Nutrient depletion slows growth
- [ ] Terminal displays metrics every 5 seconds

### Phase 2 Complete When:
- [ ] All 6 tools can modify environment/soil state
- [ ] Fast-forward to 1 week completes in <2 seconds
- [ ] Applying watering at hour 72 revives plant
- [ ] Can query state at any past hour from checkpoint history
- [ ] Firebase persistence working

---

## File Structure After Implementation

```
PlantLabSimulation/
├── models/
│   ├── __init__.py
│   ├── state.py           # PlantState (existing)
│   ├── plant_profile.py   # PlantProfile (existing)
│   ├── engine.py          # SimulationEngine (Phase 1)
│   └── ...
├── physics/               # NEW - Phase 1
│   ├── __init__.py
│   ├── water_balance.py   # ET, drainage, soil moisture
│   ├── temperature.py     # Cardinal temp, VPD, thermal time
│   ├── growth.py          # Photosynthesis, respiration, biomass
│   ├── damage.py          # Stress, damage accumulation, death
│   └── nutrients.py       # Uptake, depletion, EC
├── tools/                 # Phase 2
│   ├── __init__.py
│   ├── watering.py
│   ├── lighting.py
│   ├── nutrients.py
│   ├── hvac.py
│   ├── humidity.py
│   └── ventilation.py
├── data/
│   └── default_plants.py  # (existing)
└── run_simulation.py      # NEW - Standalone runner (Phase 1)
```

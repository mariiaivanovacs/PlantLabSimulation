# 🌱 RGR and Logistic Growth Implementation

## Overview

Added **Relative Growth Rate (RGR)** tracking and **logistic growth constraints** to make plant growth more biologically realistic.

---

## 📊 New Metrics

### 1. **Relative Growth Rate (RGR)**

**Formula:** `RGR = (1/B) · dB/dt`

**Meaning:** Growth rate relative to current size (units: 1/hour or %/day)

**Interpretation:**
- **High RGR (>0.1/h or >240%/day)**: Exponential growth phase (seedlings)
- **Medium RGR (0.01-0.1/h or 24-240%/day)**: Active growth
- **Low RGR (<0.01/h or <24%/day)**: Approaching saturation
- **Negative RGR**: Losing biomass (night, stress)

**Example:**
```
Biomass = 10g
Growth = 2g/h
RGR = (2/1) / 10 = 0.2 /h = 480% per day
```

---

### 2. **Doubling Time (T_d)**

**Formula:** `T_d = ln(2) / RGR`

**Meaning:** Time for biomass to double at current growth rate

**Interpretation:**
- **Short doubling time (<24h)**: Rapid exponential growth
- **Medium doubling time (24-168h)**: Healthy growth
- **Long doubling time (>168h)**: Slow growth, approaching max
- **Infinite**: Not growing (RGR ≤ 0)

**Example:**
```
RGR = 0.05 /h
T_d = ln(2) / 0.05 = 13.9 hours
```

---

### 3. **Growth Saturation (B/K)**

**Formula:** `Saturation = B / K`

**Meaning:** How close plant is to maximum size

**Interpretation:**
- **0-30%**: Early growth, minimal saturation
- **30-70%**: Active growth, moderate saturation
- **70-100%**: Approaching maximum, high saturation

---

## 🔬 Logistic Growth Model

### Why Logistic Growth?

**Problem with exponential growth:**
- Early simulation used: `dB/dt = r·B` (exponential)
- This causes unrealistic infinite growth
- Real plants have genetic maximum size (K)

**Logistic growth solution:**
```
dB/dt = r·B·(1 - B/K)
```

Where:
- `r` = intrinsic growth rate
- `B` = current biomass
- `K` = carrying capacity (max_biomass)
- `(1 - B/K)` = saturation factor

### How It Works

**Early growth (B << K):**
```
B = 1g, K = 300g
Saturation factor = 1 - (1/300) = 0.997 ≈ 1.0
Growth ≈ exponential (minimal constraint)
```

**Mid growth (B ≈ K/2):**
```
B = 150g, K = 300g
Saturation factor = 1 - (150/300) = 0.5
Growth reduced by 50%
```

**Near maximum (B → K):**
```
B = 290g, K = 300g
Saturation factor = 1 - (290/300) = 0.033
Growth reduced by 97% (almost stopped)
```

---

## 💻 Implementation

### 1. **Updated `models/state.py`**

Added new fields to `PlantState`:
```python
RGR: float = Field(default=0, description="Relative Growth Rate (1/h)")
doubling_time: float = Field(default=float('inf'), description="Doubling time (hours)")
growth_saturation: float = Field(default=0, description="Growth saturation (0-1)")
```

### 2. **Added functions to `physics/growth.py`**

**New functions:**
- `calculate_RGR(biomass, delta_biomass, dt)` - Calculate RGR
- `calculate_doubling_time(RGR)` - Calculate T_d from RGR
- `calculate_growth_saturation(biomass, max_biomass)` - Calculate B/K
- `apply_logistic_growth_factor(delta_biomass, biomass, max_biomass)` - Apply logistic constraint

### 3. **Updated `models/engine.py`**

**In `_update_growth()` method:**
```python
# Calculate unconstrained growth
delta_biomass = calculate_growth(...)

# Apply logistic constraint
delta_biomass_constrained = apply_logistic_growth_factor(
    delta_biomass,
    self.state.biomass,
    self.plant_profile.growth.max_biomass
)

# Update biomass with constrained value
self.state.biomass, actual_change = update_biomass(
    self.state.biomass,
    delta_biomass_constrained,  # Use constrained!
    ...
)

# Calculate metrics
self.state.RGR = calculate_RGR(self.state.biomass, actual_change, dt=1.0)
self.state.doubling_time = calculate_doubling_time(self.state.RGR)
self.state.growth_saturation = calculate_growth_saturation(...)
```

### 4. **Updated `run_simulation.py` display**

Added new section showing:
- RGR (in /h and %/day)
- Doubling time (in hours and days)
- Saturation (color-coded: green < 30%, yellow < 70%, red ≥ 70%)

---

## 📈 Expected Behavior

### Seedling (0.05g → 1g)
```
RGR: ~0.1-0.2 /h (240-480% per day)
Doubling time: 3-7 hours
Saturation: <1% (minimal constraint)
Growth: Nearly exponential
```

### Young plant (1g → 50g)
```
RGR: ~0.02-0.05 /h (48-120% per day)
Doubling time: 14-35 hours
Saturation: 1-17% (slight constraint)
Growth: Rapid but slowing
```

### Mature plant (50g → 200g)
```
RGR: ~0.005-0.01 /h (12-24% per day)
Doubling time: 70-140 hours
Saturation: 17-67% (moderate constraint)
Growth: Steady decline
```

### Near maximum (200g → 300g)
```
RGR: ~0.001-0.002 /h (2-5% per day)
Doubling time: 350-700 hours
Saturation: 67-100% (strong constraint)
Growth: Very slow, approaching zero
```

---

## ✅ Benefits

1. **Realistic growth curves**: S-shaped (sigmoid) instead of exponential
2. **Prevents overgrowth**: Plants can't exceed genetic maximum
3. **Better predictions**: RGR and doubling time help predict growth timeline
4. **Resource planning**: Know when growth will slow, optimize inputs
5. **Biological accuracy**: Matches real plant growth patterns

---

## 🧪 Testing

Run simulation and observe:
```bash
cd PlantLabSimulation
source venv/bin/activate
python run_simulation.py --plant lettuce --hours 720  # 30 days
```

Watch for:
- High RGR early (>100%/day)
- Decreasing RGR as plant grows
- Saturation increasing toward 100%
- Growth slowing as saturation increases
- Biomass approaching but not exceeding max_biomass


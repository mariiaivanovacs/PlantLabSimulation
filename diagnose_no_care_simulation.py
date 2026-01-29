#!/usr/bin/env python3
"""
Diagnostic script to run a simulation without care and log all metrics
This will help identify why stress levels are not realistic
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.default_plants import get_tomato_profile
from models.engine import SimulationEngine
import csv

def run_diagnostic_simulation(hours=168):  # 7 days
    """Run simulation without any care and log everything"""
    
    profile = get_tomato_profile()
    engine = SimulationEngine(profile)
    
    # Disable daily regime (no automatic watering/care)
    engine.set_daily_regime(enabled=False)
    
    print("=" * 100)
    print("DIAGNOSTIC SIMULATION: NO CARE FOR 7 DAYS")
    print("=" * 100)
    print(f"Plant: {profile.species_name}")
    print(f"Initial soil water: {engine.state.soil_water}%")
    print(f"Wilting point: {profile.water.wilting_point}%")
    print(f"Optimal range: {profile.water.optimal_range_min}% - {profile.water.optimal_range_max}%")
    print()
    
    # Prepare CSV output
    csv_file = 'data/records/diagnostic_no_care.csv'
    with open(csv_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Hour', 'Day', 'Biomass_g', 'Leaf_Area_m2', 'Phenological_Stage',
            'Soil_Water_%', 'Water_Stress', 'ET_L/h',
            'Air_Temp_C', 'Temp_Stress',
            'Soil_N_ppm', 'Soil_P_ppm', 'Soil_K_ppm', 'Nutrient_Stress',
            'Cumulative_Damage_%', 'Is_Alive',
            'Photosynthesis_g/h', 'Respiration_g/h', 'Growth_Rate_g/h',
            'CO2_ppm', 'Light_PAR'
        ])
        
        # Log initial state
        s = engine.state
        writer.writerow([
            s.hour, s.hour/24, s.biomass, s.leaf_area, s.phenological_stage.value,
            s.soil_water, s.water_stress, s.ET,
            s.air_temp, s.temp_stress,
            s.soil_N, s.soil_P, s.soil_K, s.nutrient_stress,
            s.cumulative_damage, s.is_alive,
            s.photosynthesis, s.respiration, s.growth_rate,
            s.CO2, s.light_PAR
        ])
        
        # Run simulation
        for hour in range(1, hours + 1):
            engine.step(hours=1, irrigation=0.0)  # NO WATERING
            
            s = engine.state
            writer.writerow([
                s.hour, s.hour/24, s.biomass, s.leaf_area, s.phenological_stage.value,
                s.soil_water, s.water_stress, s.ET,
                s.air_temp, s.temp_stress,
                s.soil_N, s.soil_P, s.soil_K, s.nutrient_stress,
                s.cumulative_damage, s.is_alive,
                s.photosynthesis, s.respiration, s.growth_rate,
                s.CO2, s.light_PAR
            ])
            
            # Print daily summary
            if hour % 24 == 0:
                day = hour // 24
                print(f"Day {day:2d}: "
                      f"Soil Water={s.soil_water:5.1f}% (stress={s.water_stress:5.3f}), "
                      f"Temp={s.air_temp:5.1f}°C (stress={s.temp_stress:5.3f}), "
                      f"Nutrients={s.soil_N:5.0f}/{s.soil_P:4.0f}/{s.soil_K:5.0f} (stress={s.nutrient_stress:5.3f}), "
                      f"Damage={s.cumulative_damage:5.1f}%, "
                      f"Alive={s.is_alive}")
    
    print()
    print("=" * 100)
    print(f"Simulation complete. Results saved to: {csv_file}")
    print("=" * 100)
    print()
    
    # Final summary
    s = engine.state
    print("FINAL STATE:")
    print(f"  Soil Water:      {s.soil_water:8.2f}% (should be near 0%)")
    print(f"  Water Stress:    {s.water_stress:8.3f} (should be 1.0)")
    print(f"  Temp Stress:     {s.temp_stress:8.3f}")
    print(f"  Nutrient Stress: {s.nutrient_stress:8.3f}")
    print(f"  Cumulative Damage: {s.cumulative_damage:6.1f}%")
    print(f"  Is Alive:        {s.is_alive}")
    print(f"  Biomass:         {s.biomass:8.2f} g")
    print()
    
    # Analysis
    print("ANALYSIS:")
    if s.soil_water > 5:
        print(f"  ❌ PROBLEM: Soil water is {s.soil_water:.1f}% after 7 days without watering!")
        print(f"     Expected: Near 0%")
        print(f"     This suggests ET calculations are too low or water balance is broken")
    else:
        print(f"  ✓ Soil water depleted correctly")
    
    if s.water_stress < 0.9:
        print(f"  ❌ PROBLEM: Water stress is only {s.water_stress:.3f} with {s.soil_water:.1f}% soil water!")
        print(f"     Expected: 1.0 (maximum stress)")
        print(f"     This suggests stress calculation is broken")
    else:
        print(f"  ✓ Water stress calculated correctly")
    
    if s.cumulative_damage < 50 and s.soil_water < profile.water.wilting_point:
        print(f"  ❌ PROBLEM: Cumulative damage is only {s.cumulative_damage:.1f}% despite severe water stress!")
        print(f"     Expected: >50% after days of wilting")
        print(f"     This suggests damage accumulation is broken")
    else:
        print(f"  ✓ Damage accumulation working")
    
    if s.is_alive and s.cumulative_damage > 95:
        print(f"  ❌ PROBLEM: Plant is still alive with {s.cumulative_damage:.1f}% damage!")
        print(f"     Expected: Dead at 95% damage")
        print(f"     This suggests death check is broken")
    
    print()
    return csv_file

if __name__ == "__main__":
    csv_file = run_diagnostic_simulation(hours=168)
    print(f"\nTo analyze results, open: {csv_file}")
    print("Look for columns: Soil_Water_%, Water_Stress, Cumulative_Damage_%, Is_Alive")


#!/usr/bin/env python3
"""
Diagnose why damage is not accumulating after 8 days without care
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from physics.damage import calculate_damage_rate, apply_damage, check_death
from physics.water_balance import calculate_et, calculate_vpd
from data.default_plants import get_tomato_profile

def test_damage_accumulation():
    """Test damage accumulation at different soil water levels"""
    profile = get_tomato_profile()
    
    print("=" * 80)
    print("DAMAGE ACCUMULATION TEST")
    print("=" * 80)
    
    # Test at different soil water levels
    test_cases = [
        ("Well above wilting point", 25.0),
        ("Just above wilting point", 16.0),
        ("At wilting point + 0.5", 15.5),
        ("At wilting point", 15.0),
        ("Below wilting point", 14.5),
        ("Well below wilting point", 10.0),
        ("Very dry", 5.0),
    ]
    
    for label, soil_water in test_cases:
        damage_rate, breakdown = calculate_damage_rate(
            soil_water=soil_water,
            air_temp=25.0,
            soil_EC=1.5,
            wilting_point=profile.water.wilting_point,
            saturation=profile.water.saturation,
            T_min=profile.temperature.T_min,
            T_max=profile.temperature.T_max
        )
        
        print(f"\n{label} (soil_water={soil_water}%):")
        print(f"  Wilting point: {profile.water.wilting_point}%")
        print(f"  Damage rate: {damage_rate:.2f}% per hour")
        print(f"  Breakdown: {breakdown}")
        
        if damage_rate > 0:
            hours_to_death = 95 / damage_rate
            print(f"  Hours to death (95% damage): {hours_to_death:.1f} hours ({hours_to_death/24:.1f} days)")

def simulate_8_days_no_care():
    """Simulate 8 days without care and track damage"""
    profile = get_tomato_profile()
    
    print("\n" + "=" * 80)
    print("8-DAY NO-CARE SIMULATION - DAMAGE TRACKING")
    print("=" * 80)
    
    # Initial conditions
    soil_water = 35.0  # %
    cumulative_damage = 0.0
    biomass = 0.5
    leaf_area = 0.002
    pot_volume = 5.0  # L
    
    VPD = calculate_vpd(25, 60)
    
    print(f"\nInitial conditions:")
    print(f"  Soil water: {soil_water}%")
    print(f"  Wilting point: {profile.water.wilting_point}%")
    print(f"  Cumulative damage: {cumulative_damage}%")
    print(f"  Biomass: {biomass}g")
    print(f"  Leaf area: {leaf_area}m²")
    
    print(f"\n{'Hour':<6} {'Day':<6} {'Soil H2O':<10} {'Damage Rate':<12} {'Cumul. Dmg':<12} {'Status':<10}")
    print("-" * 80)
    
    for hour in range(24 * 8 + 1):  # 8 days
        day = hour / 24
        
        # Calculate ET and update soil water
        if hour > 0:
            ET = calculate_et(
                leaf_area,
                600,  # PAR
                soil_water,
                VPD,
                profile.water.wilting_point,
                profile.water.field_capacity
            )
            
            # Update soil water
            water_loss_percent = (ET / pot_volume) * 100
            soil_water = max(0, soil_water - water_loss_percent)
        
        # Calculate damage rate
        damage_rate, breakdown = calculate_damage_rate(
            soil_water=soil_water,
            air_temp=25.0,
            soil_EC=1.5,
            wilting_point=profile.water.wilting_point,
            saturation=profile.water.saturation,
            T_min=profile.temperature.T_min,
            T_max=profile.temperature.T_max
        )
        
        # Apply damage
        if hour > 0:
            cumulative_damage = apply_damage(cumulative_damage, damage_rate)
        
        # Check death
        is_dead = check_death(cumulative_damage)
        status = "DEAD" if is_dead else "alive"
        
        # Print every 12 hours
        if hour % 12 == 0:
            print(f"{hour:<6} {day:<6.1f} {soil_water:<10.2f} {damage_rate:<12.2f} {cumulative_damage:<12.2f} {status:<10}")
            
            if damage_rate > 0 and hour % 24 == 0:
                print(f"       └─ Damage sources: {breakdown}")
        
        if is_dead and hour % 24 == 0:
            print(f"\n*** PLANT DIED at hour {hour} (day {day:.1f}) ***")
            break
    
    print("\n" + "=" * 80)
    print("FINAL STATE:")
    print("=" * 80)
    print(f"  Soil water: {soil_water:.2f}%")
    print(f"  Cumulative damage: {cumulative_damage:.2f}%")
    print(f"  Status: {'DEAD' if is_dead else 'ALIVE'}")
    
    print("\n" + "=" * 80)
    print("ANALYSIS:")
    print("=" * 80)
    
    if soil_water > profile.water.wilting_point + 0.5:
        print(f"  ❌ PROBLEM: Soil water ({soil_water:.1f}%) is still above wilting point + 0.5 ({profile.water.wilting_point + 0.5}%)")
        print(f"     Damage only accumulates when soil_water <= {profile.water.wilting_point + 0.5}%")
        print(f"     This is why no damage accumulated!")
    elif cumulative_damage < 95 and not is_dead:
        print(f"  ⚠️  WARNING: Damage accumulated ({cumulative_damage:.1f}%) but plant not dead yet")
        print(f"     Death threshold: 95%")
        print(f"     Estimated hours to death: {(95 - cumulative_damage) / damage_rate:.1f} hours")
    else:
        print(f"  ✅ Plant died as expected with {cumulative_damage:.1f}% damage")

def analyze_damage_threshold():
    """Analyze the damage threshold logic"""
    profile = get_tomato_profile()
    
    print("\n" + "=" * 80)
    print("DAMAGE THRESHOLD ANALYSIS")
    print("=" * 80)
    
    wilting_point = profile.water.wilting_point
    threshold = wilting_point + 0.5
    
    print(f"\nWilting point: {wilting_point}%")
    print(f"Damage threshold: soil_water <= {threshold}%")
    print(f"\nThis means:")
    print(f"  - Soil water > {threshold}%: NO damage")
    print(f"  - Soil water <= {threshold}%: 5% damage per hour (drought)")
    print(f"\nAfter 7 days in our simulation:")
    print(f"  - Soil water was 16.0%")
    print(f"  - Threshold is {threshold}%")
    print(f"  - 16.0 > {threshold}? {16.0 > threshold}")
    print(f"  - Therefore: {'NO DAMAGE' if 16.0 > threshold else 'DAMAGE ACCUMULATING'}")

if __name__ == "__main__":
    test_damage_accumulation()
    simulate_8_days_no_care()
    analyze_damage_threshold()


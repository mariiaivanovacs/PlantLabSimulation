"""
Comprehensive Water Stress and Death Diagnostic Tool

Analyzes:
1. Daily watering application timing and amount
2. Soil water balance (ET, drainage, watering)
3. Water stress calculation
4. RGR-based death conditions
5. Why plant survives 11 days without care
"""
from models.engine import SimulationEngine
from data.default_plants import load_default_profile
from physics.water_balance import calculate_et, calculate_vpd, calculate_water_stress
from physics.damage import calculate_damage_rate, check_death_comprehensive


def diagnose_with_daily_care():
    """Diagnose water stress with daily watering"""
    print("\n" + "="*100)
    print("SCENARIO 1: WITH DAILY WATERING (Once per day at 7 AM)")
    print("="*100)
    
    profile = load_default_profile("tomato_standard")
    engine = SimulationEngine(profile, plant_id="daily_care")
    engine.set_daily_regime(
        enabled=True,
        watering_hour=7,
        water_amount=0.3  # 0.3L per day
    )
    
    print(f"\nPlant Profile:")
    print(f"  Pot volume: {engine.state.pot_volume}L")
    print(f"  Wilting point: {profile.water.wilting_point}%")
    print(f"  Optimal range: {profile.water.optimal_range_min}% - {profile.water.optimal_range_max}%")
    print(f"  Field capacity: {profile.water.field_capacity}%")
    print(f"  Saturation: {profile.water.saturation}%")
    print(f"\nDaily Regime:")
    print(f"  Watering hour: 7 AM")
    print(f"  Water amount: 0.3L/day = {(0.3/engine.state.pot_volume)*100:.1f}% of pot volume")
    
    print(f"\n{'Day':<4} | {'Hour':<4} | {'Soil H2O':<9} | {'ET (L/h)':<9} | {'Water In':<9} | {'Stress':<7} | {'RGR':<9} | {'Biomass':<8} | {'Status':<10}")
    print("-" * 100)
    
    for day in range(8):
        for hour in range(24):
            # Track before watering
            before_water = engine.state.soil_water
            
            # Step simulation
            engine.step(hours=1)
            
            # Check if watering occurred
            water_added = engine.state.soil_water - before_water
            if water_added < 0:
                water_added = 0  # ET caused decrease
            
            # Calculate ET for this hour
            VPD = calculate_vpd(engine.state.air_temp, engine.state.relative_humidity)
            ET = calculate_et(
                engine.state.leaf_area,
                engine.state.light_PAR,
                before_water,
                VPD,
                profile.water.wilting_point,
                profile.water.field_capacity
            )
            
            # Print hourly data (only show key hours)
            hour_of_day = engine.state.hour % 24
            if hour_of_day in [0, 7, 12, 18, 23]:  # Midnight, watering time, noon, evening, night
                water_in_str = f"{water_added:>6.2f}%" if water_added > 0.01 else "-"
                print(f"{day:<4} | {hour_of_day:>2}:00 | {engine.state.soil_water:>7.2f}% | {ET:>7.4f}L | {water_in_str:<9} | "
                      f"{engine.state.water_stress:>5.3f} | {engine.state.RGR:>7.5f} | {engine.state.biomass:>6.3f}g | "
                      f"{'DEAD' if not engine.state.is_alive else 'alive'}")
            
            if not engine.state.is_alive:
                print(f"\n💀 Plant died at Day {day}, Hour {hour_of_day}")
                print(f"   Death reason: {engine.state.death_reason}")
                return
    
    print(f"\n✅ Plant survived 7 days with daily watering")
    print(f"   Final soil water: {engine.state.soil_water:.2f}%")
    print(f"   Final water stress: {engine.state.water_stress:.3f}")
    print(f"   Final biomass: {engine.state.biomass:.3f}g")


def diagnose_without_care():
    """Diagnose why plant survives 11 days without care"""
    print("\n" + "="*100)
    print("SCENARIO 2: WITHOUT CARE (No watering)")
    print("="*100)
    
    profile = load_default_profile("tomato_standard")
    engine = SimulationEngine(profile, plant_id="no_care")
    engine.set_daily_regime(enabled=False)
    
    print(f"\n{'Day':<4} | {'Soil H2O':<9} | {'ET/day':<9} | {'Stress':<7} | {'RGR':<9} | {'Biomass':<8} | {'Damage':<7} | {'CO2 Up':<8} | {'Status':<10}")
    print("-" * 110)
    
    daily_et_total = 0
    rgr_history = []
    co2_history = []
    
    for day in range(15):
        day_start_water = engine.state.soil_water
        
        # Run 24 hours
        for hour in range(24):
            VPD = calculate_vpd(engine.state.air_temp, engine.state.relative_humidity)
            ET = calculate_et(
                engine.state.leaf_area,
                engine.state.light_PAR,
                engine.state.soil_water,
                VPD,
                profile.water.wilting_point,
                profile.water.field_capacity
            )
            daily_et_total += ET
            
            engine.step(hours=1)
            
            if not engine.state.is_alive:
                break
        
        day_end_water = engine.state.soil_water
        daily_et_avg = daily_et_total / 24
        daily_et_total = 0
        
        # Track RGR and CO2 uptake
        rgr_history.append(engine.state.RGR)
        co2_history.append(engine.state.co2_uptake)
        
        print(f"{day:<4} | {engine.state.soil_water:>7.2f}% | {daily_et_avg:>7.4f}L | "
              f"{engine.state.water_stress:>5.3f} | {engine.state.RGR:>7.5f} | {engine.state.biomass:>6.3f}g | "
              f"{engine.state.cumulative_damage:>5.1f}% | {engine.state.co2_uptake:>6.4f} | "
              f"{'DEAD' if not engine.state.is_alive else 'alive'}")
        
        if not engine.state.is_alive:
            print(f"\n💀 Plant died at Day {day}")
            print(f"   Death reason: {engine.state.death_reason}")
            
            # Analyze death conditions
            print(f"\n📊 Death Condition Analysis:")
            print(f"   Cumulative damage: {engine.state.cumulative_damage:.1f}% (threshold: 95%)")
            print(f"   Final biomass: {engine.state.biomass:.3f}g (threshold: 0.01g)")
            print(f"   Final RGR: {engine.state.RGR:.5f}")
            print(f"   Final CO2 uptake: {engine.state.co2_uptake:.5f}")
            
            # Check RGR <= 0 for > 48h
            negative_rgr_hours = sum(1 for rgr in rgr_history[-3:] if rgr <= 0) * 24
            print(f"   Negative RGR duration: ~{negative_rgr_hours}h (threshold: >48h)")
            
            # Check CO2 uptake <= 0 for > 24h
            negative_co2_hours = sum(1 for co2 in co2_history[-2:] if co2 <= 0) * 24
            print(f"   Negative CO2 uptake duration: ~{negative_co2_hours}h (threshold: >24h)")
            
            return
    
    print(f"\n⚠️  WARNING: Plant survived {day} days without care!")
    print(f"   Final soil water: {engine.state.soil_water:.2f}%")
    print(f"   Final water stress: {engine.state.water_stress:.3f}")
    print(f"   Final damage: {engine.state.cumulative_damage:.1f}%")
    print(f"   Final RGR: {engine.state.RGR:.5f}")


if __name__ == "__main__":
    print("\n" + "="*100)
    print("WATER STRESS & DEATH DIAGNOSTIC TOOL")
    print("="*100)
    
    diagnose_with_daily_care()
    diagnose_without_care()
    
    print("\n" + "="*100)
    print("ANALYSIS COMPLETE")
    print("="*100)


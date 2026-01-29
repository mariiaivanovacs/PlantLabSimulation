"""
Debug adaptive watering to see why it's not working
"""
from models.engine import SimulationEngine
from data.default_plants import load_default_profile
from tools.base import ToolType


def debug_adaptive_watering():
    """Debug the adaptive watering calculation"""
    print("\n" + "="*100)
    print("DEBUGGING ADAPTIVE WATERING")
    print("="*100)
    
    profile = load_default_profile("tomato_standard")
    engine = SimulationEngine(profile, plant_id="debug_test")
    
    # Run for 2 days to let soil water drop
    for day in range(2):
        for hour in range(24):
            engine.step(hours=1)
    
    # Now check adaptive watering calculation
    watering_tool = engine.tools[ToolType.WATERING]
    
    print(f"\nCurrent State:")
    print(f"  Biomass: {engine.state.biomass:.2f}g")
    print(f"  Leaf area: {engine.state.leaf_area:.4f}m²")
    print(f"  Soil water: {engine.state.soil_water:.1f}%")
    print(f"  Pot volume: {engine.state.pot_volume}L")
    
    print(f"\nPlant Profile:")
    print(f"  Wilting point: {profile.water.wilting_point}%")
    print(f"  Optimal min: {profile.water.optimal_range_min}%")
    print(f"  Optimal max: {profile.water.optimal_range_max}%")
    print(f"  Field capacity: {profile.water.field_capacity}%")
    
    # Calculate adaptive amount
    adaptive_amount = watering_tool.calculate_adaptive_water_amount(
        state=engine.state,
        wilting_point=profile.water.wilting_point,
        optimal_min=profile.water.optimal_range_min,
        field_capacity=profile.water.field_capacity
    )
    
    print(f"\nAdaptive Watering Calculation:")
    print(f"  Adaptive amount: {adaptive_amount:.3f}L")
    
    # Manual calculation
    biomass = engine.state.biomass
    current_soil_water = engine.state.soil_water
    
    if biomass < 1.0:
        target_water = (profile.water.wilting_point + profile.water.optimal_range_min) / 2
        max_water = 0.05
        print(f"  Category: Seed/Tiny seedling (< 1g)")
    elif biomass < 5.0:
        target_water = profile.water.optimal_range_min - 5.0
        max_water = 0.1 + (biomass - 1.0) * 0.025
        print(f"  Category: Small seedling (1-5g)")
    elif biomass < 30.0:
        target_water = profile.water.optimal_range_min
        max_water = 0.2 + (biomass - 5.0) * 0.012
        print(f"  Category: Medium seedling (5-30g)")
    else:
        target_water = profile.water.field_capacity
        max_water = engine.state.leaf_area * 7.2 * 1.2
        print(f"  Category: Mature plant (> 30g)")
    
    print(f"  Target soil water: {target_water:.1f}%")
    print(f"  Max water per day: {max_water:.3f}L")
    
    if current_soil_water >= target_water:
        print(f"  ❌ Soil water ({current_soil_water:.1f}%) >= target ({target_water:.1f}%) - NO WATERING")
    else:
        water_deficit = target_water - current_soil_water
        water_needed = (water_deficit / 100) * engine.state.pot_volume
        water_amount = min(water_needed, max_water)
        print(f"  Water deficit: {water_deficit:.1f}%")
        print(f"  Water needed: {water_needed:.3f}L")
        print(f"  Water amount (capped): {water_amount:.3f}L")


if __name__ == "__main__":
    debug_adaptive_watering()


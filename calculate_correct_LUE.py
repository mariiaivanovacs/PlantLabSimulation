import math

# Current situation: 68g plant producing 138 g/h photosynthesis
# This is WAY too high!

biomass = 68.34
leaf_area_ratio = 0.004
leaf_area = biomass * leaf_area_ratio  # 0.2734 m²
k = 0.7
light_interception = 1 - math.exp(-k * leaf_area)  # 0.1742
light_PAR = 200.0
PAR_absorbed = light_PAR * light_interception * 3600  # 125,394 umol/h
f_temp = 1.0
f_nutrient = 0.92

print("=" * 60)
print("CURRENT SITUATION (BROKEN)")
print("=" * 60)
LUE_current = 0.0012
P_gross_current = LUE_current * PAR_absorbed * f_temp * f_nutrient
print(f"LUE: {LUE_current} g/umol")
print(f"P_gross: {P_gross_current:.2f} g/h")
print(f"Daily gain (14h): {P_gross_current * 14:.2f} g/day")
print(f"Weekly gain: {P_gross_current * 14 * 7:.2f} g/week")
print(f"Growth rate: {(P_gross_current * 14 / biomass) * 100:.1f}% per day")
print()

print("=" * 60)
print("TARGET: REALISTIC GROWTH")
print("=" * 60)
print("For 68g lettuce:")
print("  - Should gain 5-10g per day")
print("  - Growth rate: 7-15% per day")
print("  - Photosynthesis: 0.5-1.0 g/h at noon")
print()

# Calculate required LUE for realistic growth
target_P_gross = 0.7  # g/h (realistic for 68g plant)
required_LUE = target_P_gross / (PAR_absorbed * f_temp * f_nutrient)

print("=" * 60)
print("SOLUTION: CORRECT LUE VALUE")
print("=" * 60)
print(f"Required LUE: {required_LUE:.10f} g/umol")
print(f"Current LUE: {LUE_current} g/umol")
print(f"Ratio: Current is {LUE_current / required_LUE:.1f}x TOO HIGH!")
print()

# Test with corrected LUE
P_gross_new = required_LUE * PAR_absorbed * f_temp * f_nutrient
print(f"With corrected LUE:")
print(f"  P_gross: {P_gross_new:.2f} g/h")
print(f"  Daily gain (14h): {P_gross_new * 14:.2f} g/day")
print(f"  Weekly gain: {P_gross_new * 14 * 7:.2f} g/week")
print(f"  Growth rate: {(P_gross_new * 14 / biomass) * 100:.1f}% per day")
print()

# Test for seedling with boosts
print("=" * 60)
print("SEEDLING (0.05g) WITH BOOSTS")
print("=" * 60)
biomass_seed = 0.05
leaf_area_seed = biomass_seed * leaf_area_ratio
light_interception_seed = 1 - math.exp(-k * leaf_area_seed)
PAR_absorbed_seed = light_PAR * light_interception_seed * 3600
LUE_boosted = required_LUE * 3 * 2  # 3x and 2x boosts
P_gross_seed = LUE_boosted * PAR_absorbed_seed * f_temp * f_nutrient
print(f"LUE (with 3x and 2x boosts): {LUE_boosted:.10f} g/umol")
print(f"P_gross: {P_gross_seed:.4f} g/h")
print(f"Daily gain (14h): {P_gross_seed * 14:.4f} g/day")
print(f"Growth rate: {(P_gross_seed * 14 / biomass_seed) * 100:.1f}% per day")
print()

# Growth timeline with corrected LUE
print("=" * 60)
print("EXPECTED GROWTH TIMELINE")
print("=" * 60)
print("Day 0:  0.05g  (seed)")
print("Day 1:  0.06g  (20% growth)")
print("Day 7:  0.15g  (3x in week 1)")
print("Day 14: 0.5g   (10x in 2 weeks)")
print("Day 21: 2g     (40x in 3 weeks)")
print("Day 28: 8g     (160x in 4 weeks)")
print("Day 35: 30g    (600x in 5 weeks)")
print("Day 42: 100g   (2000x in 6 weeks) - HARVEST!")
print()

print("=" * 60)
print("RECOMMENDATION")
print("=" * 60)
print(f"Change LUE from {LUE_current} to {required_LUE:.10f}")
print(f"This is approximately: {required_LUE:.2e} g/umol")
print("=" * 60)


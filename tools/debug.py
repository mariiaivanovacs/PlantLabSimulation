


import os
from models.engine import SimulationEngine

def format_time(hours: int) -> str:
    """Format hours as days:hours"""
    days = hours // 24
    hrs = hours % 24
    return f"{days}d {hrs:02d}h"


def display_metrics(engine: SimulationEngine, simulation_hours_per_tick: int = 1, show_tools: bool = False, file_name = 'data/records/logs.txt'):
    """Display current plant metrics in terminal"""
    state = engine.state
    profile = engine.plant_profile
    co2_fluxes = engine.co2_fluxes

    # Calculate hour of day (0-23)
    hour_of_day = state.hour % 24

    # Only log during DAYTIME hours (6 AM to 6 PM)
    # This ensures we capture day measurements (photosynthesis, growth) rather than night measurements
    is_daytime = 6 <= hour_of_day < 18

    # Log to file only during daytime and at specific intervals (e.g., every 4 hours during day)
    # This gives us measurements at: 8 AM, 12 PM, 4 PM (midday measurements)
    # if is_daytime and hour_of_day % 4 == 0:
    try: 
        with open(file_name, 'a') as f:
            # Record: day, biomass, pheno stage, relative humidity, air temperature, CO2, RGR
            f.write(f"{state.hour / 24:.2f},{state.biomass:.4f},{state.phenological_stage.value},{state.relative_humidity:.2f},{state.air_temp:.2f},{state.CO2:.2f},{state.RGR:.6f}, {state.ET:.4f}, {state.water_stress:.6f}\n")
    except FileNotFoundError:
        os.makedirs(os.path.dirname(file_name), exist_ok=True)


    # Minimal one-liner to terminal (full metrics go to files)
    day = state.hour // 24
    hour_of_day = state.hour % 24
    status = "ALIVE" if state.is_alive else "DEAD"
    print(f"Day {day:3d} H{hour_of_day:02d} | biomass={state.biomass:7.2f}g | {state.phenological_stage.value:12s} | water={state.soil_water:5.1f}% | damage={state.cumulative_damage:5.1f}% | {status}")




def get_status_color(value: float, good_max: float, warn_max: float) -> str:
    """Get ANSI color code based on value thresholds"""
    if value <= good_max:
        return "\033[92m"  # Green
    elif value <= warn_max:
        return "\033[93m"  # Yellow
    else:
        return "\033[91m"  # Red


def get_stress_bar(stress: float, width: int = 20) -> str:
    """Create visual stress bar"""
    filled = int(stress * width)
    empty = width - filled

    if stress < 0.3:
        color = "\033[92m"  # Green
    elif stress < 0.6:
        color = "\033[93m"  # Yellow
    else:
        color = "\033[91m"  # Red

    reset = "\033[0m"
    return f"{color}{'█' * filled}{'░' * empty}{reset} {stress*100:5.1f}%"


def get_co2_bar(co2: float, width: int = 20) -> str:
    """Create visual CO2 level bar"""
    # Normalize: 150-2000 ppm range
    normalized = max(0, min(1, (co2 - 150) / (2000 - 150)))
    filled = int(normalized * width)
    empty = width - filled

    # Color based on CO2 level
    if 400 <= co2 <= 1200:
        color = "\033[92m"  # Green - optimal range
    elif 200 <= co2 < 400 or 1200 < co2 <= 1500:
        color = "\033[93m"  # Yellow - acceptable
    else:
        color = "\033[91m"  # Red - stress zone

    reset = "\033[0m"
    return f"{color}{'█' * filled}{'░' * empty}{reset} {co2:6.0f} ppm"


def display_final_summary(engine: SimulationEngine, total_co2_fluxes: dict, start_biomass: float, start_co2: float):
    """
    Display comprehensive summary after simulation ends (normal exit or Ctrl+C)
    Focuses on total CO2 fluxes and overall plant performance
    """
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"

    state = engine.state
    profile = engine.plant_profile

    # Calculate totals
    total_hours = state.hour
    total_days = total_hours / 24
    biomass_change = state.biomass - start_biomass
    co2_change = state.CO2 - start_co2

    print(f"\n{BOLD}{'='*80}{RESET}")
    print(f"{BOLD}{'SIMULATION FINAL SUMMARY':^80}{RESET}")
    print(f"{BOLD}{'='*80}{RESET}")

    # Time and Status
    print(f"\n{CYAN}{BOLD}TIME & FINAL STATUS{RESET}")
    print(f"  Total Duration:      {total_hours:8.0f} hours ({total_days:6.2f} days)")
    print(f"  Plant Status:        {GREEN}ALIVE{RESET}" if state.is_alive else f"  Plant Status:        {RED}DEAD{RESET} - {state.death_reason}")
    print(f"  Final Stage:         {state.phenological_stage.value.capitalize()}")

    # Plant Growth Summary
    print(f"\n{CYAN}{BOLD}PLANT GROWTH SUMMARY{RESET}")
    print(f"  Initial Biomass:     {start_biomass:8.2f} g")
    print(f"  Final Biomass:       {state.biomass:8.2f} g")
    biomass_color = GREEN if biomass_change > 0 else RED
    print(f"  Total Growth:        {biomass_color}{biomass_change:+8.2f} g{RESET}  ({biomass_change/start_biomass*100:+6.1f}%)")
    print(f"  Final Leaf Area:     {state.leaf_area:8.4f} m²")
    print(f"  Thermal Time:        {state.thermal_time:8.1f} °C·h")

    # Final Damage
    damage_color = GREEN if state.cumulative_damage < 30 else (YELLOW if state.cumulative_damage < 70 else RED)
    print(f"  Final Damage:        {damage_color}{state.cumulative_damage:8.1f}%{RESET}")

    # CO2 FLUXES SUMMARY (MAIN FOCUS)
    print(f"\n{MAGENTA}{BOLD}{'='*80}{RESET}")
    print(f"{MAGENTA}{BOLD}{'TOTAL CO2 FLUXES SUMMARY':^80}{RESET}")
    print(f"{MAGENTA}{BOLD}{'='*80}{RESET}")

    # Extract totals
    total_production = total_co2_fluxes.get('total_production_ppm', 0)
    total_consumption = total_co2_fluxes.get('total_consumption_ppm', 0)
    total_injection = total_co2_fluxes.get('total_injection_ppm', 0)
    total_ventilation = total_co2_fluxes.get('total_ventilation_ppm', 0)
    total_leakage = total_co2_fluxes.get('total_leakage_ppm', 0)
    net_total = total_co2_fluxes.get('net_total_ppm', 0)

    print(f"\n{MAGENTA}CO2 FLUXES (Total over {total_days:.1f} days){RESET}")
    print(f"  Production (Respiration):    {total_production:+12.2f} ppm  (CO2 released)")
    print(f"  Consumption (Photosynthesis): {-total_consumption:+12.2f} ppm  (CO2 absorbed)")
    print(f"  Injection (Enrichment):      {total_injection:+12.2f} ppm  (CO2 added)")
    print(f"  Ventilation (Air Exchange):  {total_ventilation:+12.2f} ppm  (CO2 exchanged)")
    print(f"  Leakage (Natural):           {total_leakage:+12.2f} ppm  (CO2 leaked)")

    net_color = GREEN if net_total > 0 else RED
    print(f"\n  {BOLD}NET TOTAL CHANGE:            {net_color}{net_total:+12.2f} ppm{RESET}")

    # CO2 Level Change
    print(f"\n{MAGENTA}CO2 LEVEL CHANGE{RESET}")
    print(f"  Initial CO2:         {start_co2:8.1f} ppm")
    print(f"  Final CO2:           {state.CO2:8.1f} ppm")
    co2_change_color = GREEN if abs(co2_change) < 100 else YELLOW
    print(f"  Total Change:        {co2_change_color}{co2_change:+8.1f} ppm{RESET}")

    # Average rates
    print(f"\n{MAGENTA}AVERAGE HOURLY RATES{RESET}")
    avg_production = total_production / total_hours if total_hours > 0 else 0
    avg_consumption = total_consumption / total_hours if total_hours > 0 else 0
    avg_net = net_total / total_hours if total_hours > 0 else 0

    print(f"  Avg Production:      {avg_production:+8.4f} ppm/h")
    print(f"  Avg Consumption:     {-avg_consumption:+8.4f} ppm/h")
    print(f"  Avg Net Change:      {avg_net:+8.4f} ppm/h")

    # Photosynthesis vs Respiration Balance
    if total_consumption > 0:
        photo_resp_ratio = total_consumption / total_production if total_production > 0 else 0
        print(f"\n{MAGENTA}PHOTOSYNTHESIS / RESPIRATION BALANCE{RESET}")
        print(f"  P/R Ratio:           {photo_resp_ratio:8.2f}")
        if photo_resp_ratio > 1.5:
            print(f"  Status:              {GREEN}Excellent{RESET} - Strong net photosynthesis")
        elif photo_resp_ratio > 1.0:
            print(f"  Status:              {GREEN}Good{RESET} - Positive carbon balance")
        elif photo_resp_ratio > 0.8:
            print(f"  Status:              {YELLOW}Marginal{RESET} - Low net growth")
        else:
            print(f"  Status:              {RED}Poor{RESET} - Net carbon loss")

    # Environmental Summary
    print(f"\n{CYAN}{BOLD}FINAL ENVIRONMENTAL CONDITIONS{RESET}")
    print(f"  Soil Water:          {state.soil_water:8.1f}%  (optimal: {profile.water.optimal_range_min}-{profile.water.optimal_range_max}%)")
    print(f"  Air Temperature:     {state.air_temp:8.1f} °C")
    print(f"  Relative Humidity:   {state.relative_humidity:8.1f}%")
    print(f"  Light PAR:           {state.light_PAR:8.0f} µmol/m²/s")

    # Tool Usage Summary
    actions = engine.get_action_history()
    if actions:
        print(f"\n{CYAN}{BOLD}TOOL USAGE SUMMARY{RESET}")
        print(f"  Total Actions:       {len(actions):8d}")

        # Count by tool type
        tool_counts = {}
        for action in actions:
            tool = action['action']
            tool_counts[tool] = tool_counts.get(tool, 0) + 1

        for tool, count in sorted(tool_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {tool:20s} {count:8d} times")

    # Resource Usage Summary (Daily Regime)
    print(f"\n{CYAN}{BOLD}RESOURCE USAGE (Daily Regime){RESET}")

    # Water usage
    if engine.total_water_supplied_L > 0:
        avg_water_per_application = engine.total_water_supplied_L / engine.water_applications if engine.water_applications > 0 else 0
        print(f"  💧 Total Water Supplied:     {engine.total_water_supplied_L:8.3f} L")
        print(f"  💧 Water Applications:       {engine.water_applications:8d} times")
        print(f"  💧 Average per Application:  {avg_water_per_application:8.3f} L")
    else:
        print(f"  💧 No water supplied via daily regime")

    # CO2 usage
    if engine.total_co2_injected_g > 0:
        avg_co2_per_injection = engine.total_co2_injected_g / engine.co2_injections if engine.co2_injections > 0 else 0
        print(f"  🌫️  Total CO2 Injected:       {engine.total_co2_injected_g:8.3f} g")
        print(f"  🌫️  CO2 Injections:          {engine.co2_injections:8d} times")
        print(f"  🌫️  Average per Injection:   {avg_co2_per_injection:8.3f} g")
    else:
        print(f"  🌫️  No CO2 injected via daily regime")

    print(f"\n{BOLD}{'='*80}{RESET}")
    print(f"{BOLD}{'END OF SIMULATION':^80}{RESET}")
    print(f"{BOLD}{'='*80}{RESET}\n")


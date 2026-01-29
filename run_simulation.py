#!/usr/bin/env python3
"""
Plant Simulation Runner
Standalone script to run plant simulation with terminal display

Phase 2 features:
- CO2 level monitoring and display
- CO2 production/consumption flux tracking
- Interactive tool controls
- BigQuery logging (when configured)
- Firebase persistence (when configured)

Usage:
    python run_simulation.py                    # Run with default (tomato)
    python run_simulation.py --plant tomato     # Run with specific plant
    python run_simulation.py --plant lettuce
    python run_simulation.py --plant basil
    python run_simulation.py --list             # List available plants
    python run_simulation.py --hours 168        # Run for specific hours
    python run_simulation.py --interactive      # Enable tool controls
"""

import sys
import os
import time
import argparse
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.default_plants import DEFAULT_PROFILES, load_default_profile
from models.engine import SimulationEngine
from tools.base import ToolAction, ToolType
from services.bigquery_service import BigQueryService
from services.firebase_service import FirebaseService


def clear_screen():
    """Clear terminal screen"""
    os.system('cls' if os.name == 'nt' else 'clear')


def format_time(hours: int) -> str:
    """Format hours as days:hours"""
    days = hours // 24
    hrs = hours % 24
    return f"{days}d {hrs:02d}h"


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


def display_metrics(engine: SimulationEngine, simulation_hours_per_tick: int = 1, show_tools: bool = False, file_name = 'data/records/logs.txt'):
    """Display current plant metrics in terminal"""
    state = engine.state
    profile = engine.plant_profile
    co2_fluxes = engine.co2_fluxes
    
    
    
    
    
    
    
    # add record to the txt file - data/records/logs.txt
    with open(file_name, 'a') as f:
        # need to record if the engine.state.hour % 24 == 0: -> every 24 hours
        # need to record -> biomass, pheno stage, relative humidity, air temperature, CO2
        f.write(f"{state.hour / 24},{state.biomass},{state.phenological_stage.value},{state.relative_humidity},{state.air_temp},{state.CO2}, {state.RGR}\n")  
        

        

    # ANSI colors
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    BLUE = "\033[94m"

    # Status indicators
    alive_status = f"{GREEN}ALIVE{RESET}" if state.is_alive else f"{RED}DEAD{RESET}"

    print(f"\n{BOLD}{'='*70}{RESET}")
    print(f"{BOLD}  PLANT SIMULATION - {profile.species_name} (Phase 2){RESET}")
    print(f"{BOLD}{'='*70}{RESET}")

    # Time and Status
    print(f"\n{CYAN}TIME & STATUS{RESET}")
    print(f"  Simulation Time: {format_time(state.hour)}")
    print(f"  Plant Status:    {alive_status}")
    print(f"  Stage:           {state.phenological_stage.value.capitalize()}")

    # Plant Health
    print(f"\n{CYAN}PLANT HEALTH{RESET}")
    print(f"  Biomass:         {state.biomass:8.2f} g  (max: {profile.growth.max_biomass} g)")
    print(f"  Leaf Area:       {state.leaf_area:8.4f} m²")
    print(f"  Thermal Time:    {state.thermal_time:8.1f} °C·h")

    # Growth Metrics (NEW: RGR and logistic growth)
    print(f"\n{CYAN}GROWTH METRICS{RESET}")
    rgr_percent_per_day = state.RGR * 24 * 100  # Convert 1/h to %/day
    print(f"  RGR:             {state.RGR:8.6f} /h  ({rgr_percent_per_day:6.2f}% per day)")

    if state.doubling_time < 1000:
        doubling_days = state.doubling_time / 24
        print(f"  Doubling Time:   {state.doubling_time:8.1f} h  ({doubling_days:5.2f} days)")
    else:
        print(f"  Doubling Time:   {'∞':>8s} h  (not growing)")

    saturation_percent = state.growth_saturation * 100
    saturation_color = GREEN if saturation_percent < 30 else (YELLOW if saturation_percent < 70 else RED)
    print(f"  Saturation:      {saturation_color}{saturation_percent:7.1f}%{RESET}  (B/K ratio)")

    # Damage
    damage_color = GREEN if state.cumulative_damage < 30 else (YELLOW if state.cumulative_damage < 70 else RED)
    print(f"\n{CYAN}DAMAGE{RESET}")
    print(f"  Cumulative:      {damage_color}{state.cumulative_damage:8.1f}%{RESET}")

    # Stress Levels
    print(f"\n{CYAN}STRESS LEVELS{RESET}")
    print(f"  Water Stress:    {get_stress_bar(state.water_stress)}")
    print(f"  Temp Stress:     {get_stress_bar(state.temp_stress)}")
    print(f"  Nutrient Stress: {get_stress_bar(state.nutrient_stress)}")

    # Soil Conditions
    water_color = GREEN if profile.water.optimal_range_min <= state.soil_water <= profile.water.optimal_range_max else YELLOW
    if state.soil_water < profile.water.wilting_point:
        water_color = RED

    print(f"\n{CYAN}SOIL CONDITIONS{RESET}")
    print(f"  Soil Water:      {water_color}{state.soil_water:8.1f}%{RESET}  (optimal: {profile.water.optimal_range_min}-{profile.water.optimal_range_max}%)")
    print(f"  Soil Temp:       {state.soil_temp:8.1f} °C")
    print(f"  Soil N/P/K:      {state.soil_N:6.1f} / {state.soil_P:5.1f} / {state.soil_K:5.1f} ppm")
    print(f"  Soil EC:         {state.soil_EC:8.2f} mS/cm")

    # Environment
    temp_color = GREEN if profile.temperature.T_min <= state.air_temp <= profile.temperature.T_max else RED
    print(f"\n{CYAN}ENVIRONMENT{RESET}")
    print(f"  Air Temp:        {temp_color}{state.air_temp:8.1f} °C{RESET}  (range: {profile.temperature.T_min}-{profile.temperature.T_max}°C)")
    print(f"  Humidity:        {state.relative_humidity:8.1f}%")
    print(f"  VPD:             {state.VPD:8.2f} kPa")
    print(f"  Light PAR:       {state.light_PAR:8.0f} µmol/m²/s")

    # CO2 Section (Phase 2)
    print(f"\n{MAGENTA}CO2 DYNAMICS{RESET}")
    print(f"  CO2 Level:       {get_co2_bar(state.CO2)}")
    print(f"  Ambient:         {400:6.0f} ppm  (outdoor reference)")
    print(f"  Optimal:         800-1200 ppm  (enhanced growth zone)")

    # CO2 Fluxes
    if co2_fluxes:
        prod = co2_fluxes.get('production_ppm', 0)
        cons = co2_fluxes.get('consumption_ppm', 0)
        inj = co2_fluxes.get('injection_ppm', 0)
        vent = co2_fluxes.get('ventilation_ppm', 0)
        leak = co2_fluxes.get('leakage_ppm', 0)
        net = co2_fluxes.get('net_change_ppm', 0)

        print(f"\n{MAGENTA}CO2 FLUXES (per hour){RESET}")
        print(f"  Production:      {prod:+8.2f} ppm  (respiration)")
        print(f"  Consumption:     {-cons:+8.2f} ppm  (photosynthesis)")
        print(f"  Injection:       {inj:+8.2f} ppm  (CO2 enrichment)")
        print(f"  Ventilation:     {vent:+8.2f} ppm  (air exchange)")
        print(f"  Leakage:         {leak:+8.2f} ppm  (natural)")
        net_color = GREEN if abs(net) < 5 else (YELLOW if abs(net) < 20 else RED)
        print(f"  {BOLD}Net Change:      {net_color}{net:+8.2f} ppm{RESET}")

    # Fluxes (rates)
    print(f"\n{CYAN}HOURLY FLUXES{RESET}")
    print(f"  ET:              {state.ET:8.4f} L/h")
    print(f"  Photosynthesis:  {state.photosynthesis:8.4f} g/h")
    print(f"  Respiration:     {state.respiration:8.4f} g/h")
    print(f"  Net Growth:      {state.growth_rate:8.4f} g/h")

    # Tool controls hint
    if show_tools:
        print(f"\n{BLUE}TOOL CONTROLS{RESET}")
        print(f"  [W] Water plant      [L] Toggle lights    [N] Add nutrients")
        print(f"  [H] Adjust HVAC      [U] Adjust humidity  [V] Ventilation")
        print(f"  [C] CO2 enrichment   [Q] Quit")

    print(f"\n{BOLD}{'='*70}{RESET}")
    print(f"  Simulating {simulation_hours_per_tick} hour(s) per tick | Press Ctrl+C to stop")
    if not show_tools:
        print(f"  Run with --interactive for tool controls")
    print(f"{BOLD}{'='*70}{RESET}\n")


def apply_tool_interactive(engine: SimulationEngine, tool_key: str) -> None:
    """Apply a tool based on user input"""
    RESET = "\033[0m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"

    tool_map = {
        'w': (ToolType.WATERING, "Watering"),
        'l': (ToolType.LIGHTING, "Lighting"),
        'n': (ToolType.NUTRIENTS, "Nutrients"),
        'h': (ToolType.HVAC, "HVAC"),
        'u': (ToolType.HUMIDITY, "Humidity"),
        'v': (ToolType.VENTILATION, "Ventilation"),
        'c': (ToolType.CO2_CONTROL, "CO2 Control"),
    }

    if tool_key.lower() not in tool_map:
        return

    tool_type, tool_name = tool_map[tool_key.lower()]

    print(f"\n{YELLOW}--- {tool_name} Tool ---{RESET}")

    # Get parameters based on tool type
    params = {}

    try:
        if tool_type == ToolType.WATERING:
            amount = input(f"  Water amount (L) [default: 0.5]: ").strip()
            params['water_L'] = float(amount) if amount else 0.5

        elif tool_type == ToolType.LIGHTING:
            target = input(f"  Target PAR (µmol/m²/s) [default: 400, 0=off]: ").strip()
            params['target_PAR'] = float(target) if target else 400

        elif tool_type == ToolType.NUTRIENTS:
            print(f"  Current N/P/K: {engine.state.soil_N:.1f}/{engine.state.soil_P:.1f}/{engine.state.soil_K:.1f} ppm")
            n = input(f"  Add N (ppm) [default: 50]: ").strip()
            p = input(f"  Add P (ppm) [default: 20]: ").strip()
            k = input(f"  Add K (ppm) [default: 40]: ").strip()
            params['N_dose'] = float(n) if n else 50
            params['P_dose'] = float(p) if p else 20
            params['K_dose'] = float(k) if k else 40

        elif tool_type == ToolType.HVAC:
            print(f"  Current temp: {engine.state.air_temp:.1f}°C")
            target = input(f"  Target temp (°C) [default: 25]: ").strip()
            params['target_temp'] = float(target) if target else 25

        elif tool_type == ToolType.HUMIDITY:
            print(f"  Current humidity: {engine.state.relative_humidity:.1f}%")
            target = input(f"  Target humidity (%) [default: 65]: ").strip()
            params['target_RH'] = float(target) if target else 65

        elif tool_type == ToolType.VENTILATION:
            print(f"  Current CO2: {engine.state.CO2:.0f} ppm")
            rate = input(f"  Ventilation rate (0-1) [default: 0.2]: ").strip()
            params['rate'] = float(rate) if rate else 0.2
            duration = input(f"  Duration (hours) [default: 1]: ").strip()
            params['duration_hours'] = int(duration) if duration else 1

        elif tool_type == ToolType.CO2_CONTROL:
            print(f"  Current CO2: {engine.state.CO2:.0f} ppm")
            print(f"  Optimal range: 800-1200 ppm")
            target = input(f"  Target CO2 (ppm) [default: 1000]: ").strip()
            params['target_co2_ppm'] = float(target) if target else 1000

        # Create and apply action
        action = ToolAction(
            tool_type=tool_type,
            parameters=params
        )

        result = engine.apply_tool(action)

        if result.success:
            print(f"{GREEN}  Success: {result.message}{RESET}")
        else:
            print(f"\033[91m  Failed: {result.message}{RESET}")

    except ValueError as e:
        print(f"\033[91m  Invalid input: {e}{RESET}")
    except KeyboardInterrupt:
        pass

    input("\n  Press Enter to continue...")


def list_plants():
    """List available plant profiles"""
    print("\nAvailable Plant Profiles:")
    print("-" * 50)
    for profile_id, profile in DEFAULT_PROFILES.items():
        print(f"  {profile_id:20s} - {profile.species_name}")
    print("-" * 50)
    print("\nUsage: python run_simulation.py --plant <profile_id>")


def run_simulation(
    plant_name: str = "tomato_standard",
    max_hours: int = 0,
    display_interval: float = 5.0,
    hours_per_tick: int = 1,
    interactive: bool = False,
    enable_logging: bool = True,
    daily_regime: bool = True
):
    """
    Run simulation with terminal display

    Args:
        plant_name: Profile ID to use
        max_hours: Maximum hours to simulate (0 = unlimited)
        display_interval: Seconds between display updates
        hours_per_tick: Simulation hours per display tick
        interactive: Enable interactive tool controls
        enable_logging: Enable BigQuery/Firebase logging
    """
    # Load plant profile
    try:
        profile = load_default_profile(plant_name)
    except ValueError as e:
        print(f"Error: {e}")
        list_plants()
        return

    # Create simulation engine
    engine = SimulationEngine(profile)
    
    # Set daily regime
    engine.set_daily_regime(enabled=False)

    # Initialize services (will gracefully degrade if not configured)
    bq_service = None
    fb_service = None

    if enable_logging:
        try:
            bq_service = BigQueryService(enabled=True)
            if not bq_service.connected:
                print("BigQuery not configured - logging to local buffer")
        except Exception as e:
            print(f"BigQuery init failed: {e}")

        try:
            fb_service = FirebaseService(enabled=True)
            if not fb_service.connected:
                print("Firebase not configured - using local cache")
        except Exception as e:
            print(f"Firebase init failed: {e}")

    print(f"\nStarting simulation with: {profile.species_name}")
    print(f"Profile ID: {profile.profile_id}")
    print(f"Display updates every {display_interval} seconds")
    print(f"Simulating {hours_per_tick} hour(s) per tick")
    if max_hours > 0:
        print(f"Will run for {max_hours} hours ({max_hours/24:.1f} days)")
    if interactive:
        print("Interactive mode enabled - tool controls available")
    print("\nPress Ctrl+C to stop...\n")
    time.sleep(2)
    
    
    current_time = datetime.now()
    # day, hour and min
    file_name = f'data/records/logs_{current_time.strftime("%d%H%M")}.txt'

    try:
        while True:
            clear_screen()
            display_metrics(engine, hours_per_tick, show_tools=interactive, file_name = file_name)

            # Log to services
            if bq_service:
                bq_service.log_state(
                    engine.simulation_id,
                    engine.plant_id,
                    engine.state.to_dict(),
                    engine.co2_fluxes
                )

            if fb_service:
                fb_service.save_simulation(
                    engine.simulation_id,
                    engine.plant_id,
                    engine.state.to_dict(),
                    profile.profile_id,
                    engine.co2_fluxes
                )

            # Check termination conditions
            if max_hours > 0 and engine.state.hour >= max_hours:
                print(f"\nReached maximum simulation time ({max_hours} hours)")
                break

            if not engine.state.is_alive and engine.state.biomass < 0.01:
                print("\nPlant has fully decomposed. Simulation ended.")
                break

            # Interactive mode: check for tool input
            if interactive:
                import select
                import tty
                import termios

                # Non-blocking input check (Unix only)
                try:
                    old_settings = termios.tcgetattr(sys.stdin)
                    try:
                        tty.setcbreak(sys.stdin.fileno())
                        rlist, _, _ = select.select([sys.stdin], [], [], display_interval)
                        if rlist:
                            key = sys.stdin.read(1)
                            if key.lower() == 'q':
                                print("\nQuitting...")
                                break
                            elif key.lower() in 'wlnhuvc':
                                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
                                apply_tool_interactive(engine, key)
                                continue
                    finally:
                        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
                except (termios.error, AttributeError):
                    # Windows or non-TTY - fall back to regular sleep
                    time.sleep(display_interval)
            else:
                # Wait for display interval
                time.sleep(display_interval)

            # Advance simulation
            engine.step(hours=hours_per_tick)

    except KeyboardInterrupt:
        print("\n\nSimulation stopped by user.")

    # Flush logs
    if bq_service:
        bq_service.flush_all()
        local_log = bq_service.get_local_log()
        if local_log:
            print(f"BigQuery: {len(local_log)} records logged locally")

    if fb_service:
        cache_stats = fb_service.get_cache_stats()
        print(f"Firebase cache: {cache_stats}")

    # Final summary
    print("\n" + "=" * 70)
    print("SIMULATION SUMMARY")
    print("=" * 70)
    summary = engine.get_summary()
    for key, value in summary.items():
        print(f"  {key:25s}: {value}")
    print("=" * 70)

    # Show action history if any tools were used
    actions = engine.get_action_history()
    if actions:
        print(f"\nTOOL ACTIONS ({len(actions)} total):")
        print("-" * 70)
        for action in actions[-10:]:  # Show last 10
            print(f"  Hour {action['hour']:4d}: {action['action']:15s} - {action['result'].get('message', '')[:40]}")
        if len(actions) > 10:
            print(f"  ... and {len(actions) - 10} more actions")
        print("-" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Plant Growth Simulation Runner (Phase 2)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_simulation.py                      # Run with tomato (default)
  python run_simulation.py --plant lettuce      # Run with lettuce
  python run_simulation.py --plant basil        # Run with basil
  python run_simulation.py --list               # List available plants
  python run_simulation.py --hours 168          # Run for 1 week (168 hours)
  python run_simulation.py --speed 24           # Simulate 24 hours per tick
  python run_simulation.py --interval 2         # Update display every 2 seconds
  python run_simulation.py --interactive        # Enable tool controls
    python run_simulation.py --daily_regime False        # Disable daily regime
        """
    )

    parser.add_argument(
        "--plant", "-p",
        type=str,
        default="tomato_standard",
        help="Plant profile to use (default: tomato_standard)"
    )
    
    parser.add_argument(
        "--daily_regime", "-d",
        type=bool,
        default=True,
        help="Enable daily regime (default: True)"
    )


    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List available plant profiles"
    )

    parser.add_argument(
        "--hours", "-H",
        type=int,
        default=0,
        help="Maximum hours to simulate (0 = unlimited)"
    )

    parser.add_argument(
        "--interval", "-i",
        type=float,
        default=5.0,
        help="Display update interval in seconds (default: 5)"
    )

    parser.add_argument(
        "--speed", "-s",
        type=int,
        default=1,
        help="Simulation hours per tick (default: 1)"
    )

    parser.add_argument(
        "--interactive", "-I",
        action="store_true",
        help="Enable interactive tool controls"
    )

    parser.add_argument(
        "--no-logging",
        action="store_true",
        help="Disable BigQuery/Firebase logging"
    )

    args = parser.parse_args()

    if args.list:
        list_plants()
        return

    run_simulation(
        plant_name=args.plant,
        daily_regime=args.daily_regime,
        max_hours=args.hours,
        display_interval=args.interval,
        hours_per_tick=args.speed,
        interactive=args.interactive,
        enable_logging=not args.no_logging
    )


if __name__ == "__main__":
    main()

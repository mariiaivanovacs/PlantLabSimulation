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
from tools.debug import display_metrics, display_final_summary

def clear_screen():
    """Clear terminal screen"""
    os.system('cls' if os.name == 'nt' else 'clear')




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
    
    
    print(f"Daily regime: {daily_regime}")
    
    # Set daily regime
    engine.set_daily_regime(enabled=daily_regime)

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

    # Track initial state for summary
    start_biomass = engine.state.biomass
    start_co2 = engine.state.CO2

    # Initialize CO2 flux accumulators
    total_co2_fluxes = {
        'total_production_ppm': 0.0,
        'total_consumption_ppm': 0.0,
        'total_injection_ppm': 0.0,
        'total_ventilation_ppm': 0.0,
        'total_leakage_ppm': 0.0,
        'net_total_ppm': 0.0
    }

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

            # Accumulate CO2 fluxes for summary
            if engine.co2_fluxes:
                total_co2_fluxes['total_production_ppm'] += engine.co2_fluxes.get('production_ppm', 0) * hours_per_tick
                total_co2_fluxes['total_consumption_ppm'] += engine.co2_fluxes.get('consumption_ppm', 0) * hours_per_tick
                total_co2_fluxes['total_injection_ppm'] += engine.co2_fluxes.get('injection_ppm', 0) * hours_per_tick
                total_co2_fluxes['total_ventilation_ppm'] += engine.co2_fluxes.get('ventilation_ppm', 0) * hours_per_tick
                total_co2_fluxes['total_leakage_ppm'] += engine.co2_fluxes.get('leakage_ppm', 0) * hours_per_tick
                total_co2_fluxes['net_total_ppm'] += engine.co2_fluxes.get('net_change_ppm', 0) * hours_per_tick

    except KeyboardInterrupt:
        print("\n\nSimulation stopped by user (Ctrl+C).")

    # Display comprehensive final summary
    display_final_summary(engine, total_co2_fluxes, start_biomass, start_co2)

    # Flush logs
    if bq_service:
        bq_service.flush_all()
        local_log = bq_service.get_local_log()
        if local_log:
            print(f"\n📊 BigQuery: {len(local_log)} records logged locally")

    if fb_service:
        cache_stats = fb_service.get_cache_stats()
        print(f"📊 Firebase cache: {cache_stats}")


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
        type=str,
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
    
    
    print(f"From args: Daily regime: {args.daily_regime}")

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

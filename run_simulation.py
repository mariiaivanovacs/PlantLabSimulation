#!/usr/bin/env python3
"""
Plant Simulation Runner
Standalone script to run plant simulation with terminal display

Usage:
    python run_simulation.py                    # Run with default (tomato)
    python run_simulation.py --plant tomato     # Run with specific plant
    python run_simulation.py --plant lettuce
    python run_simulation.py --plant basil
    python run_simulation.py --list             # List available plants
    python run_simulation.py --hours 168        # Run for specific hours
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


def display_metrics(engine: SimulationEngine, simulation_hours_per_tick: int = 1):
    """Display current plant metrics in terminal"""
    state = engine.state
    profile = engine.plant_profile

    # ANSI colors
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"

    # Status indicators
    alive_status = f"{GREEN}ALIVE{RESET}" if state.is_alive else f"{RED}DEAD{RESET}"

    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  PLANT SIMULATION - {profile.species_name}{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")

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

    # Fluxes (rates)
    print(f"\n{CYAN}HOURLY FLUXES{RESET}")
    print(f"  ET:              {state.ET:8.4f} L/h")
    print(f"  Photosynthesis:  {state.photosynthesis:8.4f} g/h")
    print(f"  Respiration:     {state.respiration:8.4f} g/h")
    print(f"  Net Growth:      {state.growth_rate:8.4f} g/h")

    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"  Simulating {simulation_hours_per_tick} hour(s) per tick | Press Ctrl+C to stop")
    print(f"{BOLD}{'='*60}{RESET}\n")


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
    hours_per_tick: int = 1
):
    """
    Run simulation with terminal display

    Args:
        plant_name: Profile ID to use
        max_hours: Maximum hours to simulate (0 = unlimited)
        display_interval: Seconds between display updates
        hours_per_tick: Simulation hours per display tick
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

    print(f"\nStarting simulation with: {profile.species_name}")
    print(f"Profile ID: {profile.profile_id}")
    print(f"Display updates every {display_interval} seconds")
    print(f"Simulating {hours_per_tick} hour(s) per tick")
    if max_hours > 0:
        print(f"Will run for {max_hours} hours ({max_hours/24:.1f} days)")
    print("\nPress Ctrl+C to stop...\n")
    time.sleep(2)

    try:
        while True:
            clear_screen()
            display_metrics(engine, hours_per_tick)

            # Check termination conditions
            if max_hours > 0 and engine.state.hour >= max_hours:
                print(f"\nReached maximum simulation time ({max_hours} hours)")
                break

            if not engine.state.is_alive and engine.state.biomass < 0.01:
                print("\nPlant has fully decomposed. Simulation ended.")
                break

            # Wait for display interval
            time.sleep(display_interval)

            # Advance simulation
            engine.step(hours=hours_per_tick)

    except KeyboardInterrupt:
        print("\n\nSimulation stopped by user.")

    # Final summary
    print("\n" + "=" * 60)
    print("SIMULATION SUMMARY")
    print("=" * 60)
    summary = engine.get_summary()
    for key, value in summary.items():
        print(f"  {key:25s}: {value}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Plant Growth Simulation Runner",
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
        """
    )

    parser.add_argument(
        "--plant", "-p",
        type=str,
        default="tomato_standard",
        help="Plant profile to use (default: tomato_standard)"
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

    args = parser.parse_args()

    if args.list:
        list_plants()
        return

    run_simulation(
        plant_name=args.plant,
        max_hours=args.hours,
        display_interval=args.interval,
        hours_per_tick=args.speed
    )


if __name__ == "__main__":
    main()

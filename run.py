#!/usr/bin/env python3
"""
PlantLabSimulation - Flask Application Entry Point

Run the simulation via Flask API or directly from terminal.

Usage:
    # Start Flask server (default port 5010)
    python run.py

    # Start on custom port
    python run.py --port 8080

    # Run simulation directly (no server)
    python run.py --run --plant tomato_standard --days 30

    # Run with monitor disabled
    python run.py --run --plant lettuce_butterhead --days 14 --no-monitor
"""

import argparse
import sys
import os
from time import time

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from config.settings import initialize_firebase, PORT, HOST

# 1. Инициализация Firebase
initialize_firebase()

from data.default_plants import DEFAULT_PROFILES, load_default_profile
from config.settings import HOST, PORT


def run_flask_server(host: str = HOST, port: int = PORT, debug: bool = True):
    """Start Flask development server"""
    from app import create_app

    app = create_app()
    print(f"\n{'='*60}")
    print("PlantLabSimulation API Server")
    print(f"{'='*60}")
    print(f"\nWeb UI:    http://{host}:{port}/")
    print(f"API Info:  http://{host}:{port}/api")
    print("\nSimulation auto-runs after /start - output appears here.")
    print("\nModes:")
    print("  speed    - Fast simulation (configurable hours per tick)")
    print("  realtime - 1 sim hour = 1 real hour (low energy)")
    print(f"\n{'='*60}\n")

    app.run(host=host, port=port, debug=debug)


def list_plants():
    """List available plant profiles"""
    print("\nAvailable Plant Profiles:")
    print("-" * 50)
    for profile_id, profile in DEFAULT_PROFILES.items():
        print(f"  {profile_id:20s} - {profile.species_name}")
    print("-" * 50)
    print("\nUsage: python run_simulation.py --plant <profile_id>")




def run_simulation_direct(
    plant_name: str = 'tomato_standard',
    days: int = 30,
    daily_regime: bool = True,
    monitor_enabled: bool = True,
    hours_per_tick: int = 1
):
    """Run simulation directly without Flask server"""
    from models.engine import SimulationEngine
    from models.plant_profile import PlantProfile
    from agents.orchestrator import AgentOrchestrator

    print(f"\n{'='*60}")
    print(f"PlantLabSimulation - Direct Run")
    print(f"{'='*60}")
    print(f"Plant: {plant_name}")
    print(f"Duration: {days} days")
    print(f"Daily regime: {'enabled' if daily_regime else 'disabled'}")
    print(f"Monitor: {'enabled' if monitor_enabled else 'disabled'}")
    print(f"{'='*60}\n")

    # Get plant profile
    try:
        profile_data = load_default_profile(plant_name)
        profile = PlantProfile(**profile_data)
    except Exception as e:
        print(f"Error: Could not load plant profile '{plant_name}'.")
        list_plants()
        sys.exit(1)

    # 1. Create engine (pure physics)
    engine = SimulationEngine(profile)

    # 2. Configure daily regime
    if daily_regime:
        engine.set_daily_regime(enabled="True")
    else:
        engine.set_daily_regime(enabled="False")

    # 3. Attach agent orchestrator (independent of engine)
    orchestrator = None
    if monitor_enabled:
        orchestrator = AgentOrchestrator.create(
            engine=engine,
            monitor_enabled=True,
        )

    # Run simulation
    total_hours = days * 24
    print("Running simulation...\n")
    display_interval = 5.0  # seconds
    import time

    for hour in range(total_hours):
        engine.step(hours=hours_per_tick)

        # Print progress every day
        if (hour + 1) % 24 == 0:
            day = (hour + 1) // 24
            state = engine.state
            print(f"Day {day:3d}: biomass={state.biomass:7.2f}g | "
                  f"stage={state.phenological_stage.value:12s} | "
                  f"damage={state.cumulative_damage:5.1f}% | "
                  f"alive={state.is_alive}")
        # Wait for display interval
        time.sleep(display_interval)

    # Print final summary
    print(f"\n{'='*60}")
    print("SIMULATION COMPLETE")
    print(f"{'='*60}\n")

    summary = engine.get_summary()
    print(f"Simulation ID: {summary['simulation_id']}")
    print(f"Plant ID: {summary['plant_id']}")
    print(f"Final biomass: {summary['biomass']:.2f}g")
    print(f"Final stage: {summary['phenological_stage']}")
    print(f"Hours elapsed: {summary['hours_elapsed']}")
    print(f"Plant alive: {summary['is_alive']}")
    print(f"Final damage: {summary['cumulative_damage']:.1f}%")

    # Agent statistics (via orchestrator — independent of engine)
    if orchestrator:
        stats = orchestrator.reasoning_agent.get_statistics()
        print(f"\nMonitor Statistics:")
        print(f"  Total alerts: {stats['total_alerts']}")
        print(f"  Warnings: {stats['warnings']}")
        print(f"  Criticals: {stats['criticals']}")

        log_path = orchestrator.save_session_log()
        print(f"\nReasoning log saved: {log_path}")

    # List output files
    out_dir = "out"
    if os.path.exists(out_dir):
        files = [f for f in os.listdir(out_dir) if f.startswith('monitor_')]
        if files:
            print(f"\nMonitor output files ({len(files)} total):")
            for f in sorted(files)[-5:]:  # Show last 5
                print(f"  {f}")
            if len(files) > 5:
                print(f"  ... and {len(files) - 5} more")

    print(f"\n{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description='PlantLabSimulation - Run via Flask API or directly'
    )

    # Server options
    parser.add_argument(
        '--host',
        default=HOST,
        help=f'Host to bind Flask server (default: {HOST})'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=PORT,
        help=f'Port for Flask server (default: {PORT})'
    )
    parser.add_argument(
        '--no-debug',
        action='store_true',
        help='Disable Flask debug mode'
    )

    # Direct run options
    parser.add_argument(
        '--run',
        action='store_true',
        help='Run simulation directly (no Flask server)'
    )
    parser.add_argument(
        '--plant',
        default='tomato_standard',
        choices=['tomato_standard', 'lettuce_butterhead'],
        help='Plant type to simulate (default: tomato_standard)'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=30,
        help='Number of days to simulate (default: 30)'
    )
    parser.add_argument(
        '--no-regime',
        action='store_true',
        help='Disable daily automated regime'
    )
    parser.add_argument(
        '--no-monitor',
        action='store_true',
        help='Disable monitor agent'
    )
    parser.add_argument(
        "--speed", "-s",
        type=int,
        default=1,
        help="Simulation hours per tick (default: 1)"
    )

    args = parser.parse_args()

    # Ensure output directory exists
    os.makedirs('out', exist_ok=True)
    os.makedirs('out/reasoning', exist_ok=True)

    if args.run:
        # Run simulation directly
        run_simulation_direct(
            plant_name=args.plant,
            days=args.days,
            daily_regime=not args.no_regime,
            monitor_enabled=not args.no_monitor,
            hours_per_tick=args.speed
        )
    else:
        # Start Flask server
        run_flask_server(
            host=args.host,
            port=args.port,
            debug=not args.no_debug
        )


if __name__ == '__main__':
    main()

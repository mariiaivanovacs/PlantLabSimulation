"""Simulation API routes with auto-running simulation"""

import sys
import os
import math
import threading
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from flask import Blueprint, jsonify, request
from models.engine import SimulationEngine
from models.plant_profile import PlantProfile
from data.default_plants import DEFAULT_PROFILES, load_default_profile
from agents.orchestrator import AgentOrchestrator
import logging
from tools.debug import display_metrics, display_final_summary



logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bp = Blueprint('simulation', __name__)


def _sanitize(obj):
    """Recursively replace inf/nan floats with None so jsonify never breaks."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, float) and (math.isinf(obj) or math.isnan(obj)):
        return None
    return obj


# Global simulation state  (engine and agents are independent)
_engine = None
_orchestrator = None
_simulation_thread = None
_simulation_running = False
_simulation_config = {}


def list_plants():
    """List available plant profiles"""
    print("\nAvailable Plant Profiles:")
    print("-" * 50)
    for profile_id, profile in DEFAULT_PROFILES.items():
        print(f"  {profile_id:20s} - {profile.species_name}")
    print("-" * 50)


def get_engine():
    """Get simulation engine"""
    global _engine
    return _engine


def get_orchestrator():
    """Get agent orchestrator"""
    global _orchestrator
    return _orchestrator


def is_running():
    """Check if simulation is running"""
    global _simulation_running
    return _simulation_running


def _print_status(state, day, hour_of_day):
    """Print status to terminal"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] Day {day:3d} Hour {hour_of_day:02d}:00 | "
          f"biomass={state.biomass:7.2f}g | "
          f"stage={state.phenological_stage.value:12s} | "
          f"water={state.soil_water:5.1f}% | "
          f"temp={state.air_temp:5.1f}°C | "
          f"damage={state.cumulative_damage:5.1f}% | "
          f"alive={state.is_alive}")


def _run_simulation_loop():
    """Background thread for running simulation"""
    global _engine, _orchestrator, _simulation_running, _simulation_config

    mode = _simulation_config.get('mode', 'speed')
    hours_per_tick = _simulation_config.get('hours_per_tick', 1)
    days = _simulation_config.get('days', 30)
    tick_delay = _simulation_config.get('tick_delay', 0.1)

    total_hours = days * 24
    plant_name = _simulation_config.get('plant_name', 'unknown')

    print(f"\n{'='*70}")
    print(f"SIMULATION STARTED - {plant_name.upper()}")
    print(f"{'='*70}")
    print(f"Mode: {'REALTIME (1 tick = 1 real hour)' if mode == 'realtime' else f'SPEED ({hours_per_tick} sim hours per tick)'}")
    print(f"Duration: {days} days ({total_hours} hours)")
    print(f"{'='*70}\n")

    current_time = datetime.now()
    file_name = f'data/records/logs_{current_time.strftime("%d%H%M")}.txt'


    hour = 0
    while _simulation_running and hour < total_hours and _engine.state.is_alive:
        # Run simulation step (hooks fire automatically)
        _engine.step(hours=1)
        display_metrics(_engine, hours_per_tick, show_tools=False, file_name=file_name)


        hour += 1

        # Calculate day and hour of day
        day = hour // 24
        hour_of_day = hour % 24

        # Print status every hour in realtime, every simulated day in speed mode
        if mode == 'realtime':
            _print_status(_engine.state, day, hour_of_day)
        elif hour_of_day == 0 or hour == 1:
            _print_status(_engine.state, day, hour_of_day)

        # Wait based on mode
        if mode == 'realtime':
            for _ in range(60):
                if not _simulation_running:
                    break
                time.sleep(60)
        else:
            if hours_per_tick > 1:
                for _ in range(hours_per_tick - 1):
                    if not _simulation_running or not _engine.state.is_alive:
                        break
                    _engine.step(hours=1)
                    hour += 1

            time.sleep(tick_delay)

    # Simulation ended
    _simulation_running = False

    print(f"\n{'='*70}")
    if not _engine.state.is_alive:
        print(f"SIMULATION ENDED - PLANT DIED at hour {hour}")
        print(f"Death reason: {_engine.state.death_reason}")
    else:
        print(f"SIMULATION COMPLETE - {days} days")
    print(f"{'='*70}")

    summary = _engine.get_summary()
    print(f"Final biomass: {summary['biomass']:.2f}g")
    print(f"Final stage: {summary['phenological_stage']}")
    print(f"Cumulative damage: {summary['cumulative_damage']:.1f}%")

    # Agent stats (via orchestrator — independent of engine)
    if _orchestrator:
        stats = _orchestrator.reasoning_agent.get_statistics()
        print(f"\nMonitor Alerts: {stats['total_alerts']} total "
              f"({stats['warnings']} warnings, {stats['criticals']} criticals)")

        log_path = _orchestrator.save_session_log()
        print(f"Reasoning log: {log_path}")
    print(f"{'='*70}\n")


@bp.route('/start', methods=['POST'])
def start_simulation():
    """
    Start and auto-run a new simulation

    Request body:
    {
        "plant_name": "tomato",      # optional, defaults to "tomato"
        "days": 30,                   # optional, defaults to 30
        "mode": "speed" | "realtime", # optional, defaults to "speed"
        "hours_per_tick": 1,          # optional, for speed mode (default: 1)
        "tick_delay": 0.1,            # optional, seconds between ticks (default: 0.1)
        "daily_regime": true,         # optional, defaults to true
        "monitor_enabled": true       # optional, defaults to true
    }

    Modes:
    - "speed": runs fast with configurable hours_per_tick
    - "realtime": waits 1 real hour between each simulation hour
    """
    global _engine, _orchestrator, _simulation_thread, _simulation_running, _simulation_config

    # Stop any existing simulation
    if _simulation_running:
        _simulation_running = False
        if _simulation_thread:
            _simulation_thread.join(timeout=2)

    data = request.get_json() or {}
    logger.info(f"Received start simulation request: {data}")

    plant_name = data.get('plant_name', 'tomato_standard')
    days = data.get('days', 30)
    mode = data.get('mode', 'speed')
    hours_per_tick = data.get('hours_per_tick', 1)
    tick_delay = data.get('tick_delay', 0.1)
    daily_regime = data.get('daily_regime', True)
    monitor_enabled = data.get('monitor_enabled', True)

    # Validate mode
    if mode not in ['speed', 'realtime']:
        return jsonify({
            'success': False,
            'error': 'mode must be "speed" or "realtime"'
        }), 400

    try:
        # Get plant profile
        try:
            profile = load_default_profile(plant_name)
        except Exception:
            list_plants()
            return jsonify({
                'success': False,
                'error': f'Unknown plant profile: {plant_name}',
                'available': list(DEFAULT_PROFILES.keys())
            }), 400

        # 1. Create engine (pure physics — no agent dependencies)
        _engine = SimulationEngine(profile)

        # 2. Configure daily regime on engine
        if daily_regime:
            _engine.set_daily_regime(enabled="True")
        else:
            _engine.set_daily_regime(enabled="False")

        # 3. Create agent orchestrator (independent — attaches via hooks)
        _orchestrator = AgentOrchestrator.create(
            engine=_engine,
            monitor_enabled=monitor_enabled,
        )

        # Store config
        _simulation_config = {
            'plant_name': plant_name,
            'days': days,
            'mode': mode,
            'hours_per_tick': hours_per_tick,
            'tick_delay': tick_delay,
            'daily_regime': daily_regime,
            'monitor_enabled': monitor_enabled
        }

        # Start simulation thread
        _simulation_running = True
        _simulation_thread = threading.Thread(target=_run_simulation_loop, daemon=True)
        _simulation_thread.start()

        return jsonify({
            'success': True,
            'message': f'Simulation started for {plant_name}',
            'simulation_id': _engine.simulation_id,
            'plant_id': _engine.plant_id,
            'profile_id': profile.profile_id,
            'config': _simulation_config
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/stop', methods=['POST'])
def stop_simulation():
    """Stop current simulation"""
    global _engine, _orchestrator, _simulation_running, _simulation_thread

    if not _simulation_running and _engine is None:
        return jsonify({
            'success': False,
            'error': 'No simulation running.'
        }), 400

    _simulation_running = False

    if _simulation_thread:
        _simulation_thread.join(timeout=5)

    summary = {}
    log_path = None
    if _engine:
        summary = _engine.get_summary()
    if _orchestrator:
        log_path = _orchestrator.save_session_log()

    return jsonify({
        'success': True,
        'message': 'Simulation stopped',
        'summary': summary,
        'reasoning_log': log_path
    })


@bp.route('/state', methods=['GET'])
def get_state():
    """Get current simulation state"""
    engine = get_engine()
    if engine is None:
        return jsonify({
            'success': False,
            'error': 'No simulation running.',
            'running': False
        }), 400

    state_dict = _sanitize(engine.state.to_dict())

    return jsonify({
        'success': True,
        'running': _simulation_running,
        'config': _simulation_config,
        'state': state_dict,
        'summary': _sanitize(engine.get_summary())
    })


@bp.route('/plants', methods=['GET'])
def get_plants():
    """Get available plant profiles"""
    plants = []
    for profile_id, profile in DEFAULT_PROFILES.items():
        plants.append({
            'id': profile_id,
            'name': profile.species_name,
            'common_names': profile.common_names if hasattr(profile, 'common_names') else []
        })

    return jsonify({
        'success': True,
        'plants': plants
    })


@bp.route('/history', methods=['GET'])
def get_history():
    """Get simulation history (last N hours)"""
    engine = get_engine()
    if engine is None:
        return jsonify({
            'success': False,
            'error': 'No simulation running.'
        }), 400

    limit = request.args.get('limit', default=24, type=int)
    history = engine.get_history()
    recent = history[-limit:] if len(history) > limit else history

    return jsonify({
        'success': True,
        'total_hours': len(history),
        'returned': len(recent),
        'history': _sanitize(recent)
    })


@bp.route('/step', methods=['POST'])
def step_simulation():
    """Manually advance the simulation by N hours.

    Request body: {"hours": 1}   # 1 | 6 | 12 | 24 | 168
    """
    engine = get_engine()
    if engine is None:
        return jsonify({
            'success': False,
            'error': 'No simulation running.'
        }), 400

    if not engine.state.is_alive:
        return jsonify({
            'success': False,
            'error': 'Plant is dead — simulation cannot be stepped.'
        }), 400

    data = request.get_json() or {}
    hours = int(data.get('hours', 1))
    if hours < 1 or hours > 720:
        return jsonify({
            'success': False,
            'error': 'hours must be between 1 and 720.'
        }), 400

    for _ in range(hours):
        if not engine.state.is_alive:
            break
        engine.step(hours=1)

    state_dict = _sanitize(engine.state.to_dict())
    return jsonify({
        'success': True,
        'hours_stepped': hours,
        'state': state_dict,
        'summary': _sanitize(engine.get_summary())
    })


@bp.route('/monitor/alerts', methods=['GET'])
def get_monitor_alerts():
    """Get recent monitor alerts (via orchestrator)"""
    orchestrator = get_orchestrator()
    if orchestrator is None:
        return jsonify({
            'success': False,
            'error': 'No simulation running or agents not attached.'
        }), 400

    limit = request.args.get('limit', default=10, type=int)
    alerts = orchestrator.reasoning_agent.get_recent_alerts(limit)
    stats = orchestrator.reasoning_agent.get_statistics()

    return jsonify({
        'success': True,
        'statistics': stats,
        'alerts': alerts
    })

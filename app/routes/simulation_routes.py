"""Simulation API routes with auto-running simulation"""

import sys
import os
import json
import math
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from flask import Blueprint, jsonify, request
from models.engine import SimulationEngine
from models.plant_profile import PlantProfile
from data.default_plants import DEFAULT_PROFILES, load_default_profile
from agents.orchestrator import AgentOrchestrator
import logging
from tools.debug import display_metrics, display_final_summary
from services.bigquery_service import BigQueryService



logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bp = Blueprint('simulation', __name__)

# Desired real-time seconds per simulated hour (adjust as needed)
# E.g., 5.0 = want 5 real seconds to simulate 1 hour
DESIRED_SECONDS_PER_SIM_HOUR = 5.0


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

# MQTT integration — publisher runs inside the simulation loop,
# subscriber is spawned as a subprocess alongside the simulation.
_mqtt_client = None
_mqtt_pub_cfg: dict = {}
_subscriber_proc = None


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


def _load_mqtt_cfg() -> dict:
    """Load MQTT settings from plant-metrics-mqtt/config/.env."""
    env_path = (
        Path(__file__).resolve().parent.parent.parent
        / 'plant-metrics-mqtt' / 'config' / '.env'
    )
    raw: dict = {}
    try:
        from dotenv import dotenv_values
        raw = dict(dotenv_values(env_path))
    except Exception:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, _, v = line.partition('=')
                    raw[k.strip()] = v.strip()
    return {
        'broker_url': raw.get('MQTT_BROKER_URL', 'test.mosquitto.org'),
        'port': int(raw.get('MQTT_PORT', '1883')),
        'topic': raw.get('MQTT_TOPIC', 'companyA/GH-A1/environment'),
        'qos': int(raw.get('MQTT_QOS', '1')),
        'keepalive': int(raw.get('MQTT_KEEPALIVE', '60')),
        'payload_fields': raw.get('MQTT_PAYLOAD_FIELDS', '').strip(),
    }


def _start_mqtt_integration():
    """Start built-in MQTT publisher client and auto-spawn subscriber subprocess."""
    global _mqtt_client, _mqtt_pub_cfg, _subscriber_proc

    _mqtt_pub_cfg = _load_mqtt_cfg()

    # ── Publisher (paho client, publishes from inside the simulation loop) ───
    try:
        import paho.mqtt.client as mqtt
        _mqtt_client = mqtt.Client(client_id='plant-sim-publisher')

        def _on_connect(c, ud, flags, rc):
            if rc == 0:
                logger.info(
                    f'[MQTT] Publisher connected → '
                    f'{_mqtt_pub_cfg["broker_url"]}:{_mqtt_pub_cfg["port"]}'
                )
            else:
                logger.warning(f'[MQTT] Publisher connection failed (rc={rc})')

        _mqtt_client.on_connect = _on_connect
        _mqtt_client.connect(
            _mqtt_pub_cfg['broker_url'],
            _mqtt_pub_cfg['port'],
            _mqtt_pub_cfg['keepalive'],
        )
        _mqtt_client.loop_start()
        logger.info(f'[MQTT] Publisher ready → topic={_mqtt_pub_cfg["topic"]}')
    except ImportError:
        logger.info(
            '[MQTT] paho-mqtt not installed — publishing disabled. '
            'Run: pip install paho-mqtt'
        )
        _mqtt_client = None
    except Exception as exc:
        logger.warning(f'[MQTT] Publisher init failed: {exc}')
        _mqtt_client = None

    # ── Subscriber subprocess ────────────────────────────────────────────────
    try:
        sub_script = (
            Path(__file__).resolve().parent.parent.parent
            / 'plant-metrics-mqtt' / 'subscriber' / 'mqtt_subscriber.py'
        )
        if sub_script.exists():
            _subscriber_proc = subprocess.Popen(
                [sys.executable, str(sub_script)],
                cwd=str(sub_script.parent.parent),
            )
            logger.info(f'[MQTT] Subscriber started (pid={_subscriber_proc.pid})')
        else:
            logger.warning(f'[MQTT] Subscriber script not found: {sub_script}')
            _subscriber_proc = None
    except Exception as exc:
        logger.warning(f'[MQTT] Subscriber subprocess failed: {exc}')
        _subscriber_proc = None


def _stop_mqtt_integration():
    """Stop MQTT publisher client and subscriber subprocess."""
    global _mqtt_client, _subscriber_proc

    if _mqtt_client:
        try:
            _mqtt_client.loop_stop()
            _mqtt_client.disconnect()
            logger.info('[MQTT] Publisher disconnected')
        except Exception as exc:
            logger.debug(f'[MQTT] Publisher disconnect error: {exc}')
        _mqtt_client = None

    if _subscriber_proc:
        try:
            _subscriber_proc.terminate()
            _subscriber_proc.wait(timeout=5)
            logger.info(f'[MQTT] Subscriber stopped (pid={_subscriber_proc.pid})')
        except Exception as exc:
            logger.debug(f'[MQTT] Subscriber stop error: {exc}')
        _subscriber_proc = None


def _publish_mqtt_state(state_dict: dict):
    """Publish one hourly state snapshot to MQTT (non-blocking, best-effort)."""
    if not _mqtt_client:
        return
    try:
        fields_csv = _mqtt_pub_cfg.get('payload_fields', '')
        if fields_csv:
            fields = [f.strip() for f in fields_csv.split(',') if f.strip()]
            payload = {k: state_dict[k] for k in fields if k in state_dict}
        else:
            payload = dict(state_dict)
        _mqtt_client.publish(
            _mqtt_pub_cfg['topic'],
            json.dumps(payload, default=str),
            qos=_mqtt_pub_cfg.get('qos', 1),
        )
    except Exception as exc:
        logger.debug(f'[MQTT] Publish error: {exc}')


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
    print(f"Mode: {'REALTIME (1 tick = {hours_per_tick} real hours)' if mode == 'realtime' else f'SPEED ({hours_per_tick} sim hours per tick)'}")
    print(f"Duration: {days} days ({total_hours} hours)")
    print(f"hours_per_tick={hours_per_tick}, tick_delay={tick_delay}s")
    print(f"{'='*70}\n")

    current_time = datetime.now()
    file_name = f'data/records/logs_{current_time.strftime("%d%H%M")}.txt'

    hour = 0
    tick_count = 0

    while _simulation_running and hour < total_hours and _engine.state.is_alive:
        tick_count += 1
        tick_start_hour = hour
        
        # Step all hours for this tick at once; publish every individual hour to MQTT
        for _ in range(hours_per_tick):
            if not _simulation_running or not _engine.state.is_alive:
                break
            _engine.step(hours=1)
            hour += 1
            _publish_mqtt_state(_engine.state.to_dict())

        # Display metrics once per complete tick
        display_metrics(_engine, hours_per_tick, show_tools=False, file_name=file_name)

        # Log tick progress
        day = hour // 24
        hour_of_day = hour % 24
        logger.info(f'[TICK {tick_count}] Stepped {hours_per_tick:2d}h → Total: {hour:4d}/{total_hours} hours '
                    f'(day {day:2d}, {hour_of_day:02d}:00)')

        # Print status once per simulated day or on first tick
        if hour_of_day == 0 or tick_count == 1:
            _print_status(_engine.state, day, hour_of_day)

        # Check if plant died — immediately break to avoid delays in sleep loops
        if not _engine.state.is_alive:
            break

        # Wait based on mode
        if mode == 'realtime':
            # Each simulated hour = 1 real hour
            for _ in range(hours_per_tick * 60):
                if not _simulation_running or not _engine.state.is_alive:
                    break
                time.sleep(60)
        else:
            # Speed mode: configurable delay
            time.sleep(tick_delay)

    # Simulation ended (loop broke due to plant death or time limit)
    # Keep _simulation_running = True so frontend keeps displaying the final state
    # Only set to False when explicitly stopped or new simulation starts

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

    # Stop MQTT integration when simulation ends naturally
    _stop_mqtt_integration()

    # Flush remaining BigQuery rows and write the run summary
    try:
        bq = BigQueryService.get()
        run_row = bq.build_run_row(
            engine=_engine,
            user_id=_simulation_config.get('user_id', ''),
            plant_species=_simulation_config.get('plant_name', ''),
            tick_gap_hours=_simulation_config.get('hours_per_tick', 1),
            daily_regime_enabled=bool(_simulation_config.get('daily_regime', True)),
            started_at=_simulation_config.get('started_at', ''),
        )
        bq.log_run_row(run_row)
        bq.flush_all()
        if bq.connected:
            print(f"BigQuery: run summary written ({_engine.state.hour} hourly rows flushed)")
    except Exception as _bq_exc:
        logger.warning('BigQuery end-of-run flush failed: %s', _bq_exc)


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
        "daily_regime": true,         # optional, defaults to true
        "monitor_enabled": true       # optional, defaults to true
    }

    Modes:
    - "speed": runs fast with configurable hours_per_tick
      (tick_delay auto-calculated as hours_per_tick * 5.0 seconds per sim-hour)
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
    logger.info(f"Hours per tick: {hours_per_tick}")
    
    # tick_delay is fixed — hours_per_tick controls simulation speed by stepping more
    # hours per tick, not by stretching the delay.
    # 1h/tick  → 5s delay, simulates  1h → 5s per sim-hour
    # 24h/tick → 5s delay, simulates 24h → 0.2s per sim-hour (24× faster)
    tick_delay = DESIRED_SECONDS_PER_SIM_HOUR
    logger.info(f"tick_delay={tick_delay}s (fixed), hours_per_tick={hours_per_tick}")
    daily_regime_raw = data.get('daily_regime', True)
    # Normalize to bool — frontend may send the JSON string "false" which is
    # truthy in Python even though it means OFF.
    if isinstance(daily_regime_raw, str):
        daily_regime = daily_regime_raw.strip().lower() not in ('false', '0', 'no', '')
    else:
        daily_regime = bool(daily_regime_raw)
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

        # Resolve user_id from auth token (used by BigQuery + simulation count)
        user_id = ''
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            try:
                from services.user_service import UserService
                svc = UserService.get()
                uid = svc.verify_token(auth_header[len('Bearer '):])
                if uid:
                    user_id = uid
                    svc.increment_simulation_count(uid)
            except Exception:
                pass

        # Store config (including user_id and start time for BigQuery run row)
        _simulation_config = {
            'plant_name': plant_name,
            'days': days,
            'mode': mode,
            'hours_per_tick': hours_per_tick,
            'tick_delay': tick_delay,
            'daily_regime': daily_regime,
            'monitor_enabled': monitor_enabled,
            'user_id': user_id,
            'started_at': datetime.now(timezone.utc).isoformat(),
        }

        # Start MQTT publisher (built-in) and subscriber (subprocess)
        _start_mqtt_integration()

        # Register BigQuery per-hour hook on the engine
        try:
            bq = BigQueryService.get()
            _engine.register_post_step_hook(bq.make_hourly_hook(
                user_id=user_id,
                plant_species=plant_name,
                tick_gap_hours=hours_per_tick,
                daily_regime_enabled=bool(daily_regime),
            ))
            if bq.connected:
                logger.info('BigQueryService: hourly hook registered for simulation %s', _engine.simulation_id)
        except Exception as _bq_exc:
            logger.warning('BigQuery hook registration failed: %s', _bq_exc)

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

    # Stop MQTT publisher and subscriber
    _stop_mqtt_integration()

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

    # Resolve default step from user profile if token provided
    default_hours = 1
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        try:
            from services.user_service import UserService
            svc = UserService.get()
            uid = svc.verify_token(auth_header[len('Bearer '):])
            if uid:
                profile = svc.get_profile(uid)
                if profile:
                    default_hours = profile.get('step_size', 1)
        except Exception:
            pass

    from services.user_service import ALLOWED_STEP_SIZES
    hours_raw = data.get('hours')
    if hours_raw is None:
        hours = default_hours
    else:
        try:
            hours = int(hours_raw)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'hours must be an integer.'}), 400

    if hours not in ALLOWED_STEP_SIZES:
        return jsonify({
            'success': False,
            'error': f'hours must be one of {ALLOWED_STEP_SIZES}.'
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


@bp.route('/metrics', methods=['GET'])
def get_metrics():
    """Get simulation metrics from log files for charting.

    Returns parsed CSV data from the current session log and physics metric files.
    """
    engine = get_engine()
    if engine is None:
        return jsonify({
            'success': False,
            'error': 'No simulation running.'
        }), 400

    import glob as glob_mod

    result = {'success': True, 'files': {}}

    # Find the current session log (most recent logs_*.txt)
    log_files = sorted(glob_mod.glob('data/records/logs_*.txt'))
    if log_files:
        latest_log = log_files[-1]
        try:
            with open(latest_log, 'r') as f:
                lines = f.readlines()
            rows = []
            for line in lines:
                parts = [p.strip() for p in line.strip().split(',')]
                if len(parts) >= 9:
                    try:
                        rows.append({
                            'day': float(parts[0]),
                            'biomass': float(parts[1]),
                            'stage': parts[2],
                            'humidity': float(parts[3]),
                            'air_temp': float(parts[4]),
                            'co2': float(parts[5]),
                            'rgr': float(parts[6]),
                            'et': float(parts[7]),
                            'water_stress': float(parts[8]),
                        })
                    except (ValueError, IndexError):
                        continue
            result['files']['session_log'] = rows
        except Exception:
            pass

    # Read physics metric files
    metric_files = {
        'photosynthesis': ('data/records/photosynthesis.txt', ['p_gross', 'light_par', 'light_interception', 'stress_factor']),
        'respiration': ('data/records/respiration.txt', ['r_maint', 'biomass', 'air_temp', 'temp_factor']),
        'leaf': ('data/records/leaf.txt', ['biomass', 'leaf_area', 'expansion_factor']),
        'soil_water': ('data/records/soil_water.txt', ['old_water', 'new_water', 'irrigation_pct', 'et_pct', 'drainage']),
        'water_stress': ('data/records/water_stress.txt', ['soil_water', 'wilting', 'opt_min', 'opt_max', 'saturation', 'instant_stress', 'new_stress', 'hours_dry', 'new_hours_dry']),
        'co2_consumption': ('data/records/co2_consumption.txt', ['co2_consumed']),
    }

    for key, (filepath, columns) in metric_files.items():
        try:
            with open(filepath, 'r') as f:
                lines = f.readlines()
            rows = []
            for line in lines:
                parts = [p.strip() for p in line.strip().split(',')]
                if len(parts) >= len(columns):
                    try:
                        row = {}
                        for i, col in enumerate(columns):
                            row[col] = float(parts[i])
                        rows.append(row)
                    except (ValueError, IndexError):
                        continue
            result['files'][key] = rows
        except FileNotFoundError:
            result['files'][key] = []

    return jsonify(_sanitize(result))


@bp.route('/regime', methods=['POST'])
def set_regime():
    """Update the daily care regime while the simulation is running.

    Body (JSON):
        enabled              : bool   — turn regime on/off
        watering_hour        : int    — hour of day to water (0-23)
        ventilation_hour     : int    — hour of day to ventilate (0-23)
        water_amount         : float  — liters per watering event
        fan_speed            : float  — ventilation fan speed (0-100%)
        co2_enrichment       : bool
        co2_target           : float  — ppm
        target_temp          : float|null — °C override (null = use profile)
        target_par           : float|null — µmol/m²/s override (null = use profile)
        notify_nutrient_stress: bool  — emit alert when nutrient_stress > 0.3
    """
    engine = get_engine()
    if engine is None:
        return jsonify({'success': False, 'error': 'No simulation running.'}), 400

    data = request.get_json() or {}

    enabled           = data.get('enabled', True)
    watering_hour     = int(data.get('watering_hour', 7))
    ventilation_hour  = int(data.get('ventilation_hour', 12))
    water_amount      = float(data.get('water_amount', 0.3))
    fan_speed         = float(data.get('fan_speed', 20.0))
    co2_enrichment    = bool(data.get('co2_enrichment', True))
    co2_target        = float(data.get('co2_target', 1000.0))
    target_temp       = data.get('target_temp')   # None is allowed
    target_par        = data.get('target_par')    # None is allowed
    notify_nutrient   = bool(data.get('notify_nutrient_stress', False))

    engine.set_daily_regime(
        enabled=enabled,
        watering_hour=watering_hour,
        ventilation_hour=ventilation_hour,
        water_amount=water_amount,
        fan_speed=fan_speed,
        co2_enrichment=co2_enrichment,
        co2_target=co2_target,
        target_temp=float(target_temp) if target_temp is not None else None,
        target_par=float(target_par) if target_par is not None else None,
    )

    # Persist notify flag and updated regime settings in shared config
    _simulation_config['notify_nutrient_stress'] = notify_nutrient
    _simulation_config['regime'] = {
        'enabled': engine.daily_regime_enabled,
        'watering_hour': engine.watering_hour,
        'ventilation_hour': engine.ventilation_hour,
        'water_amount': engine.daily_water_amount,
        'fan_speed': engine.daily_ventilation_speed,
        'co2_enrichment': engine.co2_enrichment_enabled,
        'co2_target': engine.co2_target_ppm,
        'target_temp': engine.regime_target_temp,
        'target_par': engine.regime_target_par,
    }

    # Sync executor agent if orchestrator is attached
    orchestrator = get_orchestrator()
    if orchestrator is not None:
        orchestrator.sync_regime_config(engine)

    logger.info(f"Regime updated via API: {_simulation_config['regime']}")

    return jsonify({
        'success': True,
        'message': 'Daily regime updated',
        'config': _simulation_config,
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

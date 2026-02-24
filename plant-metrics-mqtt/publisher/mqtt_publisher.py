"""
MQTT Publisher — Plant Lab Simulation

Runs the SimulationEngine directly (now lives inside PlantLabSimulation/)
and publishes each hourly plant-state snapshot to the configured MQTT broker.

Key behaviour
─────────────
• Steps the engine by MQTT_HOURS_PER_STEP sim-hours per publish cycle.
• Reloads config/.env every CONFIG_RELOAD_CYCLES cycles so that a running
  Flask server can update hours_per_step (via /api/mqtt/config) and the
  publisher picks it up without restart.
• Auto-restarts the simulation engine if the plant dies.

Usage:
    python publisher/mqtt_publisher.py

Environment (plant-metrics-mqtt/config/.env):
    MQTT_BROKER_URL           broker hostname (default: test.mosquitto.org)
    MQTT_PORT                 broker port (default: 1883)
    MQTT_TOPIC                publish topic (default: companyA/GH-A1/environment)
    MQTT_QOS                  QoS level 0/1/2 (default: 1)
    MQTT_KEEPALIVE            keepalive seconds (default: 60)
    MQTT_PLANT_NAME           plant profile id (default: tomato_standard)
    MQTT_PUBLISH_INTERVAL_S   real-time seconds between publishes (default: 2.0)
    MQTT_HOURS_PER_STEP       sim-hours stepped per publish (default: 1)
    MQTT_PAYLOAD_FIELDS       comma-sep field whitelist (empty = full state)
"""

import sys
import json
import time
import logging
from pathlib import Path

# ── Bootstrap ─────────────────────────────────────────────────────────────────
# plant-metrics-mqtt/ is now inside PlantLabSimulation/:
#   publisher/ → plant-metrics-mqtt/ → PlantLabSimulation/
_PLANT_LAB = Path(__file__).resolve().parent.parent.parent
if str(_PLANT_LAB) not in sys.path:
    sys.path.insert(0, str(_PLANT_LAB))

_ENV_FILE = Path(__file__).parent.parent / 'config' / '.env'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [PUBLISHER] %(levelname)s %(message)s',
)
logger = logging.getLogger(__name__)

# How many publish cycles between config/.env reloads
CONFIG_RELOAD_CYCLES = 30

# How many publish cycles between stop-flag checks
STOP_CHECK_CYCLES = 5


# ── Config loader ─────────────────────────────────────────────────────────────

def _load_env() -> dict:
    """Read config/.env and return a settings dict."""
    raw: dict = {}
    try:
        from dotenv import dotenv_values
        raw = dict(dotenv_values(_ENV_FILE))
    except ImportError:
        if _ENV_FILE.exists():
            for line in _ENV_FILE.read_text().splitlines():
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
        'plant_name': raw.get('MQTT_PLANT_NAME', 'tomato_standard'),
        'publish_interval': float(raw.get('MQTT_PUBLISH_INTERVAL_S', '2.0')),
        'hours_per_step': int(raw.get('MQTT_HOURS_PER_STEP', '1')),
        'payload_fields': raw.get('MQTT_PAYLOAD_FIELDS', '').strip(),
        # Cross-process coordination flags written by Flask.
        # Default True so publisher keeps running if Flask hasn't written the flag yet.
        'simulation_running': raw.get('MQTT_SIMULATION_RUNNING', 'true').lower() not in ('false', '0', 'no'),
        'flask_api_url': raw.get('FLASK_API_URL', ''),
    }


# ── Payload filter ────────────────────────────────────────────────────────────

def _filter_payload(state_dict: dict, fields_csv: str) -> dict:
    if not fields_csv:
        return dict(state_dict)
    fields = [f.strip() for f in fields_csv.split(',') if f.strip()]
    return {k: state_dict[k] for k in fields if k in state_dict}


# ── Engine factory ────────────────────────────────────────────────────────────

def _build_engine(plant_name: str):
    from models.engine import SimulationEngine
    from data.default_plants import load_default_profile
    return SimulationEngine(load_default_profile(plant_name))


# ── Main publisher loop ───────────────────────────────────────────────────────

def run_publisher():
    import paho.mqtt.client as mqtt

    cfg = _load_env()
    engine = _build_engine(cfg['plant_name'])

    client = mqtt.Client(client_id=f'plant-publisher-{cfg["plant_name"]}')

    def on_connect(c, userdata, flags, rc):
        if rc == 0:
            logger.info(f'Connected to {cfg["broker_url"]}:{cfg["port"]}')
        else:
            logger.error(f'Broker connection failed (rc={rc})')

    def on_disconnect(c, userdata, rc):
        if rc != 0:
            logger.warning(f'Unexpected disconnect (rc={rc})')

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    logger.info(f'Connecting to {cfg["broker_url"]}:{cfg["port"]} …')
    client.connect(cfg['broker_url'], cfg['port'], cfg['keepalive'])
    client.loop_start()

    logger.info(
        f'Simulation started — plant={cfg["plant_name"]}, '
        f'topic={cfg["topic"]}, '
        f'hours_per_step={cfg["hours_per_step"]}, '
        f'interval={cfg["publish_interval"]}s'
    )

    cycle = 0
    try:
        while True:
            # ── Check Flask stop signal every STOP_CHECK_CYCLES cycles ────
            if cycle % STOP_CHECK_CYCLES == 0:
                stop_cfg = _load_env()
                if not stop_cfg['simulation_running']:
                    logger.info('Flask simulation stopped — publisher exiting.')
                    break
                # Absorb any hours_per_step update discovered during stop check
                if stop_cfg['hours_per_step'] != cfg['hours_per_step']:
                    logger.info(
                        f'hours_per_step updated: '
                        f'{cfg["hours_per_step"]} → {stop_cfg["hours_per_step"]}'
                    )
                cfg = stop_cfg

            # ── Hot-reload full config every N cycles ──────────────────────
            elif cycle > 0 and cycle % CONFIG_RELOAD_CYCLES == 0:
                new_cfg = _load_env()
                if new_cfg['hours_per_step'] != cfg['hours_per_step']:
                    logger.info(
                        f'hours_per_step updated: '
                        f'{cfg["hours_per_step"]} → {new_cfg["hours_per_step"]}'
                    )
                cfg = new_cfg

            hours = cfg['hours_per_step']

            # ── Step engine by hours_per_step ──────────────────────────────
            for _ in range(hours):
                if not engine.state.is_alive:
                    break
                engine.step(hours=1)

            state_dict = engine.state.to_dict()
            payload = _filter_payload(state_dict, cfg['payload_fields'])
            payload_json = json.dumps(payload, default=str)

            result = client.publish(cfg['topic'], payload_json, qos=cfg['qos'])

            logger.info(
                f'H{state_dict.get("hour", "?"):>4} '
                f'(+{hours}h) | '
                f'stage={str(state_dict.get("phenological_stage", "?")):<12} | '
                f'biomass={state_dict.get("biomass", 0):.2f}g | '
                f'{len(payload_json)}B → {cfg["topic"]} (mid={result.mid})'
            )

            # ── Restart engine if plant dies ───────────────────────────────
            if not engine.state.is_alive:
                logger.warning(
                    f'Plant died ({engine.state.death_reason}). '
                    f'Restarting simulation.'
                )
                engine = _build_engine(cfg['plant_name'])

            time.sleep(cfg['publish_interval'])
            cycle += 1

    except KeyboardInterrupt:
        logger.info('Publisher stopped by user')
    finally:
        client.loop_stop()
        client.disconnect()

        # Signal Flask to stop its simulation engine too
        flask_url = cfg.get('flask_api_url', '')
        if flask_url:
            try:
                import urllib.request
                req = urllib.request.Request(
                    f'{flask_url}/api/simulation/stop',
                    method='POST',
                    headers={'Content-Type': 'application/json'},
                    data=b'{}',
                )
                urllib.request.urlopen(req, timeout=3)
                logger.info(f'Flask simulation stop signalled → {flask_url}')
            except Exception as _exc:
                logger.debug(f'Could not signal Flask stop: {_exc}')


if __name__ == '__main__':
    run_publisher()

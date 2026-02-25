"""
MQTT Publisher — Plant Lab Simulation

Two operating modes:

1. FLASK-BACKED MODE (default when FLASK_API_URL is set):
   Polls the Flask simulation API at GET /api/simulation/state and publishes
   each new hour's state to MQTT.  This keeps the publisher perfectly in sync
   with whatever simulation run.py is displaying in its terminal.

2. STANDALONE MODE (fallback when FLASK_API_URL is empty or unreachable):
   Runs its own SimulationEngine locally — the original behaviour.

Key behaviour
─────────────
• In Flask-backed mode a new MQTT message is emitted only when the simulation
  hour advances (no duplicate publishes for the same hour).
• In standalone mode the engine is stepped by MQTT_HOURS_PER_STEP per cycle.
• Config/.env is reloaded every CONFIG_RELOAD_CYCLES so a running Flask server
  can update hours_per_step (via /api/mqtt/config) without restarting.
• Auto-restarts the standalone engine if the plant dies.

Usage:
    python publisher/mqtt_publisher.py

Environment (plant-metrics-mqtt/config/.env):
    MQTT_BROKER_URL           broker hostname (default: test.mosquitto.org)
    MQTT_PORT                 broker port (default: 1883)
    MQTT_TOPIC                publish topic (default: companyA/GH-A1/environment)
    MQTT_QOS                  QoS level 0/1/2 (default: 1)
    MQTT_KEEPALIVE            keepalive seconds (default: 60)
    MQTT_PLANT_NAME           plant profile id used in standalone mode (default: tomato_standard)
    MQTT_PUBLISH_INTERVAL_S   real-time seconds between polls/publishes (default: 2.0)
    MQTT_HOURS_PER_STEP       sim-hours stepped per cycle in standalone mode (default: 1)
    MQTT_PAYLOAD_FIELDS       comma-sep field whitelist (empty = full state)
    FLASK_API_URL             Flask server URL — enables Flask-backed mode when set
                              (default: http://localhost:5010)
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

# Short sleep between polls when waiting for the simulation hour to advance
POLL_INTERVAL_S = 1.0


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
        'flask_api_url': raw.get('FLASK_API_URL', 'http://localhost:5010').rstrip('/'),
    }


# ── Payload filter ────────────────────────────────────────────────────────────

def _filter_payload(state_dict: dict, fields_csv: str) -> dict:
    if not fields_csv:
        return dict(state_dict)
    fields = [f.strip() for f in fields_csv.split(',') if f.strip()]
    return {k: state_dict[k] for k in fields if k in state_dict}


# ── Standalone engine factory ─────────────────────────────────────────────────

def _build_engine(plant_name: str):
    from models.engine import SimulationEngine
    from data.default_plants import load_default_profile
    return SimulationEngine(load_default_profile(plant_name))


# ── Flask state fetch ─────────────────────────────────────────────────────────

def _fetch_flask_state(flask_url: str) -> dict | None:
    """
    Poll GET /api/simulation/state on the Flask server.
    Returns the raw state dict on success, None otherwise.
    """
    import urllib.request
    import urllib.error
    try:
        url = f'{flask_url}/api/simulation/state'
        with urllib.request.urlopen(url, timeout=3) as resp:
            data = json.loads(resp.read())
        if data.get('success') and 'state' in data:
            return data['state']
        return None
    except urllib.error.URLError as exc:
        logger.debug(f'Flask state fetch failed: {exc}')
        return None
    except Exception as exc:
        logger.debug(f'Flask state fetch error: {exc}')
        return None


def _flask_is_available(flask_url: str) -> bool:
    """Quick connectivity probe to the Flask server."""
    import urllib.request
    import urllib.error
    try:
        urllib.request.urlopen(f'{flask_url}/api', timeout=2)
        return True
    except Exception:
        return False


# ── Main publisher loop ───────────────────────────────────────────────────────

def run_publisher():
    import paho.mqtt.client as mqtt

    cfg = _load_env()

    # ── Decide operating mode ──────────────────────────────────────────────────
    flask_url = cfg['flask_api_url']
    use_flask = bool(flask_url) and _flask_is_available(flask_url)

    if use_flask:
        logger.info(
            f'Flask-backed mode: publishing state from {flask_url}/api/simulation/state'
        )
        engine = None
    else:
        if flask_url:
            logger.warning(
                f'Flask server not reachable at {flask_url}. '
                f'Falling back to standalone engine mode.'
            )
        else:
            logger.info('No FLASK_API_URL set. Running in standalone engine mode.')
        engine = _build_engine(cfg['plant_name'])

    # ── MQTT client setup ──────────────────────────────────────────────────────
    client = mqtt.Client(client_id=f'plant-publisher-{"flask" if use_flask else cfg["plant_name"]}')

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

    mode_label = 'flask-backed' if use_flask else f'standalone plant={cfg["plant_name"]}'
    logger.info(
        f'Publisher running — mode={mode_label}, '
        f'topic={cfg["topic"]}, '
        f'interval={cfg["publish_interval"]}s'
    )

    cycle = 0
    last_published_hour = -1  # used in flask-backed mode to skip duplicate hours

    try:
        while True:
            # ── Check Flask stop signal every STOP_CHECK_CYCLES cycles ────────
            if cycle % STOP_CHECK_CYCLES == 0:
                stop_cfg = _load_env()
                if not stop_cfg['simulation_running']:
                    logger.info('Flask simulation stopped — publisher exiting.')
                    break
                if stop_cfg['hours_per_step'] != cfg['hours_per_step']:
                    logger.info(
                        f'hours_per_step updated: '
                        f'{cfg["hours_per_step"]} → {stop_cfg["hours_per_step"]}'
                    )
                cfg = stop_cfg

            # ── Hot-reload full config every N cycles ──────────────────────────
            elif cycle > 0 and cycle % CONFIG_RELOAD_CYCLES == 0:
                new_cfg = _load_env()
                if new_cfg['hours_per_step'] != cfg['hours_per_step']:
                    logger.info(
                        f'hours_per_step updated: '
                        f'{cfg["hours_per_step"]} → {new_cfg["hours_per_step"]}'
                    )
                cfg = new_cfg

            # ── Obtain state dict ──────────────────────────────────────────────
            if use_flask:
                state_dict = _fetch_flask_state(cfg['flask_api_url'])
                if state_dict is None:
                    # Simulation not started on Flask yet — wait quietly
                    logger.debug('Waiting for Flask simulation to start…')
                    time.sleep(POLL_INTERVAL_S)
                    cycle += 1
                    continue

                current_hour = state_dict.get('hour', -1)
                if current_hour == last_published_hour:
                    # Hour hasn't advanced yet — poll faster than publish_interval
                    time.sleep(POLL_INTERVAL_S)
                    cycle += 1
                    continue

                last_published_hour = current_hour
                hours_label = current_hour

            else:
                # Standalone: step the engine ourselves
                hours = cfg['hours_per_step']
                for _ in range(hours):
                    if not engine.state.is_alive:
                        break
                    engine.step(hours=1)
                state_dict = engine.state.to_dict()
                hours_label = state_dict.get('hour', '?')

            # ── Publish ────────────────────────────────────────────────────────
            payload = _filter_payload(state_dict, cfg['payload_fields'])
            payload_json = json.dumps(payload, default=str)
            result = client.publish(cfg['topic'], payload_json, qos=cfg['qos'])

            logger.info(
                f'H{hours_label!s:>4} | '
                f'stage={str(state_dict.get("phenological_stage", "?")):<12} | '
                f'biomass={state_dict.get("biomass", 0):.2f}g | '
                f'{len(payload_json)}B → {cfg["topic"]} (mid={result.mid})'
            )

            # ── Standalone: restart engine if plant dies ───────────────────────
            if not use_flask and not engine.state.is_alive:
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

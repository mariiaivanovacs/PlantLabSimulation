"""
MQTT configuration & status endpoints.

GET  /api/mqtt/config   — return current MQTT broker config
POST /api/mqtt/config   — update config and persist to plant-metrics-mqtt/config/.env
GET  /api/mqtt/latest   — fetch the most recent MQTT message from Firestore
"""

import os
import logging
from pathlib import Path

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)
bp = Blueprint('mqtt', __name__)

# plant-metrics-mqtt/ is now INSIDE PlantLabSimulation/, so path is:
#   app/routes/mqtt_routes.py → app/routes/ → app/ → PlantLabSimulation/
#   → plant-metrics-mqtt/config/.env
_MQTT_ENV = (
    Path(__file__).resolve().parent.parent.parent  # → PlantLabSimulation/
    / 'plant-metrics-mqtt'
    / 'config'
    / '.env'
)

# In-memory config — seeded from the host environment at startup.
_config: dict = {
    'broker_url': os.getenv('MQTT_BROKER_URL', 'test.mosquitto.org'),
    'port': int(os.getenv('MQTT_PORT', '1883')),
    'topic': os.getenv('MQTT_TOPIC', 'companyA/GH-A1/environment'),
    'subscribe_topic': os.getenv('MQTT_SUBSCRIBE_TOPIC', 'companyA/+/environment'),
    'qos': int(os.getenv('MQTT_QOS', '1')),
    'keepalive': int(os.getenv('MQTT_KEEPALIVE', '60')),
    # Simulation speed — kept in sync with Flask simulation when it starts.
    'hours_per_step': int(os.getenv('MQTT_HOURS_PER_STEP', '1')),
    # Cross-process coordination flags.
    'simulation_running': True,
    'flask_api_url': os.getenv('FLASK_API_URL', f'http://localhost:{os.getenv("PORT", "5010")}'),
}

_INT_KEYS = {'port', 'qos', 'keepalive', 'hours_per_step'}
_ALLOWED_KEYS = set(_config.keys())


# ── Public helpers called by simulation_routes ────────────────────────────────

def sync_simulation_speed(hours_per_tick: int, flask_api_url: str = '') -> None:
    """
    Called by simulation_routes when a new simulation starts.
    Updates the MQTT config so the publisher picks up the new speed.
    
    NOTE: The MQTT publisher runs as a separate process. It polls the Flask API
    (/api/mqtt/config) to stay in sync with simulation speed changes.
    """
    old_hours = _config.get('hours_per_step', 1)
    _config['hours_per_step'] = int(hours_per_tick)
    _config['simulation_running'] = True
    if flask_api_url:
        _config['flask_api_url'] = flask_api_url
    _persist_env()
    logger.info(f'MQTT sync: hours_per_step {old_hours} → {hours_per_tick}, '
                f'simulation_running=True')


def signal_publisher_stop() -> None:
    """
    Called when the Flask simulation stops (via /stop or natural end).
    Sets MQTT_SIMULATION_RUNNING=false in the publisher config so the
    publisher process exits on its next stop-check cycle.
    """
    _config['simulation_running'] = False
    _persist_env()
    logger.info('MQTT: publisher stop signal written')


# ── GET /config ───────────────────────────────────────────────────────────────

@bp.route('/config', methods=['GET'])
def get_config():
    return jsonify({'success': True, 'config': _config})


# ── POST /config ──────────────────────────────────────────────────────────────

@bp.route('/config', methods=['POST'])
def update_config():
    body = request.get_json(silent=True) or {}

    for key in _ALLOWED_KEYS:
        if key not in body:
            continue
        val = body[key]
        if key in _INT_KEYS:
            try:
                val = int(val)
            except (TypeError, ValueError):
                return jsonify({'success': False, 'error': f'{key} must be an integer'}), 400
        _config[key] = val

    _persist_env()
    return jsonify({'success': True, 'config': _config})


# ── GET /latest ───────────────────────────────────────────────────────────────

@bp.route('/latest', methods=['GET'])
def get_latest():
    """Return the most recently stored MQTT plant-state from Firestore."""
    try:
        import firebase_admin
        from firebase_admin import firestore as fs

        if not firebase_admin._apps:
            return jsonify({'success': False, 'error': 'Firebase not initialised'}), 503

        db = fs.client()
        docs = (
            db.collection('mqtt_plant_states')
            .order_by('_received_at', direction=fs.Query.DESCENDING)
            .limit(1)
            .stream()
        )
        for doc in docs:
            return jsonify({'success': True, 'state': doc.to_dict()})

        return jsonify({'success': False, 'error': 'No MQTT messages stored yet'})

    except Exception as exc:
        logger.exception('GET /mqtt/latest failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── helpers ───────────────────────────────────────────────────────────────────

def _persist_env() -> None:
    """Write the in-memory MQTT config back to plant-metrics-mqtt/config/.env."""
    try:
        _MQTT_ENV.parent.mkdir(parents=True, exist_ok=True)

        # Preserve non-MQTT lines already in the file
        preserved: list[str] = []
        if _MQTT_ENV.exists():
            for line in _MQTT_ENV.read_text().splitlines():
                stripped = line.strip()
                if stripped.startswith('MQTT_') or stripped == '' or stripped.startswith('#'):
                    continue
                preserved.append(line)

        new_lines = [
            '# MQTT Broker configuration — updated via Flask /api/mqtt/config',
            f'MQTT_BROKER_URL={_config["broker_url"]}',
            f'MQTT_PORT={_config["port"]}',
            f'MQTT_TOPIC={_config["topic"]}',
            f'MQTT_SUBSCRIBE_TOPIC={_config["subscribe_topic"]}',
            f'MQTT_QOS={_config["qos"]}',
            f'MQTT_KEEPALIVE={_config["keepalive"]}',
            f'MQTT_HOURS_PER_STEP={_config["hours_per_step"]}',
            f'MQTT_SIMULATION_RUNNING={str(_config["simulation_running"]).lower()}',
            f'FLASK_API_URL={_config["flask_api_url"]}',
        ]

        content = '\n'.join(preserved + new_lines) + '\n'
        _MQTT_ENV.write_text(content)
        logger.info(f'MQTT config persisted → {_MQTT_ENV}')

    except Exception as exc:
        logger.warning(f'Could not persist MQTT env: {exc}')

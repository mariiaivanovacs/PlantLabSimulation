"""
Plant management routes.
All Firestore access is server-side via Firebase Admin SDK.
No Firebase credentials are exposed to the client.

Endpoints (all require Bearer token):
  GET  /api/plants                          — list user's plants
  POST /api/plants                          — create a plant
  GET  /api/plants/<plant_id>/health-checks — list health checks for a plant
"""
import logging
from flask import Blueprint, jsonify, request
from services.user_service import UserService

logger = logging.getLogger(__name__)
bp = Blueprint('plants', __name__)


def _get_uid():
    """Verify Bearer token and return (uid, None) or (None, error_response)."""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None, (jsonify({'success': False,
                               'error': 'Missing or invalid Authorization header'}), 401)
    token = auth_header[len('Bearer '):]
    uid = UserService.get().verify_token(token)
    if uid is None:
        return None, (jsonify({'success': False,
                               'error': 'Invalid or expired token'}), 401)
    return uid, None


# ── List plants ───────────────────────────────────────────────────────────────

@bp.route('', methods=['GET'])
def list_plants():
    """Return all plants for the authenticated user."""
    uid, err = _get_uid()
    if err:
        return err

    try:
        plants = UserService.get().get_plants(uid)
        return jsonify({'success': True, 'plants': plants})
    except Exception:
        logger.exception('GET /plants failed')
        return jsonify({'success': False, 'error': 'Failed to load plants'}), 500


# ── Create plant ──────────────────────────────────────────────────────────────

@bp.route('', methods=['POST'])
def create_plant():
    """
    Create a new plant for the authenticated user.

    Body (JSON):
        name          : str  — user-given nickname
        identified_as : str  — "tomato" | "lettuce" | "basil"
        age_days      : int  — days since planting
    """
    uid, err = _get_uid()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    identified_as = (data.get('identified_as') or '').strip()
    age_days = int(data.get('age_days', 1))

    if not name:
        return jsonify({'success': False, 'error': 'name is required'}), 400
    if identified_as not in {'tomato', 'lettuce', 'basil'}:
        return jsonify({'success': False,
                        'error': 'identified_as must be tomato, lettuce, or basil'}), 400

    try:
        plant = UserService.get().add_plant(
            uid=uid,
            name=name,
            identified_as=identified_as,
            age_days=age_days,
        )
        return jsonify({'success': True, 'plant': plant}), 201
    except Exception:
        logger.exception('POST /plants failed')
        return jsonify({'success': False, 'error': 'Failed to create plant'}), 500


# ── List health checks ────────────────────────────────────────────────────────

@bp.route('/<plant_id>/health-checks', methods=['GET'])
def list_health_checks(plant_id: str):
    """Return the 20 most recent health checks for the given plant."""
    uid, err = _get_uid()
    if err:
        return err

    try:
        checks = UserService.get().get_health_checks(uid, plant_id)
        return jsonify({'success': True, 'health_checks': checks})
    except Exception:
        logger.exception('GET /plants/%s/health-checks failed', plant_id)
        return jsonify({'success': False, 'error': 'Failed to load health checks'}), 500

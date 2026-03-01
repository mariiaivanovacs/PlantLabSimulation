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

FREE_PLANT_LIMIT = 3


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


def _get_user_plan(uid: str) -> str:
    """Read subscriptionType from users/{uid}. Defaults to 'free'."""
    svc = UserService.get()
    if not svc._connected:
        return 'free'
    try:
        doc = svc._db.collection('users').document(uid).get()
        if doc.exists:
            return (doc.to_dict() or {}).get('plan', 'free')
    except Exception:
        logger.warning('Could not read plan for uid %s', uid)
    return 'free'


def _update_plant_count(uid: str, count: int, plan: str) -> None:
    """Write numberOfPlants and subscriptionType back to users/{uid}."""
    svc = UserService.get()
    if not svc._connected:
        return
    try:
        svc._db.collection('users').document(uid).set(
            {'numberOfPlants': count, 'subscriptionType': plan},
            merge=True,
        )
    except Exception:
        logger.warning('Could not update plant count for uid %s', uid)


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

    Returns 403 with upgrade_required=true when a free user hits the plant limit.
    """
    uid, err = _get_uid()
    if err:
        return err

    # ── Subscription / plant-limit check ──────────────────────────────────────
    plan = _get_user_plan(uid)
    if plan != 'pro':
        try:
            existing = UserService.get().get_plants(uid)
            if len(existing) >= FREE_PLANT_LIMIT:
                return jsonify({
                    'success': False,
                    'upgrade_required': True,
                    'error': (
                        f'Free plan supports up to {FREE_PLANT_LIMIT} plants. '
                        'Upgrade to Pro for unlimited plants.'
                    ),
                    'limit': FREE_PLANT_LIMIT,
                    'current': len(existing),
                }), 403
        except Exception:
            logger.exception('Plant limit check failed for uid %s', uid)

    # ── Validate body ─────────────────────────────────────────────────────────
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    identified_as = (data.get('identified_as') or '').strip()
    age_days = int(data.get('age_days', 1))

    if not name:
        return jsonify({'success': False, 'error': 'name is required'}), 400
    if identified_as not in {'tomato', 'lettuce', 'basil'}:
        return jsonify({'success': False,
                        'error': 'identified_as must be tomato, lettuce, or basil'}), 400

    # ── Create ────────────────────────────────────────────────────────────────
    try:
        svc = UserService.get()
        plant = svc.add_plant(uid=uid, name=name, identified_as=identified_as, age_days=age_days)

        # Keep users/{uid}.numberOfPlants in sync
        try:
            new_count = len(svc.get_plants(uid))
            _update_plant_count(uid, new_count, plan)
        except Exception:
            pass

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

"""Auth API routes — user profile management backed by Firestore."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from flask import Blueprint, jsonify, request
from services.user_service import UserService, ALLOWED_STEP_SIZES

bp = Blueprint('auth', __name__)


# ── helpers ──────────────────────────────────────────────────────────────────

def _get_uid() -> tuple[str | None, object | None]:
    """Extract and verify the Bearer token from Authorization header.

    Returns (uid, None) on success, (None, error_response) on failure.
    """
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None, jsonify({'success': False, 'error': 'Missing or invalid Authorization header'}), 401

    token = auth_header[len('Bearer '):]
    svc = UserService.get()
    uid = svc.verify_token(token)
    if uid is None:
        return None, jsonify({'success': False, 'error': 'Invalid or expired token'}), 401
    return uid, None


# ── endpoints ─────────────────────────────────────────────────────────────────

@bp.route('/profile', methods=['POST'])
def create_profile():
    """Create (or fetch) a user profile after the client authenticates.

    Request body:
        { "display_name": "Alice" }

    Authorization: Bearer <firebase-id-token>
    """
    uid, err = _get_uid()
    if err:
        return err

    data = request.get_json() or {}
    display_name = data.get('display_name', '')

    # Read the email from the token claim (already verified)
    auth_header = request.headers.get('Authorization', '')
    token = auth_header[len('Bearer '):]
    try:
        import firebase_admin.auth as fb_auth
        decoded = fb_auth.verify_id_token(token)
        email = decoded.get('email', '')
    except Exception:
        email = ''

    svc = UserService.get()
    profile = svc.get_or_create_profile(uid, email=email, display_name=display_name)
    return jsonify({'success': True, 'profile': profile})


@bp.route('/profile', methods=['GET'])
def get_profile():
    """Return the authenticated user's profile.

    Authorization: Bearer <firebase-id-token>
    """
    uid, err = _get_uid()
    if err:
        return err

    svc = UserService.get()
    profile = svc.get_profile(uid)
    if profile is None:
        return jsonify({'success': False, 'error': 'Profile not found. Call POST /api/auth/profile first.'}), 404
    return jsonify({'success': True, 'profile': profile})


@bp.route('/profile', methods=['PUT'])
def update_profile():
    """Partially update the authenticated user's profile.

    Request body (all fields optional):
        {
            "step_size":              1 | 2 | 3 | 6 | 12 | 24,
            "daily_regime_enabled":   true | false,
            "pot_size_L":             5.0,
            "default_plant":          "tomato_standard",
            "favorite_plants":        ["tomato_standard", "lettuce"]
        }

    Authorization: Bearer <firebase-id-token>
    """
    uid, err = _get_uid()
    if err:
        return err

    patch = request.get_json() or {}
    svc = UserService.get()
    try:
        profile = svc.update_profile(uid, patch)
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400

    return jsonify({'success': True, 'profile': profile})


@bp.route('/allowed-steps', methods=['GET'])
def allowed_steps():
    """Return the list of allowed step sizes (no auth required)."""
    return jsonify({'success': True, 'allowed_step_sizes': ALLOWED_STEP_SIZES})

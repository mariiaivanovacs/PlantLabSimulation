"""
User Service
Manages user settings in Firestore. Verifies Firebase ID tokens via firebase-admin.
Gracefully degrades to in-memory defaults when Firebase is not configured.
"""
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

ALLOWED_STEP_SIZES = [1, 2, 3, 6, 12, 24]

_DEFAULT_SETTINGS: Dict[str, Any] = {
    'step_size': 1,
    'daily_regime_enabled': True,
    'pot_size_L': 5.0,
    'default_plant': 'tomato_standard',
    'last_simulation_date': None,
    'total_simulations_run': 0,
    'favorite_plants': [],
}


class UserService:
    """
    Single-responsibility service for:
    - Verifying Firebase ID tokens
    - CRUD on user_settings Firestore collection
    - Graceful no-op when Firebase is not configured
    """

    _instance: Optional['UserService'] = None

    def __init__(self) -> None:
        self._db = None
        self._auth = None
        self._connected = False
        # In-memory fallback (keyed by uid) for local-dev without Firebase
        self._local: Dict[str, Dict[str, Any]] = {}
        self._try_connect()

    # ── singleton ────────────────────────────────────────────────────────────

    @classmethod
    def get(cls) -> 'UserService':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── internal setup ───────────────────────────────────────────────────────

    def _try_connect(self) -> None:
        try:
            import firebase_admin
            from firebase_admin import auth, credentials, firestore

            project_id = os.getenv('FIREBASE_PROJECT_ID')
            creds_path = os.getenv('FIREBASE_CREDENTIALS_PATH')

            try:
                firebase_admin.get_app()
            except ValueError:
                if creds_path:
                    cred = credentials.Certificate(creds_path)
                    firebase_admin.initialize_app(cred, {'projectId': project_id})
                elif project_id:
                    firebase_admin.initialize_app(options={'projectId': project_id})
                else:
                    firebase_admin.initialize_app()

            self._db = firestore.client()
            self._auth = auth
            self._connected = True
            logger.info('UserService: connected to Firebase')
        except ImportError:
            logger.warning('UserService: firebase-admin not installed — using local fallback')
        except Exception as exc:
            logger.warning('UserService: Firebase init failed (%s) — using local fallback', exc)

    def _col(self):
        return self._db.collection('user_settings') if self._connected else None

    # ── token verification ───────────────────────────────────────────────────

    def verify_token(self, id_token: str) -> Optional[str]:
        """Verify a Firebase ID token and return the uid, or None on failure."""
        if not self._connected:
            return None
        try:
            decoded = self._auth.verify_id_token(id_token)
            return decoded['uid']
        except Exception as exc:
            logger.warning('Token verification failed: %s', exc)
            return None

    # ── profile CRUD ─────────────────────────────────────────────────────────

    def get_or_create_profile(
        self,
        uid: str,
        email: str = '',
        display_name: str = '',
    ) -> Dict[str, Any]:
        """Return existing profile or create one with defaults."""
        existing = self.get_profile(uid)
        if existing:
            return existing
        return self._create_profile(uid, email, display_name)

    def get_profile(self, uid: str) -> Optional[Dict[str, Any]]:
        """Return profile dict or None if not found."""
        if self._connected:
            doc = self._col().document(uid).get()
            if doc.exists:
                data = doc.to_dict()
                data = self._coerce_timestamps(data)
                return data
            return None
        return self._local.get(uid)

    def update_profile(self, uid: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        """Apply a partial update and return the full updated profile."""
        allowed_fields = {
            'step_size', 'daily_regime_enabled', 'pot_size_L',
            'default_plant', 'favorite_plants',
        }
        clean = {k: v for k, v in patch.items() if k in allowed_fields}
        if 'step_size' in clean and clean['step_size'] not in ALLOWED_STEP_SIZES:
            raise ValueError(f"step_size must be one of {ALLOWED_STEP_SIZES}")

        clean['updated_at'] = datetime.now(timezone.utc).isoformat()

        if self._connected:
            ref = self._col().document(uid)
            ref.update(clean)
            updated = ref.get().to_dict()
            return self._coerce_timestamps(updated)

        # local fallback
        profile = self._local.setdefault(uid, dict(_DEFAULT_SETTINGS))
        profile.update(clean)
        return dict(profile)

    def increment_simulation_count(self, uid: str) -> None:
        """Increment total_simulations_run and set last_simulation_date."""
        now_iso = datetime.now(timezone.utc).isoformat()
        if self._connected:
            from firebase_admin import firestore as _fs
            ref = self._col().document(uid)
            ref.update({
                'total_simulations_run': _fs.Increment(1),
                'last_simulation_date': now_iso,
                'updated_at': now_iso,
            })
        else:
            profile = self._local.setdefault(uid, dict(_DEFAULT_SETTINGS))
            profile['total_simulations_run'] = profile.get('total_simulations_run', 0) + 1
            profile['last_simulation_date'] = now_iso

    # ── internal ─────────────────────────────────────────────────────────────

    def _create_profile(self, uid: str, email: str, display_name: str) -> Dict[str, Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        doc = {
            'user_id': uid,
            'email': email,
            'display_name': display_name or email.split('@')[0],
            **_DEFAULT_SETTINGS,
            'created_at': now_iso,
            'updated_at': now_iso,
        }
        if self._connected:
            self._col().document(uid).set(doc)
        else:
            self._local[uid] = dict(doc)
        return dict(doc)

    @staticmethod
    def _coerce_timestamps(data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Firestore Timestamp objects to ISO strings."""
        for key, val in data.items():
            if hasattr(val, 'isoformat'):
                data[key] = val.isoformat()
            elif hasattr(val, '_seconds'):  # Firestore Timestamp
                data[key] = datetime.fromtimestamp(val._seconds, tz=timezone.utc).isoformat()
        return data

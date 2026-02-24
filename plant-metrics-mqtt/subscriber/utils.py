"""
Utility helpers for the MQTT subscriber:
  - JSON schema validation
  - Payload normalisation
  - Firebase Firestore singleton
"""

import os
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Validation ────────────────────────────────────────────────────────────────

REQUIRED_FIELDS: List[str] = ['hour', 'is_alive', 'biomass', 'phenological_stage']
NON_NEGATIVE_FIELDS: List[str] = ['biomass', 'leaf_area', 'soil_water', 'hour']


def validate_state(payload: Dict[str, Any]) -> List[str]:
    """
    Basic schema validation.
    Returns a list of error strings; empty list means valid.
    """
    errors: List[str] = []

    for field in REQUIRED_FIELDS:
        if field not in payload:
            errors.append(f'Missing required field: {field}')

    for field in NON_NEGATIVE_FIELDS:
        val = payload.get(field)
        if val is not None and isinstance(val, (int, float)) and val < 0:
            errors.append(f'Field {field} must be >= 0, got {val}')

    return errors


# ── Normalisation ─────────────────────────────────────────────────────────────

_NUMERIC_FIELDS = ('hour', 'biomass', 'leaf_area', 'soil_water', 'air_temp', 'CO2',
                   'relative_humidity', 'VPD', 'light_PAR', 'photosynthesis',
                   'growth_rate', 'RGR', 'cumulative_damage',
                   'water_stress', 'temp_stress', 'nutrient_stress')


def normalize_state(payload: Dict[str, Any], topic: str) -> Dict[str, Any]:
    """
    Add ingestion metadata and coerce numeric string values.
    Returns a new dict (original is unchanged).
    """
    normalized = dict(payload)

    normalized['_mqtt_topic'] = topic
    normalized['_received_at'] = datetime.now(timezone.utc).isoformat()

    if 'timestamp' not in normalized:
        normalized['timestamp'] = normalized['_received_at']

    for key in _NUMERIC_FIELDS:
        val = normalized.get(key)
        if isinstance(val, str):
            try:
                normalized[key] = float(val)
            except ValueError:
                pass

    return normalized


# ── Firebase singleton ────────────────────────────────────────────────────────

_db = None


def get_firebase_db():
    """
    Lazy-initialise Firebase Firestore and return the client.
    Returns None if Firebase is unavailable (graceful degradation).
    """
    global _db
    if _db is not None:
        return _db

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        try:
            firebase_admin.get_app()
        except ValueError:
            creds_path = os.getenv('FIREBASE_CREDENTIALS_PATH', '').strip()
            project_id = os.getenv('FIREBASE_PROJECT_ID', '').strip() or None

            if creds_path:
                from pathlib import Path
                p = Path(creds_path)
                if not p.is_absolute():
                    # Resolve relative to PlantLabSimulation/ (parent of plant-metrics-mqtt/)
                    # subscriber/ → plant-metrics-mqtt/ → PlantLabSimulation/
                    _PLANT_LAB = Path(__file__).resolve().parent.parent.parent
                    p = _PLANT_LAB / creds_path
                cred = credentials.Certificate(str(p))
                init_kwargs = {'projectId': project_id} if project_id else {}
                firebase_admin.initialize_app(cred, init_kwargs)
            else:
                # Attempt Application Default Credentials (Cloud Run / gcloud)
                firebase_admin.initialize_app()

        _db = firestore.client()
        logger.info('Firebase Firestore connected')
        return _db

    except Exception as exc:
        logger.warning(f'Firebase unavailable: {exc}')
        return None

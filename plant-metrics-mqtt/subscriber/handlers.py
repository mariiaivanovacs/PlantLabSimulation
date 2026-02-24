"""
Message handler: validate → normalise → store to Firestore.
"""

import os
import logging
from typing import Any, Dict

from utils import validate_state, normalize_state, get_firebase_db

logger = logging.getLogger(__name__)

COLLECTION = os.getenv('MQTT_FIRESTORE_COLLECTION', 'mqtt_plant_states')


def handle_message(topic: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process one incoming MQTT plant-state message.

    Args:
        topic:   MQTT topic the message arrived on (e.g. companyA/GH-A1/environment)
        payload: Decoded JSON dict from the broker

    Returns:
        {'success': bool, 'doc_id': str | None, 'error': str | None}
    """
    # 1. Validate schema
    errors = validate_state(payload)
    if errors:
        logger.warning(f'Validation errors [{topic}]: {errors}')
        return {'success': False, 'doc_id': None, 'error': '; '.join(errors)}

    # 2. Normalise (add metadata, coerce types)
    normalized = normalize_state(payload, topic)

    # 3. Derive Firestore document ID:  <greenhouse_id>_h<hour:06d>
    parts = topic.split('/')
    gh_id = parts[1] if len(parts) >= 2 else 'unknown'
    hour = int(normalized.get('hour', 0))
    doc_id = f'{gh_id}_h{hour:06d}'

    # 4. Write to Firestore
    db = get_firebase_db()
    if db is None:
        # Graceful degradation: log the state locally
        logger.warning('Firebase unavailable — message logged locally only')
        logger.info(
            f'[LOCAL] {doc_id} | biomass={normalized.get("biomass", "?")}g | '
            f'stage={normalized.get("phenological_stage", "?")} | '
            f'alive={normalized.get("is_alive", "?")}'
        )
        return {'success': True, 'doc_id': None, 'error': None}

    try:
        db.collection(COLLECTION).document(doc_id).set(normalized)
        logger.info(f'Stored [{doc_id}] → Firestore/{COLLECTION}')
        return {'success': True, 'doc_id': doc_id, 'error': None}

    except Exception as exc:
        logger.error(f'Firestore write failed for {doc_id}: {exc}')
        return {'success': False, 'doc_id': None, 'error': str(exc)}

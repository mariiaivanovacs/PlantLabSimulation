"""
Gemini AI routes — plant identification and health checks.
All Gemini calls are server-side; the API key never reaches the client.

Required env var:  GEMINI_API_KEY
"""
import os
import base64
import json
import logging
import io

from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)
bp = Blueprint('gemini', __name__)

SUPPORTED_PLANTS = {'tomato', 'lettuce', 'basil'}

_IDENTIFY_PROMPT = (
    "Identify the plant shown. Reply with ONLY one of these exact words:\n"
    "  tomato   — Solanum lycopersicum (tomato plant)\n"
    "  lettuce  — Lactuca sativa (any lettuce variety)\n"
    "  basil    — Ocimum basilicum (sweet basil)\n"
    "  none     — cannot identify, or not one of the above\n"
    "One word only. No punctuation. No explanation."
)

_IDENTIFY_TEXT_TEMPLATE = (
    "The user describes their plant as: '{name}'.\n"
    "Which of these matches best? Reply with ONLY one exact word:\n"
    "  tomato   — tomato plant\n"
    "  lettuce  — any lettuce\n"
    "  basil    — sweet basil\n"
    "  none     — doesn't match any of the above\n"
    "One word only. No punctuation. No explanation."
)

_HEALTH_PROMPT_TEMPLATE = (
    "You are an expert plant biologist and health advisor.\n"
    "This is a {plant_type} plant that has been growing for {age_days} day(s).\n\n"
    "Carefully analyse the image and respond ONLY with valid JSON in this exact format "
    "(no markdown fences, no extra keys, floats in 0.0–1.0 range unless noted):\n"
    '{{\n'
    '  "phenological_stage": "one of: seed | seedling | vegetative | flowering | fruiting | mature",\n'
    '  "estimated_biomass_g": <float: estimated dry plant mass grams, e.g. 12.5>,\n'
    '  "estimated_leaf_area_m2": <float: total visible leaf area m², e.g. 0.045>,\n'
    '  "leaf_yellowing_score": <float 0-1: 0=all-green healthy, 1=severe yellowing/chlorosis>,\n'
    '  "leaf_droop_score": <float 0-1: 0=fully turgid upright, 1=severe wilting/drooping>,\n'
    '  "necrosis_score": <float 0-1: 0=no dead tissue, 1=widespread necrotic spots>,\n'
    '  "health_summary": "2-3 sentences: current health, visible symptoms, overall condition.",\n'
    '  "recommended_actions": ["specific action 1", "specific action 2", "specific action 3"]\n'
    '}}\n'
    "Be precise with the visual scores — they drive automated stress predictions. "
    "Recommended actions must be practical: watering schedule, fertilisation, light, "
    "temperature, pest or disease treatment."
)


def _model():
    """Return a configured Gemini GenerativeModel, or raise RuntimeError."""
    try:
        import google.generativeai as genai  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError('google-generativeai package not installed') from exc

    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise RuntimeError('GEMINI_API_KEY environment variable is not set')

    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-2.5-flash')


def _decode_image(image_b64: str):
    """Decode base64 image string and return a PIL Image."""
    from PIL import Image  # noqa: PLC0415
    raw = base64.b64decode(image_b64)
    return Image.open(io.BytesIO(raw))


def _strip_fences(text: str) -> str:
    """Remove markdown code fences that Gemini sometimes wraps JSON in."""
    text = text.strip()
    if text.startswith('```'):
        lines = text.splitlines()
        # Drop opening and closing fence lines
        lines = [l for l in lines if not l.startswith('```')]
        text = '\n'.join(lines).strip()
    return text


# ── Identify ─────────────────────────────────────────────────────────────────

@bp.route('/identify', methods=['POST'])
def identify_plant():
    """
    Identify the plant species from an image or a typed name.

    Body (JSON):
        image_b64  : str  — base64-encoded image (optional)
        plant_name : str  — text name typed by the user (optional)

    At least one of image_b64 / plant_name is required.

    Response:
        identified : "tomato" | "lettuce" | "basil" | "none"
        supported  : bool
    """
    data = request.get_json(silent=True) or {}
    image_b64 = data.get('image_b64', '')
    plant_name = (data.get('plant_name') or '').strip()

    if not image_b64 and not plant_name:
        return jsonify({'success': False,
                        'error': 'Provide image_b64 or plant_name'}), 400

    try:
        model = _model()
    except RuntimeError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 503

    try:
        if image_b64:
            img = _decode_image(image_b64)
            response = model.generate_content([_IDENTIFY_PROMPT, img])
        else:
            prompt = _IDENTIFY_TEXT_TEMPLATE.format(name=plant_name)
            response = model.generate_content(prompt)

        identified = response.text.strip().lower().split()[0]  # first word only
        # Normalise to known set
        if identified not in SUPPORTED_PLANTS | {'none'}:
            identified = 'none'

        return jsonify({
            'success': True,
            'identified': identified,
            'supported': identified in SUPPORTED_PLANTS,
        })

    except Exception:
        logger.exception('Gemini /identify failed')
        return jsonify({'success': False,
                        'error': 'AI identification failed. Please try again.'}), 500


# ── Health check ──────────────────────────────────────────────────────────────

@bp.route('/health', methods=['POST'])
def check_health():
    """
    Full plant health pipeline:
      1. Gemini extracts visual metrics from the photo
      2. XGBoost predicts water / nutrient / temperature stress
      3. ML + rule-based recommendations are merged
      4. Result is saved to Firestore (if auth token + plant_id provided)

    Body (JSON):
        image_b64         : str  — base64-encoded image (required)
        plant_type        : str  — "tomato" | "lettuce" | "basil"
        age_days          : int  — days since planting
        plant_id          : str  — Firestore plant doc ID (to save history)
        last_watering_days: float — optional, days since last watering
        room_temp_c       : float — optional, current room temperature °C
        soil_water_pct    : float — optional, soil moisture estimate

    Response:
        health_summary, recommended_actions,
        phenological_stage, estimated_biomass_g, estimated_leaf_area_m2,
        leaf_yellowing_score, leaf_droop_score, necrosis_score,
        water_stress, nutrient_stress, temperature_stress,
        water_stress_cat, nutrient_stress_cat, temperature_stress_cat,
        model_used, firestore_id
    """
    data       = request.get_json(silent=True) or {}
    image_b64  = data.get('image_b64', '')
    plant_type = data.get('plant_type', 'tomato')
    age_days   = int(data.get('age_days', 1))
    plant_id   = data.get('plant_id', '')

    # Optional env hints the client may pass
    last_watering_days = data.get('last_watering_days')
    room_temp_c        = data.get('room_temp_c')
    soil_water_pct     = data.get('soil_water_pct')

    if not image_b64:
        return jsonify({'success': False, 'error': 'image_b64 is required'}), 400

    try:
        gemini = _model()
    except RuntimeError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 503

    # ── Step 1: Gemini visual analysis ────────────────────────────────────────
    try:
        img    = _decode_image(image_b64)
        prompt = _HEALTH_PROMPT_TEMPLATE.format(
            plant_type=plant_type,
            age_days=age_days,
        )
        response = gemini.generate_content([prompt, img])
        raw      = _strip_fences(response.text)

        try:
            gemini_result = json.loads(raw)
        except json.JSONDecodeError:
            gemini_result = {'health_summary': response.text.strip(), 'recommended_actions': []}

    except Exception:
        logger.exception('Gemini /health failed')
        return jsonify({'success': False,
                        'error': 'AI health check failed. Please try again.'}), 500

    # Extract visual scores with safe defaults
    stage          = gemini_result.get('phenological_stage', 'vegetative')
    biomass        = float(gemini_result.get('estimated_biomass_g', 10.0))
    leaf_area      = float(gemini_result.get('estimated_leaf_area_m2', 0.02))
    yellowing      = float(gemini_result.get('leaf_yellowing_score', 0.0))
    droop          = float(gemini_result.get('leaf_droop_score', 0.0))
    necrosis       = float(gemini_result.get('necrosis_score', 0.0))
    health_summary = gemini_result.get('health_summary', '')
    gemini_actions = gemini_result.get('recommended_actions', [])

    # ── Step 2: XGBoost stress prediction ────────────────────────────────────
    from services.stress_prediction_service import StressPredictionService
    svc = StressPredictionService.get()

    pred = svc.predict(
        plant_type=plant_type,
        plant_age_days=age_days,
        phenological_stage=stage,
        estimated_biomass=biomass,
        leaf_area_m2=leaf_area,
        leaf_yellowing_score=yellowing,
        leaf_droop_score=droop,
        necrosis_score=necrosis,
        last_watering_days=last_watering_days,
        air_temp_c=room_temp_c,
        soil_water_pct=soil_water_pct,
    )

    # ── Step 3: Merge ML + Gemini recommendations ────────────────────────────
    ml_actions = svc.recommend_actions(
        water_stress=pred['water_stress'],
        nutrient_stress=pred['nutrient_stress'],
        temperature_stress=pred['temperature_stress'],
        plant_type=plant_type,
        leaf_yellowing_score=yellowing,
        necrosis_score=necrosis,
        last_watering_days=last_watering_days,
    )
    # Merge: ml_actions first (data-driven), then unique Gemini extras
    seen = set(ml_actions)
    merged_actions = ml_actions[:]
    for a in gemini_actions:
        if a not in seen:
            merged_actions.append(a)
            seen.add(a)
    merged_actions = merged_actions[:6]

    # ── Step 4: Firestore persistence ─────────────────────────────────────────
    firestore_id = None
    uid = None
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer ') and plant_id:
        try:
            from services.user_service import UserService
            uid = UserService.get().verify_token(auth_header[len('Bearer '):])
        except Exception:
            pass

    if uid and plant_id:
        record = {
            'timestamp':             __import__('datetime').datetime.utcnow().isoformat(),
            'plant_type':            plant_type,
            'age_days':              age_days,
            'phenological_stage':    stage,
            'estimated_biomass_g':   biomass,
            'estimated_leaf_area_m2': leaf_area,
            'leaf_yellowing_score':  yellowing,
            'leaf_droop_score':      droop,
            'necrosis_score':        necrosis,
            'water_stress':          pred['water_stress'],
            'nutrient_stress':       pred['nutrient_stress'],
            'temperature_stress':    pred['temperature_stress'],
            'water_stress_cat':      pred['water_stress_cat'],
            'nutrient_stress_cat':   pred['nutrient_stress_cat'],
            'temperature_stress_cat': pred['temperature_stress_cat'],
            'model_used':            pred['model_used'],
            'health_summary':        health_summary,
            'recommended_actions':   merged_actions,
            'last_watering_days':    last_watering_days,
            'room_temp_c':           room_temp_c,
        }
        firestore_id = StressPredictionService.save_to_firestore(uid, plant_id, record)

    # ── Step 5: Return enriched response ──────────────────────────────────────
    return jsonify({
        'success': True,
        # Gemini visual assessment
        'phenological_stage':     stage,
        'estimated_biomass_g':    biomass,
        'estimated_leaf_area_m2': leaf_area,
        'leaf_yellowing_score':   yellowing,
        'leaf_droop_score':       droop,
        'necrosis_score':         necrosis,
        # ML predictions
        'water_stress':           pred['water_stress'],
        'nutrient_stress':        pred['nutrient_stress'],
        'temperature_stress':     pred['temperature_stress'],
        'water_stress_cat':       pred['water_stress_cat'],
        'nutrient_stress_cat':    pred['nutrient_stress_cat'],
        'temperature_stress_cat': pred['temperature_stress_cat'],
        'model_used':             pred['model_used'],
        # Summary + actions
        'health_summary':         health_summary,
        'recommended_actions':    merged_actions,
        # Persistence
        'firestore_id':           firestore_id,
    })

    # except Exception:
    #     logger.exception('Gemini /health failed')
    #     return jsonify({'success': False,
    #                     'error': 'AI health check failed. Please try again.'}), 500

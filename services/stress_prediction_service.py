"""
Stress Prediction Service
=========================
Singleton that wraps the trained XGBoost model.

Pipeline:
  visual_metrics + plant_profile + optional env hints
    → feature vector (16 values)
    → StandardScaler
    → XGBRegressor
    → (water_stress, nutrient_stress, temperature_stress) ∈ [0, 1]
    → recommended actions

Feature vector order matches trained_models/metadata.joblib:
  plant_type_enc, phenological_stage, estimated_biomass, leaf_area_m2,
  plant_age_days, health_confidence, cumulative_damage_pct,
  soil_water_pct, last_watering_days, air_temp_C, relative_humidity_pct,
  light_PAR_umol_m2_s, photosynthesis_g_h, respiration_g_h,
  growth_rate_g_h, indoor_flag
"""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ── plant-type encoding (matches LabelEncoder alphabetical sort used in training) ──
_PLANT_TYPE_ENC = {"basil": 0, "lettuce": 1, "tomato": 2}

# ── phenological stage ordinal map ───────────────────────────────────────────
_STAGE_ORD = {
    "seed": 1, "seedling": 2, "vegetative": 3,
    "flowering": 4, "fruiting": 5, "mature": 6, "senescent": 7,
}

# ── per-plant environmental defaults (when user doesn't provide them) ─────────
# Derived from default_plants.py profiles
_PLANT_DEFAULTS = {
    "tomato": {
        "soil_water_opt": 35.0,   # mid of optimal_range (30-40)
        "air_temp_opt":   25.0,   # T_opt
        "rh_opt":         60.0,   # mid of optimal_RH (50-70)
        "par_opt":       600.0,   # optimal_PAR
        "wilting_point":  15.0,
    },
    "lettuce": {
        "soil_water_opt": 37.5,   # mid (30-45)
        "air_temp_opt":   20.0,
        "rh_opt":         70.0,
        "par_opt":       600.0,
        "wilting_point":  10.0,
    },
    "basil": {
        "soil_water_opt": 38.5,   # mid (32-45)
        "air_temp_opt":   24.0,
        "rh_opt":         55.0,
        "par_opt":       450.0,
        "wilting_point":  18.0,
    },
}

# Stress category bins matching training
_BINS   = [0.0, 0.33, 0.67, 1.0]
_LABELS = ["low", "medium", "high"]


def _stress_category(v: float) -> str:
    if v < 0.33:
        return "low"
    if v < 0.67:
        return "medium"
    return "high"


class StressPredictionService:
    """Singleton. Call .get() to retrieve the shared instance."""

    _instance: Optional["StressPredictionService"] = None

    def __init__(self) -> None:
        self._model   = None
        self._scaler  = None
        self._features: List[str] = []
        self._ready   = False
        self._load()

    @classmethod
    def get(cls) -> "StressPredictionService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── model loading ─────────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load XGBoost model + scaler from trained_models/."""
        try:
            import joblib

            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            model_dir = os.path.join(root, "trained_models")

            self._scaler  = joblib.load(os.path.join(model_dir, "_scaler.joblib"))
            self._model   = joblib.load(os.path.join(model_dir, "xgboost.joblib"))
            meta          = joblib.load(os.path.join(model_dir, "metadata.joblib"))
            self._features = meta["features"]
            self._ready    = True
            logger.info(
                "StressPredictionService: XGBoost model loaded (%d features)",
                len(self._features),
            )
        except Exception as exc:
            logger.warning(
                "StressPredictionService: could not load model (%s) — rule-based fallback only",
                exc,
            )

    # ── feature vector ────────────────────────────────────────────────────────

    def build_features(
        self,
        plant_type: str,           # "tomato" | "lettuce" | "basil"
        plant_age_days: int,
        phenological_stage: str,   # "seed" | "seedling" | … | "mature"
        estimated_biomass: float,  # grams
        leaf_area_m2: float,
        leaf_yellowing_score: float,  # 0-1 visual
        leaf_droop_score: float,      # 0-1 visual
        necrosis_score: float,        # 0-1 visual
        # optional env hints — caller may pass None to use plant defaults
        last_watering_days: Optional[float] = None,
        air_temp_c: Optional[float] = None,
        relative_humidity: Optional[float] = None,
        soil_water_pct: Optional[float] = None,
    ) -> np.ndarray:
        """
        Build the 16-element feature vector expected by the XGBoost model.

        Visual scores are used as proxies where direct sensor readings
        are unavailable:
          • health_confidence    = 1 − mean(yellowing, droop, necrosis)
          • cumulative_damage    = mean(yellowing, droop, necrosis)
          • soil_water_pct       ≈ optimal − droop × (optimal − wilting)
            (high droop → plant was losing turgor → lower soil water)
        """
        ptype   = plant_type.lower().split("_")[0]   # "tomato_standard" → "tomato"
        defs    = _PLANT_DEFAULTS.get(ptype, _PLANT_DEFAULTS["tomato"])
        enc     = float(_PLANT_TYPE_ENC.get(ptype, 2))
        stage   = float(_STAGE_ORD.get(phenological_stage.lower(), 3))

        # Derived health indicators from visual scores
        damage           = float(np.mean([leaf_yellowing_score, leaf_droop_score, necrosis_score]))
        health_conf      = float(np.clip(1.0 - damage, 0.0, 1.0))
        cum_damage       = float(np.clip(damage, 0.0, 1.0))

        # Soil water: infer from droop unless user provided it
        if soil_water_pct is not None:
            sw = float(soil_water_pct)
        else:
            # High droop → water deficit → lower soil water
            sw = defs["soil_water_opt"] - leaf_droop_score * (
                defs["soil_water_opt"] - defs["wilting_point"]
            )
            sw = float(np.clip(sw, defs["wilting_point"] + 0.5, 55.0))

        vec = {
            "plant_type_enc":         enc,
            "phenological_stage":     stage,
            "estimated_biomass":      float(np.clip(estimated_biomass, 0.0, 600.0)),
            "leaf_area_m2":           float(np.clip(leaf_area_m2, 0.0, 1.5)),
            "plant_age_days":         float(plant_age_days),
            "health_confidence":      health_conf,
            "cumulative_damage_pct":  cum_damage,
            "soil_water_pct":         sw,
            "last_watering_days":     float(last_watering_days if last_watering_days is not None else 1.0),
            "air_temp_C":             float(air_temp_c if air_temp_c is not None else defs["air_temp_opt"]),
            "relative_humidity_pct":  float(relative_humidity if relative_humidity is not None else defs["rh_opt"]),
            "light_PAR_umol_m2_s":    float(defs["par_opt"]),   # always default — not visible in photo
            "photosynthesis_g_h":     0.0,   # not observable from image
            "respiration_g_h":        0.0,
            "growth_rate_g_h":        0.0,
            "indoor_flag":            1.0,
        }

        return np.array([vec[f] for f in self._features], dtype=float)

    # ── prediction ────────────────────────────────────────────────────────────

    def predict(
        self,
        plant_type: str,
        plant_age_days: int,
        phenological_stage: str,
        estimated_biomass: float,
        leaf_area_m2: float,
        leaf_yellowing_score: float,
        leaf_droop_score: float,
        necrosis_score: float,
        last_watering_days: Optional[float] = None,
        air_temp_c: Optional[float] = None,
        relative_humidity: Optional[float] = None,
        soil_water_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Run the full prediction pipeline.

        Falls back to visual-score rule-based estimates if the model isn't loaded.

        Returns dict with keys:
            water_stress, nutrient_stress, temperature_stress  (floats 0-1)
            water_stress_cat, nutrient_stress_cat, temperature_stress_cat (str)
            model_used  ("xgboost" | "rule_based")
        """
        # Rule-based estimates from visual scores (always computed as fallback / supplement)
        rb_water    = float(np.clip(leaf_droop_score * 0.8 + leaf_yellowing_score * 0.2, 0, 1))
        rb_nutrient = float(np.clip(leaf_yellowing_score * 0.75 + necrosis_score * 0.25, 0, 1))
        rb_temp     = float(np.clip(necrosis_score * 0.6 + leaf_yellowing_score * 0.2 + leaf_droop_score * 0.2, 0, 1))

        if not self._ready:
            logger.warning("Model not ready — using rule-based fallback")
            water, nutrient, temp = rb_water, rb_nutrient, rb_temp
            model_used = "rule_based"
        else:
            try:
                fv = self.build_features(
                    plant_type, plant_age_days, phenological_stage,
                    estimated_biomass, leaf_area_m2,
                    leaf_yellowing_score, leaf_droop_score, necrosis_score,
                    last_watering_days, air_temp_c, relative_humidity, soil_water_pct,
                )
                fv_scaled = self._scaler.transform(fv.reshape(1, -1))
                pred = self._model.predict(fv_scaled)[0]   # shape (3,) from MultiOutputRegressor

                water    = float(np.clip(pred[0], 0, 1))
                nutrient = float(np.clip(pred[1], 0, 1))
                temp     = float(np.clip(pred[2], 0, 1))
                model_used = "xgboost"
            except Exception as exc:
                logger.warning("XGBoost predict failed (%s) — rule-based fallback", exc)
                water, nutrient, temp = rb_water, rb_nutrient, rb_temp
                model_used = "rule_based"

        return {
            "water_stress":            round(water,    3),
            "nutrient_stress":         round(nutrient, 3),
            "temperature_stress":      round(temp,     3),
            "water_stress_cat":        _stress_category(water),
            "nutrient_stress_cat":     _stress_category(nutrient),
            "temperature_stress_cat":  _stress_category(temp),
            "model_used":              model_used,
        }

    # ── recommendations ───────────────────────────────────────────────────────

    @staticmethod
    def recommend_actions(
        water_stress: float,
        nutrient_stress: float,
        temperature_stress: float,
        plant_type: str,
        leaf_yellowing_score: float = 0.0,
        necrosis_score: float = 0.0,
        last_watering_days: Optional[float] = None,
    ) -> List[str]:
        """
        Return a prioritised list of actionable recommendations.
        Combines ML stress predictions with visual-score signals.
        """
        actions: List[str] = []
        ptype = plant_type.lower().split("_")[0]

        # ── water ─────────────────────────────────────────────────────────────
        if water_stress >= 0.67:
            wd = f" (last watered {last_watering_days:.0f}d ago)" if last_watering_days and last_watering_days > 1 else ""
            actions.append(f"Water immediately{wd} — severe water stress detected")
        elif water_stress >= 0.33:
            actions.append("Increase watering frequency — mild water stress")
        elif water_stress < 0.1 and last_watering_days and last_watering_days < 0.5:
            actions.append("Avoid overwatering — soil moisture appears adequate")

        # ── nutrients ─────────────────────────────────────────────────────────
        if nutrient_stress >= 0.67:
            if leaf_yellowing_score >= 0.5:
                actions.append("Apply balanced NPK fertiliser — yellowing indicates nitrogen deficiency")
            else:
                actions.append("Add nutrients — significant nutrient stress detected")
        elif nutrient_stress >= 0.33:
            actions.append("Consider light fertilisation — mild nutrient deficiency")

        # ── temperature ───────────────────────────────────────────────────────
        temp_tips = {
            "tomato":  ("Move to warmer location (18-27°C)", "Improve ventilation or shade — heat stress"),
            "lettuce": ("Warm to 15-20°C — lettuce is cold-sensitive below 10°C", "Cool to below 25°C — lettuce bolts in heat"),
            "basil":   ("Move to warmer spot (20-28°C) — basil is tropical", "Reduce direct sunlight or improve airflow"),
        }
        cold_tip, hot_tip = temp_tips.get(ptype, ("Adjust temperature", "Improve ventilation"))
        if temperature_stress >= 0.67:
            actions.append(hot_tip)
        elif temperature_stress >= 0.33:
            actions.append(cold_tip if necrosis_score < 0.3 else hot_tip)

        # ── general observations ──────────────────────────────────────────────
        if necrosis_score >= 0.5:
            actions.append("Inspect for fungal disease or root rot — necrotic spots detected")
        if all(s < 0.2 for s in [water_stress, nutrient_stress, temperature_stress]):
            actions.append("Plant looks healthy — maintain current care routine")

        return actions[:5]   # cap at 5 to avoid overwhelming the user

    # ── firestore persistence ─────────────────────────────────────────────────

    @staticmethod
    def save_to_firestore(
        uid: str,
        plant_id: str,
        record: Dict[str, Any],
    ) -> Optional[str]:
        """
        Write one health-check record to:
          users/{uid}/plants/{plant_id}/health_checks/{auto_id}

        Returns the generated doc ID, or None on failure.
        """
        try:
            from services.user_service import UserService
            svc = UserService.get()
            if not svc._connected or svc._db is None:
                logger.warning("Firestore not connected — health check not persisted")
                return None

            from google.cloud.firestore import SERVER_TIMESTAMP
            record["saved_at"] = SERVER_TIMESTAMP

            ref = (
                svc._db
                .collection("users")
                .document(uid)
                .collection("plants")
                .document(plant_id)
                .collection("health_checks")
                .document()   # auto-generated ID
            )
            ref.set(record)
            logger.info(
                "Health check saved: users/%s/plants/%s/health_checks/%s",
                uid, plant_id, ref.id,
            )
            return ref.id
        except Exception as exc:
            logger.warning("Firestore save failed: %s", exc)
            return None

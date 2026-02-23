#!/usr/bin/env python3
"""
Stress Prediction Model Trainer
================================
Trains models to predict water_stress, nutrient_stress, and temperature_stress
from plant simulation data.

Models compared
---------------
  DecisionTree        - interpretable baseline
  RandomForest        - ensemble of trees (robust, handles non-linearity)
  XGBoost             - gradient-boosted trees (typically best accuracy)
  GradientBoosting    - sklearn GBM for additional comparison
  UMAP + kNN          - manifold-based: dimensionality reduction → neighbour classifier

Data sources
------------
  --source bq         fetch from BigQuery (requires credentials)
  --source local      generate data in-process via SimulationEngine (no BQ needed)
  --source csv PATH   load from a saved CSV file

Usage
-----
  # Best option: BQ already populated (run generate_training_data.py first)
  python tools/train_stress_model.py --source bq

  # Development / first run — generates ~33 k rows locally and trains
  python tools/train_stress_model.py --source local

  # Load previously saved CSV
  python tools/train_stress_model.py --source csv data/training_export.csv

  # Save trained models to disk (joblib)
  python tools/train_stress_model.py --source local --save-models models/
"""

import argparse
import logging
import os
import sys
import time
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import joblib
import matplotlib
matplotlib.use("Agg")   # headless-safe; swap to "TkAgg" or "Qt5Agg" for interactive
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.ensemble import (
    GradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    mean_absolute_error,
    r2_score,
)
from sklearn.model_selection import train_test_split
from sklearn.multioutput import MultiOutputRegressor
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.tree import DecisionTreeRegressor
from xgboost import XGBRegressor

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# ── project root ──────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("train_stress")

# ── constants ─────────────────────────────────────────────────────────────────

TARGETS = ["water_stress", "nutrient_stress", "temperature_stress"]

# Feature columns (matches training table schema from train_model.py / docs)
FEATURE_COLS = [
    # Plant identity / phenotype
    "plant_type_enc",          # label-encoded plant_type
    "phenological_stage",      # ordinal 1-7
    "estimated_biomass",       # biomass_g
    "leaf_area_m2",
    "plant_age_days",          # day from simulation
    # Health
    "health_confidence",       # 1 - cumulative_damage
    "cumulative_damage_pct",
    # Water management
    "soil_water_pct",
    "last_watering_days",
    # Environment
    "air_temp_C",
    "relative_humidity_pct",
    "light_PAR_umol_m2_s",
    # Carbon / growth fluxes
    "photosynthesis_g_h",
    "respiration_g_h",
    "growth_rate_g_h",
    # Metadata
    "indoor_flag",
]

# Categorical stress bins for confusion matrix
STRESS_BINS   = [0.0, 0.33, 0.67, 1.01]
STRESS_LABELS = ["low", "medium", "high"]


# ═══════════════════════════════════════════════════════════════════════════════
# 1. DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════════

def load_from_bigquery(limit: Optional[int] = 200_000) -> pd.DataFrame:
    """Fetch data via BigQueryTrainingDataBuilder (existing train_model.py class)."""
    from tools.train_model import BigQueryTrainingDataBuilder
    builder = BigQueryTrainingDataBuilder()
    if not builder.connected:
        raise RuntimeError("BigQuery not connected — check FIREBASE_PROJECT_ID and credentials.")
    logger.info("Fetching training data from BigQuery (limit=%s)…", limit)
    df = builder.build_training_data_from_hourly(limit=limit)
    if df.empty:
        raise RuntimeError(
            "BigQuery returned 0 rows. "
            "Run `python tools/generate_training_data.py` first to populate the tables."
        )
    logger.info("  Fetched %d rows from BigQuery", len(df))
    return df


def generate_local_data() -> pd.DataFrame:
    """
    Run a representative subset of SimulationEngine scenarios in-process and
    collect every hourly snapshot into a DataFrame.

    Conditions: optimal, water_low, temp_cold, temp_hot, nutrient_low
    Plants:     all 3
    Regimes:    on / off
    → 5 × 3 × 2 = 30 sims, ~33 k rows — enough to train a demo model.
    """
    from data.default_plants import DEFAULT_PROFILES, load_default_profile
    from models.engine import SimulationEngine
    from tools.generate_training_data import (
        BASE_CONDITIONS,
        DURATION_DAYS,
        apply_condition,
    )

    SELECTED_CONDS = {
        "optimal", "water_low", "water_high",
        "temp_cold", "temp_hot", "nutrient_low",
        "nutrient_high", "combo_cold_dry", "combo_hot_poor",
    }
    conditions = [c for c in BASE_CONDITIONS if c.name in SELECTED_CONDS]

    records = []
    total = len(DEFAULT_PROFILES) * len(conditions) * 2
    idx   = 0

    for profile_id in DEFAULT_PROFILES:
        profile = load_default_profile(profile_id)
        duration_days = DURATION_DAYS.get(profile_id, 45)

        for regime in (True, False):
            for cond in conditions:
                idx += 1
                logger.info(
                    "[%d/%d] Generating: %-20s cond=%-18s regime=%s",
                    idx, total, profile_id, cond.name, "on" if regime else "off",
                )
                engine = SimulationEngine(profile)
                apply_condition(engine, cond)
                engine.set_daily_regime(enabled=regime)

                for _ in range(duration_days * 24):
                    engine.step(hours=1)
                    s = engine.state
                    records.append({
                        "plant_type":              profile_id,
                        "phenological_stage":      (
                            s.phenological_stage.value
                            if hasattr(s.phenological_stage, "value")
                            else str(s.phenological_stage)
                        ),
                        "estimated_biomass":        s.biomass,
                        "leaf_area_m2":             s.leaf_area,
                        "plant_age_days":           s.hour // 24,
                        "health_confidence":        max(0.0, 1.0 - s.cumulative_damage),
                        "cumulative_damage_pct":    s.cumulative_damage,
                        "soil_water_pct":           s.soil_water,
                        "last_watering_days":       s.last_watering_hour / 24.0,
                        "air_temp_C":               s.air_temp,
                        "relative_humidity_pct":    s.relative_humidity,
                        "light_PAR_umol_m2_s":      s.light_PAR,
                        "photosynthesis_g_h":        s.photosynthesis,
                        "respiration_g_h":           s.respiration,
                        "growth_rate_g_h":           s.growth_rate,
                        "indoor_flag":               1,
                        "water_stress":              s.water_stress,
                        "nutrient_stress":           s.nutrient_stress,
                        "temperature_stress":        s.temp_stress,
                        "condition":                 cond.name,
                        "daily_regime":              regime,
                    })
                    if not s.is_alive:
                        break

    df = pd.DataFrame(records)
    logger.info("Generated %d hourly rows from local simulations", len(df))
    return df


def load_from_csv(path: str) -> pd.DataFrame:
    logger.info("Loading data from CSV: %s", path)
    df = pd.read_csv(path)
    logger.info("  Loaded %d rows", len(df))
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# 2. PREPROCESSING
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_phenological_stage(series: pd.Series) -> pd.Series:
    """Convert string stage names to ordinal ints if not already numeric."""
    _stage_map = {
        "seed": 1, "seedling": 2, "vegetative": 3,
        "flowering": 4, "fruiting": 5, "mature": 6, "senescent": 7,
    }
    if pd.api.types.is_numeric_dtype(series):
        return series.fillna(3)
    return series.str.lower().map(_stage_map).fillna(3).astype(int)


def preprocess(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, LabelEncoder]:
    """
    Returns (X, y, label_encoder_for_plant_type).

    Steps:
      1. Label-encode plant_type
      2. Ordinal-encode phenological_stage (string → 1-7)
      3. Cast indoor_flag to int
      4. Impute missing values with median
      5. Keep only rows where all 3 stress targets are present
    """
    df = df.copy()

    # ── plant type encoding ───────────────────────────────────────────────────
    le = LabelEncoder()
    plant_col = "plant_type" if "plant_type" in df.columns else "plant_species"
    # strip profile suffix for cleaner labels (tomato_standard → tomato)
    df["plant_type_clean"] = df[plant_col].str.split("_").str[0]
    df["plant_type_enc"]   = le.fit_transform(df["plant_type_clean"])

    # ── phenological stage ────────────────────────────────────────────────────
    df["phenological_stage"] = _resolve_phenological_stage(df["phenological_stage"])

    # ── indoor flag ───────────────────────────────────────────────────────────
    if "indoor_flag" in df.columns:
        df["indoor_flag"] = df["indoor_flag"].fillna(1).astype(int)
    else:
        df["indoor_flag"] = 1

    # ── rename BQ column names → training names ───────────────────────────────
    renames = {
        "biomass_g":   "estimated_biomass",
        "temp_stress": "temperature_stress",
        "day":         "plant_age_days",
    }
    df.rename(columns={k: v for k, v in renames.items() if k in df.columns},
              inplace=True)

    # ── derived: health_confidence ────────────────────────────────────────────
    if "health_confidence" not in df.columns and "cumulative_damage_pct" in df.columns:
        df["health_confidence"] = (1.0 - df["cumulative_damage_pct"]).clip(0, 1)

    # ── last_watering_days ────────────────────────────────────────────────────
    if "last_watering_days" not in df.columns and "last_watering_hour" in df.columns:
        df["last_watering_days"] = df["last_watering_hour"] / 24.0

    # ── drop rows without targets ─────────────────────────────────────────────
    df = df.dropna(subset=TARGETS)

    # ── build X ───────────────────────────────────────────────────────────────
    available_features = [c for c in FEATURE_COLS if c in df.columns]
    missing_features   = [c for c in FEATURE_COLS if c not in df.columns]
    if missing_features:
        logger.warning("Missing feature columns (will skip): %s", missing_features)

    X = df[available_features].copy()

    # Impute missing values with column median
    for col in X.columns:
        if X[col].isna().any():
            X[col] = X[col].fillna(X[col].median())

    y = df[TARGETS].copy()
    # Clip stresses to [0, 1]
    y = y.clip(0, 1)

    logger.info(
        "Preprocessing complete: %d rows × %d features → targets %s",
        len(X), len(X.columns), TARGETS,
    )
    logger.info("  Features used: %s", list(X.columns))
    logger.info("  Target stats:\n%s", y.describe().round(3).to_string())

    return X, y, le


# ═══════════════════════════════════════════════════════════════════════════════
# 3. MODEL TRAINING & EVALUATION
# ═══════════════════════════════════════════════════════════════════════════════

def _stress_category(arr: np.ndarray) -> np.ndarray:
    """Bin continuous stress [0,1] into low / medium / high."""
    return pd.cut(arr, bins=STRESS_BINS, labels=STRESS_LABELS, right=False).astype(str)


def evaluate_model(
    name: str,
    y_true: pd.DataFrame,
    y_pred: np.ndarray,
) -> Dict:
    """Compute R², MAE, RMSE and per-class confusion matrices."""
    results = {"model": name, "targets": {}}

    for i, target in enumerate(y_true.columns):
        yt = y_true[target].values
        yp = y_pred[:, i]

        r2   = r2_score(yt, yp)
        mae  = mean_absolute_error(yt, yp)
        rmse = float(np.sqrt(np.mean((yt - yp) ** 2)))

        # Categorical confusion matrix
        yt_cat = _stress_category(yt)
        yp_cat = _stress_category(np.clip(yp, 0, 1))
        cm = confusion_matrix(yt_cat, yp_cat, labels=STRESS_LABELS)
        cr = classification_report(
            yt_cat, yp_cat, labels=STRESS_LABELS,
            output_dict=True, zero_division=0,
        )

        results["targets"][target] = {
            "r2": r2, "mae": mae, "rmse": rmse,
            "confusion_matrix": cm,
            "classification_report": cr,
        }

    # Overall R² (mean across targets)
    results["mean_r2"] = float(np.mean([
        results["targets"][t]["r2"] for t in y_true.columns
    ]))
    return results


def train_all_models(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
    X_test:  pd.DataFrame,
    y_test:  pd.DataFrame,
) -> Tuple[Dict, Dict]:
    """
    Train Decision Tree, Random Forest, XGBoost, Gradient Boosting.
    Returns (results_dict, fitted_models_dict).
    """
    model_defs = {
        "DecisionTree": MultiOutputRegressor(
            DecisionTreeRegressor(max_depth=8, min_samples_leaf=10, random_state=42)
        ),
        "RandomForest": RandomForestRegressor(
            n_estimators=120, max_depth=10, min_samples_leaf=5,
            n_jobs=-1, random_state=42,
        ),
        "XGBoost": MultiOutputRegressor(
            XGBRegressor(
                n_estimators=200, max_depth=6, learning_rate=0.08,
                subsample=0.8, colsample_bytree=0.8,
                objective="reg:squarederror",
                verbosity=0, random_state=42,
            )
        ),
        "GradientBoosting": MultiOutputRegressor(
            GradientBoostingRegressor(
                n_estimators=120, max_depth=5, learning_rate=0.08,
                subsample=0.8, random_state=42,
            )
        ),
    }

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_train)
    X_te_s = scaler.transform(X_test)

    all_results = {}
    all_models  = {"_scaler": scaler}

    for name, model in model_defs.items():
        logger.info("Training %s…", name)
        t0 = time.monotonic()
        model.fit(X_tr_s, y_train)
        elapsed = time.monotonic() - t0

        y_pred = model.predict(X_te_s)
        res    = evaluate_model(name, y_test, y_pred)
        res["train_time_s"] = round(elapsed, 2)

        logger.info(
            "  %s — mean R²=%.3f  (time=%.1fs)",
            name, res["mean_r2"], elapsed,
        )
        for t in TARGETS:
            r = res["targets"][t]
            logger.info(
                "      %-22s  R²=%+.3f  MAE=%.3f  RMSE=%.3f",
                t, r["r2"], r["mae"], r["rmse"],
            )

        all_results[name] = res
        all_models[name]  = model

    return all_results, all_models


def train_umap_knn(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
    X_test:  pd.DataFrame,
    y_test:  pd.DataFrame,
) -> Tuple[Dict, object, object, np.ndarray]:
    """
    Supervised UMAP (2-D) followed by kNN classifier for each stress target.
    Returns (results, umap_model, knn_models, embedding_test).
    """
    import umap as umap_lib

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_train)
    X_te_s = scaler.transform(X_test)

    # Use average stress as supervision label for the shared UMAP space
    avg_stress_train = y_train[TARGETS].mean(axis=1).values

    logger.info("Training UMAP + kNN…")
    t0 = time.monotonic()
    reducer = umap_lib.UMAP(
        n_components=2,
        n_neighbors=20,
        min_dist=0.1,
        target_weight=0.5,   # supervised signal strength
        random_state=42,
        n_jobs=1,
    )
    reducer.fit(X_tr_s, avg_stress_train)
    emb_train = reducer.transform(X_tr_s)
    emb_test  = reducer.transform(X_te_s)
    umap_time = time.monotonic() - t0
    logger.info("  UMAP fitted (%.1fs)", umap_time)

    # kNN regressor in UMAP space per target
    from sklearn.neighbors import KNeighborsRegressor
    knn_models  = {}
    y_pred_all  = np.zeros((len(X_test), len(TARGETS)))

    for i, target in enumerate(TARGETS):
        yt = y_train[target].values
        knn = KNeighborsRegressor(n_neighbors=7, weights="distance", n_jobs=-1)
        knn.fit(emb_train, yt)
        y_pred_all[:, i] = knn.predict(emb_test)
        knn_models[target] = knn

    res = evaluate_model("UMAP+kNN", y_test, y_pred_all)
    res["train_time_s"] = round(umap_time, 2)
    logger.info(
        "  UMAP+kNN — mean R²=%.3f",
        res["mean_r2"],
    )

    return res, reducer, knn_models, emb_test, scaler


# ═══════════════════════════════════════════════════════════════════════════════
# 4. VISUALISATION
# ═══════════════════════════════════════════════════════════════════════════════

def _savefig(fig: plt.Figure, path: str) -> None:
    fig.savefig(path, dpi=120, bbox_inches="tight")
    logger.info("  Saved: %s", path)
    plt.close(fig)


def plot_summary_table(all_results: Dict, out_dir: str) -> None:
    """Print and save a per-model × per-target metrics table."""
    rows = []
    for model_name, res in all_results.items():
        for target in TARGETS:
            r = res["targets"][target]
            rows.append({
                "Model": model_name,
                "Target": target,
                "R²":    round(r["r2"],   3),
                "MAE":   round(r["mae"],  4),
                "RMSE":  round(r["rmse"], 4),
                "Train s": res.get("train_time_s", "-"),
            })
    df = pd.DataFrame(rows)
    print("\n" + "=" * 80)
    print("REGRESSION METRICS (test set)")
    print("=" * 80)
    print(df.to_string(index=False))
    print("=" * 80)

    # Bar chart of R² per model × target
    fig, ax = plt.subplots(figsize=(10, 4))
    pivot = df.pivot(index="Target", columns="Model", values="R²")
    pivot.plot(kind="bar", ax=ax, colormap="tab10", edgecolor="white")
    ax.axhline(0, color="black", linewidth=0.7)
    ax.set_title("R² score per model and stress target (test set)")
    ax.set_ylabel("R²")
    ax.set_ylim(-0.15, 1.05)
    ax.legend(bbox_to_anchor=(1.01, 1), loc="upper left")
    ax.tick_params(axis="x", rotation=0)
    ax.set_facecolor("#1a1a2e")
    fig.patch.set_facecolor("#0f0f1a")
    ax.title.set_color("white")
    ax.yaxis.label.set_color("white")
    ax.xaxis.label.set_color("white")
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_edgecolor("#444")
    _savefig(fig, os.path.join(out_dir, "r2_comparison.png"))


def plot_confusion_matrices(all_results: Dict, out_dir: str) -> None:
    """3×3 confusion matrix (low/medium/high) for every (model, target)."""
    n_models  = len(all_results)
    n_targets = len(TARGETS)

    fig, axes = plt.subplots(
        n_targets, n_models,
        figsize=(4 * n_models, 4 * n_targets),
        squeeze=False,
    )
    fig.patch.set_facecolor("#0f0f1a")

    for col, (model_name, res) in enumerate(all_results.items()):
        for row, target in enumerate(TARGETS):
            ax  = axes[row][col]
            cm  = res["targets"][target]["confusion_matrix"]
            # Normalise row-wise (true class)
            cm_norm  = cm.astype(float)
            row_sums = cm_norm.sum(axis=1, keepdims=True)
            with np.errstate(invalid="ignore", divide="ignore"):
                cm_norm = np.where(row_sums > 0, cm_norm / row_sums, 0.0)

            sns.heatmap(
                cm_norm,
                annot=cm,          # show raw counts
                fmt="d",
                xticklabels=STRESS_LABELS,
                yticklabels=STRESS_LABELS,
                ax=ax,
                cmap="YlGn",
                vmin=0, vmax=1,
                cbar=False,
                linewidths=0.3,
                linecolor="#333",
            )
            ax.set_xlabel("Predicted", color="white", fontsize=9)
            ax.set_ylabel("Actual",    color="white", fontsize=9)
            ax.set_title(
                f"{model_name}\n{target.replace('_', ' ')}",
                color="white", fontsize=10,
            )
            ax.set_facecolor("#151821")
            ax.tick_params(colors="white", labelsize=8)

    fig.suptitle("Confusion matrices (low / medium / high stress)", color="white", fontsize=13, y=1.01)
    plt.tight_layout()
    _savefig(fig, os.path.join(out_dir, "confusion_matrices.png"))


def plot_feature_importance(all_results: Dict, fitted_models: Dict, feature_names: List[str], out_dir: str) -> None:
    """Feature importance for tree-based models."""
    tree_models = ["DecisionTree", "RandomForest", "GradientBoosting"]
    available   = [m for m in tree_models if m in fitted_models]

    if not available:
        return

    fig, axes = plt.subplots(1, len(available), figsize=(6 * len(available), 5), squeeze=False)
    fig.patch.set_facecolor("#0f0f1a")

    for col, model_name in enumerate(available):
        ax    = axes[0][col]
        model = fitted_models[model_name]

        # MultiOutputRegressor: average importances across sub-estimators
        try:
            imps = np.mean(
                [est.feature_importances_ for est in model.estimators_],
                axis=0,
            )
        except AttributeError:
            # SingleOutput
            imps = model.feature_importances_

        idx    = np.argsort(imps)[::-1]
        sorted_names = [feature_names[i] for i in idx]
        sorted_imps  = imps[idx]

        colors = ["#3FA34D" if i % 2 == 0 else "#6FCF97" for i in range(len(sorted_names))]
        ax.barh(sorted_names[::-1], sorted_imps[::-1], color=colors[::-1], edgecolor="#222")
        ax.set_title(f"{model_name}\nFeature Importance (avg across targets)", color="white")
        ax.set_xlabel("Importance", color="white")
        ax.set_facecolor("#151821")
        ax.tick_params(colors="white", labelsize=8)
        for spine in ax.spines.values():
            spine.set_edgecolor("#333")

    fig.suptitle("Feature Importances", color="white", fontsize=13)
    plt.tight_layout()
    _savefig(fig, os.path.join(out_dir, "feature_importance.png"))


def plot_actual_vs_predicted(
    all_results: Dict,
    fitted_models: Dict,
    X_test: pd.DataFrame,
    y_test: pd.DataFrame,
    scaler,
    out_dir: str,
) -> None:
    """Scatter: actual vs predicted for each model, one subplot per target."""
    # Filter out UMAP components and scaler; only include actual regressor models
    model_names = [k for k in fitted_models if k != "_scaler" and not k.startswith("UMAP+kNN_")]
    n_models  = len(model_names)
    n_targets = len(TARGETS)
    X_te_s    = scaler.transform(X_test)

    fig, axes = plt.subplots(
        n_targets, n_models,
        figsize=(4 * n_models, 4 * n_targets),
        squeeze=False,
    )
    fig.patch.set_facecolor("#0f0f1a")

    for col, model_name in enumerate(model_names):
        model = fitted_models[model_name]
        y_pred = model.predict(X_te_s)
        if y_pred.ndim == 1:
            y_pred = y_pred.reshape(-1, 1)

        for row, target in enumerate(TARGETS):
            ax = axes[row][col]
            yt = y_test[target].values
            yp = np.clip(y_pred[:, row], 0, 1)

            ax.scatter(yt, yp, alpha=0.15, s=4, color="#6FCF97", edgecolors="none")
            lims = [0, 1]
            ax.plot(lims, lims, "r--", linewidth=0.8, label="perfect")
            ax.set_xlim(lims); ax.set_ylim(lims)
            r2 = all_results[model_name]["targets"][target]["r2"]
            ax.set_title(f"{model_name} / {target}\nR²={r2:.3f}", color="white", fontsize=9)
            ax.set_xlabel("Actual",    color="white", fontsize=8)
            ax.set_ylabel("Predicted", color="white", fontsize=8)
            ax.set_facecolor("#151821")
            ax.tick_params(colors="white", labelsize=7)
            for sp in ax.spines.values():
                sp.set_edgecolor("#333")

    fig.suptitle("Actual vs Predicted (test set)", color="white", fontsize=13, y=1.01)
    plt.tight_layout()
    _savefig(fig, os.path.join(out_dir, "actual_vs_predicted.png"))


def plot_umap_embedding(
    emb_test: np.ndarray,
    y_test: pd.DataFrame,
    out_dir: str,
) -> None:
    """2-D UMAP scatter coloured by each stress target."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    fig.patch.set_facecolor("#0f0f1a")

    for ax, target in zip(axes, TARGETS):
        sc = ax.scatter(
            emb_test[:, 0], emb_test[:, 1],
            c=y_test[target].values,
            cmap="RdYlGn_r",
            s=4, alpha=0.4, edgecolors="none",
            vmin=0, vmax=1,
        )
        plt.colorbar(sc, ax=ax, label=target.replace("_", " "))
        ax.set_title(target.replace("_", " "), color="white")
        ax.set_facecolor("#151821")
        ax.tick_params(colors="white", labelsize=7)
        ax.set_xlabel("UMAP-1", color="white", fontsize=8)
        ax.set_ylabel("UMAP-2", color="white", fontsize=8)
        for sp in ax.spines.values():
            sp.set_edgecolor("#333")

    fig.suptitle("UMAP 2-D Embedding coloured by stress (test samples)", color="white", fontsize=12)
    plt.tight_layout()
    _savefig(fig, os.path.join(out_dir, "umap_embedding.png"))


def plot_stress_distribution(y: pd.DataFrame, out_dir: str) -> None:
    """Histogram of stress value distributions."""
    fig, axes = plt.subplots(1, 3, figsize=(12, 3))
    fig.patch.set_facecolor("#0f0f1a")

    for ax, target in zip(axes, TARGETS):
        counts, bins, _ = ax.hist(y[target], bins=40, color="#3FA34D", edgecolor="#111", alpha=0.85)
        ax.set_title(target.replace("_", " "), color="white")
        ax.set_xlabel("Stress level", color="white")
        ax.set_ylabel("Count",        color="white")
        ax.set_facecolor("#151821")
        ax.tick_params(colors="white")
        for sp in ax.spines.values():
            sp.set_edgecolor("#333")
        # Add class boundary lines
        for b in [0.33, 0.67]:
            ax.axvline(b, color="#F59E0B", linewidth=1, linestyle="--", alpha=0.7)

    fig.suptitle("Stress distribution in training data  (dashed = class boundaries)", color="white", fontsize=11)
    plt.tight_layout()
    _savefig(fig, os.path.join(out_dir, "stress_distribution.png"))


# ═══════════════════════════════════════════════════════════════════════════════
# 5. MODEL PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════════════

def save_models(fitted_models: Dict, feature_names: List[str], out_dir: str) -> None:
    """Save all fitted models + scaler + metadata with joblib."""
    os.makedirs(out_dir, exist_ok=True)
    for name, obj in fitted_models.items():
        path = os.path.join(out_dir, f"{name.replace('+', '_').lower()}.joblib")
        joblib.dump(obj, path)
        logger.info("Saved %s → %s", name, path)

    meta = {"features": feature_names, "targets": TARGETS, "stress_bins": STRESS_BINS}
    joblib.dump(meta, os.path.join(out_dir, "metadata.joblib"))
    logger.info("Saved metadata → %s/metadata.joblib", out_dir)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. CORRECTNESS AUDIT of train_model.py
# ═══════════════════════════════════════════════════════════════════════════════

def audit_train_model_py() -> None:
    """
    Print a review of train_model.py against docs/next_adjustments.md.
    This runs no code — just prints a static analysis report.
    """
    issues = [
        ("BUG",  "populate_training_table()",
         "Line ~369: `self._client.load_table_from_dataframe(df, table_ref).job_config` "
         "returns a LoadJob, not a config object. Should use `bigquery.LoadJobConfig()` "
         "directly and set write_disposition on it before calling load_table_from_dataframe once."),

        ("BUG",  "_transform_to_training_format()",
         "Line ~301: `df['phenological_stage'].fillna(3, inplace=True)` on a chained "
         "indexing result raises DeprecationWarning in pandas >= 2.0. "
         "Use `df['phenological_stage'] = df['phenological_stage'].fillna(3)`."),

        ("INFO", "_transform_to_training_format()",
         "Renames simulation_id → plant_id but the schema also defines a separate "
         "`simulation_id` column (line 97). That column is absent from training_cols "
         "list so it is never written. Minor inconsistency; no data is lost."),

        ("OK",   "Feature columns",
         "All columns required by docs/next_adjustments.md are present and correctly "
         "mapped: plant_type, phenological_stage, estimated_biomass, health_confidence, "
         "plant_age_days, last_watering_days, indoor_flag, plus extended environment "
         "columns (air_temp_C, soil_water_pct, etc.)."),

        ("OK",   "Target columns",
         "water_stress, nutrient_stress, temp_stress → temperature_stress — "
         "all three stress targets correctly included."),

        ("OK",   "StressPredictor (rule-based)",
         "Thresholds and tool recommendations match docs Step 4 requirements."),
    ]

    print("\n" + "=" * 80)
    print("AUDIT: tools/train_model.py vs docs/next_adjustments.md")
    print("=" * 80)
    for kind, where, note in issues:
        tag = {"BUG": "❌ BUG", "INFO": "⚠️  INFO", "OK": "✅ OK"}.get(kind, kind)
        print(f"\n{tag}  [{where}]")
        print(f"   {note}")
    print("=" * 80 + "\n")


# ═══════════════════════════════════════════════════════════════════════════════
# 7. CLI + MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Train stress prediction models from simulation data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--source", choices=["bq", "local", "csv"], default="local",
                   help="Data source: bq (BigQuery), local (generate in-process), csv PATH")
    p.add_argument("--csv", default="", metavar="PATH",
                   help="Path to CSV file (required when --source csv)")
    p.add_argument("--bq-limit", type=int, default=200_000,
                   help="Max rows to fetch from BigQuery (default 200 000)")
    p.add_argument("--test-size", type=float, default=0.2,
                   help="Fraction of data held out for evaluation (default 0.2)")
    p.add_argument("--skip-umap", action="store_true",
                   help="Skip UMAP+kNN training (saves time for quick runs)")
    p.add_argument("--save-models", default="", metavar="DIR",
                   help="Directory to save fitted models (joblib)")
    p.add_argument("--out-dir", default="tools/output_plots",
                   help="Directory for output plots (default: tools/output_plots)")
    p.add_argument("--audit-only", action="store_true",
                   help="Only print audit of train_model.py and exit")
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    audit_train_model_py()
    if args.audit_only:
        return

    out_dir = os.path.join(_ROOT, args.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    logger.info("Output plots → %s", out_dir)

    # ── 1. Load data ──────────────────────────────────────────────────────────
    if args.source == "bq":
        df = load_from_bigquery(limit=args.bq_limit)
    elif args.source == "csv":
        if not args.csv:
            logger.error("--source csv requires --csv PATH")
            sys.exit(1)
        df = load_from_csv(args.csv)
    else:
        df = generate_local_data()

    logger.info("Dataset: %d rows, %d columns", len(df), len(df.columns))

    # ── 2. Preprocess ─────────────────────────────────────────────────────────
    X, y, le = preprocess(df)
    feature_names = list(X.columns)

    # Plot distribution before train/test split
    plot_stress_distribution(y, out_dir)

    # ── 3. Train / test split ─────────────────────────────────────────────────
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=args.test_size, random_state=42, shuffle=True,
    )
    logger.info(
        "Train: %d rows | Test: %d rows",
        len(X_train), len(X_test),
    )

    # ── 4. Train models ───────────────────────────────────────────────────────
    all_results, fitted_models = train_all_models(X_train, y_train, X_test, y_test)

    # ── 5. UMAP + kNN ─────────────────────────────────────────────────────────
    umap_emb_test = None
    if not args.skip_umap:
        try:
            umap_res, umap_model, knn_models, umap_emb_test, umap_scaler = train_umap_knn(
                X_train, y_train, X_test, y_test
            )
            all_results["UMAP+kNN"] = umap_res
            fitted_models["UMAP+kNN_umap"]   = umap_model
            fitted_models["UMAP+kNN_knns"]   = knn_models
            fitted_models["UMAP+kNN_scaler"] = umap_scaler
        except Exception as exc:
            logger.warning("UMAP+kNN training failed: %s", exc)

    # ── 6. Plots ──────────────────────────────────────────────────────────────
    logger.info("Generating plots…")
    plot_summary_table(all_results, out_dir)
    plot_confusion_matrices(all_results, out_dir)
    plot_feature_importance(all_results, fitted_models, feature_names, out_dir)
    plot_actual_vs_predicted(all_results, fitted_models, X_test, y_test,
                             fitted_models["_scaler"], out_dir)
    if umap_emb_test is not None:
        plot_umap_embedding(umap_emb_test, y_test, out_dir)

    # ── 7. Best model summary ─────────────────────────────────────────────────
    best_name = max(
        (k for k in all_results if k != "UMAP+kNN"),
        key=lambda k: all_results[k]["mean_r2"],
    )
    print(f"\nBest model: {best_name}  (mean R² = {all_results[best_name]['mean_r2']:.4f})")

    # ── 8. Classification report for best model ───────────────────────────────
    for target in TARGETS:
        cr = all_results[best_name]["targets"][target]["classification_report"]
        print(f"\n{best_name} — {target}:")
        print(f"  {'':12s}  precision  recall  f1-score  support")
        for label in STRESS_LABELS:
            d = cr.get(label, {})
            print(
                f"  {label:12s}  {d.get('precision', 0):.2f}       "
                f"{d.get('recall', 0):.2f}    {d.get('f1-score', 0):.2f}      "
                f"{int(d.get('support', 0))}",
            )

    # ── 9. Save models ────────────────────────────────────────────────────────
    if args.save_models:
        save_models(fitted_models, feature_names, args.save_models)

    print(f"\nAll plots saved to: {out_dir}/")
    print("Files: r2_comparison.png  confusion_matrices.png  feature_importance.png")
    print("       actual_vs_predicted.png  umap_embedding.png  stress_distribution.png")


if __name__ == "__main__":
    main()

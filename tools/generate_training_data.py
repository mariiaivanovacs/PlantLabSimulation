#!/usr/bin/env python3
"""
Training Data Generator for Stress Prediction Model
=====================================================
Runs N headless simulations directly against the engine (no Flask / HTTP)
and logs every hourly snapshot to BigQuery via the existing BigQueryService hook.

Strategy
--------
A good stress-prediction model needs examples where water_stress, temp_stress,
and nutrient_stress cover the full 0–1 range independently AND in combination.
This script covers that through a **condition matrix** — a set of named
initial-state presets (computed relative to each plant's own profile thresholds)
multiplied across:

  3 plant types  ×  2 daily-regime settings  ×  N_CONDITIONS initial presets
  = 60 base simulations (~66 k hourly rows, enough to train a robust model)

You can expand further with the --extra-random flag, which adds an additional
batch of runs with random perturbations on top of the base matrix.

Usage
-----
  # Full base matrix (60 sims, all plants, all conditions)
  python tools/generate_training_data.py

  # Quick smoke-test (only optimal condition, all plants)
  python tools/generate_training_data.py --conditions optimal

  # Tomato only
  python tools/generate_training_data.py --plants tomato_standard

  # Add 20 extra randomised runs per plant
  python tools/generate_training_data.py --extra-random 20

  # Disable BigQuery (dry-run — useful for debugging)
  python tools/generate_training_data.py --no-bq

Initial-condition presets (relative to profile thresholds)
----------------------------------------------------------
  optimal         — all conditions at plant optimum (baseline)
  water_low       — soil water near wilting point  (water stress target)
  water_high      — soil water near saturation     (waterlogging risk)
  temp_cold       — air temp at T_min + 2°C        (cold stress target)
  temp_hot        — air temp at T_max - 2°C        (heat stress target)
  nutrient_low    — N/P/K at 40 % of optimal      (nutrient stress target)
  nutrient_high   — N/P/K at 150 % of optimal     (EC toxicity risk)
  combo_cold_dry  — cold + water_low               (combined stress)
  combo_hot_poor  — hot  + nutrient_low            (combined stress)
  rh_extreme      — very high RH (95%) + slight warmth (humidity edge case)
"""

import argparse
import logging
import math
import os
import random
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

# ── project root ──────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from data.default_plants import DEFAULT_PROFILES, load_default_profile
from models.engine import SimulationEngine
from models.plant_profile import PlantProfile
from services.bigquery_service import BigQueryService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("gen_training")


# ── simulation durations (days) per plant ─────────────────────────────────────
# Long enough to pass through multiple phenological stages; short enough to
# keep batch runs feasible.
DURATION_DAYS: Dict[str, int] = {
    "tomato_standard":    60,   # seed → (often) fruiting  (~1440 rows)
    "lettuce_butterhead": 35,   # seed → harvestable head   (~840 rows)
    "basil_sweet":        45,   # seed → mature herb        (~1080 rows)
}


# ── condition preset definitions ──────────────────────────────────────────────

@dataclass
class ConditionPreset:
    """Relative overrides applied to engine.state after engine creation."""
    name: str
    description: str

    # Fractions / offsets applied per-plant relative to its own thresholds.
    # None means "use the engine default".
    soil_water_frac: Optional[float] = None  # fraction between wilting and saturation
    air_temp_delta:  Optional[float] = None  # delta from T_opt
    nutrient_frac:   Optional[float] = None  # fraction of optimal N/P/K
    rh_override:     Optional[float] = None  # absolute RH %


# 10 base presets ─────────────────────────────────────────────────────────────
BASE_CONDITIONS: List[ConditionPreset] = [
    ConditionPreset(
        name="optimal",
        description="All conditions at plant optimum — baseline, minimal stress",
        soil_water_frac=0.65,   # mid-optimal band
        air_temp_delta=0.0,
        nutrient_frac=1.0,
        rh_override=None,       # use engine default (mid of optimal_RH range)
    ),
    ConditionPreset(
        name="water_low",
        description="Soil water near wilting point — targets water_stress → 1",
        soil_water_frac=0.05,   # just above wilting
        air_temp_delta=0.0,
        nutrient_frac=1.0,
    ),
    ConditionPreset(
        name="water_high",
        description="Soil water near saturation — waterlogging / anaerobic risk",
        soil_water_frac=0.97,
        air_temp_delta=0.0,
        nutrient_frac=1.0,
    ),
    ConditionPreset(
        name="temp_cold",
        description="Air temp at T_min + 2°C — targets temp_stress → high",
        soil_water_frac=0.65,
        air_temp_delta=None,    # set to T_min + 2 (handled in apply_condition)
        nutrient_frac=1.0,
        rh_override=70.0,
    ),
    ConditionPreset(
        name="temp_hot",
        description="Air temp at T_max - 2°C — heat stress without immediate death",
        soil_water_frac=0.65,
        air_temp_delta=None,    # set to T_max - 2 (handled in apply_condition)
        nutrient_frac=1.0,
        rh_override=45.0,
    ),
    ConditionPreset(
        name="nutrient_low",
        description="N/P/K at 40 % of optimal — targets nutrient_stress → high",
        soil_water_frac=0.65,
        air_temp_delta=0.0,
        nutrient_frac=0.40,
    ),
    ConditionPreset(
        name="nutrient_high",
        description="N/P/K at 150 % of optimal — EC toxicity risk at high excess",
        soil_water_frac=0.65,
        air_temp_delta=0.0,
        nutrient_frac=1.50,
    ),
    ConditionPreset(
        name="combo_cold_dry",
        description="Cold + water-low — combined temp and water stress",
        soil_water_frac=0.08,
        air_temp_delta=None,    # T_min + 3
        nutrient_frac=0.80,
        rh_override=75.0,
    ),
    ConditionPreset(
        name="combo_hot_poor",
        description="Hot + nutrient-low — combined heat and nutrient stress",
        soil_water_frac=0.55,
        air_temp_delta=None,    # T_max - 3
        nutrient_frac=0.35,
        rh_override=40.0,
    ),
    ConditionPreset(
        name="rh_extreme",
        description="Very high RH (95 %) — humidity edge case, slight warmth",
        soil_water_frac=0.70,
        air_temp_delta=3.0,
        nutrient_frac=1.0,
        rh_override=95.0,
    ),
]

_CONDITION_MAP: Dict[str, ConditionPreset] = {c.name: c for c in BASE_CONDITIONS}


# ── helpers ───────────────────────────────────────────────────────────────────

def _lerp(lo: float, hi: float, frac: float) -> float:
    """Linear interpolation, clamped to [lo, hi]."""
    return lo + (hi - lo) * max(0.0, min(1.0, frac))


def apply_condition(engine: SimulationEngine, cond: ConditionPreset) -> None:
    """Override engine.state fields according to the preset."""
    p = engine.plant_profile
    s = engine.state

    # ── soil water ────────────────────────────────────────────────────────────
    if cond.soil_water_frac is not None:
        s.soil_water = _lerp(
            p.water.wilting_point,
            p.water.saturation,
            cond.soil_water_frac,
        )

    # ── air temperature ───────────────────────────────────────────────────────
    if cond.name == "temp_cold" or cond.name == "combo_cold_dry":
        s.air_temp = p.temperature.T_min + 2.0
    elif cond.name == "temp_hot" or cond.name == "combo_hot_poor":
        s.air_temp = p.temperature.T_max - 2.0
    elif cond.air_temp_delta is not None:
        s.air_temp = p.temperature.T_opt + cond.air_temp_delta
    # Clamp to physiological limits
    s.air_temp = max(p.temperature.T_min - 5, min(p.temperature.T_max + 5, s.air_temp))
    # Keep soil temp in sync
    s.soil_temp = s.air_temp - 1.0

    # ── nutrients ─────────────────────────────────────────────────────────────
    if cond.nutrient_frac is not None:
        s.soil_N = p.nutrients.optimal_N * cond.nutrient_frac
        s.soil_P = p.nutrients.optimal_P * cond.nutrient_frac
        s.soil_K = p.nutrients.optimal_K * cond.nutrient_frac

    # ── humidity ──────────────────────────────────────────────────────────────
    if cond.rh_override is not None:
        s.relative_humidity = cond.rh_override


def random_condition(profile: PlantProfile, seed: Optional[int] = None) -> ConditionPreset:
    """Generate a random preset whose parameters span the physiological range."""
    rng = random.Random(seed)
    return ConditionPreset(
        name=f"random_{rng.randint(1000, 9999)}",
        description="Randomly sampled initial conditions for extra diversity",
        soil_water_frac=rng.uniform(0.02, 0.98),
        air_temp_delta=rng.uniform(
            profile.temperature.T_min - profile.temperature.T_opt,
            profile.temperature.T_max - profile.temperature.T_opt,
        ),
        nutrient_frac=rng.uniform(0.20, 1.60),
        rh_override=rng.uniform(30.0, 98.0),
    )


# ── single simulation runner ──────────────────────────────────────────────────

def run_one(
    profile_id: str,
    cond: ConditionPreset,
    daily_regime: bool,
    duration_days: int,
    bq: BigQueryService,
    user_id: str = "gen_script",
    verbose: bool = False,
) -> Dict:
    """
    Run one headless simulation and log all hourly rows to BigQuery.

    Returns a summary dict.
    """
    profile = load_default_profile(profile_id)
    sim_id  = str(uuid.uuid4())[:12]
    engine  = SimulationEngine(profile, simulation_id=sim_id)

    # Apply initial-condition overrides BEFORE first step
    apply_condition(engine, cond)

    # Configure daily regime
    engine.set_daily_regime(enabled=daily_regime)

    # Register BigQuery per-hour hook (same path used by Flask routes)
    regime_label = "regime_on" if daily_regime else "regime_off"
    bq_species   = f"{profile_id}_{cond.name}_{regime_label}"
    engine.register_post_step_hook(
        bq.make_hourly_hook(
            user_id=user_id,
            plant_species=profile_id,       # keep species clean for BQ filtering
            tick_gap_hours=1,
            daily_regime_enabled=daily_regime,
        )
    )

    total_hours = duration_days * 24
    start_ts    = time.monotonic()

    for h in range(total_hours):
        engine.step(hours=1)
        if not engine.state.is_alive:
            break

    elapsed  = time.monotonic() - start_ts
    state    = engine.state
    survived = state.is_alive

    summary = {
        "simulation_id":    sim_id,
        "profile_id":       profile_id,
        "condition":        cond.name,
        "daily_regime":     daily_regime,
        "hours_run":        state.hour,
        "final_biomass_g":  round(state.biomass, 3),
        "final_stage":      state.phenological_stage.value,
        "survived":         survived,
        "death_reason":     state.death_reason if not survived else None,
        "cum_damage_pct":   round(state.cumulative_damage, 2),
        "wall_s":           round(elapsed, 1),
    }

    # Write run-level row to BQ
    try:
        run_row = bq.build_run_row(
            engine=engine,
            user_id=user_id,
            plant_species=profile_id,
            tick_gap_hours=1,
            daily_regime_enabled=daily_regime,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        bq.log_run_row(run_row)
    except Exception as exc:
        logger.warning("build_run_row failed: %s", exc)

    if verbose:
        status = "ALIVE" if survived else f"DIED ({state.death_reason})"
        logger.info(
            "  [%s] cond=%-18s regime=%-3s  "
            "h=%4d  biomass=%7.2fg  stage=%-12s  %s  (%.1fs)",
            profile_id,
            cond.name,
            "on" if daily_regime else "off",
            state.hour,
            state.biomass,
            state.phenological_stage.value,
            status,
            elapsed,
        )

    return summary


# ── batch runner ──────────────────────────────────────────────────────────────

def run_batch(
    plants:       List[str],
    conditions:   List[ConditionPreset],
    regimes:      List[bool],
    bq:           BigQueryService,
    extra_random: int = 0,
    verbose:      bool = True,
) -> List[Dict]:
    """
    Run the full condition matrix, flushing BigQuery every 10 simulations.

    Returns list of summary dicts.
    """
    summaries: List[Dict] = []
    total = len(plants) * len(conditions) * len(regimes)
    idx   = 0

    logger.info("=" * 70)
    logger.info("Batch: %d plants × %d conditions × %d regimes = %d simulations",
                len(plants), len(conditions), len(regimes), total)
    if extra_random > 0:
        logger.info("  + %d extra random sims per plant (%d additional)",
                    extra_random, extra_random * len(plants))
    logger.info("=" * 70)

    for profile_id in plants:
        duration = DURATION_DAYS.get(profile_id, 45)

        for regime in regimes:
            for cond in conditions:
                idx += 1
                if verbose:
                    logger.info(
                        "[%d/%d] %s | cond=%-18s | regime=%s",
                        idx, total, profile_id, cond.name,
                        "on" if regime else "off",
                    )
                try:
                    s = run_one(
                        profile_id=profile_id,
                        cond=cond,
                        daily_regime=regime,
                        duration_days=duration,
                        bq=bq,
                        verbose=verbose,
                    )
                    summaries.append(s)
                except Exception as exc:
                    logger.error("Sim failed (%s / %s / regime=%s): %s",
                                 profile_id, cond.name, regime, exc)

                # Periodic BQ flush (avoids huge in-memory buffer)
                if idx % 10 == 0:
                    bq.flush_all()

        # ── extra random sims for this plant ──────────────────────────────
        if extra_random > 0:
            profile = load_default_profile(profile_id)
            logger.info("  Running %d random sims for %s …", extra_random, profile_id)
            for r in range(extra_random):
                regime = r % 2 == 0   # alternate on/off
                seed   = abs(hash((profile_id, r))) % (2**31)
                cond   = random_condition(profile, seed=seed)
                try:
                    s = run_one(
                        profile_id=profile_id,
                        cond=cond,
                        daily_regime=regime,
                        duration_days=DURATION_DAYS.get(profile_id, 45),
                        bq=bq,
                        verbose=verbose,
                    )
                    summaries.append(s)
                except Exception as exc:
                    logger.error("Random sim failed (%s seed=%d): %s",
                                 profile_id, seed, exc)

            bq.flush_all()

    # Final flush
    bq.flush_all()
    return summaries


# ── summary report ────────────────────────────────────────────────────────────

def print_report(summaries: List[Dict]) -> None:
    if not summaries:
        print("\nNo simulations completed.")
        return

    total   = len(summaries)
    alive   = sum(1 for s in summaries if s["survived"])
    dead    = total - alive
    total_h = sum(s["hours_run"] for s in summaries)

    print("\n" + "=" * 70)
    print("BATCH COMPLETE — SUMMARY")
    print("=" * 70)
    print(f"  Total simulations   : {total}")
    print(f"  Plant survived      : {alive}  ({100*alive//total}%)")
    print(f"  Plant died          : {dead}")
    print(f"  Total simulated hrs : {total_h:,}  "
          f"({total_h // 24:,} days, ~{total_h:,} BigQuery rows)")
    print()

    # Per-plant breakdown
    for pid in sorted({s["profile_id"] for s in summaries}):
        psims = [s for s in summaries if s["profile_id"] == pid]
        avg_h = sum(s["hours_run"] for s in psims) / len(psims)
        print(f"  {pid}:")
        print(f"    sims={len(psims)}, avg_hours={avg_h:.0f}, "
              f"survived={sum(1 for s in psims if s['survived'])}/{len(psims)}")

        # Death reasons
        deaths = [s["death_reason"] for s in psims if not s["survived"]]
        if deaths:
            from collections import Counter
            for reason, count in Counter(deaths).most_common():
                print(f"      death → {reason}: {count}×")
    print("=" * 70)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate BigQuery training data via headless simulations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples
--------
  # Full matrix — all plants, all conditions, both regimes (60 sims)
  python tools/generate_training_data.py

  # Only tomato, both regimes, all conditions
  python tools/generate_training_data.py --plants tomato_standard

  # Only specific condition(s)
  python tools/generate_training_data.py --conditions water_low,temp_hot

  # Add 30 random sims per plant for extra diversity
  python tools/generate_training_data.py --extra-random 30

  # Dry run (no BigQuery writes, useful for testing)
  python tools/generate_training_data.py --no-bq

  # Disable daily regime entirely (only unmanaged sims)
  python tools/generate_training_data.py --no-regime

  # Only daily-regime sims
  python tools/generate_training_data.py --only-regime

Available initial-condition presets
------------------------------------
""" + "\n".join(
    f"  {c.name:<20} {c.description}" for c in BASE_CONDITIONS
),
    )
    parser.add_argument(
        "--plants", "-p",
        default="",
        help="Comma-separated list of plant profile IDs (default: all 3)",
    )
    parser.add_argument(
        "--conditions", "-c",
        default="",
        help="Comma-separated condition preset names (default: all 10)",
    )
    parser.add_argument(
        "--extra-random", "-r",
        type=int,
        default=0,
        metavar="N",
        help="Add N extra randomised simulations per plant (default: 0)",
    )
    parser.add_argument(
        "--no-bq",
        action="store_true",
        help="Skip BigQuery writes (dry-run / debug mode)",
    )
    parser.add_argument(
        "--no-regime",
        action="store_true",
        help="Only run sims WITHOUT daily regime",
    )
    parser.add_argument(
        "--only-regime",
        action="store_true",
        help="Only run sims WITH daily regime",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress per-simulation log lines",
    )
    return parser.parse_args()


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()

    # ── resolve plant list ────────────────────────────────────────────────────
    all_plants = list(DEFAULT_PROFILES.keys())
    if args.plants:
        plants = [p.strip() for p in args.plants.split(",") if p.strip()]
        unknown = [p for p in plants if p not in DEFAULT_PROFILES]
        if unknown:
            logger.error("Unknown plant profiles: %s", unknown)
            logger.error("Available: %s", all_plants)
            sys.exit(1)
    else:
        plants = all_plants

    # ── resolve condition list ────────────────────────────────────────────────
    if args.conditions:
        cond_names = [c.strip() for c in args.conditions.split(",") if c.strip()]
        unknown_c = [c for c in cond_names if c not in _CONDITION_MAP]
        if unknown_c:
            logger.error("Unknown conditions: %s", unknown_c)
            logger.error("Available: %s", list(_CONDITION_MAP.keys()))
            sys.exit(1)
        conditions = [_CONDITION_MAP[c] for c in cond_names]
    else:
        conditions = BASE_CONDITIONS

    # ── resolve regime list ───────────────────────────────────────────────────
    if args.no_regime and args.only_regime:
        logger.error("--no-regime and --only-regime are mutually exclusive")
        sys.exit(1)
    elif args.no_regime:
        regimes = [False]
    elif args.only_regime:
        regimes = [True]
    else:
        regimes = [True, False]

    # ── BigQuery service ──────────────────────────────────────────────────────
    bq = BigQueryService.get()

    if args.no_bq:
        # Monkey-patch to suppress writes
        bq._connected = False
        logger.info("--no-bq: BigQuery writes disabled (dry run)")
    else:
        if bq.connected:
            logger.info("BigQuery connected — rows will be written to %s.%s",
                        bq.DATASET, bq.TABLE_HOURLY)
        else:
            logger.warning(
                "BigQuery NOT connected — rows buffered locally only.\n"
                "  Set FIREBASE_PROJECT_ID + FIREBASE_CREDENTIALS_PATH env vars to enable."
            )

    # ── print plan ────────────────────────────────────────────────────────────
    est_rows = sum(
        DURATION_DAYS.get(pid, 45) * 24
        for pid in plants
        for _ in conditions
        for _ in regimes
    )
    if args.extra_random > 0:
        est_rows += sum(
            DURATION_DAYS.get(pid, 45) * 24 * args.extra_random
            for pid in plants
        )

    print()
    print("=" * 70)
    print("TRAINING DATA GENERATION PLAN")
    print("=" * 70)
    print(f"  Plants      : {plants}")
    print(f"  Conditions  : {[c.name for c in conditions]}")
    print(f"  Regimes     : {['on' if r else 'off' for r in regimes]}")
    print(f"  Extra random: {args.extra_random} per plant")
    print(f"  Est. rows   : ~{est_rows:,}")
    print("=" * 70)
    print()

    # ── run ───────────────────────────────────────────────────────────────────
    t0 = time.monotonic()
    summaries = run_batch(
        plants=plants,
        conditions=conditions,
        regimes=regimes,
        bq=bq,
        extra_random=args.extra_random,
        verbose=not args.quiet,
    )
    elapsed = time.monotonic() - t0

    print_report(summaries)
    print(f"\nTotal wall time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()

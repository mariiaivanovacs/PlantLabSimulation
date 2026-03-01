# """Test script to verify the structure works"""

# import sys
# import os

# # Test imports
# print("Testing PlantLabSimulation2 structure...")
# print("="*60)

# try:
#     # Test Flask app
#     from app import create_app
#     app = create_app()
#     print("✓ Flask app created successfully")
    
#     # Test simulation engine
#     from models.engine import SimulationEngine
#     from models.plant_profile import PlantProfile
#     from models.state import PlantState
#     print("✓ Simulation engine imports successful")
    
#     # Test agents
#     from agents.planner import Planner
#     from agents.executor import Executor
#     from agents.memory import Memory
#     print("✓ Agent imports successful")
    
#     # Test services
#     from services.firebase_service import FirebaseService
#     from services.logging_service import LoggingService
#     print("✓ Service imports successful")
    
#     # Test data
#     from data.default_plants import get_plant_profile, DEFAULT_PLANTS
#     print("✓ Data imports successful")
    
#     # Test config
#     from config.settings import FLASK_ENV, PORT
#     print("✓ Config imports successful")
    
#     print("="*60)
#     print("All imports successful! ✓")
#     print("\nAvailable plants:")
#     for plant_name in DEFAULT_PLANTS.keys():
#         print(f"  - {plant_name}")
    
#     print("\nTo run Flask server:")
#     print("  python run.py")
    
#     print("\nTo run CLI:")
#     print("  python main.py list")
#     print("  python main.py run tomato 30")
    
# except Exception as e:
#     print(f"✗ Error: {e}")
#     import traceback
#     traceback.print_exc()



#!/usr/bin/env python3
"""
visualize_growth_log.py

Read and visualize a plant-growth log recorded every 12 hours with lines like:
  record_idx,biomass,phenological_stage,relative_humidity,air_temp,CO2,RGR

Example line:
  0,0.05,seedling,70.0,20.0,400.0,0

This script:
 - robustly parses the file (tolerant to spaces and small formatting problems)
 - reconstructs a time axis in hours (record_idx * 12)
 - writes parsed CSV and summary CSVs
 - saves individual matplotlib plots:
     biomass, RGR, CO2, temp+RH (twin axis), phenology (step)
 - creates a small problem_report CSV listing rows with negative RGR or
   negative biomass deltas between consecutive records.

Usage:
  python visualize_growth_log.py growth_log.txt --outdir ./out --show-table
"""

import argparse
import os
import sys
from io import StringIO
import pandas as pd
import matplotlib.pyplot as plt

# SAMPLE_TEXT = """0,0.05,seedling,70.0,20.0,400.0,0
# 1,0.31564322783412435,vegetative,68.0,20.0,942.1234196499513,-0.00034975390579549147
# 2,1.14542086429885,vegetative,66.2,20.0,941.8295484777631,-0.0003487848180027874
# 3,2.633786816383623,vegetative,64.58000000000001,20.0,941.5772650371332,-0.00034704658187207786
# 4,4.679688563736865,vegetative,63.122000000000014,20.0,941.3829263531528,-0.00034465722931756207
# 5,7.195437628314755,vegetative,61.80980000000002,20.0,941.2273431245769,-0.00034171918625731836
# 6,10.12184456707248,vegetative,60.62882000000002,20.0,941.0997768183884,-0.000338301595660929
# 7,13.412973168049273,flowering,59.56593800000002,20.0,940.9950426567917,-0.00033445812238133005
# 8,17.028809614025672,fruiting,58.60934420000002,20.0,940.9102149131922,-0.0003302355141723347
# 9,20.931827589937587,fruiting,57.74840978000002,20.0,940.8433105614414,-0.00032567761265481573
# """

EXPECTED_COLS = [
    "record_idx",
    "biomass",
    "phenological_stage",
    "relative_humidity",
    "air_temp",
    "CO2",
    "RGR",
    "ET",
    "water_stress"
]

STAGE_ORDER = ["seed", "seedling", "vegetative", "flowering", "fruiting", "mature", "dead"]


def parse_line(line: str, line_no: int):
    """Parse a single log line into a dict; return None for malformed lines."""
    if not line or not line.strip():
        return None
    # split into at most 9 parts to handle new ET and water_stress fields
    parts = [p.strip() for p in line.strip().split(",", 8)]
    if len(parts) < 7:
        # if still fewer than 7, skip (old format without ET and water_stress)
        print(f"[parse] skipping malformed line {line_no}: {line.strip()}", file=sys.stderr)
        return None

    try:
        rec_idx = int(float(parts[0]))
        biomass = float(parts[1])
        pheno = parts[2].strip().lower()
        rh = float(parts[3])
        t = float(parts[4])
        co2 = float(parts[5])
        rgr = float(parts[6])

        # Handle optional ET and water_stress fields (new format)
        et = float(parts[7]) if len(parts) > 7 else 0.0
        water_stress = float(parts[8]) if len(parts) > 8 else 0.0

        return {
            "record_idx": rec_idx,
            "biomass": biomass,
            "phenological_stage": pheno,
            "relative_humidity": rh,
            "air_temp": t,
            "CO2": co2,
            "RGR": rgr,
            "ET": et,
            "water_stress": water_stress
        }
    except Exception as e:
        print(f"[parse] error parsing line {line_no}: {e}; line content: {parts}", file=sys.stderr)
        return None


def load_log(file_path: str):
    """Load the growth log file; if missing, use SAMPLE_TEXT as demo fallback."""
    if not file_path or not os.path.exists(file_path):
        print(f"[load_log] file '{file_path}' not found — using embedded sample data for demo.", file=sys.stderr)
        fh = StringIO(SAMPLE_TEXT)
    else:
        fh = open(file_path, "r", encoding="utf-8")

    records = []
    for i, line in enumerate(fh, start=1):
        parsed = parse_line(line, i)
        if parsed:
            records.append(parsed)
    try:
        if hasattr(fh, "close"):
            fh.close()
    except Exception:
        pass

    if not records:
        raise ValueError("No valid records parsed from the file (and sample fallback failed).")

    df = pd.DataFrame.from_records(records)
    # reconstruct time in hours: record_idx * 12
    df["time_hours"] = df["record_idx"].astype(int) * 12
    df = df.sort_values("time_hours").reset_index(drop=True)

    # make phenological_stage categorical with desired order
    df["phenological_stage"] = pd.Categorical(
        df["phenological_stage"].str.lower().str.strip(),
        categories=STAGE_ORDER,
        ordered=True
    )
    return df


def summarize_and_save(df: pd.DataFrame, outdir: str, prefix: str = "growth"):
    """Save parsed CSV, summary stats and stage durations CSVs."""
    os.makedirs(outdir, exist_ok=True)
    parsed_csv = os.path.join(outdir, f"{prefix}_parsed.csv")
    df.to_csv(parsed_csv, index=False)

    # Include ET and water_stress in summary if they exist
    summary_cols = ["biomass", "RGR", "CO2", "air_temp", "relative_humidity"]
    if "ET" in df.columns:
        summary_cols.append("ET")
    if "water_stress" in df.columns:
        summary_cols.append("water_stress")

    summary = df[summary_cols].agg(["min", "mean", "max"]).T
    summary_csv = os.path.join(outdir, f"{prefix}_summary.csv")
    summary.to_csv(summary_csv)

    # stage durations (hours) measured by count of records * 12
    stage_durations = []
    if df["phenological_stage"].notna().any():
        grouped = df.groupby("phenological_stage", sort=False)
        for stage, g in grouped:
            duration_hours = len(g) * 12
            stage_durations.append({"phenological_stage": stage, "duration_hours": duration_hours, "records": len(g)})
    stage_df = pd.DataFrame(stage_durations)
    stage_csv = os.path.join(outdir, f"{prefix}_stage_durations.csv")
    if not stage_df.empty:
        stage_df.to_csv(stage_csv, index=False)

    return {
        "parsed_csv": parsed_csv,
        "summary_csv": summary_csv,
        "stage_csv": stage_csv if not stage_df.empty else None
    }


def generate_plots(df: pd.DataFrame, outdir: str, prefix: str = "growth"):
    """Create and save separate matplotlib figures (one per file)."""
    os.makedirs(outdir, exist_ok=True)
    saved = {}

    # 1) Biomass
    fig = plt.figure(figsize=(8, 4))
    plt.plot(df["time_hours"], df["biomass"], marker="o")
    plt.title("Biomass over time (hours)")
    plt.xlabel("Time (hours)")
    plt.ylabel("Biomass (g)")
    plt.grid(True)
    plt.tight_layout()
    path = os.path.join(outdir, f"{prefix}_biomass.png")
    fig.savefig(path)
    plt.close(fig)
    saved["biomass_plot"] = path

    # 2) RGR
    fig = plt.figure(figsize=(8, 4))
    plt.plot(df["time_hours"], df["RGR"], marker="o")
    plt.axhline(0, linestyle="--")
    plt.title("Relative Growth Rate (RGR) over time")
    plt.xlabel("Time (hours)")
    plt.ylabel("RGR")
    plt.grid(True)
    plt.tight_layout()
    path = os.path.join(outdir, f"{prefix}_RGR.png")
    fig.savefig(path)
    plt.close(fig)
    saved["RGR_plot"] = path

    # 3) CO2
    fig = plt.figure(figsize=(8, 4))
    plt.plot(df["time_hours"], df["CO2"], marker="o")
    plt.title("CO₂ (ppm) over time")
    plt.xlabel("Time (hours)")
    plt.ylabel("CO₂ (ppm)")
    plt.grid(True)
    plt.tight_layout()
    path = os.path.join(outdir, f"{prefix}_CO2.png")
    fig.savefig(path)
    plt.close(fig)
    saved["CO2_plot"] = path

    # 4) Temp + RH (twin axis)
    fig = plt.figure(figsize=(8, 4))
    ax1 = fig.add_subplot(111)
    ax1.plot(df["time_hours"], df["air_temp"], marker="o")
    ax1.set_xlabel("Time (hours)")
    ax1.set_ylabel("Air Temp (°C)")
    ax2 = ax1.twinx()
    ax2.plot(df["time_hours"], df["relative_humidity"], marker="s")
    ax2.set_ylabel("Relative Humidity (%)")
    plt.title("Air Temperature and Relative Humidity over time")
    plt.grid(True)
    plt.tight_layout()
    path = os.path.join(outdir, f"{prefix}_temp_rh.png")
    fig.savefig(path)
    plt.close(fig)
    saved["temp_rh_plot"] = path

    # 5) Phenology step plot
    # Convert categories to codes (NaN -> -1). We'll map -1 to 'unknown' if present.
    codes = df["phenological_stage"].cat.codes.replace(-1, pd.NA)
    fig = plt.figure(figsize=(8, 3))
    plt.step(df["time_hours"], codes, where="post", marker="o")
    defined = [s for s in STAGE_ORDER if s in df["phenological_stage"].cat.categories]
    y_ticks = list(range(len(defined)))
    plt.yticks(y_ticks, defined)
    plt.xlabel("Time (hours)")
    plt.title("Phenological stage over time (step plot)")
    plt.tight_layout()
    path = os.path.join(outdir, f"{prefix}_phenology.png")
    fig.savefig(path)
    plt.close(fig)
    saved["phenology_plot"] = path

    # 6) ET (Evapotranspiration) - if available
    if "ET" in df.columns and df["ET"].notna().any():
        fig = plt.figure(figsize=(8, 4))
        plt.plot(df["time_hours"], df["ET"], marker="o", color="blue")
        plt.title("Evapotranspiration (ET) over time")
        plt.xlabel("Time (hours)")
        plt.ylabel("ET (L/h)")
        plt.grid(True)
        plt.tight_layout()
        path = os.path.join(outdir, f"{prefix}_ET.png")
        fig.savefig(path)
        plt.close(fig)
        saved["ET_plot"] = path

    # 7) Water Stress - if available
    if "water_stress" in df.columns and df["water_stress"].notna().any():
        fig = plt.figure(figsize=(8, 4))
        plt.plot(df["time_hours"], df["water_stress"], marker="o", color="red")
        plt.axhline(0.5, linestyle="--", color="orange", label="High stress threshold")
        plt.axhline(0.8, linestyle="--", color="darkred", label="Critical stress threshold")
        plt.title("Water Stress over time")
        plt.xlabel("Time (hours)")
        plt.ylabel("Water Stress (0-1)")
        plt.ylim(0, 1)
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        path = os.path.join(outdir, f"{prefix}_water_stress.png")
        fig.savefig(path)
        plt.close(fig)
        saved["water_stress_plot"] = path

    # 8) Combined ET vs Water Stress - if both available
    if "ET" in df.columns and "water_stress" in df.columns and df["ET"].notna().any() and df["water_stress"].notna().any():
        fig = plt.figure(figsize=(8, 4))
        ax1 = fig.add_subplot(111)
        ax1.plot(df["time_hours"], df["ET"], marker="o", color="blue", label="ET (L/h)")
        ax1.set_xlabel("Time (hours)")
        ax1.set_ylabel("ET (L/h)", color="blue")
        ax1.tick_params(axis='y', labelcolor="blue")

        ax2 = ax1.twinx()
        ax2.plot(df["time_hours"], df["water_stress"], marker="s", color="red", label="Water Stress")
        ax2.set_ylabel("Water Stress (0-1)", color="red")
        ax2.tick_params(axis='y', labelcolor="red")
        ax2.set_ylim(0, 1)

        plt.title("ET and Water Stress over time")
        plt.grid(True)
        plt.tight_layout()
        path = os.path.join(outdir, f"{prefix}_ET_vs_water_stress.png")
        fig.savefig(path)
        plt.close(fig)
        saved["ET_vs_water_stress_plot"] = path

    return saved


def generate_problem_report(df: pd.DataFrame, outdir: str, prefix: str = "growth"):
    """Identify negative RGRs and negative biomass deltas and save a small report CSV."""
    os.makedirs(outdir, exist_ok=True)
    report_rows = []

    # Negative RGR rows
    neg_rgr = df[df["RGR"] < 0]
    for _, r in neg_rgr.iterrows():
        report_rows.append({
            "time_hours": r["time_hours"],
            "issue": "negative_RGR",
            "record_idx": r["record_idx"],
            "biomass": r["biomass"],
            "RGR": r["RGR"],
            "phenological_stage": r["phenological_stage"]
        })

    # Negative biomass delta between consecutive records
    df_sorted = df.sort_values("time_hours").reset_index(drop=True)
    df_sorted["biomass_delta"] = df_sorted["biomass"].diff()
    neg_delta = df_sorted[df_sorted["biomass_delta"] < 0]
    for _, r in neg_delta.iterrows():
        report_rows.append({
            "time_hours": r["time_hours"],
            "issue": "negative_biomass_delta",
            "record_idx": r["record_idx"],
            "biomass": r["biomass"],
            "biomass_delta": r["biomass_delta"],
            "phenological_stage": r["phenological_stage"]
        })

    report_df = pd.DataFrame(report_rows)
    report_path = os.path.join(outdir, f"{prefix}_problem_report.csv")
    report_df.to_csv(report_path, index=False)
    return report_path, report_df


def main(argv=None):
    parser = argparse.ArgumentParser(description="Visualize plant growth log recorded every 12 hours.")
    parser.add_argument("file", help="Path to growth log file (text). If missing, a sample dataset will be used.")
    parser.add_argument("--outdir", "-o", help="Output directory for CSVs and plots", default="./out")
    parser.add_argument("--prefix", "-p", help="Filename prefix for saved files", default="growth")
    parser.add_argument("--show-table", action="store_true", help="Attempt to show parsed table using display helper (Jupyter-only)")
    args = parser.parse_args(argv)

    try:
        df = load_log(args.file)
    except Exception as e:
        print(f"[error] failed to load file: {e}", file=sys.stderr)
        sys.exit(2)

    # Optionally show table (Jupyter helper)
    if args.show_table:
        try:
            from caas_jupyter_tools import display_dataframe_to_user
            display_dataframe_to_user("Parsed growth log", df)
        except Exception as e:
            print("[info] show-table requested but display helper not available:", e, file=sys.stderr)
            print(df.head())

    saved = summarize_and_save(df, args.outdir, prefix=args.prefix)
    plots = generate_plots(df, args.outdir, prefix=args.prefix)
    problem_path, problem_df = generate_problem_report(df, args.outdir, prefix=args.prefix)

    print("\nSaved files:")
    for k, v in saved.items():
        if v:
            print(f"  {k}: {v}")
    for k, v in plots.items():
        print(f"  {k}: {v}")
    print(f"  problem_report: {problem_path}")

    # brief console summary
    print("\nQuick summary:")
    print(f"  Records parsed: {len(df)}")
    if not problem_df.empty:
        print(f"  Problems found: {len(problem_df)} (see problem_report CSV)")
    else:
        print("  No negative RGR or negative biomass delta detected in parsed records.")

    print("\nDone.")


if __name__ == "__main__":
    main()

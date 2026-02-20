"""
BigQuery Logging Service

Stores per-hour simulation snapshots and per-run summaries in BigQuery for
ML training / prediction.

Tables (dataset: plant_simulation):
  simulation_hourly_logs  — one row per simulated hour, partitioned by date
  simulation_runs         — one summary row per completed run

Usage (from simulation_routes.py):
    from services.bigquery_service import BigQueryService
    bq = BigQueryService.get()
    engine.register_post_step_hook(bq.make_hourly_hook(
        user_id, plant_species, tick_gap_hours, daily_regime))
    ...
    bq.log_run_row(bq.build_run_row(...))
    bq.flush_all()
"""

import json
import logging
import math
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── helpers ───────────────────────────────────────────────────────────────────

def _safe_float(v) -> Optional[float]:
    """Return None for inf / nan so BigQuery accepts the value."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None


# ── service ───────────────────────────────────────────────────────────────────

class BigQueryService:
    """
    Singleton BigQuery writer.

    Buffers rows and flushes every BUFFER_SIZE records or when flush_all()
    is called explicitly (e.g. at simulation end).
    """

    DATASET = "plant_simulation"
    TABLE_HOURLY = "simulation_hourly_logs"
    TABLE_RUNS = "simulation_runs"
    BUFFER_SIZE = 50  # rows before auto-flush

    # ── BigQuery schema definitions ───────────────────────────────────────────
    # Each entry: (column_name, BQ_type, mode)

    _SCHEMA_HOURLY = [
        # Identifiers / metadata
        ("simulation_id",                "STRING",    "NULLABLE"),
        ("user_id",                      "STRING",    "NULLABLE"),
        ("plant_species",                "STRING",    "NULLABLE"),
        ("hour",                         "INTEGER",   "NULLABLE"),
        ("day",                          "INTEGER",   "NULLABLE"),
        ("hour_of_day",                  "INTEGER",   "NULLABLE"),
        ("simulated_timestamp",          "TIMESTAMP", "NULLABLE"),
        ("tick_gap_hours",               "INTEGER",   "NULLABLE"),
        ("recorded_at",                  "TIMESTAMP", "NULLABLE"),
        ("simulated_date",               "DATE",      "NULLABLE"),  # partition column
        # Core plant state
        ("is_alive",                     "BOOL",      "NULLABLE"),
        ("phenological_stage",           "STRING",    "NULLABLE"),
        ("biomass_g",                    "FLOAT64",   "NULLABLE"),
        ("leaf_biomass_g",               "FLOAT64",   "NULLABLE"),
        ("stem_biomass_g",               "FLOAT64",   "NULLABLE"),
        ("root_biomass_g",               "FLOAT64",   "NULLABLE"),
        ("leaf_area_m2",                 "FLOAT64",   "NULLABLE"),
        ("thermal_time_Cdh",             "FLOAT64",   "NULLABLE"),
        ("seed_reserves_g",              "FLOAT64",   "NULLABLE"),
        ("growth_saturation",            "FLOAT64",   "NULLABLE"),
        ("death_reason",                 "STRING",    "NULLABLE"),
        # Growth / carbon fluxes (per hour)
        ("photosynthesis_g_h",           "FLOAT64",   "NULLABLE"),
        ("respiration_g_h",              "FLOAT64",   "NULLABLE"),
        ("growth_rate_g_h",              "FLOAT64",   "NULLABLE"),
        ("co2_uptake_g_h",               "FLOAT64",   "NULLABLE"),
        ("RGR_per_h",                    "FLOAT64",   "NULLABLE"),
        ("doubling_time_h",              "FLOAT64",   "NULLABLE"),
        # CO2 room dynamics (per hour, from engine.co2_fluxes)
        ("co2_ppm",                      "FLOAT64",   "NULLABLE"),
        ("co2_production_ppm_h",         "FLOAT64",   "NULLABLE"),
        ("co2_consumption_ppm_h",        "FLOAT64",   "NULLABLE"),
        ("co2_injection_ppm_h",          "FLOAT64",   "NULLABLE"),
        ("co2_ventilation_ppm_h",        "FLOAT64",   "NULLABLE"),
        ("co2_leakage_ppm_h",            "FLOAT64",   "NULLABLE"),
        # Water balance
        ("soil_water_pct",               "FLOAT64",   "NULLABLE"),
        ("ET_L_h",                       "FLOAT64",   "NULLABLE"),
        ("hours_without_adequate_water", "FLOAT64",   "NULLABLE"),
        ("last_watering_hour",           "INTEGER",   "NULLABLE"),
        # Soil chemistry
        ("soil_temp_C",                  "FLOAT64",   "NULLABLE"),
        ("soil_N_ppm",                   "FLOAT64",   "NULLABLE"),
        ("soil_P_ppm",                   "FLOAT64",   "NULLABLE"),
        ("soil_K_ppm",                   "FLOAT64",   "NULLABLE"),
        ("soil_EC_mS_cm",                "FLOAT64",   "NULLABLE"),
        ("soil_pH",                      "FLOAT64",   "NULLABLE"),
        # Environment / climate
        ("air_temp_C",                   "FLOAT64",   "NULLABLE"),
        ("relative_humidity_pct",        "FLOAT64",   "NULLABLE"),
        ("VPD_kPa",                      "FLOAT64",   "NULLABLE"),
        ("light_PAR_umol_m2_s",          "FLOAT64",   "NULLABLE"),
        # Stress indices (0–1)
        ("water_stress",                 "FLOAT64",   "NULLABLE"),
        ("temp_stress",                  "FLOAT64",   "NULLABLE"),
        ("nutrient_stress",              "FLOAT64",   "NULLABLE"),
        ("cumulative_damage_pct",        "FLOAT64",   "NULLABLE"),
        ("accumulated_water_stress",     "FLOAT64",   "NULLABLE"),
        # Tool actions at this hour
        ("actions_applied",              "STRING",    "NULLABLE"),  # JSON array string
        ("watering_applied_L",           "FLOAT64",   "NULLABLE"),
        ("co2_injected_g",               "FLOAT64",   "NULLABLE"),
        # Simulation config (duplicated for ML convenience)
        ("pot_volume_L",                 "FLOAT64",   "NULLABLE"),
        ("room_volume_m3",               "FLOAT64",   "NULLABLE"),
        ("daily_regime_enabled",         "BOOL",      "NULLABLE"),
    ]

    _SCHEMA_RUNS = [
        ("simulation_id",            "STRING",    "NULLABLE"),
        ("user_id",                  "STRING",    "NULLABLE"),
        ("plant_species",            "STRING",    "NULLABLE"),
        ("started_at",               "TIMESTAMP", "NULLABLE"),
        ("ended_at",                 "TIMESTAMP", "NULLABLE"),
        ("total_hours",              "INTEGER",   "NULLABLE"),
        ("total_days",               "FLOAT64",   "NULLABLE"),
        ("final_biomass_g",          "FLOAT64",   "NULLABLE"),
        ("final_stage",              "STRING",    "NULLABLE"),
        ("is_alive",                 "BOOL",      "NULLABLE"),
        ("death_reason",             "STRING",    "NULLABLE"),
        ("cumulative_damage_pct",    "FLOAT64",   "NULLABLE"),
        ("total_water_supplied_L",   "FLOAT64",   "NULLABLE"),
        ("water_applications",       "INTEGER",   "NULLABLE"),
        ("total_co2_injected_g",     "FLOAT64",   "NULLABLE"),
        ("co2_injections",           "INTEGER",   "NULLABLE"),
        ("tick_gap_hours",           "INTEGER",   "NULLABLE"),
        ("daily_regime_enabled",     "BOOL",      "NULLABLE"),
        ("total_actions",            "INTEGER",   "NULLABLE"),
    ]

    _instance: Optional['BigQueryService'] = None

    # ── init / singleton ──────────────────────────────────────────────────────

    def __init__(self) -> None:
        self._client = None
        self._connected = False
        self._project_id: Optional[str] = None
        self._buffer_hourly: List[Dict[str, Any]] = []
        self._buffer_runs: List[Dict[str, Any]] = []
        self._try_connect()

    @classmethod
    def get(cls) -> 'BigQueryService':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── connection ────────────────────────────────────────────────────────────

    def _try_connect(self) -> None:
        try:
            from google.cloud import bigquery
            from google.oauth2 import service_account

            project_id = os.getenv('FIREBASE_PROJECT_ID') or os.getenv('BIGQUERY_PROJECT_ID')
            creds_path = os.getenv('FIREBASE_CREDENTIALS_PATH')

            if not project_id:
                logger.warning('BigQueryService: FIREBASE_PROJECT_ID not set — local-only mode')
                return

            self._project_id = project_id

            if creds_path and os.path.exists(creds_path):
                creds = service_account.Credentials.from_service_account_file(
                    creds_path,
                    scopes=["https://www.googleapis.com/auth/bigquery"],
                )
                self._client = bigquery.Client(project=project_id, credentials=creds)
            else:
                self._client = bigquery.Client(project=project_id)

            self._connected = True
            logger.info('BigQueryService: connected to project %s', project_id)
            self._ensure_tables()

        except ImportError:
            logger.warning('BigQueryService: google-cloud-bigquery not installed — local-only mode')
        except Exception as exc:
            logger.warning('BigQueryService: init failed (%s) — local-only mode', exc)

    @property
    def connected(self) -> bool:
        return self._connected

    # ── table management ──────────────────────────────────────────────────────

    def _ensure_tables(self) -> None:
        """Create dataset and both tables if they don't exist."""
        if not self._connected:
            return
        try:
            from google.cloud import bigquery

            # Dataset
            dataset_ref = f"{self._project_id}.{self.DATASET}"
            dataset = bigquery.Dataset(dataset_ref)
            dataset.location = "US"
            self._client.create_dataset(dataset, exists_ok=True)

            # Hourly logs — partitioned by simulated_date, clustered
            self._create_table(
                self.TABLE_HOURLY,
                self._SCHEMA_HOURLY,
                partition_field="simulated_date",
                cluster_fields=["simulation_id", "user_id", "plant_species"],
            )

            # Run summaries — no partitioning needed (low volume)
            self._create_table(self.TABLE_RUNS, self._SCHEMA_RUNS)

        except Exception as exc:
            logger.error('BigQueryService: _ensure_tables failed: %s', exc)
            self._connected = False

    def _create_table(
        self,
        table_name: str,
        schema_def: list,
        partition_field: Optional[str] = None,
        cluster_fields: Optional[List[str]] = None,
    ) -> None:
        from google.cloud import bigquery

        _type_map = {
            "STRING":    bigquery.enums.SqlTypeNames.STRING,
            "INTEGER":   bigquery.enums.SqlTypeNames.INT64,
            "INT64":     bigquery.enums.SqlTypeNames.INT64,
            "FLOAT64":   bigquery.enums.SqlTypeNames.FLOAT64,
            "FLOAT":     bigquery.enums.SqlTypeNames.FLOAT64,
            "BOOL":      bigquery.enums.SqlTypeNames.BOOL,
            "BOOLEAN":   bigquery.enums.SqlTypeNames.BOOL,
            "TIMESTAMP": bigquery.enums.SqlTypeNames.TIMESTAMP,
            "DATE":      bigquery.enums.SqlTypeNames.DATE,
        }

        schema = [
            bigquery.SchemaField(name, _type_map.get(dtype, dtype), mode=mode)
            for name, dtype, mode in schema_def
        ]

        table_ref = f"{self._project_id}.{self.DATASET}.{table_name}"
        table = bigquery.Table(table_ref, schema=schema)

        if partition_field:
            table.time_partitioning = bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field=partition_field,
            )
        if cluster_fields:
            table.clustering_fields = cluster_fields

        self._client.create_table(table, exists_ok=True)
        logger.info('BigQueryService: table %s ready', table_name)

    # ── row builders ──────────────────────────────────────────────────────────

    def build_hourly_row(
        self,
        engine,
        user_id: str,
        plant_species: str,
        tick_gap_hours: int,
        daily_regime_enabled: bool,
    ) -> Dict[str, Any]:
        """Build one BigQuery row from the engine's current state."""
        s = engine.state
        fluxes = engine.co2_fluxes or {}
        now = datetime.now(timezone.utc)

        # Collect tool actions applied at this specific hour
        current_hour = s.hour
        hour_actions = [
            {
                'tool_type': a['action'],
                'parameters': a.get('parameters', {}),
                'success': a.get('result', {}).get('success', True),
            }
            for a in engine.action_history
            if a.get('hour') == current_hour
        ]
        watering_L = sum(
            a.get('parameters', {}).get('volume_L', 0.0)
            for a in engine.action_history
            if a.get('hour') == current_hour and a.get('action') == 'watering'
        )
        co2_inj_g = sum(
            a.get('result', {}).get('changes', {}).get('co2_injected_g', 0.0)
            for a in engine.action_history
            if a.get('hour') == current_hour and a.get('action') == 'co2_control'
        )

        # Simulated timestamp — engine stores a datetime on state.timestamp
        sim_ts = s.timestamp
        if hasattr(sim_ts, 'isoformat'):
            sim_ts_str = sim_ts.isoformat()
            sim_date_str = sim_ts.strftime('%Y-%m-%d') if hasattr(sim_ts, 'strftime') else str(sim_ts)[:10]
        else:
            sim_ts_str = str(sim_ts)
            sim_date_str = str(sim_ts)[:10]

        stage_val = (
            s.phenological_stage.value
            if hasattr(s.phenological_stage, 'value')
            else str(s.phenological_stage)
        )

        return {
            # Identifiers
            'simulation_id':                engine.simulation_id,
            'user_id':                      user_id or '',
            'plant_species':                plant_species,
            'hour':                         s.hour,
            'day':                          s.hour // 24,
            'hour_of_day':                  s.hour % 24,
            'simulated_timestamp':          sim_ts_str,
            'tick_gap_hours':               tick_gap_hours,
            'recorded_at':                  now.isoformat(),
            'simulated_date':               sim_date_str,
            # Core plant state
            'is_alive':                     s.is_alive,
            'phenological_stage':           stage_val,
            'biomass_g':                    _safe_float(s.biomass),
            'leaf_biomass_g':               _safe_float(s.leaf_biomass),
            'stem_biomass_g':               _safe_float(s.stem_biomass),
            'root_biomass_g':               _safe_float(s.root_biomass),
            'leaf_area_m2':                 _safe_float(s.leaf_area),
            'thermal_time_Cdh':             _safe_float(s.thermal_time),
            'seed_reserves_g':              _safe_float(s.seed_reserves),
            'growth_saturation':            _safe_float(s.growth_saturation),
            'death_reason':                 s.death_reason or None,
            # Growth / carbon
            'photosynthesis_g_h':           _safe_float(s.photosynthesis),
            'respiration_g_h':              _safe_float(s.respiration),
            'growth_rate_g_h':              _safe_float(s.growth_rate),
            'co2_uptake_g_h':               _safe_float(s.co2_uptake),
            'RGR_per_h':                    _safe_float(s.RGR),
            'doubling_time_h':              _safe_float(s.doubling_time),
            # CO2 room dynamics
            'co2_ppm':                      _safe_float(s.CO2),
            'co2_production_ppm_h':         _safe_float(fluxes.get('production_ppm')),
            'co2_consumption_ppm_h':        _safe_float(fluxes.get('consumption_ppm')),
            'co2_injection_ppm_h':          _safe_float(fluxes.get('injection_ppm')),
            'co2_ventilation_ppm_h':        _safe_float(fluxes.get('ventilation_ppm')),
            'co2_leakage_ppm_h':            _safe_float(fluxes.get('leakage_ppm')),
            # Water balance
            'soil_water_pct':               _safe_float(s.soil_water),
            'ET_L_h':                       _safe_float(s.ET),
            'hours_without_adequate_water': _safe_float(s.hours_without_adequate_water),
            'last_watering_hour':           s.last_watering_hour,
            # Soil chemistry
            'soil_temp_C':                  _safe_float(s.soil_temp),
            'soil_N_ppm':                   _safe_float(s.soil_N),
            'soil_P_ppm':                   _safe_float(s.soil_P),
            'soil_K_ppm':                   _safe_float(s.soil_K),
            'soil_EC_mS_cm':                _safe_float(s.soil_EC),
            'soil_pH':                      _safe_float(s.soil_pH),
            # Environment
            'air_temp_C':                   _safe_float(s.air_temp),
            'relative_humidity_pct':        _safe_float(s.relative_humidity),
            'VPD_kPa':                      _safe_float(s.VPD),
            'light_PAR_umol_m2_s':          _safe_float(s.light_PAR),
            # Stress
            'water_stress':                 _safe_float(s.water_stress),
            'temp_stress':                  _safe_float(s.temp_stress),
            'nutrient_stress':              _safe_float(s.nutrient_stress),
            'cumulative_damage_pct':        _safe_float(s.cumulative_damage),
            'accumulated_water_stress':     _safe_float(s.accumulated_water_stress),
            # Tool actions
            'actions_applied':              json.dumps(hour_actions) if hour_actions else None,
            'watering_applied_L':           _safe_float(watering_L),
            'co2_injected_g':               _safe_float(co2_inj_g),
            # Config
            'pot_volume_L':                 _safe_float(s.pot_volume),
            'room_volume_m3':               _safe_float(s.room_volume),
            'daily_regime_enabled':         daily_regime_enabled,
        }

    def build_run_row(
        self,
        engine,
        user_id: str,
        plant_species: str,
        tick_gap_hours: int,
        daily_regime_enabled: bool,
        started_at: str,
    ) -> Dict[str, Any]:
        """Build one summary row for the simulation_runs table."""
        s = engine.state
        stage_val = (
            s.phenological_stage.value
            if hasattr(s.phenological_stage, 'value')
            else str(s.phenological_stage)
        )
        return {
            'simulation_id':          engine.simulation_id,
            'user_id':                user_id or '',
            'plant_species':          plant_species,
            'started_at':             started_at,
            'ended_at':               datetime.now(timezone.utc).isoformat(),
            'total_hours':            s.hour,
            'total_days':             _safe_float(s.hour / 24),
            'final_biomass_g':        _safe_float(s.biomass),
            'final_stage':            stage_val,
            'is_alive':               s.is_alive,
            'death_reason':           s.death_reason or None,
            'cumulative_damage_pct':  _safe_float(s.cumulative_damage),
            'total_water_supplied_L': _safe_float(engine.total_water_supplied_L),
            'water_applications':     engine.water_applications,
            'total_co2_injected_g':   _safe_float(engine.total_co2_injected_g),
            'co2_injections':         engine.co2_injections,
            'tick_gap_hours':         tick_gap_hours,
            'daily_regime_enabled':   daily_regime_enabled,
            'total_actions':          len(engine.action_history),
        }

    # ── hook factory ──────────────────────────────────────────────────────────

    def make_hourly_hook(
        self,
        user_id: str,
        plant_species: str,
        tick_gap_hours: int,
        daily_regime_enabled: bool,
    ):
        """
        Return a post-step hook callable that logs one row per simulated hour.

        Register with: engine.register_post_step_hook(bq.make_hourly_hook(...))
        """
        def _hook(engine) -> None:
            try:
                row = self.build_hourly_row(
                    engine=engine,
                    user_id=user_id,
                    plant_species=plant_species,
                    tick_gap_hours=tick_gap_hours,
                    daily_regime_enabled=daily_regime_enabled,
                )
                self.log_hourly_row(row)
            except Exception as exc:
                logger.warning('BigQueryService hourly hook error: %s', exc)

        return _hook

    # ── public API ────────────────────────────────────────────────────────────

    def log_hourly_row(self, row: Dict[str, Any]) -> None:
        """Buffer one hourly row; auto-flush when buffer is full."""
        self._buffer_hourly.append(row)
        if len(self._buffer_hourly) >= self.BUFFER_SIZE:
            self._flush_hourly()

    def log_run_row(self, row: Dict[str, Any]) -> None:
        """Buffer a run summary row and immediately flush it."""
        self._buffer_runs.append(row)
        self._flush_runs()

    def flush_all(self) -> None:
        """Flush all pending rows to BigQuery (call at simulation end)."""
        self._flush_hourly()
        self._flush_runs()

    # ── internal flushes ──────────────────────────────────────────────────────

    def _flush_hourly(self) -> None:
        if not self._buffer_hourly:
            return
        rows, self._buffer_hourly = self._buffer_hourly[:], []
        self._insert(self.TABLE_HOURLY, rows)

    def _flush_runs(self) -> None:
        if not self._buffer_runs:
            return
        rows, self._buffer_runs = self._buffer_runs[:], []
        self._insert(self.TABLE_RUNS, rows)

    def _insert(self, table_name: str, rows: List[Dict[str, Any]]) -> None:
        if not self._connected or not self._client:
            logger.debug('BigQueryService: not connected — discarding %d rows', len(rows))
            return
        
        table_ref = f"{self._project_id}.{self.DATASET}.{table_name}"
        
        try:
            job = self._client.load_table_from_json(rows, table_ref)
            job.result()  # ждём завершения
            
            # 🔍 Проверяем результат задачи
            if job.errors:
                logger.error('❌ BigQuery load errors (%s): %s', table_name, job.errors)
            elif job.output_rows is not None:
                logger.info('✅ BigQuery: записано %d строк в %s (job ID: %s)', 
                        job.output_rows, table_name, job.job_id)
            else:
                logger.warning('⚠️ BigQuery: job завершён, но output_rows неизвестен')
                
        except Exception as exc:
            logger.error('❌ BigQueryService insert failed (%s): %s', table_name, exc)
            # 🔍 Выведем детали исключения
            if hasattr(exc, 'errors'):
                logger.error('Детали ошибки: %s', exc.errors)
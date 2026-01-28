"""
BigQuery Logging Service
Logs simulation data to Google BigQuery for analytics and monitoring

Tables:
- simulation_states: Hourly state snapshots
- simulation_events: Tool actions and events
- simulation_metrics: Aggregated metrics
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)


class BigQueryService:
    """
    BigQuery logging service for plant simulation data

    Logs simulation data to BigQuery when configured.
    Gracefully degrades to local logging when BigQuery is not available.
    """

    # Table schemas for reference
    SCHEMA_STATES = {
        'simulation_id': 'STRING',
        'plant_id': 'STRING',
        'timestamp': 'TIMESTAMP',
        'hour': 'INTEGER',
        'biomass': 'FLOAT',
        'leaf_area': 'FLOAT',
        'is_alive': 'BOOLEAN',
        'cumulative_damage': 'FLOAT',
        'phenological_stage': 'STRING',
        'soil_water': 'FLOAT',
        'soil_temp': 'FLOAT',
        'soil_N': 'FLOAT',
        'soil_P': 'FLOAT',
        'soil_K': 'FLOAT',
        'soil_EC': 'FLOAT',
        'air_temp': 'FLOAT',
        'relative_humidity': 'FLOAT',
        'VPD': 'FLOAT',
        'light_PAR': 'FLOAT',
        'CO2': 'FLOAT',
        'water_stress': 'FLOAT',
        'temp_stress': 'FLOAT',
        'nutrient_stress': 'FLOAT',
        'ET': 'FLOAT',
        'photosynthesis': 'FLOAT',
        'respiration': 'FLOAT',
        'growth_rate': 'FLOAT',
        'co2_production_ppm': 'FLOAT',
        'co2_consumption_ppm': 'FLOAT',
        'co2_injection_ppm': 'FLOAT',
    }

    SCHEMA_EVENTS = {
        'simulation_id': 'STRING',
        'plant_id': 'STRING',
        'timestamp': 'TIMESTAMP',
        'hour': 'INTEGER',
        'event_type': 'STRING',  # 'tool_action', 'stage_change', 'death', etc.
        'tool_type': 'STRING',
        'action_id': 'STRING',
        'parameters': 'JSON',
        'result_success': 'BOOLEAN',
        'result_message': 'STRING',
        'changes': 'JSON',
    }

    SCHEMA_METRICS = {
        'simulation_id': 'STRING',
        'plant_id': 'STRING',
        'timestamp': 'TIMESTAMP',
        'metric_name': 'STRING',
        'metric_value': 'FLOAT',
        'metric_unit': 'STRING',
        'aggregation_period': 'STRING',  # 'hourly', 'daily', 'total'
    }

    def __init__(
        self,
        project_id: Optional[str] = None,
        dataset_id: str = "plant_simulation",
        credentials_path: Optional[str] = None,
        buffer_size: int = 100,
        enabled: bool = True
    ):
        """
        Initialize BigQuery service

        Args:
            project_id: GCP project ID (None = auto-detect or disabled)
            dataset_id: BigQuery dataset name
            credentials_path: Path to service account JSON (None = use default)
            buffer_size: Number of records to buffer before flush
            enabled: Whether BigQuery logging is enabled
        """
        self.project_id = project_id
        self.dataset_id = dataset_id
        self.credentials_path = credentials_path
        self.buffer_size = buffer_size
        self.enabled = enabled

        self.client = None
        self.connected = False

        # Buffers for batch inserts
        self._state_buffer: List[Dict[str, Any]] = []
        self._event_buffer: List[Dict[str, Any]] = []
        self._metric_buffer: List[Dict[str, Any]] = []

        # Local fallback storage
        self._local_log: List[Dict[str, Any]] = []

        if enabled:
            self._connect()

    def _connect(self) -> bool:
        """
        Attempt to connect to BigQuery

        Returns:
            True if connected, False otherwise
        """
        if not self.enabled:
            return False

        try:
            from google.cloud import bigquery

            if self.credentials_path:
                self.client = bigquery.Client.from_service_account_json(
                    self.credentials_path,
                    project=self.project_id
                )
            else:
                self.client = bigquery.Client(project=self.project_id)

            self.connected = True
            logger.info(f"Connected to BigQuery project: {self.project_id}")
            return True

        except ImportError:
            logger.warning("google-cloud-bigquery not installed. Using local logging.")
            self.connected = False
            return False

        except Exception as e:
            logger.warning(f"Failed to connect to BigQuery: {e}. Using local logging.")
            self.connected = False
            return False

    def log_state(
        self,
        simulation_id: str,
        plant_id: str,
        state_dict: Dict[str, Any],
        co2_fluxes: Optional[Dict[str, float]] = None
    ) -> bool:
        """
        Log a simulation state snapshot

        Args:
            simulation_id: Unique simulation identifier
            plant_id: Unique plant identifier
            state_dict: PlantState as dictionary
            co2_fluxes: CO2 flux data from engine

        Returns:
            True if logged successfully
        """
        record = {
            'simulation_id': simulation_id,
            'plant_id': plant_id,
            'timestamp': state_dict.get('timestamp', datetime.now().isoformat()),
            'hour': state_dict.get('hour', 0),
            'biomass': state_dict.get('biomass', 0),
            'leaf_area': state_dict.get('leaf_area', 0),
            'is_alive': state_dict.get('is_alive', True),
            'cumulative_damage': state_dict.get('cumulative_damage', 0),
            'phenological_stage': state_dict.get('phenological_stage', 'seedling'),
            'soil_water': state_dict.get('soil_water', 0),
            'soil_temp': state_dict.get('soil_temp', 0),
            'soil_N': state_dict.get('soil_N', 0),
            'soil_P': state_dict.get('soil_P', 0),
            'soil_K': state_dict.get('soil_K', 0),
            'soil_EC': state_dict.get('soil_EC', 0),
            'air_temp': state_dict.get('air_temp', 0),
            'relative_humidity': state_dict.get('relative_humidity', 0),
            'VPD': state_dict.get('VPD', 0),
            'light_PAR': state_dict.get('light_PAR', 0),
            'CO2': state_dict.get('CO2', 400),
            'water_stress': state_dict.get('water_stress', 0),
            'temp_stress': state_dict.get('temp_stress', 0),
            'nutrient_stress': state_dict.get('nutrient_stress', 0),
            'ET': state_dict.get('ET', 0),
            'photosynthesis': state_dict.get('photosynthesis', 0),
            'respiration': state_dict.get('respiration', 0),
            'growth_rate': state_dict.get('growth_rate', 0),
        }

        # Add CO2 flux data if available
        if co2_fluxes:
            record['co2_production_ppm'] = co2_fluxes.get('production_ppm', 0)
            record['co2_consumption_ppm'] = co2_fluxes.get('consumption_ppm', 0)
            record['co2_injection_ppm'] = co2_fluxes.get('injection_ppm', 0)

        self._state_buffer.append(record)

        if len(self._state_buffer) >= self.buffer_size:
            return self._flush_states()

        return True

    def log_event(
        self,
        simulation_id: str,
        plant_id: str,
        hour: int,
        event_type: str,
        tool_type: Optional[str] = None,
        action_id: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        success: bool = True,
        message: str = "",
        changes: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Log a simulation event (tool action, stage change, etc.)

        Args:
            simulation_id: Unique simulation identifier
            plant_id: Unique plant identifier
            hour: Simulation hour
            event_type: Type of event
            tool_type: Tool type if applicable
            action_id: Action ID if applicable
            parameters: Action parameters
            success: Whether action succeeded
            message: Result message
            changes: State changes from action

        Returns:
            True if logged successfully
        """
        record = {
            'simulation_id': simulation_id,
            'plant_id': plant_id,
            'timestamp': datetime.now().isoformat(),
            'hour': hour,
            'event_type': event_type,
            'tool_type': tool_type,
            'action_id': action_id,
            'parameters': json.dumps(parameters) if parameters else None,
            'result_success': success,
            'result_message': message,
            'changes': json.dumps(changes) if changes else None,
        }

        self._event_buffer.append(record)

        if len(self._event_buffer) >= self.buffer_size:
            return self._flush_events()

        return True

    def log_metric(
        self,
        simulation_id: str,
        plant_id: str,
        metric_name: str,
        metric_value: float,
        metric_unit: str = "",
        aggregation_period: str = "hourly"
    ) -> bool:
        """
        Log a custom metric

        Args:
            simulation_id: Unique simulation identifier
            plant_id: Unique plant identifier
            metric_name: Name of the metric
            metric_value: Value of the metric
            metric_unit: Unit of measurement
            aggregation_period: Period of aggregation

        Returns:
            True if logged successfully
        """
        record = {
            'simulation_id': simulation_id,
            'plant_id': plant_id,
            'timestamp': datetime.now().isoformat(),
            'metric_name': metric_name,
            'metric_value': metric_value,
            'metric_unit': metric_unit,
            'aggregation_period': aggregation_period,
        }

        self._metric_buffer.append(record)

        if len(self._metric_buffer) >= self.buffer_size:
            return self._flush_metrics()

        return True

    def _flush_states(self) -> bool:
        """Flush state buffer to BigQuery"""
        if not self._state_buffer:
            return True

        success = self._insert_rows("simulation_states", self._state_buffer)
        if success:
            self._state_buffer = []
        return success

    def _flush_events(self) -> bool:
        """Flush event buffer to BigQuery"""
        if not self._event_buffer:
            return True

        success = self._insert_rows("simulation_events", self._event_buffer)
        if success:
            self._event_buffer = []
        return success

    def _flush_metrics(self) -> bool:
        """Flush metric buffer to BigQuery"""
        if not self._metric_buffer:
            return True

        success = self._insert_rows("simulation_metrics", self._metric_buffer)
        if success:
            self._metric_buffer = []
        return success

    def flush_all(self) -> bool:
        """Flush all buffers to BigQuery"""
        success = True
        success = self._flush_states() and success
        success = self._flush_events() and success
        success = self._flush_metrics() and success
        return success

    def _insert_rows(self, table_name: str, rows: List[Dict[str, Any]]) -> bool:
        """
        Insert rows into BigQuery table

        Args:
            table_name: Name of the table
            rows: List of row dictionaries

        Returns:
            True if successful
        """
        if not rows:
            return True

        # Store locally regardless of BigQuery status
        for row in rows:
            self._local_log.append({
                'table': table_name,
                'data': row
            })

        if not self.connected or not self.client:
            logger.debug(f"BigQuery not connected. Stored {len(rows)} rows locally.")
            return True

        try:
            table_ref = f"{self.project_id}.{self.dataset_id}.{table_name}"
            errors = self.client.insert_rows_json(table_ref, rows)

            if errors:
                logger.error(f"BigQuery insert errors: {errors}")
                return False

            logger.debug(f"Inserted {len(rows)} rows to {table_name}")
            return True

        except Exception as e:
            logger.error(f"BigQuery insert failed: {e}")
            return False

    def get_local_log(self) -> List[Dict[str, Any]]:
        """Get local log entries (for debugging or fallback)"""
        return self._local_log

    def export_local_log(self, filepath: str) -> bool:
        """
        Export local log to JSON file

        Args:
            filepath: Path to output file

        Returns:
            True if successful
        """
        try:
            with open(filepath, 'w') as f:
                json.dump(self._local_log, f, indent=2, default=str)
            logger.info(f"Exported {len(self._local_log)} log entries to {filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to export log: {e}")
            return False

    def create_tables(self) -> bool:
        """
        Create BigQuery tables if they don't exist

        Returns:
            True if successful
        """
        if not self.connected or not self.client:
            logger.warning("Cannot create tables: BigQuery not connected")
            return False

        try:
            from google.cloud import bigquery

            # Create dataset if it doesn't exist
            dataset_ref = f"{self.project_id}.{self.dataset_id}"
            dataset = bigquery.Dataset(dataset_ref)
            dataset.location = "US"

            try:
                self.client.create_dataset(dataset, exists_ok=True)
                logger.info(f"Dataset {self.dataset_id} ready")
            except Exception as e:
                logger.warning(f"Dataset creation: {e}")

            # Create tables
            tables = [
                ("simulation_states", self.SCHEMA_STATES),
                ("simulation_events", self.SCHEMA_EVENTS),
                ("simulation_metrics", self.SCHEMA_METRICS),
            ]

            for table_name, schema_dict in tables:
                schema = [
                    bigquery.SchemaField(name, dtype)
                    for name, dtype in schema_dict.items()
                ]

                table_ref = f"{self.project_id}.{self.dataset_id}.{table_name}"
                table = bigquery.Table(table_ref, schema=schema)

                try:
                    self.client.create_table(table, exists_ok=True)
                    logger.info(f"Table {table_name} ready")
                except Exception as e:
                    logger.warning(f"Table {table_name} creation: {e}")

            return True

        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
            return False

    def close(self) -> None:
        """Close connection and flush remaining data"""
        self.flush_all()
        if self.client:
            self.client.close()
            self.client = None
        self.connected = False

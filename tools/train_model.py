"""
BigQuery Model Training Data Pipeline

Creates and populates training dataset tables from simulation data.
Transforms hourly simulation logs into structured ML-ready format.

New Table Schema (training_data):
  - plant_type (STRING): plant_species (lettuce_butterhead, tomato_standard, basil)
  - phenological_stage (INT): ordinal encoding (1-6)
  - estimated_biomass (FLOAT): biomass_g
  - health_confidence (FLOAT): derived from cumulative_damage_pct (1.0 - damage)
  - last_watering_days (INT): converted from last_watering_hour
  - water_stress (FLOAT): 0-1 stress indicator
  - nutrient_stress (FLOAT): 0-1 stress indicator
  - temperature_stress (FLOAT): temp_stress from simulation
  - cumulative_damage_pct (FLOAT): plant health damage

- plant_id (STRING): simulation_id or unique plant identifier
- timestamp (TIMESTAMP): simulated_timestamp
- plant_age_days (INT): day from simulation
 - indoor_flag (BOOL): defaulted to TRUE for controlled environment





FIELDS AVAILABLE FROM BIGQUERY:
  ✓ plant_species, biomass_g, phenological_stage (STRING)
  ✓ water_stress, nutrient_stress, temp_stress (FLOAT)
  ✓ day, last_watering_hour, is_alive
  ✓ simulated_timestamp, simulation_id

FIELDS NOT FOUND IN BIGQUERY (using defaults/derivations):
  ✗ health_confidence: DERIVED from cumulative_damage_pct (1.0 - damage % clipped to 0-1)
  ✗ indoor_flag: HARDCODED to TRUE (controlled greenhouse environment)
  ⚠ plant_id: using simulation_id as unique identifier
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import pandas as pd
import numpy as np

# Load .env file at startup
try:
    from dotenv import load_dotenv
    # Load from project root .env
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path, override=False)
except ImportError:
    pass  # python-dotenv not required

logger = logging.getLogger(__name__)

# Phenological stage mapping: STRING → INT ordinal
PHENOLOGICAL_STAGES = {
    'seed': 1,
    'seedling': 2,
    'vegetative': 3,
    'flowering': 4,
    'fruiting': 5,
    'mature': 6,
    'senescent': 7,
}


class BigQueryTrainingDataBuilder:
    """
    Creates and populates training datasets in BigQuery.
    
    Transforms simulation hourly logs into ML-ready training format.
    """
    
    DATASET = "plant_simulation"
    TABLE_TRAINING_DATA = "training_data"
    TABLE_HOURLY = "simulation_hourly_logs"
    TABLE_RUNS = "simulation_runs"
    
    # Training data schema
    _SCHEMA_TRAINING = [
        ("plant_id",                 "STRING",    "NULLABLE"),      # simulation_id
        ("timestamp",                "TIMESTAMP", "NULLABLE"),      # simulated_timestamp
        ("plant_type",               "STRING",    "NULLABLE"),      # plant_species
        ("phenological_stage",       "INTEGER",   "NULLABLE"),      # ordinal 1-7
        ("estimated_biomass",        "FLOAT64",   "NULLABLE"),      # biomass_g
        ("health_confidence",        "FLOAT64",   "NULLABLE"),      # derived: 1.0=alive, 0.0=dead
        ("plant_age_days",           "INTEGER",   "NULLABLE"),      # day from simulation
        ("last_watering_days",       "FLOAT64",   "NULLABLE"),      # hours_from_last_watering / 24
        ("indoor_flag",              "BOOL",      "NULLABLE"),      # TRUE for controlled environment
        ("water_stress",             "FLOAT64",   "NULLABLE"),      # 0-1 stress level
        ("nutrient_stress",          "FLOAT64",   "NULLABLE"),      # 0-1 stress level
        ("temperature_stress",       "FLOAT64",   "NULLABLE"),      # 0-1 stress level
        ("cumulative_damage_pct",    "FLOAT64",   "NULLABLE"),      # plant health damage
        # Additional features for model input
        ("air_temp_C",               "FLOAT64",   "NULLABLE"),
        ("relative_humidity_pct",    "FLOAT64",   "NULLABLE"),
        ("light_PAR_umol_m2_s",      "FLOAT64",   "NULLABLE"),
        ("soil_water_pct",           "FLOAT64",   "NULLABLE"),
        ("leaf_area_m2",             "FLOAT64",   "NULLABLE"),
        ("photosynthesis_g_h",       "FLOAT64",   "NULLABLE"),
        ("respiration_g_h",          "FLOAT64",   "NULLABLE"),
        ("growth_rate_g_h",          "FLOAT64",   "NULLABLE"),
        ("recorded_at",              "TIMESTAMP", "NULLABLE"),      # when data was recorded
        ("simulation_id",            "STRING",    "NULLABLE"),      # original simulation reference
    ]
    
    def __init__(self):
        """Initialize BigQuery client."""
        self._client = None
        self._connected = False
        self._project_id: Optional[str] = None
        self._try_connect()
    
    def _try_connect(self) -> None:
        """Establish connection to BigQuery."""
        try:
            from google.cloud import bigquery
            from google.oauth2 import service_account
            
            self._project_id = os.getenv('FIREBASE_PROJECT_ID') or os.getenv('BIGQUERY_PROJECT_ID')
            creds_path = os.getenv('FIREBASE_CREDENTIALS_PATH')
            
            if not self._project_id:
                logger.warning('BigQueryTrainingDataBuilder: FIREBASE_PROJECT_ID not set')
                return
            
            # Resolve credentials path relative to project root if relative
            if creds_path:
                creds_path = Path(creds_path)
                if not creds_path.is_absolute():
                    # Make relative to project root
                    project_root = Path(__file__).parent.parent
                    creds_path = project_root / creds_path
            
            if creds_path and creds_path.exists():
                logger.info('Loading credentials from: %s', creds_path)
                creds = service_account.Credentials.from_service_account_file(
                    str(creds_path),
                    scopes=["https://www.googleapis.com/auth/bigquery"],
                )
                self._client = bigquery.Client(project=self._project_id, credentials=creds)
            else:
                logger.info('No credentials file found, using Application Default Credentials')
                self._client = bigquery.Client(project=self._project_id)
            
            self._connected = True
            logger.info('BigQueryTrainingDataBuilder: connected to %s', self._project_id)
            
        except ImportError:
            logger.warning('BigQueryTrainingDataBuilder: google-cloud-bigquery not installed')
        except Exception as exc:
            logger.error('BigQueryTrainingDataBuilder: connection failed (%s)', exc)
    
    @property
    def connected(self) -> bool:
        """Check if connected to BigQuery."""
        return self._connected
    
    # ── Table management ──────────────────────────────────────────────────────
    
    def create_training_table(self) -> bool:
        """
        Create training_data table in BigQuery if it doesn't exist.
        
        Returns:
            True if table created/exists, False if error
        """
        if not self._connected:
            logger.error('BigQueryTrainingDataBuilder: not connected')
            return False
        
        try:
            from google.cloud import bigquery
            
            # Ensure dataset exists
            dataset_ref = f"{self._project_id}.{self.DATASET}"
            dataset = bigquery.Dataset(dataset_ref)
            dataset.location = "US"
            self._client.create_dataset(dataset, exists_ok=True)
            
            # Create training table
            _type_map = {
                "STRING":    bigquery.enums.SqlTypeNames.STRING,
                "INTEGER":   bigquery.enums.SqlTypeNames.INT64,
                "FLOAT64":   bigquery.enums.SqlTypeNames.FLOAT64,
                "BOOL":      bigquery.enums.SqlTypeNames.BOOL,
                "TIMESTAMP": bigquery.enums.SqlTypeNames.TIMESTAMP,
            }
            
            schema = [
                bigquery.SchemaField(name, _type_map.get(dtype, dtype), mode=mode)
                for name, dtype, mode in self._SCHEMA_TRAINING
            ]
            
            table_ref = f"{self._project_id}.{self.DATASET}.{self.TABLE_TRAINING_DATA}"
            table = bigquery.Table(table_ref, schema=schema)
            
            # Partition by timestamp for efficient queries
            table.time_partitioning = bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field="timestamp",
            )
            
            # Cluster for better query performance
            table.clustering_fields = ["plant_type", "plant_id"]
            
            self._client.create_table(table, exists_ok=True)
            logger.info('✅ Training table %s ready', self.TABLE_TRAINING_DATA)
            return True
            
        except Exception as exc:
            logger.error('Failed to create training table: %s', exc)
            return False
    
    # ── Data transformation & population ──────────────────────────────────────
    
    def build_training_data_from_hourly(
        self,
        plant_species: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Extract hourly logs and transform into training format.
        
        Args:
            plant_species: Optional filter by species
            date_from: Start date (UTC)
            date_to: End date (UTC)
            limit: Maximum rows
        
        Returns:
            DataFrame in training format
        """
        if not self._connected:
            logger.error('Not connected to BigQuery')
            return pd.DataFrame()
        
        # Build WHERE clause
        where_clauses = []
        if plant_species:
            where_clauses.append(f"plant_species = '{plant_species}'")
        if date_from:
            where_clauses.append(f"simulated_date >= '{date_from.strftime('%Y-%m-%d')}'")
        if date_to:
            where_clauses.append(f"simulated_date <= '{date_to.strftime('%Y-%m-%d')}'")
        
        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
        limit_clause = f"LIMIT {limit}" if limit else ""
        
        query = f"""
        SELECT 
            simulation_id,
            user_id,
            plant_species,
            phenological_stage,
            simulated_timestamp,
            day,
            hour,
            biomass_g,
            is_alive,
            water_stress,
            nutrient_stress,
            temp_stress,
            cumulative_damage_pct,
            last_watering_hour,
            hour_of_day,
            air_temp_C,
            relative_humidity_pct,
            light_PAR_umol_m2_s,
            soil_water_pct,
            leaf_area_m2,
            photosynthesis_g_h,
            respiration_g_h,
            growth_rate_g_h,
            recorded_at
        FROM `{self._project_id}.{self.DATASET}.{self.TABLE_HOURLY}`
        WHERE {where_clause}
        ORDER BY simulation_id, day, hour
        {limit_clause}
        """
        
        try:
            logger.info(f"QUERY IS:\n{query}")
            df = self._client.query(query).to_dataframe()
            logger.info('Extracted %d hourly records', len(df))
            
            # Transform to training format
            df = self._transform_to_training_format(df)
            return df
            
        except Exception as exc:
            logger.error('Failed to extract hourly logs: %s', exc)
            return pd.DataFrame()
    
    @staticmethod
    def _transform_to_training_format(df: pd.DataFrame) -> pd.DataFrame:
        """
        Transform raw hourly data into training format.
        
        Maps columns and creates derived features.
        """
        df = df.copy()
        
        # 1. Rename columns
        df.rename(columns={
            'simulation_id': 'plant_id',
            'simulated_timestamp': 'timestamp',
            'plant_species': 'plant_type',
            'biomass_g': 'estimated_biomass',
            'temp_stress': 'temperature_stress',
        }, inplace=True)
        
        # 2. Encode phenological_stage to ordinal
        if 'phenological_stage' in df.columns:
            df['phenological_stage'] = df['phenological_stage'].map(PHENOLOGICAL_STAGES)
            # Fill unknown stages with vegetative (3)
            df['phenological_stage'] = df['phenological_stage'].fillna(3)
            df['phenological_stage'] = df['phenological_stage'].astype(int)
        
        # 3. health_confidence: derived from cumulative_damage_pct
        if 'cumulative_damage_pct' in df.columns:
            df['health_confidence'] = (1.0 - df['cumulative_damage_pct']).clip(0, 1)  # 1.0 - damage
        else:
            df['health_confidence'] = 1.0  # default to healthy
        
        # 4. plant_age_days: from day column
        if 'day' in df.columns:
            df['plant_age_days'] = df['day'].astype(int)
        else:
            df['plant_age_days'] = 0
        
        # 5. last_watering_days: convert hours to days
        if 'last_watering_hour' in df.columns:
            df['last_watering_days'] = (df['last_watering_hour'] / 24.0).round(2)
        else:
            df['last_watering_days'] = None
        
        # 6. indoor_flag: hardcoded to TRUE (controlled greenhouse)
        df['indoor_flag'] = True
        
        # 7. Reorder columns to match schema
        training_cols = [
            'plant_id', 'timestamp', 'plant_type', 'phenological_stage',
            'estimated_biomass', 'health_confidence', 'plant_age_days',
            'last_watering_days', 'indoor_flag', 'water_stress',
            'nutrient_stress', 'temperature_stress', 'cumulative_damage_pct',
            'air_temp_C', 'relative_humidity_pct', 'light_PAR_umol_m2_s',
            'soil_water_pct', 'leaf_area_m2', 'photosynthesis_g_h',
            'respiration_g_h', 'growth_rate_g_h', 'recorded_at'
        ]
        
        # Keep only columns that exist
        available_cols = [col for col in training_cols if col in df.columns]
        df = df[available_cols]
        
        logger.info('✓ Transformed %d rows to training format', len(df))
        return df
    
    def populate_training_table(
        self,
        df: pd.DataFrame,
        replace: bool = False,
    ) -> bool:
        """
        Load training data into BigQuery.
        
        Args:
            df: DataFrame in training format
            replace: If True, replace existing data; if False, append
        
        Returns:
            True if successful
        """
        if not self._connected:
            logger.error('Not connected to BigQuery')
            return False
        
        if df.empty:
            logger.warning('Empty DataFrame, skipping load')
            return False
        
        table_ref = f"{self._project_id}.{self.DATASET}.{self.TABLE_TRAINING_DATA}"
        
        try:
            from google.cloud import bigquery as _bq
            job_config = _bq.LoadJobConfig()
            if replace:
                job_config.write_disposition = _bq.WriteDisposition.WRITE_TRUNCATE
            else:
                job_config.write_disposition = _bq.WriteDisposition.WRITE_APPEND

            job = self._client.load_table_from_dataframe(df, table_ref, job_config=job_config)
            job.result()  # Wait for completion
            
            logger.info('✅ Loaded %d rows into %s', len(df), self.TABLE_TRAINING_DATA)
            return True
            
        except Exception as exc:
            logger.error('Failed to populate training table: %s', exc)
            return False
    
    def build_and_populate_training_table(
        self,
        plant_species: Optional[str] = None,
        days_back: int = 30,
        replace: bool = False,
    ) -> Tuple[bool, int]:
        """
        Complete pipeline: extract, transform, load training data.
        
        Args:
            plant_species: Optional species filter
            days_back: Days of history to include
            replace: If True, replace existing data
        
        Returns:
            Tuple of (success, row_count)
        """
        # Create table if needed
        if not self.create_training_table():
            return False, 0
        
        # Extract and transform
        date_to = datetime.now(timezone.utc)
        date_from = date_to - timedelta(days=days_back)
        
        df = self.build_training_data_from_hourly(
            plant_species=plant_species,
            date_from=date_from,
            date_to=date_to,
            limit=100000,  # Reasonable limit for training data
        )
        
        if df.empty:
            logger.warning('No training data extracted')
            return False, 0
        
        # Load to BigQuery
        success = self.populate_training_table(df, replace=replace)
        return success, len(df)
    
    def query_training_data(
        self,
        plant_type: Optional[str] = None,
        phenological_range: Optional[Tuple[int, int]] = None,
        health_confidence_min: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Query training data with optional filters.
        
        Args:
            plant_type: Filter by plant type
            phenological_range: Tuple (min_stage, max_stage)
            health_confidence_min: Minimum health confidence
            limit: Max rows to return
        
        Returns:
            DataFrame with filtered training data
        """
        if not self._connected:
            logger.error('Not connected to BigQuery')
            return pd.DataFrame()
        
        where_clauses = []
        
        if plant_type:
            where_clauses.append(f"plant_type = '{plant_type}'")
        if phenological_range:
            min_s, max_s = phenological_range
            where_clauses.append(f"phenological_stage BETWEEN {min_s} AND {max_s}")
        if health_confidence_min is not None:
            where_clauses.append(f"health_confidence >= {health_confidence_min}")
        
        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
        limit_clause = f"LIMIT {limit}" if limit else ""
        
        query = f"""
        SELECT *
        FROM `{self._project_id}.{self.DATASET}.{self.TABLE_TRAINING_DATA}`
        WHERE {where_clause}
        ORDER BY timestamp DESC
        {limit_clause}
        """
        
        try:
            df = self._client.query(query).to_dataframe()
            logger.info('Queried %d training records', len(df))
            return df
        except Exception as exc:
            logger.error('Failed to query training data: %s', exc)
            return pd.DataFrame()


# ── Stress prediction utilities ────────────────────────────────────────────────

class StressPredictor:
    """
    Simple rule-based predictor for plant stress and tool recommendations.
    
    Takes training data and suggests corrective actions based on stress levels.
    """
    
    STRESS_THRESHOLDS = {
        'low': 0.3,
        'medium': 0.6,
        'high': 1.0,
    }
    
    @staticmethod
    def categorize_stress(stress_value: float) -> str:
        """Convert stress 0-1 to category: low, medium, high."""
        if stress_value < 0.3:
            return 'low'
        elif stress_value < 0.6:
            return 'medium'
        else:
            return 'high'
    
    @staticmethod
    def recommend_tools(
        water_stress: float,
        nutrient_stress: float,
        temperature_stress: float,
        air_temp_C: float,
        relative_humidity_pct: float,
        soil_water_pct: float,
    ) -> Dict[str, Any]:
        """
        Rule-based tool recommendations based on stress levels.
        
        Args:
            water_stress: 0-1 water stress indicator
            nutrient_stress: 0-1 nutrient stress indicator
            temperature_stress: 0-1 temperature stress indicator
            air_temp_C: Current air temperature
            relative_humidity_pct: Current humidity %
            soil_water_pct: Soil water content %
        
        Returns:
            Dict with recommended tools and parameters
        """
        recommendations = {
            'tools': [],
            'reasoning': [],
            'urgency': 'low',
        }
        
        # Water stress → Watering
        if water_stress > 0.5:
            if soil_water_pct < 40:
                recommendations['tools'].append({
                    'tool': 'watering',
                    'intensity': 'high' if water_stress > 0.7 else 'medium',
                    'target_soil_water_pct': 70,
                })
                recommendations['reasoning'].append(
                    f'Water stress {water_stress:.2f}, soil water {soil_water_pct:.1f}%'
                )
                if water_stress > 0.7:
                    recommendations['urgency'] = 'high'
        
        # Nutrient stress → Nutrient supply
        if nutrient_stress > 0.5:
            recommendations['tools'].append({
                'tool': 'nutrients',
                'intensity': 'high' if nutrient_stress > 0.7 else 'medium',
                'nutrient_boost': 'NPK' if nutrient_stress > 0.6 else 'N',
            })
            recommendations['reasoning'].append(
                f'Nutrient stress {nutrient_stress:.2f}'
            )
        
        # Temperature stress → HVAC/Lighting
        if temperature_stress > 0.5:
            if air_temp_C < 18:
                recommendations['tools'].append({
                    'tool': 'hvac',
                    'mode': 'heating',
                    'target_temp_C': 22,
                })
                recommendations['reasoning'].append(
                    f'Temperature stress {temperature_stress:.2f}, temp {air_temp_C:.1f}°C (too cold)'
                )
            elif air_temp_C > 30:
                recommendations['tools'].append({
                    'tool': 'hvac',
                    'mode': 'cooling',
                    'target_temp_C': 25,
                })
                recommendations['reasoning'].append(
                    f'Temperature stress {temperature_stress:.2f}, temp {air_temp_C:.1f}°C (too hot)'
                )
            
            # Humidity adjustment
            if relative_humidity_pct < 40:
                recommendations['tools'].append({
                    'tool': 'humidity',
                    'action': 'increase',
                    'target_pct': 60,
                })
        
        return recommendations


# ── Example usage functions ───────────────────────────────────────────────────

def example_create_and_populate_training_table(
    plant_species: Optional[str] = None,
    days_back: int = 7,
):
    """
    Example: Create and populate training data table.
    
    Args:
        plant_species: Optional species filter (tomato_standard, lettuce_butterhead, basil)
        days_back: Days of historical data to include
    """
    print("\n" + "="*70)
    print("CREATING & POPULATING TRAINING DATA TABLE")
    print("="*70)
    
    builder = BigQueryTrainingDataBuilder()
    if not builder.connected:
        print("❌ Failed to connect to BigQuery")
        return
    
    # Create table
    print("\n📋 Creating training_data table schema...")
    if not builder.create_training_table():
        print("❌ Failed to create table")
        return
    
    # Build and populate
    print(f"\n📥 Extracting {days_back} days of data...")
    success, row_count = builder.build_and_populate_training_table(
        plant_species=plant_species,
        days_back=days_back,
        replace=False,  # Append mode
    )
    
    if success:
        print(f"✅ Successfully loaded {row_count} training records")
    else:
        print("❌ Failed to populate training table")
    
    # Display sample
    if row_count > 0:
        print("\n📊 Querying sample data...")
        sample_df = builder.query_training_data(
            plant_type=plant_species,
            limit=5,
        )
        if not sample_df.empty:
            print(f"\nSample {len(sample_df)} rows:")
            print(sample_df[['plant_id', 'plant_type', 'phenological_stage', 
                           'estimated_biomass', 'water_stress', 'nutrient_stress']].to_string())


def example_query_and_analyze_training_data(plant_type: str = 'tomato_standard'):
    """
    Example: Query training data and analyze stress patterns.
    
    Args:
        plant_type: Plant species to analyze
    """
    print("\n" + "="*70)
    print("ANALYZING TRAINING DATA & STRESS PATTERNS")
    print("="*70)
    
    builder = BigQueryTrainingDataBuilder()
    if not builder.connected:
        print("❌ Failed to connect to BigQuery")
        return
    
    # Query all data for plant type
    print(f"\n📖 Querying {plant_type} training data...")
    df = builder.query_training_data(plant_type=plant_type, limit=10000)
    
    if df.empty:
        print(f"No training data found for {plant_type}")
        return
    
    print(f"✅ Retrieved {len(df)} records")
    
    # Analyze stress distribution
    print("\n📊 STRESS STATISTICS:")
    print("-" * 70)
    for stress_col in ['water_stress', 'nutrient_stress', 'temperature_stress']:
        if stress_col in df.columns:
            mean_val = df[stress_col].mean()
            max_val = df[stress_col].max()
            min_val = df[stress_col].min()
            print(f"\n{stress_col}:")
            print(f"  Mean: {mean_val:.3f} | Min: {min_val:.3f} | Max: {max_val:.3f}")
    
    # Analyze by phenological stage
    if 'phenological_stage' in df.columns:
        print("\n📈 BY PHENOLOGICAL STAGE:")
        print("-" * 70)
        stage_names = {v: k for k, v in PHENOLOGICAL_STAGES.items()}
        for stage_int in sorted(df['phenological_stage'].unique()):
            stage_name = stage_names.get(stage_int, f"stage_{stage_int}")
            stage_df = df[df['phenological_stage'] == stage_int]
            avg_stress = stage_df['water_stress'].mean()
            print(f"{stage_name:15}: avg_water_stress={avg_stress:.3f} ({len(stage_df)} records)")
    
    # Sample recommendations
    if len(df) > 0:
        print("\n💡 TOOL RECOMMENDATIONS (sample row):")
        print("-" * 70)
        sample_row = df.iloc[0]
        recommendations = StressPredictor.recommend_tools(
            water_stress=sample_row.get('water_stress', 0.0),
            nutrient_stress=sample_row.get('nutrient_stress', 0.0),
            temperature_stress=sample_row.get('temperature_stress', 0.0),
            air_temp_C=sample_row.get('air_temp_C', 22.0),
            relative_humidity_pct=sample_row.get('relative_humidity_pct', 60.0),
            soil_water_pct=sample_row.get('soil_water_pct', 60.0),
        )
        
        print(f"Urgency: {recommendations['urgency']}")
        print(f"Tools to apply: {len(recommendations['tools'])}")
        for tool in recommendations['tools']:
            print(f"  • {tool['tool']}: {tool}")
        for reason in recommendations['reasoning']:
            print(f"  → {reason}")


def example_data_quality_report():
    """
    Example: Check data quality and missing values.
    """
    print("\n" + "="*70)
    print("DATA QUALITY REPORT")
    print("="*70)
    
    builder = BigQueryTrainingDataBuilder()
    if not builder.connected:
        print("❌ Failed to connect to BigQuery")
        return
    
    print("\n🔍 Checking existing training_data table...")
    
    # Query all available data
    df = builder.query_training_data(limit=None)
    
    if df.empty:
        print("⚠️  No data in training_data table yet")
        print(f"\n📋 Expected schema columns:")
        for col_name, col_type, mode in builder._SCHEMA_TRAINING:
            print(f"  • {col_name}: {col_type}")
        return
    
    print(f"\n✅ Table has {len(df)} rows, {len(df.columns)} columns")
    
    print("\n📊 MISSING VALUES:")
    print("-" * 70)
    missing = df.isnull().sum()
    missing_pct = (missing / len(df) * 100).round(2)
    for col in df.columns:
        if missing[col] > 0:
            print(f"  {col}: {missing[col]} null ({missing_pct[col]}%)")
    
    if missing.sum() == 0:
        print("  ✓ No missing values detected")
    
    print("\n📝 COLUMN DATA TYPES:")
    print("-" * 70)
    print(df.dtypes.to_string())
    
    print("\n🎯 FIELDS MISSING FROM BIGQUERY (using defaults/derivations):")
    print("-" * 70)
    print("  ✗ health_confidence: DERIVED from cumulative_damage_pct (1.0 - damage, clipped 0-1)")
    print("  ✗ indoor_flag: HARDCODED to TRUE (controlled greenhouse environment)")
    print("  ⚠ plant_id: Using simulation_id as unique identifier")
    print("  ⚠ last_watering_days: Converted from last_watering_hour")


def print_schema_reference():
    """Print the training data schema for reference."""
    print("\n" + "="*70)
    print("TRAINING DATA SCHEMA REFERENCE")
    print("="*70)
    
    builder = BigQueryTrainingDataBuilder()
    
    print("\nTable: plant_simulation.training_data")
    print("-" * 70)
    
    # Group by category
    categories = {
        'Identifiers': ['plant_id', 'plant_type', 'timestamp', 'simulation_id'],
        'Plant Phenotype': ['phenological_stage', 'estimated_biomass', 'plant_age_days', 'leaf_area_m2'],
        'Health Indicators': ['health_confidence', 'cumulative_damage_pct'],
        'Stress Targets (0-1)': ['water_stress', 'nutrient_stress', 'temperature_stress'],
        'Water Management': ['last_watering_days', 'soil_water_pct'],
        'Environment': ['air_temp_C', 'relative_humidity_pct', 'light_PAR_umol_m2_s'],
        'Growth Metrics': ['photosynthesis_g_h', 'respiration_g_h', 'growth_rate_g_h'],
        'Metadata': ['indoor_flag', 'recorded_at'],
    }
    
    for category, cols in categories.items():
        print(f"\n{category}:")
        for col in cols:
            schema_entry = next((s for s in builder._SCHEMA_TRAINING if s[0] == col), None)
            if schema_entry:
                col_name, col_type, col_mode = schema_entry
                print(f"  • {col_name:<30} {col_type:10} ({col_mode})")


if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    )
    
    # Print schema reference
    print_schema_reference()
    
    # Example 1: Data quality check
    print("\n\n")
    example_data_quality_report()
    
    # Example 2: Create training table (if not exists)
    print("\n\n")
    example_create_and_populate_training_table(
        plant_species='tomato_standard',
        days_back=7,
    )
    
    # Example 3: Analyze training data
    print("\n\n")
    example_query_and_analyze_training_data(plant_type='tomato_standard')

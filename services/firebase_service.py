"""
Firebase Service
Handles state persistence to Firebase Firestore

Collections:
- simulations: Simulation metadata and current state
- simulation_history: Historical state snapshots
- plants: Plant profile configurations
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)


class FirebaseService:
    """
    Firebase Firestore integration for plant simulation state persistence

    Stores simulation state in real-time and enables resuming simulations.
    Gracefully degrades when Firebase is not configured.
    """

    def __init__(
        self,
        project_id: Optional[str] = None,
        credentials_path: Optional[str] = None,
        enabled: bool = True
    ):
        """
        Initialize Firebase service

        Args:
            project_id: Firebase project ID (None = auto-detect or disabled)
            credentials_path: Path to service account JSON (None = use default)
            enabled: Whether Firebase persistence is enabled
        """
        self.project_id = project_id
        self.credentials_path = credentials_path
        self.enabled = enabled

        self.db = None
        self.connected = False

        # Local cache for offline operation
        self._local_cache: Dict[str, Any] = {
            'simulations': {},
            'history': {},
            'plants': {}
        }

        if enabled:
            self._connect()

    def _connect(self) -> bool:
        """
        Attempt to connect to Firebase Firestore

        Returns:
            True if connected, False otherwise
        """
        if not self.enabled:
            return False

        try:
            import firebase_admin
            from firebase_admin import credentials, firestore

            # Check if already initialized
            try:
                app = firebase_admin.get_app()
            except ValueError:
                # Not initialized, initialize now
                if self.credentials_path:
                    cred = credentials.Certificate(self.credentials_path)
                    firebase_admin.initialize_app(cred, {
                        'projectId': self.project_id
                    })
                else:
                    # Try default credentials
                    firebase_admin.initialize_app()

            self.db = firestore.client()
            self.connected = True
            logger.info(f"Connected to Firebase project: {self.project_id or 'default'}")
            return True

        except ImportError:
            logger.warning("firebase-admin not installed. Using local cache.")
            self.connected = False
            return False

        except Exception as e:
            logger.warning(f"Failed to connect to Firebase: {e}. Using local cache.")
            self.connected = False
            return False

    # -------------------------------------------------------------------------
    # Simulation State Management
    # -------------------------------------------------------------------------

    def save_simulation(
        self,
        simulation_id: str,
        plant_id: str,
        state_dict: Dict[str, Any],
        profile_id: str,
        co2_fluxes: Optional[Dict[str, float]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Save current simulation state

        Args:
            simulation_id: Unique simulation identifier
            plant_id: Unique plant identifier
            state_dict: PlantState as dictionary
            profile_id: Plant profile ID
            co2_fluxes: Current CO2 flux data
            metadata: Additional metadata

        Returns:
            True if saved successfully
        """
        doc_data = {
            'simulation_id': simulation_id,
            'plant_id': plant_id,
            'profile_id': profile_id,
            'state': state_dict,
            'co2_fluxes': co2_fluxes or {},
            'metadata': metadata or {},
            'updated_at': datetime.now().isoformat(),
        }

        # Always update local cache
        self._local_cache['simulations'][simulation_id] = doc_data

        if not self.connected or not self.db:
            logger.debug(f"Firebase not connected. Cached simulation {simulation_id} locally.")
            return True

        try:
            self.db.collection('simulations').document(simulation_id).set(doc_data)
            logger.debug(f"Saved simulation {simulation_id} to Firebase")
            return True

        except Exception as e:
            logger.error(f"Failed to save simulation to Firebase: {e}")
            return False

    def load_simulation(self, simulation_id: str) -> Optional[Dict[str, Any]]:
        """
        Load simulation state

        Args:
            simulation_id: Unique simulation identifier

        Returns:
            Simulation data dictionary or None if not found
        """
        # Check local cache first
        if simulation_id in self._local_cache['simulations']:
            return self._local_cache['simulations'][simulation_id]

        if not self.connected or not self.db:
            return None

        try:
            doc = self.db.collection('simulations').document(simulation_id).get()
            if doc.exists:
                data = doc.to_dict()
                self._local_cache['simulations'][simulation_id] = data
                return data
            return None

        except Exception as e:
            logger.error(f"Failed to load simulation from Firebase: {e}")
            return None

    def delete_simulation(self, simulation_id: str) -> bool:
        """
        Delete simulation state

        Args:
            simulation_id: Unique simulation identifier

        Returns:
            True if deleted successfully
        """
        # Remove from local cache
        if simulation_id in self._local_cache['simulations']:
            del self._local_cache['simulations'][simulation_id]

        if not self.connected or not self.db:
            return True

        try:
            self.db.collection('simulations').document(simulation_id).delete()
            return True

        except Exception as e:
            logger.error(f"Failed to delete simulation from Firebase: {e}")
            return False

    def list_simulations(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        List all simulations

        Args:
            limit: Maximum number of simulations to return

        Returns:
            List of simulation metadata
        """
        results = list(self._local_cache['simulations'].values())

        if self.connected and self.db:
            try:
                docs = self.db.collection('simulations').limit(limit).stream()
                for doc in docs:
                    data = doc.to_dict()
                    sim_id = data.get('simulation_id')
                    if sim_id and sim_id not in self._local_cache['simulations']:
                        self._local_cache['simulations'][sim_id] = data
                        results.append(data)
            except Exception as e:
                logger.error(f"Failed to list simulations: {e}")

        return results[:limit]

    # -------------------------------------------------------------------------
    # Simulation History
    # -------------------------------------------------------------------------

    def save_history_snapshot(
        self,
        simulation_id: str,
        hour: int,
        state_dict: Dict[str, Any],
        co2_fluxes: Optional[Dict[str, float]] = None
    ) -> bool:
        """
        Save a historical state snapshot

        Args:
            simulation_id: Unique simulation identifier
            hour: Simulation hour
            state_dict: PlantState as dictionary
            co2_fluxes: CO2 flux data

        Returns:
            True if saved successfully
        """
        doc_id = f"{simulation_id}_h{hour:06d}"
        doc_data = {
            'simulation_id': simulation_id,
            'hour': hour,
            'state': state_dict,
            'co2_fluxes': co2_fluxes or {},
            'timestamp': datetime.now().isoformat(),
        }

        # Local cache
        if simulation_id not in self._local_cache['history']:
            self._local_cache['history'][simulation_id] = {}
        self._local_cache['history'][simulation_id][hour] = doc_data

        if not self.connected or not self.db:
            return True

        try:
            self.db.collection('simulation_history').document(doc_id).set(doc_data)
            return True

        except Exception as e:
            logger.error(f"Failed to save history snapshot: {e}")
            return False

    def load_history(
        self,
        simulation_id: str,
        start_hour: int = 0,
        end_hour: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Load simulation history

        Args:
            simulation_id: Unique simulation identifier
            start_hour: Start hour (inclusive)
            end_hour: End hour (inclusive, None = latest)

        Returns:
            List of historical state snapshots
        """
        results = []

        # Check local cache
        if simulation_id in self._local_cache['history']:
            for hour, data in self._local_cache['history'][simulation_id].items():
                if hour >= start_hour and (end_hour is None or hour <= end_hour):
                    results.append(data)

        if self.connected and self.db:
            try:
                query = self.db.collection('simulation_history').where(
                    'simulation_id', '==', simulation_id
                ).where(
                    'hour', '>=', start_hour
                )

                if end_hour is not None:
                    query = query.where('hour', '<=', end_hour)

                query = query.order_by('hour')

                for doc in query.stream():
                    data = doc.to_dict()
                    # Avoid duplicates from cache
                    hour = data.get('hour')
                    if not any(r.get('hour') == hour for r in results):
                        results.append(data)

            except Exception as e:
                logger.error(f"Failed to load history: {e}")

        return sorted(results, key=lambda x: x.get('hour', 0))

    # -------------------------------------------------------------------------
    # Plant Profiles
    # -------------------------------------------------------------------------

    def save_plant_profile(
        self,
        profile_id: str,
        profile_dict: Dict[str, Any]
    ) -> bool:
        """
        Save a plant profile

        Args:
            profile_id: Unique profile identifier
            profile_dict: PlantProfile as dictionary

        Returns:
            True if saved successfully
        """
        doc_data = {
            'profile_id': profile_id,
            'profile': profile_dict,
            'updated_at': datetime.now().isoformat(),
        }

        self._local_cache['plants'][profile_id] = doc_data

        if not self.connected or not self.db:
            return True

        try:
            self.db.collection('plants').document(profile_id).set(doc_data)
            return True

        except Exception as e:
            logger.error(f"Failed to save plant profile: {e}")
            return False

    def load_plant_profile(self, profile_id: str) -> Optional[Dict[str, Any]]:
        """
        Load a plant profile

        Args:
            profile_id: Unique profile identifier

        Returns:
            Profile dictionary or None
        """
        if profile_id in self._local_cache['plants']:
            return self._local_cache['plants'][profile_id].get('profile')

        if not self.connected or not self.db:
            return None

        try:
            doc = self.db.collection('plants').document(profile_id).get()
            if doc.exists:
                data = doc.to_dict()
                self._local_cache['plants'][profile_id] = data
                return data.get('profile')
            return None

        except Exception as e:
            logger.error(f"Failed to load plant profile: {e}")
            return None

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    def export_cache(self, filepath: str) -> bool:
        """
        Export local cache to JSON file

        Args:
            filepath: Path to output file

        Returns:
            True if successful
        """
        try:
            with open(filepath, 'w') as f:
                json.dump(self._local_cache, f, indent=2, default=str)
            logger.info(f"Exported cache to {filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to export cache: {e}")
            return False

    def import_cache(self, filepath: str) -> bool:
        """
        Import local cache from JSON file

        Args:
            filepath: Path to input file

        Returns:
            True if successful
        """
        try:
            with open(filepath, 'r') as f:
                self._local_cache = json.load(f)
            logger.info(f"Imported cache from {filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to import cache: {e}")
            return False

    def sync_to_firebase(self) -> bool:
        """
        Sync local cache to Firebase

        Returns:
            True if successful
        """
        if not self.connected or not self.db:
            logger.warning("Cannot sync: Firebase not connected")
            return False

        try:
            # Sync simulations
            for sim_id, data in self._local_cache['simulations'].items():
                self.db.collection('simulations').document(sim_id).set(data)

            # Sync history
            for sim_id, hours in self._local_cache['history'].items():
                for hour, data in hours.items():
                    doc_id = f"{sim_id}_h{hour:06d}"
                    self.db.collection('simulation_history').document(doc_id).set(data)

            # Sync profiles
            for profile_id, data in self._local_cache['plants'].items():
                self.db.collection('plants').document(profile_id).set(data)

            logger.info("Synced local cache to Firebase")
            return True

        except Exception as e:
            logger.error(f"Failed to sync to Firebase: {e}")
            return False

    def get_cache_stats(self) -> Dict[str, int]:
        """Get statistics about local cache"""
        history_count = sum(len(h) for h in self._local_cache['history'].values())
        return {
            'simulations': len(self._local_cache['simulations']),
            'history_snapshots': history_count,
            'plant_profiles': len(self._local_cache['plants']),
        }

    def clear_cache(self) -> None:
        """Clear local cache"""
        self._local_cache = {
            'simulations': {},
            'history': {},
            'plants': {}
        }

    def close(self) -> None:
        """Close Firebase connection"""
        self.db = None
        self.connected = False

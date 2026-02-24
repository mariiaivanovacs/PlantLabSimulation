"""
Converts PlantState dict to an MQTT-ready payload.

Payload content is controlled by the MQTT_PAYLOAD_FIELDS environment variable:
  - Empty / unset  → full PlantState dict is published
  - Comma-separated field names → only those fields are included

Example .env entry:
  MQTT_PAYLOAD_FIELDS=hour,biomass,phenological_stage,is_alive,water_stress,soil_water,air_temp,CO2
"""

import os
from typing import Dict, Any, List, Optional
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / 'config' / '.env')
except ImportError:
    pass


class SimulationAdapter:
    """Filters PlantState dict to the configured MQTT payload fields."""

    def __init__(self):
        whitelist_env = os.getenv('MQTT_PAYLOAD_FIELDS', '').strip()
        if whitelist_env:
            self._fields: Optional[List[str]] = [
                f.strip() for f in whitelist_env.split(',') if f.strip()
            ]
        else:
            self._fields = None  # None → publish full state

    def to_mqtt_payload(self, state_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Return filtered (or full) payload dict ready for JSON serialisation."""
        if self._fields is None:
            return dict(state_dict)
        return {k: state_dict[k] for k in self._fields if k in state_dict}

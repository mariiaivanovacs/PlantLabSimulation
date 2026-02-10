"""
Reasoning Agent
Receives routed alerts from Monitor Agent, queries the RAG knowledge base
for grounded plant-physiology diagnostics, and suggests corrective tool
actions that the Executor Agent can apply.

RAG cycle runs every 6 simulation hours (called from engine).
"""
import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, TYPE_CHECKING
from collections import deque

if TYPE_CHECKING:
    from ai.rag.query_engine import PlantDiagnosticQueryEngine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Flag-to-action mapping (deterministic, no LLM)
# ---------------------------------------------------------------------------

# Maps health-flag names to corrective tool actions.
# Each entry: flag_name -> list of {"tool_type": ..., "parameters": ...}
_FLAG_ACTION_MAP: Dict[str, List[Dict[str, Any]]] = {
    # Water-related
    "SOIL_AT_WILTING_POINT": [
        {"tool_type": "watering", "parameters": {"volume_L": 0.5}},
    ],
    "SOIL_BELOW_FIELD_CAPACITY": [
        {"tool_type": "watering", "parameters": {"volume_L": 0.2}},
    ],
    # Temperature-related
    "TEMPERATURE_DEVIATION_PERSISTENT": [
        {"tool_type": "hvac", "parameters": {"target_temp_C": None, "max_rate_C_per_h": 3.0}},
    ],
    "TEMPERATURE_SUBOPTIMAL": [
        {"tool_type": "hvac", "parameters": {"target_temp_C": None, "max_rate_C_per_h": 2.0}},
    ],
    # VPD / humidity
    "VPD_HIGH_PERSISTENT": [
        {"tool_type": "humidity", "parameters": {"target_RH": None}},
    ],
    # EC / nutrients
    "EC_TOXICITY": [
        {"tool_type": "watering", "parameters": {"volume_L": 1.0}},  # flush
    ],
    # Light
    "PAR_LOW_DAYTIME": [
        {"tool_type": "lighting", "parameters": {"target_PAR": None}},
    ],
}


class ReasoningAgent:
    """
    Reasoning Agent with optional RAG-based diagnostics.

    Core responsibilities:
    - Receive and store WARNING / CRITICAL alerts from MonitorAgent
    - Query RAG knowledge base for grounded explanations (if rag_engine set)
    - Suggest deterministic corrective tool actions based on health flags
    - Maintain alert history and statistics

    The RAG engine is optional: if not set, analyze() falls back to a
    flag-summary-only mode (no LLM call).
    """

    def __init__(
        self,
        plant_id: str = "unknown",
        simulation_id: str = "unknown",
        max_history: int = 1000,
        log_dir: str = "out/reasoning",
        rag_engine: Optional["PlantDiagnosticQueryEngine"] = None,
    ):
        self.plant_id = plant_id
        self.simulation_id = simulation_id
        self.log_dir = log_dir
        self.rag_engine = rag_engine

        # Alert history (deque with max size)
        self.alert_history: deque = deque(maxlen=max_history)

        # Diagnostic history (parallel to alerts that were analyzed)
        self.diagnostic_history: List[Dict[str, Any]] = []

        # Statistics
        self.total_alerts_received: int = 0
        self.warnings_received: int = 0
        self.criticals_received: int = 0
        self.rag_queries: int = 0

        # Ensure log directory exists
        os.makedirs(log_dir, exist_ok=True)

        logger.info(
            f"ReasoningAgent initialized for plant {plant_id} "
            f"(RAG {'enabled' if rag_engine else 'disabled'})"
        )

    # ------------------------------------------------------------------
    # Alert reception (unchanged API)
    # ------------------------------------------------------------------

    def receive_alert(self, alert: Dict[str, Any]) -> None:
        """
        Receive an alert from MonitorAgent.

        Args:
            alert: Alert dictionary in sample.json format
        """
        self.total_alerts_received += 1

        severity = alert.get("routing", {}).get("highest_severity", "UNKNOWN")
        hour = alert.get("meta", {}).get("hour", -1)

        if severity == "WARNING":
            self.warnings_received += 1
        elif severity == "CRITICAL":
            self.criticals_received += 1

        self.alert_history.append({
            "received_at": datetime.now().isoformat(),
            "alert": alert
        })

        warning_count = len(alert.get("health_flags", {}).get("warning", []))
        critical_count = len(alert.get("health_flags", {}).get("critical", []))

        logger.info(
            f"ReasoningAgent received {severity} alert at hour {hour}: "
            f"{warning_count} warnings, {critical_count} criticals"
        )

        for flag in alert.get("health_flags", {}).get("critical", []):
            logger.warning(f"  CRITICAL: {flag.get('flag')} - {flag.get('metric')}={flag.get('value')}")

        for flag in alert.get("health_flags", {}).get("warning", []):
            logger.info(f"  WARNING: {flag.get('flag')} - {flag.get('metric')}={flag.get('value')}")

    # ------------------------------------------------------------------
    # RAG-powered analysis
    # ------------------------------------------------------------------

    def analyze(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze an alert using the RAG knowledge base (if available).

        When rag_engine is set:
          1. Formats the RAG template with alert data
          2. Queries the vector index for relevant plant-physiology knowledge
          3. Returns grounded diagnostic text from GPT-4o

        When rag_engine is None:
          Falls back to a simple flag summary (no LLM call).

        Returns:
            {"status": "analyzed"|"fallback", "diagnostic": str, "alert_severity": str}
        """
        severity = alert.get("routing", {}).get("highest_severity", "UNKNOWN")
        hour = alert.get("meta", {}).get("hour", -1)

        logger.info(f"Analyze RAG was called for alert at hour {hour} with severity {severity}")
        if self.rag_engine is not None:
            
            try:
                diagnostic = self.rag_engine.query(alert)
                logger.info(f"RAG query successful at hour {hour}, diagnostic length: {len(diagnostic)} chars")
                self.rag_queries += 1
                result = {
                    "status": "analyzed",
                    "diagnostic": diagnostic,
                    "alert_severity": severity,
                    "hour": hour,
                }
                logger.info(f"RAG diagnostic at hour {hour}: {len(diagnostic)} chars")
            except Exception as e:
                logger.error(f"RAG query failed at hour {hour}: {e}")
                diagnostic = self._fallback_summary(alert)
                result = {
                    "status": "fallback",
                    "diagnostic": diagnostic,
                    "alert_severity": severity,
                    "hour": hour,
                    "error": str(e),
                }
        else:
            logger.info(f"No RAG engine configured, using fallback summary at hour {hour}")
            diagnostic = self._fallback_summary(alert)
            result = {
                "status": "fallback",
                "diagnostic": diagnostic,
                "alert_severity": severity,
                "hour": hour,
            }

        self.diagnostic_history.append(result)
        return result

    def _fallback_summary(self, alert: Dict[str, Any]) -> str:
        """Build a simple text summary from health flags (no LLM)."""
        lines = []
        for severity in ("critical", "warning", "info"):
            for flag in alert.get("health_flags", {}).get(severity, []):
                lines.append(
                    f"[{severity.upper()}] {flag.get('flag')}: "
                    f"{flag.get('metric')}={flag.get('value')} "
                    f"(threshold: {flag.get('threshold')}, "
                    f"duration: {flag.get('duration_hours', 0)}h)"
                )
        return "\n".join(lines) if lines else "No active flags."

    # ------------------------------------------------------------------
    # Action suggestion (deterministic flag-to-action mapping)
    # ------------------------------------------------------------------

    def suggest_actions(
        self,
        alert: Dict[str, Any],
        diagnostic: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Suggest corrective tool actions based on active health flags.

        Uses a deterministic flag-to-action map (_FLAG_ACTION_MAP).
        Fills in species-specific parameter values from the alert's
        thresholds reference where applicable (e.g. target_temp_C).

        Args:
            alert: Alert dict (sample.json format)
            diagnostic: Optional diagnostic result from analyze()

        Returns:
            List of {"tool_type": str, "parameters": dict} ready for
            ExecutorAgent.execute_plan()
        """
        thresholds = alert.get("species_thresholds_reference", {})
        metrics = alert.get("metrics", {})
        actions: List[Dict[str, Any]] = []
        seen_tools: set = set()  # avoid duplicate tool calls

        for severity in ("critical", "warning"):
            for flag in alert.get("health_flags", {}).get(severity, []):
                flag_name = flag.get("flag", "")
                mapped = _FLAG_ACTION_MAP.get(flag_name)
                if not mapped:
                    continue

                for action_template in mapped:
                    tool_type = action_template["tool_type"]
                    if tool_type in seen_tools:
                        continue
                    seen_tools.add(tool_type)

                    params = dict(action_template["parameters"])
                    # Fill None placeholders with species-specific values
                    params = self._fill_params(params, flag_name, thresholds, metrics)
                    actions.append({"tool_type": tool_type, "parameters": params})

        if actions:
            logger.info(f"ReasoningAgent suggests {len(actions)} corrective action(s)")
        return actions

    @staticmethod
    def _fill_params(
        params: Dict[str, Any],
        flag_name: str,
        thresholds: Dict[str, Any],
        metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Fill None placeholder values with species-specific targets."""
        if params.get("target_temp_C") is None and "TEMPERATURE" in flag_name:
            params["target_temp_C"] = thresholds.get("temp_opt_c", 25.0)

        if params.get("target_RH") is None and "VPD" in flag_name:
            # Raise RH to reduce VPD; target midpoint between current and 70%
            current_rh = metrics.get("relative_humidity", 60)
            params["target_RH"] = min(80.0, current_rh + 10.0)

        if params.get("target_PAR") is None and "PAR" in flag_name:
            params["target_PAR"] = thresholds.get("par_optimal_umol_m2_s", 400)

        return params

    # ------------------------------------------------------------------
    # Retrieval helpers (unchanged API)
    # ------------------------------------------------------------------

    def get_recent_alerts(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get most recent alerts"""
        return list(self.alert_history)[-count:]

    def get_alerts_by_severity(self, severity: str) -> List[Dict[str, Any]]:
        """Get alerts filtered by severity"""
        return [
            entry for entry in self.alert_history
            if entry["alert"].get("routing", {}).get("highest_severity") == severity
        ]

    def get_alerts_in_range(self, start_hour: int, end_hour: int) -> List[Dict[str, Any]]:
        """Get alerts within hour range"""
        return [
            entry for entry in self.alert_history
            if start_hour <= entry["alert"].get("meta", {}).get("hour", -1) <= end_hour
        ]

    def get_statistics(self) -> Dict[str, Any]:
        """Get alert statistics"""
        return {
            "plant_id": self.plant_id,
            "simulation_id": self.simulation_id,
            "total_alerts": self.total_alerts_received,
            "warnings": self.warnings_received,
            "criticals": self.criticals_received,
            "rag_queries": self.rag_queries,
            "history_size": len(self.alert_history),
            "diagnostics": len(self.diagnostic_history),
        }

    def get_recent_diagnostics(self, count: int = 5) -> List[Dict[str, Any]]:
        """Get the most recent RAG diagnostic results."""
        return self.diagnostic_history[-count:]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_session_log(self) -> str:
        """Save session alerts and diagnostics to log file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"reasoning_session_{self.plant_id}_{timestamp}.json"
        filepath = os.path.join(self.log_dir, filename)

        session_data = {
            "plant_id": self.plant_id,
            "simulation_id": self.simulation_id,
            "statistics": self.get_statistics(),
            "alerts": list(self.alert_history),
            "diagnostics": self.diagnostic_history,
        }

        with open(filepath, 'w') as f:
            json.dump(session_data, f, indent=2)

        logger.info(f"ReasoningAgent session log saved: {filepath}")
        return filepath

    def reset(self) -> None:
        """Reset agent state"""
        self.alert_history.clear()
        self.diagnostic_history.clear()
        self.total_alerts_received = 0
        self.warnings_received = 0
        self.criticals_received = 0
        self.rag_queries = 0

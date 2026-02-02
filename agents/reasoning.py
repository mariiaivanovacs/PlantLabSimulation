"""
Reasoning Agent (Skeleton)
Receives routed alerts from Monitor Agent.
Currently only logs and stores alerts - no autonomous decision-making.
"""
import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import deque

logger = logging.getLogger(__name__)


class ReasoningAgent:
    """
    Skeleton Reasoning Agent for receiving and storing alerts.

    This agent is the target for WARNING and CRITICAL alerts from MonitorAgent.
    Currently implements:
    - Alert reception and logging
    - Alert history storage
    - Basic alert retrieval

    Future extensions could add:
    - LLM-based analysis
    - Autonomous corrective actions
    - Pattern recognition across alerts
    """

    def __init__(
        self,
        plant_id: str = "unknown",
        simulation_id: str = "unknown",
        max_history: int = 1000,
        log_dir: str = "out/reasoning"
    ):
        self.plant_id = plant_id
        self.simulation_id = simulation_id
        self.log_dir = log_dir

        # Alert history (deque with max size)
        self.alert_history: deque = deque(maxlen=max_history)

        # Statistics
        self.total_alerts_received: int = 0
        self.warnings_received: int = 0
        self.criticals_received: int = 0

        # Ensure log directory exists
        os.makedirs(log_dir, exist_ok=True)

        logger.info(f"ReasoningAgent initialized for plant {plant_id}")

    def receive_alert(self, alert: Dict[str, Any]) -> None:
        """
        Receive an alert from MonitorAgent.

        Args:
            alert: Alert dictionary in sample.json format
        """
        self.total_alerts_received += 1

        severity = alert.get("routing", {}).get("highest_severity", "UNKNOWN")
        hour = alert.get("meta", {}).get("hour", -1)

        # Update statistics
        if severity == "WARNING":
            self.warnings_received += 1
        elif severity == "CRITICAL":
            self.criticals_received += 1

        # Store in history
        self.alert_history.append({
            "received_at": datetime.now().isoformat(),
            "alert": alert
        })

        # Log the alert
        warning_count = len(alert.get("health_flags", {}).get("warning", []))
        critical_count = len(alert.get("health_flags", {}).get("critical", []))

        logger.info(
            f"ReasoningAgent received {severity} alert at hour {hour}: "
            f"{warning_count} warnings, {critical_count} criticals"
        )

        # Log specific flags for debugging
        for flag in alert.get("health_flags", {}).get("critical", []):
            logger.warning(f"  CRITICAL: {flag.get('flag')} - {flag.get('metric')}={flag.get('value')}")

        for flag in alert.get("health_flags", {}).get("warning", []):
            logger.info(f"  WARNING: {flag.get('flag')} - {flag.get('metric')}={flag.get('value')}")

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
            "history_size": len(self.alert_history)
        }

    def analyze(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze an alert (skeleton - returns placeholder).

        Future implementation could:
        - Call LLM for analysis
        - Suggest corrective actions
        - Identify root causes
        """
        return {
            "status": "skeleton",
            "message": "ReasoningAgent.analyze() not yet implemented",
            "alert_severity": alert.get("routing", {}).get("highest_severity"),
            "recommendation": None
        }

    def suggest_actions(self, alert: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Suggest corrective actions (skeleton - returns empty list).

        Future implementation could return tool actions:
        [
            {"tool": "watering", "params": {"volume_L": 0.5}},
            {"tool": "hvac", "params": {"target_temp_C": 25}}
        ]
        """
        return []

    def save_session_log(self) -> str:
        """Save session alerts to log file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"reasoning_session_{self.plant_id}_{timestamp}.json"
        filepath = os.path.join(self.log_dir, filename)

        session_data = {
            "plant_id": self.plant_id,
            "simulation_id": self.simulation_id,
            "statistics": self.get_statistics(),
            "alerts": list(self.alert_history)
        }

        with open(filepath, 'w') as f:
            json.dump(session_data, f, indent=2)

        logger.info(f"ReasoningAgent session log saved: {filepath}")
        return filepath

    def reset(self) -> None:
        """Reset agent state"""
        self.alert_history.clear()
        self.total_alerts_received = 0
        self.warnings_received = 0
        self.criticals_received = 0

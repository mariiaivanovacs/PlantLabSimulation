"""
Plant Diagnostic Query Engine

Formats the RAG template with alert data and queries the vector index
for grounded plant-physiology explanations.
"""
import logging
from pathlib import Path
from typing import Dict, Any

from llama_index.core import VectorStoreIndex
from llama_index.llms.openai import OpenAI

logger = logging.getLogger(__name__)

# Path to the RAG prompt template
RAG_TEMPLATE_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "RAG_template.md"


class PlantDiagnosticQueryEngine:
    """
    Wraps a LlamaIndex query engine with plant-specific prompt formatting.

    Usage:
        engine = PlantDiagnosticQueryEngine(index)
        response = engine.query(alert_dict)   # returns str
    """

    def __init__(self, index: VectorStoreIndex, model: str = "gpt-4o"):
        self._index = index
        self._llm = OpenAI(model=model, temperature=0.2)
        self._query_engine = index.as_query_engine(
            llm=self._llm,
            similarity_top_k=5,
        )
        self._template = self._load_template()

    @staticmethod
    def _load_template() -> str:
        """Load the RAG prompt template from docs/RAG_template.md."""
        if RAG_TEMPLATE_PATH.exists():
            return RAG_TEMPLATE_PATH.read_text()
        logger.warning(f"RAG template not found at {RAG_TEMPLATE_PATH}, using fallback")
        return (
            "Analyze the following plant state and explain likely causes "
            "and consequences of any active health warnings.\n\n{health_flags_summary}"
        )

    def format_prompt(self, alert: Dict[str, Any]) -> str:
        """
        Fill the RAG template placeholders with data from an alert dict.

        The alert follows the structure defined in docs/sample.json.
        """
        meta = alert.get("meta", {})
        metrics = alert.get("metrics", {})
        thresholds = alert.get("species_thresholds_reference", {})
        health_flags = alert.get("health_flags", {})

        # Build health flags summary text
        flags_lines = []
        for severity in ("critical", "warning", "info"):
            for flag in health_flags.get(severity, []):
                flags_lines.append(
                    f"- [{flag.get('severity', severity.upper())}] "
                    f"{flag.get('flag')}: {flag.get('metric')}={flag.get('value')} "
                    f"(threshold: {flag.get('threshold')}, "
                    f"duration: {flag.get('duration_hours', 0)}h)"
                )
        health_flags_summary = "\n".join(flags_lines) if flags_lines else "No active flags."

        # Map template placeholders to values
        mapping = {
            # Meta
            "profile_id": meta.get("profile_id", "unknown"),
            "phenological_stage": metrics.get("phenological_stage", "unknown"),
            "hour": meta.get("hour", "?"),
            "local_time": meta.get("local_time", "?"),
            "pot_volume": meta.get("pot_volume", "?"),
            "room_volume": meta.get("room_volume", "?"),
            # Metrics
            "air_temp": metrics.get("air_temp", "?"),
            "VPD": metrics.get("VPD", "?"),
            "soil_water": metrics.get("soil_water", "?"),
            "relative_humidity": metrics.get("relative_humidity", "?"),
            "light_PAR": metrics.get("light_PAR", "?"),
            "water_stress": metrics.get("water_stress", "?"),
            "growth_rate": metrics.get("growth_rate", "?"),
            "cumulative_damage": metrics.get("cumulative_damage", "?"),
            # Thresholds
            "temp_opt_c": thresholds.get("temp_opt_c", "?"),
            "vpd_opt_kpa": thresholds.get("vpd_opt_kpa", "?"),
            "vpd_warning_kpa": thresholds.get("vpd_warning_kpa", "?"),
            "soil_field_capacity_percent": thresholds.get("soil_field_capacity_percent", "?"),
            # Health flags
            "health_flags_summary": health_flags_summary,
        }

        prompt = self._template
        for key, value in mapping.items():
            prompt = prompt.replace(f"{{{key}}}", str(value))

        return prompt

    def query(self, alert: Dict[str, Any]) -> str:
        """
        Format the prompt from an alert dict and query the RAG index.

        Returns:
            The LLM response string (grounded diagnostic).
        """
        prompt = self.format_prompt(alert)
        logger.info(f"Querying RAG with {len(prompt)} char prompt")
        response = self._query_engine.query(prompt)
        return str(response)

"""
Agent Orchestrator
Owns and coordinates all agents (monitor, reasoning, executor) independently
of the SimulationEngine.  Attaches to an engine via post-step hooks so the
simulation can run with or without the agent layer.

Usage:
    engine = SimulationEngine(profile)
    orchestrator = AgentOrchestrator.create(engine)
    # engine now calls orchestrator hooks automatically each step
"""
import logging
from typing import Dict, Any, Optional, TYPE_CHECKING

from agents.monitor import MonitorAgent, MonitorThresholds
from agents.reasoning import ReasoningAgent
from agents.executor import ExecutorAgent



if TYPE_CHECKING:
    from models.engine import SimulationEngine

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Creates and manages the full agent layer independently of SimulationEngine.

    Agents owned:
      - MonitorAgent   (health checks every hour)
      - ReasoningAgent (RAG diagnostics every 6 hours)
      - ExecutorAgent  (tool application — caring regime + corrective actions)

    The orchestrator registers two hooks on the engine:
      1. pre-physics hook  — runs executor caring regime before physics
      2. post-physics hook  — runs monitor check + reasoning cycle after physics
    """

    def __init__(
        self,
        engine: "SimulationEngine",
        monitor_agent: MonitorAgent,
        reasoning_agent: ReasoningAgent,
        executor_agent: ExecutorAgent,
        monitor_enabled: bool = True,
        reasoning_interval: int = 6,
    ):
        self.engine = engine
        self.monitor_agent = monitor_agent
        self.reasoning_agent = reasoning_agent
        self.executor_agent = executor_agent
        self.monitor_enabled = monitor_enabled
        self.reasoning_interval = reasoning_interval

    # ------------------------------------------------------------------
    # Factory: create orchestrator and attach to engine in one call
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        engine: "SimulationEngine",
        monitor_enabled: bool = True,
        reasoning_interval: int = 6,
    ) -> "AgentOrchestrator":
        """
        Build all agents from the engine's profile and attach hooks.

        Args:
            engine: SimulationEngine instance (must be fully initialized)
            monitor_enabled: whether to run monitor checks each step
            reasoning_interval: sim-hours between reasoning cycles (default 6)

        Returns:
            Attached AgentOrchestrator instance
        """
        profile = engine.plant_profile

        # --- Monitor Agent ---
        thresholds = MonitorThresholds.from_plant_profile(profile)
        monitor = MonitorAgent(
            thresholds=thresholds,
            output_dir="out",
            plant_id=engine.plant_id,
            simulation_id=engine.simulation_id,
            profile_id=profile.profile_id,
        )

        # --- Reasoning Agent ---
        reasoning = ReasoningAgent(
            plant_id=engine.plant_id,
            simulation_id=engine.simulation_id,
            log_dir="out/reasoning",
        )

        # --- Executor Agent ---
        executor = ExecutorAgent(
            engine=engine,
            regime_config={
                "watering_hour": engine.watering_hour,
                "ventilation_hour": engine.ventilation_hour,
                "daily_water_amount": engine.daily_water_amount,
                "fan_speed": engine.daily_ventilation_speed,
                "co2_enrichment": engine.co2_enrichment_enabled,
                "co2_target_ppm": engine.co2_target_ppm,
                "co2_enrichment_hours": engine.co2_enrichment_hours,
            },
        )

        orchestrator = cls(
            engine=engine,
            monitor_agent=monitor,
            reasoning_agent=reasoning,
            executor_agent=executor,
            monitor_enabled=monitor_enabled,
            reasoning_interval=reasoning_interval,
        )

        # Register hooks on the engine
        orchestrator._attach(engine)

        logger.info(
            f"AgentOrchestrator attached to engine {engine.simulation_id} "
            f"(monitor={'on' if monitor_enabled else 'off'}, "
            f"reasoning every {reasoning_interval}h)"
        )
        return orchestrator

    # ------------------------------------------------------------------
    # Hook registration
    # ------------------------------------------------------------------

    def _attach(self, engine: "SimulationEngine") -> None:
        """Register pre-physics and post-physics hooks on the engine."""
        # Pre-physics: executor caring regime (runs before environmental calcs)
        pre_hook = self._pre_physics_hook
        # pre_hook._pre_physics = True  # type: ignore[attr-defined]
        engine.register_post_step_hook(pre_hook)

        # Post-physics: monitor + reasoning (runs after checkpoints)
        engine.register_post_step_hook(self._post_physics_hook)

    def _pre_physics_hook(self, engine: "SimulationEngine") -> None:
        """Executor caring regime — runs before physics each hour."""
        if engine.daily_regime_enabled:
            logger.info(f"Pre-physics hook at hour {engine.state.hour}: executing caring regime")
            self.executor_agent.execute_caring_regime()

    def _post_physics_hook(self, engine: "SimulationEngine") -> None:
        """Monitor check + reasoning cycle — runs after physics each hour."""
        if not engine.state.is_alive:
            return
        
        logger.info(f"Post-physics hook at hour {engine.state.hour}: ")

        # Monitor check every hour
        if self.monitor_enabled:
            self._run_monitor_check(engine)

        # Reasoning cycle at interval
        if self.monitor_enabled and engine.state.hour % self.reasoning_interval == 0:
            logger.info(f"Hour {engine.state.hour}: running reasoning cycle ...")
            self._run_reasoning_cycle(engine)
        
        # Send results to LLM once a day at least 
        # if engine.state.hour % 24 == 0:
        #     self.reasoning_agent.analyze

    # ------------------------------------------------------------------
    # Monitor
    # ------------------------------------------------------------------

    def _run_monitor_check(self, engine: "SimulationEngine") -> None:
        """Run monitor agent and route alerts to reasoning agent."""
        alert = self.monitor_agent.check(
            state=engine.state,
            reasoning_agent=self.reasoning_agent,
        )
        if alert:
            severity = alert.get("routing", {}).get("highest_severity", "UNKNOWN")
            logger.info(f"Monitor detected {severity} at hour {engine.state.hour}")

    # ------------------------------------------------------------------
    # Reasoning cycle
    # ------------------------------------------------------------------

    def _run_reasoning_cycle(self, engine: "SimulationEngine") -> None:
        """Analyze latest alert via RAG and feed corrective actions to executor."""
        recent = self.reasoning_agent.get_recent_alerts(count=1)
        if not recent:
            logger.info("No recent alerts for reasoning")
            return

        alert = recent[-1]["alert"]
        severity = alert.get("routing", {}).get("highest_severity", "INFO")

        if severity not in ("WARNING", "CRITICAL"):
            return

        logger.info(f"Reasoning cycle at hour {engine.state.hour}: analyzing {severity}")

        diagnostic = self.reasoning_agent.analyze(alert)
        actions = self.reasoning_agent.suggest_actions(alert, diagnostic)

        if actions:
            logger.info(
                f"Reasoning cycle: executing {len(actions)} corrective action(s)"
            )
            self.executor_agent.execute_plan(actions)

    # ------------------------------------------------------------------
    # Config sync (called when engine.set_daily_regime changes settings)
    # ------------------------------------------------------------------

    def sync_regime_config(self, engine: "SimulationEngine") -> None:
        """Sync executor config from engine's daily-regime settings."""
        self.executor_agent.watering_hour = engine.watering_hour
        self.executor_agent.ventilation_hour = engine.ventilation_hour
        self.executor_agent.daily_water_amount = engine.daily_water_amount
        self.executor_agent.fan_speed = engine.daily_ventilation_speed
        self.executor_agent.co2_enrichment_enabled = engine.co2_enrichment_enabled
        self.executor_agent.co2_target_ppm = engine.co2_target_ppm

    def set_monitor_enabled(self, enabled: bool) -> None:
        """Enable or disable the monitor agent."""
        self.monitor_enabled = enabled
        logger.info(f"Monitor Agent {'enabled' if enabled else 'disabled'}")

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_statistics(self) -> Dict[str, Any]:
        """Get combined agent statistics."""
        return {
            "monitor_enabled": self.monitor_enabled,
            "reasoning": self.reasoning_agent.get_statistics(),
            "executor_actions": len(self.executor_agent.get_log()),
        }

    def save_session_log(self) -> str:
        """Delegate to reasoning agent session log."""
        return self.reasoning_agent.save_session_log()

    def reset(self) -> None:
        """Reset all agents."""
        self.monitor_agent.reset()
        self.reasoning_agent.reset()
        self.executor_agent.reset()

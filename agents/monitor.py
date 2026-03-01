"""
Monitor Agent
Per-hour monitoring of plant health thresholds with sliding windows and hysteresis.
Outputs alerts only when WARNING or CRITICAL conditions are detected.
"""
import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

logger = logging.getLogger(__name__)


# Current Status 
class Severity(str, Enum):
    """Alert severity levels"""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


# Current Target
class RouteTarget(str, Enum):
    """Routing targets based on severity"""
    LOG_ONLY = "LOG_ONLY"
    REASONING_AGENT = "REASONING_AGENT"
    EMERGENCY_SHUTDOWN = "EMERGENCY_SHUTDOWN"


@dataclass
class HealthFlag:
    """Single health flag/alert"""
    flag: str
    metric: str
    value: float
    threshold: float
    duration_hours: float
    trigger_type: str
    severity: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "flag": self.flag,
            "metric": self.metric,
            "value": self.value,
            "threshold": self.threshold,
            "duration_hours": self.duration_hours,
            "trigger_type": self.trigger_type,
            "severity": self.severity
        }


@dataclass
class MonitorThresholds:
    """Threshold configuration for monitoring - derived from PlantProfile"""
    # Temperature
    temp_opt: float = 25.0
    temp_warning_delta: float = 3.0  # |T - T_opt| > this for WARNING
    temp_warning_hours: int = 2
    temp_hysteresis: float = 1.0  # Clear when delta < (warning_delta - hysteresis)

    # VPD
    vpd_opt: float = 1.0
    vpd_warning: float = 1.8
    vpd_warning_hours: int = 3
    vpd_hysteresis: float = 0.2

    # PAR (light)
    par_optimal: float = 600.0
    par_warning_percent: float = 20.0  # WARNING when PAR < 20% of optimal during daytime
    par_warning_hours: int = 4

    # Growth
    rgr_zero_hours: int = 48  # WARNING when RGR <= 0 for this many hours

    # Soil - CRITICAL thresholds
    soil_wilting_point: float = 15.0
    soil_field_capacity: float = 35.0

    # pH/EC toxicity - CRITICAL
    ph_min: float = 5.0
    ph_max: float = 8.0
    ec_toxicity: float = 3.5

    # Multi-warning escalation
    warnings_for_critical: int = 2  # Two WARNINGs in 6h = CRITICAL
    warning_window_hours: int = 6

    @classmethod
    def from_plant_profile(cls, profile) -> 'MonitorThresholds':
        """Create thresholds from a PlantProfile"""
        return cls(
            temp_opt=profile.temperature.T_opt,
            vpd_opt=profile.optimal_VPD,
            par_optimal=profile.growth.optimal_PAR,
            soil_wilting_point=profile.water.wilting_point,
            soil_field_capacity=profile.water.field_capacity,
            ph_min=profile.optimal_pH_min,
            ph_max=profile.optimal_pH_max,
            ec_toxicity=profile.EC_toxicity_threshold,
        )


@dataclass
class SlidingWindow:
    """Sliding window for tracking metric history"""
    max_hours: int = 48  # Keep up to 48 hours of history
    data: deque = field(default_factory=lambda: deque(maxlen=48))

    def __post_init__(self):
        self.data = deque(maxlen=self.max_hours)

    def add(self, hour: int, value: float) -> None:
        """Add a data point"""
        self.data.append((hour, value))

    def get_duration_above(self, threshold: float) -> int:
        """Get consecutive hours where value > threshold (from most recent)"""
        count = 0
        for _, value in reversed(self.data):
            if value > threshold:
                count += 1
            else:
                break
        return count

    def get_duration_below(self, threshold: float) -> int:
        """Get consecutive hours where value < threshold (from most recent)"""
        count = 0
        for _, value in reversed(self.data):
            if value < threshold:
                count += 1
            else:
                break
        return count

    def get_duration_at_or_below(self, threshold: float) -> int:
        """Get consecutive hours where value <= threshold (from most recent)"""
        count = 0
        for _, value in reversed(self.data):
            if value <= threshold:
                count += 1
            else:
                break
        return count

    def get_recent(self, hours: int) -> List[Tuple[int, float]]:
        """Get most recent N hours of data"""
        return list(self.data)[-hours:]


class MonitorAgent:
    """
    Monitor Agent for plant health monitoring.

    Checks thresholds every hour, uses sliding windows for duration-based alerts,
    and implements hysteresis to prevent alert flapping.

    Outputs to /out directory only when WARNING or CRITICAL detected.
    """

    def __init__(
        self,
        thresholds: Optional[MonitorThresholds] = None,
        output_dir: str = "out",
        plant_id: str = "unknown",
        simulation_id: str = "unknown",
        profile_id: str = "unknown"
    ):
        self.thresholds = thresholds or MonitorThresholds()
        self.output_dir = output_dir
        self.plant_id = plant_id
        self.simulation_id = simulation_id
        self.profile_id = profile_id

        # Sliding windows for duration-based checks
        self.windows: Dict[str, SlidingWindow] = {
            "temp_delta": SlidingWindow(max_hours=48),
            "vpd": SlidingWindow(max_hours=48),
            "par": SlidingWindow(max_hours=48),
            "rgr": SlidingWindow(max_hours=72),  # Need 48h history
            "is_daytime": SlidingWindow(max_hours=48),
        }

        # Active alerts with hysteresis state
        self.active_alerts: Dict[str, HealthFlag] = {}

        # Warning history for escalation (stores warning timestamps)
        self.warning_history: deque = deque(maxlen=24)  # Last 24 warnings

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        logger.info(f"MonitorAgent initialized for plant {plant_id}")

    def _is_daytime(self, hour: int) -> bool:
        """Check if current hour is daytime (6:00 - 20:00)"""
        hour_of_day = hour % 24
        return 6 <= hour_of_day < 20

    def update_windows(self, state) -> None:
        """Update sliding windows with current state values"""
        hour = state.hour

        # Temperature delta from optimal
        temp_delta = abs(state.air_temp - self.thresholds.temp_opt)
        self.windows["temp_delta"].add(hour, temp_delta)

        # VPD
        self.windows["vpd"].add(hour, state.VPD)

        # PAR
        self.windows["par"].add(hour, state.light_PAR)

        # RGR
        self.windows["rgr"].add(hour, state.RGR)

        # Daytime flag
        self.windows["is_daytime"].add(hour, 1.0 if self._is_daytime(hour) else 0.0)

    def check_warnings(self, state) -> List[HealthFlag]:
        """Check WARNING-level conditions"""
        warnings = []
        th = self.thresholds
        
        
        # add here water stress check temperature and nutrient stress checks if needed
        if state.water_stress > 0.3:
            flag = HealthFlag(
                flag="HIGH_WATER_STRESS",
                metric="water_stress",
                value=state.water_stress,
                threshold=0.7,
                duration_hours=0,
                trigger_type="species_threshold",
                severity=Severity.WARNING.value
            )
            warnings.append(flag)
        if state.nutrient_stress > 0.3:
            flag = HealthFlag(
                flag="HIGH_NUTRIENT_STRESS",
                metric="nutrient_stress",
                value=state.nutrient_stress,
                threshold=0.7,
                duration_hours=0,
                trigger_type="species_threshold",
                severity=Severity.WARNING.value
            )
            warnings.append(flag)
        if state.temp_stress > 0.3:
            flag = HealthFlag(
                flag="HIGH_TEMPERATURE_STRESS",
                metric="temp_stress",
                value=state.temp_stress,
                threshold=0.7,
                duration_hours=0,
                trigger_type="species_threshold",
                severity=Severity.WARNING.value
            )
            warnings.append(flag)

        # 1. Temperature deviation > 3°C for > 2h
        temp_delta = abs(state.air_temp - th.temp_opt)
        temp_duration = self.windows["temp_delta"].get_duration_above(th.temp_warning_delta)

        alert_key = "TEMP_DEVIATION"
        if temp_duration > th.temp_warning_hours:
            # Check hysteresis - only alert if not already active or if recovering
            if alert_key not in self.active_alerts:
                flag = HealthFlag(
                    flag="TEMPERATURE_DEVIATION_PERSISTENT",
                    metric="air_temp_delta_C",
                    value=temp_delta,
                    threshold=th.temp_warning_delta,
                    duration_hours=temp_duration,
                    trigger_type="duration_exceeded",
                    severity=Severity.WARNING.value
                )
                warnings.append(flag)
                self.active_alerts[alert_key] = flag
        elif temp_delta < (th.temp_warning_delta - th.temp_hysteresis):
            # Clear alert with hysteresis
            self.active_alerts.pop(alert_key, None)

        # 2. VPD > 1.8 kPa for > 3h
        vpd_duration = self.windows["vpd"].get_duration_above(th.vpd_warning)

        alert_key = "VPD_HIGH"
        if vpd_duration > th.vpd_warning_hours:
            if alert_key not in self.active_alerts:
                flag = HealthFlag(
                    flag="VPD_HIGH_PERSISTENT",
                    metric="VPD_kPa",
                    value=state.VPD,
                    threshold=th.vpd_warning,
                    duration_hours=vpd_duration,
                    trigger_type="duration_exceeded",
                    severity=Severity.WARNING.value
                )
                warnings.append(flag)
                self.active_alerts[alert_key] = flag
        elif state.VPD < (th.vpd_warning - th.vpd_hysteresis):
            self.active_alerts.pop(alert_key, None)

        # 3. PAR < 20% of optimal during daytime for > 4h
        par_threshold = th.par_optimal * (th.par_warning_percent / 100.0)

        # Count daytime hours with low PAR
        par_data = self.windows["par"].get_recent(th.par_warning_hours + 1)
        daytime_data = self.windows["is_daytime"].get_recent(th.par_warning_hours + 1)

        low_par_daytime_hours = 0
        for (_, par), (_, is_day) in zip(reversed(par_data), reversed(daytime_data)):
            if is_day > 0.5 and par < par_threshold:
                low_par_daytime_hours += 1
            elif is_day > 0.5:
                break  # Must be consecutive

        alert_key = "PAR_LOW"
        if low_par_daytime_hours > th.par_warning_hours:
            if alert_key not in self.active_alerts:
                flag = HealthFlag(
                    flag="PAR_LOW_DAYTIME_PERSISTENT",
                    metric="light_PAR_umol_m2_s",
                    value=state.light_PAR,
                    threshold=par_threshold,
                    duration_hours=low_par_daytime_hours,
                    trigger_type="daytime_duration_exceeded",
                    severity=Severity.WARNING.value
                )
                warnings.append(flag)
                self.active_alerts[alert_key] = flag
        elif state.light_PAR >= par_threshold * 1.5:  # Clear when PAR recovers to 30%
            self.active_alerts.pop(alert_key, None)

        # 3b. PAR > 150% of optimal during daytime for > 2h (photo-inhibition risk)
        par_high_threshold = th.par_optimal * 1.5
        high_par_daytime_hours = 0
        for (_, par), (_, is_day) in zip(reversed(par_data), reversed(daytime_data)):
            if is_day > 0.5 and par > par_high_threshold:
                high_par_daytime_hours += 1
            elif is_day > 0.5:
                break

        alert_key = "PAR_HIGH"
        if high_par_daytime_hours > 2:
            if alert_key not in self.active_alerts:
                flag = HealthFlag(
                    flag="PAR_HIGH_DAYTIME",
                    metric="light_PAR_umol_m2_s",
                    value=state.light_PAR,
                    threshold=par_high_threshold,
                    duration_hours=high_par_daytime_hours,
                    trigger_type="daytime_duration_exceeded",
                    severity=Severity.WARNING.value
                )
                warnings.append(flag)
                self.active_alerts[alert_key] = flag
        elif state.light_PAR <= par_high_threshold * 0.9:
            self.active_alerts.pop(alert_key, None)

        # 4. RGR <= 0 for 48h
        rgr_zero_duration = self.windows["rgr"].get_duration_at_or_below(0)

        alert_key = "RGR_ZERO"
        if rgr_zero_duration >= th.rgr_zero_hours:
            if alert_key not in self.active_alerts:
                flag = HealthFlag(
                    flag="RGR_ZERO_PROLONGED",
                    metric="RGR_per_hour",
                    value=state.RGR,
                    threshold=0.0,
                    duration_hours=rgr_zero_duration,
                    trigger_type="duration_exceeded",
                    severity=Severity.WARNING.value
                )
                warnings.append(flag)
                self.active_alerts[alert_key] = flag
        elif state.RGR > 0.001:  # Clear when RGR becomes positive
            self.active_alerts.pop(alert_key, None)

        return warnings

    def check_criticals(self, state, current_warnings: List[HealthFlag]) -> List[HealthFlag]:
        """Check CRITICAL-level conditions"""
        criticals = []
        th = self.thresholds

        # 1. Soil water <= wilting point
        if state.soil_water <= th.soil_wilting_point:
            flag = HealthFlag(
                flag="SOIL_AT_WILTING_POINT",
                metric="soil_water_percent",
                value=state.soil_water,
                threshold=th.soil_wilting_point,
                duration_hours=0,
                trigger_type="threshold_breach",
                severity=Severity.CRITICAL.value
            )
            criticals.append(flag)

        # 2. pH toxicity (outside safe range)
        if state.soil_pH < th.ph_min:
            flag = HealthFlag(
                flag="SOIL_PH_TOO_LOW",
                metric="soil_pH",
                value=state.soil_pH,
                threshold=th.ph_min,
                duration_hours=0,
                trigger_type="threshold_breach",
                severity=Severity.CRITICAL.value
            )
            criticals.append(flag)
        elif state.soil_pH > th.ph_max:
            flag = HealthFlag(
                flag="SOIL_PH_TOO_HIGH",
                metric="soil_pH",
                value=state.soil_pH,
                threshold=th.ph_max,
                duration_hours=0,
                trigger_type="threshold_breach",
                severity=Severity.CRITICAL.value
            )
            criticals.append(flag)

        # 3. EC toxicity
        if state.soil_EC >= th.ec_toxicity:
            flag = HealthFlag(
                flag="EC_TOXICITY",
                metric="soil_EC_mS_cm",
                value=state.soil_EC,
                threshold=th.ec_toxicity,
                duration_hours=0,
                trigger_type="threshold_breach",
                severity=Severity.CRITICAL.value
            )
            criticals.append(flag)

        # 4. Two WARNINGs in 6h => CRITICAL escalation
        # Add current warnings to history
        for w in current_warnings:
            self.warning_history.append((state.hour, w.flag))

        # Count unique warnings in last 6 hours
        recent_warnings = set()
        cutoff_hour = state.hour - th.warning_window_hours
        for hour, flag_name in self.warning_history:
            if hour >= cutoff_hour:
                recent_warnings.add(flag_name)

        if len(recent_warnings) >= th.warnings_for_critical:
            flag = HealthFlag(
                flag="MULTIPLE_WARNINGS_ESCALATION",
                metric="unique_warnings_in_6h",
                value=len(recent_warnings),
                threshold=th.warnings_for_critical,
                duration_hours=th.warning_window_hours,
                trigger_type="escalation",
                severity=Severity.CRITICAL.value
            )
            criticals.append(flag)

        return criticals

    def check_info(self, state) -> List[HealthFlag]:
        """Check INFO-level conditions (minor deviations)"""
        infos = []
        th = self.thresholds

        # Soil below field capacity (informational)
        if state.soil_water < th.soil_field_capacity:
            flag = HealthFlag(
                flag="SOIL_BELOW_FIELD_CAPACITY",
                metric="soil_water_percent",
                value=state.soil_water,
                threshold=th.soil_field_capacity,
                duration_hours=0,
                trigger_type="species_threshold",
                severity=Severity.INFO.value
            )
            infos.append(flag)

        # Minor temperature deviation (1-3°C)
        temp_delta = abs(state.air_temp - th.temp_opt)
        if 1.0 < temp_delta <= th.temp_warning_delta:
            flag = HealthFlag(
                flag="TEMPERATURE_SUBOPTIMAL",
                metric="air_temp_delta_C",
                value=temp_delta,
                threshold=1.0,
                duration_hours=0,
                trigger_type="species_threshold",
                severity=Severity.INFO.value
            )
            infos.append(flag)

        return infos

    def determine_routing(self, warnings: List[HealthFlag], criticals: List[HealthFlag]) -> Tuple[str, str]:
        """Determine highest severity and routing target"""
        if criticals:
            return Severity.CRITICAL.value, RouteTarget.REASONING_AGENT.value
        elif warnings:
            return Severity.WARNING.value, RouteTarget.REASONING_AGENT.value
        else:
            return Severity.INFO.value, RouteTarget.LOG_ONLY.value

    def build_output(
        self,
        state,
        infos: List[HealthFlag],
        warnings: List[HealthFlag],
        criticals: List[HealthFlag]
    ) -> Dict[str, Any]:
        """Build output JSON following sample.json format"""
        hour_of_day = state.hour % 24
        is_daytime = self._is_daytime(state.hour)

        highest_severity, route_to = self.determine_routing(warnings, criticals)

        output = {
            "meta": {
                "timestamp": int(datetime.now().timestamp()),
                "plant_id": self.plant_id,
                "simulation_id": self.simulation_id,
                "profile_id": self.profile_id,
                "hour": state.hour,
                "local_time": f"{hour_of_day:02d}:00",
                "is_daytime": is_daytime,
                "pot_volume": state.pot_volume,
                "room_volume": state.room_volume
            },
            "metrics": {
                "biomass": state.biomass,
                "leaf_biomass": state.leaf_biomass,
                "stem_biomass": state.stem_biomass,
                "root_biomass": state.root_biomass,
                "leaf_area": state.leaf_area,
                "phenological_stage": state.phenological_stage.value if hasattr(state.phenological_stage, 'value') else str(state.phenological_stage),
                "thermal_time": state.thermal_time,
                "is_alive": state.is_alive,
                "cumulative_damage": state.cumulative_damage,
                "water_stress": state.water_stress,
                "temp_stress": state.temp_stress,
                "nutrient_stress": state.nutrient_stress,
                "soil_water": state.soil_water,
                "soil_temp": state.soil_temp,
                "soil_N": state.soil_N,
                "soil_P": state.soil_P,
                "soil_K": state.soil_K,
                "soil_EC": state.soil_EC,
                "soil_pH": state.soil_pH,
                "air_temp": state.air_temp,
                "relative_humidity": state.relative_humidity,
                "VPD": state.VPD,
                "light_PAR": state.light_PAR,
                "CO2": state.CO2,
                "ET": state.ET,
                "photosynthesis": state.photosynthesis,
                "respiration": state.respiration,
                "growth_rate": state.growth_rate,
                "RGR": state.RGR,
                "pot_volume": state.pot_volume,
                "room_volume": state.room_volume
            },
            "species_thresholds_reference": {
                "temp_opt_c": self.thresholds.temp_opt,
                "vpd_opt_kpa": self.thresholds.vpd_opt,
                "vpd_warning_kpa": self.thresholds.vpd_warning,
                "soil_wilting_point_percent": self.thresholds.soil_wilting_point,
                "soil_field_capacity_percent": self.thresholds.soil_field_capacity,
                "par_optimal_umol_m2_s": self.thresholds.par_optimal,
                "par_warning_percent_of_target": self.thresholds.par_warning_percent,
                "ec_toxicity_threshold_ms_cm": self.thresholds.ec_toxicity,
                "pH_min": self.thresholds.ph_min,
                "pH_max": self.thresholds.ph_max
            },
            "health_flags": {
                "info": [f.to_dict() for f in infos],
                "warning": [f.to_dict() for f in warnings],
                "critical": [f.to_dict() for f in criticals]
            },
            "routing": {
                "highest_severity": highest_severity,
                "route_to": route_to
            }
        }

        return output

    def save_output(self, output: Dict[str, Any]) -> str:
        """Save output to JSON file with timestamp"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        hour = output["meta"]["hour"]
        severity = output["routing"]["highest_severity"]

        filename = f"monitor_{self.plant_id}_h{hour:04d}_{severity}_{timestamp}.json"
        filepath = os.path.join(self.output_dir, filename)

        with open(filepath, 'w') as f:
            json.dump(output, f, indent=2)

        logger.info(f"Monitor output saved: {filepath}")
        return filepath

    def check(self, state, reasoning_agent=None) -> Optional[Dict[str, Any]]:
        """
        Main check method - called every hour from engine.

        Returns output dict if WARNING or CRITICAL detected, None otherwise.
        Routes to reasoning agent if provided.
        """
        logger.info(f"Monitor check at hour {state.hour}")
        logger.info(f"Reasoning agent provided: {'Yes' if reasoning_agent else 'No'}")
        # Update sliding windows
        self.update_windows(state)

        # Check all conditions
        infos = self.check_info(state)
        warnings = self.check_warnings(state)
        criticals = self.check_criticals(state, warnings)
        logger.info(f"Detected {len(infos)} INFO, {len(warnings)} WARNING, {len(criticals)} CRITICAL alerts")

        # Only output if WARNING or CRITICAL
        if not warnings and not criticals:
            logger.info("No WARNING or CRITICAL alerts detected.")
            return None

        # Build output
        output = self.build_output(state, infos, warnings, criticals)

        # Save to file
        filepath = self.save_output(output)

        # Route to reasoning agent if provided
        
        if reasoning_agent is not None:
            logger.info(f"Routing alert to reasoning agent at hour {state.hour}")
            reasoning_agent.receive_alert(output)

        logger.warning(
            f"Monitor alert at hour {state.hour}: "
            f"{len(warnings)} warnings, {len(criticals)} criticals"
        )

        return output

    def get_active_alerts(self) -> Dict[str, HealthFlag]:
        """Get currently active alerts (for debugging)"""
        return self.active_alerts.copy()

    def reset(self) -> None:
        """Reset monitor state"""
        for window in self.windows.values():
            window.data.clear()
        self.active_alerts.clear()
        self.warning_history.clear()

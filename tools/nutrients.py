"""
Nutrient Dosing Tool
Adds fertilizer (N, P, K) to soil
"""
from typing import Dict, Any
from .base import BaseTool, ToolAction, ToolResult, ToolType


class NutrientTool(BaseTool):
    """
    Nutrient Dosing Tool

    Adds fertilizer to the soil to replenish N, P, K levels.

    Primary effects:
    - Increases soil_N, soil_P, soil_K
    - Increases soil_EC

    Secondary effects:
    - Adequate nutrients → reduces nutrient_stress
    - Excessive nutrients (high EC) → toxicity damage
    """

    tool_type = ToolType.NUTRIENTS

    def __init__(
        self,
        max_N_dose: float = 100.0,
        max_P_dose: float = 50.0,
        max_K_dose: float = 100.0,
        ec_toxicity_threshold: float = 3.5
    ):
        """
        Initialize nutrient tool

        Args:
            max_N_dose: Maximum N dose per application (ppm)
            max_P_dose: Maximum P dose per application (ppm)
            max_K_dose: Maximum K dose per application (ppm)
            ec_toxicity_threshold: EC level that causes damage
        """
        self.max_N_dose = max_N_dose
        self.max_P_dose = max_P_dose
        self.max_K_dose = max_K_dose
        self.ec_toxicity_threshold = ec_toxicity_threshold

    @property
    def description(self) -> str:
        return "Add fertilizer (N, P, K) to soil"

    @property
    def parameter_schema(self) -> Dict[str, Any]:
        return {
            'N_dose_ppm': {
                'type': 'float',
                'description': 'Nitrogen to add (ppm)',
                'min': 0,
                'max': self.max_N_dose,
                'default': 0
            },
            'P_dose_ppm': {
                'type': 'float',
                'description': 'Phosphorus to add (ppm)',
                'min': 0,
                'max': self.max_P_dose,
                'default': 0
            },
            'K_dose_ppm': {
                'type': 'float',
                'description': 'Potassium to add (ppm)',
                'min': 0,
                'max': self.max_K_dose,
                'default': 0
            }
        }

    def validate_parameters(self, parameters: Dict[str, Any]) -> tuple[bool, str]:
        """Validate nutrient parameters"""
        N_dose = parameters.get('N_dose_ppm', 0)
        P_dose = parameters.get('P_dose_ppm', 0)
        K_dose = parameters.get('K_dose_ppm', 0)

        if N_dose < 0 or P_dose < 0 or K_dose < 0:
            return False, "Nutrient doses cannot be negative"

        if N_dose > self.max_N_dose:
            return False, f"N_dose ({N_dose}) exceeds maximum ({self.max_N_dose})"
        if P_dose > self.max_P_dose:
            return False, f"P_dose ({P_dose}) exceeds maximum ({self.max_P_dose})"
        if K_dose > self.max_K_dose:
            return False, f"K_dose ({K_dose}) exceeds maximum ({self.max_K_dose})"

        if N_dose == 0 and P_dose == 0 and K_dose == 0:
            return False, "At least one nutrient must be dosed"

        return True, ""

    def apply(self, state: Any, action: ToolAction) -> ToolResult:
        """
        Apply nutrient dosing action

        Update logic:
        soil_N += N_dose_ppm
        soil_P += P_dose_ppm
        soil_K += K_dose_ppm
        soil_EC = 0.001 × (soil_N + soil_P + soil_K)
        """
        is_valid, error = self.validate_parameters(action.parameters)
        if not is_valid:
            return ToolResult(
                success=False,
                tool_type=self.tool_type,
                action_id=action.action_id,
                changes={},
                message=f"Validation failed: {error}"
            )

        N_dose = action.parameters.get('N_dose_ppm', 0)
        P_dose = action.parameters.get('P_dose_ppm', 0)
        K_dose = action.parameters.get('K_dose_ppm', 0)

        # Store before values
        before_N = state.soil_N
        before_P = state.soil_P
        before_K = state.soil_K
        before_EC = state.soil_EC

        # Apply nutrients
        state.soil_N += N_dose
        state.soil_P += P_dose
        state.soil_K += K_dose

        # Update EC
        state.soil_EC = 0.001 * (state.soil_N + state.soil_P + state.soil_K)

        # Warning if EC is high
        warning = ""
        if state.soil_EC > self.ec_toxicity_threshold:
            warning = f" WARNING: EC ({state.soil_EC:.2f}) exceeds toxicity threshold!"

        return ToolResult(
            success=True,
            tool_type=self.tool_type,
            action_id=action.action_id,
            changes={
                'soil_N': {'before': before_N, 'after': state.soil_N},
                'soil_P': {'before': before_P, 'after': state.soil_P},
                'soil_K': {'before': before_K, 'after': state.soil_K},
                'soil_EC': {'before': before_EC, 'after': state.soil_EC}
            },
            message=f"Added N:{N_dose:.0f} P:{P_dose:.0f} K:{K_dose:.0f} ppm. EC: {before_EC:.2f} → {state.soil_EC:.2f}{warning}"
        )

    def calculate_required_nutrients(
        self,
        current_N: float,
        current_P: float,
        current_K: float,
        optimal_N: float,
        optimal_P: float,
        optimal_K: float
    ) -> Dict[str, float]:
        """
        Calculate nutrients needed to reach optimal levels

        Args:
            current_N, P, K: Current nutrient levels (ppm)
            optimal_N, P, K: Target optimal levels (ppm)

        Returns:
            Dict with required N, P, K doses
        """
        return {
            'N_dose_ppm': max(0, optimal_N - current_N),
            'P_dose_ppm': max(0, optimal_P - current_P),
            'K_dose_ppm': max(0, optimal_K - current_K)
        }

"""
Base Tool Class
Abstract base class for all autonomous tools
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional
from enum import Enum


class ToolType(str, Enum):
    """Types of available tools"""
    WATERING = "watering"
    LIGHTING = "lighting"
    NUTRIENTS = "nutrients"
    HVAC = "hvac"
    HUMIDITY = "humidity"
    VENTILATION = "ventilation"
    CO2_CONTROL = "co2_control"


@dataclass
class ToolAction:
    """Represents a tool action/command"""
    tool_type: ToolType
    parameters: Dict[str, Any]
    scheduled_hour: Optional[int] = None  # Hour to execute (for scheduling)
    timestamp: datetime = field(default_factory=datetime.now)
    action_id: str = ""

    def __post_init__(self):
        if not self.action_id:
            import uuid
            self.action_id = str(uuid.uuid4())[:8]


@dataclass
class ToolResult:
    """Result of a tool action"""
    success: bool
    tool_type: ToolType
    action_id: str
    changes: Dict[str, Any]  # What changed (before/after values)
    message: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'success': self.success,
            'tool_type': self.tool_type.value,
            'action_id': self.action_id,
            'changes': self.changes,
            'message': self.message,
            'timestamp': self.timestamp.isoformat()
        }


class BaseTool(ABC):
    """
    Abstract base class for all tools

    Each tool can:
    - Apply an action to modify plant/environment state
    - Validate parameters before applying
    - Report what changed after application
    """

    tool_type: ToolType

    @abstractmethod
    def apply(self, state: Any, action: ToolAction) -> ToolResult:
        """
        Apply the tool action to the current state

        Args:
            state: Current PlantState object
            action: ToolAction with parameters

        Returns:
            ToolResult with success status and changes made
        """
        pass

    @abstractmethod
    def validate_parameters(self, parameters: Dict[str, Any]) -> tuple[bool, str]:
        """
        Validate action parameters

        Args:
            parameters: Dict of parameter name -> value

        Returns:
            Tuple of (is_valid, error_message)
        """
        pass

    def create_action(self, **kwargs) -> ToolAction:
        """Create a ToolAction for this tool"""
        return ToolAction(
            tool_type=self.tool_type,
            parameters=kwargs
        )

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of the tool"""
        pass

    @property
    @abstractmethod
    def parameter_schema(self) -> Dict[str, Any]:
        """Schema describing valid parameters"""
        pass

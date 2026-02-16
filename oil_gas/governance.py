"""
Oil & Gas Four-Plane Architecture - Execution & Governance Plane

Handles: Tool schemas, validation, security controls, RBAC, audit logging.
Aligns with NIST AI RMF and OWASP Gen AI Security guidelines.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Set
from enum import Enum
import json
import hashlib
import re
import logging

from .data_plane import (
    AutonomyLevel,
    ActionRiskLevel,
    CasePriority,
    ActionStep,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Tool Schema Definitions
# =============================================================================

class ToolCategory(str, Enum):
    """Categories of tools"""
    DIAGNOSTIC = "diagnostic"       # Read-only data queries
    NOTIFICATION = "notification"   # Send alerts/messages
    TICKETING = "ticketing"         # Create/update tickets
    BMS_COMMAND = "bms_command"     # Building Management System commands
    SETPOINT = "setpoint"           # Change setpoints
    EQUIPMENT = "equipment"         # Equipment start/stop/configure
    DISPATCH = "dispatch"           # Dispatch technicians


@dataclass
class ToolParameter:
    """Parameter definition for a tool"""
    name: str
    param_type: str  # string, number, boolean, enum, object
    description: str
    required: bool = True
    default: Any = None
    enum_values: List[Any] = field(default_factory=list)
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    pattern: Optional[str] = None  # Regex pattern for strings


@dataclass
class ToolSchema:
    """
    Strict schema definition for a tool.
    Designed to mitigate prompt injection and unauthorized tool use.
    """
    tool_id: str
    name: str
    description: str
    category: ToolCategory
    risk_level: ActionRiskLevel
    
    # Parameters
    parameters: List[ToolParameter] = field(default_factory=list)
    
    # Permissions
    required_roles: Set[str] = field(default_factory=set)
    requires_approval: bool = False
    approval_threshold: CasePriority = CasePriority.P3_MEDIUM
    
    # Rate limiting
    max_calls_per_hour: int = 100
    cooldown_seconds: int = 0
    
    # Safety
    is_reversible: bool = True
    rollback_tool_id: Optional[str] = None
    
    def validate_params(self, params: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validate parameters against schema"""
        errors = []
        
        for param_def in self.parameters:
            value = params.get(param_def.name)
            
            # Check required
            if param_def.required and value is None:
                errors.append(f"Missing required parameter: {param_def.name}")
                continue
            
            if value is None:
                continue
            
            # Type validation
            if param_def.param_type == "number":
                if not isinstance(value, (int, float)):
                    errors.append(f"{param_def.name}: expected number, got {type(value)}")
                elif param_def.min_value is not None and value < param_def.min_value:
                    errors.append(f"{param_def.name}: value {value} below minimum {param_def.min_value}")
                elif param_def.max_value is not None and value > param_def.max_value:
                    errors.append(f"{param_def.name}: value {value} above maximum {param_def.max_value}")
            
            elif param_def.param_type == "string":
                if not isinstance(value, str):
                    errors.append(f"{param_def.name}: expected string, got {type(value)}")
                elif param_def.pattern:
                    if not re.match(param_def.pattern, value):
                        errors.append(f"{param_def.name}: value does not match pattern {param_def.pattern}")
            
            elif param_def.param_type == "enum":
                if value not in param_def.enum_values:
                    errors.append(f"{param_def.name}: value {value} not in allowed values {param_def.enum_values}")
            
            elif param_def.param_type == "boolean":
                if not isinstance(value, bool):
                    errors.append(f"{param_def.name}: expected boolean, got {type(value)}")
        
        return len(errors) == 0, errors


# =============================================================================
# Standard Tool Definitions
# =============================================================================

def get_standard_tools() -> Dict[str, ToolSchema]:
    """Get standard tool schemas for Oil & Gas operations"""
    return {
        # Diagnostic tools (safe)
        "query_telemetry": ToolSchema(
            tool_id="query_telemetry",
            name="Query Telemetry Data",
            description="Query historical telemetry data for sensors",
            category=ToolCategory.DIAGNOSTIC,
            risk_level=ActionRiskLevel.SAFE,
            parameters=[
                ToolParameter("sensor_ids", "string", "Comma-separated sensor IDs", required=True),
                ToolParameter("start_time", "string", "ISO8601 start timestamp", required=True),
                ToolParameter("end_time", "string", "ISO8601 end timestamp", required=True),
            ],
        ),
        
        "query_events": ToolSchema(
            tool_id="query_events",
            name="Query Device Events",
            description="Query device event history",
            category=ToolCategory.DIAGNOSTIC,
            risk_level=ActionRiskLevel.SAFE,
            parameters=[
                ToolParameter("device_id", "string", "Device identifier", required=True),
                ToolParameter("hours_back", "number", "Hours of history to query", required=False, default=24, max_value=720),
            ],
        ),
        
        "query_maintenance_history": ToolSchema(
            tool_id="query_maintenance_history",
            name="Query Maintenance History",
            description="Query maintenance records for equipment",
            category=ToolCategory.DIAGNOSTIC,
            risk_level=ActionRiskLevel.SAFE,
            parameters=[
                ToolParameter("equipment_id", "string", "Equipment identifier", required=True),
            ],
        ),
        
        # Notification tools (low risk)
        "send_notification": ToolSchema(
            tool_id="send_notification",
            name="Send Notification",
            description="Send notification to stakeholders",
            category=ToolCategory.NOTIFICATION,
            risk_level=ActionRiskLevel.LOW,
            is_reversible=False,
            parameters=[
                ToolParameter("recipient_type", "enum", "Type of recipient", enum_values=["operator", "manager", "customer", "technician"]),
                ToolParameter("subject", "string", "Notification subject", required=True),
                ToolParameter("message", "string", "Notification message", required=True),
                ToolParameter("priority", "enum", "Priority level", enum_values=["low", "normal", "high", "urgent"]),
            ],
            max_calls_per_hour=50,
        ),
        
        "send_customer_update": ToolSchema(
            tool_id="send_customer_update",
            name="Send Customer Update",
            description="Send status update to customer (requires approval for non-routine)",
            category=ToolCategory.NOTIFICATION,
            risk_level=ActionRiskLevel.LOW,
            requires_approval=True,
            approval_threshold=CasePriority.P4_LOW,
            parameters=[
                ToolParameter("customer_id", "string", "Customer identifier", required=True),
                ToolParameter("update_type", "enum", "Type of update", enum_values=["status", "eta", "resolution", "escalation"]),
                ToolParameter("message", "string", "Update message", required=True),
            ],
        ),
        
        # Ticketing tools (low risk)
        "create_ticket": ToolSchema(
            tool_id="create_ticket",
            name="Create Service Ticket",
            description="Create a service/maintenance ticket",
            category=ToolCategory.TICKETING,
            risk_level=ActionRiskLevel.LOW,
            parameters=[
                ToolParameter("title", "string", "Ticket title", required=True),
                ToolParameter("description", "string", "Ticket description", required=True),
                ToolParameter("priority", "enum", "Ticket priority", enum_values=["P1", "P2", "P3", "P4"]),
                ToolParameter("equipment_id", "string", "Related equipment", required=False),
                ToolParameter("case_id", "string", "Related case ID", required=False),
            ],
        ),
        
        "update_ticket": ToolSchema(
            tool_id="update_ticket",
            name="Update Service Ticket",
            description="Update an existing service ticket",
            category=ToolCategory.TICKETING,
            risk_level=ActionRiskLevel.LOW,
            parameters=[
                ToolParameter("ticket_id", "string", "Ticket identifier", required=True),
                ToolParameter("status", "enum", "New status", enum_values=["open", "in_progress", "pending", "resolved", "closed"], required=False),
                ToolParameter("notes", "string", "Additional notes", required=False),
            ],
        ),
        
        # BMS command tools (medium to high risk)
        "adjust_setpoint": ToolSchema(
            tool_id="adjust_setpoint",
            name="Adjust Setpoint",
            description="Adjust equipment setpoint (temperature, pressure, etc.)",
            category=ToolCategory.SETPOINT,
            risk_level=ActionRiskLevel.MEDIUM,
            requires_approval=True,
            approval_threshold=CasePriority.P3_MEDIUM,
            is_reversible=True,
            rollback_tool_id="adjust_setpoint",
            parameters=[
                ToolParameter("equipment_id", "string", "Equipment identifier", required=True),
                ToolParameter("setpoint_name", "string", "Name of setpoint to adjust", required=True),
                ToolParameter("new_value", "number", "New setpoint value", required=True),
                ToolParameter("unit", "string", "Unit of measurement", required=True),
            ],
            cooldown_seconds=300,
            max_calls_per_hour=20,
        ),
        
        "adjust_staging": ToolSchema(
            tool_id="adjust_staging",
            name="Adjust Equipment Staging",
            description="Adjust staging/sequencing for multi-stage equipment",
            category=ToolCategory.BMS_COMMAND,
            risk_level=ActionRiskLevel.MEDIUM,
            requires_approval=True,
            is_reversible=True,
            parameters=[
                ToolParameter("equipment_id", "string", "Equipment identifier", required=True),
                ToolParameter("staging_mode", "enum", "Staging mode", enum_values=["auto", "manual", "lead-lag", "rotation"]),
                ToolParameter("active_stages", "number", "Number of active stages", required=False, min_value=0, max_value=10),
            ],
            cooldown_seconds=600,
        ),
        
        # Equipment control (high risk)
        "start_equipment": ToolSchema(
            tool_id="start_equipment",
            name="Start Equipment",
            description="Start equipment (pump, compressor, etc.)",
            category=ToolCategory.EQUIPMENT,
            risk_level=ActionRiskLevel.HIGH,
            requires_approval=True,
            approval_threshold=CasePriority.P2_HIGH,
            is_reversible=True,
            rollback_tool_id="stop_equipment",
            parameters=[
                ToolParameter("equipment_id", "string", "Equipment identifier", required=True),
                ToolParameter("startup_mode", "enum", "Startup mode", enum_values=["normal", "soft", "bypass"], required=False, default="normal"),
            ],
            cooldown_seconds=300,
            max_calls_per_hour=10,
        ),
        
        "stop_equipment": ToolSchema(
            tool_id="stop_equipment",
            name="Stop Equipment",
            description="Stop equipment (pump, compressor, etc.)",
            category=ToolCategory.EQUIPMENT,
            risk_level=ActionRiskLevel.HIGH,
            requires_approval=True,
            approval_threshold=CasePriority.P2_HIGH,
            is_reversible=True,
            rollback_tool_id="start_equipment",
            parameters=[
                ToolParameter("equipment_id", "string", "Equipment identifier", required=True),
                ToolParameter("shutdown_mode", "enum", "Shutdown mode", enum_values=["normal", "emergency", "graceful"], required=False, default="graceful"),
            ],
            cooldown_seconds=300,
        ),
        
        # Dispatch tools
        "dispatch_technician": ToolSchema(
            tool_id="dispatch_technician",
            name="Dispatch Technician",
            description="Dispatch field technician for onsite inspection/repair",
            category=ToolCategory.DISPATCH,
            risk_level=ActionRiskLevel.LOW,
            requires_approval=True,
            approval_threshold=CasePriority.P3_MEDIUM,
            parameters=[
                ToolParameter("site_id", "string", "Site identifier", required=True),
                ToolParameter("urgency", "enum", "Dispatch urgency", enum_values=["routine", "same_day", "urgent", "emergency"]),
                ToolParameter("skill_required", "string", "Required technician skill", required=True),
                ToolParameter("description", "string", "Work description", required=True),
                ToolParameter("case_id", "string", "Related case ID", required=False),
            ],
        ),
        
        "order_part": ToolSchema(
            tool_id="order_part",
            name="Order Replacement Part",
            description="Order replacement part for equipment",
            category=ToolCategory.DISPATCH,
            risk_level=ActionRiskLevel.LOW,
            parameters=[
                ToolParameter("part_number", "string", "Part number", required=True),
                ToolParameter("quantity", "number", "Quantity to order", required=True, min_value=1, max_value=100),
                ToolParameter("urgency", "enum", "Order urgency", enum_values=["standard", "expedited", "emergency"]),
                ToolParameter("equipment_id", "string", "Target equipment", required=False),
            ],
        ),
    }


# =============================================================================
# RBAC & Policy
# =============================================================================

@dataclass
class Role:
    """Role definition with permissions"""
    role_id: str
    name: str
    description: str
    
    # Tool access
    allowed_tools: Set[str] = field(default_factory=set)
    denied_tools: Set[str] = field(default_factory=set)
    
    # Autonomy
    max_autonomy_level: AutonomyLevel = AutonomyLevel.RECOMMEND_ONLY
    max_action_risk: ActionRiskLevel = ActionRiskLevel.LOW
    
    # Scope
    site_ids: Set[str] = field(default_factory=set)  # Empty = all sites
    equipment_ids: Set[str] = field(default_factory=set)  # Empty = all equipment


@dataclass
class SitePolicy:
    """Policy configuration for a specific site"""
    site_id: str
    customer_id: str
    
    # Autonomy level
    autonomy_level: AutonomyLevel = AutonomyLevel.RECOMMEND_ONLY
    
    # Action restrictions
    allowed_tool_categories: Set[ToolCategory] = field(default_factory=lambda: {
        ToolCategory.DIAGNOSTIC,
        ToolCategory.NOTIFICATION,
        ToolCategory.TICKETING,
    })
    
    # Time-based restrictions
    auto_execute_hours: tuple = (6, 22)  # Only auto-execute between 6 AM and 10 PM
    
    # Approval requirements
    require_human_approval_for: Set[ActionRiskLevel] = field(default_factory=lambda: {
        ActionRiskLevel.HIGH,
        ActionRiskLevel.CRITICAL,
    })
    
    # Safety overrides
    safety_interlock_enabled: bool = True
    emergency_stop_enabled: bool = True


class PolicyEngine:
    """
    Policy enforcement engine.
    Evaluates permissions, autonomy levels, and approval requirements.
    """
    
    def __init__(self):
        self.tools = get_standard_tools()
        self.roles: Dict[str, Role] = {}
        self.site_policies: Dict[str, SitePolicy] = {}
        
        # Default roles
        self._create_default_roles()
    
    def _create_default_roles(self):
        """Create default role definitions"""
        self.roles = {
            "observer": Role(
                role_id="observer",
                name="Observer",
                description="Read-only access to monitoring data",
                allowed_tools={"query_telemetry", "query_events", "query_maintenance_history"},
                max_autonomy_level=AutonomyLevel.OBSERVE_ONLY,
                max_action_risk=ActionRiskLevel.SAFE,
            ),
            "operator": Role(
                role_id="operator",
                name="Operator",
                description="Can monitor and create tickets",
                allowed_tools={
                    "query_telemetry", "query_events", "query_maintenance_history",
                    "send_notification", "create_ticket", "update_ticket",
                },
                max_autonomy_level=AutonomyLevel.RECOMMEND_ONLY,
                max_action_risk=ActionRiskLevel.LOW,
            ),
            "technician": Role(
                role_id="technician",
                name="Technician",
                description="Can adjust setpoints and control equipment",
                allowed_tools={
                    "query_telemetry", "query_events", "query_maintenance_history",
                    "send_notification", "create_ticket", "update_ticket",
                    "adjust_setpoint", "adjust_staging", "order_part",
                },
                max_autonomy_level=AutonomyLevel.AUTO_LOW_RISK,
                max_action_risk=ActionRiskLevel.MEDIUM,
            ),
            "supervisor": Role(
                role_id="supervisor",
                name="Supervisor",
                description="Full operational control with approval authority",
                allowed_tools=set(get_standard_tools().keys()),
                max_autonomy_level=AutonomyLevel.AUTO_MEDIUM_RISK,
                max_action_risk=ActionRiskLevel.HIGH,
            ),
        }
    
    def set_site_policy(self, policy: SitePolicy):
        """Set policy for a site"""
        self.site_policies[policy.site_id] = policy
    
    def can_execute_tool(
        self,
        tool_id: str,
        role_id: str,
        site_id: str,
        case_priority: CasePriority
    ) -> tuple[bool, str]:
        """
        Check if a tool can be executed given role and site policy.
        Returns (allowed, reason).
        """
        # Tool exists?
        if tool_id not in self.tools:
            return False, f"Unknown tool: {tool_id}"
        
        tool = self.tools[tool_id]
        
        # Role exists?
        if role_id not in self.roles:
            return False, f"Unknown role: {role_id}"
        
        role = self.roles[role_id]
        
        # Tool allowed for role?
        if tool_id in role.denied_tools:
            return False, f"Tool {tool_id} denied for role {role_id}"
        
        if role.allowed_tools and tool_id not in role.allowed_tools:
            return False, f"Tool {tool_id} not in allowed list for role {role_id}"
        
        # Risk level allowed?
        risk_order = [r for r in ActionRiskLevel]
        if risk_order.index(tool.risk_level) > risk_order.index(role.max_action_risk):
            return False, f"Tool risk level {tool.risk_level.value} exceeds role maximum {role.max_action_risk.value}"
        
        # Site policy
        policy = self.site_policies.get(site_id)
        if policy:
            # Category allowed?
            if tool.category not in policy.allowed_tool_categories:
                return False, f"Tool category {tool.category.value} not allowed for site {site_id}"
            
            # Time-based restriction
            current_hour = datetime.utcnow().hour
            if policy.auto_execute_hours:
                start, end = policy.auto_execute_hours
                if not (start <= current_hour < end):
                    if tool.risk_level in [ActionRiskLevel.MEDIUM, ActionRiskLevel.HIGH]:
                        return False, f"Auto-execution not allowed outside hours {start}-{end}"
        
        return True, "Allowed"
    
    def requires_approval(
        self,
        tool_id: str,
        site_id: str,
        case_priority: CasePriority
    ) -> tuple[bool, str]:
        """Check if tool execution requires human approval"""
        if tool_id not in self.tools:
            return True, "Unknown tool requires approval"
        
        tool = self.tools[tool_id]
        
        # Tool-level requirement
        if tool.requires_approval:
            # Check if case priority meets threshold
            priority_order = list(CasePriority)
            if priority_order.index(case_priority) >= priority_order.index(tool.approval_threshold):
                return True, f"Tool requires approval for priority {case_priority.value}"
        
        # Site policy requirement
        policy = self.site_policies.get(site_id)
        if policy:
            if tool.risk_level in policy.require_human_approval_for:
                return True, f"Site policy requires approval for {tool.risk_level.value} risk actions"
        
        return False, "No approval required"


# =============================================================================
# Audit Logging
# =============================================================================

@dataclass
class AuditEntry:
    """Audit log entry"""
    entry_id: str
    timestamp: datetime
    
    # What
    action_type: str  # tool_call, state_change, approval, escalation
    tool_id: Optional[str] = None
    
    # Who
    actor_type: str = "agent"  # agent, human, system
    actor_id: str = ""
    role_id: Optional[str] = None
    
    # Where
    site_id: Optional[str] = None
    case_id: Optional[str] = None
    
    # Details
    parameters: Dict[str, Any] = field(default_factory=dict)
    result: Optional[str] = None
    error: Optional[str] = None
    
    # Outcome
    success: bool = True
    duration_ms: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp.isoformat(),
            "action_type": self.action_type,
            "tool_id": self.tool_id,
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
            "site_id": self.site_id,
            "case_id": self.case_id,
            "success": self.success,
        }


class AuditLogger:
    """
    Audit logging for all agent actions.
    Provides full traceability per NIST AI RMF requirements.
    """
    
    def __init__(self, max_entries: int = 100000):
        self.entries: List[AuditEntry] = []
        self.max_entries = max_entries
    
    def log(
        self,
        action_type: str,
        actor_id: str,
        actor_type: str = "agent",
        tool_id: Optional[str] = None,
        site_id: Optional[str] = None,
        case_id: Optional[str] = None,
        parameters: Dict[str, Any] = None,
        result: Optional[str] = None,
        error: Optional[str] = None,
        success: bool = True,
        duration_ms: int = 0,
    ) -> AuditEntry:
        """Log an audit entry"""
        entry = AuditEntry(
            entry_id=hashlib.md5(f"{datetime.utcnow().isoformat()}_{actor_id}".encode()).hexdigest()[:12],
            timestamp=datetime.utcnow(),
            action_type=action_type,
            tool_id=tool_id,
            actor_type=actor_type,
            actor_id=actor_id,
            site_id=site_id,
            case_id=case_id,
            parameters=parameters or {},
            result=result,
            error=error,
            success=success,
            duration_ms=duration_ms,
        )
        
        self.entries.append(entry)
        
        # Prune old entries
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]
        
        # Log to standard logger
        log_msg = f"AUDIT: {action_type} by {actor_id}"
        if tool_id:
            log_msg += f" tool={tool_id}"
        if case_id:
            log_msg += f" case={case_id}"
        if not success:
            log_msg += f" ERROR: {error}"
        
        logger.info(log_msg)
        
        return entry
    
    def get_entries(
        self,
        case_id: Optional[str] = None,
        site_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> List[AuditEntry]:
        """Query audit entries"""
        result = self.entries
        
        if case_id:
            result = [e for e in result if e.case_id == case_id]
        if site_id:
            result = [e for e in result if e.site_id == site_id]
        if actor_id:
            result = [e for e in result if e.actor_id == actor_id]
        if since:
            result = [e for e in result if e.timestamp >= since]
        
        return result


# =============================================================================
# Output Validation
# =============================================================================

class OutputValidator:
    """
    Validates and sanitizes agent outputs before passing to downstream systems.
    Prevents insecure output handling per OWASP guidelines.
    """
    
    def __init__(self):
        # Patterns to detect/sanitize
        self.dangerous_patterns = [
            r'<script[^>]*>.*?</script>',  # XSS
            r'javascript:',
            r'on\w+\s*=',  # Event handlers
            r'\${.*}',  # Template injection
            r'{{.*}}',  # Template injection
        ]
        
        # Max lengths
        self.max_message_length = 10000
        self.max_param_length = 1000
    
    def sanitize_string(self, value: str) -> str:
        """Sanitize a string value"""
        if not isinstance(value, str):
            return str(value)
        
        # Truncate
        if len(value) > self.max_message_length:
            value = value[:self.max_message_length] + "..."
        
        # Remove dangerous patterns
        import re
        for pattern in self.dangerous_patterns:
            value = re.sub(pattern, '[REMOVED]', value, flags=re.IGNORECASE | re.DOTALL)
        
        return value
    
    def validate_tool_output(
        self,
        tool_id: str,
        output: Dict[str, Any]
    ) -> tuple[bool, Dict[str, Any], List[str]]:
        """
        Validate tool output.
        Returns (is_valid, sanitized_output, warnings).
        """
        warnings = []
        sanitized = {}
        
        for key, value in output.items():
            if isinstance(value, str):
                sanitized_value = self.sanitize_string(value)
                if sanitized_value != value:
                    warnings.append(f"Sanitized field {key}")
                sanitized[key] = sanitized_value
            elif isinstance(value, dict):
                _, nested_sanitized, nested_warnings = self.validate_tool_output(tool_id, value)
                sanitized[key] = nested_sanitized
                warnings.extend(nested_warnings)
            elif isinstance(value, list):
                sanitized_list = []
                for item in value:
                    if isinstance(item, str):
                        sanitized_list.append(self.sanitize_string(item))
                    elif isinstance(item, dict):
                        _, nested_sanitized, _ = self.validate_tool_output(tool_id, item)
                        sanitized_list.append(nested_sanitized)
                    else:
                        sanitized_list.append(item)
                sanitized[key] = sanitized_list
            else:
                sanitized[key] = value
        
        return True, sanitized, warnings

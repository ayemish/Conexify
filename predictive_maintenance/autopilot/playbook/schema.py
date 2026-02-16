"""
Playbook Schema Definitions

Defines the structure of playbook definitions and JSON schema for validation.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class OnFailAction(str, Enum):
    """Action when precondition fails"""
    BLOCK = "BLOCK"
    TICKET_ONLY = "TICKET_ONLY"
    ESCALATE = "ESCALATE"


class OnErrorAction(str, Enum):
    """Action when step errors"""
    RETRY = "RETRY"
    SKIP = "SKIP"
    ESCALATE = "ESCALATE"
    ABORT = "ABORT"


class StepType(str, Enum):
    """Types of playbook steps"""
    READ = "READ"
    WRITE_POINT = "WRITE_POINT"
    CREATE_TICKET = "CREATE_TICKET"
    UPDATE_TICKET = "UPDATE_TICKET"
    NOTIFY = "NOTIFY"
    WAIT = "WAIT"
    COMPUTE = "COMPUTE"
    RUN_TEST = "RUN_TEST"
    ESCALATE = "ESCALATE"


@dataclass
class PlaybookTrigger:
    """Trigger condition for playbook activation"""
    expr: str
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {"expr": self.expr, "description": self.description}


@dataclass
class PlaybookPrecondition:
    """Precondition that must be met before execution"""
    expr: str
    on_fail: OnFailAction = OnFailAction.BLOCK
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "expr": self.expr,
            "on_fail": self.on_fail.value,
            "description": self.description,
        }


@dataclass
class PlaybookStep:
    """Individual step in a playbook"""
    id: str
    type: StepType
    params: Dict[str, Any] = field(default_factory=dict)
    requires_approval: bool = False
    on_error: OnErrorAction = OnErrorAction.ESCALATE
    description: str = ""
    timeout_seconds: int = 300
    retry_count: int = 0
    max_retries: int = 3
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "params": self.params,
            "requires_approval": self.requires_approval,
            "on_error": self.on_error.value,
            "description": self.description,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass
class PlaybookVerification:
    """Verification check after execution"""
    expr: str
    window_sec: int = 900  # 15 minutes
    must_hold: bool = True
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "expr": self.expr,
            "window_sec": self.window_sec,
            "must_hold": self.must_hold,
            "description": self.description,
        }


@dataclass
class PlaybookEscalation:
    """Escalation configuration"""
    create_ticket: bool = True
    priority: str = "P2"
    notify_roles: List[str] = field(default_factory=list)
    vendor_dispatch: bool = False
    call_tree: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "create_ticket": self.create_ticket,
            "priority": self.priority,
            "notify_roles": self.notify_roles,
            "vendor_dispatch": self.vendor_dispatch,
            "call_tree": self.call_tree,
        }


@dataclass
class PlaybookEvidence:
    """Evidence capture requirements"""
    capture_windows_sec: Dict[str, int] = field(default_factory=lambda: {"before": 3600, "after": 3600})
    required_points: List[str] = field(default_factory=list)
    include_regime_history: bool = True
    include_alert_history: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "capture_windows_sec": self.capture_windows_sec,
            "required_points": self.required_points,
            "include_regime_history": self.include_regime_history,
            "include_alert_history": self.include_alert_history,
        }


@dataclass
class PlaybookDefinition:
    """
    Complete playbook definition.
    
    A playbook defines a templated remediation procedure for a specific
    asset class and fault type combination.
    """
    id: str
    version: str
    name: str
    asset_class: str
    fault_type: str
    risk_tier: str = "MEDIUM"  # LOW, MEDIUM, HIGH
    
    # Activation
    triggers: List[PlaybookTrigger] = field(default_factory=list)
    preconditions: List[PlaybookPrecondition] = field(default_factory=list)
    
    # Execution
    steps: List[PlaybookStep] = field(default_factory=list)
    
    # Post-execution
    verification: List[PlaybookVerification] = field(default_factory=list)
    escalation: PlaybookEscalation = field(default_factory=PlaybookEscalation)
    evidence: PlaybookEvidence = field(default_factory=PlaybookEvidence)
    
    # Metadata
    description: str = ""
    author: str = ""
    tags: List[str] = field(default_factory=list)
    
    # Lifecycle
    effective_from: Optional[datetime] = None
    retired_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "name": self.name,
            "asset_class": self.asset_class,
            "fault_type": self.fault_type,
            "risk_tier": self.risk_tier,
            "triggers": [t.to_dict() for t in self.triggers],
            "preconditions": [p.to_dict() for p in self.preconditions],
            "steps": [s.to_dict() for s in self.steps],
            "verification": [v.to_dict() for v in self.verification],
            "escalation": self.escalation.to_dict(),
            "evidence": self.evidence.to_dict(),
            "description": self.description,
            "author": self.author,
            "tags": self.tags,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlaybookDefinition":
        """Create a PlaybookDefinition from a dictionary"""
        triggers = [
            PlaybookTrigger(
                expr=t.get("expr", ""),
                description=t.get("description", ""),
            )
            for t in data.get("triggers", [])
        ]
        
        preconditions = [
            PlaybookPrecondition(
                expr=p.get("expr", ""),
                on_fail=OnFailAction(p.get("on_fail", "BLOCK")),
                description=p.get("description", ""),
            )
            for p in data.get("preconditions", [])
        ]
        
        steps = [
            PlaybookStep(
                id=s.get("id", f"step_{i}"),
                type=StepType(s.get("type", "READ")),
                params=s.get("params", {}),
                requires_approval=s.get("requires_approval", False),
                on_error=OnErrorAction(s.get("on_error", "ESCALATE")),
                description=s.get("description", ""),
                timeout_seconds=s.get("timeout_seconds", 300),
            )
            for i, s in enumerate(data.get("steps", []))
        ]
        
        verification = [
            PlaybookVerification(
                expr=v.get("expr", ""),
                window_sec=v.get("window_sec", 900),
                must_hold=v.get("must_hold", True),
                description=v.get("description", ""),
            )
            for v in data.get("verification", [])
        ]
        
        esc_data = data.get("escalation", {})
        escalation = PlaybookEscalation(
            create_ticket=esc_data.get("create_ticket", True),
            priority=esc_data.get("priority", "P2"),
            notify_roles=esc_data.get("notify_roles", []),
            vendor_dispatch=esc_data.get("vendor_dispatch", False),
            call_tree=esc_data.get("call_tree", []),
        )
        
        evd_data = data.get("evidence", {})
        evidence = PlaybookEvidence(
            capture_windows_sec=evd_data.get("capture_windows_sec", {"before": 3600, "after": 3600}),
            required_points=evd_data.get("required_points", []),
            include_regime_history=evd_data.get("include_regime_history", True),
            include_alert_history=evd_data.get("include_alert_history", True),
        )
        
        return cls(
            id=data.get("id", f"pb_{uuid.uuid4().hex[:8]}"),
            version=data.get("version", "1.0.0"),
            name=data.get("name", "Unnamed Playbook"),
            asset_class=data.get("asset_class", "OTHER"),
            fault_type=data.get("fault_type", "unknown"),
            risk_tier=data.get("risk_tier", "MEDIUM"),
            triggers=triggers,
            preconditions=preconditions,
            steps=steps,
            verification=verification,
            escalation=escalation,
            evidence=evidence,
            description=data.get("description", ""),
            author=data.get("author", ""),
            tags=data.get("tags", []),
        )


# JSON Schema for playbook validation
PLAYBOOK_JSON_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["id", "version", "name", "asset_class", "fault_type", "steps"],
    "properties": {
        "id": {"type": "string", "pattern": "^[a-zA-Z0-9_-]+$"},
        "version": {"type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$"},
        "name": {"type": "string", "minLength": 1, "maxLength": 200},
        "asset_class": {
            "type": "string",
            "enum": ["HVAC", "REFRIGERATION", "LIGHTING", "ELECTRICAL", "PLUMBING", "OTHER"]
        },
        "fault_type": {"type": "string", "minLength": 1},
        "risk_tier": {
            "type": "string",
            "enum": ["LOW", "MEDIUM", "HIGH"],
            "default": "MEDIUM"
        },
        "triggers": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["expr"],
                "properties": {
                    "expr": {"type": "string"},
                    "description": {"type": "string"}
                }
            }
        },
        "preconditions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["expr"],
                "properties": {
                    "expr": {"type": "string"},
                    "on_fail": {
                        "type": "string",
                        "enum": ["BLOCK", "TICKET_ONLY", "ESCALATE"],
                        "default": "BLOCK"
                    },
                    "description": {"type": "string"}
                }
            }
        },
        "steps": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["id", "type"],
                "properties": {
                    "id": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": ["READ", "WRITE_POINT", "CREATE_TICKET", "UPDATE_TICKET", 
                                 "NOTIFY", "WAIT", "COMPUTE", "RUN_TEST", "ESCALATE"]
                    },
                    "params": {"type": "object"},
                    "requires_approval": {"type": "boolean", "default": False},
                    "on_error": {
                        "type": "string",
                        "enum": ["RETRY", "SKIP", "ESCALATE", "ABORT"],
                        "default": "ESCALATE"
                    },
                    "description": {"type": "string"},
                    "timeout_seconds": {"type": "integer", "minimum": 1, "default": 300}
                }
            }
        },
        "verification": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["expr"],
                "properties": {
                    "expr": {"type": "string"},
                    "window_sec": {"type": "integer", "minimum": 60, "default": 900},
                    "must_hold": {"type": "boolean", "default": True},
                    "description": {"type": "string"}
                }
            }
        },
        "escalation": {
            "type": "object",
            "properties": {
                "create_ticket": {"type": "boolean", "default": True},
                "priority": {
                    "type": "string",
                    "enum": ["P1", "P2", "P3", "P4"],
                    "default": "P2"
                },
                "notify_roles": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "vendor_dispatch": {"type": "boolean", "default": False},
                "call_tree": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            }
        },
        "evidence": {
            "type": "object",
            "properties": {
                "capture_windows_sec": {
                    "type": "object",
                    "properties": {
                        "before": {"type": "integer", "minimum": 0, "default": 3600},
                        "after": {"type": "integer", "minimum": 0, "default": 3600}
                    }
                },
                "required_points": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "include_regime_history": {"type": "boolean", "default": True},
                "include_alert_history": {"type": "boolean", "default": True}
            }
        },
        "description": {"type": "string"},
        "author": {"type": "string"},
        "tags": {
            "type": "array",
            "items": {"type": "string"}
        }
    }
}

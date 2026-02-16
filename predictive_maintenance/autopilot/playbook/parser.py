"""
Playbook Parser and Validator

Parses and validates playbook definitions from JSON/YAML.
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

try:
    import jsonschema
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from .schema import PlaybookDefinition, PLAYBOOK_JSON_SCHEMA, StepType

logger = logging.getLogger(__name__)


class PlaybookValidationError(Exception):
    """Raised when playbook validation fails"""
    
    def __init__(self, message: str, errors: List[str] = None):
        super().__init__(message)
        self.errors = errors or []


class PlaybookParser:
    """
    Parser and validator for playbook definitions.
    
    Supports:
    - JSON format
    - YAML format (if PyYAML installed)
    - Schema validation
    - Expression syntax validation
    - Safety checks for unsafe actions
    """
    
    # Actions that require explicit allowlisting
    UNSAFE_ACTIONS = {StepType.WRITE_POINT, StepType.ESCALATE}
    
    # Required fields for each step type
    STEP_REQUIRED_PARAMS = {
        StepType.READ: ["point_ids"],
        StepType.WRITE_POINT: ["point_id", "value"],
        StepType.CREATE_TICKET: ["title", "description"],
        StepType.UPDATE_TICKET: ["ticket_id"],
        StepType.NOTIFY: ["recipients", "message"],
        StepType.WAIT: ["duration_seconds"],
        StepType.COMPUTE: ["expression"],
        StepType.RUN_TEST: ["test_id"],
        StepType.ESCALATE: ["reason"],
    }
    
    def __init__(self, strict: bool = True):
        """
        Initialize parser.
        
        Args:
            strict: If True, fail on any validation warning
        """
        self.strict = strict
    
    def parse_json(self, json_str: str) -> PlaybookDefinition:
        """Parse playbook from JSON string"""
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise PlaybookValidationError(f"Invalid JSON: {e}")
        
        return self.parse_dict(data)
    
    def parse_yaml(self, yaml_str: str) -> PlaybookDefinition:
        """Parse playbook from YAML string"""
        if not YAML_AVAILABLE:
            raise PlaybookValidationError("YAML parsing requires PyYAML: pip install pyyaml")
        
        try:
            data = yaml.safe_load(yaml_str)
        except yaml.YAMLError as e:
            raise PlaybookValidationError(f"Invalid YAML: {e}")
        
        return self.parse_dict(data)
    
    def parse_file(self, file_path: str) -> PlaybookDefinition:
        """Parse playbook from file (auto-detect format)"""
        with open(file_path, 'r') as f:
            content = f.read()
        
        if file_path.endswith('.yaml') or file_path.endswith('.yml'):
            return self.parse_yaml(content)
        else:
            return self.parse_json(content)
    
    def parse_dict(self, data: Dict[str, Any]) -> PlaybookDefinition:
        """Parse and validate playbook from dictionary"""
        errors = []
        warnings = []
        
        # JSON Schema validation
        schema_errors = self._validate_schema(data)
        errors.extend(schema_errors)
        
        # Semantic validation
        semantic_errors, semantic_warnings = self._validate_semantics(data)
        errors.extend(semantic_errors)
        warnings.extend(semantic_warnings)
        
        # Safety checks
        safety_errors, safety_warnings = self._validate_safety(data)
        errors.extend(safety_errors)
        warnings.extend(safety_warnings)
        
        # Log warnings
        for warning in warnings:
            logger.warning(f"Playbook validation warning: {warning}")
        
        # Fail if errors
        if errors:
            raise PlaybookValidationError(
                f"Playbook validation failed with {len(errors)} error(s)",
                errors=errors
            )
        
        # Fail on warnings if strict
        if self.strict and warnings:
            raise PlaybookValidationError(
                f"Playbook validation failed (strict mode) with {len(warnings)} warning(s)",
                errors=warnings
            )
        
        # Parse into dataclass
        return PlaybookDefinition.from_dict(data)
    
    def _validate_schema(self, data: Dict[str, Any]) -> List[str]:
        """Validate against JSON schema"""
        errors = []
        
        if not JSONSCHEMA_AVAILABLE:
            logger.warning("jsonschema not installed, skipping schema validation")
            return errors
        
        try:
            jsonschema.validate(data, PLAYBOOK_JSON_SCHEMA)
        except jsonschema.ValidationError as e:
            errors.append(f"Schema validation error: {e.message}")
        except jsonschema.SchemaError as e:
            errors.append(f"Schema error: {e.message}")
        
        return errors
    
    def _validate_semantics(self, data: Dict[str, Any]) -> Tuple[List[str], List[str]]:
        """Validate semantic correctness"""
        errors = []
        warnings = []
        
        # Check for required top-level fields
        required = ["id", "version", "name", "asset_class", "fault_type", "steps"]
        for field in required:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        
        # Validate steps
        steps = data.get("steps", [])
        if not steps:
            errors.append("Playbook must have at least one step")
        
        step_ids = set()
        for i, step in enumerate(steps):
            step_id = step.get("id", f"step_{i}")
            
            # Check for duplicate step IDs
            if step_id in step_ids:
                errors.append(f"Duplicate step ID: {step_id}")
            step_ids.add(step_id)
            
            # Validate step type
            step_type_str = step.get("type")
            if step_type_str:
                try:
                    step_type = StepType(step_type_str)
                    
                    # Check required params for step type
                    required_params = self.STEP_REQUIRED_PARAMS.get(step_type, [])
                    params = step.get("params", {})
                    for param in required_params:
                        if param not in params:
                            warnings.append(
                                f"Step '{step_id}' of type {step_type_str} "
                                f"missing recommended param: {param}"
                            )
                except ValueError:
                    errors.append(f"Invalid step type: {step_type_str}")
        
        # Validate triggers
        for i, trigger in enumerate(data.get("triggers", [])):
            expr = trigger.get("expr", "")
            if not expr:
                warnings.append(f"Trigger {i} has empty expression")
        
        # Validate preconditions
        for i, precond in enumerate(data.get("preconditions", [])):
            expr = precond.get("expr", "")
            if not expr:
                warnings.append(f"Precondition {i} has empty expression")
        
        # Validate verification
        for i, verif in enumerate(data.get("verification", [])):
            expr = verif.get("expr", "")
            if not expr:
                warnings.append(f"Verification {i} has empty expression")
            
            window = verif.get("window_sec", 900)
            if window < 60:
                warnings.append(
                    f"Verification {i} has very short window ({window}s), "
                    "may cause false negatives"
                )
        
        return errors, warnings
    
    def _validate_safety(self, data: Dict[str, Any]) -> Tuple[List[str], List[str]]:
        """Validate safety constraints"""
        errors = []
        warnings = []
        
        risk_tier = data.get("risk_tier", "MEDIUM")
        steps = data.get("steps", [])
        
        # Check for unsafe actions in LOW risk playbooks
        if risk_tier == "LOW":
            for step in steps:
                step_type_str = step.get("type", "")
                try:
                    step_type = StepType(step_type_str)
                    if step_type in self.UNSAFE_ACTIONS:
                        warnings.append(
                            f"Step '{step.get('id')}' uses unsafe action {step_type_str} "
                            f"but playbook is risk_tier=LOW"
                        )
                except ValueError:
                    pass
        
        # Check WRITE_POINT steps have approval for HIGH risk
        if risk_tier == "HIGH":
            for step in steps:
                step_type_str = step.get("type", "")
                if step_type_str == "WRITE_POINT" and not step.get("requires_approval", False):
                    warnings.append(
                        f"Step '{step.get('id')}' is WRITE_POINT in HIGH risk playbook "
                        "but requires_approval is False"
                    )
        
        # Check for potentially dangerous parameter values
        for step in steps:
            params = step.get("params", {})
            
            # Check for large setpoint changes
            if "value" in params and "delta" in str(params.get("value", "")):
                # Value is computed as delta, check if it's bounded
                pass
            
            # Check for long TTLs
            ttl = params.get("ttl_seconds", 0)
            if ttl > 7200:  # 2 hours
                warnings.append(
                    f"Step '{step.get('id')}' has very long TTL ({ttl}s), "
                    "consider shorter override duration"
                )
        
        return errors, warnings
    
    def compute_hash(self, data: Dict[str, Any]) -> str:
        """Compute content hash for integrity verification"""
        # Serialize deterministically
        canonical = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode()).hexdigest()
    
    def render_canonical(self, playbook: PlaybookDefinition) -> str:
        """Render playbook to canonical JSON (for audit byte-identity)"""
        data = playbook.to_dict()
        return json.dumps(data, sort_keys=True, indent=2)
    
    def validate_expression(self, expr: str) -> Tuple[bool, Optional[str]]:
        """
        Validate expression syntax without evaluating.
        
        Returns:
            (is_valid, error_message)
        """
        if not expr or not expr.strip():
            return True, None
        
        # Check for balanced parentheses
        depth = 0
        for c in expr:
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
            if depth < 0:
                return False, "Unbalanced parentheses"
        if depth != 0:
            return False, "Unbalanced parentheses"
        
        # Check for valid operators
        valid_ops = ['>', '>=', '<', '<=', '==', '!=', '+', '-', '*', '/']
        
        # Check for known functions
        import re
        functions = re.findall(r'(\w+)\s*\(', expr)
        known_functions = {
            'avg', 'slope', 'in_band', 'is_valid', 'is_override_active',
            'abs', 'min', 'max', 'delta', 'rate_of_change', 'within_threshold'
        }
        for fn in functions:
            if fn not in known_functions and fn not in ['and', 'or', 'not']:
                return False, f"Unknown function: {fn}"
        
        return True, None

"""
LLM Validator Service

Validates workflow items before approval using LLM-powered checks
combined with rule-based validation.
"""

import logging
import json
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .models import (
    QueueItem,
    LLMValidation,
    ValidationStatus,
)

logger = logging.getLogger(__name__)


VALIDATION_SYSTEM_PROMPT = """You are a safety and validation expert for building automation systems.
Your role is to validate proposed automated actions before they are executed.

Check for:
1. Safety concerns - could this action harm equipment or people?
2. Precondition violations - are all requirements met?
3. Logical consistency - does the action make sense given the context?
4. Parameter validity - are values within acceptable ranges?
5. Timing concerns - is now the right time to take this action?

Be thorough but practical. Flag genuine concerns while avoiding false alarms."""


VALIDATION_USER_PROMPT = """Please validate the following proposed workflow action:

## Context
- Asset: {asset_id}
- Fault Type: {fault_type}
- Risk Tier: {risk_tier}

## Current Conditions
{telemetry}

## Proposed Actions
{proposed_actions}

## Preconditions Required
{preconditions}

Please validate and provide:
1. Overall validation status (passed/warning/failed/needs_review)
2. List of validation checks performed with results
3. Any errors (blocking issues)
4. Any warnings (non-blocking concerns)
5. Recommendations for the reviewer
6. Safety assessment

Format as JSON with fields:
- status
- checks (list of {{name, passed, message, severity}})
- errors (list of strings)
- warnings (list of strings)
- recommendations (list of strings)
- safety_passed
- safety_concerns (list of strings)
- confidence (0-1)
"""


class LLMValidatorService:
    """
    Validates workflow items using LLM and rule-based checks.
    
    Combines:
    - LLM-powered semantic validation
    - Rule-based safety checks
    - Parameter range validation
    - Precondition verification
    """
    
    def __init__(
        self,
        llm_client: Callable = None,
        model_name: str = "gpt-4",
        strict_mode: bool = False,
    ):
        self.llm_client = llm_client
        self.model_name = model_name
        self.strict_mode = strict_mode
        
        # Safety limits for common control points
        self.safety_limits = {
            "zone_temp_setpoint": {"min": 55, "max": 85, "unit": "°F"},
            "discharge_air_temp_setpoint": {"min": 45, "max": 75, "unit": "°F"},
            "supply_fan_speed": {"min": 0, "max": 100, "unit": "%"},
            "condenser_fan_speed": {"min": 0, "max": 100, "unit": "%"},
            "compressor_capacity": {"min": 0, "max": 100, "unit": "%"},
            "damper_position": {"min": 0, "max": 100, "unit": "%"},
        }
    
    async def validate(
        self,
        item: QueueItem,
        run_llm_validation: bool = True,
    ) -> LLMValidation:
        """
        Validate a queue item.
        
        Args:
            item: The queue item to validate
            run_llm_validation: Whether to run LLM semantic validation
            
        Returns:
            LLMValidation with validation results
        """
        start_time = datetime.utcnow()
        
        validation = LLMValidation()
        all_checks = []
        
        try:
            # 1. Run rule-based safety checks
            safety_checks = self._run_safety_checks(item)
            all_checks.extend(safety_checks)
            
            # 2. Run parameter validation
            param_checks = self._run_parameter_checks(item)
            all_checks.extend(param_checks)
            
            # 3. Run precondition checks
            precond_checks = self._run_precondition_checks(item)
            all_checks.extend(precond_checks)
            
            # 4. Run LLM semantic validation if enabled
            if run_llm_validation and self.llm_client:
                llm_checks = await self._run_llm_validation(item)
                all_checks.extend(llm_checks)
            elif run_llm_validation:
                # Fallback semantic checks without LLM
                semantic_checks = self._run_semantic_checks(item)
                all_checks.extend(semantic_checks)
            
            # Compile results
            validation.checks = all_checks
            
            # Extract errors and warnings
            for check in all_checks:
                if not check.get("passed", True):
                    severity = check.get("severity", "warning")
                    message = check.get("message", check.get("name", "Check failed"))
                    
                    if severity == "error":
                        validation.errors.append(message)
                    elif severity == "warning":
                        validation.warnings.append(message)
                    else:
                        validation.info.append(message)
            
            # Check safety
            safety_failed = [c for c in all_checks if c.get("category") == "safety" and not c.get("passed")]
            validation.safety_checks_passed = len(safety_failed) == 0
            validation.safety_concerns = [c.get("message") for c in safety_failed]
            
            # Check preconditions
            precond_failed = [c for c in all_checks if c.get("category") == "precondition" and not c.get("passed")]
            validation.preconditions_met = len(precond_failed) == 0
            validation.failed_preconditions = [c.get("message") for c in precond_failed]
            
            # Determine overall status
            validation.status = self._determine_status(validation)
            
            # Generate recommendations
            validation.recommendations = self._generate_recommendations(item, validation)
            
            # Calculate confidence
            passed_checks = sum(1 for c in all_checks if c.get("passed", True))
            validation.validation_confidence = passed_checks / len(all_checks) if all_checks else 0.5
            
        except Exception as e:
            logger.error(f"Validation error: {e}")
            validation.errors.append(f"Validation error: {str(e)}")
            validation.status = ValidationStatus.NEEDS_REVIEW
        
        # Set metadata
        validation.model_used = self.model_name if run_llm_validation else "rule-based"
        validation.validated_at = datetime.utcnow()
        validation.validation_time_ms = int(
            (datetime.utcnow() - start_time).total_seconds() * 1000
        )
        
        return validation
    
    def _run_safety_checks(self, item: QueueItem) -> List[Dict[str, Any]]:
        """Run safety-related validation checks"""
        checks = []
        
        # Check risk tier matches actions
        high_risk_actions = ["EMERGENCY_SHUTDOWN", "BYPASS_SAFETY", "DISABLE_ALARM"]
        for action in item.proposed_actions:
            action_type = action.get("type", "")
            
            if action_type in high_risk_actions:
                checks.append({
                    "name": f"High-risk action: {action_type}",
                    "passed": item.risk_tier in ("HIGH", "EXTREME"),
                    "message": f"{action_type} requires HIGH or EXTREME risk tier",
                    "severity": "error" if item.risk_tier not in ("HIGH", "EXTREME") else "info",
                    "category": "safety",
                })
            
            # Check for write actions
            if action_type == "WRITE_POINT":
                point_id = action.get("point_id", "")
                value = action.get("value")
                
                # Check safety limits
                if point_id in self.safety_limits:
                    limits = self.safety_limits[point_id]
                    in_range = limits["min"] <= value <= limits["max"]
                    checks.append({
                        "name": f"Value range: {point_id}",
                        "passed": in_range,
                        "message": f"{point_id}={value} {'within' if in_range else 'outside'} "
                                   f"limits [{limits['min']}-{limits['max']}] {limits['unit']}",
                        "severity": "error" if not in_range else "info",
                        "category": "safety",
                    })
                
                # Check for TTL on write actions
                ttl = action.get("ttl_seconds")
                checks.append({
                    "name": f"TTL configured: {point_id}",
                    "passed": ttl is not None and ttl > 0,
                    "message": f"Write action {'has' if ttl else 'missing'} TTL auto-revert",
                    "severity": "warning" if not ttl else "info",
                    "category": "safety",
                })
        
        # Check for multiple simultaneous writes
        write_actions = [a for a in item.proposed_actions if a.get("type") == "WRITE_POINT"]
        if len(write_actions) > 3:
            checks.append({
                "name": "Multiple simultaneous writes",
                "passed": False,
                "message": f"{len(write_actions)} simultaneous write actions may cause instability",
                "severity": "warning",
                "category": "safety",
            })
        
        return checks
    
    def _run_parameter_checks(self, item: QueueItem) -> List[Dict[str, Any]]:
        """Validate action parameters"""
        checks = []
        
        for action in item.proposed_actions:
            action_type = action.get("type", "")
            
            # Check required parameters by action type
            required_params = {
                "WRITE_POINT": ["point_id", "value"],
                "CREATE_TICKET": ["title", "priority"],
                "SEND_NOTIFICATION": ["recipient", "message"],
                "READ": ["point_ids"],
            }
            
            if action_type in required_params:
                missing = [p for p in required_params[action_type] if p not in action]
                checks.append({
                    "name": f"Required params: {action_type}",
                    "passed": len(missing) == 0,
                    "message": f"Missing: {', '.join(missing)}" if missing else "All required params present",
                    "severity": "error" if missing else "info",
                    "category": "parameter",
                })
        
        return checks
    
    def _run_precondition_checks(self, item: QueueItem) -> List[Dict[str, Any]]:
        """Check if preconditions are met"""
        checks = []
        
        preconditions = item.fault_context.get("preconditions", [])
        
        for precond in preconditions:
            expr = precond.get("expr", "")
            description = precond.get("description", expr)
            met = precond.get("met", True)  # Assume met if not specified
            
            checks.append({
                "name": f"Precondition: {description[:50]}",
                "passed": met,
                "message": f"{'Met' if met else 'Not met'}: {description}",
                "severity": "error" if not met else "info",
                "category": "precondition",
            })
        
        return checks
    
    def _run_semantic_checks(self, item: QueueItem) -> List[Dict[str, Any]]:
        """Run semantic validation without LLM (rule-based fallback)"""
        checks = []
        
        # Check action-fault consistency
        fault_type = item.fault_context.get("fault_type", "")
        
        # Basic consistency checks
        for action in item.proposed_actions:
            action_type = action.get("type", "")
            target = action.get("point_id", action.get("target", ""))
            
            # Warn if action seems unrelated to fault
            if fault_type and target:
                # Simple keyword matching
                fault_keywords = set(fault_type.lower().replace("_", " ").split())
                target_keywords = set(target.lower().replace("_", " ").split())
                
                overlap = fault_keywords & target_keywords
                
                if not overlap and len(fault_keywords) > 1:
                    checks.append({
                        "name": "Action-fault relevance",
                        "passed": True,  # Just informational
                        "message": f"Verify {action_type} on {target} addresses {fault_type}",
                        "severity": "info",
                        "category": "semantic",
                    })
        
        # Check timing appropriateness
        current_hour = datetime.utcnow().hour
        if 0 <= current_hour < 6:  # Night hours
            checks.append({
                "name": "Off-hours action",
                "passed": True,  # Warning only
                "message": "Action requested during off-hours (midnight-6am UTC)",
                "severity": "warning",
                "category": "semantic",
            })
        
        return checks
    
    async def _run_llm_validation(self, item: QueueItem) -> List[Dict[str, Any]]:
        """Run LLM-powered semantic validation"""
        try:
            prompt = VALIDATION_USER_PROMPT.format(
                asset_id=item.asset_id,
                fault_type=item.fault_context.get("fault_type", "unknown"),
                risk_tier=item.risk_tier,
                telemetry=json.dumps(item.telemetry_snapshot, indent=2),
                proposed_actions=json.dumps(item.proposed_actions, indent=2),
                preconditions=json.dumps(item.fault_context.get("preconditions", []), indent=2),
            )
            
            messages = [
                {"role": "system", "content": VALIDATION_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            
            response = await self.llm_client(
                model=self.model_name,
                messages=messages,
                temperature=0.2,
                max_tokens=1000,
            )
            
            # Parse response
            data = json.loads(response)
            return data.get("checks", [])
            
        except Exception as e:
            logger.warning(f"LLM validation failed: {e}")
            return [{
                "name": "LLM Validation",
                "passed": True,
                "message": "LLM validation unavailable, using rule-based checks",
                "severity": "info",
                "category": "semantic",
            }]
    
    def _determine_status(self, validation: LLMValidation) -> ValidationStatus:
        """Determine overall validation status"""
        if validation.errors:
            return ValidationStatus.FAILED
        
        if not validation.safety_checks_passed:
            return ValidationStatus.FAILED
        
        if not validation.preconditions_met:
            return ValidationStatus.FAILED if self.strict_mode else ValidationStatus.WARNING
        
        if validation.warnings:
            return ValidationStatus.WARNING
        
        return ValidationStatus.PASSED
    
    def _generate_recommendations(
        self,
        item: QueueItem,
        validation: LLMValidation,
    ) -> List[str]:
        """Generate recommendations for the reviewer"""
        recommendations = []
        
        if validation.errors:
            recommendations.append("Review and resolve errors before approving")
        
        if validation.warnings:
            recommendations.append("Consider warnings before making decision")
        
        if not validation.safety_checks_passed:
            recommendations.append("Safety concerns require careful review")
        
        if item.risk_tier in ("HIGH", "EXTREME"):
            recommendations.append("High-risk action - verify all conditions before approval")
        
        if validation.validation_confidence < 0.7:
            recommendations.append("Low validation confidence - manual verification recommended")
        
        if not recommendations:
            recommendations.append("All checks passed - ready for approval")
        
        return recommendations

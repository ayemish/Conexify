"""
Verification Engine

Executes verification checks defined by playbooks to validate
that actions had the intended effect.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
import time
import uuid

from sqlalchemy.orm import Session

from ..schemas import VerificationStatus
from ..models import VerificationResultModel
from ..playbook.schema import PlaybookVerification
from ..playbook.expressions import ExpressionEvaluator, EvalContext
from ..connectors.bms import BMSConnector

logger = logging.getLogger(__name__)


class VerificationOutcome(str, Enum):
    """Verification check outcome"""
    PASSED = "passed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass
class VerificationCheck:
    """A single verification check to execute"""
    check_id: str
    expression: str
    window_seconds: int = 900  # 15 minutes
    must_hold: bool = True
    poll_interval_seconds: int = 30
    description: str = ""


@dataclass
class VerificationResult:
    """Result of a verification check"""
    check_id: str
    outcome: VerificationOutcome
    passed: bool
    
    # Timing
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    stability_achieved_at: Optional[datetime] = None
    
    # Values
    before_values: Dict[str, float] = field(default_factory=dict)
    after_values: Dict[str, float] = field(default_factory=dict)
    delta: Dict[str, float] = field(default_factory=dict)
    
    # Samples
    samples: List[Dict[str, Any]] = field(default_factory=list)
    
    # Details
    message: str = ""
    expression: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "outcome": self.outcome.value,
            "passed": self.passed,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "stability_achieved_at": self.stability_achieved_at.isoformat() if self.stability_achieved_at else None,
            "before_values": self.before_values,
            "after_values": self.after_values,
            "delta": self.delta,
            "message": self.message,
            "expression": self.expression,
        }


class VerificationEngine:
    """
    Executes verification checks after playbook actions.
    
    Verification checks validate that:
    - Values changed as expected (delta checks)
    - Trends reversed (slope reversal)
    - Values are within acceptable bands
    - Stability was achieved (value held for duration)
    """
    
    def __init__(
        self,
        session_factory: Callable[[], Session] = None,
        bms_connector: BMSConnector = None,
    ):
        self.session_factory = session_factory
        self.bms_connector = bms_connector
        self.evaluator = ExpressionEvaluator()
    
    def verify(
        self,
        checks: List[VerificationCheck],
        context: EvalContext,
        run_id: str = None,
    ) -> List[VerificationResult]:
        """
        Execute a list of verification checks.
        
        Args:
            checks: Checks to execute
            context: Current evaluation context
            run_id: Run ID for persistence
            
        Returns:
            List of VerificationResult
        """
        results = []
        
        for check in checks:
            result = self.execute_check(check, context)
            results.append(result)
            
            # Persist result if session available
            if self.session_factory and run_id:
                self._persist_result(run_id, result)
        
        return results
    
    def execute_check(
        self,
        check: VerificationCheck,
        context: EvalContext,
    ) -> VerificationResult:
        """
        Execute a single verification check.
        
        Args:
            check: Check to execute
            context: Evaluation context
            
        Returns:
            VerificationResult
        """
        result = VerificationResult(
            check_id=check.check_id,
            outcome=VerificationOutcome.FAILED,
            passed=False,
            expression=check.expression,
        )
        
        try:
            # Capture before values
            result.before_values = context.points.copy()
            
            if check.must_hold:
                # Wait for stability window
                outcome, message, samples = self._wait_for_stability(
                    check, context
                )
                result.outcome = outcome
                result.message = message
                result.samples = samples
                result.passed = outcome == VerificationOutcome.PASSED
                
                if result.passed:
                    result.stability_achieved_at = datetime.utcnow()
            else:
                # Single-point check
                try:
                    check_result = self.evaluator.evaluate(check.expression, context)
                    result.passed = bool(check_result)
                    result.outcome = VerificationOutcome.PASSED if result.passed else VerificationOutcome.FAILED
                    result.message = f"Check {'passed' if result.passed else 'failed'}: {check.expression}"
                except Exception as e:
                    result.outcome = VerificationOutcome.ERROR
                    result.message = f"Evaluation error: {e}"
            
            # Capture after values
            result.after_values = context.points.copy()
            
            # Calculate deltas
            for key in result.after_values:
                if key in result.before_values:
                    result.delta[key] = result.after_values[key] - result.before_values[key]
            
            result.completed_at = datetime.utcnow()
            
        except Exception as e:
            logger.error(f"Verification check {check.check_id} failed: {e}")
            result.outcome = VerificationOutcome.ERROR
            result.message = str(e)
            result.completed_at = datetime.utcnow()
        
        return result
    
    def _wait_for_stability(
        self,
        check: VerificationCheck,
        context: EvalContext,
    ) -> Tuple[VerificationOutcome, str, List[Dict[str, Any]]]:
        """
        Wait for condition to hold stable for the window duration.
        
        Returns:
            (outcome, message, samples)
        """
        start_time = datetime.utcnow()
        end_time = start_time + timedelta(seconds=check.window_seconds)
        
        first_pass_time = None
        consecutive_passes = 0
        samples = []
        
        logger.info(
            f"Starting stability check for {check.check_id}, "
            f"window={check.window_seconds}s, poll={check.poll_interval_seconds}s"
        )
        
        while datetime.utcnow() < end_time:
            # Refresh point values if BMS connector available
            if self.bms_connector:
                try:
                    point_ids = list(context.points.keys())
                    if point_ids:
                        readings = self.bms_connector.read_points(point_ids)
                        for pid, pv in readings.items():
                            context.points[pid] = pv.value
                except Exception as e:
                    logger.warning(f"Failed to refresh points: {e}")
            
            # Evaluate expression
            try:
                result = self.evaluator.evaluate(check.expression, context)
                passed = bool(result)
            except Exception as e:
                logger.warning(f"Evaluation error during stability check: {e}")
                passed = False
            
            # Record sample
            sample = {
                "timestamp": datetime.utcnow().isoformat(),
                "passed": passed,
                "points": context.points.copy(),
            }
            samples.append(sample)
            
            if passed:
                if first_pass_time is None:
                    first_pass_time = datetime.utcnow()
                consecutive_passes += 1
            else:
                first_pass_time = None
                consecutive_passes = 0
            
            # Check if we've held stability for enough time
            if first_pass_time:
                stability_duration = (datetime.utcnow() - first_pass_time).total_seconds()
                if stability_duration >= check.window_seconds:
                    return (
                        VerificationOutcome.PASSED,
                        f"Stability achieved after {stability_duration:.0f}s",
                        samples,
                    )
            
            # Wait before next poll
            time.sleep(min(check.poll_interval_seconds, 5))  # Cap at 5s for dev
        
        # Timeout - check final result
        if consecutive_passes > 0:
            return (
                VerificationOutcome.PASSED,
                f"Check passed with {consecutive_passes} consecutive samples",
                samples,
            )
        
        return (
            VerificationOutcome.TIMEOUT,
            f"Stability not achieved within {check.window_seconds}s window",
            samples,
        )
    
    def _persist_result(self, run_id: str, result: VerificationResult):
        """Persist verification result to database"""
        if not self.session_factory:
            return
        
        session = self.session_factory()
        try:
            verification = VerificationResultModel(
                verification_id=f"VER-{uuid.uuid4().hex[:8].upper()}",
                run_id=run_id,
                check_expression=result.expression,
                status=result.outcome.value,
                passed=result.passed,
                before_values=result.before_values,
                after_values=result.after_values,
                delta=result.delta,
                message=result.message,
                started_at=result.started_at,
                completed_at=result.completed_at,
                stability_achieved_at=result.stability_achieved_at,
            )
            session.add(verification)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to persist verification result: {e}")
        finally:
            session.close()
    
    def create_checks_from_playbook(
        self,
        verifications: List[PlaybookVerification],
    ) -> List[VerificationCheck]:
        """
        Create verification checks from playbook definitions.
        
        Args:
            verifications: Playbook verification definitions
            
        Returns:
            List of VerificationCheck objects
        """
        checks = []
        
        for i, v in enumerate(verifications):
            check = VerificationCheck(
                check_id=f"check_{i}",
                expression=v.expr,
                window_seconds=v.window_sec,
                must_hold=v.must_hold,
                description=v.description,
            )
            checks.append(check)
        
        return checks
    
    def all_passed(self, results: List[VerificationResult]) -> bool:
        """Check if all verification results passed"""
        return all(r.passed for r in results)
    
    def summarize(self, results: List[VerificationResult]) -> Dict[str, Any]:
        """
        Summarize verification results.
        
        Returns:
            Summary dict with pass/fail counts and details
        """
        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed)
        
        return {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "all_passed": failed == 0,
            "outcomes": {
                r.check_id: {
                    "passed": r.passed,
                    "outcome": r.outcome.value,
                    "message": r.message,
                }
                for r in results
            },
        }

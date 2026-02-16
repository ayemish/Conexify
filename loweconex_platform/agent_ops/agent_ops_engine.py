"""
Agent Operations Engine — Golden Tests, Runbooks, Deterministic Replay.

Implements:
- Golden test suites per KPI (known inputs → expected outputs, regression detection)
- Runbooks for failure modes and dead-letter processing
- Deterministic replay engine for audits (tied back to lineage)
- Agent health monitoring (silent degradation detection)

Ensures agents never silently degrade by providing continuous
verification infrastructure.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Golden test model
# =============================================================================

class TestStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class GoldenTestCase:
    """
    A single golden test case: known inputs → expected outputs.

    Used for regression testing of KPI calculations and agent behaviors.
    """
    test_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    kpi_name: str = ""

    # Inputs (frozen, deterministic)
    inputs: Dict[str, Any] = field(default_factory=dict)
    # e.g., {"assets": [...], "tariffs": {...}, "telemetry": [...]}

    # Expected outputs
    expected_outputs: Dict[str, Any] = field(default_factory=dict)
    # e.g., {"savings_medium": 12500.0, "confidence": 0.85}

    # Tolerance for numeric comparisons
    tolerances: Dict[str, float] = field(default_factory=dict)
    # e.g., {"savings_medium": 0.05} means 5% tolerance
    default_tolerance: float = 0.01  # 1% default

    # Tags for filtering
    tags: List[str] = field(default_factory=list)

    # Metadata
    created_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_by: str = ""
    last_passed_ts: Optional[str] = None
    input_hash: Optional[str] = None

    def compute_input_hash(self) -> str:
        """Deterministic hash of inputs for reproducibility."""
        serialized = json.dumps(self.inputs, sort_keys=True, default=str)
        self.input_hash = hashlib.sha256(serialized.encode()).hexdigest()[:16]
        return self.input_hash

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "name": self.name,
            "description": self.description,
            "kpi_name": self.kpi_name,
            "expected_outputs": self.expected_outputs,
            "tolerances": self.tolerances,
            "default_tolerance": self.default_tolerance,
            "tags": self.tags,
            "created_ts": self.created_ts,
            "created_by": self.created_by,
            "last_passed_ts": self.last_passed_ts,
            "input_hash": self.input_hash,
        }


@dataclass
class TestResult:
    """Result of running a single golden test case."""
    test_id: str
    status: str = TestStatus.PASSED.value
    actual_outputs: Dict[str, Any] = field(default_factory=dict)
    mismatches: List[Dict[str, Any]] = field(default_factory=list)
    error_message: Optional[str] = None
    duration_ms: int = 0
    run_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "status": self.status,
            "actual_outputs": self.actual_outputs,
            "mismatches": self.mismatches,
            "error_message": self.error_message,
            "duration_ms": self.duration_ms,
            "run_ts": self.run_ts,
        }


class GoldenTestSuite:
    """
    A collection of golden test cases for a KPI or agent.

    Supports:
    - Running all tests against a calculation function
    - Regression detection (comparing against last-known-good)
    - Coverage reporting
    """

    def __init__(self, suite_name: str = "", kpi_name: str = ""):
        self.suite_name = suite_name
        self.kpi_name = kpi_name
        self._cases: Dict[str, GoldenTestCase] = {}
        self._history: List[Dict[str, Any]] = []

    def add_case(self, case: GoldenTestCase):
        case.compute_input_hash()
        self._cases[case.test_id] = case

    def get_case(self, test_id: str) -> Optional[GoldenTestCase]:
        return self._cases.get(test_id)

    def run_all(
        self,
        calculation_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Run all (or filtered) test cases against a calculation function.

        Args:
            calculation_fn: Function that takes inputs dict → outputs dict
            tags: Optional tag filter

        Returns:
            Summary with pass/fail counts and detailed results
        """
        cases = list(self._cases.values())
        if tags:
            tag_set = set(tags)
            cases = [c for c in cases if tag_set.intersection(c.tags)]

        results: List[TestResult] = []
        for case in cases:
            result = self._run_case(case, calculation_fn)
            results.append(result)

        passed = sum(1 for r in results if r.status == TestStatus.PASSED.value)
        failed = sum(1 for r in results if r.status == TestStatus.FAILED.value)
        errors = sum(1 for r in results if r.status == TestStatus.ERROR.value)

        summary = {
            "suite_name": self.suite_name,
            "kpi_name": self.kpi_name,
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "pass_rate": passed / len(results) if results else 0,
            "all_passed": failed == 0 and errors == 0,
            "run_ts": datetime.utcnow().isoformat(),
            "results": [r.to_dict() for r in results],
        }

        self._history.append(summary)
        logger.info(
            f"Golden test suite '{self.suite_name}': "
            f"{passed}/{len(results)} passed"
        )
        return summary

    def _run_case(
        self, case: GoldenTestCase, calculation_fn: Callable
    ) -> TestResult:
        start = datetime.utcnow()
        try:
            actual = calculation_fn(copy.deepcopy(case.inputs))
            mismatches = self._compare_outputs(case, actual)
            status = TestStatus.PASSED.value if not mismatches else TestStatus.FAILED.value

            if status == TestStatus.PASSED.value:
                case.last_passed_ts = datetime.utcnow().isoformat()

            end = datetime.utcnow()
            return TestResult(
                test_id=case.test_id,
                status=status,
                actual_outputs=actual,
                mismatches=mismatches,
                duration_ms=int((end - start).total_seconds() * 1000),
            )
        except Exception as e:
            end = datetime.utcnow()
            return TestResult(
                test_id=case.test_id,
                status=TestStatus.ERROR.value,
                error_message=str(e),
                duration_ms=int((end - start).total_seconds() * 1000),
            )

    def _compare_outputs(
        self, case: GoldenTestCase, actual: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        mismatches = []
        for key, expected_val in case.expected_outputs.items():
            actual_val = actual.get(key)
            if actual_val is None:
                mismatches.append({
                    "key": key,
                    "expected": expected_val,
                    "actual": None,
                    "type": "missing_key",
                })
                continue

            if isinstance(expected_val, (int, float)) and isinstance(actual_val, (int, float)):
                tol = case.tolerances.get(key, case.default_tolerance)
                if expected_val == 0:
                    if abs(actual_val) > tol:
                        mismatches.append({
                            "key": key,
                            "expected": expected_val,
                            "actual": actual_val,
                            "tolerance": tol,
                            "type": "numeric_mismatch",
                        })
                else:
                    rel_diff = abs(actual_val - expected_val) / abs(expected_val)
                    if rel_diff > tol:
                        mismatches.append({
                            "key": key,
                            "expected": expected_val,
                            "actual": actual_val,
                            "relative_diff": round(rel_diff, 6),
                            "tolerance": tol,
                            "type": "numeric_mismatch",
                        })
            elif expected_val != actual_val:
                mismatches.append({
                    "key": key,
                    "expected": expected_val,
                    "actual": actual_val,
                    "type": "value_mismatch",
                })

        return mismatches

    def regression_trend(self) -> List[Dict[str, Any]]:
        """Get pass rate trend over time."""
        return [
            {
                "run_ts": h["run_ts"],
                "pass_rate": h["pass_rate"],
                "passed": h["passed"],
                "total": h["total"],
            }
            for h in self._history
        ]

    def get_never_passed(self) -> List[GoldenTestCase]:
        """Get test cases that have never passed."""
        return [c for c in self._cases.values() if c.last_passed_ts is None]

    def stats(self) -> Dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "total_cases": len(self._cases),
            "total_runs": len(self._history),
            "never_passed": len(self.get_never_passed()),
            "last_run": self._history[-1] if self._history else None,
        }


# =============================================================================
# Runbooks
# =============================================================================

class RunbookTrigger(str, Enum):
    AGENT_FAILURE = "agent_failure"
    DLQ_THRESHOLD = "dlq_threshold"
    KPI_TIMEOUT = "kpi_timeout"
    DATA_QUALITY_BLOCK = "data_quality_block"
    DRIFT_DETECTED = "drift_detected"
    SLA_BREACH = "sla_breach"
    MANUAL = "manual"


@dataclass
class RunbookStep:
    """A single step in a runbook."""
    step_number: int
    title: str
    description: str
    action_type: str = "manual"  # manual, automated, check, escalate
    command: Optional[str] = None  # For automated steps
    expected_outcome: str = ""
    timeout_minutes: int = 30
    escalation_contact: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_number": self.step_number,
            "title": self.title,
            "description": self.description,
            "action_type": self.action_type,
            "command": self.command,
            "expected_outcome": self.expected_outcome,
            "timeout_minutes": self.timeout_minutes,
            "escalation_contact": self.escalation_contact,
        }


@dataclass
class Runbook:
    """
    An operational runbook for a specific failure scenario.

    Defines the step-by-step process for diagnosing and resolving
    a specific type of failure.
    """
    runbook_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    trigger: str = RunbookTrigger.AGENT_FAILURE.value
    severity: str = "medium"

    steps: List[RunbookStep] = field(default_factory=list)

    # Applicability
    applicable_kpis: List[str] = field(default_factory=list)  # empty = all
    applicable_agents: List[str] = field(default_factory=list)

    # Metadata
    owner: str = ""
    created_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_used_ts: Optional[str] = None
    times_used: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "runbook_id": self.runbook_id,
            "name": self.name,
            "description": self.description,
            "trigger": self.trigger,
            "severity": self.severity,
            "steps": [s.to_dict() for s in self.steps],
            "applicable_kpis": self.applicable_kpis,
            "applicable_agents": self.applicable_agents,
            "owner": self.owner,
            "last_used_ts": self.last_used_ts,
            "times_used": self.times_used,
        }


def create_standard_runbooks() -> List[Runbook]:
    """Create standard operational runbooks for the platform."""
    runbooks = []

    # DLQ processing runbook
    runbooks.append(Runbook(
        name="Dead-Letter Queue Processing",
        description="Process messages that failed delivery in the Redis event bus.",
        trigger=RunbookTrigger.DLQ_THRESHOLD.value,
        severity="high",
        steps=[
            RunbookStep(1, "Check DLQ depth",
                        "Query Redis for current DLQ message count.",
                        action_type="automated",
                        command="redis-cli XLEN platform:dlq"),
            RunbookStep(2, "Inspect failed messages",
                        "Read the oldest 10 DLQ messages to identify failure patterns.",
                        action_type="automated",
                        command="redis-cli XRANGE platform:dlq - + COUNT 10"),
            RunbookStep(3, "Classify failure type",
                        "Determine if failures are: (a) transient (retry), "
                        "(b) poison pill (discard), or (c) systemic (investigate).",
                        action_type="manual"),
            RunbookStep(4, "Retry transient failures",
                        "Move retryable messages back to their source streams.",
                        action_type="manual"),
            RunbookStep(5, "Archive poison pills",
                        "Move non-retryable messages to archive with error annotation.",
                        action_type="manual"),
            RunbookStep(6, "Investigate systemic issues",
                        "If >50% of DLQ messages have the same error, escalate.",
                        action_type="escalate",
                        escalation_contact="engineering_lead"),
        ],
    ))

    # Agent failure runbook
    runbooks.append(Runbook(
        name="KPI Agent Failure Recovery",
        description="Recover from a KPI crew agent failure.",
        trigger=RunbookTrigger.AGENT_FAILURE.value,
        severity="high",
        steps=[
            RunbookStep(1, "Check agent logs",
                        "Review structured logs for the failing agent's correlation_id.",
                        action_type="automated"),
            RunbookStep(2, "Verify input data",
                        "Run data quality suite for the KPI's input dataset.",
                        action_type="automated"),
            RunbookStep(3, "Run golden tests",
                        "Execute golden test suite for the affected KPI.",
                        action_type="automated"),
            RunbookStep(4, "Check for drift",
                        "Run drift monitoring on the KPI's model.",
                        action_type="automated"),
            RunbookStep(5, "Attempt retry",
                        "If transient failure, retry the crew run with same inputs.",
                        action_type="manual"),
            RunbookStep(6, "Rollback if persistent",
                        "If failure persists, rollback to previous model version.",
                        action_type="manual",
                        escalation_contact="data_scientist"),
        ],
    ))

    # Data quality block runbook
    runbooks.append(Runbook(
        name="Data Quality Gate Block Resolution",
        description="Resolve blocked KPI publication due to data quality gate failure.",
        trigger=RunbookTrigger.DATA_QUALITY_BLOCK.value,
        severity="medium",
        steps=[
            RunbookStep(1, "Review quality report",
                        "Check the quality report for the blocked dataset.",
                        action_type="manual"),
            RunbookStep(2, "Identify failing expectations",
                        "List all error-severity expectations that failed.",
                        action_type="manual"),
            RunbookStep(3, "Assess data source",
                        "Check if the source data is available and fresh.",
                        action_type="manual"),
            RunbookStep(4, "Fix or waive",
                        "Either fix the data issue or request a waiver from the data owner.",
                        action_type="manual"),
            RunbookStep(5, "Re-run validation",
                        "Re-run the expectation suite to confirm fix.",
                        action_type="automated"),
            RunbookStep(6, "Unblock KPI",
                        "Once quality gate passes, re-trigger KPI calculation.",
                        action_type="manual"),
        ],
    ))

    return runbooks


# =============================================================================
# Deterministic replay engine
# =============================================================================

@dataclass
class ReplaySession:
    """A deterministic replay session tied to a lineage event."""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    original_run_id: str = ""
    original_lineage_event_id: str = ""
    kpi_name: str = ""

    # Frozen inputs
    frozen_inputs: Dict[str, Any] = field(default_factory=dict)
    frozen_config: Dict[str, Any] = field(default_factory=dict)
    input_hash: str = ""

    # Replay results
    original_outputs: Dict[str, Any] = field(default_factory=dict)
    replay_outputs: Dict[str, Any] = field(default_factory=dict)
    outputs_match: bool = False
    mismatches: List[Dict[str, Any]] = field(default_factory=list)

    # Timing
    original_ts: Optional[str] = None
    replay_ts: Optional[str] = None
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "original_run_id": self.original_run_id,
            "original_lineage_event_id": self.original_lineage_event_id,
            "kpi_name": self.kpi_name,
            "input_hash": self.input_hash,
            "outputs_match": self.outputs_match,
            "mismatches": self.mismatches,
            "original_ts": self.original_ts,
            "replay_ts": self.replay_ts,
            "duration_ms": self.duration_ms,
        }


class ReplayEngine:
    """
    Deterministic replay engine for audit and debugging.

    Given a lineage event (run_id), recreates the exact inputs
    and re-runs the calculation to verify reproducibility.

    Ties back to the lineage graph (#1) for full traceability.
    """

    def __init__(self):
        self._sessions: Dict[str, ReplaySession] = {}

    def create_session(
        self,
        original_run_id: str,
        lineage_event_id: str,
        kpi_name: str,
        frozen_inputs: Dict[str, Any],
        frozen_config: Dict[str, Any],
        original_outputs: Dict[str, Any],
        original_ts: Optional[str] = None,
    ) -> ReplaySession:
        """Create a replay session from a lineage event."""
        input_str = json.dumps(frozen_inputs, sort_keys=True, default=str)
        input_hash = hashlib.sha256(input_str.encode()).hexdigest()[:16]

        session = ReplaySession(
            original_run_id=original_run_id,
            original_lineage_event_id=lineage_event_id,
            kpi_name=kpi_name,
            frozen_inputs=frozen_inputs,
            frozen_config=frozen_config,
            input_hash=input_hash,
            original_outputs=original_outputs,
            original_ts=original_ts,
        )
        self._sessions[session.session_id] = session
        return session

    def replay(
        self,
        session_id: str,
        calculation_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
        tolerance: float = 0.01,
    ) -> ReplaySession:
        """
        Execute a replay: re-run the calculation with frozen inputs
        and compare against original outputs.
        """
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Replay session {session_id} not found")

        start = datetime.utcnow()
        try:
            replay_outputs = calculation_fn(copy.deepcopy(session.frozen_inputs))
        except Exception as e:
            session.replay_ts = datetime.utcnow().isoformat()
            session.mismatches = [{"type": "execution_error", "message": str(e)}]
            session.outputs_match = False
            return session

        end = datetime.utcnow()
        session.replay_outputs = replay_outputs
        session.replay_ts = end.isoformat()
        session.duration_ms = int((end - start).total_seconds() * 1000)

        # Compare
        mismatches = []
        for key, orig_val in session.original_outputs.items():
            replay_val = replay_outputs.get(key)
            if replay_val is None:
                mismatches.append({"key": key, "original": orig_val, "replay": None, "type": "missing"})
                continue
            if isinstance(orig_val, (int, float)) and isinstance(replay_val, (int, float)):
                if orig_val != 0:
                    rel_diff = abs(replay_val - orig_val) / abs(orig_val)
                    if rel_diff > tolerance:
                        mismatches.append({
                            "key": key, "original": orig_val, "replay": replay_val,
                            "relative_diff": round(rel_diff, 6), "type": "numeric_drift",
                        })
                elif abs(replay_val) > tolerance:
                    mismatches.append({
                        "key": key, "original": orig_val, "replay": replay_val,
                        "type": "numeric_drift",
                    })
            elif orig_val != replay_val:
                mismatches.append({
                    "key": key, "original": orig_val, "replay": replay_val,
                    "type": "value_drift",
                })

        session.mismatches = mismatches
        session.outputs_match = len(mismatches) == 0

        logger.info(
            f"Replay {session_id}: {'MATCH' if session.outputs_match else 'DRIFT'} "
            f"({len(mismatches)} mismatches)"
        )
        return session

    def get_session(self, session_id: str) -> Optional[ReplaySession]:
        return self._sessions.get(session_id)

    def get_sessions_for_kpi(self, kpi_name: str) -> List[ReplaySession]:
        return [s for s in self._sessions.values() if s.kpi_name == kpi_name]

    def reproducibility_report(self) -> Dict[str, Any]:
        """Generate a reproducibility report across all replay sessions."""
        total = len(self._sessions)
        matched = sum(1 for s in self._sessions.values() if s.outputs_match)
        drifted = sum(1 for s in self._sessions.values() if not s.outputs_match and s.replay_ts)
        pending = total - matched - drifted

        by_kpi = defaultdict(lambda: {"total": 0, "matched": 0})
        for s in self._sessions.values():
            by_kpi[s.kpi_name]["total"] += 1
            if s.outputs_match:
                by_kpi[s.kpi_name]["matched"] += 1

        return {
            "total_sessions": total,
            "matched": matched,
            "drifted": drifted,
            "pending": pending,
            "reproducibility_rate": matched / total if total else 0,
            "by_kpi": dict(by_kpi),
        }


# =============================================================================
# Agent health monitoring
# =============================================================================

class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class AgentHealthMonitor:
    """
    Monitors agent health to detect silent degradation.

    Tracks:
    - Agent success/failure rates
    - Latency trends
    - Output quality scores
    - Golden test pass rates
    """

    def __init__(self, degradation_threshold: float = 0.15):
        self.degradation_threshold = degradation_threshold
        self._agent_stats: Dict[str, Dict[str, Any]] = {}
        self._health_history: List[Dict[str, Any]] = []

    def record_execution(
        self,
        agent_id: str,
        success: bool,
        duration_ms: int,
        quality_score: Optional[float] = None,
    ):
        """Record an agent execution for health tracking."""
        if agent_id not in self._agent_stats:
            self._agent_stats[agent_id] = {
                "total": 0, "successes": 0, "failures": 0,
                "durations": [], "quality_scores": [],
                "recent_failures": 0, "recent_window": 20,
            }

        stats = self._agent_stats[agent_id]
        stats["total"] += 1
        if success:
            stats["successes"] += 1
        else:
            stats["failures"] += 1

        stats["durations"].append(duration_ms)
        if len(stats["durations"]) > 100:
            stats["durations"] = stats["durations"][-100:]

        if quality_score is not None:
            stats["quality_scores"].append(quality_score)
            if len(stats["quality_scores"]) > 100:
                stats["quality_scores"] = stats["quality_scores"][-100:]

        # Track recent failure rate
        recent = stats["recent_window"]
        recent_results = []
        total = stats["total"]
        for i in range(max(0, total - recent), total):
            recent_results.append(i < stats["successes"])

    def get_health(self, agent_id: str) -> Dict[str, Any]:
        """Get current health status for an agent."""
        stats = self._agent_stats.get(agent_id)
        if not stats or stats["total"] == 0:
            return {"agent_id": agent_id, "status": HealthStatus.UNKNOWN.value}

        failure_rate = stats["failures"] / stats["total"]
        avg_duration = sum(stats["durations"]) / len(stats["durations"]) if stats["durations"] else 0
        avg_quality = (
            sum(stats["quality_scores"]) / len(stats["quality_scores"])
            if stats["quality_scores"] else None
        )

        # Determine status
        if failure_rate > 0.5:
            status = HealthStatus.UNHEALTHY.value
        elif failure_rate > self.degradation_threshold:
            status = HealthStatus.DEGRADED.value
        elif avg_quality is not None and avg_quality < 0.6:
            status = HealthStatus.DEGRADED.value
        else:
            status = HealthStatus.HEALTHY.value

        # Detect latency degradation
        durations = stats["durations"]
        latency_degraded = False
        if len(durations) > 20:
            first_half = durations[:len(durations) // 2]
            second_half = durations[len(durations) // 2:]
            avg_first = sum(first_half) / len(first_half)
            avg_second = sum(second_half) / len(second_half)
            if avg_first > 0 and (avg_second - avg_first) / avg_first > 0.5:
                latency_degraded = True
                if status == HealthStatus.HEALTHY.value:
                    status = HealthStatus.DEGRADED.value

        result = {
            "agent_id": agent_id,
            "status": status,
            "total_executions": stats["total"],
            "failure_rate": round(failure_rate, 4),
            "avg_duration_ms": round(avg_duration, 1),
            "avg_quality_score": round(avg_quality, 4) if avg_quality else None,
            "latency_degraded": latency_degraded,
        }

        self._health_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            **result,
        })

        return result

    def get_all_health(self) -> Dict[str, Dict[str, Any]]:
        """Get health status for all tracked agents."""
        return {agent_id: self.get_health(agent_id) for agent_id in self._agent_stats}

    def get_degraded_agents(self) -> List[str]:
        """Get IDs of agents that are degraded or unhealthy."""
        degraded = []
        for agent_id in self._agent_stats:
            health = self.get_health(agent_id)
            if health["status"] in (HealthStatus.DEGRADED.value, HealthStatus.UNHEALTHY.value):
                degraded.append(agent_id)
        return degraded

    def stats(self) -> Dict[str, Any]:
        all_health = self.get_all_health()
        statuses = defaultdict(int)
        for h in all_health.values():
            statuses[h["status"]] += 1
        return {
            "tracked_agents": len(self._agent_stats),
            "by_status": dict(statuses),
            "history_entries": len(self._health_history),
        }

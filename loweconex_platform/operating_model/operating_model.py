"""
Operating Model — RACI, SLAs, Review Cadence, Exception Management.

Implements:
- RACI matrices per KPI (Responsible, Accountable, Consulted, Informed)
- SLA definitions with threshold enforcement and breach tracking
- Review cadence scheduling (weekly triage, monthly savings, quarterly model)
- Exception management (data gaps, mis-mappings, false positives, escalation)
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# RACI model
# =============================================================================

class RACIRole(str, Enum):
    RESPONSIBLE = "R"    # Does the work
    ACCOUNTABLE = "A"    # Ultimately answerable
    CONSULTED = "C"      # Provides input
    INFORMED = "I"       # Kept up to date


@dataclass
class RACIEntry:
    """A single RACI assignment."""
    kpi_name: str
    activity: str         # e.g., "data_collection", "calculation", "approval", "review"
    person_or_role: str   # e.g., "data_engineer", "energy_manager", "CFO"
    raci_role: str = RACIRole.RESPONSIBLE.value
    team: str = ""
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kpi_name": self.kpi_name,
            "activity": self.activity,
            "person_or_role": self.person_or_role,
            "raci_role": self.raci_role,
            "team": self.team,
            "notes": self.notes,
        }


class RACIMatrix:
    """
    RACI matrix per KPI.

    Defines who is Responsible, Accountable, Consulted, and Informed
    for each activity in the KPI lifecycle.
    """

    STANDARD_ACTIVITIES = [
        "data_collection",
        "data_validation",
        "kpi_calculation",
        "qa_review",
        "savings_approval",
        "report_generation",
        "exception_resolution",
        "model_review",
        "benchmark_update",
        "mv_reconciliation",
    ]

    def __init__(self):
        self._entries: List[RACIEntry] = []

    def assign(self, entry: RACIEntry):
        self._entries.append(entry)

    def get_matrix(self, kpi_name: str) -> Dict[str, Dict[str, List[str]]]:
        """Get RACI matrix for a KPI: activity → role → [people]."""
        matrix: Dict[str, Dict[str, List[str]]] = {}
        for entry in self._entries:
            if entry.kpi_name != kpi_name:
                continue
            if entry.activity not in matrix:
                matrix[entry.activity] = {"R": [], "A": [], "C": [], "I": []}
            matrix[entry.activity][entry.raci_role].append(entry.person_or_role)
        return matrix

    def get_responsible(self, kpi_name: str, activity: str) -> List[str]:
        return [
            e.person_or_role for e in self._entries
            if e.kpi_name == kpi_name and e.activity == activity
            and e.raci_role == RACIRole.RESPONSIBLE.value
        ]

    def get_accountable(self, kpi_name: str, activity: str) -> Optional[str]:
        accts = [
            e.person_or_role for e in self._entries
            if e.kpi_name == kpi_name and e.activity == activity
            and e.raci_role == RACIRole.ACCOUNTABLE.value
        ]
        return accts[0] if accts else None

    def validate(self) -> List[str]:
        """Validate the RACI matrix for completeness and correctness."""
        issues = []
        kpis = set(e.kpi_name for e in self._entries)
        for kpi in kpis:
            matrix = self.get_matrix(kpi)
            for activity in self.STANDARD_ACTIVITIES:
                if activity not in matrix:
                    issues.append(f"{kpi}/{activity}: No assignments")
                    continue
                roles = matrix[activity]
                if not roles["R"]:
                    issues.append(f"{kpi}/{activity}: No Responsible assigned")
                if not roles["A"]:
                    issues.append(f"{kpi}/{activity}: No Accountable assigned")
                if len(roles["A"]) > 1:
                    issues.append(f"{kpi}/{activity}: Multiple Accountable (should be exactly 1)")
        return issues

    def export(self) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self._entries]


# =============================================================================
# SLA definitions and tracking
# =============================================================================

class SLASeverity(str, Enum):
    WARNING = "warning"
    BREACH = "breach"
    CRITICAL = "critical"


@dataclass
class SLADefinition:
    """A Service Level Agreement definition."""
    sla_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    metric: str = ""            # e.g., "data_freshness_hours", "kpi_latency_hours"

    # Thresholds
    target_value: float = 0.0
    warning_threshold: float = 0.0
    breach_threshold: float = 0.0
    operator: str = "<"         # < means metric must be less than threshold

    # Scope
    kpi_name: Optional[str] = None
    company_id: Optional[str] = None

    # Cadence
    measurement_frequency: str = "daily"
    reporting_frequency: str = "weekly"

    # Ownership
    owner: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sla_id": self.sla_id,
            "name": self.name,
            "description": self.description,
            "metric": self.metric,
            "target_value": self.target_value,
            "warning_threshold": self.warning_threshold,
            "breach_threshold": self.breach_threshold,
            "operator": self.operator,
            "kpi_name": self.kpi_name,
            "company_id": self.company_id,
            "measurement_frequency": self.measurement_frequency,
            "owner": self.owner,
        }

    def evaluate(self, current_value: float) -> Dict[str, Any]:
        ops = {
            "<": lambda a, b: a < b,
            "<=": lambda a, b: a <= b,
            ">": lambda a, b: a > b,
            ">=": lambda a, b: a >= b,
        }
        compare = ops.get(self.operator, lambda a, b: a < b)

        if compare(current_value, self.target_value):
            status = "met"
            severity = None
        elif compare(current_value, self.warning_threshold):
            status = "warning"
            severity = SLASeverity.WARNING.value
        elif compare(current_value, self.breach_threshold):
            status = "warning"
            severity = SLASeverity.WARNING.value
        else:
            status = "breached"
            severity = SLASeverity.BREACH.value

        return {
            "sla_id": self.sla_id,
            "name": self.name,
            "current_value": current_value,
            "target": self.target_value,
            "status": status,
            "severity": severity,
        }


class SLATracker:
    """Tracks SLA compliance over time."""

    def __init__(self):
        self._slas: Dict[str, SLADefinition] = {}
        self._measurements: List[Dict[str, Any]] = []
        self._breaches: List[Dict[str, Any]] = []

    def register_sla(self, sla: SLADefinition):
        self._slas[sla.sla_id] = sla

    def add_standard_slas(self):
        """Add standard platform SLAs."""
        standards = [
            SLADefinition(name="Data Freshness", metric="data_age_hours",
                          target_value=24, warning_threshold=36, breach_threshold=48,
                          operator="<", description="Telemetry data must be < 24h old"),
            SLADefinition(name="KPI Calculation Latency", metric="kpi_latency_hours",
                          target_value=4, warning_threshold=8, breach_threshold=24,
                          operator="<", description="KPI results within 4h of data arrival"),
            SLADefinition(name="Report Delivery", metric="report_delivery_days",
                          target_value=1, warning_threshold=2, breach_threshold=5,
                          operator="<", description="Reports delivered within 1 business day"),
            SLADefinition(name="Data Quality Score", metric="quality_score",
                          target_value=0.90, warning_threshold=0.80, breach_threshold=0.70,
                          operator=">", description="Data quality score > 90%"),
            SLADefinition(name="Exception Resolution", metric="exception_resolution_hours",
                          target_value=48, warning_threshold=72, breach_threshold=168,
                          operator="<", description="Exceptions resolved within 48h"),
        ]
        for sla in standards:
            self.register_sla(sla)

    def record_measurement(self, sla_id: str, value: float, context: Optional[Dict] = None):
        sla = self._slas.get(sla_id)
        if not sla:
            return

        result = sla.evaluate(value)
        measurement = {
            "timestamp": datetime.utcnow().isoformat(),
            "sla_id": sla_id,
            "value": value,
            "result": result,
            "context": context or {},
        }
        self._measurements.append(measurement)

        if result["status"] == "breached":
            self._breaches.append(measurement)
            logger.warning(f"SLA BREACH: {sla.name} = {value} (target {sla.target_value})")

    def get_breaches(self, since: Optional[datetime] = None) -> List[Dict[str, Any]]:
        if not since:
            return list(self._breaches)
        return [
            b for b in self._breaches
            if datetime.fromisoformat(b["timestamp"]) >= since
        ]

    def compliance_summary(self) -> Dict[str, Any]:
        summary = {}
        for sla_id, sla in self._slas.items():
            measurements = [m for m in self._measurements if m["sla_id"] == sla_id]
            if not measurements:
                summary[sla.name] = {"status": "no_data", "measurements": 0}
                continue
            met = sum(1 for m in measurements if m["result"]["status"] == "met")
            summary[sla.name] = {
                "measurements": len(measurements),
                "met": met,
                "compliance_pct": met / len(measurements),
                "last_value": measurements[-1]["value"],
                "last_status": measurements[-1]["result"]["status"],
            }
        return summary


# =============================================================================
# Review cadence
# =============================================================================

class ReviewType(str, Enum):
    WEEKLY_TRIAGE = "weekly_triage"
    MONTHLY_SAVINGS = "monthly_savings"
    QUARTERLY_MODEL = "quarterly_model"
    ANNUAL_STRATEGY = "annual_strategy"


@dataclass
class ReviewCadence:
    """A scheduled review meeting/process."""
    review_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    review_type: str = ReviewType.WEEKLY_TRIAGE.value
    name: str = ""
    description: str = ""
    frequency_days: int = 7
    attendees: List[str] = field(default_factory=list)
    agenda_items: List[str] = field(default_factory=list)
    owner: str = ""

    # Tracking
    last_held: Optional[str] = None
    next_due: Optional[str] = None
    outcomes: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "review_id": self.review_id,
            "review_type": self.review_type,
            "name": self.name,
            "description": self.description,
            "frequency_days": self.frequency_days,
            "attendees": self.attendees,
            "agenda_items": self.agenda_items,
            "owner": self.owner,
            "last_held": self.last_held,
            "next_due": self.next_due,
        }


class ReviewScheduler:
    """Manages review cadence scheduling and tracking."""

    def __init__(self):
        self._reviews: Dict[str, ReviewCadence] = {}

    def register_review(self, review: ReviewCadence):
        if not review.next_due:
            review.next_due = (
                datetime.utcnow() + timedelta(days=review.frequency_days)
            ).isoformat()
        self._reviews[review.review_id] = review

    def add_standard_cadence(self):
        """Add standard review cadence for the platform."""
        self.register_review(ReviewCadence(
            review_type=ReviewType.WEEKLY_TRIAGE.value,
            name="Weekly Data & Exception Triage",
            frequency_days=7,
            agenda_items=[
                "Review open data quality exceptions",
                "Triage new data gaps / mis-mappings",
                "Review false positive alerts",
                "SLA compliance check",
                "Action items from previous week",
            ],
            attendees=["data_engineer", "energy_analyst", "ops_manager"],
        ))
        self.register_review(ReviewCadence(
            review_type=ReviewType.MONTHLY_SAVINGS.value,
            name="Monthly Savings Review",
            frequency_days=30,
            agenda_items=[
                "M&V reconciliation results by location",
                "Savings realization rate vs predictions",
                "Recommendation acceptance rate",
                "New KPI results and trends",
                "Budget vs actuals",
                "Exception escalations",
            ],
            attendees=["energy_manager", "finance_analyst", "ops_director", "data_engineer"],
        ))
        self.register_review(ReviewCadence(
            review_type=ReviewType.QUARTERLY_MODEL.value,
            name="Quarterly Model & Benchmark Review",
            frequency_days=90,
            agenda_items=[
                "Model performance drift assessment",
                "Benchmark distribution updates",
                "Model card review and update",
                "Schema version compatibility",
                "AI risk registry review",
                "Security controls audit status",
            ],
            attendees=["data_scientist", "energy_manager", "compliance_officer", "engineering_lead"],
        ))
        self.register_review(ReviewCadence(
            review_type=ReviewType.ANNUAL_STRATEGY.value,
            name="Annual Strategy & Roadmap Review",
            frequency_days=365,
            agenda_items=[
                "Platform ROI assessment",
                "KPI coverage expansion plan",
                "Technology upgrade roadmap",
                "Compliance framework updates",
                "Staffing and training needs",
            ],
            attendees=["vp_operations", "cfo", "cto", "energy_manager"],
        ))

    def get_overdue(self) -> List[ReviewCadence]:
        now = datetime.utcnow()
        return [
            r for r in self._reviews.values()
            if r.next_due and datetime.fromisoformat(r.next_due) < now
        ]

    def record_held(self, review_id: str, outcomes: Optional[List[Dict[str, Any]]] = None):
        review = self._reviews.get(review_id)
        if not review:
            return
        review.last_held = datetime.utcnow().isoformat()
        review.next_due = (
            datetime.utcnow() + timedelta(days=review.frequency_days)
        ).isoformat()
        if outcomes:
            review.outcomes.extend(outcomes)

    def get_all(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self._reviews.values()]


# =============================================================================
# Exception management
# =============================================================================

class ExceptionType(str, Enum):
    DATA_GAP = "data_gap"
    MIS_MAPPING = "mis_mapping"
    FALSE_POSITIVE = "false_positive"
    CALCULATION_ERROR = "calculation_error"
    INTEGRATION_FAILURE = "integration_failure"
    SCHEMA_MISMATCH = "schema_mismatch"
    BENCHMARK_OUTLIER = "benchmark_outlier"
    OTHER = "other"


class ExceptionPriority(str, Enum):
    CRITICAL = "critical"    # Blocks KPI publication
    HIGH = "high"            # Must resolve within 24h
    MEDIUM = "medium"        # Must resolve within 1 week
    LOW = "low"              # Best-effort


class ExceptionStatus(str, Enum):
    OPEN = "open"
    TRIAGED = "triaged"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    WONT_FIX = "wont_fix"
    ESCALATED = "escalated"


@dataclass
class ExceptionRecord:
    """An exception requiring human resolution."""
    exception_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    exception_type: str = ExceptionType.DATA_GAP.value
    priority: str = ExceptionPriority.MEDIUM.value
    status: str = ExceptionStatus.OPEN.value
    title: str = ""
    description: str = ""

    # Scope
    company_id: Optional[str] = None
    location_id: Optional[str] = None
    asset_id: Optional[str] = None
    kpi_name: Optional[str] = None

    # Assignment
    assigned_to: Optional[str] = None
    escalated_to: Optional[str] = None

    # Resolution
    resolution: str = ""
    root_cause: str = ""
    preventive_action: str = ""

    # Timeline
    created_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    triaged_ts: Optional[str] = None
    resolved_ts: Optional[str] = None
    sla_due_ts: Optional[str] = None

    # Impact
    blocked_kpis: List[str] = field(default_factory=list)
    affected_reports: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "exception_id": self.exception_id,
            "exception_type": self.exception_type,
            "priority": self.priority,
            "status": self.status,
            "title": self.title,
            "description": self.description,
            "company_id": self.company_id,
            "location_id": self.location_id,
            "asset_id": self.asset_id,
            "kpi_name": self.kpi_name,
            "assigned_to": self.assigned_to,
            "escalated_to": self.escalated_to,
            "resolution": self.resolution,
            "root_cause": self.root_cause,
            "preventive_action": self.preventive_action,
            "created_ts": self.created_ts,
            "triaged_ts": self.triaged_ts,
            "resolved_ts": self.resolved_ts,
            "sla_due_ts": self.sla_due_ts,
            "blocked_kpis": self.blocked_kpis,
            "affected_reports": self.affected_reports,
        }


class ExceptionManager:
    """
    Manages the exception lifecycle: creation → triage → investigation → resolution.

    Supports escalation, SLA tracking, and pattern analysis.
    """

    SLA_HOURS = {
        ExceptionPriority.CRITICAL.value: 4,
        ExceptionPriority.HIGH.value: 24,
        ExceptionPriority.MEDIUM.value: 168,  # 1 week
        ExceptionPriority.LOW.value: 720,      # 1 month
    }

    def __init__(self):
        self._exceptions: Dict[str, ExceptionRecord] = {}

    def create(self, exc: ExceptionRecord) -> str:
        sla_hours = self.SLA_HOURS.get(exc.priority, 168)
        exc.sla_due_ts = (datetime.utcnow() + timedelta(hours=sla_hours)).isoformat()
        self._exceptions[exc.exception_id] = exc
        logger.info(f"Exception created: {exc.title} ({exc.priority})")
        return exc.exception_id

    def triage(self, exception_id: str, assigned_to: str, priority: Optional[str] = None):
        exc = self._exceptions.get(exception_id)
        if not exc:
            return
        exc.status = ExceptionStatus.TRIAGED.value
        exc.assigned_to = assigned_to
        exc.triaged_ts = datetime.utcnow().isoformat()
        if priority:
            exc.priority = priority
            sla_hours = self.SLA_HOURS.get(priority, 168)
            exc.sla_due_ts = (datetime.utcnow() + timedelta(hours=sla_hours)).isoformat()

    def resolve(self, exception_id: str, resolution: str, root_cause: str = "", preventive: str = ""):
        exc = self._exceptions.get(exception_id)
        if not exc:
            return
        exc.status = ExceptionStatus.RESOLVED.value
        exc.resolution = resolution
        exc.root_cause = root_cause
        exc.preventive_action = preventive
        exc.resolved_ts = datetime.utcnow().isoformat()
        logger.info(f"Exception resolved: {exception_id}")

    def escalate(self, exception_id: str, escalated_to: str, reason: str = ""):
        exc = self._exceptions.get(exception_id)
        if not exc:
            return
        exc.status = ExceptionStatus.ESCALATED.value
        exc.escalated_to = escalated_to
        logger.warning(f"Exception escalated: {exception_id} to {escalated_to}")

    def get_open(self) -> List[ExceptionRecord]:
        return [
            e for e in self._exceptions.values()
            if e.status not in (ExceptionStatus.RESOLVED.value, ExceptionStatus.WONT_FIX.value)
        ]

    def get_overdue(self) -> List[ExceptionRecord]:
        now = datetime.utcnow()
        return [
            e for e in self.get_open()
            if e.sla_due_ts and datetime.fromisoformat(e.sla_due_ts) < now
        ]

    def get_blocking(self) -> List[ExceptionRecord]:
        """Get exceptions that are blocking KPI publication."""
        return [e for e in self.get_open() if e.blocked_kpis]

    def pattern_analysis(self) -> Dict[str, Any]:
        """Analyze exception patterns for systemic issues."""
        by_type = defaultdict(int)
        by_kpi = defaultdict(int)
        by_location = defaultdict(int)
        for exc in self._exceptions.values():
            by_type[exc.exception_type] += 1
            if exc.kpi_name:
                by_kpi[exc.kpi_name] += 1
            if exc.location_id:
                by_location[exc.location_id] += 1

        return {
            "total": len(self._exceptions),
            "open": len(self.get_open()),
            "overdue": len(self.get_overdue()),
            "blocking": len(self.get_blocking()),
            "by_type": dict(by_type),
            "top_kpis": dict(sorted(by_kpi.items(), key=lambda x: -x[1])[:5]),
            "top_locations": dict(sorted(by_location.items(), key=lambda x: -x[1])[:5]),
        }

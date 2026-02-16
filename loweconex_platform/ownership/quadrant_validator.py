"""
Quadrant Validator — enforces Q1-Q4 metric → owner → cost flow integrity.

Validates that:
1. Every metric has a quadrant assignment
2. The accountable owner matches the quadrant's default RACI mapping
3. Cost lines carry the correct cost_type for their quadrant
4. Translation rules target the correct quadrant metrics
5. No orphan metrics (metrics with no translation rules)
6. Cross-silo (Q4) metrics have proper dependency edges
7. Pipeline integrity: metric → ownership → cost line → ROI all consistent

Used at three checkpoints:
- Pre-pipeline: validate catalog + ownership setup
- Post-translation: validate cost lines match quadrant expectations
- Post-reconciliation: validate unified cost stack integrity
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from loweconex_platform.ownership.metric_catalog import MetricCatalog, Quadrant
from loweconex_platform.ownership.ownership_model import (
    OwnershipEngine, QUADRANT_DEFAULT_OWNERS, RACIType,
)
from loweconex_platform.ownership.translation_rules import TranslationRulesLibrary
from loweconex_platform.ownership.aggregation_engine import AggregationEngine
from loweconex_platform.ownership.cost_stack import CostStack

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Quadrant ↔ Cost Type mapping
# ═══════════════════════════════════════════════════════════════════

QUADRANT_COST_TYPE: Dict[str, str] = {
    "Q1": "opex",
    "Q2": "capex",
    "Q3": "risk",
    "Q4": "strategic",
}

COST_TYPE_QUADRANT: Dict[str, str] = {v: k for k, v in QUADRANT_COST_TYPE.items()}


# ═══════════════════════════════════════════════════════════════════
# Validation Issue
# ═══════════════════════════════════════════════════════════════════

class Severity(str, Enum):
    ERROR = "error"       # Pipeline will produce incorrect results
    WARNING = "warning"   # Results may be inaccurate
    INFO = "info"         # Informational, non-blocking


@dataclass
class ValidationIssue:
    """A single validation issue found during quadrant wiring checks."""
    severity: str
    category: str        # e.g., "ownership_mismatch", "orphan_metric", "cost_type_mismatch"
    metric_id: str = ""
    quadrant: str = ""
    description: str = ""
    suggestion: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "category": self.category,
            "metric_id": self.metric_id,
            "quadrant": self.quadrant,
            "description": self.description,
            "suggestion": self.suggestion,
        }


@dataclass
class ValidationReport:
    """Complete validation report for quadrant wiring."""
    issues: List[ValidationIssue] = field(default_factory=list)
    metrics_checked: int = 0
    rules_checked: int = 0
    cost_lines_checked: int = 0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    passed: bool = True

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR.value]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING.value]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "info_count": len([i for i in self.issues if i.severity == Severity.INFO.value]),
            "metrics_checked": self.metrics_checked,
            "rules_checked": self.rules_checked,
            "cost_lines_checked": self.cost_lines_checked,
            "timestamp": self.timestamp,
            "issues": [i.to_dict() for i in self.issues],
        }


# ═══════════════════════════════════════════════════════════════════
# Quadrant Validator
# ═══════════════════════════════════════════════════════════════════

class QuadrantValidator:
    """
    Validates Q1-Q4 metric → owner → cost flow integrity at multiple
    pipeline stages.

    Checks:
    1. Metric catalog completeness and quadrant assignment
    2. Ownership RACI matches quadrant defaults (or has explicit override)
    3. Translation rules cover all metrics
    4. Cost lines carry correct cost_type for their quadrant
    5. Cross-silo (Q4) dependency edges are defined
    6. Post-reconciliation cost stack integrity
    """

    def __init__(
        self,
        catalog: MetricCatalog,
        ownership: OwnershipEngine,
        rules: TranslationRulesLibrary,
        aggregation: AggregationEngine,
    ):
        self.catalog = catalog
        self.ownership = ownership
        self.rules = rules
        self.aggregation = aggregation

    # ── Checkpoint 1: Pre-pipeline ────────────────────────────────

    def validate_setup(self) -> ValidationReport:
        """
        Pre-pipeline validation: catalog, ownership, and rules are consistent.

        Run before building the cost stack.
        """
        report = ValidationReport()

        metrics = self.catalog.list_all()
        report.metrics_checked = len(metrics)

        if not metrics:
            report.issues.append(ValidationIssue(
                severity=Severity.ERROR.value,
                category="empty_catalog",
                description="Metric catalog is empty — no metrics defined.",
                suggestion="Seed the metric catalog with system metrics.",
            ))
            report.passed = False
            return report

        # Check each metric
        quadrant_counts: Dict[str, int] = {"Q1": 0, "Q2": 0, "Q3": 0, "Q4": 0}
        metrics_with_rules: Set[str] = set()

        for metric in metrics:
            mid = metric.metric_id
            quad = metric.quadrant

            # 1. Quadrant assignment exists
            if quad not in quadrant_counts:
                report.issues.append(ValidationIssue(
                    severity=Severity.ERROR.value,
                    category="invalid_quadrant",
                    metric_id=mid,
                    quadrant=str(quad),
                    description=f"Metric '{mid}' has invalid quadrant '{quad}'.",
                    suggestion="Assign a valid quadrant: Q1, Q2, Q3, or Q4.",
                ))
            else:
                quadrant_counts[quad] += 1

            # 2. Ownership matches quadrant default
            assignment = self.ownership.resolve(mid)
            if assignment:
                expected_accountable = QUADRANT_DEFAULT_OWNERS.get(quad, {}).get(
                    RACIType.ACCOUNTABLE.value, ""
                )
                actual_accountable = assignment.get(RACIType.ACCOUNTABLE.value, "")
                if expected_accountable and actual_accountable != expected_accountable:
                    # Check if there's an explicit override
                    if not self.ownership.has_override(mid):
                        report.issues.append(ValidationIssue(
                            severity=Severity.WARNING.value,
                            category="ownership_mismatch",
                            metric_id=mid,
                            quadrant=quad,
                            description=(
                                f"Metric '{mid}' ({quad}) accountable is '{actual_accountable}' "
                                f"but quadrant default is '{expected_accountable}'."
                            ),
                            suggestion=(
                                f"Either change accountable to '{expected_accountable}' or "
                                f"add an explicit ownership override with justification."
                            ),
                        ))
            else:
                report.issues.append(ValidationIssue(
                    severity=Severity.ERROR.value,
                    category="no_ownership",
                    metric_id=mid,
                    quadrant=quad,
                    description=f"Metric '{mid}' has no ownership assignment.",
                    suggestion="Run ownership.set_default_from_quadrant() for this metric.",
                ))

            # 3. Translation rules exist for this metric
            matched_rules = self.rules.list_by_metric(mid)
            if matched_rules:
                metrics_with_rules.add(mid)
            else:
                report.issues.append(ValidationIssue(
                    severity=Severity.WARNING.value,
                    category="orphan_metric",
                    metric_id=mid,
                    quadrant=quad,
                    description=f"Metric '{mid}' has no translation rules — it won't produce cost lines.",
                    suggestion="Add a TranslationRule for this metric.",
                ))

        report.rules_checked = len(metrics_with_rules)

        # 4. Check quadrant balance
        for quad, count in quadrant_counts.items():
            if count == 0:
                report.issues.append(ValidationIssue(
                    severity=Severity.WARNING.value,
                    category="empty_quadrant",
                    quadrant=quad,
                    description=f"Quadrant {quad} has no metrics.",
                    suggestion=f"Add metrics for {quad} ({QUADRANT_COST_TYPE.get(quad, '')}).",
                ))

        # 5. Q4 metrics should have dependency edges
        q4_metrics = [m for m in metrics if m.quadrant == "Q4"]
        dep_graph = self.aggregation.get_dependency_graph()
        dep_metric_ids = set()
        for edge in dep_graph:
            dep_metric_ids.add(edge.get("upstream", ""))
            dep_metric_ids.add(edge.get("downstream", ""))

        for m in q4_metrics:
            if m.metric_id not in dep_metric_ids:
                report.issues.append(ValidationIssue(
                    severity=Severity.INFO.value,
                    category="q4_no_dependency",
                    metric_id=m.metric_id,
                    quadrant="Q4",
                    description=(
                        f"Q4 metric '{m.metric_id}' has no dependency edges — "
                        f"cross-silo overlap detection may be incomplete."
                    ),
                    suggestion="Add DependencyEdge entries for Q4 cross-silo metrics.",
                ))

        report.passed = len(report.errors) == 0
        return report

    # ── Checkpoint 2: Post-translation ────────────────────────────

    def validate_cost_lines(self, cost_stack: CostStack) -> ValidationReport:
        """
        Post-translation validation: cost lines match quadrant expectations.

        Run after AggregationEngine.build_cost_stack().
        """
        report = ValidationReport()

        lines = cost_stack.lines if hasattr(cost_stack, 'lines') else []
        report.cost_lines_checked = len(lines)

        if not lines:
            report.issues.append(ValidationIssue(
                severity=Severity.WARNING.value,
                category="empty_cost_stack",
                description="Cost stack has no lines after translation.",
                suggestion="Verify metric inputs and translation rules.",
            ))
            report.passed = True
            return report

        for line in lines:
            mid = getattr(line, 'metric_id', '')
            cost_type = getattr(line, 'cost_type', '')
            owner = getattr(line, 'owner', '')

            # Look up metric quadrant
            metric_def = self.catalog.get(mid) if mid else None
            if not metric_def:
                continue

            expected_cost_type = QUADRANT_COST_TYPE.get(metric_def.quadrant, "")

            # Validate cost_type matches quadrant
            if expected_cost_type and cost_type != expected_cost_type:
                report.issues.append(ValidationIssue(
                    severity=Severity.WARNING.value,
                    category="cost_type_mismatch",
                    metric_id=mid,
                    quadrant=metric_def.quadrant,
                    description=(
                        f"Cost line for '{mid}' ({metric_def.quadrant}) has "
                        f"cost_type='{cost_type}' but expected '{expected_cost_type}'."
                    ),
                    suggestion=f"Update the translation rule to use cost_type='{expected_cost_type}'.",
                ))

            # Validate owner is in the RACI for this metric's quadrant
            quad_owners = QUADRANT_DEFAULT_OWNERS.get(metric_def.quadrant, {})
            valid_owners = set(quad_owners.values())
            if owner and owner not in valid_owners:
                report.issues.append(ValidationIssue(
                    severity=Severity.INFO.value,
                    category="owner_not_in_quadrant_raci",
                    metric_id=mid,
                    quadrant=metric_def.quadrant,
                    description=(
                        f"Cost line owner '{owner}' for '{mid}' ({metric_def.quadrant}) "
                        f"is not in quadrant RACI: {valid_owners}."
                    ),
                    suggestion="This may be intentional for cross-silo allocation.",
                ))

        report.passed = len(report.errors) == 0
        return report

    # ── Checkpoint 3: Post-reconciliation ─────────────────────────

    def validate_reconciled_stack(
        self,
        cost_stack: CostStack,
        adjustments: List[Dict[str, Any]],
    ) -> ValidationReport:
        """
        Post-reconciliation validation: unified cost stack integrity.

        Run after ReconciliationAgent or AggregationEngine reconciliation.
        """
        report = ValidationReport()

        lines = cost_stack.lines if hasattr(cost_stack, 'lines') else []
        report.cost_lines_checked = len(lines)

        # Check no negative-beyond-reasonable adjustments
        for adj in adjustments:
            overlap_frac = adj.get("overlap_fraction", 0)
            if overlap_frac > 1.0 or overlap_frac < 0:
                report.issues.append(ValidationIssue(
                    severity=Severity.ERROR.value,
                    category="invalid_adjustment",
                    description=(
                        f"Adjustment overlap fraction {overlap_frac} is out of "
                        f"range [0, 1] for {adj.get('source_metric', '')} → "
                        f"{adj.get('target_metric', '')}."
                    ),
                    suggestion="Fix the dependency edge overlap_fraction.",
                ))

        # Check cost stack totals are reasonable
        total = sum(abs(getattr(l, 'amount', 0)) for l in lines)
        if total == 0 and len(lines) > 0:
            report.issues.append(ValidationIssue(
                severity=Severity.WARNING.value,
                category="zero_total",
                description="Reconciled cost stack has lines but total is $0.",
                suggestion="Check if all amounts were adjusted to zero.",
            ))

        # Check quadrant coverage in cost lines
        quadrants_represented = set()
        for line in lines:
            mid = getattr(line, 'metric_id', '')
            metric_def = self.catalog.get(mid) if mid else None
            if metric_def:
                quadrants_represented.add(metric_def.quadrant)

        for q in ["Q1", "Q2", "Q3", "Q4"]:
            if q not in quadrants_represented:
                # Check if there are metrics for this quadrant
                q_metrics = self.catalog.list_by_quadrant(q)
                if q_metrics:
                    report.issues.append(ValidationIssue(
                        severity=Severity.INFO.value,
                        category="quadrant_not_in_stack",
                        quadrant=q,
                        description=(
                            f"Quadrant {q} has {len(q_metrics)} catalog metrics but "
                            f"no cost lines in the reconciled stack."
                        ),
                        suggestion="Check if metric inputs were provided for this quadrant.",
                    ))

        report.passed = len(report.errors) == 0
        return report

    # ── Full pipeline validation ──────────────────────────────────

    def validate_full_pipeline(
        self,
        cost_stack: Optional[CostStack] = None,
        adjustments: Optional[List[Dict[str, Any]]] = None,
    ) -> ValidationReport:
        """
        Run all validation checkpoints and merge into one report.
        """
        merged = ValidationReport()

        # Checkpoint 1: Setup
        setup_report = self.validate_setup()
        merged.issues.extend(setup_report.issues)
        merged.metrics_checked = setup_report.metrics_checked
        merged.rules_checked = setup_report.rules_checked

        # Checkpoint 2: Cost lines (if stack provided)
        if cost_stack:
            lines_report = self.validate_cost_lines(cost_stack)
            merged.issues.extend(lines_report.issues)
            merged.cost_lines_checked = lines_report.cost_lines_checked

        # Checkpoint 3: Reconciliation (if adjustments provided)
        if cost_stack and adjustments is not None:
            recon_report = self.validate_reconciled_stack(cost_stack, adjustments)
            merged.issues.extend(recon_report.issues)

        merged.passed = len(merged.errors) == 0
        return merged

    # ── Utility: get quadrant summary ─────────────────────────────

    def get_quadrant_summary(self) -> Dict[str, Any]:
        """Return a summary of metrics, ownership, and rules per quadrant."""
        summary = {}
        for q in ["Q1", "Q2", "Q3", "Q4"]:
            metrics = self.catalog.list_by_quadrant(q)
            metric_ids = [m.metric_id for m in metrics]
            rules_count = sum(
                1 for mid in metric_ids
                if self.rules.list_by_metric(mid)
            )
            default_owner = QUADRANT_DEFAULT_OWNERS.get(q, {}).get(
                RACIType.ACCOUNTABLE.value, "N/A"
            )
            summary[q] = {
                "label": QUADRANT_COST_TYPE.get(q, ""),
                "metric_count": len(metrics),
                "metric_ids": metric_ids,
                "rules_count": rules_count,
                "default_accountable": default_owner,
                "cost_type": QUADRANT_COST_TYPE.get(q, ""),
            }
        return summary

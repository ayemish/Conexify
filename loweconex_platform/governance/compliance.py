"""
Compliance Checker — validates KPI outputs against regulatory
and standards requirements before publication.

Checks: data lineage completeness, evidence grounding, confidence thresholds,
and domain-specific compliance rules (food safety, refrigerant, ESG).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ComplianceCheck:
    """Result of a single compliance check."""
    check_id: str
    check_name: str
    domain: str  # "food_safety", "refrigerant", "esg", "data_quality", "governance"
    status: str = "pass"  # "pass" | "fail" | "warning" | "not_applicable"
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    severity: str = "info"  # "info" | "warning" | "critical"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "check_name": self.check_name,
            "domain": self.domain,
            "status": self.status,
            "message": self.message,
            "details": self.details,
            "severity": self.severity,
        }


@dataclass
class ComplianceReport:
    """Aggregated compliance report."""
    checks: List[ComplianceCheck] = field(default_factory=list)
    overall_status: str = "pass"
    generated_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_status": self.overall_status,
            "total_checks": len(self.checks),
            "passed": sum(1 for c in self.checks if c.status == "pass"),
            "failed": sum(1 for c in self.checks if c.status == "fail"),
            "warnings": sum(1 for c in self.checks if c.status == "warning"),
            "checks": [c.to_dict() for c in self.checks],
            "generated_ts": self.generated_ts,
        }


class ComplianceChecker:
    """
    Runs compliance checks against KPI outputs and report artifacts.
    
    Domains:
    - Food safety (FDA Food Code alignment)
    - Refrigerant (EPA Section 608)
    - ESG (GHG Protocol)
    - Data quality (completeness, lineage)
    - Governance (prompt governance, evidence grounding)
    """

    def run_all_checks(
        self,
        kpi_results: Dict[str, Dict[str, Any]],
        report: Optional[Dict[str, Any]] = None,
    ) -> ComplianceReport:
        """Run all compliance checks and return aggregated report."""
        checks: List[ComplianceCheck] = []

        checks.extend(self._check_data_quality(kpi_results))
        checks.extend(self._check_evidence_grounding(kpi_results))
        checks.extend(self._check_food_safety(kpi_results))
        checks.extend(self._check_refrigerant(kpi_results))
        checks.extend(self._check_esg(kpi_results))
        checks.extend(self._check_governance(kpi_results))

        has_failures = any(c.status == "fail" for c in checks)
        has_criticals = any(c.severity == "critical" and c.status == "fail" for c in checks)

        overall = "fail" if has_criticals else ("warning" if has_failures else "pass")

        report_obj = ComplianceReport(checks=checks, overall_status=overall)
        logger.info(
            f"Compliance check: {overall} "
            f"({report_obj.to_dict()['passed']} pass, "
            f"{report_obj.to_dict()['failed']} fail, "
            f"{report_obj.to_dict()['warnings']} warn)"
        )
        return report_obj

    def _check_data_quality(self, kpi_results: Dict[str, Dict[str, Any]]) -> List[ComplianceCheck]:
        checks = []
        for kpi_name, result in kpi_results.items():
            dq = result.get("data_quality", {})
            score = dq.get("score", 1.0)
            gaps = result.get("gaps", [])

            if score < 0.5:
                checks.append(ComplianceCheck(
                    check_id=f"dq_{kpi_name}",
                    check_name=f"Data quality for {kpi_name}",
                    domain="data_quality",
                    status="fail",
                    message=f"Data quality score {score:.2f} below threshold (0.5)",
                    severity="critical" if score < 0.3 else "warning",
                    details={"score": score, "gap_count": len(gaps)},
                ))
            elif gaps:
                checks.append(ComplianceCheck(
                    check_id=f"dq_{kpi_name}",
                    check_name=f"Data quality for {kpi_name}",
                    domain="data_quality",
                    status="warning",
                    message=f"{len(gaps)} data gaps detected",
                    severity="warning",
                    details={"score": score, "gaps": gaps},
                ))
            else:
                checks.append(ComplianceCheck(
                    check_id=f"dq_{kpi_name}",
                    check_name=f"Data quality for {kpi_name}",
                    domain="data_quality",
                    status="pass",
                    message="Data quality acceptable",
                ))
        return checks

    def _check_evidence_grounding(self, kpi_results: Dict[str, Dict[str, Any]]) -> List[ComplianceCheck]:
        checks = []
        for kpi_name, result in kpi_results.items():
            evidence = result.get("evidence_refs", [])
            assumptions = result.get("assumptions", [])

            if not evidence and not assumptions:
                checks.append(ComplianceCheck(
                    check_id=f"ev_{kpi_name}",
                    check_name=f"Evidence grounding for {kpi_name}",
                    domain="governance",
                    status="fail",
                    message="No evidence references or assumptions documented",
                    severity="warning",
                ))
            elif not evidence:
                checks.append(ComplianceCheck(
                    check_id=f"ev_{kpi_name}",
                    check_name=f"Evidence grounding for {kpi_name}",
                    domain="governance",
                    status="warning",
                    message="Assumptions documented but no evidence references",
                    severity="info",
                ))
            else:
                checks.append(ComplianceCheck(
                    check_id=f"ev_{kpi_name}",
                    check_name=f"Evidence grounding for {kpi_name}",
                    domain="governance",
                    status="pass",
                    message=f"{len(evidence)} evidence references provided",
                ))
        return checks

    def _check_food_safety(self, kpi_results: Dict[str, Dict[str, Any]]) -> List[ComplianceCheck]:
        checks = []
        fs_result = kpi_results.get("food_safety_compliance", {})
        if not fs_result:
            checks.append(ComplianceCheck(
                check_id="fs_missing",
                check_name="Food safety KPI presence",
                domain="food_safety",
                status="not_applicable",
                message="Food safety KPI not computed",
            ))
            return checks

        metrics = fs_result.get("metrics", {})
        threshold = metrics.get("cold_holding_threshold_f", 0)

        if threshold != 41.0 and threshold != 0:
            checks.append(ComplianceCheck(
                check_id="fs_threshold",
                check_name="Cold holding threshold alignment",
                domain="food_safety",
                status="warning",
                message=f"Cold holding threshold {threshold}°F differs from FDA standard 41°F",
                severity="warning",
                details={"actual": threshold, "expected": 41.0},
            ))
        else:
            checks.append(ComplianceCheck(
                check_id="fs_threshold",
                check_name="Cold holding threshold alignment",
                domain="food_safety",
                status="pass",
                message="Aligned with FDA Food Code 41°F standard",
            ))
        return checks

    def _check_refrigerant(self, kpi_results: Dict[str, Dict[str, Any]]) -> List[ComplianceCheck]:
        checks = []
        leak_result = kpi_results.get("refrigerant_leak_reduction", {})
        if not leak_result:
            return [ComplianceCheck(
                check_id="ref_missing",
                check_name="Refrigerant KPI presence",
                domain="refrigerant",
                status="not_applicable",
                message="Refrigerant leak KPI not computed",
            )]

        metrics = leak_result.get("metrics", {})
        baseline_rate = metrics.get("baseline_leak_rate", 0)

        if baseline_rate > 0.20:
            checks.append(ComplianceCheck(
                check_id="ref_epa608",
                check_name="EPA Section 608 leak rate compliance",
                domain="refrigerant",
                status="fail",
                message=f"Baseline leak rate {baseline_rate*100:.0f}% exceeds EPA 20% threshold",
                severity="critical",
                details={"baseline_rate": baseline_rate, "epa_threshold": 0.20},
            ))
        else:
            checks.append(ComplianceCheck(
                check_id="ref_epa608",
                check_name="EPA Section 608 leak rate compliance",
                domain="refrigerant",
                status="pass",
                message=f"Baseline leak rate {baseline_rate*100:.0f}% within EPA threshold",
            ))
        return checks

    def _check_esg(self, kpi_results: Dict[str, Dict[str, Any]]) -> List[ComplianceCheck]:
        checks = []
        esg_result = kpi_results.get("esg_compliance", {})
        if not esg_result:
            return [ComplianceCheck(
                check_id="esg_missing",
                check_name="ESG KPI presence",
                domain="esg",
                status="not_applicable",
                message="ESG KPI not computed",
            )]

        metrics = esg_result.get("metrics", {})
        scope1 = metrics.get("scope1_reduction_tco2e", 0)
        scope2 = metrics.get("scope2_reduction_tco2e", 0)

        if scope1 == 0 and scope2 == 0:
            checks.append(ComplianceCheck(
                check_id="esg_scopes",
                check_name="GHG Protocol scope assignment",
                domain="esg",
                status="warning",
                message="No Scope 1 or Scope 2 reductions computed",
                severity="warning",
            ))
        else:
            checks.append(ComplianceCheck(
                check_id="esg_scopes",
                check_name="GHG Protocol scope assignment",
                domain="esg",
                status="pass",
                message=f"Scope 1: {scope1:.1f} tCO2e, Scope 2: {scope2:.1f} tCO2e reductions",
            ))
        return checks

    def _check_governance(self, kpi_results: Dict[str, Dict[str, Any]]) -> List[ComplianceCheck]:
        checks = []

        # Check all KPIs have confidence scores
        no_confidence = [k for k, v in kpi_results.items() if v.get("confidence", -1) < 0]
        if no_confidence:
            checks.append(ComplianceCheck(
                check_id="gov_confidence",
                check_name="Confidence scores present",
                domain="governance",
                status="fail",
                message=f"{len(no_confidence)} KPIs missing confidence scores",
                severity="warning",
            ))
        else:
            checks.append(ComplianceCheck(
                check_id="gov_confidence",
                check_name="Confidence scores present",
                domain="governance",
                status="pass",
                message="All KPIs have confidence scores",
            ))

        # Check savings ordering (low <= medium <= high)
        misordered = []
        for k, v in kpi_results.items():
            low = v.get("savings_low", 0)
            med = v.get("savings_medium", 0)
            high = v.get("savings_high", 0)
            if low > med or med > high:
                misordered.append(k)

        if misordered:
            checks.append(ComplianceCheck(
                check_id="gov_savings_order",
                check_name="Savings band ordering",
                domain="governance",
                status="fail",
                message=f"Savings bands misordered in: {', '.join(misordered)}",
                severity="critical",
            ))
        else:
            checks.append(ComplianceCheck(
                check_id="gov_savings_order",
                check_name="Savings band ordering",
                domain="governance",
                status="pass",
                message="All savings bands properly ordered (low <= medium <= high)",
            ))

        return checks

"""
Composite Report Builder — assembles the multi-section report
from KPI artifacts, scenario comparisons, and ROI computations.

Report structure (FRD Section 12):
1. Executive Summary
2. Estate Overview (KPI scorecards, benchmarks)
3. Location Ranking (top/bottom deciles)
4. Asset Action List (replace/repair/tune/monitor/defer)
5. KPI Deep Dives
6. Scenario Comparison
7. Methodology & Governance Appendix
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CompositeReportBuilder:
    """
    Builds the composite ROI report from pipeline outputs.
    
    Each section is built independently and can be regenerated.
    All sections carry evidence references back to source data.
    """

    def __init__(self):
        self._sections: Dict[str, Dict[str, Any]] = {}
        self._report_id = str(uuid.uuid4())
        self._metadata: Dict[str, Any] = {
            "report_id": self._report_id,
            "generated_ts": datetime.utcnow().isoformat(),
            "version": "1.0",
        }

    def build_full_report(self, composite_result: Dict[str, Any]) -> Dict[str, Any]:
        """Build all report sections from the orchestrator's composite result."""
        self._build_executive_summary(composite_result)
        self._build_estate_overview(composite_result)
        self._build_location_ranking(composite_result)
        self._build_asset_action_list(composite_result)
        self._build_kpi_deep_dives(composite_result)
        self._build_scenario_comparison(composite_result)
        self._build_methodology_appendix(composite_result)

        return {
            "report_id": self._report_id,
            "metadata": self._metadata,
            "sections": self._sections,
            "table_of_contents": list(self._sections.keys()),
        }

    # -------------------------------------------------------------------------
    # Section 1: Executive Summary
    # -------------------------------------------------------------------------

    def _build_executive_summary(self, data: Dict[str, Any]):
        summary = data.get("executive_summary", {})
        roi = data.get("savings_reconciliation", {})
        reconciled = roi.get("reconciled_totals", {})

        self._sections["executive_summary"] = {
            "title": "Executive Summary",
            "total_savings": {
                "low": reconciled.get("total_savings_low", 0),
                "medium": reconciled.get("total_savings_medium", 0),
                "high": reconciled.get("total_savings_high", 0),
            },
            "kpi_count": summary.get("kpi_count", 0),
            "approved_kpis": summary.get("approved_kpis", 0),
            "key_risks": summary.get("key_risks", []),
            "savings_by_category": reconciled.get("by_category", {}),
            "narrative": self._generate_executive_narrative(summary, reconciled),
        }

    def _generate_executive_narrative(
        self, summary: Dict, reconciled: Dict
    ) -> str:
        total_med = reconciled.get("total_savings_medium", 0)
        kpi_count = summary.get("kpi_count", 0)
        approved = summary.get("approved_kpis", 0)

        lines = [
            f"Analysis of {kpi_count} KPI dimensions ({approved} approved) identifies "
            f"${total_med:,.0f} in annual savings (medium estimate).",
        ]

        by_cat = reconciled.get("by_category", {})
        if by_cat:
            top_cats = sorted(by_cat.items(), key=lambda x: x[1].get("medium", 0), reverse=True)[:3]
            top_strs = [f"{cat}: ${vals.get('medium', 0):,.0f}" for cat, vals in top_cats]
            lines.append(f"Top savings drivers: {'; '.join(top_strs)}.")

        risks = summary.get("key_risks", [])
        if risks:
            lines.append(f"Key risks: {risks[0]}")

        return " ".join(lines)

    # -------------------------------------------------------------------------
    # Section 2: Estate Overview
    # -------------------------------------------------------------------------

    def _build_estate_overview(self, data: Dict[str, Any]):
        scorecards = data.get("kpi_scorecards", {})

        self._sections["estate_overview"] = {
            "title": "Estate Overview",
            "kpi_scorecards": scorecards,
            "benchmark_distributions": self._compute_benchmarks(data),
            "narrative": f"Estate-wide analysis covers {len(scorecards)} KPI dimensions.",
        }

    def _compute_benchmarks(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Compute benchmark distributions from KPI results."""
        kpi_results = data.get("kpi_results", {})
        benchmarks = {}
        for kpi_name, result in kpi_results.items():
            confidence = result.get("confidence", 0)
            savings = result.get("savings_medium", 0)
            benchmarks[kpi_name] = {
                "savings_medium": savings,
                "confidence": confidence,
                "data_quality": result.get("data_quality", {}).get("score", 0),
            }
        return benchmarks

    # -------------------------------------------------------------------------
    # Section 3: Location Ranking
    # -------------------------------------------------------------------------

    def _build_location_ranking(self, data: Dict[str, Any]):
        kpi_results = data.get("kpi_results", {})
        scorecards = data.get("kpi_scorecards", {})

        # Gather per-location savings from twin patches and KPI results
        location_scores: Dict[str, Dict[str, Any]] = {}

        for kpi_name, result in kpi_results.items():
            patches = result.get("twin_patches", [])
            savings_med = result.get("savings_medium", 0)
            confidence = result.get("confidence", 0)
            loc_id = result.get("location_id") or "estate_aggregate"

            if loc_id not in location_scores:
                location_scores[loc_id] = {
                    "location_id": loc_id,
                    "savings_medium": 0.0,
                    "savings_low": 0.0,
                    "savings_high": 0.0,
                    "kpi_count": 0,
                    "avg_confidence": 0.0,
                    "data_quality_avg": 0.0,
                    "asset_health_avg": 0.0,
                    "compliance_risk_score": 0.0,
                    "_confidence_sum": 0.0,
                    "_dq_sum": 0.0,
                    "_health_sum": 0.0,
                }

            loc = location_scores[loc_id]
            loc["savings_medium"] += savings_med
            loc["savings_low"] += result.get("savings_low", 0)
            loc["savings_high"] += result.get("savings_high", 0)
            loc["kpi_count"] += 1
            loc["_confidence_sum"] += confidence
            dq = result.get("data_quality", {})
            loc["_dq_sum"] += dq.get("score", 0.5) if isinstance(dq, dict) else 0.5

        # Finalize averages and compute composite score
        ranked = []
        for loc_id, loc in location_scores.items():
            n = max(loc["kpi_count"], 1)
            loc["avg_confidence"] = round(loc["_confidence_sum"] / n, 3)
            loc["data_quality_avg"] = round(loc["_dq_sum"] / n, 3)
            # Composite score: weighted combination
            loc["composite_score"] = round(
                0.50 * loc["savings_medium"] / max(loc["savings_medium"], 1)
                + 0.20 * loc["avg_confidence"]
                + 0.15 * loc["data_quality_avg"]
                + 0.15 * (1.0 - loc.get("compliance_risk_score", 0)),
                4,
            )
            # Clean internal keys
            loc.pop("_confidence_sum", None)
            loc.pop("_dq_sum", None)
            loc.pop("_health_sum", None)
            ranked.append(loc)

        # Sort descending by composite score
        ranked.sort(key=lambda x: x["composite_score"], reverse=True)

        # Assign rank
        for i, loc in enumerate(ranked, 1):
            loc["rank"] = i

        # Top and bottom decile
        n_total = len(ranked)
        decile_size = max(1, n_total // 10)
        top_decile = ranked[:decile_size]
        bottom_decile = ranked[-decile_size:] if n_total > 1 else []

        self._sections["location_ranking"] = {
            "title": "Location Ranking",
            "description": "Locations ranked by composite score (savings, confidence, data quality, compliance).",
            "ranking_criteria": [
                "Total savings opportunity — 50% weight",
                "Average KPI confidence — 20% weight",
                "Data quality score — 15% weight",
                "Compliance risk (inverted) — 15% weight",
            ],
            "ranked_locations": ranked,
            "top_decile": top_decile,
            "bottom_decile": bottom_decile,
            "total_locations": n_total,
            "narrative": (
                f"{n_total} location(s) ranked. "
                f"Top location: {ranked[0]['location_id'] if ranked else 'N/A'} "
                f"(score={ranked[0]['composite_score'] if ranked else 0:.3f}). "
                f"Bottom: {ranked[-1]['location_id'] if ranked else 'N/A'}."
            ),
        }

    # -------------------------------------------------------------------------
    # Section 4: Asset Action List
    # -------------------------------------------------------------------------

    def _build_asset_action_list(self, data: Dict[str, Any]):
        optimization = data.get("portfolio_optimization", {})
        opt_result = optimization.get("optimization", {})
        categorized = optimization.get("categorized_actions", {})

        actions_summary = {
            "replace": [],
            "repair": [],
            "tune": [],
            "monitor": [],
            "defer": [],
        }

        # Map optimization categories to action types
        for action in categorized.get("capex_replacements", []):
            actions_summary["replace"].append(action)
        for action in categorized.get("structural_fixes", []):
            actions_summary["repair"].append(action)
        for action in categorized.get("quick_wins", []):
            actions_summary["tune"].append(action)
        for action in categorized.get("policy_changes", []):
            actions_summary["monitor"].append(action)

        self._sections["asset_action_list"] = {
            "title": "Asset Action List",
            "actions_by_type": actions_summary,
            "total_selected_actions": opt_result.get("selected_count", 0),
            "total_cost": opt_result.get("total_cost", 0),
            "total_npv": opt_result.get("total_npv", 0),
            "narrative": f"{opt_result.get('selected_count', 0)} actions recommended across replace/repair/tune/monitor categories.",
        }

    # -------------------------------------------------------------------------
    # Section 5: KPI Deep Dives
    # -------------------------------------------------------------------------

    def _build_kpi_deep_dives(self, data: Dict[str, Any]):
        kpi_results = data.get("kpi_results", {})
        deep_dives = {}

        for kpi_name, result in kpi_results.items():
            deep_dives[kpi_name] = {
                "title": kpi_name.replace("_", " ").title(),
                "status": result.get("status"),
                "inputs_used": result.get("extraction", {}).get("inputs", {}),
                "data_quality": result.get("data_quality", {}),
                "gaps": result.get("gaps", []),
                "metrics": result.get("metrics", {}),
                "savings": {
                    "low": result.get("savings_low", 0),
                    "medium": result.get("savings_medium", 0),
                    "high": result.get("savings_high", 0),
                },
                "confidence": result.get("confidence", 0),
                "assumptions": result.get("assumptions", []),
                "evidence_refs": result.get("evidence_refs", []),
                "narrative": result.get("narrative", ""),
                "qa_status": result.get("qa_status"),
                "qa_issues": result.get("qa_issues", []),
            }

        self._sections["kpi_deep_dives"] = {
            "title": "KPI Deep Dives",
            "kpis": deep_dives,
        }

    # -------------------------------------------------------------------------
    # Section 6: Scenario Comparison
    # -------------------------------------------------------------------------

    def _build_scenario_comparison(self, data: Dict[str, Any]):
        scenario_data = data.get("scenario_analysis", {})
        scenarios = scenario_data.get("scenarios", {})
        comparison = scenario_data.get("comparison", {})

        self._sections["scenario_comparison"] = {
            "title": "Scenario Comparison",
            "scenarios": {
                name: {
                    "parameters_changed": s.get("parameters", {}).get("description", ""),
                    "total_savings_medium": s.get("reconciled_totals", {}).get("total_savings_medium", 0),
                    "by_category": s.get("reconciled_totals", {}).get("by_category", {}),
                }
                for name, s in scenarios.items()
            },
            "comparison_matrix": comparison,
            "narrative": f"Analyzed {len(scenarios)} scenarios. "
                         f"See comparison matrix for side-by-side results.",
        }

    # -------------------------------------------------------------------------
    # Section 7: Methodology & Governance Appendix
    # -------------------------------------------------------------------------

    def _build_methodology_appendix(self, data: Dict[str, Any]):
        metadata = data.get("metadata", {})
        reconciliation = data.get("savings_reconciliation", {})

        self._sections["methodology_appendix"] = {
            "title": "Methodology & Governance Appendix",
            "data_lineage": {
                "description": "Every metric links back to source filters and time windows.",
                "kpi_count": len(data.get("kpi_results", {})),
                "evidence_trail": "See KPI deep dives for per-KPI evidence references.",
            },
            "assumptions": self._collect_all_assumptions(data),
            "model_versions": {
                "platform_version": metadata.get("platform_version", "1.0.0"),
                "crewai_available": metadata.get("crewai_available", False),
            },
            "double_counting_policy": metadata.get("double_counting_policy", "first_claim"),
            "reconciliation_note": reconciliation.get("reconciliation_note", ""),
            "standards_references": [
                "ISO 23247 - Digital Twin Framework",
                "ISO 55000 - Asset Management",
                "ISO 17359 - Condition Monitoring Guidelines",
                "ISO 50001 - Energy Management",
                "IPMVP + ASHRAE Guideline 14 - M&V",
                "EPA Section 608 - Refrigerant Leak Repair",
                "FDA Food Code - Temperature Controls",
                "GHG Protocol - Corporate Standard",
            ],
        }

    def _collect_all_assumptions(self, data: Dict[str, Any]) -> List[str]:
        """Collect assumptions from all KPI results."""
        assumptions = []
        for kpi_name, result in data.get("kpi_results", {}).items():
            for a in result.get("assumptions", []):
                assumptions.append(f"[{kpi_name}] {a}")
        return assumptions

    # -------------------------------------------------------------------------
    # Evidence Requirements
    # -------------------------------------------------------------------------

    def build_recommendation_evidence(
        self,
        recommendation: Dict[str, Any],
        kpi_results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        For every recommendation, build evidence package per FRD 12.2:
        - Asset/location identifiers
        - KPI impact (quant + $)
        - Evidence summary
        - Confidence score and top uncertainty drivers
        - "How to validate" checklist
        """
        kpi_sources = recommendation.get("kpi_sources", [])
        evidence = {
            "asset_ids": recommendation.get("asset_ids", []),
            "location_ids": recommendation.get("location_ids", []),
            "kpi_impacts": {},
            "evidence_summary": "",
            "confidence": recommendation.get("confidence", 0),
            "uncertainty_drivers": [],
            "validation_checklist": [],
        }

        summaries = []
        for kpi_name in kpi_sources:
            result = kpi_results.get(kpi_name, {})
            evidence["kpi_impacts"][kpi_name] = {
                "savings_medium": result.get("savings_medium", 0),
                "confidence": result.get("confidence", 0),
            }
            summaries.append(result.get("narrative", ""))

            if result.get("confidence", 1.0) < 0.6:
                evidence["uncertainty_drivers"].append(
                    f"{kpi_name}: confidence {result.get('confidence', 0):.0%}"
                )
            if result.get("gaps"):
                evidence["uncertainty_drivers"].append(
                    f"{kpi_name}: {len(result['gaps'])} data gaps"
                )

        evidence["evidence_summary"] = " | ".join(s for s in summaries if s)

        # Standard validation checklist
        evidence["validation_checklist"] = [
            "Verify baseline data completeness for affected assets",
            "Confirm labor/vendor rates match current contracts",
            "Spot-check 3 sample assets for metric accuracy",
            "Review assumptions with domain SME",
            "Compare savings estimates to industry benchmarks",
        ]

        return evidence

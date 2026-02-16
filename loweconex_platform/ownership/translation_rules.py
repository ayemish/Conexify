"""
Translation Rules — converts metrics into cost impacts.

Each rule maps a source metric to one or more CostLineItems via
formula-based or model-based computation. Supports confidence bands,
unit tracking, assumption tagging, and missing-data flagging.
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from loweconex_platform.ownership.cost_stack import CostLineItem, CostType
from loweconex_platform.ownership.metric_catalog import Quadrant

logger = logging.getLogger(__name__)


@dataclass
class TranslationRule:
    """
    A rule that translates a metric value into cost impact.

    Can be formula-based (expression string evaluated with inputs)
    or model-based (callable that returns cost).
    """
    rule_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    source_metric_id: str = ""
    target_cost_type: str = CostType.OPEX.value
    quadrant: str = Quadrant.Q1_FM_OPEX.value

    # Formula
    formula_expression: str = ""     # e.g. "wo_count * cost_per_wo * reduction_pct"
    required_inputs: List[str] = field(default_factory=list)
    output_unit: str = "$"

    # Confidence
    confidence_band: str = "medium"  # "low", "medium", "high"
    low_multiplier: float = 0.5
    high_multiplier: float = 1.5

    # Assumptions
    default_assumptions: Dict[str, Any] = field(default_factory=dict)
    assumptions_notes: List[str] = field(default_factory=list)

    # Calculation function (optional, for model-based rules)
    _calc_fn: Optional[Callable] = field(default=None, repr=False)

    # Metadata
    is_system: bool = True
    created_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def evaluate(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate this rule with the given inputs.

        Returns dict with amount, amount_low, amount_high, confidence,
        missing_inputs, assumptions_used.
        """
        # Check for missing inputs
        missing = [k for k in self.required_inputs if k not in inputs or inputs[k] is None]
        assumptions_used = []

        # Fill missing with defaults
        resolved = dict(inputs)
        for key in missing:
            if key in self.default_assumptions:
                resolved[key] = self.default_assumptions[key]
                assumptions_used.append(f"{key}={self.default_assumptions[key]} (default assumption)")

        still_missing = [k for k in self.required_inputs if k not in resolved or resolved[k] is None]

        if still_missing:
            return {
                "amount": 0.0,
                "amount_low": 0.0,
                "amount_high": 0.0,
                "confidence": 0.0,
                "missing_inputs": still_missing,
                "assumptions_used": assumptions_used,
                "error": f"Missing required inputs: {still_missing}",
            }

        # Evaluate
        try:
            if self._calc_fn:
                amount = self._calc_fn(resolved)
            else:
                amount = self._eval_formula(resolved)

            amount = float(amount)
            amount_low = amount * self.low_multiplier
            amount_high = amount * self.high_multiplier

            # Adjust confidence based on assumption usage
            confidence = {"low": 0.4, "medium": 0.7, "high": 0.9}.get(self.confidence_band, 0.7)
            if assumptions_used:
                confidence *= 0.7  # reduce confidence when assumptions are used

            return {
                "amount": round(amount, 2),
                "amount_low": round(amount_low, 2),
                "amount_high": round(amount_high, 2),
                "confidence": round(confidence, 3),
                "missing_inputs": [],
                "assumptions_used": assumptions_used,
            }

        except Exception as e:
            logger.error(f"Translation rule {self.rule_id} evaluation failed: {e}")
            return {
                "amount": 0.0,
                "amount_low": 0.0,
                "amount_high": 0.0,
                "confidence": 0.0,
                "missing_inputs": [],
                "assumptions_used": assumptions_used,
                "error": str(e),
            }

    def to_cost_line(self, inputs: Dict[str, Any], owner_roles: List[str]) -> CostLineItem:
        """Evaluate and produce a CostLineItem."""
        result = self.evaluate(inputs)
        return CostLineItem(
            name=self.name,
            description=self.description,
            cost_type=self.target_cost_type,
            owner_roles=owner_roles,
            amount=result["amount"],
            amount_low=result["amount_low"],
            amount_high=result["amount_high"],
            calculation_formula_ref=self.rule_id,
            input_metric_ids=[self.source_metric_id],
            assumptions=result.get("assumptions_used", []) + self.assumptions_notes,
            confidence=result["confidence"],
            is_savings=result["amount"] > 0,
            is_assumption_based=bool(result.get("assumptions_used")),
            missing_inputs=result.get("missing_inputs", []),
            quadrant=self.quadrant,
        )

    def _eval_formula(self, inputs: Dict[str, Any]) -> float:
        """Safely evaluate the formula expression with inputs as local vars."""
        safe_builtins = {"min": min, "max": max, "abs": abs, "round": round, "sum": sum, "math": math}
        try:
            return float(eval(self.formula_expression, {"__builtins__": safe_builtins}, inputs))
        except Exception as e:
            raise ValueError(f"Formula evaluation error: {self.formula_expression} -> {e}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "source_metric_id": self.source_metric_id,
            "target_cost_type": self.target_cost_type,
            "quadrant": self.quadrant,
            "formula_expression": self.formula_expression,
            "required_inputs": self.required_inputs,
            "output_unit": self.output_unit,
            "confidence_band": self.confidence_band,
            "low_multiplier": self.low_multiplier,
            "high_multiplier": self.high_multiplier,
            "default_assumptions": self.default_assumptions,
            "assumptions_notes": self.assumptions_notes,
            "is_system": self.is_system,
        }


class TranslationRulesLibrary:
    """
    Library of translation rules organized by quadrant.

    Pre-seeded with rules for MVP metrics:
    - Q1: reactive jobs, PPM, work order volume
    - Q2: replacement cycle
    - Q3: temperature breaches → discard/penalty EV
    - Q4: energy reduction + bundled ROI
    """

    def __init__(self):
        self._rules: Dict[str, TranslationRule] = {}
        self._seed_rules()

    # ── CRUD ────────────────────────────────────────────────────────

    def get(self, rule_id: str) -> Optional[TranslationRule]:
        return self._rules.get(rule_id)

    def list_all(self) -> List[TranslationRule]:
        return list(self._rules.values())

    def list_by_metric(self, metric_id: str) -> List[TranslationRule]:
        return [r for r in self._rules.values() if r.source_metric_id == metric_id]

    def list_by_quadrant(self, quadrant: str) -> List[TranslationRule]:
        return [r for r in self._rules.values() if r.quadrant == quadrant]

    def add(self, rule: TranslationRule) -> TranslationRule:
        self._rules[rule.rule_id] = rule
        logger.info(f"Added translation rule: {rule.name} ({rule.rule_id})")
        return rule

    def evaluate_all_for_metric(
        self, metric_id: str, inputs: Dict[str, Any], owner_roles: List[str]
    ) -> List[CostLineItem]:
        """Evaluate all rules for a metric and return cost line items."""
        rules = self.list_by_metric(metric_id)
        lines = []
        for rule in rules:
            line = rule.to_cost_line(inputs, owner_roles)
            lines.append(line)
        return lines

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rules": {rid: r.to_dict() for rid, r in self._rules.items()},
            "count": len(self._rules),
            "by_quadrant": {
                q.value: len(self.list_by_quadrant(q.value))
                for q in Quadrant
            },
        }

    # ── Seed MVP rules ──────────────────────────────────────────────

    def _seed_rules(self):
        seeds = [
            # ── Q1: FM-Controlled Opex ──────────────────────────────

            TranslationRule(
                rule_id="tr_reactive_labor",
                name="Reactive WO → Labor + Travel + Parts Cost",
                description="Translates reactive work order count into labor, travel, and parts cost impact.",
                source_metric_id="m_reactive_jobs",
                target_cost_type=CostType.OPEX.value,
                quadrant=Quadrant.Q1_FM_OPEX.value,
                formula_expression="wo_count * cost_per_wo * reduction_pct",
                required_inputs=["wo_count", "cost_per_wo", "reduction_pct"],
                default_assumptions={
                    "cost_per_wo": 380.0,
                    "reduction_pct": 0.25,
                },
                assumptions_notes=[
                    "Cost per WO: ISO 14224:2016 median ($380)",
                    "Reduction rate: Jardine et al. 2006 lower bound (25%)",
                ],
                confidence_band="medium",
            ),
            TranslationRule(
                rule_id="tr_ppm_savings",
                name="PPM Optimization → Planned Labor + Parts Savings",
                description="Translates PPM frequency optimization into planned labor and parts savings vs avoided reactive.",
                source_metric_id="m_ppm_frequency",
                target_cost_type=CostType.OPEX.value,
                quadrant=Quadrant.Q1_FM_OPEX.value,
                formula_expression="(baseline_pm_tasks - optimized_pm_tasks) * pm_cost_per_task + avoided_reactive_savings",
                required_inputs=["baseline_pm_tasks", "optimized_pm_tasks", "pm_cost_per_task", "avoided_reactive_savings"],
                default_assumptions={
                    "pm_cost_per_task": 150.0,
                    "avoided_reactive_savings": 0.0,
                },
                assumptions_notes=[
                    "PM cost per task: $150 industry average",
                ],
                confidence_band="medium",
            ),
            TranslationRule(
                rule_id="tr_wo_volume_vendor",
                name="WO Volume → Vendor Invoice + Admin Overhead",
                description="Translates work order volume into vendor invoice and internal admin overhead.",
                source_metric_id="m_wo_volume",
                target_cost_type=CostType.OPEX.value,
                quadrant=Quadrant.Q1_FM_OPEX.value,
                formula_expression="wo_volume * avg_vendor_rate * vendor_reduction_pct + wo_volume * admin_overhead_per_wo * admin_reduction_pct",
                required_inputs=["wo_volume", "avg_vendor_rate", "vendor_reduction_pct", "admin_overhead_per_wo", "admin_reduction_pct"],
                default_assumptions={
                    "avg_vendor_rate": 250.0,
                    "vendor_reduction_pct": 0.15,
                    "admin_overhead_per_wo": 45.0,
                    "admin_reduction_pct": 0.20,
                },
                assumptions_notes=[
                    "Vendor rate: $250 avg per WO (cost-plus model)",
                    "Admin overhead: $45 per WO for dispatch/coordination",
                ],
                confidence_band="medium",
            ),
            TranslationRule(
                rule_id="tr_call_center",
                name="Call Center Deflection → Cost Savings",
                description="Translates call center deflection rate into cost savings.",
                source_metric_id="m_service_bureau",
                target_cost_type=CostType.OPEX.value,
                quadrant=Quadrant.Q1_FM_OPEX.value,
                formula_expression="call_volume * cost_per_call * deflection_rate",
                required_inputs=["call_volume", "cost_per_call", "deflection_rate"],
                default_assumptions={
                    "cost_per_call": 25.0,
                    "deflection_rate": 0.30,
                },
                confidence_band="medium",
            ),

            # ── Q2: Finance-Controlled Capex ────────────────────────

            TranslationRule(
                rule_id="tr_replacement_cycle",
                name="Replacement Cycle → CapEx Outlay vs Avoided Failures",
                description="Translates asset replacement decisions into capex outlay net of avoided failure costs.",
                source_metric_id="m_replacement_cycle",
                target_cost_type=CostType.CAPEX.value,
                quadrant=Quadrant.Q2_FINANCE_CAPEX.value,
                formula_expression="replacement_count * avg_replacement_cost - avoided_failure_cost",
                required_inputs=["replacement_count", "avg_replacement_cost", "avoided_failure_cost"],
                default_assumptions={
                    "avg_replacement_cost": 18000.0,
                    "avoided_failure_cost": 5000.0,
                },
                assumptions_notes=[
                    "Average replacement cost based on asset type catalog",
                    "Avoided failure cost: estimated from historical emergency repair costs",
                ],
                confidence_band="medium",
            ),
            TranslationRule(
                rule_id="tr_lifecycle_npv",
                name="Lifecycle Model → NPV Comparison (Keep vs Replace)",
                description="Translates lifecycle cost model into NPV comparison of keep vs replace.",
                source_metric_id="m_lifecycle_model",
                target_cost_type=CostType.CAPEX.value,
                quadrant=Quadrant.Q2_FINANCE_CAPEX.value,
                formula_expression="keep_lcc_npv - replace_lcc_npv",
                required_inputs=["keep_lcc_npv", "replace_lcc_npv"],
                default_assumptions={},
                assumptions_notes=[
                    "NPV comparison per ASTM E917 LCC methodology",
                ],
                confidence_band="high",
            ),

            # ── Q3: Compliance-Driven Risk ──────────────────────────

            TranslationRule(
                rule_id="tr_temp_breach_spoilage",
                name="Temp Breaches → Spoilage + Penalty + Audit Risk",
                description="Translates temperature breach count into expected spoilage, penalty, and audit risk costs.",
                source_metric_id="m_temp_breaches",
                target_cost_type=CostType.RISK.value,
                quadrant=Quadrant.Q3_COMPLIANCE_RISK.value,
                formula_expression="breach_count * avg_spoilage_per_breach + breach_count * penalty_probability * avg_penalty + audit_risk_cost",
                required_inputs=["breach_count", "avg_spoilage_per_breach", "penalty_probability", "avg_penalty", "audit_risk_cost"],
                default_assumptions={
                    "avg_spoilage_per_breach": 2500.0,
                    "penalty_probability": 0.15,
                    "avg_penalty": 10000.0,
                    "audit_risk_cost": 5000.0,
                },
                assumptions_notes=[
                    "Spoilage per breach: $2,500 avg (perishable goods)",
                    "Penalty probability: 15% per breach (varies by jurisdiction)",
                    "Average penalty: $10,000 (FDA / local health authority)",
                    "Audit risk: additional cost of remediation and re-audit",
                ],
                confidence_band="medium",
                low_multiplier=0.4,
                high_multiplier=2.0,
            ),
            TranslationRule(
                rule_id="tr_product_discard",
                name="Product Discard → COGS + Labor + Disposal",
                description="Translates product discard volume into COGS loss, labor, and waste disposal costs.",
                source_metric_id="m_product_discard",
                target_cost_type=CostType.RISK.value,
                quadrant=Quadrant.Q3_COMPLIANCE_RISK.value,
                formula_expression="discard_volume * avg_cogs_per_unit + discard_events * labor_per_event + discard_volume * disposal_cost_per_unit",
                required_inputs=["discard_volume", "avg_cogs_per_unit", "discard_events", "labor_per_event", "disposal_cost_per_unit"],
                default_assumptions={
                    "avg_cogs_per_unit": 8.0,
                    "labor_per_event": 120.0,
                    "disposal_cost_per_unit": 1.5,
                },
                confidence_band="medium",
            ),
            TranslationRule(
                rule_id="tr_regulatory_penalty",
                name="Regulatory Penalties → Fine + Remediation",
                description="Translates regulatory penalty events into fine schedule and remediation costs.",
                source_metric_id="m_regulatory_penalties",
                target_cost_type=CostType.RISK.value,
                quadrant=Quadrant.Q3_COMPLIANCE_RISK.value,
                formula_expression="penalty_events * avg_fine + penalty_events * remediation_cost",
                required_inputs=["penalty_events", "avg_fine", "remediation_cost"],
                default_assumptions={
                    "avg_fine": 15000.0,
                    "remediation_cost": 8000.0,
                },
                confidence_band="low",
                low_multiplier=0.3,
                high_multiplier=3.0,
            ),

            # ── Q4: Cross-Silo Strategic ────────────────────────────

            TranslationRule(
                rule_id="tr_energy_reduction",
                name="Energy Reduction → Utility Savings + Carbon Value",
                description="Translates energy reduction into utility bill savings and carbon credit value.",
                source_metric_id="m_energy_reduction",
                target_cost_type=CostType.STRATEGIC.value,
                quadrant=Quadrant.Q4_CROSS_SILO.value,
                formula_expression="kwh_reduction * electricity_rate + kwh_reduction * carbon_factor * carbon_price",
                required_inputs=["kwh_reduction", "electricity_rate", "carbon_factor", "carbon_price"],
                default_assumptions={
                    "electricity_rate": 0.12,
                    "carbon_factor": 0.0004,   # tCO2e per kWh
                    "carbon_price": 50.0,       # $ per tCO2e
                },
                assumptions_notes=[
                    "Electricity rate: $0.12/kWh (US average)",
                    "Carbon factor: 0.4 kg CO2e/kWh (US grid average)",
                    "Carbon price: $50/tCO2e (voluntary market)",
                ],
                confidence_band="high",
            ),
            TranslationRule(
                rule_id="tr_cross_silo_bundle",
                name="Cross-Silo Initiative → Aggregated Multi-Quadrant Benefits",
                description="Aggregates benefits across Q1+Q2+Q3 into a single strategic initiative ROI.",
                source_metric_id="m_cross_silo_initiative",
                target_cost_type=CostType.STRATEGIC.value,
                quadrant=Quadrant.Q4_CROSS_SILO.value,
                formula_expression="q1_opex_savings + q2_capex_avoided + q3_risk_reduction + energy_savings + emissions_value",
                required_inputs=["q1_opex_savings", "q2_capex_avoided", "q3_risk_reduction", "energy_savings", "emissions_value"],
                default_assumptions={},
                assumptions_notes=[
                    "Components sourced from Q1, Q2, Q3 translation outputs",
                    "Subject to anti-double-counting allocation rules",
                ],
                confidence_band="medium",
            ),
            TranslationRule(
                rule_id="tr_emissions_reduction",
                name="Emissions Reduction → Carbon Credit + Compliance Value",
                description="Translates GHG emissions reduction into carbon credit and compliance reporting value.",
                source_metric_id="m_emissions_reduction",
                target_cost_type=CostType.STRATEGIC.value,
                quadrant=Quadrant.Q4_CROSS_SILO.value,
                formula_expression="emissions_reduced_tco2e * carbon_price + compliance_reporting_value",
                required_inputs=["emissions_reduced_tco2e", "carbon_price", "compliance_reporting_value"],
                default_assumptions={
                    "carbon_price": 50.0,
                    "compliance_reporting_value": 10000.0,
                },
                confidence_band="medium",
            ),
        ]

        for rule in seeds:
            rule.is_system = True
            self._rules[rule.rule_id] = rule

        logger.info(f"Seeded {len(seeds)} translation rules across Q1-Q4")

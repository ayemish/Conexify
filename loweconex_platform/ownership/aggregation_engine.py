"""
Cross-Silo Aggregation Engine — aggregates cost impacts across owners,
cost types, org levels, and time horizons.

Handles benefit bundling for Q4 initiatives, dependency graph tracking,
and anti-double-counting allocation rules.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from loweconex_platform.ownership.cost_stack import CostLineItem, CostStack, CostType
from loweconex_platform.ownership.metric_catalog import MetricCatalog, Quadrant
from loweconex_platform.ownership.ownership_model import OwnershipEngine
from loweconex_platform.ownership.translation_rules import TranslationRulesLibrary

logger = logging.getLogger(__name__)


@dataclass
class DependencyEdge:
    """A directed edge in the benefit dependency graph."""
    source_metric_id: str = ""
    target_metric_id: str = ""
    overlap_type: str = ""        # "subsumes", "partial_overlap", "independent"
    overlap_fraction: float = 0.0  # fraction of target benefit that overlaps source
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_metric_id": self.source_metric_id,
            "target_metric_id": self.target_metric_id,
            "overlap_type": self.overlap_type,
            "overlap_fraction": self.overlap_fraction,
            "description": self.description,
        }


@dataclass
class BenefitBundle:
    """
    A bundled initiative that aggregates benefits from multiple metrics
    across quadrants (typically Q4 cross-silo).
    """
    bundle_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    constituent_metric_ids: List[str] = field(default_factory=list)
    allocated_benefits_by_owner: Dict[str, float] = field(default_factory=dict)
    total_benefit: float = 0.0
    total_cost: float = 0.0
    net_benefit: float = 0.0
    confidence: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "name": self.name,
            "description": self.description,
            "constituent_metric_ids": self.constituent_metric_ids,
            "allocated_benefits_by_owner": self.allocated_benefits_by_owner,
            "total_benefit": self.total_benefit,
            "total_cost": self.total_cost,
            "net_benefit": self.net_benefit,
            "confidence": self.confidence,
        }


# Known overlap relationships for anti-double-counting
OVERLAP_RULES: List[DependencyEdge] = [
    DependencyEdge(
        source_metric_id="m_temp_breaches",
        target_metric_id="m_product_discard",
        overlap_type="subsumes",
        overlap_fraction=0.7,
        description="Reduced temp breaches implies reduced product discard (70% overlap)",
    ),
    DependencyEdge(
        source_metric_id="m_energy_reduction",
        target_metric_id="m_emissions_reduction",
        overlap_type="partial_overlap",
        overlap_fraction=0.5,
        description="Energy reduction drives ~50% of emissions reduction",
    ),
    DependencyEdge(
        source_metric_id="m_reactive_jobs",
        target_metric_id="m_wo_volume",
        overlap_type="subsumes",
        overlap_fraction=0.6,
        description="Reactive job reduction reduces overall WO volume (60% overlap)",
    ),
    DependencyEdge(
        source_metric_id="m_ppm_frequency",
        target_metric_id="m_reactive_jobs",
        overlap_type="partial_overlap",
        overlap_fraction=0.3,
        description="Better PPM reduces reactive jobs (30% attribution)",
    ),
    DependencyEdge(
        source_metric_id="m_refrigerant_leakage",
        target_metric_id="m_energy_reduction",
        overlap_type="partial_overlap",
        overlap_fraction=0.2,
        description="Leak repair improves efficiency → energy savings (20%)",
    ),
]


class AggregationEngine:
    """
    Aggregates translated cost impacts across owners, cost types,
    org levels, and time horizons.

    Prevents double-counting via dependency graph and allocation rules.
    Supports benefit bundling for Q4 cross-silo initiatives.
    """

    def __init__(
        self,
        metric_catalog: MetricCatalog,
        ownership_engine: OwnershipEngine,
        rules_library: TranslationRulesLibrary,
    ):
        self._catalog = metric_catalog
        self._ownership = ownership_engine
        self._rules = rules_library
        self._dependency_edges = list(OVERLAP_RULES)
        self._adjustments: List[Dict[str, Any]] = []

    # ── Full pipeline ───────────────────────────────────────────────

    def build_cost_stack(
        self,
        metric_inputs: Dict[str, Dict[str, Any]],
        scenario_id: Optional[str] = None,
    ) -> CostStack:
        """
        Build a complete cost stack from metric inputs.

        Args:
            metric_inputs: {metric_id: {input_name: value, ...}}
            scenario_id: optional scenario identifier

        Returns:
            CostStack with all translated, ownership-attributed, de-duplicated lines.
        """
        stack = CostStack(scenario_id=scenario_id)
        self._adjustments.clear()

        # Step 1: Translate each metric into cost line items
        raw_lines: List[CostLineItem] = []
        for metric_id, inputs in metric_inputs.items():
            metric = self._catalog.get(metric_id)
            if not metric:
                logger.warning(f"Metric {metric_id} not found in catalog, skipping")
                continue

            # Resolve ownership
            ownership = self._ownership.resolve(metric_id)
            owner_roles = [ownership.get("accountable", metric.default_owner_role)]
            if ownership.get("responsible"):
                owner_roles.append(ownership["responsible"])

            # Evaluate all translation rules for this metric
            lines = self._rules.evaluate_all_for_metric(metric_id, inputs, owner_roles)
            raw_lines.extend(lines)

        # Step 2: Apply anti-double-counting
        adjusted_lines = self._apply_overlap_adjustments(raw_lines)

        # Step 3: Add to cost stack
        stack.add_lines(adjusted_lines)

        logger.info(
            f"Built cost stack: {len(adjusted_lines)} lines, "
            f"{len(self._adjustments)} adjustments applied"
        )
        return stack

    # ── Benefit bundling ────────────────────────────────────────────

    def create_bundle(
        self,
        name: str,
        metric_ids: List[str],
        cost_stack: CostStack,
    ) -> BenefitBundle:
        """
        Create a benefit bundle aggregating multiple metric cost lines
        into a single initiative-level view (Q4).
        """
        bundle_lines = [
            line for line in cost_stack.lines
            if any(mid in line.input_metric_ids for mid in metric_ids)
        ]

        # Aggregate by owner
        by_owner: Dict[str, float] = {}
        total_benefit = 0.0
        total_cost_val = 0.0
        confidences: List[float] = []

        for line in bundle_lines:
            for owner in line.owner_roles:
                weight = 1.0 / len(line.owner_roles) if line.owner_roles else 1.0
                by_owner[owner] = by_owner.get(owner, 0.0) + line.amount * weight

            if line.is_savings:
                total_benefit += line.amount
            else:
                total_cost_val += abs(line.amount)
            confidences.append(line.confidence)

        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        return BenefitBundle(
            name=name,
            constituent_metric_ids=metric_ids,
            allocated_benefits_by_owner=by_owner,
            total_benefit=round(total_benefit, 2),
            total_cost=round(total_cost_val, 2),
            net_benefit=round(total_benefit - total_cost_val, 2),
            confidence=round(avg_confidence, 3),
        )

    # ── Dependency graph ────────────────────────────────────────────

    def add_overlap_rule(self, edge: DependencyEdge):
        self._dependency_edges.append(edge)

    def get_dependency_graph(self) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self._dependency_edges]

    def get_adjustments(self) -> List[Dict[str, Any]]:
        return list(self._adjustments)

    # ── Anti-double-counting ────────────────────────────────────────

    def _apply_overlap_adjustments(
        self, lines: List[CostLineItem]
    ) -> List[CostLineItem]:
        """
        Apply overlap adjustments to prevent double-counting.

        When two metrics have overlapping cost impacts, reduce the
        downstream metric's contribution by the overlap fraction.
        """
        # Index lines by source metric
        lines_by_metric: Dict[str, List[CostLineItem]] = {}
        for line in lines:
            for mid in line.input_metric_ids:
                if mid not in lines_by_metric:
                    lines_by_metric[mid] = []
                lines_by_metric[mid].append(line)

        # Track which metrics have been processed (for precedence)
        processed: Set[str] = set()
        adjusted_lines: List[CostLineItem] = []

        # Process in quadrant order: Q1 → Q2 → Q3 → Q4
        quadrant_order = [
            Quadrant.Q1_FM_OPEX.value,
            Quadrant.Q2_FINANCE_CAPEX.value,
            Quadrant.Q3_COMPLIANCE_RISK.value,
            Quadrant.Q4_CROSS_SILO.value,
        ]

        for quadrant in quadrant_order:
            quadrant_lines = [l for l in lines if l.quadrant == quadrant]
            for line in quadrant_lines:
                adjustment_factor = 1.0

                for mid in line.input_metric_ids:
                    # Check if any overlap rule applies
                    for edge in self._dependency_edges:
                        if edge.target_metric_id == mid and edge.source_metric_id in processed:
                            reduction = edge.overlap_fraction
                            adjustment_factor *= (1.0 - reduction)
                            self._adjustments.append({
                                "type": "overlap_reduction",
                                "target_metric": mid,
                                "source_metric": edge.source_metric_id,
                                "overlap_fraction": reduction,
                                "description": edge.description,
                                "adjusted_line_id": line.line_id,
                            })

                # Apply adjustment
                if adjustment_factor < 1.0:
                    line.amount = round(line.amount * adjustment_factor, 2)
                    line.amount_low = round(line.amount_low * adjustment_factor, 2)
                    line.amount_high = round(line.amount_high * adjustment_factor, 2)
                    line.assumptions.append(
                        f"Adjusted by {(1-adjustment_factor)*100:.0f}% for overlap with upstream metrics"
                    )

                adjusted_lines.append(line)
                for mid in line.input_metric_ids:
                    processed.add(mid)

        return adjusted_lines

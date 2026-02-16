"""
Metric Catalog — system-managed and user-extensible metric definitions
with Q1-Q4 quadrant classification and owner defaults.

Each metric is classified into one of four quadrants:
  Q1: FM-Controlled Opex
  Q2: Finance-Controlled Capex
  Q3: Compliance-Driven Risk
  Q4: Cross-Silo Strategic
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Quadrant(str, Enum):
    """Ownership vs Cost Type quadrant classification."""
    Q1_FM_OPEX = "Q1"
    Q2_FINANCE_CAPEX = "Q2"
    Q3_COMPLIANCE_RISK = "Q3"
    Q4_CROSS_SILO = "Q4"


class SourceType(str, Enum):
    CMMS = "cmms"
    IOT = "iot"
    ENERGY_BILLS = "energy_bills"
    AUDITS = "audits"
    ERP = "erp"
    MANUAL = "manual"
    CALCULATED = "calculated"


class UnitType(str, Enum):
    COUNT = "count"
    HOURS = "hours"
    CURRENCY = "$"
    KWH = "kWh"
    INCIDENTS = "incidents"
    PROBABILITY = "probability"
    PERCENT = "%"
    TEMPERATURE = "temperature"
    WEIGHT = "weight"
    EMISSIONS = "tCO2e"


class MeasurementFrequency(str, Enum):
    REAL_TIME = "real_time"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUALLY = "annually"


@dataclass
class ConfidenceInputs:
    """Data quality inputs that drive metric confidence scoring."""
    data_quality_rating: float = 0.5       # 0.0 - 1.0
    coverage_pct: float = 0.5              # 0.0 - 1.0
    recency_days: int = 30                 # days since last update
    source_reliability: float = 0.7        # 0.0 - 1.0

    @property
    def composite_score(self) -> float:
        recency_factor = max(0.0, 1.0 - (self.recency_days / 365.0))
        return round(
            self.data_quality_rating * 0.3
            + self.coverage_pct * 0.3
            + recency_factor * 0.2
            + self.source_reliability * 0.2,
            3,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "data_quality_rating": self.data_quality_rating,
            "coverage_pct": self.coverage_pct,
            "recency_days": self.recency_days,
            "source_reliability": self.source_reliability,
            "composite_score": self.composite_score,
        }


@dataclass
class MetricDefinition:
    """A single metric in the catalog with quadrant and owner classification."""
    metric_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    quadrant: str = Quadrant.Q1_FM_OPEX.value
    default_owner_role: str = "fm"          # matches OwnerRole values
    unit_type: str = UnitType.COUNT.value
    measurement_frequency: str = MeasurementFrequency.MONTHLY.value
    source_type: str = SourceType.CMMS.value
    confidence_inputs: ConfidenceInputs = field(default_factory=ConfidenceInputs)
    cost_mapping_rule_ids: List[str] = field(default_factory=list)

    # Links to existing KPI crews (if any)
    kpi_crew_name: Optional[str] = None

    # Admin metadata
    is_system: bool = True       # False for user-created metrics
    created_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_by: str = "system"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "name": self.name,
            "description": self.description,
            "quadrant": self.quadrant,
            "default_owner_role": self.default_owner_role,
            "unit_type": self.unit_type,
            "measurement_frequency": self.measurement_frequency,
            "source_type": self.source_type,
            "confidence_inputs": self.confidence_inputs.to_dict(),
            "cost_mapping_rule_ids": self.cost_mapping_rule_ids,
            "kpi_crew_name": self.kpi_crew_name,
            "is_system": self.is_system,
            "created_ts": self.created_ts,
            "updated_ts": self.updated_ts,
            "created_by": self.created_by,
        }


class MetricCatalog:
    """
    Registry of all metric definitions with quadrant classification.

    Supports system-seeded metrics (from existing KPI crews) and
    user-extensible custom metrics.
    """

    def __init__(self):
        self._metrics: Dict[str, MetricDefinition] = {}
        self._seed_system_metrics()

    # ── CRUD ────────────────────────────────────────────────────────

    def get(self, metric_id: str) -> Optional[MetricDefinition]:
        return self._metrics.get(metric_id)

    def get_by_name(self, name: str) -> Optional[MetricDefinition]:
        for m in self._metrics.values():
            if m.name == name:
                return m
        return None

    def list_all(self) -> List[MetricDefinition]:
        return list(self._metrics.values())

    def list_by_quadrant(self, quadrant: str) -> List[MetricDefinition]:
        return [m for m in self._metrics.values() if m.quadrant == quadrant]

    def list_by_owner(self, owner_role: str) -> List[MetricDefinition]:
        return [m for m in self._metrics.values() if m.default_owner_role == owner_role]

    def add(self, metric: MetricDefinition) -> MetricDefinition:
        metric.updated_ts = datetime.utcnow().isoformat()
        self._metrics[metric.metric_id] = metric
        logger.info(f"Added metric: {metric.name} ({metric.metric_id}) [{metric.quadrant}]")
        return metric

    def update(self, metric_id: str, updates: Dict[str, Any]) -> Optional[MetricDefinition]:
        metric = self._metrics.get(metric_id)
        if not metric:
            return None
        for key, value in updates.items():
            if hasattr(metric, key) and key not in ("metric_id", "is_system", "created_ts"):
                setattr(metric, key, value)
        metric.updated_ts = datetime.utcnow().isoformat()
        return metric

    def delete(self, metric_id: str) -> bool:
        metric = self._metrics.get(metric_id)
        if metric and not metric.is_system:
            del self._metrics[metric_id]
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metrics": {mid: m.to_dict() for mid, m in self._metrics.items()},
            "count": len(self._metrics),
            "by_quadrant": {
                q.value: len(self.list_by_quadrant(q.value))
                for q in Quadrant
            },
        }

    # ── Seed system metrics ─────────────────────────────────────────

    def _seed_system_metrics(self):
        """Seed catalog with metrics mapped from existing KPI crews."""
        seeds = [
            # ── Q1: FM-Controlled Opex ──────────────────────────────
            MetricDefinition(
                metric_id="m_reactive_jobs",
                name="Reactive Work Orders",
                description="Count and cost of unplanned reactive maintenance work orders.",
                quadrant=Quadrant.Q1_FM_OPEX.value,
                default_owner_role="fm",
                unit_type=UnitType.COUNT.value,
                measurement_frequency=MeasurementFrequency.DAILY.value,
                source_type=SourceType.CMMS.value,
                kpi_crew_name="work_order_reduction",
            ),
            MetricDefinition(
                metric_id="m_ppm_frequency",
                name="Planned Preventive Maintenance Frequency",
                description="PPM task execution rate and schedule adherence.",
                quadrant=Quadrant.Q1_FM_OPEX.value,
                default_owner_role="fm",
                unit_type=UnitType.COUNT.value,
                measurement_frequency=MeasurementFrequency.WEEKLY.value,
                source_type=SourceType.CMMS.value,
                kpi_crew_name="ppm_maximization",
            ),
            MetricDefinition(
                metric_id="m_wo_volume",
                name="Work Order Volume",
                description="Total work order volume driving vendor invoice and admin overhead.",
                quadrant=Quadrant.Q1_FM_OPEX.value,
                default_owner_role="fm",
                unit_type=UnitType.COUNT.value,
                measurement_frequency=MeasurementFrequency.MONTHLY.value,
                source_type=SourceType.CMMS.value,
                kpi_crew_name="work_order_reduction",
            ),
            MetricDefinition(
                metric_id="m_tech_utilization",
                name="Technician Utilization",
                description="Technician productive hours vs available hours, overtime, and backlog.",
                quadrant=Quadrant.Q1_FM_OPEX.value,
                default_owner_role="fm",
                unit_type=UnitType.PERCENT.value,
                measurement_frequency=MeasurementFrequency.WEEKLY.value,
                source_type=SourceType.CMMS.value,
            ),
            MetricDefinition(
                metric_id="m_repeat_failures",
                name="Repeat Failure Rate",
                description="Percentage of work orders on same asset within 30-day window.",
                quadrant=Quadrant.Q1_FM_OPEX.value,
                default_owner_role="fm",
                unit_type=UnitType.PERCENT.value,
                measurement_frequency=MeasurementFrequency.MONTHLY.value,
                source_type=SourceType.CMMS.value,
                kpi_crew_name="work_order_reduction",
            ),
            MetricDefinition(
                metric_id="m_service_bureau",
                name="Service Bureau / Call Center Volume",
                description="Call center dispatch volume and deflection rate.",
                quadrant=Quadrant.Q1_FM_OPEX.value,
                default_owner_role="fm",
                unit_type=UnitType.COUNT.value,
                measurement_frequency=MeasurementFrequency.DAILY.value,
                source_type=SourceType.CMMS.value,
                kpi_crew_name="call_center_volume_reduction",
            ),
            MetricDefinition(
                metric_id="m_vendor_cost",
                name="Vendor Invoice Cost",
                description="Total vendor invoice spend per period.",
                quadrant=Quadrant.Q1_FM_OPEX.value,
                default_owner_role="fm",
                unit_type=UnitType.CURRENCY.value,
                measurement_frequency=MeasurementFrequency.MONTHLY.value,
                source_type=SourceType.ERP.value,
                kpi_crew_name="service_bureau_reduction",
            ),

            # ── Q2: Finance-Controlled Capex ────────────────────────
            MetricDefinition(
                metric_id="m_replacement_cycle",
                name="Asset Replacement Cycle",
                description="Replacement timing based on age, condition, failure probability.",
                quadrant=Quadrant.Q2_FINANCE_CAPEX.value,
                default_owner_role="finance",
                unit_type=UnitType.CURRENCY.value,
                measurement_frequency=MeasurementFrequency.QUARTERLY.value,
                source_type=SourceType.ERP.value,
                kpi_crew_name="capex_lifecycle_optimization",
            ),
            MetricDefinition(
                metric_id="m_lifecycle_model",
                name="Lifecycle Cost Model",
                description="Expected replacement timing, residual value, and total lifecycle cost.",
                quadrant=Quadrant.Q2_FINANCE_CAPEX.value,
                default_owner_role="finance",
                unit_type=UnitType.CURRENCY.value,
                measurement_frequency=MeasurementFrequency.QUARTERLY.value,
                source_type=SourceType.CALCULATED.value,
                kpi_crew_name="capex_lifecycle_optimization",
            ),
            MetricDefinition(
                metric_id="m_capital_efficiency",
                name="Capital Efficiency (ROI per CapEx $)",
                description="Return on investment per capex dollar under budget constraint.",
                quadrant=Quadrant.Q2_FINANCE_CAPEX.value,
                default_owner_role="finance",
                unit_type=UnitType.CURRENCY.value,
                measurement_frequency=MeasurementFrequency.QUARTERLY.value,
                source_type=SourceType.CALCULATED.value,
            ),
            MetricDefinition(
                metric_id="m_asset_condition",
                name="Asset Condition Score",
                description="Composite condition score from age, health index, degradation.",
                quadrant=Quadrant.Q2_FINANCE_CAPEX.value,
                default_owner_role="finance",
                unit_type=UnitType.COUNT.value,
                measurement_frequency=MeasurementFrequency.MONTHLY.value,
                source_type=SourceType.IOT.value,
                kpi_crew_name="failure_prediction_accuracy",
            ),

            # ── Q3: Compliance-Driven Risk ──────────────────────────
            MetricDefinition(
                metric_id="m_temp_breaches",
                name="Temperature Breaches",
                description="Count and duration of food safety temperature excursions.",
                quadrant=Quadrant.Q3_COMPLIANCE_RISK.value,
                default_owner_role="food_safety",
                unit_type=UnitType.INCIDENTS.value,
                measurement_frequency=MeasurementFrequency.DAILY.value,
                source_type=SourceType.IOT.value,
                kpi_crew_name="food_temp_diagnostics_improvement",
            ),
            MetricDefinition(
                metric_id="m_product_discard",
                name="Product Discard / Spoilage",
                description="Product discarded due to temperature excursions.",
                quadrant=Quadrant.Q3_COMPLIANCE_RISK.value,
                default_owner_role="food_safety",
                unit_type=UnitType.CURRENCY.value,
                measurement_frequency=MeasurementFrequency.DAILY.value,
                source_type=SourceType.MANUAL.value,
                kpi_crew_name="food_waste_reduction",
            ),
            MetricDefinition(
                metric_id="m_regulatory_penalties",
                name="Regulatory Penalties",
                description="Fines, penalties, and audit failure costs.",
                quadrant=Quadrant.Q3_COMPLIANCE_RISK.value,
                default_owner_role="food_safety",
                unit_type=UnitType.CURRENCY.value,
                measurement_frequency=MeasurementFrequency.MONTHLY.value,
                source_type=SourceType.AUDITS.value,
                kpi_crew_name="food_safety_compliance",
            ),
            MetricDefinition(
                metric_id="m_brand_exposure",
                name="Brand Exposure Risk",
                description="Estimated brand damage from compliance failures (configurable proxy).",
                quadrant=Quadrant.Q3_COMPLIANCE_RISK.value,
                default_owner_role="food_safety",
                unit_type=UnitType.CURRENCY.value,
                measurement_frequency=MeasurementFrequency.QUARTERLY.value,
                source_type=SourceType.CALCULATED.value,
            ),
            MetricDefinition(
                metric_id="m_refrigerant_leakage",
                name="Refrigerant Leakage",
                description="Refrigerant leak rate and associated costs.",
                quadrant=Quadrant.Q3_COMPLIANCE_RISK.value,
                default_owner_role="food_safety",
                unit_type=UnitType.WEIGHT.value,
                measurement_frequency=MeasurementFrequency.MONTHLY.value,
                source_type=SourceType.IOT.value,
                kpi_crew_name="refrigerant_leak_reduction",
            ),

            # ── Q4: Cross-Silo Strategic ────────────────────────────
            MetricDefinition(
                metric_id="m_energy_reduction",
                name="Energy Reduction",
                description="Energy savings from equipment efficiency and optimization.",
                quadrant=Quadrant.Q4_CROSS_SILO.value,
                default_owner_role="esg",
                unit_type=UnitType.KWH.value,
                measurement_frequency=MeasurementFrequency.MONTHLY.value,
                source_type=SourceType.ENERGY_BILLS.value,
                kpi_crew_name="energy_reduction",
            ),
            MetricDefinition(
                metric_id="m_emissions_reduction",
                name="Emissions Reduction",
                description="GHG emissions avoided through energy and refrigerant improvements.",
                quadrant=Quadrant.Q4_CROSS_SILO.value,
                default_owner_role="esg",
                unit_type=UnitType.EMISSIONS.value,
                measurement_frequency=MeasurementFrequency.MONTHLY.value,
                source_type=SourceType.CALCULATED.value,
                kpi_crew_name="esg_compliance",
            ),
            MetricDefinition(
                metric_id="m_cross_silo_initiative",
                name="Cross-Silo Initiative ROI",
                description="Aggregated benefits across Q1-Q3 + energy + emissions for strategic initiatives.",
                quadrant=Quadrant.Q4_CROSS_SILO.value,
                default_owner_role="executive",
                unit_type=UnitType.CURRENCY.value,
                measurement_frequency=MeasurementFrequency.QUARTERLY.value,
                source_type=SourceType.CALCULATED.value,
            ),
            MetricDefinition(
                metric_id="m_ai_optimization",
                name="AI/Analytics Optimization Value",
                description="Value from AI-driven control: energy + reduced failures + improved compliance.",
                quadrant=Quadrant.Q4_CROSS_SILO.value,
                default_owner_role="executive",
                unit_type=UnitType.CURRENCY.value,
                measurement_frequency=MeasurementFrequency.QUARTERLY.value,
                source_type=SourceType.CALCULATED.value,
            ),
            MetricDefinition(
                metric_id="m_uptime_improvement",
                name="System Uptime Improvement",
                description="Improved equipment uptime from predictive maintenance.",
                quadrant=Quadrant.Q4_CROSS_SILO.value,
                default_owner_role="ops",
                unit_type=UnitType.PERCENT.value,
                measurement_frequency=MeasurementFrequency.MONTHLY.value,
                source_type=SourceType.IOT.value,
                kpi_crew_name="uptime_improvement",
            ),
            MetricDefinition(
                metric_id="m_pm_optimization",
                name="PM Schedule Optimization",
                description="Savings from optimizing preventive maintenance intervals.",
                quadrant=Quadrant.Q4_CROSS_SILO.value,
                default_owner_role="ops",
                unit_type=UnitType.CURRENCY.value,
                measurement_frequency=MeasurementFrequency.MONTHLY.value,
                source_type=SourceType.CALCULATED.value,
                kpi_crew_name="preventive_maintenance_optimization",
            ),
        ]

        for metric in seeds:
            metric.is_system = True
            self._metrics[metric.metric_id] = metric

        logger.info(f"Seeded {len(seeds)} system metrics across Q1-Q4")

"""
Ownership-Aware Cost Decision Support Module.

Provides metric catalog, ownership mapping, cost stack generation,
cross-silo aggregation, and consolidated ROI with Q1-Q4 quadrant
classification for maintenance and replacement decision support.
"""

from loweconex_platform.ownership.metric_catalog import (
    Quadrant,
    MetricDefinition,
    MetricCatalog,
)
from loweconex_platform.ownership.ownership_model import (
    OwnerRole,
    OwnershipAssignment,
    OwnershipEngine,
)
from loweconex_platform.ownership.cost_stack import (
    CostType,
    CostLineItem,
    CostStack,
)
from loweconex_platform.ownership.translation_rules import (
    TranslationRule,
    TranslationRulesLibrary,
)
from loweconex_platform.ownership.aggregation_engine import (
    AggregationEngine,
    BenefitBundle,
)
from loweconex_platform.ownership.consolidated_roi import (
    ConsolidatedROI,
    ConsolidatedROIEngine,
)
from loweconex_platform.ownership.constraint_optimizer import (
    ConstraintOptimizer,
    BudgetConstraints,
)
from loweconex_platform.ownership.parameter_hierarchy import (
    ParameterHierarchy,
    ParameterDefinition,
)
from loweconex_platform.ownership.scenario_extensions import (
    OwnershipScenario,
    ScenarioManager,
)
from loweconex_platform.ownership.api_routes import (
    OwnershipDecisionService,
    get_service,
)
from loweconex_platform.ownership.quadrant_validator import (
    QuadrantValidator,
    ValidationReport,
    ValidationIssue,
    QUADRANT_COST_TYPE,
)
from loweconex_platform.ownership.governance_engine import (
    GovernanceEngine,
    ChangeRequest,
    AuditEntry,
    ApprovalStatus,
    ChangeType,
    ImpactLevel,
)

# Multi-agent crew (graceful import)
try:
    from loweconex_platform.ownership.crew.decision_crew import OwnershipDecisionCrew
    from loweconex_platform.ownership.crew.schemas import DecisionCrewOutput
    OWNERSHIP_CREW_AVAILABLE = True
except ImportError:
    OWNERSHIP_CREW_AVAILABLE = False

__all__ = [
    "Quadrant",
    "MetricDefinition",
    "MetricCatalog",
    "OwnerRole",
    "OwnershipAssignment",
    "OwnershipEngine",
    "CostType",
    "CostLineItem",
    "CostStack",
    "TranslationRule",
    "TranslationRulesLibrary",
    "AggregationEngine",
    "BenefitBundle",
    "ConsolidatedROI",
    "ConsolidatedROIEngine",
    "ConstraintOptimizer",
    "BudgetConstraints",
    "ParameterHierarchy",
    "ParameterDefinition",
    "OwnershipScenario",
    "ScenarioManager",
    "OwnershipDecisionService",
    "get_service",
    "QuadrantValidator",
    "ValidationReport",
    "ValidationIssue",
    "QUADRANT_COST_TYPE",
    "GovernanceEngine",
    "ChangeRequest",
    "AuditEntry",
    "ApprovalStatus",
    "ChangeType",
    "ImpactLevel",
]

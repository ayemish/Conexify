"""
API Routes for the Ownership-Aware Decision Support Module.

Provides REST endpoints for metric catalog, ownership mapping,
cost stack, consolidated ROI, scenarios, parameters, and advisory.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from loweconex_platform.ownership.metric_catalog import MetricCatalog, MetricDefinition, Quadrant
from loweconex_platform.ownership.ownership_model import OwnershipEngine, OwnershipAssignment, OwnerWeight
from loweconex_platform.ownership.cost_stack import CostStack
from loweconex_platform.ownership.translation_rules import TranslationRulesLibrary
from loweconex_platform.ownership.aggregation_engine import AggregationEngine
from loweconex_platform.ownership.consolidated_roi import ConsolidatedROIEngine
from loweconex_platform.ownership.constraint_optimizer import ConstraintOptimizer, BudgetConstraints
from loweconex_platform.ownership.parameter_hierarchy import ParameterHierarchy
from loweconex_platform.ownership.scenario_extensions import ScenarioManager

logger = logging.getLogger(__name__)


class OwnershipDecisionService:
    """
    Facade that wires all ownership module components together
    and exposes a clean API surface for the frontend.

    This is instantiated once and shared across API routes.
    """

    def __init__(self):
        # Core components
        self.catalog = MetricCatalog()
        self.ownership = OwnershipEngine()
        self.rules = TranslationRulesLibrary()
        self.params = ParameterHierarchy()
        self.roi_engine = ConsolidatedROIEngine()
        self.optimizer = ConstraintOptimizer()

        # Aggregation engine needs references to core components
        self.aggregation = AggregationEngine(
            metric_catalog=self.catalog,
            ownership_engine=self.ownership,
            rules_library=self.rules,
        )

        # Scenario manager needs parameter hierarchy
        self.scenarios = ScenarioManager(parameter_hierarchy=self.params)

        # Initialize default ownership from metric catalog
        self._init_default_ownership()

    def _init_default_ownership(self):
        """Set default ownership for all catalog metrics based on quadrant."""
        for metric in self.catalog.list_all():
            self.ownership.set_default_from_quadrant(metric.metric_id, metric.quadrant)

    # ═══════════════════════════════════════════════════════════════
    # Metric Catalog API
    # ═══════════════════════════════════════════════════════════════

    def get_metrics(self, quadrant: Optional[str] = None, owner: Optional[str] = None) -> Dict[str, Any]:
        if quadrant:
            metrics = self.catalog.list_by_quadrant(quadrant)
        elif owner:
            metrics = self.catalog.list_by_owner(owner)
        else:
            metrics = self.catalog.list_all()
        return {
            "metrics": [m.to_dict() for m in metrics],
            "count": len(metrics),
        }

    def add_metric(self, data: Dict[str, Any]) -> Dict[str, Any]:
        metric = MetricDefinition(
            name=data.get("name", ""),
            description=data.get("description", ""),
            quadrant=data.get("quadrant", "Q1"),
            default_owner_role=data.get("default_owner_role", "fm"),
            unit_type=data.get("unit_type", "count"),
            measurement_frequency=data.get("measurement_frequency", "monthly"),
            source_type=data.get("source_type", "manual"),
            is_system=False,
            created_by=data.get("created_by", "user"),
        )
        self.catalog.add(metric)
        self.ownership.set_default_from_quadrant(metric.metric_id, metric.quadrant)
        return metric.to_dict()

    # ═══════════════════════════════════════════════════════════════
    # Ownership API
    # ═══════════════════════════════════════════════════════════════

    def get_ownership_map(self) -> Dict[str, Any]:
        all_resolved = self.ownership.resolve_all()
        return {
            "ownership_map": all_resolved,
            "count": len(all_resolved),
        }

    def override_ownership(self, metric_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        weights = None
        if data.get("owner_weights"):
            weights = [
                OwnerWeight(owner_role=w["owner_role"], weight=w["weight"])
                for w in data["owner_weights"]
            ]
        assignment = self.ownership.override(
            metric_id=metric_id,
            org_level=data.get("org_level", "global"),
            org_entity=data.get("org_entity", ""),
            accountable=data.get("accountable"),
            responsible=data.get("responsible"),
            consulted=data.get("consulted"),
            informed=data.get("informed"),
            owner_weights=weights,
            created_by=data.get("created_by", "user"),
        )
        return assignment.to_dict()

    def get_metrics_for_owner(self, owner_role: str) -> Dict[str, Any]:
        metrics = self.ownership.get_metrics_for_owner(owner_role)
        return {"owner_role": owner_role, "metrics": metrics, "count": len(metrics)}

    def get_cross_silo_deps(self, metric_id: str) -> Dict[str, Any]:
        deps = self.ownership.get_cross_silo_dependencies(metric_id)
        return {"metric_id": metric_id, "dependencies": deps, "count": len(deps)}

    # ═══════════════════════════════════════════════════════════════
    # Parameters API
    # ═══════════════════════════════════════════════════════════════

    def get_parameters(self, category: Optional[str] = None) -> Dict[str, Any]:
        defs = self.params.list_definitions(category)
        return {"parameters": [d.to_dict() for d in defs], "count": len(defs)}

    def get_slider_params(self) -> Dict[str, Any]:
        sliders = self.params.list_slider_params()
        return {"sliders": [d.to_dict() for d in sliders], "count": len(sliders)}

    def set_parameter_override(self, param_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        override = self.params.set_override(
            param_id=param_id,
            level=data.get("level", "global"),
            entity=data.get("entity", ""),
            value=data.get("value", 0),
            reason=data.get("reason", ""),
            created_by=data.get("created_by", "user"),
        )
        if override:
            return override.to_dict()
        return {"error": f"Parameter {param_id} not found"}

    def resolve_parameters(
        self, store: str = "", banner: str = "", region: str = ""
    ) -> Dict[str, Any]:
        return self.params.resolve_all(store=store, banner=banner, region=region)

    # ═══════════════════════════════════════════════════════════════
    # Cost Stack & ROI API
    # ═══════════════════════════════════════════════════════════════

    def build_cost_stack(
        self,
        metric_inputs: Dict[str, Dict[str, Any]],
        scenario_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        stack = self.aggregation.build_cost_stack(metric_inputs, scenario_id)
        return stack.to_dict()

    def compute_roi(
        self,
        metric_inputs: Dict[str, Dict[str, Any]],
        scenario_id: str = "",
        scenario_name: str = "",
        baseline_inputs: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        stack = self.aggregation.build_cost_stack(metric_inputs, scenario_id)
        baseline_stack = None
        if baseline_inputs:
            baseline_stack = self.aggregation.build_cost_stack(baseline_inputs)

        roi = self.roi_engine.compute(
            cost_stack=stack,
            scenario_id=scenario_id,
            scenario_name=scenario_name,
            baseline_stack=baseline_stack,
        )
        return roi.to_dict()

    def run_scenario(self, scenario_id: str, base_metric_inputs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Run a complete scenario: resolve params → translate → aggregate → ROI."""
        scenario = self.scenarios.get(scenario_id)
        if not scenario:
            return {"error": f"Scenario {scenario_id} not found"}

        resolved_inputs = self.scenarios.resolve_metric_inputs(scenario_id, base_metric_inputs)
        stack = self.aggregation.build_cost_stack(resolved_inputs, scenario_id)
        roi = self.roi_engine.compute(
            cost_stack=stack,
            scenario_id=scenario_id,
            scenario_name=scenario.name,
        )
        return {
            "scenario": scenario.to_dict(),
            "cost_stack": stack.to_dict(),
            "roi": roi.to_dict(),
        }

    def compare_scenarios(
        self,
        scenario_ids: List[str],
        base_metric_inputs: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Compare multiple scenarios side by side."""
        from loweconex_platform.ownership.consolidated_roi import ConsolidatedROI
        results = {}
        for sid in scenario_ids:
            run = self.run_scenario(sid, base_metric_inputs)
            if "error" not in run:
                name = run["scenario"]["name"]
                # Reconstruct ConsolidatedROI for comparison
                roi_data = run["roi"]
                roi_obj = ConsolidatedROI(
                    scenario_id=sid,
                    scenario_name=name,
                    total_savings=roi_data.get("total_savings", 0),
                    total_cost=roi_data.get("total_cost", 0),
                    net_benefit=roi_data.get("net_benefit", 0),
                    roi_pct=roi_data.get("roi_pct", 0),
                    npv=roi_data.get("npv", 0),
                    payback_months=roi_data.get("payback_months"),
                )
                results[name] = roi_obj
        return self.roi_engine.compare_scenarios(results)

    # ═══════════════════════════════════════════════════════════════
    # Optimization API
    # ═══════════════════════════════════════════════════════════════

    def optimize(
        self,
        metric_inputs: Dict[str, Dict[str, Any]],
        constraints_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        stack = self.aggregation.build_cost_stack(metric_inputs)
        constraints = BudgetConstraints(
            total_budget=constraints_data.get("total_budget", float("inf")),
            capex_budget=constraints_data.get("capex_budget", float("inf")),
            opex_budget=constraints_data.get("opex_budget", float("inf")),
            owner_budgets=constraints_data.get("owner_budgets", {}),
            min_confidence=constraints_data.get("min_confidence", 0),
        )
        result = self.optimizer.optimize(stack, constraints)
        return result.to_dict()

    def simulate_budget_cut(
        self,
        metric_inputs: Dict[str, Dict[str, Any]],
        cut_pct: float = 0.50,
        cut_type: str = "opex",
    ) -> Dict[str, Any]:
        stack = self.aggregation.build_cost_stack(metric_inputs)
        constraints = BudgetConstraints()
        return self.optimizer.simulate_budget_cut(stack, constraints, cut_pct, cut_type)

    # ═══════════════════════════════════════════════════════════════
    # Scenario Management API
    # ═══════════════════════════════════════════════════════════════

    def create_scenario(self, data: Dict[str, Any]) -> Dict[str, Any]:
        scenario = self.scenarios.create(
            name=data.get("name", "New Scenario"),
            description=data.get("description", ""),
            region=data.get("region", ""),
            banner=data.get("banner", ""),
            store=data.get("store", ""),
            parameter_overrides=data.get("parameter_overrides", {}),
            owner_budget_overrides=data.get("owner_budget_overrides", {}),
            created_by=data.get("created_by", "user"),
        )
        return scenario.to_dict()

    def list_scenarios(self) -> Dict[str, Any]:
        scenarios = self.scenarios.list_all()
        return {"scenarios": [s.to_dict() for s in scenarios], "count": len(scenarios)}

    def update_scenario_status(self, scenario_id: str, status: str, by: str = "user") -> Dict[str, Any]:
        success = self.scenarios.update_status(scenario_id, status, by)
        return {"success": success, "scenario_id": scenario_id, "new_status": status}

    # ═══════════════════════════════════════════════════════════════
    # Translation Rules API
    # ═══════════════════════════════════════════════════════════════

    def get_translation_rules(self, quadrant: Optional[str] = None) -> Dict[str, Any]:
        if quadrant:
            rules = self.rules.list_by_quadrant(quadrant)
        else:
            rules = self.rules.list_all()
        return {"rules": [r.to_dict() for r in rules], "count": len(rules)}

    # ═══════════════════════════════════════════════════════════════
    # Audit & Export API
    # ═══════════════════════════════════════════════════════════════

    def get_audit_log(self, entity_type: Optional[str] = None, entity_id: Optional[str] = None) -> Dict[str, Any]:
        logs = []
        if entity_type == "ownership":
            logs = self.ownership.get_audit_log(entity_id)
        elif entity_type == "parameter":
            logs = self.params.get_audit_log(entity_id)
        else:
            logs = self.ownership.get_audit_log() + self.params.get_audit_log()
        return {"audit_log": logs, "count": len(logs)}

    def get_dependency_graph(self) -> Dict[str, Any]:
        return {"edges": self.aggregation.get_dependency_graph()}

    def export_pack(
        self,
        metric_inputs: Dict[str, Dict[str, Any]],
        scenario_id: str = "",
    ) -> Dict[str, Any]:
        """Generate a complete export pack for budget discussions."""
        stack = self.aggregation.build_cost_stack(metric_inputs, scenario_id)
        roi = self.roi_engine.compute(stack, scenario_id=scenario_id)
        return {
            "roi_summary": roi.to_dict(),
            "cost_stack_detail": stack.to_dict(),
            "ownership_map": self.get_ownership_map(),
            "parameter_values": self.params.resolve_all(),
            "translation_rules": self.get_translation_rules(),
            "dependency_graph": self.get_dependency_graph(),
            "audit_log": self.get_audit_log(),
        }


# ═══════════════════════════════════════════════════════════════════
# Singleton service instance
# ═══════════════════════════════════════════════════════════════════

_service: Optional[OwnershipDecisionService] = None


def get_service() -> OwnershipDecisionService:
    """Get or create the singleton OwnershipDecisionService."""
    global _service
    if _service is None:
        _service = OwnershipDecisionService()
    return _service

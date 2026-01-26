"""
Demand Forecast & Procurement - Orchestrator

Coordinates the complete demand forecasting and procurement workflow.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import hashlib
import numpy as np

from ...crewai_base import AgentRegistry, AgentMessageBus

from .schemas import (
    DemandProcurementConfig,
    SKUConfig,
    SupplierConfig,
    SupplierTier,
    ServiceLevel,
    DPDecisionPack,
)

from .agents import (
    DemandForecastAgent,
    InventoryOptimizationAgent,
    SupplierManagementAgent,
    RiskAnalysisAgent,
    ScenarioSimulationAgent,
    ProcurementPlanningAgent,
    DPGovernanceAgent,
    DPReportingAgent,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DemandProcurementOrchestrator:
    """
    Orchestrates the Demand & Procurement workflow.
    
    Pipeline: Forecast → Optimize → Risk → Simulate → Plan → Govern → Report
    """
    
    def __init__(self, config: DemandProcurementConfig):
        self.config = config
        self.registry = AgentRegistry.get_instance()
        self.message_bus = self.registry.message_bus
        
        self._initialize_agents()
        
        self.run_history: List[DPDecisionPack] = []
        logger.info(f"DemandProcurementOrchestrator initialized for {config.organization_name}")
    
    def _initialize_agents(self):
        """Initialize all Demand & Procurement agents"""
        org_id = self.config.organization_id
        skus = self.config.skus
        suppliers = self.config.suppliers
        
        self.forecast_agent = DemandForecastAgent(org_id, skus, self.message_bus)
        self.inventory_agent = InventoryOptimizationAgent(org_id, skus, self.message_bus)
        self.supplier_agent = SupplierManagementAgent(org_id, suppliers, self.message_bus)
        self.risk_agent = RiskAnalysisAgent(org_id, skus, self.message_bus)
        self.scenario_agent = ScenarioSimulationAgent(org_id, self.message_bus)
        self.procurement_agent = ProcurementPlanningAgent(org_id, skus, suppliers, self.message_bus)
        self.governance_agent = DPGovernanceAgent(org_id, self.config, self.message_bus)
        self.reporting_agent = DPReportingAgent(org_id, self.message_bus)
        
        # Register agents
        for agent in [
            self.forecast_agent, self.inventory_agent, self.supplier_agent,
            self.risk_agent, self.scenario_agent, self.procurement_agent,
            self.governance_agent, self.reporting_agent
        ]:
            self.registry.register(agent)
        
        logger.info(f"Initialized 8 Demand & Procurement agents")
    
    def run(
        self,
        demand_history: Dict[str, np.ndarray],
        current_inventory: Optional[Dict[str, int]] = None,
    ) -> DPDecisionPack:
        """
        Run the complete Demand & Procurement workflow.
        
        Args:
            demand_history: Historical demand by SKU (sku_id -> weekly demand array)
            current_inventory: Current inventory levels by SKU
        
        Returns:
            DPDecisionPack with forecasts, policies, and plans
        """
        run_id = hashlib.md5(
            f"{datetime.utcnow().isoformat()}_{self.config.organization_id}".encode()
        ).hexdigest()[:12]
        
        logger.info(f"Starting Demand & Procurement run {run_id}")
        
        # Update current inventory in SKU configs
        if current_inventory:
            for sku in self.config.skus:
                if sku.sku_id in current_inventory:
                    sku.current_inventory = current_inventory[sku.sku_id]
        
        # 1. Generate forecasts
        logger.info("Step 1: Demand forecasting")
        forecasts = {}
        for sku in self.config.skus:
            history = demand_history.get(sku.sku_id, np.array([100] * 12))
            forecast = self.forecast_agent.forecast(
                sku.sku_id, history, self.config.forecast_horizon_weeks
            )
            forecasts[sku.sku_id] = forecast
        
        # 2. Optimize inventory policies
        logger.info("Step 2: Inventory optimization")
        policies = {}
        for sku_id, forecast in forecasts.items():
            policy = self.inventory_agent.optimize_policy(sku_id, forecast)
            policies[sku_id] = policy
        
        # 3. Risk assessment
        logger.info("Step 3: Risk assessment")
        risk_assessments = {}
        for sku in self.config.skus:
            if sku.sku_id in forecasts and sku.sku_id in policies:
                assessment = self.risk_agent.assess_risk(
                    sku.sku_id,
                    forecasts[sku.sku_id],
                    policies[sku.sku_id],
                    sku.current_inventory
                )
                risk_assessments[sku.sku_id] = assessment
        
        # 4. Scenario simulation
        logger.info("Step 4: Scenario simulation")
        scenario_results = {}
        
        # Baseline scenario
        baseline = self.scenario_agent.simulate(
            "baseline", "Baseline", policies, forecasts, n_simulations=500
        )
        scenario_results["baseline"] = baseline
        
        # Conservative scenario (higher safety stock)
        conservative_policies = {}
        for sku_id, policy in policies.items():
            from copy import deepcopy
            cp = deepcopy(policy)
            cp.safety_stock = int(cp.safety_stock * 1.3)
            cp.reorder_point = int(cp.reorder_point * 1.2)
            conservative_policies[sku_id] = cp
        
        conservative = self.scenario_agent.simulate(
            "conservative", "Conservative", conservative_policies, forecasts, n_simulations=500
        )
        scenario_results["conservative"] = conservative
        
        # Select best scenario
        selected_scenario = "baseline"
        if conservative.expected_service_level > baseline.expected_service_level + 0.02:
            selected_scenario = "conservative"
        
        # 5. Generate procurement plans
        logger.info("Step 5: Procurement planning")
        plans = self.procurement_agent.generate_plans(policies, risk_assessments)
        
        # 6. Governance validation
        logger.info("Step 6: Governance validation")
        governance = self.governance_agent.validate(plans)
        
        # 7. Generate report
        logger.info("Step 7: Report generation")
        summary = self.reporting_agent.generate_summary(
            forecasts, policies, plans, risk_assessments
        )
        
        # Build recommendations
        recommendations = []
        for plan in plans[:5]:
            recommendations.append({
                "type": "procurement",
                "sku_id": plan.sku_id,
                "action": f"Order {plan.order_quantity} units",
                "priority": plan.priority,
            })
        
        high_risk = [r for r in risk_assessments.values() if r.risk_level in ["critical", "high"]]
        for risk in high_risk[:3]:
            recommendations.append({
                "type": "risk_mitigation",
                "sku_id": risk.sku_id,
                "action": f"Address {risk.risk_level} risk",
                "priority": 1 if risk.risk_level == "critical" else 2,
            })
        
        # Build decision pack
        decision_pack = DPDecisionPack(
            pack_id=run_id,
            organization_id=self.config.organization_id,
            created_at=datetime.utcnow(),
            forecasts=forecasts,
            policies=policies,
            procurement_plans=plans,
            risk_assessments=risk_assessments,
            scenario_results=scenario_results,
            selected_scenario=selected_scenario,
            executive_summary=summary,
            recommendations=recommendations,
            status="completed" if governance["approved"] else "pending_review",
            confidence_score=0.85 if governance["approved"] else 0.6,
        )
        
        self.run_history.append(decision_pack)
        logger.info(f"Demand & Procurement run complete: {decision_pack.status}")
        
        return decision_pack
    
    def get_agent_summary(self) -> Dict[str, Any]:
        """Get summary of D&P agents"""
        return {
            "ecosystem": "Demand & Procurement",
            "organization_id": self.config.organization_id,
            "n_skus": len(self.config.skus),
            "n_suppliers": len(self.config.suppliers),
            "agents": [
                "DemandForecast", "InventoryOptimization", "SupplierManagement",
                "RiskAnalysis", "ScenarioSimulation", "ProcurementPlanning",
                "Governance", "Reporting"
            ],
        }


def create_demand_procurement_orchestrator(
    organization_id: str,
    organization_name: str,
    skus: Optional[List[Dict[str, Any]]] = None,
    suppliers: Optional[List[Dict[str, Any]]] = None,
    **kwargs
) -> DemandProcurementOrchestrator:
    """Factory function for Demand & Procurement orchestrator"""
    
    # Default SKUs if not provided
    if skus is None:
        skus = [
            {"sku_id": "SKU-001", "sku_name": "Widget A", "category": "Widgets", "unit_cost": 25.0, "lead_time_days": 7, "current_inventory": 500},
            {"sku_id": "SKU-002", "sku_name": "Widget B", "category": "Widgets", "unit_cost": 45.0, "lead_time_days": 10, "current_inventory": 300},
            {"sku_id": "SKU-003", "sku_name": "Gadget X", "category": "Gadgets", "unit_cost": 120.0, "lead_time_days": 14, "current_inventory": 150, "service_level": ServiceLevel.GOLD},
            {"sku_id": "SKU-004", "sku_name": "Gadget Y", "category": "Gadgets", "unit_cost": 85.0, "lead_time_days": 12, "current_inventory": 200},
            {"sku_id": "SKU-005", "sku_name": "Component Z", "category": "Components", "unit_cost": 15.0, "lead_time_days": 5, "current_inventory": 1000},
        ]
    
    # Default suppliers if not provided
    if suppliers is None:
        suppliers = [
            {"supplier_id": "SUP-001", "supplier_name": "Acme Supplies", "tier": SupplierTier.STRATEGIC, "avg_lead_time_days": 7, "sku_ids": ["SKU-001", "SKU-002"]},
            {"supplier_id": "SUP-002", "supplier_name": "Global Parts", "tier": SupplierTier.PREFERRED, "avg_lead_time_days": 14, "sku_ids": ["SKU-003", "SKU-004"]},
            {"supplier_id": "SUP-003", "supplier_name": "Quick Components", "tier": SupplierTier.APPROVED, "avg_lead_time_days": 5, "sku_ids": ["SKU-005"]},
        ]
    
    # Build SKU configs
    sku_configs = [
        SKUConfig(
            sku_id=s.get("sku_id", f"SKU-{i}"),
            sku_name=s.get("sku_name", f"SKU {i}"),
            category=s.get("category", "General"),
            unit_cost=s.get("unit_cost", 10.0),
            lead_time_days=s.get("lead_time_days", 7),
            current_inventory=s.get("current_inventory", 0),
            service_level=s.get("service_level", ServiceLevel.SILVER),
        )
        for i, s in enumerate(skus)
    ]
    
    # Build supplier configs
    supplier_configs = [
        SupplierConfig(
            supplier_id=s.get("supplier_id", f"SUP-{i}"),
            supplier_name=s.get("supplier_name", f"Supplier {i}"),
            tier=s.get("tier", SupplierTier.APPROVED),
            avg_lead_time_days=s.get("avg_lead_time_days", 14),
            sku_ids=s.get("sku_ids", []),
        )
        for i, s in enumerate(suppliers)
    ]
    
    config = DemandProcurementConfig(
        organization_id=organization_id,
        organization_name=organization_name,
        skus=sku_configs,
        suppliers=supplier_configs,
        **kwargs
    )
    
    return DemandProcurementOrchestrator(config)

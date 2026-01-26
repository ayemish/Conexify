"""
Demand Forecast & Procurement - Agents

CrewAI-compliant agents for demand forecasting and procurement optimization.
"""

import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, date, timedelta
import logging
import hashlib

from ...crewai_base import (
    DemandTwinAgent,
    CrewAIAgentConfig,
    AgentCategory,
    AgentRole,
    AgentMessageBus,
)

from .schemas import (
    DemandProcurementConfig,
    SKUConfig,
    SupplierConfig,
    ServiceLevel,
    DemandForecast,
    InventoryPolicy,
    ProcurementPlan,
    RiskAssessment,
    DPScenarioResult,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Service level to Z-score mapping
SERVICE_LEVEL_Z = {
    ServiceLevel.BRONZE: 1.28,    # 90%
    ServiceLevel.SILVER: 1.645,   # 95%
    ServiceLevel.GOLD: 2.05,      # 98%
    ServiceLevel.PLATINUM: 2.33,  # 99%
}


class DemandForecastAgent(DemandTwinAgent):
    """
    Generates probabilistic demand forecasts.
    """
    
    def __init__(
        self,
        org_id: str,
        skus: List[SKUConfig],
        message_bus: Optional[AgentMessageBus] = None,
    ):
        config = CrewAIAgentConfig(
            agent_id=f"dp-{org_id}-forecast",
            role=AgentRole.FORECASTER,
            category=AgentCategory.ANALYTICS,
            name="Demand Forecaster",
            goal="Generate accurate probabilistic demand forecasts",
            backstory="""You are an expert demand forecaster using state-of-the-art 
            time series methods. You produce probabilistic forecasts with honest 
            uncertainty quantification.""",
            retailer_id=org_id,
        )
        super().__init__(config, message_bus)
        
        self.skus = {s.sku_id: s for s in skus}
        self.forecasts: Dict[str, DemandForecast] = {}
    
    def forecast(
        self,
        sku_id: str,
        history: np.ndarray,
        horizon_weeks: int = 13
    ) -> DemandForecast:
        """Generate probabilistic forecast for a SKU"""
        if len(history) < 4:
            # Insufficient history - use mean
            mean = np.mean(history) if len(history) > 0 else 100
            std = mean * 0.3
        else:
            # Simple exponential smoothing
            alpha = 0.3
            level = history[0]
            for obs in history[1:]:
                level = alpha * obs + (1 - alpha) * level
            mean = level
            std = np.std(history)
        
        # Generate forecast with growing uncertainty
        point_forecast = []
        q10 = []
        q50 = []
        q90 = []
        
        for h in range(1, horizon_weeks + 1):
            h_std = std * np.sqrt(1 + 0.1 * h)  # Uncertainty grows
            point_forecast.append(max(0, mean + np.random.normal(0, h_std * 0.1)))
            q10.append(max(0, mean - 1.28 * h_std))
            q50.append(mean)
            q90.append(mean + 1.28 * h_std)
        
        forecast = DemandForecast(
            sku_id=sku_id,
            forecast_date=date.today(),
            horizon_weeks=horizon_weeks,
            point_forecast=point_forecast,
            q10=q10,
            q50=q50,
            q90=q90,
        )
        forecast.compute_derived()
        
        self.forecasts[sku_id] = forecast
        self.log_action("forecast", {"sku_id": sku_id}, forecast.to_dict())
        
        return forecast
    
    def get_all_forecasts(self) -> Dict[str, DemandForecast]:
        """Get all forecasts"""
        return dict(self.forecasts)


class InventoryOptimizationAgent(DemandTwinAgent):
    """
    Computes optimal inventory policies (ROP, EOQ, safety stock).
    """
    
    def __init__(
        self,
        org_id: str,
        skus: List[SKUConfig],
        message_bus: Optional[AgentMessageBus] = None,
    ):
        config = CrewAIAgentConfig(
            agent_id=f"dp-{org_id}-inventory",
            role=AgentRole.INVENTORY_OPTIMIZER,
            category=AgentCategory.OPTIMIZATION,
            name="Inventory Optimizer",
            goal="Optimize inventory policies to balance service and cost",
            backstory="""You optimize inventory using stochastic programming. 
            You find the right balance between service level targets and 
            inventory holding costs.""",
            retailer_id=org_id,
        )
        super().__init__(config, message_bus)
        
        self.skus = {s.sku_id: s for s in skus}
        self.policies: Dict[str, InventoryPolicy] = {}
    
    def optimize_policy(
        self,
        sku_id: str,
        forecast: DemandForecast
    ) -> InventoryPolicy:
        """Compute optimal inventory policy for a SKU"""
        sku = self.skus.get(sku_id)
        if not sku:
            raise ValueError(f"Unknown SKU: {sku_id}")
        
        mean_demand = forecast.mean_weekly_demand
        std_demand = forecast.std_weekly_demand
        
        # Service level parameters
        z = SERVICE_LEVEL_Z.get(sku.service_level, 1.645)
        target_service = {
            ServiceLevel.BRONZE: 0.90,
            ServiceLevel.SILVER: 0.95,
            ServiceLevel.GOLD: 0.98,
            ServiceLevel.PLATINUM: 0.99,
        }.get(sku.service_level, 0.95)
        
        # Lead time in weeks
        lt_weeks = sku.lead_time_days / 7
        lt_std_weeks = sku.lead_time_std_days / 7
        
        # Safety stock
        demand_during_lt = mean_demand * lt_weeks
        demand_std_during_lt = np.sqrt(
            lt_weeks * std_demand**2 + mean_demand**2 * lt_std_weeks**2
        )
        safety_stock = int(np.ceil(z * demand_std_during_lt))
        
        # Reorder point
        reorder_point = int(np.ceil(demand_during_lt + safety_stock))
        
        # EOQ
        annual_demand = mean_demand * 52
        holding_cost = sku.unit_cost * sku.holding_cost_pct
        if holding_cost > 0 and annual_demand > 0:
            eoq = np.sqrt(2 * annual_demand * sku.ordering_cost / holding_cost)
        else:
            eoq = mean_demand * 4  # 4 weeks supply
        
        # Round to case pack
        order_qty = max(sku.min_order_qty, int(np.ceil(eoq / sku.case_pack) * sku.case_pack))
        
        # Expected costs
        annual_holding = (order_qty / 2 + safety_stock) * holding_cost
        annual_ordering = (annual_demand / order_qty) * sku.ordering_cost
        annual_stockout = annual_demand * (1 - target_service) * sku.unit_cost * 0.5
        total_cost = annual_holding + annual_ordering + annual_stockout
        
        policy = InventoryPolicy(
            sku_id=sku_id,
            reorder_point=reorder_point,
            order_quantity=order_qty,
            safety_stock=safety_stock,
            expected_service_level=target_service,
            expected_stockout_risk=1 - target_service,
            expected_inventory_turns=annual_demand / max((order_qty / 2 + safety_stock), 1),
            expected_weeks_of_supply=(order_qty / 2 + safety_stock) / max(mean_demand, 1),
            expected_annual_holding_cost=annual_holding,
            expected_annual_ordering_cost=annual_ordering,
            expected_annual_stockout_cost=annual_stockout,
            total_annual_cost=total_cost,
        )
        
        self.policies[sku_id] = policy
        self.log_action("optimize_policy", {"sku_id": sku_id}, policy.to_dict())
        
        return policy
    
    def get_all_policies(self) -> Dict[str, InventoryPolicy]:
        """Get all policies"""
        return dict(self.policies)


class SupplierManagementAgent(DemandTwinAgent):
    """
    Manages supplier relationships and selection.
    """
    
    def __init__(
        self,
        org_id: str,
        suppliers: List[SupplierConfig],
        message_bus: Optional[AgentMessageBus] = None,
    ):
        config = CrewAIAgentConfig(
            agent_id=f"dp-{org_id}-supplier",
            role=AgentRole.RESOURCE_ALLOCATOR,
            category=AgentCategory.OPTIMIZATION,
            name="Supplier Manager",
            goal="Optimize supplier selection and relationships",
            backstory="""You manage supplier relationships and select optimal 
            suppliers based on cost, reliability, and strategic alignment.""",
            retailer_id=org_id,
        )
        super().__init__(config, message_bus)
        
        self.suppliers = {s.supplier_id: s for s in suppliers}
        self.sku_supplier_map: Dict[str, str] = {}
        
        # Build SKU to supplier mapping
        for supplier in suppliers:
            for sku_id in supplier.sku_ids:
                self.sku_supplier_map[sku_id] = supplier.supplier_id
    
    def get_supplier_for_sku(self, sku_id: str) -> Optional[SupplierConfig]:
        """Get the supplier for a SKU"""
        supplier_id = self.sku_supplier_map.get(sku_id)
        if supplier_id:
            return self.suppliers.get(supplier_id)
        return None
    
    def score_supplier(self, supplier_id: str) -> float:
        """Score a supplier based on performance"""
        supplier = self.suppliers.get(supplier_id)
        if not supplier:
            return 0.0
        
        # Weighted score
        score = (
            supplier.on_time_delivery_rate * 0.4 +
            supplier.quality_score * 0.3 +
            (1 - supplier.lead_time_variability) * 0.2 +
            (1 if supplier.tier.value in ["strategic", "preferred"] else 0.5) * 0.1
        )
        return score


class RiskAnalysisAgent(DemandTwinAgent):
    """
    Analyzes stockout and overstock risks.
    """
    
    def __init__(
        self,
        org_id: str,
        skus: List[SKUConfig],
        message_bus: Optional[AgentMessageBus] = None,
    ):
        config = CrewAIAgentConfig(
            agent_id=f"dp-{org_id}-risk",
            role=AgentRole.ANOMALY_DETECTOR,
            category=AgentCategory.ANALYTICS,
            name="Risk Analyst",
            goal="Identify and quantify inventory risks",
            backstory="""You analyze inventory risk using probabilistic methods. 
            You identify stockout and overstock risks with uncertainty quantification.""",
            retailer_id=org_id,
        )
        super().__init__(config, message_bus)
        
        self.skus = {s.sku_id: s for s in skus}
        self.assessments: Dict[str, RiskAssessment] = {}
    
    def assess_risk(
        self,
        sku_id: str,
        forecast: DemandForecast,
        policy: InventoryPolicy,
        current_inventory: int
    ) -> RiskAssessment:
        """Assess risk for a SKU"""
        sku = self.skus.get(sku_id)
        if not sku:
            raise ValueError(f"Unknown SKU: {sku_id}")
        
        mean_weekly = forecast.mean_weekly_demand
        std_weekly = forecast.std_weekly_demand
        
        # Days until stockout
        if mean_weekly > 0:
            days_of_supply = current_inventory / (mean_weekly / 7)
            days_until_stockout = int(days_of_supply) if days_of_supply < 30 else None
        else:
            days_until_stockout = None
        
        # Stockout probability (simplified)
        if current_inventory < policy.reorder_point:
            stockout_prob = min(0.9, (policy.reorder_point - current_inventory) / max(policy.reorder_point, 1))
        else:
            stockout_prob = max(0.01, 1 - policy.expected_service_level)
        
        expected_stockout_units = stockout_prob * mean_weekly * (sku.lead_time_days / 7)
        stockout_cost = expected_stockout_units * sku.unit_cost
        
        # Overstock probability
        weeks_of_supply = current_inventory / max(mean_weekly, 1)
        if weeks_of_supply > 8:
            overstock_prob = min(0.8, (weeks_of_supply - 8) / 8)
        else:
            overstock_prob = 0.1
        
        excess = max(0, current_inventory - mean_weekly * 6)
        holding_cost = excess * sku.unit_cost * sku.holding_cost_pct / 52
        
        # Lead time risk (from supplier)
        lead_time_risk = 0.1  # Simplified
        
        # Overall risk score
        overall_risk = stockout_prob * 0.5 + overstock_prob * 0.2 + lead_time_risk * 0.3
        
        # Risk level
        if overall_risk > 0.7:
            risk_level = "critical"
        elif overall_risk > 0.4:
            risk_level = "high"
        elif overall_risk > 0.2:
            risk_level = "medium"
        else:
            risk_level = "low"
        
        assessment = RiskAssessment(
            sku_id=sku_id,
            stockout_probability=stockout_prob,
            days_until_stockout=days_until_stockout,
            expected_stockout_units=expected_stockout_units,
            expected_stockout_cost=stockout_cost,
            overstock_probability=overstock_prob,
            expected_excess_inventory=excess,
            expected_holding_cost=holding_cost,
            lead_time_risk=lead_time_risk,
            overall_risk_score=overall_risk,
            risk_level=risk_level,
        )
        
        self.assessments[sku_id] = assessment
        self.log_action("assess_risk", {"sku_id": sku_id}, assessment.to_dict())
        
        return assessment


class ScenarioSimulationAgent(DemandTwinAgent):
    """
    Runs what-if scenarios for inventory planning.
    """
    
    def __init__(
        self,
        org_id: str,
        message_bus: Optional[AgentMessageBus] = None,
    ):
        config = CrewAIAgentConfig(
            agent_id=f"dp-{org_id}-scenario",
            role=AgentRole.DIGITAL_TWIN,
            category=AgentCategory.SIMULATION,
            name="Scenario Simulator",
            goal="Simulate inventory scenarios with Monte Carlo methods",
            backstory="""You run Monte Carlo simulations to evaluate inventory 
            scenarios. You model demand variability, lead time uncertainty, 
            and policy performance.""",
            retailer_id=org_id,
        )
        super().__init__(config, message_bus)
        
        self.results: Dict[str, DPScenarioResult] = {}
    
    def simulate(
        self,
        scenario_id: str,
        scenario_name: str,
        policies: Dict[str, InventoryPolicy],
        forecasts: Dict[str, DemandForecast],
        n_simulations: int = 1000
    ) -> DPScenarioResult:
        """Simulate a scenario"""
        service_levels = []
        total_costs = []
        stockouts = []
        
        for _ in range(n_simulations):
            sim_service = []
            sim_cost = 0
            sim_stockouts = 0
            
            for sku_id, policy in policies.items():
                forecast = forecasts.get(sku_id)
                if not forecast:
                    continue
                
                # Simulate service level with variability
                base_sl = policy.expected_service_level
                sim_sl = np.clip(base_sl + np.random.normal(0, 0.02), 0.7, 1.0)
                sim_service.append(sim_sl)
                
                # Simulate cost
                base_cost = policy.total_annual_cost
                sim_cost += base_cost * np.random.normal(1, 0.1)
                
                # Simulate stockouts
                if np.random.random() > sim_sl:
                    sim_stockouts += 1
            
            if sim_service:
                service_levels.append(np.mean(sim_service))
            total_costs.append(sim_cost)
            stockouts.append(sim_stockouts)
        
        result = DPScenarioResult(
            scenario_id=scenario_id,
            scenario_name=scenario_name,
            expected_service_level=float(np.mean(service_levels)) if service_levels else 0.95,
            expected_total_cost=float(np.mean(total_costs)),
            expected_stockouts=int(np.mean(stockouts)),
            expected_inventory_value=float(np.mean(total_costs)) * 0.3,
            service_level_ci=(float(np.percentile(service_levels, 5)) if service_levels else 0.9,
                             float(np.percentile(service_levels, 95)) if service_levels else 0.99),
            cost_ci=(float(np.percentile(total_costs, 5)),
                    float(np.percentile(total_costs, 95))),
            n_simulations=n_simulations,
        )
        
        self.results[scenario_id] = result
        return result


class ProcurementPlanningAgent(DemandTwinAgent):
    """
    Generates procurement plans.
    """
    
    def __init__(
        self,
        org_id: str,
        skus: List[SKUConfig],
        suppliers: List[SupplierConfig],
        message_bus: Optional[AgentMessageBus] = None,
    ):
        config = CrewAIAgentConfig(
            agent_id=f"dp-{org_id}-procurement",
            role=AgentRole.RESOURCE_ALLOCATOR,
            category=AgentCategory.OPTIMIZATION,
            name="Procurement Planner",
            goal="Generate optimal procurement plans",
            backstory="""You create procurement plans that balance inventory needs 
            with supplier constraints and working capital limits.""",
            retailer_id=org_id,
        )
        super().__init__(config, message_bus)
        
        self.skus = {s.sku_id: s for s in skus}
        self.suppliers = {s.supplier_id: s for s in suppliers}
        self.sku_supplier_map: Dict[str, str] = {}
        
        for supplier in suppliers:
            for sku_id in supplier.sku_ids:
                self.sku_supplier_map[sku_id] = supplier.supplier_id
    
    def generate_plans(
        self,
        policies: Dict[str, InventoryPolicy],
        risk_assessments: Dict[str, RiskAssessment]
    ) -> List[ProcurementPlan]:
        """Generate procurement plans based on policies and risks"""
        plans = []
        today = date.today()
        
        for sku_id, policy in policies.items():
            sku = self.skus.get(sku_id)
            risk = risk_assessments.get(sku_id)
            
            if not sku:
                continue
            
            # Determine if order needed
            needs_order = False
            trigger_reason = ""
            priority = 3
            
            if sku.current_inventory <= policy.reorder_point:
                needs_order = True
                trigger_reason = "below_rop"
                priority = 2
            
            if risk and risk.risk_level in ["critical", "high"]:
                needs_order = True
                trigger_reason = "high_risk"
                priority = 1
            
            if not needs_order:
                continue
            
            # Get supplier
            supplier_id = self.sku_supplier_map.get(sku_id)
            if not supplier_id:
                continue
            
            supplier = self.suppliers.get(supplier_id)
            lead_time = supplier.avg_lead_time_days if supplier else sku.lead_time_days
            
            plan = ProcurementPlan(
                plan_id=hashlib.md5(f"{sku_id}_{today}".encode()).hexdigest()[:12],
                sku_id=sku_id,
                supplier_id=supplier_id,
                order_quantity=policy.order_quantity,
                order_date=today,
                expected_delivery_date=today + timedelta(days=lead_time),
                unit_cost=sku.unit_cost,
                total_cost=policy.order_quantity * sku.unit_cost,
                priority=priority,
                trigger_reason=trigger_reason,
            )
            
            plans.append(plan)
        
        # Sort by priority
        plans.sort(key=lambda p: p.priority)
        
        return plans


class DPGovernanceAgent(DemandTwinAgent):
    """
    Validates procurement recommendations against policies.
    """
    
    def __init__(
        self,
        org_id: str,
        config: DemandProcurementConfig,
        message_bus: Optional[AgentMessageBus] = None,
    ):
        agent_config = CrewAIAgentConfig(
            agent_id=f"dp-{org_id}-governance",
            role=AgentRole.POLICY_VALIDATOR,
            category=AgentCategory.GOVERNANCE,
            name="Procurement Governance",
            goal="Ensure procurement plans comply with policies",
            backstory="""You validate procurement plans against budget limits, 
            supplier agreements, and organizational policies.""",
            retailer_id=org_id,
        )
        super().__init__(agent_config, message_bus)
        
        self.dp_config = config
    
    def validate(
        self,
        plans: List[ProcurementPlan]
    ) -> Dict[str, Any]:
        """Validate procurement plans"""
        violations = []
        
        # Check working capital limit
        total_cost = sum(p.total_cost for p in plans)
        if self.dp_config.working_capital_limit and total_cost > self.dp_config.working_capital_limit:
            violations.append(f"Total order value ${total_cost:,.0f} exceeds working capital limit")
        
        # Check supplier constraints
        # (Simplified - would check min/max order values per supplier)
        
        return {
            "approved": len(violations) == 0,
            "violations": violations,
            "total_order_value": total_cost,
            "n_orders": len(plans),
        }


class DPReportingAgent(DemandTwinAgent):
    """
    Generates decision pack reports.
    """
    
    def __init__(
        self,
        org_id: str,
        message_bus: Optional[AgentMessageBus] = None,
    ):
        config = CrewAIAgentConfig(
            agent_id=f"dp-{org_id}-reporting",
            role=AgentRole.REPORT_WRITER,
            category=AgentCategory.COMMUNICATION,
            name="Decision Pack Reporter",
            goal="Generate comprehensive procurement decision packs",
            backstory="""You compile forecasts, policies, and plans into 
            clear, actionable decision packs for procurement teams.""",
            retailer_id=org_id,
        )
        super().__init__(config, message_bus)
    
    def generate_summary(
        self,
        forecasts: Dict[str, DemandForecast],
        policies: Dict[str, InventoryPolicy],
        plans: List[ProcurementPlan],
        risk_assessments: Dict[str, RiskAssessment]
    ) -> str:
        """Generate executive summary"""
        total_demand = sum(f.total_forecast for f in forecasts.values())
        total_cost = sum(p.total_annual_cost for p in policies.values())
        total_orders = sum(p.total_cost for p in plans)
        high_risk = len([r for r in risk_assessments.values() if r.risk_level in ["critical", "high"]])
        
        summary = f"""## Demand & Procurement Decision Pack

**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}

### Forecast Summary
- **SKUs Analyzed:** {len(forecasts)}
- **Total Forecasted Demand:** {total_demand:,.0f} units (13-week horizon)
- **Average Weekly Demand:** {total_demand / 13:,.0f} units

### Inventory Policies
- **Total Annual Inventory Cost:** ${total_cost:,.0f}
- **Average Service Level Target:** {np.mean([p.expected_service_level for p in policies.values()]):.1%}

### Procurement Plans
- **Orders Generated:** {len(plans)}
- **Total Order Value:** ${total_orders:,.0f}
- **Priority 1 Orders:** {len([p for p in plans if p.priority == 1])}

### Risk Assessment
- **High/Critical Risk SKUs:** {high_risk}
- **SKUs Below ROP:** {len([p for p in plans if p.trigger_reason == 'below_rop'])}

### Recommendations
"""
        
        for plan in sorted(plans, key=lambda x: x.priority)[:5]:
            summary += f"- **{plan.sku_id}**: Order {plan.order_quantity} units (Priority {plan.priority})\n"
        
        return summary

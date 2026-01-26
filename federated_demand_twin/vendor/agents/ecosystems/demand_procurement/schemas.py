"""
Demand Forecast & Procurement - Data Contracts

Defines data structures for demand forecasting and procurement.
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
import json


class ServiceLevel(str, Enum):
    """Service level targets"""
    BRONZE = "bronze"  # 90%
    SILVER = "silver"  # 95%
    GOLD = "gold"      # 98%
    PLATINUM = "platinum"  # 99%


class SupplierTier(str, Enum):
    """Supplier classification"""
    STRATEGIC = "strategic"
    PREFERRED = "preferred"
    APPROVED = "approved"
    CONDITIONAL = "conditional"


class OrderFrequency(str, Enum):
    """Order frequency options"""
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"


@dataclass
class SKUConfig:
    """Configuration for a SKU"""
    sku_id: str
    sku_name: str
    category: str
    
    # Inventory parameters
    unit_cost: float = 0.0
    holding_cost_pct: float = 0.25  # Annual holding cost as % of unit cost
    ordering_cost: float = 50.0
    
    # Constraints
    min_order_qty: int = 1
    case_pack: int = 1
    
    # Lead time
    lead_time_days: int = 7
    lead_time_std_days: float = 2.0
    
    # Service level
    service_level: ServiceLevel = ServiceLevel.SILVER
    
    # Current state
    current_inventory: int = 0
    on_order: int = 0


@dataclass
class SupplierConfig:
    """Configuration for a supplier"""
    supplier_id: str
    supplier_name: str
    tier: SupplierTier
    
    # Lead times
    avg_lead_time_days: int = 14
    lead_time_variability: float = 0.2
    
    # Constraints
    min_order_value: float = 0.0
    max_order_value: float = float('inf')
    order_frequency: OrderFrequency = OrderFrequency.WEEKLY
    
    # Performance
    on_time_delivery_rate: float = 0.95
    quality_score: float = 0.98
    
    # SKUs supplied
    sku_ids: List[str] = field(default_factory=list)


@dataclass
class DemandProcurementConfig:
    """Configuration for Demand & Procurement optimization"""
    organization_id: str
    organization_name: str
    
    # SKUs and Suppliers
    skus: List[SKUConfig] = field(default_factory=list)
    suppliers: List[SupplierConfig] = field(default_factory=list)
    
    # Forecasting
    forecast_horizon_weeks: int = 13
    confidence_level: float = 0.90
    
    # Optimization
    optimize_frequency: OrderFrequency = OrderFrequency.WEEKLY
    working_capital_limit: Optional[float] = None
    
    # Risk thresholds
    max_stockout_risk: float = 0.05
    max_overstock_weeks: int = 8


@dataclass
class DemandForecast:
    """Probabilistic demand forecast for a SKU"""
    sku_id: str
    forecast_date: date
    horizon_weeks: int
    
    # Point forecasts
    point_forecast: List[float]  # Weekly demand
    
    # Uncertainty
    q10: List[float]  # 10th percentile
    q50: List[float]  # Median
    q90: List[float]  # 90th percentile
    
    # Derived
    mean_weekly_demand: float = 0.0
    std_weekly_demand: float = 0.0
    total_forecast: float = 0.0
    
    # Model info
    model_version: str = "v1"
    generated_at: datetime = field(default_factory=datetime.utcnow)
    
    def compute_derived(self):
        """Compute derived metrics"""
        import numpy as np
        self.mean_weekly_demand = float(np.mean(self.point_forecast))
        self.std_weekly_demand = float(np.std(self.point_forecast))
        self.total_forecast = float(np.sum(self.point_forecast))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "sku_id": self.sku_id,
            "forecast_date": self.forecast_date.isoformat(),
            "horizon_weeks": self.horizon_weeks,
            "mean_weekly_demand": self.mean_weekly_demand,
            "total_forecast": self.total_forecast,
        }


@dataclass
class InventoryPolicy:
    """Optimal inventory policy for a SKU"""
    sku_id: str
    
    # Policy parameters
    reorder_point: int
    order_quantity: int
    safety_stock: int
    
    # Expected outcomes
    expected_service_level: float
    expected_stockout_risk: float
    expected_inventory_turns: float
    expected_weeks_of_supply: float
    
    # Costs
    expected_annual_holding_cost: float
    expected_annual_ordering_cost: float
    expected_annual_stockout_cost: float
    total_annual_cost: float
    
    # Optimization info
    solver_status: str = "optimal"
    optimized_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "sku_id": self.sku_id,
            "reorder_point": self.reorder_point,
            "order_quantity": self.order_quantity,
            "safety_stock": self.safety_stock,
            "expected_service_level": self.expected_service_level,
            "total_annual_cost": self.total_annual_cost,
        }


@dataclass
class ProcurementPlan:
    """Procurement plan for upcoming orders"""
    plan_id: str
    sku_id: str
    supplier_id: str
    
    # Order details
    order_quantity: int
    order_date: date
    expected_delivery_date: date
    
    # Costs
    unit_cost: float
    total_cost: float
    
    # Status
    status: str = "planned"  # planned, submitted, confirmed, received
    priority: int = 3  # 1-5
    
    # Rationale
    trigger_reason: str = ""  # below_rop, scheduled, expedite
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "sku_id": self.sku_id,
            "supplier_id": self.supplier_id,
            "order_quantity": self.order_quantity,
            "order_date": self.order_date.isoformat(),
            "total_cost": self.total_cost,
            "status": self.status,
        }


@dataclass
class RiskAssessment:
    """Risk assessment for a SKU"""
    sku_id: str
    
    # Stockout risk
    stockout_probability: float
    days_until_stockout: Optional[int]
    expected_stockout_units: float
    expected_stockout_cost: float
    
    # Overstock risk
    overstock_probability: float
    expected_excess_inventory: float
    expected_holding_cost: float
    
    # Lead time risk
    lead_time_risk: float  # Probability of late delivery
    
    # Overall
    overall_risk_score: float  # 0-1
    risk_level: str = "low"  # low, medium, high, critical
    
    assessed_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "sku_id": self.sku_id,
            "stockout_probability": self.stockout_probability,
            "days_until_stockout": self.days_until_stockout,
            "overall_risk_score": self.overall_risk_score,
            "risk_level": self.risk_level,
        }


@dataclass
class DPScenarioResult:
    """Result from a demand/procurement scenario simulation"""
    scenario_id: str
    scenario_name: str
    
    # KPIs
    expected_service_level: float
    expected_total_cost: float
    expected_stockouts: int
    expected_inventory_value: float
    
    # Distributions
    service_level_ci: Tuple[float, float]
    cost_ci: Tuple[float, float]
    
    # Simulation metadata
    n_simulations: int
    simulated_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "expected_service_level": self.expected_service_level,
            "expected_total_cost": self.expected_total_cost,
        }


@dataclass
class DPDecisionPack:
    """Complete Demand & Procurement decision package"""
    pack_id: str
    organization_id: str
    created_at: datetime
    
    # Results
    forecasts: Dict[str, DemandForecast]
    policies: Dict[str, InventoryPolicy]
    procurement_plans: List[ProcurementPlan]
    risk_assessments: Dict[str, RiskAssessment]
    
    # Scenarios
    scenario_results: Dict[str, DPScenarioResult]
    selected_scenario: str
    
    # Summary
    executive_summary: str
    recommendations: List[Dict[str, Any]]
    
    # Status
    status: str = "completed"
    confidence_score: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "organization_id": self.organization_id,
            "created_at": self.created_at.isoformat(),
            "n_skus": len(self.forecasts),
            "n_orders": len(self.procurement_plans),
            "status": self.status,
            "confidence_score": self.confidence_score,
        }
    
    def save(self, path: str):
        """Save decision pack to JSON"""
        from pathlib import Path as PathLib
        PathLib(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)

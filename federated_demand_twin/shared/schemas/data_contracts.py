"""
Data Contracts for Federated Demand Forecasting + Bayesian Decision Twin MVP

Implements Section 6 of the consolidated requirements:
- Customer-side canonical tables (private)
- Exportable summaries (customer → vendor)
- FL messages (customer ↔ vendor)
"""

from datetime import date, datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, validator
import numpy as np


# =============================================================================
# Enums
# =============================================================================

class HierarchyLevel(str, Enum):
    SKU = "sku"
    SUBCATEGORY = "subcategory"
    CATEGORY = "category"
    REGION = "region"


class PrivacyMode(str, Enum):
    NONE = "none"
    SECURE_AGGREGATION = "secure_aggregation"
    DIFFERENTIAL_PRIVACY = "differential_privacy"
    BOTH = "both"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# =============================================================================
# Section 6.1: Customer-side canonical tables (private - never exported)
# =============================================================================

class SalesHistory(BaseModel):
    """
    FR-1.1: Raw sales data - NEVER leaves customer environment
    Table: sales_history(sku_id, store_id, week_start, units, revenue, price, promo_flag)
    """
    sku_id: str = Field(..., description="Stock Keeping Unit identifier")
    store_id: str = Field(..., description="Store/location identifier")
    week_start: date = Field(..., description="Start date of the sales week (Monday)")
    units: float = Field(..., ge=0, description="Units sold")
    revenue: float = Field(..., ge=0, description="Revenue generated")
    price: float = Field(..., ge=0, description="Selling price per unit")
    promo_flag: bool = Field(default=False, description="Whether item was on promotion")
    
    class Config:
        schema_extra = {
            "example": {
                "sku_id": "SKU-001",
                "store_id": "STORE-A",
                "week_start": "2024-01-01",
                "units": 150.0,
                "revenue": 2250.0,
                "price": 15.0,
                "promo_flag": True
            }
        }


class InventoryState(BaseModel):
    """
    FR-1.1: Inventory position - private customer data
    Table: inventory_state(sku_id, store_id, week_start, on_hand, on_order, backorders)
    """
    sku_id: str
    store_id: str
    week_start: date
    on_hand: float = Field(..., ge=0, description="Units currently on hand")
    on_order: float = Field(..., ge=0, description="Units on order from suppliers")
    backorders: float = Field(..., ge=0, description="Units backordered to customers")
    
    @property
    def available_to_promise(self) -> float:
        """Calculate available inventory"""
        return max(0, self.on_hand + self.on_order - self.backorders)


class SupplyParams(BaseModel):
    """
    FR-1.1: Supply chain parameters
    Table: supply_params(sku_id, supplier_id, lead_time_weeks, MOQ, case_pack, capacity_flags)
    """
    sku_id: str
    supplier_id: str
    lead_time_weeks: int = Field(..., ge=0, description="Supplier lead time in weeks")
    moq: int = Field(..., ge=1, description="Minimum Order Quantity")
    case_pack: int = Field(..., ge=1, description="Case pack size")
    capacity_flags: Dict[str, bool] = Field(
        default_factory=dict,
        description="Capacity constraint flags (e.g., seasonal_limit, warehouse_constrained)"
    )
    
    def round_to_case_pack(self, quantity: float) -> int:
        """Round order quantity up to nearest case pack"""
        return int(np.ceil(quantity / self.case_pack) * self.case_pack)
    
    def apply_moq(self, quantity: float) -> int:
        """Apply MOQ constraint"""
        rounded = self.round_to_case_pack(quantity)
        return max(rounded, self.moq) if rounded > 0 else 0


class HierarchyMap(BaseModel):
    """
    FR-4.1: Hierarchy mapping for reconciliation
    Table: hierarchy_map(sku_id, subcategory_id, category_id, region_id)
    """
    sku_id: str
    subcategory_id: str
    category_id: str
    region_id: str
    
    def get_parent(self, level: HierarchyLevel) -> str:
        """Get parent identifier at specified level"""
        level_map = {
            HierarchyLevel.SKU: self.sku_id,
            HierarchyLevel.SUBCATEGORY: self.subcategory_id,
            HierarchyLevel.CATEGORY: self.category_id,
            HierarchyLevel.REGION: self.region_id,
        }
        return level_map[level]


# =============================================================================
# Section 6.2: Exportable summaries (customer → vendor)
# =============================================================================

class DemandForecastSummary(BaseModel):
    """
    FR-5.2: Approved forecast summary for export
    Table: demand_forecast_summary(entity_id, week_start, q10, q50, q90, model_version)
    
    This is the ONLY forecast data that leaves the customer environment.
    """
    entity_id: str = Field(..., description="Hierarchy entity identifier (SKU/subcategory/category)")
    entity_level: HierarchyLevel = Field(..., description="Level in hierarchy")
    week_start: date = Field(..., description="Forecast week start date")
    q10: float = Field(..., ge=0, description="10th percentile forecast")
    q50: float = Field(..., ge=0, description="50th percentile (median) forecast")
    q90: float = Field(..., ge=0, description="90th percentile forecast")
    model_version: str = Field(..., description="Model version that produced this forecast")
    run_id: str = Field(..., description="Pipeline run identifier")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    @validator('q50')
    def q50_between_quantiles(cls, v, values):
        if 'q10' in values and v < values['q10']:
            raise ValueError('q50 must be >= q10')
        return v
    
    @validator('q90')
    def q90_above_q50(cls, v, values):
        if 'q50' in values and v < values['q50']:
            raise ValueError('q90 must be >= q50')
        return v
    
    @property
    def forecast_spread(self) -> float:
        """Measure of forecast uncertainty"""
        return self.q90 - self.q10
    
    @property
    def coefficient_of_variation(self) -> float:
        """Normalized uncertainty measure"""
        if self.q50 == 0:
            return float('inf') if self.forecast_spread > 0 else 0
        return self.forecast_spread / self.q50


class RevenueForecastSummary(BaseModel):
    """
    Revenue forecast summary for export (companion to DemandForecastSummary).
    Table: revenue_forecast_summary(entity_id, week_start, q10, q50, q90, model_version)
    
    Enables FL to abstract revenue alongside demand (units).
    """
    entity_id: str = Field(..., description="Hierarchy entity identifier")
    entity_level: HierarchyLevel = Field(..., description="Level in hierarchy")
    week_start: date = Field(..., description="Forecast week start date")
    q10: float = Field(..., ge=0, description="10th percentile revenue forecast")
    q50: float = Field(..., ge=0, description="50th percentile (median) revenue forecast")
    q90: float = Field(..., ge=0, description="90th percentile revenue forecast")
    currency: str = Field(default="USD", description="Currency code")
    model_version: str = Field(..., description="Model version that produced this forecast")
    run_id: str = Field(..., description="Pipeline run identifier")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Optional: link to corresponding demand forecast
    demand_forecast_id: Optional[str] = Field(
        None, description="ID of corresponding demand forecast (for traceability)"
    )
    
    @validator('q50')
    def q50_between_quantiles(cls, v, values):
        if 'q10' in values and v < values['q10']:
            raise ValueError('q50 must be >= q10')
        return v
    
    @validator('q90')
    def q90_above_q50(cls, v, values):
        if 'q50' in values and v < values['q50']:
            raise ValueError('q90 must be >= q50')
        return v
    
    @property
    def forecast_spread(self) -> float:
        """Measure of forecast uncertainty in revenue"""
        return self.q90 - self.q10


class CovariateSummary(BaseModel):
    """
    FR-5.2: Optional covariate summary for export
    Table: covariate_summary(entity_id, week_start, promo_intensity_index, price_index, event_flags)
    """
    entity_id: str
    entity_level: HierarchyLevel
    week_start: date
    promo_intensity_index: float = Field(
        ..., ge=0, le=1, 
        description="Aggregated promotion intensity (0=no promo, 1=deep discount)"
    )
    price_index: float = Field(
        ..., ge=0,
        description="Price index relative to baseline (1.0 = baseline price)"
    )
    event_flags: Dict[str, bool] = Field(
        default_factory=dict,
        description="Event indicators (e.g., holiday, back_to_school, seasonal_peak)"
    )


# =============================================================================
# Section 6.3: FL messages (customer ↔ vendor)
# =============================================================================

class ModelUpdate(BaseModel):
    """
    FR-2.2: Federated learning model update from client
    Message: model_update(round_id, client_id, weights_delta, metrics)
    
    Note: weights_delta is encrypted if Secure Aggregation is enabled
    """
    round_id: int = Field(..., ge=0, description="Federated learning round number")
    client_id: str = Field(..., description="Client identifier")
    weights_delta: bytes = Field(..., description="Serialized model weight updates")
    metrics: Dict[str, float] = Field(
        default_factory=dict,
        description="Training metrics (loss, samples_used, etc.)"
    )
    privacy_mode: PrivacyMode = Field(
        default=PrivacyMode.NONE,
        description="Privacy protection mode used"
    )
    dp_epsilon: Optional[float] = Field(
        None, ge=0,
        description="Differential privacy epsilon if DP enabled"
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        schema_extra = {
            "example": {
                "round_id": 5,
                "client_id": "retailco-client-1",
                "weights_delta": b"<serialized_weights>",
                "metrics": {"loss": 0.0234, "samples_used": 10000},
                "privacy_mode": "secure_aggregation"
            }
        }


class GlobalModel(BaseModel):
    """
    FR-2.3: Versioned global model from FL server
    Message: global_model(model_version, weights, config_hash)
    """
    model_version: str = Field(..., description="Semantic version of the model")
    weights: bytes = Field(..., description="Serialized model weights")
    config_hash: str = Field(..., description="Hash of model configuration for verification")
    round_id: int = Field(..., ge=0, description="Round that produced this model")
    aggregation_method: str = Field(default="fedavg", description="Aggregation algorithm used")
    num_clients: int = Field(..., ge=1, description="Number of clients in aggregation")
    privacy_flags: Dict[str, bool] = Field(
        default_factory=dict,
        description="Privacy features enabled (secure_agg, dp, etc.)"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# Bayesian Decision Engine Contracts
# =============================================================================

class BayesianInput(BaseModel):
    """
    FR-6.1: Input to Bayesian decision engine
    """
    entity_id: str
    forecast_quantiles: Dict[str, float] = Field(
        ..., description="Forecast quantiles {week_start: {q10, q50, q90}}"
    )
    current_inventory: float = Field(..., ge=0)
    on_order: float = Field(..., ge=0)
    lead_time_weeks: int = Field(..., ge=0)
    moq: int = Field(..., ge=1)
    case_pack: int = Field(..., ge=1)
    holding_cost_per_unit: float = Field(..., ge=0)
    stockout_cost_per_unit: float = Field(..., ge=0)
    constraints: Dict[str, Any] = Field(default_factory=dict)


class PosteriorOutcome(BaseModel):
    """
    FR-6.1: Bayesian posterior outcome distribution
    """
    entity_id: str
    scenario_name: str = Field(default="baseline")
    
    # Stockout risk
    stockout_probability: float = Field(..., ge=0, le=1)
    stockout_probability_ci_lower: float = Field(..., ge=0, le=1)
    stockout_probability_ci_upper: float = Field(..., ge=0, le=1)
    
    # Expected margin impact
    expected_margin_impact: float
    margin_impact_ci_lower: float
    margin_impact_ci_upper: float
    
    # Service level
    expected_service_level: float = Field(..., ge=0, le=1)
    service_level_ci_lower: float = Field(..., ge=0, le=1)
    service_level_ci_upper: float = Field(..., ge=0, le=1)
    
    # Inventory metrics
    expected_inventory_turns: float = Field(..., ge=0)
    expected_weeks_of_supply: float = Field(..., ge=0)
    
    model_version: str
    run_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# Optimization Service Contracts
# =============================================================================

class OptimizationRequest(BaseModel):
    """
    FR-7.1: Input to optimization service
    """
    entity_id: str
    posterior_outcomes: List[PosteriorOutcome]
    target_service_level: float = Field(default=0.95, ge=0, le=1)
    max_inventory_investment: Optional[float] = None
    warehouse_capacity: Optional[float] = None
    min_weeks_of_supply: float = Field(default=2.0, ge=0)
    max_weeks_of_supply: float = Field(default=12.0, ge=0)


class OptimizationResult(BaseModel):
    """
    FR-7.1: Output from optimization service with audit trail
    """
    entity_id: str
    recommended_reorder_point: int = Field(..., ge=0)
    recommended_order_quantity: int = Field(..., ge=0)
    
    # Audit fields (FR-7.2)
    objective_value: float
    constraints_satisfied: Dict[str, bool]
    binding_constraints: List[str]
    inputs_hash: str = Field(..., description="Hash of inputs for reproducibility")
    
    # Expected outcomes under recommendation
    expected_stockout_risk: float = Field(..., ge=0, le=1)
    expected_service_level: float = Field(..., ge=0, le=1)
    expected_inventory_cost: float = Field(..., ge=0)
    
    solver_status: str
    solve_time_seconds: float
    model_version: str
    run_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# Digital Twin Contracts
# =============================================================================

class TwinState(BaseModel):
    """
    FR-8.1: Digital twin living state representation
    """
    state_id: str
    week_start: date
    entity_states: Dict[str, Dict[str, Any]] = Field(
        ..., description="State by entity_id: inventory, orders, policies"
    )
    demand_model_version: str
    policy_version: str
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class ScenarioRequest(BaseModel):
    """
    FR-8.2: Scenario simulation request
    """
    scenario_name: str
    base_state_id: str
    modifications: Dict[str, Any] = Field(
        ..., 
        description="Scenario modifications (e.g., lead_time_delta, promo_toggle)"
    )
    simulation_weeks: int = Field(default=13, ge=1, le=52)
    num_simulations: int = Field(default=1000, ge=100, le=10000)


class ScenarioResult(BaseModel):
    """
    FR-8.2: Scenario simulation output
    """
    scenario_name: str
    base_state_id: str
    
    # KPI distributions
    kpi_distributions: Dict[str, Dict[str, float]] = Field(
        ...,
        description="KPI name → {mean, std, q10, q50, q90}"
    )
    
    # Recommended actions under scenario
    recommended_actions: List[OptimizationResult]
    
    simulation_metadata: Dict[str, Any]
    run_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# Decision Pack (CrewAI Output)
# =============================================================================

class DecisionPackItem(BaseModel):
    """
    FR-9.1: Single decision recommendation with rationale
    """
    entity_id: str
    action_type: str = Field(..., description="e.g., 'reorder_point_change', 'order_quantity'")
    current_value: Any
    recommended_value: Any
    rationale: str = Field(..., description="Human-readable explanation")
    confidence: float = Field(..., ge=0, le=1)
    risk_flags: List[str] = Field(default_factory=list)
    linked_artifacts: Dict[str, str] = Field(
        default_factory=dict,
        description="References to supporting artifacts (forecast_id, optimization_id, etc.)"
    )


class MonitoringAlert(BaseModel):
    """
    FR-9.1: Monitoring alert from agent layer
    """
    alert_id: str
    severity: str = Field(..., description="info, warning, critical")
    message: str
    entity_id: Optional[str] = None
    metric_name: str
    current_value: float
    threshold_value: float
    triggered_at: datetime = Field(default_factory=datetime.utcnow)


class DecisionPack(BaseModel):
    """
    FR-9.1: Complete decision pack output from CrewAI agents
    """
    pack_id: str
    run_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Executive summary
    executive_summary: str
    
    # Recommendations
    recommendations: List[DecisionPackItem]
    
    # Scenario comparisons
    scenario_comparisons: Dict[str, ScenarioResult]
    
    # Alerts
    monitoring_alerts: List[MonitoringAlert]
    
    # Artifact references for auditability
    model_version: str
    forecast_run_id: str
    optimization_run_id: str
    
    # Agent metadata
    agent_versions: Dict[str, str]
    orchestration_log: List[Dict[str, Any]]


# =============================================================================
# Pipeline Artifacts
# =============================================================================

class PipelineRun(BaseModel):
    """
    NFR-3.1: Pipeline run tracking for reproducibility
    """
    run_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: RunStatus
    
    # Configuration
    config_hash: str
    privacy_settings: Dict[str, Any]
    
    # Artifacts produced
    artifacts: Dict[str, str] = Field(
        default_factory=dict,
        description="Artifact type → artifact_id mapping"
    )
    
    # Metrics
    metrics: Dict[str, float] = Field(default_factory=dict)
    
    # Error tracking
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None


class DataQualityReport(BaseModel):
    """
    Data quality validation report
    """
    run_id: str
    table_name: str
    total_records: int
    valid_records: int
    null_counts: Dict[str, int]
    range_violations: Dict[str, int]
    freshness_check: bool
    schema_version: str
    validated_at: datetime = Field(default_factory=datetime.utcnow)
    
    @property
    def validity_rate(self) -> float:
        if self.total_records == 0:
            return 0.0
        return self.valid_records / self.total_records

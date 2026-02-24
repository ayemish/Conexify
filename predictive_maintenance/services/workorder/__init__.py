"""Work Order AI services — LLM-powered interpretation, triage, dispatch, and verification."""

from .models import (
    WorkOrder,
    WorkOrderPriority,
    WorkOrderStatus,
    WorkOrderSource,
    AIImpactAssessment,
    ProviderMatch,
    CostRecommendation,
    VerificationResult,
    ForecastPoint,
    ABBaselineMetrics,
    ABBaselineResponse,
    ABMetricProvenance,
    AB_IMPROVEMENT_FACTORS,
    ABTestRequest,
    ABTestResponse,
)
from .llm_service import WorkOrderLLMService, get_wo_llm_service
from .tools import (
    interpret_work_request,
    auto_create_work_order,
    prioritize_work_order,
    match_service_providers,
    recommend_cost_approval,
    verify_repair_completion,
    forecast_work_orders,
    analyze_wo_ab_test,
)

__all__ = [
    "WorkOrder",
    "WorkOrderPriority",
    "WorkOrderStatus",
    "WorkOrderSource",
    "AIImpactAssessment",
    "ProviderMatch",
    "CostRecommendation",
    "VerificationResult",
    "ForecastPoint",
    "ABBaselineMetrics",
    "ABBaselineResponse",
    "ABMetricProvenance",
    "AB_IMPROVEMENT_FACTORS",
    "ABTestRequest",
    "ABTestResponse",
    "WorkOrderLLMService",
    "get_wo_llm_service",
    # @tool wrappers
    "interpret_work_request",
    "auto_create_work_order",
    "prioritize_work_order",
    "match_service_providers",
    "recommend_cost_approval",
    "verify_repair_completion",
    "forecast_work_orders",
    "analyze_wo_ab_test",
]

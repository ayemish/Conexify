"""
CrewAI @tool wrappers for WorkOrderLLMService.

Each @tool wraps an existing WorkOrderLLMService method, preserving its
deterministic fallback. These tools are attached to Work Order Crew agents
so the LLM can reason about *when* and *how* to use each function.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from .llm_service import get_wo_llm_service
from .models import (
    AutoCreateWORequest,
    CostRecommendRequest,
    ForecastRequest,
    MatchRequest,
    NLInterpretRequest,
    PrioritizeRequest,
    Provider,
    SensorSignal,
    VerificationRequest,
    WorkOrderPriority,
    WorkOrderSource,
)

logger = logging.getLogger(__name__)

# CrewAI @tool decorator with fallback
try:
    from crewai.tools import tool as crewai_tool
except ImportError:
    def crewai_tool(name_or_func=None):
        """Fallback @tool decorator when CrewAI is unavailable."""
        def decorator(func):
            func.tool_name = name_or_func if isinstance(name_or_func, str) else func.__name__
            return func
        if callable(name_or_func):
            return decorator(name_or_func)
        return decorator


# =============================================================================
# 1. Natural Language → Structured WO
# =============================================================================

@crewai_tool("interpret_work_request")
def interpret_work_request(text: str, context_json: str = "{}") -> dict:
    """Interpret natural-language text into a structured work order draft.
    context_json is an optional JSON string with additional context."""
    svc = get_wo_llm_service()
    ctx = None
    try:
        ctx = json.loads(context_json) if context_json and context_json != "{}" else None
    except json.JSONDecodeError:
        pass
    request = NLInterpretRequest(text=text, context=ctx)
    resp = svc.interpret(request)
    return {
        "title": resp.title,
        "description": resp.description,
        "asset_id": resp.asset_id,
        "priority": resp.priority.value if hasattr(resp.priority, "value") else str(resp.priority),
        "problem_type": resp.problem_type,
        "symptoms": resp.symptoms,
        "confidence": resp.confidence,
        "clarifications": resp.clarifications,
    }


# =============================================================================
# 2. Autonomous WO from PdM Signals
# =============================================================================

@crewai_tool("auto_create_work_order")
def auto_create_work_order(signals_json: str, asset_id: str = "") -> dict:
    """Evaluate PdM sensor signals and generate a work order if warranted.
    signals_json is a JSON array of signal objects with keys: asset_id,
    sensor_type, anomaly_type, change_score, persistence_hours, sensor_trust,
    regime, fault_hypothesis, fault_probability."""
    svc = get_wo_llm_service()
    try:
        raw_signals = json.loads(signals_json)
    except json.JSONDecodeError:
        return {"error": "Invalid signals_json", "should_create": False}

    signals = []
    for s in raw_signals:
        signals.append(SensorSignal(
            asset_id=s.get("asset_id", asset_id),
            sensor_type=s.get("sensor_type", "unknown"),
            anomaly_type=s.get("anomaly_type", "unknown"),
            change_score=float(s.get("change_score", 0)),
            persistence_hours=float(s.get("persistence_hours", 0)),
            sensor_trust=float(s.get("sensor_trust", 0.5)),
            regime=s.get("regime", "NORMAL"),
            fault_hypothesis=s.get("fault_hypothesis"),
            fault_probability=float(s.get("fault_probability", 0)) if s.get("fault_probability") else None,
        ))

    if not signals:
        return {"error": "No valid signals", "should_create": False}

    request = AutoCreateWORequest(signals=signals)
    resp = svc.auto_create(request)
    return {
        "should_create": resp.should_create,
        "title": resp.title,
        "description": resp.description,
        "asset_id": resp.asset_id,
        "priority": resp.priority.value if hasattr(resp.priority, "value") else str(resp.priority),
        "problem_type": resp.problem_type,
        "diagnostic_context": resp.diagnostic_context,
        "confidence": resp.confidence,
        "rationale": resp.rationale,
    }


# =============================================================================
# 3. AI Prioritization & Triage
# =============================================================================

@crewai_tool("prioritize_work_order")
def prioritize_work_order(
    work_order_id: str, title: str, description: str,
    asset_id: str, priority: str, source: str = "manual",
    historical_context_json: str = "{}"
) -> dict:
    """Assess work order impact and assign a priority score (0-100).
    Returns AI impact assessment with safety risk, revenue impact, and SLA recommendation."""
    svc = get_wo_llm_service()
    hist = None
    try:
        hist = json.loads(historical_context_json) if historical_context_json != "{}" else None
    except json.JSONDecodeError:
        pass

    request = PrioritizeRequest(
        work_order_id=work_order_id,
        title=title,
        description=description,
        asset_id=asset_id,
        priority=WorkOrderPriority(priority) if priority in [e.value for e in WorkOrderPriority] else WorkOrderPriority.MEDIUM,
        source=WorkOrderSource(source) if source in [e.value for e in WorkOrderSource] else WorkOrderSource.MANUAL,
        historical_context=hist,
    )
    resp = svc.prioritize(request)
    return {
        "work_order_id": resp.work_order_id,
        "priority_score": resp.assessment.priority_score,
        "safety_risk": resp.assessment.safety_risk,
        "revenue_impact": resp.assessment.revenue_impact,
        "sla_breach_risk": resp.assessment.sla_breach_risk,
        "recommended_sla_hours": resp.assessment.recommended_sla_hours,
        "suggested_priority": resp.suggested_priority.value if hasattr(resp.suggested_priority, "value") else str(resp.suggested_priority),
        "rationale": resp.rationale_summary,
    }


# =============================================================================
# 4. Provider Matching & Dispatch
# =============================================================================

@crewai_tool("match_service_providers")
def match_service_providers(
    work_order_id: str, title: str, description: str,
    asset_id: str, priority: str, problem_type: str,
    providers_json: str = "[]"
) -> dict:
    """Match and rank service providers for a work order.
    providers_json is a JSON array of provider objects."""
    svc = get_wo_llm_service()
    try:
        raw_providers = json.loads(providers_json)
    except json.JSONDecodeError:
        return {"error": "Invalid providers_json", "matches": []}

    providers = []
    for p in raw_providers:
        providers.append(Provider(
            id=p.get("id", ""),
            name=p.get("name", ""),
            specialty=p.get("specialty", "General"),
            ftfr=float(p.get("ftfr", 0.7)),
            avg_response_hrs=float(p.get("avg_response_hrs", 24)),
            proximity_miles=float(p.get("proximity_miles", 10)),
            rating=float(p.get("rating", 3.0)),
            available=p.get("available", True),
        ))

    request = MatchRequest(
        work_order_id=work_order_id,
        title=title,
        description=description,
        asset_id=asset_id,
        priority=WorkOrderPriority(priority) if priority in [e.value for e in WorkOrderPriority] else WorkOrderPriority.MEDIUM,
        problem_type=problem_type,
        providers=providers,
    )
    resp = svc.match_providers(request)
    return {
        "work_order_id": resp.work_order_id,
        "matches": [
            {
                "provider_id": m.provider.id,
                "provider_name": m.provider.name,
                "match_score": m.match_score,
                "recommended": m.recommended,
                "rationale": m.rationale,
            }
            for m in resp.matches
        ],
        "rationale_summary": resp.rationale_summary,
    }


# =============================================================================
# 5. Cost & Approval Recommendation
# =============================================================================

@crewai_tool("recommend_cost_approval")
def recommend_cost_approval(
    work_order_id: str, title: str, description: str,
    asset_id: str, priority: str, estimated_cost: float,
    provider_name: str = "", historical_similar_json: str = "[]"
) -> dict:
    """Analyze estimated cost against historical data and provide approval recommendation."""
    svc = get_wo_llm_service()
    try:
        hist = json.loads(historical_similar_json)
    except json.JSONDecodeError:
        hist = []

    request = CostRecommendRequest(
        work_order_id=work_order_id,
        title=title,
        description=description,
        asset_id=asset_id,
        priority=WorkOrderPriority(priority) if priority in [e.value for e in WorkOrderPriority] else WorkOrderPriority.MEDIUM,
        estimated_cost=estimated_cost,
        provider_name=provider_name,
        historical_similar=hist,
    )
    resp = svc.recommend_cost(request)
    return {
        "work_order_id": resp.work_order_id,
        "action": resp.recommendation.action,
        "confidence": resp.recommendation.confidence,
        "reason": resp.recommendation.reason,
        "historical_comparison": resp.recommendation.historical_comparison,
        "risk_factors": resp.recommendation.risk_factors,
    }


# =============================================================================
# 6. Post-Service Verification
# =============================================================================

@crewai_tool("verify_repair_completion")
def verify_repair_completion(
    work_order_id: str, title: str, asset_id: str,
    problem_type: str, pre_metrics_json: str, post_metrics_json: str,
    service_description: str = ""
) -> dict:
    """Compare pre-service and post-service metrics to determine repair effectiveness."""
    svc = get_wo_llm_service()
    try:
        pre = json.loads(pre_metrics_json)
        post = json.loads(post_metrics_json)
    except json.JSONDecodeError:
        return {"error": "Invalid metrics JSON", "passed": False}

    request = VerificationRequest(
        work_order_id=work_order_id,
        title=title,
        asset_id=asset_id,
        problem_type=problem_type,
        pre_service_metrics=pre,
        post_service_metrics=post,
        service_description=service_description,
    )
    resp = svc.verify(request)
    return {
        "work_order_id": resp.work_order_id,
        "passed": resp.verification.passed,
        "confidence": resp.verification.confidence,
        "post_metrics_improved": resp.verification.post_metrics_improved,
        "evidence_summary": resp.verification.evidence_summary,
        "reopen_reason": resp.verification.reopen_reason,
        "recommendations": resp.verification.recommendations,
    }


# =============================================================================
# 7. Forecast Interpretation
# =============================================================================

@crewai_tool("forecast_work_orders")
def forecast_work_orders(
    site_id: str = "default", horizon_days: int = 30,
    historical_json: str = "[]", risk_scores_json: str = "{}"
) -> dict:
    """Generate WO forecast with narrative interpretation.
    Returns time-series predictions and natural-language interpretation."""
    svc = get_wo_llm_service()
    try:
        hist = json.loads(historical_json)
        risk = json.loads(risk_scores_json)
    except json.JSONDecodeError:
        hist, risk = [], {}

    request = ForecastRequest(
        site_id=site_id,
        horizon_days=horizon_days,
        historical_wo_counts=hist,
        asset_risk_scores=risk,
    )
    resp = svc.forecast(request)
    return {
        "site_id": resp.site_id,
        "narrative": resp.narrative,
        "risk_estates": resp.risk_estates,
        "total_predicted": sum(p.predicted_count for p in resp.points),
        "point_count": len(resp.points),
    }


# =============================================================================
# 8. A/B Test Analysis
# =============================================================================

@crewai_tool("analyze_wo_ab_test")
def analyze_wo_ab_test(
    baseline_json: str, predicted_json: str, time_range: str = "30d"
) -> dict:
    """A/B test insight comparing baseline vs AI-predicted work order metrics.
    Returns analytical narrative, top improvements, risk areas, and executive summary."""
    svc = get_wo_llm_service()
    try:
        baseline = json.loads(baseline_json)
        predicted = json.loads(predicted_json)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON input"}

    resp = svc.ab_test(baseline, predicted, time_range)
    return {
        "insight": resp.insight,
        "top_improvements": resp.top_improvements,
        "risk_areas": resp.risk_areas,
        "confidence_level": resp.confidence_level,
        "executive_summary": resp.executive_summary,
    }


# =============================================================================
# Convenience: all tools as a list for Crew attachment
# =============================================================================

ALL_WO_TOOLS = [
    interpret_work_request,
    auto_create_work_order,
    prioritize_work_order,
    match_service_providers,
    recommend_cost_approval,
    verify_repair_completion,
    forecast_work_orders,
    analyze_wo_ab_test,
]

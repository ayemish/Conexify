"""
Advanced Services API Routes

Endpoints for Phase 3-4 capabilities:
- Ensemble calibration with conformal prediction
- Adaptive agent weights via Thompson Sampling
- SHAP-based explainability
- TFT RUL predictions
- Digital twin state
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request/Response Models ─────────────────────────────────────────


class ModelPredictionInput(BaseModel):
    """Input for ensemble prediction"""
    model_predictions: Dict[str, float] = Field(..., description="Predictions from each model")
    model_intervals: Optional[Dict[str, List[float]]] = Field(None, description="Prediction intervals [lower, upper]")


class CalibrationUpdateInput(BaseModel):
    """Input for calibration update"""
    model_predictions: Dict[str, float]
    actual_value: float
    model_intervals: Optional[Dict[str, List[float]]] = None


class AgentVoteInput(BaseModel):
    """Input for recording agent voting decision"""
    asset_id: str
    agent_votes: Dict[str, bool]  # agent_role -> vote (True = alarm)
    agent_weights: Dict[str, float]
    final_decision: str
    confidence: float
    regime: str = ""
    fault_type: str = ""


class FeedbackInput(BaseModel):
    """Input for agent feedback"""
    decision_id: str
    outcome: str
    was_correct: bool


class ExplanationRequest(BaseModel):
    """Request for fault explanation"""
    asset_id: str
    features: Dict[str, float]
    fault_belief: Dict[str, float]
    predicted_fault: str
    confidence: float
    false_alarm_probability: float = 0.0
    gate_evaluations: Optional[List[Dict[str, Any]]] = None


class TFTPredictionInput(BaseModel):
    """Input for TFT RUL prediction"""
    static_features: Dict[str, float]
    temporal_features: List[Dict[str, float]]
    failure_threshold: float = 0.8


class PhysicsCheckInput(BaseModel):
    """Input for physics constraint check"""
    features: Dict[str, float]


class DigitalTwinStateInput(BaseModel):
    """Input for digital twin state update"""
    asset_id: str
    telemetry: Dict[str, float]
    component_health: Dict[str, float]
    alerts: List[Dict[str, Any]] = []


# ── Service Singletons ──────────────────────────────────────────────


_ensemble_service = None
_agent_weights_service = None
_explainability_service = None
_tft_predictor = None
_physics_loss = None


def get_ensemble_service():
    global _ensemble_service
    if _ensemble_service is None:
        from ...services.ensemble_calibration_service import EnsembleCalibrationService
        _ensemble_service = EnsembleCalibrationService(
            model_ids=["weibull", "degradation", "trend", "ensemble"],
            coverage_level=0.90,
        )
    return _ensemble_service


def get_agent_weights_service():
    global _agent_weights_service
    if _agent_weights_service is None:
        from ...services.adaptive_agent_weights import AdaptiveAgentWeights
        _agent_weights_service = AdaptiveAgentWeights(
            agent_roles=[
                "regime_detector",
                "sensor_trust",
                "behavior_modeler",
                "change_detector",
                "fault_hypothesis",
                "decision_policy",
            ],
        )
    return _agent_weights_service


def get_explainability_service():
    global _explainability_service
    if _explainability_service is None:
        from ...services.explainability_service import ExplainabilityService
        _explainability_service = ExplainabilityService()
    return _explainability_service


def get_tft_predictor():
    global _tft_predictor
    if _tft_predictor is None:
        from ...models.temporal_fusion_transformer import TFTRULPredictor
        _tft_predictor = TFTRULPredictor()
    return _tft_predictor


def get_physics_loss():
    global _physics_loss
    if _physics_loss is None:
        from ...models.physics_informed_constraints import PhysicsInformedLoss
        _physics_loss = PhysicsInformedLoss()
    return _physics_loss


# ── Ensemble Calibration Endpoints ──────────────────────────────────


@router.post("/ensemble/predict")
async def ensemble_predict(input: ModelPredictionInput) -> Dict[str, Any]:
    """
    Generate calibrated ensemble prediction with conformal interval.
    """
    service = get_ensemble_service()
    
    # Convert intervals from list to tuple
    model_intervals = None
    if input.model_intervals:
        model_intervals = {
            k: (v[0], v[1]) for k, v in input.model_intervals.items()
        }
    
    result = service.predict(input.model_predictions, model_intervals)
    
    return {
        "point_estimate": result.point_estimate,
        "lower_bound": result.lower_bound,
        "upper_bound": result.upper_bound,
        "coverage_level": result.coverage_level,
        "model_weights": result.model_weights,
        "calibration_set_size": result.calibration_set_size,
        "is_valid": result.is_valid,
    }


@router.post("/ensemble/update")
async def ensemble_update(input: CalibrationUpdateInput) -> Dict[str, str]:
    """
    Update calibration with observed ground truth.
    """
    service = get_ensemble_service()
    
    model_intervals = None
    if input.model_intervals:
        model_intervals = {
            k: (v[0], v[1]) for k, v in input.model_intervals.items()
        }
    
    service.update(input.model_predictions, input.actual_value, model_intervals)
    
    return {"status": "updated"}


@router.get("/ensemble/metrics")
async def ensemble_metrics() -> Dict[str, Any]:
    """
    Get current ensemble calibration metrics.
    """
    service = get_ensemble_service()
    return service.get_calibration_metrics()


@router.get("/ensemble/ranking")
async def ensemble_ranking() -> List[Dict[str, Any]]:
    """
    Get models ranked by performance.
    """
    service = get_ensemble_service()
    ranking = service.get_model_ranking()
    return [
        {"model_id": mid, "weight": w, "mae": mae}
        for mid, w, mae in ranking
    ]


# ── Adaptive Agent Weights Endpoints ────────────────────────────────


@router.post("/agents/sample-weights")
async def sample_agent_weights(
    regime: str = Query("", description="Operating regime"),
    fault_type: str = Query("", description="Fault type being evaluated"),
) -> Dict[str, float]:
    """
    Sample agent weights using Thompson Sampling.
    """
    service = get_agent_weights_service()
    
    context = None
    if regime or fault_type:
        context = {"regime": regime, "fault_type": fault_type}
    
    return service.sample_weights(context)


@router.get("/agents/mean-weights")
async def get_mean_agent_weights(
    regime: str = Query("", description="Operating regime"),
    fault_type: str = Query("", description="Fault type"),
) -> Dict[str, float]:
    """
    Get mean agent weights (exploitation only).
    """
    service = get_agent_weights_service()
    
    context = None
    if regime or fault_type:
        context = {"regime": regime, "fault_type": fault_type}
    
    return service.get_mean_weights(context)


@router.post("/agents/record-decision")
async def record_agent_decision(input: AgentVoteInput) -> Dict[str, str]:
    """
    Record a voting decision for later learning.
    """
    service = get_agent_weights_service()
    
    decision_id = service.record_decision(
        asset_id=input.asset_id,
        agent_votes=input.agent_votes,
        agent_weights=input.agent_weights,
        final_decision=input.final_decision,
        confidence=input.confidence,
        regime=input.regime,
        fault_type=input.fault_type,
    )
    
    return {"decision_id": decision_id}


@router.post("/agents/feedback")
async def submit_agent_feedback(input: FeedbackInput) -> Dict[str, str]:
    """
    Update agent beliefs based on decision outcome.
    """
    service = get_agent_weights_service()
    
    service.update_from_feedback(
        decision_id=input.decision_id,
        outcome=input.outcome,
        was_correct=input.was_correct,
    )
    
    return {"status": "updated"}


@router.get("/agents/stats")
async def get_agent_stats() -> Dict[str, Any]:
    """
    Get current statistics for all agents.
    """
    service = get_agent_weights_service()
    return {
        "agents": service.get_agent_stats(),
        "overall_accuracy": service.overall_accuracy,
        "ranking": [
            {"role": role, "mean": mean, "confidence": conf}
            for role, mean, conf in service.get_ranking()
        ],
    }


# ── Explainability Endpoints ────────────────────────────────────────


@router.post("/explain/fault")
async def explain_fault(input: ExplanationRequest) -> Dict[str, Any]:
    """
    Generate comprehensive explanation for a fault hypothesis.
    """
    service = get_explainability_service()
    
    explanation = service.explain_fault_hypothesis(
        asset_id=input.asset_id,
        features=input.features,
        fault_belief=input.fault_belief,
        predicted_fault=input.predicted_fault,
        confidence=input.confidence,
        false_alarm_probability=input.false_alarm_probability,
        gate_evaluations=input.gate_evaluations,
    )
    
    return explanation.to_dict()


@router.post("/explain/add-case")
async def add_resolved_case(case: Dict[str, Any]) -> Dict[str, str]:
    """
    Add a resolved case to the explanation database.
    """
    service = get_explainability_service()
    service.add_case_to_database(case)
    return {"status": "added"}


# ── TFT RUL Prediction Endpoints ────────────────────────────────────


@router.post("/tft/predict")
async def tft_predict(input: TFTPredictionInput) -> Dict[str, Any]:
    """
    Predict RUL using Temporal Fusion Transformer.
    """
    predictor = get_tft_predictor()
    
    result = predictor.predict(
        static_features=input.static_features,
        temporal_features=input.temporal_features,
        failure_threshold=input.failure_threshold,
    )
    
    return {
        "prediction_id": result.prediction_id,
        "timestamp": result.timestamp.isoformat(),
        "rul_hours": result.rul_hours,
        "rul_lower": result.rul_lower,
        "rul_upper": result.rul_upper,
        "degradation_rate": result.degradation_rate,
        "point_forecast": result.point_forecast.tolist() if len(result.point_forecast) > 0 else [],
        "quantile_forecasts": {
            str(q): v.tolist() for q, v in result.quantile_forecasts.items()
        },
        "static_weights": result.static_weights,
        "temporal_weights": result.temporal_weights,
    }


@router.get("/tft/feature-importance")
async def tft_feature_importance() -> Dict[str, float]:
    """
    Get global feature importance from TFT model.
    """
    predictor = get_tft_predictor()
    return predictor.get_feature_importance()


# ── Physics Constraints Endpoints ───────────────────────────────────


@router.post("/physics/check")
async def check_physics_constraints(input: PhysicsCheckInput) -> Dict[str, Any]:
    """
    Check physics constraints for given features.
    """
    loss = get_physics_loss()
    
    penalty, violations = loss.compute_penalty(input.features)
    
    return {
        "total_penalty": penalty,
        "violations": [
            {
                "constraint_id": v.constraint_id,
                "constraint_name": v.constraint_name,
                "residual": v.residual,
                "penalty": v.penalty,
            }
            for v in violations
        ],
    }


@router.post("/physics/project")
async def project_to_feasible(input: PhysicsCheckInput) -> Dict[str, float]:
    """
    Project features to feasible region (satisfy hard constraints).
    """
    loss = get_physics_loss()
    return loss.project_to_feasible(input.features)


@router.get("/physics/constraints")
async def list_physics_constraints() -> List[Dict[str, Any]]:
    """
    List all active physics constraints.
    """
    loss = get_physics_loss()
    
    return [
        {
            "id": c.constraint_id,
            "name": c.name,
            "type": c.constraint_type.value,
            "weight": c.weight,
            "is_hard": c.is_hard,
            "description": c.description,
            "equation": c.equation,
        }
        for c in loss.constraints
    ]


@router.get("/physics/violations")
async def get_violation_summary() -> Dict[str, Any]:
    """
    Get summary of recent constraint violations.
    """
    loss = get_physics_loss()
    return loss.get_violation_summary()


# ── Digital Twin State Endpoints ────────────────────────────────────


_digital_twin_states: Dict[str, Dict[str, Any]] = {}


@router.post("/digital-twin/update")
async def update_digital_twin(input: DigitalTwinStateInput) -> Dict[str, str]:
    """
    Update digital twin state for an asset.
    """
    _digital_twin_states[input.asset_id] = {
        "asset_id": input.asset_id,
        "telemetry": input.telemetry,
        "component_health": input.component_health,
        "alerts": input.alerts,
        "last_updated": datetime.utcnow().isoformat(),
    }
    
    return {"status": "updated", "asset_id": input.asset_id}


@router.get("/digital-twin/{asset_id}")
async def get_digital_twin_state(asset_id: str) -> Dict[str, Any]:
    """
    Get current digital twin state for an asset.
    """
    if asset_id not in _digital_twin_states:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    
    return _digital_twin_states[asset_id]


@router.get("/digital-twin/{asset_id}/components")
async def get_component_health(asset_id: str) -> Dict[str, float]:
    """
    Get component health scores for digital twin.
    """
    if asset_id not in _digital_twin_states:
        # Return default healthy state
        return {
            "compressor": 95.0,
            "condenser": 92.0,
            "condenser_fan": 98.0,
            "evaporator": 90.0,
            "evaporator_fan": 97.0,
            "expansion_valve": 88.0,
            "filter_drier": 85.0,
        }
    
    return _digital_twin_states[asset_id].get("component_health", {})


# ── Fleet Correlation Context ───────────────────────────────────────


@router.get("/fleet/voting-context/{asset_id}")
async def get_fleet_voting_context(asset_id: str) -> Dict[str, Any]:
    """
    Get fleet correlation context for agent voting decisions.
    """
    try:
        from ...services.fleet_correlation_service import FleetCorrelationService
        
        # Get or create service (in production this would be a singleton)
        service = FleetCorrelationService()
        return service.get_voting_context(asset_id)
    except Exception as e:
        logger.warning(f"Fleet correlation not available: {e}")
        return {"fleet_context_available": False, "error": str(e)}

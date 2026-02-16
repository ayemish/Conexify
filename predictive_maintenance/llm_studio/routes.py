"""
LLM Studio API Routes

REST API endpoints for workflow exploration and LLM training data management.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field

from .models import (
    DecisionType,
    OutcomeStatus,
    AnnotationType,
    ExportFormat,
)
from .capture import WorkflowCaptureService
from .export import TrainingDataExporter

# Initialize services
capture_service = WorkflowCaptureService()
exporter = TrainingDataExporter()

# Create routers
traces_router = APIRouter(prefix="/traces", tags=["Workflow Traces"])
decisions_router = APIRouter(prefix="/decisions", tags=["Agent Decisions"])
annotations_router = APIRouter(prefix="/annotations", tags=["Annotations"])
export_router = APIRouter(prefix="/export", tags=["Training Export"])
stats_router = APIRouter(prefix="/stats", tags=["Statistics"])


# Request/Response Models
class TraceResponse(BaseModel):
    trace_id: str
    workflow_type: str
    incident_id: Optional[str]
    run_id: Optional[str]
    tenant_id: str
    site_id: str
    asset_id: str
    started_at: str
    completed_at: Optional[str]
    final_status: str
    final_outcome: str
    decision_count: int
    include_in_training: bool
    quality_score: Optional[float]


class DecisionResponse(BaseModel):
    decision_id: str
    trace_id: str
    decision_type: str
    agent_name: str
    timestamp: str
    confidence: float
    decision: str
    reasoning_steps: List[str]
    outcome_status: Optional[str]
    outcome_summary: Optional[str]


class AnnotationRequest(BaseModel):
    annotation_type: str = Field(..., description="Type of annotation")
    annotator_id: str = Field(..., description="ID of the annotator")
    is_correct: Optional[bool] = None
    quality_score: Optional[float] = Field(None, ge=0, le=1)
    corrected_decision: Optional[str] = None
    corrected_reasoning: Optional[List[str]] = None
    notes: str = ""
    tags: List[str] = []
    annotator_role: str = ""


class ExportRequest(BaseModel):
    format: str = Field(default="jsonl", description="Export format")
    decision_types: Optional[List[str]] = None
    min_confidence: Optional[float] = None
    only_successful: bool = True
    only_human_verified: bool = False
    limit: int = Field(default=1000, le=10000)


class StatsResponse(BaseModel):
    total_traces: int
    total_decisions: int
    status_counts: Dict[str, int]
    decision_type_counts: Dict[str, int]
    successful_decisions: int
    verified_decisions: int
    trainable_decisions: int
    avg_decisions_per_trace: float


# Trace Endpoints
@traces_router.get("", response_model=List[TraceResponse])
async def list_traces(
    tenant_id: Optional[str] = None,
    workflow_type: Optional[str] = None,
    status: Optional[str] = None,
    include_in_training: Optional[bool] = None,
    min_quality_score: Optional[float] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
):
    """List workflow traces with filtering"""
    status_enum = OutcomeStatus(status) if status else None
    
    traces = capture_service.list_traces(
        tenant_id=tenant_id,
        workflow_type=workflow_type,
        status=status_enum,
        include_in_training=include_in_training,
        min_quality_score=min_quality_score,
        limit=limit,
        offset=offset,
    )
    
    return [
        TraceResponse(
            trace_id=t.trace_id,
            workflow_type=t.workflow_type,
            incident_id=t.incident_id,
            run_id=t.run_id,
            tenant_id=t.tenant_id,
            site_id=t.site_id,
            asset_id=t.asset_id,
            started_at=t.started_at.isoformat(),
            completed_at=t.completed_at.isoformat() if t.completed_at else None,
            final_status=t.final_status.value,
            final_outcome=t.final_outcome,
            decision_count=len(t.decisions),
            include_in_training=t.include_in_training,
            quality_score=t.quality_score,
        )
        for t in traces
    ]


@traces_router.get("/{trace_id}")
async def get_trace(trace_id: str):
    """Get a specific trace with all decisions"""
    trace = capture_service.get_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    
    return trace.to_dict()


@traces_router.patch("/{trace_id}/training")
async def update_training_status(
    trace_id: str,
    include_in_training: bool = Body(..., embed=True),
):
    """Update whether a trace should be included in training"""
    trace = capture_service.get_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    
    trace.include_in_training = include_in_training
    
    return {"trace_id": trace_id, "include_in_training": include_in_training}


@traces_router.patch("/{trace_id}/quality")
async def update_quality_score(
    trace_id: str,
    quality_score: float = Body(..., embed=True, ge=0, le=1),
):
    """Update the quality score of a trace"""
    trace = capture_service.get_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    
    trace.quality_score = quality_score
    
    return {"trace_id": trace_id, "quality_score": quality_score}


# Decision Endpoints
@decisions_router.get("")
async def list_decisions(
    trace_id: Optional[str] = None,
    decision_type: Optional[str] = None,
    min_confidence: Optional[float] = None,
    only_successful: bool = False,
    limit: int = Query(default=100, le=500),
):
    """List agent decisions with filtering"""
    decision_types = [DecisionType(decision_type)] if decision_type else None
    
    decisions = capture_service.get_decisions_for_training(
        decision_types=decision_types,
        min_confidence=min_confidence,
        only_successful=only_successful,
        limit=limit,
    )
    
    if trace_id:
        decisions = [d for d in decisions if d.trace_id == trace_id]
    
    return [
        DecisionResponse(
            decision_id=d.decision_id,
            trace_id=d.trace_id,
            decision_type=d.decision_type.value,
            agent_name=d.agent_name,
            timestamp=d.timestamp.isoformat(),
            confidence=d.confidence,
            decision=d.decision,
            reasoning_steps=d.reasoning_steps,
            outcome_status=d.outcome.status.value if d.outcome else None,
            outcome_summary=d.outcome.result_summary if d.outcome else None,
        )
        for d in decisions
    ]


@decisions_router.get("/{decision_id}")
async def get_decision(decision_id: str):
    """Get a specific decision with full context"""
    decision = capture_service._decisions.get(decision_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")
    
    return decision.to_dict()


@decisions_router.get("/{decision_id}/training-example")
async def get_training_example(decision_id: str):
    """Get a decision formatted as a training example"""
    decision = capture_service._decisions.get(decision_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")
    
    example = exporter.decision_to_example(decision)
    
    return {
        "jsonl": example.to_jsonl(),
        "conversation": example.to_conversation(),
        "alpaca": example.to_alpaca(),
        "sharegpt": example.to_sharegpt(),
    }


# Annotation Endpoints
@annotations_router.post("/decision/{decision_id}")
async def annotate_decision(decision_id: str, request: AnnotationRequest):
    """Add an annotation to a decision"""
    try:
        annotation_type = AnnotationType(request.annotation_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid annotation type: {request.annotation_type}"
        )
    
    annotation = capture_service.add_annotation(
        annotation_type=annotation_type,
        annotator_id=request.annotator_id,
        decision_id=decision_id,
        is_correct=request.is_correct,
        quality_score=request.quality_score,
        corrected_decision=request.corrected_decision,
        corrected_reasoning=request.corrected_reasoning,
        notes=request.notes,
        tags=request.tags,
        annotator_role=request.annotator_role,
    )
    
    return annotation.to_dict()


@annotations_router.post("/trace/{trace_id}")
async def annotate_trace(trace_id: str, request: AnnotationRequest):
    """Add an annotation to a trace"""
    try:
        annotation_type = AnnotationType(request.annotation_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid annotation type: {request.annotation_type}"
        )
    
    annotation = capture_service.add_annotation(
        annotation_type=annotation_type,
        annotator_id=request.annotator_id,
        trace_id=trace_id,
        is_correct=request.is_correct,
        quality_score=request.quality_score,
        corrected_decision=request.corrected_decision,
        corrected_reasoning=request.corrected_reasoning,
        notes=request.notes,
        tags=request.tags,
        annotator_role=request.annotator_role,
    )
    
    return annotation.to_dict()


@annotations_router.get("/decision/{decision_id}")
async def get_decision_annotations(decision_id: str):
    """Get all annotations for a decision"""
    annotations = capture_service._annotations.get(decision_id, [])
    return [a.to_dict() for a in annotations]


# Export Endpoints
@export_router.post("/decisions")
async def export_decisions(request: ExportRequest):
    """Export decisions as training data"""
    try:
        format_enum = ExportFormat(request.format)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid format: {request.format}"
        )
    
    decision_types = None
    if request.decision_types:
        decision_types = [DecisionType(dt) for dt in request.decision_types]
    
    decisions = capture_service.get_decisions_for_training(
        decision_types=decision_types,
        min_confidence=request.min_confidence,
        only_successful=request.only_successful,
        only_human_verified=request.only_human_verified,
        limit=request.limit,
    )
    
    # Generate examples inline (not writing to file)
    examples = [exporter.decision_to_example(d) for d in decisions]
    
    if format_enum == ExportFormat.JSONL:
        data = [e.to_jsonl() for e in examples]
    elif format_enum == ExportFormat.CONVERSATION:
        data = [e.to_conversation() for e in examples]
    elif format_enum == ExportFormat.ALPACA:
        data = [e.to_alpaca() for e in examples]
    elif format_enum == ExportFormat.SHAREGPT:
        data = [e.to_sharegpt() for e in examples]
    
    return {
        "format": format_enum.value,
        "count": len(data),
        "data": data,
    }


@export_router.post("/traces/conversations")
async def export_traces_as_conversations(
    trace_ids: List[str] = Body(..., description="List of trace IDs to export"),
):
    """Export traces as multi-turn conversations"""
    conversations = []
    
    for trace_id in trace_ids:
        trace = capture_service.get_trace(trace_id)
        if trace and trace.include_in_training:
            messages = exporter.trace_to_conversation(trace)
            conversations.append({
                "trace_id": trace_id,
                "messages": messages,
            })
    
    return {
        "count": len(conversations),
        "conversations": conversations,
    }


# Stats Endpoints
@stats_router.get("", response_model=StatsResponse)
async def get_stats():
    """Get statistics about captured workflows"""
    stats = capture_service.get_trace_stats()
    return StatsResponse(**stats)


@stats_router.get("/decision-types")
async def get_decision_type_distribution():
    """Get distribution of decision types"""
    stats = capture_service.get_trace_stats()
    return stats["decision_type_counts"]


@stats_router.get("/quality-distribution")
async def get_quality_distribution():
    """Get distribution of quality scores"""
    traces = capture_service.list_traces(limit=10000)
    
    buckets = {
        "0.0-0.2": 0,
        "0.2-0.4": 0,
        "0.4-0.6": 0,
        "0.6-0.8": 0,
        "0.8-1.0": 0,
        "unscored": 0,
    }
    
    for trace in traces:
        if trace.quality_score is None:
            buckets["unscored"] += 1
        elif trace.quality_score < 0.2:
            buckets["0.0-0.2"] += 1
        elif trace.quality_score < 0.4:
            buckets["0.2-0.4"] += 1
        elif trace.quality_score < 0.6:
            buckets["0.4-0.6"] += 1
        elif trace.quality_score < 0.8:
            buckets["0.6-0.8"] += 1
        else:
            buckets["0.8-1.0"] += 1
    
    return buckets

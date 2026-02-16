"""
Playbook Planner

Integrates Estate Brain knowledge with playbook execution for
context-aware step parameterization.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
import uuid

from .brain import EstateBrain, KnowledgeQuery, KnowledgeResult
from .graph import KnowledgeGraph, EntityType
from ..playbook.schema import PlaybookDefinition, PlaybookStep
from ..playbook.expressions import ExpressionEvaluator, EvalContext

logger = logging.getLogger(__name__)


@dataclass
class PlannerContext:
    """Context for playbook planning"""
    tenant_id: str
    site_id: str
    asset_id: str
    
    # Incident info
    incident_id: str = ""
    fault_type: str = ""
    severity: str = "medium"
    
    # Current telemetry
    points: Dict[str, float] = field(default_factory=dict)
    
    # Asset info from knowledge graph
    asset_info: Dict[str, Any] = field(default_factory=dict)
    related_points: List[str] = field(default_factory=list)
    
    # Policy constraints
    policy: Dict[str, Any] = field(default_factory=dict)
    
    # Knowledge results
    knowledge_result: Optional[KnowledgeResult] = None
    
    def to_eval_context(self) -> EvalContext:
        """Convert to expression evaluation context"""
        return EvalContext(
            points=self.points,
            asset_id=self.asset_id,
            policy=self.policy,
        )


@dataclass
class PlannedStep:
    """A step with resolved parameters"""
    step_id: str
    original_step: PlaybookStep
    
    # Resolved parameters
    resolved_params: Dict[str, Any] = field(default_factory=dict)
    
    # Rationale
    rationale: str = ""
    
    # Knowledge citations used
    citations: List[str] = field(default_factory=list)
    
    # Approval requirements
    requires_approval: bool = False
    approval_reason: str = ""


@dataclass
class ExecutionPlan:
    """Complete execution plan for a playbook"""
    plan_id: str = field(default_factory=lambda: f"PLAN-{uuid.uuid4().hex[:8].upper()}")
    
    # Source
    playbook_id: str = ""
    playbook_version: str = ""
    
    # Context
    context: PlannerContext = None
    
    # Planned steps
    steps: List[PlannedStep] = field(default_factory=list)
    
    # Overall rationale
    rationale: str = ""
    
    # Risk assessment
    risk_tier: str = "MEDIUM"
    risk_factors: List[str] = field(default_factory=list)
    
    # Timing
    planned_at: datetime = field(default_factory=datetime.utcnow)
    estimated_duration_seconds: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "playbook_id": self.playbook_id,
            "playbook_version": self.playbook_version,
            "rationale": self.rationale,
            "risk_tier": self.risk_tier,
            "risk_factors": self.risk_factors,
            "steps": [
                {
                    "step_id": s.step_id,
                    "type": s.original_step.type.value,
                    "resolved_params": s.resolved_params,
                    "rationale": s.rationale,
                    "requires_approval": s.requires_approval,
                }
                for s in self.steps
            ],
            "planned_at": self.planned_at.isoformat(),
            "estimated_duration_seconds": self.estimated_duration_seconds,
        }


class PlaybookPlanner:
    """
    Plans playbook execution using Estate Brain knowledge.
    
    Responsibilities:
    - Resolve dynamic parameters using context
    - Enrich steps with knowledge graph data
    - Compute risk factors
    - Determine approval requirements
    - Generate execution rationale
    """
    
    def __init__(
        self,
        brain: EstateBrain = None,
        evaluator: ExpressionEvaluator = None,
    ):
        self.brain = brain or EstateBrain()
        self.evaluator = evaluator or ExpressionEvaluator()
    
    def plan(
        self,
        playbook: PlaybookDefinition,
        context: PlannerContext,
    ) -> ExecutionPlan:
        """
        Create an execution plan for a playbook.
        
        Args:
            playbook: Playbook to plan
            context: Planning context
            
        Returns:
            ExecutionPlan with resolved steps
        """
        plan = ExecutionPlan(
            playbook_id=playbook.id,
            playbook_version=playbook.version,
            context=context,
            risk_tier=playbook.risk_tier,
        )
        
        # 1. Query knowledge for context
        knowledge = self._query_knowledge(playbook, context)
        context.knowledge_result = knowledge
        
        # 2. Enrich context from knowledge graph
        self._enrich_context(context)
        
        # 3. Plan each step
        for step in playbook.steps:
            planned_step = self._plan_step(step, context, knowledge)
            plan.steps.append(planned_step)
        
        # 4. Assess risk
        plan.risk_factors = self._assess_risk(plan, context)
        if plan.risk_factors:
            # Upgrade risk tier if significant factors found
            if len(plan.risk_factors) >= 3:
                plan.risk_tier = "HIGH"
            elif len(plan.risk_factors) >= 1 and plan.risk_tier == "LOW":
                plan.risk_tier = "MEDIUM"
        
        # 5. Generate rationale
        plan.rationale = self._generate_rationale(plan, context, knowledge)
        
        # 6. Estimate duration
        plan.estimated_duration_seconds = self._estimate_duration(plan)
        
        logger.info(
            f"Created execution plan {plan.plan_id} for playbook {playbook.id} "
            f"with {len(plan.steps)} steps (risk_tier={plan.risk_tier})"
        )
        
        return plan
    
    def _query_knowledge(
        self,
        playbook: PlaybookDefinition,
        context: PlannerContext,
    ) -> KnowledgeResult:
        """Query Estate Brain for relevant knowledge"""
        query = KnowledgeQuery(
            question=f"How to resolve {playbook.fault_type} on {playbook.asset_class}?",
            tenant_id=context.tenant_id,
            asset_id=context.asset_id,
            fault_type=context.fault_type or playbook.fault_type,
            include_similar_cases=True,
            include_documentation=True,
            include_graph_context=True,
        )
        
        return self.brain.query(query)
    
    def _enrich_context(self, context: PlannerContext):
        """Enrich context with knowledge graph data"""
        if not context.asset_id:
            return
        
        # Get asset info from graph
        hierarchy = self.brain.graph.get_equipment_hierarchy(context.asset_id)
        if hierarchy:
            context.asset_info = hierarchy.get("entity", {})
            
            # Extract point IDs
            for point_data in hierarchy.get("points", []):
                point_id = point_data.get("entity_id")
                if point_id:
                    context.related_points.append(point_id)
    
    def _plan_step(
        self,
        step: PlaybookStep,
        context: PlannerContext,
        knowledge: KnowledgeResult,
    ) -> PlannedStep:
        """Plan a single step with resolved parameters"""
        planned = PlannedStep(
            step_id=step.id,
            original_step=step,
            requires_approval=step.requires_approval,
        )
        
        # Resolve parameters
        planned.resolved_params = self._resolve_params(step.params, context)
        
        # Determine if approval needed based on action type
        if step.type.value in ["WRITE_POINT", "ESCALATE"]:
            if context.policy.get("require_approval_for_writes", True):
                planned.requires_approval = True
                planned.approval_reason = f"Control write requires approval (type={step.type.value})"
        
        # Add knowledge citations
        if knowledge.citations:
            for citation in knowledge.citations[:2]:
                if self._citation_relevant_to_step(citation, step):
                    planned.citations.append(citation.source_id)
        
        # Generate step rationale
        planned.rationale = self._generate_step_rationale(step, context, knowledge)
        
        return planned
    
    def _resolve_params(
        self,
        params: Dict[str, Any],
        context: PlannerContext,
    ) -> Dict[str, Any]:
        """Resolve dynamic parameters using context"""
        resolved = {}
        
        for key, value in params.items():
            if isinstance(value, str):
                # Check for expression syntax
                if value.startswith("${") and value.endswith("}"):
                    # Extract expression
                    expr = value[2:-1]
                    try:
                        resolved[key] = self.evaluator.evaluate(
                            expr, context.to_eval_context()
                        )
                    except Exception as e:
                        logger.warning(f"Failed to resolve param {key}: {e}")
                        resolved[key] = value
                
                # Check for context references
                elif value.startswith("context."):
                    ref = value[8:]
                    if ref in context.points:
                        resolved[key] = context.points[ref]
                    elif hasattr(context, ref):
                        resolved[key] = getattr(context, ref)
                    else:
                        resolved[key] = value
                
                # Check for point references
                elif value in context.points:
                    resolved[key] = context.points[value]
                
                else:
                    resolved[key] = value
            else:
                resolved[key] = value
        
        return resolved
    
    def _citation_relevant_to_step(self, citation, step: PlaybookStep) -> bool:
        """Check if a citation is relevant to a step"""
        # Simple keyword matching
        step_keywords = [
            step.type.value.lower(),
            step.description.lower() if step.description else "",
        ]
        
        excerpt_lower = citation.excerpt.lower()
        
        return any(kw in excerpt_lower for kw in step_keywords if kw)
    
    def _assess_risk(
        self,
        plan: ExecutionPlan,
        context: PlannerContext,
    ) -> List[str]:
        """Assess risk factors for the plan"""
        factors = []
        
        # Count control writes
        write_count = sum(
            1 for s in plan.steps
            if s.original_step.type.value == "WRITE_POINT"
        )
        if write_count > 3:
            factors.append(f"Multiple control writes ({write_count})")
        
        # Check for large setpoint changes
        for step in plan.steps:
            if step.original_step.type.value == "WRITE_POINT":
                value = step.resolved_params.get("value")
                point_id = step.resolved_params.get("point_id")
                
                if point_id and value:
                    current = context.points.get(point_id)
                    if current:
                        delta = abs(value - current)
                        max_delta = context.policy.get("max_setpoint_delta", 5.0)
                        if delta > max_delta:
                            factors.append(
                                f"Large setpoint change: {point_id} delta={delta:.1f}"
                            )
        
        # Check operating hours
        current_hour = datetime.utcnow().hour
        store_start = context.policy.get("store_hours_start", 6)
        store_end = context.policy.get("store_hours_end", 22)
        if not (store_start <= current_hour < store_end):
            factors.append("Execution outside store hours")
        
        # Check similar case outcomes
        if context.knowledge_result:
            failed_cases = [
                c for c in context.knowledge_result.similar_cases
                if c.get("outcome") == "FAILED"
            ]
            if failed_cases:
                factors.append(f"Similar cases with failures found ({len(failed_cases)})")
        
        return factors
    
    def _generate_rationale(
        self,
        plan: ExecutionPlan,
        context: PlannerContext,
        knowledge: KnowledgeResult,
    ) -> str:
        """Generate overall plan rationale"""
        parts = [
            f"Execution plan for {plan.playbook_id} v{plan.playbook_version}",
            f"Asset: {context.asset_id}",
            f"Fault type: {context.fault_type}",
            "",
        ]
        
        # Add knowledge summary
        if knowledge.confidence > 0.5:
            parts.append(f"Knowledge confidence: {knowledge.confidence:.0%}")
            if knowledge.citations:
                parts.append(f"Referenced {len(knowledge.citations)} documents")
            if knowledge.similar_cases:
                parts.append(f"Found {len(knowledge.similar_cases)} similar past cases")
        
        # Add risk summary
        if plan.risk_factors:
            parts.append("")
            parts.append(f"Risk factors ({len(plan.risk_factors)}):")
            for factor in plan.risk_factors:
                parts.append(f"  - {factor}")
        
        # Add step summary
        parts.append("")
        parts.append(f"Steps: {len(plan.steps)}")
        approval_count = sum(1 for s in plan.steps if s.requires_approval)
        if approval_count:
            parts.append(f"Approvals required: {approval_count}")
        
        return "\n".join(parts)
    
    def _generate_step_rationale(
        self,
        step: PlaybookStep,
        context: PlannerContext,
        knowledge: KnowledgeResult,
    ) -> str:
        """Generate rationale for a single step"""
        rationale = step.description or f"Execute {step.type.value}"
        
        # Add context from similar cases
        if knowledge.similar_cases:
            for case in knowledge.similar_cases[:1]:
                if case.get("resolution_action"):
                    rationale += f" (similar to previous resolution: {case['resolution_action'][:50]})"
                    break
        
        return rationale
    
    def _estimate_duration(self, plan: ExecutionPlan) -> int:
        """Estimate total execution duration in seconds"""
        duration = 0
        
        for step in plan.steps:
            step_type = step.original_step.type.value
            
            # Base durations by type
            durations = {
                "READ": 5,
                "WRITE_POINT": 10,
                "CREATE_TICKET": 15,
                "UPDATE_TICKET": 10,
                "NOTIFY": 5,
                "WAIT": step.resolved_params.get("duration_seconds", 60),
                "COMPUTE": 2,
                "RUN_TEST": 30,
                "ESCALATE": 5,
            }
            
            duration += durations.get(step_type, 10)
            
            # Add approval wait time estimate
            if step.requires_approval:
                duration += 300  # 5 minute estimate
        
        return duration

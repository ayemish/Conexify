"""
LLM Explainer Service

Generates natural language explanations for workflow items to help
human reviewers understand what's happening and why.
"""

import logging
import json
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .models import (
    QueueItem,
    LLMExplanation,
    RiskAssessment,
    RiskLevel,
)

logger = logging.getLogger(__name__)


# Prompt templates for explanation generation
EXPLANATION_SYSTEM_PROMPT = """You are an expert building operations assistant that explains
automated remediation actions to facility managers and technicians.

Your role is to:
1. Clearly explain what triggered this workflow
2. Describe what actions will be taken
3. Explain why this approach is recommended
4. Assess risks and expected outcomes
5. Provide relevant context from similar past cases

Always be clear, concise, and actionable. Use technical terms appropriately
but explain them when needed. Focus on helping the reviewer make an informed decision."""


EXPLANATION_USER_PROMPT = """Please generate an explanation for the following workflow item
that requires human approval:

## Asset Information
- Asset ID: {asset_id}
- Site: {site_id}
- Type: {item_type}
- Risk Tier: {risk_tier}

## Fault Context
{fault_context}

## Current Telemetry
{telemetry}

## Proposed Actions
{proposed_actions}

## Evidence
{evidence}

Please provide:
1. A clear title summarizing this workflow
2. A brief summary (2-3 sentences)
3. What happened to trigger this workflow
4. What actions will be taken if approved
5. Why this approach is recommended
6. Expected outcome if actions succeed
7. Risk assessment with factors and mitigations
8. Any uncertainty factors

Format your response as JSON with these fields:
- title
- summary
- what_happened
- what_will_happen
- why_recommended
- expected_outcome
- risk_level (low/medium/high/critical)
- risk_factors (list of strings)
- mitigations (list of strings)
- uncertainty_factors (list of strings)
- confidence (0-1)
"""


class LLMExplainerService:
    """
    Generates LLM-powered explanations for workflow queue items.
    
    Supports multiple LLM backends and caches explanations.
    """
    
    def __init__(
        self,
        llm_client: Callable = None,
        model_name: str = "gpt-4",
        cache_enabled: bool = True,
    ):
        self.llm_client = llm_client
        self.model_name = model_name
        self.cache_enabled = cache_enabled
        self._cache: Dict[str, LLMExplanation] = {}
    
    async def generate_explanation(
        self,
        item: QueueItem,
        include_similar_cases: bool = True,
        include_alternatives: bool = True,
    ) -> LLMExplanation:
        """
        Generate an LLM explanation for a queue item.
        
        Args:
            item: The queue item to explain
            include_similar_cases: Whether to find and include similar past cases
            include_alternatives: Whether to suggest alternative approaches
            
        Returns:
            LLMExplanation with natural language explanation
        """
        start_time = datetime.utcnow()
        
        # Check cache
        cache_key = f"{item.item_id}:{item.updated_at.isoformat()}"
        if self.cache_enabled and cache_key in self._cache:
            logger.debug(f"Cache hit for explanation {item.item_id}")
            return self._cache[cache_key]
        
        try:
            # Build prompt
            prompt = self._build_prompt(item)
            
            # Call LLM (or use fallback if no client)
            if self.llm_client:
                response = await self._call_llm(prompt)
                explanation = self._parse_response(response, item)
            else:
                # Fallback: generate structured explanation without LLM
                explanation = self._generate_fallback_explanation(item)
            
            # Add similar cases if requested
            if include_similar_cases:
                explanation.similar_cases = await self._find_similar_cases(item)
            
            # Add alternatives if requested
            if include_alternatives:
                explanation.alternatives = self._generate_alternatives(item)
            
            # Set metadata
            explanation.model_used = self.model_name
            explanation.generated_at = datetime.utcnow()
            explanation.generation_time_ms = int(
                (datetime.utcnow() - start_time).total_seconds() * 1000
            )
            
            # Cache result
            if self.cache_enabled:
                self._cache[cache_key] = explanation
            
            logger.info(f"Generated explanation for {item.item_id}")
            return explanation
            
        except Exception as e:
            logger.error(f"Failed to generate explanation: {e}")
            raise
    
    def _build_prompt(self, item: QueueItem) -> str:
        """Build the prompt for explanation generation"""
        return EXPLANATION_USER_PROMPT.format(
            asset_id=item.asset_id,
            site_id=item.site_id,
            item_type=item.item_type,
            risk_tier=item.risk_tier,
            fault_context=json.dumps(item.fault_context, indent=2),
            telemetry=json.dumps(item.telemetry_snapshot, indent=2),
            proposed_actions=json.dumps(item.proposed_actions, indent=2),
            evidence=json.dumps(item.evidence, indent=2),
        )
    
    async def _call_llm(self, prompt: str) -> str:
        """Call the LLM with the prompt"""
        if not self.llm_client:
            raise ValueError("LLM client not configured")
        
        messages = [
            {"role": "system", "content": EXPLANATION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        
        response = await self.llm_client(
            model=self.model_name,
            messages=messages,
            temperature=0.3,
            max_tokens=1500,
        )
        
        return response
    
    def _parse_response(self, response: str, item: QueueItem) -> LLMExplanation:
        """Parse LLM response into structured explanation"""
        try:
            # Try to parse as JSON
            data = json.loads(response)
            
            risk_level = RiskLevel(data.get("risk_level", "medium"))
            
            risk_assessment = RiskAssessment(
                overall_risk=risk_level,
                risk_factors=data.get("risk_factors", []),
                mitigations=data.get("mitigations", []),
            )
            
            return LLMExplanation(
                title=data.get("title", "Workflow Approval Required"),
                summary=data.get("summary", ""),
                what_happened=data.get("what_happened", ""),
                what_will_happen=data.get("what_will_happen", ""),
                why_recommended=data.get("why_recommended", ""),
                expected_outcome=data.get("expected_outcome", ""),
                risk_assessment=risk_assessment,
                confidence=data.get("confidence", 0.7),
                uncertainty_factors=data.get("uncertainty_factors", []),
            )
            
        except json.JSONDecodeError:
            # Fallback: use response as summary
            return LLMExplanation(
                title="Workflow Approval Required",
                summary=response[:500],
                what_happened=f"Fault detected on asset {item.asset_id}",
                what_will_happen=item.action_summary,
            )
    
    def _generate_fallback_explanation(self, item: QueueItem) -> LLMExplanation:
        """Generate explanation without LLM (rule-based fallback)"""
        # Determine risk level
        risk_level = RiskLevel.MEDIUM
        if item.risk_tier == "HIGH":
            risk_level = RiskLevel.HIGH
        elif item.risk_tier == "LOW":
            risk_level = RiskLevel.LOW
        elif item.risk_tier == "EXTREME":
            risk_level = RiskLevel.CRITICAL
        
        # Build risk factors based on item
        risk_factors = []
        mitigations = []
        
        if item.risk_tier in ("HIGH", "EXTREME"):
            risk_factors.append("High-risk tier requiring careful review")
            mitigations.append("Manual verification step included")
        
        for action in item.proposed_actions:
            action_type = action.get("type", "")
            if action_type == "WRITE_POINT":
                risk_factors.append("Direct control point modification")
                mitigations.append("TTL-based auto-revert configured")
            elif action_type == "EMERGENCY_SHUTDOWN":
                risk_factors.append("Equipment shutdown action")
                mitigations.append("Restart procedure documented")
        
        # Build explanation text
        fault_type = item.fault_context.get("fault_type", "issue")
        
        what_happened = f"The system detected a {fault_type} condition on asset {item.asset_id}."
        if item.fault_context.get("severity"):
            what_happened += f" Severity: {item.fault_context['severity']}."
        
        what_will_happen = item.action_summary or "The proposed actions will address the detected condition."
        if item.proposed_actions:
            actions_desc = []
            for action in item.proposed_actions:
                action_type = action.get("type", "action")
                target = action.get("target", action.get("point_id", ""))
                if target:
                    actions_desc.append(f"{action_type} on {target}")
                else:
                    actions_desc.append(action_type)
            what_will_happen = f"Actions: {', '.join(actions_desc)}"
        
        why_recommended = "This action is recommended based on the playbook configuration and current system state."
        expected_outcome = "The detected condition should be resolved or mitigated."
        
        # Build key evidence
        key_evidence = []
        for key, value in item.telemetry_snapshot.items():
            if isinstance(value, (int, float)):
                key_evidence.append({"point": key, "value": value})
        
        return LLMExplanation(
            title=f"{fault_type.replace('_', ' ').title()} - Action Required",
            summary=f"Automated response to {fault_type} detected on {item.asset_id}. "
                    f"Risk tier: {item.risk_tier}. {len(item.proposed_actions)} actions proposed.",
            what_happened=what_happened,
            what_will_happen=what_will_happen,
            why_recommended=why_recommended,
            expected_outcome=expected_outcome,
            risk_assessment=RiskAssessment(
                overall_risk=risk_level,
                risk_factors=risk_factors,
                mitigations=mitigations,
            ),
            key_evidence=key_evidence[:5],  # Top 5
            confidence=0.7,
        )
    
    async def _find_similar_cases(self, item: QueueItem) -> List[Dict[str, Any]]:
        """Find similar past cases for context"""
        # This would query historical data
        # For now, return placeholder structure
        return []
    
    def _generate_alternatives(self, item: QueueItem) -> List[Dict[str, Any]]:
        """Generate alternative approaches"""
        alternatives = []
        
        # Always offer manual investigation as alternative
        alternatives.append({
            "name": "Manual Investigation",
            "description": "Reject automated action and investigate manually",
            "pros": ["Full control", "Can gather more context"],
            "cons": ["Slower response", "Requires technician availability"],
        })
        
        # For non-critical items, offer deferral
        if item.risk_tier not in ("HIGH", "EXTREME"):
            alternatives.append({
                "name": "Defer Decision",
                "description": "Delay decision pending more data or different conditions",
                "pros": ["More data collection", "Reduced false positive risk"],
                "cons": ["Delayed remediation", "Condition may worsen"],
            })
        
        return alternatives
    
    def invalidate_cache(self, item_id: str = None):
        """Invalidate cached explanations"""
        if item_id:
            keys_to_remove = [k for k in self._cache if k.startswith(item_id)]
            for key in keys_to_remove:
                del self._cache[key]
        else:
            self._cache.clear()

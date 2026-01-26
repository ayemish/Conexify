"""
Governance / Policy Agent

Responsibilities:
- Enforces business rules (min spend, retailer commitments, brand protections, policy guardrails)
- Blocks recommendations when confidence thresholds fail
- Produces a structured explanation + evidence pack for decision-makers

Business value: makes "autonomy" enterprise-acceptable.
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
import logging

from .base import (
    BaseIQueueAgent, AgentConfig, AgentType, BeliefState,
    AgentMessage, MessageType, ConfidenceLevel, AgentMessageBus
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PolicyType(str, Enum):
    """Types of governance policies"""
    MIN_SPEND = "min_spend"
    MAX_SPEND = "max_spend"
    RETAILER_COMMITMENT = "retailer_commitment"
    BRAND_PROTECTION = "brand_protection"
    RISK_LIMIT = "risk_limit"
    CONFIDENCE_THRESHOLD = "confidence_threshold"
    APPROVAL_REQUIRED = "approval_required"


class DecisionStatus(str, Enum):
    """Status of governance decision"""
    APPROVED = "approved"
    BLOCKED = "blocked"
    REQUIRES_REVIEW = "requires_review"
    ESCALATED = "escalated"


@dataclass
class GovernancePolicy:
    """A governance policy rule"""
    policy_id: str
    policy_type: PolicyType
    name: str
    description: str
    
    # Rule parameters
    driver: Optional[str] = None
    threshold: float = 0.0
    operator: str = ">="  # >=, <=, ==, !=
    
    # Enforcement
    is_hard: bool = True  # Hard = must satisfy, Soft = warning only
    violation_action: str = "block"  # block, warn, escalate
    
    # Context
    applicable_retailers: Optional[List[str]] = None
    applicable_segments: Optional[List[str]] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    
    def evaluate(self, value: float) -> bool:
        """Evaluate if policy is satisfied"""
        if self.operator == ">=":
            return value >= self.threshold
        elif self.operator == "<=":
            return value <= self.threshold
        elif self.operator == "==":
            return abs(value - self.threshold) < 0.01
        elif self.operator == "!=":
            return abs(value - self.threshold) >= 0.01
        elif self.operator == ">":
            return value > self.threshold
        elif self.operator == "<":
            return value < self.threshold
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'policy_id': self.policy_id,
            'policy_type': self.policy_type.value,
            'name': self.name,
            'description': self.description,
            'driver': self.driver,
            'threshold': self.threshold,
            'operator': self.operator,
            'is_hard': self.is_hard,
            'violation_action': self.violation_action
        }


@dataclass
class PolicyViolation:
    """Record of a policy violation"""
    policy: GovernancePolicy
    actual_value: float
    expected_value: float
    severity: str  # low, medium, high, critical
    recommendation: str


@dataclass
class DecisionPackage:
    """Structured decision package for decision-makers"""
    package_id: str
    timestamp: datetime
    
    # Decision
    recommendation: Dict[str, Any]
    decision_status: DecisionStatus
    
    # Governance checks
    policies_checked: List[str]
    policies_passed: List[str]
    policies_failed: List[str]
    violations: List[PolicyViolation]
    
    # Confidence
    overall_confidence: float
    confidence_breakdown: Dict[str, float]
    confidence_threshold: float
    confidence_passed: bool
    
    # Evidence
    evidence: Dict[str, Any]
    rationale: List[str]
    
    # Action required
    requires_human_approval: bool
    approval_level: str  # manager, director, executive
    escalation_reason: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'package_id': self.package_id,
            'timestamp': self.timestamp.isoformat(),
            'recommendation': self.recommendation,
            'decision_status': self.decision_status.value,
            'policies_checked': self.policies_checked,
            'policies_passed': self.policies_passed,
            'policies_failed': self.policies_failed,
            'violations': [
                {
                    'policy': v.policy.name,
                    'actual': v.actual_value,
                    'expected': v.expected_value,
                    'severity': v.severity,
                    'recommendation': v.recommendation
                }
                for v in self.violations
            ],
            'overall_confidence': self.overall_confidence,
            'confidence_breakdown': self.confidence_breakdown,
            'confidence_passed': self.confidence_passed,
            'evidence': self.evidence,
            'rationale': self.rationale,
            'requires_human_approval': self.requires_human_approval,
            'approval_level': self.approval_level,
            'escalation_reason': self.escalation_reason
        }


class GovernanceAgent(BaseIQueueAgent):
    """
    Governance / Policy Agent
    
    Enforces business rules and policy guardrails:
    - Minimum/maximum spend constraints
    - Retailer commitments
    - Brand protection rules
    - Risk limits
    - Confidence thresholds
    
    Produces structured explanation and evidence pack for decision-makers.
    """
    
    def __init__(
        self,
        config: AgentConfig,
        message_bus: Optional[AgentMessageBus] = None,
        policies: Optional[List[GovernancePolicy]] = None
    ):
        self.policies: Dict[str, GovernancePolicy] = {}
        self.decision_history: List[DecisionPackage] = []
        self.default_confidence_threshold = 0.7
        
        super().__init__(config, message_bus)
        
        # Initialize policies
        if policies:
            for policy in policies:
                self.policies[policy.policy_id] = policy
        else:
            self._initialize_default_policies()
    
    def _initialize_default_policies(self):
        """Initialize default governance policies"""
        default_policies = [
            GovernancePolicy(
                policy_id="conf_threshold",
                policy_type=PolicyType.CONFIDENCE_THRESHOLD,
                name="Minimum Confidence",
                description="Recommendations must meet confidence threshold",
                threshold=0.7,
                operator=">=",
                is_hard=True,
                violation_action="block"
            ),
            GovernancePolicy(
                policy_id="risk_limit",
                policy_type=PolicyType.RISK_LIMIT,
                name="Downside Risk Limit",
                description="Probability of negative ROI must be below threshold",
                threshold=0.2,
                operator="<=",
                is_hard=True,
                violation_action="escalate"
            ),
            GovernancePolicy(
                policy_id="budget_limit",
                policy_type=PolicyType.MAX_SPEND,
                name="Budget Limit",
                description="Total spend must not exceed budget",
                threshold=float('inf'),  # Set dynamically
                operator="<=",
                is_hard=True,
                violation_action="block"
            )
        ]
        
        for policy in default_policies:
            self.policies[policy.policy_id] = policy
    
    def _initialize_beliefs(self):
        """Initialize beliefs about governance effectiveness"""
        # Belief about policy effectiveness
        self.beliefs['policy_effectiveness'] = BeliefState(
            name='policy_effectiveness',
            mean=0.85,
            variance=0.01,
            confidence=0.6,
            source='prior'
        )
        
        # Belief about decision quality
        self.beliefs['decision_quality'] = BeliefState(
            name='decision_quality',
            mean=0.8,
            variance=0.02,
            confidence=0.5,
            source='prior'
        )
    
    def _subscribe_to_messages(self):
        """Subscribe to governance-related messages"""
        self.message_bus.subscribe(
            MessageType.OPTIMIZATION_RESULT,
            self._handle_optimization_result
        )
        
        self.message_bus.subscribe(
            MessageType.GOVERNANCE_CHECK,
            self._handle_governance_check
        )
    
    def _handle_optimization_result(self, message: AgentMessage):
        """Automatically validate optimization results"""
        payload = message.payload
        
        # Create governance check request
        check_request = {
            'recommendation': payload,
            'source': 'optimization_agent',
            'auto_check': True
        }
        
        # Process governance check
        result = self.process(check_request)
        
        # Publish decision
        self.message_bus.publish(AgentMessage(
            message_id=self._generate_id(),
            message_type=MessageType.GOVERNANCE_DECISION,
            sender_id=self.config.agent_id,
            recipient_id=message.sender_id,
            payload=result
        ))
    
    def _handle_governance_check(self, message: AgentMessage):
        """Handle explicit governance check requests"""
        result = self.process(message.payload)
        
        self.message_bus.publish(AgentMessage(
            message_id=self._generate_id(),
            message_type=MessageType.GOVERNANCE_DECISION,
            sender_id=self.config.agent_id,
            recipient_id=message.sender_id,
            payload=result,
            requires_response=False
        ))
    
    def process(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process governance check request.
        
        Args:
            inputs: Dict containing:
                - recommendation: The recommendation to validate
                - confidence_sources: Dict of confidence scores by source
                - evidence: Supporting evidence
                - context: Business context (retailer, segment, etc.)
        """
        recommendation = inputs.get('recommendation', {})
        confidence_sources = inputs.get('confidence_sources', {})
        evidence = inputs.get('evidence', {})
        context = inputs.get('context', {})
        
        # Extract allocations from recommendation
        allocations = recommendation.get('allocations', {})
        
        # Check all policies
        violations = []
        policies_passed = []
        policies_failed = []
        
        for policy_id, policy in self.policies.items():
            passed, violation = self._check_policy(policy, recommendation, allocations, context)
            
            if passed:
                policies_passed.append(policy_id)
            else:
                policies_failed.append(policy_id)
                if violation:
                    violations.append(violation)
        
        # Compute overall confidence
        overall_confidence, confidence_breakdown = self._compute_confidence(
            recommendation, confidence_sources
        )
        
        confidence_threshold = self.default_confidence_threshold
        confidence_passed = overall_confidence >= confidence_threshold
        
        # Determine decision status
        decision_status = self._determine_status(
            policies_failed, violations, confidence_passed
        )
        
        # Generate rationale
        rationale = self._generate_rationale(
            recommendation, violations, overall_confidence, decision_status
        )
        
        # Determine approval requirements
        requires_approval, approval_level, escalation_reason = self._determine_approval(
            decision_status, violations, overall_confidence
        )
        
        # Create decision package
        package = DecisionPackage(
            package_id=self._generate_id(),
            timestamp=datetime.utcnow(),
            recommendation=recommendation,
            decision_status=decision_status,
            policies_checked=list(self.policies.keys()),
            policies_passed=policies_passed,
            policies_failed=policies_failed,
            violations=violations,
            overall_confidence=overall_confidence,
            confidence_breakdown=confidence_breakdown,
            confidence_threshold=confidence_threshold,
            confidence_passed=confidence_passed,
            evidence=evidence,
            rationale=rationale,
            requires_human_approval=requires_approval,
            approval_level=approval_level,
            escalation_reason=escalation_reason
        )
        
        # Store history
        self.decision_history.append(package)
        
        self.last_update = datetime.utcnow()
        self.update_count += 1
        
        return package.to_dict()
    
    def _check_policy(
        self,
        policy: GovernancePolicy,
        recommendation: Dict[str, Any],
        allocations: Dict[str, float],
        context: Dict[str, Any]
    ) -> Tuple[bool, Optional[PolicyViolation]]:
        """Check if a policy is satisfied"""
        # Check applicability
        if policy.applicable_retailers:
            retailer = context.get('retailer_id')
            if retailer and retailer not in policy.applicable_retailers:
                return True, None  # Not applicable
        
        # Get value to check
        if policy.driver:
            value = allocations.get(policy.driver, 0)
        elif policy.policy_type == PolicyType.CONFIDENCE_THRESHOLD:
            value = recommendation.get('confidence', 0)
        elif policy.policy_type == PolicyType.RISK_LIMIT:
            value = recommendation.get('downside_probability', 0)
        elif policy.policy_type == PolicyType.MAX_SPEND:
            value = sum(allocations.values())
        elif policy.policy_type == PolicyType.MIN_SPEND:
            value = sum(allocations.values())
        else:
            value = 0
        
        # Evaluate
        passed = policy.evaluate(value)
        
        if passed:
            return True, None
        else:
            severity = self._assess_violation_severity(policy, value)
            recommendation_text = self._generate_violation_recommendation(policy, value)
            
            return False, PolicyViolation(
                policy=policy,
                actual_value=value,
                expected_value=policy.threshold,
                severity=severity,
                recommendation=recommendation_text
            )
    
    def _assess_violation_severity(self, policy: GovernancePolicy, value: float) -> str:
        """Assess severity of policy violation"""
        if policy.threshold == 0:
            return "medium"
        
        deviation = abs(value - policy.threshold) / abs(policy.threshold)
        
        if deviation > 0.5:
            return "critical"
        elif deviation > 0.25:
            return "high"
        elif deviation > 0.1:
            return "medium"
        else:
            return "low"
    
    def _generate_violation_recommendation(
        self,
        policy: GovernancePolicy,
        value: float
    ) -> str:
        """Generate recommendation for addressing violation"""
        if policy.policy_type == PolicyType.MIN_SPEND:
            return f"Increase {policy.driver or 'total'} spend to meet minimum of {policy.threshold:.0f}"
        elif policy.policy_type == PolicyType.MAX_SPEND:
            return f"Reduce {policy.driver or 'total'} spend to stay within maximum of {policy.threshold:.0f}"
        elif policy.policy_type == PolicyType.CONFIDENCE_THRESHOLD:
            return "Gather more data or reduce recommendation scope to improve confidence"
        elif policy.policy_type == PolicyType.RISK_LIMIT:
            return "Adjust allocation to reduce downside risk exposure"
        else:
            return f"Address {policy.name} policy violation"
    
    def _compute_confidence(
        self,
        recommendation: Dict[str, Any],
        sources: Dict[str, float]
    ) -> Tuple[float, Dict[str, float]]:
        """Compute overall confidence from multiple sources"""
        breakdown = {}
        
        # Recommendation confidence
        breakdown['recommendation'] = recommendation.get('confidence', 0.5)
        
        # Add source confidences
        for source, conf in sources.items():
            breakdown[source] = conf
        
        # Default sources if not provided
        if 'data_quality' not in breakdown:
            breakdown['data_quality'] = 0.8
        if 'model' not in breakdown:
            breakdown['model'] = 0.7
        
        # Weighted average (equal weights)
        overall = np.mean(list(breakdown.values()))
        
        return overall, breakdown
    
    def _determine_status(
        self,
        policies_failed: List[str],
        violations: List[PolicyViolation],
        confidence_passed: bool
    ) -> DecisionStatus:
        """Determine overall decision status"""
        # Check for hard policy failures
        hard_failures = [v for v in violations if v.policy.is_hard]
        
        if hard_failures:
            # Check if any require escalation
            escalate = any(v.policy.violation_action == 'escalate' for v in hard_failures)
            if escalate:
                return DecisionStatus.ESCALATED
            return DecisionStatus.BLOCKED
        
        if not confidence_passed:
            return DecisionStatus.REQUIRES_REVIEW
        
        if violations:  # Soft violations only
            return DecisionStatus.REQUIRES_REVIEW
        
        return DecisionStatus.APPROVED
    
    def _generate_rationale(
        self,
        recommendation: Dict[str, Any],
        violations: List[PolicyViolation],
        confidence: float,
        status: DecisionStatus
    ) -> List[str]:
        """Generate human-readable rationale"""
        rationale = []
        
        # Status explanation
        if status == DecisionStatus.APPROVED:
            rationale.append(
                f"Recommendation approved with {confidence:.1%} confidence. "
                f"All governance policies satisfied."
            )
        elif status == DecisionStatus.BLOCKED:
            rationale.append(
                f"Recommendation blocked due to policy violations. "
                f"{len(violations)} issue(s) require resolution."
            )
        elif status == DecisionStatus.REQUIRES_REVIEW:
            rationale.append(
                f"Recommendation requires human review. "
                f"Confidence ({confidence:.1%}) or policy concerns noted."
            )
        elif status == DecisionStatus.ESCALATED:
            rationale.append(
                f"Recommendation escalated to senior leadership. "
                f"Critical policy violations detected."
            )
        
        # Violation details
        for v in violations:
            rationale.append(
                f"• {v.policy.name}: {v.recommendation} "
                f"(actual: {v.actual_value:.2f}, required: {v.policy.operator} {v.expected_value:.2f})"
            )
        
        # Positive aspects
        if recommendation.get('expected_roi', 0) > 0:
            roi = recommendation.get('expected_roi', 0)
            rationale.append(f"Expected ROI: {roi:.1%}")
        
        return rationale
    
    def _determine_approval(
        self,
        status: DecisionStatus,
        violations: List[PolicyViolation],
        confidence: float
    ) -> Tuple[bool, str, Optional[str]]:
        """Determine approval requirements"""
        if status == DecisionStatus.APPROVED:
            return False, "none", None
        
        if status == DecisionStatus.BLOCKED:
            return True, "manager", "Policy violations require manager review"
        
        if status == DecisionStatus.ESCALATED:
            return True, "executive", "Critical policy violations require executive approval"
        
        if status == DecisionStatus.REQUIRES_REVIEW:
            if confidence < 0.5:
                return True, "director", f"Low confidence ({confidence:.1%}) requires director approval"
            return True, "manager", "Review required for policy concerns"
        
        return False, "none", None
    
    def add_policy(self, policy: GovernancePolicy):
        """Add a governance policy"""
        self.policies[policy.policy_id] = policy
        logger.info(f"Added policy: {policy.name}")
    
    def remove_policy(self, policy_id: str):
        """Remove a governance policy"""
        if policy_id in self.policies:
            del self.policies[policy_id]
            logger.info(f"Removed policy: {policy_id}")
    
    def get_policy_summary(self) -> Dict[str, Any]:
        """Get summary of all policies"""
        return {
            'total_policies': len(self.policies),
            'policies': [p.to_dict() for p in self.policies.values()],
            'hard_policies': len([p for p in self.policies.values() if p.is_hard]),
            'soft_policies': len([p for p in self.policies.values() if not p.is_hard])
        }
    
    def _get_goal(self) -> str:
        return (
            "Enforce governance policies and business rules on all recommendations. "
            "Block or escalate recommendations that violate policies or lack confidence. "
            "Produce structured explanation and evidence packs for decision-makers."
        )
    
    def _get_backstory(self) -> str:
        return (
            "You are a governance expert ensuring that autonomous recommendations meet "
            "enterprise standards. You balance enabling automation with maintaining control. "
            "Your structured decision packages make AI recommendations enterprise-acceptable."
        )


def create_governance_agent(
    retailer_id: str,
    policies: Optional[List[GovernancePolicy]] = None,
    message_bus: Optional[AgentMessageBus] = None
) -> GovernanceAgent:
    """Factory function for creating Governance Agent"""
    config = AgentConfig(
        agent_id=f"governance_{retailer_id}",
        agent_type=AgentType.GOVERNANCE,
        retailer_id=retailer_id
    )
    
    return GovernanceAgent(config, message_bus, policies)

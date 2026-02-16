"""Guardian merge service for combining kernel output with agent advisories.

The guardian enforces monotonic safety:
- advisory layer can tighten decisions (downgrade/escalate/suppress),
- advisory layer cannot relax deterministic hard gates from the kernel.
"""

from dataclasses import dataclass
from typing import List, Optional

from ..core.decision_contracts import (
    AdvisoryAction,
    AgentAdvisory,
    FinalDisposition,
    GuardianDecision,
    KernelDecisionArtifact,
)
from ..core.schemas import AlertType


@dataclass
class GuardianPolicyConfig:
    """Thresholds for applying advisory actions."""

    escalate_conf_threshold: float = 0.75
    downgrade_conf_threshold: float = 0.70
    enrich_conf_threshold: float = 0.60


class GuardianMergeService:
    """Merge kernel artifact with advisories while preserving hard policy gates."""

    def __init__(self, config: Optional[GuardianPolicyConfig] = None):
        self.config = config or GuardianPolicyConfig()

    def merge(
        self,
        artifact: KernelDecisionArtifact,
        advisories: List[AgentAdvisory],
    ) -> GuardianDecision:
        reasons: List[str] = []
        advisories_used: List[str] = []
        recommended_action = artifact.base_recommended_action
        final_alert_type = artifact.base_alert_type

        failed_gates = [g for g in artifact.gates if not g.passed]
        if failed_gates:
            if final_alert_type == AlertType.ACTIONABLE:
                final_alert_type = AlertType.WATCH
            reasons.extend([f"{g.gate.value}: {g.reason}" for g in failed_gates])
            return GuardianDecision(
                disposition=FinalDisposition.AUTO_MONITOR,
                final_alert_type=final_alert_type,
                confidence=artifact.base_alert_confidence,
                false_alarm_probability=artifact.base_false_alarm_probability,
                recommended_action=recommended_action,
                reasons=reasons,
                advisories_used=advisories_used,
            )

        suppressors = [
            a
            for a in advisories
            if a.action == AdvisoryAction.SUPPRESS_FOR_DATA_QUALITY
            and a.confidence >= self.config.downgrade_conf_threshold
        ]
        if suppressors:
            advisories_used.extend([a.agent_id for a in suppressors])
            reasons.extend([f"{a.agent_id}: {a.rationale}" for a in suppressors])
            final_alert_type = (
                AlertType.SENSOR_INTEGRITY if artifact.untrusted_sensors else AlertType.WATCH
            )

        downgraders = [
            a
            for a in advisories
            if a.action == AdvisoryAction.DOWNGRADE_TO_WATCH
            and a.confidence >= self.config.downgrade_conf_threshold
        ]
        if downgraders:
            advisories_used.extend([a.agent_id for a in downgraders])
            reasons.extend([f"{a.agent_id}: {a.rationale}" for a in downgraders])
            if final_alert_type == AlertType.ACTIONABLE:
                final_alert_type = AlertType.WATCH

        escalators = [
            a
            for a in advisories
            if a.action == AdvisoryAction.ESCALATE_TO_HUMAN
            and a.confidence >= self.config.escalate_conf_threshold
        ]
        human_review_required = len(escalators) > 0
        if escalators:
            advisories_used.extend([a.agent_id for a in escalators])
            reasons.extend([f"{a.agent_id}: {a.rationale}" for a in escalators])

        enrichers = [
            a
            for a in advisories
            if a.action == AdvisoryAction.ENRICH_ACTION_PLAN
            and a.confidence >= self.config.enrich_conf_threshold
        ]
        if enrichers:
            advisories_used.extend([a.agent_id for a in enrichers])
            reasons.extend([f"{a.agent_id}: {a.rationale}" for a in enrichers])
            extras = [a.rationale for a in enrichers if a.rationale]
            if extras:
                recommended_action = f"{recommended_action} | Agent notes: {'; '.join(extras)}"

        # Monotonic rule: advisories cannot promote a non-actionable kernel alert.
        if artifact.base_alert_type != AlertType.ACTIONABLE and final_alert_type == AlertType.ACTIONABLE:
            final_alert_type = artifact.base_alert_type

        if human_review_required:
            disposition = FinalDisposition.HUMAN_REVIEW_REQUIRED
        elif final_alert_type == AlertType.ACTIONABLE:
            disposition = FinalDisposition.AUTO_ACTIONABLE
        else:
            disposition = FinalDisposition.AUTO_MONITOR

        if not reasons:
            reasons.append("No advisory overrides applied")

        return GuardianDecision(
            disposition=disposition,
            final_alert_type=final_alert_type,
            confidence=artifact.base_alert_confidence,
            false_alarm_probability=artifact.base_false_alarm_probability,
            recommended_action=recommended_action,
            reasons=reasons,
            advisories_used=advisories_used,
        )

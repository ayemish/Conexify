import sys
import pathlib
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from predictive_maintenance.core.decision_contracts import (
    AdvisoryAction,
    AgentAdvisory,
    FinalDisposition,
    GateEvaluation,
    HardGate,
    HypothesisSnapshot,
    KernelDecisionArtifact,
)
from predictive_maintenance.core.schemas import AlertType, FaultType, OperatingRegime
from predictive_maintenance.services.guardian_merge_service import GuardianMergeService


def _artifact(
    base_alert: AlertType = AlertType.ACTIONABLE,
    gate_pass: bool = True,
) -> KernelDecisionArtifact:
    return KernelDecisionArtifact(
        artifact_id="artifact-1",
        asset_id="asset-1",
        site_id="site-1",
        timestamp=datetime.utcnow(),
        regime=OperatingRegime.STEADY_COOL,
        is_steady_state=True,
        trust_scores={"s1": 0.95},
        untrusted_sensors=[],
        change_scores={"s1": 0.8},
        change_detected={"s1": True},
        change_duration_hours={"s1": 8.0},
        joint_change_detected=True,
        joint_change_score=0.7,
        hypothesis=HypothesisSnapshot(
            top_fault=FaultType.REFRIGERANT_LEAK,
            top_probability=0.9,
            is_concentrated=True,
            beliefs={FaultType.REFRIGERANT_LEAK.value: 0.9},
        ),
        base_alert_type=base_alert,
        base_alert_confidence=0.9,
        base_false_alarm_probability=0.02,
        base_recommended_action="Inspect refrigerant circuit",
        gates=[
            GateEvaluation(
                gate=HardGate.SENSOR_TRUST,
                passed=gate_pass,
                reason="ok" if gate_pass else "low trust",
                metric=0.95 if gate_pass else 0.3,
                threshold=0.5,
            )
        ],
        context={},
    )


def test_guardian_hard_gate_failure_prevents_actionable():
    guardian = GuardianMergeService()
    artifact = _artifact(base_alert=AlertType.ACTIONABLE, gate_pass=False)

    decision = guardian.merge(artifact, advisories=[])

    assert decision.final_alert_type == AlertType.WATCH
    assert decision.disposition == FinalDisposition.AUTO_MONITOR


def test_guardian_escalation_requires_human_review():
    guardian = GuardianMergeService()
    artifact = _artifact(base_alert=AlertType.ACTIONABLE, gate_pass=True)
    advisory = AgentAdvisory(
        agent_id="agent-risk",
        agent_role="risk",
        action=AdvisoryAction.ESCALATE_TO_HUMAN,
        confidence=0.9,
        rationale="Potential safety impact requires human review",
    )

    decision = guardian.merge(artifact, advisories=[advisory])

    assert decision.final_alert_type == AlertType.ACTIONABLE
    assert decision.disposition == FinalDisposition.HUMAN_REVIEW_REQUIRED
    assert "agent-risk" in decision.advisories_used


def test_guardian_suppress_data_quality_downgrades():
    guardian = GuardianMergeService()
    artifact = _artifact(base_alert=AlertType.ACTIONABLE, gate_pass=True)
    advisory = AgentAdvisory(
        agent_id="agent-dq",
        agent_role="data_quality",
        action=AdvisoryAction.SUPPRESS_FOR_DATA_QUALITY,
        confidence=0.85,
        rationale="Conflicting telemetry stream quality",
    )

    decision = guardian.merge(artifact, advisories=[advisory])

    assert decision.final_alert_type == AlertType.WATCH
    assert decision.disposition == FinalDisposition.AUTO_MONITOR


def test_guardian_enrichment_appends_recommendation():
    guardian = GuardianMergeService()
    artifact = _artifact(base_alert=AlertType.ACTIONABLE, gate_pass=True)
    advisory = AgentAdvisory(
        agent_id="agent-plan",
        agent_role="planner",
        action=AdvisoryAction.ENRICH_ACTION_PLAN,
        confidence=0.7,
        rationale="Bring manifold gauges and leak detector",
    )

    decision = guardian.merge(artifact, advisories=[advisory])

    assert decision.disposition == FinalDisposition.AUTO_ACTIONABLE
    assert "Agent notes:" in decision.recommended_action

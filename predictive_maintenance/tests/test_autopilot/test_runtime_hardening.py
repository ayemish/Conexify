import os
from datetime import datetime

import pytest

from predictive_maintenance.autopilot.orchestrator.approval import ApprovalManager, ApprovalRequest
from predictive_maintenance.autopilot.orchestrator.runtime import OrchestrationRuntime, RunContext
from predictive_maintenance.autopilot.playbook.schema import (
    OnErrorAction,
    PlaybookDefinition,
    PlaybookStep,
    StepType,
)
from predictive_maintenance.autopilot.schemas import EvidencePack, RiskTier
from predictive_maintenance.autopilot.verification.evidence import EvidencePackExporter


class _DummySession:
    def close(self):
        return None


def _session_factory():
    return _DummySession()


def _minimal_playbook() -> PlaybookDefinition:
    return PlaybookDefinition(
        id="pb-retry",
        version="1.0.0",
        name="Retry Test",
        asset_class="HVAC",
        fault_type="fault",
        steps=[],
    )


def test_runtime_retry_executes_bounded_retries(monkeypatch):
    runtime = OrchestrationRuntime(_session_factory, connectors={})
    monkeypatch.setattr(runtime, "_update_run_status", lambda *args, **kwargs: None)

    context = RunContext(
        run_id="RUN-RETRY-1",
        thread_id="thread-1",
        tenant_id="tenant",
        site_id="site-1",
        asset_id="asset-1",
        playbook=_minimal_playbook(),
    )
    step = PlaybookStep(
        id="step-retry",
        type=StepType.READ,
        on_error=OnErrorAction.RETRY,
        max_retries=2,
        params={"retry_backoff_seconds": 0.01},
    )

    assert runtime._handle_step_error(context, step, "boom-1") is None
    assert runtime._handle_step_error(context, step, "boom-2") is None
    outcome = runtime._handle_step_error(context, step, "boom-3")
    assert outcome is not None
    assert outcome[0] == "FAILED"
    retry_audits = [a for a in context.actions_taken if a.get("action_type") == "RETRY_STEP"]
    assert len(retry_audits) == 2


def test_approval_notification_dispatch_invoked():
    sent = {"count": 0, "approval_id": None}

    class _Connector:
        def send_approval_request(self, **kwargs):
            sent["count"] += 1
            sent["approval_id"] = kwargs.get("approval_id")

            class _Resp:
                success = True

            return _Resp()

    manager = ApprovalManager(
        _session_factory,
        notification_connector=_Connector(),
        dev_mode=False,
    )
    request = ApprovalRequest(
        run_id="RUN-123",
        step_id="step-1",
        tenant_id="tenant-a",
        approval_type="step",
        risk_tier=RiskTier.MEDIUM,
        proposed_actions=[{"type": "WRITE_POINT"}],
        rationale="Need approval",
    )
    manager._notify_approvers(request, "APR-123")

    assert sent["count"] == 1
    assert sent["approval_id"] == "APR-123"


@pytest.mark.optional_export
def test_evidence_exporter_outputs_pdf_bytes(monkeypatch):
    pytest.importorskip("reportlab")
    monkeypatch.setenv("PDM_ENVIRONMENT", "production")
    monkeypatch.delenv("PDM_DEV_MODE", raising=False)

    exporter = EvidencePackExporter()
    pack = EvidencePack(
        pack_id="EVD-TEST-001",
        run_id="RUN-001",
        incident_id="INC-001",
        tenant_id="tenant",
        site_id="site",
        asset_id="asset",
        playbook_id="pb",
        playbook_version="1.0.0",
        incident_start=datetime.utcnow(),
        run_start=datetime.utcnow(),
        run_end=datetime.utcnow(),
        outcome="RESOLVED",
        outcome_reason="ok",
    )
    pdf = exporter.to_pdf(pack)
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF")

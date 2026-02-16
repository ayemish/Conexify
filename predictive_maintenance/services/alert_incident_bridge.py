"""
Alert → Incident Bridge

Automatically converts actionable PDM alerts into autopilot incidents,
closing the gap between detection and remediation.

The bridge:
1. Receives PDMAlert from the kernel or orchestrator
2. Deduplicates against open incidents
3. Creates an autopilot Incident record
4. Optionally auto-matches a playbook and creates a Run
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from ..core.schemas import AlertType, FaultType, PDMAlert

logger = logging.getLogger(__name__)


class AlertIncidentBridge:
    """Bridges PDM alerts into the autopilot incident/run pipeline."""

    def __init__(
        self,
        session_factory: Optional[Callable] = None,
        tenant_id: str = "default",
        auto_create_run: bool = True,
    ):
        self.session_factory = session_factory
        self.tenant_id = tenant_id
        self.auto_create_run = auto_create_run

    def process_alert(
        self,
        alert: PDMAlert,
        site_id: Optional[str] = None,
        telemetry_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Convert an actionable PDM alert into an autopilot incident.

        Returns a dict with ``incident_id`` (and ``run_id`` if a run was
        auto-created), or *None* when the alert does not warrant an incident.
        """
        if alert.alert_type not in (AlertType.ACTIONABLE, AlertType.SENSOR_INTEGRITY):
            return None

        if self.session_factory is None:
            logger.debug("AlertIncidentBridge: no session_factory, skipping DB write")
            return self._build_in_memory_result(alert, site_id)

        from ..autopilot.repositories import (
            IncidentRepository,
            AutopilotRunRepository,
            PlaybookRepository,
        )

        result: Dict[str, Any] = {}

        with self.session_factory() as session:
            inc_repo = IncidentRepository(session)

            fault_type_str = alert.primary_fault.value if alert.primary_fault else "unknown"
            start_ts = getattr(alert, "created_at", None) or datetime.utcnow()
            effective_site = site_id or getattr(alert, "site_id", "default")

            # Deduplication
            existing = inc_repo.find_duplicate(
                asset_id=alert.asset_id,
                fault_type=fault_type_str,
                start_ts=start_ts,
            )
            if existing:
                result["incident_id"] = existing.incident_id
                result["duplicate"] = True
                return result

            incident_id = f"INC-{uuid.uuid4().hex[:12].upper()}"
            trigger_evidence = {
                "alert_id": alert.alert_id,
                "alert_type": alert.alert_type.value,
                "confidence": alert.confidence,
                "false_alarm_probability": alert.false_alarm_probability,
                "fault_beliefs": {
                    (ft.value if hasattr(ft, "value") else str(ft)): prob
                    for ft, prob in (alert.fault_beliefs or {}).items()
                } if getattr(alert, "fault_beliefs", None) else {},
            }
            if telemetry_snapshot:
                trigger_evidence["telemetry"] = telemetry_snapshot

            severity = self._map_severity(alert)

            inc_repo.create(
                incident_id=incident_id,
                tenant_id=self.tenant_id,
                site_id=effective_site,
                asset_id=alert.asset_id,
                fault_type=fault_type_str,
                severity=severity,
                source="pdm_kernel",
                start_ts=start_ts,
                trigger_evidence=trigger_evidence,
            )
            result["incident_id"] = incident_id
            result["duplicate"] = False

            # Auto-match playbook and create run
            if self.auto_create_run:
                run_info = self._try_create_run(
                    session, incident_id, fault_type_str,
                    effective_site, alert.asset_id,
                )
                if run_info:
                    result.update(run_info)

            session.commit()

        logger.info(
            "AlertIncidentBridge: alert %s → incident %s (dup=%s)",
            alert.alert_id, result.get("incident_id"), result.get("duplicate"),
        )
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _try_create_run(
        self,
        session,
        incident_id: str,
        fault_type: str,
        site_id: str,
        asset_id: str,
    ) -> Optional[Dict[str, Any]]:
        from ..autopilot.repositories import (
            AutopilotRunRepository,
            PlaybookRepository,
            IncidentRepository,
        )

        pb_repo = PlaybookRepository(session)
        playbooks = pb_repo.list_active(fault_type=fault_type)
        if not playbooks:
            return None

        playbook = playbooks[0]

        inc_repo = IncidentRepository(session)
        inc_repo.set_matched_playbook(
            incident_id=incident_id,
            playbook_id=playbook.playbook_id,
            match_reason=f"Auto-matched by fault_type={fault_type}",
        )

        run_repo = AutopilotRunRepository(session)
        run_id = f"RUN-{uuid.uuid4().hex[:12].upper()}"
        thread_id = str(uuid.uuid4())

        run_repo.create(
            run_id=run_id,
            incident_id=incident_id,
            playbook_id=playbook.playbook_id,
            playbook_version=playbook.current_version,
            tenant_id=self.tenant_id,
            site_id=site_id,
            asset_id=asset_id,
            thread_id=thread_id,
            risk_tier=playbook.risk_tier,
            plan_rationale=f"Auto-created from incident {incident_id}",
        )
        return {"run_id": run_id, "playbook_id": playbook.playbook_id}

    @staticmethod
    def _map_severity(alert: PDMAlert) -> str:
        if hasattr(alert, "severity") and alert.severity:
            return alert.severity.value if hasattr(alert.severity, "value") else str(alert.severity)
        if alert.confidence >= 0.9:
            return "critical"
        if alert.confidence >= 0.7:
            return "high"
        if alert.confidence >= 0.5:
            return "medium"
        return "low"

    @staticmethod
    def _build_in_memory_result(alert: PDMAlert, site_id: Optional[str]) -> Dict[str, Any]:
        return {
            "incident_id": f"INC-{uuid.uuid4().hex[:12].upper()}",
            "duplicate": False,
            "in_memory": True,
        }

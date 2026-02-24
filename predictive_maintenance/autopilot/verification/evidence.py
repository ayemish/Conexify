"""
Evidence Pack Generator

Generates immutable audit-grade artifacts documenting autopilot runs.
"""

import hashlib
import io
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional
import uuid

from sqlalchemy.orm import Session

from ..schemas import EvidencePack
from ..models import (
    EvidencePackModel,
    AutopilotRunModel,
    IncidentModel,
    RunActionModel,
    ApprovalModel,
    VerificationResultModel,
)

logger = logging.getLogger(__name__)


@dataclass
class TelemetryWindow:
    """Telemetry data for a time window"""
    start: datetime
    end: datetime
    points: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    summary: Dict[str, Dict[str, float]] = field(default_factory=dict)  # point -> {min, max, avg}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "points": self.points,
            "summary": self.summary,
        }


class EvidencePackGenerator:
    """
    Generates evidence packs for completed autopilot runs.
    
    An evidence pack includes:
    - Triggering telemetry window (before)
    - Action chain (who/what/when)
    - Verification results (after)
    - Outcome status
    """
    
    def __init__(self, session_factory: Callable[[], Session]):
        self.session_factory = session_factory
    
    def generate(
        self,
        run_id: str,
        before_window_seconds: int = 3600,
        after_window_seconds: int = 3600,
    ) -> EvidencePack:
        """
        Generate an evidence pack for a completed run.
        
        Args:
            run_id: Run ID
            before_window_seconds: Telemetry window before incident
            after_window_seconds: Telemetry window after actions
            
        Returns:
            EvidencePack
        """
        session = self.session_factory()
        try:
            # Get run
            run = session.query(AutopilotRunModel).filter(
                AutopilotRunModel.run_id == run_id
            ).first()
            
            if not run:
                raise ValueError(f"Run {run_id} not found")
            
            # Get incident
            incident = session.query(IncidentModel).filter(
                IncidentModel.incident_id == run.incident_id
            ).first()
            
            # Get actions
            actions = session.query(RunActionModel).filter(
                RunActionModel.run_id == run_id
            ).order_by(RunActionModel.executed_at).all()
            
            # Get approvals
            approvals = session.query(ApprovalModel).filter(
                ApprovalModel.run_id == run_id
            ).order_by(ApprovalModel.created_at).all()
            
            # Get verification results
            verifications = session.query(VerificationResultModel).filter(
                VerificationResultModel.run_id == run_id
            ).all()
            
            # Build evidence pack
            pack_id = f"EVD-{uuid.uuid4().hex[:12].upper()}"
            
            # Calculate windows
            incident_start = incident.start_ts if incident else run.created_at
            before_window_start = incident_start - timedelta(seconds=before_window_seconds)
            before_window_end = incident_start
            
            run_end = run.completed_at or datetime.utcnow()
            after_window_start = run_end
            after_window_end = run_end + timedelta(seconds=after_window_seconds)
            
            # Build telemetry windows (placeholder - would integrate with time-series DB)
            before_telemetry = self._build_telemetry_window(
                run.asset_id,
                before_window_start,
                before_window_end,
            )
            
            after_telemetry = self._build_telemetry_window(
                run.asset_id,
                after_window_start,
                after_window_end,
            )
            
            # Build action chain
            action_chain = [
                {
                    "action_id": a.action_id,
                    "step_id": a.step_id,
                    "action_type": a.action_type,
                    "target": a.target,
                    "point_id": a.point_id,
                    "value_before": a.value_before,
                    "value_after": a.value_after,
                    "executed_at": a.executed_at.isoformat() if a.executed_at else None,
                    "executed_by": a.executed_by,
                    "success": a.success,
                    "correlation_id": a.correlation_id,
                }
                for a in actions
            ]
            
            # Build approval chain
            approval_chain = [
                {
                    "approval_id": ap.approval_id,
                    "approval_type": ap.approval_type,
                    "risk_tier": ap.risk_tier,
                    "status": ap.status,
                    "decision": ap.decision,
                    "decided_by": ap.decided_by,
                    "decided_at": ap.decided_at.isoformat() if ap.decided_at else None,
                    "decision_notes": ap.decision_notes,
                }
                for ap in approvals
            ]
            
            # Build verification results
            verification_results = [
                {
                    "verification_id": v.verification_id,
                    "check_expression": v.check_expression,
                    "status": v.status,
                    "passed": v.passed,
                    "before_values": v.before_values,
                    "after_values": v.after_values,
                    "delta": v.delta,
                    "message": v.message,
                }
                for v in verifications
            ]
            
            # Create evidence pack
            pack = EvidencePack(
                pack_id=pack_id,
                run_id=run_id,
                incident_id=run.incident_id,
                tenant_id=run.tenant_id,
                site_id=run.site_id,
                asset_id=run.asset_id,
                playbook_id=run.playbook_id,
                playbook_version=run.playbook_version,
                incident_start=incident_start,
                run_start=run.started_at or run.created_at,
                run_end=run_end,
                before_telemetry_window=before_telemetry.to_dict() if before_telemetry else {},
                before_window_start=before_window_start,
                before_window_end=before_window_end,
                actions=action_chain,
                approvals=approval_chain,
                after_telemetry_window=after_telemetry.to_dict() if after_telemetry else {},
                after_window_start=after_window_start,
                after_window_end=after_window_end,
                verification_results=verification_results,
                outcome=run.outcome or "UNKNOWN",
                outcome_reason=run.outcome_reason or "",
            )
            
            # Compute content hash for immutability
            pack.content_hash = self._compute_hash(pack)
            
            # Persist evidence pack
            self._persist_pack(session, pack)
            session.commit()
            
            logger.info(f"Generated evidence pack {pack_id} for run {run_id}")
            
            return pack
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to generate evidence pack: {e}")
            raise
        finally:
            session.close()
    
    def _build_telemetry_window(
        self,
        asset_id: str,
        start: datetime,
        end: datetime,
    ) -> Optional[TelemetryWindow]:
        """Build telemetry window from persisted telemetry data."""
        try:
            from predictive_maintenance.persistence.models import TelemetryModel

            session = self.session_factory()
            try:
                rows = (
                    session.query(TelemetryModel)
                    .filter(
                        TelemetryModel.asset_id == asset_id,
                        TelemetryModel.timestamp >= start,
                        TelemetryModel.timestamp <= end,
                    )
                    .order_by(TelemetryModel.timestamp.asc())
                    .all()
                )
            finally:
                session.close()

            point_fields = [
                "compressor_current",
                "compressor_power",
                "suction_temp",
                "discharge_temp",
                "supply_air_temp",
                "return_air_temp",
                "ambient_temp",
                "zone_temp",
                "suction_pressure",
                "discharge_pressure",
                "superheat",
                "subcool",
                "setpoint",
                "cooling_valve_pct",
                "heating_valve_pct",
                "damper_position_pct",
            ]

            points: Dict[str, List[Dict[str, Any]]] = {}
            for row in rows:
                ts_iso = row.timestamp.isoformat() if row.timestamp else None
                for field_name in point_fields:
                    raw_value = getattr(row, field_name, None)
                    if raw_value is None:
                        continue
                    try:
                        value = float(raw_value)
                    except (TypeError, ValueError):
                        continue
                    points.setdefault(field_name, []).append(
                        {"timestamp": ts_iso, "value": value}
                    )

            summary: Dict[str, Dict[str, float]] = {}
            for field_name, values in points.items():
                nums = [v["value"] for v in values]
                if not nums:
                    continue
                summary[field_name] = {
                    "min": min(nums),
                    "max": max(nums),
                    "avg": sum(nums) / max(len(nums), 1),
                }

            return TelemetryWindow(
                start=start,
                end=end,
                points=points,
                summary=summary,
            )
        except Exception as exc:
            logger.warning(
                "Telemetry window retrieval failed for asset_id=%s window=(%s,%s): %s",
                asset_id,
                start.isoformat(),
                end.isoformat(),
                exc,
            )
            return TelemetryWindow(start=start, end=end, points={}, summary={})
    
    def _compute_hash(self, pack: EvidencePack) -> str:
        """Compute SHA-256 hash of pack content for immutability"""
        # Serialize pack deterministically
        data = pack.to_dict()
        data.pop("content_hash", None)  # Exclude hash from hash
        data.pop("signed_at", None)
        
        canonical = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()
    
    def _persist_pack(self, session: Session, pack: EvidencePack):
        """Persist evidence pack to database"""
        model = EvidencePackModel(
            pack_id=pack.pack_id,
            run_id=pack.run_id,
            incident_id=pack.incident_id,
            tenant_id=pack.tenant_id,
            site_id=pack.site_id,
            asset_id=pack.asset_id,
            playbook_id=pack.playbook_id,
            playbook_version=pack.playbook_version,
            incident_start=pack.incident_start,
            run_start=pack.run_start,
            run_end=pack.run_end,
            before_telemetry_window=pack.before_telemetry_window,
            before_window_start=pack.before_window_start,
            before_window_end=pack.before_window_end,
            actions=pack.actions,
            approvals=pack.approvals,
            after_telemetry_window=pack.after_telemetry_window,
            after_window_start=pack.after_window_start,
            after_window_end=pack.after_window_end,
            verification_results=pack.verification_results,
            outcome=pack.outcome,
            outcome_reason=pack.outcome_reason,
            content_hash=pack.content_hash,
        )
        session.add(model)
    
    def get_pack(self, pack_id: str) -> Optional[EvidencePack]:
        """Retrieve an evidence pack by ID"""
        session = self.session_factory()
        try:
            model = session.query(EvidencePackModel).filter(
                EvidencePackModel.pack_id == pack_id
            ).first()
            
            if not model:
                return None
            
            return EvidencePack(
                pack_id=model.pack_id,
                run_id=model.run_id,
                incident_id=model.incident_id,
                tenant_id=model.tenant_id,
                site_id=model.site_id,
                asset_id=model.asset_id,
                playbook_id=model.playbook_id,
                playbook_version=model.playbook_version,
                incident_start=model.incident_start,
                run_start=model.run_start,
                run_end=model.run_end,
                before_telemetry_window=model.before_telemetry_window or {},
                before_window_start=model.before_window_start,
                before_window_end=model.before_window_end,
                actions=model.actions or [],
                approvals=model.approvals or [],
                after_telemetry_window=model.after_telemetry_window or {},
                after_window_start=model.after_window_start,
                after_window_end=model.after_window_end,
                verification_results=model.verification_results or [],
                outcome=model.outcome,
                outcome_reason=model.outcome_reason,
                content_hash=model.content_hash,
                cmms_ticket_ids=model.cmms_ticket_ids or [],
            )
        finally:
            session.close()


class EvidencePackExporter:
    """
    Exports evidence packs to various formats.
    """
    
    def to_json(self, pack: EvidencePack) -> str:
        """Export evidence pack to JSON"""
        return json.dumps(pack.to_dict(), indent=2, default=str)
    
    def to_pdf(self, pack: EvidencePack, output_path: str = None) -> bytes:
        """
        Export evidence pack to PDF.
        
        Args:
            pack: Evidence pack to export
            output_path: Optional file path to write PDF
            
        Returns:
            PDF content as bytes
        """
        dev_mode = os.getenv("PDM_DEV_MODE", "").lower() in {"1", "true", "yes"}
        environment = os.getenv("PDM_ENVIRONMENT", "development").lower()
        allow_text_fallback = dev_mode or environment != "production"

        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas
        except Exception as exc:
            if not allow_text_fallback:
                raise RuntimeError(
                    "reportlab is required for evidence PDF export in non-dev environments"
                ) from exc
            logger.warning("reportlab unavailable; using dev text fallback for evidence export: %s", exc)
            pdf_bytes = self._build_pdf_content(pack).encode("utf-8")
            if output_path:
                with open(output_path, "wb") as f:
                    f.write(pdf_bytes)
            return pdf_bytes

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        x = 48
        y = height - 48

        lines = self._build_pdf_content(pack).splitlines()
        c.setFont("Helvetica", 10)
        for line in lines:
            if y < 48:
                c.showPage()
                c.setFont("Helvetica", 10)
                y = height - 48
            c.drawString(x, y, line[:160])
            y -= 14

        c.save()
        pdf_bytes = buffer.getvalue()
        if output_path:
            with open(output_path, "wb") as f:
                f.write(pdf_bytes)
        return pdf_bytes
    
    def _build_pdf_content(self, pack: EvidencePack) -> str:
        """Build PDF content as text (placeholder for actual PDF generation)"""
        lines = [
            "=" * 80,
            "EVIDENCE PACK",
            "=" * 80,
            "",
            f"Pack ID: {pack.pack_id}",
            f"Run ID: {pack.run_id}",
            f"Incident ID: {pack.incident_id}",
            f"Content Hash: {pack.content_hash}",
            "",
            "-" * 40,
            "IDENTIFIERS",
            "-" * 40,
            f"Tenant: {pack.tenant_id}",
            f"Site: {pack.site_id}",
            f"Asset: {pack.asset_id}",
            f"Playbook: {pack.playbook_id} v{pack.playbook_version}",
            "",
            "-" * 40,
            "TIMELINE",
            "-" * 40,
            f"Incident Start: {pack.incident_start}",
            f"Run Start: {pack.run_start}",
            f"Run End: {pack.run_end}",
            "",
            "-" * 40,
            "OUTCOME",
            "-" * 40,
            f"Status: {pack.outcome}",
            f"Reason: {pack.outcome_reason}",
            "",
            "-" * 40,
            "ACTIONS TAKEN",
            "-" * 40,
        ]
        
        for i, action in enumerate(pack.actions, 1):
            lines.append(f"{i}. {action.get('action_type', 'Unknown')}")
            lines.append(f"   Target: {action.get('target', 'N/A')}")
            lines.append(f"   Executed: {action.get('executed_at', 'N/A')}")
            lines.append(f"   By: {action.get('executed_by', 'N/A')}")
            lines.append(f"   Success: {action.get('success', False)}")
            lines.append("")
        
        lines.extend([
            "-" * 40,
            "APPROVALS",
            "-" * 40,
        ])
        
        for i, approval in enumerate(pack.approvals, 1):
            lines.append(f"{i}. {approval.get('approval_id', 'Unknown')}")
            lines.append(f"   Type: {approval.get('approval_type', 'N/A')}")
            lines.append(f"   Decision: {approval.get('decision', 'N/A')}")
            lines.append(f"   By: {approval.get('decided_by', 'N/A')}")
            lines.append("")
        
        lines.extend([
            "-" * 40,
            "VERIFICATION RESULTS",
            "-" * 40,
        ])
        
        for i, ver in enumerate(pack.verification_results, 1):
            lines.append(f"{i}. Check: {ver.get('check_expression', 'Unknown')[:50]}")
            lines.append(f"   Status: {ver.get('status', 'N/A')}")
            lines.append(f"   Passed: {ver.get('passed', False)}")
            lines.append("")
        
        lines.extend([
            "=" * 80,
            f"Generated: {datetime.utcnow().isoformat()}",
            "This document is an immutable audit record.",
            "=" * 80,
        ])
        
        return "\n".join(lines)
    
    def to_html(self, pack: EvidencePack) -> str:
        """Export evidence pack to HTML"""
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Evidence Pack {pack.pack_id}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        h1 {{ color: #333; }}
        h2 {{ color: #666; border-bottom: 1px solid #ccc; }}
        .meta {{ background: #f5f5f5; padding: 15px; border-radius: 5px; }}
        .outcome {{ font-size: 1.2em; font-weight: bold; }}
        .outcome.RESOLVED {{ color: green; }}
        .outcome.FAILED {{ color: red; }}
        .outcome.PARTIAL {{ color: orange; }}
        table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background: #f0f0f0; }}
        .hash {{ font-family: monospace; font-size: 0.9em; color: #666; }}
    </style>
</head>
<body>
    <h1>Evidence Pack</h1>
    
    <div class="meta">
        <p><strong>Pack ID:</strong> {pack.pack_id}</p>
        <p><strong>Run ID:</strong> {pack.run_id}</p>
        <p><strong>Incident ID:</strong> {pack.incident_id}</p>
        <p class="hash"><strong>Content Hash:</strong> {pack.content_hash}</p>
    </div>
    
    <h2>Identifiers</h2>
    <table>
        <tr><th>Field</th><th>Value</th></tr>
        <tr><td>Tenant</td><td>{pack.tenant_id}</td></tr>
        <tr><td>Site</td><td>{pack.site_id}</td></tr>
        <tr><td>Asset</td><td>{pack.asset_id}</td></tr>
        <tr><td>Playbook</td><td>{pack.playbook_id} v{pack.playbook_version}</td></tr>
    </table>
    
    <h2>Outcome</h2>
    <p class="outcome {pack.outcome}">{pack.outcome}</p>
    <p>{pack.outcome_reason}</p>
    
    <h2>Actions ({len(pack.actions)})</h2>
    <table>
        <tr><th>#</th><th>Type</th><th>Target</th><th>Executed</th><th>Success</th></tr>
        {"".join(f"<tr><td>{i+1}</td><td>{a.get('action_type')}</td><td>{a.get('target', 'N/A')}</td><td>{a.get('executed_at', 'N/A')}</td><td>{'✓' if a.get('success') else '✗'}</td></tr>" for i, a in enumerate(pack.actions))}
    </table>
    
    <h2>Approvals ({len(pack.approvals)})</h2>
    <table>
        <tr><th>#</th><th>Type</th><th>Decision</th><th>By</th><th>At</th></tr>
        {"".join(f"<tr><td>{i+1}</td><td>{a.get('approval_type')}</td><td>{a.get('decision', 'N/A')}</td><td>{a.get('decided_by', 'N/A')}</td><td>{a.get('decided_at', 'N/A')}</td></tr>" for i, a in enumerate(pack.approvals))}
    </table>
    
    <h2>Verification ({len(pack.verification_results)})</h2>
    <table>
        <tr><th>#</th><th>Check</th><th>Passed</th><th>Message</th></tr>
        {"".join(f"<tr><td>{i+1}</td><td>{v.get('check_expression', '')[:40]}...</td><td>{'✓' if v.get('passed') else '✗'}</td><td>{v.get('message', '')[:50]}</td></tr>" for i, v in enumerate(pack.verification_results))}
    </table>
    
    <hr>
    <p><small>Generated: {datetime.utcnow().isoformat()} | This document is an immutable audit record.</small></p>
</body>
</html>
"""
        return html

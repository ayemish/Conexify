"""
PDM Repository Layer

Data access patterns for PDM domain objects.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.orm import Session

from .models import (
    AssetModel,
    TelemetryModel,
    AlertModel,
    FingerprintModel,
    FeedbackModel,
    RagDocumentModel,
    CalibrationStateModel,
    RegimeSegmentModel,
    ChangeDetectionModel,
    FaultHypothesisModel,
    ModelVersionModel,
    AuditLogModel,
    WorkOrderModel,
)

logger = logging.getLogger(__name__)


class BaseRepository:
    """Base repository with common operations"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def commit(self):
        self.session.commit()
    
    def rollback(self):
        self.session.rollback()


class AssetRepository(BaseRepository):
    """Repository for asset operations"""
    
    def create(self, asset_id: str, site_id: str, **kwargs) -> AssetModel:
        """Create a new asset"""
        asset = AssetModel(
            asset_id=asset_id,
            site_id=site_id,
            **kwargs
        )
        self.session.add(asset)
        self.session.flush()
        return asset
    
    def get_by_id(self, asset_id: str) -> Optional[AssetModel]:
        """Get asset by asset_id"""
        return self.session.query(AssetModel).filter(
            AssetModel.asset_id == asset_id
        ).first()
    
    def get_by_site(self, site_id: str, active_only: bool = True) -> List[AssetModel]:
        """Get all assets for a site"""
        query = self.session.query(AssetModel).filter(AssetModel.site_id == site_id)
        if active_only:
            query = query.filter(AssetModel.is_active == True)
        return query.all()
    
    def update_last_telemetry(self, asset_id: str, timestamp: datetime):
        """Update last telemetry timestamp"""
        self.session.query(AssetModel).filter(
            AssetModel.asset_id == asset_id
        ).update({"last_telemetry_at": timestamp})
    
    def deactivate(self, asset_id: str):
        """Deactivate an asset"""
        self.session.query(AssetModel).filter(
            AssetModel.asset_id == asset_id
        ).update({"is_active": False})
    
    def count_by_site(self, site_id: str) -> int:
        """Count active assets in a site"""
        return self.session.query(AssetModel).filter(
            AssetModel.site_id == site_id,
            AssetModel.is_active == True
        ).count()


class TelemetryRepository(BaseRepository):
    """Repository for telemetry operations"""
    
    def create(self, asset_id: str, timestamp: datetime, **data) -> TelemetryModel:
        """Store a telemetry reading"""
        telemetry = TelemetryModel(
            asset_id=asset_id,
            timestamp=timestamp,
            **data
        )
        self.session.add(telemetry)
        return telemetry
    
    def bulk_create(self, records: List[Dict[str, Any]], actor: str = "system") -> int:
        """Bulk insert telemetry records.

        Uses bulk_insert_mappings for performance. An audit log entry is
        written separately to maintain traceability for bulk imports.
        """
        count = len(records)
        self.session.bulk_insert_mappings(TelemetryModel, records)

        # Write audit trail for bulk import
        try:
            asset_ids = list({r.get("asset_id", "") for r in records if r.get("asset_id")})
            audit = AuditLogModel(
                event_id=f"bulk-{__import__('uuid').uuid4().hex[:12]}",
                action="telemetry_bulk_import",
                actor=actor,
                target_type="telemetry",
                target_id=asset_ids[0] if len(asset_ids) == 1 else None,
                details={
                    "record_count": count,
                    "asset_ids": asset_ids[:50],
                    "asset_count": len(asset_ids),
                },
            )
            self.session.add(audit)
        except Exception as e:
            logger.debug("Bulk import audit log failed: %s", e)

        return count
    
    def get_range(
        self,
        asset_id: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 10000
    ) -> List[TelemetryModel]:
        """Get telemetry in a time range"""
        return self.session.query(TelemetryModel).filter(
            TelemetryModel.asset_id == asset_id,
            TelemetryModel.timestamp >= start_time,
            TelemetryModel.timestamp <= end_time
        ).order_by(TelemetryModel.timestamp).limit(limit).all()
    
    def get_latest(self, asset_id: str, n: int = 1) -> List[TelemetryModel]:
        """Get the latest n telemetry records"""
        return self.session.query(TelemetryModel).filter(
            TelemetryModel.asset_id == asset_id
        ).order_by(TelemetryModel.timestamp.desc()).limit(n).all()
    
    def get_regime_summary(
        self,
        asset_id: str,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, int]:
        """Get count of samples per regime"""
        results = self.session.query(
            TelemetryModel.regime,
            func.count(TelemetryModel.id)
        ).filter(
            TelemetryModel.asset_id == asset_id,
            TelemetryModel.timestamp >= start_time,
            TelemetryModel.timestamp <= end_time
        ).group_by(TelemetryModel.regime).all()
        
        return {regime: count for regime, count in results}
    
    def delete_old(self, asset_id: str, before: datetime) -> int:
        """Delete telemetry older than a certain date"""
        result = self.session.query(TelemetryModel).filter(
            TelemetryModel.asset_id == asset_id,
            TelemetryModel.timestamp < before
        ).delete()
        return result


class AlertRepository(BaseRepository):
    """Repository for alert operations"""
    
    def create(self, asset_id: str, alert_id: str, **data) -> AlertModel:
        """Create a new alert"""
        alert = AlertModel(
            asset_id=asset_id,
            alert_id=alert_id,
            **data
        )
        self.session.add(alert)
        self.session.flush()
        return alert
    
    def get_by_id(self, alert_id: str) -> Optional[AlertModel]:
        """Get alert by alert_id"""
        return self.session.query(AlertModel).filter(
            AlertModel.alert_id == alert_id
        ).first()
    
    def get_active(self, asset_id: str) -> List[AlertModel]:
        """Get all active alerts for an asset"""
        return self.session.query(AlertModel).filter(
            AlertModel.asset_id == asset_id,
            AlertModel.status == "active"
        ).order_by(AlertModel.created_at.desc()).all()
    
    def get_by_type_and_range(
        self,
        asset_id: str,
        alert_type: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[AlertModel]:
        """Get alerts by type in a time range"""
        return self.session.query(AlertModel).filter(
            AlertModel.asset_id == asset_id,
            AlertModel.alert_type == alert_type,
            AlertModel.created_at >= start_time,
            AlertModel.created_at <= end_time
        ).all()
    
    def acknowledge(self, alert_id: str, acknowledged_by: str):
        """Acknowledge an alert"""
        self.session.query(AlertModel).filter(
            AlertModel.alert_id == alert_id
        ).update({
            "status": "acknowledged",
            "acknowledged_at": datetime.utcnow(),
            "acknowledged_by": acknowledged_by
        })
    
    def resolve(self, alert_id: str, resolved_by: str, notes: str = ""):
        """Resolve an alert"""
        self.session.query(AlertModel).filter(
            AlertModel.alert_id == alert_id
        ).update({
            "status": "resolved",
            "resolved_at": datetime.utcnow(),
            "resolved_by": resolved_by,
            "resolution_notes": notes
        })

    def dismiss(self, alert_id: str, dismissed_by: str, notes: str = ""):
        """Suppress/dismiss an alert without marking as resolved fault."""
        self.session.query(AlertModel).filter(
            AlertModel.alert_id == alert_id
        ).update({
            "status": "suppressed",
            "resolved_at": datetime.utcnow(),
            "resolved_by": dismissed_by,
            "resolution_notes": notes or "dismissed",
        })
    
    def add_feedback(self, alert_id: str, outcome: str, notes: str = ""):
        """Add feedback to an alert"""
        self.session.query(AlertModel).filter(
            AlertModel.alert_id == alert_id
        ).update({
            "feedback_outcome": outcome,
            "feedback_notes": notes,
            "feedback_at": datetime.utcnow()
        })
    
    def count_by_type_and_month(
        self,
        asset_id: str,
        alert_type: str,
        year: int,
        month: int
    ) -> int:
        """Count alerts by type for a specific month"""
        start = datetime(year, month, 1)
        if month == 12:
            end = datetime(year + 1, 1, 1)
        else:
            end = datetime(year, month + 1, 1)
        
        return self.session.query(AlertModel).filter(
            AlertModel.asset_id == asset_id,
            AlertModel.alert_type == alert_type,
            AlertModel.created_at >= start,
            AlertModel.created_at < end
        ).count()

    def count_by_type_and_month_for_site(
        self,
        site_id: str,
        alert_type: str,
        year: int,
        month: int
    ) -> int:
        """Count alerts by type for a site (fleet) in a specific month"""
        start = datetime(year, month, 1)
        if month == 12:
            end = datetime(year + 1, 1, 1)
        else:
            end = datetime(year, month + 1, 1)
        
        return self.session.query(AlertModel).join(
            AssetModel, AlertModel.asset_id == AssetModel.asset_id
        ).filter(
            AssetModel.site_id == site_id,
            AlertModel.alert_type == alert_type,
            AlertModel.created_at >= start,
            AlertModel.created_at < end
        ).count()
    
    def get_feedback_summary(
        self,
        asset_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, int]:
        """Get summary of feedback outcomes"""
        query = self.session.query(
            AlertModel.feedback_outcome,
            func.count(AlertModel.id)
        ).filter(
            AlertModel.feedback_outcome.isnot(None)
        )
        
        if asset_id:
            query = query.filter(AlertModel.asset_id == asset_id)
        if start_time:
            query = query.filter(AlertModel.created_at >= start_time)
        if end_time:
            query = query.filter(AlertModel.created_at <= end_time)
        
        results = query.group_by(AlertModel.feedback_outcome).all()
        return {outcome: count for outcome, count in results}


class FingerprintRepository(BaseRepository):
    """Repository for equipment fingerprint operations"""
    
    def create(
        self,
        asset_id: str,
        fingerprint_id: str,
        **data
    ) -> FingerprintModel:
        """Create a new fingerprint"""
        fingerprint = FingerprintModel(
            asset_id=asset_id,
            fingerprint_id=fingerprint_id,
            **data
        )
        self.session.add(fingerprint)
        self.session.flush()
        return fingerprint
    
    def get_by_asset(self, asset_id: str) -> Optional[FingerprintModel]:
        """Get fingerprint for an asset"""
        return self.session.query(FingerprintModel).filter(
            FingerprintModel.asset_id == asset_id
        ).first()
    
    def upsert(self, asset_id: str, fingerprint_id: str, **data) -> FingerprintModel:
        """Create or update fingerprint"""
        existing = self.get_by_asset(asset_id)
        if existing:
            for key, value in data.items():
                setattr(existing, key, value)
            existing.updated_at = datetime.utcnow()
            return existing
        else:
            return self.create(asset_id, fingerprint_id, **data)
    
    def update_learning_progress(
        self,
        asset_id: str,
        hours_of_data: float,
        adaptation_confidence: float
    ):
        """Update learning progress"""
        self.session.query(FingerprintModel).filter(
            FingerprintModel.asset_id == asset_id
        ).update({
            "hours_of_data": hours_of_data,
            "adaptation_confidence": adaptation_confidence,
            "updated_at": datetime.utcnow()
        })


class FeedbackRepository(BaseRepository):
    """Repository for feedback operations"""
    
    def create(
        self,
        alert_id: str,
        asset_id: str,
        outcome: str,
        **data
    ) -> FeedbackModel:
        """Record feedback"""
        feedback = FeedbackModel(
            alert_id=alert_id,
            asset_id=asset_id,
            outcome=outcome,
            **data
        )
        self.session.add(feedback)
        return feedback
    
    def get_for_calibration(
        self,
        asset_type: Optional[str] = None,
        limit: int = 1000
    ) -> List[FeedbackModel]:
        """Get feedback records for calibration"""
        query = self.session.query(FeedbackModel)
        # Add asset_type filter if needed via join
        return query.order_by(FeedbackModel.feedback_at.desc()).limit(limit).all()
    
    def count_by_outcome(
        self,
        asset_id: Optional[str] = None,
        start_time: Optional[datetime] = None
    ) -> Dict[str, int]:
        """Count feedback by outcome"""
        query = self.session.query(
            FeedbackModel.outcome,
            func.count(FeedbackModel.id)
        )
        if asset_id:
            query = query.filter(FeedbackModel.asset_id == asset_id)
        if start_time:
            query = query.filter(FeedbackModel.feedback_at >= start_time)
        
        results = query.group_by(FeedbackModel.outcome).all()
        return {outcome: count for outcome, count in results}


class CalibrationRepository(BaseRepository):
    """Repository for calibration state persistence"""
    
    def get_for_asset(self, asset_id: str) -> Optional[CalibrationStateModel]:
        return self.session.query(CalibrationStateModel).filter(
            CalibrationStateModel.asset_id == asset_id
        ).first()
    
    def get_for_asset_type(self, asset_type: str) -> Optional[CalibrationStateModel]:
        return self.session.query(CalibrationStateModel).filter(
            CalibrationStateModel.asset_type == asset_type
        ).order_by(CalibrationStateModel.updated_at.desc()).first()
    
    def upsert(
        self,
        asset_id: Optional[str],
        asset_type: Optional[str],
        calibration_curve: Dict[str, float],
        n_records: int,
        last_calibrated_at: Optional[datetime]
    ) -> CalibrationStateModel:
        existing = None
        if asset_id:
            existing = self.get_for_asset(asset_id)
        if not existing and asset_type:
            existing = self.get_for_asset_type(asset_type)
        if existing:
            existing.calibration_curve = calibration_curve
            existing.n_records = n_records
            existing.last_calibrated_at = last_calibrated_at
            existing.updated_at = datetime.utcnow()
            return existing
        state = CalibrationStateModel(
            asset_id=asset_id,
            asset_type=asset_type,
            calibration_curve=calibration_curve,
            n_records=n_records,
            last_calibrated_at=last_calibrated_at,
        )
        self.session.add(state)
        return state


class RagRepository(BaseRepository):
    """Repository for RAG documents and embeddings"""
    
    def upsert(
        self,
        doc_id: str,
        doc_type: str,
        content: str,
        embedding,
        embedding_dim: int,
        asset_id: Optional[str] = None,
        site_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RagDocumentModel:
        existing = self.session.query(RagDocumentModel).filter(
            RagDocumentModel.doc_id == doc_id
        ).first()
        if existing:
            existing.doc_type = doc_type
            existing.content = content
            existing.embedding = embedding
            existing.embedding_dim = embedding_dim
            existing.asset_id = asset_id
            existing.site_id = site_id
            existing.doc_metadata = metadata or {}
            existing.updated_at = datetime.utcnow()
            return existing
        doc = RagDocumentModel(
            doc_id=doc_id,
            doc_type=doc_type,
            content=content,
            embedding=embedding,
            embedding_dim=embedding_dim,
            asset_id=asset_id,
            site_id=site_id,
            doc_metadata=metadata or {},
        )
        self.session.add(doc)
        return doc
    
    def list_recent(self, limit: int = 200) -> List[RagDocumentModel]:
        return self.session.query(RagDocumentModel).order_by(
            RagDocumentModel.created_at.desc()
        ).limit(limit).all()


class RegimeSegmentRepository(BaseRepository):
    """Repository for regime segment operations"""
    
    def create(self, asset_id: str, regime: str, start_time: datetime, **data) -> RegimeSegmentModel:
        """Create a new regime segment"""
        segment = RegimeSegmentModel(
            asset_id=asset_id,
            regime=regime,
            start_time=start_time,
            **data
        )
        self.session.add(segment)
        return segment
    
    def close_segment(self, segment_id: str, end_time: datetime, **stats):
        """Close an open regime segment"""
        self.session.query(RegimeSegmentModel).filter(
            RegimeSegmentModel.id == segment_id
        ).update({
            "end_time": end_time,
            **stats
        })
    
    def get_open_segment(self, asset_id: str) -> Optional[RegimeSegmentModel]:
        """Get the current open segment"""
        return self.session.query(RegimeSegmentModel).filter(
            RegimeSegmentModel.asset_id == asset_id,
            RegimeSegmentModel.end_time.is_(None)
        ).first()


class ChangeDetectionRepository(BaseRepository):
    """Repository for change detection state"""
    
    def upsert(self, detector_id: str, asset_id: str, **data) -> ChangeDetectionModel:
        """Create or update change detection state"""
        existing = self.session.query(ChangeDetectionModel).filter(
            ChangeDetectionModel.detector_id == detector_id,
            ChangeDetectionModel.asset_id == asset_id
        ).first()
        
        if existing:
            for key, value in data.items():
                setattr(existing, key, value)
            return existing
        else:
            change = ChangeDetectionModel(
                detector_id=detector_id,
                asset_id=asset_id,
                **data
            )
            self.session.add(change)
            return change
    
    def get_active_changes(self, asset_id: str) -> List[ChangeDetectionModel]:
        """Get all active change detections"""
        return self.session.query(ChangeDetectionModel).filter(
            ChangeDetectionModel.asset_id == asset_id,
            ChangeDetectionModel.change_detected == True
        ).all()


class WorkOrderRepository(BaseRepository):
    """Repository for work order operations"""

    def create(self, wo_id: str, asset_id: str, site_id: str, **kwargs) -> WorkOrderModel:
        """Create a new work order record."""
        wo = WorkOrderModel(
            wo_id=wo_id,
            asset_id=asset_id,
            site_id=site_id,
            **kwargs,
        )
        self.session.add(wo)
        self.session.flush()
        return wo

    def get_by_wo_id(self, wo_id: str) -> Optional[WorkOrderModel]:
        return self.session.query(WorkOrderModel).filter(
            WorkOrderModel.wo_id == wo_id
        ).first()

    def get_by_asset(self, asset_id: str, limit: int = 100) -> List[WorkOrderModel]:
        return self.session.query(WorkOrderModel).filter(
            WorkOrderModel.asset_id == asset_id
        ).order_by(WorkOrderModel.opened_at.desc()).limit(limit).all()

    def get_by_site(self, site_id: str, limit: int = 500) -> List[WorkOrderModel]:
        return self.session.query(WorkOrderModel).filter(
            WorkOrderModel.site_id == site_id
        ).order_by(WorkOrderModel.opened_at.desc()).limit(limit).all()

    def get_open(self, site_id: Optional[str] = None) -> List[WorkOrderModel]:
        """Get all open/in-progress work orders."""
        query = self.session.query(WorkOrderModel).filter(
            WorkOrderModel.status.in_(["open", "in_progress", "assigned"])
        )
        if site_id:
            query = query.filter(WorkOrderModel.site_id == site_id)
        return query.order_by(WorkOrderModel.opened_at.desc()).all()

    def get_in_range(
        self,
        start: "datetime",
        end: "datetime",
        site_id: Optional[str] = None,
    ) -> List[WorkOrderModel]:
        """Get work orders opened within a date range."""
        query = self.session.query(WorkOrderModel).filter(
            WorkOrderModel.opened_at >= start,
            WorkOrderModel.opened_at <= end,
        )
        if site_id:
            query = query.filter(WorkOrderModel.site_id == site_id)
        return query.order_by(WorkOrderModel.opened_at.desc()).all()

    def close(self, wo_id: str, resolution: str = "", cost: float = 0.0, labor_hours: float = 0.0) -> Optional[WorkOrderModel]:
        """Close a work order."""
        wo = self.get_by_wo_id(wo_id)
        if wo:
            wo.status = "completed"
            wo.resolution = resolution
            wo.cost = cost
            wo.labor_hours = labor_hours
            wo.closed_at = datetime.utcnow()
            self.session.flush()
        return wo


class AuditRepository(BaseRepository):
    """Repository for audit log operations"""
    
    def log(
        self,
        action: str,
        actor: str,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        details: Optional[Dict] = None
    ) -> AuditLogModel:
        """Log an audit event"""
        import uuid
        event = AuditLogModel(
            event_id=str(uuid.uuid4())[:12],
            action=action,
            actor=actor,
            target_type=target_type,
            target_id=target_id,
            details=details or {}
        )
        self.session.add(event)
        return event
    
    def get_recent(
        self,
        action: Optional[str] = None,
        target_id: Optional[str] = None,
        limit: int = 100
    ) -> List[AuditLogModel]:
        """Get recent audit events"""
        query = self.session.query(AuditLogModel)
        if action:
            query = query.filter(AuditLogModel.action == action)
        if target_id:
            query = query.filter(AuditLogModel.target_id == target_id)
        return query.order_by(AuditLogModel.timestamp.desc()).limit(limit).all()

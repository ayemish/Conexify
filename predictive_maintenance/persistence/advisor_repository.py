"""
Advisor Session Repository — persist and restore chat sessions.

Write-through: every session create / message append is written to PostgreSQL
so sessions survive server restarts.  On advisor startup the in-memory store
is hydrated from the database.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DB_AVAILABLE = False
try:
    from predictive_maintenance.persistence.database import get_session
    from predictive_maintenance.persistence.models import (
        AdvisorSessionModel,
        AdvisorMessageModel,
    )
    _DB_AVAILABLE = True
except ImportError:
    logger.info("Advisor repository: DB not available")


class AdvisorRepository:
    """CRUD operations for advisor sessions and messages."""

    @staticmethod
    def is_available() -> bool:
        return _DB_AVAILABLE

    # ── Sessions ────────────────────────────────────────────────────

    @staticmethod
    def create_session(
        session_id: str,
        ecosystem: str = "auto",
        site_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if not _DB_AVAILABLE:
            return False
        try:
            with get_session() as db:
                row = AdvisorSessionModel(
                    session_id=session_id,
                    ecosystem=ecosystem,
                    site_id=site_id,
                    context=context or {},
                )
                db.add(row)
                db.commit()
            return True
        except Exception as e:
            logger.debug("create_session DB write failed: %s", e)
            return False

    @staticmethod
    def delete_session(session_id: str) -> bool:
        if not _DB_AVAILABLE:
            return False
        try:
            with get_session() as db:
                row = db.query(AdvisorSessionModel).filter(
                    AdvisorSessionModel.session_id == session_id,
                ).first()
                if row:
                    row.is_active = False
                    db.commit()
            return True
        except Exception as e:
            logger.debug("delete_session DB write failed: %s", e)
            return False

    @staticmethod
    def load_all_active_sessions() -> List[Dict[str, Any]]:
        """Return all active sessions with their messages for hydration."""
        if not _DB_AVAILABLE:
            return []
        try:
            with get_session() as db:
                rows = (
                    db.query(AdvisorSessionModel)
                    .filter(AdvisorSessionModel.is_active == True)
                    .all()
                )
                sessions = []
                for row in rows:
                    messages = (
                        db.query(AdvisorMessageModel)
                        .filter(AdvisorMessageModel.session_id == row.session_id)
                        .order_by(AdvisorMessageModel.created_at)
                        .all()
                    )
                    sessions.append({
                        "session_id": row.session_id,
                        "ecosystem": row.ecosystem,
                        "site_id": row.site_id,
                        "context": row.context or {},
                        "created_at": row.created_at,
                        "messages": [
                            {
                                "role": m.role,
                                "content": m.content,
                                "metadata": m.metadata_ or {},
                                "created_at": m.created_at,
                            }
                            for m in messages
                        ],
                    })
                return sessions
        except Exception as e:
            logger.debug("load_all_active_sessions failed: %s", e)
            return []

    # ── Messages ────────────────────────────────────────────────────

    @staticmethod
    def append_message(
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if not _DB_AVAILABLE:
            return False
        try:
            with get_session() as db:
                msg = AdvisorMessageModel(
                    session_id=session_id,
                    role=role,
                    content=content,
                    metadata_=metadata or {},
                )
                db.add(msg)
                # Update session timestamp
                session_row = db.query(AdvisorSessionModel).filter(
                    AdvisorSessionModel.session_id == session_id,
                ).first()
                if session_row:
                    session_row.updated_at = datetime.utcnow()
                db.commit()
            return True
        except Exception as e:
            logger.debug("append_message DB write failed: %s", e)
            return False

    @staticmethod
    def get_messages(session_id: str) -> List[Dict[str, Any]]:
        if not _DB_AVAILABLE:
            return []
        try:
            with get_session() as db:
                messages = (
                    db.query(AdvisorMessageModel)
                    .filter(AdvisorMessageModel.session_id == session_id)
                    .order_by(AdvisorMessageModel.created_at)
                    .all()
                )
                return [
                    {
                        "role": m.role,
                        "content": m.content,
                        "metadata": m.metadata_ or {},
                        "created_at": m.created_at.isoformat() if m.created_at else None,
                    }
                    for m in messages
                ]
        except Exception as e:
            logger.debug("get_messages failed: %s", e)
            return []

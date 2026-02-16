"""
Telemetry Retention Policy — prevent unbounded pdm_telemetry growth.

Provides:
- Configurable retention window (default 90 days)
- Bulk DELETE of rows older than the window
- Optional downsampling (keep 1-per-hour for data between 30–90 days)
- Callable from CLI, scheduler, or API health-check hooks

Usage:
    from predictive_maintenance.persistence.telemetry_retention import enforce_retention
    deleted = enforce_retention()          # uses defaults
    deleted = enforce_retention(days=60)   # custom window
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Defaults
DEFAULT_RETENTION_DAYS = 90
DEFAULT_DOWNSAMPLE_AFTER_DAYS = 30
BATCH_SIZE = 5000


def enforce_retention(
    days: Optional[int] = None,
    downsample_after_days: Optional[int] = None,
    batch_size: int = BATCH_SIZE,
    dry_run: bool = False,
) -> int:
    """Delete telemetry rows older than *days* (default 90).

    Parameters
    ----------
    days : int, optional
        Hard-delete rows older than this many days.
    downsample_after_days : int, optional
        For rows between ``downsample_after_days`` and ``days``, keep only
        one reading per asset per hour (delete duplicates).
    batch_size : int
        Max rows to delete per batch to avoid long locks.
    dry_run : bool
        If True, log what would be deleted but don't commit.

    Returns
    -------
    int
        Total number of rows deleted.
    """
    retention_days = days or DEFAULT_RETENTION_DAYS
    ds_days = downsample_after_days or DEFAULT_DOWNSAMPLE_AFTER_DAYS

    total_deleted = 0
    total_deleted += _hard_delete_old(retention_days, batch_size, dry_run)
    total_deleted += _downsample_range(ds_days, retention_days, batch_size, dry_run)
    return total_deleted


def _hard_delete_old(retention_days: int, batch_size: int, dry_run: bool) -> int:
    """Hard-delete all telemetry older than retention_days."""
    try:
        from predictive_maintenance.persistence.database import get_session
        from predictive_maintenance.persistence.models import TelemetryModel
    except ImportError:
        logger.warning("Telemetry retention: DB not available")
        return 0

    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    total = 0

    while True:
        try:
            with get_session() as session:
                q = (
                    session.query(TelemetryModel)
                    .filter(TelemetryModel.timestamp < cutoff)
                    .limit(batch_size)
                )
                count = 0
                if dry_run:
                    count = q.count()
                    logger.info(
                        "[DRY RUN] Would delete %d telemetry rows older than %s",
                        count, cutoff.isoformat(),
                    )
                    return count
                else:
                    ids = [row.id for row in q.all()]
                    if not ids:
                        break
                    count = (
                        session.query(TelemetryModel)
                        .filter(TelemetryModel.id.in_(ids))
                        .delete(synchronize_session=False)
                    )
                    session.commit()
                total += count
                if count < batch_size:
                    break
        except Exception as e:
            logger.error("Telemetry hard-delete batch failed: %s", e)
            break

    if total:
        logger.info(
            "Telemetry retention: deleted %d rows older than %d days (cutoff=%s)",
            total, retention_days, cutoff.isoformat(),
        )
    return total


def _downsample_range(
    downsample_after_days: int,
    retention_days: int,
    batch_size: int,
    dry_run: bool,
) -> int:
    """Within the downsample window, keep only one row per asset per hour."""
    try:
        from predictive_maintenance.persistence.database import get_engine
        from sqlalchemy import text
    except ImportError:
        return 0

    engine = get_engine()
    db_url = str(engine.url)
    if db_url.startswith("sqlite"):
        # SQLite lacks date_trunc; skip downsampling there
        return 0

    older_than = datetime.utcnow() - timedelta(days=downsample_after_days)
    newer_than = datetime.utcnow() - timedelta(days=retention_days)

    sql = text("""
        DELETE FROM pdm_telemetry
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY asset_id, date_trunc('hour', timestamp)
                           ORDER BY timestamp
                       ) AS rn
                FROM pdm_telemetry
                WHERE timestamp >= :newer_than
                  AND timestamp < :older_than
            ) sub
            WHERE sub.rn > 1
            LIMIT :batch_size
        )
    """)

    total = 0
    try:
        with engine.begin() as conn:
            if dry_run:
                count_sql = text("""
                    SELECT count(*) FROM (
                        SELECT id,
                               ROW_NUMBER() OVER (
                                   PARTITION BY asset_id, date_trunc('hour', timestamp)
                                   ORDER BY timestamp
                               ) AS rn
                        FROM pdm_telemetry
                        WHERE timestamp >= :newer_than
                          AND timestamp < :older_than
                    ) sub WHERE sub.rn > 1
                """)
                result = conn.execute(count_sql, {"newer_than": newer_than, "older_than": older_than})
                total = result.scalar() or 0
                logger.info("[DRY RUN] Would downsample %d duplicate telemetry rows", total)
            else:
                while True:
                    result = conn.execute(sql, {
                        "newer_than": newer_than,
                        "older_than": older_than,
                        "batch_size": batch_size,
                    })
                    deleted = result.rowcount
                    total += deleted
                    if deleted < batch_size:
                        break

                if total:
                    logger.info(
                        "Telemetry retention: downsampled %d duplicate rows (%d–%d days old)",
                        total, downsample_after_days, retention_days,
                    )
    except Exception as e:
        logger.error("Telemetry downsample failed: %s", e)

    return total


def get_telemetry_stats() -> dict:
    """Return telemetry table stats for monitoring."""
    try:
        from predictive_maintenance.persistence.database import get_session
        from predictive_maintenance.persistence.models import TelemetryModel
        from sqlalchemy import func

        with get_session() as session:
            total = session.query(func.count(TelemetryModel.id)).scalar() or 0
            oldest = session.query(func.min(TelemetryModel.timestamp)).scalar()
            newest = session.query(func.max(TelemetryModel.timestamp)).scalar()
            return {
                "total_rows": total,
                "oldest_timestamp": oldest.isoformat() if oldest else None,
                "newest_timestamp": newest.isoformat() if newest else None,
                "retention_days": DEFAULT_RETENTION_DAYS,
            }
    except Exception as e:
        return {"error": str(e)}

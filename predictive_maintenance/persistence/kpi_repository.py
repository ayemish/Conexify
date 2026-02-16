"""
KPI Pipeline Repository — persistence for KPI orchestration runs and results.

Provides:
- KPI pipeline run tracking (status, phases, crew statuses)
- Individual KPI result persistence
- Schema mapping CRUD
- Redis-backed dashboard result cache
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .models import KPIPipelineRunModel, KPIResultModel, SchemaMappingModel

logger = logging.getLogger(__name__)


class KPIPipelineRepository:
    """Repository for KPI pipeline run tracking."""

    def __init__(self, session: Session):
        self.session = session

    def create_run(self, site_id: str) -> KPIPipelineRunModel:
        run = KPIPipelineRunModel(
            run_id=f"kpi-{uuid.uuid4().hex[:12]}",
            site_id=site_id,
            status="pending",
            started_at=datetime.utcnow(),
        )
        self.session.add(run)
        self.session.flush()
        return run

    def update_phase(self, run_id: str, phase: str, phase_index: int):
        self.session.query(KPIPipelineRunModel).filter(
            KPIPipelineRunModel.run_id == run_id
        ).update({
            "phase": phase,
            "phase_index": phase_index,
            "status": "running",
        })

    def update_crew_status(self, run_id: str, kpi_name: str, status_update: Dict):
        run = self.session.query(KPIPipelineRunModel).filter(
            KPIPipelineRunModel.run_id == run_id
        ).first()
        if run:
            statuses = dict(run.crew_statuses or {})
            statuses[kpi_name] = status_update
            run.crew_statuses = statuses

    def complete_run(self, run_id: str, result_payload: Dict[str, Any]):
        now = datetime.utcnow()
        run = self.session.query(KPIPipelineRunModel).filter(
            KPIPipelineRunModel.run_id == run_id
        ).first()
        if run:
            run.status = "completed"
            run.completed_at = now
            run.result_payload = result_payload
            if run.started_at:
                run.duration_seconds = (now - run.started_at).total_seconds()

    def fail_run(self, run_id: str, error: str):
        self.session.query(KPIPipelineRunModel).filter(
            KPIPipelineRunModel.run_id == run_id
        ).update({
            "status": "failed",
            "error_message": error,
            "completed_at": datetime.utcnow(),
        })

    def get_latest_run(self, site_id: str) -> Optional[KPIPipelineRunModel]:
        return self.session.query(KPIPipelineRunModel).filter(
            KPIPipelineRunModel.site_id == site_id
        ).order_by(KPIPipelineRunModel.created_at.desc()).first()

    def get_run(self, run_id: str) -> Optional[KPIPipelineRunModel]:
        return self.session.query(KPIPipelineRunModel).filter(
            KPIPipelineRunModel.run_id == run_id
        ).first()

    def get_recent_runs(self, site_id: str, limit: int = 20) -> List[KPIPipelineRunModel]:
        return self.session.query(KPIPipelineRunModel).filter(
            KPIPipelineRunModel.site_id == site_id
        ).order_by(KPIPipelineRunModel.created_at.desc()).limit(limit).all()


class KPIResultRepository:
    """Repository for individual KPI results."""

    def __init__(self, session: Session):
        self.session = session

    def store_results(self, run_id: str, site_id: str, results: List[Dict[str, Any]]):
        for r in results:
            model = KPIResultModel(
                run_id=run_id,
                site_id=site_id,
                kpi_name=r.get("kpi_name", ""),
                display_name=r.get("display_name", ""),
                category=r.get("category", ""),
                savings_low=r.get("savings_low", 0),
                savings_medium=r.get("savings_medium", 0),
                savings_high=r.get("savings_high", 0),
                confidence=r.get("confidence", 0),
                status=r.get("status", "pending"),
                narrative=r.get("narrative", ""),
                assumptions=r.get("assumptions", []),
                supporting_metrics=r.get("supporting_metrics", {}),
                data_points_used=r.get("data_points_used", 0),
                data_coverage_pct=r.get("data_coverage_pct", 0),
            )
            self.session.add(model)

    def get_by_run(self, run_id: str) -> List[KPIResultModel]:
        return self.session.query(KPIResultModel).filter(
            KPIResultModel.run_id == run_id
        ).order_by(KPIResultModel.savings_medium.desc()).all()

    def get_latest_for_site(self, site_id: str) -> List[KPIResultModel]:
        """Get the most recent KPI results for a site."""
        from sqlalchemy import func
        subq = self.session.query(
            func.max(KPIResultModel.computed_at).label("max_ts")
        ).filter(KPIResultModel.site_id == site_id).scalar_subquery()

        return self.session.query(KPIResultModel).filter(
            KPIResultModel.site_id == site_id,
            KPIResultModel.computed_at == subq,
        ).order_by(KPIResultModel.savings_medium.desc()).all()


class SchemaMappingRepository:
    """Repository for data mapping configurations."""

    def __init__(self, session: Session):
        self.session = session

    def create(self, site_id: str, name: str, **kwargs) -> SchemaMappingModel:
        mapping = SchemaMappingModel(
            mapping_id=f"map-{uuid.uuid4().hex[:12]}",
            site_id=site_id,
            name=name,
            **kwargs,
        )
        self.session.add(mapping)
        self.session.flush()
        return mapping

    def get_by_id(self, mapping_id: str) -> Optional[SchemaMappingModel]:
        return self.session.query(SchemaMappingModel).filter(
            SchemaMappingModel.mapping_id == mapping_id
        ).first()

    def get_for_site(self, site_id: str) -> List[SchemaMappingModel]:
        return self.session.query(SchemaMappingModel).filter(
            SchemaMappingModel.site_id == site_id,
            SchemaMappingModel.is_active == True,
        ).order_by(SchemaMappingModel.updated_at.desc()).all()

    def update(self, mapping_id: str, **kwargs) -> Optional[SchemaMappingModel]:
        mapping = self.get_by_id(mapping_id)
        if mapping:
            for key, value in kwargs.items():
                if hasattr(mapping, key):
                    setattr(mapping, key, value)
            mapping.updated_at = datetime.utcnow()
        return mapping

    def delete(self, mapping_id: str):
        self.session.query(SchemaMappingModel).filter(
            SchemaMappingModel.mapping_id == mapping_id
        ).update({"is_active": False})


# ═══════════════════════════════════════════════════════════════════════
# Redis-backed KPI Dashboard Cache
# ═══════════════════════════════════════════════════════════════════════

class RedisDashboardCache:
    """Redis-backed cache for KPI dashboard results.

    Replaces the in-memory dict cache used by the loweconex_platform
    API routes. Falls back to in-memory when Redis is unavailable.
    """

    def __init__(self, redis_url: Optional[str] = None, ttl_seconds: int = 3600):
        self._ttl = ttl_seconds
        self._redis = None
        self._memory_cache: Dict[str, Any] = {}

        if redis_url:
            try:
                import redis
                self._redis = redis.from_url(redis_url, decode_responses=True)
                self._redis.ping()
                logger.info("Redis dashboard cache connected")
            except Exception as e:
                logger.warning("Redis unavailable, using in-memory cache: %s", e)
                self._redis = None

    def get(self, site_id: str) -> Optional[Dict[str, Any]]:
        cache_key = f"kpi_dashboard:{site_id}"
        if self._redis:
            try:
                data = self._redis.get(cache_key)
                if data:
                    return json.loads(data)
            except Exception as e:
                logger.debug("Redis get failed: %s", e)
        return self._memory_cache.get(site_id)

    def set(self, site_id: str, dashboard: Dict[str, Any]):
        cache_key = f"kpi_dashboard:{site_id}"
        if self._redis:
            try:
                self._redis.setex(cache_key, self._ttl, json.dumps(dashboard, default=str))
            except Exception as e:
                logger.debug("Redis set failed: %s", e)
        self._memory_cache[site_id] = dashboard

    def invalidate(self, site_id: str):
        cache_key = f"kpi_dashboard:{site_id}"
        if self._redis:
            try:
                self._redis.delete(cache_key)
            except Exception:
                pass
        self._memory_cache.pop(site_id, None)

    # ── Per-scenario caching ────────────────────────────────────────

    def get_scenario(self, site_id: str, scenario_id: str) -> Optional[Dict[str, Any]]:
        cache_key = f"kpi_scenario:{site_id}:{scenario_id}"
        if self._redis:
            try:
                data = self._redis.get(cache_key)
                if data:
                    return json.loads(data)
            except Exception as e:
                logger.debug("Redis scenario get failed: %s", e)
        return self._memory_cache.get(cache_key)

    def set_scenario(self, site_id: str, scenario_id: str, results: Dict[str, Any]):
        cache_key = f"kpi_scenario:{site_id}:{scenario_id}"
        if self._redis:
            try:
                self._redis.setex(cache_key, self._ttl, json.dumps(results, default=str))
            except Exception as e:
                logger.debug("Redis scenario set failed: %s", e)
        self._memory_cache[cache_key] = results

    def invalidate_scenario(self, site_id: str, scenario_id: str):
        cache_key = f"kpi_scenario:{site_id}:{scenario_id}"
        if self._redis:
            try:
                self._redis.delete(cache_key)
            except Exception:
                pass
        self._memory_cache.pop(cache_key, None)

    def invalidate_all_scenarios(self, site_id: str):
        """Invalidate all scenario caches for a site."""
        prefix = f"kpi_scenario:{site_id}:"
        if self._redis:
            try:
                keys = self._redis.keys(f"{prefix}*")
                if keys:
                    self._redis.delete(*keys)
            except Exception:
                pass
        to_remove = [k for k in self._memory_cache if k.startswith(prefix)]
        for k in to_remove:
            del self._memory_cache[k]


# Module-level cache instance (initialized lazily)
_dashboard_cache: Optional[RedisDashboardCache] = None


def get_dashboard_cache() -> RedisDashboardCache:
    """Get or create the dashboard cache singleton."""
    global _dashboard_cache
    if _dashboard_cache is None:
        redis_url = None
        try:
            from ..config import settings
            redis_url = settings.redis.url
        except Exception:
            pass
        _dashboard_cache = RedisDashboardCache(redis_url=redis_url)
    return _dashboard_cache

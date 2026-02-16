"""
Shared tools for all KPI crews.

Platform-specific implementations of the tool interfaces defined in the FRD.
These tools provide agents with read/write access to twins, time-series,
events, work orders, tariffs, and the event bus.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from loweconex_platform.digital_twins.store import TwinStore, OperationalEvent
from loweconex_platform.event_bus.redis_streams import LoweconexEventBus
from loweconex_platform.event_bus.events import EventEnvelope, EventType, create_envelope
from loweconex_platform.ai_risk.risk_framework import PromptGuard
from loweconex_platform.kpi_crews.research_corpus import get_research_snippets, get_benchmarks_for_kpi

logger = logging.getLogger(__name__)


class ArtifactStore:
    """
    Simple artifact store for persisting intermediate crew outputs.
    
    Artifacts are referenced by ID in Redis messages. Supports JSON
    serialization with metadata tracking.
    """

    def __init__(self, base_path: str = "./artifacts"):
        self._artifacts: Dict[str, Dict[str, Any]] = {}
        self.base_path = base_path
        self._counter = 0

    def store(self, artifact_type: str, data: Dict[str, Any], producer: str = "") -> str:
        self._counter += 1
        artifact_id = f"art_{artifact_type}_{self._counter}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        self._artifacts[artifact_id] = {
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "producer": producer,
            "data": data,
            "created_ts": datetime.utcnow().isoformat(),
        }
        return artifact_id

    def get(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        return self._artifacts.get(artifact_id)

    def list_by_type(self, artifact_type: str) -> List[Dict[str, Any]]:
        return [a for a in self._artifacts.values() if a["artifact_type"] == artifact_type]

    def list_by_producer(self, producer: str) -> List[Dict[str, Any]]:
        return [a for a in self._artifacts.values() if a["producer"] == producer]


class LoweconexTools:
    """
    Centralized tool provider for all KPI crews.
    
    Wraps the TwinStore, EventBus, and ArtifactStore to provide
    the tool interfaces specified in the FRD (Section 13.1).
    
    Integrates PromptGuard middleware for:
    - Per-agent tool allowlist enforcement
    - Prompt injection detection before LLM calls
    - Output exfiltration scanning
    """

    def __init__(
        self,
        twin_store: TwinStore,
        event_bus: LoweconexEventBus,
        artifact_store: Optional[ArtifactStore] = None,
        prompt_guard: Optional[PromptGuard] = None,
    ):
        self.twin_store = twin_store
        self.event_bus = event_bus
        self.artifact_store = artifact_store or ArtifactStore()
        self.prompt_guard = prompt_guard or PromptGuard(
            tool_allowlists={
                "research_agent": {"load_research_snippets"},
                "extraction_agent": {"read_twin", "query_timeseries", "query_events",
                                     "query_work_orders", "fetch_tariffs",
                                     "get_assets_for_scope", "get_locations_for_company"},
                "calculation_agent": {"read_twin", "write_twin", "query_events",
                                      "query_timeseries", "publish_event", "store_artifact"},
                "qa_agent": {"read_twin", "get_artifact", "query_events"},
            }
        )

    def check_tool_access(self, agent_id: str, tool_name: str) -> bool:
        """Check if agent is allowed to use a tool. Logs violations."""
        result = self.prompt_guard.check_tool_use(agent_id, tool_name)
        if not result["allowed"]:
            logger.warning(f"PromptGuard BLOCKED: agent={agent_id} tool={tool_name} reason={result.get('reason')}")
            return False
        return True

    def check_prompt_safe(self, prompt: str, agent_id: str = "") -> bool:
        """Check if a prompt is safe (no injection). Returns True if safe."""
        result = self.prompt_guard.check_prompt(prompt, agent_id)
        if result.get("blocked"):
            logger.warning(f"PromptGuard BLOCKED prompt for agent={agent_id}: {result.get('violations')}")
            return False
        return True

    def check_output_safe(self, output: str, agent_id: str = "") -> bool:
        """Check agent output for PII/exfiltration. Returns True if safe."""
        result = self.prompt_guard.check_output(output, agent_id)
        if not result.get("safe", True):
            logger.warning(f"PromptGuard flagged output for agent={agent_id}: {result.get('findings')}")
            return False
        return True

    # -------------------------------------------------------------------------
    # Twin Read/Write
    # -------------------------------------------------------------------------

    def read_twin(self, entity_type: str, entity_id: str) -> Dict[str, Any]:
        """Read a twin by type and ID. Returns dict or empty dict if not found."""
        result = self.twin_store.read_twin(entity_type, entity_id)
        return result or {}

    def write_twin(self, entity_type: str, entity_id: str, patch: Dict[str, Any]) -> bool:
        """Apply a partial update to a twin."""
        success = self.twin_store.patch_twin(entity_type, entity_id, patch)
        if success:
            self.event_bus.publish(create_envelope(
                event_type=EventType.TWIN_UPDATED,
                company_id=patch.get("company_id", ""),
                producer="tools.write_twin",
                payload={"entity_type": entity_type, "entity_id": entity_id, "patch_keys": list(patch.keys())},
            ))
        return success

    # -------------------------------------------------------------------------
    # Time-Series
    # -------------------------------------------------------------------------

    def query_timeseries(
        self,
        company_id: str = "",
        point_ids: Optional[List[str]] = None,
        start_ts: Optional[str] = None,
        end_ts: Optional[str] = None,
        limit: int = 1000,
    ) -> Any:
        """
        Query time-series data for given point IDs and time range.
        Returns {point_id: [{timestamp, value, quality, unit}]}.
        """
        if point_ids is None:
            # Backward-compatible single-point call form:
            # query_timeseries(point_id, start_ts=..., end_ts=..., limit=...)
            point_id = company_id
            company_id = ""
            point_ids = [point_id] if point_id else []

        if isinstance(point_ids, str):
            point_ids = [point_ids]

        if not point_ids:
            return {}

        end = datetime.fromisoformat(end_ts) if end_ts else datetime.utcnow()
        start = (
            datetime.fromisoformat(start_ts)
            if start_ts
            else end - timedelta(days=30)
        )
        raw = self.twin_store.query_timeseries(point_ids, start, end)
        result = {
            pid: [p.to_dict() for p in pts]
            for pid, pts in raw.items()
        }
        # Legacy compatibility for single-point callers.
        if len(point_ids) == 1:
            return result.get(point_ids[0], [])[:limit]
        return result

    # -------------------------------------------------------------------------
    # Events
    # -------------------------------------------------------------------------

    def query_events(self, company_id: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Query operational events (faults, excursions, leaks, work orders).
        Filters: location_id, asset_id, event_type, start_ts, end_ts, limit.
        """
        events = self.twin_store.query_events(
            company_id=company_id,
            location_id=filters.get("location_id"),
            asset_id=filters.get("asset_id"),
            event_type=filters.get("event_type"),
            start_ts=datetime.fromisoformat(filters["start_ts"]) if filters.get("start_ts") else None,
            end_ts=datetime.fromisoformat(filters["end_ts"]) if filters.get("end_ts") else None,
            limit=filters.get("limit", 1000),
        )
        return [e.to_dict() for e in events]

    # -------------------------------------------------------------------------
    # Work Orders
    # -------------------------------------------------------------------------

    def query_work_orders(
        self,
        company_id: str,
        start_ts: str = "",
        end_ts: str = "",
        location_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Query work order events within a time range."""
        if not end_ts:
            end_ts = datetime.utcnow().isoformat()
        if not start_ts:
            start_ts = (datetime.utcnow() - timedelta(days=30)).isoformat()
        return self.query_events(company_id, {
            "event_type": "work_order",
            "location_id": location_id,
            "start_ts": start_ts,
            "end_ts": end_ts,
        })

    # -------------------------------------------------------------------------
    # Tariffs
    # -------------------------------------------------------------------------

    def fetch_tariffs(self, location_id: str) -> Dict[str, Any]:
        """Fetch utility tariffs for a location."""
        loc = self.twin_store.get_location(location_id)
        if loc:
            return loc.utility_tariffs
        return {}

    # -------------------------------------------------------------------------
    # Event Bus
    # -------------------------------------------------------------------------

    def publish_event(
        self,
        stream: str,
        message: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
        company_id: str = "",
        location_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        producer: str = "tools.publish_event",
    ) -> str:
        """Publish an event to the bus."""
        msg = dict(message) if isinstance(message, dict) else {}
        if payload is not None:
            msg["payload"] = payload
        if company_id:
            msg["company_id"] = company_id
        if location_id:
            msg["location_id"] = location_id
        if asset_id:
            msg["asset_id"] = asset_id
        if producer:
            msg["producer"] = producer
        envelope = EventEnvelope(
            event_type=stream,
            company_id=msg.get("company_id", ""),
            location_id=msg.get("location_id"),
            asset_id=msg.get("asset_id"),
            producer=msg.get("producer", "tools.publish_event"),
            payload=msg.get("payload", msg),
            kpi_name=msg.get("kpi_name"),
        )
        return self.event_bus.publish(envelope)

    # -------------------------------------------------------------------------
    # Research / RAG
    # -------------------------------------------------------------------------

    def load_research_snippets(self, topic: str) -> List[Dict[str, Any]]:
        """
        Load research snippets from curated corpus (RAG).

        Delegates to research_corpus module which contains literature-grounded
        benchmarks, citations, and industry defaults for all 14 KPIs.
        In production, augments with pgvector similarity search.
        """
        return get_research_snippets(topic)

    def get_benchmarks(self, kpi_name: str) -> Dict[str, Any]:
        """
        Return merged benchmark dict for a KPI from the research corpus.
        Used by Calculation agents to select literature-grounded defaults.
        """
        return get_benchmarks_for_kpi(kpi_name)

    # -------------------------------------------------------------------------
    # Artifacts
    # -------------------------------------------------------------------------

    def store_artifact(self, artifact_type: str, data: Dict[str, Any], producer: str = "") -> str:
        return self.artifact_store.store(artifact_type, data, producer)

    def get_artifact(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        return self.artifact_store.get(artifact_id)

    # -------------------------------------------------------------------------
    # Location/Asset lookups
    # -------------------------------------------------------------------------

    def get_assets_for_scope(
        self,
        company_id: str,
        location_id: Optional[str] = None,
        asset_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get assets matching the given scope."""
        if location_id:
            assets = self.twin_store.get_assets_by_location(location_id)
        else:
            assets = self.twin_store.get_assets_by_company(company_id)
        if asset_type:
            assets = [a for a in assets if a.asset_type.value == asset_type]
        return [a.to_dict() for a in assets]

    def get_locations_for_company(self, company_id: str) -> List[Dict[str, Any]]:
        """Get all locations for a company."""
        locs = self.twin_store.get_locations_by_company(company_id)
        return [l.to_dict() for l in locs]

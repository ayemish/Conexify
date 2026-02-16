"""
CrewAI Tool Wrappers — binds LoweconexTools methods as CrewAI-compatible BaseTool
subclasses so that KPI crew agents can invoke twin store, event, timeseries,
artifact, and research operations during LLM-powered execution.

Each tool carries a typed _run() method that delegates to the shared
LoweconexTools singleton injected at crew-build time.
"""

import json
import logging
from typing import Any, Dict, List

from shared.agents.crewai_base import BaseTool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper: safe JSON return
# ---------------------------------------------------------------------------

def _json_result(data: Any) -> str:
    """Ensure tool output is a JSON string for LLM consumption."""
    try:
        return json.dumps(data, indent=2, default=str)
    except Exception:
        return str(data)


# =============================================================================
# Research Tools
# =============================================================================

class LoadResearchSnippetsTool(BaseTool):
    name: str = "load_research_snippets"
    description: str = (
        "Load curated research snippets for a given KPI topic. "
        "Input: JSON with 'kpi_name' (str). "
        "Returns: list of {summary, citation, source} dicts."
    )

    def __init__(self, tools_provider):
        super().__init__()
        self._tools = tools_provider

    def _run(self, kpi_name: str = "", **kwargs) -> str:
        snippets = self._tools.load_research_snippets(kpi_name or kwargs.get("kpi_name", ""))
        return _json_result(snippets)


# =============================================================================
# Extraction / Read Tools
# =============================================================================

class ReadTwinTool(BaseTool):
    name: str = "read_twin"
    description: str = (
        "Read a digital twin entity (asset, location, or estate). "
        "Input: JSON with 'entity_type' (str: asset|location|estate) and 'entity_id' (str). "
        "Returns: twin dict or error message."
    )

    def __init__(self, tools_provider):
        super().__init__()
        self._tools = tools_provider

    def _run(self, entity_type: str = "asset", entity_id: str = "", **kwargs) -> str:
        result = self._tools.read_twin(
            entity_type or kwargs.get("entity_type", "asset"),
            entity_id or kwargs.get("entity_id", ""),
        )
        return _json_result(result)


class QueryTimeseriesToolCrew(BaseTool):
    name: str = "query_timeseries"
    description: str = (
        "Query time-series data for a point ID within an optional time range. "
        "Input: JSON with 'point_id' (str), optional 'start_ts' and 'end_ts' (ISO strings), optional 'limit' (int). "
        "Returns: list of {timestamp, value, unit} dicts."
    )

    def __init__(self, tools_provider):
        super().__init__()
        self._tools = tools_provider

    def _run(self, point_id: str = "", **kwargs) -> str:
        result = self._tools.query_timeseries(
            point_id or kwargs.get("point_id", ""),
            start_ts=kwargs.get("start_ts"),
            end_ts=kwargs.get("end_ts"),
            limit=kwargs.get("limit", 1000),
        )
        return _json_result(result)


class QueryEventsTool(BaseTool):
    name: str = "query_events"
    description: str = (
        "Query operational events (work orders, faults, excursions). "
        "Input: JSON with 'company_id' (str) and optional filter fields: "
        "'event_type' (str), 'asset_id' (str), 'location_id' (str), 'severity' (str). "
        "Returns: list of event dicts."
    )

    def __init__(self, tools_provider):
        super().__init__()
        self._tools = tools_provider

    def _run(
        self,
        company_id: str = "",
        event_type: str = "",
        asset_id: str = "",
        location_id: str = "",
        severity: str = "",
        **kwargs,
    ) -> str:
        filters = {}
        for key, val in [
            ("event_type", event_type or kwargs.get("event_type", "")),
            ("asset_id", asset_id or kwargs.get("asset_id", "")),
            ("location_id", location_id or kwargs.get("location_id", "")),
            ("severity", severity or kwargs.get("severity", "")),
        ]:
            if val:
                filters[key] = val
        result = self._tools.query_events(
            company_id or kwargs.get("company_id", ""),
            filters,
        )
        return _json_result(result)


class QueryWorkOrdersTool(BaseTool):
    name: str = "query_work_orders"
    description: str = (
        "Query work order events for a company. "
        "Input: JSON with 'company_id' (str), optional 'location_id' (str). "
        "Returns: list of work order event dicts."
    )

    def __init__(self, tools_provider):
        super().__init__()
        self._tools = tools_provider

    def _run(
        self,
        company_id: str = "",
        start_ts: str = "",
        end_ts: str = "",
        **kwargs,
    ) -> str:
        result = self._tools.query_work_orders(
            company_id or kwargs.get("company_id", ""),
            start_ts=start_ts or kwargs.get("start_ts", ""),
            end_ts=end_ts or kwargs.get("end_ts", ""),
            location_id=kwargs.get("location_id"),
        )
        return _json_result(result)


class FetchTariffsTool(BaseTool):
    name: str = "fetch_tariffs"
    description: str = (
        "Fetch utility tariffs for a location. "
        "Input: JSON with 'location_id' (str). "
        "Returns: tariff dict with electricity_rate, gas_rate, demand_charges, tou_schedule."
    )

    def __init__(self, tools_provider):
        super().__init__()
        self._tools = tools_provider

    def _run(self, location_id: str = "", **kwargs) -> str:
        result = self._tools.fetch_tariffs(location_id or kwargs.get("location_id", ""))
        return _json_result(result)


class GetAssetsForScopeTool(BaseTool):
    name: str = "get_assets_for_scope"
    description: str = (
        "Get all asset twin dicts for a company, optionally filtered to a location. "
        "Input: JSON with 'company_id' (str), optional 'location_id' (str). "
        "Returns: list of asset twin dicts."
    )

    def __init__(self, tools_provider):
        super().__init__()
        self._tools = tools_provider

    def _run(self, company_id: str = "", location_id: str = "", **kwargs) -> str:
        result = self._tools.get_assets_for_scope(
            company_id or kwargs.get("company_id", ""),
            location_id or kwargs.get("location_id"),
        )
        return _json_result(result)


class GetLocationsForCompanyTool(BaseTool):
    name: str = "get_locations_for_company"
    description: str = (
        "Get all location twin dicts for a company. "
        "Input: JSON with 'company_id' (str). "
        "Returns: list of location twin dicts."
    )

    def __init__(self, tools_provider):
        super().__init__()
        self._tools = tools_provider

    def _run(self, company_id: str = "", **kwargs) -> str:
        result = self._tools.get_locations_for_company(
            company_id or kwargs.get("company_id", ""),
        )
        return _json_result(result)


# =============================================================================
# Calculation / Write Tools
# =============================================================================

class WriteTwinTool(BaseTool):
    name: str = "write_twin"
    description: str = (
        "Patch (partial update) a digital twin entity. "
        "Input: JSON with 'entity_type' (str: asset|location|estate), "
        "'entity_id' (str), 'patch' (dict of fields to update). "
        "Returns: success/failure message."
    )

    def __init__(self, tools_provider):
        super().__init__()
        self._tools = tools_provider

    def _run(self, entity_type: str = "asset", entity_id: str = "", patch_json: str = "", **kwargs) -> str:
        patch = {}
        raw = patch_json or kwargs.get("patch_json", "") or kwargs.get("patch", "")
        if raw:
            try:
                patch = json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                patch = {}
        result = self._tools.write_twin(
            entity_type or kwargs.get("entity_type", "asset"),
            entity_id or kwargs.get("entity_id", ""),
            patch,
        )
        return _json_result(result)


class PublishEventTool(BaseTool):
    name: str = "publish_event"
    description: str = (
        "Publish an event to the platform event bus. "
        "Input: JSON with 'event_type' (str), 'company_id' (str), "
        "'payload' (dict), optional 'location_id', 'asset_id'. "
        "Returns: event envelope ID."
    )

    def __init__(self, tools_provider):
        super().__init__()
        self._tools = tools_provider

    def _run(self, event_type: str = "", company_id: str = "", payload_json: str = "", location_id: str = "", asset_id: str = "", **kwargs) -> str:
        payload = {}
        raw = payload_json or kwargs.get("payload_json", "") or kwargs.get("payload", "")
        if raw:
            try:
                payload = json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                payload = {}
        result = self._tools.publish_event(
            stream=event_type or kwargs.get("event_type", ""),
            company_id=company_id or kwargs.get("company_id", ""),
            payload=payload,
            location_id=location_id or kwargs.get("location_id"),
            asset_id=asset_id or kwargs.get("asset_id"),
        )
        return _json_result(result)


class StoreArtifactTool(BaseTool):
    name: str = "store_artifact"
    description: str = (
        "Store an intermediate artifact (JSON-serializable dict). "
        "Input: JSON with 'artifact_type' (str), 'data' (dict), 'producer' (str). "
        "Returns: artifact ID string."
    )

    def __init__(self, tools_provider):
        super().__init__()
        self._tools = tools_provider

    def _run(self, artifact_type: str = "", data_json: str = "", producer: str = "", **kwargs) -> str:
        data = {}
        raw = data_json or kwargs.get("data_json", "") or kwargs.get("data", "")
        if raw:
            try:
                data = json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                data = {}
        result = self._tools.store_artifact(
            artifact_type or kwargs.get("artifact_type", ""),
            data,
            producer or kwargs.get("producer", "agent"),
        )
        return _json_result(result)


# =============================================================================
# QA Tools
# =============================================================================

class GetArtifactTool(BaseTool):
    name: str = "get_artifact"
    description: str = (
        "Retrieve a previously stored artifact by ID. "
        "Input: JSON with 'artifact_id' (str). "
        "Returns: artifact dict or null."
    )

    def __init__(self, tools_provider):
        super().__init__()
        self._tools = tools_provider

    def _run(self, artifact_id: str = "", **kwargs) -> str:
        result = self._tools.get_artifact(artifact_id or kwargs.get("artifact_id", ""))
        return _json_result(result)


# =============================================================================
# Tool Set Builders (per agent role)
# =============================================================================

def build_research_tools(tools_provider) -> list:
    """Tools available to the Research agent."""
    return [
        LoadResearchSnippetsTool(tools_provider),
    ]


def build_extraction_tools(tools_provider) -> list:
    """Tools available to the Extraction agent."""
    return [
        ReadTwinTool(tools_provider),
        QueryTimeseriesToolCrew(tools_provider),
        QueryEventsTool(tools_provider),
        QueryWorkOrdersTool(tools_provider),
        FetchTariffsTool(tools_provider),
        GetAssetsForScopeTool(tools_provider),
        GetLocationsForCompanyTool(tools_provider),
    ]


def build_calculation_tools(tools_provider) -> list:
    """Tools available to the Calculation agent."""
    return [
        ReadTwinTool(tools_provider),
        WriteTwinTool(tools_provider),
        QueryEventsTool(tools_provider),
        QueryTimeseriesToolCrew(tools_provider),
        PublishEventTool(tools_provider),
        StoreArtifactTool(tools_provider),
    ]


def build_qa_tools(tools_provider) -> list:
    """Tools available to the QA agent."""
    return [
        ReadTwinTool(tools_provider),
        GetArtifactTool(tools_provider),
        QueryEventsTool(tools_provider),
    ]

"""
Sensor Coverage Agent (A3)

CrewAI agent that assesses sensor coverage gaps across assets and sites.
Maps installed sensors against the ontology-defined required set, identifies
gaps, and recommends instrumentation improvements.

Addresses FR-13 / G2 / A3 from the FRD.
"""

import logging
from typing import Any, Dict, List, Optional

from shared.agents.crewai_base import (
    Agent, Task, Crew, Process, CREWAI_AVAILABLE,
    CrewAIAgentConfig, AgentCategory, AgentRole,
    BaseCrewAgent,
)
from predictive_maintenance.agents.protocols import (
    ProtocolEnabledAgent, ProtocolMessageBus,
)

logger = logging.getLogger(__name__)

# CrewAI @tool decorator with fallback
try:
    from crewai.tools import tool as crewai_tool
except ImportError:
    def crewai_tool(name_or_func=None):
        """Fallback @tool decorator when CrewAI is unavailable."""
        def decorator(func):
            func.tool_name = name_or_func if isinstance(name_or_func, str) else func.__name__
            return func
        if callable(name_or_func):
            return decorator(name_or_func)
        return decorator


# =============================================================================
# @tool Functions
# =============================================================================

@crewai_tool("assess_sensor_coverage")
def assess_sensor_coverage(
    asset_id: str,
    installed_sensors: str,
    required_sensors: str,
) -> dict:
    """Assess sensor coverage for an asset by comparing installed vs required sensors.
    installed_sensors and required_sensors are comma-separated strings of sensor type names.
    Returns coverage percentage, missing sensors, and recommendations."""
    installed = set(s.strip().lower() for s in installed_sensors.split(",") if s.strip())
    required = set(s.strip().lower() for s in required_sensors.split(",") if s.strip())

    if not required:
        return {
            "asset_id": asset_id,
            "coverage_pct": 100.0,
            "missing_sensors": [],
            "extra_sensors": sorted(installed),
            "recommendation": "No required sensor list defined for this asset type.",
        }

    covered = installed & required
    missing = required - installed
    extra = installed - required
    coverage_pct = round(len(covered) / len(required) * 100, 1)

    if coverage_pct >= 90:
        rec = "Good coverage. Minor gaps may be acceptable."
    elif coverage_pct >= 70:
        rec = "Moderate gaps. Recommend adding missing sensors before enabling autonomous actions."
    elif coverage_pct >= 50:
        rec = "Significant gaps. PdM models will operate in degraded mode."
    else:
        rec = "Critical coverage gap. Insufficient for reliable predictive maintenance."

    return {
        "asset_id": asset_id,
        "coverage_pct": coverage_pct,
        "installed_count": len(installed),
        "required_count": len(required),
        "covered_count": len(covered),
        "missing_sensors": sorted(missing),
        "extra_sensors": sorted(extra),
        "recommendation": rec,
    }


@crewai_tool("identify_site_coverage_gaps")
def identify_site_coverage_gaps(
    site_id: str,
    asset_coverage_json: str,
) -> dict:
    """Aggregate sensor coverage across all assets at a site.
    asset_coverage_json is a JSON array of objects with keys: asset_id, coverage_pct, missing_sensors.
    Returns site-level summary with worst-covered assets and aggregate statistics."""
    import json
    try:
        assets = json.loads(asset_coverage_json)
    except json.JSONDecodeError:
        return {"error": "Invalid asset_coverage_json"}

    if not assets:
        return {"site_id": site_id, "error": "No asset coverage data provided"}

    coverages = [a.get("coverage_pct", 0) for a in assets]
    avg_coverage = round(sum(coverages) / len(coverages), 1)
    min_coverage = min(coverages)

    # Find worst-covered assets
    worst = sorted(assets, key=lambda a: a.get("coverage_pct", 0))[:5]

    # Aggregate missing sensor types across site
    all_missing = {}
    for a in assets:
        for sensor in a.get("missing_sensors", []):
            all_missing[sensor] = all_missing.get(sensor, 0) + 1

    top_missing = sorted(all_missing.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "site_id": site_id,
        "total_assets": len(assets),
        "avg_coverage_pct": avg_coverage,
        "min_coverage_pct": min_coverage,
        "worst_assets": [
            {"asset_id": a.get("asset_id"), "coverage_pct": a.get("coverage_pct")}
            for a in worst
        ],
        "most_common_missing_sensors": [
            {"sensor_type": s, "affected_assets": c} for s, c in top_missing
        ],
        "site_grade": (
            "A" if avg_coverage >= 90 else
            "B" if avg_coverage >= 75 else
            "C" if avg_coverage >= 60 else
            "D" if avg_coverage >= 40 else "F"
        ),
    }


@crewai_tool("recommend_instrumentation")
def recommend_instrumentation(
    asset_id: str,
    missing_sensors: str,
    asset_criticality: str = "medium",
    estimated_cost_per_sensor: float = 250.0,
) -> dict:
    """Recommend instrumentation improvements for an asset with coverage gaps.
    missing_sensors is a comma-separated string. Returns prioritized list with ROI estimate."""
    sensors = [s.strip() for s in missing_sensors.split(",") if s.strip()]

    if not sensors:
        return {"asset_id": asset_id, "recommendations": [], "total_cost": 0}

    # Priority ordering based on PdM value
    high_value = {"temperature", "pressure", "vibration", "current", "power"}
    medium_value = {"humidity", "flow", "level", "rpm", "voltage"}

    recommendations = []
    for sensor in sensors:
        sensor_lower = sensor.lower()
        if any(hv in sensor_lower for hv in high_value):
            priority = "high"
            roi_multiplier = 3.0
        elif any(mv in sensor_lower for mv in medium_value):
            priority = "medium"
            roi_multiplier = 2.0
        else:
            priority = "low"
            roi_multiplier = 1.0

        # Boost priority for critical assets
        if asset_criticality == "critical":
            priority = "high" if priority != "high" else "critical"
            roi_multiplier *= 1.5

        recommendations.append({
            "sensor_type": sensor,
            "priority": priority,
            "estimated_cost": estimated_cost_per_sensor,
            "estimated_annual_roi": round(estimated_cost_per_sensor * roi_multiplier, 2),
            "justification": f"Required for PdM model coverage on {asset_criticality}-criticality asset.",
        })

    # Sort by priority
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    recommendations.sort(key=lambda r: priority_order.get(r["priority"], 4))

    return {
        "asset_id": asset_id,
        "asset_criticality": asset_criticality,
        "recommendations": recommendations,
        "total_cost": round(len(sensors) * estimated_cost_per_sensor, 2),
        "total_annual_roi": round(sum(r["estimated_annual_roi"] for r in recommendations), 2),
    }


# =============================================================================
# Sensor Coverage CrewAI Agent
# =============================================================================

class SensorCoverageAgent(BaseCrewAgent):
    """
    CrewAI agent that assesses sensor coverage gaps across assets and sites.

    Responsibilities:
    - Map installed sensors against ontology-defined required sets
    - Identify coverage gaps per asset and aggregate at site level
    - Recommend instrumentation improvements with ROI estimates
    - Participate in collaborative voting on coverage-related decisions
    """

    def __init__(
        self,
        site_id: str = "default",
        protocol_bus: Optional[ProtocolMessageBus] = None,
        **kwargs,
    ):
        config = CrewAIAgentConfig(
            agent_id=f"sensor_coverage_{site_id}",
            role=AgentRole.DATA_VALIDATOR,
            category=AgentCategory.DATA,
            name="Sensor Coverage Analyst",
            goal=(
                "Assess sensor coverage across all assets, identify gaps that "
                "degrade PdM model performance, and recommend cost-effective "
                "instrumentation improvements."
            ),
            backstory=(
                "You are a sensor instrumentation specialist with deep knowledge "
                "of HVAC/R systems. You understand which measurements are critical "
                "for predictive maintenance models and can quantify the impact of "
                "missing sensors on prediction accuracy and operational risk."
            ),
        )
        super().__init__(config, **kwargs)

        self.site_id = site_id
        self._protocol: Optional[ProtocolEnabledAgent] = None
        if protocol_bus is not None:
            self._protocol = ProtocolEnabledAgent(config.agent_id, protocol_bus)

    @property
    def tools(self) -> list:
        return [assess_sensor_coverage, identify_site_coverage_gaps, recommend_instrumentation]

    def assess_asset(self, asset_id: str, installed: List[str], required: List[str]) -> dict:
        """Convenience method to assess a single asset."""
        return assess_sensor_coverage(
            asset_id=asset_id,
            installed_sensors=",".join(installed),
            required_sensors=",".join(required),
        )

    def assess_site(self, site_id: str, asset_results: List[dict]) -> dict:
        """Convenience method to assess site-level coverage."""
        import json
        return identify_site_coverage_gaps(
            site_id=site_id,
            asset_coverage_json=json.dumps(asset_results),
        )

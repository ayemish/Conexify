"""
Parts & Inventory Agent (A10)

CrewAI agent that manages spare parts inventory, predicts consumption,
and recommends reorder points based on maintenance forecasts.

Responsibilities:
- Track parts inventory levels across sites
- Predict parts consumption from WO forecasts and fault patterns
- Recommend reorder points and safety stock levels
- Flag shortages that could delay upcoming maintenance

Addresses A10 from the FRD implementation plan.
"""

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from shared.agents.crewai_base import (
    BaseCrewAgent, CrewAIAgentConfig, AgentCategory, AgentRole,
)

logger = logging.getLogger(__name__)

# CrewAI @tool decorator with fallback
try:
    from crewai.tools import tool as crewai_tool
except ImportError:
    def crewai_tool(name_or_func=None):
        def decorator(func):
            func.tool_name = name_or_func if isinstance(name_or_func, str) else func.__name__
            return func
        if callable(name_or_func):
            return decorator(name_or_func)
        return decorator


# =============================================================================
# @tool Functions
# =============================================================================

@crewai_tool("check_parts_availability")
def check_parts_availability(
    part_ids: str, site_id: str = "default", inventory_json: str = "{}"
) -> dict:
    """Check current availability of parts at a site.
    part_ids: comma-separated part IDs.
    inventory_json: JSON object mapping part_id to {"on_hand": int, "committed": int}."""
    try:
        inventory = json.loads(inventory_json) if inventory_json != "{}" else {}
    except json.JSONDecodeError:
        inventory = {}

    parts = [p.strip() for p in part_ids.split(",") if p.strip()]
    results = []
    all_available = True

    for pid in parts:
        inv = inventory.get(pid, {})
        on_hand = inv.get("on_hand", 0)
        committed = inv.get("committed", 0)
        available = max(0, on_hand - committed)
        if available == 0:
            all_available = False

        results.append({
            "part_id": pid,
            "on_hand": on_hand,
            "committed": committed,
            "available": available,
            "status": "in_stock" if available > 0 else "out_of_stock",
        })

    return {
        "site_id": site_id,
        "all_available": all_available,
        "parts": results,
    }


@crewai_tool("calculate_reorder_point")
def calculate_reorder_point(
    part_id: str,
    avg_daily_usage: float,
    lead_time_days: int,
    service_level: float = 0.95,
    usage_std_dev: float = -1,
) -> dict:
    """Calculate reorder point and safety stock for a part.
    service_level: target fill rate (0.0-1.0). Default 0.95 (95%).
    usage_std_dev: daily usage standard deviation (-1 to auto-estimate)."""
    if usage_std_dev < 0:
        usage_std_dev = avg_daily_usage * 0.3  # 30% CV default

    # Z-score for service level (normal approximation)
    z_map = {0.90: 1.28, 0.95: 1.65, 0.97: 1.88, 0.99: 2.33}
    z = z_map.get(round(service_level, 2), 1.65)

    safety_stock = math.ceil(z * usage_std_dev * math.sqrt(lead_time_days))
    reorder_point = math.ceil(avg_daily_usage * lead_time_days + safety_stock)

    return {
        "part_id": part_id,
        "avg_daily_usage": avg_daily_usage,
        "lead_time_days": lead_time_days,
        "service_level": service_level,
        "safety_stock": safety_stock,
        "reorder_point": reorder_point,
        "recommendation": f"Reorder when inventory reaches {reorder_point} units.",
    }


@crewai_tool("predict_parts_demand")
def predict_parts_demand(
    fault_forecast_json: str,
    fault_parts_map_json: str,
    horizon_days: int = 30,
) -> dict:
    """Predict parts demand from fault type forecasts.
    fault_forecast_json: {"fault_type": expected_count, ...}.
    fault_parts_map_json: {"fault_type": [{"part_id": str, "qty": int}, ...]}."""
    try:
        forecasts = json.loads(fault_forecast_json)
        parts_map = json.loads(fault_parts_map_json)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON"}

    demand: Dict[str, int] = {}
    breakdown = []

    for fault_type, count in forecasts.items():
        parts_needed = parts_map.get(fault_type, [])
        for part in parts_needed:
            pid = part.get("part_id", "unknown")
            qty = part.get("qty", 1) * int(count)
            demand[pid] = demand.get(pid, 0) + qty
            breakdown.append({
                "fault_type": fault_type,
                "part_id": pid,
                "projected_qty": qty,
            })

    return {
        "horizon_days": horizon_days,
        "total_unique_parts": len(demand),
        "demand": demand,
        "breakdown": breakdown,
    }


@crewai_tool("identify_shortage_risks")
def identify_shortage_risks(
    demand_json: str, inventory_json: str
) -> dict:
    """Compare projected demand against current inventory to identify shortage risks.
    demand_json: {"part_id": qty_needed}.
    inventory_json: {"part_id": {"on_hand": int, "on_order": int}}."""
    try:
        demand = json.loads(demand_json)
        inventory = json.loads(inventory_json)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON"}

    risks = []
    for pid, needed in demand.items():
        inv = inventory.get(pid, {})
        available = inv.get("on_hand", 0) + inv.get("on_order", 0)
        shortfall = needed - available

        if shortfall > 0:
            risks.append({
                "part_id": pid,
                "needed": needed,
                "available": available,
                "shortfall": shortfall,
                "severity": "critical" if shortfall > needed * 0.5 else "moderate",
            })

    risks.sort(key=lambda r: r["shortfall"], reverse=True)

    return {
        "total_parts_checked": len(demand),
        "shortage_count": len(risks),
        "risks": risks,
        "all_covered": len(risks) == 0,
    }


# =============================================================================
# Parts & Inventory CrewAI Agent
# =============================================================================

class PartsInventoryAgent(BaseCrewAgent):
    """
    CrewAI agent that manages spare parts inventory and predicts consumption.
    """

    def __init__(self, **kwargs):
        config = CrewAIAgentConfig(
            agent_id="parts_inventory",
            role=AgentRole.INVENTORY_OPTIMIZER,
            category=AgentCategory.OPTIMIZATION,
            name="Parts & Inventory Specialist",
            goal=(
                "Track parts inventory, predict consumption from maintenance "
                "forecasts, calculate reorder points, and flag shortage risks "
                "that could delay critical maintenance."
            ),
            backstory=(
                "You are a supply chain specialist for HVAC/R maintenance. "
                "You ensure that the right parts are available at the right site "
                "before technicians arrive, minimizing repeat visits and "
                "maximizing first-time fix rates."
            ),
        )
        super().__init__(config, **kwargs)

    @property
    def tools(self) -> list:
        return [
            check_parts_availability,
            calculate_reorder_point,
            predict_parts_demand,
            identify_shortage_risks,
        ]

"""
Technician Scheduling Agent (A11)

CrewAI agent that optimizes technician dispatch and scheduling based on
skills, location, availability, and work order urgency.

Responsibilities:
- Match technician skills to work order requirements
- Optimize travel routes and minimize truck rolls
- Balance workload across available technicians
- Handle emergency re-scheduling and escalation

Addresses A11 from the FRD implementation plan.
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

@crewai_tool("match_technician_skills")
def match_technician_skills(
    required_skills: str,
    technicians_json: str,
) -> dict:
    """Match work order skill requirements against available technicians.
    required_skills: comma-separated skill names.
    technicians_json: JSON array of {"id": str, "name": str, "skills": [str],
    "available": bool, "location_lat": float, "location_lon": float}."""
    try:
        techs = json.loads(technicians_json)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON"}

    required = set(s.strip().lower() for s in required_skills.split(",") if s.strip())
    matches = []

    for tech in techs:
        tech_skills = set(s.lower() for s in tech.get("skills", []))
        overlap = required & tech_skills
        coverage = len(overlap) / max(len(required), 1)

        matches.append({
            "technician_id": tech.get("id"),
            "name": tech.get("name", ""),
            "available": tech.get("available", False),
            "skill_coverage": round(coverage, 2),
            "matching_skills": sorted(overlap),
            "missing_skills": sorted(required - tech_skills),
            "qualified": coverage >= 0.8 and tech.get("available", False),
        })

    matches.sort(key=lambda m: (m["qualified"], m["skill_coverage"]), reverse=True)
    qualified_count = sum(1 for m in matches if m["qualified"])

    return {
        "required_skills": sorted(required),
        "total_technicians": len(techs),
        "qualified_count": qualified_count,
        "matches": matches,
    }


@crewai_tool("optimize_schedule")
def optimize_schedule(
    work_orders_json: str,
    technicians_json: str,
    max_hours_per_day: float = 8.0,
) -> dict:
    """Create an optimized daily schedule assigning work orders to technicians.
    work_orders_json: JSON array of {"id": str, "site_id": str, "priority": str,
    "estimated_hours": float, "required_skills": [str], "lat": float, "lon": float}.
    technicians_json: as above."""
    try:
        wos = json.loads(work_orders_json)
        techs = json.loads(technicians_json)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON"}

    # Priority ordering
    priority_order = {"emergency": 0, "critical": 1, "high": 2, "medium": 3, "low": 4}
    wos.sort(key=lambda w: priority_order.get(w.get("priority", "medium"), 3))

    available_techs = [t for t in techs if t.get("available", False)]
    tech_hours: Dict[str, float] = {t["id"]: 0.0 for t in available_techs}
    assignments = []
    unassigned = []

    for wo in wos:
        est_hours = wo.get("estimated_hours", 2.0)
        wo_skills = set(s.lower() for s in wo.get("required_skills", []))

        best_tech = None
        best_score = -1

        for tech in available_techs:
            remaining = max_hours_per_day - tech_hours.get(tech["id"], 0)
            if remaining < est_hours:
                continue

            tech_skills = set(s.lower() for s in tech.get("skills", []))
            skill_match = len(wo_skills & tech_skills) / max(len(wo_skills), 1)
            if skill_match < 0.5:
                continue

            # Score: skill match + proximity bonus + workload balance
            score = skill_match * 50
            # Prefer less-loaded technicians
            score += (max_hours_per_day - tech_hours.get(tech["id"], 0)) / max_hours_per_day * 30
            # Proximity (simple distance estimate)
            if all(k in tech and k in wo for k in ("lat", "lon")):
                dist = math.sqrt(
                    (tech.get("lat", 0) - wo.get("lat", 0)) ** 2 +
                    (tech.get("lon", 0) - wo.get("lon", 0)) ** 2
                ) * 69  # rough miles
                score += max(0, 20 - dist)

            if score > best_score:
                best_score = score
                best_tech = tech

        if best_tech:
            tech_hours[best_tech["id"]] += est_hours
            assignments.append({
                "work_order_id": wo.get("id"),
                "technician_id": best_tech["id"],
                "technician_name": best_tech.get("name", ""),
                "priority": wo.get("priority", "medium"),
                "estimated_hours": est_hours,
                "score": round(best_score, 1),
            })
        else:
            unassigned.append({
                "work_order_id": wo.get("id"),
                "priority": wo.get("priority", "medium"),
                "reason": "No qualified/available technician with capacity",
            })

    return {
        "total_work_orders": len(wos),
        "assigned": len(assignments),
        "unassigned_count": len(unassigned),
        "assignments": assignments,
        "unassigned": unassigned,
        "technician_utilization": {
            tid: round(hrs / max_hours_per_day * 100, 1)
            for tid, hrs in tech_hours.items()
        },
    }


@crewai_tool("calculate_travel_time")
def calculate_travel_time(
    origin_lat: float, origin_lon: float,
    destination_lat: float, destination_lon: float,
    avg_speed_mph: float = 30.0,
) -> dict:
    """Estimate travel time between two locations (Haversine + avg speed).
    Returns distance in miles and estimated travel minutes."""
    # Haversine
    R = 3959  # Earth radius in miles
    lat1, lat2 = math.radians(origin_lat), math.radians(destination_lat)
    dlat = math.radians(destination_lat - origin_lat)
    dlon = math.radians(destination_lon - origin_lon)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c

    travel_minutes = (distance / avg_speed_mph) * 60

    return {
        "distance_miles": round(distance, 1),
        "travel_minutes": round(travel_minutes, 0),
        "avg_speed_mph": avg_speed_mph,
    }


@crewai_tool("handle_emergency_reschedule")
def handle_emergency_reschedule(
    emergency_wo_json: str,
    current_schedule_json: str,
) -> dict:
    """Re-schedule around an emergency work order by preempting lower-priority work.
    emergency_wo_json: single WO object. current_schedule_json: array of assignments."""
    try:
        emergency = json.loads(emergency_wo_json)
        schedule = json.loads(current_schedule_json)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON"}

    est_hours = emergency.get("estimated_hours", 2.0)
    wo_skills = set(s.lower() for s in emergency.get("required_skills", []))
    priority_order = {"emergency": 0, "critical": 1, "high": 2, "medium": 3, "low": 4}

    # Find best technician to preempt
    candidates = []
    for assign in schedule:
        assign_priority = priority_order.get(assign.get("priority", "medium"), 3)
        if assign_priority >= 2:  # Can preempt medium and lower
            candidates.append(assign)

    if not candidates:
        return {
            "action": "escalate",
            "reason": "No preemptable assignments found. Need overtime or contractor.",
            "emergency_wo": emergency.get("id"),
        }

    # Pick lowest priority assignment to defer
    candidates.sort(key=lambda a: priority_order.get(a.get("priority", "medium"), 3), reverse=True)
    preempted = candidates[0]

    return {
        "action": "reschedule",
        "emergency_wo": emergency.get("id"),
        "assigned_technician": preempted.get("technician_id"),
        "preempted_wo": preempted.get("work_order_id"),
        "preempted_priority": preempted.get("priority"),
        "recommendation": (
            f"Assign emergency WO to {preempted.get('technician_name', preempted.get('technician_id'))}. "
            f"Defer WO {preempted.get('work_order_id')} ({preempted.get('priority')}) to next available slot."
        ),
    }


# =============================================================================
# Technician Scheduling CrewAI Agent
# =============================================================================

class TechnicianSchedulingAgent(BaseCrewAgent):
    """
    CrewAI agent that optimizes technician dispatch and scheduling.
    """

    def __init__(self, **kwargs):
        config = CrewAIAgentConfig(
            agent_id="technician_scheduling",
            role=AgentRole.RESOURCE_ALLOCATOR,
            category=AgentCategory.OPTIMIZATION,
            name="Technician Scheduling Optimizer",
            goal=(
                "Optimize technician dispatch by matching skills to work orders, "
                "minimizing travel time, balancing workloads, and handling "
                "emergency re-scheduling."
            ),
            backstory=(
                "You are a field service optimization expert who ensures "
                "technicians are dispatched efficiently. You balance urgency, "
                "skill fit, travel distance, and workload to maximize "
                "first-time fix rates and minimize response times."
            ),
        )
        super().__init__(config, **kwargs)

    @property
    def tools(self) -> list:
        return [
            match_technician_skills,
            optimize_schedule,
            calculate_travel_time,
            handle_emergency_reschedule,
        ]

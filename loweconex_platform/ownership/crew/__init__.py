"""
Ownership Decision Crew — multi-agent CrewAI system for ownership-aware
cost optimization and decision support.

Agent Groups:
  A) Stakeholder Agents — protect ownership boundaries (FM, Finance, Compliance, Ops, ESG)
  B) Dimension Agents — enforce financial correctness (Opex, Capex, Risk, Strategic)
  C) Governance Agents — coordinate, reconcile, optimize, explain

Process: Hierarchical with parallel stages for validation and cost translation.
"""

from loweconex_platform.ownership.crew.schemas import (
    StakeholderPosition,
    AssumptionRecord,
    NegotiationLog,
    ParetoOption,
    DecisionCrewOutput,
)

__all__ = [
    "StakeholderPosition",
    "AssumptionRecord",
    "NegotiationLog",
    "ParetoOption",
    "DecisionCrewOutput",
]

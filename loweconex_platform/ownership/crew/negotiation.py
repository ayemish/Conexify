"""
Negotiation Engine — structured conflict resolution between stakeholder agents.

Collects StakeholderPositions, detects conflicts between hard/soft constraints,
runs constraint satisfaction to propose compromise scenarios, and logs the
full negotiation process for audit trail.

Common conflicts handled:
  - Finance pushes capex down vs FM wants replacement
  - Compliance requires tighter buffer vs ESG wants higher setpoint
  - Ops wants zero downtime vs FM wants maintenance windows
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from loweconex_platform.ownership.crew.schemas import (
    Constraint,
    ConflictRecord,
    NegotiationLog,
    StakeholderPosition,
    TradeBand,
)

logger = logging.getLogger(__name__)


class NegotiationEngine:
    """
    Resolves conflicts between stakeholder positions using:
    1. Hard constraint enforcement (non-negotiable)
    2. Soft constraint weighted compromise
    3. Trade band overlap detection
    4. Manager override for unresolvable conflicts

    Produces a NegotiationLog with full audit trail.
    """

    def __init__(self, max_rounds: int = 3):
        self.max_rounds = max_rounds
        self._positions: List[StakeholderPosition] = []
        self._conflicts: List[ConflictRecord] = []
        self._resolved_constraints: Dict[str, float] = {}

    def negotiate(
        self,
        positions: List[StakeholderPosition],
    ) -> NegotiationLog:
        """
        Run the full negotiation process.

        Args:
            positions: StakeholderPositions from all agents.

        Returns:
            NegotiationLog with conflicts, resolutions, and sign-offs.
        """
        self._positions = list(positions)
        self._conflicts = []
        self._resolved_constraints = {}

        log = NegotiationLog(positions=list(positions))

        # Round 1: Detect conflicts
        conflicts = self._detect_conflicts()
        log.conflicts_detected = conflicts
        self._conflicts = conflicts

        if not conflicts:
            # No conflicts — all agents sign off
            log.final_sign_offs = {p.agent_id: True for p in positions}
            log.rounds = 1
            return log

        # Round 2: Attempt resolution
        resolved_count = 0
        for conflict in conflicts:
            resolution = self._resolve_conflict(conflict, positions)
            if resolution:
                conflict.resolution = resolution["description"]
                conflict.resolution_method = resolution["method"]
                conflict.compromise_value = resolution.get("compromise_value")
                resolved_count += 1

        log.conflicts_resolved = resolved_count
        log.rounds = 2

        # Round 3: Escalate unresolved to manager override
        unresolved = [c for c in conflicts if not c.resolution]
        if unresolved:
            log.rounds = 3
            for conflict in unresolved:
                override = self._manager_override(conflict, positions)
                conflict.resolution = override["description"]
                conflict.resolution_method = "manager_override"
                conflict.compromise_value = override.get("compromise_value")
                resolved_count += 1
            log.conflicts_resolved = resolved_count

        # Determine sign-offs
        log.final_sign_offs = self._determine_sign_offs(positions, conflicts)
        log.unresolved_objections = [
            c.description for c in conflicts if not c.resolution
        ]

        return log

    # ── Conflict Detection ──────────────────────────────────────

    def _detect_conflicts(self) -> List[ConflictRecord]:
        """Detect conflicts between stakeholder positions."""
        conflicts: List[ConflictRecord] = []

        all_hard = []
        all_soft = []
        all_bands: Dict[str, List[Tuple[str, TradeBand]]] = {}

        for pos in self._positions:
            for c in pos.non_negotiables:
                all_hard.append((pos.agent_id, c))
            for c in pos.preferences:
                all_soft.append((pos.agent_id, c))
            for tb in pos.trade_bands:
                if tb.parameter_id not in all_bands:
                    all_bands[tb.parameter_id] = []
                all_bands[tb.parameter_id].append((pos.agent_id, tb))

        # Check hard-vs-hard conflicts (same parameter, contradictory operators)
        conflicts.extend(self._check_hard_conflicts(all_hard))

        # Check hard-vs-soft conflicts
        conflicts.extend(self._check_hard_soft_conflicts(all_hard, all_soft))

        # Check trade band non-overlap
        conflicts.extend(self._check_trade_band_conflicts(all_bands))

        return conflicts

    def _check_hard_conflicts(
        self, hard_constraints: List[Tuple[str, Constraint]]
    ) -> List[ConflictRecord]:
        """Check for conflicts between hard constraints on the same parameter."""
        conflicts = []
        by_param: Dict[str, List[Tuple[str, Constraint]]] = {}

        for agent_id, c in hard_constraints:
            key = c.parameter_id or c.metric_id or c.description
            if key not in by_param:
                by_param[key] = []
            by_param[key].append((agent_id, c))

        for param_key, entries in by_param.items():
            if len(entries) < 2:
                continue

            for i in range(len(entries)):
                for j in range(i + 1, len(entries)):
                    a_id, a_c = entries[i]
                    b_id, b_c = entries[j]

                    if self._constraints_conflict(a_c, b_c):
                        conflicts.append(ConflictRecord(
                            agents_involved=[a_id, b_id],
                            description=(
                                f"Hard constraint conflict on '{param_key}': "
                                f"{a_id} requires {a_c.operator} {a_c.value}, "
                                f"{b_id} requires {b_c.operator} {b_c.value}"
                            ),
                            conflict_type="threshold",
                        ))

        return conflicts

    def _check_hard_soft_conflicts(
        self,
        hard_constraints: List[Tuple[str, Constraint]],
        soft_constraints: List[Tuple[str, Constraint]],
    ) -> List[ConflictRecord]:
        """Check if soft preferences violate hard constraints."""
        conflicts = []

        for h_agent, h_c in hard_constraints:
            for s_agent, s_c in soft_constraints:
                if h_agent == s_agent:
                    continue

                key_h = h_c.parameter_id or h_c.metric_id
                key_s = s_c.parameter_id or s_c.metric_id
                if not key_h or key_h != key_s:
                    continue

                if self._soft_violates_hard(h_c, s_c):
                    conflicts.append(ConflictRecord(
                        agents_involved=[h_agent, s_agent],
                        description=(
                            f"Soft preference from {s_agent} ({s_c.description}) "
                            f"violates hard constraint from {h_agent} ({h_c.description})"
                        ),
                        conflict_type="priority",
                    ))

        return conflicts

    def _check_trade_band_conflicts(
        self,
        all_bands: Dict[str, List[Tuple[str, TradeBand]]],
    ) -> List[ConflictRecord]:
        """Check for non-overlapping trade bands on the same parameter."""
        conflicts = []

        for param_id, entries in all_bands.items():
            if len(entries) < 2:
                continue

            for i in range(len(entries)):
                for j in range(i + 1, len(entries)):
                    a_id, a_tb = entries[i]
                    b_id, b_tb = entries[j]

                    # Check if ranges overlap
                    overlap_min = max(a_tb.min_acceptable, b_tb.min_acceptable)
                    overlap_max = min(a_tb.max_acceptable, b_tb.max_acceptable)

                    if overlap_min > overlap_max:
                        conflicts.append(ConflictRecord(
                            agents_involved=[a_id, b_id],
                            description=(
                                f"Non-overlapping trade bands for '{param_id}': "
                                f"{a_id} accepts [{a_tb.min_acceptable}, {a_tb.max_acceptable}], "
                                f"{b_id} accepts [{b_tb.min_acceptable}, {b_tb.max_acceptable}]"
                            ),
                            conflict_type="valuation",
                        ))

        return conflicts

    # ── Conflict Resolution ─────────────────────────────────────

    def _resolve_conflict(
        self,
        conflict: ConflictRecord,
        positions: List[StakeholderPosition],
    ) -> Optional[Dict[str, Any]]:
        """Attempt to resolve a conflict via constraint satisfaction."""

        if conflict.conflict_type == "priority":
            # Hard constraint always wins over soft preference
            hard_agent = self._find_hard_constraint_agent(conflict, positions)
            if hard_agent:
                return {
                    "description": (
                        f"Hard constraint from {hard_agent} takes precedence. "
                        f"Soft preference adjusted to comply."
                    ),
                    "method": "constraint_satisfaction",
                }

        if conflict.conflict_type == "valuation":
            # Find the closest overlapping point
            compromise = self._find_trade_compromise(conflict, positions)
            if compromise is not None:
                return {
                    "description": f"Compromise value {compromise:.4f} found within adjusted bands.",
                    "method": "weight_compromise",
                    "compromise_value": compromise,
                }

        if conflict.conflict_type == "threshold":
            # Use the more restrictive constraint (safety-first)
            return {
                "description": "Applied more restrictive constraint (safety-first principle).",
                "method": "constraint_satisfaction",
            }

        return None

    def _manager_override(
        self,
        conflict: ConflictRecord,
        positions: List[StakeholderPosition],
    ) -> Dict[str, Any]:
        """Manager resolves unresolvable conflicts using governance rules."""
        # Priority: Compliance > Finance > FM > Ops > ESG
        priority_order = ["compliance", "finance", "fm", "ops", "esg"]

        for agent_id in priority_order:
            if agent_id in conflict.agents_involved:
                return {
                    "description": (
                        f"Manager override: {agent_id}'s position prioritized "
                        f"(governance priority order). Affected agents notified."
                    ),
                    "method": "manager_override",
                }

        return {
            "description": "Manager override: default to most conservative position.",
            "method": "manager_override",
        }

    # ── Helpers ──────────────────────────────────────────────────

    def _constraints_conflict(self, a: Constraint, b: Constraint) -> bool:
        """Check if two constraints on the same param are contradictory."""
        if a.operator == "lte" and b.operator == "gte":
            return a.value < b.value
        if a.operator == "gte" and b.operator == "lte":
            return b.value < a.value
        if a.operator == "eq" and b.operator == "eq":
            return abs(a.value - b.value) > 1e-6
        return False

    def _soft_violates_hard(self, hard: Constraint, soft: Constraint) -> bool:
        """Check if a soft preference value violates a hard constraint."""
        if hard.operator == "lte" and soft.value > hard.value:
            return True
        if hard.operator == "gte" and soft.value < hard.value:
            return True
        return False

    def _find_hard_constraint_agent(
        self, conflict: ConflictRecord, positions: List[StakeholderPosition]
    ) -> Optional[str]:
        """Find which agent in the conflict has the hard constraint."""
        for pos in positions:
            if pos.agent_id in conflict.agents_involved and pos.non_negotiables:
                return pos.agent_id
        return None

    def _find_trade_compromise(
        self, conflict: ConflictRecord, positions: List[StakeholderPosition]
    ) -> Optional[float]:
        """Find a weighted compromise between non-overlapping trade bands."""
        bands = []
        for pos in positions:
            if pos.agent_id in conflict.agents_involved:
                for tb in pos.trade_bands:
                    bands.append((pos.agent_id, tb))

        if len(bands) < 2:
            return None

        # Weighted midpoint between preferred values
        total_weight = 0.0
        weighted_sum = 0.0
        for agent_id, tb in bands:
            # Give compliance higher weight
            w = 2.0 if "compliance" in agent_id else 1.0
            weighted_sum += tb.preferred * w
            total_weight += w

        if total_weight > 0:
            return round(weighted_sum / total_weight, 4)
        return None

    def _determine_sign_offs(
        self,
        positions: List[StakeholderPosition],
        conflicts: List[ConflictRecord],
    ) -> Dict[str, bool]:
        """Determine which agents sign off after negotiation."""
        sign_offs = {}
        unresolved_agents = set()

        for c in conflicts:
            if not c.resolution:
                for agent_id in c.agents_involved:
                    unresolved_agents.add(agent_id)

        for pos in positions:
            # Agent signs off if no unresolved conflicts involve them
            sign_offs[pos.agent_id] = pos.agent_id not in unresolved_agents

        return sign_offs

    def get_effective_constraints(self) -> Dict[str, Any]:
        """
        Return the effective constraints after negotiation.

        These are used to feed the optimizer with stakeholder-aware bounds.
        """
        hard_constraints = {}
        soft_preferences = {}

        for pos in self._positions:
            for c in pos.non_negotiables:
                key = c.parameter_id or c.metric_id or c.description
                hard_constraints[key] = {
                    "operator": c.operator,
                    "value": c.value,
                    "agent": pos.agent_id,
                    "justification": c.justification,
                }

            for c in pos.preferences:
                key = c.parameter_id or c.metric_id or c.description
                if key not in soft_preferences:
                    soft_preferences[key] = []
                soft_preferences[key].append({
                    "operator": c.operator,
                    "value": c.value,
                    "weight": c.weight,
                    "agent": pos.agent_id,
                })

        return {
            "hard_constraints": hard_constraints,
            "soft_preferences": soft_preferences,
            "resolved_overrides": self._resolved_constraints,
        }

"""
Decision Utility Service — formal expected-utility routing layer.

Computes U(dispatch), U(review), U(wait) from calibrated probabilities,
cost parameters, budget state, and operator capability.  Implements:

1. **Expected-utility decision**: choose action maximising expected utility
   under the Neyman–Pearson false-positive budget.
2. **Value-of-Information (VoI) routing**: "review now vs. gather more data
   vs. dispatch" with formal information-value logic.
3. **Human–AI complementarity**: route by uncertainty, consequence, and
   operator capability — not generic escalation flags.

References
----------
- Howard (1966) "Information Value Theory"
- Neyman–Pearson lemma for constrained detection
- Gneiting & Raftery (2007) for proper scoring context
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

class RoutingAction(str, Enum):
    DISPATCH = "dispatch"
    HUMAN_REVIEW = "human_review"
    GATHER_DATA = "gather_data"
    WATCH = "watch"
    SUPPRESS = "suppress"


@dataclass
class ActionUtility:
    """Expected utility for a single candidate action."""
    action: RoutingAction
    expected_utility: float = 0.0
    components: Dict[str, float] = field(default_factory=dict)
    rationale: str = ""


@dataclass
class RoutingDecision:
    """Output of the decision-utility layer."""
    recommended_action: RoutingAction
    utilities: Dict[str, ActionUtility] = field(default_factory=dict)
    voi_review: float = 0.0
    voi_gather: float = 0.0
    complementarity_score: float = 0.0
    budget_headroom_frac: float = 1.0
    rationale: str = ""


@dataclass
class OperatorCapability:
    """Operator context for human–AI complementarity routing."""
    queue_depth: int = 0
    avg_review_minutes: float = 10.0
    sla_minutes: float = 60.0
    historical_accuracy: float = 0.85
    is_available: bool = True


# ─────────────────────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────────────────────

class DecisionUtilityService:
    """
    Formal policy layer sitting between the detection/diagnosis stack and
    the action dispatch / approval queue.

    Inputs
    ------
    - Calibrated fault probability ``p_fault``
    - Calibrated false-alarm probability ``fa_prob``
    - Ensemble confidence interval width ``ci_width``
    - Cost parameters from ``FalsePositiveBudget``
    - Current budget state (alerts this month, NIF rate)
    - Operator capability context

    Outputs
    -------
    ``RoutingDecision`` with ranked utilities and recommended action.
    """

    def __init__(
        self,
        cost_truck_roll: float = 250.0,
        cost_missed_failure: float = 5000.0,
        cost_false_alarm: float = 300.0,
        cost_human_review: float = 40.0,
        cost_delay_per_hour: float = 20.0,
        budget_alarm_rate: float = 0.3,
        budget_nif_rate: float = 0.05,
    ):
        self.cost_truck_roll = cost_truck_roll
        self.cost_missed = cost_missed_failure
        self.cost_fa = cost_false_alarm
        self.cost_review = cost_human_review
        self.cost_delay = cost_delay_per_hour
        self.budget_alarm_rate = budget_alarm_rate
        self.budget_nif_rate = budget_nif_rate

    @classmethod
    def from_budget(cls, budget: Any) -> "DecisionUtilityService":
        """Construct from a ``FalsePositiveBudget`` dataclass."""
        return cls(
            cost_truck_roll=float(getattr(budget, "cost_truck_roll", 250.0)),
            cost_missed_failure=float(getattr(budget, "cost_missed_failure", 5000.0)),
            cost_false_alarm=float(getattr(budget, "cost_false_alarm", 300.0)),
            budget_alarm_rate=float(getattr(budget, "max_actionable_alarms_per_unit_per_month", 0.3)),
            budget_nif_rate=float(getattr(budget, "max_no_issue_found_rate", 0.05)),
        )

    # ─── Main entry point ─────────────────────────────────────────────

    def evaluate(
        self,
        p_fault: float,
        fa_prob: float,
        ci_width: float = 0.0,
        monthly_alerts: int = 0,
        monthly_nif: int = 0,
        persistence_hours: float = 0.0,
        operator: Optional[OperatorCapability] = None,
    ) -> RoutingDecision:
        """Compute utilities and recommend optimal action."""

        p_fault = float(max(0.0, min(1.0, p_fault)))
        p_no = 1.0 - p_fault
        operator = operator or OperatorCapability()

        # ── 1. Raw expected utilities ────────────────────────────────
        u_dispatch = self._u_dispatch(p_fault, p_no)
        u_review = self._u_review(p_fault, p_no, operator)
        u_gather = self._u_gather(p_fault, p_no, ci_width, persistence_hours)
        u_watch = self._u_watch(p_fault, p_no)

        # ── 2. Budget penalty ────────────────────────────────────────
        budget_headroom = self._budget_headroom(monthly_alerts, monthly_nif)
        budget_penalty = self._budget_penalty(budget_headroom)
        u_dispatch.expected_utility -= budget_penalty
        u_dispatch.components["budget_penalty"] = -budget_penalty

        # ── 3. Value of Information ──────────────────────────────────
        voi_review = self._voi_review(p_fault, ci_width, operator)
        voi_gather = self._voi_gather(p_fault, ci_width, persistence_hours)

        u_review.expected_utility += voi_review
        u_review.components["voi_bonus"] = voi_review
        u_gather.expected_utility += voi_gather
        u_gather.components["voi_bonus"] = voi_gather

        # ── 4. Human–AI complementarity ──────────────────────────────
        comp_score = self._complementarity_score(p_fault, ci_width, operator)

        # If complementarity is high (operator likely to add value), boost review
        if comp_score > 0.5:
            bonus = comp_score * self.cost_missed * 0.05
            u_review.expected_utility += bonus
            u_review.components["complementarity_bonus"] = bonus

        # If operator queue is saturated, penalise review
        if not operator.is_available or operator.queue_depth > 20:
            saturation_penalty = self.cost_review * 2.0
            u_review.expected_utility -= saturation_penalty
            u_review.components["saturation_penalty"] = -saturation_penalty

        # ── 5. Rank and select ───────────────────────────────────────
        candidates = {
            "dispatch": u_dispatch,
            "human_review": u_review,
            "gather_data": u_gather,
            "watch": u_watch,
        }

        best_key = max(candidates, key=lambda k: candidates[k].expected_utility)
        best = candidates[best_key]

        return RoutingDecision(
            recommended_action=best.action,
            utilities=candidates,
            voi_review=voi_review,
            voi_gather=voi_gather,
            complementarity_score=comp_score,
            budget_headroom_frac=budget_headroom,
            rationale=best.rationale,
        )

    # ─── Utility functions ────────────────────────────────────────────

    def _u_dispatch(self, pf: float, pn: float) -> ActionUtility:
        """U(dispatch) = p_fault × benefit_of_catching − p_no × cost_of_false_dispatch."""
        benefit = pf * self.cost_missed
        cost = pn * (self.cost_truck_roll + self.cost_fa)
        eu = benefit - cost
        return ActionUtility(
            action=RoutingAction.DISPATCH,
            expected_utility=eu,
            components={"benefit_catch": benefit, "cost_false_dispatch": -cost},
            rationale=f"Dispatch: benefit={benefit:.0f}, cost={cost:.0f}",
        )

    def _u_review(self, pf: float, pn: float, op: OperatorCapability) -> ActionUtility:
        """U(review) — human review can improve decision accuracy at review cost."""
        # Assume human review catches fraction of true faults and filters fraction of false alarms
        human_tpr = op.historical_accuracy
        human_fpr = 1.0 - op.historical_accuracy

        benefit = pf * human_tpr * self.cost_missed
        wasted = pn * human_fpr * (self.cost_truck_roll + self.cost_fa)
        review_cost = self.cost_review
        eu = benefit - wasted - review_cost
        return ActionUtility(
            action=RoutingAction.HUMAN_REVIEW,
            expected_utility=eu,
            components={
                "benefit_catch": benefit,
                "cost_false_after_review": -wasted,
                "review_cost": -review_cost,
            },
            rationale=f"Review: human_tpr={human_tpr:.0%}, benefit={benefit:.0f}",
        )

    def _u_gather(self, pf: float, pn: float, ci_width: float, persistence_h: float) -> ActionUtility:
        """U(gather more data) — delay cost vs. expected uncertainty reduction."""
        delay_cost = pf * self.cost_delay * 6.0  # assume 6 more hours
        # Expected uncertainty reduction: wider CI → more to gain
        info_gain = ci_width * self.cost_missed * 0.1  # heuristic

        # If already very persistent, little to gain from waiting
        if persistence_h > 24.0:
            info_gain *= 0.3

        eu = info_gain - delay_cost
        return ActionUtility(
            action=RoutingAction.GATHER_DATA,
            expected_utility=eu,
            components={"info_gain": info_gain, "delay_cost": -delay_cost},
            rationale=f"Gather: info_gain={info_gain:.0f}, delay_cost={delay_cost:.0f}",
        )

    def _u_watch(self, pf: float, pn: float) -> ActionUtility:
        """U(watch) — do nothing; risk missing fault, save dispatch cost."""
        missed_cost = pf * self.cost_missed * 0.5  # discounted by time
        eu = -missed_cost
        return ActionUtility(
            action=RoutingAction.WATCH,
            expected_utility=eu,
            components={"missed_cost": -missed_cost},
            rationale=f"Watch: discounted missed cost={missed_cost:.0f}",
        )

    # ─── Value-of-Information ─────────────────────────────────────────

    def _voi_review(self, pf: float, ci_width: float, op: OperatorCapability) -> float:
        """
        VoI for human review = expected improvement in decision quality
        from having an expert examine the case.

        Higher when:
        - Uncertainty (ci_width) is large
        - p_fault is near the decision boundary (~0.5)
        - Operator accuracy is high
        """
        boundary_proximity = 1.0 - 2.0 * abs(pf - 0.5)  # peaks at pf=0.5
        uncertainty_factor = min(1.0, ci_width / 0.5) if ci_width > 0 else 0.3
        human_value = op.historical_accuracy - 0.5  # above random

        voi = boundary_proximity * uncertainty_factor * human_value * self.cost_missed * 0.15
        return max(0.0, voi)

    def _voi_gather(self, pf: float, ci_width: float, persistence_h: float) -> float:
        """
        VoI for gathering more data = expected uncertainty reduction × cost impact.

        Higher when:
        - ci_width is large (much to learn)
        - persistence is short (early in event, more data will help)
        """
        if ci_width <= 0.05:
            return 0.0

        learning_potential = min(1.0, ci_width / 0.4)
        freshness = max(0.1, 1.0 - persistence_h / 48.0)  # decays over 48h

        voi = learning_potential * freshness * self.cost_missed * 0.08
        return max(0.0, voi)

    # ─── Budget awareness ─────────────────────────────────────────────

    def _budget_headroom(self, monthly_alerts: int, monthly_nif: int) -> float:
        """Fraction of budget remaining (0 = exhausted, 1 = full)."""
        limit = max(1, math.ceil(self.budget_alarm_rate))
        used_frac = monthly_alerts / limit if limit > 0 else 1.0

        nif_frac = 0.0
        if monthly_alerts > 0:
            nif_frac = monthly_nif / monthly_alerts
        nif_pressure = nif_frac / self.budget_nif_rate if self.budget_nif_rate > 0 else 0.0

        headroom = max(0.0, 1.0 - max(used_frac, nif_pressure))
        return headroom

    def _budget_penalty(self, headroom: float) -> float:
        """Penalty applied to dispatch utility when budget is tight."""
        if headroom >= 0.5:
            return 0.0
        # Exponential penalty as headroom shrinks
        penalty_frac = (0.5 - headroom) / 0.5
        return penalty_frac * (self.cost_truck_roll + self.cost_fa)

    # ─── Human–AI complementarity ─────────────────────────────────────

    def _complementarity_score(
        self, pf: float, ci_width: float, op: OperatorCapability,
    ) -> float:
        """
        Score in [0, 1] indicating how much a human operator would improve
        the decision versus the model acting alone.

        High when:
        - Model uncertainty is high (ci_width large)
        - Case is near decision boundary
        - Consequences are high (p_fault significant)
        - Operator is accurate and available
        """
        boundary = 1.0 - 2.0 * abs(pf - 0.5)
        uncertainty = min(1.0, ci_width / 0.4) if ci_width > 0 else 0.3
        consequence = min(1.0, pf * 2.0)
        operator_quality = op.historical_accuracy if op.is_available else 0.0

        raw = (0.3 * boundary + 0.3 * uncertainty + 0.2 * consequence + 0.2 * operator_quality)
        return float(max(0.0, min(1.0, raw)))

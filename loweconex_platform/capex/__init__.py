"""
CapEx Generator — Capital Expenditure Planning & Optimization Engine.

Ported from the standalone JavaScript CapEx Generator into the Loweconex platform.
Provides lifecycle cost analysis, survival modeling, fault-aware scoring,
knapsack budget optimization, and Monte Carlo probabilistic NPV.

Core components:
- CapExEngine:       Top-level orchestrator for full store/fleet analysis
- LCCEngine:         ASTM E917 life-cycle cost with EAC + Monte Carlo
- SurvivalModel:     Weibull + Cox PH failure probability modeling
- KnapsackOptimizer: DP + greedy budget-constrained portfolio selection
- AssetScorer:       Multi-factor priority scoring (condition, risk, energy, fault)
- FaultScorer:       FDD-derived fault burden scoring
"""

from loweconex_platform.capex.engine import CapExEngine
from loweconex_platform.capex.lcc import (
    LCCEngine,
    compute_keep_lcc,
    compute_replace_lcc,
    compute_npv_comparison,
    monte_carlo_npv,
)
from loweconex_platform.capex.survival import SurvivalModel, WEIBULL_PARAMETERS
from loweconex_platform.capex.optimizer import KnapsackOptimizer
from loweconex_platform.capex.scorer import AssetScorer

__all__ = [
    "CapExEngine",
    "LCCEngine",
    "SurvivalModel",
    "KnapsackOptimizer",
    "AssetScorer",
    "compute_keep_lcc",
    "compute_replace_lcc",
    "compute_npv_comparison",
    "monte_carlo_npv",
    "WEIBULL_PARAMETERS",
]

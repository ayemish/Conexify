"""
Savings/ROI Engine — total savings computation, cost modeling,
attribution ledger, and financial metrics (NPV, IRR, payback).

Aligned with the FRD Section 11 rollup structure.
"""

from loweconex_platform.roi_engine.savings_engine import SavingsEngine
from loweconex_platform.roi_engine.cost_model import CostModel, ProgramCosts
from loweconex_platform.roi_engine.attribution_ledger import AttributionLedger

__all__ = [
    "SavingsEngine",
    "CostModel",
    "ProgramCosts",
    "AttributionLedger",
]

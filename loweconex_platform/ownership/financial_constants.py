"""
Shared Financial Constants — single source of truth for NPV, ROI,
and investment analysis parameters used by both the KPI Dashboard
pipeline and the Ownership Decision Support crew.

Centralising these values ensures the two views produce comparable
figures and eliminates silent drift between pipelines.
"""

# ── Discount / Time-Value ──────────────────────────────────────────
DISCOUNT_RATE: float = 0.08          # 8 % weighted-average cost of capital
HORIZON_YEARS: int = 5               # 5-year evaluation window

# ── Platform Investment ────────────────────────────────────────────
IMPLEMENTATION_COST: float = 250_000.0   # estimated platform deployment cost (USD)

# ── Time-Horizon label used by CostLineItem ────────────────────────
HORIZON_LABEL: str = "5yr"           # must match TimeHorizon enum value

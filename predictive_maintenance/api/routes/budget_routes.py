"""
Budget Management API Routes

Provides endpoints for storing and retrieving budget data:
- GET  /api/v1/budget/{site_id} — retrieve current budget for a site
- POST /api/v1/budget/{site_id} — save/update budget for a site
- GET  /api/v1/budget           — retrieve all budgets
"""

import logging
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

budget_router = APIRouter()

# ── Persistence (JSON file-backed for simplicity) ────────────────────
_BUDGET_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "budgets"
_BUDGET_DIR.mkdir(parents=True, exist_ok=True)


def _budget_path(site_id: str) -> Path:
    safe_id = site_id.replace("/", "_").replace("\\", "_")
    return _BUDGET_DIR / f"{safe_id}.json"


# ── Schemas ──────────────────────────────────────────────────────────

class LocationBudget(BaseModel):
    location_id: str
    capex: float = 0
    opex: float = 0


class AssetTypeBudget(BaseModel):
    asset_type: str
    capex: float = 0
    opex: float = 0


class BudgetData(BaseModel):
    site_id: str = "default"
    overall_capex: float = 0
    overall_opex: float = 0
    by_location: List[LocationBudget] = Field(default_factory=list)
    by_asset_type: List[AssetTypeBudget] = Field(default_factory=list)
    notes: str = ""
    updated_at: Optional[datetime] = None


class BudgetResponse(BaseModel):
    site_id: str
    budget: BudgetData
    message: str = ""


# ── Routes ───────────────────────────────────────────────────────────

@budget_router.get("/{site_id}", response_model=BudgetResponse)
async def get_budget(site_id: str):
    """Retrieve budget data for a site."""
    path = _budget_path(site_id)
    if path.exists():
        try:
            raw = json.loads(path.read_text())
            budget = BudgetData(**raw)
        except Exception as e:
            logger.warning("Failed to load budget for %s: %s", site_id, e)
            budget = BudgetData(site_id=site_id)
    else:
        budget = BudgetData(site_id=site_id)

    return BudgetResponse(site_id=site_id, budget=budget)


@budget_router.post("/{site_id}", response_model=BudgetResponse)
async def save_budget(site_id: str, budget: BudgetData):
    """Save or update budget data for a site."""
    budget.site_id = site_id
    budget.updated_at = datetime.now(timezone.utc)

    path = _budget_path(site_id)
    try:
        path.write_text(json.dumps(budget.dict(), default=str, indent=2))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save budget: {e}")

    logger.info("Budget saved for site %s: capex=$%,.0f opex=$%,.0f",
                site_id, budget.overall_capex, budget.overall_opex)

    return BudgetResponse(
        site_id=site_id,
        budget=budget,
        message="Budget saved successfully",
    )


@budget_router.get("", response_model=List[BudgetResponse])
async def list_budgets():
    """List all saved budgets."""
    results = []
    for path in sorted(_BUDGET_DIR.glob("*.json")):
        try:
            raw = json.loads(path.read_text())
            budget = BudgetData(**raw)
            results.append(BudgetResponse(site_id=budget.site_id, budget=budget))
        except Exception as e:
            logger.warning("Skipping budget file %s: %s", path.name, e)
    return results

"""
Governance & Compliance API Routes

Gap #26: Exposes all 12 loweconex_platform governance modules via REST API
so the frontend GovernanceDashboard can display their status.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

governance_api_router = APIRouter()

# All 12 governance modules with their import paths
_GOVERNANCE_MODULES = {
    "lineage":         "loweconex_platform.lineage",
    "data_quality":    "loweconex_platform.data_quality",
    "mlops":           "loweconex_platform.mlops",
    "ai_risk":         "loweconex_platform.ai_risk",
    "agent_ops":       "loweconex_platform.agent_ops",
    "security":        "loweconex_platform.security",
    "semantic":        "loweconex_platform.semantic",
    "twin_versioning": "loweconex_platform.twin_versioning",
    "mv_verification": "loweconex_platform.mv_verification",
    "operating_model": "loweconex_platform.operating_model",
    "benchmarking":    "loweconex_platform.benchmarking",
    "execution":       "loweconex_platform.execution",
}


class GovernanceModuleStatus(BaseModel):
    module_id: str
    status: str  # active, inactive, error
    version: Optional[str] = None
    error: Optional[str] = None


class GovernanceStatusResponse(BaseModel):
    modules: Dict[str, GovernanceModuleStatus]
    modules_active: List[str] = Field(default_factory=list)
    total_available: int = 0
    total_active: int = 0
    loweconex_bridge: Optional[Dict[str, Any]] = None


@governance_api_router.get("/status", response_model=GovernanceStatusResponse)
async def get_governance_status():
    """Check which governance modules are available and active."""
    modules = {}
    active_list = []

    for mod_id, import_path in _GOVERNANCE_MODULES.items():
        try:
            __import__(import_path)
            version = None
            try:
                import importlib
                m = importlib.import_module(import_path)
                version = getattr(m, "__version__", getattr(m, "VERSION", None))
            except Exception:
                pass
            modules[mod_id] = GovernanceModuleStatus(
                module_id=mod_id, status="active", version=version
            )
            active_list.append(mod_id)
        except ImportError as e:
            modules[mod_id] = GovernanceModuleStatus(
                module_id=mod_id, status="inactive", error=str(e)
            )
        except Exception as e:
            modules[mod_id] = GovernanceModuleStatus(
                module_id=mod_id, status="error", error=str(e)
            )

    # Loweconex bridge status
    bridge_status = None
    try:
        from ...services.kpi.loweconex_bridge import get_bridge_status
        bridge_status = get_bridge_status()
    except Exception:
        pass

    return GovernanceStatusResponse(
        modules=modules,
        modules_active=active_list,
        total_available=len(_GOVERNANCE_MODULES),
        total_active=len(active_list),
        loweconex_bridge=bridge_status,
    )


@governance_api_router.get("/data-quality/summary")
async def get_data_quality_summary():
    """Get data quality summary from the ISO 25012 quality engine."""
    try:
        from loweconex_platform.data_quality import DataQualityEngine
        engine = DataQualityEngine()
        return {"status": "active", "summary": engine.get_summary() if hasattr(engine, 'get_summary') else {}}
    except ImportError:
        raise HTTPException(status_code=501, detail="Data quality module not available")


@governance_api_router.get("/mlops/models")
async def get_model_registry():
    """List models from the MLOps model registry."""
    try:
        from loweconex_platform.mlops import ModelRegistry
        registry = ModelRegistry()
        models = registry.list_models() if hasattr(registry, 'list_models') else []
        return {"status": "active", "models": models}
    except ImportError:
        raise HTTPException(status_code=501, detail="MLOps module not available")


@governance_api_router.get("/ai-risk/dashboard")
async def get_ai_risk_dashboard():
    """Get AI risk assessment from the NIST AI RMF framework."""
    try:
        from loweconex_platform.ai_risk import AIRiskRegistry
        registry = AIRiskRegistry()
        risks = registry.get_risks() if hasattr(registry, 'get_risks') else []
        return {"status": "active", "risks": risks}
    except ImportError:
        raise HTTPException(status_code=501, detail="AI risk module not available")


@governance_api_router.get("/lineage/graph")
async def get_lineage_graph():
    """Get data lineage graph for audit trail."""
    try:
        from loweconex_platform.lineage import LineageTracker
        tracker = LineageTracker()
        graph = tracker.get_graph() if hasattr(tracker, 'get_graph') else {}
        return {"status": "active", "graph": graph}
    except ImportError:
        raise HTTPException(status_code=501, detail="Lineage module not available")

"""
ROI Workbook Export API Routes

Endpoints for generating and downloading the multi-tab .xlsx ROI workbook
populated from KPI agent outputs, RAG evidence, and cost parameters.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

export_router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════
# Request / Response Schemas
# ═══════════════════════════════════════════════════════════════════════


class CostLineItemSchema(BaseModel):
    cost_item: str = Field(..., description="Description of the cost line item")
    amount: float = Field(..., description="Dollar amount")
    month: int = Field(..., ge=1, le=36, description="Month in which payment occurs (1-36)")
    cost_type: str = Field(default="OPEX", description="CAPEX or OPEX")
    notes: str = Field(default="", description="Optional notes")


class ExportRequestSchema(BaseModel):
    """Request body for ROI workbook export."""
    # Scope
    tenant_id: str = Field(default="", description="Tenant ID")
    company_id: str = Field(default="", description="Company ID (all locations if blank)")
    estate_id: str = Field(default="", description="Estate ID filter")
    location_id: str = Field(default="", description="Single location ID filter")

    # Filters
    date_start: Optional[datetime] = Field(default=None, description="Start date filter")
    date_end: Optional[datetime] = Field(default=None, description="End date filter")
    asset_classes: Optional[List[str]] = Field(default=None, description="Asset class filter")
    kpi_categories: Optional[List[str]] = Field(
        default=None,
        description="KPI bucket include-list (e.g. ['Energy_Saving', 'PPM_Savings']); null = all",
    )

    # Scenario
    first_year_scenario: str = Field(
        default="Medium",
        description="Scenario driving Tab 10 First Year View (Low/Medium/High)",
    )

    # Assumptions
    currency: str = Field(default="USD")
    horizon_months: int = Field(default=36, ge=1, le=120)
    discount_rate: float = Field(default=0.08, ge=0, le=1)
    energy_price_kwh: float = Field(default=0.12, ge=0)
    labor_cost_hourly: float = Field(default=75.0, ge=0)
    refrigerant_cost_lb: float = Field(default=15.0, ge=0)
    waste_cogs_pct: float = Field(default=0.30, ge=0, le=1)

    # Rollout
    total_stores: int = Field(default=300, ge=1)
    monthly_rollout: int = Field(default=25, ge=1)
    start_month: int = Field(default=1, ge=1)

    # Costs
    cost_3yr_total: float = Field(default=2_500_000.0, ge=0, description="3-year total cost")
    monthly_license: float = Field(default=55_000.0, ge=0, description="Monthly software license")
    cost_schedule: Optional[List[CostLineItemSchema]] = Field(
        default=None,
        description="Custom payment schedule; if null, default schedule is generated",
    )

    # Site for KPI data lookup
    site_id: str = Field(
        default="default",
        description="Site ID to pull KPI dashboard data from",
    )


class ValidationIssueSchema(BaseModel):
    code: str
    message: str
    severity: str


class ExportResponseSchema(BaseModel):
    """Response metadata when export is returned inline (non-file)."""
    status: str
    validation_issues: List[ValidationIssueSchema] = Field(default_factory=list)
    kpi_row_count: int = 0
    buckets_populated: int = 0
    file_size_bytes: int = 0


# ═══════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════


@export_router.post(
    "/roi-workbook",
    response_class=Response,
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}
            },
            "description": "ROI workbook .xlsx file",
        }
    },
    summary="Generate ROI Workbook (.xlsx)",
    description=(
        "Generates a multi-tab Excel workbook with KPI savings by scenario, "
        "cost modeling, rollout schedule, and payback analysis. "
        "Data is pulled from KPI agent outputs and RAG evidence store."
    ),
)
async def export_roi_workbook(body: ExportRequestSchema):
    """Generate and return the ROI workbook as a downloadable .xlsx file."""
    try:
        from ...services.kpi.excel_export import (
            ExportRequest,
            CostLineItem,
            generate_roi_workbook,
        )
    except ImportError as e:
        raise HTTPException(
            status_code=501,
            detail=f"Excel export module not available: {e}",
        )

    # Convert Pydantic schema → dataclass
    cost_schedule = None
    if body.cost_schedule:
        cost_schedule = [
            CostLineItem(
                cost_item=c.cost_item,
                amount=c.amount,
                month=c.month,
                cost_type=c.cost_type,
                notes=c.notes,
            )
            for c in body.cost_schedule
        ]

    request = ExportRequest(
        tenant_id=body.tenant_id,
        company_id=body.company_id,
        estate_id=body.estate_id,
        location_id=body.location_id,
        date_start=body.date_start,
        date_end=body.date_end,
        asset_classes=body.asset_classes,
        kpi_categories=body.kpi_categories,
        first_year_scenario=body.first_year_scenario,
        currency=body.currency,
        horizon_months=body.horizon_months,
        discount_rate=body.discount_rate,
        energy_price_kwh=body.energy_price_kwh,
        labor_cost_hourly=body.labor_cost_hourly,
        refrigerant_cost_lb=body.refrigerant_cost_lb,
        waste_cogs_pct=body.waste_cogs_pct,
        total_stores=body.total_stores,
        monthly_rollout=body.monthly_rollout,
        start_month=body.start_month,
        cost_3yr_total=body.cost_3yr_total,
        monthly_license=body.monthly_license,
        cost_schedule=cost_schedule or [],
    )

    # Optionally pull fresh dashboard data
    dashboard_result = None
    try:
        from ..routes.kpi_fleet_routes import compute_dashboard_data

        site_id = body.site_id or body.location_id or body.company_id or "default"
        dashboard_result = compute_dashboard_data(
            site_id=site_id,
            run_scenarios=True,
        )
    except Exception as e:
        logger.warning("Live KPI computation failed, falling back to stored data: %s", e)

    # Gap #21: Enrich ROI export with CapEx engine data when available
    capex_enrichment = None
    try:
        from loweconex_platform.capex.engine import CapExEngine
        from ..routes.kpi_fleet_routes import _collect_data_from_db, _collect_health_data
        site_id = body.site_id or body.location_id or body.company_id or "default"
        asset_data, _, _, _ = _collect_data_from_db(site_id)
        if asset_data:
            capex_enrichment = {
                "capex_engine_available": True,
                "asset_count": len(asset_data),
            }
    except Exception:
        pass
    if capex_enrichment and dashboard_result:
        dashboard_result.setdefault("capex_enrichment", capex_enrichment)

    # Generate workbook
    try:
        xlsx_bytes, issues = generate_roi_workbook(request, dashboard_result)
    except Exception as e:
        logger.error("Workbook generation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Workbook generation failed: {e}")

    # Check for hard errors
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        logger.warning(
            "Export has %d validation errors: %s",
            len(errors),
            [e.message for e in errors],
        )

    # Build filename
    scope = body.company_id or body.estate_id or body.location_id or "all"
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"ROI_Workbook_{scope}_{timestamp}.xlsx"

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Validation-Warnings": str(len([i for i in issues if i.severity == "warning"])),
            "X-Validation-Errors": str(len(errors)),
        },
    )


@export_router.post(
    "/roi-workbook/validate",
    response_model=ExportResponseSchema,
    summary="Validate ROI Export (dry run)",
    description="Runs validation checks without generating the file.",
)
async def validate_roi_export(body: ExportRequestSchema):
    """Dry-run validation of the export configuration."""
    try:
        from ...services.kpi.excel_export import (
            ExportRequest,
            CostLineItem,
            KPIDataCollector,
            ROIWorkbookBuilder,
            validate_export,
            BUCKET_ORDER,
        )
    except ImportError as e:
        raise HTTPException(status_code=501, detail=f"Excel export module not available: {e}")

    cost_schedule = None
    if body.cost_schedule:
        cost_schedule = [
            CostLineItem(
                cost_item=c.cost_item,
                amount=c.amount,
                month=c.month,
                cost_type=c.cost_type,
                notes=c.notes,
            )
            for c in body.cost_schedule
        ]

    request = ExportRequest(
        tenant_id=body.tenant_id,
        company_id=body.company_id,
        estate_id=body.estate_id,
        location_id=body.location_id,
        date_start=body.date_start,
        date_end=body.date_end,
        asset_classes=body.asset_classes,
        kpi_categories=body.kpi_categories,
        first_year_scenario=body.first_year_scenario,
        currency=body.currency,
        horizon_months=body.horizon_months,
        discount_rate=body.discount_rate,
        energy_price_kwh=body.energy_price_kwh,
        labor_cost_hourly=body.labor_cost_hourly,
        refrigerant_cost_lb=body.refrigerant_cost_lb,
        waste_cogs_pct=body.waste_cogs_pct,
        total_stores=body.total_stores,
        monthly_rollout=body.monthly_rollout,
        start_month=body.start_month,
        cost_3yr_total=body.cost_3yr_total,
        monthly_license=body.monthly_license,
        cost_schedule=cost_schedule or [],
    )

    collector = KPIDataCollector()
    kpi_rows, _ = collector.collect(request)

    builder = ROIWorkbookBuilder(request)
    bucket_totals = builder._aggregate_buckets(kpi_rows)

    issues = validate_export(request, kpi_rows, bucket_totals)

    buckets_with_data = sum(
        1 for b in BUCKET_ORDER
        if any(r.kpi_bucket == b for r in kpi_rows)
    )

    return ExportResponseSchema(
        status="valid" if not any(i.severity == "error" for i in issues) else "invalid",
        validation_issues=[
            ValidationIssueSchema(code=i.code, message=i.message, severity=i.severity)
            for i in issues
        ],
        kpi_row_count=len(kpi_rows),
        buckets_populated=buckets_with_data,
    )

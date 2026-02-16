"""
ROI Workbook Excel Export Service

Generates a multi-tab .xlsx workbook populated from KPI agent outputs,
RAG-stored evidence, and cost parameters.  Reproduces the 12-tab structure:

  Inputs_Assumptions | KPI_Outputs_Raw | KPI_to_Bucket_Map | Costs_Input
  Tab1–Tab8 (KPI category sheets) | Tab9_Total_Savings_and_Costs
  Tab10_First_Year_View | Decision_Advisory

All monetary cells use Excel formulas so the workbook remains "live"
and auditable after export.
"""

import io
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from openpyxl import Workbook
from openpyxl.styles import (
    Alignment,
    Border,
    Font,
    NamedStyle,
    PatternFill,
    Side,
    numbers,
)
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# Data Contracts
# ═══════════════════════════════════════════════════════════════════════════

SCENARIO_NAMES = ("Low", "Medium", "High")

# Map the 14 KPI agent names → 8 ROI buckets
KPI_TO_BUCKET: Dict[str, str] = {
    "work_order_reduction": "Workorder_Reduction",
    "service_bureau_reduction": "3rdParty_Job_Reduction",
    "refrigerant_leak_reduction": "Gas_Leak_Reduction",
    "energy_reduction": "Energy_Saving",
    "food_waste_reduction": "Store_Manager_Productivity",
    "food_safety_compliance": "Store_Manager_Productivity",
    "food_temp_diagnostics_improvement": "Store_Manager_Productivity",
    "call_center_volume_reduction": "CC_Cost_Productivity",
    "asset_failure_prediction": "Shrink_Reduction",
    "asset_uptime_increase": "Shrink_Reduction",
    "esg_compliance": "Shrink_Reduction",
    "capex_lifecycle_optimization": "Shrink_Reduction",
    "ppm_maximization": "PPM_Savings",
    "preventive_maintenance_optimization": "PPM_Savings",
}

BUCKET_ORDER = [
    "Workorder_Reduction",
    "3rdParty_Job_Reduction",
    "Gas_Leak_Reduction",
    "Energy_Saving",
    "Store_Manager_Productivity",
    "CC_Cost_Productivity",
    "Shrink_Reduction",
    "PPM_Savings",
]

BUCKET_DISPLAY = {
    "Workorder_Reduction": "Workorder Reduction",
    "3rdParty_Job_Reduction": "3rd Party Job Reduction",
    "Gas_Leak_Reduction": "Gas Leak Reduction",
    "Energy_Saving": "Energy Saving",
    "Store_Manager_Productivity": "Store Manager Productivity",
    "CC_Cost_Productivity": "CC Cost Productivity",
    "Shrink_Reduction": "Shrink Reduction",
    "PPM_Savings": "PPM Savings",
}

TAB_SHEET_NAMES = {
    "Workorder_Reduction": "Tab1_Workorder_Reduction",
    "3rdParty_Job_Reduction": "Tab2_3rdParty_Job_Reduction",
    "Gas_Leak_Reduction": "Tab3_Gas_Leak_Reduction",
    "Energy_Saving": "Tab4_Energy_Saving",
    "Store_Manager_Productivity": "Tab5_Store_Manager_Productivity",
    "CC_Cost_Productivity": "Tab6_CC_Cost_Productivity",
    "Shrink_Reduction": "Tab7_Shrink_Reduction",
    "PPM_Savings": "Tab8_PPM_Savings",
}


@dataclass
class KPIOutputRow:
    """FR-3.1 — Minimum required fields per KPI agent output row."""
    tenant_id: str = ""
    company_id: str = ""
    estate_id: str = ""
    location_id: str = ""
    kpi_id: str = ""
    kpi_name: str = ""
    display_name: str = ""
    kpi_bucket: str = ""
    scenario: str = "Medium"          # Low | Medium | High
    horizon_months: int = 36
    total_savings_usd: float = 0.0
    run_rate_monthly_usd: float = 0.0
    confidence: float = 0.0
    ramp_profile_id: str = ""
    evidence_refs: List[str] = field(default_factory=list)
    narrative: str = ""
    assumptions: List[str] = field(default_factory=list)
    data_points_used: int = 0
    data_coverage_pct: float = 0.0
    double_count_flag: bool = False


@dataclass
class CostLineItem:
    """FR-6.2 — Payment schedule table row."""
    cost_item: str
    amount: float
    month: int            # 1-based month in which payment occurs
    cost_type: str = "OPEX"   # CAPEX | OPEX
    notes: str = ""


@dataclass
class ExportRequest:
    """Parameters controlling a single export run."""
    # Scope
    tenant_id: str = ""
    company_id: str = ""
    estate_id: str = ""
    location_id: str = ""          # nullable → company-level if blank

    # Filters
    date_start: Optional[datetime] = None
    date_end: Optional[datetime] = None
    asset_classes: Optional[List[str]] = None
    kpi_categories: Optional[List[str]] = None   # include-list; None = all

    # Scenario
    first_year_scenario: str = "Medium"   # drives Tab 10

    # Assumptions
    currency: str = "USD"
    horizon_months: int = 36
    discount_rate: float = 0.08
    energy_price_kwh: float = 0.12
    labor_cost_hourly: float = 75.0
    refrigerant_cost_lb: float = 15.0
    waste_cogs_pct: float = 0.30

    # Rollout
    total_stores: int = 300
    monthly_rollout: int = 25
    start_month: int = 1

    # Costs
    cost_3yr_total: float = 2_500_000.0
    monthly_license: float = 55_000.0
    cost_schedule: List[CostLineItem] = field(default_factory=list)


@dataclass
class ValidationIssue:
    """A single export-time validation failure."""
    code: str
    message: str
    severity: str = "error"   # error | warning


# ═══════════════════════════════════════════════════════════════════════════
# Data Collector — pulls from KPI orchestrator + RAG + DB
# ═══════════════════════════════════════════════════════════════════════════

class KPIDataCollector:
    """Collects KPI agent outputs and transforms them into ExportRows."""

    def collect(
        self,
        request: ExportRequest,
        dashboard_result: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[KPIOutputRow], List[str]]:
        """Return (rows, double_count_flags).

        Sources (in priority order):
        1. Provided dashboard_result dict (from orchestrator)
        2. KPI result repository (PostgreSQL)
        3. RAG store (evidence enrichment)
        """
        rows: List[KPIOutputRow] = []
        double_flags: List[str] = []

        scorecards = self._resolve_scorecards(request, dashboard_result)

        for sc in scorecards:
            kpi_name = sc.get("kpi_name", "")
            bucket = KPI_TO_BUCKET.get(kpi_name, "")
            if not bucket:
                logger.warning("KPI %s has no bucket mapping, skipping", kpi_name)
                continue

            # Optional category filter
            if request.kpi_categories and bucket not in request.kpi_categories:
                continue

            base_id = f"{kpi_name}_{request.company_id or 'global'}"

            # Evidence from RAG (best-effort)
            evidence_refs = self._fetch_evidence_refs(kpi_name, request)

            for scenario, savings_key in [
                ("Low", "savings_low"),
                ("Medium", "savings_medium"),
                ("High", "savings_high"),
            ]:
                annual = sc.get(savings_key, 0.0)
                # Scale annual savings to horizon
                horizon_factor = request.horizon_months / 12.0
                total_savings = annual * horizon_factor

                rows.append(KPIOutputRow(
                    tenant_id=request.tenant_id,
                    company_id=request.company_id,
                    estate_id=request.estate_id,
                    location_id=request.location_id,
                    kpi_id=f"{base_id}_{scenario}",
                    kpi_name=kpi_name,
                    display_name=sc.get("display_name", kpi_name),
                    kpi_bucket=bucket,
                    scenario=scenario,
                    horizon_months=request.horizon_months,
                    total_savings_usd=round(total_savings, 2),
                    run_rate_monthly_usd=round(total_savings / max(request.horizon_months, 1), 2),
                    confidence=sc.get("confidence", 0.0),
                    evidence_refs=evidence_refs,
                    narrative=sc.get("narrative", ""),
                    assumptions=sc.get("assumptions", []),
                    data_points_used=sc.get("data_points_used", 0),
                    data_coverage_pct=sc.get("data_coverage_pct", 0.0),
                ))

        # Check for double-count reconciliation
        if dashboard_result:
            gov = dashboard_result.get("governance", {})
            recon = gov.get("savings_reconciliation", {})
            for adj in recon.get("adjustments", []):
                double_flags.append(
                    f"{adj.get('kpi_name', '?')}: {adj.get('reason', 'overlap detected')}"
                )

        return rows, double_flags

    def _resolve_scorecards(
        self,
        request: ExportRequest,
        dashboard_result: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Get scorecards from dashboard_result or fall back to DB."""
        if dashboard_result and dashboard_result.get("scorecards"):
            return dashboard_result["scorecards"]

        # Fall back to DB
        try:
            from ...persistence.database import get_session
            from ...persistence.kpi_repository import KPIResultRepository

            site_id = request.location_id or request.estate_id or request.company_id or "default"
            with get_session() as session:
                repo = KPIResultRepository(session)
                models = repo.get_latest_for_site(site_id)
                return [
                    {
                        "kpi_name": m.kpi_name,
                        "display_name": m.display_name,
                        "category": m.category,
                        "savings_low": m.savings_low,
                        "savings_medium": m.savings_medium,
                        "savings_high": m.savings_high,
                        "confidence": m.confidence,
                        "status": m.status,
                        "narrative": m.narrative,
                        "assumptions": m.assumptions or [],
                        "data_points_used": m.data_points_used,
                        "data_coverage_pct": m.data_coverage_pct,
                    }
                    for m in models
                ]
        except Exception as e:
            logger.warning("DB fallback failed: %s", e)
            return []

    def _fetch_evidence_refs(self, kpi_name: str, request: ExportRequest) -> List[str]:
        """Retrieve evidence references from the RAG store."""
        refs: List[str] = []
        try:
            from ..rag_service import get_rag_service
            rag = get_rag_service()
            site_id = request.location_id or request.estate_id or request.company_id
            results = rag.search(
                query=f"KPI evidence {kpi_name} savings",
                site_id=site_id,
                top_k=3,
            )
            for r in results:
                refs.append(f"[{r.doc_type}] {r.doc_id} (score={r.score:.2f})")
        except Exception as e:
            logger.debug("RAG evidence lookup skipped for %s: %s", kpi_name, e)

        # Also try the advisor RAG store
        try:
            from ..advisor.rag_store import RagStore
            store = RagStore(namespace="scenario_advisor")
            results = store.search(
                query=f"{kpi_name} savings evidence",
                top_k=2,
                doc_type="scenario_result",
            )
            for r in results:
                refs.append(f"[advisor:{r.doc_type}] {r.doc_id} (score={r.score:.2f})")
        except Exception as e:
            logger.debug("Advisor RAG lookup skipped: %s", e)

        return refs


# ═══════════════════════════════════════════════════════════════════════════
# Styles
# ═══════════════════════════════════════════════════════════════════════════

_HEADER_FONT = Font(name="Calibri", bold=True, size=11, color="FFFFFF")
_HEADER_FILL = PatternFill(start_color="2F5496", end_color="2F5496", fill_type="solid")
_SUBHEADER_FILL = PatternFill(start_color="D6E4F0", end_color="D6E4F0", fill_type="solid")
_TITLE_FONT = Font(name="Calibri", bold=True, size=14, color="2F5496")
_CURRENCY_FMT = '#,##0'
_CURRENCY_DEC_FMT = '#,##0.00'
_PCT_FMT = '0.0%'
_NUM_FMT = '#,##0.0'
_THIN_BORDER = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"), bottom=Side(style="thin"),
)
_GREEN_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
_RED_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")


def _style_header_row(ws, row: int, max_col: int):
    for col in range(1, max_col + 1):
        cell = ws.cell(row=row, column=col)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _THIN_BORDER


def _style_data_cell(ws, row: int, col: int, fmt: Optional[str] = None):
    cell = ws.cell(row=row, column=col)
    cell.border = _THIN_BORDER
    cell.alignment = Alignment(horizontal="right")
    if fmt:
        cell.number_format = fmt


# ═══════════════════════════════════════════════════════════════════════════
# Workbook Builder
# ═══════════════════════════════════════════════════════════════════════════

class ROIWorkbookBuilder:
    """Builds the full multi-tab ROI workbook."""

    def __init__(self, request: ExportRequest):
        self.req = request
        self.wb = Workbook()
        # Remove default sheet
        self.wb.remove(self.wb.active)

    def _define_name(self, name: str, attr_text: str):
        """Create a workbook-scoped named range."""
        try:
            dn = DefinedName(name, attr_text=attr_text)
            self.wb.defined_names.add(dn)
        except Exception as e:
            logger.debug("Could not define name %s: %s", name, e)

    def build(
        self,
        kpi_rows: List[KPIOutputRow],
        double_count_flags: List[str],
        decision_advisory: Optional[Dict[str, Any]] = None,
    ) -> Workbook:
        """Build and return the complete workbook."""
        self._write_inputs_assumptions()
        self._write_kpi_outputs_raw(kpi_rows)
        self._write_kpi_to_bucket_map()
        self._write_costs_input()

        # Aggregate by bucket + scenario for the 8 KPI tabs
        bucket_totals = self._aggregate_buckets(kpi_rows)

        for idx, bucket in enumerate(BUCKET_ORDER, start=1):
            self._write_kpi_bucket_tab(idx, bucket, bucket_totals, kpi_rows)

        self._write_tab9(bucket_totals, double_count_flags)
        self._write_tab10(bucket_totals)
        self._write_decision_advisory(decision_advisory)

        return self.wb

    # ── Tab: Inputs_Assumptions ───────────────────────────────────────

    def _write_inputs_assumptions(self):
        ws = self.wb.create_sheet("Inputs_Assumptions")
        ws.sheet_properties.tabColor = "2F5496"
        ws.column_dimensions["A"].width = 35
        ws.column_dimensions["B"].width = 25

        ws.cell(row=1, column=1, value="ROI Workbook — Inputs & Assumptions")
        ws.cell(row=1, column=1).font = _TITLE_FONT

        params = [
            ("Currency", self.req.currency),
            ("Horizon Months", self.req.horizon_months),
            ("Discount Rate", self.req.discount_rate),
            ("Energy Price ($/kWh)", self.req.energy_price_kwh),
            ("Labor Cost ($/hr)", self.req.labor_cost_hourly),
            ("Refrigerant Cost ($/lb)", self.req.refrigerant_cost_lb),
            ("Waste COGS %", self.req.waste_cogs_pct),
            ("", ""),
            ("Rollout Parameters", ""),
            ("Total Stores", self.req.total_stores),
            ("Monthly Rollout", self.req.monthly_rollout),
            ("Start Month", self.req.start_month),
            ("", ""),
            ("Scope", ""),
            ("Company ID", self.req.company_id or "(all)"),
            ("Estate ID", self.req.estate_id or "(all)"),
            ("Location ID", self.req.location_id or "(all)"),
            ("First Year Scenario", self.req.first_year_scenario),
            ("", ""),
            ("Export Metadata", ""),
            ("Generated At", datetime.now(timezone.utc).isoformat()),
            ("Export ID", str(uuid.uuid4())[:12]),
        ]

        row = 3
        _style_header_row(ws, row, 2)
        ws.cell(row=row, column=1, value="Parameter")
        ws.cell(row=row, column=2, value="Value")
        row += 1

        for label, value in params:
            ws.cell(row=row, column=1, value=label)
            c = ws.cell(row=row, column=2, value=value)
            if isinstance(value, float) and label.endswith("%"):
                c.number_format = _PCT_FMT
            elif isinstance(value, (int, float)):
                c.number_format = _CURRENCY_FMT
            _style_data_cell(ws, row, 1)
            _style_data_cell(ws, row, 2)
            row += 1

        # Named ranges for key inputs
        self._define_name("Horizon_Months", "Inputs_Assumptions!$B$6")
        self._define_name("Total_Stores", "Inputs_Assumptions!$B$13")
        self._define_name("Monthly_Rollout", "Inputs_Assumptions!$B$14")

    # ── Tab: KPI_Outputs_Raw ──────────────────────────────────────────

    def _write_kpi_outputs_raw(self, rows: List[KPIOutputRow]):
        ws = self.wb.create_sheet("KPI_Outputs_Raw")
        ws.sheet_properties.tabColor = "548235"

        headers = [
            "kpi_id", "kpi_name", "display_name", "kpi_bucket", "scenario",
            "horizon_months", "total_savings_usd", "run_rate_monthly_usd",
            "confidence", "tenant_id", "company_id", "estate_id",
            "location_id", "evidence_refs", "narrative", "assumptions",
            "data_points_used", "data_coverage_pct", "double_count_flag",
        ]
        for col_idx, h in enumerate(headers, 1):
            ws.cell(row=1, column=col_idx, value=h)
        _style_header_row(ws, 1, len(headers))

        for r_idx, row in enumerate(rows, start=2):
            ws.cell(row=r_idx, column=1, value=row.kpi_id)
            ws.cell(row=r_idx, column=2, value=row.kpi_name)
            ws.cell(row=r_idx, column=3, value=row.display_name)
            ws.cell(row=r_idx, column=4, value=row.kpi_bucket)
            ws.cell(row=r_idx, column=5, value=row.scenario)
            ws.cell(row=r_idx, column=6, value=row.horizon_months)
            c = ws.cell(row=r_idx, column=7, value=row.total_savings_usd)
            c.number_format = _CURRENCY_FMT
            c = ws.cell(row=r_idx, column=8, value=row.run_rate_monthly_usd)
            c.number_format = _CURRENCY_FMT
            c = ws.cell(row=r_idx, column=9, value=row.confidence)
            c.number_format = "0.000"
            ws.cell(row=r_idx, column=10, value=row.tenant_id)
            ws.cell(row=r_idx, column=11, value=row.company_id)
            ws.cell(row=r_idx, column=12, value=row.estate_id)
            ws.cell(row=r_idx, column=13, value=row.location_id)
            ws.cell(row=r_idx, column=14, value="; ".join(row.evidence_refs) if row.evidence_refs else "")
            ws.cell(row=r_idx, column=15, value=row.narrative[:500] if row.narrative else "")
            ws.cell(row=r_idx, column=16, value="; ".join(row.assumptions) if row.assumptions else "")
            ws.cell(row=r_idx, column=17, value=row.data_points_used)
            c = ws.cell(row=r_idx, column=18, value=row.data_coverage_pct)
            c.number_format = _PCT_FMT
            ws.cell(row=r_idx, column=19, value="YES" if row.double_count_flag else "")

            for col in range(1, len(headers) + 1):
                _style_data_cell(ws, r_idx, col)

        # Auto-width
        for col_idx in range(1, len(headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = max(14, len(headers[col_idx - 1]) + 4)

    # ── Tab: KPI_to_Bucket_Map ────────────────────────────────────────

    def _write_kpi_to_bucket_map(self):
        ws = self.wb.create_sheet("KPI_to_Bucket_Map")
        ws.sheet_properties.tabColor = "BF8F00"

        headers = ["KPI Agent Name", "ROI Bucket", "Bucket Display Name", "Allocation Rule"]
        for c, h in enumerate(headers, 1):
            ws.cell(row=1, column=c, value=h)
        _style_header_row(ws, 1, len(headers))

        row = 2
        for kpi_name, bucket in sorted(KPI_TO_BUCKET.items()):
            ws.cell(row=row, column=1, value=kpi_name)
            ws.cell(row=row, column=2, value=bucket)
            ws.cell(row=row, column=3, value=BUCKET_DISPLAY.get(bucket, bucket))
            ws.cell(row=row, column=4, value="100% allocation")
            for c in range(1, 5):
                _style_data_cell(ws, row, c)
            row += 1

        for c in range(1, 5):
            ws.column_dimensions[get_column_letter(c)].width = 38

    # ── Tab: Costs_Input ──────────────────────────────────────────────

    def _write_costs_input(self):
        ws = self.wb.create_sheet("Costs_Input")
        ws.sheet_properties.tabColor = "C00000"

        ws.cell(row=1, column=1, value="Cost Schedule").font = _TITLE_FONT

        # Summary block
        ws.cell(row=3, column=1, value="3-Year Cost Total")
        c = ws.cell(row=3, column=2, value=self.req.cost_3yr_total)
        c.number_format = _CURRENCY_FMT
        _style_data_cell(ws, 3, 1)
        _style_data_cell(ws, 3, 2, _CURRENCY_FMT)

        ws.cell(row=4, column=1, value="Monthly License Cost")
        c = ws.cell(row=4, column=2, value=self.req.monthly_license)
        c.number_format = _CURRENCY_FMT
        _style_data_cell(ws, 4, 1)
        _style_data_cell(ws, 4, 2, _CURRENCY_FMT)

        # Payment schedule table
        headers = ["Cost Item", "Amount", "Month", "Type (CAPEX/OPEX)", "Notes"]
        header_row = 6
        for c_idx, h in enumerate(headers, 1):
            ws.cell(row=header_row, column=c_idx, value=h)
        _style_header_row(ws, header_row, len(headers))

        schedule = self.req.cost_schedule or self._default_cost_schedule()
        for r_idx, item in enumerate(schedule, start=header_row + 1):
            ws.cell(row=r_idx, column=1, value=item.cost_item)
            c = ws.cell(row=r_idx, column=2, value=item.amount)
            c.number_format = _CURRENCY_FMT
            ws.cell(row=r_idx, column=3, value=item.month)
            ws.cell(row=r_idx, column=4, value=item.cost_type)
            ws.cell(row=r_idx, column=5, value=item.notes)
            for col in range(1, 6):
                _style_data_cell(ws, r_idx, col)

        ws.column_dimensions["A"].width = 40
        ws.column_dimensions["B"].width = 18
        ws.column_dimensions["C"].width = 10
        ws.column_dimensions["D"].width = 18
        ws.column_dimensions["E"].width = 30

    def _default_cost_schedule(self) -> List[CostLineItem]:
        """Generate a default cost schedule from the 3-year total."""
        items = []
        # Monthly license for 36 months
        for m in range(1, 37):
            items.append(CostLineItem(
                cost_item="Software License",
                amount=self.req.monthly_license,
                month=m,
                cost_type="OPEX",
                notes="Monthly recurring",
            ))
        # One-time professional services (month 1)
        ps_amount = max(0, self.req.cost_3yr_total - self.req.monthly_license * 36) * 0.6
        items.append(CostLineItem(
            cost_item="Professional Services — Implementation",
            amount=round(ps_amount, 2),
            month=1,
            cost_type="CAPEX",
            notes="One-time implementation",
        ))
        # One-time support/marketing (month 2)
        sm_amount = max(0, self.req.cost_3yr_total - self.req.monthly_license * 36) * 0.4
        items.append(CostLineItem(
            cost_item="Support & Marketing Services",
            amount=round(sm_amount, 2),
            month=2,
            cost_type="CAPEX",
            notes="One-time staged",
        ))
        return items

    # ── KPI Bucket Aggregation ────────────────────────────────────────

    def _aggregate_buckets(
        self, rows: List[KPIOutputRow]
    ) -> Dict[str, Dict[str, float]]:
        """Aggregate KPI rows into {bucket: {scenario: total_savings}}."""
        totals: Dict[str, Dict[str, float]] = {}
        for b in BUCKET_ORDER:
            totals[b] = {"Low": 0.0, "Medium": 0.0, "High": 0.0}

        for row in rows:
            bucket = row.kpi_bucket
            if bucket not in totals:
                continue
            totals[bucket][row.scenario] += row.total_savings_usd

        return totals

    # ── Tab 1–8: KPI Bucket Sheets ────────────────────────────────────

    def _write_kpi_bucket_tab(
        self,
        tab_num: int,
        bucket: str,
        bucket_totals: Dict[str, Dict[str, float]],
        all_rows: List[KPIOutputRow],
    ):
        sheet_name = TAB_SHEET_NAMES[bucket]
        ws = self.wb.create_sheet(sheet_name)
        ws.sheet_properties.tabColor = "548235"

        display = BUCKET_DISPLAY[bucket]
        ws.cell(row=1, column=1, value=f"Tab {tab_num}: {display}").font = _TITLE_FONT

        # Header row
        headers = ["KPI Name", "Scenario", "Total Savings (3yr)", "Monthly Run Rate",
                    "Confidence", "Evidence", "Narrative"]
        row = 3
        for c, h in enumerate(headers, 1):
            ws.cell(row=row, column=c, value=h)
        _style_header_row(ws, row, len(headers))
        row += 1

        # Filter rows for this bucket
        bucket_rows = [r for r in all_rows if r.kpi_bucket == bucket]
        data_start_row = row

        for r in bucket_rows:
            ws.cell(row=row, column=1, value=r.display_name)
            ws.cell(row=row, column=2, value=r.scenario)
            c = ws.cell(row=row, column=3, value=r.total_savings_usd)
            c.number_format = _CURRENCY_FMT
            c = ws.cell(row=row, column=4, value=r.run_rate_monthly_usd)
            c.number_format = _CURRENCY_FMT
            c = ws.cell(row=row, column=5, value=r.confidence)
            c.number_format = "0.000"
            ws.cell(row=row, column=6, value="; ".join(r.evidence_refs[:2]) if r.evidence_refs else "")
            ws.cell(row=row, column=7, value=r.narrative[:200] if r.narrative else "")
            for col in range(1, 8):
                _style_data_cell(ws, row, col)
            row += 1

        data_end_row = row - 1

        # Summary block: 3-year savings per scenario
        row += 1
        ws.cell(row=row, column=1, value="Summary").font = Font(bold=True, size=12)
        row += 1

        summary_headers = ["Metric", "Low", "Medium", "High"]
        for c, h in enumerate(summary_headers, 1):
            ws.cell(row=row, column=c, value=h)
        _style_header_row(ws, row, len(summary_headers))
        row += 1

        savings_row = row
        ws.cell(row=row, column=1, value="3-Year Savings")
        for s_idx, scenario in enumerate(SCENARIO_NAMES):
            val = bucket_totals.get(bucket, {}).get(scenario, 0)
            c = ws.cell(row=row, column=2 + s_idx, value=val)
            c.number_format = _CURRENCY_FMT
            _style_data_cell(ws, row, 2 + s_idx, _CURRENCY_FMT)
        _style_data_cell(ws, row, 1)
        row += 1

        # Monthly run rate = 3yr / horizon
        ws.cell(row=row, column=1, value="Monthly Run Rate")
        for s_idx in range(3):
            col_letter = get_column_letter(2 + s_idx)
            # Formula referencing the savings row above
            c = ws.cell(row=row, column=2 + s_idx)
            c.value = f"={col_letter}{savings_row}/{self.req.horizon_months}"
            c.number_format = _CURRENCY_FMT
            _style_data_cell(ws, row, 2 + s_idx, _CURRENCY_FMT)
        _style_data_cell(ws, row, 1)

        # Define named ranges for Tab9 consumption
        for s_idx, scenario in enumerate(SCENARIO_NAMES):
            col_letter = get_column_letter(2 + s_idx)
            name = f"{bucket}_{scenario}_3yr"
            # Sanitize: Excel named ranges can't start with a digit
            safe_name = name.replace("3rdParty", "ThirdParty")
            self._define_name(safe_name, f"'{sheet_name}'!${col_letter}${savings_row}")

        # Column widths
        widths = [30, 12, 22, 22, 12, 40, 50]
        for i, w in enumerate(widths):
            ws.column_dimensions[get_column_letter(i + 1)].width = w

    # ── Tab 9: Total Savings and Costs ────────────────────────────────

    def _write_tab9(
        self,
        bucket_totals: Dict[str, Dict[str, float]],
        double_count_flags: List[str],
    ):
        ws = self.wb.create_sheet("Tab9_Total_Savings_Costs")
        ws.sheet_properties.tabColor = "2F5496"

        ws.cell(row=1, column=1, value="Total Savings and Costs").font = _TITLE_FONT

        headers = ["Category", "Low", "Medium", "High"]
        row = 3
        for c, h in enumerate(headers, 1):
            ws.cell(row=row, column=c, value=h)
        _style_header_row(ws, row, len(headers))

        # Category rows (FR-4.1)
        cat_start = row + 1
        for bucket in BUCKET_ORDER:
            row += 1
            display = BUCKET_DISPLAY[bucket]
            ws.cell(row=row, column=1, value=display)
            _style_data_cell(ws, row, 1)
            for s_idx, scenario in enumerate(SCENARIO_NAMES):
                val = bucket_totals.get(bucket, {}).get(scenario, 0.0)
                c = ws.cell(row=row, column=2 + s_idx, value=round(val, 2))
                c.number_format = _CURRENCY_FMT
                _style_data_cell(ws, row, 2 + s_idx, _CURRENCY_FMT)
        cat_end = row

        # Total savings (FR-4.2) — SUM formulas
        row += 1
        total_row = row
        ws.cell(row=row, column=1, value="Total Savings")
        ws.cell(row=row, column=1).font = Font(bold=True)
        for s_idx in range(3):
            col_letter = get_column_letter(2 + s_idx)
            c = ws.cell(row=row, column=2 + s_idx)
            c.value = f"=SUM({col_letter}{cat_start}:{col_letter}{cat_end})"
            c.number_format = _CURRENCY_FMT
            c.font = Font(bold=True)
            _style_data_cell(ws, row, 2 + s_idx, _CURRENCY_FMT)
        _style_data_cell(ws, row, 1)

        # 3-year cost (FR-4.3)
        row += 2
        cost_row = row
        ws.cell(row=row, column=1, value="3-Year Cost")
        _style_data_cell(ws, row, 1)
        c = ws.cell(row=row, column=2, value=self.req.cost_3yr_total)
        c.number_format = _CURRENCY_FMT
        _style_data_cell(ws, row, 2, _CURRENCY_FMT)

        # Savings-to-cost multiple (FR-4.4)
        row += 1
        ws.cell(row=row, column=1, value="Savings-to-Cost Multiple")
        _style_data_cell(ws, row, 1)
        for s_idx in range(3):
            col_letter = get_column_letter(2 + s_idx)
            c = ws.cell(row=row, column=2 + s_idx)
            c.value = f"={col_letter}{total_row}/B{cost_row}"
            c.number_format = "0.0x"
            _style_data_cell(ws, row, 2 + s_idx)

        # Monthly savings (FR-4.5)
        row += 1
        monthly_row = row
        ws.cell(row=row, column=1, value="Monthly Savings")
        _style_data_cell(ws, row, 1)
        for s_idx in range(3):
            col_letter = get_column_letter(2 + s_idx)
            c = ws.cell(row=row, column=2 + s_idx)
            c.value = f"={col_letter}{total_row}/{self.req.horizon_months}"
            c.number_format = _CURRENCY_FMT
            _style_data_cell(ws, row, 2 + s_idx, _CURRENCY_FMT)

        # Payback period (FR-4.6)
        row += 1
        ws.cell(row=row, column=1, value="Payback Period (months)")
        _style_data_cell(ws, row, 1)
        for s_idx in range(3):
            col_letter = get_column_letter(2 + s_idx)
            c = ws.cell(row=row, column=2 + s_idx)
            c.value = f"=IF({col_letter}{monthly_row}>0,B{cost_row}/{col_letter}{monthly_row},\"N/A\")"
            c.number_format = _NUM_FMT
            _style_data_cell(ws, row, 2 + s_idx, _NUM_FMT)

        # FR-4.7 — Traceability: confidence rollup
        row += 2
        ws.cell(row=row, column=1, value="Traceability — Confidence Rollup").font = Font(bold=True, size=11)
        row += 1
        ws.cell(row=row, column=1, value="Scope")
        ws.cell(row=row, column=2, value=(
            f"Company={self.req.company_id or 'all'}, "
            f"Estate={self.req.estate_id or 'all'}, "
            f"Location={self.req.location_id or 'all'}"
        ))
        row += 1
        ws.cell(row=row, column=1, value="Date Range")
        ws.cell(row=row, column=2, value=(
            f"{self.req.date_start or 'N/A'} — {self.req.date_end or 'N/A'}"
        ))

        # Double-count flags
        if double_count_flags:
            row += 2
            ws.cell(row=row, column=1, value="Double Count Flags").font = Font(bold=True, color="C00000")
            for flag in double_count_flags:
                row += 1
                ws.cell(row=row, column=1, value=flag)
                ws.cell(row=row, column=1).font = Font(color="C00000")

        ws.column_dimensions["A"].width = 32
        ws.column_dimensions["B"].width = 20
        ws.column_dimensions["C"].width = 20
        ws.column_dimensions["D"].width = 20

    # ── Tab 10: First Year View ───────────────────────────────────────

    def _write_tab10(self, bucket_totals: Dict[str, Dict[str, float]]):
        ws = self.wb.create_sheet("Tab10_First_Year_View")
        ws.sheet_properties.tabColor = "548235"
        scenario = self.req.first_year_scenario

        ws.cell(row=1, column=1, value=f"First Year View — {scenario} Scenario").font = _TITLE_FONT

        # Column layout: A=label, B=3yr, C=monthly, D..O = months 1-12
        month_cols = list(range(4, 16))  # columns D through O

        # ── Rollout schedule block (FR-5.1) ──────────────
        row = 3
        ws.cell(row=row, column=1, value="Rollout Schedule").font = Font(bold=True, size=12)
        row += 1

        headers = ["", "3 Years", "Monthly"] + [f"Month {m}" for m in range(1, 13)]
        for c, h in enumerate(headers, 1):
            ws.cell(row=row, column=c, value=h)
        _style_header_row(ws, row, len(headers))

        # Total Stores
        row += 1
        stores_row = row
        ws.cell(row=row, column=1, value="Total Stores")
        ws.cell(row=row, column=2, value=self.req.total_stores)
        _style_data_cell(ws, row, 1)
        _style_data_cell(ws, row, 2, _CURRENCY_FMT)

        # Monthly Rollout
        row += 1
        rollout_row = row
        ws.cell(row=row, column=1, value="Monthly Rollout")
        ws.cell(row=row, column=2, value=self.req.monthly_rollout)
        _style_data_cell(ws, row, 1)
        _style_data_cell(ws, row, 2, _CURRENCY_FMT)
        for m_idx, col in enumerate(month_cols):
            ws.cell(row=row, column=col, value=self.req.monthly_rollout)
            _style_data_cell(ws, row, col, _CURRENCY_FMT)

        # Cumulative Stores Deployed
        row += 1
        cum_stores_row = row
        ws.cell(row=row, column=1, value="Cumulative Stores Deployed")
        _style_data_cell(ws, row, 1)
        for m_idx, col in enumerate(month_cols):
            month_num = m_idx + 1
            cum_deployed = min(self.req.total_stores, self.req.monthly_rollout * month_num)
            ws.cell(row=row, column=col, value=cum_deployed)
            _style_data_cell(ws, row, col, _CURRENCY_FMT)

        # % Deployed
        row += 1
        pct_row = row
        ws.cell(row=row, column=1, value="% Deployed")
        _style_data_cell(ws, row, 1)
        for m_idx, col in enumerate(month_cols):
            col_letter = get_column_letter(col)
            cum_letter = get_column_letter(col)
            c = ws.cell(row=row, column=col)
            c.value = f"={cum_letter}{cum_stores_row}/$B${stores_row}"
            c.number_format = _PCT_FMT
            _style_data_cell(ws, row, col, _PCT_FMT)

        # ── KPI Savings rows (FR-5.2) ────────────────────
        row += 2
        ws.cell(row=row, column=1, value="Savings by KPI Category").font = Font(bold=True, size=12)
        row += 1
        for c, h in enumerate(headers, 1):
            ws.cell(row=row, column=c, value=h)
        _style_header_row(ws, row, len(headers))

        kpi_savings_start = row + 1
        bucket_monthly_rows = {}

        for bucket in BUCKET_ORDER:
            row += 1
            display = BUCKET_DISPLAY[bucket]
            savings_3yr = bucket_totals.get(bucket, {}).get(scenario, 0.0)
            run_rate = savings_3yr / max(self.req.horizon_months, 1)

            ws.cell(row=row, column=1, value=display)
            c = ws.cell(row=row, column=2, value=round(savings_3yr, 2))
            c.number_format = _CURRENCY_FMT
            _style_data_cell(ws, row, 2, _CURRENCY_FMT)

            c = ws.cell(row=row, column=3, value=round(run_rate, 2))
            c.number_format = _CURRENCY_FMT
            _style_data_cell(ws, row, 3, _CURRENCY_FMT)

            bucket_monthly_rows[bucket] = row
            # FR-5.2: Savings_month[m] = RunRate_monthly * %Deployed[m]
            run_rate_ref = f"$C${row}"
            for m_idx, col in enumerate(month_cols):
                pct_ref = f"{get_column_letter(col)}${pct_row}"
                c = ws.cell(row=row, column=col)
                c.value = f"={run_rate_ref}*{pct_ref}"
                c.number_format = _CURRENCY_FMT
                _style_data_cell(ws, row, col, _CURRENCY_FMT)

            _style_data_cell(ws, row, 1)

        kpi_savings_end = row

        # ── Total Savings row (FR-5.3) ───────────────────
        row += 1
        total_sav_row = row
        ws.cell(row=row, column=1, value="Total Savings")
        ws.cell(row=row, column=1).font = Font(bold=True)
        _style_data_cell(ws, row, 1)

        # 3yr total
        c = ws.cell(row=row, column=2)
        c.value = f"=SUM(B{kpi_savings_start}:B{kpi_savings_end})"
        c.number_format = _CURRENCY_FMT
        c.font = Font(bold=True)
        _style_data_cell(ws, row, 2, _CURRENCY_FMT)

        # Monthly total
        c = ws.cell(row=row, column=3)
        c.value = f"=SUM(C{kpi_savings_start}:C{kpi_savings_end})"
        c.number_format = _CURRENCY_FMT
        c.font = Font(bold=True)
        _style_data_cell(ws, row, 3, _CURRENCY_FMT)

        for m_idx, col in enumerate(month_cols):
            col_letter = get_column_letter(col)
            c = ws.cell(row=row, column=col)
            c.value = f"=SUM({col_letter}{kpi_savings_start}:{col_letter}{kpi_savings_end})"
            c.number_format = _CURRENCY_FMT
            c.font = Font(bold=True)
            _style_data_cell(ws, row, col, _CURRENCY_FMT)

        # Cumulative savings
        row += 1
        cum_sav_row = row
        ws.cell(row=row, column=1, value="Cumulative Savings")
        ws.cell(row=row, column=1).font = Font(bold=True)
        _style_data_cell(ws, row, 1)

        for m_idx, col in enumerate(month_cols):
            if m_idx == 0:
                c = ws.cell(row=row, column=col)
                c.value = f"={get_column_letter(col)}{total_sav_row}"
            else:
                prev_col_letter = get_column_letter(month_cols[m_idx - 1])
                this_col_letter = get_column_letter(col)
                c = ws.cell(row=row, column=col)
                c.value = f"={prev_col_letter}{cum_sav_row}+{this_col_letter}{total_sav_row}"
            c.number_format = _CURRENCY_FMT
            _style_data_cell(ws, row, col, _CURRENCY_FMT)

        # ── Costs block (FR-5.4) ─────────────────────────
        row += 2
        ws.cell(row=row, column=1, value="Costs").font = Font(bold=True, size=12)
        row += 1
        for c_idx, h in enumerate(headers, 1):
            ws.cell(row=row, column=c_idx, value=h)
        _style_header_row(ws, row, len(headers))

        schedule = self.req.cost_schedule or self._default_cost_schedule()

        # Aggregate costs by type for display
        license_monthly = self.req.monthly_license
        ps_by_month: Dict[int, float] = {}
        sm_by_month: Dict[int, float] = {}
        capex_total = 0.0
        opex_total = 0.0

        for item in schedule:
            if "license" in item.cost_item.lower():
                continue  # handled as recurring
            if item.cost_type == "CAPEX":
                capex_total += item.amount
                ps_by_month[item.month] = ps_by_month.get(item.month, 0) + item.amount
            else:
                opex_total += item.amount
                sm_by_month[item.month] = sm_by_month.get(item.month, 0) + item.amount

        # Software License row
        row += 1
        license_row = row
        ws.cell(row=row, column=1, value="Software License (monthly)")
        ws.cell(row=row, column=2, value=license_monthly * 36)
        ws.cell(row=row, column=2).number_format = _CURRENCY_FMT
        ws.cell(row=row, column=3, value=license_monthly)
        ws.cell(row=row, column=3).number_format = _CURRENCY_FMT
        _style_data_cell(ws, row, 1)
        _style_data_cell(ws, row, 2, _CURRENCY_FMT)
        _style_data_cell(ws, row, 3, _CURRENCY_FMT)
        for m_idx, col in enumerate(month_cols):
            ws.cell(row=row, column=col, value=license_monthly)
            ws.cell(row=row, column=col).number_format = _CURRENCY_FMT
            _style_data_cell(ws, row, col, _CURRENCY_FMT)

        # Professional Services row
        row += 1
        ps_row = row
        ws.cell(row=row, column=1, value="Professional Services (one-time)")
        _style_data_cell(ws, row, 1)
        ws.cell(row=row, column=2, value=sum(ps_by_month.values()))
        ws.cell(row=row, column=2).number_format = _CURRENCY_FMT
        _style_data_cell(ws, row, 2, _CURRENCY_FMT)
        for m_idx, col in enumerate(month_cols):
            month_num = m_idx + 1
            val = ps_by_month.get(month_num, 0)
            ws.cell(row=row, column=col, value=val)
            ws.cell(row=row, column=col).number_format = _CURRENCY_FMT
            _style_data_cell(ws, row, col, _CURRENCY_FMT)

        # Support/Marketing row
        row += 1
        sm_row = row
        ws.cell(row=row, column=1, value="Support/Marketing Services")
        _style_data_cell(ws, row, 1)
        ws.cell(row=row, column=2, value=sum(sm_by_month.values()))
        ws.cell(row=row, column=2).number_format = _CURRENCY_FMT
        _style_data_cell(ws, row, 2, _CURRENCY_FMT)
        for m_idx, col in enumerate(month_cols):
            month_num = m_idx + 1
            val = sm_by_month.get(month_num, 0)
            ws.cell(row=row, column=col, value=val)
            ws.cell(row=row, column=col).number_format = _CURRENCY_FMT
            _style_data_cell(ws, row, col, _CURRENCY_FMT)

        # Total Monthly Costs
        row += 1
        total_cost_row = row
        ws.cell(row=row, column=1, value="Total Monthly Costs")
        ws.cell(row=row, column=1).font = Font(bold=True)
        _style_data_cell(ws, row, 1)
        for m_idx, col in enumerate(month_cols):
            col_letter = get_column_letter(col)
            c = ws.cell(row=row, column=col)
            c.value = f"={col_letter}{license_row}+{col_letter}{ps_row}+{col_letter}{sm_row}"
            c.number_format = _CURRENCY_FMT
            c.font = Font(bold=True)
            _style_data_cell(ws, row, col, _CURRENCY_FMT)

        # 3yr total cost
        c = ws.cell(row=row, column=2)
        c.value = f"=B{license_row}+B{ps_row}+B{sm_row}"
        c.number_format = _CURRENCY_FMT
        c.font = Font(bold=True)
        _style_data_cell(ws, row, 2, _CURRENCY_FMT)

        # Cumulative Costs
        row += 1
        cum_cost_row = row
        ws.cell(row=row, column=1, value="Cumulative Costs")
        ws.cell(row=row, column=1).font = Font(bold=True)
        _style_data_cell(ws, row, 1)

        for m_idx, col in enumerate(month_cols):
            if m_idx == 0:
                c = ws.cell(row=row, column=col)
                c.value = f"={get_column_letter(col)}{total_cost_row}"
            else:
                prev_letter = get_column_letter(month_cols[m_idx - 1])
                this_letter = get_column_letter(col)
                c = ws.cell(row=row, column=col)
                c.value = f"={prev_letter}{cum_cost_row}+{this_letter}{total_cost_row}"
            c.number_format = _CURRENCY_FMT
            _style_data_cell(ws, row, col, _CURRENCY_FMT)

        # CAPEX / OPEX summary (FR-6.3)
        row += 1
        ws.cell(row=row, column=1, value="CAPEX Total")
        ws.cell(row=row, column=2, value=capex_total)
        ws.cell(row=row, column=2).number_format = _CURRENCY_FMT
        _style_data_cell(ws, row, 1)
        _style_data_cell(ws, row, 2, _CURRENCY_FMT)

        row += 1
        ws.cell(row=row, column=1, value="OPEX Total (12mo license)")
        ws.cell(row=row, column=2, value=license_monthly * 12)
        ws.cell(row=row, column=2).number_format = _CURRENCY_FMT
        _style_data_cell(ws, row, 1)
        _style_data_cell(ws, row, 2, _CURRENCY_FMT)

        # ── Delta and Payback (FR-5.5) ───────────────────
        row += 2
        ws.cell(row=row, column=1, value="Delta Cumulative (Savings − Costs)").font = Font(bold=True, size=12)
        row += 1
        delta_row = row
        ws.cell(row=row, column=1, value="Delta Cumulative")
        ws.cell(row=row, column=1).font = Font(bold=True)
        _style_data_cell(ws, row, 1)

        payback_found = False
        for m_idx, col in enumerate(month_cols):
            col_letter = get_column_letter(col)
            c = ws.cell(row=row, column=col)
            c.value = f"={col_letter}{cum_sav_row}-{col_letter}{cum_cost_row}"
            c.number_format = _CURRENCY_FMT
            _style_data_cell(ws, row, col, _CURRENCY_FMT)

        # Payback highlight: conditional formatting approach via static values
        # We'll compute and highlight after formulas
        row += 1
        payback_row = row
        ws.cell(row=row, column=1, value="Payback Month")
        ws.cell(row=row, column=1).font = Font(bold=True, color="2F5496")
        _style_data_cell(ws, row, 1)

        for m_idx, col in enumerate(month_cols):
            col_letter = get_column_letter(col)
            c = ws.cell(row=row, column=col)
            c.value = f'=IF({col_letter}{delta_row}>=0,"PAYBACK","")'
            _style_data_cell(ws, row, col)

        # Column widths
        ws.column_dimensions["A"].width = 35
        ws.column_dimensions["B"].width = 18
        ws.column_dimensions["C"].width = 16
        for col in month_cols:
            ws.column_dimensions[get_column_letter(col)].width = 14

    # ── Tab: Decision_Advisory ───────────────────────────────────────

    def _write_decision_advisory(self, decision_advisory: Optional[Dict[str, Any]]):
        """Write orchestrator decision advisory recommendations when available."""
        if not decision_advisory:
            return

        ws = self.wb.create_sheet("Decision_Advisory")
        ws.sheet_properties.tabColor = "2F5496"
        ws.cell(row=1, column=1, value="Decision Advisory").font = _TITLE_FONT

        narrative = decision_advisory.get("executive_narrative", "")
        if narrative:
            ws.cell(row=3, column=1, value="Executive Narrative").font = Font(bold=True, size=11)
            ws.cell(row=4, column=1, value=narrative)
            ws.cell(row=4, column=1).alignment = Alignment(wrap_text=True, vertical="top")

        recs = decision_advisory.get("strategic_recommendations", []) or []
        start_row = 6
        if narrative:
            start_row = 7

        if recs:
            headers = ["Priority", "Title", "Impact", "Savings Impact", "Rationale"]
            for c_idx, h in enumerate(headers, 1):
                ws.cell(row=start_row, column=c_idx, value=h)
            _style_header_row(ws, start_row, len(headers))

            row = start_row + 1
            for rec in recs:
                ws.cell(row=row, column=1, value=rec.get("priority", ""))
                ws.cell(row=row, column=2, value=rec.get("title", ""))
                ws.cell(row=row, column=3, value=rec.get("impact", ""))

                savings_impact = rec.get("savings_impact", 0.0)
                try:
                    savings_impact = float(savings_impact)
                except (TypeError, ValueError):
                    savings_impact = 0.0

                c = ws.cell(row=row, column=4, value=savings_impact)
                c.number_format = _CURRENCY_FMT
                ws.cell(row=row, column=5, value=rec.get("rationale", ""))

                for col in range(1, 6):
                    _style_data_cell(ws, row, col, _CURRENCY_FMT if col == 4 else None)
                    ws.cell(row=row, column=col).alignment = Alignment(
                        horizontal="left", vertical="top", wrap_text=True
                    )
                row += 1

        ws.column_dimensions["A"].width = 10
        ws.column_dimensions["B"].width = 30
        ws.column_dimensions["C"].width = 16
        ws.column_dimensions["D"].width = 18
        ws.column_dimensions["E"].width = 70


# ═══════════════════════════════════════════════════════════════════════════
# Validation (FR-7.2)
# ═══════════════════════════════════════════════════════════════════════════

def validate_export(
    request: ExportRequest,
    kpi_rows: List[KPIOutputRow],
    bucket_totals: Dict[str, Dict[str, float]],
) -> List[ValidationIssue]:
    """Run pre-export validation checks."""
    issues: List[ValidationIssue] = []

    # Check all 8 buckets present for selected scenario
    for bucket in BUCKET_ORDER:
        for scenario in SCENARIO_NAMES:
            bucket_rows = [
                r for r in kpi_rows
                if r.kpi_bucket == bucket and r.scenario == scenario
            ]
            if not bucket_rows:
                issues.append(ValidationIssue(
                    code="MISSING_BUCKET",
                    message=f"Bucket '{bucket}' has no data for scenario '{scenario}'",
                    severity="warning",
                ))

    # Horizon check
    if request.horizon_months != 36:
        issues.append(ValidationIssue(
            code="NON_STANDARD_HORIZON",
            message=f"Horizon is {request.horizon_months} months (expected 36)",
            severity="warning",
        ))

    # Tab 9 total reconciliation
    for scenario in SCENARIO_NAMES:
        computed_total = sum(
            bucket_totals.get(b, {}).get(scenario, 0) for b in BUCKET_ORDER
        )
        sum_rows = sum(
            r.total_savings_usd for r in kpi_rows if r.scenario == scenario
        )
        if abs(computed_total - sum_rows) > 0.01:
            issues.append(ValidationIssue(
                code="TOTAL_MISMATCH",
                message=(
                    f"Tab9 {scenario} total ({computed_total:,.2f}) != "
                    f"sum of raw rows ({sum_rows:,.2f})"
                ),
                severity="error",
            ))

    return issues


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════

def generate_roi_workbook(
    request: ExportRequest,
    dashboard_result: Optional[Dict[str, Any]] = None,
) -> Tuple[bytes, List[ValidationIssue]]:
    """Generate the complete ROI workbook and return (xlsx_bytes, issues).

    Parameters
    ----------
    request : ExportRequest
        Controls scope, scenario, cost, and rollout parameters.
    dashboard_result : dict, optional
        Pre-computed KPI dashboard (from orchestrator). If None,
        the collector will query the DB and RAG store.

    Returns
    -------
    tuple of (bytes, list[ValidationIssue])
        The .xlsx file content and any validation issues.
    """
    collector = KPIDataCollector()
    kpi_rows, double_flags = collector.collect(request, dashboard_result)

    builder = ROIWorkbookBuilder(request)
    bucket_totals = builder._aggregate_buckets(kpi_rows)

    # Validate
    issues = validate_export(request, kpi_rows, bucket_totals)

    # Build workbook
    decision_advisory = {}
    if dashboard_result:
        decision_advisory = dashboard_result.get("decision_advisory", {}) or {}
    wb = builder.build(kpi_rows, double_flags, decision_advisory=decision_advisory)

    # Serialize
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    return buf.getvalue(), issues

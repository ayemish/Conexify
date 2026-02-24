import io

import pytest

pytestmark = pytest.mark.optional_export
openpyxl = pytest.importorskip("openpyxl")
load_workbook = openpyxl.load_workbook

from predictive_maintenance.services.kpi.excel_export import (
    ExportRequest,
    generate_roi_workbook,
)


def _dashboard_with_minimal_scorecards():
    return {
        "scorecards": [
            {
                "kpi_name": "energy_reduction",
                "display_name": "Energy Reduction",
                "savings_low": 10_000.0,
                "savings_medium": 20_000.0,
                "savings_high": 30_000.0,
                "confidence": 0.82,
                "narrative": "Deterministic KPI baseline.",
                "assumptions": ["Baseline validated"],
                "data_points_used": 120,
                "data_coverage_pct": 0.95,
            }
        ]
    }


def test_roi_export_includes_decision_advisory_sheet_when_present():
    request = ExportRequest(company_id="site-001", location_id="site-001")
    dashboard = _dashboard_with_minimal_scorecards()
    dashboard["decision_advisory"] = {
        "executive_narrative": "Prioritize preventive maintenance at high-risk sites.",
        "strategic_recommendations": [
            {
                "priority": "P1",
                "title": "Increase PM cadence",
                "impact": "Reliability",
                "savings_impact": 15000.0,
                "rationale": "Reduces emergency dispatches and downtime.",
            }
        ],
    }

    xlsx_bytes, issues = generate_roi_workbook(request, dashboard)
    assert isinstance(xlsx_bytes, bytes)
    assert issues is not None

    wb = load_workbook(io.BytesIO(xlsx_bytes))
    assert "Decision_Advisory" in wb.sheetnames

    ws = wb["Decision_Advisory"]
    assert ws["A3"].value == "Executive Narrative"
    assert "preventive maintenance" in (ws["A4"].value or "").lower()
    assert ws["A8"].value == "P1"
    assert ws["B8"].value == "Increase PM cadence"


def test_roi_export_omits_decision_advisory_sheet_when_absent():
    request = ExportRequest(company_id="site-001", location_id="site-001")
    dashboard = _dashboard_with_minimal_scorecards()

    xlsx_bytes, _ = generate_roi_workbook(request, dashboard)
    wb = load_workbook(io.BytesIO(xlsx_bytes))
    assert "Decision_Advisory" not in wb.sheetnames

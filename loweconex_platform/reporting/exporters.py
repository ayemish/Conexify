"""
Report Exporters — JSON, PDF, and web-ready export formats.

All exporters consume the structured report dict produced by
CompositeReportBuilder and emit format-specific outputs.
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ReportExporter(ABC):
    """Base class for report exporters."""

    @abstractmethod
    def export(self, report: Dict[str, Any], output_path: str) -> str:
        """Export report and return the output file path."""
        pass


class JSONExporter(ReportExporter):
    """Export report as machine-readable JSON."""

    def export(self, report: Dict[str, Any], output_path: str) -> str:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        logger.info(f"JSON report exported to {output_path}")
        return output_path


class PDFExporter(ReportExporter):
    """
    Export report as board-ready PDF.
    
    Uses a text-based fallback if reportlab/weasyprint are not available.
    For production, integrate with a proper PDF templating library.
    """

    def export(self, report: Dict[str, Any], output_path: str) -> str:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        try:
            return self._export_with_reportlab(report, output_path)
        except ImportError:
            return self._export_text_fallback(report, output_path)

    def _export_with_reportlab(self, report: Dict[str, Any], output_path: str) -> str:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        doc = SimpleDocTemplate(output_path, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = []

        # Title
        title_style = ParagraphStyle("Title", parent=styles["Title"], fontSize=18, spaceAfter=20)
        elements.append(Paragraph("Composite ROI Report", title_style))
        elements.append(Spacer(1, 12))

        metadata = report.get("metadata", {})
        elements.append(Paragraph(f"Report ID: {metadata.get('report_id', 'N/A')}", styles["Normal"]))
        elements.append(Paragraph(f"Generated: {metadata.get('generated_ts', 'N/A')}", styles["Normal"]))
        elements.append(Spacer(1, 20))

        # Executive Summary
        exec_section = report.get("sections", {}).get("executive_summary", {})
        elements.append(Paragraph("1. Executive Summary", styles["Heading1"]))
        elements.append(Paragraph(exec_section.get("narrative", ""), styles["Normal"]))
        elements.append(Spacer(1, 12))

        # Savings table
        savings = exec_section.get("total_savings", {})
        data = [
            ["Metric", "Low", "Medium", "High"],
            [
                "Total Annual Savings",
                f"${savings.get('low', 0):,.0f}",
                f"${savings.get('medium', 0):,.0f}",
                f"${savings.get('high', 0):,.0f}",
            ],
        ]
        table = Table(data, colWidths=[2.5 * inch, 1.5 * inch, 1.5 * inch, 1.5 * inch])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 20))

        # Category breakdown
        by_cat = exec_section.get("savings_by_category", {})
        if by_cat:
            elements.append(Paragraph("Savings by Category", styles["Heading2"]))
            cat_data = [["Category", "Low", "Medium", "High"]]
            for cat, vals in sorted(by_cat.items(), key=lambda x: x[1].get("medium", 0), reverse=True):
                cat_data.append([
                    cat.replace("_", " ").title(),
                    f"${vals.get('low', 0):,.0f}",
                    f"${vals.get('medium', 0):,.0f}",
                    f"${vals.get('high', 0):,.0f}",
                ])
            cat_table = Table(cat_data, colWidths=[2.5 * inch, 1.5 * inch, 1.5 * inch, 1.5 * inch])
            cat_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            elements.append(cat_table)
            elements.append(Spacer(1, 20))

        # Remaining sections as text
        for section_key in ["estate_overview", "scenario_comparison", "methodology_appendix"]:
            section = report.get("sections", {}).get(section_key, {})
            if section:
                elements.append(Paragraph(section.get("title", section_key), styles["Heading1"]))
                narrative = section.get("narrative", "")
                if narrative:
                    elements.append(Paragraph(narrative, styles["Normal"]))
                elements.append(Spacer(1, 12))

        doc.build(elements)
        logger.info(f"PDF report exported to {output_path}")
        return output_path

    def _export_text_fallback(self, report: Dict[str, Any], output_path: str) -> str:
        """Fallback: export as formatted text file when reportlab is not available."""
        txt_path = output_path.replace(".pdf", ".txt")
        lines = []
        lines.append("=" * 70)
        lines.append("COMPOSITE ROI REPORT")
        lines.append("=" * 70)

        metadata = report.get("metadata", {})
        lines.append(f"Report ID: {metadata.get('report_id', 'N/A')}")
        lines.append(f"Generated: {metadata.get('generated_ts', 'N/A')}")
        lines.append("")

        for section_key, section in report.get("sections", {}).items():
            lines.append("-" * 50)
            lines.append(section.get("title", section_key).upper())
            lines.append("-" * 50)

            narrative = section.get("narrative", "")
            if narrative:
                lines.append(narrative)
                lines.append("")

            # Savings table
            if section_key == "executive_summary":
                savings = section.get("total_savings", {})
                lines.append(f"  Low:    ${savings.get('low', 0):>12,.0f}")
                lines.append(f"  Medium: ${savings.get('medium', 0):>12,.0f}")
                lines.append(f"  High:   ${savings.get('high', 0):>12,.0f}")
                lines.append("")

                by_cat = section.get("savings_by_category", {})
                if by_cat:
                    lines.append("  By Category:")
                    for cat, vals in sorted(by_cat.items(), key=lambda x: x[1].get("medium", 0), reverse=True):
                        lines.append(f"    {cat:<35s} ${vals.get('medium', 0):>10,.0f}")
                    lines.append("")

            lines.append("")

        Path(txt_path).parent.mkdir(parents=True, exist_ok=True)
        with open(txt_path, "w") as f:
            f.write("\n".join(lines))
        logger.info(f"Text report exported to {txt_path} (PDF library not available)")
        return txt_path


class WebExporter(ReportExporter):
    """Export report as web-ready HTML with interactive elements."""

    def export(self, report: Dict[str, Any], output_path: str) -> str:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        html = self._build_html(report)
        with open(output_path, "w") as f:
            f.write(html)
        logger.info(f"Web report exported to {output_path}")
        return output_path

    def _build_html(self, report: Dict[str, Any]) -> str:
        metadata = report.get("metadata", {})
        sections = report.get("sections", {})
        exec_summary = sections.get("executive_summary", {})
        savings = exec_summary.get("total_savings", {})
        by_cat = exec_summary.get("savings_by_category", {})

        cat_rows = ""
        for cat, vals in sorted(by_cat.items(), key=lambda x: x[1].get("medium", 0), reverse=True):
            cat_rows += f"""
            <tr>
                <td>{cat.replace('_', ' ').title()}</td>
                <td class="num">${vals.get('low', 0):,.0f}</td>
                <td class="num highlight">${vals.get('medium', 0):,.0f}</td>
                <td class="num">${vals.get('high', 0):,.0f}</td>
            </tr>"""

        kpi_cards = ""
        kpi_dives = sections.get("kpi_deep_dives", {}).get("kpis", {})
        for kpi_name, kpi_data in kpi_dives.items():
            status_class = "approved" if kpi_data.get("qa_status") == "approved" else "rejected"
            kpi_cards += f"""
            <div class="kpi-card {status_class}">
                <h3>{kpi_data.get('title', kpi_name)}</h3>
                <div class="savings">${kpi_data.get('savings', {}).get('medium', 0):,.0f}</div>
                <div class="confidence">Confidence: {kpi_data.get('confidence', 0):.0%}</div>
                <div class="status">{kpi_data.get('qa_status', 'N/A')}</div>
            </div>"""

        scenario_section = sections.get("scenario_comparison", {})
        scenario_rows = ""
        for name, s_data in scenario_section.get("scenarios", {}).items():
            scenario_rows += f"""
            <tr>
                <td><strong>{name.title()}</strong></td>
                <td class="num">${s_data.get('total_savings_medium', 0):,.0f}</td>
            </tr>"""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Composite ROI Report</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f7fa; color: #333; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 2rem; }}
        h1 {{ color: #1a365d; margin-bottom: 0.5rem; }}
        h2 {{ color: #2d3748; margin: 2rem 0 1rem; border-bottom: 2px solid #e2e8f0; padding-bottom: 0.5rem; }}
        .meta {{ color: #718096; margin-bottom: 2rem; }}
        .summary-box {{ background: white; border-radius: 12px; padding: 2rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 2rem; }}
        .big-number {{ font-size: 2.5rem; font-weight: 700; color: #2b6cb0; }}
        .label {{ font-size: 0.875rem; color: #718096; text-transform: uppercase; letter-spacing: 0.05em; }}
        table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin: 1rem 0; }}
        th {{ background: #2d3748; color: white; padding: 0.75rem 1rem; text-align: left; }}
        td {{ padding: 0.75rem 1rem; border-bottom: 1px solid #e2e8f0; }}
        .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
        .highlight {{ font-weight: 700; color: #2b6cb0; }}
        .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 1rem; margin: 1rem 0; }}
        .kpi-card {{ background: white; border-radius: 8px; padding: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border-left: 4px solid #48bb78; }}
        .kpi-card.rejected {{ border-left-color: #f56565; }}
        .kpi-card h3 {{ font-size: 0.95rem; margin-bottom: 0.5rem; }}
        .kpi-card .savings {{ font-size: 1.5rem; font-weight: 700; color: #2b6cb0; }}
        .kpi-card .confidence {{ font-size: 0.8rem; color: #718096; }}
        .kpi-card .status {{ font-size: 0.75rem; text-transform: uppercase; margin-top: 0.5rem; }}
        .narrative {{ background: #edf2f7; padding: 1rem; border-radius: 8px; margin: 1rem 0; font-style: italic; }}
    </style>
</head>
<body>
<div class="container">
    <h1>Composite ROI Report</h1>
    <div class="meta">
        Report ID: {metadata.get('report_id', '')} |
        Generated: {metadata.get('generated_ts', '')}
    </div>

    <div class="summary-box">
        <div class="label">Total Annual Savings (Medium Estimate)</div>
        <div class="big-number">${savings.get('medium', 0):,.0f}</div>
        <div style="margin-top:0.5rem; color:#718096;">
            Range: ${savings.get('low', 0):,.0f} — ${savings.get('high', 0):,.0f}
        </div>
    </div>

    <div class="narrative">{exec_summary.get('narrative', '')}</div>

    <h2>Savings by Category</h2>
    <table>
        <tr><th>Category</th><th>Low</th><th>Medium</th><th>High</th></tr>
        {cat_rows}
        <tr style="font-weight:700; background:#edf2f7;">
            <td>TOTAL</td>
            <td class="num">${savings.get('low', 0):,.0f}</td>
            <td class="num highlight">${savings.get('medium', 0):,.0f}</td>
            <td class="num">${savings.get('high', 0):,.0f}</td>
        </tr>
    </table>

    <h2>KPI Scorecards</h2>
    <div class="kpi-grid">{kpi_cards}</div>

    <h2>Scenario Comparison</h2>
    <table>
        <tr><th>Scenario</th><th>Total Savings (Medium)</th></tr>
        {scenario_rows}
    </table>

    <h2>Methodology</h2>
    <div class="narrative">
        Analysis grounded in ISO 23247, ISO 55000, IPMVP/ASHRAE Guideline 14,
        EPA Section 608, FDA Food Code, and GHG Protocol standards.
        Double-counting resolved via attribution ledger with configurable policy.
    </div>
</div>
</body>
</html>"""


class PPTXExporter(ReportExporter):
    """
    Export report as a PowerPoint presentation (PPTX).

    Requires python-pptx. Falls back to a text summary if not available.
    Slides:
        1. Title + metadata
        2. Executive summary (savings table)
        3. KPI scorecards grid
        4. Scenario comparison
        5. Location ranking
        6. Methodology note
    """

    def export(self, report: Dict[str, Any], output_path: str) -> str:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            return self._export_pptx(report, output_path)
        except ImportError:
            return self._export_fallback(report, output_path)

    def _export_pptx(self, report: Dict[str, Any], output_path: str) -> str:
        from pptx import Presentation
        from pptx.util import Inches, Pt, Emu
        from pptx.enum.text import PP_ALIGN

        prs = Presentation()
        prs.slide_width = Inches(13.33)
        prs.slide_height = Inches(7.5)
        metadata = report.get("metadata", {})
        sections = report.get("sections", {})
        exec_summary = sections.get("executive_summary", {})
        savings = exec_summary.get("total_savings", {})
        by_cat = exec_summary.get("savings_by_category", {})

        # --- Slide 1: Title ---
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        slide.shapes.title.text = "Composite ROI Report"
        slide.placeholders[1].text = (
            f"Report ID: {metadata.get('report_id', 'N/A')}\n"
            f"Generated: {metadata.get('generated_ts', 'N/A')}"
        )

        # --- Slide 2: Executive Summary ---
        slide = prs.slides.add_slide(prs.slide_layouts[5])  # blank
        slide.shapes.title.text = "Executive Summary"
        left, top, width, height = Inches(0.5), Inches(1.5), Inches(12), Inches(1)
        txBox = slide.shapes.add_textbox(left, top, width, height)
        tf = txBox.text_frame
        tf.text = exec_summary.get("narrative", "")
        for p in tf.paragraphs:
            p.font.size = Pt(14)

        # Savings table
        rows_count = 2 + len(by_cat)
        table_shape = slide.shapes.add_table(
            rows_count, 4, Inches(0.5), Inches(3), Inches(10), Inches(0.4 * rows_count)
        )
        tbl = table_shape.table
        for ci, hdr in enumerate(["Category", "Low", "Medium", "High"]):
            tbl.cell(0, ci).text = hdr
        row_idx = 1
        for cat, vals in sorted(by_cat.items(), key=lambda x: x[1].get("medium", 0), reverse=True):
            tbl.cell(row_idx, 0).text = cat.replace("_", " ").title()
            tbl.cell(row_idx, 1).text = f"${vals.get('low', 0):,.0f}"
            tbl.cell(row_idx, 2).text = f"${vals.get('medium', 0):,.0f}"
            tbl.cell(row_idx, 3).text = f"${vals.get('high', 0):,.0f}"
            row_idx += 1
        tbl.cell(row_idx, 0).text = "TOTAL"
        tbl.cell(row_idx, 1).text = f"${savings.get('low', 0):,.0f}"
        tbl.cell(row_idx, 2).text = f"${savings.get('medium', 0):,.0f}"
        tbl.cell(row_idx, 3).text = f"${savings.get('high', 0):,.0f}"

        # --- Slide 3: KPI Scorecards ---
        kpi_dives = sections.get("kpi_deep_dives", {}).get("kpis", {})
        if kpi_dives:
            slide = prs.slides.add_slide(prs.slide_layouts[5])
            slide.shapes.title.text = "KPI Scorecards"
            kpi_rows = 1 + len(kpi_dives)
            tbl_shape = slide.shapes.add_table(
                kpi_rows, 4, Inches(0.5), Inches(1.5), Inches(10), Inches(0.35 * kpi_rows)
            )
            kt = tbl_shape.table
            for ci, hdr in enumerate(["KPI", "Savings (Med)", "Confidence", "Status"]):
                kt.cell(0, ci).text = hdr
            for ri, (kname, kdata) in enumerate(kpi_dives.items(), 1):
                kt.cell(ri, 0).text = kdata.get("title", kname)
                kt.cell(ri, 1).text = f"${kdata.get('savings', {}).get('medium', 0):,.0f}"
                kt.cell(ri, 2).text = f"{kdata.get('confidence', 0):.0%}"
                kt.cell(ri, 3).text = kdata.get("qa_status", "N/A")

        # --- Slide 4: Scenario Comparison ---
        scenario_section = sections.get("scenario_comparison", {})
        scenario_data = scenario_section.get("scenarios", {})
        if scenario_data:
            slide = prs.slides.add_slide(prs.slide_layouts[5])
            slide.shapes.title.text = "Scenario Comparison"
            s_rows = 1 + len(scenario_data)
            st = slide.shapes.add_table(
                s_rows, 2, Inches(2), Inches(1.5), Inches(8), Inches(0.4 * s_rows)
            ).table
            st.cell(0, 0).text = "Scenario"
            st.cell(0, 1).text = "Total Savings (Medium)"
            for ri, (sname, sdata) in enumerate(scenario_data.items(), 1):
                st.cell(ri, 0).text = sname.title()
                st.cell(ri, 1).text = f"${sdata.get('total_savings_medium', 0):,.0f}"

        # --- Slide 5: Location Ranking ---
        loc_ranking = sections.get("location_ranking", {})
        ranked = loc_ranking.get("ranked_locations", [])
        if ranked:
            slide = prs.slides.add_slide(prs.slide_layouts[5])
            slide.shapes.title.text = "Location Ranking"
            lr = 1 + min(len(ranked), 20)
            lt = slide.shapes.add_table(
                lr, 4, Inches(0.5), Inches(1.5), Inches(10), Inches(0.35 * lr)
            ).table
            for ci, hdr in enumerate(["Rank", "Location", "Savings (Med)", "Score"]):
                lt.cell(0, ci).text = hdr
            for ri, loc in enumerate(ranked[:20], 1):
                lt.cell(ri, 0).text = str(ri)
                lt.cell(ri, 1).text = loc.get("location_id", "")
                lt.cell(ri, 2).text = f"${loc.get('savings_medium', 0):,.0f}"
                lt.cell(ri, 3).text = f"{loc.get('composite_score', 0):.2f}"

        # --- Slide 6: Methodology ---
        slide = prs.slides.add_slide(prs.slide_layouts[5])
        slide.shapes.title.text = "Methodology & Governance"
        txBox = slide.shapes.add_textbox(Inches(0.5), Inches(1.5), Inches(12), Inches(4))
        tf = txBox.text_frame
        tf.word_wrap = True
        meth = sections.get("methodology_appendix", {})
        tf.text = meth.get("narrative", (
            "Analysis grounded in ISO 23247, ISO 55000, IPMVP/ASHRAE Guideline 14, "
            "EPA Section 608, FDA Food Code, and GHG Protocol standards. "
            "Double-counting resolved via attribution ledger."
        ))

        prs.save(output_path)
        logger.info(f"PPTX report exported to {output_path}")
        return output_path

    def _export_fallback(self, report: Dict[str, Any], output_path: str) -> str:
        """Fallback when python-pptx is not installed — write JSON instead."""
        fallback_path = output_path.replace(".pptx", "_pptx_fallback.json")
        Path(fallback_path).parent.mkdir(parents=True, exist_ok=True)
        with open(fallback_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        logger.warning(f"python-pptx not installed; wrote JSON fallback to {fallback_path}")
        return fallback_path

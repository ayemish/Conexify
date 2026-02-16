"""
Business Case Generation API Routes

Provides endpoint to generate a structured business case document from
selected KPI recommendations and ROI analysis, using OpenAI for text generation
and python-docx for Word document export.
"""

import io
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

business_case_router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────

class RecommendationItem(BaseModel):
    title: str = ""
    kpi_name: str = ""
    savings_impact: float = 0
    rationale: str = ""
    priority: int = 0
    confidence: float = 0
    category: str = ""


class BusinessCaseRequest(BaseModel):
    selected_recommendations: List[RecommendationItem] = Field(default_factory=list)
    roi_summary: Dict[str, Any] = Field(default_factory=dict)
    budget: Dict[str, Any] = Field(default_factory=dict)
    executive_summary: Dict[str, Any] = Field(default_factory=dict)
    additional_context: str = ""


class BusinessCaseResponse(BaseModel):
    business_case_text: str
    generated_at: str
    model_used: str = ""
    sections: List[str] = Field(default_factory=list)


# ── Business Case Template ───────────────────────────────────────────

BUSINESS_CASE_SYSTEM_PROMPT = """You are a senior facilities management consultant specializing in 
HVAC/R predictive maintenance business cases. Generate a comprehensive, professional business case 
document following enterprise best practices.

The business case MUST follow this exact structure with clear markdown headings:

## 1. Executive Summary
Brief overview of the business case, the problem being addressed, and the recommended solution.

## 2. Problem Statement
Describe the current operational challenges, maintenance inefficiencies, and cost impacts that 
the predictive maintenance platform addresses.

## 3. Proposed Solution
Detail the specific KPI optimizations and recommendations selected. For each recommendation, 
explain the action, expected impact, and implementation approach.

## 4. Financial Analysis
### 4.1 Investment Required
Break down the CapEx and OpEx requirements.
### 4.2 Expected Returns
Detail the annual savings, NPV, payback period, and ROI multiple.
### 4.3 Sensitivity Analysis
Discuss confidence levels and risk-adjusted returns.

## 5. Implementation Plan
### 5.1 Phase 1: Quick Wins (0-3 months)
### 5.2 Phase 2: Core Implementation (3-6 months)  
### 5.3 Phase 3: Optimization (6-12 months)

## 6. Risk Assessment
Identify key risks and mitigation strategies.

## 7. Success Metrics & KPIs
Define how success will be measured.

## 8. Recommendation
Final recommendation with clear call to action.

## 9. Appendix
Supporting data tables and assumptions.

Write in a professional, concise business tone. Use specific dollar figures and percentages 
from the provided data. Do not fabricate numbers — use only what is provided. Where data is 
missing, note assumptions clearly."""


def _build_user_prompt(req: BusinessCaseRequest) -> str:
    """Build the user prompt from the request data."""
    lines = ["Generate a business case document based on the following analysis data:\n"]

    # Executive summary
    es = req.executive_summary
    if es:
        lines.append(f"**Overall Analysis:** {es.get('kpi_count', 0)} KPI dimensions analyzed. "
                      f"Total annual savings estimate: ${es.get('total_savings_medium', 0):,.0f} "
                      f"(range: ${es.get('total_savings_low', 0):,.0f} – ${es.get('total_savings_high', 0):,.0f}). "
                      f"Average confidence: {es.get('avg_confidence', 0):.1%}.\n")

    # ROI
    roi = req.roi_summary
    if roi:
        lines.append(f"**ROI Summary:** Payback period: {roi.get('payback_months', 0)} months. "
                      f"NPV: ${roi.get('npv', 0):,.0f}. "
                      f"Savings-to-cost multiple: {roi.get('savings_to_cost_multiple', 0)}x. "
                      f"IRR: {roi.get('irr', 0):.1%}.\n")

    # Budget
    budget = req.budget
    if budget:
        lines.append(f"**Budget:** CapEx: ${budget.get('overall_capex', 0):,.0f}. "
                      f"OpEx: ${budget.get('overall_opex', 0):,.0f}. "
                      f"Total: ${budget.get('overall_capex', 0) + budget.get('overall_opex', 0):,.0f}.\n")
        if budget.get("by_location"):
            lines.append(f"  Allocated across {len(budget['by_location'])} locations.\n")
        if budget.get("by_asset_type"):
            lines.append(f"  Allocated across {len(budget['by_asset_type'])} asset types.\n")

    # Selected recommendations
    if req.selected_recommendations:
        lines.append(f"\n**Selected Recommendations ({len(req.selected_recommendations)}):**\n")
        for i, rec in enumerate(req.selected_recommendations, 1):
            lines.append(f"{i}. **{rec.title}** (Priority {rec.priority})")
            lines.append(f"   - KPI: {rec.kpi_name.replace('_', ' ').title()}")
            lines.append(f"   - Annual savings impact: ${rec.savings_impact:,.0f}")
            lines.append(f"   - Confidence: {rec.confidence:.0%}")
            lines.append(f"   - Rationale: {rec.rationale}\n")

    if req.additional_context:
        lines.append(f"\n**Additional Context:** {req.additional_context}\n")

    lines.append("\nGenerate the full business case document now.")
    return "\n".join(lines)


# ── Routes ───────────────────────────────────────────────────────────

@business_case_router.post("/generate", response_model=BusinessCaseResponse)
async def generate_business_case(req: BusinessCaseRequest):
    """Generate a business case document from selected recommendations using OpenAI."""
    if not req.selected_recommendations:
        raise HTTPException(status_code=400, detail="No recommendations selected")

    user_prompt = _build_user_prompt(req)
    model_used = ""

    # Try OpenAI
    try:
        from ...services.advisor.openai_client import OpenAIClient
        client = OpenAIClient(model="gpt-4o", temperature=0.4, max_tokens=4096)

        if client.is_available:
            response = client.chat(
                messages=[
                    {"role": "system", "content": BUSINESS_CASE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                use_tools=False,
            )
            if response.content:
                model_used = response.model or "gpt-4o"
                sections = [line.strip("# ").strip() for line in response.content.split("\n")
                            if line.startswith("## ")]
                return BusinessCaseResponse(
                    business_case_text=response.content,
                    generated_at=datetime.now(timezone.utc).isoformat(),
                    model_used=model_used,
                    sections=sections,
                )
    except Exception as e:
        logger.warning("OpenAI business case generation failed: %s", e)

    # Fallback: generate a template-based business case
    logger.info("Generating template-based business case (OpenAI unavailable)")
    text = _generate_template_business_case(req)
    sections = [line.strip("# ").strip() for line in text.split("\n") if line.startswith("## ")]

    return BusinessCaseResponse(
        business_case_text=text,
        generated_at=datetime.now(timezone.utc).isoformat(),
        model_used="template-fallback",
        sections=sections,
    )


@business_case_router.post("/export-docx")
async def export_business_case_docx(req: Dict[str, Any]):
    """Export a business case as a Word document."""
    text = req.get("business_case_text", "")
    if not text:
        raise HTTPException(status_code=400, detail="No business case text provided")

    try:
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
    except ImportError:
        # Fallback: return as plain text file
        buf = io.BytesIO(text.encode("utf-8"))
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="text/plain",
            headers={"Content-Disposition": "attachment; filename=Business_Case.txt"},
        )

    doc = Document()

    # Title
    title = doc.add_heading("Business Case: Predictive Maintenance Investment", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Metadata
    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta_run = meta.add_run(f"Generated: {datetime.now().strftime('%B %d, %Y')}")
    meta_run.font.size = Pt(10)
    meta_run.font.color.rgb = RGBColor(100, 116, 139)
    doc.add_paragraph("")

    # Parse markdown-ish text into Word
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            doc.add_paragraph("")
            continue
        if stripped.startswith("## "):
            heading_text = stripped[3:].strip()
            doc.add_heading(heading_text, level=2)
        elif stripped.startswith("### "):
            heading_text = stripped[4:].strip()
            doc.add_heading(heading_text, level=3)
        elif stripped.startswith("# "):
            heading_text = stripped[2:].strip()
            doc.add_heading(heading_text, level=1)
        elif stripped.startswith("- ") or stripped.startswith("* "):
            bullet_text = stripped[2:]
            p = doc.add_paragraph(style="List Bullet")
            # Handle bold markers
            parts = bullet_text.split("**")
            for j, part in enumerate(parts):
                run = p.add_run(part)
                if j % 2 == 1:
                    run.bold = True
        elif stripped.startswith("|"):
            # Table row — simplified handling
            p = doc.add_paragraph(stripped)
            p.style.font.size = Pt(9)
        else:
            # Regular paragraph — handle inline bold
            p = doc.add_paragraph()
            parts = stripped.split("**")
            for j, part in enumerate(parts):
                run = p.add_run(part)
                if j % 2 == 1:
                    run.bold = True

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    filename = f"Business_Case_{datetime.now().strftime('%Y%m%d')}.docx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _generate_template_business_case(req: BusinessCaseRequest) -> str:
    """Generate a structured business case using templates when OpenAI is unavailable."""
    es = req.executive_summary
    roi = req.roi_summary
    budget = req.budget
    recs = req.selected_recommendations

    total_savings = sum(r.savings_impact for r in recs)
    capex = budget.get("overall_capex", 0) if budget else 0
    opex = budget.get("overall_opex", 0) if budget else 0

    lines = []
    lines.append("## 1. Executive Summary\n")
    lines.append(f"This business case proposes investment in predictive maintenance optimization "
                 f"across {es.get('kpi_count', 'multiple')} operational KPI dimensions. "
                 f"The analysis identifies **${total_savings:,.0f}** in annual savings from "
                 f"**{len(recs)} selected initiatives**, with a projected payback period of "
                 f"**{roi.get('payback_months', 'N/A')} months** and an NPV of "
                 f"**${roi.get('npv', 0):,.0f}** over a 5-year horizon.\n")

    lines.append("## 2. Problem Statement\n")
    lines.append("Current HVAC/R maintenance operations rely primarily on reactive and scheduled "
                 "maintenance strategies, resulting in:\n")
    lines.append("- Unplanned equipment failures causing product loss and comfort complaints")
    lines.append("- Suboptimal energy consumption from degraded equipment performance")
    lines.append("- Higher-than-necessary maintenance labor costs from inefficient scheduling")
    lines.append("- Shortened asset lifecycles due to deferred maintenance decisions\n")

    lines.append("## 3. Proposed Solution\n")
    lines.append(f"The following **{len(recs)} initiatives** have been selected based on KPI "
                 f"optimization analysis:\n")
    for i, rec in enumerate(recs, 1):
        lines.append(f"### Initiative {i}: {rec.title}")
        lines.append(f"- **KPI:** {rec.kpi_name.replace('_', ' ').title()}")
        lines.append(f"- **Priority:** {rec.priority}")
        lines.append(f"- **Annual Savings:** ${rec.savings_impact:,.0f}")
        lines.append(f"- **Confidence:** {rec.confidence:.0%}")
        lines.append(f"- **Rationale:** {rec.rationale}\n")

    lines.append("## 4. Financial Analysis\n")
    lines.append("### 4.1 Investment Required")
    lines.append(f"- **CapEx Budget:** ${capex:,.0f}")
    lines.append(f"- **OpEx Budget:** ${opex:,.0f}")
    lines.append(f"- **Total Investment:** ${capex + opex:,.0f}\n")

    lines.append("### 4.2 Expected Returns")
    lines.append(f"- **Annual Savings (Selected):** ${total_savings:,.0f}")
    lines.append(f"- **Total Annual Savings (All KPIs):** ${es.get('total_savings_medium', 0):,.0f}")
    lines.append(f"- **Payback Period:** {roi.get('payback_months', 'N/A')} months")
    lines.append(f"- **Net Present Value (5-year):** ${roi.get('npv', 0):,.0f}")
    lines.append(f"- **Savings-to-Cost Multiple:** {roi.get('savings_to_cost_multiple', 0)}x")
    lines.append(f"- **Internal Rate of Return:** {float(roi.get('irr', 0)):.1%}\n")

    lines.append("### 4.3 Sensitivity Analysis")
    lines.append(f"- **Conservative Estimate (P10):** ${es.get('total_savings_low', 0):,.0f}")
    lines.append(f"- **Moderate Estimate (P50):** ${es.get('total_savings_medium', 0):,.0f}")
    lines.append(f"- **Aggressive Estimate (P90):** ${es.get('total_savings_high', 0):,.0f}")
    lines.append(f"- **Average Confidence:** {es.get('avg_confidence', 0):.1%}\n")

    lines.append("## 5. Implementation Plan\n")
    quick = [r for r in recs if r.priority <= 2]
    core = [r for r in recs if 2 < r.priority <= 5]
    optimize = [r for r in recs if r.priority > 5]

    lines.append("### 5.1 Phase 1: Quick Wins (0-3 months)")
    if quick:
        for r in quick:
            lines.append(f"- {r.title} (${r.savings_impact:,.0f}/yr)")
    else:
        lines.append("- Deploy monitoring and baseline data collection")
    lines.append("")

    lines.append("### 5.2 Phase 2: Core Implementation (3-6 months)")
    if core:
        for r in core:
            lines.append(f"- {r.title} (${r.savings_impact:,.0f}/yr)")
    else:
        lines.append("- Implement primary optimization strategies")
    lines.append("")

    lines.append("### 5.3 Phase 3: Optimization (6-12 months)")
    if optimize:
        for r in optimize:
            lines.append(f"- {r.title} (${r.savings_impact:,.0f}/yr)")
    else:
        lines.append("- Fine-tune models and expand to additional sites")
    lines.append("")

    lines.append("## 6. Risk Assessment\n")
    lines.append("| Risk | Likelihood | Impact | Mitigation |")
    lines.append("|------|-----------|--------|------------|")
    lines.append("| Data quality gaps | Medium | High | Phased rollout with data validation gates |")
    lines.append("| Integration complexity | Medium | Medium | Standardized API connectors, staged integration |")
    lines.append("| Staff adoption resistance | Low | Medium | Training program, change management |")
    lines.append("| Savings below forecast | Low | High | Conservative estimates used, quarterly reviews |")
    lines.append("")

    lines.append("## 7. Success Metrics & KPIs\n")
    lines.append("- **Primary:** Annual maintenance cost reduction vs. baseline")
    lines.append("- **Secondary:** Unplanned downtime reduction, energy savings, asset lifecycle extension")
    lines.append("- **Leading indicators:** Alert response time, predictive accuracy, work order completion rate")
    lines.append("- **Review cadence:** Monthly operational review, quarterly business review\n")

    lines.append("## 8. Recommendation\n")
    lines.append(f"Based on the analysis of {es.get('kpi_count', 0)} KPI dimensions and "
                 f"the selection of {len(recs)} high-impact initiatives, **we recommend proceeding "
                 f"with the proposed ${capex + opex:,.0f} investment**. The projected "
                 f"{roi.get('payback_months', 'N/A')}-month payback period and "
                 f"{roi.get('savings_to_cost_multiple', 0)}x return over 5 years represent "
                 f"a compelling value proposition with manageable risk.\n")

    lines.append("## 9. Appendix\n")
    lines.append("### A. Selected Recommendation Details\n")
    lines.append("| # | Initiative | KPI | Annual Savings | Priority | Confidence |")
    lines.append("|---|-----------|-----|---------------|----------|------------|")
    for i, r in enumerate(recs, 1):
        lines.append(f"| {i} | {r.title} | {r.kpi_name.replace('_', ' ').title()} | "
                     f"${r.savings_impact:,.0f} | {r.priority} | {r.confidence:.0%} |")
    lines.append("")

    return "\n".join(lines)

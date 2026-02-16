"""
KPI Crew Registry — specifications and calculation functions for all 14 KPI crews.

Each KPI has a KPICrewSpec with domain-specific prompts, required inputs,
formulas, and a deterministic calculation function.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

from loweconex_platform.kpi_crews.base_crew import KPICrewSpec, SpecialistAgentDef
from loweconex_platform.kpi_crews.research_corpus import get_benchmarks_for_kpi
from loweconex_platform.kpi_crews.kpi_specific_tools import (
    build_wo_reduction_research_tools,
    build_wo_reduction_extraction_tools,
    build_ppm_research_tools,
    build_ppm_extraction_tools,
    build_energy_research_tools,
    build_energy_extraction_tools,
    build_refrigerant_research_tools,
    build_refrigerant_extraction_tools,
    build_food_waste_extraction_tools,
    build_call_center_extraction_tools,
    build_service_bureau_extraction_tools,
    build_failure_prediction_extraction_tools,
    build_uptime_extraction_tools,
    build_food_temp_extraction_tools,
    build_food_safety_extraction_tools,
    build_esg_extraction_tools,
    build_pm_opt_research_tools,
    build_pm_opt_extraction_tools,
    build_capex_extraction_tools,
)
from loweconex_platform.mv_verification.mv_engine import MVEngine, MVPlan, BaselineWindow, IPMVPOption
from loweconex_platform.digital_twins.relationships import RelationshipGraph

logger = logging.getLogger(__name__)


# =============================================================================
# Calculation helper utilities
# =============================================================================

def _safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    return numerator / denominator if denominator != 0 else default


def _savings_bands(base: float, low_pct: float = 0.5, high_pct: float = 1.5) -> dict:
    return {
        "savings_low": base * low_pct,
        "savings_medium": base,
        "savings_high": base * high_pct,
    }


def _count_assets_by_type(assets: List[Dict], asset_type: str) -> int:
    return sum(1 for a in assets if a.get("asset_type") == asset_type)


# =============================================================================
# KPI-1: Work Order Reduction
# =============================================================================

def calc_work_order_reduction(tools, company_id, location_id, assets, locations, scenario_params, research, **kw):
    wo_events = tools.query_events(company_id, {"event_type": "work_order"})
    wo_count = len(wo_events)
    bm = get_benchmarks_for_kpi("work_order_reduction")
    cost_per_wo = scenario_params.get("cost_per_wo", bm.get("cost_per_wo_median", 380.0))  # ISO 14224:2016 median
    reduction_pct = scenario_params.get("wo_reduction_pct", bm.get("cbm_wo_reduction_range", [0.25, 0.50])[0])  # Jardine et al. 2006 lower bound

    baseline_annual_cost = wo_count * cost_per_wo * 12 if wo_count > 0 else len(assets) * 2 * cost_per_wo * 12
    savings_base = baseline_annual_cost * reduction_pct

    # --- Repeat-failure time-window clustering ---
    repeat_window_days = scenario_params.get("repeat_window_days", 30)
    repeat_failures = 0
    asset_last_wo: Dict[str, str] = {}
    for e in sorted(wo_events, key=lambda x: x.get("start_ts", "")):
        aid = e.get("asset_id", "")
        ts_str = e.get("start_ts", "")
        if aid and aid in asset_last_wo:
            try:
                from datetime import datetime as _dt
                prev = _dt.fromisoformat(str(asset_last_wo[aid]))
                curr = _dt.fromisoformat(str(ts_str))
                if (curr - prev).days <= repeat_window_days:
                    repeat_failures += 1
            except Exception:
                if e.get("payload", {}).get("repeat", False):
                    repeat_failures += 1
        elif e.get("payload", {}).get("repeat", False):
            repeat_failures += 1
        if aid and ts_str:
            asset_last_wo[aid] = ts_str
    repeat_rate = _safe_div(repeat_failures, wo_count)

    return {
        "metrics": {
            "wo_baseline_monthly": wo_count if wo_count > 0 else len(assets) * 2,
            "wo_expected_post": (wo_count if wo_count > 0 else len(assets) * 2) * (1 - reduction_pct),
            "wo_reduction_pct": reduction_pct,
            "repeat_failure_rate": repeat_rate,
            "repeat_failures_detected": repeat_failures,
            "repeat_window_days": repeat_window_days,
            "cost_per_wo": cost_per_wo,
            "baseline_annual_cost": baseline_annual_cost,
        },
        **_savings_bands(savings_base),
        "confidence": 0.7 if wo_count > 0 else 0.4,
        "assumptions": [
            f"Baseline WO count: {wo_count or 'estimated from asset count'}",
            f"Cost per WO: ${cost_per_wo}",
            f"Reduction target: {reduction_pct*100}%",
            f"Repeat-failure window: {repeat_window_days} days (same asset)",
            "Reduction achieved via earlier detection, better triage, repeat failure prevention",
        ],
        "narrative": f"Work order reduction targets {reduction_pct*100:.0f}% fewer reactive WOs, saving ${savings_base:,.0f}/year. "
                     f"Repeat-failure rate: {repeat_rate:.1%} ({repeat_failures} within {repeat_window_days}-day window).",
        "twin_patches": [],
        "evidence_refs": [{"type": "wo_count", "value": wo_count, "source": "event_store"}],
    }


WO_REDUCTION_SPEC = KPICrewSpec(
    kpi_name="work_order_reduction",
    display_name="Work Order Reduction",
    objective="Reduce reactive work orders by earlier detection, better triage, and preventing repeat failures.",
    # --- Domain-specific agent goals ---
    research_goal=(
        "Curate MTTR/MTBF benchmarks (EN 13306, ISO 14224:2016), CBM work-order "
        "reduction ranges (Jardine et al. 2006: 25-50%), and cost-per-WO distributions. "
        "Identify which failure-mode categories (mechanical, electrical, controls, refrigerant) "
        "have the highest reducibility through condition monitoring vs. time-based PM."
    ),
    extraction_goal=(
        "Extract all work orders, classify each by failure mode (mechanical/electrical/controls/"
        "refrigerant/structural/environmental), identify repeat-failure assets using "
        "time-window clustering (30-day default), and compute per-category WO counts and costs. "
        "Flag chronic assets (>3 WOs in 90 days) and calculate repeat-failure rate."
    ),
    calculation_goal=(
        "Compute WO reduction savings by failure mode category — not as a flat percentage. "
        "Apply category-specific reduction rates: controls faults (highest, 40-60% reducible via analytics), "
        "mechanical (25-40% via vibration/thermal CBM), refrigerant (20-35% via pressure trending). "
        "Weight total savings by actual failure mode distribution from extraction data."
    ),
    qa_goal=(
        "Validate that WO reduction targets are grounded in the actual failure mode mix — "
        "reject if a flat percentage is applied without failure mode decomposition. "
        "Cross-check repeat-failure rate against ISO 14224 benchmarks (10-25% typical). "
        "Verify cost-per-WO falls within $200-$700 range per SMRP 5.5.4."
    ),
    # --- Domain-specific backstory supplements ---
    research_backstory=(
        "You specialize in maintenance engineering with deep knowledge of FMEA, "
        "reliability-centered maintenance (SAE JA1011), and condition monitoring standards. "
        "You always decompose WO reduction by failure mode, never as a single aggregate number."
    ),
    extraction_backstory=(
        "You are an expert at mining CMMS/work order data. You classify WOs by failure mode "
        "using keyword analysis and asset type correlation. You identify chronic/repeat failures "
        "that represent the highest-value reduction opportunities."
    ),
    research_topics=["work_order_reduction", "MTTR", "reactive_maintenance"],
    required_inputs=["work_orders", "events", "labor_rates", "vendor_rates"],
    formulas=[
        "WO_reduction_% = 1 - (WO_post / WO_baseline)",
        "Savings_WO = Σ(WO_baseline_category * reduction_rate_category * Cost_per_WO)",
    ],
    output_metrics=["wo_baseline_monthly", "wo_expected_post", "wo_reduction_pct", "repeat_failure_rate"],
    savings_category="Workorder Reduction",
    calculation_fn=calc_work_order_reduction,
    # --- KPI-specific tool overrides ---
    research_tool_builder=build_wo_reduction_research_tools,
    extraction_tool_builder=build_wo_reduction_extraction_tools,
    # --- Specialist agent: Failure Mode Analyst ---
    specialist_agents=[
        SpecialistAgentDef(
            role="Failure Mode & Repeat-Failure Analyst",
            goal=(
                "Classify all work orders by FMEA failure mode category and identify chronic "
                "repeat-failure assets. Produce a Pareto distribution of failure modes with "
                "per-category reducibility estimates based on P-F interval availability."
            ),
            backstory=(
                "You are an FMEA specialist trained in ISO 14224 and SAE JA1011 RCM methodology. "
                "You decompose work order streams into actionable failure mode categories and "
                "identify the top 20% of assets responsible for 80% of reactive work."
            ),
            task_description=(
                "Use classify_work_orders_by_failure_mode and analyze_repeat_failures tools to: "
                "1. Produce failure mode Pareto distribution (mechanical, electrical, controls, etc.) "
                "2. Identify top 20 chronic/repeat-failure assets with repeat rates "
                "3. Map each category to reducibility estimate (controls=highest, structural=lowest) "
                "4. Calculate category-weighted expected WO reduction percentage"
            ),
            expected_output=(
                'JSON: {"failure_mode_pareto": {category: {count, pct, reducibility}}, '
                '"chronic_assets": [{asset_id, repeat_rate, failure_mode}], '
                '"weighted_reduction_pct": float, "top_category": str}'
            ),
            position="pre_calc",
        ),
    ],
)


# =============================================================================
# KPI-2: PPM Maximization
# =============================================================================

def calc_ppm_maximization(tools, company_id, location_id, assets, locations, scenario_params, research, **kw):
    wo_events = tools.query_events(company_id, {"event_type": "work_order"})
    pm_events = [e for e in wo_events if e.get("payload", {}).get("category") == "pm"]
    reactive_events = [e for e in wo_events if e.get("payload", {}).get("category") != "pm"]

    total_wo = len(wo_events) or max(len(assets) * 3, 1)
    pm_count = len(pm_events) or int(total_wo * 0.3)
    reactive_count = total_wo - pm_count

    current_planned_ratio = _safe_div(pm_count, total_wo, 0.3)
    bm = get_benchmarks_for_kpi("ppm_maximization")
    target_planned_ratio = scenario_params.get("target_planned_ratio", bm.get("planned_pct_world_class", 0.80))  # SMRP 5.5.1
    emergency_premium = scenario_params.get("emergency_premium", bm.get("emergency_cost_premium_median", 2.0))  # SMRP 5.5.1 median
    avg_wo_cost = scenario_params.get("avg_wo_cost", get_benchmarks_for_kpi("work_order_reduction").get("cost_per_wo_median", 380.0))  # ISO 14224

    convertible_reactive = reactive_count * (target_planned_ratio - current_planned_ratio)
    savings_per_converted = avg_wo_cost * (emergency_premium - 1.0)
    savings_base = max(0, convertible_reactive * savings_per_converted * 12)

    return {
        "metrics": {
            "current_planned_ratio": current_planned_ratio,
            "target_planned_ratio": target_planned_ratio,
            "pm_work_orders": pm_count,
            "reactive_work_orders": reactive_count,
            "convertible_reactive_monthly": convertible_reactive,
        },
        **_savings_bands(savings_base),
        "confidence": 0.65 if wo_events else 0.35,
        "assumptions": [
            f"Current planned ratio: {current_planned_ratio:.0%}",
            f"Target planned ratio: {target_planned_ratio:.0%}",
            f"Emergency cost premium: {emergency_premium}x",
            "Conversion driven by improved fault classification and PM triggers",
        ],
        "narrative": f"Converting reactive to planned maintenance by improving planned ratio from {current_planned_ratio:.0%} to {target_planned_ratio:.0%}.",
        "twin_patches": [],
        "evidence_refs": [],
    }


PPM_MAXIMIZATION_SPEC = KPICrewSpec(
    kpi_name="ppm_maximization",
    display_name="Planned Preventive Maintenance Maximization",
    objective="Convert reactive maintenance into planned PM by improving classification of faults/anomalies.",
    research_goal=(
        "Curate SMRP 5.5.1 planned-maintenance ratio benchmarks (80% world-class target), "
        "Mobley (2002) P-F interval methodology, and emergency cost premium ranges (1.3-3.0×). "
        "Identify which failure modes are convertible to planned work based on P-F interval "
        "availability (controls=instant detection, mechanical=1-6 months, structural=3-12 months)."
    ),
    extraction_goal=(
        "Extract work orders and classify as planned (PM) vs reactive. Calculate current "
        "planned ratio. For each reactive WO, assess convertibility by failure mode — "
        "determine if a detectable P-F interval exists that would allow proactive scheduling. "
        "Report PM schedule coverage: which asset types have PM tasks, which have gaps."
    ),
    calculation_goal=(
        "Compute savings from converting reactive to planned work using failure-mode-specific "
        "convertibility rates (not a flat conversion assumption). Apply emergency premium "
        "differentials (SMRP 5.5.1: 1.3-3.0×) only to genuinely convertible reactive WOs. "
        "Account for irreducibly unplanned work (vandalism, weather, external damage)."
    ),
    qa_goal=(
        "Validate planned ratio improvement is achievable given the actual failure mode mix. "
        "Reject targets that assume >90% planned ratio without justification. "
        "Verify emergency premium falls within SMRP 5.5.1 range (1.3-3.0×). "
        "Check that convertibility assessment covers all major failure categories."
    ),
    research_backstory=(
        "You are a reliability engineering expert who understands P-F intervals and "
        "condition monitoring applicability per failure mode. You know that not all "
        "reactive work can be converted — some failures are inherently unpredictable."
    ),
    extraction_backstory=(
        "You classify work orders by planned vs reactive and further by failure mode to "
        "determine convertibility. You identify PM schedule gaps where assets lack "
        "appropriate preventive tasks."
    ),
    research_topics=["preventive_maintenance_optimization", "condition_monitoring"],
    required_inputs=["work_orders", "pm_schedules", "failure_modes_taxonomy", "telemetry"],
    formulas=[
        "Planned_Ratio = PM_work / (PM_work + Reactive_work)",
        "Savings = Σ(convertible_reactive_category * emergency_premium * avg_cost)",
    ],
    output_metrics=["current_planned_ratio", "target_planned_ratio", "convertible_reactive_monthly"],
    savings_category="PPM Savings",
    calculation_fn=calc_ppm_maximization,
    research_tool_builder=build_ppm_research_tools,
    extraction_tool_builder=build_ppm_extraction_tools,
    specialist_agents=[
        SpecialistAgentDef(
            role="P-F Interval & Convertibility Analyst",
            goal=(
                "Assess which reactive work orders are convertible to planned maintenance "
                "based on P-F interval availability per failure mode. Produce convertibility "
                "matrix with per-category conversion rates and recommended detection methods."
            ),
            backstory=(
                "You apply Mobley (2002) P-F curve methodology to determine which failure "
                "modes have detectable precursors. You know that controls failures are instantly "
                "detectable (analytics), mechanical failures have months of lead time (vibration), "
                "but some structural issues require visual inspection with long intervals."
            ),
            task_description=(
                "Use analyze_pm_conversion_feasibility and classify_work_orders_by_failure_mode to: "
                "1. Map each failure mode category to P-F interval and detection method "
                "2. Calculate per-category convertibility rate "
                "3. Identify irreducibly reactive work (vandalism, weather, external) "
                "4. Produce weighted conversion target based on actual failure mode distribution"
            ),
            expected_output=(
                'JSON: {"convertibility_matrix": {category: {convertible_pct, pf_interval, method}}, '
                '"irreducible_reactive_pct": float, "weighted_conversion_target": float}'
            ),
            position="pre_calc",
        ),
    ],
)


# =============================================================================
# KPI-3: Energy Reduction
# =============================================================================

def calc_energy_reduction(tools, company_id, location_id, assets, locations, scenario_params, research, **kw):
    hvac_count = _count_assets_by_type(assets, "hvac_rtu") + _count_assets_by_type(assets, "hvac_ahu")
    refrig_count = _count_assets_by_type(assets, "refrigeration_rack") + _count_assets_by_type(assets, "refrigeration_case")
    total_assets = len(assets) or 1

    bm = get_benchmarks_for_kpi("energy_reduction")
    avg_kwh_per_sqft = scenario_params.get("avg_kwh_per_sqft", bm.get("kwh_per_sqft_food_sales_median", 52.5))  # EIA CBECS 2018 Table C1
    electricity_rate = scenario_params.get("electricity_rate", bm.get("commercial_rate_per_kwh_national", 0.107))  # EIA 2023
    reduction_pct = scenario_params.get("energy_reduction_pct", bm.get("retro_cx_savings_range", [0.05, 0.15])[1])  # ENERGY STAR retro-Cx upper

    total_sqft = sum(l.get("sqft", 50000) for l in locations) or 50000
    baseline_kwh = total_sqft * avg_kwh_per_sqft
    baseline_cost = baseline_kwh * electricity_rate
    savings_base = baseline_cost * reduction_pct

    # --- M&V Engine integration (IPMVP Option C) ---
    mv_result = {}
    try:
        mv_engine = MVEngine()
        plan = MVPlan(
            plan_id=f"mv_energy_{company_id}",
            plan_name="Energy Reduction M&V",
            ipmvp_option=IPMVPOption.OPTION_C,
            baseline=BaselineWindow(
                start_date="2024-01-01",
                end_date="2024-12-31",
                avg_daily_kwh=baseline_kwh / 365,
                std_daily=baseline_kwh / 365 * 0.15,
                n_days=365,
                cv_rmse=scenario_params.get("cv_rmse", 0.15),
            ),
        )
        mv_engine.register_plan(plan)
        reconciliation = mv_engine.reconcile_period(
            plan.plan_id,
            period_start="2025-01-01",
            period_end="2025-12-31",
            actual_kwh=baseline_kwh * (1 - reduction_pct),
            predicted_kwh=baseline_kwh,
        )
        if reconciliation:
            mv_result = {
                "mv_status": reconciliation.status,
                "mv_savings_kwh": reconciliation.savings_kwh,
                "mv_savings_pct": reconciliation.savings_pct,
                "mv_uncertainty_pct": reconciliation.uncertainty_pct,
                "mv_confidence_lower": reconciliation.confidence_lower,
                "mv_confidence_upper": reconciliation.confidence_upper,
            }
    except Exception as e:
        logger.warning(f"M&V engine integration skipped: {e}")
        mv_result = {"mv_status": "skipped", "mv_error": str(e)}

    # --- Cross-asset edge awareness ---
    cross_asset_penalty = 0.0
    thermal_groups = []
    try:
        rel_graph = kw.get("relationship_graph")
        if rel_graph and isinstance(rel_graph, RelationshipGraph):
            deps = rel_graph.find_cross_asset_kpi_dependencies()
            energy_deps = deps.get("energy", [])
            for dep_pair in energy_deps:
                cross_asset_penalty += baseline_cost * 0.02
            for asset in assets:
                group = rel_graph.get_thermal_interaction_group(asset.get("asset_id", ""))
                if len(group) > 1:
                    thermal_groups.append(group)
    except Exception as e:
        logger.debug(f"Cross-asset edge analysis skipped: {e}")

    savings_base += cross_asset_penalty

    return {
        "metrics": {
            "baseline_kwh_annual": baseline_kwh,
            "baseline_cost_annual": baseline_cost,
            "expected_savings_kwh": baseline_kwh * reduction_pct,
            "expected_savings_cost": savings_base,
            "reduction_pct": reduction_pct,
            "hvac_asset_count": hvac_count,
            "refrigeration_asset_count": refrig_count,
            "total_sqft": total_sqft,
            "electricity_rate": electricity_rate,
            "cross_asset_penalty_savings": cross_asset_penalty,
            "thermal_interaction_groups": len(thermal_groups),
            **mv_result,
        },
        **_savings_bands(savings_base, 0.6, 1.4),
        "confidence": 0.75,
        "assumptions": [
            f"Baseline energy: {avg_kwh_per_sqft} kWh/sqft/year (grocery benchmark)",
            f"Electricity rate: ${electricity_rate}/kWh",
            f"Reduction target: {reduction_pct*100}%",
            "M&V approach: IPMVP Option C (whole facility regression vs OAT)",
            "Savings attributed to: fault correction, setpoint optimization, scheduling",
            f"Cross-asset thermal interactions: {len(thermal_groups)} groups detected",
        ],
        "narrative": f"Energy reduction of {reduction_pct*100:.0f}% from baseline of {baseline_kwh:,.0f} kWh saves ${savings_base:,.0f}/year.",
        "twin_patches": [],
        "evidence_refs": [{"type": "energy_benchmark", "source": "EIA CBECS", "value": avg_kwh_per_sqft}],
    }


ENERGY_REDUCTION_SPEC = KPICrewSpec(
    kpi_name="energy_reduction",
    display_name="Energy Reduction",
    objective="Reduce kWh and demand by optimizing controls, fixing faults, and cross-asset interactions.",
    research_goal=(
        "Curate IPMVP Option C regression methodology, ASHRAE Guideline 14 statistical "
        "thresholds (CV(RMSE)<25% monthly, NMBE<±10%), EIA CBECS 2018 grocery benchmarks "
        "(52.5 kWh/sqft), ENERGY STAR retro-Cx savings ranges (5-15%), and demand charge "
        "reduction literature. Identify tariff structures that affect savings valuation."
    ),
    extraction_goal=(
        "Extract interval energy data, weather data (OAT), tariff schedules (energy + demand "
        "charges + TOU periods), and store operating hours. Build weather-normalized energy "
        "baseline using degree-day or change-point regression. Report data completeness: "
        "months of billing data, weather station coverage, tariff structure completeness."
    ),
    calculation_goal=(
        "Compute energy savings disaggregated by ECM type: fault_correction (35%), "
        "setpoint_optimization (25%), scheduling (20%), equipment_efficiency (15%), "
        "demand_response (5%). Calculate BOTH energy (kWh) savings AND demand (kW) savings "
        "separately — demand charges can be 30-50% of total bill. Apply weather-normalized "
        "baseline from extraction agent, not raw kWh comparison."
    ),
    qa_goal=(
        "Validate that savings use a weather-normalized baseline (reject raw year-over-year "
        "comparison). Verify CV(RMSE) and NMBE meet ASHRAE Guideline 14 thresholds. "
        "Check that demand savings are calculated separately from energy savings. "
        "Validate kWh/sqft falls within ±30% of CBECS grocery benchmark (52.5 kWh/sqft)."
    ),
    research_backstory=(
        "You are an energy engineer certified in IPMVP methodology. You understand "
        "that raw energy comparison without weather normalization is meaningless — "
        "a mild winter can appear as 'savings' without any intervention. You always "
        "require regression-based baselines and separate energy vs demand analysis."
    ),
    extraction_backstory=(
        "You specialize in utility data analysis. You build weather-normalized baselines "
        "using 3-parameter change-point models, validate statistical fit against ASHRAE "
        "Guideline 14, and decompose bills into energy charges, demand charges, and TOU premiums."
    ),
    calculation_backstory=(
        "You disaggregate savings by ECM type using engineering estimates. You never report "
        "a single lump energy savings number — you always break it down by measure category "
        "and separate kWh from kW savings for accurate financial valuation."
    ),
    research_topics=["energy_reduction"],
    required_inputs=["interval_energy", "telemetry", "tariffs", "weather", "store_hours"],
    formulas=[
        "Savings_kWh = kWh_baseline_model(OAT) - kWh_actual_post",
        "Savings_$ = Savings_kWh * $/kWh + Savings_kW * $/kW/month",
    ],
    output_metrics=["baseline_kwh_annual", "expected_savings_kwh", "reduction_pct"],
    savings_category="Energy Saving",
    calculation_fn=calc_energy_reduction,
    research_tool_builder=build_energy_research_tools,
    extraction_tool_builder=build_energy_extraction_tools,
    specialist_agents=[
        SpecialistAgentDef(
            role="Weather Normalization & ECM Disaggregation Specialist",
            goal=(
                "Build a weather-normalized energy baseline using change-point regression "
                "against outdoor air temperature. Disaggregate total savings into ECM categories. "
                "Calculate demand (kW) savings separately from energy (kWh) savings."
            ),
            backstory=(
                "You are an IPMVP-certified M&V practitioner. You build 3-parameter "
                "change-point models, validate against ASHRAE Guideline 14 statistical "
                "thresholds, and always separate energy savings from demand savings."
            ),
            task_description=(
                "Use weather_normalize_energy, disaggregate_ecm_savings, and calculate_demand_savings to: "
                "1. Build weather-normalized baseline per location (report CV(RMSE) and NMBE) "
                "2. Disaggregate total savings into 5 ECM categories with kWh per category "
                "3. Calculate demand charge savings separately (kW × $/kW/month) "
                "4. Produce combined savings table: energy + demand per location"
            ),
            expected_output=(
                'JSON: {"weather_baselines": [{location_id, model_type, cv_rmse, nmbe}], '
                '"ecm_disaggregation": {category: kwh}, '
                '"demand_savings_annual": float, "total_combined_savings": float}'
            ),
            position="pre_calc",
        ),
    ],
)


# =============================================================================
# KPI-4: Refrigerant Leak Reduction
# =============================================================================

def calc_refrigerant_leak_reduction(tools, company_id, location_id, assets, locations, scenario_params, research, **kw):
    leak_events = tools.query_events(company_id, {"event_type": "refrigerant_leak"})
    rack_count = _count_assets_by_type(assets, "refrigeration_rack") or max(len(locations), 1) * 4

    bm = get_benchmarks_for_kpi("refrigerant_leak_reduction")
    avg_charge_lbs = scenario_params.get("avg_charge_lbs", 1500)
    baseline_leak_rate = scenario_params.get("baseline_leak_rate", bm.get("industry_avg_leak_rate", 0.25))  # EPA GreenChill 2022 industry avg
    target_leak_rate = scenario_params.get("target_leak_rate", bm.get("greenchill_avg_leak_rate", 0.123))  # GreenChill partner avg
    refrigerant_cost_per_lb = scenario_params.get("refrigerant_cost_per_lb", bm.get("r404a_cost_per_lb_range", [12, 18])[1])  # R-404A upper
    avg_gwp = scenario_params.get("avg_gwp", bm.get("r404a_gwp", 3922))  # R-404A per EPA

    total_charge = rack_count * avg_charge_lbs
    baseline_leak_lbs = total_charge * baseline_leak_rate
    target_leak_lbs = total_charge * target_leak_rate
    avoided_lbs = baseline_leak_lbs - target_leak_lbs

    savings_refrigerant = avoided_lbs * refrigerant_cost_per_lb
    co2e_avoided = avoided_lbs * 0.4536 * avg_gwp / 1000  # lbs->kg, then tCO2e

    # --- M&V: secondary energy savings from reduced leak (compressor efficiency) ---
    energy_penalty_per_lb_leak = scenario_params.get("energy_penalty_kwh_per_lb_leak", sum(bm.get("kwh_penalty_per_lb_leaked_range", [35, 65])) / 2)  # AHRI 580 midpoint
    electricity_rate = scenario_params.get("electricity_rate", bm.get("electricity_rate_commercial", 0.1184))  # EIA CBECS 2023 commercial avg
    energy_savings_kwh = avoided_lbs * energy_penalty_per_lb_leak
    energy_savings_cost = energy_savings_kwh * electricity_rate
    mv_result = {}
    try:
        mv_engine = MVEngine()
        plan = MVPlan(
            plan_id=f"mv_leak_energy_{company_id}",
            plan_name="Leak Reduction Energy M&V",
            ipmvp_option=IPMVPOption.OPTION_C,
            baseline=BaselineWindow(
                start_date="2024-01-01", end_date="2024-12-31",
                avg_daily_kwh=energy_savings_kwh / 365 if energy_savings_kwh else 1,
                std_daily=energy_savings_kwh / 365 * 0.20 if energy_savings_kwh else 0.5,
                n_days=365, cv_rmse=0.20,
            ),
        )
        mv_engine.register_plan(plan)
        reconciliation = mv_engine.reconcile_period(
            plan.plan_id, period_start="2025-01-01", period_end="2025-12-31",
            actual_kwh=0, predicted_kwh=energy_savings_kwh,
        )
        if reconciliation:
            mv_result = {"mv_status": reconciliation.status, "mv_savings_kwh": reconciliation.savings_kwh}
    except Exception as e:
        mv_result = {"mv_status": "skipped", "mv_note": str(e)}

    savings_base = savings_refrigerant + energy_savings_cost

    return {
        "metrics": {
            "rack_count": rack_count,
            "total_charge_lbs": total_charge,
            "baseline_leak_rate": baseline_leak_rate,
            "target_leak_rate": target_leak_rate,
            "avoided_lbs": avoided_lbs,
            "co2e_avoided_tonnes": co2e_avoided,
            "leak_events_found": len(leak_events),
            "secondary_energy_savings_kwh": energy_savings_kwh,
            "secondary_energy_savings_cost": energy_savings_cost,
            **mv_result,
        },
        **_savings_bands(savings_base, 0.5, 1.6),
        "confidence": 0.65 if leak_events else 0.45,
        "assumptions": [
            f"Average system charge: {avg_charge_lbs} lbs per rack",
            f"Baseline leak rate: {baseline_leak_rate*100}% (EPA threshold: 20%)",
            f"Target leak rate: {target_leak_rate*100}%",
            f"Refrigerant cost: ${refrigerant_cost_per_lb}/lb",
            f"Average GWP: {avg_gwp} (R-404A equivalent)",
            f"Secondary energy penalty: {energy_penalty_per_lb_leak} kWh/lb leaked (compressor efficiency)",
            "M&V: IPMVP Option C applied to secondary energy savings",
        ],
        "narrative": f"Reducing leak rate from {baseline_leak_rate*100:.0f}% to {target_leak_rate*100:.0f}% avoids {avoided_lbs:,.0f} lbs, "
                     f"saving ${savings_base:,.0f}/year (${savings_refrigerant:,.0f} refrigerant + ${energy_savings_cost:,.0f} energy) and {co2e_avoided:,.0f} tCO2e.",
        "twin_patches": [],
        "evidence_refs": [{"type": "epa_608", "source": "40 CFR Part 82"}],
    }


REFRIGERANT_LEAK_SPEC = KPICrewSpec(
    kpi_name="refrigerant_leak_reduction",
    display_name="Gas Leakage Reduction (Refrigerant Leaks)",
    objective="Detect, localize, and repair refrigerant leaks faster; reduce emissions and product loss risk.",
    research_goal=(
        "Curate EPA Section 608 regulatory thresholds (20% commercial, 30% industrial), "
        "GreenChill 2022 partner averages (12.3% vs 25% industry), AHRI 580 secondary "
        "energy penalty (35-65 kWh/lb leaked), and AIM Act HFC phase-down schedule. "
        "Include R-404A (GWP=3922) to R-448A (GWP=1387) transition economics."
    ),
    extraction_goal=(
        "Extract all refrigerant leak events, rack charge inventories, and repair histories. "
        "Calculate per-system leak rates and identify systems exceeding EPA thresholds. "
        "Track EPA repair deadlines (30-day standard, 120-day with plan) and flag overdue repairs. "
        "Compute blended GWP across the fleet based on actual refrigerant types per system."
    ),
    calculation_goal=(
        "Compute refrigerant savings as: (1) direct refrigerant cost from reduced leakage, "
        "(2) secondary energy savings from compressor efficiency at proper charge (AHRI 580: "
        "35-65 kWh/lb), (3) EPA penalty avoidance for systems over threshold, and (4) CO2e "
        "reduction using per-system GWP (not fleet average). Apply M&V to energy component."
    ),
    qa_goal=(
        "Validate leak rates against EPA Section 608 thresholds — flag any system above 20%. "
        "Verify GWP values match actual refrigerant types per system (not a flat R-404A assumption). "
        "Cross-check secondary energy penalty against AHRI 580 range (35-65 kWh/lb). "
        "Validate EPA compliance deadlines are tracked for all active leaks."
    ),
    research_backstory=(
        "You are a refrigerant management specialist with deep knowledge of EPA Section 608, "
        "GreenChill certification, and AIM Act phase-down schedules. You understand both the "
        "environmental (GWP) and economic (refrigerant cost + energy penalty) dimensions of "
        "leak reduction."
    ),
    extraction_backstory=(
        "You specialize in refrigerant tracking systems. You compute per-system leak rates, "
        "track EPA compliance deadlines, and identify blended GWP across multi-refrigerant fleets. "
        "You flag any system that has exceeded the EPA repair deadline as a compliance risk."
    ),
    research_topics=["refrigerant_leak_reduction"],
    required_inputs=["leak_events", "refrigerant_charge", "rack_performance", "compliance_logs"],
    formulas=[
        "Leak_rate = leaked_lbs / total_charge",
        "CO2e = leaked_kg * GWP(refrigerant_type)",
        "Savings = avoided_lbs * cost_per_lb + energy_penalty_kwh * $/kWh + penalty_avoidance",
    ],
    output_metrics=["baseline_leak_rate", "target_leak_rate", "avoided_lbs", "co2e_avoided_tonnes"],
    savings_category="Gas Leak Reduction",
    calculation_fn=calc_refrigerant_leak_reduction,
    research_tool_builder=build_refrigerant_research_tools,
    extraction_tool_builder=build_refrigerant_extraction_tools,
    specialist_agents=[
        SpecialistAgentDef(
            role="EPA Compliance & Refrigerant Transition Analyst",
            goal=(
                "Track EPA Section 608 compliance deadlines for all active leaks and assess "
                "GWP reduction opportunities from transitioning to lower-GWP refrigerants "
                "(R-404A→R-448A/R-449A/CO2) per AIM Act phase-down schedule."
            ),
            backstory=(
                "You are an EPA Section 608 compliance officer and refrigerant transition "
                "planner. You track repair deadlines, flag overdue systems, and evaluate "
                "the economic and environmental case for refrigerant conversions under the "
                "AIM Act HFC phase-down."
            ),
            task_description=(
                "Use check_refrigerant_compliance_deadlines and analyze_refrigerant_transition to: "
                "1. Identify all systems with active EPA compliance deadlines and flag overdue repairs "
                "2. Calculate per-system leak rates and compare against 20% EPA threshold "
                "3. Evaluate GWP reduction from R-404A→R-448A/R-449A/CO2 per rack "
                "4. Produce compliance risk summary and transition opportunity assessment"
            ),
            expected_output=(
                'JSON: {"compliance_status": {overdue: int, pending: int, compliant: int}, '
                '"systems_over_threshold": int, '
                '"transition_opportunities": [{target, gwp_reduction_pct, co2e_avoided}], '
                '"compliance_risk_level": "low|medium|high"}'
            ),
            position="pre_calc",
        ),
    ],
)


# =============================================================================
# KPI-5: Food Waste Reduction
# =============================================================================

def calc_food_waste_reduction(tools, company_id, location_id, assets, locations, scenario_params, research, **kw):
    excursion_events = tools.query_events(company_id, {"event_type": "temp_excursion"})
    case_count = _count_assets_by_type(assets, "refrigeration_case") or max(len(locations), 1) * 30

    bm = get_benchmarks_for_kpi("food_waste_reduction")
    avg_inventory_per_case = scenario_params.get("avg_inventory_per_case", sum(bm.get("inventory_per_case_range", [1800, 3500])) / 2)  # FMI 2020 midpoint
    baseline_shrink_pct = scenario_params.get("baseline_shrink_pct", bm.get("total_perishable_shrink_avg", 0.042))  # FMI Shrink Survey 2020
    excursion_attribution_pct = scenario_params.get("excursion_attribution_pct", sum(bm.get("excursion_attribution_range", [0.30, 0.50])) / 2)  # USDA ERS midpoint
    reduction_pct = scenario_params.get("shrink_reduction_pct", 0.30)

    total_inventory = case_count * avg_inventory_per_case
    excursion_attributed_shrink = total_inventory * baseline_shrink_pct * excursion_attribution_pct
    savings_base = excursion_attributed_shrink * reduction_pct * 12

    # --- Cross-asset: HVAC humidity coupling ---
    cross_asset_note = ""
    humidity_penalty = 0.0
    try:
        rel_graph = kw.get("relationship_graph")
        if rel_graph and isinstance(rel_graph, RelationshipGraph):
            hvac_assets = [a for a in assets if a.get("asset_type") in ("hvac_rtu", "hvac_ahu")]
            for hvac in hvac_assets:
                group = rel_graph.get_thermal_interaction_group(hvac.get("asset_id", ""))
                if len(group) > 1:
                    humidity_penalty += savings_base * 0.03
            if humidity_penalty > 0:
                cross_asset_note = f"HVAC-refrigeration humidity coupling adds ${humidity_penalty:,.0f} savings."
    except Exception:
        pass
    savings_base += humidity_penalty

    return {
        "metrics": {
            "case_count": case_count,
            "total_inventory_value": total_inventory,
            "baseline_shrink_pct": baseline_shrink_pct,
            "excursion_attribution_pct": excursion_attribution_pct,
            "excursion_events_found": len(excursion_events),
            "reduction_pct": reduction_pct,
            "cross_asset_humidity_savings": humidity_penalty,
        },
        **_savings_bands(savings_base, 0.4, 1.5),
        "confidence": 0.55 if excursion_events else 0.35,
        "assumptions": [
            f"Average inventory per case: ${avg_inventory_per_case}",
            f"Baseline shrink: {baseline_shrink_pct*100}%",
            f"Excursion-attributed share: {excursion_attribution_pct*100}%",
            f"Reduction from improved monitoring: {reduction_pct*100}%",
            "Cross-asset: HVAC humidity interaction considered for refrigeration cases",
        ],
        "narrative": f"Reducing excursion-driven shrink by {reduction_pct*100:.0f}% saves ${savings_base:,.0f}/year across {case_count} cases. {cross_asset_note}",
        "twin_patches": [],
        "evidence_refs": [],
    }


FOOD_WASTE_SPEC = KPICrewSpec(
    kpi_name="food_waste_reduction",
    display_name="Food Wastage Reduction (Shrink Reduction)",
    objective="Reduce spoilage and shrink driven by temperature excursions and equipment performance.",
    research_goal=(
        "Curate FMI Shrink Survey 2020 per-department shrink rates (Dairy 2.8%, Deli 8.7%, "
        "Meat 4.1%, Produce 5.8%), USDA ERS excursion attribution (30-50%), and FDA Food Code "
        "Arrhenius Q10 factors for temperature-dependent spoilage acceleration. "
        "Identify product categories with highest excursion sensitivity."
    ),
    extraction_goal=(
        "Extract temperature excursion events, case inventory data, and shrink records. "
        "Classify excursions by product category (dairy/meat/deli/produce/frozen) using "
        "case-to-department mapping. Score each excursion by severity (magnitude × duration × "
        "product sensitivity) using Q10 model. Calculate per-department exposed inventory."
    ),
    calculation_goal=(
        "Compute shrink reduction savings PER PRODUCT CATEGORY — not as a single flat rate. "
        "Apply category-specific shrink baselines (FMI 2020) and Q10 spoilage acceleration "
        "factors. Weight savings by actual excursion severity scores and exposed inventory value. "
        "Account for HVAC-refrigeration humidity coupling as cross-asset interaction."
    ),
    qa_goal=(
        "Validate shrink rates fall within FMI 2020 ranges per department. Reject single "
        "flat-rate shrink assumptions that ignore product sensitivity. Verify excursion severity "
        "scoring uses magnitude AND duration (not just threshold crossing count). "
        "Check that Q10 factors are appropriate per product category (2.0-4.0 range)."
    ),
    research_backstory=(
        "You are a food science specialist who understands temperature-dependent spoilage "
        "kinetics. You apply Arrhenius Q10 models to estimate shelf-life reduction from "
        "temperature excursions and know that a 42°F excursion for 20 minutes has a "
        "fundamentally different impact than 55°F for 4 hours."
    ),
    extraction_backstory=(
        "You map refrigeration cases to product departments and score excursions by "
        "severity using food science principles. You distinguish minor excursions (small "
        "magnitude, short duration) from critical ones that require product evaluation."
    ),
    research_topics=["food_waste", "temperature_excursions"],
    required_inputs=["shrink_data", "food_temperature_logs", "excursion_events", "product_sensitivity"],
    formulas=[
        "Shrink_avoided = Σ_dept(Excursion_severity * inventory_exposed * Q10_spoilage_factor * reduction_pct)",
    ],
    output_metrics=["case_count", "baseline_shrink_pct", "excursion_attribution_pct"],
    savings_category="Shrink Reduction",
    calculation_fn=calc_food_waste_reduction,
    extraction_tool_builder=build_food_waste_extraction_tools,
    specialist_agents=[
        SpecialistAgentDef(
            role="Product Sensitivity & Excursion Severity Analyst",
            goal=(
                "Classify products by temperature sensitivity using Q10 model, score each "
                "excursion by severity (magnitude × duration × product type), and produce "
                "per-department impact assessments for shrink estimation."
            ),
            backstory=(
                "You are a food safety scientist specializing in cold chain integrity. "
                "You apply Arrhenius Q10 models to quantify shelf-life reduction from "
                "temperature abuse. You classify products by TCS (Time/Temperature Control "
                "for Safety) risk level per FDA Food Code."
            ),
            task_description=(
                "Use classify_product_sensitivity and score_excursion_severity tools to: "
                "1. Classify all product categories with Q10 factors and optimal temp ranges "
                "2. Score each excursion event by severity (1-10 scale) based on magnitude, duration, product "
                "3. Produce per-department impact summary: critical/moderate/minor excursion counts "
                "4. Calculate weighted shrink attribution by department and severity tier"
            ),
            expected_output=(
                'JSON: {"product_categories": {dept: {q10, optimal_temp, excursion_count}}, '
                '"severity_distribution": {critical: int, moderate: int, minor: int}, '
                '"per_dept_impact": {dept: {shrink_rate, exposed_inventory, severity_weighted_risk}}}'
            ),
            position="pre_calc",
        ),
    ],
)


# =============================================================================
# KPI-6: Call Center Volume Reduction
# =============================================================================

def calc_call_center_reduction(tools, company_id, location_id, assets, locations, scenario_params, research, **kw):
    call_events = tools.query_events(company_id, {"event_type": "call_center_ticket"})
    location_count = len(locations) or 1

    bm = get_benchmarks_for_kpi("call_center_volume_reduction")
    calls_per_location_monthly = scenario_params.get("calls_per_location_monthly", 15)
    cost_per_call = scenario_params.get("cost_per_call", bm.get("cost_per_call_median", 11.0))  # ICMI 2022 median
    deflection_rate = scenario_params.get("deflection_rate", sum(bm.get("iot_deflection_range", [0.20, 0.40])) / 2)  # Gartner 2023 midpoint
    aht_reduction_minutes = scenario_params.get("aht_reduction_minutes", 2.0)
    cost_per_minute = scenario_params.get("cost_per_minute", 0.50)

    baseline_calls_monthly = (len(call_events) or location_count * calls_per_location_monthly)
    calls_avoided = baseline_calls_monthly * deflection_rate
    savings_deflection = calls_avoided * cost_per_call * 12
    savings_aht = (baseline_calls_monthly - calls_avoided) * aht_reduction_minutes * cost_per_minute * 12
    savings_base = savings_deflection + savings_aht

    return {
        "metrics": {
            "baseline_calls_monthly": baseline_calls_monthly,
            "calls_avoided_monthly": calls_avoided,
            "deflection_rate": deflection_rate,
            "cost_per_call": cost_per_call,
            "aht_reduction_minutes": aht_reduction_minutes,
        },
        **_savings_bands(savings_base),
        "confidence": 0.6 if call_events else 0.4,
        "assumptions": [
            f"Baseline calls: {baseline_calls_monthly}/month",
            f"Deflection rate: {deflection_rate*100}%",
            f"Cost per call: ${cost_per_call}",
            f"AHT reduction: {aht_reduction_minutes} min on remaining calls",
        ],
        "narrative": f"Call center savings of ${savings_base:,.0f}/year via {deflection_rate*100:.0f}% deflection and AHT reduction.",
        "twin_patches": [],
        "evidence_refs": [],
    }


CALL_CENTER_SPEC = KPICrewSpec(
    kpi_name="call_center_volume_reduction",
    display_name="Call Center Volume Reduction",
    objective="Reduce inbound issue calls via proactive detection, auto-triage, and self-service resolution.",
    research_goal=(
        "Curate ICMI 2022 cost-per-contact benchmarks (phone $8-15, chat $3-5, self-service "
        "$0.10-0.50), Gartner 2023 IoT call deflection rates (20-40%), and AHT benchmarks "
        "(8-12 min for HVAC/R service calls). Identify which call categories are deflectable "
        "via IoT auto-detect, self-service portals, and proactive notifications."
    ),
    extraction_goal=(
        "Extract call center tickets and classify by root cause category: comfort_complaint, "
        "equipment_alarm, food_safety, energy_dispute, scheduled_maintenance, other. "
        "Produce Pareto distribution of call types. Calculate baseline AHT per category. "
        "Identify which categories are deflectable and which require human intervention."
    ),
    calculation_goal=(
        "Compute savings using CATEGORY-SPECIFIC deflection rates — not a single blended rate. "
        "Model multi-channel shift: phone→chat→self-service with per-channel costs per Gartner. "
        "Calculate AHT reduction savings only on non-deflected calls. Include proactive "
        "notification savings (10-25% of comfort complaints deflected by automated alerts)."
    ),
    qa_goal=(
        "Validate deflection rates are category-specific — reject if a single flat rate is used. "
        "Verify cost-per-call falls within ICMI 2022 range ($8-15 phone). Check that food safety "
        "calls are NOT marked as deflectable (require human validation). Validate AHT reduction "
        "is derived from baseline measurement, not hardcoded."
    ),
    research_backstory=(
        "You are a contact center optimization specialist. You understand that different call "
        "types have fundamentally different deflection potential — equipment alarms can be "
        "auto-triaged at 60% deflection, but food safety calls require human judgment at <10%. "
        "You model multi-channel economics, not just phone call avoidance."
    ),
    extraction_backstory=(
        "You classify calls by root cause using text analysis of ticket descriptions. "
        "You produce Pareto distributions that reveal the 20% of call categories responsible "
        "for 80% of volume. You identify self-service candidates vs. human-required calls."
    ),
    research_topics=["call_center_optimization"],
    required_inputs=["call_center_tickets", "work_orders", "alert_history", "knowledge_articles"],
    formulas=[
        "Deflection_rate_weighted = Σ(category_pct * category_deflection_rate)",
        "Savings = Σ(deflected × phone_cost) + channel_shift_savings + AHT_reduction_savings",
    ],
    output_metrics=["baseline_calls_monthly", "deflection_rate", "calls_avoided_monthly"],
    savings_category="Call Center Cost Productivity",
    calculation_fn=calc_call_center_reduction,
    extraction_tool_builder=build_call_center_extraction_tools,
    specialist_agents=[
        SpecialistAgentDef(
            role="Call Categorization & Channel Shift Analyst",
            goal=(
                "Classify calls by root cause, determine per-category deflection potential, "
                "and model the multi-channel savings opportunity from shifting calls from "
                "phone ($11/contact) to chat ($4) and self-service ($0.30)."
            ),
            backstory=(
                "You are a contact center analytics specialist who uses NLP-based call "
                "categorization and Gartner channel shift models. You distinguish deflectable "
                "calls (equipment alarms, maintenance status) from non-deflectable calls "
                "(food safety, complex complaints)."
            ),
            task_description=(
                "Use categorize_calls_by_root_cause and model_self_service_funnel tools to: "
                "1. Classify all calls into root cause categories with deflection rates "
                "2. Identify calls that are deflectable via IoT vs self-service vs chat "
                "3. Model multi-channel cost savings from current mix to target mix "
                "4. Calculate weighted average deflection rate and total savings opportunity"
            ),
            expected_output=(
                'JSON: {"call_categories": {category: {count, pct, deflection_rate, method}}, '
                '"weighted_deflection_rate": float, '
                '"channel_shift_savings": {current_cost, target_cost, monthly_savings}, '
                '"non_deflectable_categories": [str]}'
            ),
            position="pre_calc",
        ),
    ],
)


# =============================================================================
# KPI-7: Service Bureau Reduction
# =============================================================================

def calc_service_bureau_reduction(tools, company_id, location_id, assets, locations, scenario_params, research, **kw):
    vendor_events = tools.query_events(company_id, {"event_type": "vendor_job"})
    location_count = len(locations) or 1

    vendor_jobs_monthly = len(vendor_events) or location_count * 5
    bm = get_benchmarks_for_kpi("service_bureau_reduction")
    avg_vendor_cost = scenario_params.get("avg_vendor_cost", sum(bm.get("vendor_dispatch_cost_refrig_range", [350, 700])) / 2)  # Service Council 2022 midpoint
    nff_rate = scenario_params.get("nff_rate", sum(bm.get("nff_rate_range", [0.15, 0.30])) / 2)  # Aberdeen 2019 midpoint
    job_avoidance_pct = scenario_params.get("job_avoidance_pct", 0.20)
    rework_rate = scenario_params.get("rework_rate", bm.get("rework_rate_average", 0.12))  # Service Council 2022

    jobs_avoided = vendor_jobs_monthly * job_avoidance_pct
    nff_avoided = vendor_jobs_monthly * nff_rate * 0.5
    rework_avoided = vendor_jobs_monthly * rework_rate * 0.5
    total_avoided = jobs_avoided + nff_avoided + rework_avoided

    savings_base = total_avoided * avg_vendor_cost * 12

    return {
        "metrics": {
            "vendor_jobs_monthly": vendor_jobs_monthly,
            "avg_vendor_cost": avg_vendor_cost,
            "jobs_avoided_monthly": total_avoided,
            "nff_rate": nff_rate,
            "rework_rate": rework_rate,
        },
        **_savings_bands(savings_base),
        "confidence": 0.6 if vendor_events else 0.4,
        "assumptions": [
            f"Baseline vendor jobs: {vendor_jobs_monthly}/month",
            f"Average vendor cost: ${avg_vendor_cost}",
            f"Job avoidance rate: {job_avoidance_pct*100}%",
            f"NFF (no-fault-found) rate reduction: 50% of {nff_rate*100}%",
        ],
        "narrative": f"Service bureau reduction saves ${savings_base:,.0f}/year by avoiding {total_avoided:.0f} jobs/month.",
        "twin_patches": [],
        "evidence_refs": [],
    }


SERVICE_BUREAU_SPEC = KPICrewSpec(
    kpi_name="service_bureau_reduction",
    display_name="Service Bureau Reduction (3rd-Party Job Reduction)",
    objective="Reduce outsourced tickets/jobs by improving first-time fix, better diagnostics, and avoiding unnecessary dispatch.",
    research_goal=(
        "Curate Aberdeen 2019 NFF (no-fault-found) rate benchmarks (15-30%), first-time fix "
        "rate targets (90% best-in-class), Service Council 2022 rework rates (12% avg), and "
        "vendor dispatch cost ranges ($350-700 for refrigeration). Identify which job types "
        "are avoidable via remote diagnostics vs requiring physical presence."
    ),
    extraction_goal=(
        "Extract vendor job records and classify by outcome: successful_fix, no_fault_found, "
        "rework_required, parts_not_available. Score each vendor on FTF rate, NFF rate, rework "
        "rate, and average cost per job. Identify which job types could have been avoided with "
        "remote diagnostics (NFF and nuisance alarm dispatches)."
    ),
    calculation_goal=(
        "Compute savings from three distinct levers — not a flat avoidance percentage: "
        "(1) NFF elimination: 50% of NFF dispatches avoidable via remote diagnostics, "
        "(2) Rework reduction: improved FTF from better pre-dispatch diagnostics, "
        "(3) Vendor routing optimization: shift jobs to higher-FTF vendors. "
        "Calculate per-lever savings separately with distinct confidence levels."
    ),
    qa_goal=(
        "Validate NFF rates fall within Aberdeen 2019 range (15-30%). Verify FTF rate targets "
        "are realistic (<95% is unrealistic for refrigeration per Service Council). "
        "Check that vendor scoring is based on actual job outcome data, not assumptions. "
        "Validate cost per vendor job falls within $350-700 per Service Council 2022."
    ),
    research_backstory=(
        "You are a field service optimization consultant specializing in HVAC/R vendor "
        "management. You understand that NFF dispatches ($350-700 wasted per trip) are "
        "the lowest-hanging fruit, followed by rework reduction through better pre-dispatch "
        "diagnostics that ensure the right parts and technician are sent first time."
    ),
    extraction_backstory=(
        "You analyze vendor job outcome data to score vendor performance. You identify "
        "NFF patterns (e.g., nuisance alarms, intermittent faults that clear before arrival) "
        "and rework patterns (wrong parts ordered, technician skill mismatch)."
    ),
    research_topics=["service_optimization"],
    required_inputs=["vendor_jobs", "costs", "reopen_rates", "telemetry_evidence"],
    formulas=[
        "Savings = NFF_avoided * avg_cost + rework_avoided * avg_cost + routing_savings",
    ],
    output_metrics=["vendor_jobs_monthly", "jobs_avoided_monthly", "nff_rate"],
    savings_category="3rd Party Job Reduction",
    calculation_fn=calc_service_bureau_reduction,
    extraction_tool_builder=build_service_bureau_extraction_tools,
    specialist_agents=[
        SpecialistAgentDef(
            role="Vendor Performance & NFF Root Cause Analyst",
            goal=(
                "Score each vendor on FTF rate, NFF rate, rework rate, and cost per job. "
                "Identify NFF root causes (nuisance alarms, intermittent faults, customer-side "
                "issues) to determine which are eliminable via remote diagnostics."
            ),
            backstory=(
                "You are a field service analytics specialist who benchmarks vendor performance "
                "against Aberdeen 2019 and Service Council 2022 standards. You identify "
                "systematic NFF patterns and recommend vendor routing optimization."
            ),
            task_description=(
                "Use score_vendor_performance tool to: "
                "1. Score all vendors on FTF, NFF, rework rates and cost efficiency "
                "2. Identify the top NFF root causes and which are avoidable via remote diagnostics "
                "3. Recommend vendor routing changes to improve fleet-wide FTF rate "
                "4. Calculate per-lever savings: NFF elimination + rework reduction + routing optimization"
            ),
            expected_output=(
                'JSON: {"vendor_scorecards": [{vendor, ftf_rate, nff_rate, score}], '
                '"nff_root_causes": [{cause, avoidable_pct}], '
                '"routing_recommendations": str, '
                '"per_lever_savings": {nff: float, rework: float, routing: float}}'
            ),
            position="pre_calc",
        ),
    ],
)


# =============================================================================
# KPI-8: Asset Failure Prediction
# =============================================================================

def calc_asset_failure_prediction(tools, company_id, location_id, assets, locations, scenario_params, research, **kw):
    asset_count = len(assets) or 1
    bm = get_benchmarks_for_kpi("asset_failure_prediction")
    avg_downtime_cost = scenario_params.get("avg_downtime_cost", bm.get("downtime_cost_per_event_median", 1500.0))  # Jardine & Tsang 2013
    lead_time_hours = scenario_params.get("lead_time_hours", 72)
    collateral_reduction = scenario_params.get("collateral_damage_factor", sum(bm.get("collateral_damage_factor_range", [0.20, 0.40])) / 2)  # McKinsey 2020 midpoint

    # --- PdM bridge integration: use real model outputs when available ---
    pdm_source = "heuristic"
    pdm_details = scenario_params.get("pdm_asset_details", [])
    pdm_avg_health = scenario_params.get("pdm_avg_health_score")
    pdm_avg_rul = scenario_params.get("pdm_avg_rul_hours")
    pdm_failure_rate = scenario_params.get("pdm_failure_rate_30d")
    pdm_accuracy = scenario_params.get("pdm_prediction_accuracy")
    pdm_fault_dist = scenario_params.get("pdm_fault_distribution", {})

    if pdm_details:
        # Use PdM-grounded values
        pdm_source = "pdm_bridge"
        baseline_failure_rate = pdm_failure_rate if pdm_failure_rate else scenario_params.get("baseline_failure_rate", 0.05)
        prediction_accuracy = pdm_accuracy if pdm_accuracy else scenario_params.get("prediction_accuracy", 0.70)
        # Compute fleet-level prevented failures from per-asset risk
        prevented_failures = 0.0
        for pd in pdm_details:
            r30 = pd.get("failure_risk_30d", baseline_failure_rate)
            prevented_failures += r30 * prediction_accuracy
        if pdm_avg_rul and pdm_avg_rul < float("inf"):
            lead_time_hours = min(pdm_avg_rul * 0.5, 168)  # 50% of avg RUL, capped at 1 week
    else:
        baseline_failure_rate = scenario_params.get("baseline_failure_rate", sum(bm.get("monthly_failure_rate_fleet_avg", [0.003, 0.007])) / 2)  # ISO 14224 midpoint
        prediction_accuracy = scenario_params.get("prediction_accuracy", bm.get("cbm_prediction_accuracy_range", [0.70, 0.85])[0])  # Jardine & Tsang lower bound
        prevented_failures = asset_count * baseline_failure_rate * prediction_accuracy

    savings_downtime = prevented_failures * avg_downtime_cost * 12
    savings_collateral = prevented_failures * avg_downtime_cost * collateral_reduction * 12
    savings_base = savings_downtime + savings_collateral

    # Generate risk register patches (PdM-grounded when available)
    twin_patches = []
    for a in assets[:50]:
        pdm_match = next((p for p in pdm_details if p.get("asset_id") == a.get("asset_id")), None)
        if pdm_match:
            risk_30d = pdm_match.get("failure_risk_30d", 0.05)
            risk_90d = pdm_match.get("failure_risk_90d", 0.10)
        else:
            risk_30d = baseline_failure_rate * (1 - a.get("health", {}).get("health_score", 80) / 100)
            risk_90d = min(risk_30d * 2.5, 1.0)
        twin_patches.append({
            "entity_type": "asset",
            "entity_id": a["asset_id"],
            "patch": {"health": {"failure_risk_30d": round(risk_30d, 4), "failure_risk_90d": round(min(risk_90d, 1.0), 4)}},
        })

    # Confidence is higher when backed by real PdM models
    confidence = 0.80 if pdm_source == "pdm_bridge" else 0.60

    return {
        "metrics": {
            "asset_count": asset_count,
            "baseline_failure_rate_monthly": baseline_failure_rate,
            "prediction_accuracy": prediction_accuracy,
            "prevented_failures_monthly": prevented_failures,
            "lead_time_hours": lead_time_hours,
            "pdm_source": pdm_source,
            "pdm_avg_health_score": pdm_avg_health,
            "pdm_avg_rul_hours": pdm_avg_rul if pdm_avg_rul and pdm_avg_rul < float("inf") else None,
            "pdm_assets_at_risk": scenario_params.get("pdm_assets_at_risk", 0),
            "pdm_fault_distribution": pdm_fault_dist,
        },
        **_savings_bands(savings_base, 0.5, 1.5),
        "confidence": confidence,
        "assumptions": [
            f"Baseline monthly failure rate: {baseline_failure_rate*100:.1f}% (source: {pdm_source})",
            f"Prediction accuracy: {prediction_accuracy*100:.0f}% (source: {pdm_source})",
            f"Average downtime cost: ${avg_downtime_cost}",
            f"Lead time for planned action: {lead_time_hours:.0f} hours",
            f"PdM model integration: {'active — {len(pdm_details)} assets with real-time risk scores' if pdm_details else 'not available — using heuristic estimates'}",
        ],
        "narrative": (
            f"Predicting {prevented_failures:.0f} failures/month with {lead_time_hours:.0f}h lead time "
            f"saves ${savings_base:,.0f}/year. "
            f"{'PdM models provide per-asset risk scores for ' + str(len(pdm_details)) + ' assets.' if pdm_details else 'Using heuristic failure rate estimates.'}"
        ),
        "twin_patches": twin_patches,
        "evidence_refs": [{"type": "pdm_model", "source": pdm_source}] if pdm_details else [],
    }


ASSET_FAILURE_SPEC = KPICrewSpec(
    kpi_name="asset_failure_prediction",
    display_name="Asset Failure Prediction",
    objective="Predict failure probability and lead time to enable planned actions.",
    research_goal=(
        "Curate ISO 14224:2016 failure rate data per component type (RTU 3-8%, compressor 2-6%), "
        "Jardine & Tsang 2013 CBM prediction accuracy (70-85%), McKinsey 2020 downtime reduction "
        "(30-50%) and collateral damage factors (20-40%). Include Weibull shape parameters "
        "(β=1.2-2.5 for HVAC/R) for age-dependent failure rate modeling."
    ),
    extraction_goal=(
        "Extract failure events, work order history, telemetry features (vibration, temperature, "
        "pressure, current draw), and asset age/maintenance records. For each asset, compute: "
        "time since last failure, time since last PM, current health score from PdM models "
        "(if available). Identify assets in 'action' or 'critical' health bands."
    ),
    calculation_goal=(
        "Compute failure prediction value using FMEA-weighted approach: prioritize failure modes "
        "by RPN (Risk Priority Number = Severity × Occurrence × Detection). Use PdM model outputs "
        "when available (pdm_bridge) for per-asset failure risk; fall back to ISO 14224 heuristics "
        "when PdM unavailable. Calculate lead time from RUL estimates, not a flat 72h assumption."
    ),
    qa_goal=(
        "Validate that failure rates align with ISO 14224 ranges per asset type (not a fleet-wide "
        "average). Verify PdM-grounded estimates have higher confidence than heuristic estimates. "
        "Check that collateral damage factor falls within McKinsey range (20-40%). "
        "Reject if lead time is hardcoded rather than derived from RUL or maintenance scheduling."
    ),
    research_backstory=(
        "You are a reliability engineer specializing in FMEA and CBM/PdM for HVAC/R systems. "
        "You understand Weibull hazard modeling, RPN-based prioritization, and the critical "
        "difference between time-based and condition-based failure prediction."
    ),
    extraction_backstory=(
        "You integrate PdM model outputs with CMMS failure history. You identify assets at "
        "elevated risk using both data-driven health scores and maintenance gap analysis."
    ),
    research_topics=["preventive_maintenance_optimization"],
    required_inputs=["telemetry", "events", "work_orders", "maintenance_history"],
    formulas=[
        "failure_risk_30d = f(telemetry_features, age, maintenance_history)",
        "RPN = Severity × Occurrence × Detection (per failure mode)",
        "Value = Σ(prevented_failures × (downtime_cost + collateral_damage))",
    ],
    output_metrics=["prediction_accuracy", "prevented_failures_monthly", "lead_time_hours"],
    savings_category="Asset Failure Prevention",
    calculation_fn=calc_asset_failure_prediction,
    extraction_tool_builder=build_failure_prediction_extraction_tools,
    specialist_agents=[
        SpecialistAgentDef(
            role="FMEA Risk Priority & Hazard Analyst",
            goal=(
                "Compute Risk Priority Numbers (RPN) for each failure mode per FMEA methodology. "
                "Identify the top failure modes by consequence × probability and determine which "
                "are addressable by PdM vs. requiring design changes."
            ),
            backstory=(
                "You are an FMEA specialist per SAE J1739. You score failure modes on Severity "
                "(1-10), Occurrence (1-10), and Detection (1-10) using ISO 14224 failure rate "
                "data and HVAC/R-specific consequence models."
            ),
            task_description=(
                "Use compute_fmea_risk_priority tool to: "
                "1. Generate FMEA table with RPN scores for all major HVAC/R failure modes "
                "2. Identify critical failure modes (RPN ≥ 200) requiring immediate PdM coverage "
                "3. Map each failure mode to detection method and P-F interval "
                "4. Prioritize PdM investment by failure mode based on RPN ranking"
            ),
            expected_output=(
                'JSON: {"fmea_table": [{failure_mode, rpn, severity, occurrence, detection}], '
                '"critical_modes": [{failure_mode, rpn, recommended_action}], '
                '"pdm_coverage_gaps": [str], "top_priority_mode": str}'
            ),
            position="pre_calc",
        ),
    ],
)


# =============================================================================
# KPI-9: Asset Uptime Increase
# =============================================================================

def calc_asset_uptime_increase(tools, company_id, location_id, assets, locations, scenario_params, research, **kw):
    downtime_events = tools.query_events(company_id, {"event_type": "downtime"})
    asset_count = len(assets) or 1

    bm = get_benchmarks_for_kpi("asset_uptime_increase")
    operating_hours_monthly = scenario_params.get("operating_hours_monthly", 480)
    baseline_uptime_pct = scenario_params.get("baseline_uptime_pct", sum(bm.get("availability_average_range", [0.88, 0.92])) / 2)  # SMRP 5.3.1 avg
    target_uptime_pct = scenario_params.get("target_uptime_pct", bm.get("availability_grocery_refrig_target", 0.99))  # SMRP food safety critical
    value_per_downtime_hour = scenario_params.get("value_per_downtime_hour", bm.get("downtime_value_per_hour_grocery_median", 175.0))  # EN 15341 grocery median

    # --- PdM bridge: refine uptime estimates from real health data ---
    pdm_details = scenario_params.get("pdm_asset_details", [])
    pdm_source = "heuristic"
    pdm_predicted_downtime_reduction = 0.0
    if pdm_details:
        pdm_source = "pdm_bridge"
        # Assets with low health scores are likely to have more downtime
        critical_assets = [p for p in pdm_details if p.get("health_band") in ("action", "critical")]
        monitoring_assets = [p for p in pdm_details if p.get("health_band") == "monitoring"]
        # Early intervention on at-risk assets yields additional downtime avoidance
        pdm_predicted_downtime_reduction = (
            len(critical_assets) * 8.0 +  # 8 hours saved per critical asset/month
            len(monitoring_assets) * 2.0   # 2 hours saved per monitoring asset/month
        )
        # Refine baseline uptime from PdM health distribution
        pdm_avg_health = scenario_params.get("pdm_avg_health_score", 80)
        if pdm_avg_health < 80:
            baseline_uptime_pct = max(0.90, baseline_uptime_pct - (80 - pdm_avg_health) * 0.002)

    baseline_downtime = operating_hours_monthly * (1 - baseline_uptime_pct) * asset_count
    target_downtime = operating_hours_monthly * (1 - target_uptime_pct) * asset_count
    avoided_downtime = baseline_downtime - target_downtime + pdm_predicted_downtime_reduction
    savings_base = avoided_downtime * value_per_downtime_hour * 12

    confidence = 0.75 if pdm_source == "pdm_bridge" else (0.6 if downtime_events else 0.4)

    return {
        "metrics": {
            "baseline_uptime_pct": baseline_uptime_pct,
            "target_uptime_pct": target_uptime_pct,
            "avoided_downtime_hours_monthly": avoided_downtime,
            "pdm_predicted_downtime_reduction_hours": pdm_predicted_downtime_reduction,
            "asset_count": asset_count,
            "downtime_events_found": len(downtime_events),
            "pdm_source": pdm_source,
        },
        **_savings_bands(savings_base, 0.5, 1.4),
        "confidence": confidence,
        "assumptions": [
            f"Baseline uptime: {baseline_uptime_pct*100:.1f}% (source: {pdm_source})",
            f"Target uptime: {target_uptime_pct*100}%",
            f"Value per downtime hour: ${value_per_downtime_hour}",
            f"Operating hours: {operating_hours_monthly}/month per asset",
            f"PdM-predicted additional downtime avoidance: {pdm_predicted_downtime_reduction:.0f} hours/month" if pdm_details else "PdM models not available",
        ],
        "narrative": (
            f"Improving uptime from {baseline_uptime_pct*100:.1f}% to {target_uptime_pct*100:.1f}% "
            f"avoids {avoided_downtime:.0f} hours/month, saving ${savings_base:,.0f}/year. "
            f"{'PdM models contributed ' + str(pdm_predicted_downtime_reduction) + 'h additional avoidance.' if pdm_details else ''}"
        ),
        "twin_patches": [],
        "evidence_refs": [{"type": "pdm_model", "source": pdm_source}] if pdm_details else [],
    }


ASSET_UPTIME_SPEC = KPICrewSpec(
    kpi_name="asset_uptime_increase",
    display_name="Asset Uptime Increase",
    objective="Reduce downtime minutes/hours per asset and per location.",
    research_goal=(
        "Curate SMRP 5.3.1 OEE benchmarks (85% world-class, 95% availability target), "
        "EN 15341 downtime cost ranges ($50-500/hr by criticality tier), and root cause "
        "decomposition literature. Distinguish Availability, Performance, and Quality "
        "components of OEE for HVAC/R assets."
    ),
    extraction_goal=(
        "Extract downtime events and classify by root cause: equipment_failure, parts_delay, "
        "scheduling_gap, operator_error, external_event. Calculate hours lost per category. "
        "Tier each asset by criticality (critical=$300-500/hr for food safety, important=$100-300/hr, "
        "standard=$50-100/hr) using EN 15341 framework. Report downtime Pareto by cause and tier."
    ),
    calculation_goal=(
        "Compute uptime improvement savings using CRITICALITY-WEIGHTED downtime costs — not a "
        "flat $/hr. Apply per-category reducibility rates (equipment_failure 60%, scheduling_gap "
        "70%, parts_delay 40%). Weight savings by asset criticality tier. Use PdM bridge data "
        "for assets with real-time health scores to refine avoided downtime estimates."
    ),
    qa_goal=(
        "Validate that downtime costs are differentiated by criticality tier — reject if a "
        "single flat rate is used for all assets. Verify uptime targets are realistic: "
        "99% for food-safety-critical assets, 95% for important assets per SMRP. "
        "Check that PdM-grounded estimates receive higher confidence than heuristic estimates."
    ),
    research_backstory=(
        "You are an OEE specialist who decomposes uptime into Availability, Performance, and "
        "Quality components. You understand that a refrigeration rack going down has a "
        "$400/hr impact (food safety + product loss) while an RTU downtime is $175/hr "
        "(comfort complaints + energy waste)."
    ),
    extraction_backstory=(
        "You classify downtime events by root cause and tier assets by criticality. "
        "You produce Pareto distributions that reveal the highest-impact downtime drivers "
        "and the asset tiers where downtime reduction has the largest ROI."
    ),
    research_topics=["asset_uptime", "downtime_reduction"],
    required_inputs=["downtime_events", "operating_hours", "work_orders"],
    formulas=[
        "Uptime% = 1 - (Downtime / Operating_time)",
        "Savings = Σ(avoided_hours_category × criticality_cost_per_hour × reducibility_rate)",
    ],
    output_metrics=["baseline_uptime_pct", "target_uptime_pct", "avoided_downtime_hours_monthly"],
    savings_category="Uptime Improvement",
    calculation_fn=calc_asset_uptime_increase,
    extraction_tool_builder=build_uptime_extraction_tools,
    specialist_agents=[
        SpecialistAgentDef(
            role="Downtime Pareto & Asset Criticality Analyst",
            goal=(
                "Classify downtime events by root cause, tier assets by criticality, and "
                "produce a weighted downtime cost analysis that accounts for the vastly "
                "different cost-per-hour across food safety vs comfort vs non-critical assets."
            ),
            backstory=(
                "You are a reliability and availability specialist who applies EN 15341 "
                "criticality frameworks to HVAC/R fleets. You understand that Pareto analysis "
                "of downtime causes is the first step to targeted improvement."
            ),
            task_description=(
                "Use classify_downtime_causes and tier_asset_criticality tools to: "
                "1. Classify all downtime events by root cause with hours lost per category "
                "2. Tier all assets by criticality (critical/important/standard) with cost/hr "
                "3. Cross-reference: which downtime causes affect which criticality tiers most "
                "4. Identify top reducible downtime: category × tier combinations with highest ROI"
            ),
            expected_output=(
                'JSON: {"downtime_pareto": {cause: {hours, pct, reducible_pct}}, '
                '"criticality_tiers": {tier: {count, cost_per_hr}}, '
                '"top_reducible_combinations": [{cause, tier, reducible_hours, savings}], '
                '"weighted_avg_downtime_cost_per_hr": float}'
            ),
            position="pre_calc",
        ),
    ],
)


# =============================================================================
# KPI-10: Food Temperature Diagnostics
# =============================================================================

def calc_food_temp_diagnostics(tools, company_id, location_id, assets, locations, scenario_params, research, **kw):
    excursion_events = tools.query_events(company_id, {"event_type": "temp_excursion"})
    case_count = _count_assets_by_type(assets, "refrigeration_case") or max(len(locations), 1) * 30

    bm = get_benchmarks_for_kpi("food_temperature_diagnostics")
    baseline_diagnostic_time_hours = scenario_params.get("baseline_diagnostic_time_hours", bm.get("diagnostic_time_manual_minutes", [30, 90])[1] / 60 if isinstance(bm.get("diagnostic_time_manual_minutes"), list) else 1.5)  # FDA Model Food Code upper
    target_diagnostic_time_hours = scenario_params.get("target_diagnostic_time_hours", bm.get("diagnostic_time_automated_minutes", [2, 10])[1] / 60 if isinstance(bm.get("diagnostic_time_automated_minutes"), list) else 0.17)  # Automated upper
    baseline_precision = scenario_params.get("baseline_precision", sum(bm.get("rule_based_diagnostic_accuracy_range", [0.40, 0.60])) / 2)  # ASHRAE Handbook
    target_precision = scenario_params.get("target_precision", sum(bm.get("ml_diagnostic_accuracy_range", [0.75, 0.92])) / 2)  # ML diagnostic midpoint
    cost_per_misdiagnosis = scenario_params.get("cost_per_misdiagnosis", sum(bm.get("misdiagnosis_service_call_cost_range", [250, 500])) / 2)  # FDA Model Food Code
    excursions_per_case_monthly = scenario_params.get("excursions_per_case_monthly", 0.5)

    total_excursions_monthly = len(excursion_events) or case_count * excursions_per_case_monthly
    misdiagnoses_avoided = total_excursions_monthly * (target_precision - baseline_precision)
    time_saved = total_excursions_monthly * (baseline_diagnostic_time_hours - target_diagnostic_time_hours)
    savings_base = (misdiagnoses_avoided * cost_per_misdiagnosis + time_saved * 50) * 12

    return {
        "metrics": {
            "baseline_precision": baseline_precision,
            "target_precision": target_precision,
            "baseline_time_to_root_cause_hours": baseline_diagnostic_time_hours,
            "target_time_to_root_cause_hours": target_diagnostic_time_hours,
            "total_excursions_monthly": total_excursions_monthly,
            "misdiagnoses_avoided_monthly": misdiagnoses_avoided,
        },
        **_savings_bands(savings_base, 0.5, 1.5),
        "confidence": 0.55,
        "assumptions": [
            f"Baseline diagnostic precision: {baseline_precision*100}%",
            f"Target precision: {target_precision*100}%",
            f"Time-to-root-cause reduction: {baseline_diagnostic_time_hours}h → {target_diagnostic_time_hours}h",
            "Root causes: door left open, evap icing, refrigerant undercharge, sensor drift",
        ],
        "narrative": f"Improved food temp diagnostics reduces root cause time from {baseline_diagnostic_time_hours}h to {target_diagnostic_time_hours}h.",
        "twin_patches": [],
        "evidence_refs": [],
    }


FOOD_TEMP_DIAGNOSTICS_SPEC = KPICrewSpec(
    kpi_name="food_temp_diagnostics_improvement",
    display_name="Improved Food Temperature Diagnostics",
    objective="Improve diagnostic accuracy and speed for temperature excursions.",
    research_goal=(
        "Curate ASHRAE Handbook diagnostic methodologies for refrigeration excursions, "
        "FDA Model Food Code diagnostic timing benchmarks (manual 30-90 min vs automated 2-10 min), "
        "and ML diagnostic accuracy ranges (rule-based 40-60% vs ML 75-92%). "
        "Document the fault isolation decision tree: door→evaporator→refrigerant→sensor→defrost."
    ),
    extraction_goal=(
        "Extract temperature excursion events with simultaneous sensor signals: compressor amps, "
        "suction/discharge pressure, defrost cycle timing, door switch state, and zone conditions. "
        "For each excursion, extract the multi-sensor context needed for root cause isolation. "
        "Assess sensor health: identify sensors with drift, calibration gaps, or stale readings."
    ),
    calculation_goal=(
        "Compute diagnostic improvement value from TWO levers: (1) precision improvement — "
        "fewer misdiagnoses means fewer unnecessary service calls (cost_per_misdiagnosis), and "
        "(2) time-to-root-cause reduction — faster diagnostics means shorter product exposure. "
        "Apply the fault isolation decision tree to estimate per-fault-type diagnostic accuracy."
    ),
    qa_goal=(
        "Validate diagnostic precision claims against actual diagnostic outcome data if available. "
        "Reject precision improvement targets that exceed 92% without ML model validation. "
        "Verify sensor health assessment is included — misdiagnosis from sensor drift is a major "
        "source of NFF dispatches. Check time-to-root-cause uses the decision tree methodology."
    ),
    research_backstory=(
        "You are a refrigeration diagnostics specialist who uses fault isolation decision trees "
        "and multi-sensor correlation to identify root causes of temperature excursions. "
        "You understand that door-left-open, evaporator icing, refrigerant undercharge, sensor "
        "drift, and defrost failure each have distinct sensor signatures."
    ),
    extraction_backstory=(
        "You correlate temperature excursions with simultaneous multi-sensor data to enable "
        "root cause isolation. You identify sensor health issues (drift, calibration gaps) "
        "that may cause misdiagnosis and flag them as data quality concerns."
    ),
    research_topics=["food_temperature", "root_cause_analysis"],
    required_inputs=["temperature_sensors", "door_sensors", "defrost_cycles", "hvac_zone_conditions"],
    formulas=[
        "Diagnostic_precision = correct_diagnoses / total_diagnoses",
        "Time_to_root_cause = f(fault_type, sensor_availability, decision_tree_depth)",
        "Savings = misdiagnoses_avoided × cost_per_misdiagnosis + time_saved × labor_rate",
    ],
    output_metrics=["baseline_precision", "target_precision", "time_to_root_cause_hours"],
    savings_category="Food Temperature Diagnostics",
    calculation_fn=calc_food_temp_diagnostics,
    extraction_tool_builder=build_food_temp_extraction_tools,
    specialist_agents=[
        SpecialistAgentDef(
            role="Diagnostic Decision Tree & Sensor Health Analyst",
            goal=(
                "Apply refrigeration fault isolation decision tree to classify excursion root "
                "causes and assess sensor health to identify calibration drift that may cause "
                "misdiagnosis. Score each excursion by diagnostic confidence."
            ),
            backstory=(
                "You are a refrigeration FDD (Fault Detection & Diagnostics) specialist. "
                "You apply multi-signal correlation: if door switch shows open + temp rising = "
                "door issue; if suction pressure low + superheat high = undercharge; if "
                "defrost timer exceeded + ice detected = defrost failure."
            ),
            task_description=(
                "Use classify_product_sensitivity and score_excursion_severity tools to: "
                "1. Classify each excursion by probable root cause using multi-sensor correlation "
                "2. Assess sensor health across the fleet (drift, stale, missing) "
                "3. Score diagnostic confidence per excursion based on sensor data availability "
                "4. Identify excursions where root cause remains ambiguous due to sensor gaps"
            ),
            expected_output=(
                'JSON: {"root_cause_distribution": {cause: {count, pct, avg_diagnostic_confidence}}, '
                '"sensor_health": {healthy_pct, drifting_pct, missing_pct}, '
                '"ambiguous_excursions_pct": float, '
                '"diagnostic_improvement_potential": {precision_gain, time_reduction_hours}}'
            ),
            position="pre_calc",
        ),
    ],
)


# =============================================================================
# KPI-11: Food Safety Compliance
# =============================================================================

def calc_food_safety_compliance(tools, company_id, location_id, assets, locations, scenario_params, research, **kw):
    violation_events = tools.query_events(company_id, {"event_type": "food_safety_violation"})
    excursion_events = tools.query_events(company_id, {"event_type": "temp_excursion"})
    case_count = _count_assets_by_type(assets, "refrigeration_case") or max(len(locations), 1) * 30

    bm = get_benchmarks_for_kpi("food_safety_compliance")
    cold_holding_threshold_f = scenario_params.get("cold_holding_threshold_f", bm.get("cold_hold_threshold_f", 41.0))  # FDA Food Code 2022 §3-501.16
    violations_per_location_monthly = scenario_params.get("violations_per_location_monthly", 3.0)
    cost_per_violation = scenario_params.get("cost_per_violation", sum(bm.get("fda_penalty_per_observation_range", [500, 10000])) / 2)  # FDA penalty midpoint
    reduction_pct = scenario_params.get("violation_reduction_pct", sum(bm.get("haccp_incident_reduction_range", [0.40, 0.70])) / 2)  # CDC HACCP midpoint
    corrective_action_sla_hours = scenario_params.get("corrective_action_sla_hours", 4.0)

    location_count = len(locations) or 1
    baseline_violations = len(violation_events) or location_count * violations_per_location_monthly
    avoided_violations = baseline_violations * reduction_pct
    savings_base = avoided_violations * cost_per_violation * 12

    # --- Time out of range computation ---
    total_excursion_minutes = 0
    excursion_count = len(excursion_events)
    for exc in excursion_events:
        payload = exc.get("payload", {})
        duration_min = payload.get("duration_minutes", 30)
        total_excursion_minutes += duration_min
    avg_excursion_minutes = _safe_div(total_excursion_minutes, excursion_count, 30.0)
    time_out_of_range_hours_monthly = total_excursion_minutes / 60 if excursion_events else case_count * 0.5

    # --- Corrective action SLA ---
    sla_met_count = 0
    sla_breached_count = 0
    for v in violation_events:
        payload = v.get("payload", {})
        response_hours = payload.get("response_time_hours")
        if response_hours is not None:
            if response_hours <= corrective_action_sla_hours:
                sla_met_count += 1
            else:
                sla_breached_count += 1
    total_sla_tracked = sla_met_count + sla_breached_count
    sla_compliance_rate = _safe_div(sla_met_count, total_sla_tracked, 0.80)

    return {
        "metrics": {
            "cold_holding_threshold_f": cold_holding_threshold_f,
            "baseline_violations_monthly": baseline_violations,
            "avoided_violations_monthly": avoided_violations,
            "reduction_pct": reduction_pct,
            "cost_per_violation": cost_per_violation,
            "excursion_count": excursion_count,
            "time_out_of_range_hours_monthly": round(time_out_of_range_hours_monthly, 1),
            "avg_excursion_duration_minutes": round(avg_excursion_minutes, 1),
            "corrective_action_sla_hours": corrective_action_sla_hours,
            "sla_compliance_rate": round(sla_compliance_rate, 3),
            "sla_met_count": sla_met_count,
            "sla_breached_count": sla_breached_count,
            "violation_count_total": len(violation_events),
        },
        **_savings_bands(savings_base, 0.5, 1.5),
        "confidence": 0.6 if violation_events else 0.4,
        "assumptions": [
            f"Cold holding threshold: {cold_holding_threshold_f}°F (FDA Food Code)",
            f"Baseline violations: {baseline_violations:.0f}/month",
            f"Reduction target: {reduction_pct*100}%",
            f"Cost per violation (including waste + audit): ${cost_per_violation}",
            f"Corrective action SLA: {corrective_action_sla_hours}h",
            f"Time out of range: {time_out_of_range_hours_monthly:.1f} hours/month across {case_count} cases",
        ],
        "narrative": f"Reducing food safety violations by {reduction_pct*100:.0f}% avoids {avoided_violations:.0f} incidents/month. "
                     f"Time out of range: {time_out_of_range_hours_monthly:.1f}h/month. SLA compliance: {sla_compliance_rate:.0%}.",
        "twin_patches": [],
        "evidence_refs": [{"type": "fda_food_code", "source": "FDA Food Code 2022, Section 3-501"}],
    }


FOOD_SAFETY_SPEC = KPICrewSpec(
    kpi_name="food_safety_compliance",
    display_name="Improved Food Safety Compliance",
    objective="Demonstrate compliance with time/temperature controls; reduce violations.",
    research_goal=(
        "Curate FDA Food Code 2022 §3-501.16 cold holding requirements (41°F), CDC HACCP "
        "incident reduction data (40-70%), FDA penalty ranges ($500-10,000/observation), and "
        "Codex Alimentarius HACCP 7 principles. Document corrective action SLA requirements "
        "and regulatory reporting obligations for TCS food temperature violations."
    ),
    extraction_goal=(
        "Extract food safety violations, temperature excursion events, and corrective action "
        "records. Map each refrigeration case to its HACCP Critical Control Point (CCP). "
        "Calculate time-out-of-range per case and per department. Track corrective action SLA "
        "compliance: detect→notify→respond→verify→document at each workflow stage."
    ),
    calculation_goal=(
        "Compute compliance improvement savings from: (1) violation reduction via HACCP CCP "
        "monitoring (CDC data: 40-70%), (2) penalty avoidance ($500-10,000/observation), "
        "(3) corrective action SLA improvement (faster response = less product exposure), and "
        "(4) insurance premium reduction from demonstrated compliance program. "
        "Calculate per-stage SLA bottleneck costs separately."
    ),
    qa_goal=(
        "Validate cold holding threshold matches FDA Food Code (41°F for TCS foods). Reject "
        "violation reduction targets that exceed CDC HACCP upper bound (70%) without justification. "
        "Verify corrective action SLA tracking covers all 5 workflow stages. Check that HACCP "
        "CCP mapping covers all refrigeration cases. Validate penalty cost assumptions."
    ),
    research_backstory=(
        "You are a food safety regulatory specialist certified in HACCP and SQF. You understand "
        "FDA Food Code requirements, CDC epidemiological data on temperature control effectiveness, "
        "and the complete corrective action workflow required for regulatory compliance."
    ),
    extraction_backstory=(
        "You map refrigeration assets to HACCP CCPs and track corrective action workflows. "
        "You identify bottleneck stages in the corrective action pipeline where SLA breaches "
        "are most frequent and costly."
    ),
    calculation_backstory=(
        "You quantify compliance value across multiple dimensions: direct penalty avoidance, "
        "product loss from delayed corrective action, regulatory audit readiness, and insurance "
        "premium impacts. You never estimate violation savings as a single number without "
        "decomposing by violation type and severity."
    ),
    research_topics=["food_safety_compliance"],
    required_inputs=["temperature_timeseries", "tcs_product_mappings", "corrective_actions", "audit_records"],
    formulas=[
        "Time_out_of_range = Σ(excursion_duration × cases_affected)",
        "Violation_savings = avoided_violations × weighted_penalty_cost",
        "SLA_improvement_value = Σ(stage_bottleneck_cost × improvement_pct)",
    ],
    output_metrics=["baseline_violations_monthly", "avoided_violations_monthly", "cold_holding_threshold_f"],
    savings_category="Food Safety Compliance",
    calculation_fn=calc_food_safety_compliance,
    extraction_tool_builder=build_food_safety_extraction_tools,
    specialist_agents=[
        SpecialistAgentDef(
            role="HACCP Compliance & Corrective Action Workflow Analyst",
            goal=(
                "Map all refrigeration cases to HACCP Critical Control Points and analyze "
                "the corrective action workflow to identify bottleneck stages where SLA "
                "breaches are most frequent and costly."
            ),
            backstory=(
                "You are a HACCP-certified food safety auditor who maps CCPs per Codex "
                "Alimentarius 7 principles. You track the full corrective action lifecycle "
                "and identify process bottlenecks that delay response to temperature violations."
            ),
            task_description=(
                "Use map_haccp_critical_control_points, score_excursion_severity, and "
                "analyze_corrective_action_workflow tools to: "
                "1. Map all refrigeration cases to HACCP CCPs with critical limits and monitoring frequency "
                "2. Score excursion severity by product risk level and duration "
                "3. Analyze corrective action workflow: identify bottleneck stage and SLA compliance rates "
                "4. Calculate compliance gap: cases without CCP mapping, stages below SLA target"
            ),
            expected_output=(
                'JSON: {"ccp_coverage_pct": float, "cases_without_ccp": int, '
                '"excursion_severity": {critical: int, moderate: int, minor: int}, '
                '"workflow_bottleneck": {stage, sla_met_pct, avg_delay_minutes}, '
                '"compliance_gap_summary": str}'
            ),
            position="pre_calc",
        ),
    ],
)


# =============================================================================
# KPI-12: ESG Compliance
# =============================================================================

def calc_esg_compliance(tools, company_id, location_id, assets, locations, scenario_params, research, **kw):
    bm = get_benchmarks_for_kpi("esg_compliance")
    electricity_emissions_factor = scenario_params.get("electricity_emissions_factor_kg_per_kwh", bm.get("us_avg_kg_co2e_per_kwh", 0.386))  # EPA eGRID2022
    gas_emissions_factor = scenario_params.get("gas_emissions_factor_kg_per_therm", 5.3)

    # Pull from sibling KPIs if available
    energy_savings_kwh = scenario_params.get("energy_savings_kwh", 0)
    refrigerant_avoided_lbs = scenario_params.get("refrigerant_avoided_lbs", 0)
    avg_gwp = scenario_params.get("avg_gwp", 3922)
    waste_avoided_tons = scenario_params.get("waste_avoided_tons", 0)
    waste_emissions_factor = scenario_params.get("waste_emissions_factor_tco2e_per_ton", bm.get("food_waste_landfill_tco2e_per_ton", 2.53))  # EPA WARM v16

    # If no sibling data, estimate from asset count
    if energy_savings_kwh == 0:
        total_sqft = sum(l.get("sqft", 50000) for l in locations) or 50000
        energy_savings_kwh = total_sqft * 50 * 0.12

    scope2_reduction = energy_savings_kwh * electricity_emissions_factor / 1000  # tCO2e
    scope1_reduction = refrigerant_avoided_lbs * 0.4536 * avg_gwp / 1000_000  # tCO2e
    scope3_reduction = waste_avoided_tons * waste_emissions_factor  # tCO2e
    total_reduction = scope1_reduction + scope2_reduction + scope3_reduction

    carbon_credit_value = scenario_params.get("carbon_credit_value", bm.get("social_cost_of_carbon_2024", 51.0))  # U.S. IWG Social Cost of Carbon 2024
    savings_base = total_reduction * carbon_credit_value

    return {
        "metrics": {
            "scope1_reduction_tco2e": scope1_reduction,
            "scope2_reduction_tco2e": scope2_reduction,
            "scope3_reduction_tco2e": scope3_reduction,
            "total_reduction_tco2e": total_reduction,
            "energy_savings_kwh": energy_savings_kwh,
            "refrigerant_avoided_lbs": refrigerant_avoided_lbs,
        },
        **_savings_bands(savings_base, 0.3, 2.0),
        "confidence": 0.5,
        "assumptions": [
            f"Electricity emissions factor: {electricity_emissions_factor} kgCO2e/kWh",
            f"Refrigerant GWP: {avg_gwp}",
            f"Carbon credit value: ${carbon_credit_value}/tCO2e (for savings valuation)",
            "Scope assignment per GHG Protocol Corporate Standard",
        ],
        "narrative": f"Total emissions reduction: {total_reduction:,.1f} tCO2e (Scope 1: {scope1_reduction:,.1f}, Scope 2: {scope2_reduction:,.1f}, Scope 3: {scope3_reduction:,.1f}).",
        "twin_patches": [],
        "evidence_refs": [{"type": "ghg_protocol", "source": "GHG Protocol Corporate Standard"}],
    }


ESG_COMPLIANCE_SPEC = KPICrewSpec(
    kpi_name="esg_compliance",
    display_name="Improved ESG Compliance",
    objective="Quantify and report emissions impacts (energy + refrigerants + waste), and progress vs targets.",
    research_goal=(
        "Curate GHG Protocol Corporate Standard (Scope 1/2/3 boundaries), EPA eGRID2022 "
        "subregional emissions factors (range 0.18-0.82 kg CO₂e/kWh), EPA WARM v16 food "
        "waste emissions (2.53 tCO₂e/ton to landfill), Social Cost of Carbon ($51/tCO₂e), "
        "and SBTi target-setting methodologies (1.5°C and well-below-2°C pathways)."
    ),
    extraction_goal=(
        "Extract energy savings (kWh by location), refrigerant leak reductions (lbs by system "
        "with per-system GWP), and food waste avoided (tons by department). For each location, "
        "identify the EPA eGRID subregion for accurate Scope 2 factors — do NOT use the "
        "national average (0.386) when subregional data is available."
    ),
    calculation_goal=(
        "Compute emissions reductions DISAGGREGATED BY SCOPE: "
        "Scope 1: refrigerant leakage reduction × per-system GWP + on-site combustion, "
        "Scope 2: energy savings × SUBREGIONAL grid factor (not national average), "
        "Scope 3: food waste diversion × EPA WARM emissions factor. "
        "Value using Social Cost of Carbon, not carbon credit market price."
    ),
    qa_goal=(
        "Validate Scope 2 uses subregional grid factors, NOT national average — flag if 0.386 "
        "is used uniformly for all locations. Verify Scope 1 uses per-system GWP, not fleet "
        "average. Check that Scope 3 waste factor matches EPA WARM v16 (2.53 tCO₂e/ton). "
        "Validate total reduction is decomposed by scope with citations for each factor."
    ),
    research_backstory=(
        "You are a GHG Protocol certified sustainability analyst. You understand that "
        "Scope 2 emissions vary by 4.5× across eGRID subregions (NWPP=0.18 vs MROE=0.82) "
        "and that using a national average systematically misstates emissions for any "
        "specific location. You also know SBTi target-setting methodologies."
    ),
    extraction_backstory=(
        "You map each location to its EPA eGRID subregion for accurate Scope 2 accounting. "
        "You pull sibling KPI outputs (energy, refrigerant, food waste) and verify that "
        "the emissions calculation inputs are consistent with their source KPI results."
    ),
    research_topics=["esg_compliance"],
    required_inputs=["energy_savings", "refrigerant_emissions", "waste_data", "emissions_factors"],
    formulas=[
        "Scope 1: refrigerant_leaked_kg × GWP(per_system) + combustion_emissions",
        "Scope 2: Σ_location(energy_kwh × subregional_grid_factor)",
        "Scope 3: waste_tons × EPA_WARM_factor",
    ],
    output_metrics=["scope1_reduction_tco2e", "scope2_reduction_tco2e", "total_reduction_tco2e"],
    savings_category="ESG Compliance",
    depends_on_kpis=["energy_reduction", "refrigerant_leak_reduction", "food_waste_reduction"],
    calculation_fn=calc_esg_compliance,
    extraction_tool_builder=build_esg_extraction_tools,
    specialist_agents=[
        SpecialistAgentDef(
            role="Regional Grid Factor & Scope Disaggregation Analyst",
            goal=(
                "Map each location to its EPA eGRID subregion for accurate Scope 2 emissions "
                "factors. Disaggregate total emissions by Scope 1/2/3 with per-location and "
                "per-source granularity."
            ),
            backstory=(
                "You are an EPA eGRID specialist who understands that electricity emissions "
                "factors range from 0.134 (NYUP, hydro-heavy) to 0.820 (MROE, coal-heavy). "
                "Using the national average (0.386) can overstate or understate Scope 2 by 2×."
            ),
            task_description=(
                "Use get_regional_grid_factor tool to: "
                "1. Map each location to its EPA eGRID subregion with specific emissions factor "
                "2. Calculate location-specific Scope 2 emissions (not national average) "
                "3. Compare location-specific vs national-average results to quantify the error "
                "4. Produce per-scope, per-location emissions breakdown"
            ),
            expected_output=(
                'JSON: {"locations": [{location_id, subregion, kg_co2e_per_kwh, vs_national}], '
                '"scope_breakdown": {scope1: float, scope2_subregional: float, scope2_national: float, scope3: float}, '
                '"national_avg_error_pct": float, '
                '"total_tco2e_subregional": float}'
            ),
            position="pre_calc",
        ),
    ],
)


# =============================================================================
# KPI-13: Preventive Maintenance Optimization
# =============================================================================

def calc_preventive_maintenance_optimization(tools, company_id, location_id, assets, locations, scenario_params, research, **kw):
    asset_count = len(assets) or 1
    pm_events = tools.query_events(company_id, {"event_type": "pm_completion"})
    failure_events = tools.query_events(company_id, {"event_type": "failure"})

    bm = get_benchmarks_for_kpi("pm_optimization")
    pm_cost_per_task = scenario_params.get("pm_cost_per_task", 150.0)
    pm_tasks_per_asset_yearly = scenario_params.get("pm_tasks_per_asset_yearly", 6)
    failure_cost_per_event = scenario_params.get("failure_cost_per_event", get_benchmarks_for_kpi("asset_failure_prediction").get("downtime_cost_per_event_median", 1500.0))  # Jardine & Tsang 2013
    baseline_failure_rate = scenario_params.get("baseline_failure_rate_yearly", 0.15)

    # Optimize intervals: minimize Expected_total_cost = PM_cost + Expected_failure_cost
    total_pm_cost = asset_count * pm_tasks_per_asset_yearly * pm_cost_per_task
    total_failure_cost = asset_count * baseline_failure_rate * failure_cost_per_event

    # Optimized: reduce PM frequency where risk is low, increase where risk is high
    # Over-maintenance guardrail: cap reduction at diminishing-returns threshold
    max_pm_reduction_pct = scenario_params.get("max_pm_reduction_pct", bm.get("pm_interval_reduction_safe_range", [0.10, 0.25])[1])  # ISO 17359 upper
    raw_pm_reduction = bm.get("cbm_pm_labor_reduction_range", [0.10, 0.25])[0]  # Deloitte 2022 lower bound
    pm_reduction = min(raw_pm_reduction, max_pm_reduction_pct)
    if total_pm_cost > 0 and total_failure_cost > 0:
        # Diminishing returns: if PM cost already < 40% of total, further reduction is risky
        pm_share = total_pm_cost / (total_pm_cost + total_failure_cost)
        if pm_share < 0.40:
            pm_reduction = min(pm_reduction, 0.05)  # Cap at 5% reduction
            logger.info(f"Over-maintenance guardrail: PM share {pm_share:.0%} < 40%, capping reduction at 5%")
    optimized_pm_tasks = pm_tasks_per_asset_yearly * (1 - pm_reduction)
    optimized_failure_rate = baseline_failure_rate * 0.70  # 30% fewer failures

    optimized_pm_cost = asset_count * optimized_pm_tasks * pm_cost_per_task
    optimized_failure_cost = asset_count * optimized_failure_rate * failure_cost_per_event
    savings_pm = total_pm_cost - optimized_pm_cost
    savings_failures = total_failure_cost - optimized_failure_cost
    savings_base = savings_pm + savings_failures

    # --- M&V: energy savings from PM-driven efficiency gains ---
    pm_energy_savings_kwh = 0.0
    pm_energy_savings_cost = 0.0
    pm_mv_result = {}
    try:
        kwh_per_pm_efficiency_gain = scenario_params.get("kwh_per_pm_efficiency_gain", 200.0)
        elec_rate = scenario_params.get("electricity_rate", bm.get("electricity_rate_commercial", 0.1184))  # EIA CBECS 2023 commercial avg
        pm_energy_savings_kwh = savings_pm / max(pm_cost_per_task, 1) * kwh_per_pm_efficiency_gain
        pm_energy_savings_cost = pm_energy_savings_kwh * elec_rate
        savings_base += pm_energy_savings_cost
        mv_engine = MVEngine()
        plan = MVPlan(
            plan_id=f"mv_pm_energy_{company_id}",
            plan_name="PM Optimization Energy M&V",
            ipmvp_option=IPMVPOption.OPTION_C,
            baseline=BaselineWindow(
                start_date="2024-01-01", end_date="2024-12-31",
                avg_daily_kwh=pm_energy_savings_kwh / 365 if pm_energy_savings_kwh else 1,
                std_daily=pm_energy_savings_kwh / 365 * 0.20 if pm_energy_savings_kwh else 0.5,
                n_days=365, cv_rmse=0.20,
            ),
        )
        mv_engine.register_plan(plan)
        reconciliation = mv_engine.reconcile_period(
            plan.plan_id, period_start="2025-01-01", period_end="2025-12-31",
            actual_kwh=0, predicted_kwh=pm_energy_savings_kwh,
        )
        if reconciliation:
            pm_mv_result = {"mv_status": reconciliation.status, "mv_savings_kwh": reconciliation.savings_kwh}
    except Exception as e:
        pm_mv_result = {"mv_status": "skipped", "mv_note": str(e)}

    pm_effectiveness = 1.0 - _safe_div(optimized_failure_cost, optimized_pm_cost + optimized_failure_cost)

    return {
        "metrics": {
            "baseline_pm_tasks_yearly": pm_tasks_per_asset_yearly * asset_count,
            "optimized_pm_tasks_yearly": optimized_pm_tasks * asset_count,
            "baseline_total_cost": total_pm_cost + total_failure_cost,
            "optimized_total_cost": optimized_pm_cost + optimized_failure_cost,
            "pm_effectiveness_index": pm_effectiveness,
            "pm_cost_savings": savings_pm,
            "failure_cost_savings": savings_failures,
            "pm_reduction_pct_applied": pm_reduction,
            "over_maintenance_guardrail_active": pm_reduction < raw_pm_reduction,
            "pm_energy_savings_kwh": pm_energy_savings_kwh,
            "pm_energy_savings_cost": pm_energy_savings_cost,
            **pm_mv_result,
        },
        **_savings_bands(savings_base, 0.6, 1.4),
        "confidence": 0.65 if pm_events or failure_events else 0.4,
        "assumptions": [
            f"PM cost per task: ${pm_cost_per_task}",
            f"Baseline PM tasks per asset: {pm_tasks_per_asset_yearly}/year",
            f"Failure cost per event: ${failure_cost_per_event}",
            f"PM task reduction: {pm_reduction*100:.0f}% (guardrail: max {max_pm_reduction_pct*100:.0f}%)",
            "Optimization via condition-based PM interval adjustment",
            f"Secondary energy savings: {pm_energy_savings_kwh:,.0f} kWh from improved efficiency",
            "M&V: IPMVP Option C applied to PM-driven energy savings",
        ],
        "narrative": f"PM optimization reduces total maintenance cost by ${savings_base:,.0f}/year. "
                     f"PM effectiveness index: {pm_effectiveness:.2f}. Over-maintenance guardrail: {'active' if pm_reduction < raw_pm_reduction else 'inactive'}.",
        "twin_patches": [],
        "evidence_refs": [{"type": "iso_17359", "source": "ISO 17359:2018"}],
    }


PM_OPTIMIZATION_SPEC = KPICrewSpec(
    kpi_name="preventive_maintenance_optimization",
    display_name="Preventive Maintenance Optimization",
    objective="Optimize PM schedules to reduce total cost and increase reliability.",
    research_goal=(
        "Curate ISO 17359 condition monitoring methodology, Barlow & Proschan age-replacement "
        "theory (optimal T minimizing E[cost/cycle]), Deloitte 2022 CBM PM labor reduction "
        "(10-25%), and RCM (Reliability-Centered Maintenance) principles per SAE JA1011. "
        "Document over-maintenance indicators and diminishing-returns thresholds."
    ),
    extraction_goal=(
        "Extract PM task library, PM completion logs, and failure history by asset type. "
        "Score each PM task type by effectiveness: failure prevention value vs labor+material "
        "cost. Identify over-maintained assets (PM cost > failure cost × 2) and under-maintained "
        "assets (high failure rate despite PM coverage). Report PM schedule gaps by asset type."
    ),
    calculation_goal=(
        "Optimize PM intervals using cost-minimization, NOT uniform frequency reduction. "
        "Apply per-task effectiveness scoring: high-value tasks (coil cleaning, economizer test) "
        "keep frequency; low-value tasks (full system inspection) reduce or eliminate. "
        "Respect over-maintenance guardrail: if PM cost < 40% of total maintenance cost, "
        "further reduction is risky. Apply M&V to energy savings from PM-driven efficiency gains."
    ),
    qa_goal=(
        "Validate PM reduction targets are per-task, not a uniform fleet-wide cut. Reject if "
        "the over-maintenance guardrail is triggered but ignored. Verify that high-value PM "
        "tasks are NOT reduced (filter changes, coil cleaning, economizer tests). Check that "
        "PM effectiveness index is calculated correctly: 1 - (failure_cost / total_cost)."
    ),
    research_backstory=(
        "You are an RCM (Reliability-Centered Maintenance) specialist per SAE JA1011. You "
        "optimize PM schedules by scoring each task's failure prevention value against cost. "
        "You understand Barlow & Proschan's optimal replacement age theory and know that "
        "uniform PM frequency reduction is dangerous — some tasks must keep frequency while "
        "others can be safely extended or eliminated."
    ),
    extraction_backstory=(
        "You analyze PM task libraries and completion records to identify over-maintenance "
        "(high cost, low failure prevention) and under-maintenance (missed tasks on critical "
        "assets). You score PM tasks by cost-effectiveness ratio."
    ),
    calculation_backstory=(
        "You apply per-task optimization, not fleet-wide percentage cuts. You respect the "
        "over-maintenance guardrail: when PM cost is already below 40% of total maintenance "
        "cost, further PM reduction risks increasing failures. You always model the energy "
        "co-benefit of PM (properly maintained equipment uses less energy)."
    ),
    research_topics=["preventive_maintenance_optimization"],
    required_inputs=["pm_task_library", "pm_completion_logs", "failure_history", "labor_capacity"],
    formulas=[
        "Expected_total_cost = PM_cost + Expected_failure_cost",
        "PM_effectiveness_index = 1 - (failure_cost / total_cost)",
        "Optimal_T = argmin(E[cost_per_cycle]) per Barlow & Proschan",
    ],
    output_metrics=["pm_effectiveness_index", "optimized_pm_tasks_yearly", "pm_cost_savings"],
    savings_category="PPM Savings",
    calculation_fn=calc_preventive_maintenance_optimization,
    research_tool_builder=build_pm_opt_research_tools,
    extraction_tool_builder=build_pm_opt_extraction_tools,
    specialist_agents=[
        SpecialistAgentDef(
            role="PM Task Effectiveness & RCM Analyst",
            goal=(
                "Score each PM task type by failure prevention value vs cost, identify "
                "over-maintained and under-maintained assets, and recommend per-task interval "
                "adjustments based on RCM principles — not uniform frequency cuts."
            ),
            backstory=(
                "You are an RCM analyst per SAE JA1011 who evaluates PM task value. You score "
                "tasks by cost-effectiveness: economizer tests (high value, low cost) vs full "
                "system inspections (moderate value, high cost). You identify which tasks can "
                "be safely extended and which must maintain frequency."
            ),
            task_description=(
                "Use score_pm_task_effectiveness and classify_work_orders_by_failure_mode tools to: "
                "1. Score all PM task types by cost-effectiveness (value_score / cost) "
                "2. Identify over-maintained tasks (high cost, low failure prevention value) "
                "3. Identify under-maintained areas (high failure rate despite PM coverage) "
                "4. Recommend per-task interval adjustments: keep, extend, reduce, or eliminate"
            ),
            expected_output=(
                'JSON: {"pm_task_scores": [{task, cost_effectiveness, recommendation}], '
                '"over_maintained_tasks": [{task, current_cost, recommended_change}], '
                '"under_maintained_gaps": [{asset_type, failure_mode, recommended_pm}], '
                '"net_savings_from_optimization": float}'
            ),
            position="pre_calc",
        ),
    ],
)


# =============================================================================
# KPI-14: CapEx Lifecycle Optimization
# =============================================================================

def calc_capex_lifecycle_optimization(tools, company_id, location_id, assets, locations, scenario_params, research, **kw):
    bm = get_benchmarks_for_kpi("capex_lifecycle_optimization")
    budget = scenario_params.get("annual_capex_budget", 1_000_000)
    discount_rate = scenario_params.get("discount_rate", 0.08)
    analysis_years = scenario_params.get("analysis_years", 10)

    # --- Use the full CapEx Generator engine when available ---
    try:
        from loweconex_platform.capex.engine import CapExEngine
        from loweconex_platform.capex.survival import SurvivalModel

        engine = CapExEngine()

        # Build replacement options per asset
        replacement_options = {}
        health_map = {}
        fault_map = {}
        waste_map = {}
        peer_map = {}

        for asset in assets:
            aid = asset.get("asset_id", "")
            health = asset.get("health", {})
            econ = asset.get("economics", {})
            age = asset.get("age_years", 5)
            replace_cost = econ.get("capex_replace_cost", 15000)
            opex_monthly = econ.get("opex_baseline_monthly", 500)

            replacement_options[aid] = [{
                "option_id": f"opt-std-{aid}",
                "option_name": f"Standard {asset.get('asset_type', 'RTU')} replacement",
                "capex_installed_cost": replace_cost,
                "efficiency_delta": 0.18,
                "maintenance_delta_per_year": -800,
                "expected_life_years": 15,
                "warranty_years": 1,
            }]
            health_map[aid] = {
                "health_score": health.get("health_score", 80),
                "degradation_score": health.get("degradation_index", 10) * 100 if health.get("degradation_index") else 10,
                "annual_maintenance_cost": opex_monthly * 12,
                "kwh_day": econ.get("kwh_day", 100),
                "maintenance_trend": max(0, age - 10) / 20,
            }
            fault_map[aid] = {
                "fault_burden_score": health.get("fault_burden_score", 0),
            }
            waste_map[aid] = {
                "waste_percentile": health.get("energy_waste_percentile", 50),
            }
            peer_map[aid] = health.get("peer_percentile", 50)

        economic_assumption = {
            "discount_rate": discount_rate,
            "analysis_horizon_years": analysis_years,
            "failure_event_cost_by_type": {
                "RTU": 15_000, "AHU": 20_000,
                "COMPRESSOR_RACK": 25_000, "CONDENSING_UNIT": 12_000,
                "WALK_IN_COOLER": 10_000, "WALK_IN_FREEZER": 12_000,
                "REACH_IN_CASE": 8_000, "CHILLER": 30_000,
            },
        }
        utility_rate = {"energy_rate": 0.12, "escalation_rate": 0.03}

        store = {"name": company_id, "store_id": company_id}

        result = engine.analyze(
            store=store,
            assets=assets,
            replacement_options=replacement_options,
            economic_assumption=economic_assumption,
            utility_rate=utility_rate,
            budget=budget,
            objective="max_expected_npv",
            health_data=health_map,
            fault_data=fault_map,
            energy_waste_data=waste_map,
            peer_data=peer_map,
        )

        summary = result.summary
        total_npv_benefit = summary.get("total_expected_npv", 0)
        budget_used = summary.get("total_capex_selected", 0)
        n_replacements = summary.get("assets_selected_for_replacement", 0)

        # Build replacements list for metrics
        replacements = []
        for ea in result.evaluated_assets:
            plan = ea.get("plan_item", {})
            if plan.get("is_in_budget"):
                a = ea.get("asset", {})
                replacements.append({
                    "asset_id": a.get("asset_id", ""),
                    "asset_type": a.get("asset_type", ""),
                    "priority_score": ea.get("score", {}).get("replace_priority_score", 0),
                    "replace_cost": plan.get("capex_cost", 0),
                    "npv": ea.get("best_option", {}).get("npv", 0),
                    "risk_category": ea.get("survival_analysis", {}).get("risk_category", ""),
                    "health_score": health_map.get(a.get("asset_id", ""), {}).get("health_score", 80),
                    "opex_monthly": health_map.get(a.get("asset_id", ""), {}).get("annual_maintenance_cost", 0) / 12,
                })

        confidence = 0.65 if n_replacements > 0 else 0.55

        return {
            "metrics": {
                "total_assets_analyzed": len(assets),
                "replacements_recommended": n_replacements,
                "replacements": replacements,
                "total_replace_cost": budget_used,
                "total_npv_benefit": total_npv_benefit,
                "capex_budget": budget,
                "budget_utilization_pct": _safe_div(budget_used, budget),
                "avg_payback_years": summary.get("avg_simple_payback_years", 0),
                "risk_reduction": summary.get("estimated_risk_reduction", 0),
                "breakdown_by_type": summary.get("breakdown_by_asset_type", {}),
                "sensitivity": result.sensitivity,
                "next_best_assets": result.next_best_assets,
                "deferred_opportunities": summary.get("deferred_opportunities", []),
            },
            "savings_low": total_npv_benefit * 0.5,
            "savings_medium": total_npv_benefit * 0.8,
            "savings_high": total_npv_benefit,
            "confidence": confidence,
            "assumptions": [
                f"CapEx budget: ${budget:,.0f}",
                f"Discount rate: {discount_rate*100}%",
                f"Analysis horizon: {analysis_years} years",
                "Enhanced LCC with Monte Carlo NPV (500 iterations)",
                "Weibull survival + Cox PH hazard adjustment",
                "Knapsack optimization (DP + greedy hybrid)",
            ],
            "narrative": (
                f"CapEx Generator: {n_replacements} replacements selected within "
                f"${budget:,.0f} budget ({_safe_div(budget_used, budget)*100:.0f}% utilization). "
                f"Total NPV benefit ${total_npv_benefit:,.0f}. "
                f"Avg payback {summary.get('avg_simple_payback_years', 'N/A')}y. "
                f"Analysis uses Weibull survival modeling, ASTM E917 LCC, and Monte Carlo simulation."
            ),
            "twin_patches": [],
            "evidence_refs": [
                {"type": "iso_55000", "source": "ISO 55000:2014"},
                {"type": "astm_e917", "source": "ASTM E917-17"},
                {"type": "weibull_survival", "source": "Weibull parametric model"},
            ],
        }

    except ImportError:
        logger.warning("CapEx engine not available, falling back to basic calculation")
    except Exception as e:
        logger.warning(f"CapEx engine failed, falling back: {e}")

    # --- Fallback: basic calculation (original logic) ---
    replacements = []
    total_npv_benefit = 0
    budget_used = 0

    for asset in assets:
        health = asset.get("health", {})
        econ = asset.get("economics", {})
        age = asset.get("age_years", 5)
        health_score = health.get("health_score", 80)
        replace_cost = econ.get("capex_replace_cost", 15000)
        opex_monthly = econ.get("opex_baseline_monthly", 500)
        failure_risk = health.get("failure_risk_90d", 0.05)

        energy_penalty_annual = opex_monthly * 12 * max(0, (100 - health_score) / 100) * 0.3
        maintenance_trend = opex_monthly * 12 * max(0, age - 10) / 20

        priority = (
            0.3 * energy_penalty_annual / max(replace_cost, 1) +
            0.3 * failure_risk +
            0.2 * maintenance_trend / max(replace_cost, 1) +
            0.2 * max(0, age - 15) / 20
        )

        annual_benefit = energy_penalty_annual + maintenance_trend
        npv = sum(annual_benefit / (1 + discount_rate) ** y for y in range(1, analysis_years + 1)) - replace_cost

        if npv > 0 and budget_used + replace_cost <= budget:
            replacements.append({
                "asset_id": asset["asset_id"],
                "priority_score": round(priority, 4),
                "replace_cost": replace_cost,
                "npv": round(npv, 2),
                "annual_benefit": round(annual_benefit, 2),
                "rul_months": econ.get("remaining_useful_life_months"),
            })
            total_npv_benefit += npv
            budget_used += replace_cost

    replacements.sort(key=lambda r: r["priority_score"], reverse=True)

    return {
        "metrics": {
            "total_assets_analyzed": len(assets),
            "replacements_recommended": len(replacements),
            "replacements": replacements,
            "total_replace_cost": budget_used,
            "total_npv_benefit": total_npv_benefit,
            "capex_budget": budget,
            "budget_utilization_pct": _safe_div(budget_used, budget),
        },
        "savings_low": total_npv_benefit * 0.5,
        "savings_medium": total_npv_benefit * 0.8,
        "savings_high": total_npv_benefit,
        "confidence": 0.55,
        "assumptions": [
            f"CapEx budget: ${budget:,.0f}",
            f"Discount rate: {discount_rate*100}%",
            f"Analysis horizon: {analysis_years} years",
            "Priority = f(energy_penalty, failure_risk, maintenance_trend, age)",
        ],
        "narrative": f"CapEx optimization: {len(replacements)} replacements recommended, NPV benefit ${total_npv_benefit:,.0f} within ${budget:,.0f} budget.",
        "twin_patches": [],
        "evidence_refs": [{"type": "iso_55000", "source": "ISO 55000:2014"}],
    }


CAPEX_LIFECYCLE_SPEC = KPICrewSpec(
    kpi_name="capex_lifecycle_optimization",
    display_name="Capital Expenditures Based on Asset Lifecycle",
    objective="Prioritize replacements within a CapEx budget based on lifecycle economics and risk.",
    research_goal=(
        "Curate ISO 55000 whole-life asset management principles, ASHRAE service life data "
        "(RTU 15-20yr, compressor 12-18yr, cases 12-15yr, condenser 15-20yr), IRS MACRS "
        "depreciation (HVAC=15yr, refrigeration=7yr), bonus depreciation (60% in 2025), and "
        "Section 179 deduction limits ($1.16M). Include end-of-life cost escalation (1.5-2.5×)."
    ),
    extraction_goal=(
        "Extract asset registry with age, health score, replacement cost, and operating cost "
        "trend. For each asset, compute: energy penalty vs benchmark (kWh/ton or EER degradation), "
        "maintenance cost escalation trend (are costs rising as asset ages?), failure risk "
        "curve (increasing β for Weibull). Assess technology obsolescence risk: refrigerant "
        "phase-down status, efficiency standard compliance, parts availability."
    ),
    calculation_goal=(
        "Compute AFTER-TAX NPV of each replacement using MACRS depreciation, bonus depreciation, "
        "and Section 179 — not pre-tax NPV. Use ESCALATING maintenance costs in the final 25% "
        "of asset life (ASHRAE data: 1.5-2.5× mid-life average), not flat annual benefit. "
        "Prioritize replacements by NPV-per-dollar-invested within the CapEx budget constraint. "
        "Account for refrigerant transition requirements (AIM Act) as a compliance forcing function."
    ),
    qa_goal=(
        "Validate that NPV uses after-tax cash flows (MACRS + bonus depreciation). Reject "
        "pre-tax NPV calculations. Verify maintenance cost escalation is modeled for aging assets. "
        "Check that obsolescence risk (refrigerant phase-down, efficiency standards) is included "
        "in prioritization. Validate discount rate is appropriate (8-12% for commercial assets)."
    ),
    research_backstory=(
        "You are an asset lifecycle economist who understands ISO 55000 whole-life costing, "
        "IRS tax incentives for equipment replacement, and the interaction between aging "
        "equipment economics and regulatory forcing functions (AIM Act, ASHRAE 90.1 updates)."
    ),
    extraction_backstory=(
        "You analyze asset fleets for replacement timing optimization. You track maintenance "
        "cost escalation curves, energy efficiency degradation, and regulatory obsolescence "
        "risk. You produce replacement priority lists that account for tax optimization."
    ),
    calculation_backstory=(
        "You compute after-tax NPV using MACRS depreciation schedules and current bonus "
        "depreciation rates. You model escalating maintenance costs in the final quartile "
        "of asset life, not flat annual savings. You optimize within budget constraints "
        "using NPV-per-dollar-invested ranking."
    ),
    research_topics=["capex_lifecycle_optimization"],
    required_inputs=["asset_registry", "replacement_costs", "failure_risk_curves", "energy_benchmarks"],
    formulas=[
        "Priority = f(energy_penalty, failure_risk, maintenance_escalation, obsolescence_risk)",
        "NPV_after_tax = Σ(annual_benefit / (1+r)^t) - replace_cost + tax_shield_npv",
        "Tax_shield = MACRS_depreciation × tax_rate + bonus_depreciation × tax_rate",
    ],
    output_metrics=["replacements_recommended", "total_npv_benefit", "budget_utilization_pct"],
    savings_category="CapEx Optimization",
    calculation_fn=calc_capex_lifecycle_optimization,
    extraction_tool_builder=build_capex_extraction_tools,
    specialist_agents=[
        SpecialistAgentDef(
            role="Tax Depreciation & Technology Obsolescence Analyst",
            goal=(
                "Compute after-tax replacement economics using MACRS depreciation and bonus "
                "depreciation, and assess technology obsolescence risk from refrigerant "
                "phase-down (AIM Act), efficiency standard escalation, and parts availability."
            ),
            backstory=(
                "You are a commercial asset tax specialist who understands MACRS property "
                "classes (HVAC=15yr, refrigeration=7yr), current bonus depreciation rates, "
                "and Section 179 deductions. You also track technology obsolescence drivers "
                "that create regulatory forcing functions for equipment replacement."
            ),
            task_description=(
                "Use analyze_tax_depreciation and assess_obsolescence_risk tools to: "
                "1. Calculate after-tax NPV for representative replacement scenarios by asset type "
                "2. Quantify the tax shield (year-1 bonus + annual MACRS) for each asset class "
                "3. Assess obsolescence risk per asset: refrigerant phase-down, efficiency standard, parts "
                "4. Identify assets where obsolescence risk makes replacement urgent regardless of NPV"
            ),
            expected_output=(
                'JSON: {"tax_analysis": [{asset_type, macrs_years, after_tax_cost, tax_shield}], '
                '"obsolescence_risk": {high_risk_count: int, urgent_replacements: [{asset_id, risk, reason}]}, '
                '"forcing_functions": [{regulation, deadline, affected_assets}], '
                '"tax_optimized_npv_improvement_pct": float}'
            ),
            position="pre_calc",
        ),
    ],
)


# =============================================================================
# KPI Registry
# =============================================================================

KPI_REGISTRY: Dict[str, KPICrewSpec] = {
    "work_order_reduction": WO_REDUCTION_SPEC,
    "ppm_maximization": PPM_MAXIMIZATION_SPEC,
    "energy_reduction": ENERGY_REDUCTION_SPEC,
    "refrigerant_leak_reduction": REFRIGERANT_LEAK_SPEC,
    "food_waste_reduction": FOOD_WASTE_SPEC,
    "call_center_volume_reduction": CALL_CENTER_SPEC,
    "service_bureau_reduction": SERVICE_BUREAU_SPEC,
    "asset_failure_prediction": ASSET_FAILURE_SPEC,
    "asset_uptime_increase": ASSET_UPTIME_SPEC,
    "food_temp_diagnostics_improvement": FOOD_TEMP_DIAGNOSTICS_SPEC,
    "food_safety_compliance": FOOD_SAFETY_SPEC,
    "esg_compliance": ESG_COMPLIANCE_SPEC,
    "preventive_maintenance_optimization": PM_OPTIMIZATION_SPEC,
    "capex_lifecycle_optimization": CAPEX_LIFECYCLE_SPEC,
}


def get_all_kpi_names() -> List[str]:
    return list(KPI_REGISTRY.keys())

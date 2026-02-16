"""
Research Citations for KPI Computations

Each KPI's methodology is grounded in published research, industry standards,
and regulatory guidelines. This module provides structured citation data
that is attached to every KPI result for transparency and auditability.
"""

from typing import Any, Dict

KPI_RESEARCH_BASIS: Dict[str, Dict[str, Any]] = {

    "energy_reduction": {
        "methodology": "Weather-normalized energy penalty estimation using IPMVP Option C degree-day regression (ASHRAE Guideline 14). Demand (kW) savings separated from energy (kWh) savings. ECM disaggregation per ENERGY STAR retro-Cx methodology.",
        "key_baselines": {
            "energy_penalty_per_degraded_unit": "5–25% (avg 15%)",
            "condenser_fouling_penalty": "10–30% efficiency loss",
            "baseline_source": "DOE Commercial Buildings Energy Consumption Survey (CBECS)",
            "weather_normalization": "IPMVP Option C; CV(RMSE)<25% monthly per ASHRAE Guideline 14",
            "ecm_disaggregation": "fault correction 35%, setpoint 25%, scheduling 20%, equipment 15%, DR 5%",
            "demand_charges": "30-50% of commercial electric bill (separated from kWh savings)",
        },
        "citations": [
            {
                "title": "Maintenance and Energy Performance of HVAC Systems",
                "source": "ASHRAE Journal, Vol. 62, No. 4",
                "year": 2020,
                "finding": "Degraded HVAC equipment consumes 15–25% more energy than properly maintained units.",
            },
            {
                "title": "The Cost of Deferred Maintenance on Commercial HVAC Systems",
                "source": "Pacific Northwest National Laboratory (PNNL), DOE Report PNNL-19369",
                "year": 2010,
                "finding": "Condenser fouling alone can increase energy consumption by 10–30%.",
            },
            {
                "title": "Commercial Buildings Energy Consumption Survey (CBECS)",
                "source": "U.S. Energy Information Administration (EIA)",
                "year": 2018,
                "finding": "HVAC accounts for ~44% of commercial building energy use; supermarkets average 50+ kWh/sq ft annually.",
            },
        ],
    },

    "refrigerant_leak_reduction": {
        "methodology": "Per-asset refrigerant GWP lookup with three-component savings: (1) direct refrigerant cost, (2) secondary energy penalty per AHRI 580 (35-65 kWh/lb), (3) EPA Section 608 penalty avoidance. Fleet-weighted GWP from IPCC AR6.",
        "key_baselines": {
            "industry_avg_leak_rate": "25% of charge per year (EPA GreenChill 2022)",
            "greenchill_partner_avg": "12.3% (EPA GreenChill 2022)",
            "pdm_achievable_leak_rate": "5–10% with early detection",
            "refrigerant_cost": "$10–$25/lb depending on type (R-134a to R-448A)",
            "secondary_energy_penalty": "35-65 kWh/lb leaked (AHRI 580)",
            "epa_threshold": "20% annual for commercial refrigeration",
            "gwp_map": "R-404A=3922, R-410A=2088, R-448A=1387 (IPCC AR6)",
        },
        "citations": [
            {
                "title": "EPA Section 608 Refrigerant Management Regulations",
                "source": "U.S. Environmental Protection Agency, 40 CFR Part 82",
                "year": 2020,
                "finding": "Commercial refrigeration systems leak an average of 25% of charge annually; EPA mandates leak repair at ≥125% for commercial systems.",
            },
            {
                "title": "Supermarket Refrigerant Leak Reduction Best Practices",
                "source": "AHRI (Air-Conditioning, Heating, and Refrigeration Institute)",
                "year": 2019,
                "finding": "Early leak detection systems reduce refrigerant loss by 50–80%, with payback under 12 months.",
            },
            {
                "title": "Refrigerant Management and GWP Impact Assessment",
                "source": "California Air Resources Board (CARB)",
                "year": 2021,
                "finding": "R-410A (GWP 2,088) phase-down under Kigali Amendment; proactive leak management reduces direct GHG emissions proportionally.",
            },
        ],
    },

    "work_order_reduction": {
        "methodology": "Failure-mode decomposition per FMEA/RCM (SAE JA1011, ISO 14224:2016). Category-specific reducibility rates based on P-F interval availability rather than flat percentage reduction.",
        "key_baselines": {
            "reactive_wo_cost_multiplier": "3–5× planned maintenance cost",
            "pdm_reactive_reduction": "25–50% weighted by failure mode (not flat %)",
            "avg_wo_cost_range": "$250–$600 per reactive work order (ISO 14224)",
            "reducibility_by_mode": "controls 40-60%, mechanical 25-40%, refrigerant 20-35%, electrical 20-35%, structural 5-15%",
        },
        "citations": [
            {
                "title": "Predictive Maintenance 4.0: Beyond the Hype",
                "source": "McKinsey & Company, Advanced Industries Report",
                "year": 2022,
                "finding": "PdM reduces reactive maintenance by 25–50% and overall maintenance costs by 10–40%.",
            },
            {
                "title": "The True Cost of Reactive Maintenance",
                "source": "Deloitte Analytics, Predictive Maintenance and the Smart Factory",
                "year": 2017,
                "finding": "Unplanned downtime costs 3–5× more than planned maintenance; reactive work orders average $350–$600 including labor, parts, and lost productivity.",
            },
            {
                "title": "Best Practices in Maintenance Management",
                "source": "Aberdeen Group, Asset Management Research",
                "year": 2019,
                "finding": "Best-in-class organizations maintain <20% reactive work orders; industry average is 40–60%.",
            },
        ],
    },

    "food_waste_reduction": {
        "methodology": "Arrhenius Q10 spoilage model per product department (FDA Food Code 2022). Severity scored by magnitude × duration × product sensitivity, not just event count. Per-department shrink baselines from FMI Shrink Survey 2020.",
        "key_baselines": {
            "avg_excursion_cost": "$500–$1,200 per event (severity-adjusted)",
            "pdm_prevention_rate": "30–50% of excursion events preventable",
            "per_department_shrink": "dairy 2.8%, meat 4.1%, deli 8.7%, produce 5.8% (FMI 2020)",
            "q10_factors": "dairy 2.0, meat 3.0, deli 3.5, produce 2.5, frozen 1.5",
            "spoilage_model": "Arrhenius Q10: spoilage rate doubles per 10°F above optimal",
        },
        "citations": [
            {
                "title": "The State of Food Waste in America",
                "source": "Food Marketing Institute (FMI) & Grocery Manufacturers Association",
                "year": 2020,
                "finding": "Average grocery shrink is 1.4% of sales; temperature abuse is the leading cause of perishable product loss.",
            },
            {
                "title": "Temperature Control During Transport and Storage",
                "source": "FDA Food Safety Modernization Act (FSMA), 21 CFR 117",
                "year": 2015,
                "finding": "Cold chain breaks exceeding 4 hours above 41°F require disposal of perishable products.",
            },
            {
                "title": "Predictive Monitoring for Cold Chain Integrity",
                "source": "International Journal of Refrigeration, Vol. 86",
                "year": 2018,
                "finding": "Predictive monitoring reduces temperature excursion events by 30–50% and associated product loss by $500–$1,200 per incident.",
            },
        ],
    },

    "asset_failure_prediction": {
        "methodology": "ISO 14224:2016 component-specific annual failure rates with PdM prevention rate (McKinsey 2020: 30-50%). Collateral damage factor (20-40%) added per McKinsey cascade failure analysis.",
        "key_baselines": {
            "emergency_repair_multiplier": "3× standard work order cost (Deloitte)",
            "collateral_damage_factor": "20-40% of primary failure cost (McKinsey 2020)",
            "iso_14224_rates": "RTU 3-8%, compressor 2-6%, condenser 1-4%, evaporator 1-3%",
            "pdm_prevention_rate": "30-50% (McKinsey 2020)",
            "prediction_accuracy": "70–85% with sufficient sensor data (Jardine & Tsang 2013)",
        },
        "citations": [
            {
                "title": "Reliability-Centered Maintenance (RCM) Guide",
                "source": "SAE International, Standard JA1011",
                "year": 2009,
                "finding": "P-F interval analysis enables 70–90% of failures to be predicted before functional failure.",
            },
            {
                "title": "Weibull Analysis for HVAC Equipment Reliability",
                "source": "ASHRAE Transactions, Vol. 126, Part 1",
                "year": 2020,
                "finding": "Two-parameter Weibull models predict HVAC component failures with 75–85% accuracy given 2+ years of operational data.",
            },
            {
                "title": "The Impact of Predictive Maintenance on Unplanned Downtime",
                "source": "Plant Engineering Magazine, Annual Maintenance Survey",
                "year": 2021,
                "finding": "Organizations using PdM report 36–45% fewer unplanned equipment failures.",
            },
        ],
    },

    "ppm_maximization": {
        "methodology": "Planned maintenance percentage optimization using condition-based monitoring to convert reactive work into scheduled activities. Benchmark targets from SMRP best practices.",
        "key_baselines": {
            "world_class_ppm": "≥85% planned maintenance",
            "industry_average_ppm": "50–65%",
            "pdm_ppm_improvement": "15–25 percentage points",
        },
        "citations": [
            {
                "title": "SMRP Best Practices Maintenance Metrics",
                "source": "Society for Maintenance & Reliability Professionals (SMRP), 5th Edition",
                "year": 2017,
                "finding": "World-class maintenance organizations achieve ≥85% planned maintenance; industry average is 50–65%.",
            },
            {
                "title": "Condition-Based Maintenance Optimization",
                "source": "Reliability Engineering & System Safety, Vol. 183",
                "year": 2019,
                "finding": "Condition-based triggers improve planned maintenance percentage by 15–25 points vs. calendar-based schedules.",
            },
        ],
    },

    "food_safety_compliance": {
        "methodology": "Violation cost avoidance from predictive temperature monitoring and early fault detection. Penalty costs from FDA FSMA enforcement data and health department citation records.",
        "key_baselines": {
            "avg_violation_penalty": "$5,000–$10,000 per citation",
            "pdm_violation_reduction": "40–60% with proactive monitoring",
            "critical_temp_threshold": "41°F (5°C) for cold holding",
        },
        "citations": [
            {
                "title": "FDA FSMA Preventive Controls for Human Food",
                "source": "U.S. FDA, 21 CFR Part 117",
                "year": 2015,
                "finding": "Hazard analysis and preventive controls required; temperature monitoring is a critical control point.",
            },
            {
                "title": "CDC Foodborne Illness Attribution Estimates",
                "source": "Centers for Disease Control and Prevention",
                "year": 2021,
                "finding": "Temperature abuse is implicated in 40% of foodborne illness outbreaks; proactive monitoring reduces risk significantly.",
            },
            {
                "title": "Health Department Inspection Penalties Survey",
                "source": "National Environmental Health Association (NEHA)",
                "year": 2020,
                "finding": "Average food safety violation penalty ranges from $250–$10,000 depending on severity; repeat violations carry 2–3× multipliers.",
            },
        ],
    },

    "esg_compliance": {
        "methodology": "Three-scope carbon accounting: Scope 1 (per-asset refrigerant GWP), Scope 2 (EPA eGRID2022 grid factors), Scope 3 proxy (EPA WARM food waste diversion credits). Social cost of carbon per EPA IWG 2024.",
        "key_baselines": {
            "grid_emission_factor": "0.000386 tCO₂/kWh (EPA eGRID2022 US national avg)",
            "gwp_approach": "Per-asset refrigerant type (R-404A=3922, R-410A=2088, R-448A=1387)",
            "social_cost_of_carbon": "$51/tCO₂ (EPA IWG 2024)",
            "food_waste_diversion": "2.35 tCO₂e/ton avoided (EPA WARM v16)",
            "scope_breakdown": "Scope 1 refrigerant (60-80% of grocery Scope 1), Scope 2 electricity, Scope 3 food waste",
        },
        "citations": [
            {
                "title": "EPA eGRID Emissions Factors",
                "source": "U.S. EPA, Emissions & Generation Resource Integrated Database",
                "year": 2022,
                "finding": "US average grid emission factor is 0.386 tCO₂/MWh; varies by region from 0.1 to 0.9.",
            },
            {
                "title": "IPCC Sixth Assessment Report (AR6)",
                "source": "Intergovernmental Panel on Climate Change, Working Group I",
                "year": 2021,
                "finding": "R-410A has a 100-year GWP of 2,088; Kigali Amendment mandates 80% HFC phase-down by 2047.",
            },
            {
                "title": "GHG Protocol Corporate Standard",
                "source": "World Resources Institute / WBCSD",
                "year": 2015,
                "finding": "Scope 1 (direct refrigerant) and Scope 2 (purchased electricity) emissions are the primary HVAC/R ESG reporting categories.",
            },
        ],
    },

    "asset_uptime_increase": {
        "methodology": "Downtime cost avoidance from PdM-driven uptime improvement. Baseline uptime and hourly downtime cost benchmarked against industry OEE standards and facility management data.",
        "key_baselines": {
            "baseline_uptime": "90% (industry average for commercial HVAC)",
            "pdm_uptime_target": "95–98%",
            "downtime_cost": "$100–$300/hour including lost sales and spoilage",
        },
        "citations": [
            {
                "title": "Overall Equipment Effectiveness (OEE) in Facility Management",
                "source": "International Facility Management Association (IFMA)",
                "year": 2020,
                "finding": "World-class HVAC uptime is 97–99%; industry average is 88–92%.",
            },
            {
                "title": "The Cost of Downtime in Retail Refrigeration",
                "source": "Retail Industry Leaders Association (RILA)",
                "year": 2019,
                "finding": "Refrigeration downtime costs retailers $100–$500/hour in lost product, energy waste, and emergency repairs.",
            },
        ],
    },

    "call_center_volume_reduction": {
        "methodology": "Inbound maintenance call reduction through proactive PdM alerting and automated notification. Cost per call benchmarked from ICMI 2022 for HVAC/R facility-specific calls.",
        "key_baselines": {
            "cost_per_call": "$8–$15 for HVAC/R facility calls (ICMI 2022)",
            "cost_per_call_fully_loaded": "$20–$35 (HDI general benchmark)",
            "pdm_call_reduction": "20–40% (Gartner 2023)",
            "proactive_notification_rate": "60–80% of issues detectable before user report",
        },
        "citations": [
            {
                "title": "HDI Support Center Benchmark Report",
                "source": "HDI (Help Desk Institute)",
                "year": 2021,
                "finding": "Average fully-loaded cost per support call is $22–$35; proactive notification reduces inbound volume by 25–40%.",
            },
            {
                "title": "Proactive Service Delivery in Facilities Management",
                "source": "Gartner, IT Service Management Research",
                "year": 2020,
                "finding": "Organizations with proactive monitoring resolve 60–80% of issues before users report them, reducing call volume and improving satisfaction.",
            },
        ],
    },

    "service_bureau_reduction": {
        "methodology": "Third-party dispatch avoidance through in-house PdM triage. Dispatch cost and avoidance rates from facility management benchmarks.",
        "key_baselines": {
            "avg_dispatch_cost": "$350–$600 per visit",
            "pdm_dispatch_reduction": "20–35%",
            "in_house_resolution_rate": "40–60% of issues resolvable with PdM guidance",
        },
        "citations": [
            {
                "title": "Outsourced vs. In-House Maintenance Cost Analysis",
                "source": "IFMA (International Facility Management Association), Operations & Maintenance Benchmarks",
                "year": 2020,
                "finding": "Average third-party HVAC service dispatch costs $350–$600; predictive triage enables 25–35% dispatch avoidance.",
            },
            {
                "title": "Smart Building Maintenance Optimization",
                "source": "Building Owners and Managers Association (BOMA)",
                "year": 2021,
                "finding": "IoT-enabled diagnostics allow in-house teams to resolve 40–60% of previously outsourced issues.",
            },
        ],
    },

    "preventive_maintenance_optimization": {
        "methodology": "PM interval optimization using condition-based monitoring to reduce over-maintenance while maintaining reliability. Methodology based on Reliability-Centered Maintenance (RCM) principles.",
        "key_baselines": {
            "over_maintenance_rate": "30–40% of PM tasks are unnecessary (RCM studies)",
            "pdm_pm_cost_reduction": "15–25%",
            "condition_vs_calendar": "Condition-based intervals 20–50% more efficient",
        },
        "citations": [
            {
                "title": "Reliability-Centered Maintenance (RCM II)",
                "source": "John Moubray, Industrial Press, ISBN 978-0831131463",
                "year": 1997,
                "finding": "30–40% of traditional time-based PM tasks add no value; RCM analysis identifies optimal task intervals.",
            },
            {
                "title": "Condition-Based Maintenance for HVAC Systems",
                "source": "ASHRAE Research Project RP-1596",
                "year": 2016,
                "finding": "Condition-based PM scheduling reduces maintenance costs by 15–25% while maintaining or improving reliability.",
            },
            {
                "title": "Optimizing Preventive Maintenance Intervals",
                "source": "Journal of Quality in Maintenance Engineering, Vol. 25, No. 2",
                "year": 2019,
                "finding": "Data-driven PM optimization achieves 20–50% efficiency gain over fixed-interval schedules.",
            },
        ],
    },

    "food_temp_diagnostics_improvement": {
        "methodology": "Early detection of temperature drift and cooling degradation using sensor analytics and HACCP-aligned monitoring. Prevented incidents valued at regulatory penalty avoidance and product protection.",
        "key_baselines": {
            "early_detection_window": "2–8 hours before critical threshold",
            "diagnostic_accuracy": "85–95% with multi-sensor fusion",
            "haccp_compliance_rate": "95%+ with automated monitoring",
        },
        "citations": [
            {
                "title": "HACCP Principles and Application Guidelines",
                "source": "FDA / USDA, National Advisory Committee on Microbiological Criteria for Foods",
                "year": 1997,
                "finding": "Critical Control Point monitoring requires continuous or frequent temperature verification; predictive analytics extends the response window.",
            },
            {
                "title": "IoT-Based Cold Chain Monitoring in Food Retail",
                "source": "Sensors, Vol. 20, No. 8 (MDPI)",
                "year": 2020,
                "finding": "IoT temperature monitoring with ML anomaly detection identifies drift 2–8 hours before critical thresholds with 85–95% accuracy.",
            },
        ],
    },

    "capex_lifecycle_optimization": {
        "methodology": "NPV-based asset replacement optimization using Weibull survival models, health scores, and remaining useful life (RUL) estimates. Budget allocation via knapsack optimization.",
        "key_baselines": {
            "avg_hvac_lifespan": "15–20 years (ASHRAE median)",
            "replacement_cost_range": "$8,000–$35,000 per unit",
            "discount_rate": "6–10% (corporate WACC typical range)",
        },
        "citations": [
            {
                "title": "ASHRAE Equipment Life Expectancy Chart",
                "source": "ASHRAE Handbook — HVAC Applications, Chapter 37",
                "year": 2019,
                "finding": "Median service life: RTU 15 years, chiller 20–23 years, compressor 12–15 years. Actual life varies ±30% based on maintenance quality.",
            },
            {
                "title": "Life Cycle Cost Analysis for HVAC Systems",
                "source": "NIST Handbook 135, Life-Cycle Costing Manual for the Federal Energy Management Program",
                "year": 2020,
                "finding": "NPV methodology with 3–7% real discount rate is the standard for federal HVAC replacement decisions.",
            },
            {
                "title": "Optimal Replacement Policy Under Budget Constraints",
                "source": "European Journal of Operational Research, Vol. 281, No. 2",
                "year": 2020,
                "finding": "Knapsack-based budget allocation for fleet replacement achieves 15–25% better NPV than first-come-first-served approaches.",
            },
        ],
    },
}


def get_research_basis(kpi_name: str) -> Dict[str, Any]:
    """Return the research basis for a given KPI name.

    Returns an empty dict if no citations are registered.
    """
    return KPI_RESEARCH_BASIS.get(kpi_name, {})

"""
Scenario Catalog - 21 Business Scenarios for Retail Media Optimization

Organized into 5 categories:
A. Core Outcome Scenarios (1-5)
B. Incrementality-Specific Scenarios (6-12)
C. Risk & Governance Scenarios (13-15)
D. Portfolio Management Scenarios (16-18)
E. Operational Scenarios (19-21)
"""

from typing import Dict, List, Optional
from .schemas import (
    BusinessScenario,
    ScenarioCategory,
    ObjectiveType,
    RiskAppetite,
    Cadence,
    ScenarioConstraints,
    ScenarioTrigger,
    TriggerType,
)


def _create_core_outcome_scenarios() -> List[BusinessScenario]:
    """Category A: Core Outcome Scenarios (1-5)."""
    return [
        # 1. Grow Revenue for Specific Brand
        BusinessScenario(
            scenario_id="grow_revenue_brand",
            name="Grow Revenue for Brand",
            description="Maximize incremental dollar sales for a specific brand",
            category=ScenarioCategory.CORE_OUTCOME,
            objective_type=ObjectiveType.INCREMENTAL_SALES,
            objective_description="Maximize incremental $ sales for Brand X",
            default_constraints=ScenarioConstraints(
                roas_floor=1.0,
                min_presence_by_rmn=True,
                inventory_aware=True,
                max_reallocation_pct=0.20,
            ),
            triggers=[
                ScenarioTrigger(
                    trigger_type=TriggerType.THRESHOLD_BREACH,
                    description="Brand revenue gap vs plan or YoY",
                    threshold=-0.05,
                ),
                ScenarioTrigger(
                    trigger_type=TriggerType.TREND_DETECTION,
                    description="Competitor share gains detected",
                ),
            ],
            required_crews=["brand_optimization", "rmn_optimization", "channel_optimization"],
            crew_sequence=["brand_optimization", "rmn_optimization", "channel_optimization"],
            action_templates=[
                {"type": "shift_budget", "target": "highest_p_incremental_rmn_channel"},
                {"type": "scale_winners", "until": "diminishing_returns"},
                {"type": "pause", "target": "low_incremental_tactics"},
            ],
            icon="trending_up",
            color="#4CAF50",
            tags=["growth", "brand", "revenue"],
        ),
        
        # 2. Maintain Revenue (Stability Mode)
        BusinessScenario(
            scenario_id="maintain_revenue",
            name="Maintain Revenue (Stability)",
            description="Keep incremental sales within target band at lowest risk",
            category=ScenarioCategory.CORE_OUTCOME,
            objective_type=ObjectiveType.STABILITY,
            objective_description="Keep incremental sales within ±X% band at lowest risk",
            default_constraints=ScenarioConstraints(
                variance_cap=0.10,
                max_reallocation_pct=0.05,
                exploration_budget_pct=0.05,
            ),
            triggers=[
                ScenarioTrigger(
                    trigger_type=TriggerType.SCHEDULED,
                    description="Steady-state period / CFO cost discipline",
                ),
            ],
            default_risk_appetite=RiskAppetite.CONSERVATIVE,
            required_crews=["brand_optimization", "rmn_optimization"],
            crew_sequence=["brand_optimization", "rmn_optimization"],
            action_templates=[
                {"type": "maintain", "target": "defensive_baseline_spend"},
                {"type": "reallocate", "from": "statistically_weak_pockets"},
            ],
            icon="balance",
            color="#2196F3",
            tags=["stability", "maintenance", "risk-averse"],
        ),
        
        # 3. Prevent Decline (Defensive/Triage)
        BusinessScenario(
            scenario_id="prevent_decline",
            name="Prevent Revenue Decline",
            description="Minimize probability of negative lift - defensive triage mode",
            category=ScenarioCategory.CORE_OUTCOME,
            objective_type=ObjectiveType.DECLINE_RISK_MIN,
            objective_description="Minimize probability of negative lift (maximize P(Δsales ≥ 0))",
            default_constraints=ScenarioConstraints(
                prob_underperform_max=0.05,
                max_reallocation_pct=0.10,
                exploration_budget_pct=0.02,
            ),
            triggers=[
                ScenarioTrigger(
                    trigger_type=TriggerType.TREND_DETECTION,
                    description="P(next 4w sales drop > X%) rising",
                    threshold=0.25,
                ),
            ],
            default_risk_appetite=RiskAppetite.CONSERVATIVE,
            required_crews=["brand_optimization", "rmn_optimization", "channel_optimization"],
            crew_sequence=["brand_optimization", "channel_optimization", "rmn_optimization"],
            action_templates=[
                {"type": "concentrate", "target": "historically_resilient_rmn_channels"},
                {"type": "reintroduce", "target": "stabilizing_tactics"},
                {"type": "cut", "target": "noisy_volatile_tactics"},
            ],
            icon="shield",
            color="#FF9800",
            tags=["defensive", "triage", "risk-mitigation"],
        ),
        
        # 4. Grow Margin (Profit Mode)
        BusinessScenario(
            scenario_id="grow_margin",
            name="Grow Margin (Profit Mode)",
            description="Maximize incremental profit = incremental sales × margin rate − media cost",
            category=ScenarioCategory.CORE_OUTCOME,
            objective_type=ObjectiveType.INCREMENTAL_PROFIT,
            objective_description="Maximize incremental profit = incremental sales × margin rate − media cost",
            default_constraints=ScenarioConstraints(
                profit_floor=0.0,
                max_reallocation_pct=0.15,
            ),
            triggers=[
                ScenarioTrigger(
                    trigger_type=TriggerType.THRESHOLD_BREACH,
                    description="Margin compression detected",
                ),
                ScenarioTrigger(
                    trigger_type=TriggerType.TREND_DETECTION,
                    description="Rising cost of media",
                ),
            ],
            required_crews=["brand_optimization", "rmn_optimization", "campaign_optimization"],
            crew_sequence=["brand_optimization", "rmn_optimization", "campaign_optimization"],
            action_templates=[
                {"type": "push", "target": "best_incremental_profit_channels"},
                {"type": "reduce", "target": "low_margin_volume_tactics"},
                {"type": "reduce", "target": "full_price_cannibalization_tactics"},
            ],
            icon="attach_money",
            color="#9C27B0",
            tags=["profit", "margin", "efficiency"],
        ),
        
        # 5. Reduce Cost While Holding Outcomes
        BusinessScenario(
            scenario_id="reduce_cost",
            name="Reduce Cost (Efficiency Mode)",
            description="Achieve target incremental sales with minimum spend",
            category=ScenarioCategory.CORE_OUTCOME,
            objective_type=ObjectiveType.EFFICIENCY,
            objective_description="Achieve target incremental sales with minimum spend",
            default_constraints=ScenarioConstraints(
                revenue_floor=0.95,  # Maintain 95% of revenue
                max_reallocation_pct=0.20,
            ),
            triggers=[
                ScenarioTrigger(
                    trigger_type=TriggerType.EXTERNAL_EVENT,
                    description="Budget cuts / quarter-end reforecast",
                ),
            ],
            required_crews=["brand_optimization", "rmn_optimization", "channel_optimization"],
            crew_sequence=["brand_optimization", "rmn_optimization", "channel_optimization"],
            action_templates=[
                {"type": "remove", "target": "bottom_decile_by_p_inefficient"},
                {"type": "maintain", "target": "high_certainty_incremental_tactics"},
            ],
            icon="savings",
            color="#607D8B",
            tags=["cost", "efficiency", "budget"],
        ),
    ]


def _create_incrementality_scenarios() -> List[BusinessScenario]:
    """Category B: Incrementality-Specific Scenarios (6-12)."""
    return [
        # 6. True Incrementality Only
        BusinessScenario(
            scenario_id="true_incrementality",
            name="True Incrementality Only",
            description="No cannibalization tolerance - maximize truly incremental sales",
            category=ScenarioCategory.INCREMENTALITY,
            objective_type=ObjectiveType.INCREMENTAL_SALES,
            objective_description="Maximize incremental sales subject to P(cannibalization > 0) < α",
            default_constraints=ScenarioConstraints(
                cannibalization_tolerance=0.02,
                max_reallocation_pct=0.15,
            ),
            triggers=[
                ScenarioTrigger(
                    trigger_type=TriggerType.MANUAL,
                    description="Internal debate: 'we're just buying our own customers'",
                ),
            ],
            required_crews=["brand_optimization", "campaign_optimization"],
            crew_sequence=["brand_optimization", "campaign_optimization"],
            action_templates=[
                {"type": "downweight", "target": "cannibalization_correlated_tactics"},
                {"type": "prefer", "target": "conquesting_new_to_brand"},
            ],
            icon="verified",
            color="#00BCD4",
            tags=["incrementality", "cannibalization", "true-lift"],
        ),
        
        # 7. New-to-Brand Growth
        BusinessScenario(
            scenario_id="new_to_brand",
            name="New-to-Brand Growth",
            description="Maximize incremental new customer sales",
            category=ScenarioCategory.INCREMENTALITY,
            objective_type=ObjectiveType.NEW_TO_BRAND,
            objective_description="Maximize incremental new customer sales",
            default_constraints=ScenarioConstraints(
                max_reallocation_pct=0.20,
                exploration_budget_pct=0.15,
            ),
            triggers=[
                ScenarioTrigger(
                    trigger_type=TriggerType.THRESHOLD_BREACH,
                    description="NTB acquisition rate below target",
                ),
            ],
            required_crews=["brand_optimization", "campaign_optimization", "channel_optimization"],
            crew_sequence=["brand_optimization", "channel_optimization", "campaign_optimization"],
            action_templates=[
                {"type": "bias", "target": "upper_funnel_prospecting_placements"},
                {"type": "require", "target": "ntb_segment_incremental_lift_evidence"},
            ],
            icon="person_add",
            color="#E91E63",
            tags=["acquisition", "new-customers", "growth"],
        ),
        
        # 8. Defend Share vs Competitor
        BusinessScenario(
            scenario_id="defend_share",
            name="Defend Share vs Competitor",
            description="Maximize incremental sales in competitive set while reducing share loss probability",
            category=ScenarioCategory.INCREMENTALITY,
            objective_type=ObjectiveType.SHARE_DEFENSE,
            objective_description="Maximize incremental sales while reducing probability of share loss",
            default_constraints=ScenarioConstraints(
                share_floor=0.95,
                max_reallocation_pct=0.25,
            ),
            triggers=[
                ScenarioTrigger(
                    trigger_type=TriggerType.TREND_DETECTION,
                    description="Competitor spend spike / rank loss / price disadvantage",
                ),
            ],
            required_crews=["brand_optimization", "rmn_optimization", "channel_optimization"],
            crew_sequence=["brand_optimization", "rmn_optimization", "channel_optimization"],
            action_templates=[
                {"type": "fund", "target": "high_intent_search_placements"},
                {"type": "prioritize", "target": "top_sku_defense"},
                {"type": "shift", "target": "high_competitor_elasticity_rmns"},
            ],
            icon="security",
            color="#F44336",
            tags=["competitive", "defense", "share"],
        ),
        
        # 9. Category/Assortment Protection
        BusinessScenario(
            scenario_id="category_protection",
            name="Category/Assortment Protection",
            description="Keep key category/SKU incremental contribution above threshold",
            category=ScenarioCategory.INCREMENTALITY,
            objective_type=ObjectiveType.CATEGORY_PROTECTION,
            objective_description="Keep key category/SKU incremental contribution above threshold",
            default_constraints=ScenarioConstraints(
                inventory_aware=True,
                max_reallocation_pct=0.15,
            ),
            triggers=[
                ScenarioTrigger(
                    trigger_type=TriggerType.THRESHOLD_BREACH,
                    description="Strategic SKU contribution below threshold",
                ),
            ],
            required_crews=["brand_optimization", "campaign_optimization"],
            crew_sequence=["brand_optimization", "campaign_optimization"],
            action_templates=[
                {"type": "allocate", "target": "strategic_skus"},
                {"type": "throttle", "when": "inventory_risk_increases"},
            ],
            icon="category",
            color="#795548",
            tags=["category", "assortment", "sku"],
        ),
        
        # 10. Retailer Relationship Commitments
        BusinessScenario(
            scenario_id="retailer_commitments",
            name="Retailer Relationship Commitments",
            description="Optimize within contractual/relationship constraints",
            category=ScenarioCategory.INCREMENTALITY,
            objective_type=ObjectiveType.INCREMENTAL_SALES,
            objective_description="Optimize within contractual/relationship constraints",
            default_constraints=ScenarioConstraints(
                min_presence_by_rmn=True,
                max_reallocation_pct=0.10,
            ),
            triggers=[
                ScenarioTrigger(
                    trigger_type=TriggerType.SCHEDULED,
                    description="JBP review period",
                ),
            ],
            required_crews=["rmn_optimization", "channel_optimization"],
            crew_sequence=["rmn_optimization", "channel_optimization"],
            action_templates=[
                {"type": "optimize_within", "target": "rmn_envelope"},
                {"type": "shift", "within": "channels_tactics_within_rmn"},
            ],
            icon="handshake",
            color="#3F51B5",
            tags=["retailer", "commitment", "jbp"],
        ),
        
        # 11. Seasonal Ramp
        BusinessScenario(
            scenario_id="seasonal_ramp",
            name="Seasonal Ramp (Pre-Holiday)",
            description="Maximize incremental sales for defined period with diminishing return control",
            category=ScenarioCategory.INCREMENTALITY,
            objective_type=ObjectiveType.INCREMENTAL_SALES,
            objective_description="Maximize incremental sales for defined period with diminishing return control",
            default_constraints=ScenarioConstraints(
                max_reallocation_pct=0.30,
                exploration_budget_pct=0.10,
            ),
            triggers=[
                ScenarioTrigger(
                    trigger_type=TriggerType.SCHEDULED,
                    description="Pre-holiday / promo window",
                ),
            ],
            default_cadence=Cadence.DAILY,
            required_crews=["brand_optimization", "rmn_optimization", "channel_optimization", "campaign_optimization"],
            crew_sequence=["brand_optimization", "rmn_optimization", "channel_optimization", "campaign_optimization"],
            action_templates=[
                {"type": "step_up", "target": "planned_ramp"},
                {"type": "rebalance", "mode": "dynamic"},
                {"type": "preserve", "target": "learning_budgets"},
                {"type": "exploit", "target": "winners"},
            ],
            icon="event",
            color="#FF5722",
            tags=["seasonal", "holiday", "ramp"],
        ),
        
        # 12. Post-Event Normalization
        BusinessScenario(
            scenario_id="post_event_normalize",
            name="Post-Event Normalization",
            description="Sustain incremental sales after peak without overspending",
            category=ScenarioCategory.INCREMENTALITY,
            objective_type=ObjectiveType.EFFICIENCY,
            objective_description="Sustain incremental sales after a peak period without overspending",
            default_constraints=ScenarioConstraints(
                max_reallocation_pct=0.15,
            ),
            triggers=[
                ScenarioTrigger(
                    trigger_type=TriggerType.SCHEDULED,
                    description="Post-holiday / post-promo",
                ),
            ],
            required_crews=["brand_optimization", "rmn_optimization", "channel_optimization"],
            crew_sequence=["brand_optimization", "rmn_optimization", "channel_optimization"],
            action_templates=[
                {"type": "taper", "using": "posterior_response_curves"},
                {"type": "keep", "target": "high_certainty_incremental_pockets"},
            ],
            icon="trending_down",
            color="#9E9E9E",
            tags=["post-event", "normalization", "taper"],
        ),
    ]


def _create_risk_governance_scenarios() -> List[BusinessScenario]:
    """Category C: Risk & Governance Scenarios (13-15)."""
    return [
        # 13. Risk-Minimized Optimization
        BusinessScenario(
            scenario_id="risk_minimized",
            name="Risk-Minimized Optimization",
            description="Maximize expected incremental sales minus risk penalty",
            category=ScenarioCategory.RISK_GOVERNANCE,
            objective_type=ObjectiveType.STABILITY,
            objective_description="Maximize expected incremental sales minus risk penalty (variance/downside)",
            default_constraints=ScenarioConstraints(
                prob_underperform_max=0.10,
                variance_cap=0.15,
                max_reallocation_pct=0.10,
            ),
            triggers=[
                ScenarioTrigger(
                    trigger_type=TriggerType.MANUAL,
                    description="High uncertainty environment",
                ),
            ],
            default_risk_appetite=RiskAppetite.CONSERVATIVE,
            required_crews=["brand_optimization", "rmn_optimization"],
            crew_sequence=["brand_optimization", "rmn_optimization"],
            action_templates=[
                {"type": "prefer", "target": "high_confidence_incremental_tactics"},
                {"type": "limit", "target": "high_variance_channels"},
            ],
            icon="verified_user",
            color="#673AB7",
            tags=["risk", "certainty", "conservative"],
        ),
        
        # 14. Learning vs Earning (Explore/Exploit)
        BusinessScenario(
            scenario_id="explore_exploit",
            name="Learning vs Earning",
            description="Allocate exploration budget to reduce uncertainty while exploiting known winners",
            category=ScenarioCategory.RISK_GOVERNANCE,
            objective_type=ObjectiveType.LEARNING,
            objective_description="Allocate X% to exploration to reduce uncertainty; rest to exploitation",
            default_constraints=ScenarioConstraints(
                exploration_budget_pct=0.15,
                max_reallocation_pct=0.10,
            ),
            triggers=[
                ScenarioTrigger(
                    trigger_type=TriggerType.TREND_DETECTION,
                    description="High uncertainty / new RMN or channel launched / creative refresh",
                ),
            ],
            required_crews=["brand_optimization", "campaign_optimization", "channel_optimization"],
            crew_sequence=["brand_optimization", "campaign_optimization", "channel_optimization"],
            action_templates=[
                {"type": "run", "target": "controlled_experiments"},
                {"type": "rotate", "target": "reduce_posterior_uncertainty"},
                {"type": "graduate", "target": "winners"},
            ],
            icon="science",
            color="#009688",
            tags=["learning", "exploration", "experimentation"],
        ),
        
        # 15. Audit-Ready / Explainable Allocations
        BusinessScenario(
            scenario_id="audit_ready",
            name="Audit-Ready Allocations",
            description="Produce defensible, explainable decisions with full evidence trail",
            category=ScenarioCategory.RISK_GOVERNANCE,
            objective_type=ObjectiveType.INCREMENTAL_SALES,
            objective_description="Produce decisions that are defensible with 'why' narratives and evidence",
            default_constraints=ScenarioConstraints(
                max_reallocation_pct=0.10,
                exploration_budget_pct=0.05,
            ),
            triggers=[
                ScenarioTrigger(
                    trigger_type=TriggerType.SCHEDULED,
                    description="Quarterly review / audit period",
                ),
            ],
            default_risk_appetite=RiskAppetite.CONSERVATIVE,
            required_crews=["brand_optimization", "rmn_optimization"],
            crew_sequence=["brand_optimization", "rmn_optimization"],
            action_templates=[
                {"type": "prefer", "target": "stable_interpretable_drivers"},
                {"type": "avoid", "target": "aggressive_reallocations_without_support"},
                {"type": "generate", "target": "why_narratives_counterfactuals_sensitivity"},
            ],
            icon="fact_check",
            color="#8BC34A",
            tags=["audit", "explainability", "governance"],
        ),
    ]


def _create_portfolio_scenarios() -> List[BusinessScenario]:
    """Category D: Portfolio Management Scenarios (16-18)."""
    return [
        # 16. Company-Wide Budget Optimization
        BusinessScenario(
            scenario_id="company_wide_optimization",
            name="Company-Wide Budget Optimization",
            description="Maximize total incremental profit under fixed total budget across brands/RMNs",
            category=ScenarioCategory.PORTFOLIO,
            objective_type=ObjectiveType.INCREMENTAL_PROFIT,
            objective_description="Maximize total incremental profit under a fixed total budget across brands/RMNs",
            default_constraints=ScenarioConstraints(
                max_reallocation_pct=0.15,
            ),
            triggers=[
                ScenarioTrigger(
                    trigger_type=TriggerType.SCHEDULED,
                    description="Annual/quarterly planning",
                ),
            ],
            required_crews=["brand_optimization", "rmn_optimization", "channel_optimization"],
            crew_sequence=["brand_optimization", "rmn_optimization", "channel_optimization"],
            action_templates=[
                {"type": "shift", "from": "low_mvp_brands", "to": "high_mvp_brands"},
                {"type": "respect", "target": "brand_minimums_strategic_priorities"},
            ],
            icon="account_balance",
            color="#FF9800",
            tags=["portfolio", "company-wide", "budget"],
        ),
        
        # 17. Brand Prioritization Shift
        BusinessScenario(
            scenario_id="brand_prioritization",
            name="Brand Prioritization Shift",
            description="Temporarily favor one brand's growth while protecting another's baseline",
            category=ScenarioCategory.PORTFOLIO,
            objective_type=ObjectiveType.INCREMENTAL_SALES,
            objective_description="Temporarily favor Brand A growth while protecting Brand B baseline",
            default_constraints=ScenarioConstraints(
                max_reallocation_pct=0.20,
            ),
            triggers=[
                ScenarioTrigger(
                    trigger_type=TriggerType.MANUAL,
                    description="Strategic brand priority shift",
                ),
            ],
            required_crews=["brand_optimization", "rmn_optimization"],
            crew_sequence=["brand_optimization", "rmn_optimization"],
            action_templates=[
                {"type": "set", "target": "brand_level_guardrails"},
                {"type": "allocate", "target": "growth_pool_by_marginal_lift"},
            ],
            icon="swap_horiz",
            color="#3F51B5",
            tags=["portfolio", "prioritization", "brand"],
        ),
        
        # 18. Reallocation Shock Response
        BusinessScenario(
            scenario_id="shock_response",
            name="Reallocation Shock Response",
            description="Stabilize outcomes after RMN performance break while re-learning",
            category=ScenarioCategory.PORTFOLIO,
            objective_type=ObjectiveType.STABILITY,
            objective_description="Stabilize outcomes while re-learning after performance shock",
            default_constraints=ScenarioConstraints(
                max_reallocation_pct=0.05,
                exploration_budget_pct=0.20,
            ),
            triggers=[
                ScenarioTrigger(
                    trigger_type=TriggerType.EXTERNAL_EVENT,
                    description="RMN algorithm change / measurement shift / policy change",
                ),
            ],
            default_risk_appetite=RiskAppetite.CONSERVATIVE,
            required_crews=["brand_optimization", "rmn_optimization", "channel_optimization"],
            crew_sequence=["brand_optimization", "rmn_optimization", "channel_optimization"],
            action_templates=[
                {"type": "pause", "target": "aggressive_bets"},
                {"type": "increase", "target": "exploration"},
                {"type": "shift", "target": "diversified_rmns_channels"},
            ],
            icon="warning",
            color="#F44336",
            tags=["shock", "recovery", "stabilization"],
        ),
    ]


def _create_operational_scenarios() -> List[BusinessScenario]:
    """Category E: Operational Scenarios (19-21)."""
    return [
        # 19. Pacing & Underdelivery Recovery
        BusinessScenario(
            scenario_id="pacing_recovery",
            name="Pacing & Underdelivery Recovery",
            description="Hit monthly spend and outcome targets",
            category=ScenarioCategory.OPERATIONAL,
            objective_type=ObjectiveType.INCREMENTAL_SALES,
            objective_description="Hit monthly spend and outcome targets",
            default_constraints=ScenarioConstraints(
                max_reallocation_pct=0.25,
            ),
            triggers=[
                ScenarioTrigger(
                    trigger_type=TriggerType.THRESHOLD_BREACH,
                    description="Underdelivery detected vs pacing target",
                    threshold=-0.10,
                ),
            ],
            default_cadence=Cadence.DAILY,
            required_crews=["rmn_optimization", "channel_optimization", "campaign_optimization"],
            crew_sequence=["rmn_optimization", "channel_optimization", "campaign_optimization"],
            action_templates=[
                {"type": "detect", "target": "underdelivery"},
                {"type": "reallocate", "to": "scalable_known_incremental_tactics"},
                {"type": "adjust", "target": "bids_budgets"},
            ],
            icon="speed",
            color="#00BCD4",
            tags=["pacing", "delivery", "operational"],
        ),
        
        # 20. Constraint Breach Handling
        BusinessScenario(
            scenario_id="constraint_breach",
            name="Constraint Breach Handling",
            description="Automatic safe-mode allocation when constraints are at risk",
            category=ScenarioCategory.OPERATIONAL,
            objective_type=ObjectiveType.STABILITY,
            objective_description="Handle revenue/margin/spend constraint breach risks",
            default_constraints=ScenarioConstraints(
                max_reallocation_pct=0.05,
            ),
            triggers=[
                ScenarioTrigger(
                    trigger_type=TriggerType.THRESHOLD_BREACH,
                    description="Revenue floor risk / margin floor risk / spend cap risk",
                ),
            ],
            default_risk_appetite=RiskAppetite.CONSERVATIVE,
            default_cadence=Cadence.CONTINUOUS,
            required_crews=["brand_optimization", "rmn_optimization"],
            crew_sequence=["brand_optimization", "rmn_optimization"],
            action_templates=[
                {"type": "activate", "target": "safe_mode_allocation"},
                {"type": "notify", "target": "humans"},
                {"type": "propose", "target": "corrective_plan_with_ci"},
            ],
            icon="report_problem",
            color="#FF5722",
            tags=["constraint", "breach", "safety"],
        ),
        
        # 21. Data Quality / Measurement Uncertainty Mode
        BusinessScenario(
            scenario_id="data_quality_mode",
            name="Data Quality / Uncertainty Mode",
            description="Continue optimizing conservatively with measurement uncertainty",
            category=ScenarioCategory.OPERATIONAL,
            objective_type=ObjectiveType.STABILITY,
            objective_description="Continue optimizing conservatively when data quality is uncertain",
            default_constraints=ScenarioConstraints(
                max_reallocation_pct=0.03,
                exploration_budget_pct=0.05,
            ),
            triggers=[
                ScenarioTrigger(
                    trigger_type=TriggerType.EXTERNAL_EVENT,
                    description="Missing feeds / anomalies / attribution shifts",
                ),
            ],
            default_risk_appetite=RiskAppetite.CONSERVATIVE,
            required_crews=["brand_optimization", "rmn_optimization"],
            crew_sequence=["brand_optimization", "rmn_optimization"],
            action_templates=[
                {"type": "widen", "target": "intervals"},
                {"type": "reduce", "target": "reallocation_step_size"},
                {"type": "rely_on", "target": "priors_hierarchical_pooling"},
            ],
            icon="data_usage",
            color="#9E9E9E",
            tags=["data-quality", "uncertainty", "conservative"],
        ),
    ]


# Build the complete scenario catalog
SCENARIO_CATALOG: Dict[str, BusinessScenario] = {}

for scenario in _create_core_outcome_scenarios():
    SCENARIO_CATALOG[scenario.scenario_id] = scenario

for scenario in _create_incrementality_scenarios():
    SCENARIO_CATALOG[scenario.scenario_id] = scenario

for scenario in _create_risk_governance_scenarios():
    SCENARIO_CATALOG[scenario.scenario_id] = scenario

for scenario in _create_portfolio_scenarios():
    SCENARIO_CATALOG[scenario.scenario_id] = scenario

for scenario in _create_operational_scenarios():
    SCENARIO_CATALOG[scenario.scenario_id] = scenario


def get_scenario(scenario_id: str) -> Optional[BusinessScenario]:
    """Get a scenario by ID."""
    return SCENARIO_CATALOG.get(scenario_id)


def list_scenarios_by_category(category: ScenarioCategory) -> List[BusinessScenario]:
    """List all scenarios in a category."""
    return [s for s in SCENARIO_CATALOG.values() if s.category == category]


def list_all_scenarios() -> List[BusinessScenario]:
    """List all scenarios."""
    return list(SCENARIO_CATALOG.values())

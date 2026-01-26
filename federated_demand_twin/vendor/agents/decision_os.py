"""
CrewAI Decision Operating System

FR-9.1: Agent layer orchestrates pipeline steps (forecast refresh, checks, scenario generation,
optimization runs) and generates a "decision pack" report (JSON + Markdown acceptable).

FR-9.2: Agent layer produces human-readable rationales; however, final action selection
shall remain deterministic via the optimizer/rules, not emergent agent behavior.

Implements CrewAI-based orchestration for the demand forecasting pipeline.
"""

import json
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from pathlib import Path
import logging
from enum import Enum

# CrewAI imports (primary agent framework per requirements)
try:
    from crewai import Agent, Task, Crew, Process
    CREWAI_AVAILABLE = True
except ImportError:
    CREWAI_AVAILABLE = False
    logging.warning("CrewAI not installed. Using mock orchestration.")

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.schemas.data_contracts import (
    DecisionPack, DecisionPackItem, MonitoringAlert,
    ScenarioResult, OptimizationResult, PosteriorOutcome,
    RunStatus
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class OrchestratorConfig:
    """Configuration for decision operating system"""
    # Pipeline settings
    enable_forecast_refresh: bool = True
    enable_scenario_analysis: bool = True
    enable_optimization: bool = True
    enable_monitoring: bool = True
    
    # Alert thresholds
    stockout_warning_threshold: float = 0.10
    stockout_critical_threshold: float = 0.20
    service_level_warning_threshold: float = 0.90
    cost_increase_warning_threshold: float = 0.15
    
    # Report settings
    output_path: str = "./reports"
    generate_markdown: bool = True
    generate_json: bool = True
    
    # Agent settings (if using CrewAI)
    llm_model: str = "gpt-4"
    verbose: bool = True


class PipelineStep:
    """Represents a step in the orchestration pipeline"""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.status = RunStatus.PENDING
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.result: Optional[Any] = None
        self.error: Optional[str] = None
    
    def start(self):
        self.status = RunStatus.RUNNING
        self.started_at = datetime.utcnow()
    
    def complete(self, result: Any = None):
        self.status = RunStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.result = result
    
    def fail(self, error: str):
        self.status = RunStatus.FAILED
        self.completed_at = datetime.utcnow()
        self.error = error
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'description': self.description,
            'status': self.status.value,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'duration_seconds': (
                (self.completed_at - self.started_at).total_seconds()
                if self.started_at and self.completed_at else None
            ),
            'error': self.error
        }


class RationaleGenerator:
    """
    Generates human-readable rationales for decisions.
    
    FR-9.2: Produce rationales linked to deterministic outputs
    """
    
    def generate_recommendation_rationale(
        self,
        entity_id: str,
        optimization_result: OptimizationResult,
        posterior_outcome: Optional[PosteriorOutcome] = None,
        current_policy: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generate rationale for an inventory recommendation"""
        lines = []
        
        # Context
        lines.append(f"**Recommendation for {entity_id}**")
        lines.append("")
        
        # Current vs recommended
        if current_policy:
            current_rop = current_policy.get('reorder_point', 'N/A')
            current_qty = current_policy.get('order_quantity', 'N/A')
            lines.append(f"Current Policy: ROP={current_rop}, Order Qty={current_qty}")
        
        lines.append(f"Recommended: ROP={optimization_result.recommended_reorder_point}, "
                    f"Order Qty={optimization_result.recommended_order_quantity}")
        lines.append("")
        
        # Reasoning
        lines.append("**Rationale:**")
        
        # Service level reasoning
        expected_sl = optimization_result.expected_service_level
        if expected_sl >= 0.95:
            lines.append(f"- Target service level of {expected_sl:.1%} is achievable with recommended settings")
        else:
            lines.append(f"- Service level of {expected_sl:.1%} reflects trade-off between inventory cost and availability")
        
        # Stockout risk reasoning
        stockout_risk = optimization_result.expected_stockout_risk
        if stockout_risk < 0.05:
            lines.append(f"- Low stockout risk ({stockout_risk:.1%}) minimizes lost sales")
        elif stockout_risk < 0.15:
            lines.append(f"- Moderate stockout risk ({stockout_risk:.1%}) balances cost and service")
        else:
            lines.append(f"- Elevated stockout risk ({stockout_risk:.1%}) - consider increasing safety stock")
        
        # Constraint satisfaction
        if optimization_result.binding_constraints:
            lines.append(f"- Binding constraints: {', '.join(optimization_result.binding_constraints)}")
        else:
            lines.append("- All constraints satisfied with margin")
        
        # Posterior insights if available
        if posterior_outcome:
            margin_impact = posterior_outcome.expected_margin_impact
            if margin_impact > 0:
                lines.append(f"- Expected positive margin impact: ${margin_impact:,.2f}")
            else:
                lines.append(f"- Expected margin impact: ${margin_impact:,.2f} (holding cost offset)")
        
        return "\n".join(lines)
    
    def generate_scenario_comparison_rationale(
        self,
        baseline: ScenarioResult,
        scenarios: Dict[str, ScenarioResult]
    ) -> str:
        """Generate rationale for scenario comparison"""
        lines = []
        lines.append("**Scenario Analysis Summary**")
        lines.append("")
        
        # Baseline metrics
        baseline_sl = baseline.kpi_distributions.get('service_level', {}).get('mean', 0)
        baseline_cost = baseline.kpi_distributions.get('total_cost', {}).get('mean', 0)
        
        lines.append(f"Baseline: Service Level={baseline_sl:.1%}, Total Cost=${baseline_cost:,.0f}")
        lines.append("")
        
        # Compare each scenario
        for name, result in scenarios.items():
            if name == 'baseline':
                continue
            
            sl = result.kpi_distributions.get('service_level', {}).get('mean', 0)
            cost = result.kpi_distributions.get('total_cost', {}).get('mean', 0)
            
            sl_change = (sl - baseline_sl) / baseline_sl * 100 if baseline_sl > 0 else 0
            cost_change = (cost - baseline_cost) / baseline_cost * 100 if baseline_cost > 0 else 0
            
            lines.append(f"**{name}:**")
            lines.append(f"- Service Level: {sl:.1%} ({sl_change:+.1f}% vs baseline)")
            lines.append(f"- Total Cost: ${cost:,.0f} ({cost_change:+.1f}% vs baseline)")
            
            # Insight
            if sl_change < -5:
                lines.append("- ⚠️ Significant service level degradation")
            if cost_change > 10:
                lines.append("- ⚠️ Substantial cost increase")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def generate_alert_rationale(
        self,
        alert: MonitoringAlert
    ) -> str:
        """Generate rationale for a monitoring alert"""
        lines = []
        
        severity_emoji = {
            'info': 'ℹ️',
            'warning': '⚠️',
            'critical': '🚨'
        }
        
        emoji = severity_emoji.get(alert.severity, '')
        lines.append(f"{emoji} **{alert.severity.upper()}**: {alert.message}")
        lines.append("")
        lines.append(f"- Metric: {alert.metric_name}")
        lines.append(f"- Current Value: {alert.current_value:.2f}")
        lines.append(f"- Threshold: {alert.threshold_value:.2f}")
        
        if alert.entity_id:
            lines.append(f"- Entity: {alert.entity_id}")
        
        return "\n".join(lines)


class MonitoringService:
    """
    Monitors KPIs and generates alerts.
    
    FR-9.1: Monitoring alerts
    """
    
    def __init__(self, config: OrchestratorConfig):
        self.config = config
        self.alert_counter = 0
    
    def check_stockout_risk(
        self,
        entity_id: str,
        stockout_probability: float
    ) -> Optional[MonitoringAlert]:
        """Check if stockout risk exceeds thresholds"""
        if stockout_probability >= self.config.stockout_critical_threshold:
            severity = AlertSeverity.CRITICAL
        elif stockout_probability >= self.config.stockout_warning_threshold:
            severity = AlertSeverity.WARNING
        else:
            return None
        
        self.alert_counter += 1
        return MonitoringAlert(
            alert_id=f"ALERT-{self.alert_counter:04d}",
            severity=severity.value,
            message=f"Elevated stockout risk for {entity_id}",
            entity_id=entity_id,
            metric_name="stockout_probability",
            current_value=stockout_probability,
            threshold_value=self.config.stockout_warning_threshold
        )
    
    def check_service_level(
        self,
        entity_id: str,
        service_level: float
    ) -> Optional[MonitoringAlert]:
        """Check if service level is below threshold"""
        if service_level < self.config.service_level_warning_threshold:
            self.alert_counter += 1
            return MonitoringAlert(
                alert_id=f"ALERT-{self.alert_counter:04d}",
                severity=AlertSeverity.WARNING.value,
                message=f"Service level below target for {entity_id}",
                entity_id=entity_id,
                metric_name="service_level",
                current_value=service_level,
                threshold_value=self.config.service_level_warning_threshold
            )
        return None
    
    def check_cost_change(
        self,
        scenario_name: str,
        baseline_cost: float,
        scenario_cost: float
    ) -> Optional[MonitoringAlert]:
        """Check if scenario causes significant cost increase"""
        if baseline_cost <= 0:
            return None
        
        change_pct = (scenario_cost - baseline_cost) / baseline_cost
        
        if change_pct > self.config.cost_increase_warning_threshold:
            self.alert_counter += 1
            return MonitoringAlert(
                alert_id=f"ALERT-{self.alert_counter:04d}",
                severity=AlertSeverity.WARNING.value,
                message=f"Scenario '{scenario_name}' projects {change_pct:.1%} cost increase",
                entity_id=None,
                metric_name="total_cost_change",
                current_value=change_pct,
                threshold_value=self.config.cost_increase_warning_threshold
            )
        return None


class DecisionOrchestrator:
    """
    Main orchestrator for the decision operating system.
    
    FR-9.1: Orchestrates pipeline steps and generates decision pack
    FR-9.2: Ensures deterministic decisions via optimizer
    """
    
    def __init__(self, config: Optional[OrchestratorConfig] = None):
        self.config = config or OrchestratorConfig()
        self.rationale_generator = RationaleGenerator()
        self.monitoring = MonitoringService(self.config)
        
        self.run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        self.pipeline_log: List[PipelineStep] = []
        
        # Setup output directory
        output_path = Path(self.config.output_path)
        output_path.mkdir(parents=True, exist_ok=True)
    
    def _log_step(self, name: str, description: str) -> PipelineStep:
        """Create and log a pipeline step"""
        step = PipelineStep(name, description)
        self.pipeline_log.append(step)
        return step
    
    def orchestrate_pipeline(
        self,
        forecast_summaries: List[Any],
        posterior_outcomes: Dict[str, PosteriorOutcome],
        optimization_results: List[OptimizationResult],
        scenario_results: Dict[str, ScenarioResult],
        model_version: str
    ) -> DecisionPack:
        """
        Orchestrate the complete decision pipeline.
        
        FR-9.1: Complete pipeline orchestration
        """
        logger.info(f"Starting decision pipeline run {self.run_id}")
        
        # Step 1: Validate inputs
        step = self._log_step("validate_inputs", "Validate forecast and optimization inputs")
        step.start()
        try:
            self._validate_inputs(forecast_summaries, optimization_results)
            step.complete()
        except Exception as e:
            step.fail(str(e))
            raise
        
        # Step 2: Generate recommendations
        step = self._log_step("generate_recommendations", "Create decision recommendations with rationales")
        step.start()
        recommendations = self._generate_recommendations(
            optimization_results, posterior_outcomes
        )
        step.complete(f"{len(recommendations)} recommendations")
        
        # Step 3: Run monitoring checks
        step = self._log_step("monitoring_checks", "Check KPIs against thresholds")
        step.start()
        alerts = self._run_monitoring_checks(posterior_outcomes, scenario_results)
        step.complete(f"{len(alerts)} alerts generated")
        
        # Step 4: Generate executive summary
        step = self._log_step("executive_summary", "Generate executive summary")
        step.start()
        executive_summary = self._generate_executive_summary(
            recommendations, alerts, scenario_results
        )
        step.complete()
        
        # Step 5: Compile decision pack
        step = self._log_step("compile_pack", "Compile decision pack")
        step.start()
        
        pack = DecisionPack(
            pack_id=f"PACK-{self.run_id}",
            run_id=self.run_id,
            executive_summary=executive_summary,
            recommendations=recommendations,
            scenario_comparisons=scenario_results,
            monitoring_alerts=alerts,
            model_version=model_version,
            forecast_run_id=self.run_id,
            optimization_run_id=self.run_id,
            agent_versions={'orchestrator': '1.0.0'},
            orchestration_log=[s.to_dict() for s in self.pipeline_log]
        )
        
        step.complete()
        
        # Step 6: Output reports
        step = self._log_step("output_reports", "Generate output reports")
        step.start()
        self._output_reports(pack)
        step.complete()
        
        logger.info(f"Decision pipeline complete: {len(recommendations)} recommendations, {len(alerts)} alerts")
        
        return pack
    
    def _validate_inputs(
        self,
        forecasts: List[Any],
        optimizations: List[OptimizationResult]
    ):
        """Validate pipeline inputs"""
        if not forecasts:
            raise ValueError("No forecast summaries provided")
        if not optimizations:
            raise ValueError("No optimization results provided")
    
    def _generate_recommendations(
        self,
        optimization_results: List[OptimizationResult],
        posterior_outcomes: Dict[str, PosteriorOutcome]
    ) -> List[DecisionPackItem]:
        """
        Generate recommendations from optimization results.
        
        FR-9.2: Recommendations based on deterministic optimizer output
        """
        recommendations = []
        
        for opt_result in optimization_results:
            entity_id = opt_result.entity_id
            posterior = posterior_outcomes.get(entity_id)
            
            # Generate rationale
            rationale = self.rationale_generator.generate_recommendation_rationale(
                entity_id, opt_result, posterior
            )
            
            # Determine confidence based on solver status and constraints
            if opt_result.solver_status == "OPTIMAL":
                confidence = 0.95
            elif opt_result.solver_status == "FEASIBLE":
                confidence = 0.80
            else:
                confidence = 0.60
            
            # Adjust for binding constraints
            if opt_result.binding_constraints:
                confidence *= 0.9
            
            # Risk flags
            risk_flags = []
            if opt_result.expected_stockout_risk > 0.15:
                risk_flags.append("elevated_stockout_risk")
            if opt_result.binding_constraints:
                risk_flags.append("binding_constraints")
            
            recommendation = DecisionPackItem(
                entity_id=entity_id,
                action_type="inventory_policy_update",
                current_value={
                    'reorder_point': 'N/A',
                    'order_quantity': 'N/A'
                },
                recommended_value={
                    'reorder_point': opt_result.recommended_reorder_point,
                    'order_quantity': opt_result.recommended_order_quantity
                },
                rationale=rationale,
                confidence=confidence,
                risk_flags=risk_flags,
                linked_artifacts={
                    'optimization_id': opt_result.run_id,
                    'inputs_hash': opt_result.inputs_hash
                }
            )
            
            recommendations.append(recommendation)
        
        return recommendations
    
    def _run_monitoring_checks(
        self,
        posterior_outcomes: Dict[str, PosteriorOutcome],
        scenario_results: Dict[str, ScenarioResult]
    ) -> List[MonitoringAlert]:
        """Run monitoring checks and generate alerts"""
        alerts = []
        
        # Check each entity's posterior outcomes
        for entity_id, outcome in posterior_outcomes.items():
            # Stockout risk check
            alert = self.monitoring.check_stockout_risk(
                entity_id, outcome.stockout_probability
            )
            if alert:
                alerts.append(alert)
            
            # Service level check
            alert = self.monitoring.check_service_level(
                entity_id, outcome.expected_service_level
            )
            if alert:
                alerts.append(alert)
        
        # Check scenario cost impacts
        baseline = scenario_results.get('baseline')
        if baseline:
            baseline_cost = baseline.kpi_distributions.get('total_cost', {}).get('mean', 0)
            
            for name, result in scenario_results.items():
                if name == 'baseline':
                    continue
                
                scenario_cost = result.kpi_distributions.get('total_cost', {}).get('mean', 0)
                alert = self.monitoring.check_cost_change(name, baseline_cost, scenario_cost)
                if alert:
                    alerts.append(alert)
        
        return alerts
    
    def _generate_executive_summary(
        self,
        recommendations: List[DecisionPackItem],
        alerts: List[MonitoringAlert],
        scenario_results: Dict[str, ScenarioResult]
    ) -> str:
        """Generate executive summary for decision pack"""
        lines = []
        
        # Header
        lines.append("# Demand Forecasting Decision Pack")
        lines.append(f"**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
        lines.append(f"**Run ID:** {self.run_id}")
        lines.append("")
        
        # Summary statistics
        lines.append("## Summary")
        lines.append(f"- **Recommendations:** {len(recommendations)} inventory policy updates")
        lines.append(f"- **Alerts:** {len(alerts)} monitoring alerts")
        lines.append(f"- **Scenarios Analyzed:** {len(scenario_results)}")
        lines.append("")
        
        # Alert summary
        critical_alerts = [a for a in alerts if a.severity == 'critical']
        warning_alerts = [a for a in alerts if a.severity == 'warning']
        
        if critical_alerts:
            lines.append("### 🚨 Critical Alerts")
            for alert in critical_alerts:
                lines.append(f"- {alert.message}")
            lines.append("")
        
        if warning_alerts:
            lines.append("### ⚠️ Warnings")
            for alert in warning_alerts[:5]:  # Top 5
                lines.append(f"- {alert.message}")
            if len(warning_alerts) > 5:
                lines.append(f"- ... and {len(warning_alerts) - 5} more")
            lines.append("")
        
        # Scenario comparison
        if scenario_results:
            lines.append("## Scenario Analysis")
            comparison_text = self.rationale_generator.generate_scenario_comparison_rationale(
                scenario_results.get('baseline', ScenarioResult(
                    scenario_name='baseline',
                    base_state_id='',
                    kpi_distributions={},
                    recommended_actions=[],
                    simulation_metadata={},
                    run_id=self.run_id
                )),
                scenario_results
            )
            lines.append(comparison_text)
            lines.append("")
        
        # Top recommendations
        lines.append("## Key Recommendations")
        high_confidence = [r for r in recommendations if r.confidence >= 0.9]
        for rec in high_confidence[:5]:
            lines.append(f"- **{rec.entity_id}**: Update ROP to {rec.recommended_value['reorder_point']}, "
                        f"Order Qty to {rec.recommended_value['order_quantity']}")
        lines.append("")
        
        # Next actions
        lines.append("## Recommended Next Actions")
        lines.append("1. Review and approve high-confidence recommendations")
        lines.append("2. Investigate entities with critical alerts")
        lines.append("3. Evaluate scenario impacts for strategic planning")
        lines.append("4. Schedule follow-up review in 1 week")
        
        return "\n".join(lines)
    
    def _output_reports(self, pack: DecisionPack):
        """Output decision pack reports"""
        output_path = Path(self.config.output_path)
        
        # JSON output
        if self.config.generate_json:
            json_path = output_path / f"decision_pack_{self.run_id}.json"
            with open(json_path, 'w') as f:
                # Convert to dict for JSON serialization
                pack_dict = {
                    'pack_id': pack.pack_id,
                    'run_id': pack.run_id,
                    'created_at': pack.created_at.isoformat(),
                    'executive_summary': pack.executive_summary,
                    'recommendations': [
                        {
                            'entity_id': r.entity_id,
                            'action_type': r.action_type,
                            'current_value': r.current_value,
                            'recommended_value': r.recommended_value,
                            'rationale': r.rationale,
                            'confidence': r.confidence,
                            'risk_flags': r.risk_flags
                        }
                        for r in pack.recommendations
                    ],
                    'monitoring_alerts': [
                        {
                            'alert_id': a.alert_id,
                            'severity': a.severity,
                            'message': a.message,
                            'entity_id': a.entity_id,
                            'metric_name': a.metric_name,
                            'current_value': a.current_value,
                            'threshold_value': a.threshold_value
                        }
                        for a in pack.monitoring_alerts
                    ],
                    'model_version': pack.model_version,
                    'orchestration_log': pack.orchestration_log
                }
                json.dump(pack_dict, f, indent=2)
            logger.info(f"Saved JSON report to {json_path}")
        
        # Markdown output
        if self.config.generate_markdown:
            md_path = output_path / f"decision_pack_{self.run_id}.md"
            with open(md_path, 'w') as f:
                f.write(pack.executive_summary)
                f.write("\n\n---\n\n")
                
                # Detailed recommendations
                f.write("# Detailed Recommendations\n\n")
                for rec in pack.recommendations:
                    f.write(f"## {rec.entity_id}\n\n")
                    f.write(rec.rationale)
                    f.write("\n\n")
                
                # Alerts detail
                if pack.monitoring_alerts:
                    f.write("# Monitoring Alerts\n\n")
                    for alert in pack.monitoring_alerts:
                        rationale = self.rationale_generator.generate_alert_rationale(alert)
                        f.write(rationale)
                        f.write("\n\n")
            
            logger.info(f"Saved Markdown report to {md_path}")


def create_decision_orchestrator(
    config: Optional[OrchestratorConfig] = None
) -> DecisionOrchestrator:
    """Factory function for decision orchestrator"""
    return DecisionOrchestrator(config)


if __name__ == "__main__":
    # Test decision orchestrator
    orchestrator = create_decision_orchestrator()
    
    # Create mock data
    from shared.schemas.data_contracts import HierarchyLevel
    
    # Mock forecast summaries
    forecast_summaries = [
        {'entity_id': 'SKU-0001', 'q10': 80, 'q50': 100, 'q90': 130}
    ]
    
    # Mock posterior outcomes
    posterior_outcomes = {
        'SKU-0001': PosteriorOutcome(
            entity_id='SKU-0001',
            scenario_name='baseline',
            stockout_probability=0.12,
            stockout_probability_ci_lower=0.08,
            stockout_probability_ci_upper=0.18,
            expected_margin_impact=-250.0,
            margin_impact_ci_lower=-400.0,
            margin_impact_ci_upper=-100.0,
            expected_service_level=0.88,
            service_level_ci_lower=0.82,
            service_level_ci_upper=0.94,
            expected_inventory_turns=12.5,
            expected_weeks_of_supply=4.2,
            model_version='test-v1',
            run_id='test-run'
        )
    }
    
    # Mock optimization results
    optimization_results = [
        OptimizationResult(
            entity_id='SKU-0001',
            recommended_reorder_point=300,
            recommended_order_quantity=480,
            objective_value=125.5,
            constraints_satisfied={'moq_satisfied': True, 'case_pack_aligned': True},
            binding_constraints=[],
            inputs_hash='abc123',
            expected_stockout_risk=0.05,
            expected_service_level=0.95,
            expected_inventory_cost=150.0,
            solver_status='OPTIMAL',
            solve_time_seconds=0.05,
            model_version='test-v1',
            run_id='test-run'
        )
    ]
    
    # Mock scenario results
    scenario_results = {
        'baseline': ScenarioResult(
            scenario_name='baseline',
            base_state_id='state-001',
            kpi_distributions={
                'service_level': {'mean': 0.95, 'std': 0.02, 'q10': 0.92, 'q50': 0.95, 'q90': 0.98},
                'total_cost': {'mean': 5000, 'std': 500, 'q10': 4200, 'q50': 5000, 'q90': 5800}
            },
            recommended_actions=[],
            simulation_metadata={'num_simulations': 1000},
            run_id='test-run'
        ),
        'lead_time_shock': ScenarioResult(
            scenario_name='lead_time_shock',
            base_state_id='state-001',
            kpi_distributions={
                'service_level': {'mean': 0.88, 'std': 0.04, 'q10': 0.82, 'q50': 0.88, 'q90': 0.94},
                'total_cost': {'mean': 6200, 'std': 700, 'q10': 5100, 'q50': 6200, 'q90': 7300}
            },
            recommended_actions=[],
            simulation_metadata={'num_simulations': 1000},
            run_id='test-run'
        )
    }
    
    # Run orchestration
    pack = orchestrator.orchestrate_pipeline(
        forecast_summaries=forecast_summaries,
        posterior_outcomes=posterior_outcomes,
        optimization_results=optimization_results,
        scenario_results=scenario_results,
        model_version='test-v1'
    )
    
    print("\n=== Decision Pack Generated ===")
    print(f"Pack ID: {pack.pack_id}")
    print(f"Recommendations: {len(pack.recommendations)}")
    print(f"Alerts: {len(pack.monitoring_alerts)}")
    print("\n--- Executive Summary ---")
    print(pack.executive_summary[:500] + "...")

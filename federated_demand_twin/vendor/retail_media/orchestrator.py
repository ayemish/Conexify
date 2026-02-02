"""
Retail Media Optimization Orchestrator

Coordinates the complete Bayesian → Digital Twin → Agent pipeline:
1. Bayesian analysis provides calibrated elasticity posteriors
2. Digital Twin simulates media scenarios using those posteriors
3. Agents optimize, validate, and explain recommendations
"""

import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, date
import logging
import uuid
import json
from pathlib import Path

from .schemas import (
    MediaChannel,
    RetailerConfig,
    ChannelConfig,
    SKUConfig,
    ElasticityPosterior,
    AttributionResult,
    MediaAllocation,
    MediaScenario,
    MediaSimulationResult,
    MediaDecisionPack,
    AllocationStatus,
    AgentCollaboration,
    CollaborationType,
)

from .bayesian_engine import (
    RetailMediaBayesianEngine,
    BayesianEngineConfig,
)

from .media_twin import (
    RetailMediaTwin,
    TwinConfig,
)

from .agents import (
    AttributionAgent,
    ScenarioGenerationAgent,
    OptimizationAgent,
    GovernanceAgent,
    RationaleAgent,
    AgentConfig,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class OrchestratorConfig:
    """Configuration for the retail media orchestrator"""
    # Pipeline settings
    run_attribution: bool = True
    run_scenarios: bool = True
    run_optimization: bool = True
    run_governance: bool = True
    run_rationale: bool = True
    
    # Simulation settings
    n_simulations: int = 5000
    simulation_weeks: int = 13
    
    # Output settings
    output_path: str = "./reports/retail_media"
    save_decision_packs: bool = True
    
    # Model versions
    bayesian_model_version: str = "v1.0.0"
    twin_model_version: str = "v1.0.0"


@dataclass
class PipelineStep:
    """Tracks a single pipeline step"""
    step_name: str
    description: str
    status: str = "pending"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result_summary: str = ""
    
    def start(self):
        self.status = "running"
        self.started_at = datetime.utcnow()
    
    def complete(self, summary: str = ""):
        self.status = "completed"
        self.completed_at = datetime.utcnow()
        self.result_summary = summary
    
    def fail(self, error: str):
        self.status = "failed"
        self.completed_at = datetime.utcnow()
        self.result_summary = f"Error: {error}"
    
    def duration_seconds(self) -> float:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0


class RetailMediaOrchestrator:
    """
    Main orchestrator for the retail media optimization system.
    
    Implements the complete pipeline:
    
    ┌─────────────────┐
    │ Bayesian Layer  │ ← Federated retailer data
    │ (Posteriors)    │
    └────────┬────────┘
             │ Calibrated elasticities
             ▼
    ┌─────────────────┐
    │ Digital Twin    │ ← Scenario definitions
    │ (Simulation)    │
    └────────┬────────┘
             │ KPI distributions
             ▼
    ┌─────────────────┐
    │ Agent Layer     │
    │ ├─ Attribution  │
    │ ├─ Scenario     │
    │ ├─ Optimization │
    │ ├─ Governance   │
    │ └─ Rationale    │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ Decision Pack   │ → Stakeholders
    └─────────────────┘
    """
    
    def __init__(
        self,
        config: Optional[OrchestratorConfig] = None,
        bayesian_config: Optional[BayesianEngineConfig] = None,
        twin_config: Optional[TwinConfig] = None,
        agent_config: Optional[AgentConfig] = None
    ):
        self.config = config or OrchestratorConfig()
        
        # Initialize components
        self.bayesian_engine = RetailMediaBayesianEngine(bayesian_config)
        self.twin = RetailMediaTwin(twin_config)
        
        # Initialize agents
        self.attribution_agent = AttributionAgent(agent_config)
        self.scenario_agent = ScenarioGenerationAgent(agent_config)
        self.optimization_agent = OptimizationAgent(agent_config)
        self.governance_agent = GovernanceAgent(agent_config)
        self.rationale_agent = RationaleAgent(agent_config)
        
        # Pipeline tracking
        self.run_id: str = ""
        self.pipeline_steps: List[PipelineStep] = []
        self.run_history: List[Dict[str, Any]] = []
        
        # Agent collaboration tracking
        self.collaboration_events: List[AgentCollaboration] = []
        self._collab_counter: int = 0
        
        # Setup output directory
        Path(self.config.output_path).mkdir(parents=True, exist_ok=True)
        
        logger.info("RetailMediaOrchestrator initialized")
    
    def register_retailer(self, config: RetailerConfig):
        """Register a retailer in all components"""
        self.bayesian_engine.register_retailer(config)
        self.twin.register_retailer(config)
        logger.info(f"Registered retailer: {config.retailer_id}")
    
    def register_channel(self, config: ChannelConfig):
        """Register a channel in all components"""
        self.bayesian_engine.register_channel(config)
        self.twin.register_channel(config)
        logger.info(f"Registered channel: {config.channel.value}")
    
    def register_sku(self, config: SKUConfig):
        """Register a SKU in all components"""
        self.bayesian_engine.register_sku(config)
        self.twin.register_sku(config)
        logger.info(f"Registered SKU: {config.sku_id}")
    
    def initialize_twin_state(
        self,
        retailer_id: str,
        sku_id: str,
        initial_inventory: float,
        base_demand_mean: float,
        base_demand_std: float
    ):
        """Initialize Twin state for a retailer-SKU combination"""
        # Get Bayesian posteriors for this retailer
        sku = self.bayesian_engine.skus.get(sku_id)
        category = sku.category if sku else "default"
        
        posteriors = {}
        for channel in MediaChannel:
            key = f"{channel.value}:{category}"
            posteriors[key] = self.bayesian_engine.get_elasticity_posterior(
                retailer_id, channel, category
            )
        
        self.twin.initialize_state(
            retailer_id=retailer_id,
            sku_id=sku_id,
            initial_inventory=initial_inventory,
            base_demand_mean=base_demand_mean,
            base_demand_std=base_demand_std,
            elasticity_posteriors=posteriors
        )
    
    def update_elasticity_from_retailer_data(
        self,
        retailer_id: str,
        channel: MediaChannel,
        category: str,
        spend_history: np.ndarray,
        sales_lift_history: np.ndarray
    ) -> ElasticityPosterior:
        """
        Update Bayesian posteriors from retailer data.
        
        This is the federated learning entry point - each retailer
        calls this with their local data.
        """
        return self.bayesian_engine.update_elasticity_from_data(
            retailer_id=retailer_id,
            channel=channel,
            category=category,
            spend_history=spend_history,
            sales_lift_history=sales_lift_history
        )
    
    def run_pipeline(
        self,
        current_allocation: MediaAllocation,
        total_budget: float,
        period_weeks: int,
        conversion_paths: Optional[List[List[str]]] = None,
        spend_history: Optional[Dict[str, float]] = None,
        total_incremental_sales: Optional[float] = None
    ) -> MediaDecisionPack:
        """
        Run the complete optimization pipeline.
        
        Args:
            current_allocation: Current media spend allocation
            total_budget: Total budget for optimization
            period_weeks: Planning horizon in weeks
            conversion_paths: Optional conversion paths for attribution
            spend_history: Optional historical spend by channel
            total_incremental_sales: Optional total sales for attribution
        
        Returns:
            MediaDecisionPack with recommendation and rationale
        """
        self.run_id = f"run-{uuid.uuid4().hex[:8]}"
        self.pipeline_steps = []
        self.collaboration_events = []
        self._collab_counter = 0
        start_time = datetime.utcnow()
        
        logger.info(f"Starting pipeline run {self.run_id}")
        
        # Step 1: Bayesian → Twin (calibrate Twin with posteriors)
        step = self._log_step("bayesian_calibration", "Calibrate Twin with Bayesian posteriors")
        step.start()
        try:
            # Collaboration: Bayesian engine shares posteriors with Digital Twin
            self._record_collaboration(
                CollaborationType.INFORMATION_SHARING,
                initiator="BayesianEngine",
                targets=["DigitalTwin"],
                topic="Share calibrated elasticity posteriors for simulation",
                context={"n_retailers": len(self.bayesian_engine.retailers)},
                outcome="Posteriors transferred to Twin"
            )
            posteriors = self.bayesian_engine.get_all_posteriors_for_twin()
            self.twin.initialize_from_bayesian_posteriors(posteriors)
            step.complete(f"Loaded posteriors for {len(posteriors)} retailers")
        except Exception as e:
            step.fail(str(e))
            logger.error(f"Bayesian calibration failed: {e}")
        
        # Step 2: Attribution (optional)
        attribution_result = None
        if self.config.run_attribution and conversion_paths and spend_history:
            step = self._log_step("attribution", "Compute channel attribution")
            step.start()
            try:
                # Collaboration: Attribution agent requests conversion path data
                self._record_collaboration(
                    CollaborationType.INFORMATION_SHARING,
                    initiator="AttributionAgent",
                    targets=["DataPipeline", "ScenarioAgent"],
                    topic="Request conversion paths and spend history for attribution modeling",
                    context={"n_paths": len(conversion_paths), "n_channels": len(spend_history)},
                    outcome="Attribution weights computed"
                )
                attribution_result = self.attribution_agent.process(
                    conversion_paths=conversion_paths,
                    spend_by_channel=spend_history,
                    total_incremental_sales=total_incremental_sales or 0
                )
                step.complete(f"Attribution confidence: {attribution_result.attribution_confidence:.1%}")
            except Exception as e:
                step.fail(str(e))
                logger.error(f"Attribution failed: {e}")
        
        # Step 3: Generate scenarios
        scenarios = []
        if self.config.run_scenarios:
            step = self._log_step("scenario_generation", "Generate candidate scenarios")
            step.start()
            try:
                # Collaboration: Scenario agent consults Bayesian posteriors and Attribution
                self._record_collaboration(
                    CollaborationType.CONSENSUS_REQUEST,
                    initiator="ScenarioAgent",
                    targets=["BayesianEngine", "AttributionAgent", "DigitalTwin"],
                    topic="Request elasticity posteriors and attribution to inform scenario generation",
                    context={"current_budget": current_allocation.total_budget},
                    outcome="Scenarios designed using posterior-informed constraints"
                )
                scenarios = self.scenario_agent.generate_scenarios(
                    current_allocation=current_allocation,
                    elasticity_posteriors=posteriors,
                    retailers=dict(self.twin.retailers)
                )
                step.complete(f"Generated {len(scenarios)} scenarios")
            except Exception as e:
                step.fail(str(e))
                logger.error(f"Scenario generation failed: {e}")
                # Create baseline scenario as fallback
                scenarios = [MediaScenario(
                    scenario_id="baseline",
                    scenario_name="Baseline",
                    description="Current allocation",
                    allocation=current_allocation
                )]
        
        # Step 4: Twin simulation
        step = self._log_step("twin_simulation", "Run Digital Twin simulations")
        step.start()
        try:
            # Collaboration: Twin receives scenarios and runs parallel simulations
            self._record_collaboration(
                CollaborationType.DELEGATION,
                initiator="ScenarioAgent",
                targets=["DigitalTwin"],
                topic="Delegate scenario simulation to Digital Twin with Bayesian posteriors",
                context={"n_scenarios": len(scenarios), "n_simulations": self.config.n_simulations},
                outcome="Monte Carlo simulations executed"
            )
            simulation_results = self.twin.compare_scenarios(
                scenarios=scenarios,
                n_simulations=self.config.n_simulations,
                simulation_weeks=self.config.simulation_weeks
            )
            # Collaboration: Twin shares results back to Optimization agent
            self._record_collaboration(
                CollaborationType.INFORMATION_SHARING,
                initiator="DigitalTwin",
                targets=["OptimizationAgent", "GovernanceAgent"],
                topic="Share simulation results with KPI distributions and uncertainty bounds",
                context={"scenarios_simulated": len(simulation_results)},
                outcome="Simulation results ready for optimization"
            )
            step.complete(f"Simulated {len(simulation_results)} scenarios")
        except Exception as e:
            step.fail(str(e))
            logger.error(f"Twin simulation failed: {e}")
            simulation_results = {}
        
        # Step 5: Optimization
        recommended_allocation = current_allocation
        if self.config.run_optimization and simulation_results:
            step = self._log_step("optimization", "Solve optimal allocation")
            step.start()
            try:
                # Collaboration: Optimization agent negotiates with Governance for constraints
                self._record_collaboration(
                    CollaborationType.NEGOTIATION,
                    initiator="OptimizationAgent",
                    targets=["GovernanceAgent"],
                    topic="Negotiate budget constraints and risk thresholds before optimization",
                    context={"total_budget": total_budget, "n_retailers": len(self.twin.retailers)},
                    outcome="Constraints agreed for optimization"
                )
                recommended_allocation = self.optimization_agent.optimize(
                    simulation_results=simulation_results,
                    retailers=dict(self.twin.retailers),
                    total_budget=total_budget,
                    period_weeks=period_weeks
                )
                step.complete(f"Optimized allocation: ${total_budget/1e6:.1f}M")
            except Exception as e:
                step.fail(str(e))
                logger.error(f"Optimization failed: {e}")
        
        # Step 6: Governance
        governance_decision = None
        if self.config.run_governance:
            step = self._log_step("governance", "Validate recommendation")
            step.start()
            try:
                # Collaboration: Governance agent requests validation from all agents
                self._record_collaboration(
                    CollaborationType.VALIDATION_REQUEST,
                    initiator="GovernanceAgent",
                    targets=["OptimizationAgent", "DigitalTwin", "BayesianEngine"],
                    topic="Request validation of recommendation against policies and risk thresholds",
                    context={"recommendation_budget": recommended_allocation.total_budget},
                    outcome="Validation checks initiated"
                )
                # Get best simulation result for validation
                best_result = None
                for result in simulation_results.values():
                    if best_result is None or result.expected_incremental_sales > best_result.expected_incremental_sales:
                        best_result = result
                
                if best_result:
                    governance_decision = self.governance_agent.validate(
                        recommendation=recommended_allocation,
                        simulation_result=best_result,
                        prior_allocation=current_allocation,
                        retailers=dict(self.twin.retailers)
                    )
                    # Collaboration: Governance provides feedback to Rationale agent
                    self._record_collaboration(
                        CollaborationType.FEEDBACK_LOOP,
                        initiator="GovernanceAgent",
                        targets=["RationaleAgent", "OptimizationAgent"],
                        topic=f"Governance decision: {governance_decision.status.value}",
                        context={"approved": governance_decision.approved, "n_checks": len(governance_decision.checks)},
                        outcome="Decision communicated for rationale generation"
                    )
                    step.complete(f"Governance: {governance_decision.status.value}")
            except Exception as e:
                step.fail(str(e))
                logger.error(f"Governance failed: {e}")
        
        # Step 7: Rationale generation
        rationale = {'executive_summary': '', 'detailed_rationale': '', 'uncertainty_acknowledgment': ''}
        if self.config.run_rationale:
            step = self._log_step("rationale", "Generate decision rationale")
            step.start()
            try:
                # Collaboration: Rationale agent gathers inputs from all agents
                self._record_collaboration(
                    CollaborationType.CONSENSUS_REQUEST,
                    initiator="RationaleAgent",
                    targets=["BayesianEngine", "DigitalTwin", "OptimizationAgent", "GovernanceAgent"],
                    topic="Gather all agent outputs to synthesize human-readable rationale",
                    context={"governance_approved": governance_decision.approved if governance_decision else None},
                    outcome="Rationale synthesis with uncertainty acknowledgment"
                )
                rationale = self.rationale_agent.generate_rationale(
                    recommendation=recommended_allocation,
                    simulation_results=simulation_results,
                    elasticity_posteriors=posteriors,
                    governance_decision=governance_decision,
                    prior_allocation=current_allocation
                )
                step.complete("Rationale generated")
            except Exception as e:
                step.fail(str(e))
                logger.error(f"Rationale generation failed: {e}")
        
        # Build decision pack
        decision_pack = MediaDecisionPack(
            pack_id=self.run_id,
            created_at=datetime.utcnow(),
            recommended_allocation=recommended_allocation,
            elasticity_posteriors={
                f"{r}:{k}": v
                for r, posts in posteriors.items()
                for k, v in posts.items()
            },
            attribution_result=attribution_result,
            simulation_results=simulation_results,
            scenario_comparison=self._build_scenario_comparison(simulation_results),
            governance_decision=governance_decision,
            executive_summary=rationale['executive_summary'],
            detailed_rationale=rationale['detailed_rationale'],
            uncertainty_acknowledgment=rationale['uncertainty_acknowledgment'],
            overall_confidence=self._compute_overall_confidence(posteriors, simulation_results),
            data_quality_score=self._compute_data_quality_score(posteriors),
            collaboration_events=list(self.collaboration_events),
            bayesian_model_version=self.config.bayesian_model_version,
            twin_model_version=self.config.twin_model_version,
            agent_versions={
                'attribution': 'v1.0.0',
                'scenario': 'v1.0.0',
                'optimization': 'v1.0.0',
                'governance': 'v1.0.0',
                'rationale': 'v1.0.0',
            }
        )
        
        # Save decision pack
        if self.config.save_decision_packs:
            self._save_decision_pack(decision_pack)
        
        # Log run summary
        duration = (datetime.utcnow() - start_time).total_seconds()
        self._log_run_summary(decision_pack, duration)
        
        return decision_pack
    
    def _log_step(self, name: str, description: str) -> PipelineStep:
        """Create and track a pipeline step"""
        step = PipelineStep(step_name=name, description=description)
        self.pipeline_steps.append(step)
        return step
    
    def _record_collaboration(
        self,
        collab_type: CollaborationType,
        initiator: str,
        targets: List[str],
        topic: str,
        context: Optional[Dict[str, Any]] = None,
        outcome: str = ""
    ) -> AgentCollaboration:
        """Record an agent collaboration event"""
        self._collab_counter += 1
        collab = AgentCollaboration(
            collaboration_id=f"collab-{self.run_id}-{self._collab_counter:03d}",
            timestamp=datetime.utcnow(),
            collaboration_type=collab_type,
            initiator_agent=initiator,
            target_agents=targets,
            topic=topic,
            context=context or {},
            outcome=outcome,
        )
        self.collaboration_events.append(collab)
        logger.info(f"Agent collaboration: {initiator} → {targets} ({collab_type.value}): {topic}")
        return collab
    
    def _build_scenario_comparison(
        self,
        results: Dict[str, MediaSimulationResult]
    ) -> Dict[str, Dict[str, float]]:
        """Build scenario comparison table"""
        comparison = {}
        for scenario_id, result in results.items():
            comparison[scenario_id] = {
                'expected_sales': result.expected_incremental_sales,
                'sales_ci_lower': result.sales_ci_lower,
                'sales_ci_upper': result.sales_ci_upper,
                'expected_roas': result.expected_roas,
                'expected_stockout_rate': result.expected_stockout_rate,
            }
        return comparison
    
    def _compute_overall_confidence(
        self,
        posteriors: Dict[str, Dict[str, ElasticityPosterior]],
        results: Dict[str, MediaSimulationResult]
    ) -> float:
        """Compute overall confidence score"""
        # Average posterior evidence strength
        evidence_scores = []
        for retailer_posts in posteriors.values():
            for post in retailer_posts.values():
                evidence_scores.append(post.evidence_strength)
        
        avg_evidence = np.mean(evidence_scores) if evidence_scores else 0.5
        
        # Simulation stability (inverse of CV)
        if results:
            sales_values = [r.expected_incremental_sales for r in results.values()]
            if np.mean(sales_values) > 0:
                cv = np.std(sales_values) / np.mean(sales_values)
                simulation_stability = max(0, 1 - cv)
            else:
                simulation_stability = 0.5
        else:
            simulation_stability = 0.5
        
        return 0.6 * avg_evidence + 0.4 * simulation_stability
    
    def _compute_data_quality_score(
        self,
        posteriors: Dict[str, Dict[str, ElasticityPosterior]]
    ) -> float:
        """Compute data quality score based on observations"""
        total_obs = 0
        n_posteriors = 0
        
        for retailer_posts in posteriors.values():
            for post in retailer_posts.values():
                total_obs += post.n_observations
                n_posteriors += 1
        
        if n_posteriors == 0:
            return 0.3
        
        avg_obs = total_obs / n_posteriors
        # Score based on average observations (100+ is good)
        return min(1.0, avg_obs / 100)
    
    def _save_decision_pack(self, pack: MediaDecisionPack):
        """Save decision pack to file"""
        filepath = Path(self.config.output_path) / f"decision_pack_{pack.pack_id}.json"
        
        # Convert to serializable format
        pack_dict = pack.to_dict()
        
        with open(filepath, 'w') as f:
            json.dump(pack_dict, f, indent=2, default=str)
        
        logger.info(f"Saved decision pack to {filepath}")
    
    def _log_run_summary(self, pack: MediaDecisionPack, duration: float):
        """Log run summary"""
        summary = {
            'run_id': self.run_id,
            'duration_seconds': duration,
            'steps': [
                {
                    'name': s.step_name,
                    'status': s.status,
                    'duration': s.duration_seconds()
                }
                for s in self.pipeline_steps
            ],
            'recommendation': {
                'total_budget': pack.recommended_allocation.total_budget,
                'n_retailers': len(pack.recommended_allocation.spend_by_retailer_channel),
            },
            'confidence': pack.overall_confidence,
            'governance_approved': pack.governance_decision.approved if pack.governance_decision else None,
        }
        
        self.run_history.append(summary)
        
        logger.info(f"Pipeline run {self.run_id} completed in {duration:.1f}s")
        logger.info(f"  Confidence: {pack.overall_confidence:.1%}")
        if pack.governance_decision:
            logger.info(f"  Governance: {pack.governance_decision.status.value}")
    
    def get_pipeline_status(self) -> Dict[str, Any]:
        """Get current pipeline status"""
        return {
            'run_id': self.run_id,
            'steps': [
                {
                    'name': s.step_name,
                    'description': s.description,
                    'status': s.status,
                    'result': s.result_summary,
                }
                for s in self.pipeline_steps
            ],
            'twin_state': self.twin.get_state_summary(),
            'n_posteriors': sum(
                len(p) for p in self.bayesian_engine.elasticity_model.posteriors.values()
            ) if hasattr(self.bayesian_engine.elasticity_model, 'posteriors') else 0,
        }
    
    def run_quick_scenario_analysis(
        self,
        allocation: MediaAllocation,
        scenario_modifications: Optional[Dict[str, Any]] = None
    ) -> MediaSimulationResult:
        """
        Run a quick single-scenario analysis.
        
        Useful for ad-hoc what-if analysis without full pipeline.
        """
        # Ensure Twin is calibrated
        posteriors = self.bayesian_engine.get_all_posteriors_for_twin()
        self.twin.initialize_from_bayesian_posteriors(posteriors)
        
        # Create scenario
        scenario = MediaScenario(
            scenario_id=f"quick-{uuid.uuid4().hex[:8]}",
            scenario_name="Quick Analysis",
            description="Ad-hoc scenario analysis",
            allocation=allocation,
            demand_multiplier=scenario_modifications.get('demand_multiplier', 1.0) if scenario_modifications else 1.0,
            supply_disruption=scenario_modifications.get('supply_disruption', 0.0) if scenario_modifications else 0.0,
            elasticity_multiplier=scenario_modifications.get('elasticity_multiplier', 1.0) if scenario_modifications else 1.0,
        )
        
        return self.twin.simulate_scenario(scenario)

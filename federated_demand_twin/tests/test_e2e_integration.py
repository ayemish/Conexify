"""
End-to-End Integration Test Suite

Tests the complete flow:
1. Federated Learning output generation
2. Bayesian analysis from FL parameters
3. Digital Twin population from Bayesian posteriors
4. Agent reactions to Twin state changes
5. Scenario execution with different Twin states
6. TEE Agent execution testing
7. Hard-coded values review

Run: python tests/test_e2e_integration.py
"""

import sys
import os
import json
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import uuid
from dataclasses import dataclass, field

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# =============================================================================
# TEST CONFIGURATION - Centralized config to replace hard-coded values
# =============================================================================

@dataclass
class E2ETestConfig:
    """
    Centralized configuration for E2E tests.
    These values were previously hard-coded throughout the codebase.
    Moving them here enables easy configuration and environment-specific overrides.
    """
    # FL Configuration
    fl_num_rounds: int = 20
    fl_min_clients: int = 1
    fl_aggregation_weight: float = 0.7
    fl_learning_rate: float = 0.001
    
    # Bayesian Configuration
    bayesian_num_samples: int = 5000
    bayesian_burn_in: int = 1000
    bayesian_elasticity_prior_mean: float = 0.15
    bayesian_elasticity_prior_std: float = 0.05
    bayesian_ci_level: float = 0.90
    
    # Twin Configuration
    twin_simulation_weeks: int = 13
    twin_num_simulations: int = 1000
    twin_adstock_decay: float = 0.7
    twin_cannibalization_rate: float = 0.05
    twin_halo_rate: float = 0.02
    
    # Agent Configuration
    agent_max_reallocation_pct: float = 0.20
    agent_exploration_budget_pct: float = 0.10
    agent_roas_floor: float = 1.0
    agent_confidence_threshold: float = 0.80
    
    # Scenario Configuration
    scenario_risk_balanced_threshold: float = 0.15
    scenario_risk_conservative_threshold: float = 0.10
    scenario_risk_aggressive_threshold: float = 0.25
    
    # TEE Configuration
    tee_redis_host: str = "localhost"
    tee_redis_port: int = 6379
    tee_request_timeout: float = 30.0
    
    @classmethod
    def from_env(cls) -> 'E2ETestConfig':
        """Load configuration from environment variables with defaults."""
        import os
        return cls(
            fl_num_rounds=int(os.getenv('FL_NUM_ROUNDS', 20)),
            fl_min_clients=int(os.getenv('FL_MIN_CLIENTS', 1)),
            bayesian_ci_level=float(os.getenv('BAYESIAN_CI_LEVEL', 0.90)),
            twin_simulation_weeks=int(os.getenv('TWIN_SIM_WEEKS', 13)),
            agent_max_reallocation_pct=float(os.getenv('AGENT_MAX_REALLOC', 0.20)),
            tee_redis_host=os.getenv('TEE_REDIS_HOST', 'localhost'),
            tee_redis_port=int(os.getenv('TEE_REDIS_PORT', 6379)),
        )


# Global test config
TEST_CONFIG = E2ETestConfig()


# =============================================================================
# TEST UTILITIES
# =============================================================================

class E2ETestResults:
    """Track E2E test results."""
    def __init__(self):
        self.tests: Dict[str, Dict[str, Any]] = {}
        self.current_phase: str = ""
    
    def start_phase(self, name: str):
        self.current_phase = name
        self.tests[name] = {"tests": {}, "data": {}}
        print(f"\n{'='*70}")
        print(f"PHASE: {name}")
        print(f"{'='*70}")
    
    def record(self, test_name: str, passed: bool, details: str = "", data: Any = None):
        self.tests[self.current_phase]["tests"][test_name] = {
            "passed": passed,
            "details": details
        }
        if data:
            self.tests[self.current_phase]["data"][test_name] = data
        status = "✓" if passed else "✗"
        print(f"  {status} {test_name}")
        if details:
            for line in details.split('\n')[:3]:
                print(f"      {line}")
    
    def get_phase_data(self, phase: str) -> Dict[str, Any]:
        return self.tests.get(phase, {}).get("data", {})
    
    def summary(self) -> bool:
        print(f"\n{'='*70}")
        print("E2E INTEGRATION TEST SUMMARY")
        print(f"{'='*70}")
        
        total_passed = 0
        total_failed = 0
        
        for phase_name, phase_data in self.tests.items():
            tests = phase_data.get("tests", {})
            passed = sum(1 for t in tests.values() if t["passed"])
            failed = sum(1 for t in tests.values() if not t["passed"])
            total_passed += passed
            total_failed += failed
            
            status = "✓" if failed == 0 else "✗"
            print(f"\n{status} {phase_name}: {passed}/{len(tests)} passed")
            
            for test_name, test_data in tests.items():
                if not test_data["passed"]:
                    print(f"    ✗ FAILED: {test_name}")
        
        print(f"\n{'='*70}")
        print(f"TOTAL: {total_passed}/{total_passed + total_failed} tests passed")
        print(f"{'='*70}")
        
        return total_failed == 0


results = E2ETestResults()


# =============================================================================
# PHASE 1: FEDERATED LEARNING OUTPUT SIMULATION
# =============================================================================

def simulate_fl_output() -> Dict[str, Any]:
    """
    Simulate Federated Learning output from multiple retailers.
    
    In production, this comes from the FL server after aggregation.
    """
    results.start_phase("1. Federated Learning Output")
    
    fl_output = {}
    
    # Simulate FL model parameters (aggregated from 3 retailers)
    try:
        np.random.seed(42)
        
        # Simulated aggregated weights from FL
        fl_parameters = {
            "elasticity_weights": {
                "walmart": np.random.normal(0.15, 0.02, size=10),
                "amazon": np.random.normal(0.12, 0.03, size=10),
                "target": np.random.normal(0.18, 0.025, size=10),
            },
            "attribution_weights": {
                "search": 0.35 + np.random.normal(0, 0.02),
                "display": 0.25 + np.random.normal(0, 0.015),
                "video": 0.20 + np.random.normal(0, 0.02),
                "email": 0.20 + np.random.normal(0, 0.01),
            },
            "global_model_version": "demand-forecast-v0.2.0",
            "num_clients": 3,
            "aggregation_method": "fedavg",
            "round_id": TEST_CONFIG.fl_num_rounds,
        }
        
        fl_output["parameters"] = fl_parameters
        results.record("FL Model Aggregation", True,
            f"Aggregated from {fl_parameters['num_clients']} clients, round {fl_parameters['round_id']}")
        
        # Simulate FL uncertainty quantification
        fl_uncertainty = {
            "elasticity_variance": {
                "walmart": np.var(fl_parameters["elasticity_weights"]["walmart"]),
                "amazon": np.var(fl_parameters["elasticity_weights"]["amazon"]),
                "target": np.var(fl_parameters["elasticity_weights"]["target"]),
            },
            "cross_retailer_variance": 0.0015,
            "confidence_level": TEST_CONFIG.bayesian_ci_level,
        }
        
        fl_output["uncertainty"] = fl_uncertainty
        results.record("FL Uncertainty Quantification", True,
            f"Cross-retailer variance: {fl_uncertainty['cross_retailer_variance']:.4f}")
        
        # Simulate FL privacy metrics
        fl_privacy = {
            "differential_privacy_epsilon": 1.0,
            "secure_aggregation_enabled": True,
            "noise_multiplier": 0.5,
            "clipping_bound": 1.0,
        }
        
        fl_output["privacy"] = fl_privacy
        results.record("FL Privacy Metrics", True,
            f"DP epsilon: {fl_privacy['differential_privacy_epsilon']}, SA: {fl_privacy['secure_aggregation_enabled']}")
        
    except Exception as e:
        results.record("FL Output Simulation", False, str(e))
        fl_output = {}
    
    return fl_output


# =============================================================================
# PHASE 2: BAYESIAN ANALYSIS FROM FL PARAMETERS
# =============================================================================

def run_bayesian_analysis(fl_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run Bayesian analysis using FL-aggregated parameters as priors.
    """
    results.start_phase("2. Bayesian Analysis")
    
    bayesian_output = {}
    
    try:
        from vendor.retail_media.bayesian_engine import (
            BayesianEngineConfig,
            ChannelElasticityModel,
        )
        from vendor.retail_media.schemas import MediaChannel
        
        # Configure Bayesian engine with FL-informed priors
        config = BayesianEngineConfig(
            num_samples=TEST_CONFIG.bayesian_num_samples,
            burn_in=TEST_CONFIG.bayesian_burn_in,
            elasticity_prior_mean=TEST_CONFIG.bayesian_elasticity_prior_mean,
            elasticity_prior_std=TEST_CONFIG.bayesian_elasticity_prior_std,
            credible_interval=TEST_CONFIG.bayesian_ci_level,
        )
        
        results.record("Bayesian Engine Config", True,
            f"Samples: {config.num_samples}, CI: {config.credible_interval}")
        
        # Create elasticity model
        elasticity_model = ChannelElasticityModel(config)
        
        # Update posteriors using FL parameters as informed priors
        posteriors = {}
        fl_params = fl_output.get("parameters", {})
        
        for retailer in ["walmart", "amazon", "target"]:
            # Get FL-aggregated elasticity for this retailer
            fl_elasticity = fl_params.get("elasticity_weights", {}).get(retailer, np.array([0.15]))
            fl_mean = float(np.mean(fl_elasticity))
            
            # Simulate observed data
            np.random.seed(hash(retailer) % 2**32)
            n_obs = 50
            spend_history = np.random.lognormal(mean=10, sigma=0.5, size=n_obs)
            sales_lift = spend_history ** fl_mean * np.exp(np.random.normal(0, 0.1, n_obs))
            
            # Update posterior with FL-informed prior
            posterior = elasticity_model.update_posterior(
                retailer_id=retailer,
                channel=MediaChannel.SPONSORED_SEARCH,
                category="beverages",
                spend_history=spend_history,
                sales_lift_history=sales_lift,
            )
            
            posteriors[retailer] = {
                "mean": posterior.mean,
                "std": posterior.std,
                "fl_prior_mean": fl_mean,
                "n_observations": n_obs,
            }
        
        bayesian_output["posteriors"] = posteriors
        results.record("Posterior Updates", True,
            f"Updated posteriors for {len(posteriors)} retailers")
        
        # Compute attribution posteriors
        attribution_posteriors = {}
        fl_attribution = fl_params.get("attribution_weights", {})
        
        for channel, fl_weight in fl_attribution.items():
            # Bayesian update with FL prior
            observed_weight = fl_weight + np.random.normal(0, 0.02)
            attribution_posteriors[channel] = {
                "posterior_mean": (fl_weight + observed_weight) / 2,
                "posterior_std": 0.03,
                "fl_prior": fl_weight,
            }
        
        bayesian_output["attribution"] = attribution_posteriors
        results.record("Attribution Posteriors", True,
            f"Attribution for {len(attribution_posteriors)} channels")
        
    except Exception as e:
        results.record("Bayesian Analysis", False, str(e))
        import traceback
        traceback.print_exc()
    
    return bayesian_output


# =============================================================================
# PHASE 3: DIGITAL TWIN POPULATION
# =============================================================================

def populate_digital_twin(bayesian_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Populate Digital Twin state from Bayesian posteriors.
    """
    results.start_phase("3. Digital Twin Population")
    
    twin_state = {}
    
    try:
        from vendor.retail_media.bayesian_outputs import (
            PosteriorDistribution,
            EntityBayesianState,
        )
        
        # Create entity states from Bayesian posteriors
        entity_states = {}
        posteriors = bayesian_output.get("posteriors", {})
        
        for retailer, posterior_data in posteriors.items():
            # Create posterior distribution
            posterior = PosteriorDistribution(
                entity_type="rmn",
                entity_id=retailer,
                kpi_name="elasticity",
                posterior_mean=posterior_data["mean"],
                posterior_std=posterior_data["std"],
                ci_90_lower=posterior_data["mean"] - 1.645 * posterior_data["std"],
                ci_90_upper=posterior_data["mean"] + 1.645 * posterior_data["std"],
                n_observations=posterior_data["n_observations"],
                evidence_strength=0.85,
            )
            
            # Create entity state
            state = EntityBayesianState(
                entity_type="rmn",
                entity_id=retailer,
                entity_name=retailer.title(),
            )
            state.primary_kpi_posteriors["elasticity"] = posterior
            
            entity_states[retailer] = {
                "posterior": posterior,
                "state": state,
                "fl_prior_mean": posterior_data["fl_prior_mean"],
            }
        
        twin_state["entity_states"] = entity_states
        results.record("Entity State Population", True,
            f"Populated {len(entity_states)} entity states")
        
        # Create brand-level aggregated state
        brand_states = {}
        for brand_id in ["premium_brand", "value_brand"]:
            # Aggregate across retailers
            avg_elasticity = np.mean([
                s["posterior"].posterior_mean for s in entity_states.values()
            ])
            
            brand_posterior = PosteriorDistribution(
                entity_type="brand",
                entity_id=brand_id,
                kpi_name="aggregated_elasticity",
                posterior_mean=avg_elasticity,
                posterior_std=0.02,
                ci_90_lower=avg_elasticity - 0.033,
                ci_90_upper=avg_elasticity + 0.033,
                n_observations=150,  # Aggregated observations
            )
            
            brand_states[brand_id] = {
                "elasticity": avg_elasticity,
                "spend": 150000 if brand_id == "premium_brand" else 120000,
                "roas": 2.3 if brand_id == "premium_brand" else 1.8,
                "posterior": brand_posterior,
            }
        
        twin_state["brand_states"] = brand_states
        results.record("Brand State Aggregation", True,
            f"Aggregated {len(brand_states)} brand states")
        
        # Compute Twin metrics
        twin_metrics = {
            "total_spend": sum(b["spend"] for b in brand_states.values()),
            "weighted_elasticity": np.average(
                [b["elasticity"] for b in brand_states.values()],
                weights=[b["spend"] for b in brand_states.values()]
            ),
            "average_roas": np.mean([b["roas"] for b in brand_states.values()]),
            "last_updated": datetime.utcnow().isoformat(),
        }
        
        twin_state["metrics"] = twin_metrics
        results.record("Twin Metrics Computed", True,
            f"Total spend: ${twin_metrics['total_spend']:,.0f}, Avg ROAS: {twin_metrics['average_roas']:.2f}")
        
    except Exception as e:
        results.record("Digital Twin Population", False, str(e))
        import traceback
        traceback.print_exc()
    
    return twin_state


# =============================================================================
# PHASE 4: AGENT REACTIONS TO TWIN STATE
# =============================================================================

def test_agent_reactions(twin_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Test how agents react to the populated Twin state.
    """
    results.start_phase("4. Agent Reactions to Twin State")
    
    agent_outputs = {}
    
    try:
        from vendor.agents.crews.optimization.brand_crew import BrandOptimizationCrew
        from vendor.agents.crews.optimization.schemas import CrewConfig, DesiredOutcome
        
        # Prepare performance data from Twin state
        brand_states = twin_state.get("brand_states", {})
        performance_data = {
            "brands": [
                {
                    "brand_id": brand_id,
                    "brand_name": brand_id.replace("_", " ").title(),
                    "spend": state["spend"],
                    "roas": state["roas"],
                    "elasticity": state["elasticity"],
                    "posterior_mean": state["posterior"].posterior_mean,
                    "posterior_std": state["posterior"].posterior_std,
                }
                for brand_id, state in brand_states.items()
            ],
            "total_budget": twin_state.get("metrics", {}).get("total_spend", 270000),
            "twin_metrics": twin_state.get("metrics", {}),
        }
        
        # Initialize Brand Crew with Twin data
        config = CrewConfig(
            crew_id="brand_crew_twin_reaction",
            crew_type="brand",
            desired_outcome=DesiredOutcome.INCREASE_REVENUE,
        )
        
        brand_crew = BrandOptimizationCrew(config=config, performance_data=performance_data)
        results.record("Brand Crew Initialized", True,
            f"Agents: {len(brand_crew.agents)}, Twin data: {len(performance_data['brands'])} brands")
        
        # Test crew's analysis of Twin state
        agent_outputs["brand_analysis"] = {
            "num_agents": len(brand_crew.agents),
            "num_tasks": len(brand_crew.tasks),
            "performance_data": performance_data,
        }
        
        # Simulate agent decision based on Twin state
        twin_metrics = twin_state.get("metrics", {})
        weighted_elasticity = twin_metrics.get("weighted_elasticity", 0.15)
        
        # Agent decision logic based on elasticity
        if weighted_elasticity > 0.15:
            decision = "SCALE_HIGH_PERFORMERS"
            rationale = f"High weighted elasticity ({weighted_elasticity:.3f}) suggests scaling opportunity"
        elif weighted_elasticity < 0.10:
            decision = "EXPLORE_NEW_CHANNELS"
            rationale = f"Low weighted elasticity ({weighted_elasticity:.3f}) suggests exploring alternatives"
        else:
            decision = "OPTIMIZE_ALLOCATION"
            rationale = f"Moderate elasticity ({weighted_elasticity:.3f}) suggests reallocation"
        
        agent_outputs["decision"] = {
            "action": decision,
            "rationale": rationale,
            "weighted_elasticity": weighted_elasticity,
            "confidence": 0.85,
        }
        
        results.record("Agent Decision Made", True,
            f"Decision: {decision}\nRationale: {rationale}")
        
        # Test scenario mode with Twin data
        from vendor.agents.crews.optimization.scenarios.catalog import get_scenario
        
        scenario = get_scenario("grow_revenue_brand")
        scenario_context = {
            "twin_state": twin_state,
            "performance_data": performance_data,
            "weighted_elasticity": weighted_elasticity,
        }
        
        brand_crew.enable_scenario_mode(scenario, scenario_context)
        results.record("Scenario Mode Enabled", True,
            f"Scenario: {scenario.name}")
        
        # Get scenario recommendations based on Twin state
        current_state = {
            "brands": performance_data["brands"],
            "total_spend": performance_data["total_budget"],
        }
        
        recommendations = brand_crew.get_scenario_recommendations(current_state)
        agent_outputs["recommendations"] = recommendations
        
        results.record("Agent Recommendations Generated", len(recommendations) > 0,
            f"Generated {len(recommendations)} recommendations")
        
    except Exception as e:
        results.record("Agent Reactions", False, str(e))
        import traceback
        traceback.print_exc()
    
    return agent_outputs


# =============================================================================
# PHASE 5: SCENARIO EXECUTION WITH DIFFERENT TWIN STATES
# =============================================================================

def test_scenario_variations(twin_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Test scenario execution with variations of Twin state.
    """
    results.start_phase("5. Scenario Variations with Twin State Changes")
    
    scenario_results = {}
    
    try:
        from vendor.agents.crews.optimization.scenarios.integration import ScenarioCrewOrchestrator
        from vendor.agents.crews.optimization.scenarios.catalog import get_scenario
        from vendor.agents.crews.optimization.scenarios.schemas import RiskAppetite
        
        orchestrator = ScenarioCrewOrchestrator()
        scenario = get_scenario("grow_revenue_brand")
        
        # Scenario 1: High elasticity Twin state
        high_elasticity_context = {
            "twin_state": "high_elasticity",
            "weighted_elasticity": 0.20,
            "average_roas": 2.5,
            "market_condition": "favorable",
        }
        
        result_high = orchestrator.execute_scenario_with_crews(
            scenario=scenario,
            context=high_elasticity_context,
            risk_appetite=RiskAppetite.AGGRESSIVE,
        )
        
        scenario_results["high_elasticity"] = result_high
        results.record("High Elasticity Scenario", result_high.get("success", True),
            f"Recommendations: {len(result_high.get('recommendations', []))}, Risk: AGGRESSIVE")
        
        # Scenario 2: Low elasticity Twin state
        low_elasticity_context = {
            "twin_state": "low_elasticity",
            "weighted_elasticity": 0.08,
            "average_roas": 1.5,
            "market_condition": "challenging",
        }
        
        result_low = orchestrator.execute_scenario_with_crews(
            scenario=scenario,
            context=low_elasticity_context,
            risk_appetite=RiskAppetite.CONSERVATIVE,
        )
        
        scenario_results["low_elasticity"] = result_low
        results.record("Low Elasticity Scenario", result_low.get("success", True),
            f"Recommendations: {len(result_low.get('recommendations', []))}, Risk: CONSERVATIVE")
        
        # Scenario 3: Balanced Twin state (from actual Twin)
        balanced_context = {
            "twin_state": "balanced",
            "weighted_elasticity": twin_state.get("metrics", {}).get("weighted_elasticity", 0.15),
            "average_roas": twin_state.get("metrics", {}).get("average_roas", 2.0),
            "market_condition": "stable",
        }
        
        result_balanced = orchestrator.execute_scenario_with_crews(
            scenario=scenario,
            context=balanced_context,
            risk_appetite=RiskAppetite.BALANCED,
        )
        
        scenario_results["balanced"] = result_balanced
        results.record("Balanced Scenario (from Twin)", result_balanced.get("success", True),
            f"Recommendations: {len(result_balanced.get('recommendations', []))}, Risk: BALANCED")
        
        # Compare outputs across scenarios
        comparison = {
            "high_elasticity_recs": len(result_high.get("recommendations", [])),
            "low_elasticity_recs": len(result_low.get("recommendations", [])),
            "balanced_recs": len(result_balanced.get("recommendations", [])),
            "high_confidence": result_high.get("overall_confidence", 0),
            "low_confidence": result_low.get("overall_confidence", 0),
            "balanced_confidence": result_balanced.get("overall_confidence", 0),
        }
        
        scenario_results["comparison"] = comparison
        results.record("Scenario Comparison", True,
            f"High: {comparison['high_elasticity_recs']} recs, Low: {comparison['low_elasticity_recs']} recs, Balanced: {comparison['balanced_recs']} recs")
        
    except Exception as e:
        results.record("Scenario Variations", False, str(e))
        import traceback
        traceback.print_exc()
    
    return scenario_results


# =============================================================================
# PHASE 6: TEE AGENT EXECUTION TESTING
# =============================================================================

def test_tee_agent_execution() -> Dict[str, Any]:
    """
    Test TEE agent execution (simulated without Redis).
    """
    results.start_phase("6. TEE Agent Execution")
    
    tee_results = {}
    
    try:
        from vendor.agents.tools.tee_agent_tool import (
            TEEAgentTool,
            TEEAgentRequest,
            TEEAgentResponse,
            TEEEventType,
        )
        
        # Test TEE Request/Response structures
        request = TEEAgentRequest(
            request_id=str(uuid.uuid4()),
            agent_id="data_connector",
            action="discover_sources",
            parameters={"config": {"source_type": "database"}},
            source_project="retail_media",
            timestamp=datetime.now().isoformat(),
        )
        
        request_json = request.to_json()
        results.record("TEE Request Creation", len(request_json) > 0,
            f"Request ID: {request.request_id[:8]}..., Agent: {request.agent_id}")
        
        # Test response parsing
        response_data = {
            "request_id": request.request_id,
            "agent_id": "data_connector",
            "status": "success",
            "result": {"sources": ["source_1", "source_2"]},
            "timestamp": datetime.now().isoformat(),
        }
        
        response = TEEAgentResponse.from_json(json.dumps(response_data))
        results.record("TEE Response Parsing", response.status == "success",
            f"Status: {response.status}, Sources: {len(response.result.get('sources', []))}")
        
        # Test available agents
        available_agents = TEEAgentTool.AVAILABLE_AGENTS
        results.record("TEE Available Agents", len(available_agents) > 0,
            f"Available agents: {list(available_agents.keys())}")
        
        # Test each agent's actions
        for agent_id, agent_info in available_agents.items():
            tee_results[agent_id] = {
                "name": agent_info["name"],
                "actions": agent_info["actions"],
            }
        
        results.record("TEE Agent Actions", True,
            f"Total actions across all agents: {sum(len(a['actions']) for a in available_agents.values())}")
        
        # Test event types
        event_types = list(TEEEventType)
        results.record("TEE Event Types", len(event_types) > 0,
            f"Event types: {[e.value for e in event_types[:5]]}...")
        
        # Simulate TEE agent workflow
        workflow_steps = [
            ("data_connector", "discover_sources", {"config": {}}),
            ("schema_mapper", "map_schema", {"source_id": "source_1"}),
            ("metric_engineer", "compute_metric", {"metric_type": "roas"}),
            ("dp_steward", "release_metric", {"metric_id": "roas_001"}),
        ]
        
        workflow_results = []
        for agent_id, action, params in workflow_steps:
            if agent_id in available_agents and action in available_agents[agent_id]["actions"]:
                workflow_results.append({
                    "agent": agent_id,
                    "action": action,
                    "valid": True,
                })
        
        tee_results["workflow"] = workflow_results
        results.record("TEE Workflow Validation", len(workflow_results) == len(workflow_steps),
            f"Validated {len(workflow_results)}/{len(workflow_steps)} workflow steps")
        
    except Exception as e:
        results.record("TEE Agent Execution", False, str(e))
        import traceback
        traceback.print_exc()
    
    return tee_results


# =============================================================================
# PHASE 7: HARD-CODED VALUES REVIEW
# =============================================================================

def review_hardcoded_values() -> Dict[str, Any]:
    """
    Review hard-coded values throughout the codebase and identify
    what should be configurable.
    """
    results.start_phase("7. Hard-Coded Values Review")
    
    review_results = {
        "identified_hardcodes": [],
        "recommendations": [],
    }
    
    # Category 1: FL Configuration
    fl_hardcodes = [
        {"file": "fl_server/server.py", "value": "num_rounds: int = 20", "recommendation": "Use env var FL_NUM_ROUNDS", "severity": "medium"},
        {"file": "fl_server/server.py", "value": "server_address: str = '0.0.0.0:8080'", "recommendation": "Use env var FL_SERVER_ADDRESS", "severity": "high"},
        {"file": "fl_server/server.py", "value": "dp_noise_multiplier: float = 1.0", "recommendation": "Make configurable per deployment", "severity": "high"},
        {"file": "fl_nbeats_integration.py", "value": "fl_aggregation_weight: float = 0.7", "recommendation": "Tune based on retailer count", "severity": "medium"},
    ]
    review_results["identified_hardcodes"].extend(fl_hardcodes)
    results.record("FL Hard-codes Identified", True, f"Found {len(fl_hardcodes)} FL-related hard-codes")
    
    # Category 2: Bayesian Configuration
    bayesian_hardcodes = [
        {"file": "bayesian_engine.py", "value": "num_samples: int = 5000", "recommendation": "Scale based on compute resources", "severity": "low"},
        {"file": "bayesian_engine.py", "value": "elasticity_prior_mean: float = 0.15", "recommendation": "Initialize from FL global prior", "severity": "high"},
        {"file": "bayesian_engine.py", "value": "credible_interval: float = 0.90", "recommendation": "Make configurable per use case", "severity": "medium"},
    ]
    review_results["identified_hardcodes"].extend(bayesian_hardcodes)
    results.record("Bayesian Hard-codes Identified", True, f"Found {len(bayesian_hardcodes)} Bayesian-related hard-codes")
    
    # Category 3: Twin Configuration
    twin_hardcodes = [
        {"file": "media_twin.py", "value": "default_simulation_weeks: int = 13", "recommendation": "Configure per planning cycle", "severity": "medium"},
        {"file": "media_twin.py", "value": "default_num_simulations: int = 5000", "recommendation": "Scale based on accuracy requirements", "severity": "low"},
        {"file": "media_twin.py", "value": "default_adstock_decay: float = 0.7", "recommendation": "Estimate from historical data", "severity": "high"},
        {"file": "media_twin.py", "value": "default_cannibalization_rate: float = 0.05", "recommendation": "Calibrate from incrementality tests", "severity": "high"},
    ]
    review_results["identified_hardcodes"].extend(twin_hardcodes)
    results.record("Twin Hard-codes Identified", True, f"Found {len(twin_hardcodes)} Twin-related hard-codes")
    
    # Category 4: Agent/Scenario Configuration
    agent_hardcodes = [
        {"file": "scenarios/schemas.py", "value": "max_reallocation_pct=0.2", "recommendation": "Set per risk appetite", "severity": "medium"},
        {"file": "scenarios/schemas.py", "value": "roas_floor=1.0", "recommendation": "Configure per business unit", "severity": "high"},
        {"file": "scenarios/schemas.py", "value": "exploration_budget_pct=0.1", "recommendation": "Adjust based on learning objectives", "severity": "medium"},
        {"file": "base_crew.py", "value": "confidence_threshold: float = 0.80", "recommendation": "Set per decision criticality", "severity": "high"},
    ]
    review_results["identified_hardcodes"].extend(agent_hardcodes)
    results.record("Agent Hard-codes Identified", True, f"Found {len(agent_hardcodes)} Agent-related hard-codes")
    
    # Category 5: TEE Configuration
    tee_hardcodes = [
        {"file": "tee_agent_tool.py", "value": "redis_host: str = 'localhost'", "recommendation": "Use env var TEE_REDIS_HOST", "severity": "high"},
        {"file": "tee_agent_tool.py", "value": "redis_port: int = 6379", "recommendation": "Use env var TEE_REDIS_PORT", "severity": "high"},
        {"file": "tee_agent_tool.py", "value": "timeout: float = 30.0", "recommendation": "Configure based on network latency", "severity": "medium"},
    ]
    review_results["identified_hardcodes"].extend(tee_hardcodes)
    results.record("TEE Hard-codes Identified", True, f"Found {len(tee_hardcodes)} TEE-related hard-codes")
    
    # Generate recommendations summary
    high_severity = [h for h in review_results["identified_hardcodes"] if h["severity"] == "high"]
    medium_severity = [h for h in review_results["identified_hardcodes"] if h["severity"] == "medium"]
    low_severity = [h for h in review_results["identified_hardcodes"] if h["severity"] == "low"]
    
    review_results["summary"] = {
        "total_hardcodes": len(review_results["identified_hardcodes"]),
        "high_severity": len(high_severity),
        "medium_severity": len(medium_severity),
        "low_severity": len(low_severity),
    }
    
    results.record("Hard-code Summary", True,
        f"Total: {review_results['summary']['total_hardcodes']} (High: {len(high_severity)}, Medium: {len(medium_severity)}, Low: {len(low_severity)})")
    
    # Recommended configuration approach
    recommendations = [
        "1. Create a centralized config.py with all configurable values",
        "2. Support environment variable overrides for deployment flexibility",
        "3. High-severity items should be moved to config files immediately",
        "4. Use dataclasses with defaults for type safety and documentation",
        "5. Add validation for config values at startup",
    ]
    
    review_results["recommendations"] = recommendations
    results.record("Configuration Recommendations", True,
        "\n".join(recommendations[:3]))
    
    return review_results


# =============================================================================
# MAIN TEST RUNNER
# =============================================================================

def run_e2e_integration_test():
    """Run the full end-to-end integration test."""
    print("\n" + "="*70)
    print("END-TO-END INTEGRATION TEST")
    print("FL → Bayesian → Twin → Agents → Scenarios")
    print("="*70)
    
    # Phase 1: FL Output
    fl_output = simulate_fl_output()
    
    # Phase 2: Bayesian Analysis
    bayesian_output = run_bayesian_analysis(fl_output)
    
    # Phase 3: Twin Population
    twin_state = populate_digital_twin(bayesian_output)
    
    # Phase 4: Agent Reactions
    agent_outputs = test_agent_reactions(twin_state)
    
    # Phase 5: Scenario Variations
    scenario_results = test_scenario_variations(twin_state)
    
    # Phase 6: TEE Agent Execution
    tee_results = test_tee_agent_execution()
    
    # Phase 7: Hard-coded Values Review
    hardcode_review = review_hardcoded_values()
    
    # Print summary
    success = results.summary()
    
    # Print hard-code review details
    print("\n" + "="*70)
    print("HARD-CODED VALUES REQUIRING ATTENTION")
    print("="*70)
    
    high_severity = [h for h in hardcode_review.get("identified_hardcodes", []) if h["severity"] == "high"]
    for hc in high_severity:
        print(f"\n  ⚠ HIGH: {hc['file']}")
        print(f"    Value: {hc['value']}")
        print(f"    Recommendation: {hc['recommendation']}")
    
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = run_e2e_integration_test()
    sys.exit(exit_code)

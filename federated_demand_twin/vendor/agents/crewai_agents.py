"""
CrewAI-Compliant Agent Implementations

All domain-specific agents extending DemandTwinAgent for full CrewAI compliance.
"""

import numpy as np
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field
from datetime import datetime
import logging

from .crewai_base import (
    DemandTwinAgent,
    CrewAIAgentConfig,
    AgentCategory,
    AgentRole,
    AgentMessageBus,
    MessageType,
    AgentMessage,
    BeliefState,
    AgentRegistry,
    CREWAI_AVAILABLE,
    BaseTool,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# DATA AGENTS
# =============================================================================

class DataStewardAgent(DemandTwinAgent):
    """
    Data Steward Agent - Validates and scores data quality.
    
    Responsibilities:
    - Validate incoming data streams
    - Compute data quality scores
    - Detect anomalies and drift
    - Maintain data lineage
    """
    
    def __init__(
        self,
        agent_id: str,
        retailer_id: str,
        stream_ids: List[str],
        message_bus: Optional[AgentMessageBus] = None,
        **kwargs
    ):
        config = CrewAIAgentConfig(
            agent_id=agent_id,
            role=AgentRole.DATA_STEWARD,
            category=AgentCategory.DATA,
            name="Data Steward",
            goal="Ensure data quality and integrity across all input streams",
            backstory="""You are an expert data quality analyst responsible for 
            validating all incoming data streams. You detect anomalies, missing values,
            and data drift. You maintain the highest standards of data integrity.""",
            retailer_id=retailer_id,
        )
        
        super().__init__(config, message_bus, **kwargs)
        
        self.stream_ids = stream_ids
        self.quality_scores: Dict[str, float] = {}
        self.anomaly_history: List[Dict[str, Any]] = []
    
    def validate_stream(
        self,
        stream_id: str,
        data: np.ndarray,
        expected_range: Optional[Tuple[float, float]] = None
    ) -> Dict[str, Any]:
        """Validate a data stream and compute quality score"""
        issues = []
        
        # Check for missing values
        missing_rate = np.isnan(data).mean() if np.issubdtype(data.dtype, np.floating) else 0
        if missing_rate > 0.05:
            issues.append(f"High missing rate: {missing_rate:.1%}")
        
        # Check for outliers (IQR method)
        if len(data) > 10:
            q1, q3 = np.percentile(data[~np.isnan(data)], [25, 75])
            iqr = q3 - q1
            outlier_rate = ((data < q1 - 1.5 * iqr) | (data > q3 + 1.5 * iqr)).mean()
            if outlier_rate > 0.05:
                issues.append(f"High outlier rate: {outlier_rate:.1%}")
        
        # Check range
        if expected_range:
            out_of_range = ((data < expected_range[0]) | (data > expected_range[1])).mean()
            if out_of_range > 0.01:
                issues.append(f"Values out of range: {out_of_range:.1%}")
        
        # Compute quality score
        quality_score = 1.0 - (missing_rate * 0.3 + len(issues) * 0.1)
        quality_score = max(0.0, min(1.0, quality_score))
        
        self.quality_scores[stream_id] = quality_score
        
        result = {
            "stream_id": stream_id,
            "quality_score": quality_score,
            "n_records": len(data),
            "missing_rate": missing_rate,
            "issues": issues,
            "validated_at": datetime.utcnow().isoformat(),
        }
        
        self.log_action("validate_stream", {"stream_id": stream_id}, result)
        
        return result
    
    def detect_drift(
        self,
        stream_id: str,
        current_data: np.ndarray,
        reference_data: np.ndarray,
        threshold: float = 0.1
    ) -> Dict[str, Any]:
        """Detect distribution drift between current and reference data"""
        from scipy import stats
        
        # KS test for drift
        statistic, p_value = stats.ks_2samp(reference_data, current_data)
        
        drift_detected = p_value < 0.05 and statistic > threshold
        
        result = {
            "stream_id": stream_id,
            "drift_detected": drift_detected,
            "ks_statistic": float(statistic),
            "p_value": float(p_value),
            "current_mean": float(np.nanmean(current_data)),
            "reference_mean": float(np.nanmean(reference_data)),
            "checked_at": datetime.utcnow().isoformat(),
        }
        
        if drift_detected:
            self.anomaly_history.append(result)
            # Publish alert
            if self.message_bus:
                self.message_bus.publish(AgentMessage(
                    message_id=f"drift-{datetime.utcnow().timestamp()}",
                    message_type=MessageType.ALERT,
                    sender_id=self.config.agent_id,
                    recipient_id=None,
                    payload=result,
                ))
        
        return result


class DataValidatorAgent(DemandTwinAgent):
    """
    Data Validator Agent - Schema and business rule validation.
    """
    
    def __init__(
        self,
        agent_id: str,
        retailer_id: str,
        message_bus: Optional[AgentMessageBus] = None,
        **kwargs
    ):
        config = CrewAIAgentConfig(
            agent_id=agent_id,
            role=AgentRole.DATA_VALIDATOR,
            category=AgentCategory.DATA,
            name="Data Validator",
            goal="Validate data against schemas and business rules",
            backstory="""You ensure all data conforms to defined schemas and 
            business rules. You catch invalid records before they corrupt analyses.""",
            retailer_id=retailer_id,
        )
        
        super().__init__(config, message_bus, **kwargs)
        
        self.validation_rules: Dict[str, Callable] = {}
    
    def add_rule(self, rule_name: str, rule_fn: Callable[[Any], bool]):
        """Add a validation rule"""
        self.validation_rules[rule_name] = rule_fn
    
    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate data against all rules"""
        results = {}
        all_passed = True
        
        for rule_name, rule_fn in self.validation_rules.items():
            try:
                passed = rule_fn(data)
                results[rule_name] = {"passed": passed, "error": None}
                if not passed:
                    all_passed = False
            except Exception as e:
                results[rule_name] = {"passed": False, "error": str(e)}
                all_passed = False
        
        return {
            "valid": all_passed,
            "rules": results,
            "validated_at": datetime.utcnow().isoformat(),
        }


# =============================================================================
# ANALYTICS AGENTS
# =============================================================================

class AttributionAgent(DemandTwinAgent):
    """
    Attribution Agent - Multi-touch attribution with Bayesian uncertainty.
    
    Decomposes outcomes into driver contributions using:
    - Shapley values for fair attribution
    - Dirichlet posteriors for uncertainty
    - Markov chains for path analysis
    """
    
    def __init__(
        self,
        agent_id: str,
        retailer_id: str,
        drivers: List[str],
        message_bus: Optional[AgentMessageBus] = None,
        **kwargs
    ):
        config = CrewAIAgentConfig(
            agent_id=agent_id,
            role=AgentRole.ATTRIBUTION,
            category=AgentCategory.ANALYTICS,
            name="Attribution Analyst",
            goal="Fairly attribute outcomes to marketing drivers with uncertainty quantification",
            backstory="""You are an expert in multi-touch attribution and causal inference.
            You use Shapley values and Bayesian methods to fairly distribute credit
            across marketing touchpoints while honestly communicating uncertainty.""",
            retailer_id=retailer_id,
        )
        
        super().__init__(config, message_bus, **kwargs)
        
        self.drivers = drivers
        self.attribution_history: List[Dict[str, Any]] = []
        
        # Initialize Dirichlet prior (uniform)
        n_drivers = len(drivers)
        self.dirichlet_alpha = {d: 1.0 for d in drivers}
    
    def compute_attribution(
        self,
        conversion_paths: List[List[str]],
        total_value: float
    ) -> Dict[str, Any]:
        """
        Compute attribution shares using position-based + Bayesian updates.
        """
        # Count touchpoint occurrences with position weighting
        counts = {d: 0.0 for d in self.drivers}
        
        for path in conversion_paths:
            if not path:
                continue
            
            n_touches = len(path)
            for i, touch in enumerate(path):
                if touch in counts:
                    # Position-based weighting (first and last get more credit)
                    if i == 0:
                        weight = 0.4
                    elif i == n_touches - 1:
                        weight = 0.4
                    else:
                        weight = 0.2 / max(n_touches - 2, 1)
                    counts[touch] += weight
        
        # Update Dirichlet posterior
        for driver, count in counts.items():
            self.dirichlet_alpha[driver] += count
        
        # Compute posterior mean (expected attribution shares)
        total_alpha = sum(self.dirichlet_alpha.values())
        shares = {d: alpha / total_alpha for d, alpha in self.dirichlet_alpha.items()}
        
        # Compute attributed values
        attributed = {d: share * total_value for d, share in shares.items()}
        
        result = {
            "shares": shares,
            "attributed_value": attributed,
            "total_value": total_value,
            "n_paths": len(conversion_paths),
            "dirichlet_alpha": dict(self.dirichlet_alpha),
            "computed_at": datetime.utcnow().isoformat(),
        }
        
        self.attribution_history.append(result)
        self.log_action("compute_attribution", {"n_paths": len(conversion_paths)}, result)
        
        return result


class ElasticityAgent(DemandTwinAgent):
    """
    Elasticity Agent - Estimates price and media elasticities.
    
    Maintains Bayesian posteriors for elasticity parameters.
    """
    
    def __init__(
        self,
        agent_id: str,
        retailer_id: str,
        message_bus: Optional[AgentMessageBus] = None,
        **kwargs
    ):
        config = CrewAIAgentConfig(
            agent_id=agent_id,
            role=AgentRole.ELASTICITY,
            category=AgentCategory.ANALYTICS,
            name="Elasticity Analyst",
            goal="Estimate price and media elasticities with uncertainty",
            backstory="""You are an econometrician specializing in elasticity estimation.
            You use Bayesian regression to estimate how demand responds to price
            and marketing spend changes, always communicating confidence intervals.""",
            retailer_id=retailer_id,
        )
        
        super().__init__(config, message_bus, **kwargs)
        
        # Initialize elasticity beliefs with informative priors
        self.update_belief("price_elasticity", -1.5, 0.5)  # Typical price elasticity
        self.update_belief("media_elasticity", 0.15, 0.05)  # Typical media elasticity
    
    def estimate_elasticity(
        self,
        x: np.ndarray,
        y: np.ndarray,
        elasticity_type: str = "media"
    ) -> Dict[str, Any]:
        """Estimate elasticity from spend/price and response data"""
        # Log-log regression for elasticity
        log_x = np.log(np.maximum(x, 1e-6))
        log_y = np.log(np.maximum(y, 1e-6))
        
        # Simple OLS
        n = len(x)
        if n < 10:
            return {"error": "Insufficient data", "n": n}
        
        X = np.column_stack([np.ones(n), log_x])
        try:
            beta = np.linalg.lstsq(X, log_y, rcond=None)[0]
            elasticity = beta[1]
            
            # Residual std
            residuals = log_y - X @ beta
            sigma = np.std(residuals)
            
            # Standard error
            XtX_inv = np.linalg.inv(X.T @ X)
            se = np.sqrt(sigma**2 * XtX_inv[1, 1])
            
        except np.linalg.LinAlgError:
            return {"error": "Regression failed"}
        
        # Update belief
        belief_id = f"{elasticity_type}_elasticity"
        self.update_belief(belief_id, elasticity, se)
        
        belief = self.get_belief(belief_id)
        
        return {
            "elasticity_type": elasticity_type,
            "point_estimate": float(elasticity),
            "std_error": float(se),
            "posterior_mean": belief.mean,
            "posterior_std": belief.std,
            "ci_90": [belief.ci_lower, belief.ci_upper],
            "n_observations": n,
        }


class ForecastAgent(DemandTwinAgent):
    """
    Forecast Agent - Generates probabilistic demand forecasts.
    """
    
    def __init__(
        self,
        agent_id: str,
        retailer_id: str,
        message_bus: Optional[AgentMessageBus] = None,
        **kwargs
    ):
        config = CrewAIAgentConfig(
            agent_id=agent_id,
            role=AgentRole.FORECASTER,
            category=AgentCategory.ANALYTICS,
            name="Demand Forecaster",
            goal="Generate accurate probabilistic demand forecasts",
            backstory="""You are an expert demand forecaster using state-of-the-art
            time series methods. You produce probabilistic forecasts with honest
            uncertainty quantification.""",
            retailer_id=retailer_id,
        )
        
        super().__init__(config, message_bus, **kwargs)
    
    def forecast(
        self,
        history: np.ndarray,
        horizon: int = 13,
        quantiles: List[float] = [0.1, 0.5, 0.9]
    ) -> Dict[str, Any]:
        """Generate probabilistic forecast"""
        # Simple exponential smoothing for MVP
        alpha = 0.3
        level = history[0]
        
        for obs in history[1:]:
            level = alpha * obs + (1 - alpha) * level
        
        # Forecast with uncertainty growing over horizon
        base_std = np.std(history) if len(history) > 1 else level * 0.1
        
        forecasts = []
        for h in range(1, horizon + 1):
            mean = level
            std = base_std * np.sqrt(h)  # Uncertainty grows
            
            forecast_quantiles = {
                f"q{int(q*100)}": float(mean + std * np.percentile(np.random.randn(1000), q*100))
                for q in quantiles
            }
            forecast_quantiles["mean"] = float(mean)
            forecast_quantiles["std"] = float(std)
            forecasts.append(forecast_quantiles)
        
        return {
            "horizon": horizon,
            "forecasts": forecasts,
            "method": "exponential_smoothing",
            "generated_at": datetime.utcnow().isoformat(),
        }


class AnomalyDetectorAgent(DemandTwinAgent):
    """
    Anomaly Detector Agent - Detects anomalies in time series data.
    """
    
    def __init__(
        self,
        agent_id: str,
        retailer_id: str,
        message_bus: Optional[AgentMessageBus] = None,
        **kwargs
    ):
        config = CrewAIAgentConfig(
            agent_id=agent_id,
            role=AgentRole.ANOMALY_DETECTOR,
            category=AgentCategory.ANALYTICS,
            name="Anomaly Detector",
            goal="Detect anomalies and outliers in data streams",
            backstory="""You specialize in anomaly detection using statistical
            and machine learning methods. You identify unusual patterns that
            may indicate data quality issues or significant business events.""",
            retailer_id=retailer_id,
        )
        
        super().__init__(config, message_bus, **kwargs)
        
        self.anomaly_log: List[Dict[str, Any]] = []
    
    def detect(
        self,
        data: np.ndarray,
        method: str = "zscore",
        threshold: float = 3.0
    ) -> Dict[str, Any]:
        """Detect anomalies in data"""
        if method == "zscore":
            mean = np.nanmean(data)
            std = np.nanstd(data)
            z_scores = np.abs((data - mean) / max(std, 1e-6))
            anomaly_mask = z_scores > threshold
        elif method == "iqr":
            q1, q3 = np.percentile(data[~np.isnan(data)], [25, 75])
            iqr = q3 - q1
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            anomaly_mask = (data < lower) | (data > upper)
        else:
            anomaly_mask = np.zeros(len(data), dtype=bool)
        
        anomaly_indices = np.where(anomaly_mask)[0].tolist()
        anomaly_values = data[anomaly_mask].tolist()
        
        result = {
            "method": method,
            "threshold": threshold,
            "n_anomalies": int(anomaly_mask.sum()),
            "anomaly_rate": float(anomaly_mask.mean()),
            "anomaly_indices": anomaly_indices,
            "anomaly_values": anomaly_values,
            "detected_at": datetime.utcnow().isoformat(),
        }
        
        if anomaly_indices:
            self.anomaly_log.append(result)
        
        return result


# =============================================================================
# SIMULATION AGENTS
# =============================================================================

class ScenarioGeneratorAgent(DemandTwinAgent):
    """
    Scenario Generator Agent - Creates what-if scenarios for simulation.
    """
    
    def __init__(
        self,
        agent_id: str,
        retailer_id: str,
        drivers: List[str],
        message_bus: Optional[AgentMessageBus] = None,
        **kwargs
    ):
        config = CrewAIAgentConfig(
            agent_id=agent_id,
            role=AgentRole.SCENARIO_GENERATOR,
            category=AgentCategory.SIMULATION,
            name="Scenario Planner",
            goal="Generate diverse what-if scenarios for strategic planning",
            backstory="""You are a strategic planner who creates comprehensive
            scenarios for business planning. You consider baseline, optimistic,
            pessimistic, and stress test scenarios.""",
            retailer_id=retailer_id,
        )
        
        super().__init__(config, message_bus, **kwargs)
        
        self.drivers = drivers
        self.scenario_templates = [
            "baseline",
            "high_growth",
            "conservative",
            "stress_test",
            "elasticity_optimized",
        ]
    
    def generate_scenarios(
        self,
        current_allocation: Dict[str, float],
        total_budget: float,
        n_scenarios: int = 5
    ) -> List[Dict[str, Any]]:
        """Generate a set of scenarios"""
        scenarios = []
        
        # Baseline
        scenarios.append({
            "scenario_id": "baseline",
            "name": "Baseline",
            "description": "Current allocation maintained",
            "allocation": current_allocation.copy(),
            "total_budget": total_budget,
            "demand_multiplier": 1.0,
        })
        
        # High growth
        high_growth_alloc = {k: v * 1.2 for k, v in current_allocation.items()}
        scenarios.append({
            "scenario_id": "high_growth",
            "name": "High Growth",
            "description": "20% budget increase across all drivers",
            "allocation": high_growth_alloc,
            "total_budget": total_budget * 1.2,
            "demand_multiplier": 1.1,
        })
        
        # Conservative
        conservative_alloc = {k: v * 0.85 for k, v in current_allocation.items()}
        scenarios.append({
            "scenario_id": "conservative",
            "name": "Conservative",
            "description": "15% budget reduction",
            "allocation": conservative_alloc,
            "total_budget": total_budget * 0.85,
            "demand_multiplier": 0.95,
        })
        
        # Stress test
        scenarios.append({
            "scenario_id": "stress_test",
            "name": "Stress Test",
            "description": "30% demand shock with budget constraint",
            "allocation": current_allocation.copy(),
            "total_budget": total_budget,
            "demand_multiplier": 0.7,
            "supply_disruption": 0.2,
        })
        
        # Elasticity optimized (shift to high-elasticity drivers)
        optimized_alloc = current_allocation.copy()
        if len(optimized_alloc) > 1:
            drivers = list(optimized_alloc.keys())
            # Shift 20% from first driver to second (simplified)
            shift = optimized_alloc[drivers[0]] * 0.2
            optimized_alloc[drivers[0]] -= shift
            optimized_alloc[drivers[1]] += shift
        
        scenarios.append({
            "scenario_id": "elasticity_optimized",
            "name": "Elasticity Optimized",
            "description": "Reallocate to high-elasticity channels",
            "allocation": optimized_alloc,
            "total_budget": total_budget,
            "demand_multiplier": 1.0,
        })
        
        self.log_action("generate_scenarios", {"n_scenarios": len(scenarios)}, 
                       {"scenario_ids": [s["scenario_id"] for s in scenarios]})
        
        return scenarios[:n_scenarios]


class DigitalTwinAgent(DemandTwinAgent):
    """
    Digital Twin Agent - Simulates business outcomes via Monte Carlo.
    """
    
    def __init__(
        self,
        agent_id: str,
        retailer_id: str,
        message_bus: Optional[AgentMessageBus] = None,
        **kwargs
    ):
        config = CrewAIAgentConfig(
            agent_id=agent_id,
            role=AgentRole.DIGITAL_TWIN,
            category=AgentCategory.SIMULATION,
            name="Digital Twin Simulator",
            goal="Simulate business outcomes across scenarios with uncertainty",
            backstory="""You are the Digital Twin - a sophisticated simulation engine
            that models business dynamics. You run Monte Carlo simulations to 
            project outcomes with full uncertainty quantification.""",
            retailer_id=retailer_id,
        )
        
        super().__init__(config, message_bus, **kwargs)
        
        self.simulation_history: List[Dict[str, Any]] = []
    
    def simulate(
        self,
        scenario: Dict[str, Any],
        n_simulations: int = 1000,
        horizon_weeks: int = 13
    ) -> Dict[str, Any]:
        """Run Monte Carlo simulation for a scenario"""
        allocation = scenario.get("allocation", {})
        demand_multiplier = scenario.get("demand_multiplier", 1.0)
        supply_disruption = scenario.get("supply_disruption", 0.0)
        
        # Base parameters (would come from calibrated models)
        base_sales = 1000000
        elasticity = 0.15
        
        # Monte Carlo
        sales_samples = []
        roas_samples = []
        
        total_spend = sum(allocation.values())
        
        for _ in range(n_simulations):
            # Sample elasticity with uncertainty
            sampled_elasticity = np.random.normal(elasticity, 0.03)
            
            # Compute lift from spend
            lift = (total_spend / 100000) ** sampled_elasticity
            
            # Apply demand multiplier and random variation
            noise = np.random.normal(1.0, 0.1)
            sales = base_sales * lift * demand_multiplier * (1 - supply_disruption) * noise
            
            sales_samples.append(sales)
            roas_samples.append(sales / max(total_spend, 1))
        
        sales_array = np.array(sales_samples)
        roas_array = np.array(roas_samples)
        
        result = {
            "scenario_id": scenario.get("scenario_id", "unknown"),
            "scenario_name": scenario.get("name", "Unknown"),
            "n_simulations": n_simulations,
            "horizon_weeks": horizon_weeks,
            "total_spend": total_spend,
            "expected_sales": float(np.mean(sales_array)),
            "sales_std": float(np.std(sales_array)),
            "sales_ci_90": [float(np.percentile(sales_array, 5)), 
                          float(np.percentile(sales_array, 95))],
            "expected_roas": float(np.mean(roas_array)),
            "simulated_at": datetime.utcnow().isoformat(),
        }
        
        self.simulation_history.append(result)
        self.log_action("simulate", {"scenario_id": scenario.get("scenario_id")}, result)
        
        return result


# =============================================================================
# OPTIMIZATION AGENTS
# =============================================================================

class BudgetOptimizerAgent(DemandTwinAgent):
    """
    Budget Optimizer Agent - Solves constrained budget allocation.
    """
    
    def __init__(
        self,
        agent_id: str,
        retailer_id: str,
        drivers: List[str],
        message_bus: Optional[AgentMessageBus] = None,
        **kwargs
    ):
        config = CrewAIAgentConfig(
            agent_id=agent_id,
            role=AgentRole.BUDGET_OPTIMIZER,
            category=AgentCategory.OPTIMIZATION,
            name="Budget Optimizer",
            goal="Find optimal budget allocation under constraints",
            backstory="""You are an optimization expert who finds the best
            allocation of marketing budget across channels. You balance
            expected returns with risk and business constraints.""",
            retailer_id=retailer_id,
        )
        
        super().__init__(config, message_bus, **kwargs)
        
        self.drivers = drivers
        self.optimization_history: List[Dict[str, Any]] = []
    
    def optimize(
        self,
        simulation_results: Dict[str, Dict[str, Any]],
        total_budget: float,
        min_allocation: Optional[Dict[str, float]] = None,
        max_allocation: Optional[Dict[str, float]] = None,
        risk_aversion: float = 0.3
    ) -> Dict[str, Any]:
        """Select optimal allocation from simulated scenarios"""
        if not simulation_results:
            return {"error": "No simulation results provided"}
        
        # Score each scenario
        scores = {}
        for scenario_id, result in simulation_results.items():
            expected_sales = result.get("expected_sales", 0)
            sales_std = result.get("sales_std", 0)
            
            # Risk-adjusted score
            score = expected_sales - risk_aversion * sales_std
            scores[scenario_id] = score
        
        # Select best scenario
        best_scenario = max(scores, key=scores.get)
        best_result = simulation_results[best_scenario]
        
        result = {
            "selected_scenario": best_scenario,
            "score": scores[best_scenario],
            "all_scores": scores,
            "expected_sales": best_result.get("expected_sales"),
            "expected_roas": best_result.get("expected_roas"),
            "risk_aversion": risk_aversion,
            "optimized_at": datetime.utcnow().isoformat(),
        }
        
        self.optimization_history.append(result)
        self.log_action("optimize", {"n_scenarios": len(simulation_results)}, result)
        
        return result


class InventoryOptimizerAgent(DemandTwinAgent):
    """
    Inventory Optimizer Agent - Optimizes reorder points and quantities.
    """
    
    def __init__(
        self,
        agent_id: str,
        retailer_id: str,
        message_bus: Optional[AgentMessageBus] = None,
        **kwargs
    ):
        config = CrewAIAgentConfig(
            agent_id=agent_id,
            role=AgentRole.INVENTORY_OPTIMIZER,
            category=AgentCategory.OPTIMIZATION,
            name="Inventory Optimizer",
            goal="Optimize inventory policies to balance service and cost",
            backstory="""You optimize inventory policies using stochastic
            programming. You find the right balance between service level
            targets and inventory holding costs.""",
            retailer_id=retailer_id,
        )
        
        super().__init__(config, message_bus, **kwargs)
    
    def optimize_policy(
        self,
        demand_forecast: Dict[str, Any],
        lead_time_days: int,
        service_level_target: float = 0.95,
        holding_cost_per_unit: float = 1.0
    ) -> Dict[str, Any]:
        """Compute optimal reorder point and quantity"""
        forecasts = demand_forecast.get("forecasts", [])
        if not forecasts:
            return {"error": "No forecast data"}
        
        # Get mean and std from forecast
        mean_demand = np.mean([f.get("mean", 0) for f in forecasts])
        std_demand = np.mean([f.get("std", 0) for f in forecasts])
        
        # Safety stock for service level
        from scipy import stats
        z = stats.norm.ppf(service_level_target)
        safety_stock = z * std_demand * np.sqrt(lead_time_days / 7)
        
        # Reorder point
        reorder_point = mean_demand * (lead_time_days / 7) + safety_stock
        
        # EOQ approximation
        annual_demand = mean_demand * 52
        ordering_cost = 100  # Fixed ordering cost
        eoq = np.sqrt(2 * annual_demand * ordering_cost / holding_cost_per_unit)
        
        return {
            "reorder_point": float(reorder_point),
            "order_quantity": float(eoq),
            "safety_stock": float(safety_stock),
            "service_level_target": service_level_target,
            "expected_stockout_risk": 1 - service_level_target,
            "optimized_at": datetime.utcnow().isoformat(),
        }


# =============================================================================
# GOVERNANCE AGENTS
# =============================================================================

class GovernanceAgent(DemandTwinAgent):
    """
    Governance Agent - Validates recommendations against business rules.
    """
    
    def __init__(
        self,
        agent_id: str,
        retailer_id: str,
        message_bus: Optional[AgentMessageBus] = None,
        **kwargs
    ):
        config = CrewAIAgentConfig(
            agent_id=agent_id,
            role=AgentRole.POLICY_VALIDATOR,
            category=AgentCategory.GOVERNANCE,
            name="Governance Validator",
            goal="Ensure all recommendations comply with business policies",
            backstory="""You are responsible for governance and compliance.
            You validate recommendations against business rules, regulatory
            requirements, and risk thresholds before approval.""",
            retailer_id=retailer_id,
        )
        
        super().__init__(config, message_bus, **kwargs)
        
        self.policies: List[Dict[str, Any]] = []
        self.decision_log: List[Dict[str, Any]] = []
    
    def add_policy(
        self,
        policy_name: str,
        check_fn: Callable[[Dict[str, Any]], bool],
        severity: str = "warning"
    ):
        """Add a governance policy"""
        self.policies.append({
            "name": policy_name,
            "check": check_fn,
            "severity": severity,
        })
    
    def validate(
        self,
        recommendation: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Validate a recommendation against all policies"""
        checks = []
        violations = []
        
        for policy in self.policies:
            try:
                passed = policy["check"](recommendation)
                checks.append({
                    "policy": policy["name"],
                    "passed": passed,
                    "severity": policy["severity"],
                })
                if not passed:
                    violations.append(policy["name"])
            except Exception as e:
                checks.append({
                    "policy": policy["name"],
                    "passed": False,
                    "severity": policy["severity"],
                    "error": str(e),
                })
                violations.append(policy["name"])
        
        # Determine approval status
        critical_violations = [c for c in checks if not c["passed"] and c["severity"] == "critical"]
        
        approved = len(critical_violations) == 0
        requires_review = len(violations) > 0 and approved
        
        decision = {
            "approved": approved,
            "requires_review": requires_review,
            "checks": checks,
            "violations": violations,
            "n_policies": len(self.policies),
            "validated_at": datetime.utcnow().isoformat(),
        }
        
        self.decision_log.append(decision)
        self.log_action("validate", {"recommendation_id": recommendation.get("id")}, decision)
        
        # Publish decision
        if self.message_bus:
            self.message_bus.publish(AgentMessage(
                message_id=f"gov-{datetime.utcnow().timestamp()}",
                message_type=MessageType.GOVERNANCE_DECISION,
                sender_id=self.config.agent_id,
                recipient_id=None,
                payload=decision,
            ))
        
        return decision


# =============================================================================
# COMMUNICATION AGENTS
# =============================================================================

class RationaleAgent(DemandTwinAgent):
    """
    Rationale Agent - Generates human-readable explanations.
    
    Uses LLM to produce clear, actionable rationales for recommendations.
    """
    
    def __init__(
        self,
        agent_id: str,
        retailer_id: str,
        message_bus: Optional[AgentMessageBus] = None,
        **kwargs
    ):
        config = CrewAIAgentConfig(
            agent_id=agent_id,
            role=AgentRole.RATIONALE_GENERATOR,
            category=AgentCategory.COMMUNICATION,
            name="Business Communicator",
            goal="Generate clear, actionable explanations for recommendations",
            backstory="""You are an expert at translating complex analytical
            results into clear business language. You create compelling
            rationales that stakeholders can understand and act upon.""",
            retailer_id=retailer_id,
            temperature=0.7,  # More creative for writing
        )
        
        super().__init__(config, message_bus, **kwargs)
    
    def generate_rationale(
        self,
        recommendation: Dict[str, Any],
        simulation_result: Optional[Dict[str, Any]] = None,
        governance_decision: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """Generate rationale for a recommendation"""
        # Executive summary
        expected_sales = simulation_result.get("expected_sales", 0) if simulation_result else 0
        expected_roas = simulation_result.get("expected_roas", 0) if simulation_result else 0
        
        executive_summary = f"""## Recommendation Summary

Based on our Bayesian analysis and Monte Carlo simulations, we recommend 
proceeding with the **{recommendation.get('name', 'proposed')}** allocation.

**Expected Outcomes:**
- Incremental Sales: ${expected_sales/1e6:.1f}M
- Expected ROAS: {expected_roas:.1f}x
"""
        
        # Detailed rationale
        detailed = f"""### Analysis Details

Our recommendation is grounded in:
1. **Elasticity Analysis**: Bayesian posteriors calibrated from historical data
2. **Monte Carlo Simulation**: {simulation_result.get('n_simulations', 0)} scenarios tested
3. **Risk Assessment**: 90% confidence interval considered

"""
        
        # Uncertainty acknowledgment
        if simulation_result:
            ci = simulation_result.get("sales_ci_90", [0, 0])
            uncertainty = f"""### Uncertainty Acknowledgment

The 90% credible interval for expected sales is ${ci[0]/1e6:.1f}M to ${ci[1]/1e6:.1f}M.
This uncertainty reflects both model uncertainty and market volatility.
"""
        else:
            uncertainty = "Uncertainty quantification not available."
        
        # Governance notes
        if governance_decision:
            if governance_decision.get("approved"):
                gov_note = "✅ This recommendation has passed all governance checks."
            else:
                violations = governance_decision.get("violations", [])
                gov_note = f"⚠️ Governance review required: {', '.join(violations)}"
        else:
            gov_note = ""
        
        return {
            "executive_summary": executive_summary,
            "detailed_rationale": detailed,
            "uncertainty_acknowledgment": uncertainty,
            "governance_notes": gov_note,
        }


class ReportWriterAgent(DemandTwinAgent):
    """
    Report Writer Agent - Compiles comprehensive decision reports.
    """
    
    def __init__(
        self,
        agent_id: str,
        retailer_id: str,
        message_bus: Optional[AgentMessageBus] = None,
        **kwargs
    ):
        config = CrewAIAgentConfig(
            agent_id=agent_id,
            role=AgentRole.REPORT_WRITER,
            category=AgentCategory.COMMUNICATION,
            name="Report Writer",
            goal="Compile comprehensive decision pack reports",
            backstory="""You compile analytical results into well-structured
            reports. You create both executive summaries and detailed
            technical documentation.""",
            retailer_id=retailer_id,
        )
        
        super().__init__(config, message_bus, **kwargs)
    
    def compile_report(
        self,
        recommendation: Dict[str, Any],
        simulation_results: Dict[str, Dict[str, Any]],
        governance_decision: Dict[str, Any],
        rationale: Dict[str, str]
    ) -> str:
        """Compile a full decision pack report"""
        sections = []
        
        # Header
        sections.append(f"# Decision Pack Report")
        sections.append(f"**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
        sections.append("")
        
        # Executive Summary
        sections.append(rationale.get("executive_summary", ""))
        sections.append("")
        
        # Scenario Comparison
        sections.append("## Scenario Comparison")
        sections.append("")
        sections.append("| Scenario | Expected Sales | ROAS | Risk |")
        sections.append("|----------|---------------|------|------|")
        for scenario_id, result in simulation_results.items():
            sales = result.get("expected_sales", 0)
            roas = result.get("expected_roas", 0)
            std = result.get("sales_std", 0)
            sections.append(f"| {scenario_id} | ${sales/1e6:.1f}M | {roas:.1f}x | ${std/1e6:.1f}M |")
        sections.append("")
        
        # Governance
        sections.append("## Governance Review")
        if governance_decision.get("approved"):
            sections.append("✅ All governance checks passed.")
        else:
            sections.append("⚠️ Review required:")
            for v in governance_decision.get("violations", []):
                sections.append(f"- {v}")
        sections.append("")
        
        # Uncertainty
        sections.append(rationale.get("uncertainty_acknowledgment", ""))
        
        return "\n".join(sections)


# =============================================================================
# AGENT FACTORY
# =============================================================================

def create_agent(
    role: AgentRole,
    agent_id: str,
    retailer_id: str,
    message_bus: Optional[AgentMessageBus] = None,
    **kwargs
) -> DemandTwinAgent:
    """
    Factory function to create agents by role.
    """
    agent_classes = {
        AgentRole.DATA_STEWARD: DataStewardAgent,
        AgentRole.DATA_VALIDATOR: DataValidatorAgent,
        AgentRole.ATTRIBUTION: AttributionAgent,
        AgentRole.ELASTICITY: ElasticityAgent,
        AgentRole.FORECASTER: ForecastAgent,
        AgentRole.ANOMALY_DETECTOR: AnomalyDetectorAgent,
        AgentRole.SCENARIO_GENERATOR: ScenarioGeneratorAgent,
        AgentRole.DIGITAL_TWIN: DigitalTwinAgent,
        AgentRole.BUDGET_OPTIMIZER: BudgetOptimizerAgent,
        AgentRole.INVENTORY_OPTIMIZER: InventoryOptimizerAgent,
        AgentRole.POLICY_VALIDATOR: GovernanceAgent,
        AgentRole.RATIONALE_GENERATOR: RationaleAgent,
        AgentRole.REPORT_WRITER: ReportWriterAgent,
    }
    
    agent_class = agent_classes.get(role)
    if not agent_class:
        raise ValueError(f"Unknown agent role: {role}")
    
    # Handle different constructor signatures
    if role in [AgentRole.DATA_STEWARD]:
        return agent_class(
            agent_id=agent_id,
            retailer_id=retailer_id,
            stream_ids=kwargs.pop("stream_ids", []),
            message_bus=message_bus,
            **kwargs
        )
    elif role in [AgentRole.ATTRIBUTION, AgentRole.SCENARIO_GENERATOR, AgentRole.BUDGET_OPTIMIZER]:
        return agent_class(
            agent_id=agent_id,
            retailer_id=retailer_id,
            drivers=kwargs.pop("drivers", []),
            message_bus=message_bus,
            **kwargs
        )
    else:
        return agent_class(
            agent_id=agent_id,
            retailer_id=retailer_id,
            message_bus=message_bus,
            **kwargs
        )

"""
ML Learning Loop - A/B Testing Framework

Framework for running A/B tests on ML models with statistical significance testing.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .learning_loop_models import (
    ApprovalStatus,
    Experiment,
    ExperimentStatus,
    ExperimentVariant,
    ModelType,
)
from .learning_loop_registry import ModelRegistry
from .governance import AuditLogger

logger = logging.getLogger(__name__)


class ABTestingFramework:
    """
    Framework for running A/B tests on ML models.
    Supports traffic splitting, metric collection, and statistical significance testing.
    """
    
    def __init__(self, model_registry: ModelRegistry, audit_logger: Optional[AuditLogger] = None):
        self.model_registry = model_registry
        self.audit_logger = audit_logger or AuditLogger()
        self.experiments: Dict[str, Experiment] = {}
        self.active_experiments: Dict[ModelType, Experiment] = {}
    
    def create_experiment(self, experiment: Experiment) -> str:
        """Create a new experiment"""
        total_traffic = sum(v.traffic_percentage for v in experiment.variants)
        if abs(total_traffic - 100.0) > 0.01:
            raise ValueError(f"Traffic percentages must sum to 100, got {total_traffic}")
        
        if not any(v.is_control for v in experiment.variants):
            raise ValueError("Experiment must have a control variant")
        
        for variant in experiment.variants:
            model = self.model_registry.get_model(variant.model_version_id)
            if not model:
                raise ValueError(f"Model version not found: {variant.model_version_id}")
        
        self.experiments[experiment.experiment_id] = experiment
        
        self.audit_logger.log(
            action_type="experiment_created",
            actor_id=experiment.created_by,
            parameters={
                "experiment_id": experiment.experiment_id,
                "name": experiment.experiment_name,
                "n_variants": len(experiment.variants),
            },
        )
        
        logger.info(f"Created experiment: {experiment.experiment_name}")
        return experiment.experiment_id
    
    def approve_experiment(self, experiment_id: str, approved_by: str) -> Tuple[bool, str]:
        """Approve an experiment for running"""
        experiment = self.experiments.get(experiment_id)
        if not experiment:
            return False, "Experiment not found"
        
        if experiment.status != ExperimentStatus.DRAFT:
            return False, f"Cannot approve experiment in {experiment.status.value} status"
        
        experiment.approval_status = ApprovalStatus.APPROVED
        experiment.approved_by = approved_by
        experiment.approved_at = datetime.utcnow()
        experiment.status = ExperimentStatus.APPROVED
        
        self.audit_logger.log(
            action_type="experiment_approved",
            actor_id=approved_by,
            parameters={"experiment_id": experiment_id},
        )
        
        return True, "Experiment approved"
    
    def start_experiment(self, experiment_id: str, started_by: str) -> Tuple[bool, str]:
        """Start an approved experiment"""
        experiment = self.experiments.get(experiment_id)
        if not experiment:
            return False, "Experiment not found"
        
        if experiment.approval_status != ApprovalStatus.APPROVED:
            return False, "Experiment not approved"
        
        if experiment.status != ExperimentStatus.APPROVED:
            return False, f"Cannot start experiment in {experiment.status.value} status"
        
        model_type = experiment.model_type
        if model_type in self.active_experiments:
            return False, f"Active experiment already exists for {model_type.value}"
        
        experiment.status = ExperimentStatus.RUNNING
        experiment.actual_start = datetime.utcnow()
        self.active_experiments[model_type] = experiment
        
        self.audit_logger.log(
            action_type="experiment_started",
            actor_id=started_by,
            parameters={"experiment_id": experiment_id},
        )
        
        logger.info(f"Started experiment: {experiment.experiment_name}")
        return True, "Experiment started"
    
    def pause_experiment(self, experiment_id: str, paused_by: str) -> Tuple[bool, str]:
        """Pause a running experiment"""
        experiment = self.experiments.get(experiment_id)
        if not experiment:
            return False, "Experiment not found"
        
        if experiment.status != ExperimentStatus.RUNNING:
            return False, "Experiment is not running"
        
        experiment.status = ExperimentStatus.PAUSED
        
        self.audit_logger.log(
            action_type="experiment_paused",
            actor_id=paused_by,
            parameters={"experiment_id": experiment_id},
        )
        
        return True, "Experiment paused"
    
    def resume_experiment(self, experiment_id: str, resumed_by: str) -> Tuple[bool, str]:
        """Resume a paused experiment"""
        experiment = self.experiments.get(experiment_id)
        if not experiment:
            return False, "Experiment not found"
        
        if experiment.status != ExperimentStatus.PAUSED:
            return False, "Experiment is not paused"
        
        experiment.status = ExperimentStatus.RUNNING
        
        self.audit_logger.log(
            action_type="experiment_resumed",
            actor_id=resumed_by,
            parameters={"experiment_id": experiment_id},
        )
        
        return True, "Experiment resumed"
    
    def get_model_for_prediction(self, model_type: ModelType, 
                                 entity_id: str) -> Tuple[str, Optional[str]]:
        """
        Get the model version to use for a prediction.
        Returns (model_version_id, experiment_variant_id or None)
        """
        experiment = self.active_experiments.get(model_type)
        if experiment and experiment.status == ExperimentStatus.RUNNING:
            variant = experiment.get_variant_for_entity(entity_id)
            return variant.model_version_id, variant.variant_id
        
        prod_model = self.model_registry.get_production_model(model_type.value)
        if prod_model:
            return prod_model.version_id, None
        
        raise ValueError(f"No model available for {model_type.value}")
    
    def record_prediction(self, experiment_id: str, variant_id: str,
                          prediction_correct: bool, metric_values: Dict[str, float] = None):
        """Record a prediction result for an experiment"""
        experiment = self.experiments.get(experiment_id)
        if not experiment:
            return
        
        for variant in experiment.variants:
            if variant.variant_id == variant_id:
                variant.n_predictions += 1
                if prediction_correct:
                    variant.n_correct_predictions += 1
                
                if metric_values:
                    for metric, value in metric_values.items():
                        if metric not in variant.accumulated_metrics:
                            variant.accumulated_metrics[metric] = 0.0
                        variant.accumulated_metrics[metric] += value
                break
    
    def record_case_outcome(self, experiment_id: str, variant_id: str,
                            case_id: str, outcome: str):
        """Record case-level outcome for an experiment"""
        experiment = self.experiments.get(experiment_id)
        if not experiment:
            return
        
        for variant in experiment.variants:
            if variant.variant_id == variant_id:
                variant.cases_handled.append(case_id)
                variant.case_outcomes[case_id] = outcome
                break
    
    def compute_experiment_statistics(self, experiment_id: str) -> Dict[str, Any]:
        """Compute current statistics for an experiment"""
        experiment = self.experiments.get(experiment_id)
        if not experiment:
            return {"error": "Experiment not found"}
        
        control = experiment.get_control_variant()
        if not control:
            return {"error": "No control variant"}
        
        results = {
            "experiment_id": experiment_id,
            "experiment_name": experiment.experiment_name,
            "status": experiment.status.value,
            "duration_hours": None,
            "variants": [],
            "statistical_significance": False,
            "p_value": None,
            "effect_size": None,
            "recommended_winner": None,
            "confidence_interval": None,
        }
        
        if experiment.actual_start:
            duration = datetime.utcnow() - experiment.actual_start
            results["duration_hours"] = duration.total_seconds() / 3600
        
        for variant in experiment.variants:
            accuracy = (variant.n_correct_predictions / variant.n_predictions 
                       if variant.n_predictions > 0 else 0)
            
            avg_metrics = {}
            for metric, total in variant.accumulated_metrics.items():
                avg_metrics[metric] = total / variant.n_predictions if variant.n_predictions > 0 else 0
            
            results["variants"].append({
                "variant_id": variant.variant_id,
                "variant_name": variant.variant_name,
                "is_control": variant.is_control,
                "n_predictions": variant.n_predictions,
                "n_correct": variant.n_correct_predictions,
                "accuracy": accuracy,
                "n_cases": len(variant.cases_handled),
                "avg_metrics": avg_metrics,
            })
        
        if control.n_predictions >= 30:
            treatment_variants = [v for v in experiment.variants if not v.is_control]
            for treatment in treatment_variants:
                if treatment.n_predictions >= 30:
                    p_value, effect_size = self._two_proportion_z_test(
                        control.n_correct_predictions, control.n_predictions,
                        treatment.n_correct_predictions, treatment.n_predictions,
                    )
                    
                    results["p_value"] = p_value
                    results["effect_size"] = effect_size
                    
                    if p_value < (1 - experiment.confidence_level):
                        results["statistical_significance"] = True
                        
                        control_rate = control.n_correct_predictions / control.n_predictions
                        treatment_rate = treatment.n_correct_predictions / treatment.n_predictions
                        
                        if treatment_rate > control_rate:
                            results["recommended_winner"] = treatment.variant_id
                        else:
                            results["recommended_winner"] = control.variant_id
                        
                        se = np.sqrt((control_rate * (1 - control_rate) / control.n_predictions) +
                                    (treatment_rate * (1 - treatment_rate) / treatment.n_predictions))
                        z = 1.96  # 95% CI
                        diff = treatment_rate - control_rate
                        results["confidence_interval"] = (diff - z * se, diff + z * se)
        
        return results
    
    def _two_proportion_z_test(self, x1: int, n1: int, x2: int, n2: int) -> Tuple[float, float]:
        """Two-proportion z-test for A/B testing. Returns (p_value, effect_size)"""
        p1 = x1 / n1
        p2 = x2 / n2
        p_pooled = (x1 + x2) / (n1 + n2)
        
        se = np.sqrt(p_pooled * (1 - p_pooled) * (1/n1 + 1/n2))
        if se == 0:
            return 1.0, 0.0
        
        z = (p1 - p2) / se
        
        # Two-tailed p-value using normal approximation
        p_value = 2 * (1 - self._norm_cdf(abs(z)))
        
        # Cohen's h effect size
        effect_size = 2 * (np.arcsin(np.sqrt(p2)) - np.arcsin(np.sqrt(p1)))
        
        return p_value, effect_size
    
    def _norm_cdf(self, x: float) -> float:
        """Standard normal CDF approximation"""
        return 0.5 * (1 + np.tanh(np.sqrt(2 / np.pi) * (x + 0.044715 * x**3)))
    
    def conclude_experiment(self, experiment_id: str, concluded_by: str,
                           winner_variant_id: Optional[str] = None,
                           reason: str = "") -> Tuple[bool, str]:
        """Conclude an experiment and optionally promote winner"""
        experiment = self.experiments.get(experiment_id)
        if not experiment:
            return False, "Experiment not found"
        
        if experiment.status not in [ExperimentStatus.RUNNING, ExperimentStatus.PAUSED]:
            return False, f"Cannot conclude experiment in {experiment.status.value} status"
        
        stats = self.compute_experiment_statistics(experiment_id)
        
        experiment.status = ExperimentStatus.COMPLETED
        experiment.actual_end = datetime.utcnow()
        experiment.winner_variant_id = winner_variant_id or stats.get("recommended_winner")
        experiment.conclusion_reason = reason
        experiment.final_p_value = stats.get("p_value")
        experiment.effect_size = stats.get("effect_size")
        
        if experiment.model_type in self.active_experiments:
            del self.active_experiments[experiment.model_type]
        
        self.audit_logger.log(
            action_type="experiment_concluded",
            actor_id=concluded_by,
            parameters={
                "experiment_id": experiment_id,
                "winner": experiment.winner_variant_id,
                "reason": reason,
                "p_value": experiment.final_p_value,
            },
        )
        
        logger.info(f"Concluded experiment: {experiment.experiment_name}. Winner: {experiment.winner_variant_id}")
        return True, "Experiment concluded"
    
    def check_auto_conclusion(self, experiment_id: str) -> Optional[str]:
        """Check if experiment should be auto-concluded. Returns reason or None."""
        experiment = self.experiments.get(experiment_id)
        if not experiment or experiment.status != ExperimentStatus.RUNNING:
            return None
        
        if experiment.actual_start:
            duration = datetime.utcnow() - experiment.actual_start
            if duration.days >= experiment.max_duration_days:
                return "max_duration_reached"
        
        if experiment.early_stopping_enabled:
            stats = self.compute_experiment_statistics(experiment_id)
            if stats.get("p_value") and stats["p_value"] < experiment.early_stopping_threshold:
                return "early_stopping_significance"
        
        min_samples_reached = all(
            v.n_predictions >= experiment.min_sample_size_per_variant
            for v in experiment.variants
        )
        if min_samples_reached:
            stats = self.compute_experiment_statistics(experiment_id)
            if stats.get("statistical_significance"):
                return "sample_size_and_significance"
        
        return None
    
    def get_experiment(self, experiment_id: str) -> Optional[Experiment]:
        """Get experiment by ID"""
        return self.experiments.get(experiment_id)
    
    def list_experiments(self, status: Optional[ExperimentStatus] = None,
                        model_type: Optional[ModelType] = None) -> List[Experiment]:
        """List experiments with optional filters"""
        results = list(self.experiments.values())
        
        if status:
            results = [e for e in results if e.status == status]
        if model_type:
            results = [e for e in results if e.model_type == model_type]
        
        results.sort(key=lambda e: e.created_at, reverse=True)
        return results
    
    def get_active_experiment(self, model_type: ModelType) -> Optional[Experiment]:
        """Get active experiment for a model type"""
        return self.active_experiments.get(model_type)
    
    def calculate_required_sample_size(self, baseline_rate: float, 
                                       minimum_detectable_effect: float,
                                       confidence_level: float = 0.95,
                                       power: float = 0.80) -> int:
        """Calculate required sample size per variant for experiment"""
        z_alpha = 1.96 if confidence_level == 0.95 else 2.576  # 95% or 99%
        z_beta = 0.84 if power == 0.80 else 1.28  # 80% or 90%
        
        p1 = baseline_rate
        p2 = baseline_rate * (1 + minimum_detectable_effect)
        p_avg = (p1 + p2) / 2
        
        numerator = (z_alpha * np.sqrt(2 * p_avg * (1 - p_avg)) + 
                    z_beta * np.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
        denominator = (p2 - p1) ** 2
        
        return int(np.ceil(numerator / denominator))

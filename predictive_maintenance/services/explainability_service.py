"""
Explainability Service with SHAP-based Explanations

Provides interpretable explanations for fault hypothesis and decisions:
1. SHAP values for feature importance
2. Counterfactual explanations
3. Similar case retrieval
4. Natural language explanation generation

References:
- Lundberg & Lee, "A Unified Approach to Interpreting Model Predictions", NeurIPS 2017
- Wachter et al., "Counterfactual Explanations without Opening the Black Box", 2017
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid

import numpy as np

logger = logging.getLogger(__name__)

try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False
    logger.warning("SHAP not installed. Using simplified explanations.")


@dataclass
class FeatureContribution:
    """Individual feature's contribution to prediction"""
    feature_name: str
    feature_value: Any
    contribution: float  # SHAP value or similar
    direction: str  # "increases" or "decreases"
    importance_rank: int = 0
    baseline_value: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature": self.feature_name,
            "value": self.feature_value,
            "contribution": round(self.contribution, 4),
            "direction": self.direction,
            "rank": self.importance_rank,
        }


@dataclass
class CounterfactualExplanation:
    """What would need to change for a different outcome"""
    counterfactual_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    
    # Current state
    current_prediction: str = ""
    current_confidence: float = 0.0
    
    # Counterfactual
    target_prediction: str = ""
    required_changes: Dict[str, Tuple[Any, Any]] = field(default_factory=dict)  # feature -> (current, required)
    
    # Feasibility
    feasibility_score: float = 0.0  # How achievable are the changes
    distance: float = 0.0  # How different from current state
    
    explanation: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.counterfactual_id,
            "current": self.current_prediction,
            "target": self.target_prediction,
            "changes": {
                k: {"from": v[0], "to": v[1]}
                for k, v in self.required_changes.items()
            },
            "feasibility": round(self.feasibility_score, 2),
            "explanation": self.explanation,
        }


@dataclass
class SimilarCase:
    """A similar historical case for comparison"""
    case_id: str
    asset_id: str
    timestamp: datetime
    
    # Similarity
    similarity_score: float
    matching_features: List[str]
    
    # Outcome
    fault_type: str
    outcome: str
    resolution: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "asset_id": self.asset_id,
            "timestamp": self.timestamp.isoformat(),
            "similarity": round(self.similarity_score, 3),
            "matching_features": self.matching_features,
            "fault_type": self.fault_type,
            "outcome": self.outcome,
            "resolution": self.resolution,
        }


@dataclass
class FaultExplanation:
    """Complete explanation for a fault hypothesis"""
    explanation_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Prediction being explained
    asset_id: str = ""
    predicted_fault: str = ""
    confidence: float = 0.0
    false_alarm_probability: float = 0.0
    
    # Feature contributions (SHAP-based)
    top_contributors: List[FeatureContribution] = field(default_factory=list)
    
    # Counterfactuals
    counterfactuals: List[CounterfactualExplanation] = field(default_factory=list)
    
    # Similar cases
    similar_cases: List[SimilarCase] = field(default_factory=list)
    
    # Natural language summary
    summary: str = ""
    technical_details: str = ""
    recommended_investigation: str = ""
    
    # Gate explanations from decision pipeline
    gate_explanations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "explanation_id": self.explanation_id,
            "timestamp": self.timestamp.isoformat(),
            "asset_id": self.asset_id,
            "predicted_fault": self.predicted_fault,
            "confidence": round(self.confidence, 3),
            "false_alarm_probability": round(self.false_alarm_probability, 3),
            "summary": self.summary,
            "technical_details": self.technical_details,
            "recommended_investigation": self.recommended_investigation,
            "top_contributors": [c.to_dict() for c in self.top_contributors],
            "counterfactuals": [c.to_dict() for c in self.counterfactuals],
            "similar_cases": [c.to_dict() for c in self.similar_cases],
            "gate_explanations": self.gate_explanations,
        }


class ExplainabilityService:
    """
    Provides interpretable explanations for PDM predictions.
    
    Uses SHAP for feature importance when available,
    falls back to simplified gradient-based explanations otherwise.
    """
    
    def __init__(
        self,
        case_database: List[Dict[str, Any]] = None,
        feature_names: List[str] = None,
        feature_baselines: Dict[str, float] = None,
    ):
        self.case_database = case_database or []
        self.feature_names = feature_names or []
        self.feature_baselines = feature_baselines or {}
        
        # SHAP explainer (lazy initialization)
        self._shap_explainer = None
        
        # Feature importance cache
        self._global_importance: Dict[str, float] = {}
        
        logger.info(f"ExplainabilityService initialized (SHAP available: {SHAP_AVAILABLE})")
    
    def explain_fault_hypothesis(
        self,
        asset_id: str,
        features: Dict[str, float],
        fault_belief: Dict[str, float],
        predicted_fault: str,
        confidence: float,
        false_alarm_probability: float,
        gate_evaluations: List[Dict[str, Any]] = None,
        model_predict_fn: Callable = None,
    ) -> FaultExplanation:
        """
        Generate comprehensive explanation for a fault hypothesis.
        
        Args:
            asset_id: Asset being analyzed
            features: Current feature values
            fault_belief: Probability distribution over fault types
            predicted_fault: Most likely fault
            confidence: Prediction confidence
            false_alarm_probability: Estimated FA probability
            gate_evaluations: Decision gate results
            model_predict_fn: Optional model prediction function for SHAP
            
        Returns:
            FaultExplanation with all explanation components
        """
        explanation = FaultExplanation(
            asset_id=asset_id,
            predicted_fault=predicted_fault,
            confidence=confidence,
            false_alarm_probability=false_alarm_probability,
        )
        
        # 1. Compute feature contributions
        contributions = self._compute_feature_contributions(
            features, fault_belief, predicted_fault, model_predict_fn
        )
        explanation.top_contributors = contributions[:10]
        
        # 2. Generate counterfactuals
        counterfactuals = self._generate_counterfactuals(
            features, predicted_fault, fault_belief
        )
        explanation.counterfactuals = counterfactuals[:3]
        
        # 3. Find similar cases
        similar = self._find_similar_cases(features, predicted_fault)
        explanation.similar_cases = similar[:5]
        
        # 4. Extract gate explanations
        if gate_evaluations:
            explanation.gate_explanations = [
                f"{g.get('gate', 'Unknown')}: {g.get('reason', 'No reason')}"
                for g in gate_evaluations
                if not g.get('passed', True)
            ]
        
        # 5. Generate natural language summary
        explanation.summary = self._generate_summary(explanation)
        explanation.technical_details = self._generate_technical_details(explanation)
        explanation.recommended_investigation = self._generate_investigation_steps(explanation)
        
        return explanation
    
    def _compute_feature_contributions(
        self,
        features: Dict[str, float],
        fault_belief: Dict[str, float],
        predicted_fault: str,
        model_predict_fn: Callable = None,
    ) -> List[FeatureContribution]:
        """Compute SHAP or simplified feature contributions"""
        contributions = []
        
        if SHAP_AVAILABLE and model_predict_fn and self._shap_explainer:
            # Use SHAP
            contributions = self._compute_shap_values(features, model_predict_fn)
        else:
            # Simplified contribution estimation
            contributions = self._compute_simplified_contributions(features, fault_belief)
        
        # Sort by absolute contribution
        contributions.sort(key=lambda x: abs(x.contribution), reverse=True)
        
        # Assign ranks
        for i, c in enumerate(contributions):
            c.importance_rank = i + 1
        
        return contributions
    
    def _compute_simplified_contributions(
        self,
        features: Dict[str, float],
        fault_belief: Dict[str, float],
    ) -> List[FeatureContribution]:
        """Simplified contribution estimation without SHAP"""
        contributions = []
        
        # Use deviation from baseline as proxy for contribution
        for feature_name, value in features.items():
            baseline = self.feature_baselines.get(feature_name, 0)
            deviation = value - baseline
            
            # Estimate contribution based on deviation magnitude
            # This is a simplified heuristic
            contribution = deviation * self._global_importance.get(feature_name, 0.1)
            
            contributions.append(FeatureContribution(
                feature_name=feature_name,
                feature_value=value,
                contribution=contribution,
                direction="increases" if contribution > 0 else "decreases",
                baseline_value=baseline,
            ))
        
        return contributions
    
    def _compute_shap_values(
        self,
        features: Dict[str, float],
        model_predict_fn: Callable,
    ) -> List[FeatureContribution]:
        """Compute actual SHAP values"""
        if not SHAP_AVAILABLE:
            return []
        
        try:
            feature_array = np.array([[features.get(f, 0) for f in self.feature_names]])
            
            if self._shap_explainer is None:
                # Create explainer with background data
                background = np.zeros((1, len(self.feature_names)))
                self._shap_explainer = shap.KernelExplainer(model_predict_fn, background)
            
            shap_values = self._shap_explainer.shap_values(feature_array)
            
            contributions = []
            for i, fname in enumerate(self.feature_names):
                sv = float(shap_values[0][i]) if hasattr(shap_values[0], '__len__') else float(shap_values[i])
                contributions.append(FeatureContribution(
                    feature_name=fname,
                    feature_value=features.get(fname, 0),
                    contribution=sv,
                    direction="increases" if sv > 0 else "decreases",
                ))
            
            return contributions
            
        except Exception as e:
            logger.warning(f"SHAP computation failed: {e}")
            return self._compute_simplified_contributions(features, {})
    
    def _generate_counterfactuals(
        self,
        features: Dict[str, float],
        predicted_fault: str,
        fault_belief: Dict[str, float],
    ) -> List[CounterfactualExplanation]:
        """Generate counterfactual explanations"""
        counterfactuals = []
        
        # Target: no fault / healthy
        if predicted_fault and predicted_fault != "none":
            cf = self._generate_single_counterfactual(
                features, predicted_fault, "none", fault_belief
            )
            if cf:
                counterfactuals.append(cf)
        
        # Target: different fault types
        for fault_type, prob in sorted(fault_belief.items(), key=lambda x: -x[1])[:3]:
            if fault_type != predicted_fault and prob > 0.1:
                cf = self._generate_single_counterfactual(
                    features, predicted_fault, fault_type, fault_belief
                )
                if cf:
                    counterfactuals.append(cf)
        
        return counterfactuals
    
    def _generate_single_counterfactual(
        self,
        features: Dict[str, float],
        current_fault: str,
        target_fault: str,
        fault_belief: Dict[str, float],
    ) -> Optional[CounterfactualExplanation]:
        """Generate a single counterfactual explanation"""
        # Simplified counterfactual generation
        # In production, use optimization-based methods
        
        required_changes = {}
        
        # Identify which features would need to change
        # This is heuristic-based for demonstration
        if target_fault == "none":
            # To be healthy, anomalous readings should return to baseline
            for fname, value in features.items():
                baseline = self.feature_baselines.get(fname, value)
                if abs(value - baseline) > baseline * 0.2:  # >20% deviation
                    required_changes[fname] = (value, baseline)
        else:
            # For different fault, show key differentiating features
            # This would ideally use actual model gradients
            top_features = list(features.items())[:3]
            for fname, value in top_features:
                # Hypothetical change
                required_changes[fname] = (value, value * 0.9)
        
        if not required_changes:
            return None
        
        # Calculate feasibility (how achievable are the changes)
        total_change = sum(
            abs(v[1] - v[0]) / max(abs(v[0]), 1)
            for v in required_changes.values()
        )
        feasibility = max(0, 1 - total_change / len(required_changes))
        
        # Generate explanation
        change_descriptions = [
            f"{fname}: {v[0]:.2f} → {v[1]:.2f}"
            for fname, v in required_changes.items()
        ]
        
        return CounterfactualExplanation(
            current_prediction=current_fault,
            target_prediction=target_fault,
            required_changes=required_changes,
            feasibility_score=feasibility,
            distance=total_change,
            explanation=f"To change prediction to '{target_fault}': {', '.join(change_descriptions)}",
        )
    
    def _find_similar_cases(
        self,
        features: Dict[str, float],
        predicted_fault: str,
        max_results: int = 5,
    ) -> List[SimilarCase]:
        """Find similar historical cases"""
        if not self.case_database:
            return []
        
        similar = []
        
        for case in self.case_database:
            similarity, matching = self._compute_case_similarity(features, case)
            
            if similarity > 0.5:  # Threshold
                similar.append(SimilarCase(
                    case_id=case.get("case_id", "unknown"),
                    asset_id=case.get("asset_id", "unknown"),
                    timestamp=case.get("timestamp", datetime.utcnow()),
                    similarity_score=similarity,
                    matching_features=matching,
                    fault_type=case.get("fault_type", "unknown"),
                    outcome=case.get("outcome", "unknown"),
                    resolution=case.get("resolution", "unknown"),
                ))
        
        # Sort by similarity
        similar.sort(key=lambda x: -x.similarity_score)
        
        return similar[:max_results]
    
    def _compute_case_similarity(
        self,
        features: Dict[str, float],
        case: Dict[str, Any],
    ) -> Tuple[float, List[str]]:
        """Compute similarity between current state and historical case"""
        case_features = case.get("features", {})
        
        if not case_features:
            return 0.0, []
        
        matching = []
        total_diff = 0
        n_compared = 0
        
        for fname, value in features.items():
            if fname in case_features:
                case_value = case_features[fname]
                # Normalized difference
                max_val = max(abs(value), abs(case_value), 1)
                diff = abs(value - case_value) / max_val
                total_diff += diff
                n_compared += 1
                
                if diff < 0.1:  # Close match
                    matching.append(fname)
        
        if n_compared == 0:
            return 0.0, []
        
        avg_diff = total_diff / n_compared
        similarity = max(0, 1 - avg_diff)
        
        return similarity, matching
    
    def _generate_summary(self, explanation: FaultExplanation) -> str:
        """Generate natural language summary"""
        parts = []
        
        # Main prediction
        parts.append(
            f"Predicted fault: **{explanation.predicted_fault}** "
            f"with {explanation.confidence:.0%} confidence."
        )
        
        # False alarm context
        if explanation.false_alarm_probability > 0.1:
            parts.append(
                f"Note: {explanation.false_alarm_probability:.0%} estimated probability "
                "this is a false alarm based on historical calibration."
            )
        
        # Top contributors
        if explanation.top_contributors:
            top3 = explanation.top_contributors[:3]
            contrib_strs = [
                f"{c.feature_name} ({c.direction} likelihood)"
                for c in top3
            ]
            parts.append(f"Key factors: {', '.join(contrib_strs)}.")
        
        # Similar cases
        if explanation.similar_cases:
            best = explanation.similar_cases[0]
            parts.append(
                f"Similar case on {best.asset_id} ({best.similarity_score:.0%} match) "
                f"resulted in: {best.outcome}."
            )
        
        return " ".join(parts)
    
    def _generate_technical_details(self, explanation: FaultExplanation) -> str:
        """Generate technical details for experts"""
        lines = []
        
        lines.append(f"Asset: {explanation.asset_id}")
        lines.append(f"Fault Type: {explanation.predicted_fault}")
        lines.append(f"Confidence: {explanation.confidence:.3f}")
        lines.append(f"FA Probability: {explanation.false_alarm_probability:.3f}")
        
        if explanation.top_contributors:
            lines.append("\nFeature Contributions:")
            for c in explanation.top_contributors[:5]:
                lines.append(f"  {c.feature_name}: {c.contribution:+.4f} ({c.direction})")
        
        if explanation.gate_explanations:
            lines.append("\nDecision Gate Notes:")
            for g in explanation.gate_explanations:
                lines.append(f"  - {g}")
        
        return "\n".join(lines)
    
    def _generate_investigation_steps(self, explanation: FaultExplanation) -> str:
        """Generate recommended investigation steps"""
        steps = []
        
        fault = explanation.predicted_fault.lower()
        
        # Fault-specific recommendations
        if "leak" in fault:
            steps.append("1. Check refrigerant charge level")
            steps.append("2. Inspect line connections and fittings")
            steps.append("3. Use electronic leak detector on suspected areas")
        elif "compressor" in fault:
            steps.append("1. Check compressor amp draw vs nameplate")
            steps.append("2. Listen for unusual sounds")
            steps.append("3. Verify oil level and pressure")
        elif "fouling" in fault:
            steps.append("1. Inspect coil cleanliness")
            steps.append("2. Check air filter condition")
            steps.append("3. Measure pressure drop across coil")
        else:
            steps.append("1. Review recent sensor readings")
            steps.append("2. Compare with similar assets")
            steps.append("3. Check for environmental factors")
        
        # Add top contributor-specific steps
        if explanation.top_contributors:
            top = explanation.top_contributors[0]
            steps.append(f"4. Investigate {top.feature_name} anomaly specifically")
        
        return "\n".join(steps)
    
    def add_case_to_database(self, case: Dict[str, Any]):
        """Add a resolved case to the database for future similarity matching"""
        self.case_database.append(case)
        
        # Trim if too large
        if len(self.case_database) > 10000:
            self.case_database = self.case_database[-5000:]
    
    def update_global_importance(self, importance: Dict[str, float]):
        """Update global feature importance from model training"""
        self._global_importance.update(importance)
    
    def set_feature_baselines(self, baselines: Dict[str, float]):
        """Set baseline values for features (healthy state)"""
        self.feature_baselines.update(baselines)

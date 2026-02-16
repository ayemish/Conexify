"""
Advanced Services Demo

Demonstrates the Phase 3-4 capabilities:
1. Ensemble calibration with conformal prediction
2. Adaptive agent weights via Thompson Sampling
3. SHAP-based explainability
4. TFT RUL predictions
5. Physics-informed constraints
"""

import json
from datetime import datetime, timedelta
import random


def demo_ensemble_calibration():
    """Demonstrate ensemble calibration with conformal prediction"""
    print("\n" + "=" * 60)
    print("ENSEMBLE CALIBRATION WITH CONFORMAL PREDICTION")
    print("=" * 60)
    
    from predictive_maintenance.services.ensemble_calibration_service import (
        EnsembleCalibrationService,
    )
    
    # Initialize service
    service = EnsembleCalibrationService(
        model_ids=["weibull", "degradation", "trend", "ensemble"],
        coverage_level=0.90,
    )
    
    # Simulate predictions and updates
    print("\n1. Training calibration set with 50 observations...")
    for i in range(50):
        # Simulated model predictions
        true_value = 0.3 + 0.01 * i + random.gauss(0, 0.05)
        predictions = {
            "weibull": true_value + random.gauss(0, 0.08),
            "degradation": true_value + random.gauss(0.02, 0.06),
            "trend": true_value + random.gauss(-0.01, 0.07),
            "ensemble": true_value + random.gauss(0, 0.05),
        }
        intervals = {
            mid: (pred - 0.15, pred + 0.15)
            for mid, pred in predictions.items()
        }
        
        # Update calibration
        service.update(predictions, true_value, intervals)
    
    print(f"   Calibration set size: {len(service.conformity_scores)}")
    
    # Make a calibrated prediction
    print("\n2. Making calibrated prediction...")
    new_predictions = {
        "weibull": 0.75,
        "degradation": 0.78,
        "trend": 0.72,
        "ensemble": 0.76,
    }
    
    result = service.predict(new_predictions)
    
    print(f"   Point estimate: {result.point_estimate:.3f}")
    print(f"   90% interval: [{result.lower_bound:.3f}, {result.upper_bound:.3f}]")
    print(f"   Model weights: {json.dumps({k: round(v, 3) for k, v in result.model_weights.items()})}")
    
    # Get metrics
    print("\n3. Calibration metrics:")
    metrics = service.get_calibration_metrics()
    print(f"   Target coverage: {metrics.get('target_coverage', 0):.0%}")
    print(f"   Empirical coverage: {metrics.get('empirical_coverage', 0):.0%}")
    
    # Model ranking
    print("\n4. Model ranking by performance:")
    for mid, weight, mae in service.get_model_ranking():
        print(f"   {mid}: weight={weight:.3f}, MAE={mae:.4f}")


def demo_adaptive_agent_weights():
    """Demonstrate Thompson Sampling for agent weights"""
    print("\n" + "=" * 60)
    print("ADAPTIVE AGENT WEIGHTS VIA THOMPSON SAMPLING")
    print("=" * 60)
    
    from predictive_maintenance.services.adaptive_agent_weights import (
        AdaptiveAgentWeights,
    )
    
    # Initialize service
    service = AdaptiveAgentWeights(
        agent_roles=[
            "regime_detector",
            "sensor_trust",
            "behavior_modeler",
            "change_detector",
            "fault_hypothesis",
            "decision_policy",
        ],
    )
    
    # Simulate decisions and feedback
    print("\n1. Simulating 30 decisions with feedback...")
    for i in range(30):
        # Sample weights
        weights = service.sample_weights({"regime": "cooling", "fault_type": "refrigerant_leak"})
        
        # Simulate votes
        votes = {role: random.random() > 0.4 for role in service.agent_roles}
        
        # Record decision
        decision_id = service.record_decision(
            asset_id=f"RTU-{i:03d}",
            agent_votes=votes,
            agent_weights=weights,
            final_decision="alarm" if sum(votes.values()) > 3 else "watch",
            confidence=0.75,
            regime="cooling",
            fault_type="refrigerant_leak",
        )
        
        # Simulate feedback (some agents are more reliable)
        correct = random.random() > 0.3  # 70% correct overall
        service.update_from_feedback(decision_id, "confirmed" if correct else "false_alarm", correct)
    
    print(f"   Total decisions: {service._total_decisions}")
    print(f"   Overall accuracy: {service.overall_accuracy:.0%}")
    
    # Show agent statistics
    print("\n2. Agent reliability estimates:")
    for role, mean, confidence in service.get_ranking():
        print(f"   {role}: mean={mean:.3f}, confidence={confidence:.0%}")
    
    # Sample weights
    print("\n3. Thompson Sampled weights (exploration-exploitation):")
    sampled = service.sample_weights({"regime": "cooling"})
    for role, weight in sorted(sampled.items(), key=lambda x: -x[1]):
        print(f"   {role}: {weight:.3f}")


def demo_explainability():
    """Demonstrate SHAP-based explainability"""
    print("\n" + "=" * 60)
    print("SHAP-BASED EXPLAINABILITY")
    print("=" * 60)
    
    from predictive_maintenance.services.explainability_service import (
        ExplainabilityService,
    )
    
    # Initialize with baselines
    service = ExplainabilityService(
        feature_baselines={
            "suction_pressure": 70,
            "discharge_pressure": 250,
            "superheat": 10,
            "subcooling": 12,
            "compressor_current": 15,
            "return_air_temp": 75,
            "supply_air_temp": 55,
        },
    )
    
    # Update global importance
    service.update_global_importance({
        "suction_pressure": 0.15,
        "discharge_pressure": 0.12,
        "superheat": 0.25,
        "subcooling": 0.18,
        "compressor_current": 0.20,
        "return_air_temp": 0.05,
        "supply_air_temp": 0.05,
    })
    
    # Explain a fault hypothesis
    print("\n1. Explaining fault hypothesis...")
    features = {
        "suction_pressure": 55,  # Low - possible leak
        "discharge_pressure": 220,
        "superheat": 18,  # High
        "subcooling": 6,  # Low
        "compressor_current": 17,
        "return_air_temp": 78,
        "supply_air_temp": 62,  # High
    }
    
    explanation = service.explain_fault_hypothesis(
        asset_id="RTU-001",
        features=features,
        fault_belief={
            "refrigerant_leak": 0.72,
            "compressor_degradation": 0.15,
            "condenser_fouling": 0.08,
            "none": 0.05,
        },
        predicted_fault="refrigerant_leak",
        confidence=0.72,
        false_alarm_probability=0.12,
    )
    
    print(f"\n   Summary: {explanation.summary}")
    
    print("\n2. Top contributing features:")
    for c in explanation.top_contributors[:5]:
        print(f"   {c.feature_name}: {c.contribution:+.4f} ({c.direction})")
    
    print("\n3. Counterfactual explanation:")
    if explanation.counterfactuals:
        cf = explanation.counterfactuals[0]
        print(f"   {cf.explanation}")
    
    print(f"\n4. Recommended investigation:\n{explanation.recommended_investigation}")


def demo_tft_prediction():
    """Demonstrate TFT RUL prediction"""
    print("\n" + "=" * 60)
    print("TEMPORAL FUSION TRANSFORMER FOR RUL")
    print("=" * 60)
    
    from predictive_maintenance.models.temporal_fusion_transformer import (
        TFTRULPredictor,
    )
    
    predictor = TFTRULPredictor()
    
    # Static features
    static = {
        "asset_age": 35000,  # hours
        "asset_type": 1,
        "site_id": 42,
        "model_variant": 2,
        "install_year": 2019,
    }
    
    # Generate temporal features (degrading trend)
    print("\n1. Generating temporal features (48 hours, degrading)...")
    temporal = []
    for h in range(48):
        degradation = 0.3 + 0.008 * h + random.gauss(0, 0.02)
        temporal.append({
            "supply_temp": 55 + random.gauss(0, 1),
            "return_temp": 75 + random.gauss(0, 1),
            "ambient_temp": 95 + random.gauss(0, 2),
            "suction_pressure": 68 - 0.2 * h + random.gauss(0, 2),
            "discharge_pressure": 260 + random.gauss(0, 5),
            "superheat": 10 + 0.1 * h + random.gauss(0, 1),
            "subcooling": 12 - 0.08 * h + random.gauss(0, 0.5),
            "compressor_current": 15 + 0.05 * h + random.gauss(0, 0.5),
            "fan_speed": 80,
            "defrost_cycles": 2,
            "runtime_hours": 35000 + h,
            "starts_today": 5,
            "health_score": max(0, 100 - degradation * 100),
            "degradation_index": min(1, degradation),
            "regime": 1,  # cooling
        })
    
    # Predict
    print("2. Making TFT prediction...")
    result = predictor.predict(static, temporal, failure_threshold=0.8)
    
    print(f"\n   RUL estimate: {result.rul_hours:.1f} hours")
    print(f"   90% interval: [{result.rul_lower:.1f}, {result.rul_upper:.1f}] hours")
    print(f"   Degradation rate: {result.degradation_rate:.4f} per hour")
    
    if result.temporal_weights:
        print("\n3. Top temporal feature importance:")
        sorted_weights = sorted(
            result.temporal_weights.items(),
            key=lambda x: -x[1][0] if x[1] else 0,
        )[:5]
        for fname, weights in sorted_weights:
            print(f"   {fname}: {weights[0]:.4f}")


def demo_physics_constraints():
    """Demonstrate physics-informed constraints"""
    print("\n" + "=" * 60)
    print("PHYSICS-INFORMED CONSTRAINTS")
    print("=" * 60)
    
    from predictive_maintenance.models.physics_informed_constraints import (
        PhysicsInformedLoss,
    )
    
    loss = PhysicsInformedLoss()
    
    print("\n1. Active physics constraints:")
    for c in loss.constraints:
        print(f"   [{c.constraint_type.value}] {c.name}: {c.description}")
    
    # Check a healthy state
    print("\n2. Checking healthy operating state...")
    healthy_features = {
        "supply_air_temp": 55,
        "return_air_temp": 75,
        "load_proxy": 0.6,
        "superheat": 12,
        "subcooling": 10,
        "suction_pressure": 70,
        "discharge_pressure": 250,
        "compressor_current": 15,
        "rated_current": 20,
        "degradation_index": 0.2,
        "prev_degradation_index": 0.19,
    }
    
    penalty, violations = loss.compute_penalty(healthy_features)
    print(f"   Total penalty: {penalty:.4f}")
    print(f"   Violations: {len(violations)}")
    
    # Check an unhealthy state
    print("\n3. Checking unhealthy state (low superheat, high ratio)...")
    unhealthy_features = {
        "supply_air_temp": 60,
        "return_air_temp": 75,
        "load_proxy": 0.6,
        "superheat": 2,  # Too low!
        "subcooling": 3,  # Too low!
        "suction_pressure": 50,  # Low
        "discharge_pressure": 350,  # High ratio
        "compressor_current": 22,
        "rated_current": 20,
        "degradation_index": 0.1,  # Went down!
        "prev_degradation_index": 0.3,
    }
    
    penalty, violations = loss.compute_penalty(unhealthy_features)
    print(f"   Total penalty: {penalty:.4f}")
    print(f"   Violations:")
    for v in violations:
        print(f"      {v.constraint_name}: residual={v.residual:.3f}, penalty={v.penalty:.4f}")
    
    # Project to feasible
    print("\n4. Projecting to feasible region...")
    projected = loss.project_to_feasible(unhealthy_features)
    print(f"   superheat: {unhealthy_features['superheat']} → {projected['superheat']}")
    print(f"   subcooling: {unhealthy_features['subcooling']} → {projected['subcooling']}")


def main():
    """Run all demos"""
    print("\n" + "#" * 60)
    print("# ADVANCED SERVICES DEMONSTRATION")
    print("# Phase 3-4 Capabilities")
    print("#" * 60)
    
    demo_ensemble_calibration()
    demo_adaptive_agent_weights()
    demo_explainability()
    demo_tft_prediction()
    demo_physics_constraints()
    
    print("\n" + "=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)
    print("\nAll Phase 3-4 services are operational.")
    print("API endpoints available at /api/v1/advanced/")


if __name__ == "__main__":
    main()

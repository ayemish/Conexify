"""
PDM Fault Hypothesis Service (Bayesian Evidence Fusion)

Treats diagnosis as probabilistic hypothesis testing, NOT multiclass classification.

Maintains belief state:
- P(refrigerant_leak)
- P(fouled_coil)
- P(failed_fan)
- P(sensor_drift)
- P(control_instability)
- P(unknown_anomaly)

Then:
- Alarm only when probability mass crosses decision threshold
- Otherwise keep monitoring and gathering evidence

This naturally reduces false positives.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..core.schemas import (
    ChangePointDetection,
    FaultEvidence,
    FaultHypothesis,
    FaultType,
    OperatingRegime,
    ResidualObservation,
    SensorType,
)

logger = logging.getLogger(__name__)


@dataclass
class SymptomExtraction:
    """Extracted symptom from telemetry patterns"""
    symptom_id: str
    symptom_name: str
    sensor_types: List[SensorType]
    strength: float  # [0, 1]
    confidence: float
    description: str
    first_seen: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)


@dataclass
class FaultPrior:
    """Prior probability for a fault type from fleet statistics"""
    fault_type: FaultType
    base_rate: float  # Base failure rate per year
    age_factor: float = 0.0  # Increase per year of age
    runtime_factor: float = 0.0  # Increase per 1000 runtime hours
    seasonal_factor: Dict[str, float] = field(default_factory=dict)  # season -> multiplier


# Default priors from typical fleet statistics
DEFAULT_FAULT_PRIORS: Dict[FaultType, FaultPrior] = {
    FaultType.REFRIGERANT_LEAK: FaultPrior(
        fault_type=FaultType.REFRIGERANT_LEAK,
        base_rate=0.15,  # 15% of units per year
        age_factor=0.02,
        runtime_factor=0.005,
    ),
    FaultType.CONDENSER_FOULING: FaultPrior(
        fault_type=FaultType.CONDENSER_FOULING,
        base_rate=0.25,
        age_factor=0.01,
        seasonal_factor={"summer": 1.5, "spring": 1.2},
    ),
    FaultType.EVAPORATOR_FOULING: FaultPrior(
        fault_type=FaultType.EVAPORATOR_FOULING,
        base_rate=0.15,
        age_factor=0.01,
    ),
    FaultType.TXV_RESTRICTION: FaultPrior(
        fault_type=FaultType.TXV_RESTRICTION,
        base_rate=0.05,
        age_factor=0.015,
    ),
    FaultType.FAN_DEGRADATION: FaultPrior(
        fault_type=FaultType.FAN_DEGRADATION,
        base_rate=0.10,
        age_factor=0.02,
        runtime_factor=0.003,
    ),
    FaultType.COMPRESSOR_DEGRADATION: FaultPrior(
        fault_type=FaultType.COMPRESSOR_DEGRADATION,
        base_rate=0.05,
        age_factor=0.03,
        runtime_factor=0.008,
    ),
    FaultType.SENSOR_DRIFT: FaultPrior(
        fault_type=FaultType.SENSOR_DRIFT,
        base_rate=0.20,  # Common!
        age_factor=0.02,
    ),
    FaultType.SENSOR_STUCK: FaultPrior(
        fault_type=FaultType.SENSOR_STUCK,
        base_rate=0.08,
        age_factor=0.01,
    ),
    FaultType.CONTROL_INSTABILITY: FaultPrior(
        fault_type=FaultType.CONTROL_INSTABILITY,
        base_rate=0.10,
    ),
    FaultType.ELECTRICAL_ISSUE: FaultPrior(
        fault_type=FaultType.ELECTRICAL_ISSUE,
        base_rate=0.05,
        age_factor=0.02,
    ),
    FaultType.UNKNOWN_ANOMALY: FaultPrior(
        fault_type=FaultType.UNKNOWN_ANOMALY,
        base_rate=0.10,  # Catch-all
    ),
}


# Likelihood ratios: P(symptom | fault) / P(symptom | normal)
# These encode domain knowledge about fault signatures
SYMPTOM_LIKELIHOOD_RATIOS: Dict[str, Dict[FaultType, float]] = {
    "rising_superheat": {
        FaultType.REFRIGERANT_LEAK: 8.0,
        FaultType.TXV_RESTRICTION: 4.0,
        FaultType.EVAPORATOR_FOULING: 2.0,
        FaultType.CONDENSER_FOULING: 1.5,
    },
    "falling_superheat": {
        FaultType.REFRIGERANT_OVERCHARGE: 6.0,
        FaultType.TXV_RESTRICTION: 2.0,  # Can go either way
    },
    "high_discharge_pressure": {
        FaultType.CONDENSER_FOULING: 10.0,
        FaultType.REFRIGERANT_OVERCHARGE: 5.0,
        FaultType.FAN_DEGRADATION: 4.0,  # Condenser fan
    },
    "low_suction_pressure": {
        FaultType.REFRIGERANT_LEAK: 8.0,
        FaultType.TXV_RESTRICTION: 6.0,
        FaultType.EVAPORATOR_FOULING: 3.0,
    },
    "high_suction_pressure": {
        FaultType.COMPRESSOR_DEGRADATION: 6.0,
        FaultType.REFRIGERANT_OVERCHARGE: 4.0,
    },
    "high_subcool": {
        FaultType.TXV_RESTRICTION: 8.0,
        FaultType.REFRIGERANT_OVERCHARGE: 5.0,
    },
    "low_subcool": {
        FaultType.REFRIGERANT_LEAK: 6.0,
        FaultType.CONDENSER_FOULING: 3.0,
    },
    "increased_duty_cycle": {
        FaultType.REFRIGERANT_LEAK: 5.0,
        FaultType.CONDENSER_FOULING: 4.0,
        FaultType.EVAPORATOR_FOULING: 3.0,
        FaultType.COMPRESSOR_DEGRADATION: 3.0,
    },
    "high_compressor_current": {
        FaultType.COMPRESSOR_DEGRADATION: 5.0,
        FaultType.CONDENSER_FOULING: 3.0,
        FaultType.ELECTRICAL_ISSUE: 4.0,
    },
    "low_compressor_current": {
        FaultType.REFRIGERANT_LEAK: 4.0,
        FaultType.COMPRESSOR_DEGRADATION: 3.0,
    },
    "temperature_sensor_anomaly": {
        FaultType.SENSOR_DRIFT: 15.0,
        FaultType.SENSOR_STUCK: 10.0,
    },
    "pressure_sensor_anomaly": {
        FaultType.SENSOR_DRIFT: 12.0,
        FaultType.SENSOR_STUCK: 8.0,
    },
    "erratic_valve_behavior": {
        FaultType.CONTROL_INSTABILITY: 8.0,
        FaultType.TXV_RESTRICTION: 3.0,
    },
    "short_cycling": {
        FaultType.CONTROL_INSTABILITY: 6.0,
        FaultType.REFRIGERANT_LEAK: 3.0,
        FaultType.ELECTRICAL_ISSUE: 4.0,
    },
    "condenser_approach_high": {
        FaultType.CONDENSER_FOULING: 12.0,
        FaultType.FAN_DEGRADATION: 6.0,
    },
    "evaporator_approach_high": {
        FaultType.EVAPORATOR_FOULING: 10.0,
        FaultType.FAN_DEGRADATION: 4.0,
    },
}


class FaultHypothesisService:
    """
    Bayesian fault hypothesis testing.
    
    Instead of forcing one label, maintains belief state over all fault types.
    Uses evidence factors (symptom scores) with likelihood ratios.
    
    Computes: P(fault_i | evidence) ∝ P(evidence | fault_i) * P(fault_i)
    """
    
    def __init__(self, asset_id: str):
        self.asset_id = asset_id
        
        # Asset metadata for prior computation
        self.asset_age_years: float = 5.0
        self.runtime_hours: float = 20000.0
        self.current_season: str = "summer"
        
        # Prior probabilities
        self.priors: Dict[FaultType, float] = {}
        self._compute_priors()
        
        # Current hypothesis state
        self.current_hypothesis: Optional[FaultHypothesis] = None
        
        # Accumulated evidence
        self.evidence_buffer: List[FaultEvidence] = []
        self.symptom_history: Dict[str, List[SymptomExtraction]] = {}
        
        # Symptom extractors
        self.symptom_extractors: Dict[str, callable] = {}
        self._register_default_extractors()
        
        logger.info(f"FaultHypothesisService initialized for asset: {asset_id}")
    
    def _compute_priors(self):
        """Compute prior probabilities from fleet statistics and asset metadata"""
        total = 0.0
        raw_priors = {}
        
        for fault_type, prior_spec in DEFAULT_FAULT_PRIORS.items():
            # Base rate
            rate = prior_spec.base_rate
            
            # Age adjustment
            rate += prior_spec.age_factor * self.asset_age_years
            
            # Runtime adjustment
            rate += prior_spec.runtime_factor * (self.runtime_hours / 1000)
            
            # Seasonal adjustment
            if self.current_season in prior_spec.seasonal_factor:
                rate *= prior_spec.seasonal_factor[self.current_season]
            
            raw_priors[fault_type] = rate
            total += rate
        
        # Normalize to probabilities
        if total > 0:
            self.priors = {ft: rate / total for ft, rate in raw_priors.items()}
        else:
            # Uniform if no data
            n = len(FaultType)
            self.priors = {ft: 1.0 / n for ft in FaultType}
    
    def update_asset_metadata(self, age_years: float = None, 
                               runtime_hours: float = None,
                               season: str = None):
        """Update asset metadata and recompute priors"""
        if age_years is not None:
            self.asset_age_years = age_years
        if runtime_hours is not None:
            self.runtime_hours = runtime_hours
        if season is not None:
            self.current_season = season
        self._compute_priors()
    
    def _register_default_extractors(self):
        """Register default symptom extraction functions"""
        # These would be called with telemetry data
        pass  # Extractors are implemented in extract_symptoms method
    
    def extract_symptoms(self,
                         residual_obs: Dict[SensorType, ResidualObservation],
                         change_detections: Dict[str, ChangePointDetection],
                         telemetry: Dict[str, float]) -> List[SymptomExtraction]:
        """
        Extract symptoms from current telemetry state.
        
        This is the "symptom extraction library" that converts
        raw observations into fault-relevant symptoms.
        """
        symptoms = []
        now = datetime.utcnow()
        
        # 1. Superheat symptoms
        if SensorType.SUCTION_LINE_TEMP in residual_obs:
            obs = residual_obs[SensorType.SUCTION_LINE_TEMP]
            if obs.z_score and obs.z_score > 2.0:
                symptoms.append(SymptomExtraction(
                    symptom_id="rising_superheat",
                    symptom_name="Rising Superheat",
                    sensor_types=[SensorType.SUCTION_LINE_TEMP, SensorType.SUCTION_PRESSURE],
                    strength=min(1.0, obs.z_score / 4.0),
                    confidence=0.8,
                    description=f"Superheat elevated by {obs.z_score:.1f}σ",
                    first_seen=now,
                    last_seen=now,
                ))
            elif obs.z_score and obs.z_score < -2.0:
                symptoms.append(SymptomExtraction(
                    symptom_id="falling_superheat",
                    symptom_name="Falling Superheat",
                    sensor_types=[SensorType.SUCTION_LINE_TEMP, SensorType.SUCTION_PRESSURE],
                    strength=min(1.0, abs(obs.z_score) / 4.0),
                    confidence=0.8,
                    description=f"Superheat low by {abs(obs.z_score):.1f}σ",
                    first_seen=now,
                    last_seen=now,
                ))
        
        # 2. Discharge pressure symptoms
        if SensorType.DISCHARGE_PRESSURE in residual_obs:
            obs = residual_obs[SensorType.DISCHARGE_PRESSURE]
            if obs.z_score and obs.z_score > 2.0:
                symptoms.append(SymptomExtraction(
                    symptom_id="high_discharge_pressure",
                    symptom_name="High Discharge Pressure",
                    sensor_types=[SensorType.DISCHARGE_PRESSURE],
                    strength=min(1.0, obs.z_score / 4.0),
                    confidence=0.85,
                    description=f"Discharge pressure elevated by {obs.z_score:.1f}σ vs ambient",
                    first_seen=now,
                    last_seen=now,
                ))
        
        # 3. Suction pressure symptoms
        if SensorType.SUCTION_PRESSURE in residual_obs:
            obs = residual_obs[SensorType.SUCTION_PRESSURE]
            if obs.z_score and obs.z_score < -2.0:
                symptoms.append(SymptomExtraction(
                    symptom_id="low_suction_pressure",
                    symptom_name="Low Suction Pressure",
                    sensor_types=[SensorType.SUCTION_PRESSURE],
                    strength=min(1.0, abs(obs.z_score) / 4.0),
                    confidence=0.85,
                    description=f"Suction pressure low by {abs(obs.z_score):.1f}σ",
                    first_seen=now,
                    last_seen=now,
                ))
            elif obs.z_score and obs.z_score > 2.0:
                symptoms.append(SymptomExtraction(
                    symptom_id="high_suction_pressure",
                    symptom_name="High Suction Pressure",
                    sensor_types=[SensorType.SUCTION_PRESSURE],
                    strength=min(1.0, obs.z_score / 4.0),
                    confidence=0.85,
                    description=f"Suction pressure elevated by {obs.z_score:.1f}σ",
                    first_seen=now,
                    last_seen=now,
                ))
        
        # 4. Compressor current symptoms
        if SensorType.COMPRESSOR_CURRENT in residual_obs:
            obs = residual_obs[SensorType.COMPRESSOR_CURRENT]
            if obs.z_score and obs.z_score > 2.0:
                symptoms.append(SymptomExtraction(
                    symptom_id="high_compressor_current",
                    symptom_name="High Compressor Current",
                    sensor_types=[SensorType.COMPRESSOR_CURRENT],
                    strength=min(1.0, obs.z_score / 4.0),
                    confidence=0.8,
                    description=f"Compressor current elevated by {obs.z_score:.1f}σ",
                    first_seen=now,
                    last_seen=now,
                ))
            elif obs.z_score and obs.z_score < -2.0:
                symptoms.append(SymptomExtraction(
                    symptom_id="low_compressor_current",
                    symptom_name="Low Compressor Current",
                    sensor_types=[SensorType.COMPRESSOR_CURRENT],
                    strength=min(1.0, abs(obs.z_score) / 4.0),
                    confidence=0.8,
                    description=f"Compressor current low by {abs(obs.z_score):.1f}σ",
                    first_seen=now,
                    last_seen=now,
                ))
        
        # 5. Check for sensor-specific anomalies suggesting sensor issues
        for sensor_type, obs in residual_obs.items():
            if obs.z_score and abs(obs.z_score) > 4.0:
                # Very large deviation - might be sensor issue
                if sensor_type in [SensorType.SUCTION_LINE_TEMP, SensorType.LIQUID_LINE_TEMP,
                                   SensorType.RETURN_AIR_TEMP, SensorType.SUPPLY_AIR_TEMP]:
                    symptoms.append(SymptomExtraction(
                        symptom_id="temperature_sensor_anomaly",
                        symptom_name="Temperature Sensor Anomaly",
                        sensor_types=[sensor_type],
                        strength=min(1.0, (abs(obs.z_score) - 3.0) / 3.0),
                        confidence=0.7,
                        description=f"{sensor_type.value} deviating by {abs(obs.z_score):.1f}σ - possible sensor issue",
                        first_seen=now,
                        last_seen=now,
                    ))
                elif sensor_type in [SensorType.SUCTION_PRESSURE, SensorType.DISCHARGE_PRESSURE]:
                    symptoms.append(SymptomExtraction(
                        symptom_id="pressure_sensor_anomaly",
                        symptom_name="Pressure Sensor Anomaly",
                        sensor_types=[sensor_type],
                        strength=min(1.0, (abs(obs.z_score) - 3.0) / 3.0),
                        confidence=0.7,
                        description=f"{sensor_type.value} deviating by {abs(obs.z_score):.1f}σ - possible sensor issue",
                        first_seen=now,
                        last_seen=now,
                    ))
        
        # 6. Duty cycle / runtime symptoms from telemetry
        if "duty_cycle" in telemetry and "duty_cycle_baseline" in telemetry:
            duty_increase = telemetry["duty_cycle"] - telemetry["duty_cycle_baseline"]
            if duty_increase > 0.15:  # 15% increase
                symptoms.append(SymptomExtraction(
                    symptom_id="increased_duty_cycle",
                    symptom_name="Increased Duty Cycle",
                    sensor_types=[SensorType.COMPRESSOR_POWER],
                    strength=min(1.0, duty_increase / 0.30),
                    confidence=0.75,
                    description=f"Duty cycle increased from {telemetry['duty_cycle_baseline']:.0%} to {telemetry['duty_cycle']:.0%}",
                    first_seen=now,
                    last_seen=now,
                ))
        
        # Store symptoms
        for symptom in symptoms:
            if symptom.symptom_id not in self.symptom_history:
                self.symptom_history[symptom.symptom_id] = []
            self.symptom_history[symptom.symptom_id].append(symptom)
            # Limit history
            if len(self.symptom_history[symptom.symptom_id]) > 100:
                self.symptom_history[symptom.symptom_id] = \
                    self.symptom_history[symptom.symptom_id][-50:]
        
        return symptoms
    
    def update_hypothesis(self, symptoms: List[SymptomExtraction]) -> FaultHypothesis:
        """
        Update fault hypothesis using Bayesian evidence fusion.
        
        P(fault | symptoms) ∝ P(symptoms | fault) * P(fault)
        
        where P(symptoms | fault) = Π_i LR_i ^ strength_i
        """
        # Start with priors (log scale for numerical stability)
        log_posteriors = {ft: np.log(p + 1e-10) for ft, p in self.priors.items()}
        
        # Accumulate evidence from each symptom
        evidence_list = []
        
        for symptom in symptoms:
            symptom_likelihoods = SYMPTOM_LIKELIHOOD_RATIOS.get(symptom.symptom_id, {})
            
            for fault_type, lr in symptom_likelihoods.items():
                # Weight by symptom strength and confidence
                effective_lr = 1.0 + (lr - 1.0) * symptom.strength * symptom.confidence
                log_posteriors[fault_type] += np.log(effective_lr)
            
            # Create evidence record
            evidence = FaultEvidence(
                fault_type=max(symptom_likelihoods.keys(), key=lambda ft: symptom_likelihoods.get(ft, 1.0))
                          if symptom_likelihoods else FaultType.UNKNOWN_ANOMALY,
                symptom=symptom.symptom_name,
                sensor_sources=[st.value for st in symptom.sensor_types],
                likelihood_ratio=max(symptom_likelihoods.values()) if symptom_likelihoods else 1.0,
                strength=symptom.strength,
                confidence=symptom.confidence,
                first_observed=symptom.first_seen,
                last_observed=symptom.last_seen,
            )
            evidence_list.append(evidence)
        
        # Normalize to get posteriors
        max_log = max(log_posteriors.values())
        exp_posteriors = {ft: np.exp(lp - max_log) for ft, lp in log_posteriors.items()}
        total = sum(exp_posteriors.values())
        posteriors = {ft: p / total for ft, p in exp_posteriors.items()}
        
        # Sort by probability
        sorted_faults = sorted(posteriors.items(), key=lambda x: -x[1])
        
        # Create hypothesis
        hypothesis = FaultHypothesis(
            asset_id=self.asset_id,
            priors=self.priors.copy(),
            posteriors=posteriors,
            evidence=evidence_list,
            most_likely_fault=sorted_faults[0][0] if sorted_faults else None,
            second_likely_fault=sorted_faults[1][0] if len(sorted_faults) > 1 else None,
            probability_mass_top2=sorted_faults[0][1] + sorted_faults[1][1] 
                                  if len(sorted_faults) > 1 else sorted_faults[0][1],
            is_concentrated=sorted_faults[0][1] > 0.5 if sorted_faults else False,
            updated_at=datetime.utcnow(),
        )
        
        # Generate recommended action
        hypothesis.recommended_action = self._generate_recommendation(hypothesis)
        
        self.current_hypothesis = hypothesis
        return hypothesis
    
    def _generate_recommendation(self, hypothesis: FaultHypothesis) -> str:
        """Generate recommended action based on hypothesis"""
        if not hypothesis.most_likely_fault:
            return "Continue monitoring; insufficient evidence for diagnosis."
        
        top_fault = hypothesis.most_likely_fault
        top_prob = hypothesis.posteriors.get(top_fault, 0)
        
        # Fault-specific recommendations
        recommendations = {
            FaultType.REFRIGERANT_LEAK: "Inspect for refrigerant leak; check for oil stains at fittings; verify charge level.",
            FaultType.REFRIGERANT_OVERCHARGE: "Check refrigerant charge level; verify subcooling.",
            FaultType.TXV_RESTRICTION: "Inspect TXV for restriction; check superheat and subcooling; verify valve operation.",
            FaultType.CONDENSER_FOULING: "Clean condenser coil; check condenser fan operation; verify airflow.",
            FaultType.EVAPORATOR_FOULING: "Clean evaporator coil; check evap fan operation; verify airflow.",
            FaultType.FAN_DEGRADATION: "Inspect fan motor and blades; check bearings; measure current draw.",
            FaultType.COMPRESSOR_DEGRADATION: "Check compressor current and efficiency; listen for unusual sounds; verify oil level.",
            FaultType.SENSOR_DRIFT: "Verify sensor calibration; compare with reference measurement.",
            FaultType.SENSOR_STUCK: "Check sensor wiring; verify sensor is responding to changes.",
            FaultType.CONTROL_INSTABILITY: "Review control setpoints; check for competing control loops; verify PID tuning.",
            FaultType.ELECTRICAL_ISSUE: "Check electrical connections; verify voltage and phase balance.",
            FaultType.UNKNOWN_ANOMALY: "Manual inspection recommended; anomaly pattern not matching known faults.",
        }
        
        base_rec = recommendations.get(top_fault, "Inspect equipment.")
        
        # Add confidence qualifier
        if top_prob > 0.7:
            qualifier = "High confidence: "
        elif top_prob > 0.5:
            qualifier = "Moderate confidence: "
        else:
            qualifier = "Low confidence; gather more evidence: "
        
        # Add secondary hypothesis if close
        second_fault = hypothesis.second_likely_fault
        second_prob = hypothesis.posteriors.get(second_fault, 0) if second_fault else 0
        
        if second_prob > 0.2:
            secondary_rec = recommendations.get(second_fault, "")
            return f"{qualifier}{base_rec} Also consider {second_fault.value}: {secondary_rec}"
        
        return f"{qualifier}{base_rec}"
    
    def get_belief_distribution(self) -> Dict[str, float]:
        """Get current belief distribution over faults"""
        if not self.current_hypothesis:
            return {}
        return self.current_hypothesis.get_belief_distribution()
    
    def is_diagnosis_confident(self, threshold: float = 0.6) -> bool:
        """Check if diagnosis has sufficient confidence"""
        if not self.current_hypothesis:
            return False
        return self.current_hypothesis.probability_mass_top2 >= threshold
    
    def get_top_hypotheses(self, n: int = 3) -> List[Tuple[FaultType, float]]:
        """Get top N fault hypotheses with probabilities"""
        if not self.current_hypothesis:
            return []
        
        sorted_faults = sorted(
            self.current_hypothesis.posteriors.items(),
            key=lambda x: -x[1]
        )
        return sorted_faults[:n]
    
    def reset_evidence(self):
        """Reset accumulated evidence for new diagnosis"""
        self.evidence_buffer = []
        self.current_hypothesis = None
    
    def get_hypothesis_summary(self) -> Dict[str, Any]:
        """Get summary of current hypothesis state"""
        if not self.current_hypothesis:
            return {"status": "no_hypothesis"}
        
        return {
            "most_likely": self.current_hypothesis.most_likely_fault.value 
                          if self.current_hypothesis.most_likely_fault else None,
            "probability": self.current_hypothesis.posteriors.get(
                self.current_hypothesis.most_likely_fault, 0
            ) if self.current_hypothesis.most_likely_fault else 0,
            "is_concentrated": self.current_hypothesis.is_concentrated,
            "top_3": [
                {"fault": ft.value, "probability": f"{p:.1%}"}
                for ft, p in self.get_top_hypotheses(3)
            ],
            "n_evidence": len(self.current_hypothesis.evidence),
            "recommendation": self.current_hypothesis.recommended_action,
        }

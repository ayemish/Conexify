"""
Physics-Informed Constraints for Model Training

Embeds thermodynamic and mechanical physics constraints into neural network training:
1. Conservation laws (energy, mass, refrigerant)
2. Thermodynamic cycle constraints (COP bounds, superheat limits)
3. Mechanical constraints (compressor curves, fan laws)
4. Soft penalties and hard projections

References:
- Raissi et al., "Physics-informed neural networks", JCP 2019
- Karniadakis et al., "Physics-informed machine learning", Nature Reviews Physics 2021
- ASHRAE Handbook - Fundamentals
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid

import numpy as np

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


class ConstraintType(str, Enum):
    """Types of physics constraints"""
    ENERGY_BALANCE = "energy_balance"
    REFRIGERANT_MASS = "refrigerant_mass"
    THERMODYNAMIC_CYCLE = "thermodynamic_cycle"
    MECHANICAL_LIMITS = "mechanical_limits"
    TEMPORAL_CONSISTENCY = "temporal_consistency"


@dataclass
class PhysicsConstraint:
    """Single physics constraint definition"""
    constraint_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    constraint_type: ConstraintType = ConstraintType.ENERGY_BALANCE
    
    # Constraint function: returns residual (should be 0 for satisfied)
    residual_fn: Optional[Callable] = None
    
    # Penalty weight
    weight: float = 1.0
    
    # Tolerance for soft constraint
    tolerance: float = 0.01
    
    # Hard constraint (projected) vs soft (penalized)
    is_hard: bool = False
    
    # Description
    description: str = ""
    equation: str = ""


@dataclass
class ConstraintViolation:
    """Record of a constraint violation"""
    constraint_id: str
    constraint_name: str
    residual: float
    penalty: float
    features: Dict[str, float] = field(default_factory=dict)
    timestamp: str = ""


class PhysicsConstraintLibrary:
    """
    Library of HVAC/R physics constraints.
    
    Provides ready-to-use constraints for refrigeration cycle physics.
    """
    
    @staticmethod
    def energy_balance_evaporator() -> PhysicsConstraint:
        """
        Evaporator energy balance:
        Q_evap = m_dot_ref * (h_out - h_in) = m_dot_air * cp_air * (T_air_in - T_air_out)
        
        Simplified: T_return - T_supply should be proportional to load
        """
        def residual(features: Dict[str, float]) -> float:
            t_return = features.get("return_air_temp", 75)
            t_supply = features.get("supply_air_temp", 55)
            load_proxy = features.get("load_proxy", 0.5)
            
            # Expected delta-T based on load
            expected_delta_t = 15 + 10 * load_proxy  # 15-25°F typical
            actual_delta_t = t_return - t_supply
            
            # Residual (normalized)
            return (actual_delta_t - expected_delta_t) / expected_delta_t
        
        return PhysicsConstraint(
            name="evaporator_energy_balance",
            constraint_type=ConstraintType.ENERGY_BALANCE,
            residual_fn=residual,
            weight=1.0,
            description="Evaporator heat transfer balance",
            equation="Q_evap = m_air * cp * ΔT_air",
        )
    
    @staticmethod
    def superheat_limits() -> PhysicsConstraint:
        """
        Superheat must be positive and within safe range:
        5°F < SH < 30°F for normal operation
        """
        def residual(features: Dict[str, float]) -> float:
            superheat = features.get("superheat", 10)
            
            if superheat < 5:
                return (5 - superheat) / 5  # Violation below minimum
            elif superheat > 30:
                return (superheat - 30) / 30  # Violation above maximum
            return 0.0
        
        return PhysicsConstraint(
            name="superheat_limits",
            constraint_type=ConstraintType.THERMODYNAMIC_CYCLE,
            residual_fn=residual,
            weight=2.0,
            description="Superheat within safe operating range",
            equation="5°F < SH < 30°F",
        )
    
    @staticmethod
    def subcooling_limits() -> PhysicsConstraint:
        """
        Subcooling must be positive:
        5°F < SC < 20°F for normal operation
        """
        def residual(features: Dict[str, float]) -> float:
            subcooling = features.get("subcooling", 10)
            
            if subcooling < 5:
                return (5 - subcooling) / 5
            elif subcooling > 20:
                return (subcooling - 20) / 20
            return 0.0
        
        return PhysicsConstraint(
            name="subcooling_limits",
            constraint_type=ConstraintType.THERMODYNAMIC_CYCLE,
            residual_fn=residual,
            weight=2.0,
            description="Subcooling within safe operating range",
            equation="5°F < SC < 20°F",
        )
    
    @staticmethod
    def cop_bounds() -> PhysicsConstraint:
        """
        COP must be physically reasonable:
        1.5 < COP < 6 for typical HVAC/R
        
        COP ≈ Q_evap / W_comp
        """
        def residual(features: Dict[str, float]) -> float:
            # Estimate COP from available data
            suction_p = features.get("suction_pressure", 70)
            discharge_p = features.get("discharge_pressure", 250)
            
            # Simplified COP estimate (inverse of pressure ratio proxy)
            pressure_ratio = discharge_p / max(suction_p, 1)
            estimated_cop = 8 / pressure_ratio  # Rough approximation
            
            if estimated_cop < 1.5:
                return (1.5 - estimated_cop) / 1.5
            elif estimated_cop > 6:
                return (estimated_cop - 6) / 6
            return 0.0
        
        return PhysicsConstraint(
            name="cop_bounds",
            constraint_type=ConstraintType.THERMODYNAMIC_CYCLE,
            residual_fn=residual,
            weight=1.5,
            description="COP within physically reasonable bounds",
            equation="1.5 < COP < 6",
        )
    
    @staticmethod
    def compressor_curve() -> PhysicsConstraint:
        """
        Compressor current should follow pressure ratio curve:
        I ∝ (P_discharge / P_suction)^k
        """
        def residual(features: Dict[str, float]) -> float:
            current = features.get("compressor_current", 15)
            suction_p = features.get("suction_pressure", 70)
            discharge_p = features.get("discharge_pressure", 250)
            rated_current = features.get("rated_current", 20)
            
            # Expected current based on pressure ratio
            pressure_ratio = discharge_p / max(suction_p, 1)
            k = 0.5  # Polytropic exponent proxy
            expected_current = rated_current * 0.6 * (pressure_ratio / 3.5) ** k
            
            deviation = abs(current - expected_current) / max(expected_current, 1)
            return deviation if deviation > 0.2 else 0.0  # 20% tolerance
        
        return PhysicsConstraint(
            name="compressor_curve",
            constraint_type=ConstraintType.MECHANICAL_LIMITS,
            residual_fn=residual,
            weight=1.0,
            description="Compressor current follows expected curve",
            equation="I ∝ (P_d/P_s)^k",
        )
    
    @staticmethod
    def fan_affinity_laws() -> PhysicsConstraint:
        """
        Fan power follows cube law:
        P ∝ (RPM)^3
        """
        def residual(features: Dict[str, float]) -> float:
            fan_speed_pct = features.get("fan_speed", 100) / 100
            fan_power = features.get("fan_power", 1)
            rated_power = features.get("rated_fan_power", 1)
            
            # Expected power from affinity law
            expected_power = rated_power * (fan_speed_pct ** 3)
            
            if expected_power > 0:
                deviation = abs(fan_power - expected_power) / expected_power
                return deviation if deviation > 0.15 else 0.0
            return 0.0
        
        return PhysicsConstraint(
            name="fan_affinity_laws",
            constraint_type=ConstraintType.MECHANICAL_LIMITS,
            residual_fn=residual,
            weight=0.5,
            description="Fan power follows cube law",
            equation="P ∝ RPM³",
        )
    
    @staticmethod
    def pressure_relationship() -> PhysicsConstraint:
        """
        Discharge pressure must exceed suction pressure:
        P_discharge > P_suction (always)
        """
        def residual(features: Dict[str, float]) -> float:
            suction_p = features.get("suction_pressure", 70)
            discharge_p = features.get("discharge_pressure", 250)
            
            if discharge_p <= suction_p:
                return 1.0  # Maximum violation
            
            # Typical ratio should be 2-5
            ratio = discharge_p / max(suction_p, 1)
            if ratio < 2:
                return (2 - ratio) / 2
            elif ratio > 6:
                return (ratio - 6) / 6
            return 0.0
        
        return PhysicsConstraint(
            name="pressure_relationship",
            constraint_type=ConstraintType.THERMODYNAMIC_CYCLE,
            residual_fn=residual,
            weight=3.0,  # High weight - fundamental constraint
            is_hard=True,
            description="Discharge pressure exceeds suction",
            equation="P_d > P_s, 2 < P_d/P_s < 6",
        )
    
    @staticmethod
    def temporal_degradation() -> PhysicsConstraint:
        """
        Degradation index should not decrease significantly over time
        (equipment doesn't spontaneously heal)
        """
        def residual(features: Dict[str, float]) -> float:
            current_deg = features.get("degradation_index", 0)
            prev_deg = features.get("prev_degradation_index", 0)
            
            # Allow small decrease (measurement noise) but not large
            if current_deg < prev_deg - 0.05:
                return (prev_deg - current_deg - 0.05) / max(prev_deg, 0.1)
            return 0.0
        
        return PhysicsConstraint(
            name="temporal_degradation",
            constraint_type=ConstraintType.TEMPORAL_CONSISTENCY,
            residual_fn=residual,
            weight=1.0,
            description="Degradation monotonically increasing",
            equation="d(degradation)/dt ≥ 0",
        )


class PhysicsInformedLoss:
    """
    Physics-informed loss function for neural network training.
    
    Combines data-driven loss with physics constraint penalties.
    """
    
    def __init__(
        self,
        constraints: List[PhysicsConstraint] = None,
        physics_weight: float = 0.1,
    ):
        self.constraints = constraints or []
        self.physics_weight = physics_weight
        
        # Initialize with standard HVAC constraints
        if not self.constraints:
            self._add_default_constraints()
        
        # Violation tracking
        self.violation_history: List[ConstraintViolation] = []
        
        logger.info(f"PhysicsInformedLoss initialized with {len(self.constraints)} constraints")
    
    def _add_default_constraints(self):
        """Add standard HVAC physics constraints"""
        lib = PhysicsConstraintLibrary
        self.constraints = [
            lib.energy_balance_evaporator(),
            lib.superheat_limits(),
            lib.subcooling_limits(),
            lib.cop_bounds(),
            lib.compressor_curve(),
            lib.pressure_relationship(),
            lib.temporal_degradation(),
        ]
    
    def compute_penalty(
        self,
        features: Dict[str, float],
        record_violations: bool = True,
    ) -> Tuple[float, List[ConstraintViolation]]:
        """
        Compute total physics penalty for given features.
        
        Args:
            features: Feature dict
            record_violations: Whether to record violations for analysis
            
        Returns:
            (total_penalty, list of violations)
        """
        total_penalty = 0.0
        violations = []
        
        for constraint in self.constraints:
            if constraint.residual_fn is None:
                continue
            
            try:
                residual = constraint.residual_fn(features)
                
                # Apply tolerance
                if abs(residual) <= constraint.tolerance:
                    residual = 0.0
                
                # Compute penalty (quadratic)
                penalty = constraint.weight * (residual ** 2)
                total_penalty += penalty
                
                # Record violation
                if abs(residual) > constraint.tolerance and record_violations:
                    violation = ConstraintViolation(
                        constraint_id=constraint.constraint_id,
                        constraint_name=constraint.name,
                        residual=residual,
                        penalty=penalty,
                        features={k: v for k, v in features.items() if k in [
                            "suction_pressure", "discharge_pressure",
                            "superheat", "subcooling", "compressor_current"
                        ]},
                    )
                    violations.append(violation)
                    self.violation_history.append(violation)
                    
            except Exception as e:
                logger.warning(f"Constraint {constraint.name} evaluation failed: {e}")
        
        return total_penalty * self.physics_weight, violations
    
    def get_loss_function(self):
        """
        Get PyTorch-compatible loss function.
        
        Returns a function that can be added to training loss.
        """
        if not TORCH_AVAILABLE:
            return None
        
        def physics_loss(predictions, features_batch):
            """Compute physics loss for a batch"""
            import torch
            
            batch_size = predictions.size(0)
            total_loss = torch.tensor(0.0)
            
            for i in range(batch_size):
                # Convert tensor to feature dict
                features = {
                    name: float(features_batch[i, j])
                    for j, name in enumerate(self._feature_names)
                }
                
                penalty, _ = self.compute_penalty(features, record_violations=False)
                total_loss = total_loss + penalty
            
            return total_loss / batch_size
        
        return physics_loss
    
    def project_to_feasible(
        self,
        features: Dict[str, float],
    ) -> Dict[str, float]:
        """
        Project features to feasible region (for hard constraints).
        
        Simple projection for common constraints.
        """
        projected = features.copy()
        
        # Superheat bounds
        if "superheat" in projected:
            projected["superheat"] = max(5, min(30, projected["superheat"]))
        
        # Subcooling bounds
        if "subcooling" in projected:
            projected["subcooling"] = max(5, min(20, projected["subcooling"]))
        
        # Pressure relationship
        if "suction_pressure" in projected and "discharge_pressure" in projected:
            suction = projected["suction_pressure"]
            discharge = projected["discharge_pressure"]
            
            if discharge <= suction:
                # Enforce minimum ratio
                projected["discharge_pressure"] = suction * 2.5
        
        # Health/degradation bounds
        if "health_score" in projected:
            projected["health_score"] = max(0, min(100, projected["health_score"]))
        
        if "degradation_index" in projected:
            projected["degradation_index"] = max(0, min(1, projected["degradation_index"]))
        
        return projected
    
    def get_violation_summary(self) -> Dict[str, Any]:
        """Get summary of constraint violations"""
        if not self.violation_history:
            return {"total_violations": 0}
        
        by_constraint = {}
        for v in self.violation_history[-1000:]:
            if v.constraint_name not in by_constraint:
                by_constraint[v.constraint_name] = []
            by_constraint[v.constraint_name].append(v.residual)
        
        summary = {
            "total_violations": len(self.violation_history),
            "by_constraint": {
                name: {
                    "count": len(residuals),
                    "mean_residual": float(np.mean(residuals)),
                    "max_residual": float(np.max(np.abs(residuals))),
                }
                for name, residuals in by_constraint.items()
            },
        }
        
        return summary
    
    def add_constraint(self, constraint: PhysicsConstraint):
        """Add a custom constraint"""
        self.constraints.append(constraint)
    
    def remove_constraint(self, name: str):
        """Remove a constraint by name"""
        self.constraints = [c for c in self.constraints if c.name != name]
    
    def set_constraint_weight(self, name: str, weight: float):
        """Update constraint weight"""
        for c in self.constraints:
            if c.name == name:
                c.weight = weight
                break

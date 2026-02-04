# Predictive Maintenance (PDM) Project

A comprehensive predictive maintenance system for HVAC/R equipment.

> **Note**: This project is **SEPARATE and DISTINCT** from the RMN (Retail Media Network) project.

## Overview

This system implements advanced predictive maintenance using:
- **Radar-inspired detection theory** for residual modeling
- **Neyman-Pearson constraints** for explicit false positive budgets
- **Bayesian fault diagnosis** with belief states (not multiclass classification)
- **Sequential change detection** (CUSUM/GLR) for persistence validation
- **Multi-agent collaboration** via CrewAI framework
- **Hierarchical modeling** with per-unit equipment fingerprints

## Project Structure

```
predictive_maintenance/
├── core/                           # Core schemas and data models
│   ├── __init__.py
│   └── schemas.py                  # Enums, data classes, type definitions
│
├── services/                       # Analytical services
│   ├── __init__.py
│   ├── regime_service.py           # Operating regime classification
│   ├── sensor_trust_service.py     # Sensor data quality assessment
│   ├── behavior_service.py         # Behavioral prediction modeling
│   ├── residual_service.py         # Residual error distribution modeling
│   ├── change_detection_service.py # CUSUM/GLR sequential change detection
│   ├── fault_hypothesis_service.py # Bayesian fault diagnosis
│   ├── decision_policy_service.py  # FA budget enforcement & alerting
│   └── fingerprint_service.py      # Equipment fingerprinting
│
├── agents/                         # Multi-agent system (CrewAI)
│   ├── __init__.py
│   ├── crewai_base.py              # CrewAI base classes and utilities
│   ├── model_agents.py             # Specialized model agents per layer
│   ├── orchestrator.py             # Agent coordination and lifecycle
│   ├── protocols.py                # Agent communication protocols
│   └── workflow.py                 # Collaborative decision workflow
│
├── integration/                    # Integration layer
│   ├── __init__.py
│   ├── advanced_system.py          # Integrated PDM system
│   ├── integrated_system.py        # Full system with lifecycle mgmt
│   ├── lifecycle.py                # Model registry, A/B testing, retraining
│   └── event_bus.py                # Redis event-driven communication
│
└── tests/                          # Test suite
```

## Key Concepts

### Three-Layer Inference
1. **Layer 1 - Sensor Trust**: "Do I trust this sensor stream right now?"
2. **Layer 2 - Behavioral Deviation**: "Is equipment behaving differently than expected?"
3. **Layer 3 - Fault Hypothesis**: "What fault best explains the deviation?"

### Multi-Agent Architecture

| Layer | Agent | Responsibility |
|-------|-------|----------------|
| 0 | RegimeDetectionAgent | Classify operating regime |
| 1 | SensorTrustAgent | Evaluate data trustworthiness |
| 2 | BehaviorModelAgent | Predict expected behavior |
| 2 | ChangeDetectionAgent | Detect persistent changes |
| 3 | FaultHypothesisAgent | Bayesian fault diagnosis |
| 4 | DecisionPolicyAgent | Enforce FA budget, aggregate votes |

### Collaborative Decision Making
- Agents vote on maintenance decisions with weighted expertise
- Consensus threshold configurable (default 60%)
- Sensor trust agent has veto power on data quality issues
- Full audit trail for governance

## Quick Start

```python
from predictive_maintenance import create_pdm_system
from predictive_maintenance.core import TelemetrySnapshot
from datetime import datetime

# Create PDM system for a site
pdm = create_pdm_system("site_001")

# Process telemetry
telemetry = TelemetrySnapshot(
    timestamp=datetime.utcnow(),
    asset_id="RTU_001",
    compressor_on=True,
    compressor_current=15.2,
    suction_pressure=68.0,
    discharge_pressure=275.0,
    supply_air_temp=55.0,
    return_air_temp=75.0,
    ambient_temp=95.0,
)

# Run collaborative decision workflow
result = pdm.process(telemetry)

# Check the decision
print(f"Decision: {result.final_decision}")
print(f"Confidence: {result.confidence:.0%}")
print(f"Fault Hypothesis: {result.fault_hypothesis}")
```

## Configuration

### False Positive Budget
```python
from predictive_maintenance.core import FalsePositiveBudget

budget = FalsePositiveBudget(
    max_actionable_alarms_per_unit_per_month=0.3,
    max_no_issue_found_rate=0.05,  # ≤5% truck rolls find nothing
    min_confidence_for_actionable=0.85,
    max_false_alarm_probability=0.02,
)
```

### Orchestrator Configuration
```python
from predictive_maintenance.agents import OrchestratorConfig

config = OrchestratorConfig(
    consensus_threshold=0.6,
    alert_confidence_threshold=0.7,
    dispatch_confidence_threshold=0.85,
    max_alerts_per_day=10,
    max_dispatches_per_week=3,
)
```

## Dependencies

- Python 3.9+
- NumPy
- SciPy
- Redis (for event bus)
- CrewAI (optional, for advanced multi-agent features)

## Separation from RMN

This project is completely separate from the RMN (Retail Media Network) project:

| Aspect | PDM Project | RMN Project |
|--------|-------------|-------------|
| Location | `/predictive_maintenance/` | `/federated_demand_twin/` |
| Domain | HVAC/R equipment maintenance | Retail media & demand forecasting |
| Focus | Fault detection & diagnosis | Campaign optimization & forecasting |
| Models | Physics-based + ML hybrid | Bayesian demand models |

## License

Proprietary - Internal Use Only

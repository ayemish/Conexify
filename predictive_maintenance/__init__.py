"""
Predictive Maintenance (PDM) Project

A comprehensive predictive maintenance system for HVAC/R equipment using:
- Advanced signal processing (radar detection theory for residuals)
- Bayesian fault diagnosis with belief states
- Sequential change detection (CUSUM/GLR)
- Multi-agent collaboration via CrewAI
- Explicit false positive budget management

Project Structure:
==================

predictive_maintenance/
├── core/                    # Core PDM schemas and utilities
│   ├── schemas.py          # Data models and enums
│   └── utils.py            # Shared utilities
├── services/               # PDM analytical services
│   ├── regime_service.py   # Operating regime classification
│   ├── sensor_trust_service.py  # Sensor data quality
│   ├── behavior_service.py     # Behavioral prediction
│   ├── residual_service.py     # Residual error modeling
│   ├── change_detection_service.py  # CUSUM/GLR change detection
│   ├── fault_hypothesis_service.py  # Bayesian fault diagnosis
│   ├── decision_policy_service.py   # FA budget enforcement
│   └── fingerprint_service.py       # Equipment fingerprinting
├── agents/                 # CrewAI multi-agent system
│   ├── model_agents.py     # Specialized model agents
│   ├── orchestrator.py     # Agent coordination
│   ├── protocols.py        # Agent communication protocols
│   └── workflow.py         # Collaborative decision workflow
├── integration/            # Integration layer
│   ├── advanced_system.py  # Integrated PDM system
│   ├── lifecycle.py        # Model lifecycle management
│   └── event_bus.py        # Event-driven communication
├── api/                    # API layer
│   └── routes.py           # REST API endpoints
└── tests/                  # Test suite
"""

__version__ = "1.0.0"
__project__ = "Predictive Maintenance"

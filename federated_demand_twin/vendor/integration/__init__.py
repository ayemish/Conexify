"""
Integration Module

Connects all components of the Federated Demand Twin:
1. Federated Learning → NBEATS demand forecasting
2. Endogenous state tracking → Forecast covariates
3. Bayesian inference → Inventory/procurement probabilities
4. Digital Twin → Scenario simulation
"""

from .twin_bayesian_connector import (
    TwinBayesianConnector,
    ScenarioInformedBayesianEngine,
    IntegrationConfig,
    create_twin_bayesian_connector,
    create_scenario_informed_engine
)

from .unified_pipeline import (
    # Product configuration
    ProductLevel,
    ProductConfig,
    SupplierConfig,
    
    # Endogenous bridge
    EndogenousState,
    EndogenousBridge,
    
    # Procurement
    ProcurementScenario,
    ProcurementProbabilityEngine,
    
    # Product-level Bayesian
    ProductPosterior,
    ProductBayesianEngine,
    
    # Unified pipeline
    UnifiedPipeline,
    create_unified_pipeline,
    create_product_config,
    create_supplier_config
)

from .fl_nbeats_integration import (
    # Configuration
    FLNBEATSConfig,
    
    # Models
    BayesianNBEATSBlock,
    FederatedNBEATSModel,
    
    # FL components
    FLNBEATSClient,
    FLNBEATSServer,
    
    # Integrated forecaster
    FLIntegratedForecaster,
    
    # Factory functions
    create_fl_nbeats_config,
    create_fl_nbeats_client,
    create_fl_nbeats_server,
    create_fl_integrated_forecaster
)

from .orchestrator import (
    OrchestratorConfig,
    IntegrationOrchestrator,
    create_orchestrator
)

__all__ = [
    # Twin-Bayesian connector
    'TwinBayesianConnector',
    'ScenarioInformedBayesianEngine',
    'IntegrationConfig',
    'create_twin_bayesian_connector',
    'create_scenario_informed_engine',
    
    # Unified pipeline
    'ProductLevel',
    'ProductConfig',
    'SupplierConfig',
    'EndogenousState',
    'EndogenousBridge',
    'ProcurementScenario',
    'ProcurementProbabilityEngine',
    'ProductPosterior',
    'ProductBayesianEngine',
    'UnifiedPipeline',
    'create_unified_pipeline',
    'create_product_config',
    'create_supplier_config',
    
    # FL-NBEATS integration
    'FLNBEATSConfig',
    'BayesianNBEATSBlock',
    'FederatedNBEATSModel',
    'FLNBEATSClient',
    'FLNBEATSServer',
    'FLIntegratedForecaster',
    'create_fl_nbeats_config',
    'create_fl_nbeats_client',
    'create_fl_nbeats_server',
    'create_fl_integrated_forecaster',
    
    # Orchestrator
    'OrchestratorConfig',
    'IntegrationOrchestrator',
    'create_orchestrator'
]

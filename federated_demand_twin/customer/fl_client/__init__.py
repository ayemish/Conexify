"""
Federated Learning Client Module

Provides demand forecasting models for federated learning:
- DemandForecastModel: Base NBEATS-inspired model
- ExtendedDemandForecastModel: Extended model with endogenous support
- FederatedDemandModel: FL wrapper
- IntegratedDemandForecaster: Full integration with Bayesian layers
- NBEATSx: Full N-BEATSx with interpretable basis functions
- FoundationModelWrapper: Wrapper for TimesFM/Chronos/Moirai
- SLOTH: Hierarchical coherence training
"""

from .demand_model import (
    ModelConfig,
    ResidualBlock,
    NBEATSBlock,
    QuantileHead,
    DemandForecastModel,
    QuantileLoss,
    FederatedDemandModel,
    create_model
)

from .extended_demand_model import (
    ExtendedModelConfig,
    BayesianLinear,
    ExtendedNBEATSBlock,
    EndogenousCovariateEncoder,
    ExtendedDemandForecastModel,
    IntegratedDemandForecaster,
    create_extended_config,
    create_integrated_forecaster
)

from .nbeatsx import (
    NBEATSxConfig,
    BlockType,
    TrendBasis,
    SeasonalityBasis,
    GenericBasis,
    NBEATSxBlock,
    NBEATSxStack,
    NBEATSx,
    NBEATSxLoss,
    FederatedNBEATSx,
    create_nbeatsx
)

from .foundation_models import (
    FoundationModelConfig,
    BaseFoundationModel,
    ChronosWrapper,
    TimesFMWrapper,
    MoiraiWrapper,
    FoundationModelWrapper,
    FoundationModelEnsemble,
    create_foundation_model
)

from .sloth import (
    SLOTHConfig,
    HierarchyStructure,
    CoherenceLoss,
    ProbabilisticCoherenceLoss,
    SLOTHLoss,
    PinballLoss,
    HierarchicalModel,
    SLOTHWrapper,
    SLOTHTrainer,
    create_sloth_trainer
)

__all__ = [
    # Base model
    'ModelConfig',
    'ResidualBlock',
    'NBEATSBlock',
    'QuantileHead',
    'DemandForecastModel',
    'QuantileLoss',
    'FederatedDemandModel',
    'create_model',
    
    # Extended model
    'ExtendedModelConfig',
    'BayesianLinear',
    'ExtendedNBEATSBlock',
    'EndogenousCovariateEncoder',
    'ExtendedDemandForecastModel',
    'IntegratedDemandForecaster',
    'create_extended_config',
    'create_integrated_forecaster',
    
    # N-BEATSx
    'NBEATSxConfig',
    'BlockType',
    'TrendBasis',
    'SeasonalityBasis',
    'GenericBasis',
    'NBEATSxBlock',
    'NBEATSxStack',
    'NBEATSx',
    'NBEATSxLoss',
    'FederatedNBEATSx',
    'create_nbeatsx',
    
    # Foundation Models
    'FoundationModelConfig',
    'BaseFoundationModel',
    'ChronosWrapper',
    'TimesFMWrapper',
    'MoiraiWrapper',
    'FoundationModelWrapper',
    'FoundationModelEnsemble',
    'create_foundation_model',
    
    # SLOTH
    'SLOTHConfig',
    'HierarchyStructure',
    'CoherenceLoss',
    'ProbabilisticCoherenceLoss',
    'SLOTHLoss',
    'PinballLoss',
    'HierarchicalModel',
    'SLOTHWrapper',
    'SLOTHTrainer',
    'create_sloth_trainer'
]

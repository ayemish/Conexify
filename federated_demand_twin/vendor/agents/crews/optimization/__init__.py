"""
Retail Media Optimization Crews

Multi-level CrewAI agent teams for retail media spend optimization across:
- Brand level
- Retail Media Network (RMN) level  
- Campaign and Message level
- Channel level

Plus scenario-oriented crews for objective-based optimization:
- INCREASE_REVENUE
- INCREASE_MARGIN
- MAINTAIN_REVENUE
- REDUCE_COST
"""

from .schemas import (
    DesiredOutcome,
    OptimizationConstraints,
    CrewConfig,
    ScenarioConfig,
    OptimizationResult,
    CrewOutput,
)

from .base_crew import BaseOptimizationCrew
from .brand_crew import BrandOptimizationCrew
from .rmn_crew import RMNOptimizationCrew
from .campaign_crew import CampaignMessageOptimizationCrew
from .channel_crew import ChannelOptimizationCrew
from .scenario_crews import (
    ScenarioOrchestratorCrew,
    IncreaseRevenueCrew,
    IncreaseMarginCrew,
    MaintainRevenueCrew,
    ReduceCostCrew,
)

__all__ = [
    # Enums and schemas
    "DesiredOutcome",
    "OptimizationConstraints",
    "CrewConfig",
    "ScenarioConfig",
    "OptimizationResult",
    "CrewOutput",
    # Level crews
    "BaseOptimizationCrew",
    "BrandOptimizationCrew",
    "RMNOptimizationCrew",
    "CampaignMessageOptimizationCrew",
    "ChannelOptimizationCrew",
    # Scenario crews
    "ScenarioOrchestratorCrew",
    "IncreaseRevenueCrew",
    "IncreaseMarginCrew",
    "MaintainRevenueCrew",
    "ReduceCostCrew",
]

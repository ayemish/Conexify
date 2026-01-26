"""
RMN (Retail Media Network) Optimization - Orchestrator

Coordinates the complete RMN optimization workflow.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import hashlib
import numpy as np

from ...crewai_base import AgentRegistry, AgentMessageBus

from .schemas import (
    RMNConfig,
    ChannelConfig,
    ChannelType,
    MediaSpendData,
    RMNDecisionPack,
)

from .agents import (
    RMNDataIngestionAgent,
    RMNAttributionAgent,
    RMNElasticityAgent,
    RMNScenarioAgent,
    RMNTwinAgent,
    RMNOptimizerAgent,
    RMNGovernanceAgent,
    RMNRationaleAgent,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RMNOrchestrator:
    """
    Orchestrates the RMN optimization workflow.
    
    Pipeline: Data → Attribution → Elasticity → Scenarios → Simulation → Optimize → Govern → Explain
    """
    
    def __init__(self, config: RMNConfig):
        self.config = config
        self.registry = AgentRegistry.get_instance()
        self.message_bus = self.registry.message_bus
        
        self._initialize_agents()
        
        self.run_history: List[RMNDecisionPack] = []
        logger.info(f"RMNOrchestrator initialized for {config.retailer_name}")
    
    def _initialize_agents(self):
        """Initialize all RMN agents"""
        channels = self.config.channels
        rid = self.config.retailer_id
        
        self.data_agent = RMNDataIngestionAgent(rid, channels, self.message_bus)
        self.attribution_agent = RMNAttributionAgent(rid, channels, self.message_bus)
        self.elasticity_agent = RMNElasticityAgent(rid, channels, self.message_bus)
        self.scenario_agent = RMNScenarioAgent(rid, channels, self.message_bus)
        self.twin_agent = RMNTwinAgent(rid, self.message_bus)
        self.optimizer_agent = RMNOptimizerAgent(rid, self.message_bus)
        self.governance_agent = RMNGovernanceAgent(rid, self.config, self.message_bus)
        self.rationale_agent = RMNRationaleAgent(rid, self.message_bus)
        
        # Register agents
        for agent in [
            self.data_agent, self.attribution_agent, self.elasticity_agent,
            self.scenario_agent, self.twin_agent, self.optimizer_agent,
            self.governance_agent, self.rationale_agent
        ]:
            self.registry.register(agent)
        
        logger.info(f"Initialized 8 RMN agents")
    
    def run(
        self,
        spend_data: List[MediaSpendData],
        conversion_paths: List[List[str]],
        current_allocation: Dict[str, float],
        base_revenue: float = 1000000,
    ) -> RMNDecisionPack:
        """
        Run the complete RMN optimization workflow.
        
        Args:
            spend_data: Historical spend and performance data
            conversion_paths: Customer conversion paths for attribution
            current_allocation: Current channel allocation
            base_revenue: Base revenue for simulation
        
        Returns:
            RMNDecisionPack with recommendations
        """
        run_id = hashlib.md5(
            f"{datetime.utcnow().isoformat()}_{self.config.retailer_id}".encode()
        ).hexdigest()[:12]
        
        logger.info(f"Starting RMN optimization run {run_id}")
        
        # 1. Data Validation
        logger.info("Step 1: Data validation")
        validation = self.data_agent.validate_data(spend_data)
        if not validation["valid"]:
            logger.warning(f"Data validation issues: {validation['issues']}")
        
        # 2. Attribution
        logger.info("Step 2: Attribution analysis")
        total_revenue = sum(d.revenue for d in spend_data)
        total_conversions = sum(d.conversions for d in spend_data)
        attribution = self.attribution_agent.compute_attribution(
            conversion_paths, total_revenue, total_conversions
        )
        
        # 3. Elasticity Estimation
        logger.info("Step 3: Elasticity estimation")
        channel_data: Dict[str, Dict[str, List]] = {}
        for record in spend_data:
            if record.channel_id not in channel_data:
                channel_data[record.channel_id] = {"spend": [], "revenue": []}
            channel_data[record.channel_id]["spend"].append(record.spend)
            channel_data[record.channel_id]["revenue"].append(record.revenue)
        
        for channel_id, data in channel_data.items():
            if len(data["spend"]) >= 10:
                self.elasticity_agent.estimate_elasticity(
                    channel_id,
                    np.array(data["spend"]),
                    np.array(data["revenue"])
                )
        
        elasticities = self.elasticity_agent.get_all_posteriors()
        
        # 4. Scenario Generation
        logger.info("Step 4: Scenario generation")
        scenarios = self.scenario_agent.generate_scenarios(
            current_allocation,
            self.config.total_budget,
            elasticities,
            n_scenarios=self.config.n_scenarios
        )
        
        # 5. Simulation
        logger.info("Step 5: Digital Twin simulation")
        simulations = {}
        for scenario in scenarios:
            sim_result = self.twin_agent.simulate(
                scenario,
                elasticities,
                base_revenue=base_revenue,
                n_simulations=self.config.n_simulations
            )
            simulations[scenario.scenario_id] = sim_result
        
        # 6. Optimization
        logger.info("Step 6: Optimization")
        optimization = self.optimizer_agent.optimize(
            simulations,
            risk_aversion=self.config.risk_aversion
        )
        
        # 7. Governance
        logger.info("Step 7: Governance validation")
        governance = self.governance_agent.validate(optimization, current_allocation)
        
        # 8. Rationale
        logger.info("Step 8: Rationale generation")
        rationale = self.rationale_agent.generate_rationale(
            optimization, simulations, governance, elasticities
        )
        
        # Build decision pack
        decision_pack = RMNDecisionPack(
            pack_id=run_id,
            retailer_id=self.config.retailer_id,
            created_at=datetime.utcnow(),
            attribution=attribution,
            elasticities=elasticities,
            scenarios=scenarios,
            simulations=simulations,
            optimization=optimization,
            governance=governance,
            executive_summary=rationale["executive_summary"],
            detailed_rationale=rationale["detailed_rationale"],
            uncertainty_acknowledgment=rationale["uncertainty_acknowledgment"],
            status="completed" if governance.approved else "pending_review",
            confidence_score=0.8 if governance.approved else 0.5,
        )
        
        self.run_history.append(decision_pack)
        logger.info(f"RMN optimization complete: {decision_pack.status}")
        
        return decision_pack
    
    def get_agent_summary(self) -> Dict[str, Any]:
        """Get summary of RMN agents"""
        return {
            "ecosystem": "RMN Optimization",
            "retailer_id": self.config.retailer_id,
            "n_channels": len(self.config.channels),
            "agents": [
                "DataIngestion", "Attribution", "Elasticity", "Scenario",
                "Twin", "Optimizer", "Governance", "Rationale"
            ],
        }


def create_rmn_orchestrator(
    retailer_id: str,
    retailer_name: str,
    channels: Optional[List[Dict[str, Any]]] = None,
    **kwargs
) -> RMNOrchestrator:
    """Factory function for RMN orchestrator"""
    
    # Default channels if not provided
    if channels is None:
        channels = [
            {"channel_id": "sponsored_search", "channel_type": ChannelType.SPONSORED_SEARCH, "name": "Sponsored Search"},
            {"channel_id": "sponsored_product", "channel_type": ChannelType.SPONSORED_PRODUCT, "name": "Sponsored Product"},
            {"channel_id": "display", "channel_type": ChannelType.DISPLAY, "name": "Display Ads"},
            {"channel_id": "video", "channel_type": ChannelType.VIDEO, "name": "Video"},
            {"channel_id": "email", "channel_type": ChannelType.EMAIL, "name": "Email"},
        ]
    
    channel_configs = [
        ChannelConfig(
            channel_id=c.get("channel_id", f"channel_{i}"),
            channel_type=c.get("channel_type", ChannelType.DISPLAY),
            name=c.get("name", f"Channel {i}"),
            min_spend=c.get("min_spend", 0),
            max_spend=c.get("max_spend", float('inf')),
            prior_elasticity_mean=c.get("prior_elasticity_mean", 0.15),
            prior_elasticity_std=c.get("prior_elasticity_std", 0.05),
        )
        for i, c in enumerate(channels)
    ]
    
    config = RMNConfig(
        retailer_id=retailer_id,
        retailer_name=retailer_name,
        channels=channel_configs,
        **kwargs
    )
    
    return RMNOrchestrator(config)

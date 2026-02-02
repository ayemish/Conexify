"""
Unified Twin Manager

Central manager that integrates:
- TwinStateStore for persistence
- RetailMediaTwin for simulation
- CSV Ingestion for data loading
- Event subscriptions for real-time updates
- Bayesian integration for posteriors
"""

import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.schemas.channel_state_contracts import (
    RMNTwinState,
    BrandTwinState,
    CampaignTwinState,
    ChannelTwinState,
    TwinType,
    TwinStateEvent,
    TwinEventType,
    PacingStatus,
)
from vendor.retail_media.twin_state_store import (
    TwinStateStore,
    TwinStateStoreConfig,
    get_twin_state_store,
)
from vendor.retail_media.csv_ingestion import CSVIngestionService, IngestionResult
from vendor.retail_media.media_twin import RetailMediaTwin, TwinConfig
from vendor.retail_media.schemas import (
    MediaChannel,
    ChannelDigitalTwinState,
    ElasticityPosterior,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class UnifiedTwinConfig:
    """Configuration for unified twin manager"""
    # State store config
    state_dir: str = "./data/twin_states"
    history_dir: str = "./data/twin_history"
    max_history_per_twin: int = 100
    
    # Simulation config
    default_num_simulations: int = 1000
    default_simulation_weeks: int = 13
    
    # Event config
    emit_events: bool = True
    
    # Auto-sync
    auto_sync_to_simulation: bool = True


class UnifiedTwinManager:
    """
    Unified manager for all digital twin operations.
    
    Provides:
    - Centralized access to all twin types (RMN, Brand, Campaign, Channel)
    - CSV ingestion with automatic state store updates
    - Simulation engine integration
    - Event subscriptions for real-time updates
    - Bayesian posterior integration
    """
    
    def __init__(self, config: Optional[UnifiedTwinConfig] = None):
        self.config = config or UnifiedTwinConfig()
        
        # Initialize state store
        store_config = TwinStateStoreConfig(
            state_dir=self.config.state_dir,
            history_dir=self.config.history_dir,
            max_history_per_twin=self.config.max_history_per_twin,
            emit_events=self.config.emit_events,
        )
        self.state_store = TwinStateStore(store_config)
        
        # Initialize ingestion service
        self.ingestion_service = CSVIngestionService(self.state_store)
        
        # Initialize simulation twin
        twin_config = TwinConfig(
            default_num_simulations=self.config.default_num_simulations,
            default_simulation_weeks=self.config.default_simulation_weeks,
        )
        self.simulation_twin = RetailMediaTwin(twin_config)
        
        # Event handlers for syncing
        if self.config.auto_sync_to_simulation:
            self._setup_sync_handlers()
        
        logger.info("UnifiedTwinManager initialized")
    
    def _setup_sync_handlers(self):
        """Setup event handlers to sync state changes to simulation"""
        # Subscribe to channel state updates
        self.state_store.subscribe(
            TwinEventType.STATE_UPDATED,
            self._on_channel_state_updated,
            twin_type=TwinType.CHANNEL,
        )
    
    def _on_channel_state_updated(self, event: TwinStateEvent):
        """Handle channel state update by syncing to simulation twin"""
        if event.twin_type != TwinType.CHANNEL:
            return
        
        try:
            # Get the updated state
            state = self.state_store.get_state(event.twin_id, TwinType.CHANNEL)
            if state:
                # Sync to simulation twin
                self._sync_channel_to_simulation(state)
        except Exception as e:
            logger.error(f"Error syncing channel state to simulation: {e}")
    
    def _sync_channel_to_simulation(self, channel_state: ChannelTwinState):
        """Sync channel twin state to simulation twin"""
        # Convert to simulation format
        try:
            channel_type_val = channel_state.channel_type.value if hasattr(channel_state.channel_type, 'value') else channel_state.channel_type
            channel_type = MediaChannel(channel_type_val)
        except ValueError:
            channel_type = MediaChannel.SPONSORED_PRODUCTS
        
        # Create ChannelDigitalTwinState for simulation
        sim_state = ChannelDigitalTwinState(
            channel=channel_type,
            retailer_id=channel_state.retailer_id,
            week=channel_state.week,
            impressions=channel_state.impressions,
            clicks=channel_state.clicks,
            conversions=channel_state.conversions,
            spend=channel_state.spend,
            click_through_rate=channel_state.ctr,
            conversion_rate=channel_state.cvr,
            cost_per_click=channel_state.cpc,
            cost_per_acquisition=channel_state.cpa,
            attributed_revenue=channel_state.revenue,
            roas=channel_state.roas,
            cumulative_adstock=channel_state.cumulative_adstock,
            adstock_decay_rate=channel_state.adstock_decay_rate,
            audience_reach=channel_state.audience_reach,
            frequency=channel_state.frequency,
            elasticity_mean=channel_state.elasticity_mean,
            elasticity_std=channel_state.elasticity_std,
            budget_utilization=channel_state.budget_utilization_pct,
            pacing_status=channel_state.pacing_status.value if hasattr(channel_state.pacing_status, 'value') else channel_state.pacing_status,
        )
        
        logger.debug(f"Synced channel {channel_state.twin_id} to simulation twin")
    
    # =========================================================================
    # CSV Ingestion
    # =========================================================================
    
    def ingest_rmn_csv(
        self,
        file_path: str,
        retailer_id: str,
        column_mapping: Optional[Dict[str, str]] = None
    ) -> IngestionResult:
        """Ingest RMN data from CSV"""
        return self.ingestion_service.ingest_rmn_csv(file_path, retailer_id, column_mapping)
    
    def ingest_brand_csv(
        self,
        file_path: str,
        retailer_id: str,
        column_mapping: Optional[Dict[str, str]] = None
    ) -> IngestionResult:
        """Ingest Brand data from CSV"""
        return self.ingestion_service.ingest_brand_csv(file_path, retailer_id, column_mapping)
    
    def ingest_campaign_csv(
        self,
        file_path: str,
        retailer_id: str,
        column_mapping: Optional[Dict[str, str]] = None
    ) -> IngestionResult:
        """Ingest Campaign data from CSV"""
        return self.ingestion_service.ingest_campaign_csv(file_path, retailer_id, column_mapping)
    
    def ingest_channel_csv(
        self,
        file_path: str,
        retailer_id: str,
        column_mapping: Optional[Dict[str, str]] = None
    ) -> IngestionResult:
        """Ingest Channel data from CSV"""
        return self.ingestion_service.ingest_channel_csv(file_path, retailer_id, column_mapping)
    
    def ingest_all_csvs(
        self,
        directory: str,
        retailer_id: str
    ) -> Dict[str, IngestionResult]:
        """
        Ingest all CSV files from a directory.
        
        Expected files:
        - rmn.csv or rmn_*.csv
        - brands.csv or brand_*.csv
        - campaigns.csv or campaign_*.csv
        - channels.csv or channel_*.csv
        """
        results = {}
        dir_path = Path(directory)
        
        # RMN files
        for f in dir_path.glob("rmn*.csv"):
            results[f.name] = self.ingest_rmn_csv(str(f), retailer_id)
        
        # Brand files
        for f in dir_path.glob("brand*.csv"):
            results[f.name] = self.ingest_brand_csv(str(f), retailer_id)
        
        # Campaign files
        for f in dir_path.glob("campaign*.csv"):
            results[f.name] = self.ingest_campaign_csv(str(f), retailer_id)
        
        # Channel files
        for f in dir_path.glob("channel*.csv"):
            results[f.name] = self.ingest_channel_csv(str(f), retailer_id)
        
        return results
    
    # =========================================================================
    # State Access
    # =========================================================================
    
    def get_rmn_state(self, retailer_id: str) -> Optional[RMNTwinState]:
        """Get RMN state for a retailer"""
        twin_id = f"rmn_{retailer_id}"
        return self.state_store.get_state(twin_id, TwinType.RMN)
    
    def get_brand_state(self, retailer_id: str, brand_id: str) -> Optional[BrandTwinState]:
        """Get Brand state"""
        twin_id = f"brand_{retailer_id}_{brand_id}"
        return self.state_store.get_state(twin_id, TwinType.BRAND)
    
    def get_campaign_state(self, retailer_id: str, campaign_id: str) -> Optional[CampaignTwinState]:
        """Get Campaign state"""
        twin_id = f"campaign_{retailer_id}_{campaign_id}"
        return self.state_store.get_state(twin_id, TwinType.CAMPAIGN)
    
    def get_channel_state(self, retailer_id: str, channel_type: str) -> Optional[ChannelTwinState]:
        """Get Channel state"""
        twin_id = f"channel_{retailer_id}_{channel_type}"
        return self.state_store.get_state(twin_id, TwinType.CHANNEL)
    
    def get_all_rmn_states(self) -> List[RMNTwinState]:
        """Get all RMN states"""
        return self.state_store.get_rmn_states()
    
    def get_all_brand_states(self, retailer_id: Optional[str] = None) -> List[BrandTwinState]:
        """Get all Brand states"""
        return self.state_store.get_brand_states(retailer_id)
    
    def get_all_campaign_states(self, retailer_id: Optional[str] = None) -> List[CampaignTwinState]:
        """Get all Campaign states"""
        return self.state_store.get_campaign_states(retailer_id)
    
    def get_all_channel_states(self, retailer_id: Optional[str] = None) -> List[ChannelTwinState]:
        """Get all Channel states"""
        return self.state_store.get_channel_states(retailer_id)
    
    # =========================================================================
    # History Access
    # =========================================================================
    
    def get_rmn_history(self, retailer_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get RMN state history"""
        twin_id = f"rmn_{retailer_id}"
        records = self.state_store.get_history(twin_id, TwinType.RMN, limit)
        return [r.dict() for r in records]
    
    def get_brand_history(self, retailer_id: str, brand_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get Brand state history"""
        twin_id = f"brand_{retailer_id}_{brand_id}"
        records = self.state_store.get_history(twin_id, TwinType.BRAND, limit)
        return [r.dict() for r in records]
    
    def get_campaign_history(self, retailer_id: str, campaign_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get Campaign state history"""
        twin_id = f"campaign_{retailer_id}_{campaign_id}"
        records = self.state_store.get_history(twin_id, TwinType.CAMPAIGN, limit)
        return [r.dict() for r in records]
    
    def get_channel_history(self, retailer_id: str, channel_type: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get Channel state history"""
        twin_id = f"channel_{retailer_id}_{channel_type}"
        records = self.state_store.get_history(twin_id, TwinType.CHANNEL, limit)
        return [r.dict() for r in records]
    
    # =========================================================================
    # Event Subscriptions
    # =========================================================================
    
    def subscribe(
        self,
        event_type: TwinEventType,
        callback: Callable[[TwinStateEvent], None],
        twin_type: Optional[TwinType] = None,
        retailer_id: Optional[str] = None
    ) -> str:
        """Subscribe to twin state events"""
        return self.state_store.subscribe(event_type, callback, twin_type, retailer_id)
    
    def unsubscribe(self, subscription_key: str, callback: Callable):
        """Unsubscribe from events"""
        self.state_store.unsubscribe(subscription_key, callback)
    
    # =========================================================================
    # Bayesian Integration
    # =========================================================================
    
    def update_channel_posteriors(
        self,
        retailer_id: str,
        channel_type: str,
        elasticity_mean: float,
        elasticity_std: float,
        elasticity_ci_lower: float,
        elasticity_ci_upper: float,
        prob_efficiency_above_target: float = 0.5,
        contribution_pct: float = 0.0,
    ):
        """Update channel state with Bayesian posteriors"""
        state = self.get_channel_state(retailer_id, channel_type)
        if not state:
            logger.warning(f"Channel state not found: {retailer_id}/{channel_type}")
            return
        
        # Update posteriors
        state.elasticity_mean = elasticity_mean
        state.elasticity_std = elasticity_std
        state.elasticity_ci_lower = elasticity_ci_lower
        state.elasticity_ci_upper = elasticity_ci_upper
        state.prob_efficiency_above_target = prob_efficiency_above_target
        state.contribution_pct = contribution_pct
        
        # Save updated state
        self.state_store.update_state(state, change_reason="Bayesian posterior update")
    
    def update_brand_posteriors(
        self,
        retailer_id: str,
        brand_id: str,
        incremental_sales_mean: float,
        incremental_sales_std: float,
        incremental_sales_ci_lower: float,
        incremental_sales_ci_upper: float,
        efficiency_mean: float,
        efficiency_std: float,
        lift_vs_prior_period: float,
        prob_positive_lift: float,
    ):
        """Update brand state with Bayesian posteriors"""
        state = self.get_brand_state(retailer_id, brand_id)
        if not state:
            logger.warning(f"Brand state not found: {retailer_id}/{brand_id}")
            return
        
        # Update posteriors
        state.incremental_sales_mean = incremental_sales_mean
        state.incremental_sales_std = incremental_sales_std
        state.incremental_sales_ci_lower = incremental_sales_ci_lower
        state.incremental_sales_ci_upper = incremental_sales_ci_upper
        state.efficiency_mean = efficiency_mean
        state.efficiency_std = efficiency_std
        state.lift_vs_prior_period = lift_vs_prior_period
        state.prob_positive_lift = prob_positive_lift
        
        # Save updated state
        self.state_store.update_state(state, change_reason="Bayesian posterior update")
    
    # =========================================================================
    # Aggregation
    # =========================================================================
    
    def compute_rmn_aggregates(self, retailer_id: str) -> Optional[RMNTwinState]:
        """
        Compute RMN aggregates from brand and channel states.
        Creates or updates RMN state based on child states.
        """
        brands = self.get_all_brand_states(retailer_id)
        channels = self.get_all_channel_states(retailer_id)
        
        if not brands and not channels:
            return None
        
        # Aggregate from brands
        total_impressions = sum(b.impressions for b in brands)
        total_clicks = sum(b.clicks for b in brands)
        total_conversions = sum(b.conversions for b in brands)
        total_spend = sum(b.spend for b in brands)
        total_revenue = sum(b.revenue for b in brands)
        total_budget = sum(b.budget for b in brands)
        
        # Get or create RMN state
        rmn_state = self.get_rmn_state(retailer_id)
        if not rmn_state:
            rmn_state = RMNTwinState(
                twin_id=f"rmn_{retailer_id}",
                retailer_id=retailer_id,
                rmn_name=retailer_id.replace('_', ' ').title(),
            )
        
        # Update aggregates
        rmn_state.total_impressions = total_impressions
        rmn_state.total_clicks = total_clicks
        rmn_state.total_conversions = total_conversions
        rmn_state.total_spend = total_spend
        rmn_state.total_revenue = total_revenue
        rmn_state.total_budget = total_budget
        
        rmn_state.overall_roas = total_revenue / total_spend if total_spend > 0 else 0
        rmn_state.overall_ctr = total_clicks / total_impressions if total_impressions > 0 else 0
        rmn_state.overall_cvr = total_conversions / total_clicks if total_clicks > 0 else 0
        
        rmn_state.active_brands = len(brands)
        rmn_state.active_channels = len(channels)
        
        rmn_state.budget_utilized = total_spend
        rmn_state.budget_utilization_pct = total_spend / total_budget if total_budget > 0 else 0
        
        # Compute channel mix
        if channels:
            total_channel_spend = sum(c.spend for c in channels)
            if total_channel_spend > 0:
                rmn_state.channel_mix = {
                    (c.channel_type.value if hasattr(c.channel_type, 'value') else c.channel_type): c.spend / total_channel_spend
                    for c in channels
                }
        
        # Compute pacing status
        if rmn_state.budget_utilization_pct < 0.8:
            rmn_state.pacing_status = PacingStatus.UNDER_PACING
        elif rmn_state.budget_utilization_pct > 1.1:
            rmn_state.pacing_status = PacingStatus.OVER_PACING
        else:
            rmn_state.pacing_status = PacingStatus.ON_TRACK
        
        # Save
        self.state_store.update_state(rmn_state, change_reason="Aggregate recomputation")
        return rmn_state
    
    # =========================================================================
    # Summary
    # =========================================================================
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all twin states"""
        store_summary = self.state_store.get_summary()
        
        # Add per-retailer breakdown
        rmn_states = self.get_all_rmn_states()
        retailer_summary = {}
        for rmn in rmn_states:
            retailer_summary[rmn.retailer_id] = {
                "rmn_name": rmn.rmn_name,
                "total_spend": rmn.total_spend,
                "total_revenue": rmn.total_revenue,
                "active_brands": rmn.active_brands,
                "active_channels": rmn.active_channels,
                "pacing_status": rmn.pacing_status.value if hasattr(rmn.pacing_status, 'value') else rmn.pacing_status,
            }
        
        return {
            **store_summary,
            "retailers": retailer_summary,
        }
    
    def persist_all(self):
        """Persist all states to disk"""
        self.state_store.persist_all()


# Singleton instance
_manager_instance: Optional[UnifiedTwinManager] = None


def get_unified_twin_manager(config: Optional[UnifiedTwinConfig] = None) -> UnifiedTwinManager:
    """Get or create singleton manager instance"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = UnifiedTwinManager(config)
    return _manager_instance


def reset_unified_twin_manager():
    """Reset singleton instance (for testing)"""
    global _manager_instance
    _manager_instance = None

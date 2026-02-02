"""
Twin State Tool for CrewAI Agents

Provides agent access to digital twin states with:
- Query interface for all twin types
- Event subscriptions for real-time updates
- History access for trend analysis
- Bayesian posterior retrieval
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from shared.schemas.channel_state_contracts import (
    RMNTwinState,
    BrandTwinState,
    CampaignTwinState,
    ChannelTwinState,
    TwinType,
    TwinStateEvent,
    TwinEventType,
    ChannelType,
    PacingStatus,
)
from vendor.retail_media.unified_twin_manager import (
    UnifiedTwinManager,
    get_unified_twin_manager,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TwinStateTool:
    """
    CrewAI tool for accessing digital twin states.
    
    Provides agents with:
    - Current state queries
    - Historical state access
    - Event subscriptions
    - Aggregated metrics
    """
    
    name: str = "twin_state_tool"
    description: str = """
    Access digital twin states for retail media networks, brands, campaigns, and channels.
    
    Use this tool to:
    - Get current state of any twin (RMN, Brand, Campaign, Channel)
    - Query historical states for trend analysis
    - Subscribe to state change events
    - Get aggregated metrics across retailers
    
    Parameters:
    - action: One of 'get_state', 'get_history', 'get_all', 'get_metrics', 'subscribe'
    - twin_type: One of 'rmn', 'brand', 'campaign', 'channel'
    - retailer_id: Retailer identifier (required for most actions)
    - entity_id: Brand, campaign, or channel identifier (if applicable)
    """
    
    def __init__(self, manager: Optional[UnifiedTwinManager] = None):
        self.manager = manager or get_unified_twin_manager()
        self._subscriptions: Dict[str, Callable] = {}
    
    def run(
        self,
        action: str,
        twin_type: str,
        retailer_id: Optional[str] = None,
        entity_id: Optional[str] = None,
        limit: int = 50,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute tool action.
        
        Args:
            action: Action to perform
            twin_type: Type of twin
            retailer_id: Retailer identifier
            entity_id: Entity identifier (brand_id, campaign_id, channel_type)
            limit: Limit for history queries
            filters: Optional filters for queries
            
        Returns:
            Result dictionary
        """
        try:
            twin_type_enum = TwinType(twin_type.lower())
        except ValueError:
            return {"error": f"Invalid twin_type: {twin_type}"}
        
        if action == "get_state":
            return self._get_state(twin_type_enum, retailer_id, entity_id)
        elif action == "get_history":
            return self._get_history(twin_type_enum, retailer_id, entity_id, limit)
        elif action == "get_all":
            return self._get_all(twin_type_enum, retailer_id)
        elif action == "get_metrics":
            return self._get_metrics(twin_type_enum, retailer_id)
        elif action == "get_summary":
            return self._get_summary()
        else:
            return {"error": f"Unknown action: {action}"}
    
    # =========================================================================
    # State Queries
    # =========================================================================
    
    def _get_state(
        self,
        twin_type: TwinType,
        retailer_id: Optional[str],
        entity_id: Optional[str]
    ) -> Dict[str, Any]:
        """Get current state of a twin"""
        if not retailer_id:
            return {"error": "retailer_id is required"}
        
        state = None
        
        if twin_type == TwinType.RMN:
            state = self.manager.get_rmn_state(retailer_id)
        elif twin_type == TwinType.BRAND:
            if not entity_id:
                return {"error": "entity_id (brand_id) is required for brand twin"}
            state = self.manager.get_brand_state(retailer_id, entity_id)
        elif twin_type == TwinType.CAMPAIGN:
            if not entity_id:
                return {"error": "entity_id (campaign_id) is required for campaign twin"}
            state = self.manager.get_campaign_state(retailer_id, entity_id)
        elif twin_type == TwinType.CHANNEL:
            if not entity_id:
                return {"error": "entity_id (channel_type) is required for channel twin"}
            state = self.manager.get_channel_state(retailer_id, entity_id)
        
        if state:
            return {"success": True, "state": state.dict()}
        else:
            return {"success": False, "error": "State not found"}
    
    def _get_history(
        self,
        twin_type: TwinType,
        retailer_id: Optional[str],
        entity_id: Optional[str],
        limit: int
    ) -> Dict[str, Any]:
        """Get state history for a twin"""
        if not retailer_id:
            return {"error": "retailer_id is required"}
        
        history = []
        
        if twin_type == TwinType.RMN:
            history = self.manager.get_rmn_history(retailer_id, limit)
        elif twin_type == TwinType.BRAND:
            if not entity_id:
                return {"error": "entity_id (brand_id) is required"}
            history = self.manager.get_brand_history(retailer_id, entity_id, limit)
        elif twin_type == TwinType.CAMPAIGN:
            if not entity_id:
                return {"error": "entity_id (campaign_id) is required"}
            history = self.manager.get_campaign_history(retailer_id, entity_id, limit)
        elif twin_type == TwinType.CHANNEL:
            if not entity_id:
                return {"error": "entity_id (channel_type) is required"}
            history = self.manager.get_channel_history(retailer_id, entity_id, limit)
        
        return {"success": True, "history": history, "count": len(history)}
    
    def _get_all(
        self,
        twin_type: TwinType,
        retailer_id: Optional[str]
    ) -> Dict[str, Any]:
        """Get all states of a type"""
        states = []
        
        if twin_type == TwinType.RMN:
            states = self.manager.get_all_rmn_states()
        elif twin_type == TwinType.BRAND:
            states = self.manager.get_all_brand_states(retailer_id)
        elif twin_type == TwinType.CAMPAIGN:
            states = self.manager.get_all_campaign_states(retailer_id)
        elif twin_type == TwinType.CHANNEL:
            states = self.manager.get_all_channel_states(retailer_id)
        
        return {
            "success": True,
            "states": [s.dict() for s in states],
            "count": len(states),
        }
    
    def _get_metrics(
        self,
        twin_type: TwinType,
        retailer_id: Optional[str]
    ) -> Dict[str, Any]:
        """Get aggregated metrics for a twin type"""
        if twin_type == TwinType.RMN:
            states = self.manager.get_all_rmn_states()
            return self._aggregate_rmn_metrics(states)
        elif twin_type == TwinType.BRAND:
            states = self.manager.get_all_brand_states(retailer_id)
            return self._aggregate_brand_metrics(states)
        elif twin_type == TwinType.CAMPAIGN:
            states = self.manager.get_all_campaign_states(retailer_id)
            return self._aggregate_campaign_metrics(states)
        elif twin_type == TwinType.CHANNEL:
            states = self.manager.get_all_channel_states(retailer_id)
            return self._aggregate_channel_metrics(states)
        
        return {"error": "Unknown twin type"}
    
    def _get_summary(self) -> Dict[str, Any]:
        """Get overall summary"""
        return {"success": True, "summary": self.manager.get_summary()}
    
    # =========================================================================
    # Aggregation Helpers
    # =========================================================================
    
    def _aggregate_rmn_metrics(self, states: List[RMNTwinState]) -> Dict[str, Any]:
        """Aggregate metrics across RMNs"""
        if not states:
            return {"success": True, "metrics": {}, "count": 0}
        
        total_spend = sum(s.total_spend for s in states)
        total_revenue = sum(s.total_revenue for s in states)
        total_impressions = sum(s.total_impressions for s in states)
        total_clicks = sum(s.total_clicks for s in states)
        total_conversions = sum(s.total_conversions for s in states)
        
        return {
            "success": True,
            "metrics": {
                "total_rmns": len(states),
                "total_spend": total_spend,
                "total_revenue": total_revenue,
                "total_impressions": total_impressions,
                "total_clicks": total_clicks,
                "total_conversions": total_conversions,
                "overall_roas": total_revenue / total_spend if total_spend > 0 else 0,
                "overall_ctr": total_clicks / total_impressions if total_impressions > 0 else 0,
                "overall_cvr": total_conversions / total_clicks if total_clicks > 0 else 0,
                "total_active_brands": sum(s.active_brands for s in states),
                "total_active_campaigns": sum(s.active_campaigns for s in states),
            },
            "count": len(states),
        }
    
    def _aggregate_brand_metrics(self, states: List[BrandTwinState]) -> Dict[str, Any]:
        """Aggregate metrics across brands"""
        if not states:
            return {"success": True, "metrics": {}, "count": 0}
        
        total_spend = sum(s.spend for s in states)
        total_revenue = sum(s.revenue for s in states)
        total_impressions = sum(s.impressions for s in states)
        total_clicks = sum(s.clicks for s in states)
        total_conversions = sum(s.conversions for s in states)
        
        # Group by category
        categories = {}
        for s in states:
            cat = s.category or "Unknown"
            if cat not in categories:
                categories[cat] = {"count": 0, "spend": 0, "revenue": 0}
            categories[cat]["count"] += 1
            categories[cat]["spend"] += s.spend
            categories[cat]["revenue"] += s.revenue
        
        return {
            "success": True,
            "metrics": {
                "total_brands": len(states),
                "total_spend": total_spend,
                "total_revenue": total_revenue,
                "total_impressions": total_impressions,
                "overall_roas": total_revenue / total_spend if total_spend > 0 else 0,
                "avg_brand_spend": total_spend / len(states),
                "avg_brand_roas": sum(s.roas for s in states) / len(states),
                "categories": categories,
            },
            "count": len(states),
        }
    
    def _aggregate_campaign_metrics(self, states: List[CampaignTwinState]) -> Dict[str, Any]:
        """Aggregate metrics across campaigns"""
        if not states:
            return {"success": True, "metrics": {}, "count": 0}
        
        total_spend = sum(s.spend for s in states)
        total_revenue = sum(s.revenue for s in states)
        
        # Group by status
        by_status = {}
        for s in states:
            status = s.status.value if hasattr(s.status, 'value') else s.status
            if status not in by_status:
                by_status[status] = 0
            by_status[status] += 1
        
        # Group by channel type
        by_channel = {}
        for s in states:
            ch = s.channel_type.value if hasattr(s.channel_type, 'value') else s.channel_type
            if ch not in by_channel:
                by_channel[ch] = {"count": 0, "spend": 0}
            by_channel[ch]["count"] += 1
            by_channel[ch]["spend"] += s.spend
        
        return {
            "success": True,
            "metrics": {
                "total_campaigns": len(states),
                "total_spend": total_spend,
                "total_revenue": total_revenue,
                "overall_roas": total_revenue / total_spend if total_spend > 0 else 0,
                "by_status": by_status,
                "by_channel": by_channel,
            },
            "count": len(states),
        }
    
    def _aggregate_channel_metrics(self, states: List[ChannelTwinState]) -> Dict[str, Any]:
        """Aggregate metrics across channels"""
        if not states:
            return {"success": True, "metrics": {}, "count": 0}
        
        total_spend = sum(s.spend for s in states)
        total_revenue = sum(s.revenue for s in states)
        total_impressions = sum(s.impressions for s in states)
        
        # Group by channel type
        by_type = {}
        for s in states:
            ch = s.channel_type.value if hasattr(s.channel_type, 'value') else s.channel_type
            if ch not in by_type:
                by_type[ch] = {
                    "count": 0,
                    "spend": 0,
                    "revenue": 0,
                    "impressions": 0,
                }
            by_type[ch]["count"] += 1
            by_type[ch]["spend"] += s.spend
            by_type[ch]["revenue"] += s.revenue
            by_type[ch]["impressions"] += s.impressions
        
        # Compute contribution percentages
        for ch_type, data in by_type.items():
            data["spend_share"] = data["spend"] / total_spend if total_spend > 0 else 0
            data["roas"] = data["revenue"] / data["spend"] if data["spend"] > 0 else 0
        
        return {
            "success": True,
            "metrics": {
                "total_channels": len(states),
                "total_spend": total_spend,
                "total_revenue": total_revenue,
                "total_impressions": total_impressions,
                "overall_roas": total_revenue / total_spend if total_spend > 0 else 0,
                "by_channel_type": by_type,
            },
            "count": len(states),
        }
    
    # =========================================================================
    # Event Subscriptions
    # =========================================================================
    
    def subscribe_to_updates(
        self,
        callback: Callable[[TwinStateEvent], None],
        twin_type: Optional[TwinType] = None,
        retailer_id: Optional[str] = None,
    ) -> str:
        """
        Subscribe to twin state update events.
        
        Args:
            callback: Function to call when state changes
            twin_type: Optional filter by twin type
            retailer_id: Optional filter by retailer
            
        Returns:
            Subscription ID
        """
        subscription_id = self.manager.subscribe(
            TwinEventType.STATE_UPDATED,
            callback,
            twin_type,
            retailer_id,
        )
        self._subscriptions[subscription_id] = callback
        return subscription_id
    
    def subscribe_to_alerts(
        self,
        callback: Callable[[TwinStateEvent], None],
        alert_type: str = "pacing",
    ) -> str:
        """
        Subscribe to alert events.
        
        Args:
            callback: Function to call when alert occurs
            alert_type: Type of alert ('pacing', 'budget', 'anomaly')
            
        Returns:
            Subscription ID
        """
        event_type = {
            "pacing": TwinEventType.PACING_ALERT,
            "budget": TwinEventType.BUDGET_ALERT,
            "anomaly": TwinEventType.ANOMALY_DETECTED,
        }.get(alert_type, TwinEventType.PACING_ALERT)
        
        subscription_id = self.manager.subscribe(event_type, callback)
        self._subscriptions[subscription_id] = callback
        return subscription_id
    
    def unsubscribe(self, subscription_id: str):
        """Unsubscribe from events"""
        if subscription_id in self._subscriptions:
            callback = self._subscriptions.pop(subscription_id)
            # Note: actual unsubscribe from manager would need subscription key
    
    # =========================================================================
    # Convenience Methods for Agents
    # =========================================================================
    
    def get_retailer_overview(self, retailer_id: str) -> Dict[str, Any]:
        """Get complete overview for a retailer"""
        rmn = self.manager.get_rmn_state(retailer_id)
        brands = self.manager.get_all_brand_states(retailer_id)
        campaigns = self.manager.get_all_campaign_states(retailer_id)
        channels = self.manager.get_all_channel_states(retailer_id)
        
        return {
            "retailer_id": retailer_id,
            "rmn": rmn.dict() if rmn else None,
            "brands": {
                "count": len(brands),
                "top_performers": sorted(
                    [b.dict() for b in brands],
                    key=lambda x: x.get('roas', 0),
                    reverse=True
                )[:5],
            },
            "campaigns": {
                "count": len(campaigns),
                "active": len([c for c in campaigns if c.status == "active"]),
                "by_status": self._group_by_status(campaigns),
            },
            "channels": {
                "count": len(channels),
                "performance": [
                    {
                        "channel": c.channel_type.value if hasattr(c.channel_type, 'value') else c.channel_type,
                        "spend": c.spend,
                        "roas": c.roas,
                        "contribution": c.contribution_pct,
                    }
                    for c in channels
                ],
            },
        }
    
    def _group_by_status(self, campaigns: List[CampaignTwinState]) -> Dict[str, int]:
        """Group campaigns by status"""
        result = {}
        for c in campaigns:
            status = c.status.value if hasattr(c.status, 'value') else c.status
            result[status] = result.get(status, 0) + 1
        return result
    
    def get_channel_bayesian_posteriors(self, retailer_id: str) -> List[Dict[str, Any]]:
        """Get Bayesian posteriors for all channels"""
        channels = self.manager.get_all_channel_states(retailer_id)
        
        return [
            {
                "channel_id": c.channel_id,
                "channel_type": c.channel_type.value if hasattr(c.channel_type, 'value') else c.channel_type,
                "elasticity": {
                    "mean": c.elasticity_mean,
                    "std": c.elasticity_std,
                    "ci_lower": c.elasticity_ci_lower,
                    "ci_upper": c.elasticity_ci_upper,
                },
                "prob_efficiency_above_target": c.prob_efficiency_above_target,
                "contribution_pct": c.contribution_pct,
            }
            for c in channels
        ]
    
    def get_brand_bayesian_posteriors(self, retailer_id: str) -> List[Dict[str, Any]]:
        """Get Bayesian posteriors for all brands"""
        brands = self.manager.get_all_brand_states(retailer_id)
        
        return [
            {
                "brand_id": b.brand_id,
                "brand_name": b.brand_name,
                "incremental_sales": {
                    "mean": b.incremental_sales_mean,
                    "std": b.incremental_sales_std,
                    "ci_lower": b.incremental_sales_ci_lower,
                    "ci_upper": b.incremental_sales_ci_upper,
                },
                "efficiency": {
                    "mean": b.efficiency_mean,
                    "std": b.efficiency_std,
                },
                "lift_vs_prior_period": b.lift_vs_prior_period,
                "prob_positive_lift": b.prob_positive_lift,
            }
            for b in brands
        ]


def create_twin_state_tool(manager: Optional[UnifiedTwinManager] = None) -> TwinStateTool:
    """Factory function for creating TwinStateTool"""
    return TwinStateTool(manager)

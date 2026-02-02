"""
Channel State Digital Twin Contracts

Canonical schemas for Retail Media Network digital twins:
- RMN (Retail Media Network) Twin
- Brand Twin
- Campaign Twin
- Channel Twin

These contracts define the data structures for:
1. Ingestion from external sources (CSV)
2. Mapping from retailer-specific formats to canonical
3. Persistence with history tracking
4. Agent access via event subscriptions
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any, Protocol
from enum import Enum
from pydantic import BaseModel, Field
from dataclasses import dataclass, field
import hashlib
import json


# =============================================================================
# Enums
# =============================================================================

class TwinType(str, Enum):
    """Types of digital twins in the retail media ecosystem"""
    RMN = "rmn"
    BRAND = "brand"
    CAMPAIGN = "campaign"
    CHANNEL = "channel"


class ChannelType(str, Enum):
    """Canonical channel types"""
    SPONSORED_SEARCH = "sponsored_search"
    SPONSORED_PRODUCTS = "sponsored_products"
    SPONSORED_BRANDS = "sponsored_brands"
    DISPLAY = "display"
    VIDEO = "video"
    EMAIL = "email"
    CONNECTED_TV = "connected_tv"
    IN_STORE = "in_store"
    SOCIAL = "social"
    DSP = "dsp"


class CampaignStatus(str, Enum):
    """Campaign status values"""
    DRAFT = "draft"
    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class PacingStatus(str, Enum):
    """Budget pacing status"""
    ON_TRACK = "on_track"
    UNDER_PACING = "under_pacing"
    OVER_PACING = "over_pacing"
    AT_RISK = "at_risk"


# =============================================================================
# Base Twin State
# =============================================================================

class BaseTwinState(BaseModel):
    """Base class for all twin states"""
    twin_id: str = Field(..., description="Unique identifier for this twin")
    twin_type: TwinType = Field(..., description="Type of twin")
    retailer_id: str = Field(..., description="Retailer/RMN identifier")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    week: int = Field(default=1, description="Current week number")
    
    # Versioning for history
    version: int = Field(default=1, description="State version number")
    previous_version_id: Optional[str] = Field(None, description="ID of previous state version")
    
    # Data quality
    data_quality_score: float = Field(default=1.0, ge=0.0, le=1.0)
    source_system: str = Field(default="manual", description="Source of data")
    
    def compute_state_hash(self) -> str:
        """Compute hash of current state for change detection"""
        state_dict = self.dict(exclude={'created_at', 'updated_at', 'version', 'previous_version_id'})
        state_json = json.dumps(state_dict, sort_keys=True, default=str)
        return hashlib.sha256(state_json.encode()).hexdigest()[:16]
    
    class Config:
        use_enum_values = True


# =============================================================================
# RMN (Retail Media Network) Twin
# =============================================================================

class RMNTwinState(BaseTwinState):
    """
    Digital Twin state for a Retail Media Network.
    
    Represents the overall state of an RMN (Walmart Connect, Amazon Ads, etc.)
    """
    twin_type: TwinType = Field(default=TwinType.RMN)
    
    # RMN Identity
    rmn_name: str = Field(..., description="RMN display name")
    
    # Aggregate Performance
    total_impressions: int = Field(default=0, ge=0)
    total_clicks: int = Field(default=0, ge=0)
    total_conversions: int = Field(default=0, ge=0)
    total_spend: float = Field(default=0.0, ge=0.0)
    total_revenue: float = Field(default=0.0, ge=0.0)
    
    # Efficiency Metrics
    overall_roas: float = Field(default=0.0, ge=0.0)
    overall_ctr: float = Field(default=0.0, ge=0.0)
    overall_cvr: float = Field(default=0.0, ge=0.0)
    
    # Portfolio Summary
    active_brands: int = Field(default=0, ge=0)
    active_campaigns: int = Field(default=0, ge=0)
    active_channels: int = Field(default=0, ge=0)
    
    # Budget State
    total_budget: float = Field(default=0.0, ge=0.0)
    budget_utilized: float = Field(default=0.0, ge=0.0)
    budget_utilization_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    pacing_status: PacingStatus = Field(default=PacingStatus.ON_TRACK)
    
    # Bayesian Posteriors (from analysis)
    efficiency_posterior_mean: float = Field(default=1.0)
    efficiency_posterior_std: float = Field(default=0.1)
    prob_positive_lift: float = Field(default=0.5, ge=0.0, le=1.0)
    
    # Channel Mix
    channel_mix: Dict[str, float] = Field(default_factory=dict, description="Channel -> spend share")


# =============================================================================
# Brand Twin
# =============================================================================

class BrandTwinState(BaseTwinState):
    """
    Digital Twin state for a Brand within an RMN.
    
    Represents brand-level performance and state.
    """
    twin_type: TwinType = Field(default=TwinType.BRAND)
    
    # Brand Identity
    brand_id: str = Field(..., description="Brand identifier")
    brand_name: str = Field(..., description="Brand display name")
    category: str = Field(default="", description="Product category")
    
    # Performance Metrics
    impressions: int = Field(default=0, ge=0)
    clicks: int = Field(default=0, ge=0)
    conversions: int = Field(default=0, ge=0)
    spend: float = Field(default=0.0, ge=0.0)
    revenue: float = Field(default=0.0, ge=0.0)
    units_sold: int = Field(default=0, ge=0)
    
    # Efficiency Metrics
    roas: float = Field(default=0.0, ge=0.0)
    ctr: float = Field(default=0.0, ge=0.0)
    cvr: float = Field(default=0.0, ge=0.0)
    cpc: float = Field(default=0.0, ge=0.0)
    cpa: float = Field(default=0.0, ge=0.0)
    
    # Brand Health
    new_to_brand_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    brand_search_lift: float = Field(default=0.0)
    share_of_voice: float = Field(default=0.0, ge=0.0, le=1.0)
    
    # Portfolio
    active_campaigns: int = Field(default=0, ge=0)
    
    # Budget State
    budget: float = Field(default=0.0, ge=0.0)
    budget_utilized: float = Field(default=0.0, ge=0.0)
    pacing_status: PacingStatus = Field(default=PacingStatus.ON_TRACK)
    
    # Bayesian Posteriors
    incremental_sales_mean: float = Field(default=0.0)
    incremental_sales_std: float = Field(default=0.0)
    incremental_sales_ci_lower: float = Field(default=0.0)
    incremental_sales_ci_upper: float = Field(default=0.0)
    efficiency_mean: float = Field(default=1.0)
    efficiency_std: float = Field(default=0.1)
    lift_vs_prior_period: float = Field(default=0.0)
    prob_positive_lift: float = Field(default=0.5, ge=0.0, le=1.0)


# =============================================================================
# Campaign Twin
# =============================================================================

class CampaignTwinState(BaseTwinState):
    """
    Digital Twin state for a Campaign.
    
    Represents campaign-level performance and state.
    """
    twin_type: TwinType = Field(default=TwinType.CAMPAIGN)
    
    # Campaign Identity
    campaign_id: str = Field(..., description="Campaign identifier")
    campaign_name: str = Field(..., description="Campaign display name")
    brand_id: str = Field(..., description="Parent brand identifier")
    
    # Campaign Config
    objective: str = Field(default="conversion", description="Campaign objective")
    channel_type: ChannelType = Field(default=ChannelType.SPONSORED_PRODUCTS)
    status: CampaignStatus = Field(default=CampaignStatus.ACTIVE)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    
    # Performance Metrics
    impressions: int = Field(default=0, ge=0)
    clicks: int = Field(default=0, ge=0)
    conversions: int = Field(default=0, ge=0)
    spend: float = Field(default=0.0, ge=0.0)
    revenue: float = Field(default=0.0, ge=0.0)
    units_sold: int = Field(default=0, ge=0)
    
    # Efficiency Metrics
    roas: float = Field(default=0.0, ge=0.0)
    ctr: float = Field(default=0.0, ge=0.0)
    cvr: float = Field(default=0.0, ge=0.0)
    cpc: float = Field(default=0.0, ge=0.0)
    cpa: float = Field(default=0.0, ge=0.0)
    
    # Budget State
    budget: float = Field(default=0.0, ge=0.0)
    daily_budget: Optional[float] = None
    budget_utilized: float = Field(default=0.0, ge=0.0)
    budget_remaining: float = Field(default=0.0, ge=0.0)
    pacing_status: PacingStatus = Field(default=PacingStatus.ON_TRACK)
    days_remaining: int = Field(default=0, ge=0)
    
    # Targeting
    targeting_segments: List[str] = Field(default_factory=list)
    
    # Attribution
    attribution_window_days: int = Field(default=14, ge=1)
    attribution_model: str = Field(default="last_click")
    
    # Bayesian Posteriors
    expected_incremental_sales: float = Field(default=0.0)
    incremental_sales_ci: List[float] = Field(default_factory=lambda: [0.0, 0.0])
    elasticity_mean: float = Field(default=0.15)
    elasticity_std: float = Field(default=0.05)


# =============================================================================
# Channel Twin
# =============================================================================

class ChannelTwinState(BaseTwinState):
    """
    Digital Twin state for a Channel within an RMN.
    
    Represents channel-level performance (e.g., Sponsored Products at Walmart).
    """
    twin_type: TwinType = Field(default=TwinType.CHANNEL)
    
    # Channel Identity
    channel_id: str = Field(..., description="Channel identifier")
    channel_type: ChannelType = Field(..., description="Type of channel")
    channel_name: str = Field(default="", description="Channel display name")
    
    # Performance Metrics
    impressions: int = Field(default=0, ge=0)
    clicks: int = Field(default=0, ge=0)
    conversions: int = Field(default=0, ge=0)
    spend: float = Field(default=0.0, ge=0.0)
    revenue: float = Field(default=0.0, ge=0.0)
    units_sold: int = Field(default=0, ge=0)
    
    # Engagement Metrics
    ctr: float = Field(default=0.0, ge=0.0)
    cvr: float = Field(default=0.0, ge=0.0)
    cpc: float = Field(default=0.0, ge=0.0)
    cpa: float = Field(default=0.0, ge=0.0)
    cpm: float = Field(default=0.0, ge=0.0)
    
    # Return Metrics
    roas: float = Field(default=0.0, ge=0.0)
    attributed_revenue: float = Field(default=0.0, ge=0.0)
    
    # Reach & Frequency
    audience_reach: int = Field(default=0, ge=0)
    frequency: float = Field(default=0.0, ge=0.0)
    viewability_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    
    # Budget State
    budget: float = Field(default=0.0, ge=0.0)
    budget_utilized: float = Field(default=0.0, ge=0.0)
    budget_utilization_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    pacing_status: PacingStatus = Field(default=PacingStatus.ON_TRACK)
    
    # Adstock (carryover effects)
    cumulative_adstock: float = Field(default=0.0, ge=0.0)
    adstock_decay_rate: float = Field(default=0.7, ge=0.0, le=1.0)
    
    # Bayesian Posteriors
    elasticity_mean: float = Field(default=0.15)
    elasticity_std: float = Field(default=0.05)
    elasticity_ci_lower: float = Field(default=0.05)
    elasticity_ci_upper: float = Field(default=0.25)
    contribution_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    prob_efficiency_above_target: float = Field(default=0.5, ge=0.0, le=1.0)


# =============================================================================
# State History Record
# =============================================================================

class TwinStateHistoryRecord(BaseModel):
    """Record for tracking twin state history"""
    record_id: str = Field(..., description="Unique record identifier")
    twin_id: str = Field(..., description="Twin identifier")
    twin_type: TwinType = Field(..., description="Type of twin")
    version: int = Field(..., description="State version number")
    state_hash: str = Field(..., description="Hash of state for change detection")
    
    # State snapshot (serialized)
    state_json: str = Field(..., description="JSON serialized state")
    
    # Metadata
    recorded_at: datetime = Field(default_factory=datetime.utcnow)
    source_system: str = Field(default="manual")
    change_reason: str = Field(default="", description="Reason for state change")
    
    # Metrics delta from previous
    metrics_delta: Dict[str, float] = Field(default_factory=dict)


# =============================================================================
# CSV Ingestion Records
# =============================================================================

class CSVIngestionRecord(BaseModel):
    """Record for CSV data ingestion"""
    ingestion_id: str = Field(..., description="Unique ingestion identifier")
    file_path: str = Field(..., description="Path to source CSV file")
    file_hash: str = Field(..., description="Hash of file for deduplication")
    
    # Ingestion metadata
    ingested_at: datetime = Field(default_factory=datetime.utcnow)
    row_count: int = Field(default=0, ge=0)
    success_count: int = Field(default=0, ge=0)
    error_count: int = Field(default=0, ge=0)
    
    # Target
    twin_type: TwinType = Field(..., description="Type of twin being populated")
    retailer_id: str = Field(..., description="Target retailer")
    
    # Validation
    validation_errors: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Status
    status: str = Field(default="pending", description="pending, processing, completed, failed")


# =============================================================================
# Mapping Protocol
# =============================================================================

class TwinStateMappingProtocol(Protocol):
    """Protocol for mapping retailer-specific data to canonical twin state"""
    
    def map_rmn_state(self, raw_data: Dict[str, Any]) -> RMNTwinState:
        """Map raw data to RMN twin state"""
        ...
    
    def map_brand_state(self, raw_data: Dict[str, Any]) -> BrandTwinState:
        """Map raw data to Brand twin state"""
        ...
    
    def map_campaign_state(self, raw_data: Dict[str, Any]) -> CampaignTwinState:
        """Map raw data to Campaign twin state"""
        ...
    
    def map_channel_state(self, raw_data: Dict[str, Any]) -> ChannelTwinState:
        """Map raw data to Channel twin state"""
        ...


# =============================================================================
# Event Types for Subscriptions
# =============================================================================

class TwinStateEvent(BaseModel):
    """Event emitted when twin state changes"""
    event_id: str = Field(..., description="Unique event identifier")
    event_type: str = Field(..., description="Type of event")
    twin_id: str = Field(..., description="Twin that changed")
    twin_type: TwinType = Field(..., description="Type of twin")
    retailer_id: str = Field(..., description="Retailer identifier")
    
    # Event data
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: int = Field(..., description="New state version")
    previous_version: Optional[int] = None
    
    # Change summary
    changed_fields: List[str] = Field(default_factory=list)
    metrics_delta: Dict[str, float] = Field(default_factory=dict)
    
    # Full state (optional, for subscribers that need it)
    state_snapshot: Optional[Dict[str, Any]] = None


class TwinEventType(str, Enum):
    """Types of twin state events"""
    STATE_CREATED = "twin.state.created"
    STATE_UPDATED = "twin.state.updated"
    STATE_DELETED = "twin.state.deleted"
    METRICS_CHANGED = "twin.metrics.changed"
    BUDGET_ALERT = "twin.budget.alert"
    PACING_ALERT = "twin.pacing.alert"
    ANOMALY_DETECTED = "twin.anomaly.detected"


# =============================================================================
# CSV Column Mappings (for ingestion)
# =============================================================================

RMN_CSV_COLUMNS = {
    "rmn_id": "twin_id",
    "rmn_name": "rmn_name",
    "retailer_id": "retailer_id",
    "total_impressions": "total_impressions",
    "total_clicks": "total_clicks",
    "total_conversions": "total_conversions",
    "total_spend": "total_spend",
    "total_revenue": "total_revenue",
    "active_brands": "active_brands",
    "active_campaigns": "active_campaigns",
    "total_budget": "total_budget",
    "week": "week",
}

BRAND_CSV_COLUMNS = {
    "brand_id": "brand_id",
    "brand_name": "brand_name",
    "retailer_id": "retailer_id",
    "category": "category",
    "impressions": "impressions",
    "clicks": "clicks",
    "conversions": "conversions",
    "spend": "spend",
    "revenue": "revenue",
    "units_sold": "units_sold",
    "budget": "budget",
    "week": "week",
}

CAMPAIGN_CSV_COLUMNS = {
    "campaign_id": "campaign_id",
    "campaign_name": "campaign_name",
    "brand_id": "brand_id",
    "retailer_id": "retailer_id",
    "channel_type": "channel_type",
    "status": "status",
    "objective": "objective",
    "impressions": "impressions",
    "clicks": "clicks",
    "conversions": "conversions",
    "spend": "spend",
    "revenue": "revenue",
    "budget": "budget",
    "daily_budget": "daily_budget",
    "start_date": "start_date",
    "end_date": "end_date",
    "week": "week",
}

CHANNEL_CSV_COLUMNS = {
    "channel_id": "channel_id",
    "channel_type": "channel_type",
    "channel_name": "channel_name",
    "retailer_id": "retailer_id",
    "impressions": "impressions",
    "clicks": "clicks",
    "conversions": "conversions",
    "spend": "spend",
    "revenue": "revenue",
    "budget": "budget",
    "audience_reach": "audience_reach",
    "frequency": "frequency",
    "week": "week",
}

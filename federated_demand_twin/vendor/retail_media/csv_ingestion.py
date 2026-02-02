"""
CSV Ingestion Module for Digital Twin States

Handles ingestion of CSV data into twin states with:
- Column mapping to canonical schema
- Validation and error handling
- Metrics computation (CTR, CVR, ROAS, etc.)
- Event emission on ingestion
"""

import csv
import hashlib
import logging
from pathlib import Path
from datetime import datetime, date
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import uuid

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.schemas.channel_state_contracts import (
    RMNTwinState,
    BrandTwinState,
    CampaignTwinState,
    ChannelTwinState,
    TwinType,
    ChannelType,
    CampaignStatus,
    PacingStatus,
    CSVIngestionRecord,
    RMN_CSV_COLUMNS,
    BRAND_CSV_COLUMNS,
    CAMPAIGN_CSV_COLUMNS,
    CHANNEL_CSV_COLUMNS,
)
from vendor.retail_media.twin_state_store import TwinStateStore, get_twin_state_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    """Result of CSV ingestion"""
    success: bool
    ingestion_id: str
    twin_type: TwinType
    records_processed: int
    records_succeeded: int
    records_failed: int
    errors: List[Dict[str, Any]]
    states_created: List[str]
    states_updated: List[str]


class CSVIngestionService:
    """
    Service for ingesting CSV data into digital twin states.
    
    Supports ingestion for:
    - RMN (Retail Media Network) data
    - Brand performance data
    - Campaign data
    - Channel data
    """
    
    def __init__(self, store: Optional[TwinStateStore] = None):
        self.store = store or get_twin_state_store()
        self._ingestion_history: List[CSVIngestionRecord] = []
    
    # =========================================================================
    # Main Ingestion Methods
    # =========================================================================
    
    def ingest_rmn_csv(
        self,
        file_path: str,
        retailer_id: str,
        column_mapping: Optional[Dict[str, str]] = None
    ) -> IngestionResult:
        """Ingest RMN data from CSV"""
        return self._ingest_csv(
            file_path=file_path,
            twin_type=TwinType.RMN,
            retailer_id=retailer_id,
            default_mapping=RMN_CSV_COLUMNS,
            custom_mapping=column_mapping,
            state_factory=self._create_rmn_state,
        )
    
    def ingest_brand_csv(
        self,
        file_path: str,
        retailer_id: str,
        column_mapping: Optional[Dict[str, str]] = None
    ) -> IngestionResult:
        """Ingest Brand data from CSV"""
        return self._ingest_csv(
            file_path=file_path,
            twin_type=TwinType.BRAND,
            retailer_id=retailer_id,
            default_mapping=BRAND_CSV_COLUMNS,
            custom_mapping=column_mapping,
            state_factory=self._create_brand_state,
        )
    
    def ingest_campaign_csv(
        self,
        file_path: str,
        retailer_id: str,
        column_mapping: Optional[Dict[str, str]] = None
    ) -> IngestionResult:
        """Ingest Campaign data from CSV"""
        return self._ingest_csv(
            file_path=file_path,
            twin_type=TwinType.CAMPAIGN,
            retailer_id=retailer_id,
            default_mapping=CAMPAIGN_CSV_COLUMNS,
            custom_mapping=column_mapping,
            state_factory=self._create_campaign_state,
        )
    
    def ingest_channel_csv(
        self,
        file_path: str,
        retailer_id: str,
        column_mapping: Optional[Dict[str, str]] = None
    ) -> IngestionResult:
        """Ingest Channel data from CSV"""
        return self._ingest_csv(
            file_path=file_path,
            twin_type=TwinType.CHANNEL,
            retailer_id=retailer_id,
            default_mapping=CHANNEL_CSV_COLUMNS,
            custom_mapping=column_mapping,
            state_factory=self._create_channel_state,
        )
    
    # =========================================================================
    # Generic Ingestion
    # =========================================================================
    
    def _ingest_csv(
        self,
        file_path: str,
        twin_type: TwinType,
        retailer_id: str,
        default_mapping: Dict[str, str],
        custom_mapping: Optional[Dict[str, str]],
        state_factory: callable,
    ) -> IngestionResult:
        """Generic CSV ingestion"""
        ingestion_id = f"ing_{uuid.uuid4().hex[:12]}"
        file_path = Path(file_path)
        
        # Validate file exists
        if not file_path.exists():
            return IngestionResult(
                success=False,
                ingestion_id=ingestion_id,
                twin_type=twin_type,
                records_processed=0,
                records_succeeded=0,
                records_failed=0,
                errors=[{"error": f"File not found: {file_path}"}],
                states_created=[],
                states_updated=[],
            )
        
        # Compute file hash
        file_hash = self._compute_file_hash(file_path)
        
        # Merge mappings
        mapping = {**default_mapping}
        if custom_mapping:
            mapping.update(custom_mapping)
        
        # Read and process CSV
        errors = []
        states_created = []
        states_updated = []
        records_processed = 0
        records_succeeded = 0
        records_failed = 0
        
        try:
            with open(file_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
                    records_processed += 1
                    
                    try:
                        # Map columns
                        mapped_data = self._map_row(row, mapping)
                        mapped_data['retailer_id'] = retailer_id
                        mapped_data['source_system'] = f"csv:{file_path.name}"
                        
                        # Create state
                        state = state_factory(mapped_data)
                        
                        # Check if exists
                        existing = self.store.get_state(state.twin_id, twin_type)
                        
                        # Update store
                        self.store.update_state(
                            state,
                            change_reason=f"CSV ingestion from {file_path.name}",
                        )
                        
                        if existing:
                            states_updated.append(state.twin_id)
                        else:
                            states_created.append(state.twin_id)
                        
                        records_succeeded += 1
                        
                    except Exception as e:
                        records_failed += 1
                        errors.append({
                            "row": row_num,
                            "error": str(e),
                            "data": row,
                        })
                        logger.warning(f"Error processing row {row_num}: {e}")
        
        except Exception as e:
            errors.append({"error": f"CSV read error: {str(e)}"})
            logger.error(f"Error reading CSV {file_path}: {e}")
        
        # Record ingestion
        record = CSVIngestionRecord(
            ingestion_id=ingestion_id,
            file_path=str(file_path),
            file_hash=file_hash,
            row_count=records_processed,
            success_count=records_succeeded,
            error_count=records_failed,
            twin_type=twin_type,
            retailer_id=retailer_id,
            validation_errors=errors,
            status="completed" if records_failed == 0 else "completed_with_errors",
        )
        self._ingestion_history.append(record)
        
        logger.info(
            f"Ingested {twin_type.value} CSV: {records_succeeded}/{records_processed} succeeded, "
            f"{len(states_created)} created, {len(states_updated)} updated"
        )
        
        return IngestionResult(
            success=records_failed == 0,
            ingestion_id=ingestion_id,
            twin_type=twin_type,
            records_processed=records_processed,
            records_succeeded=records_succeeded,
            records_failed=records_failed,
            errors=errors,
            states_created=states_created,
            states_updated=states_updated,
        )
    
    def _map_row(self, row: Dict[str, str], mapping: Dict[str, str]) -> Dict[str, Any]:
        """Map CSV row to canonical fields"""
        result = {}
        
        for csv_col, canonical_field in mapping.items():
            if csv_col in row:
                value = row[csv_col]
                # Convert types
                result[canonical_field] = self._convert_value(canonical_field, value)
        
        return result
    
    def _convert_value(self, field_name: str, value: str) -> Any:
        """Convert string value to appropriate type"""
        if value is None or value == '':
            return None
        
        # Integer fields
        int_fields = [
            'impressions', 'clicks', 'conversions', 'units_sold',
            'total_impressions', 'total_clicks', 'total_conversions',
            'active_brands', 'active_campaigns', 'active_channels',
            'audience_reach', 'week', 'version', 'attribution_window_days',
            'days_remaining',
        ]
        
        # Float fields
        float_fields = [
            'spend', 'revenue', 'budget', 'daily_budget', 'budget_utilized',
            'budget_remaining', 'total_spend', 'total_revenue', 'total_budget',
            'roas', 'ctr', 'cvr', 'cpc', 'cpa', 'cpm',
            'overall_roas', 'overall_ctr', 'overall_cvr',
            'frequency', 'viewability_rate', 'data_quality_score',
            'efficiency_mean', 'efficiency_std', 'elasticity_mean', 'elasticity_std',
            'incremental_sales_mean', 'incremental_sales_std',
            'prob_positive_lift', 'share_of_voice', 'new_to_brand_pct',
            'cumulative_adstock', 'adstock_decay_rate', 'contribution_pct',
            'budget_utilization_pct',
        ]
        
        # Date fields
        date_fields = ['start_date', 'end_date']
        
        try:
            if field_name in int_fields:
                return int(float(value))
            elif field_name in float_fields:
                return float(value)
            elif field_name in date_fields:
                return datetime.strptime(value, '%Y-%m-%d').date()
            else:
                return value
        except (ValueError, TypeError):
            return value
    
    # =========================================================================
    # State Factories
    # =========================================================================
    
    def _create_rmn_state(self, data: Dict[str, Any]) -> RMNTwinState:
        """Create RMN state from mapped data"""
        twin_id = data.get('twin_id') or f"rmn_{data['retailer_id']}"
        
        # Compute derived metrics
        total_spend = data.get('total_spend', 0) or 0
        total_revenue = data.get('total_revenue', 0) or 0
        total_impressions = data.get('total_impressions', 0) or 0
        total_clicks = data.get('total_clicks', 0) or 0
        total_conversions = data.get('total_conversions', 0) or 0
        total_budget = data.get('total_budget', 0) or 0
        
        overall_roas = total_revenue / total_spend if total_spend > 0 else 0
        overall_ctr = total_clicks / total_impressions if total_impressions > 0 else 0
        overall_cvr = total_conversions / total_clicks if total_clicks > 0 else 0
        budget_utilized = total_spend
        budget_utilization_pct = total_spend / total_budget if total_budget > 0 else 0
        
        return RMNTwinState(
            twin_id=twin_id,
            retailer_id=data['retailer_id'],
            rmn_name=data.get('rmn_name', data['retailer_id']),
            total_impressions=total_impressions,
            total_clicks=total_clicks,
            total_conversions=total_conversions,
            total_spend=total_spend,
            total_revenue=total_revenue,
            overall_roas=overall_roas,
            overall_ctr=overall_ctr,
            overall_cvr=overall_cvr,
            active_brands=data.get('active_brands', 0) or 0,
            active_campaigns=data.get('active_campaigns', 0) or 0,
            active_channels=data.get('active_channels', 0) or 0,
            total_budget=total_budget,
            budget_utilized=budget_utilized,
            budget_utilization_pct=budget_utilization_pct,
            pacing_status=self._compute_pacing_status(budget_utilization_pct),
            week=data.get('week', 1) or 1,
            source_system=data.get('source_system', 'csv'),
        )
    
    def _create_brand_state(self, data: Dict[str, Any]) -> BrandTwinState:
        """Create Brand state from mapped data"""
        brand_id = data.get('brand_id', '')
        twin_id = f"brand_{data['retailer_id']}_{brand_id}"
        
        # Compute derived metrics
        spend = data.get('spend', 0) or 0
        revenue = data.get('revenue', 0) or 0
        impressions = data.get('impressions', 0) or 0
        clicks = data.get('clicks', 0) or 0
        conversions = data.get('conversions', 0) or 0
        budget = data.get('budget', 0) or 0
        
        roas = revenue / spend if spend > 0 else 0
        ctr = clicks / impressions if impressions > 0 else 0
        cvr = conversions / clicks if clicks > 0 else 0
        cpc = spend / clicks if clicks > 0 else 0
        cpa = spend / conversions if conversions > 0 else 0
        budget_utilized = spend
        
        return BrandTwinState(
            twin_id=twin_id,
            retailer_id=data['retailer_id'],
            brand_id=brand_id,
            brand_name=data.get('brand_name', brand_id),
            category=data.get('category', ''),
            impressions=impressions,
            clicks=clicks,
            conversions=conversions,
            spend=spend,
            revenue=revenue,
            units_sold=data.get('units_sold', 0) or 0,
            roas=roas,
            ctr=ctr,
            cvr=cvr,
            cpc=cpc,
            cpa=cpa,
            budget=budget,
            budget_utilized=budget_utilized,
            pacing_status=self._compute_pacing_status(budget_utilized / budget if budget > 0 else 0),
            week=data.get('week', 1) or 1,
            source_system=data.get('source_system', 'csv'),
        )
    
    def _create_campaign_state(self, data: Dict[str, Any]) -> CampaignTwinState:
        """Create Campaign state from mapped data"""
        campaign_id = data.get('campaign_id', '')
        twin_id = f"campaign_{data['retailer_id']}_{campaign_id}"
        
        # Compute derived metrics
        spend = data.get('spend', 0) or 0
        revenue = data.get('revenue', 0) or 0
        impressions = data.get('impressions', 0) or 0
        clicks = data.get('clicks', 0) or 0
        conversions = data.get('conversions', 0) or 0
        budget = data.get('budget', 0) or 0
        
        roas = revenue / spend if spend > 0 else 0
        ctr = clicks / impressions if impressions > 0 else 0
        cvr = conversions / clicks if clicks > 0 else 0
        cpc = spend / clicks if clicks > 0 else 0
        cpa = spend / conversions if conversions > 0 else 0
        budget_utilized = spend
        budget_remaining = budget - spend
        
        # Parse channel type
        channel_type_str = data.get('channel_type', 'sponsored_products')
        try:
            channel_type = ChannelType(channel_type_str.lower().replace(' ', '_'))
        except ValueError:
            channel_type = ChannelType.SPONSORED_PRODUCTS
        
        # Parse status
        status_str = data.get('status', 'active')
        try:
            status = CampaignStatus(status_str.lower())
        except ValueError:
            status = CampaignStatus.ACTIVE
        
        return CampaignTwinState(
            twin_id=twin_id,
            retailer_id=data['retailer_id'],
            campaign_id=campaign_id,
            campaign_name=data.get('campaign_name', campaign_id),
            brand_id=data.get('brand_id', ''),
            channel_type=channel_type,
            status=status,
            objective=data.get('objective', 'conversion'),
            start_date=data.get('start_date'),
            end_date=data.get('end_date'),
            impressions=impressions,
            clicks=clicks,
            conversions=conversions,
            spend=spend,
            revenue=revenue,
            units_sold=data.get('units_sold', 0) or 0,
            roas=roas,
            ctr=ctr,
            cvr=cvr,
            cpc=cpc,
            cpa=cpa,
            budget=budget,
            daily_budget=data.get('daily_budget'),
            budget_utilized=budget_utilized,
            budget_remaining=budget_remaining,
            pacing_status=self._compute_pacing_status(budget_utilized / budget if budget > 0 else 0),
            week=data.get('week', 1) or 1,
            source_system=data.get('source_system', 'csv'),
        )
    
    def _create_channel_state(self, data: Dict[str, Any]) -> ChannelTwinState:
        """Create Channel state from mapped data"""
        channel_id = data.get('channel_id', '')
        
        # Parse channel type
        channel_type_str = data.get('channel_type', 'sponsored_products')
        try:
            channel_type = ChannelType(channel_type_str.lower().replace(' ', '_'))
        except ValueError:
            channel_type = ChannelType.SPONSORED_PRODUCTS
        
        twin_id = f"channel_{data['retailer_id']}_{channel_type.value}"
        
        # Compute derived metrics
        spend = data.get('spend', 0) or 0
        revenue = data.get('revenue', 0) or 0
        impressions = data.get('impressions', 0) or 0
        clicks = data.get('clicks', 0) or 0
        conversions = data.get('conversions', 0) or 0
        budget = data.get('budget', 0) or 0
        
        roas = revenue / spend if spend > 0 else 0
        ctr = clicks / impressions if impressions > 0 else 0
        cvr = conversions / clicks if clicks > 0 else 0
        cpc = spend / clicks if clicks > 0 else 0
        cpa = spend / conversions if conversions > 0 else 0
        cpm = (spend / impressions * 1000) if impressions > 0 else 0
        budget_utilized = spend
        budget_utilization_pct = spend / budget if budget > 0 else 0
        
        audience_reach = data.get('audience_reach', 0) or 0
        frequency = data.get('frequency') or (impressions / audience_reach if audience_reach > 0 else 0)
        
        return ChannelTwinState(
            twin_id=twin_id,
            retailer_id=data['retailer_id'],
            channel_id=channel_id or twin_id,
            channel_type=channel_type,
            channel_name=data.get('channel_name', channel_type.value.replace('_', ' ').title()),
            impressions=impressions,
            clicks=clicks,
            conversions=conversions,
            spend=spend,
            revenue=revenue,
            units_sold=data.get('units_sold', 0) or 0,
            ctr=ctr,
            cvr=cvr,
            cpc=cpc,
            cpa=cpa,
            cpm=cpm,
            roas=roas,
            attributed_revenue=revenue,
            audience_reach=audience_reach,
            frequency=frequency,
            budget=budget,
            budget_utilized=budget_utilized,
            budget_utilization_pct=budget_utilization_pct,
            pacing_status=self._compute_pacing_status(budget_utilization_pct),
            week=data.get('week', 1) or 1,
            source_system=data.get('source_system', 'csv'),
        )
    
    # =========================================================================
    # Helpers
    # =========================================================================
    
    def _compute_pacing_status(self, utilization_pct: float) -> PacingStatus:
        """Compute pacing status from budget utilization"""
        if utilization_pct < 0.8:
            return PacingStatus.UNDER_PACING
        elif utilization_pct > 1.1:
            return PacingStatus.OVER_PACING
        elif utilization_pct > 1.0:
            return PacingStatus.AT_RISK
        else:
            return PacingStatus.ON_TRACK
    
    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute hash of file contents"""
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hasher.update(chunk)
        return hasher.hexdigest()[:16]
    
    def get_ingestion_history(self) -> List[CSVIngestionRecord]:
        """Get ingestion history"""
        return self._ingestion_history


# Convenience function
def ingest_csv(
    file_path: str,
    twin_type: TwinType,
    retailer_id: str,
    column_mapping: Optional[Dict[str, str]] = None,
    store: Optional[TwinStateStore] = None
) -> IngestionResult:
    """
    Convenience function to ingest CSV into twin states.
    
    Args:
        file_path: Path to CSV file
        twin_type: Type of twin to create/update
        retailer_id: Retailer identifier
        column_mapping: Optional custom column mapping
        store: Optional twin state store
        
    Returns:
        IngestionResult with details
    """
    service = CSVIngestionService(store)
    
    method_map = {
        TwinType.RMN: service.ingest_rmn_csv,
        TwinType.BRAND: service.ingest_brand_csv,
        TwinType.CAMPAIGN: service.ingest_campaign_csv,
        TwinType.CHANNEL: service.ingest_channel_csv,
    }
    
    method = method_map.get(twin_type)
    if not method:
        raise ValueError(f"Unsupported twin type: {twin_type}")
    
    return method(file_path, retailer_id, column_mapping)

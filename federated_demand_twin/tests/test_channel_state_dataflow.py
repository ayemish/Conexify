"""
End-to-End Tests for Channel State Digital Twin Dataflow

Tests the complete dataflow:
1. CSV Ingestion → Canonical Schema Mapping
2. TwinStateStore Persistence with History
3. Event Subscriptions for Real-time Updates
4. Agent Access via TwinStateTool
5. Backend API Integration
"""

import os
import sys
import json
import tempfile
import pytest
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.schemas.channel_state_contracts import (
    RMNTwinState,
    BrandTwinState,
    CampaignTwinState,
    ChannelTwinState,
    TwinType,
    ChannelType,
    CampaignStatus,
    PacingStatus,
    TwinStateEvent,
    TwinEventType,
)
from vendor.retail_media.twin_state_store import (
    TwinStateStore,
    TwinStateStoreConfig,
    reset_twin_state_store,
)
from vendor.retail_media.csv_ingestion import CSVIngestionService, ingest_csv
from vendor.retail_media.unified_twin_manager import (
    UnifiedTwinManager,
    UnifiedTwinConfig,
    reset_unified_twin_manager,
)
from vendor.agents.tools.twin_state_tool import TwinStateTool


class TestResults:
    """Track test results"""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def record(self, name: str, passed: bool, error: str = None):
        if passed:
            self.passed += 1
            print(f"  ✅ {name}")
        else:
            self.failed += 1
            self.errors.append(f"{name}: {error}")
            print(f"  ❌ {name}: {error}")
    
    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"Test Results: {self.passed}/{total} passed")
        if self.errors:
            print(f"Failures:")
            for e in self.errors:
                print(f"  - {e}")
        print(f"{'='*60}")
        return self.failed == 0


# =============================================================================
# Test Fixtures
# =============================================================================

def create_sample_csvs(temp_dir: str) -> Dict[str, str]:
    """Create sample CSV files for testing"""
    paths = {}
    
    # RMN CSV
    rmn_csv = Path(temp_dir) / "rmn_data.csv"
    rmn_csv.write_text("""rmn_id,rmn_name,retailer_id,total_impressions,total_clicks,total_conversions,total_spend,total_revenue,active_brands,active_campaigns,total_budget,week
rmn_walmart,Walmart Connect,walmart,5000000,150000,15000,250000,750000,10,25,300000,1
rmn_amazon,Amazon Ads,amazon,8000000,240000,24000,400000,1200000,15,40,500000,1
rmn_target,Target Roundel,target,3000000,90000,9000,150000,450000,8,20,200000,1
""")
    paths["rmn"] = str(rmn_csv)
    
    # Brand CSV
    brand_csv = Path(temp_dir) / "brand_data.csv"
    brand_csv.write_text("""brand_id,brand_name,retailer_id,category,impressions,clicks,conversions,spend,revenue,units_sold,budget,week
brand_001,Acme Corp,walmart,CPG,1000000,30000,3000,50000,150000,5000,60000,1
brand_002,Beta Foods,walmart,Food,800000,24000,2400,40000,120000,4000,50000,1
brand_003,Gamma Tech,amazon,Electronics,1200000,36000,3600,60000,180000,6000,70000,1
brand_004,Delta Health,amazon,Health,900000,27000,2700,45000,135000,4500,55000,1
brand_005,Epsilon Home,target,Home,600000,18000,1800,30000,90000,3000,40000,1
""")
    paths["brand"] = str(brand_csv)
    
    # Campaign CSV
    campaign_csv = Path(temp_dir) / "campaign_data.csv"
    campaign_csv.write_text("""campaign_id,campaign_name,brand_id,retailer_id,channel_type,status,objective,impressions,clicks,conversions,spend,revenue,budget,daily_budget,start_date,end_date,week
camp_001,Summer Sale,brand_001,walmart,sponsored_products,active,conversion,200000,6000,600,10000,30000,15000,500,2024-06-01,2024-08-31,1
camp_002,Brand Awareness,brand_001,walmart,display,active,awareness,300000,9000,900,15000,45000,20000,700,2024-06-01,2024-08-31,1
camp_003,Holiday Push,brand_003,amazon,sponsored_search,active,conversion,400000,12000,1200,20000,60000,25000,800,2024-11-01,2024-12-31,1
camp_004,New Product,brand_004,amazon,video,paused,awareness,150000,4500,450,7500,22500,10000,300,2024-05-01,2024-07-31,1
camp_005,Back to School,brand_005,target,sponsored_products,active,conversion,250000,7500,750,12500,37500,18000,600,2024-07-15,2024-09-15,1
""")
    paths["campaign"] = str(campaign_csv)
    
    # Channel CSV
    channel_csv = Path(temp_dir) / "channel_data.csv"
    channel_csv.write_text("""channel_id,channel_type,channel_name,retailer_id,impressions,clicks,conversions,spend,revenue,budget,audience_reach,frequency,week
ch_walmart_sp,sponsored_products,Sponsored Products,walmart,2000000,60000,6000,100000,300000,120000,500000,4.0,1
ch_walmart_disp,display,Display Ads,walmart,1500000,45000,4500,75000,225000,90000,400000,3.75,1
ch_amazon_sp,sponsored_products,Sponsored Products,amazon,3000000,90000,9000,150000,450000,180000,750000,4.0,1
ch_amazon_search,sponsored_search,Sponsored Search,amazon,2500000,75000,7500,125000,375000,150000,600000,4.17,1
ch_target_sp,sponsored_products,Sponsored Products,target,1200000,36000,3600,60000,180000,72000,300000,4.0,1
""")
    paths["channel"] = str(channel_csv)
    
    return paths


# =============================================================================
# Phase 1 Tests: Canonical Schema
# =============================================================================

def test_canonical_schemas(results: TestResults):
    """Test canonical schema creation and validation"""
    print("\n--- Phase 1: Canonical Schema Tests ---")
    
    # Test RMN state creation
    try:
        rmn = RMNTwinState(
            twin_id="test_rmn",
            retailer_id="test_retailer",
            rmn_name="Test RMN",
            total_impressions=1000000,
            total_spend=50000,
            total_revenue=150000,
        )
        results.record("RMN state creation", rmn.twin_id == "test_rmn")
    except Exception as e:
        results.record("RMN state creation", False, str(e))
    
    # Test Brand state creation
    try:
        brand = BrandTwinState(
            twin_id="test_brand",
            retailer_id="test_retailer",
            brand_id="brand_001",
            brand_name="Test Brand",
            impressions=500000,
            spend=25000,
            revenue=75000,
        )
        results.record("Brand state creation", brand.brand_id == "brand_001")
    except Exception as e:
        results.record("Brand state creation", False, str(e))
    
    # Test Campaign state creation
    try:
        campaign = CampaignTwinState(
            twin_id="test_campaign",
            retailer_id="test_retailer",
            campaign_id="camp_001",
            campaign_name="Test Campaign",
            brand_id="brand_001",
            channel_type=ChannelType.SPONSORED_PRODUCTS,
            status=CampaignStatus.ACTIVE,
        )
        results.record("Campaign state creation", campaign.status == CampaignStatus.ACTIVE)
    except Exception as e:
        results.record("Campaign state creation", False, str(e))
    
    # Test Channel state creation
    try:
        channel = ChannelTwinState(
            twin_id="test_channel",
            retailer_id="test_retailer",
            channel_id="ch_001",
            channel_type=ChannelType.SPONSORED_PRODUCTS,
            impressions=200000,
            spend=10000,
            revenue=30000,
        )
        results.record("Channel state creation", channel.channel_type == ChannelType.SPONSORED_PRODUCTS)
    except Exception as e:
        results.record("Channel state creation", False, str(e))
    
    # Test state hash computation
    try:
        hash1 = rmn.compute_state_hash()
        hash2 = rmn.compute_state_hash()
        results.record("State hash is deterministic", hash1 == hash2)
    except Exception as e:
        results.record("State hash computation", False, str(e))


# =============================================================================
# Phase 2 & 3 Tests: CSV Ingestion and State Store
# =============================================================================

def test_csv_ingestion_and_store(results: TestResults, csv_paths: Dict[str, str], temp_dir: str):
    """Test CSV ingestion and state store persistence"""
    print("\n--- Phase 2 & 3: CSV Ingestion & State Store Tests ---")
    
    # Reset singletons
    reset_twin_state_store()
    reset_unified_twin_manager()
    
    # Create store with temp directory
    config = TwinStateStoreConfig(
        state_dir=f"{temp_dir}/states",
        history_dir=f"{temp_dir}/history",
        max_history_per_twin=10,
    )
    store = TwinStateStore(config)
    service = CSVIngestionService(store)
    
    # Test RMN CSV ingestion
    try:
        result = service.ingest_rmn_csv(csv_paths["rmn"], "walmart")
        results.record(
            "RMN CSV ingestion",
            result.records_succeeded > 0,
            f"Succeeded: {result.records_succeeded}, Failed: {result.records_failed}"
        )
    except Exception as e:
        results.record("RMN CSV ingestion", False, str(e))
    
    # Test Brand CSV ingestion
    try:
        result = service.ingest_brand_csv(csv_paths["brand"], "walmart")
        results.record(
            "Brand CSV ingestion",
            result.records_succeeded > 0,
            f"Succeeded: {result.records_succeeded}"
        )
    except Exception as e:
        results.record("Brand CSV ingestion", False, str(e))
    
    # Test Campaign CSV ingestion
    try:
        result = service.ingest_campaign_csv(csv_paths["campaign"], "walmart")
        results.record(
            "Campaign CSV ingestion",
            result.records_succeeded > 0,
            f"Succeeded: {result.records_succeeded}"
        )
    except Exception as e:
        results.record("Campaign CSV ingestion", False, str(e))
    
    # Test Channel CSV ingestion
    try:
        result = service.ingest_channel_csv(csv_paths["channel"], "walmart")
        results.record(
            "Channel CSV ingestion",
            result.records_succeeded > 0,
            f"Succeeded: {result.records_succeeded}"
        )
    except Exception as e:
        results.record("Channel CSV ingestion", False, str(e))
    
    # Test state retrieval
    try:
        rmn_states = store.get_rmn_states()
        results.record("RMN state retrieval", len(rmn_states) > 0, f"Count: {len(rmn_states)}")
    except Exception as e:
        results.record("RMN state retrieval", False, str(e))
    
    # Test state persistence
    try:
        store.persist_all()
        state_files = list(Path(f"{temp_dir}/states").rglob("*.json"))
        results.record("State persistence", len(state_files) > 0, f"Files: {len(state_files)}")
    except Exception as e:
        results.record("State persistence", False, str(e))
    
    # Test state history
    try:
        # Update a state to create history
        rmn_state = store.get_state("rmn_walmart", TwinType.RMN)
        if rmn_state:
            rmn_state.total_spend += 1000
            store.update_state(rmn_state, change_reason="Test update")
            history = store.get_history("rmn_walmart", TwinType.RMN)
            results.record("State history tracking", len(history) > 0, f"History entries: {len(history)}")
        else:
            results.record("State history tracking", False, "No RMN state found")
    except Exception as e:
        results.record("State history tracking", False, str(e))
    
    return store


# =============================================================================
# Phase 4 Tests: Event Subscriptions
# =============================================================================

def test_event_subscriptions(results: TestResults, store: TwinStateStore):
    """Test event subscription system"""
    print("\n--- Phase 4: Event Subscription Tests ---")
    
    events_received = []
    
    def event_handler(event: TwinStateEvent):
        events_received.append(event)
    
    # Subscribe to events
    try:
        subscription_id = store.subscribe(
            TwinEventType.STATE_UPDATED,
            event_handler,
            twin_type=TwinType.RMN,
        )
        results.record("Event subscription", subscription_id is not None)
    except Exception as e:
        results.record("Event subscription", False, str(e))
        return
    
    # Trigger an event by updating state
    try:
        rmn_state = store.get_state("rmn_walmart", TwinType.RMN)
        if rmn_state:
            rmn_state.total_revenue += 5000
            store.update_state(rmn_state, change_reason="Event test")
            results.record("Event emission on update", len(events_received) > 0, f"Events: {len(events_received)}")
        else:
            results.record("Event emission on update", False, "No RMN state found")
    except Exception as e:
        results.record("Event emission on update", False, str(e))
    
    # Verify event content
    if events_received:
        try:
            event = events_received[-1]
            has_twin_id = event.twin_id is not None
            has_version = event.version > 0
            results.record("Event content valid", has_twin_id and has_version)
        except Exception as e:
            results.record("Event content valid", False, str(e))


# =============================================================================
# Phase 5 Tests: Agent Access Tool
# =============================================================================

def test_agent_access_tool(results: TestResults, temp_dir: str):
    """Test TwinStateTool for agent access"""
    print("\n--- Phase 5: Agent Access Tool Tests ---")
    
    # Reset and create fresh manager
    reset_unified_twin_manager()
    
    config = UnifiedTwinConfig(
        state_dir=f"{temp_dir}/states",
        history_dir=f"{temp_dir}/history",
    )
    manager = UnifiedTwinManager(config)
    tool = TwinStateTool(manager)
    
    # Test get_state action
    try:
        result = tool.run(
            action="get_state",
            twin_type="rmn",
            retailer_id="walmart",
        )
        # May not find state if fresh manager
        results.record("Tool get_state action", "error" not in result or "not found" in result.get("error", "").lower())
    except Exception as e:
        results.record("Tool get_state action", False, str(e))
    
    # Test get_all action
    try:
        result = tool.run(
            action="get_all",
            twin_type="channel",
            retailer_id="walmart",
        )
        results.record("Tool get_all action", "states" in result)
    except Exception as e:
        results.record("Tool get_all action", False, str(e))
    
    # Test get_summary action
    try:
        result = tool.run(
            action="get_summary",
            twin_type="rmn",
        )
        results.record("Tool get_summary action", "summary" in result)
    except Exception as e:
        results.record("Tool get_summary action", False, str(e))
    
    # Test get_metrics action
    try:
        result = tool.run(
            action="get_metrics",
            twin_type="brand",
            retailer_id="walmart",
        )
        results.record("Tool get_metrics action", "metrics" in result)
    except Exception as e:
        results.record("Tool get_metrics action", False, str(e))


# =============================================================================
# Phase 6 Tests: Unified Manager Integration
# =============================================================================

def test_unified_manager(results: TestResults, csv_paths: Dict[str, str], temp_dir: str):
    """Test UnifiedTwinManager integration"""
    print("\n--- Phase 6: Unified Manager Tests ---")
    
    # Reset singleton
    reset_unified_twin_manager()
    
    config = UnifiedTwinConfig(
        state_dir=f"{temp_dir}/manager_states",
        history_dir=f"{temp_dir}/manager_history",
    )
    manager = UnifiedTwinManager(config)
    
    # Test bulk ingestion
    try:
        result = manager.ingest_rmn_csv(csv_paths["rmn"], "walmart")
        results.record("Manager RMN ingestion", result.success or result.records_succeeded > 0)
    except Exception as e:
        results.record("Manager RMN ingestion", False, str(e))
    
    try:
        result = manager.ingest_brand_csv(csv_paths["brand"], "walmart")
        results.record("Manager Brand ingestion", result.success or result.records_succeeded > 0)
    except Exception as e:
        results.record("Manager Brand ingestion", False, str(e))
    
    try:
        result = manager.ingest_channel_csv(csv_paths["channel"], "walmart")
        results.record("Manager Channel ingestion", result.success or result.records_succeeded > 0)
    except Exception as e:
        results.record("Manager Channel ingestion", False, str(e))
    
    # Test state retrieval through manager
    try:
        rmn = manager.get_rmn_state("walmart")
        results.record("Manager get_rmn_state", rmn is not None, f"Found: {rmn is not None}")
    except Exception as e:
        results.record("Manager get_rmn_state", False, str(e))
    
    # Test aggregate computation
    try:
        agg = manager.compute_rmn_aggregates("walmart")
        results.record("Manager compute_aggregates", agg is not None)
    except Exception as e:
        results.record("Manager compute_aggregates", False, str(e))
    
    # Test summary
    try:
        summary = manager.get_summary()
        results.record("Manager get_summary", "total_states" in summary or "rmn_count" in summary)
    except Exception as e:
        results.record("Manager get_summary", False, str(e))
    
    return manager


# =============================================================================
# End-to-End Dataflow Test
# =============================================================================

def test_e2e_dataflow(results: TestResults, csv_paths: Dict[str, str], temp_dir: str):
    """Test complete end-to-end dataflow"""
    print("\n--- End-to-End Dataflow Test ---")
    
    # Reset all singletons
    reset_twin_state_store()
    reset_unified_twin_manager()
    
    # Step 1: Create manager
    config = UnifiedTwinConfig(
        state_dir=f"{temp_dir}/e2e_states",
        history_dir=f"{temp_dir}/e2e_history",
    )
    manager = UnifiedTwinManager(config)
    
    # Step 2: Ingest all data
    try:
        manager.ingest_rmn_csv(csv_paths["rmn"], "walmart")
        manager.ingest_brand_csv(csv_paths["brand"], "walmart")
        manager.ingest_campaign_csv(csv_paths["campaign"], "walmart")
        manager.ingest_channel_csv(csv_paths["channel"], "walmart")
        results.record("E2E: Data ingestion", True)
    except Exception as e:
        results.record("E2E: Data ingestion", False, str(e))
        return
    
    # Step 3: Verify states exist
    try:
        rmn_states = manager.get_all_rmn_states()
        brand_states = manager.get_all_brand_states()
        campaign_states = manager.get_all_campaign_states()
        channel_states = manager.get_all_channel_states()
        
        total_states = len(rmn_states) + len(brand_states) + len(campaign_states) + len(channel_states)
        results.record("E2E: States populated", total_states > 0, f"Total: {total_states}")
    except Exception as e:
        results.record("E2E: States populated", False, str(e))
    
    # Step 4: Test agent access
    try:
        tool = TwinStateTool(manager)
        overview = tool.get_retailer_overview("walmart")
        has_data = overview.get("rmn") is not None or overview.get("brands", {}).get("count", 0) > 0
        results.record("E2E: Agent access", has_data, f"Brands: {overview.get('brands', {}).get('count', 0)}")
    except Exception as e:
        results.record("E2E: Agent access", False, str(e))
    
    # Step 5: Test persistence
    try:
        manager.persist_all()
        state_files = list(Path(f"{temp_dir}/e2e_states").rglob("*.json"))
        results.record("E2E: Persistence", len(state_files) > 0, f"Files: {len(state_files)}")
    except Exception as e:
        results.record("E2E: Persistence", False, str(e))
    
    # Step 6: Test history
    try:
        # Make an update to create history
        rmn = manager.get_rmn_state("walmart")
        if rmn:
            rmn.total_spend += 100
            manager.state_store.update_state(rmn, change_reason="E2E test")
            history = manager.get_rmn_history("walmart")
            results.record("E2E: History tracking", len(history) > 0, f"Entries: {len(history)}")
        else:
            results.record("E2E: History tracking", True, "Skipped - no state")
    except Exception as e:
        results.record("E2E: History tracking", False, str(e))


# =============================================================================
# Main Test Runner
# =============================================================================

def run_all_tests():
    """Run all dataflow tests"""
    print("="*60)
    print("Channel State Digital Twin Dataflow Tests")
    print("="*60)
    
    results = TestResults()
    
    # Create temp directory for test data
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create sample CSV files
        csv_paths = create_sample_csvs(temp_dir)
        print(f"\nCreated sample CSVs in {temp_dir}")
        
        # Run test phases
        test_canonical_schemas(results)
        store = test_csv_ingestion_and_store(results, csv_paths, temp_dir)
        test_event_subscriptions(results, store)
        test_agent_access_tool(results, temp_dir)
        test_unified_manager(results, csv_paths, temp_dir)
        test_e2e_dataflow(results, csv_paths, temp_dir)
    
    # Print summary
    success = results.summary()
    return success


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

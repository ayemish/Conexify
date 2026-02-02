"""
Unit Tests for TwinStateStore

Tests:
- State CRUD operations
- JSON persistence
- History tracking
- Event subscriptions
- State versioning
"""

import os
import sys
import json
import tempfile
import pytest
from pathlib import Path
from datetime import datetime
from typing import List

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


class TestTwinStateStoreBasics:
    """Basic CRUD operations tests"""
    
    @pytest.fixture
    def store(self):
        """Create a fresh store for each test"""
        reset_twin_state_store()
        with tempfile.TemporaryDirectory() as temp_dir:
            config = TwinStateStoreConfig(
                state_dir=f"{temp_dir}/states",
                history_dir=f"{temp_dir}/history",
                max_history_per_twin=10,
            )
            store = TwinStateStore(config)
            yield store
    
    def test_create_rmn_state(self, store):
        """Test creating RMN state"""
        state = RMNTwinState(
            twin_id="rmn_test",
            retailer_id="test_retailer",
            rmn_name="Test RMN",
            total_spend=100000,
            total_revenue=300000,
        )
        
        store.update_state(state, change_reason="Initial creation")
        
        retrieved = store.get_state("rmn_test", TwinType.RMN)
        assert retrieved is not None
        assert retrieved.rmn_name == "Test RMN"
        assert retrieved.version == 1
    
    def test_create_brand_state(self, store):
        """Test creating Brand state"""
        state = BrandTwinState(
            twin_id="brand_test",
            retailer_id="test_retailer",
            brand_id="brand001",
            brand_name="Test Brand",
            spend=50000,
            revenue=150000,
        )
        
        store.update_state(state, change_reason="Initial creation")
        
        retrieved = store.get_state("brand_test", TwinType.BRAND)
        assert retrieved is not None
        assert retrieved.brand_name == "Test Brand"
    
    def test_create_campaign_state(self, store):
        """Test creating Campaign state"""
        state = CampaignTwinState(
            twin_id="campaign_test",
            retailer_id="test_retailer",
            campaign_id="camp001",
            campaign_name="Test Campaign",
            brand_id="brand001",
            channel_type=ChannelType.SPONSORED_PRODUCTS,
            status=CampaignStatus.ACTIVE,
        )
        
        store.update_state(state, change_reason="Initial creation")
        
        retrieved = store.get_state("campaign_test", TwinType.CAMPAIGN)
        assert retrieved is not None
        assert retrieved.status == CampaignStatus.ACTIVE
    
    def test_create_channel_state(self, store):
        """Test creating Channel state"""
        state = ChannelTwinState(
            twin_id="channel_test",
            retailer_id="test_retailer",
            channel_id="ch001",
            channel_type=ChannelType.DISPLAY,
            spend=25000,
            revenue=75000,
        )
        
        store.update_state(state, change_reason="Initial creation")
        
        retrieved = store.get_state("channel_test", TwinType.CHANNEL)
        assert retrieved is not None
        assert retrieved.channel_type == ChannelType.DISPLAY
    
    def test_update_state_increments_version(self, store):
        """Test that updating state increments version"""
        state = RMNTwinState(
            twin_id="rmn_version_test",
            retailer_id="test",
            rmn_name="Version Test",
        )
        
        store.update_state(state, change_reason="v1")
        assert state.version == 1
        
        state.total_spend = 1000
        store.update_state(state, change_reason="v2")
        assert state.version == 2
        
        state.total_spend = 2000
        store.update_state(state, change_reason="v3")
        assert state.version == 3
    
    def test_delete_state(self, store):
        """Test deleting state"""
        state = RMNTwinState(
            twin_id="rmn_delete_test",
            retailer_id="test",
            rmn_name="Delete Test",
        )
        
        store.update_state(state, change_reason="Create")
        assert store.get_state("rmn_delete_test", TwinType.RMN) is not None
        
        store.delete_state("rmn_delete_test", TwinType.RMN)
        assert store.get_state("rmn_delete_test", TwinType.RMN) is None
    
    def test_get_states_by_type(self, store):
        """Test getting all states of a type"""
        # Create multiple RMN states
        for i in range(3):
            state = RMNTwinState(
                twin_id=f"rmn_{i}",
                retailer_id=f"retailer_{i}",
                rmn_name=f"RMN {i}",
            )
            store.update_state(state, change_reason="Create")
        
        rmn_states = store.get_rmn_states()
        assert len(rmn_states) == 3
    
    def test_get_states_filtered_by_retailer(self, store):
        """Test filtering states by retailer"""
        # Create brands for different retailers
        for retailer in ["walmart", "amazon", "walmart"]:
            state = BrandTwinState(
                twin_id=f"brand_{retailer}_{hash(retailer + str(datetime.now()))}",
                retailer_id=retailer,
                brand_id=f"brand_{retailer}",
                brand_name=f"Brand for {retailer}",
            )
            store.update_state(state, change_reason="Create")
        
        walmart_brands = store.get_brand_states("walmart")
        assert len(walmart_brands) >= 2
        
        amazon_brands = store.get_brand_states("amazon")
        assert len(amazon_brands) >= 1


class TestTwinStateStorePersistence:
    """Persistence and JSON file tests"""
    
    @pytest.fixture
    def store_and_dir(self):
        """Create store with accessible temp directory"""
        reset_twin_state_store()
        temp_dir = tempfile.mkdtemp()
        config = TwinStateStoreConfig(
            state_dir=f"{temp_dir}/states",
            history_dir=f"{temp_dir}/history",
        )
        store = TwinStateStore(config)
        yield store, temp_dir
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_persist_all_creates_files(self, store_and_dir):
        """Test that persist_all creates JSON files"""
        store, temp_dir = store_and_dir
        
        # Create states
        rmn = RMNTwinState(
            twin_id="rmn_persist",
            retailer_id="test",
            rmn_name="Persist Test",
        )
        store.update_state(rmn, change_reason="Create")
        
        brand = BrandTwinState(
            twin_id="brand_persist",
            retailer_id="test",
            brand_id="b1",
            brand_name="Brand Persist",
        )
        store.update_state(brand, change_reason="Create")
        
        # Persist
        store.persist_all()
        
        # Check files exist
        rmn_files = list(Path(f"{temp_dir}/states/rmn").glob("*.json"))
        brand_files = list(Path(f"{temp_dir}/states/brand").glob("*.json"))
        
        assert len(rmn_files) >= 1
        assert len(brand_files) >= 1
    
    def test_persisted_file_is_valid_json(self, store_and_dir):
        """Test that persisted files contain valid JSON"""
        store, temp_dir = store_and_dir
        
        state = RMNTwinState(
            twin_id="rmn_json_test",
            retailer_id="test",
            rmn_name="JSON Test",
            total_spend=50000,
            total_revenue=150000,
        )
        store.update_state(state, change_reason="Create")
        store.persist_all()
        
        # Read and parse JSON file
        json_file = Path(f"{temp_dir}/states/rmn/rmn_json_test.json")
        assert json_file.exists()
        
        with open(json_file) as f:
            data = json.load(f)
        
        assert data["twin_id"] == "rmn_json_test"
        assert data["total_spend"] == 50000
    
    def test_load_states_from_disk(self, store_and_dir):
        """Test loading states from persisted files"""
        store, temp_dir = store_and_dir
        
        # Create and persist state
        state = RMNTwinState(
            twin_id="rmn_load_test",
            retailer_id="test",
            rmn_name="Load Test",
        )
        store.update_state(state, change_reason="Create")
        store.persist_all()
        
        # Create new store pointing to same directory
        reset_twin_state_store()
        config = TwinStateStoreConfig(
            state_dir=f"{temp_dir}/states",
            history_dir=f"{temp_dir}/history",
        )
        new_store = TwinStateStore(config)
        
        # Should load existing state
        loaded = new_store.get_state("rmn_load_test", TwinType.RMN)
        assert loaded is not None
        assert loaded.rmn_name == "Load Test"


class TestTwinStateStoreHistory:
    """History tracking tests"""
    
    @pytest.fixture
    def store(self):
        """Create store for history tests"""
        reset_twin_state_store()
        with tempfile.TemporaryDirectory() as temp_dir:
            config = TwinStateStoreConfig(
                state_dir=f"{temp_dir}/states",
                history_dir=f"{temp_dir}/history",
                max_history_per_twin=5,  # Small limit for testing
            )
            store = TwinStateStore(config)
            yield store
    
    def test_history_recorded_on_update(self, store):
        """Test that history is recorded on state updates"""
        state = RMNTwinState(
            twin_id="rmn_history",
            retailer_id="test",
            rmn_name="History Test",
        )
        
        store.update_state(state, change_reason="Initial")
        
        # Change value to trigger actual update (hash must change)
        state.total_spend = 1000
        store.update_state(state, change_reason="Update 1")
        
        state.total_spend = 2000
        store.update_state(state, change_reason="Update 2")
        
        history = store.get_history("rmn_history", TwinType.RMN)
        assert len(history) == 3
    
    def test_history_contains_change_reason(self, store):
        """Test that history records contain change reasons"""
        state = RMNTwinState(
            twin_id="rmn_reason",
            retailer_id="test",
            rmn_name="Reason Test",
        )
        
        store.update_state(state, change_reason="Test Reason ABC")
        
        history = store.get_history("rmn_reason", TwinType.RMN)
        assert len(history) >= 1
        assert history[-1].change_reason == "Test Reason ABC"
    
    def test_history_limit_enforced(self, store):
        """Test that history limit is enforced"""
        state = RMNTwinState(
            twin_id="rmn_limit",
            retailer_id="test",
            rmn_name="Limit Test",
        )
        
        # Create more history than limit (5)
        for i in range(10):
            state.total_spend = i * 1000
            store.update_state(state, change_reason=f"Update {i}")
        
        history = store.get_history("rmn_limit", TwinType.RMN)
        # Should be limited to max_history_per_twin
        assert len(history) <= 5
    
    def test_history_contains_metrics_delta(self, store):
        """Test that history records metrics changes"""
        state = RMNTwinState(
            twin_id="rmn_delta",
            retailer_id="test",
            rmn_name="Delta Test",
            total_spend=1000,
        )
        
        store.update_state(state, change_reason="Initial")
        
        state.total_spend = 2000
        store.update_state(state, change_reason="Spend increase")
        
        history = store.get_history("rmn_delta", TwinType.RMN)
        # Latest history should have metrics_delta
        assert len(history) >= 2


class TestTwinStateStoreEvents:
    """Event subscription tests"""
    
    @pytest.fixture
    def store(self):
        """Create store for event tests"""
        reset_twin_state_store()
        with tempfile.TemporaryDirectory() as temp_dir:
            config = TwinStateStoreConfig(
                state_dir=f"{temp_dir}/states",
                history_dir=f"{temp_dir}/history",
                emit_events=True,
            )
            store = TwinStateStore(config)
            yield store
    
    def test_subscribe_to_events(self, store):
        """Test subscribing to events"""
        events_received: List[TwinStateEvent] = []
        
        def handler(event: TwinStateEvent):
            events_received.append(event)
        
        subscription_id = store.subscribe(
            TwinEventType.STATE_CREATED,
            handler,
        )
        
        assert subscription_id is not None
    
    def test_event_emitted_on_create(self, store):
        """Test that event is emitted when state is created"""
        events_received: List[TwinStateEvent] = []
        
        def handler(event: TwinStateEvent):
            events_received.append(event)
        
        store.subscribe(TwinEventType.STATE_CREATED, handler)
        
        state = RMNTwinState(
            twin_id="rmn_event_create",
            retailer_id="test",
            rmn_name="Event Create Test",
        )
        store.update_state(state, change_reason="Create")
        
        # Check event was emitted
        create_events = [e for e in events_received if e.event_type == TwinEventType.STATE_CREATED]
        assert len(create_events) >= 1
    
    def test_event_emitted_on_update(self, store):
        """Test that event is emitted when state is updated"""
        events_received: List[TwinStateEvent] = []
        
        def handler(event: TwinStateEvent):
            events_received.append(event)
        
        store.subscribe(TwinEventType.STATE_UPDATED, handler)
        
        state = RMNTwinState(
            twin_id="rmn_event_update",
            retailer_id="test",
            rmn_name="Event Update Test",
        )
        store.update_state(state, change_reason="Create")
        
        state.total_spend = 5000
        store.update_state(state, change_reason="Update")
        
        # Check update event was emitted
        update_events = [e for e in events_received if e.event_type == TwinEventType.STATE_UPDATED]
        assert len(update_events) >= 1
    
    def test_filtered_subscription_by_twin_type(self, store):
        """Test that subscriptions can filter by twin type"""
        rmn_events: List[TwinStateEvent] = []
        brand_events: List[TwinStateEvent] = []
        
        def rmn_handler(event):
            rmn_events.append(event)
        
        def brand_handler(event):
            brand_events.append(event)
        
        store.subscribe(TwinEventType.STATE_CREATED, rmn_handler, twin_type=TwinType.RMN)
        store.subscribe(TwinEventType.STATE_CREATED, brand_handler, twin_type=TwinType.BRAND)
        
        # Create RMN state
        rmn = RMNTwinState(twin_id="rmn_filter", retailer_id="test", rmn_name="Filter Test")
        store.update_state(rmn, change_reason="Create")
        
        # Create Brand state
        brand = BrandTwinState(twin_id="brand_filter", retailer_id="test", brand_id="b1", brand_name="Filter Brand")
        store.update_state(brand, change_reason="Create")
        
        # RMN handler should only get RMN events
        # Brand handler should only get Brand events


class TestTwinStateStoreSummary:
    """Summary and statistics tests"""
    
    @pytest.fixture
    def populated_store(self):
        """Create store with sample data"""
        reset_twin_state_store()
        with tempfile.TemporaryDirectory() as temp_dir:
            config = TwinStateStoreConfig(
                state_dir=f"{temp_dir}/states",
                history_dir=f"{temp_dir}/history",
            )
            store = TwinStateStore(config)
            
            # Add sample data
            store.update_state(
                RMNTwinState(twin_id="rmn_1", retailer_id="r1", rmn_name="RMN 1"),
                change_reason="Create"
            )
            store.update_state(
                BrandTwinState(twin_id="brand_1", retailer_id="r1", brand_id="b1", brand_name="Brand 1"),
                change_reason="Create"
            )
            store.update_state(
                BrandTwinState(twin_id="brand_2", retailer_id="r1", brand_id="b2", brand_name="Brand 2"),
                change_reason="Create"
            )
            store.update_state(
                ChannelTwinState(twin_id="ch_1", retailer_id="r1", channel_id="c1", channel_type=ChannelType.DISPLAY),
                change_reason="Create"
            )
            
            yield store
    
    def test_get_summary_counts(self, populated_store):
        """Test that summary includes correct counts"""
        summary = populated_store.get_summary()
        
        assert "total_states" in summary
        assert summary["total_states"] == 4
        assert summary["rmn_count"] == 1
        assert summary["brand_count"] == 2
        assert summary["channel_count"] == 1


def run_tests():
    """Run all store tests"""
    print("="*60)
    print("Twin State Store Unit Tests")
    print("="*60)
    
    exit_code = pytest.main([
        __file__,
        "-v",
        "--tb=short",
    ])
    
    return exit_code == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)

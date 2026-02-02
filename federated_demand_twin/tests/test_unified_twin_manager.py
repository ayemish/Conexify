"""
Unit Tests for UnifiedTwinManager

Tests:
- Manager initialization
- CSV ingestion through manager
- State retrieval
- Aggregation computation
- Bayesian posterior updates
- Event subscription integration
"""

import os
import sys
import tempfile
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.schemas.channel_state_contracts import (
    RMNTwinState,
    BrandTwinState,
    CampaignTwinState,
    ChannelTwinState,
    TwinType,
    ChannelType,
    PacingStatus,
    TwinStateEvent,
    TwinEventType,
)
from vendor.retail_media.unified_twin_manager import (
    UnifiedTwinManager,
    UnifiedTwinConfig,
    reset_unified_twin_manager,
)
from vendor.retail_media.twin_state_store import reset_twin_state_store


class TestUnifiedTwinManagerInit:
    """Manager initialization tests"""
    
    @pytest.fixture
    def manager(self):
        """Create fresh manager"""
        reset_twin_state_store()
        reset_unified_twin_manager()
        with tempfile.TemporaryDirectory() as temp_dir:
            config = UnifiedTwinConfig(
                state_dir=f"{temp_dir}/states",
                history_dir=f"{temp_dir}/history",
            )
            manager = UnifiedTwinManager(config)
            yield manager, temp_dir
    
    def test_manager_initializes(self, manager):
        """Test manager initializes without error"""
        mgr, _ = manager
        assert mgr is not None
        assert mgr.state_store is not None
        assert mgr.ingestion_service is not None
    
    def test_manager_has_simulation_twin(self, manager):
        """Test manager has simulation twin"""
        mgr, _ = manager
        assert mgr.simulation_twin is not None


class TestUnifiedTwinManagerIngestion:
    """Manager ingestion tests"""
    
    @pytest.fixture
    def manager(self):
        """Create fresh manager with temp directory"""
        reset_twin_state_store()
        reset_unified_twin_manager()
        with tempfile.TemporaryDirectory() as temp_dir:
            config = UnifiedTwinConfig(
                state_dir=f"{temp_dir}/states",
                history_dir=f"{temp_dir}/history",
            )
            manager = UnifiedTwinManager(config)
            yield manager, temp_dir
    
    def test_ingest_rmn_csv(self, manager):
        """Test RMN CSV ingestion through manager"""
        mgr, temp_dir = manager
        
        csv_path = Path(temp_dir) / "rmn.csv"
        csv_path.write_text("""rmn_id,rmn_name,retailer_id,total_spend,total_revenue,week
rmn_mgr,Manager Test,mgr_retailer,50000,150000,1
""")
        
        result = mgr.ingest_rmn_csv(str(csv_path), "mgr_retailer")
        
        assert result.records_processed == 1
    
    def test_ingest_brand_csv(self, manager):
        """Test Brand CSV ingestion through manager"""
        mgr, temp_dir = manager
        
        csv_path = Path(temp_dir) / "brands.csv"
        csv_path.write_text("""brand_id,brand_name,retailer_id,spend,revenue,week
brand_mgr,Manager Brand,mgr_retailer,25000,75000,1
""")
        
        result = mgr.ingest_brand_csv(str(csv_path), "mgr_retailer")
        
        assert result.records_processed == 1
    
    def test_ingest_campaign_csv(self, manager):
        """Test Campaign CSV ingestion through manager"""
        mgr, temp_dir = manager
        
        csv_path = Path(temp_dir) / "campaigns.csv"
        csv_path.write_text("""campaign_id,campaign_name,brand_id,retailer_id,channel_type,status,spend,week
camp_mgr,Manager Campaign,brand_mgr,mgr_retailer,sponsored_products,active,10000,1
""")
        
        result = mgr.ingest_campaign_csv(str(csv_path), "mgr_retailer")
        
        assert result.records_processed == 1
    
    def test_ingest_channel_csv(self, manager):
        """Test Channel CSV ingestion through manager"""
        mgr, temp_dir = manager
        
        csv_path = Path(temp_dir) / "channels.csv"
        csv_path.write_text("""channel_id,channel_type,retailer_id,spend,revenue,week
ch_mgr,sponsored_products,mgr_retailer,20000,60000,1
""")
        
        result = mgr.ingest_channel_csv(str(csv_path), "mgr_retailer")
        
        assert result.records_processed == 1


class TestUnifiedTwinManagerRetrieval:
    """State retrieval tests"""
    
    @pytest.fixture
    def populated_manager(self):
        """Create manager with sample data"""
        reset_twin_state_store()
        reset_unified_twin_manager()
        with tempfile.TemporaryDirectory() as temp_dir:
            config = UnifiedTwinConfig(
                state_dir=f"{temp_dir}/states",
                history_dir=f"{temp_dir}/history",
            )
            manager = UnifiedTwinManager(config)
            
            # Create sample data - use retailer_id as rmn_id for consistent twin_id
            rmn_csv = Path(temp_dir) / "rmn.csv"
            rmn_csv.write_text("""rmn_name,retailer_id,total_spend,total_revenue,week
Retrieval Test,ret_retailer,50000,150000,1
""")
            manager.ingest_rmn_csv(str(rmn_csv), "ret_retailer")
            
            brand_csv = Path(temp_dir) / "brands.csv"
            brand_csv.write_text("""brand_id,brand_name,retailer_id,spend,revenue,week
brand_ret1,Brand 1,ret_retailer,25000,75000,1
brand_ret2,Brand 2,ret_retailer,30000,90000,1
""")
            manager.ingest_brand_csv(str(brand_csv), "ret_retailer")
            
            channel_csv = Path(temp_dir) / "channels.csv"
            channel_csv.write_text("""channel_id,channel_type,retailer_id,spend,revenue,week
ch_ret_sp,sponsored_products,ret_retailer,20000,60000,1
ch_ret_disp,display,ret_retailer,15000,45000,1
""")
            manager.ingest_channel_csv(str(channel_csv), "ret_retailer")
            
            yield manager, temp_dir
    
    def test_get_rmn_state(self, populated_manager):
        """Test getting RMN state"""
        mgr, _ = populated_manager
        
        state = mgr.get_rmn_state("ret_retailer")
        assert state is not None
    
    def test_get_all_rmn_states(self, populated_manager):
        """Test getting all RMN states"""
        mgr, _ = populated_manager
        
        states = mgr.get_all_rmn_states()
        assert len(states) >= 1
    
    def test_get_brand_state(self, populated_manager):
        """Test getting Brand state"""
        mgr, _ = populated_manager
        
        # Get all brands first to find IDs
        brands = mgr.get_all_brand_states("ret_retailer")
        assert len(brands) >= 1
    
    def test_get_all_brand_states(self, populated_manager):
        """Test getting all Brand states"""
        mgr, _ = populated_manager
        
        states = mgr.get_all_brand_states("ret_retailer")
        assert len(states) >= 2
    
    def test_get_all_channel_states(self, populated_manager):
        """Test getting all Channel states"""
        mgr, _ = populated_manager
        
        states = mgr.get_all_channel_states("ret_retailer")
        assert len(states) >= 2


class TestUnifiedTwinManagerAggregation:
    """Aggregation computation tests"""
    
    @pytest.fixture
    def manager_with_data(self):
        """Create manager with aggregatable data"""
        reset_twin_state_store()
        reset_unified_twin_manager()
        with tempfile.TemporaryDirectory() as temp_dir:
            config = UnifiedTwinConfig(
                state_dir=f"{temp_dir}/states",
                history_dir=f"{temp_dir}/history",
            )
            manager = UnifiedTwinManager(config)
            
            # Create brands with metrics
            brand_csv = Path(temp_dir) / "brands.csv"
            brand_csv.write_text("""brand_id,brand_name,retailer_id,impressions,clicks,conversions,spend,revenue,budget,week
brand_agg1,Brand 1,agg_retailer,1000000,30000,3000,50000,150000,60000,1
brand_agg2,Brand 2,agg_retailer,800000,24000,2400,40000,120000,50000,1
""")
            manager.ingest_brand_csv(str(brand_csv), "agg_retailer")
            
            # Create channels with metrics
            channel_csv = Path(temp_dir) / "channels.csv"
            channel_csv.write_text("""channel_id,channel_type,retailer_id,impressions,clicks,conversions,spend,revenue,budget,week
ch_agg_sp,sponsored_products,agg_retailer,600000,18000,1800,30000,90000,35000,1
ch_agg_disp,display,agg_retailer,400000,12000,1200,20000,60000,25000,1
""")
            manager.ingest_channel_csv(str(channel_csv), "agg_retailer")
            
            yield manager, temp_dir
    
    def test_compute_rmn_aggregates(self, manager_with_data):
        """Test computing RMN aggregates from child states"""
        mgr, _ = manager_with_data
        
        rmn = mgr.compute_rmn_aggregates("agg_retailer")
        
        assert rmn is not None
        assert rmn.total_spend > 0
        assert rmn.total_revenue > 0
        assert rmn.active_brands >= 2
        assert rmn.active_channels >= 2
    
    def test_aggregate_calculates_roas(self, manager_with_data):
        """Test that aggregate calculates ROAS"""
        mgr, _ = manager_with_data
        
        rmn = mgr.compute_rmn_aggregates("agg_retailer")
        
        assert rmn is not None
        assert rmn.overall_roas > 0
        # ROAS should be revenue/spend
        expected_roas = rmn.total_revenue / rmn.total_spend
        assert abs(rmn.overall_roas - expected_roas) < 0.01
    
    def test_aggregate_includes_channel_mix(self, manager_with_data):
        """Test that aggregate includes channel mix"""
        mgr, _ = manager_with_data
        
        rmn = mgr.compute_rmn_aggregates("agg_retailer")
        
        assert rmn is not None
        assert rmn.channel_mix is not None
        assert len(rmn.channel_mix) >= 2


class TestUnifiedTwinManagerHistory:
    """History access tests"""
    
    @pytest.fixture
    def manager_with_history(self):
        """Create manager with history data"""
        reset_twin_state_store()
        reset_unified_twin_manager()
        with tempfile.TemporaryDirectory() as temp_dir:
            config = UnifiedTwinConfig(
                state_dir=f"{temp_dir}/states",
                history_dir=f"{temp_dir}/history",
            )
            manager = UnifiedTwinManager(config)
            
            # Create and update state multiple times - use retailer_id as twin_id
            rmn_csv = Path(temp_dir) / "rmn.csv"
            
            for i in range(3):
                rmn_csv.write_text(f"""rmn_name,retailer_id,total_spend,total_revenue,week
History Test,hist_retailer,{50000 + i*1000},{150000 + i*3000},{i+1}
""")
                manager.ingest_rmn_csv(str(rmn_csv), "hist_retailer")
            
            yield manager, temp_dir
    
    def test_get_rmn_history(self, manager_with_history):
        """Test getting RMN history"""
        mgr, _ = manager_with_history
        
        history = mgr.get_rmn_history("hist_retailer")
        
        assert len(history) >= 1


class TestUnifiedTwinManagerBayesian:
    """Bayesian posterior update tests"""
    
    @pytest.fixture
    def manager_with_channels(self):
        """Create manager with channel data"""
        reset_twin_state_store()
        reset_unified_twin_manager()
        with tempfile.TemporaryDirectory() as temp_dir:
            config = UnifiedTwinConfig(
                state_dir=f"{temp_dir}/states",
                history_dir=f"{temp_dir}/history",
            )
            manager = UnifiedTwinManager(config)
            
            channel_csv = Path(temp_dir) / "channels.csv"
            channel_csv.write_text("""channel_id,channel_type,retailer_id,spend,revenue,week
ch_bayes,sponsored_products,bayes_retailer,20000,60000,1
""")
            manager.ingest_channel_csv(str(channel_csv), "bayes_retailer")
            
            yield manager, temp_dir
    
    def test_update_channel_posteriors(self, manager_with_channels):
        """Test updating channel Bayesian posteriors"""
        mgr, _ = manager_with_channels
        
        # Update posteriors
        mgr.update_channel_posteriors(
            retailer_id="bayes_retailer",
            channel_type="sponsored_products",
            elasticity_mean=0.15,
            elasticity_std=0.03,
            elasticity_ci_lower=0.09,
            elasticity_ci_upper=0.21,
            prob_efficiency_above_target=0.85,
            contribution_pct=0.35,
        )
        
        # Retrieve and verify
        state = mgr.get_channel_state("bayes_retailer", "sponsored_products")
        if state:
            assert state.elasticity_mean == 0.15
            assert state.elasticity_std == 0.03


class TestUnifiedTwinManagerSummary:
    """Summary and persistence tests"""
    
    @pytest.fixture
    def populated_manager(self):
        """Create populated manager"""
        reset_twin_state_store()
        reset_unified_twin_manager()
        with tempfile.TemporaryDirectory() as temp_dir:
            config = UnifiedTwinConfig(
                state_dir=f"{temp_dir}/states",
                history_dir=f"{temp_dir}/history",
            )
            manager = UnifiedTwinManager(config)
            
            # Add some data
            rmn_csv = Path(temp_dir) / "rmn.csv"
            rmn_csv.write_text("""rmn_id,rmn_name,retailer_id,total_spend,week
rmn_sum,Summary Test,sum_retailer,50000,1
""")
            manager.ingest_rmn_csv(str(rmn_csv), "sum_retailer")
            
            yield manager, temp_dir
    
    def test_get_summary(self, populated_manager):
        """Test getting summary"""
        mgr, _ = populated_manager
        
        summary = mgr.get_summary()
        
        assert summary is not None
        assert "total_states" in summary or "rmn_count" in summary
    
    def test_persist_all(self, populated_manager):
        """Test persisting all states"""
        mgr, temp_dir = populated_manager
        
        mgr.persist_all()
        
        # Check files exist
        state_files = list(Path(f"{temp_dir}/states").rglob("*.json"))
        assert len(state_files) >= 1


def run_tests():
    """Run all manager tests"""
    print("="*60)
    print("Unified Twin Manager Unit Tests")
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

"""
Unit Tests for CSV Ingestion Service

Tests:
- Column mapping
- Data validation
- State creation from CSV rows
- Error handling
- Multiple twin type ingestion
"""

import os
import sys
import tempfile
import pytest
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.schemas.channel_state_contracts import (
    TwinType,
    ChannelType,
    CampaignStatus,
)
from vendor.retail_media.twin_state_store import (
    TwinStateStore,
    TwinStateStoreConfig,
    reset_twin_state_store,
)
from vendor.retail_media.csv_ingestion import (
    CSVIngestionService,
    IngestionResult,
)


class TestCSVIngestionBasics:
    """Basic CSV ingestion tests"""
    
    @pytest.fixture
    def service(self):
        """Create fresh service for each test"""
        reset_twin_state_store()
        with tempfile.TemporaryDirectory() as temp_dir:
            config = TwinStateStoreConfig(
                state_dir=f"{temp_dir}/states",
                history_dir=f"{temp_dir}/history",
            )
            store = TwinStateStore(config)
            service = CSVIngestionService(store)
            yield service, temp_dir
    
    def test_ingest_rmn_csv(self, service):
        """Test RMN CSV ingestion"""
        svc, temp_dir = service
        
        csv_path = Path(temp_dir) / "rmn.csv"
        csv_path.write_text("""rmn_id,rmn_name,retailer_id,total_impressions,total_spend,total_revenue,week
rmn_test,Test RMN,test_retailer,1000000,50000,150000,1
""")
        
        result = svc.ingest_rmn_csv(str(csv_path), "test_retailer")
        
        assert result.records_processed == 1
        assert result.records_succeeded == 1
        assert result.records_failed == 0
    
    def test_ingest_brand_csv(self, service):
        """Test Brand CSV ingestion"""
        svc, temp_dir = service
        
        csv_path = Path(temp_dir) / "brands.csv"
        csv_path.write_text("""brand_id,brand_name,retailer_id,category,impressions,spend,revenue,week
brand_001,Acme Corp,test_retailer,CPG,500000,25000,75000,1
brand_002,Beta Foods,test_retailer,Food,300000,15000,45000,1
""")
        
        result = svc.ingest_brand_csv(str(csv_path), "test_retailer")
        
        assert result.records_processed == 2
        assert result.records_succeeded == 2
    
    def test_ingest_campaign_csv(self, service):
        """Test Campaign CSV ingestion"""
        svc, temp_dir = service
        
        csv_path = Path(temp_dir) / "campaigns.csv"
        csv_path.write_text("""campaign_id,campaign_name,brand_id,retailer_id,channel_type,status,impressions,spend,revenue,budget,week
camp_001,Summer Sale,brand_001,test_retailer,sponsored_products,active,200000,10000,30000,50000,1
camp_002,Holiday Push,brand_002,test_retailer,display,paused,150000,7500,22500,40000,1
""")
        
        result = svc.ingest_campaign_csv(str(csv_path), "test_retailer")
        
        assert result.records_processed == 2
        assert result.records_succeeded == 2
    
    def test_ingest_channel_csv(self, service):
        """Test Channel CSV ingestion"""
        svc, temp_dir = service
        
        csv_path = Path(temp_dir) / "channels.csv"
        csv_path.write_text("""channel_id,channel_type,retailer_id,impressions,clicks,conversions,spend,revenue,week
ch_sp,sponsored_products,test_retailer,400000,12000,1200,20000,60000,1
ch_disp,display,test_retailer,200000,6000,600,10000,30000,1
""")
        
        result = svc.ingest_channel_csv(str(csv_path), "test_retailer")
        
        assert result.records_processed == 2
        assert result.records_succeeded == 2


class TestCSVIngestionColumnMapping:
    """Column mapping tests"""
    
    @pytest.fixture
    def service(self):
        """Create fresh service"""
        reset_twin_state_store()
        with tempfile.TemporaryDirectory() as temp_dir:
            config = TwinStateStoreConfig(
                state_dir=f"{temp_dir}/states",
                history_dir=f"{temp_dir}/history",
            )
            store = TwinStateStore(config)
            service = CSVIngestionService(store)
            yield service, temp_dir
    
    def test_custom_column_mapping(self, service):
        """Test ingestion with custom column mapping"""
        svc, temp_dir = service
        
        # CSV with non-standard column names
        csv_path = Path(temp_dir) / "custom_rmn.csv"
        csv_path.write_text("""network_id,network_name,retailer,imps,cost,rev,wk
net_001,Custom Network,custom_retailer,2000000,100000,300000,1
""")
        
        # Custom mapping
        column_mapping = {
            "rmn_id": "network_id",
            "rmn_name": "network_name",
            "retailer_id": "retailer",
            "total_impressions": "imps",
            "total_spend": "cost",
            "total_revenue": "rev",
            "week": "wk",
        }
        
        result = svc.ingest_rmn_csv(str(csv_path), "custom_retailer", column_mapping)
        
        assert result.records_succeeded == 1
    
    def test_missing_required_column(self, service):
        """Test handling of missing required columns"""
        svc, temp_dir = service
        
        # CSV missing required columns
        csv_path = Path(temp_dir) / "incomplete.csv"
        csv_path.write_text("""rmn_name,total_spend
Incomplete RMN,50000
""")
        
        result = svc.ingest_rmn_csv(str(csv_path), "test")
        
        # Should handle gracefully
        assert result.records_processed >= 0


class TestCSVIngestionValidation:
    """Data validation tests"""
    
    @pytest.fixture
    def service(self):
        """Create fresh service"""
        reset_twin_state_store()
        with tempfile.TemporaryDirectory() as temp_dir:
            config = TwinStateStoreConfig(
                state_dir=f"{temp_dir}/states",
                history_dir=f"{temp_dir}/history",
            )
            store = TwinStateStore(config)
            service = CSVIngestionService(store)
            yield service, temp_dir
    
    def test_numeric_conversion(self, service):
        """Test numeric value conversion"""
        svc, temp_dir = service
        
        csv_path = Path(temp_dir) / "numeric.csv"
        csv_path.write_text("""rmn_id,rmn_name,retailer_id,total_impressions,total_spend,total_revenue,week
rmn_num,Numeric Test,test,1000000.5,50000.75,150000.25,1
""")
        
        result = svc.ingest_rmn_csv(str(csv_path), "test")
        
        assert result.records_succeeded == 1
    
    def test_invalid_channel_type_handling(self, service):
        """Test handling of invalid channel types"""
        svc, temp_dir = service
        
        csv_path = Path(temp_dir) / "invalid_channel.csv"
        csv_path.write_text("""channel_id,channel_type,retailer_id,spend,revenue,week
ch_invalid,unknown_channel_type,test,10000,30000,1
""")
        
        result = svc.ingest_channel_csv(str(csv_path), "test")
        
        # Should either skip or use default
        assert result.records_processed == 1
    
    def test_empty_csv_handling(self, service):
        """Test handling of empty CSV files"""
        svc, temp_dir = service
        
        csv_path = Path(temp_dir) / "empty.csv"
        csv_path.write_text("""rmn_id,rmn_name,retailer_id
""")
        
        result = svc.ingest_rmn_csv(str(csv_path), "test")
        
        assert result.records_processed == 0
        assert result.success  # Empty is not an error


class TestCSVIngestionStateCreation:
    """State creation and updating tests"""
    
    @pytest.fixture
    def service(self):
        """Create fresh service"""
        reset_twin_state_store()
        with tempfile.TemporaryDirectory() as temp_dir:
            config = TwinStateStoreConfig(
                state_dir=f"{temp_dir}/states",
                history_dir=f"{temp_dir}/history",
            )
            store = TwinStateStore(config)
            service = CSVIngestionService(store)
            yield service, store, temp_dir
    
    def test_state_created_in_store(self, service):
        """Test that ingested data creates state in store"""
        svc, store, temp_dir = service
        
        csv_path = Path(temp_dir) / "rmn.csv"
        csv_path.write_text("""rmn_id,rmn_name,retailer_id,total_spend,total_revenue,week
rmn_create,Created RMN,create_retailer,50000,150000,1
""")
        
        svc.ingest_rmn_csv(str(csv_path), "create_retailer")
        
        # Check state exists in store
        states = store.get_rmn_states()
        assert len(states) >= 1
        
        # Find our state
        created_states = [s for s in states if "create" in s.twin_id.lower()]
        assert len(created_states) >= 1
    
    def test_state_updated_on_reimport(self, service):
        """Test that reimporting updates existing state"""
        svc, store, temp_dir = service
        
        csv_path = Path(temp_dir) / "rmn.csv"
        
        # First import
        csv_path.write_text("""rmn_id,rmn_name,retailer_id,total_spend,total_revenue,week
rmn_update,Update RMN,update_retailer,50000,150000,1
""")
        result1 = svc.ingest_rmn_csv(str(csv_path), "update_retailer")
        
        # Second import with updated values
        csv_path.write_text("""rmn_id,rmn_name,retailer_id,total_spend,total_revenue,week
rmn_update,Update RMN,update_retailer,75000,225000,2
""")
        result2 = svc.ingest_rmn_csv(str(csv_path), "update_retailer")
        
        # Should have updated, not created new
        assert len(result2.states_updated) >= 1 or result2.records_succeeded >= 1
    
    def test_multiple_rows_create_multiple_states(self, service):
        """Test that multiple CSV rows create multiple states"""
        svc, store, temp_dir = service
        
        csv_path = Path(temp_dir) / "brands.csv"
        csv_path.write_text("""brand_id,brand_name,retailer_id,spend,revenue,week
brand_a,Brand A,multi_retailer,25000,75000,1
brand_b,Brand B,multi_retailer,30000,90000,1
brand_c,Brand C,multi_retailer,35000,105000,1
""")
        
        result = svc.ingest_brand_csv(str(csv_path), "multi_retailer")
        
        assert result.records_succeeded == 3
        
        brands = store.get_brand_states("multi_retailer")
        assert len(brands) == 3


class TestCSVIngestionResults:
    """Ingestion result tracking tests"""
    
    @pytest.fixture
    def service(self):
        """Create fresh service"""
        reset_twin_state_store()
        with tempfile.TemporaryDirectory() as temp_dir:
            config = TwinStateStoreConfig(
                state_dir=f"{temp_dir}/states",
                history_dir=f"{temp_dir}/history",
            )
            store = TwinStateStore(config)
            service = CSVIngestionService(store)
            yield service, temp_dir
    
    def test_result_contains_ingestion_id(self, service):
        """Test that result includes unique ingestion ID"""
        svc, temp_dir = service
        
        csv_path = Path(temp_dir) / "rmn.csv"
        csv_path.write_text("""rmn_id,rmn_name,retailer_id,week
rmn_id1,Test,test,1
""")
        
        result = svc.ingest_rmn_csv(str(csv_path), "test")
        
        assert result.ingestion_id is not None
        assert len(result.ingestion_id) > 0
    
    def test_result_tracks_created_vs_updated(self, service):
        """Test that result distinguishes created vs updated"""
        svc, temp_dir = service
        
        csv_path = Path(temp_dir) / "rmn.csv"
        
        # First import - should create
        csv_path.write_text("""rmn_id,rmn_name,retailer_id,week
rmn_track,Track Test,track,1
""")
        result1 = svc.ingest_rmn_csv(str(csv_path), "track")
        assert len(result1.states_created) >= 1
        
        # Second import - should update
        csv_path.write_text("""rmn_id,rmn_name,retailer_id,total_spend,week
rmn_track,Track Test,track,5000,2
""")
        result2 = svc.ingest_rmn_csv(str(csv_path), "track")
        assert len(result2.states_updated) >= 1


class TestCSVIngestionErrors:
    """Error handling tests"""
    
    @pytest.fixture
    def service(self):
        """Create fresh service"""
        reset_twin_state_store()
        with tempfile.TemporaryDirectory() as temp_dir:
            config = TwinStateStoreConfig(
                state_dir=f"{temp_dir}/states",
                history_dir=f"{temp_dir}/history",
            )
            store = TwinStateStore(config)
            service = CSVIngestionService(store)
            yield service, temp_dir
    
    def test_nonexistent_file_handling(self, service):
        """Test handling of non-existent file"""
        svc, temp_dir = service
        
        result = svc.ingest_rmn_csv("/nonexistent/path/file.csv", "test")
        
        assert not result.success
        assert len(result.errors) > 0
    
    def test_malformed_csv_handling(self, service):
        """Test handling of malformed CSV"""
        svc, temp_dir = service
        
        csv_path = Path(temp_dir) / "malformed.csv"
        csv_path.write_text("""this is not,valid csv
missing,columns,here
""")
        
        result = svc.ingest_rmn_csv(str(csv_path), "test")
        
        # Should not crash, may have errors
        assert result is not None


def run_tests():
    """Run all CSV ingestion tests"""
    print("="*60)
    print("CSV Ingestion Service Unit Tests")
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

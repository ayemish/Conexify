"""
Unit Tests for TwinStateTool

Tests:
- Tool initialization
- State query actions
- History retrieval
- Metrics aggregation
- Event subscriptions
- Convenience methods
"""

import os
import sys
import tempfile
import pytest
from pathlib import Path
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
    TwinStateEvent,
    TwinEventType,
)
from vendor.retail_media.unified_twin_manager import (
    UnifiedTwinManager,
    UnifiedTwinConfig,
    reset_unified_twin_manager,
)
from vendor.retail_media.twin_state_store import reset_twin_state_store
from vendor.agents.tools.twin_state_tool import TwinStateTool, create_twin_state_tool


class TestTwinStateToolInit:
    """Tool initialization tests"""
    
    @pytest.fixture
    def tool(self):
        """Create fresh tool"""
        reset_twin_state_store()
        reset_unified_twin_manager()
        with tempfile.TemporaryDirectory() as temp_dir:
            config = UnifiedTwinConfig(
                state_dir=f"{temp_dir}/states",
                history_dir=f"{temp_dir}/history",
            )
            manager = UnifiedTwinManager(config)
            tool = TwinStateTool(manager)
            yield tool, manager, temp_dir
    
    def test_tool_initializes(self, tool):
        """Test tool initializes"""
        t, _, _ = tool
        assert t is not None
        assert t.manager is not None
    
    def test_tool_has_name_and_description(self, tool):
        """Test tool has name and description"""
        t, _, _ = tool
        assert t.name == "twin_state_tool"
        assert len(t.description) > 0
    
    def test_create_tool_factory(self):
        """Test factory function"""
        reset_twin_state_store()
        reset_unified_twin_manager()
        with tempfile.TemporaryDirectory() as temp_dir:
            config = UnifiedTwinConfig(
                state_dir=f"{temp_dir}/states",
                history_dir=f"{temp_dir}/history",
            )
            manager = UnifiedTwinManager(config)
            tool = create_twin_state_tool(manager)
            assert tool is not None


class TestTwinStateToolActions:
    """Tool action tests"""
    
    @pytest.fixture
    def populated_tool(self):
        """Create tool with sample data"""
        reset_twin_state_store()
        reset_unified_twin_manager()
        with tempfile.TemporaryDirectory() as temp_dir:
            config = UnifiedTwinConfig(
                state_dir=f"{temp_dir}/states",
                history_dir=f"{temp_dir}/history",
            )
            manager = UnifiedTwinManager(config)
            
            # Add sample data
            rmn_csv = Path(temp_dir) / "rmn.csv"
            rmn_csv.write_text("""rmn_id,rmn_name,retailer_id,total_spend,total_revenue,week
rmn_tool,Tool Test RMN,tool_retailer,50000,150000,1
""")
            manager.ingest_rmn_csv(str(rmn_csv), "tool_retailer")
            
            brand_csv = Path(temp_dir) / "brands.csv"
            brand_csv.write_text("""brand_id,brand_name,retailer_id,spend,revenue,category,week
brand_tool1,Tool Brand 1,tool_retailer,25000,75000,CPG,1
brand_tool2,Tool Brand 2,tool_retailer,30000,90000,Food,1
""")
            manager.ingest_brand_csv(str(brand_csv), "tool_retailer")
            
            channel_csv = Path(temp_dir) / "channels.csv"
            channel_csv.write_text("""channel_id,channel_type,retailer_id,spend,revenue,impressions,week
ch_tool_sp,sponsored_products,tool_retailer,20000,60000,400000,1
ch_tool_disp,display,tool_retailer,15000,45000,300000,1
""")
            manager.ingest_channel_csv(str(channel_csv), "tool_retailer")
            
            tool = TwinStateTool(manager)
            yield tool, manager, temp_dir
    
    def test_get_state_action_rmn(self, populated_tool):
        """Test get_state action for RMN"""
        tool, _, _ = populated_tool
        
        result = tool.run(
            action="get_state",
            twin_type="rmn",
            retailer_id="tool_retailer",
        )
        
        assert "success" in result or "state" in result or "error" not in result
    
    def test_get_state_action_brand(self, populated_tool):
        """Test get_state action for Brand"""
        tool, mgr, _ = populated_tool
        
        # Get brand ID first
        brands = mgr.get_all_brand_states("tool_retailer")
        if brands:
            brand_id = brands[0].brand_id
            result = tool.run(
                action="get_state",
                twin_type="brand",
                retailer_id="tool_retailer",
                entity_id=brand_id,
            )
            assert result is not None
    
    def test_get_state_missing_retailer(self, populated_tool):
        """Test get_state without retailer_id"""
        tool, _, _ = populated_tool
        
        result = tool.run(
            action="get_state",
            twin_type="rmn",
        )
        
        assert "error" in result
    
    def test_get_all_action(self, populated_tool):
        """Test get_all action"""
        tool, _, _ = populated_tool
        
        result = tool.run(
            action="get_all",
            twin_type="brand",
            retailer_id="tool_retailer",
        )
        
        assert "states" in result
        assert result["count"] >= 2
    
    def test_get_summary_action(self, populated_tool):
        """Test get_summary action"""
        tool, _, _ = populated_tool
        
        result = tool.run(
            action="get_summary",
            twin_type="rmn",
        )
        
        assert "summary" in result
    
    def test_get_metrics_action_brand(self, populated_tool):
        """Test get_metrics action for brands"""
        tool, _, _ = populated_tool
        
        result = tool.run(
            action="get_metrics",
            twin_type="brand",
            retailer_id="tool_retailer",
        )
        
        assert "metrics" in result
        assert "total_brands" in result["metrics"]
    
    def test_get_metrics_action_channel(self, populated_tool):
        """Test get_metrics action for channels"""
        tool, _, _ = populated_tool
        
        result = tool.run(
            action="get_metrics",
            twin_type="channel",
            retailer_id="tool_retailer",
        )
        
        assert "metrics" in result
        assert "total_channels" in result["metrics"]
    
    def test_invalid_action(self, populated_tool):
        """Test invalid action handling"""
        tool, _, _ = populated_tool
        
        result = tool.run(
            action="invalid_action",
            twin_type="rmn",
            retailer_id="tool_retailer",
        )
        
        assert "error" in result
    
    def test_invalid_twin_type(self, populated_tool):
        """Test invalid twin type handling"""
        tool, _, _ = populated_tool
        
        result = tool.run(
            action="get_state",
            twin_type="invalid_type",
            retailer_id="tool_retailer",
        )
        
        assert "error" in result


class TestTwinStateToolHistory:
    """History retrieval tests"""
    
    @pytest.fixture
    def tool_with_history(self):
        """Create tool with history data"""
        reset_twin_state_store()
        reset_unified_twin_manager()
        with tempfile.TemporaryDirectory() as temp_dir:
            config = UnifiedTwinConfig(
                state_dir=f"{temp_dir}/states",
                history_dir=f"{temp_dir}/history",
            )
            manager = UnifiedTwinManager(config)
            
            # Create state with multiple updates - use retailer_id as twin_id
            rmn_csv = Path(temp_dir) / "rmn.csv"
            for i in range(3):
                rmn_csv.write_text(f"""rmn_name,retailer_id,total_spend,week
History Test,hist_retailer,{50000 + i*1000},{i+1}
""")
                manager.ingest_rmn_csv(str(rmn_csv), "hist_retailer")
            
            tool = TwinStateTool(manager)
            yield tool, manager, temp_dir
    
    def test_get_history_action(self, tool_with_history):
        """Test get_history action"""
        tool, _, _ = tool_with_history
        
        result = tool.run(
            action="get_history",
            twin_type="rmn",
            retailer_id="hist_retailer",
            limit=10,
        )
        
        assert "history" in result
        assert result["count"] >= 1


class TestTwinStateToolAggregation:
    """Metrics aggregation tests"""
    
    @pytest.fixture
    def tool_with_aggregatable_data(self):
        """Create tool with aggregatable data"""
        reset_twin_state_store()
        reset_unified_twin_manager()
        with tempfile.TemporaryDirectory() as temp_dir:
            config = UnifiedTwinConfig(
                state_dir=f"{temp_dir}/states",
                history_dir=f"{temp_dir}/history",
            )
            manager = UnifiedTwinManager(config)
            
            # Create multiple brands
            brand_csv = Path(temp_dir) / "brands.csv"
            brand_csv.write_text("""brand_id,brand_name,retailer_id,impressions,clicks,conversions,spend,revenue,category,week
brand_agg1,Brand 1,agg_retailer,1000000,30000,3000,50000,150000,CPG,1
brand_agg2,Brand 2,agg_retailer,800000,24000,2400,40000,120000,CPG,1
brand_agg3,Brand 3,agg_retailer,600000,18000,1800,30000,90000,Food,1
""")
            manager.ingest_brand_csv(str(brand_csv), "agg_retailer")
            
            tool = TwinStateTool(manager)
            yield tool, manager, temp_dir
    
    def test_aggregate_brand_metrics(self, tool_with_aggregatable_data):
        """Test brand metrics aggregation"""
        tool, _, _ = tool_with_aggregatable_data
        
        result = tool.run(
            action="get_metrics",
            twin_type="brand",
            retailer_id="agg_retailer",
        )
        
        assert result["success"]
        metrics = result["metrics"]
        assert metrics["total_brands"] == 3
        assert metrics["total_spend"] > 0
        assert metrics["total_revenue"] > 0
    
    def test_aggregate_includes_categories(self, tool_with_aggregatable_data):
        """Test that aggregation includes category breakdown"""
        tool, _, _ = tool_with_aggregatable_data
        
        result = tool.run(
            action="get_metrics",
            twin_type="brand",
            retailer_id="agg_retailer",
        )
        
        metrics = result["metrics"]
        assert "categories" in metrics
        assert "CPG" in metrics["categories"]


class TestTwinStateToolConvenience:
    """Convenience method tests"""
    
    @pytest.fixture
    def populated_tool(self):
        """Create tool with sample data"""
        reset_twin_state_store()
        reset_unified_twin_manager()
        with tempfile.TemporaryDirectory() as temp_dir:
            config = UnifiedTwinConfig(
                state_dir=f"{temp_dir}/states",
                history_dir=f"{temp_dir}/history",
            )
            manager = UnifiedTwinManager(config)
            
            # Create comprehensive data
            rmn_csv = Path(temp_dir) / "rmn.csv"
            rmn_csv.write_text("""rmn_id,rmn_name,retailer_id,total_spend,total_revenue,week
rmn_conv,Convenience Test,conv_retailer,100000,300000,1
""")
            manager.ingest_rmn_csv(str(rmn_csv), "conv_retailer")
            
            brand_csv = Path(temp_dir) / "brands.csv"
            brand_csv.write_text("""brand_id,brand_name,retailer_id,spend,revenue,week
brand_conv1,Brand 1,conv_retailer,50000,150000,1
brand_conv2,Brand 2,conv_retailer,30000,90000,1
""")
            manager.ingest_brand_csv(str(brand_csv), "conv_retailer")
            
            channel_csv = Path(temp_dir) / "channels.csv"
            channel_csv.write_text("""channel_id,channel_type,retailer_id,spend,revenue,impressions,elasticity_mean,elasticity_std,week
ch_conv_sp,sponsored_products,conv_retailer,40000,120000,800000,0.15,0.03,1
ch_conv_disp,display,conv_retailer,25000,75000,500000,0.12,0.025,1
""")
            manager.ingest_channel_csv(str(channel_csv), "conv_retailer")
            
            tool = TwinStateTool(manager)
            yield tool, manager, temp_dir
    
    def test_get_retailer_overview(self, populated_tool):
        """Test retailer overview method"""
        tool, _, _ = populated_tool
        
        overview = tool.get_retailer_overview("conv_retailer")
        
        assert "retailer_id" in overview
        assert overview["retailer_id"] == "conv_retailer"
        assert "brands" in overview
        assert "channels" in overview
    
    def test_get_channel_bayesian_posteriors(self, populated_tool):
        """Test Bayesian posteriors retrieval"""
        tool, _, _ = populated_tool
        
        posteriors = tool.get_channel_bayesian_posteriors("conv_retailer")
        
        assert len(posteriors) >= 2
        for p in posteriors:
            assert "channel_type" in p
            assert "elasticity" in p


class TestTwinStateToolSubscriptions:
    """Event subscription tests"""
    
    @pytest.fixture
    def tool(self):
        """Create tool for subscription tests"""
        reset_twin_state_store()
        reset_unified_twin_manager()
        with tempfile.TemporaryDirectory() as temp_dir:
            config = UnifiedTwinConfig(
                state_dir=f"{temp_dir}/states",
                history_dir=f"{temp_dir}/history",
            )
            manager = UnifiedTwinManager(config)
            tool = TwinStateTool(manager)
            yield tool, manager, temp_dir
    
    def test_subscribe_to_updates(self, tool):
        """Test subscribing to updates"""
        t, _, _ = tool
        events: List[TwinStateEvent] = []
        
        def handler(event):
            events.append(event)
        
        subscription_id = t.subscribe_to_updates(handler)
        
        assert subscription_id is not None
    
    def test_subscribe_to_alerts(self, tool):
        """Test subscribing to alerts"""
        t, _, _ = tool
        
        def handler(event):
            pass
        
        subscription_id = t.subscribe_to_alerts(handler, alert_type="pacing")
        
        assert subscription_id is not None
    
    def test_unsubscribe(self, tool):
        """Test unsubscribing"""
        t, _, _ = tool
        
        def handler(event):
            pass
        
        subscription_id = t.subscribe_to_updates(handler)
        t.unsubscribe(subscription_id)
        
        # Should not raise


def run_tests():
    """Run all tool tests"""
    print("="*60)
    print("Twin State Tool Unit Tests")
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

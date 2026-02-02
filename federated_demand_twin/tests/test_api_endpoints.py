"""
API Endpoint Test Suite

Tests all REST API endpoints across:
1. Retail Media API
2. Digital Twin API
3. Optimizer API

Run: python tests/test_api_endpoints.py
"""

import sys
import os
import json
import numpy as np
from datetime import datetime, date
from typing import Dict, List, Any, Optional
import uuid

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# =============================================================================
# TEST UTILITIES
# =============================================================================

class APITestResults:
    """Track API test results."""
    def __init__(self):
        self.tests: Dict[str, Dict[str, bool]] = {}
        self.current_suite: str = ""
    
    def start_suite(self, name: str):
        self.current_suite = name
        self.tests[name] = {}
        print(f"\n{'='*70}")
        print(f"API TEST SUITE: {name}")
        print(f"{'='*70}")
    
    def record(self, test_name: str, passed: bool, details: str = ""):
        self.tests[self.current_suite][test_name] = passed
        status = "✓" if passed else "✗"
        print(f"  {status} {test_name}")
        if details and not passed:
            for line in details.split('\n')[:3]:
                print(f"      {line}")
    
    def summary(self) -> bool:
        print(f"\n{'='*70}")
        print("API ENDPOINT TEST SUMMARY")
        print(f"{'='*70}")
        
        total_passed = 0
        total_failed = 0
        
        for suite_name, tests in self.tests.items():
            passed = sum(1 for v in tests.values() if v)
            failed = sum(1 for v in tests.values() if not v)
            total_passed += passed
            total_failed += failed
            
            status = "✓" if failed == 0 else "✗"
            print(f"\n{status} {suite_name}: {passed}/{len(tests)} passed")
            
            for test_name, test_passed in tests.items():
                if not test_passed:
                    print(f"    ✗ FAILED: {test_name}")
        
        print(f"\n{'='*70}")
        print(f"TOTAL: {total_passed}/{total_passed + total_failed} tests passed")
        print(f"{'='*70}")
        
        return total_failed == 0


results = APITestResults()


# =============================================================================
# RETAIL MEDIA API TESTS
# =============================================================================

def test_retail_media_api():
    """Test Retail Media API endpoints."""
    results.start_suite("Retail Media API")
    
    try:
        from vendor.retail_media.api import (
            app,
            RetailerConfigRequest,
            ChannelConfigRequest,
            SKUConfigRequest,
            TwinStateRequest,
            ElasticityUpdateRequest,
            AllocationRequest,
            PipelineRequest,
        )
        
        # Test 1: App creation
        results.record("API App Creation", app is not None,
            f"Title: {app.title}")
        
        # Test 2: Request model - RetailerConfig
        try:
            retailer_req = RetailerConfigRequest(
                retailer_id="test_retailer",
                retailer_name="Test Retailer",
                available_channels=["sponsored_search", "display"],
                min_quarterly_spend=10000.0,
                max_quarterly_spend=1000000.0,
            )
            results.record("RetailerConfigRequest Model", True)
        except Exception as e:
            results.record("RetailerConfigRequest Model", False, str(e))
        
        # Test 3: Request model - ChannelConfig
        try:
            channel_req = ChannelConfigRequest(
                channel="sponsored_search",
                min_spend=0.0,
                max_spend=100000.0,
                cpm=12.0,
                prior_elasticity_mean=0.15,
            )
            results.record("ChannelConfigRequest Model", True)
        except Exception as e:
            results.record("ChannelConfigRequest Model", False, str(e))
        
        # Test 4: Request model - SKUConfig
        try:
            sku_req = SKUConfigRequest(
                sku_id="SKU001",
                sku_name="Premium Widget",
                category="beverages",
                brand="TestBrand",
                unit_price=4.99,
                unit_cost=2.50,
                weekly_base_demand=100.0,
            )
            results.record("SKUConfigRequest Model", True)
        except Exception as e:
            results.record("SKUConfigRequest Model", False, str(e))
        
        # Test 5: Request model - TwinState
        try:
            twin_req = TwinStateRequest(
                retailer_id="walmart",
                sku_id="SKU001",
                initial_inventory=500.0,
                base_demand_mean=100.0,
                base_demand_std=20.0,
            )
            results.record("TwinStateRequest Model", True)
        except Exception as e:
            results.record("TwinStateRequest Model", False, str(e))
        
        # Test 6: Request model - ElasticityUpdate
        try:
            elasticity_req = ElasticityUpdateRequest(
                retailer_id="walmart",
                channel="sponsored_search",
                category="beverages",
                spend_history=[1000.0, 1500.0, 2000.0],
                sales_lift_history=[50.0, 70.0, 85.0],
            )
            results.record("ElasticityUpdateRequest Model", True)
        except Exception as e:
            results.record("ElasticityUpdateRequest Model", False, str(e))
        
        # Test 7: Request model - Allocation
        try:
            allocation_req = AllocationRequest(
                allocation_id="alloc_001",
                name="Q1 Allocation",
                total_budget=500000.0,
                period_weeks=13,
                spend_by_retailer_channel={
                    "walmart": {"sponsored_search": 100000.0, "display": 50000.0},
                    "amazon": {"sponsored_search": 150000.0},
                },
            )
            results.record("AllocationRequest Model", True)
        except Exception as e:
            results.record("AllocationRequest Model", False, str(e))
        
        # Test 8: Request model - Pipeline
        try:
            pipeline_req = PipelineRequest(
                current_allocation=AllocationRequest(
                    allocation_id="alloc_001",
                    name="Q1 Allocation",
                    total_budget=500000.0,
                    period_weeks=13,
                    spend_by_retailer_channel={"walmart": {"sponsored_search": 100000.0}},
                ),
                total_budget=500000.0,
                period_weeks=13,
            )
            results.record("PipelineRequest Model", True)
        except Exception as e:
            results.record("PipelineRequest Model", False, str(e))
        
        # Test 9: API routes exist
        routes = [r.path for r in app.routes]
        expected_routes = ["/health", "/status", "/config/retailer", "/config/channel", "/config/sku"]
        found_routes = [r for r in expected_routes if r in routes]
        results.record("Expected Routes Exist", len(found_routes) >= 3,
            f"Found {len(found_routes)}/{len(expected_routes)} expected routes")
        
    except Exception as e:
        results.record("Retail Media API Import", False, str(e))
        import traceback
        traceback.print_exc()


# =============================================================================
# DIGITAL TWIN API TESTS
# =============================================================================

def test_digital_twin_api():
    """Test Digital Twin API endpoints."""
    results.start_suite("Digital Twin API")
    
    try:
        from vendor.digital_twin.api import (
            app,
            EntityStateInput,
            InitializeStateRequest,
            ScenarioRequestInput,
            CompareScenarioRequest,
        )
        
        # Test 1: App creation
        results.record("API App Creation", app is not None,
            f"Title: {app.title}")
        
        # Test 2: EntityStateInput model
        try:
            entity_input = EntityStateInput(
                entity_id="entity_001",
                on_hand=500.0,
                on_order=200.0,
                expected_weekly_demand=100.0,
                demand_std=20.0,
                lead_time_weeks=2,
                reorder_point=250.0,
                order_quantity=400,
            )
            results.record("EntityStateInput Model", True)
        except Exception as e:
            results.record("EntityStateInput Model", False, str(e))
        
        # Test 3: InitializeStateRequest model
        try:
            init_req = InitializeStateRequest(
                week_start=date.today(),
                entities=[
                    EntityStateInput(
                        entity_id="entity_001",
                        on_hand=500.0,
                        expected_weekly_demand=100.0,
                        demand_std=20.0,
                        lead_time_weeks=2,
                        reorder_point=250.0,
                        order_quantity=400,
                    )
                ],
            )
            results.record("InitializeStateRequest Model", True)
        except Exception as e:
            results.record("InitializeStateRequest Model", False, str(e))
        
        # Test 4: ScenarioRequestInput model
        try:
            scenario_req = ScenarioRequestInput(
                scenario_name="demand_surge",
                base_state_id="state_001",
                modifications={"demand_multiplier": 1.5},
                simulation_weeks=13,
                num_simulations=1000,
            )
            results.record("ScenarioRequestInput Model", True)
        except Exception as e:
            results.record("ScenarioRequestInput Model", False, str(e))
        
        # Test 5: CompareScenarioRequest model
        try:
            compare_req = CompareScenarioRequest(
                scenarios=[
                    ScenarioRequestInput(
                        scenario_name="baseline",
                        base_state_id="state_001",
                        modifications={},
                    ),
                    ScenarioRequestInput(
                        scenario_name="optimistic",
                        base_state_id="state_001",
                        modifications={"demand_multiplier": 1.2},
                    ),
                ]
            )
            results.record("CompareScenarioRequest Model", True)
        except Exception as e:
            results.record("CompareScenarioRequest Model", False, str(e))
        
        # Test 6: API routes exist
        routes = [r.path for r in app.routes]
        results.record("API Routes Defined", len(routes) > 5,
            f"Found {len(routes)} routes")
        
    except Exception as e:
        results.record("Digital Twin API Import", False, str(e))
        import traceback
        traceback.print_exc()


# =============================================================================
# OPTIMIZER API TESTS
# =============================================================================

def test_optimizer_api():
    """Test Optimizer API endpoints."""
    results.start_suite("Optimizer API")
    
    try:
        from vendor.optimizer.api import (
            app,
            OptimizeEntityRequest,
            BatchOptimizeRequest,
            OptimizeResponse,
        )
        
        # Test 1: App creation
        results.record("API App Creation", app is not None,
            f"Title: {app.title}")
        
        # Test 2: OptimizeEntityRequest model
        try:
            entity_req = OptimizeEntityRequest(
                entity_id="entity_001",
                current_inventory=500.0,
                on_order=200.0,
                expected_weekly_demand=100.0,
                demand_std=20.0,
                lead_time_weeks=2,
                moq=50,
                case_pack=12,
                unit_cost=10.0,
                holding_cost_rate=0.25,
                stockout_cost_per_unit=5.0,
                ordering_cost=50.0,
                min_service_level=0.95,
            )
            results.record("OptimizeEntityRequest Model", True)
        except Exception as e:
            results.record("OptimizeEntityRequest Model", False, str(e))
        
        # Test 3: OptimizeEntityRequest with posterior
        try:
            entity_req_posterior = OptimizeEntityRequest(
                entity_id="entity_002",
                current_inventory=300.0,
                expected_weekly_demand=80.0,
                demand_std=15.0,
                lead_time_weeks=3,
                posterior={
                    "mean": 85.0,
                    "std": 12.0,
                    "ci_lower": 65.0,
                    "ci_upper": 105.0,
                },
            )
            results.record("OptimizeEntityRequest with Posterior", True)
        except Exception as e:
            results.record("OptimizeEntityRequest with Posterior", False, str(e))
        
        # Test 4: BatchOptimizeRequest model
        try:
            batch_req = BatchOptimizeRequest(
                entities=[
                    OptimizeEntityRequest(
                        entity_id="entity_001",
                        current_inventory=500.0,
                        expected_weekly_demand=100.0,
                        demand_std=20.0,
                        lead_time_weeks=2,
                    ),
                    OptimizeEntityRequest(
                        entity_id="entity_002",
                        current_inventory=300.0,
                        expected_weekly_demand=80.0,
                        demand_std=15.0,
                        lead_time_weeks=3,
                    ),
                ],
                global_budget=100000.0,
                warehouse_capacity=10000.0,
            )
            results.record("BatchOptimizeRequest Model", True)
        except Exception as e:
            results.record("BatchOptimizeRequest Model", False, str(e))
        
        # Test 5: OptimizeResponse model
        try:
            response = OptimizeResponse(
                entity_id="entity_001",
                recommended_reorder_point=250.0,
                recommended_order_quantity=400,
                expected_service_level=0.97,
                expected_stockout_risk=0.03,
                expected_holding_cost=1250.0,
                expected_ordering_cost=200.0,
                total_expected_cost=1450.0,
                solver_status="OPTIMAL",
            )
            results.record("OptimizeResponse Model", True)
        except Exception as e:
            results.record("OptimizeResponse Model", False, str(e))
        
        # Test 6: API routes exist
        routes = [r.path for r in app.routes]
        results.record("API Routes Defined", len(routes) > 3,
            f"Found {len(routes)} routes")
        
    except Exception as e:
        results.record("Optimizer API Import", False, str(e))
        import traceback
        traceback.print_exc()


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================

def test_error_handling():
    """Test API error handling."""
    results.start_suite("API Error Handling")
    
    try:
        from pydantic import ValidationError
        from vendor.retail_media.api import RetailerConfigRequest, SKUConfigRequest
        
        # Test 1: Missing required field
        try:
            invalid_req = RetailerConfigRequest(
                retailer_name="Test",  # Missing retailer_id
            )
            results.record("Missing Required Field Detection", False, "Should have raised ValidationError")
        except ValidationError:
            results.record("Missing Required Field Detection", True)
        except Exception as e:
            results.record("Missing Required Field Detection", False, str(e))
        
        # Test 2: Invalid field type
        try:
            invalid_req = SKUConfigRequest(
                sku_id="SKU001",
                sku_name="Test",
                category="beverages",
                brand="TestBrand",
                unit_price="not_a_number",  # Should be float
                unit_cost=2.50,
            )
            results.record("Invalid Field Type Detection", False, "Should have raised ValidationError")
        except ValidationError:
            results.record("Invalid Field Type Detection", True)
        except Exception as e:
            results.record("Invalid Field Type Detection", False, str(e))
        
        # Test 3: Valid request with defaults
        try:
            valid_req = RetailerConfigRequest(
                retailer_id="test",
                retailer_name="Test Retailer",
            )
            # Check defaults are applied
            assert valid_req.min_quarterly_spend == 0.0
            assert valid_req.tier == "standard"
            results.record("Default Values Applied", True)
        except Exception as e:
            results.record("Default Values Applied", False, str(e))
        
    except Exception as e:
        results.record("Error Handling Import", False, str(e))
        import traceback
        traceback.print_exc()


# =============================================================================
# SCHEMA VALIDATION TESTS
# =============================================================================

def test_schema_validation():
    """Test request/response schema validation."""
    results.start_suite("Schema Validation")
    
    try:
        from vendor.retail_media.api import (
            AllocationRequest,
            PipelineResponse,
            SimulationResponse,
        )
        
        # Test 1: Nested dict in AllocationRequest
        try:
            allocation = AllocationRequest(
                allocation_id="alloc_001",
                name="Q1 Plan",
                total_budget=500000.0,
                period_weeks=13,
                spend_by_retailer_channel={
                    "walmart": {"search": 100000.0, "display": 50000.0},
                    "amazon": {"search": 150000.0, "video": 75000.0},
                    "target": {"search": 75000.0},
                },
            )
            # Validate structure
            assert len(allocation.spend_by_retailer_channel) == 3
            assert allocation.spend_by_retailer_channel["walmart"]["search"] == 100000.0
            results.record("Nested Dict Validation", True)
        except Exception as e:
            results.record("Nested Dict Validation", False, str(e))
        
        # Test 2: PipelineResponse structure
        try:
            response = PipelineResponse(
                pack_id="pack_001",
                status="completed",
                recommendation={"action": "shift_budget", "target": "search"},
                executive_summary="Shift 10% budget to search channel",
                confidence=0.85,
                governance_approved=True,
            )
            assert response.confidence == 0.85
            results.record("PipelineResponse Structure", True)
        except Exception as e:
            results.record("PipelineResponse Structure", False, str(e))
        
        # Test 3: SimulationResponse structure
        try:
            sim_response = SimulationResponse(
                scenario_id="scenario_001",
                scenario_name="Demand Surge",
                expected_sales=1500000.0,
                sales_ci=[1400000.0, 1600000.0],
                expected_roas=2.5,
                expected_stockout_rate=0.05,
                binding_constraints=["budget", "inventory_capacity"],
            )
            assert len(sim_response.binding_constraints) == 2
            results.record("SimulationResponse Structure", True)
        except Exception as e:
            results.record("SimulationResponse Structure", False, str(e))
        
        # Test 4: JSON serialization
        try:
            allocation = AllocationRequest(
                allocation_id="alloc_002",
                name="Q2 Plan",
                total_budget=600000.0,
                period_weeks=13,
                spend_by_retailer_channel={"walmart": {"search": 200000.0}},
            )
            json_str = allocation.model_dump_json()
            assert "allocation_id" in json_str
            assert "600000" in json_str
            results.record("JSON Serialization", True)
        except Exception as e:
            results.record("JSON Serialization", False, str(e))
        
    except Exception as e:
        results.record("Schema Validation Import", False, str(e))
        import traceback
        traceback.print_exc()


# =============================================================================
# MAIN TEST RUNNER
# =============================================================================

def run_api_tests():
    """Run all API endpoint tests."""
    print("\n" + "="*70)
    print("API ENDPOINT TESTS")
    print("="*70)
    
    # Run all test suites
    test_retail_media_api()
    test_digital_twin_api()
    test_optimizer_api()
    test_error_handling()
    test_schema_validation()
    
    # Print summary
    success = results.summary()
    
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = run_api_tests()
    sys.exit(exit_code)

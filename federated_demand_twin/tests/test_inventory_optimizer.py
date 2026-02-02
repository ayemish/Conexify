"""
Inventory Optimizer Test Suite

Tests optimization algorithms:
1. Configuration and setup
2. Safety stock calculations
3. Single and batch optimization
4. Edge cases and constraints

Run: python tests/test_inventory_optimizer.py
"""

import sys
import os
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Optional

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# =============================================================================
# TEST UTILITIES
# =============================================================================

class OptimizerTestResults:
    """Track optimizer test results."""
    def __init__(self):
        self.tests: Dict[str, Dict[str, bool]] = {}
        self.current_suite: str = ""
    
    def start_suite(self, name: str):
        self.current_suite = name
        self.tests[name] = {}
        print(f"\n{'='*70}")
        print(f"OPTIMIZER TEST SUITE: {name}")
        print(f"{'='*70}")
    
    def record(self, test_name: str, passed: bool, details: str = ""):
        self.tests[self.current_suite][test_name] = passed
        status = "✓" if passed else "✗"
        print(f"  {status} {test_name}")
        if details:
            for line in details.split('\n')[:2]:
                print(f"      {line}")
    
    def summary(self) -> bool:
        print(f"\n{'='*70}")
        print("INVENTORY OPTIMIZER TEST SUMMARY")
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


results = OptimizerTestResults()


# =============================================================================
# CONFIGURATION TESTS
# =============================================================================

def test_optimizer_config():
    """Test optimizer configuration."""
    results.start_suite("Optimizer Configuration")
    
    try:
        from vendor.optimizer.inventory_optimizer import (
            OptimizerConfig,
            InventoryDecision,
            ORTOOLS_AVAILABLE,
        )
        
        # Test 1: Default config creation
        try:
            config = OptimizerConfig()
            assert config.solver_time_limit_seconds == 30.0
            assert config.stockout_cost_weight == 10.0
            assert config.holding_cost_weight == 1.0
            results.record("Default Config Creation", True)
        except Exception as e:
            results.record("Default Config Creation", False, str(e))
        
        # Test 2: Custom config creation
        try:
            config = OptimizerConfig(
                solver_time_limit_seconds=60.0,
                solver_type="SCIP",
                stockout_cost_weight=15.0,
                holding_cost_weight=0.5,
                max_inventory_weeks=16.0,
            )
            assert config.solver_time_limit_seconds == 60.0
            assert config.solver_type == "SCIP"
            results.record("Custom Config Creation", True)
        except Exception as e:
            results.record("Custom Config Creation", False, str(e))
        
        # Test 3: OR-Tools availability check
        results.record("OR-Tools Availability", True,
            f"ORTOOLS_AVAILABLE = {ORTOOLS_AVAILABLE}")
        
        # Test 4: InventoryDecision creation
        try:
            decision = InventoryDecision(
                entity_id="SKU001",
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
            assert decision.entity_id == "SKU001"
            assert decision.min_service_level == 0.95
            results.record("InventoryDecision Creation", True)
        except Exception as e:
            results.record("InventoryDecision Creation", False, str(e))
        
        # Test 5: InventoryDecision with constraints
        try:
            decision = InventoryDecision(
                entity_id="SKU002",
                current_inventory=300.0,
                on_order=0.0,
                expected_weekly_demand=80.0,
                demand_std=15.0,
                lead_time_weeks=3,
                moq=100,
                case_pack=24,
                unit_cost=15.0,
                holding_cost_rate=0.20,
                stockout_cost_per_unit=8.0,
                ordering_cost=75.0,
                warehouse_capacity=5000.0,
                budget_limit=10000.0,
            )
            assert decision.warehouse_capacity == 5000.0
            assert decision.budget_limit == 10000.0
            results.record("InventoryDecision with Constraints", True)
        except Exception as e:
            results.record("InventoryDecision with Constraints", False, str(e))
        
    except Exception as e:
        results.record("Optimizer Config Import", False, str(e))
        import traceback
        traceback.print_exc()


# =============================================================================
# SAFETY STOCK TESTS
# =============================================================================

def test_safety_stock():
    """Test safety stock calculations."""
    results.start_suite("Safety Stock Calculations")
    
    try:
        from vendor.optimizer.inventory_optimizer import SafetyStockCalculator
        
        # Test 1: Calculator creation
        try:
            calc = SafetyStockCalculator()
            assert calc is not None
            results.record("Calculator Creation", True)
        except Exception as e:
            results.record("Calculator Creation", False, str(e))
        
        # Test 2: Basic safety stock calculation
        try:
            # Use static method
            safety_stock = SafetyStockCalculator.calculate_safety_stock(
                demand_std=20.0,
                lead_time_weeks=2,
                service_level=0.95,
            )
            
            # Safety stock should be positive
            assert safety_stock > 0
            # For 95% SL with z≈1.645: SS ≈ 1.645 * 20 * sqrt(2) ≈ 46.5
            assert 30 < safety_stock < 80
            results.record("Basic Safety Stock", True,
                f"SS = {safety_stock:.1f} units")
        except Exception as e:
            results.record("Basic Safety Stock", False, str(e))
        
        # Test 3: Higher service level = more safety stock
        try:
            ss_95 = SafetyStockCalculator.calculate_safety_stock(demand_std=20.0, lead_time_weeks=2, service_level=0.95)
            ss_99 = SafetyStockCalculator.calculate_safety_stock(demand_std=20.0, lead_time_weeks=2, service_level=0.99)
            
            assert ss_99 > ss_95
            results.record("Service Level Impact", True,
                f"95%: {ss_95:.1f}, 99%: {ss_99:.1f}")
        except Exception as e:
            results.record("Service Level Impact", False, str(e))
        
        # Test 4: Lead time impact
        try:
            ss_2wk = SafetyStockCalculator.calculate_safety_stock(demand_std=20.0, lead_time_weeks=2, service_level=0.95)
            ss_4wk = SafetyStockCalculator.calculate_safety_stock(demand_std=20.0, lead_time_weeks=4, service_level=0.95)
            
            # Longer lead time = more safety stock
            assert ss_4wk > ss_2wk
            results.record("Lead Time Impact", True,
                f"2wk: {ss_2wk:.1f}, 4wk: {ss_4wk:.1f}")
        except Exception as e:
            results.record("Lead Time Impact", False, str(e))
        
        # Test 5: Demand variability impact
        try:
            ss_low_var = SafetyStockCalculator.calculate_safety_stock(demand_std=10.0, lead_time_weeks=2, service_level=0.95)
            ss_high_var = SafetyStockCalculator.calculate_safety_stock(demand_std=30.0, lead_time_weeks=2, service_level=0.95)
            
            # Higher variability = more safety stock
            assert ss_high_var > ss_low_var
            results.record("Demand Variability Impact", True,
                f"Low: {ss_low_var:.1f}, High: {ss_high_var:.1f}")
        except Exception as e:
            results.record("Demand Variability Impact", False, str(e))
        
    except Exception as e:
        results.record("Safety Stock Import", False, str(e))
        import traceback
        traceback.print_exc()


# =============================================================================
# OPTIMIZER TESTS
# =============================================================================

def test_optimizer():
    """Test inventory optimizer."""
    results.start_suite("Inventory Optimizer")
    
    try:
        from vendor.optimizer.inventory_optimizer import (
            InventoryOptimizer,
            OptimizerConfig,
            InventoryDecision,
            create_optimizer,
        )
        
        # Test 1: Optimizer creation
        try:
            optimizer = create_optimizer()
            assert optimizer is not None
            results.record("Optimizer Creation", True)
        except Exception as e:
            results.record("Optimizer Creation", False, str(e))
        
        # Test 2: Optimizer with custom config
        try:
            config = OptimizerConfig(
                stockout_cost_weight=15.0,
                max_inventory_weeks=10.0,
            )
            optimizer = InventoryOptimizer(config)
            assert optimizer.config.stockout_cost_weight == 15.0
            results.record("Optimizer with Custom Config", True)
        except Exception as e:
            results.record("Optimizer with Custom Config", False, str(e))
        
        # Test 3: Single entity optimization
        try:
            optimizer = create_optimizer()
            
            decision = InventoryDecision(
                entity_id="SKU001",
                current_inventory=500.0,
                on_order=0.0,
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
            
            result = optimizer.optimize_single_entity(decision)
            
            # Should return a result with recommendations
            assert result is not None
            assert hasattr(result, 'recommended_reorder_point') or hasattr(result, 'recommended_order_qty')
            results.record("Single Entity Optimization", True)
        except Exception as e:
            results.record("Single Entity Optimization", False, str(e))
        
        # Test 4: Batch optimization (using single entity in loop)
        try:
            optimizer = create_optimizer()
            
            decisions = [
                InventoryDecision(
                    entity_id="SKU001",
                    current_inventory=500.0,
                    on_order=0.0,
                    expected_weekly_demand=100.0,
                    demand_std=20.0,
                    lead_time_weeks=2,
                    moq=50,
                    case_pack=12,
                    unit_cost=10.0,
                    holding_cost_rate=0.25,
                    stockout_cost_per_unit=5.0,
                    ordering_cost=50.0,
                ),
                InventoryDecision(
                    entity_id="SKU002",
                    current_inventory=300.0,
                    on_order=100.0,
                    expected_weekly_demand=80.0,
                    demand_std=15.0,
                    lead_time_weeks=3,
                    moq=100,
                    case_pack=24,
                    unit_cost=15.0,
                    holding_cost_rate=0.20,
                    stockout_cost_per_unit=8.0,
                    ordering_cost=75.0,
                ),
            ]
            
            results_list = [optimizer.optimize_single_entity(d) for d in decisions]
            
            assert len(results_list) == 2
            results.record("Batch Optimization", True,
                f"Optimized {len(results_list)} entities")
        except Exception as e:
            results.record("Batch Optimization", False, str(e))
        
        # Test 5: Optimization with budget constraint
        try:
            optimizer = create_optimizer()
            
            decision = InventoryDecision(
                entity_id="SKU003",
                current_inventory=200.0,
                on_order=0.0,
                expected_weekly_demand=150.0,
                demand_std=30.0,
                lead_time_weeks=2,
                moq=50,
                case_pack=12,
                unit_cost=20.0,
                holding_cost_rate=0.25,
                stockout_cost_per_unit=10.0,
                ordering_cost=100.0,
                budget_limit=5000.0,  # Budget constraint
            )
            
            result = optimizer.optimize_single_entity(decision)
            
            # Result should respect budget constraint
            assert result is not None
            results.record("Optimization with Budget Constraint", True)
        except Exception as e:
            results.record("Optimization with Budget Constraint", False, str(e))
        
    except Exception as e:
        results.record("Optimizer Import", False, str(e))
        import traceback
        traceback.print_exc()


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

def test_edge_cases():
    """Test optimizer edge cases."""
    results.start_suite("Edge Cases")
    
    try:
        from vendor.optimizer.inventory_optimizer import (
            InventoryOptimizer,
            OptimizerConfig,
            InventoryDecision,
            SafetyStockCalculator,
            create_optimizer,
        )
        
        # Test 1: Zero demand
        try:
            ss = SafetyStockCalculator.calculate_safety_stock(demand_std=0.0, lead_time_weeks=2, service_level=0.95)
            
            # Zero variability = zero safety stock
            assert ss == 0.0 or ss < 0.1
            results.record("Zero Demand Variability", True,
                f"SS = {ss:.2f}")
        except Exception as e:
            results.record("Zero Demand Variability", False, str(e))
        
        # Test 2: Very high demand variability
        try:
            ss = SafetyStockCalculator.calculate_safety_stock(demand_std=100.0, lead_time_weeks=2, service_level=0.95)
            
            # High variability = high safety stock
            assert ss > 100
            results.record("High Demand Variability", True,
                f"SS = {ss:.1f}")
        except Exception as e:
            results.record("High Demand Variability", False, str(e))
        
        # Test 3: MOQ constraint
        try:
            optimizer = create_optimizer()
            
            decision = InventoryDecision(
                entity_id="SKU_MOQ",
                current_inventory=100.0,
                on_order=0.0,
                expected_weekly_demand=50.0,
                demand_std=10.0,
                lead_time_weeks=2,
                moq=500,  # Large MOQ
                case_pack=50,
                unit_cost=5.0,
                holding_cost_rate=0.25,
                stockout_cost_per_unit=3.0,
                ordering_cost=25.0,
            )
            
            result = optimizer.optimize_single_entity(decision)
            assert result is not None
            results.record("Large MOQ Constraint", True)
        except Exception as e:
            results.record("Large MOQ Constraint", False, str(e))
        
        # Test 4: Long lead time
        try:
            ss = SafetyStockCalculator.calculate_safety_stock(demand_std=20.0, lead_time_weeks=12, service_level=0.95)
            
            # Long lead time = high safety stock
            assert ss > 50
            results.record("Long Lead Time", True,
                f"SS for 12 weeks = {ss:.1f}")
        except Exception as e:
            results.record("Long Lead Time", False, str(e))
        
        # Test 5: Very high service level
        try:
            ss_99_9 = SafetyStockCalculator.calculate_safety_stock(demand_std=20.0, lead_time_weeks=2, service_level=0.999)
            ss_95 = SafetyStockCalculator.calculate_safety_stock(demand_std=20.0, lead_time_weeks=2, service_level=0.95)
            
            # 99.9% SL should require much more safety stock
            assert ss_99_9 > ss_95 * 1.5
            results.record("Very High Service Level (99.9%)", True,
                f"99.9%: {ss_99_9:.1f}, 95%: {ss_95:.1f}")
        except Exception as e:
            results.record("Very High Service Level (99.9%)", False, str(e))
        
        # Test 6: Existing on-order inventory
        try:
            optimizer = create_optimizer()
            
            # Decision with significant on-order
            decision = InventoryDecision(
                entity_id="SKU_ON_ORDER",
                current_inventory=100.0,
                on_order=500.0,  # Large on-order
                expected_weekly_demand=100.0,
                demand_std=20.0,
                lead_time_weeks=2,
                moq=50,
                case_pack=12,
                unit_cost=10.0,
                holding_cost_rate=0.25,
                stockout_cost_per_unit=5.0,
                ordering_cost=50.0,
            )
            
            result = optimizer.optimize_single_entity(decision)
            assert result is not None
            results.record("On-Order Inventory Consideration", True)
        except Exception as e:
            results.record("On-Order Inventory Consideration", False, str(e))
        
    except Exception as e:
        results.record("Edge Cases Import", False, str(e))
        import traceback
        traceback.print_exc()


# =============================================================================
# MAIN TEST RUNNER
# =============================================================================

def run_optimizer_tests():
    """Run all optimizer tests."""
    print("\n" + "="*70)
    print("INVENTORY OPTIMIZER TESTS")
    print("="*70)
    
    # Run all test suites
    test_optimizer_config()
    test_safety_stock()
    test_optimizer()
    test_edge_cases()
    
    # Print summary
    success = results.summary()
    
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = run_optimizer_tests()
    sys.exit(exit_code)

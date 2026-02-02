"""
RMN Ecosystem Test Suite

Tests RMN (Retail Media Network) agent orchestration:
1. Agent initialization
2. Agent actions and capabilities
3. Autonomous orchestrator
4. Decision pack generation

Run: python tests/test_rmn_ecosystem.py
"""

import sys
import os
import numpy as np
from datetime import datetime, date
from typing import Dict, List, Any, Optional

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# =============================================================================
# TEST UTILITIES
# =============================================================================

class RMNTestResults:
    """Track RMN ecosystem test results."""
    def __init__(self):
        self.tests: Dict[str, Dict[str, bool]] = {}
        self.current_suite: str = ""
    
    def start_suite(self, name: str):
        self.current_suite = name
        self.tests[name] = {}
        print(f"\n{'='*70}")
        print(f"RMN ECOSYSTEM TEST SUITE: {name}")
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
        print("RMN ECOSYSTEM TEST SUMMARY")
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


results = RMNTestResults()


# =============================================================================
# RMN SCHEMAS TESTS
# =============================================================================

def test_rmn_schemas():
    """Test RMN schema definitions."""
    results.start_suite("RMN Schemas")
    
    try:
        from vendor.agents.ecosystems.rmn.schemas import (
            RMNConfig,
            ChannelConfig,
            ChannelType,
            MediaSpendData,
        )
        
        # Test 1: ChannelType enum
        try:
            assert ChannelType.SPONSORED_SEARCH is not None
            assert ChannelType.DISPLAY is not None
            channel_types = list(ChannelType)
            results.record("ChannelType Enum", len(channel_types) >= 2,
                f"Found {len(channel_types)} channel types")
        except Exception as e:
            results.record("ChannelType Enum", False, str(e))
        
        # Test 2: ChannelConfig creation
        try:
            channel = ChannelConfig(
                channel_id="search_001",
                channel_type=ChannelType.SPONSORED_SEARCH,
                name="Sponsored Search",
                min_spend=0.0,
                max_spend=100000.0,
                cpm=12.0,
            )
            assert channel.channel_id == "search_001"
            results.record("ChannelConfig Creation", True)
        except Exception as e:
            results.record("ChannelConfig Creation", False, str(e))
        
        # Test 3: RMNConfig creation
        try:
            config = RMNConfig(
                retailer_id="walmart",
                retailer_name="Walmart",
                channels=[
                    ChannelConfig(
                        channel_id="search",
                        channel_type=ChannelType.SPONSORED_SEARCH,
                        name="Search",
                    ),
                    ChannelConfig(
                        channel_id="display",
                        channel_type=ChannelType.DISPLAY,
                        name="Display",
                    ),
                ],
            )
            assert config.retailer_id == "walmart"
            assert len(config.channels) == 2
            results.record("RMNConfig Creation", True)
        except Exception as e:
            results.record("RMNConfig Creation", False, str(e))
        
        # Test 4: MediaSpendData creation
        try:
            spend = MediaSpendData(
                week_start=date.today(),
                channel_id="search",
                spend=50000.0,
                impressions=5000000,
                clicks=100000,
                conversions=5000,
                revenue=250000.0,
            )
            assert spend.spend == 50000.0
            results.record("MediaSpendData Creation", True)
        except Exception as e:
            results.record("MediaSpendData Creation", False, str(e))
        
        # Test 5: MediaSpendData metrics computation
        try:
            spend = MediaSpendData(
                week_start=date.today(),
                channel_id="search",
                spend=50000.0,
                impressions=5000000,
                clicks=100000,
                conversions=5000,
                revenue=250000.0,
            )
            spend.compute_metrics()
            
            # Check computed metrics
            assert hasattr(spend, 'ctr') or hasattr(spend, 'roas')
            results.record("MediaSpendData Metrics", True)
        except Exception as e:
            results.record("MediaSpendData Metrics", False, str(e))
        
    except Exception as e:
        results.record("RMN Schemas Import", False, str(e))
        import traceback
        traceback.print_exc()


# =============================================================================
# RMN AGENT TESTS
# =============================================================================

def test_rmn_agents():
    """Test RMN agent initialization and capabilities."""
    results.start_suite("RMN Agents")
    
    try:
        from vendor.agents.ecosystems.rmn.agents import (
            RMNDataIngestionAgent,
            RMNAttributionAgent,
            RMNElasticityAgent,
            RMNScenarioAgent,
            RMNTwinAgent,
            RMNOptimizerAgent,
            RMNGovernanceAgent,
            RMNRationaleAgent,
        )
        from vendor.agents.ecosystems.rmn.schemas import (
            ChannelConfig,
            ChannelType,
        )
        
        # Create test channels
        channels = [
            ChannelConfig(
                channel_id="search",
                channel_type=ChannelType.SPONSORED_SEARCH,
                name="Sponsored Search",
            ),
            ChannelConfig(
                channel_id="display",
                channel_type=ChannelType.DISPLAY,
                name="Display",
            ),
        ]
        
        # Test 1: Data Ingestion Agent
        try:
            agent = RMNDataIngestionAgent(
                retailer_id="walmart",
                channels=channels,
            )
            assert agent is not None
            assert agent.config.retailer_id == "walmart"
            results.record("Data Ingestion Agent", True)
        except Exception as e:
            results.record("Data Ingestion Agent", False, str(e))
        
        # Test 2: Attribution Agent
        try:
            agent = RMNAttributionAgent(
                retailer_id="walmart",
                channels=channels,
            )
            assert agent is not None
            results.record("Attribution Agent", True)
        except Exception as e:
            results.record("Attribution Agent", False, str(e))
        
        # Test 3: Elasticity Agent
        try:
            agent = RMNElasticityAgent(
                retailer_id="walmart",
                channels=channels,
            )
            assert agent is not None
            results.record("Elasticity Agent", True)
        except Exception as e:
            results.record("Elasticity Agent", False, str(e))
        
        # Test 4: Scenario Agent
        try:
            agent = RMNScenarioAgent(
                retailer_id="walmart",
                channels=channels,
            )
            assert agent is not None
            results.record("Scenario Agent", True)
        except Exception as e:
            results.record("Scenario Agent", False, str(e))
        
        # Test 5: Twin Agent
        try:
            agent = RMNTwinAgent(
                retailer_id="walmart",
                channels=channels,
            )
            assert agent is not None
            results.record("Twin Agent", True)
        except Exception as e:
            results.record("Twin Agent", False, str(e))
        
        # Test 6: Optimizer Agent
        try:
            agent = RMNOptimizerAgent(
                retailer_id="walmart",
                channels=channels,
            )
            assert agent is not None
            results.record("Optimizer Agent", True)
        except Exception as e:
            results.record("Optimizer Agent", False, str(e))
        
        # Test 7: Governance Agent
        try:
            agent = RMNGovernanceAgent(
                retailer_id="walmart",
                channels=channels,
            )
            assert agent is not None
            results.record("Governance Agent", True)
        except Exception as e:
            results.record("Governance Agent", False, str(e))
        
        # Test 8: Rationale Agent
        try:
            agent = RMNRationaleAgent(
                retailer_id="walmart",
                channels=channels,
            )
            assert agent is not None
            results.record("Rationale Agent", True)
        except Exception as e:
            results.record("Rationale Agent", False, str(e))
        
    except Exception as e:
        results.record("RMN Agents Import", False, str(e))
        import traceback
        traceback.print_exc()


# =============================================================================
# ORCHESTRATOR TESTS
# =============================================================================

def test_autonomous_orchestrator():
    """Test autonomous orchestrator."""
    results.start_suite("Autonomous Orchestrator")
    
    try:
        from vendor.agents.ecosystems.rmn.autonomous_orchestrator import (
            CollaborationType,
            TaskStatus,
            WorkTrackType,
            CollaborationEvent,
        )
        
        # Test 1: CollaborationType enum
        try:
            assert CollaborationType.DELEGATION is not None
            assert CollaborationType.PARALLEL_EXECUTION is not None
            collab_types = list(CollaborationType)
            results.record("CollaborationType Enum", len(collab_types) >= 4,
                f"Found {len(collab_types)} collaboration types")
        except Exception as e:
            results.record("CollaborationType Enum", False, str(e))
        
        # Test 2: TaskStatus enum
        try:
            assert TaskStatus.PENDING is not None
            assert TaskStatus.RUNNING is not None
            assert TaskStatus.COMPLETED is not None
            task_statuses = list(TaskStatus)
            results.record("TaskStatus Enum", len(task_statuses) >= 4,
                f"Found {len(task_statuses)} task statuses")
        except Exception as e:
            results.record("TaskStatus Enum", False, str(e))
        
        # Test 3: WorkTrackType enum
        try:
            assert WorkTrackType.DATA_QUALITY is not None
            assert WorkTrackType.ANALYTICS is not None
            assert WorkTrackType.OPTIMIZATION is not None
            work_tracks = list(WorkTrackType)
            results.record("WorkTrackType Enum", len(work_tracks) >= 4,
                f"Found {len(work_tracks)} work track types")
        except Exception as e:
            results.record("WorkTrackType Enum", False, str(e))
        
        # Test 4: CollaborationEvent creation
        try:
            event = CollaborationEvent(
                event_id="collab_001",
                timestamp=datetime.now(),
                collaboration_type=CollaborationType.DELEGATION,
            )
            assert event.event_id == "collab_001"
            results.record("CollaborationEvent Creation", True)
        except Exception as e:
            results.record("CollaborationEvent Creation", False, str(e))
        
        # Test 5: Orchestrator import
        try:
            from vendor.agents.ecosystems.rmn.autonomous_orchestrator import (
                AutonomousRMNOrchestrator,
            )
            results.record("Orchestrator Import", True)
        except Exception as e:
            results.record("Orchestrator Import", False, str(e))
        
    except Exception as e:
        results.record("Autonomous Orchestrator Import", False, str(e))
        import traceback
        traceback.print_exc()


# =============================================================================
# AGENT ACTION TESTS
# =============================================================================

def test_agent_actions():
    """Test RMN agent actions."""
    results.start_suite("Agent Actions")
    
    try:
        from vendor.agents.ecosystems.rmn.agents import (
            RMNDataIngestionAgent,
        )
        from vendor.agents.ecosystems.rmn.schemas import (
            ChannelConfig,
            ChannelType,
            MediaSpendData,
        )
        
        # Create test channels
        channels = [
            ChannelConfig(
                channel_id="search",
                channel_type=ChannelType.SPONSORED_SEARCH,
                name="Sponsored Search",
            ),
        ]
        
        # Test 1: Data validation action
        try:
            agent = RMNDataIngestionAgent(
                retailer_id="walmart",
                channels=channels,
            )
            
            # Create test spend data
            spend_data = [
                MediaSpendData(
                    week_start=date.today(),
                    channel_id="search",
                    spend=50000.0,
                    impressions=5000000,
                    clicks=100000,
                    conversions=5000,
                    revenue=250000.0,
                ),
            ]
            
            result = agent.validate_data(spend_data)
            assert result is not None
            results.record("Data Validation Action", True)
        except Exception as e:
            results.record("Data Validation Action", False, str(e))
        
        # Test 2: Agent has required methods
        try:
            agent = RMNDataIngestionAgent(
                retailer_id="walmart",
                channels=channels,
            )
            
            # Check core agent methods exist
            has_execute = hasattr(agent, 'execute') or hasattr(agent, 'run')
            has_config = hasattr(agent, 'config')
            
            results.record("Agent Core Methods", has_config,
                f"has_config={has_config}")
        except Exception as e:
            results.record("Agent Core Methods", False, str(e))
        
        # Test 3: Agent config properties
        try:
            agent = RMNDataIngestionAgent(
                retailer_id="walmart",
                channels=channels,
            )
            
            assert agent.config.retailer_id == "walmart"
            assert hasattr(agent.config, 'role') or hasattr(agent.config, 'agent_id')
            results.record("Agent Config Properties", True)
        except Exception as e:
            results.record("Agent Config Properties", False, str(e))
        
    except Exception as e:
        results.record("Agent Actions Import", False, str(e))
        import traceback
        traceback.print_exc()


# =============================================================================
# DECISION PACK TESTS
# =============================================================================

def test_decision_pack():
    """Test RMN decision pack generation."""
    results.start_suite("Decision Pack")
    
    try:
        from vendor.agents.ecosystems.rmn.schemas import RMNDecisionPack
        
        # Test 1: Decision pack creation
        try:
            pack = RMNDecisionPack(
                pack_id="pack_001",
                retailer_id="walmart",
                created_at=datetime.now(),
                status="completed",
            )
            assert pack.pack_id == "pack_001"
            assert pack.retailer_id == "walmart"
            results.record("Decision Pack Creation", True)
        except Exception as e:
            results.record("Decision Pack Creation", False, str(e))
        
        # Test 2: Decision pack with recommendations
        try:
            pack = RMNDecisionPack(
                pack_id="pack_002",
                retailer_id="amazon",
                created_at=datetime.now(),
                status="completed",
                recommendations=[
                    {"action": "increase_search_spend", "amount": 10000},
                    {"action": "reduce_display_spend", "amount": 5000},
                ],
            )
            assert len(pack.recommendations) == 2
            results.record("Decision Pack with Recommendations", True)
        except Exception as e:
            results.record("Decision Pack with Recommendations", False, str(e))
        
    except ImportError:
        # RMNDecisionPack might have different structure
        try:
            from vendor.agents.ecosystems.rmn.schemas import (
                OptimizationResult,
                GovernanceDecision,
            )
            
            # Test alternative structures
            try:
                opt_result = OptimizationResult(
                    scenario_id="opt_001",
                    total_spend=500000.0,
                    expected_revenue=1500000.0,
                    expected_roas=3.0,
                )
                results.record("OptimizationResult Creation", True)
            except Exception as e:
                results.record("OptimizationResult Creation", False, str(e))
            
            try:
                gov_decision = GovernanceDecision(
                    decision_id="gov_001",
                    approved=True,
                    approver="governance_agent",
                    timestamp=datetime.now(),
                )
                results.record("GovernanceDecision Creation", True)
            except Exception as e:
                results.record("GovernanceDecision Creation", False, str(e))
                
        except Exception as e:
            results.record("Decision Pack Import", False, str(e))
    except Exception as e:
        results.record("Decision Pack Import", False, str(e))
        import traceback
        traceback.print_exc()


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

def test_rmn_integration():
    """Test RMN ecosystem integration."""
    results.start_suite("RMN Integration")
    
    try:
        from vendor.agents.ecosystems.rmn import (
            RMNDataIngestionAgent,
            RMNAttributionAgent,
        )
        from vendor.agents.ecosystems.rmn.schemas import (
            ChannelConfig,
            ChannelType,
            RMNConfig,
        )
        
        # Test 1: Create full RMN config
        try:
            channels = [
                ChannelConfig(
                    channel_id="search",
                    channel_type=ChannelType.SPONSORED_SEARCH,
                    name="Sponsored Search",
                    min_spend=0.0,
                    max_spend=200000.0,
                ),
                ChannelConfig(
                    channel_id="display",
                    channel_type=ChannelType.DISPLAY,
                    name="Display Ads",
                    min_spend=0.0,
                    max_spend=100000.0,
                ),
            ]
            
            config = RMNConfig(
                retailer_id="walmart",
                retailer_name="Walmart",
                channels=channels,
            )
            
            assert config.retailer_id == "walmart"
            assert len(config.channels) == 2
            results.record("Full RMN Config", True)
        except Exception as e:
            results.record("Full RMN Config", False, str(e))
        
        # Test 2: Agent coordination potential
        try:
            channels = [
                ChannelConfig(
                    channel_id="search",
                    channel_type=ChannelType.SPONSORED_SEARCH,
                    name="Search",
                ),
            ]
            
            data_agent = RMNDataIngestionAgent(
                retailer_id="walmart",
                channels=channels,
            )
            attr_agent = RMNAttributionAgent(
                retailer_id="walmart",
                channels=channels,
            )
            
            # Both agents should be able to work with same retailer
            assert data_agent.config.retailer_id == attr_agent.config.retailer_id
            results.record("Agent Coordination Setup", True)
        except Exception as e:
            results.record("Agent Coordination Setup", False, str(e))
        
        # Test 3: Module exports
        try:
            from vendor.agents.ecosystems.rmn import __init__
            results.record("Module Exports", True)
        except Exception as e:
            results.record("Module Exports", False, str(e))
        
    except Exception as e:
        results.record("RMN Integration Import", False, str(e))
        import traceback
        traceback.print_exc()


# =============================================================================
# MAIN TEST RUNNER
# =============================================================================

def run_rmn_tests():
    """Run all RMN ecosystem tests."""
    print("\n" + "="*70)
    print("RMN ECOSYSTEM TESTS")
    print("="*70)
    
    # Run all test suites
    test_rmn_schemas()
    test_rmn_agents()
    test_autonomous_orchestrator()
    test_agent_actions()
    test_decision_pack()
    test_rmn_integration()
    
    # Print summary
    success = results.summary()
    
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = run_rmn_tests()
    sys.exit(exit_code)

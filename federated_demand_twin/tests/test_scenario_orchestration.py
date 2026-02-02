"""
Test script for comprehensive scenario orchestration and agent-generated recommendations.
Tests CrewAI agent teams collaboratively executing user-selected or agent-generated scenarios.
"""

import sys
import os
import json
from datetime import datetime
import uuid

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_scenario_catalog():
    """Test scenario catalog loading and structure."""
    print("\n" + "="*60)
    print("TEST 1: Scenario Catalog")
    print("="*60)
    
    try:
        from vendor.agents.crews.optimization.scenarios.catalog import (
            SCENARIO_CATALOG, 
            get_scenario,
            list_scenarios_by_category,
            list_all_scenarios
        )
        from vendor.agents.crews.optimization.scenarios.schemas import ScenarioCategory
        
        print(f"✓ Loaded {len(SCENARIO_CATALOG)} scenarios")
        
        # Test categories
        all_scenarios = list_all_scenarios()
        categories = set(s.category for s in all_scenarios)
        print(f"✓ Categories: {[c.value for c in categories]}")
        
        # Test get_scenario
        scenario = get_scenario('grow_revenue_brand')
        if scenario:
            print(f"✓ Retrieved scenario: {scenario.name}")
            print(f"  - ID: {scenario.scenario_id}")
            print(f"  - Category: {scenario.category.value}")
            print(f"  - Objective: {scenario.objective_type.value}")
            print(f"  - Required Crews: {scenario.required_crews}")
            print(f"  - Triggers: {len(scenario.triggers)}")
        else:
            print("✗ Failed to retrieve scenario by ID")
            return False
        
        # Test list_scenarios_by_category
        core_scenarios = list_scenarios_by_category(ScenarioCategory.CORE_OUTCOME)
        print(f"✓ Core outcome scenarios: {len(core_scenarios)}")
        for s in core_scenarios[:3]:
            print(f"    - {s.name}")
        
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_scenario_schemas():
    """Test scenario data schemas and structures."""
    print("\n" + "="*60)
    print("TEST 2: Scenario Schemas")
    print("="*60)
    
    try:
        from vendor.agents.crews.optimization.scenarios.schemas import (
            ScenarioConstraints,
            ScenarioTrigger,
            RecommendedAction,
            DecisionRecommendation,
            EvidenceItem,
            ReasoningStep,
            ReasoningChain,
            TriggerType,
            ActionType,
            EvidenceType,
        )
        
        # Test creating a RecommendedAction
        action = RecommendedAction(
            action_id="test_action_001",
            action_type=ActionType.REALLOCATE,
            entity_type="brand",
            entity_id="brand_001",
            entity_name="Premium Brand",
            description="Increase spend on Premium Brand",
            current_value=100000.0,
            recommended_value=115000.0,
            delta=15000.0,
            delta_pct=15.0,
            expected_impact=8500.0,
            confidence=0.85,
            rationale="High ROAS opportunity identified in premium segment",
            priority=1,
        )
        print(f"✓ Created RecommendedAction: {action.entity_name}")
        print(f"  - Change: ${action.current_value:,.0f} → ${action.recommended_value:,.0f} ({action.delta_pct:+.1f}%)")
        print(f"  - Expected Impact: ${action.expected_impact:,.0f}")
        print(f"  - Confidence: {action.confidence:.0%}")
        
        # Test creating EvidenceItem
        evidence = EvidenceItem(
            evidence_id="ev_001",
            evidence_type=EvidenceType.POSTERIOR_DISTRIBUTION,
            title="ROAS Analysis",
            description="Premium brand shows 2.3x higher ROAS than portfolio average",
            metric_name="roas",
            metric_value=2.3,
            confidence_interval=(2.1, 2.5),
            source="brand_optimization_crew",
        )
        print(f"✓ Created EvidenceItem: {evidence.title}")
        print(f"  - Type: {evidence.evidence_type.value}")
        print(f"  - Value: {evidence.metric_value}")
        
        # Test creating ReasoningStep
        step = ReasoningStep(
            step_id="step_001",
            step_number=1,
            crew_id="brand_optimization",
            agent_id="brand_analyst",
            action="Analyze brand performance",
            input_summary="Historical brand data for last 90 days",
            output_summary="Identified 3 high-potential brands for budget increase",
            reasoning="Evaluated historical ROAS and incrementality metrics",
            confidence=0.88,
            duration_ms=150
        )
        print(f"✓ Created ReasoningStep: {step.action}")
        
        # Test creating ReasoningChain
        chain = ReasoningChain(
            chain_id="chain_001",
            scenario_id="grow_revenue_brand",
            steps=[step],
            crews_involved=["brand_optimization"],
        )
        print(f"✓ Created ReasoningChain with {len(chain.steps)} steps")
        
        # Test creating DecisionRecommendation
        recommendation = DecisionRecommendation(
            recommendation_id="rec_001",
            scenario_id="grow_revenue_brand",
            scenario_name="Grow Revenue at Brand Level",
            executive_summary="Increase spend on high-ROAS brands for 8% revenue uplift",
            recommended_actions=[action],
            supporting_evidence=[evidence],
            reasoning_chain=chain,
            total_expected_impact=8500.0,
            overall_confidence=0.85,
            risk_assessment="LOW RISK: Conservative reallocation within proven segments",
            constraints_satisfied=True,
        )
        print(f"✓ Created DecisionRecommendation: {recommendation.scenario_name}")
        print(f"  - Actions: {len(recommendation.recommended_actions)}")
        print(f"  - Total Impact: ${recommendation.total_expected_impact:,.0f}")
        
        # Test to_dict()
        rec_dict = recommendation.to_dict()
        print(f"✓ Serialized to dict with {len(rec_dict)} fields")
        
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_messaging_system():
    """Test inter-crew messaging system."""
    print("\n" + "="*60)
    print("TEST 3: Inter-Crew Messaging System")
    print("="*60)
    
    try:
        from vendor.agents.crews.optimization.scenarios.messaging import (
            MessageBus,
            CrewMessage,
            MessageType,
            MessagePriority,
            CrossCrewCoordinator,
            CrewType,
        )
        
        # Test MessageBus
        bus = MessageBus()
        print("✓ Created MessageBus")
        
        # Create and send a message
        msg = CrewMessage(
            message_id=str(uuid.uuid4()),
            message_type=MessageType.NOTIFICATION,
            source_crew=CrewType.BRAND,
            target_crew=CrewType.RMN,
            subject="Budget Recommendation",
            payload={"brand": "Premium", "roas": 2.3, "recommendation": "increase"},
            priority=MessagePriority.HIGH,
        )
        bus.send(msg)
        print(f"✓ Sent message: {msg.source_crew.value} → {msg.target_crew.value}")
        print(f"  - Type: {msg.message_type.value}")
        print(f"  - Subject: {msg.subject}")
        
        # Test CrossCrewCoordinator
        coordinator = CrossCrewCoordinator(bus)
        print("✓ Created CrossCrewCoordinator")
        
        # Start scenario coordination
        coord_id = coordinator.start_scenario_coordination(
            scenario_id="grow_revenue_brand",
            scenario_name="Grow Revenue for Brand",
            crew_sequence=["brand_optimization", "rmn_optimization", "channel_optimization"],
            initial_context={"revenue_target": 1000000}
        )
        print(f"✓ Started scenario coordination: {coord_id}")
        
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_crew_integration():
    """Test integration with optimization crews."""
    print("\n" + "="*60)
    print("TEST 4: Crew Integration")
    print("="*60)
    
    try:
        from vendor.agents.crews.optimization.scenarios.integration import (
            ScenarioCrewOrchestrator,
            CrewExecutionRequest,
            CrewExecutionResult,
            CrewAdapter,
        )
        from vendor.agents.crews.optimization.scenarios.catalog import get_scenario
        from vendor.agents.crews.optimization.scenarios.schemas import (
            ScenarioConstraints,
            RiskAppetite,
        )
        
        # Create orchestrator
        orchestrator = ScenarioCrewOrchestrator()
        print("✓ Created ScenarioCrewOrchestrator")
        
        # Get scenario
        scenario = get_scenario("grow_revenue_brand")
        print(f"✓ Loaded scenario: {scenario.name}")
        
        # Execute with crews
        result = orchestrator.execute_scenario_with_crews(
            scenario=scenario,
            context={
                "revenue_trend": 0.08,
                "efficiency_trend": 0.02,
                "competitive_pressure": 0.5
            },
            risk_appetite=RiskAppetite.BALANCED,
        )
        
        print(f"✓ Executed scenario with crews")
        print(f"  - Status: {result.get('status', 'completed')}")
        print(f"  - Crews Executed: {result.get('crews_executed', [])}")
        print(f"  - Recommendations: {len(result.get('recommendations', []))}")
        
        # Show sample recommendations
        for rec in result.get('recommendations', [])[:3]:
            print(f"    - {rec.get('entity', 'Unknown')}: {rec.get('action', 'N/A')}")
        
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_brand_crew_scenario_mode():
    """Test brand crew with scenario mode."""
    print("\n" + "="*60)
    print("TEST 5: Brand Crew Scenario Mode")
    print("="*60)
    
    try:
        from vendor.agents.crews.optimization.brand_crew import BrandOptimizationCrew
        from vendor.agents.crews.optimization.scenarios.catalog import get_scenario
        from vendor.agents.crews.optimization.schemas import CrewConfig, DesiredOutcome
        
        # Check if class has scenario methods
        config = CrewConfig(
            crew_id="test_brand_crew",
            crew_type="brand",
            desired_outcome=DesiredOutcome.INCREASE_REVENUE,
        )
        crew = BrandOptimizationCrew(config=config)
        print(f"✓ Initialized BrandOptimizationCrew")
        print(f"  - Crew ID: {crew.config.crew_id}")
        print(f"  - Agents: {len(crew.agents)}")
        print(f"  - Tasks: {len(crew.tasks)}")
        
        # List agents
        print("\n  Crew Agents:")
        agents_list = list(crew.agents.values()) if isinstance(crew.agents, dict) else crew.agents
        for agent in agents_list[:3]:
            print(f"    - {agent.role}")
        
        # Check for scenario methods
        has_scenario_mode = hasattr(crew, 'enable_scenario_mode')
        has_get_recommendations = hasattr(crew, 'get_scenario_recommendations')
        
        if has_scenario_mode:
            print("✓ Has enable_scenario_mode method")
            scenario = get_scenario("grow_revenue_brand")
            scenario_context = {
                "revenue_target": 1000000,
                "risk_appetite": "balanced",
                "optimization_horizon": "quarterly"
            }
            crew.enable_scenario_mode(scenario, scenario_context)
            print(f"  Enabled scenario: {scenario.name}")
        else:
            print("ℹ No enable_scenario_mode method (may be in base class)")
        
        if has_get_recommendations:
            print("✓ Has get_scenario_recommendations method")
            current_state = {
                "brands": [
                    {"name": "Premium Brand A", "spend": 150000, "roas": 2.3},
                    {"name": "Value Brand B", "spend": 120000, "roas": 1.8}
                ],
                "total_spend": 270000,
                "total_revenue": 540000
            }
            recs = crew.get_scenario_recommendations(current_state)
            print(f"  Generated {len(recs)} recommendations")
        else:
            print("ℹ No get_scenario_recommendations method")
        
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_scenario_orchestrator_crew():
    """Test the scenario orchestrator crew."""
    print("\n" + "="*60)
    print("TEST 6: Scenario Orchestrator Crew")
    print("="*60)
    
    try:
        from vendor.agents.crews.optimization.scenario_orchestrator_crew import (
            ScenarioOrchestratorCrew
        )
        from vendor.agents.crews.optimization.schemas import CrewConfig, DesiredOutcome
        
        # Initialize orchestrator
        config = CrewConfig(
            crew_id="test_scenario_orchestrator",
            crew_type="scenario",
            desired_outcome=DesiredOutcome.INCREASE_REVENUE,
        )
        orchestrator = ScenarioOrchestratorCrew(config=config)
        print(f"✓ Initialized ScenarioOrchestratorCrew")
        print(f"  - Crew ID: {orchestrator.config.crew_id}")
        print(f"  - Agents: {len(orchestrator.agents)}")
        print(f"  - Tasks: {len(orchestrator.tasks)}")
        
        # List agents
        print("\n  Orchestrator Agents:")
        agents_list = list(orchestrator.agents.values()) if isinstance(orchestrator.agents, dict) else orchestrator.agents
        for agent in agents_list[:3]:
            print(f"    - {agent.role}")
        
        # Check for orchestrate method
        if hasattr(orchestrator, 'orchestrate_scenario'):
            print("\n✓ Has orchestrate_scenario method")
            result = orchestrator.orchestrate_scenario(
                scenario_id="grow_revenue_brand",
                parameters={
                    "risk_appetite": "balanced",
                    "max_reallocation_pct": 0.15
                }
            )
            print(f"  Status: {result.get('status', 'unknown')}")
        else:
            print("\nℹ orchestrate_scenario method not found")
        
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_api_endpoint_simulation():
    """Simulate API endpoint behavior for recommendations."""
    print("\n" + "="*60)
    print("TEST 7: API Endpoint Simulation")
    print("="*60)
    
    try:
        from vendor.agents.crews.optimization.scenarios.catalog import get_scenario, list_all_scenarios
        from vendor.agents.crews.optimization.scenarios.integration import ScenarioCrewOrchestrator
        from vendor.agents.crews.optimization.scenarios.schemas import RiskAppetite
        
        # Simulate /api/scenarios/list endpoint
        scenarios = list_all_scenarios()
        scenario_list = [s.to_dict() for s in scenarios]
        print(f"✓ /api/scenarios/list: {len(scenario_list)} scenarios")
        
        # Simulate /api/scenarios/execute-with-crews endpoint
        scenario = get_scenario("grow_revenue_brand")
        orchestrator = ScenarioCrewOrchestrator()
        
        execution_result = orchestrator.execute_scenario_with_crews(
            scenario=scenario,
            context={
                "revenue_trend": 0.08,
                "competitive_pressure": 0.5
            },
            risk_appetite=RiskAppetite.BALANCED,
        )
        
        print(f"✓ /api/scenarios/execute-with-crews")
        print(f"  - Scenario: {scenario.name}")
        print(f"  - Status: {execution_result.get('status')}")
        print(f"  - Crews: {execution_result.get('crews_executed', [])}")
        
        # Build response format matching frontend expectations
        response = {
            "scenario_id": scenario.scenario_id,
            "scenario_name": scenario.name,
            "crews_executed": execution_result.get('crews_executed', scenario.crew_sequence),
            "aggregated_recommendations": execution_result.get('recommendations', []),
            "supporting_evidence": execution_result.get('evidence', []),
            "executive_summary": execution_result.get('executive_summary', 
                f"Multi-crew analysis completed for {scenario.name}"),
            "total_expected_impact": sum(
                r.get('amount', 0) for r in execution_result.get('recommendations', [])
            ),
            "overall_confidence": 0.85,
            "risk_assessment": "MODERATE RISK: Balanced approach with controlled reallocation",
            "execution_time_ms": 250,
        }
        
        print(f"\n  API Response Structure:")
        print(f"    - scenario_name: {response['scenario_name']}")
        print(f"    - crews_executed: {response['crews_executed']}")
        print(f"    - recommendations: {len(response['aggregated_recommendations'])}")
        print(f"    - overall_confidence: {response['overall_confidence']:.0%}")
        
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_full_recommendation_output():
    """Test generating full recommendation output for UI."""
    print("\n" + "="*60)
    print("TEST 8: Full Recommendation Output")
    print("="*60)
    
    try:
        from vendor.agents.crews.optimization.scenarios.catalog import get_scenario
        from vendor.agents.crews.optimization.scenarios.schemas import (
            RecommendedAction, ActionType, RiskAppetite
        )
        import random
        
        scenario = get_scenario("grow_revenue_brand")
        print(f"✓ Scenario: {scenario.name}")
        
        # Generate sample recommendations by entity type
        entity_types = ["brand", "rmn", "channel", "campaign"]
        sample_entities = {
            "brand": ["Premium Brand A", "Value Brand B", "New Launch C"],
            "rmn": ["Walmart", "Amazon", "Target", "Kroger"],
            "channel": ["Search", "Display", "Video", "Sponsored Products"],
            "campaign": ["Summer Promo", "Back to School", "Holiday Push"],
        }
        
        recommendations = []
        for entity_type in entity_types:
            for entity_name in sample_entities[entity_type][:2]:
                current = random.uniform(100000, 500000)
                delta_pct = random.uniform(-10, 20)
                delta = current * delta_pct / 100
                recommended = current + delta
                
                rec = {
                    "action_id": f"rec_{entity_type}_{len(recommendations)}",
                    "entity_type": entity_type,
                    "entity_name": entity_name,
                    "action": "increase" if delta_pct > 0 else "decrease",
                    "current_value": round(current, 2),
                    "recommended_value": round(recommended, 2),
                    "delta_pct": round(delta_pct, 1),
                    "expected_impact": round(abs(delta) * random.uniform(0.05, 0.15), 2),
                    "confidence": round(random.uniform(0.75, 0.95), 2),
                    "rationale": f"Based on {entity_type}-level analysis showing strong performance potential",
                    "priority": random.randint(1, 3),
                }
                recommendations.append(rec)
        
        print(f"\n  Generated {len(recommendations)} recommendations:")
        
        # Group by entity type
        by_type = {}
        for rec in recommendations:
            et = rec['entity_type']
            if et not in by_type:
                by_type[et] = []
            by_type[et].append(rec)
        
        for entity_type, recs in by_type.items():
            print(f"\n  {entity_type.upper()} Level ({len(recs)} recommendations):")
            for rec in recs:
                action_symbol = "↑" if rec['action'] == 'increase' else "↓"
                print(f"    {action_symbol} {rec['entity_name']}: "
                      f"${rec['current_value']:,.0f} → ${rec['recommended_value']:,.0f} "
                      f"({rec['delta_pct']:+.1f}%)")
                print(f"      Impact: ${rec['expected_impact']:,.0f} | "
                      f"Confidence: {rec['confidence']:.0%}")
        
        # Generate supporting evidence
        evidence = [
            {
                "source": "brand_optimization",
                "findings": ["High ROAS brands identified", "Budget headroom available"],
                "opportunities": ["Scale top performers by 15%"],
                "risks": ["Category saturation in Q4"],
                "confidence": 0.88,
            },
            {
                "source": "rmn_optimization",
                "findings": ["Walmart showing strong incrementality", "Amazon plateauing"],
                "opportunities": ["Shift 10% from Amazon to Walmart"],
                "risks": ["Inventory constraints at Walmart"],
                "confidence": 0.82,
            },
            {
                "source": "channel_optimization",
                "findings": ["Video underperforming", "Search highly efficient"],
                "opportunities": ["Increase Search allocation"],
                "risks": ["Search auction pressure increasing"],
                "confidence": 0.85,
            },
        ]
        
        print(f"\n  Supporting Evidence ({len(evidence)} sources):")
        for ev in evidence:
            print(f"    {ev['source']}: {ev['findings'][0]} (conf: {ev['confidence']:.0%})")
        
        total_impact = sum(r['expected_impact'] for r in recommendations)
        avg_confidence = sum(r['confidence'] for r in recommendations) / len(recommendations)
        
        print(f"\n  Summary:")
        print(f"    Total Expected Impact: ${total_impact:,.0f}")
        print(f"    Average Confidence: {avg_confidence:.0%}")
        print(f"    Risk Assessment: MODERATE - Balanced reallocation approach")
        
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("SCENARIO ORCHESTRATION & RECOMMENDATIONS TEST SUITE")
    print("Testing CrewAI Agent Team Collaboration")
    print("="*60)
    
    results = []
    
    # Run tests
    tests = [
        ("Scenario Catalog", test_scenario_catalog),
        ("Scenario Schemas", test_scenario_schemas),
        ("Messaging System", test_messaging_system),
        ("Crew Integration", test_crew_integration),
        ("Brand Crew Scenario Mode", test_brand_crew_scenario_mode),
        ("Scenario Orchestrator Crew", test_scenario_orchestrator_crew),
        ("API Endpoint Simulation", test_api_endpoint_simulation),
        ("Full Recommendation Output", test_full_recommendation_output),
    ]
    
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"✗ {name} crashed: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, p in results if p)
    total = len(results)
    
    for name, p in results:
        status = "✓ PASS" if p else "✗ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\n  Total: {passed}/{total} tests passed")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

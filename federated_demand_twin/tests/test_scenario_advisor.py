"""
Tests for the Scenario Advisor conversational interface.

Tests cover:
- OpenAI client initialization and mock responses
- Session management (create, get, delete)
- Tool function handlers for RMN and D&P ecosystems
- Message handling and response formatting
"""

import sys
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestResults:
    """Track test results across suites"""
    def __init__(self):
        self.results = {}
        self.current_suite = ""
    
    def start_suite(self, name: str):
        self.current_suite = name
        self.results[name] = {"passed": 0, "failed": 0, "tests": []}
    
    def record(self, test_name: str, passed: bool, detail: str = ""):
        status = "✓" if passed else "✗"
        self.results[self.current_suite]["tests"].append({
            "name": test_name,
            "passed": passed,
            "detail": detail
        })
        if passed:
            self.results[self.current_suite]["passed"] += 1
        else:
            self.results[self.current_suite]["failed"] += 1
        print(f"  {status} {test_name}")
        if detail and not passed:
            print(f"      {detail}")
    
    def summary(self):
        print("\n" + "=" * 70)
        print("SCENARIO ADVISOR TEST SUMMARY")
        print("=" * 70 + "\n")
        
        total_passed = 0
        total_failed = 0
        
        for suite, data in self.results.items():
            passed = data["passed"]
            failed = data["failed"]
            total = passed + failed
            total_passed += passed
            total_failed += failed
            
            status = "✓" if failed == 0 else "✗"
            print(f"{status} {suite}: {passed}/{total} passed")
            
            for test in data["tests"]:
                if not test["passed"]:
                    print(f"    ✗ FAILED: {test['name']}")
        
        print("\n" + "=" * 70)
        total = total_passed + total_failed
        print(f"TOTAL: {total_passed}/{total} tests passed")
        print("=" * 70)
        
        return total_failed == 0


results = TestResults()


def test_openai_client():
    """Test OpenAI client initialization and mock responses"""
    print("\n" + "=" * 70)
    print("ADVISOR TEST SUITE: OpenAI Client")
    print("=" * 70)
    results.start_suite("OpenAI Client")
    
    from vendor.agents.conversation.openai_client import (
        OpenAIClient, ChatMessage, MessageRole, FunctionDefinition
    )
    
    # Test 1: Client creation without API key
    try:
        client = OpenAIClient(api_key=None)
        assert client is not None
        results.record("Client Creation (no key)", True,
            f"Available: {client.is_available}")
    except Exception as e:
        results.record("Client Creation (no key)", False, str(e))
    
    # Test 2: ChatMessage creation
    try:
        msg = ChatMessage(
            role=MessageRole.USER,
            content="Test message"
        )
        assert msg.role == MessageRole.USER
        assert msg.content == "Test message"
        results.record("ChatMessage Creation", True)
    except Exception as e:
        results.record("ChatMessage Creation", False, str(e))
    
    # Test 3: ChatMessage to_dict
    try:
        msg = ChatMessage(role=MessageRole.ASSISTANT, content="Response")
        d = msg.to_dict()
        assert d["role"] == "assistant"
        assert d["content"] == "Response"
        results.record("ChatMessage to_dict", True)
    except Exception as e:
        results.record("ChatMessage to_dict", False, str(e))
    
    # Test 4: FunctionDefinition creation
    try:
        func = FunctionDefinition(
            name="test_func",
            description="A test function",
            parameters={"type": "object", "properties": {}}
        )
        assert func.name == "test_func"
        tool = func.to_tool_dict()
        assert tool["type"] == "function"
        assert tool["function"]["name"] == "test_func"
        results.record("FunctionDefinition Creation", True)
    except Exception as e:
        results.record("FunctionDefinition Creation", False, str(e))
    
    # Test 5: Mock response generation
    try:
        client = OpenAIClient(api_key=None)
        messages = [ChatMessage(role=MessageRole.USER, content="What scenarios are available?")]
        response = client._mock_response(messages)
        assert "content" in response
        assert len(response["content"]) > 0
        results.record("Mock Response Generation", True)
    except Exception as e:
        results.record("Mock Response Generation", False, str(e))
    
    # Test 6: Function registration
    try:
        client = OpenAIClient(api_key=None)
        func = FunctionDefinition(
            name="get_scenarios",
            description="Get scenarios",
            parameters={"type": "object", "properties": {}},
            handler=lambda: {"scenarios": []}
        )
        client.register_function(func)
        assert "get_scenarios" in client.functions
        tools = client.get_tools()
        assert len(tools) == 1
        results.record("Function Registration", True)
    except Exception as e:
        results.record("Function Registration", False, str(e))


def test_scenario_advisor():
    """Test UnifiedScenarioAdvisor core functionality"""
    print("\n" + "=" * 70)
    print("ADVISOR TEST SUITE: Scenario Advisor")
    print("=" * 70)
    results.start_suite("Scenario Advisor")
    
    from vendor.agents.conversation.scenario_advisor import (
        UnifiedScenarioAdvisor, AdvisorSession, AdvisorResponse,
        Ecosystem, create_advisor
    )
    
    # Test 1: Advisor creation via factory
    try:
        advisor = create_advisor()
        assert advisor is not None
        assert advisor.client is not None
        results.record("Advisor Creation", True)
    except Exception as e:
        results.record("Advisor Creation", False, str(e))
    
    # Test 2: Session creation
    try:
        advisor = create_advisor()
        session = advisor.create_session(ecosystem=Ecosystem.RMN)
        assert session is not None
        assert session.session_id is not None
        assert session.ecosystem == Ecosystem.RMN
        assert len(session.messages) == 1  # System message
        results.record("Session Creation", True,
            f"Session ID: {session.session_id[:8]}...")
    except Exception as e:
        results.record("Session Creation", False, str(e))
    
    # Test 3: Get session
    try:
        advisor = create_advisor()
        session = advisor.create_session()
        retrieved = advisor.get_session(session.session_id)
        assert retrieved is not None
        assert retrieved.session_id == session.session_id
        results.record("Get Session", True)
    except Exception as e:
        results.record("Get Session", False, str(e))
    
    # Test 4: Delete session
    try:
        advisor = create_advisor()
        session = advisor.create_session()
        deleted = advisor.delete_session(session.session_id)
        assert deleted is True
        assert advisor.get_session(session.session_id) is None
        results.record("Delete Session", True)
    except Exception as e:
        results.record("Delete Session", False, str(e))
    
    # Test 5: Send message (uses mock)
    try:
        advisor = create_advisor()
        session = advisor.create_session()
        response = advisor.send_message(
            session.session_id,
            "What scenarios are available?"
        )
        assert response is not None
        assert response.message is not None
        assert len(response.message) > 0
        results.record("Send Message", True,
            f"Response length: {len(response.message)}")
    except Exception as e:
        results.record("Send Message", False, str(e))
    
    # Test 6: Session history
    try:
        advisor = create_advisor()
        session = advisor.create_session()
        advisor.send_message(session.session_id, "Hello")
        history = session.get_history()
        assert len(history) >= 2  # System + user + assistant
        results.record("Session History", True,
            f"Messages: {len(history)}")
    except Exception as e:
        results.record("Session History", False, str(e))


def test_rmn_tools():
    """Test RMN-specific tool handlers"""
    print("\n" + "=" * 70)
    print("ADVISOR TEST SUITE: RMN Tool Handlers")
    print("=" * 70)
    results.start_suite("RMN Tool Handlers")
    
    from vendor.agents.conversation.scenario_advisor import create_advisor
    
    advisor = create_advisor()
    
    # Test 1: Get RMN scenarios
    try:
        result = advisor._get_rmn_scenarios(category="all")
        assert "scenarios" in result
        assert "count" in result
        assert result["count"] > 0
        results.record("Get RMN Scenarios (all)", True,
            f"Found {result['count']} scenarios")
    except Exception as e:
        results.record("Get RMN Scenarios (all)", False, str(e))
    
    # Test 2: Get scenarios by category
    try:
        result = advisor._get_rmn_scenarios(category="core_outcome")
        assert "scenarios" in result
        results.record("Get RMN Scenarios (category)", True)
    except Exception as e:
        results.record("Get RMN Scenarios (category)", False, str(e))
    
    # Test 3: Get scenario details
    try:
        result = advisor._get_scenario_details("grow_revenue_brand")
        assert "scenario_id" in result or "error" not in result
        results.record("Get Scenario Details", True)
    except Exception as e:
        results.record("Get Scenario Details", False, str(e))
    
    # Test 4: Recommend RMN scenario
    try:
        result = advisor._recommend_rmn_scenario(
            objective="grow revenue",
            risk_appetite="balanced"
        )
        assert "recommended_scenario" in result
        assert "rationale" in result
        results.record("Recommend RMN Scenario", True,
            f"Recommended: {result['recommended_scenario']}")
    except Exception as e:
        results.record("Recommend RMN Scenario", False, str(e))


def test_dp_tools():
    """Test Demand/Procurement tool handlers"""
    print("\n" + "=" * 70)
    print("ADVISOR TEST SUITE: D&P Tool Handlers")
    print("=" * 70)
    results.start_suite("D&P Tool Handlers")
    
    from vendor.agents.conversation.scenario_advisor import create_advisor
    
    advisor = create_advisor()
    
    # Test 1: Get demand forecast
    try:
        result = advisor._get_demand_forecast("SKU-001", horizon_weeks=8)
        assert "sku_id" in result
        assert "forecasts" in result
        assert len(result["forecasts"]) == 8
        results.record("Get Demand Forecast", True,
            f"Forecast horizon: {len(result['forecasts'])} weeks")
    except Exception as e:
        results.record("Get Demand Forecast", False, str(e))
    
    # Test 2: Get inventory policy
    try:
        result = advisor._get_inventory_policy("SKU-001")
        assert "sku_id" in result
        assert "reorder_point" in result
        assert "order_quantity" in result
        assert "safety_stock" in result
        results.record("Get Inventory Policy", True,
            f"ROP: {result['reorder_point']}, SS: {result['safety_stock']}")
    except Exception as e:
        results.record("Get Inventory Policy", False, str(e))
    
    # Test 3: Assess stockout risk
    try:
        result = advisor._assess_stockout_risk("SKU-001", current_inventory=50)
        assert "sku_id" in result
        assert "stockout_probability" in result
        assert "risk_level" in result
        results.record("Assess Stockout Risk", True,
            f"Risk: {result['risk_level']}, P(stockout): {result['stockout_probability']:.1%}")
    except Exception as e:
        results.record("Assess Stockout Risk", False, str(e))
    
    # Test 4: Compare D&P scenarios
    try:
        result = advisor._compare_dp_scenarios(
            "SKU-001",
            scenarios=["baseline", "conservative"]
        )
        assert "scenarios" in result
        assert "recommended_scenario" in result
        results.record("Compare D&P Scenarios", True,
            f"Recommended: {result['recommended_scenario']}")
    except Exception as e:
        results.record("Compare D&P Scenarios", False, str(e))
    
    # Test 5: Get procurement plan
    try:
        result = advisor._get_procurement_plan(sku_ids=["SKU-001", "SKU-002"])
        assert "plans" in result
        assert "total_orders" in result
        results.record("Get Procurement Plan", True,
            f"Total orders: {result['total_orders']}")
    except Exception as e:
        results.record("Get Procurement Plan", False, str(e))


def test_advisor_response():
    """Test AdvisorResponse dataclass"""
    print("\n" + "=" * 70)
    print("ADVISOR TEST SUITE: Response Formatting")
    print("=" * 70)
    results.start_suite("Response Formatting")
    
    from vendor.agents.conversation.scenario_advisor import AdvisorResponse, Ecosystem
    
    # Test 1: Basic response creation
    try:
        response = AdvisorResponse(
            message="Test response",
            ecosystem=Ecosystem.RMN,
            confidence=0.85
        )
        assert response.message == "Test response"
        assert response.ecosystem == Ecosystem.RMN
        assert response.confidence == 0.85
        results.record("Basic Response Creation", True)
    except Exception as e:
        results.record("Basic Response Creation", False, str(e))
    
    # Test 2: Response to_dict
    try:
        response = AdvisorResponse(
            message="Test",
            ecosystem=Ecosystem.DEMAND_PROCUREMENT,
            scenario_ids=["baseline", "conservative"],
            confidence=0.9
        )
        d = response.to_dict()
        assert d["message"] == "Test"
        assert d["ecosystem"] == "demand_procurement"
        assert len(d["scenario_ids"]) == 2
        results.record("Response to_dict", True)
    except Exception as e:
        results.record("Response to_dict", False, str(e))
    
    # Test 3: Response with data
    try:
        response = AdvisorResponse(
            message="Analysis complete",
            data={"stockout_risk": 0.15, "recommendation": "order"},
            actions=[{"type": "order", "label": "Place Order"}]
        )
        assert response.data is not None
        assert len(response.actions) == 1
        results.record("Response with Data", True)
    except Exception as e:
        results.record("Response with Data", False, str(e))


def test_ecosystem_detection():
    """Test ecosystem detection from message content"""
    print("\n" + "=" * 70)
    print("ADVISOR TEST SUITE: Ecosystem Detection")
    print("=" * 70)
    results.start_suite("Ecosystem Detection")
    
    from vendor.agents.conversation.scenario_advisor import (
        create_advisor, Ecosystem
    )
    
    advisor = create_advisor()
    
    # Test 1: Detect RMN
    try:
        ecosystem = advisor._detect_ecosystem(
            "What's the ROAS for my media spend on sponsored search?"
        )
        assert ecosystem == Ecosystem.RMN
        results.record("Detect RMN Keywords", True)
    except Exception as e:
        results.record("Detect RMN Keywords", False, str(e))
    
    # Test 2: Detect D&P
    try:
        ecosystem = advisor._detect_ecosystem(
            "What's the stockout risk for my inventory forecast?"
        )
        assert ecosystem == Ecosystem.DEMAND_PROCUREMENT
        results.record("Detect D&P Keywords", True)
    except Exception as e:
        results.record("Detect D&P Keywords", False, str(e))
    
    # Test 3: Ambiguous content
    try:
        ecosystem = advisor._detect_ecosystem(
            "Hello, can you help me?"
        )
        # Should return None for ambiguous
        assert ecosystem is None
        results.record("Handle Ambiguous Content", True)
    except Exception as e:
        results.record("Handle Ambiguous Content", False, str(e))


def run_all_tests():
    """Run all test suites"""
    print("\n" + "=" * 70)
    print("SCENARIO ADVISOR TESTS")
    print("=" * 70)
    
    test_openai_client()
    test_scenario_advisor()
    test_rmn_tools()
    test_dp_tools()
    test_advisor_response()
    test_ecosystem_detection()
    
    return results.summary()


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

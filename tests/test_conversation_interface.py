"""Unit tests for the Scenario Advisor conversational interface — 59 tests.

Tests cover:
- Session management
- Ecosystem detection
- Intent inference
- Offline parameter extraction
- Current state retrieval
- Tool registration
- Scenario catalog
- RMN tool handlers
- D&P tool handlers
- Offline message handling
- Response serialization
- Send message pipeline
- Factory function
"""

import os
import sys
import json
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

# Ensure project root on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from predictive_maintenance.services.advisor.rag_store import RagStore
from predictive_maintenance.services.advisor.openai_client import OpenAIClient
from predictive_maintenance.services.advisor.scenario_advisor import (
    UnifiedScenarioAdvisor,
    AdvisorSession,
    AdvisorResponse,
    ChatMessage,
    MessageRole,
    Ecosystem,
    create_advisor,
    SYSTEM_PROMPT,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def rag():
    """In-memory RAG store with no persistence."""
    store = RagStore.__new__(RagStore)
    store.namespace = "test"
    store.dim = 64
    store.embedding_model = "test"
    store._docs = []
    store._openai_client = None
    store._use_openai = False
    store._store_path = None
    return store


@pytest.fixture
def client():
    """Offline OpenAI client (is_available=False)."""
    c = OpenAIClient.__new__(OpenAIClient)
    c.model = "gpt-4-turbo-preview"
    c.temperature = 0.7
    c.max_tokens = 2048
    c._api_key = None
    c._client = None
    c.functions = {}
    return c


@pytest.fixture
def advisor(rag, client):
    """Advisor instance with offline client and in-memory RAG."""
    return UnifiedScenarioAdvisor(rag=rag, client=client)


# ===========================================================================
# TestSessionManagement (7 tests)
# ===========================================================================

class TestSessionManagement:

    def test_create_session_returns_session(self, advisor):
        session = advisor.create_session()
        assert isinstance(session, AdvisorSession)
        assert session.session_id in advisor.sessions

    def test_create_session_with_ecosystem(self, advisor):
        session = advisor.create_session(ecosystem="rmn")
        assert session.ecosystem == Ecosystem.RMN

    def test_create_session_auto_ecosystem(self, advisor):
        session = advisor.create_session(ecosystem="auto")
        assert session.ecosystem == Ecosystem.AUTO

    def test_get_session(self, advisor):
        session = advisor.create_session()
        found = advisor.get_session(session.session_id)
        assert found is session

    def test_get_session_not_found(self, advisor):
        assert advisor.get_session("nonexistent") is None

    def test_delete_session(self, advisor):
        session = advisor.create_session()
        assert advisor.delete_session(session.session_id) is True
        assert advisor.get_session(session.session_id) is None

    def test_session_isolation(self, advisor):
        s1 = advisor.create_session()
        s2 = advisor.create_session()
        s1.add_message(MessageRole.USER, "hello from s1")
        assert len(s1.messages) != len(s2.messages)

    def test_system_prompt_injected(self, advisor):
        session = advisor.create_session()
        assert len(session.messages) >= 1
        assert session.messages[0].role == MessageRole.SYSTEM
        assert "LoweConex" in session.messages[0].content


# ===========================================================================
# TestEcosystemDetection (3 tests)
# ===========================================================================

class TestEcosystemDetection:

    def test_rmn_keywords(self, advisor):
        result = advisor._detect_ecosystem("What is the ROAS for our media channels?")
        assert result == Ecosystem.RMN

    def test_dp_keywords(self, advisor):
        result = advisor._detect_ecosystem("Show inventory levels and demand forecast for SKU")
        assert result == Ecosystem.DEMAND_PROCUREMENT

    def test_ambiguous_input(self, advisor):
        result = advisor._detect_ecosystem("Hello, how are you?")
        assert result is None


# ===========================================================================
# TestIntentInference (10 tests)
# ===========================================================================

class TestIntentInference:

    def test_rebalance_intent(self, advisor):
        assert advisor._infer_scenario_from_intent("rebalance the portfolio") == "rebalance_portfolio"

    def test_shift_budget_intent(self, advisor):
        assert advisor._infer_scenario_from_intent("shift budget from walmart") == "rebalance_portfolio"

    def test_grow_revenue_intent(self, advisor):
        assert advisor._infer_scenario_from_intent("grow revenue for brand X") == "grow_revenue_brand"

    def test_increase_sales_intent(self, advisor):
        assert advisor._infer_scenario_from_intent("increase sales across retailers") == "grow_revenue_brand"

    def test_maximize_roas_intent(self, advisor):
        assert advisor._infer_scenario_from_intent("maximize roas for Q2") == "maximize_roas"

    def test_maintain_intent(self, advisor):
        assert advisor._infer_scenario_from_intent("maintain current levels") == "maintain_revenue"

    def test_prevent_decline_intent(self, advisor):
        assert advisor._infer_scenario_from_intent("prevent decline in sales") == "prevent_decline"

    def test_experiment_intent(self, advisor):
        assert advisor._infer_scenario_from_intent("run a test for incrementality") == "experiment_incrementality"

    def test_maximize_profit_intent(self, advisor):
        assert advisor._infer_scenario_from_intent("maximize profit for the quarter") == "maximize_profit"

    def test_no_match(self, advisor):
        assert advisor._infer_scenario_from_intent("tell me a joke") is None


# ===========================================================================
# TestOfflineParamExtraction (9 tests)
# ===========================================================================

class TestOfflineParamExtraction:

    def test_extract_retailer_walmart(self, advisor):
        params = advisor._extract_offline_params("shift budget from walmart to target")
        assert "walmart" in params["target_rmns"]
        assert "target" in params["target_rmns"]

    def test_extract_retailer_kroger(self, advisor):
        params = advisor._extract_offline_params("focus on kroger campaigns")
        assert "kroger" in params["target_rmns"]

    def test_extract_channel(self, advisor):
        params = advisor._extract_offline_params("shift from search to display")
        assert "search" in params["target_channels"]
        assert "display" in params["target_channels"]

    def test_extract_percentage(self, advisor):
        params = advisor._extract_offline_params("shift 20% of budget")
        assert params["reallocation_pct"] == 0.20

    def test_extract_budget_millions(self, advisor):
        params = advisor._extract_offline_params("budget is $2m")
        assert params["budget_total"] == 2_000_000

    def test_extract_budget_thousands(self, advisor):
        params = advisor._extract_offline_params("budget of 500k")
        assert params["budget_total"] == 500_000

    def test_extract_roas_floor(self, advisor):
        params = advisor._extract_offline_params("keep roas above 3.5")
        assert params["roas_floor"] == 3.5

    def test_extract_combined(self, advisor):
        params = advisor._extract_offline_params(
            "rebalance 15% from walmart to target with roas floor 3.0 and $1.5m budget"
        )
        assert "walmart" in params.get("target_rmns", [])
        assert "target" in params.get("target_rmns", [])
        assert params.get("reallocation_pct") == 0.15

    def test_extract_no_params(self, advisor):
        params = advisor._extract_offline_params("hello world")
        assert "target_rmns" not in params
        assert "target_channels" not in params


# ===========================================================================
# TestCurrentStateRetrieval (4 tests)
# ===========================================================================

class TestCurrentStateRetrieval:

    def test_full_portfolio(self, advisor):
        state = advisor._get_current_state()
        assert "retailers" in state
        assert "walmart" in state["retailers"]
        assert "total_spend" in state

    def test_single_retailer(self, advisor):
        state = advisor._get_current_state("walmart")
        assert state.get("retailer_id") == "walmart"
        assert "spend" in state

    def test_unknown_retailer(self, advisor):
        state = advisor._get_current_state("nonexistent")
        assert "error" in state
        assert "available" in state

    def test_schema_validation(self, advisor):
        state = advisor._get_current_state()
        for name, data in state["retailers"].items():
            assert "spend" in data
            assert "roas" in data
            assert "channels" in data
            assert isinstance(data["spend"], (int, float))


# ===========================================================================
# TestToolRegistration (3 tests)
# ===========================================================================

class TestToolRegistration:

    def test_rmn_tools_count(self, advisor):
        rmn_tools = [n for n in advisor.client.functions if not n.startswith("dp_")]
        assert len(rmn_tools) == 6

    def test_dp_tools_count(self, advisor):
        dp_tools = [n for n in advisor.client.functions if n.startswith("dp_")]
        assert len(dp_tools) == 5

    def test_total_tool_count(self, advisor):
        assert len(advisor.client.functions) == 11


# ===========================================================================
# TestScenarioCatalog (4 tests)
# ===========================================================================

class TestScenarioCatalog:

    def test_catalog_loaded(self, advisor):
        assert len(advisor.catalog) == 21

    def test_match_by_id(self, advisor):
        result = advisor._match_scenario_id("run rebalance_portfolio now")
        assert result == "rebalance_portfolio"

    def test_match_by_name(self, advisor):
        result = advisor._match_scenario_id("execute Maximize ROAS scenario")
        assert result == "maximize_roas"

    def test_no_match(self, advisor):
        result = advisor._match_scenario_id("random text with no scenario")
        assert result is None


# ===========================================================================
# TestRMNToolHandlers (5 tests)
# ===========================================================================

class TestRMNToolHandlers:

    def test_get_rmn_scenarios(self, advisor):
        result = advisor._tool_get_rmn_scenarios()
        assert result["count"] == 21
        assert len(result["scenarios"]) == 21

    def test_get_rmn_scenarios_filtered(self, advisor):
        result = advisor._tool_get_rmn_scenarios(category="core_outcome")
        assert result["count"] == 5
        assert all(s["category"] == "core_outcome" for s in result["scenarios"])

    def test_get_scenario_details_found(self, advisor):
        result = advisor._tool_get_scenario_details("grow_revenue_brand")
        assert result["scenario_id"] == "grow_revenue_brand"
        assert "name" in result

    def test_get_scenario_details_not_found(self, advisor):
        result = advisor._tool_get_scenario_details("nonexistent")
        assert "error" in result

    def test_recommend_scenario(self, advisor):
        result = advisor._tool_recommend_scenario("improve return on ad spend")
        assert "recommended_scenario_id" in result
        assert "match_score" in result


# ===========================================================================
# TestDPToolHandlers (5 tests)
# ===========================================================================

class TestDPToolHandlers:

    def test_demand_forecast(self, advisor):
        result = advisor._tool_dp_demand_forecast("SKU-001")
        assert result["sku_id"] == "SKU-001"
        assert "forecast" in result
        assert "mean_daily_demand" in result["forecast"]

    def test_inventory_policy(self, advisor):
        result = advisor._tool_dp_inventory_policy("SKU-001", service_level=0.95)
        assert result["sku_id"] == "SKU-001"
        assert "policy" in result
        assert "reorder_point" in result["policy"]

    def test_stockout_risk(self, advisor):
        result = advisor._tool_dp_stockout_risk("SKU-001")
        assert "risk_assessment" in result
        assert "stockout_probability" in result["risk_assessment"]

    def test_compare_scenarios(self, advisor):
        result = advisor._tool_dp_compare_scenarios("scenario_a", "scenario_b")
        assert "comparison" in result
        assert "recommendation" in result["comparison"]

    def test_procurement_plan(self, advisor):
        result = advisor._tool_dp_procurement_plan("beverages")
        assert result["category"] == "beverages"
        assert "plan" in result
        assert "orders" in result["plan"]


# ===========================================================================
# TestOfflineMessageHandling (5 tests)
# ===========================================================================

class TestOfflineMessageHandling:

    def test_intent_based_execution(self, advisor):
        session = advisor.create_session()
        response = advisor.send_message(session.session_id, "grow revenue for our brands")
        assert response.agent_source == "scenario_executor"
        assert "grow_revenue_brand" in response.scenario_ids

    def test_parameterized_execution(self, advisor):
        session = advisor.create_session()
        response = advisor.send_message(
            session.session_id, "rebalance 20% from walmart to target"
        )
        assert response.agent_source == "scenario_executor"
        assert response.data is not None

    def test_state_query(self, advisor):
        session = advisor.create_session()
        response = advisor.send_message(session.session_id, "show current allocation")
        assert response.agent_source == "state_lookup"
        assert response.confidence == 0.8

    def test_rag_fallback(self, advisor):
        # Index a knowledge doc first
        advisor.rag.index_document(
            doc_type="knowledge",
            content="Important information about ROAS optimization",
            metadata={"topic": "roas"},
        )
        session = advisor.create_session()
        response = advisor.send_message(session.session_id, "ROAS optimization tips for new users")
        # Should hit RAG fallback since no intent match and no state keywords
        assert response.agent_source in ("rag_fallback", "scenario_executor", "state_lookup")

    def test_final_fallback(self, advisor):
        session = advisor.create_session()
        response = advisor.send_message(session.session_id, "xyzzy foobar gibberish")
        assert response.agent_source in ("offline", "rag_fallback")
        assert response.confidence <= 0.6


# ===========================================================================
# TestAdvisorResponseSerialization (2 tests)
# ===========================================================================

class TestAdvisorResponseSerialization:

    def test_to_dict_with_ecosystem(self):
        resp = AdvisorResponse(
            message="test", ecosystem=Ecosystem.RMN,
            scenario_ids=["s1"], confidence=0.9, agent_source="openai",
        )
        d = resp.to_dict()
        assert d["ecosystem"] == "rmn"
        assert d["scenario_ids"] == ["s1"]
        assert d["confidence"] == 0.9

    def test_to_dict_without_ecosystem(self):
        resp = AdvisorResponse(message="test", confidence=0.5)
        d = resp.to_dict()
        assert d["ecosystem"] is None
        assert d["message"] == "test"


# ===========================================================================
# TestSendMessage (2 tests)
# ===========================================================================

class TestSendMessage:

    def test_invalid_session(self, advisor):
        response = advisor.send_message("nonexistent", "hello")
        assert response.confidence == 0.0
        assert "not found" in response.message.lower()

    def test_valid_session_basic(self, advisor):
        session = advisor.create_session()
        response = advisor.send_message(session.session_id, "show current state")
        assert response.message
        assert len(session.messages) >= 3  # system + user + assistant


# ===========================================================================
# TestFactory (1 test)
# ===========================================================================

class TestFactory:

    def test_create_advisor(self, rag, client):
        advisor = create_advisor(rag=rag, client=client)
        assert isinstance(advisor, UnifiedScenarioAdvisor)
        assert advisor.rag is rag
        assert advisor.client is client

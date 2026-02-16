"""Integration tests for the Scenario Advisor conversational interface — 34 tests.

Tests cover:
- Multi-turn RMN scenario direction
- Multi-turn D&P conversations
- Cross-ecosystem auto-detection
- RAG accumulation
- Scenario agent direction patterns
- Edge cases
- Response round-trip serialization
- Conversation-level RAG
"""

import os
import sys
import json
import pytest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from predictive_maintenance.services.advisor.rag_store import RagStore
from predictive_maintenance.services.advisor.openai_client import OpenAIClient
from predictive_maintenance.services.advisor.scenario_advisor import (
    UnifiedScenarioAdvisor,
    AdvisorResponse,
    Ecosystem,
    MessageRole,
    create_advisor,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def rag():
    store = RagStore.__new__(RagStore)
    store.namespace = "test_integration"
    store.dim = 64
    store.embedding_model = "test"
    store._docs = []
    store._openai_client = None
    store._use_openai = False
    store._store_path = None
    return store


@pytest.fixture
def client():
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
    return UnifiedScenarioAdvisor(rag=rag, client=client)


# ===========================================================================
# TestRMNMultiTurnScenarioDirection (6 tests)
# ===========================================================================

class TestRMNMultiTurnScenarioDirection:
    """5-turn conversation: state → reallocation → RAG retrieval → grow revenue → history check."""

    def test_turn1_current_state(self, advisor):
        session = advisor.create_session(ecosystem="rmn")
        resp = advisor.send_message(session.session_id, "Show current allocation")
        assert resp.agent_source == "state_lookup"
        assert resp.confidence == 0.8

    def test_turn2_rebalance(self, advisor):
        session = advisor.create_session(ecosystem="rmn")
        advisor.send_message(session.session_id, "Show current allocation")
        resp = advisor.send_message(
            session.session_id, "Rebalance 20% from walmart to target"
        )
        assert resp.agent_source == "scenario_executor"
        assert "rebalance_portfolio" in resp.scenario_ids

    def test_turn3_rag_retrieval(self, advisor):
        session = advisor.create_session(ecosystem="rmn")
        advisor.send_message(session.session_id, "Show current allocation")
        advisor.send_message(session.session_id, "Rebalance 20% from walmart to target")
        resp = advisor.send_message(session.session_id, "What was the impact of the rebalance?")
        assert resp.message
        # Should find the indexed scenario result via RAG or intent
        assert resp.agent_source in ("rag_fallback", "scenario_executor", "state_lookup", "offline")

    def test_turn4_grow_revenue(self, advisor):
        session = advisor.create_session(ecosystem="rmn")
        advisor.send_message(session.session_id, "Show current allocation")
        advisor.send_message(session.session_id, "Rebalance from walmart to target")
        advisor.send_message(session.session_id, "What was the result?")
        resp = advisor.send_message(session.session_id, "Now grow revenue for the brand")
        assert resp.agent_source == "scenario_executor"
        assert "grow_revenue_brand" in resp.scenario_ids

    def test_turn5_rag_accumulation(self, advisor):
        session = advisor.create_session(ecosystem="rmn")
        advisor.send_message(session.session_id, "Show current allocation")
        advisor.send_message(session.session_id, "Rebalance portfolio")
        advisor.send_message(session.session_id, "grow revenue for brand")
        # RAG should now have catalog + ≥2 execution results
        results = advisor.rag.search("scenario execution", top_k=10)
        assert len(results) >= 2

    def test_session_history_length(self, advisor):
        session = advisor.create_session(ecosystem="rmn")
        advisor.send_message(session.session_id, "Show current state")
        advisor.send_message(session.session_id, "Rebalance portfolio")
        advisor.send_message(session.session_id, "grow revenue")
        advisor.send_message(session.session_id, "What is my allocation?")
        advisor.send_message(session.session_id, "maximize roas")
        history = advisor.get_history(session.session_id)
        # system + 5*(user+assistant) = 11
        assert len(history) >= 11


# ===========================================================================
# TestDPMultiTurn (4 tests)
# ===========================================================================

class TestDPMultiTurn:
    """3-turn D&P conversation: forecast → stockout → compare."""

    def test_turn1_dp_forecast_intent(self, advisor):
        session = advisor.create_session(ecosystem="demand_procurement")
        resp = advisor.send_message(session.session_id, "Show demand forecast for SKU-001")
        assert resp.message
        # Offline mode → should detect D&P ecosystem at minimum
        eco = advisor._detect_ecosystem("demand forecast SKU")
        assert eco == Ecosystem.DEMAND_PROCUREMENT

    def test_turn2_stockout(self, advisor):
        session = advisor.create_session(ecosystem="demand_procurement")
        advisor.send_message(session.session_id, "demand forecast for SKU-001")
        resp = advisor.send_message(session.session_id, "assess stockout risk for this SKU")
        assert resp.message

    def test_turn3_compare(self, advisor):
        session = advisor.create_session(ecosystem="demand_procurement")
        advisor.send_message(session.session_id, "demand forecast")
        advisor.send_message(session.session_id, "stockout risk")
        resp = advisor.send_message(session.session_id, "compare these scenarios")
        assert resp.message

    def test_dp_session_history(self, advisor):
        session = advisor.create_session(ecosystem="demand_procurement")
        advisor.send_message(session.session_id, "forecast")
        advisor.send_message(session.session_id, "stockout")
        advisor.send_message(session.session_id, "compare")
        history = advisor.get_history(session.session_id)
        # system + 3*(user+assistant) = 7
        assert len(history) >= 7


# ===========================================================================
# TestCrossEcosystemAutoDetect (3 tests)
# ===========================================================================

class TestCrossEcosystemAutoDetect:

    def test_rmn_detected(self, advisor):
        eco = advisor._detect_ecosystem("Maximize ROAS for media channels")
        assert eco == Ecosystem.RMN

    def test_dp_detected(self, advisor):
        eco = advisor._detect_ecosystem("inventory levels and demand forecast for SKU reorder")
        assert eco == Ecosystem.DEMAND_PROCUREMENT

    def test_ambiguous_offline(self, advisor):
        session = advisor.create_session()
        resp = advisor.send_message(session.session_id, "hello there")
        assert resp.agent_source in ("offline", "rag_fallback")


# ===========================================================================
# TestRAGAccumulation (4 tests)
# ===========================================================================

class TestRAGAccumulation:

    def test_manual_index_and_search(self, advisor):
        advisor.rag.index_document(
            doc_type="knowledge",
            content="ROAS optimization best practices for retail media",
            metadata={"topic": "roas"},
        )
        results = advisor.rag.search("ROAS optimization", top_k=3)
        assert len(results) >= 1
        assert any("ROAS" in r.content for r in results)

    def test_context_builder(self, advisor):
        advisor.rag.index_document(
            doc_type="knowledge",
            content="Important context about incrementality testing",
            metadata={"topic": "incrementality"},
        )
        context, results = advisor._build_rag_context("incrementality testing")
        assert "Retrieved context" in context
        assert len(results) >= 1

    def test_scenario_catalog_indexed(self, advisor):
        results = advisor.rag.search("rebalance portfolio", top_k=3, doc_type="scenario_catalog")
        assert len(results) >= 1
        assert any("rebalance" in r.content.lower() for r in results)

    def test_multiple_results_accumulate(self, advisor):
        for i in range(3):
            advisor.rag.index_document(
                doc_type="knowledge",
                content=f"Knowledge document number {i} about portfolio management",
                metadata={"index": i},
            )
        results = advisor.rag.search("portfolio management", top_k=10)
        assert len(results) >= 3


# ===========================================================================
# TestScenarioAgentDirectionPatterns (7 tests)
# ===========================================================================

class TestScenarioAgentDirectionPatterns:

    def _run_pattern(self, advisor, message, expected_scenario):
        session = advisor.create_session()
        resp = advisor.send_message(session.session_id, message)
        assert expected_scenario in resp.scenario_ids, (
            f"Expected {expected_scenario} in {resp.scenario_ids} for '{message}'"
        )
        return resp

    def test_pattern_rebalance(self, advisor):
        self._run_pattern(advisor, "Shift budget from walmart to kroger", "rebalance_portfolio")

    def test_pattern_grow_revenue(self, advisor):
        self._run_pattern(advisor, "Drive sales growth for brand X", "grow_revenue_brand")

    def test_pattern_maximize_roas(self, advisor):
        self._run_pattern(advisor, "Improve efficiency and maximize roas", "maximize_roas")

    def test_pattern_maintain(self, advisor):
        self._run_pattern(advisor, "Keep steady revenue levels", "maintain_revenue")

    def test_pattern_prevent_decline(self, advisor):
        self._run_pattern(advisor, "Protect against revenue decline", "prevent_decline")

    def test_pattern_experiment(self, advisor):
        self._run_pattern(advisor, "Run an experiment to learn about lift", "experiment_incrementality")

    def test_pattern_with_params(self, advisor):
        resp = self._run_pattern(
            advisor, "Rebalance 15% from walmart to target with roas floor 3.0",
            "rebalance_portfolio"
        )
        assert resp.data is not None
        assert resp.data.get("success") is True


# ===========================================================================
# TestEdgeCases (6 tests)
# ===========================================================================

class TestEdgeCases:

    def test_empty_message(self, advisor):
        session = advisor.create_session()
        resp = advisor.send_message(session.session_id, "")
        assert resp.message

    def test_long_message(self, advisor):
        session = advisor.create_session()
        long_msg = "optimize " * 200  # ~200 words
        resp = advisor.send_message(session.session_id, long_msg)
        assert resp.message

    def test_special_chars(self, advisor):
        session = advisor.create_session()
        resp = advisor.send_message(session.session_id, "What's the ROAS for $2M budget? (test) [brackets] {curly}")
        assert resp.message

    def test_invalid_session_id(self, advisor):
        resp = advisor.send_message("invalid-uuid", "hello")
        assert resp.confidence == 0.0

    def test_session_isolation_messages(self, advisor):
        s1 = advisor.create_session()
        s2 = advisor.create_session()
        advisor.send_message(s1.session_id, "grow revenue for brand")
        advisor.send_message(s2.session_id, "show current allocation")
        h1 = advisor.get_history(s1.session_id)
        h2 = advisor.get_history(s2.session_id)
        assert any("grow" in m.get("content", "").lower() for m in h1)
        assert not any("grow" in m.get("content", "").lower() for m in h2 if m.get("role") == "user")

    def test_rapid_fire_messages(self, advisor):
        session = advisor.create_session()
        intents = [
            "rebalance portfolio", "grow revenue for brand", "maximize roas",
            "maintain revenue levels", "prevent decline now",
            "rebalance portfolio again", "grow revenue more", "maximize roas again",
            "run an experiment to learn", "maximize profit",
        ]
        for msg in intents:
            advisor.send_message(session.session_id, msg)
        # Multiple distinct scenarios indexed as scenario_result docs
        results = advisor.rag.search("scenario execution", top_k=20, doc_type="scenario_result")
        assert len(results) >= 5


# ===========================================================================
# TestResponseRoundTrip (2 tests)
# ===========================================================================

class TestResponseRoundTrip:

    def test_scenario_response_serialization(self, advisor):
        session = advisor.create_session()
        resp = advisor.send_message(session.session_id, "Rebalance portfolio")
        d = resp.to_dict()
        serialized = json.dumps(d)
        deserialized = json.loads(serialized)
        assert deserialized["message"] == resp.message
        assert deserialized["agent_source"] == resp.agent_source
        assert deserialized["scenario_ids"] == resp.scenario_ids

    def test_state_response_serialization(self, advisor):
        session = advisor.create_session()
        resp = advisor.send_message(session.session_id, "show current allocation")
        d = resp.to_dict()
        serialized = json.dumps(d)
        deserialized = json.loads(serialized)
        assert deserialized["confidence"] == 0.8
        assert deserialized["agent_source"] == "state_lookup"


# ===========================================================================
# TestConversationLevelRAG (2 tests)
# ===========================================================================

class TestConversationLevelRAG:

    def test_knowledge_doc_indexed_and_retrievable(self, advisor):
        advisor.rag.index_document(
            doc_type="knowledge",
            content="Brand performance data: Walmart ROAS 4.2, Target ROAS 3.8",
            metadata={"source": "brand_report"},
        )
        results = advisor.rag.search("Walmart ROAS performance", top_k=3)
        assert len(results) >= 1
        assert any("Walmart" in r.content for r in results)

    def test_scenario_results_searchable(self, advisor):
        session = advisor.create_session()
        advisor.send_message(session.session_id, "grow revenue for brand")
        advisor.send_message(session.session_id, "rebalance portfolio")
        results = advisor.rag.search("scenario execution", top_k=10, doc_type="scenario_result")
        assert len(results) >= 1

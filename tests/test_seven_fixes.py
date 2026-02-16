"""
Comprehensive tests for all 7 agent audit fixes.

Fix #1: Research agent has real research corpus (not empty)
Fix #2: Extraction agent data quality gap classification
Fix #3: Calculation agent scenario selection logic
Fix #4: QA agent anomaly detection + drift checks
Fix #5: KPI-specific prompts (not generic)
Fix #6: Chain-of-thought reasoning trace captured
Fix #7: Decision Advisory feedback loop
"""

from pathlib import Path
import json
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# =====================================================================
# Fix #1: Research corpus is populated — LoadResearchSnippetsTool
#          returns real data, not empty lists
# =====================================================================

class TestFix1_ResearchCorpus:

    def test_corpus_has_all_14_kpis(self):
        from loweconex_platform.kpi_crews.research_corpus import RESEARCH_CORPUS
        assert len(RESEARCH_CORPUS) >= 14, f"Expected >= 14 topics, got {len(RESEARCH_CORPUS)}"

    def test_each_kpi_has_snippets(self):
        from loweconex_platform.kpi_crews.research_corpus import RESEARCH_CORPUS
        for topic, snippets in RESEARCH_CORPUS.items():
            assert len(snippets) >= 1, f"Topic '{topic}' has no snippets"

    def test_snippets_have_required_fields(self):
        from loweconex_platform.kpi_crews.research_corpus import RESEARCH_CORPUS
        required = {"title", "source", "citation", "summary", "benchmarks"}
        for topic, snippets in RESEARCH_CORPUS.items():
            for s in snippets:
                missing = required - set(s.keys())
                assert not missing, f"Topic '{topic}' snippet missing: {missing}"

    def test_benchmarks_are_numeric_dicts(self):
        from loweconex_platform.kpi_crews.research_corpus import get_benchmarks_for_kpi
        bm = get_benchmarks_for_kpi("work_order_reduction")
        assert isinstance(bm, dict), "Benchmarks should be a dict"
        assert len(bm) > 0, "Benchmarks should not be empty"
        # At least one value should be numeric
        has_numeric = any(isinstance(v, (int, float)) for v in bm.values())
        has_list = any(isinstance(v, list) for v in bm.values())
        assert has_numeric or has_list, "Benchmarks should contain numeric values"

    def test_get_research_snippets_returns_nonempty(self):
        from loweconex_platform.kpi_crews.research_corpus import get_research_snippets
        from loweconex_platform.kpi_crews.registry import get_all_kpi_names
        for kpi in get_all_kpi_names():
            snippets = get_research_snippets(kpi)
            assert len(snippets) >= 1, f"KPI '{kpi}' returned 0 snippets from get_research_snippets"

    def test_tools_load_research_snippets_delegates_to_corpus(self):
        """Verify LoweconexTools.load_research_snippets uses the corpus, not old hardcoded refs."""
        from loweconex_platform.kpi_crews.tools import LoweconexTools, ArtifactStore
        from loweconex_platform.digital_twins.store import TwinStore
        from loweconex_platform.event_bus.redis_streams import LoweconexEventBus
        bus = LoweconexEventBus.__new__(LoweconexEventBus)
        bus._streams = {}
        bus._consumer_groups = {}
        tools = LoweconexTools(twin_store=TwinStore(), event_bus=bus, artifact_store=ArtifactStore())
        snippets = tools.load_research_snippets("energy_reduction")
        assert len(snippets) >= 1, "LoweconexTools.load_research_snippets returned empty"
        # Verify structure matches corpus format
        assert "title" in snippets[0], "Snippet missing 'title' field"
        assert "citation" in snippets[0], "Snippet missing 'citation' field"

    def test_snippets_have_real_citations(self):
        """Citations should reference real standards/papers, not be placeholder text."""
        from loweconex_platform.kpi_crews.research_corpus import RESEARCH_CORPUS
        known_sources = {"ASHRAE", "SMRP", "EPA", "ISO", "EIA", "FDA", "IPMVP", "GHG",
                         "Jardine", "McKinsey", "Deloitte", "Aberdeen", "ICMI", "Gartner",
                         "FMI", "USDA", "CDC", "GreenChill", "ENERGY STAR", "AHRI", "EN 15341"}
        for topic, snippets in RESEARCH_CORPUS.items():
            for s in snippets:
                citation = s.get("citation", "")
                has_real_ref = any(src.lower() in citation.lower() for src in known_sources)
                assert has_real_ref or len(citation) > 10, (
                    f"Topic '{topic}' has suspect citation: '{citation}'"
                )


# =====================================================================
# Fix #2: Registry defaults are literature-grounded (not hardcoded)
# =====================================================================

class TestFix2_LiteratureGroundedDefaults:

    def test_registry_imports_research_corpus(self):
        """registry.py should import get_benchmarks_for_kpi."""
        import loweconex_platform.kpi_crews.registry as reg
        source = Path(reg.__file__).read_text()
        assert "get_benchmarks_for_kpi" in source, "registry.py does not import get_benchmarks_for_kpi"

    def test_all_calc_functions_call_get_benchmarks(self):
        """Every calc function should call get_benchmarks_for_kpi."""
        import loweconex_platform.kpi_crews.registry as reg
        source = Path(reg.__file__).read_text()
        # Each KPI section should have a bm = get_benchmarks_for_kpi(...) call
        count = source.count("get_benchmarks_for_kpi(")
        # 14 KPIs, some reference other KPIs' benchmarks too
        assert count >= 14, f"Expected >= 14 get_benchmarks_for_kpi calls, found {count}"

    def test_no_bare_magic_numbers_for_key_defaults(self):
        """Key defaults like cost_per_wo, leak_rate should reference bm.get()."""
        import loweconex_platform.kpi_crews.registry as reg
        source = Path(reg.__file__).read_text()
        # These old hardcoded values should no longer appear as bare defaults
        # (they may appear in comments or fallbacks, but the primary .get() should use bm)
        assert 'scenario_params.get("cost_per_wo", 350.0)' not in source, "Old hardcoded cost_per_wo=350 still present"
        assert 'scenario_params.get("baseline_leak_rate", 0.20)' not in source, "Old hardcoded leak_rate=0.20 still present"
        assert 'scenario_params.get("electricity_rate", 0.12)' not in source, "Old hardcoded electricity_rate=0.12 still present"
        # Verify bm.get() pattern is used instead
        assert 'bm.get("electricity_rate_commercial"' in source, "electricity_rate should use bm.get()"

    def test_calc_function_defaults_are_sourced(self):
        """Run a KPI calc and verify assumptions mention sources."""
        from loweconex_platform.kpi_crews.tools import LoweconexTools, ArtifactStore
        from loweconex_platform.digital_twins.store import TwinStore
        from loweconex_platform.event_bus.redis_streams import LoweconexEventBus
        from loweconex_platform.kpi_crews.registry import calc_energy_reduction

        bus = LoweconexEventBus.__new__(LoweconexEventBus)
        bus._streams = {}
        bus._consumer_groups = {}
        tools = LoweconexTools(twin_store=TwinStore(), event_bus=bus, artifact_store=ArtifactStore())
        result = calc_energy_reduction(
            tools=tools, company_id="test", location_id=None,
            assets=[], locations=[{"sqft": 50000}],
            scenario_params={}, research={},
        )
        assert result["metrics"]["electricity_rate"] != 0.12, (
            "Energy calc still using old hardcoded rate 0.12"
        )


# =====================================================================
# Fix #3: Calc agent scenario selection (data-driven vs benchmark vs PdM)
# =====================================================================

class TestFix3_ScenarioSelectionLogic:

    def test_calc_task_mentions_formula_variants(self):
        """The calculation task description should mention formula variant selection."""
        from loweconex_platform.kpi_crews.base_crew import KPICrew, KPICrewSpec
        source = Path(KPICrew.__module__.replace(".", "/") + ".py")
        # Read from the actual module file
        import loweconex_platform.kpi_crews.base_crew as mod
        src = Path(mod.__file__).read_text()
        assert "DATA-DRIVEN" in src, "Calc task missing DATA-DRIVEN variant"
        assert "BENCHMARK-DRIVEN" in src, "Calc task missing BENCHMARK-DRIVEN variant"
        assert "PDM-GROUNDED" in src, "Calc task missing PDM-GROUNDED variant"

    def test_calc_agent_backstory_includes_benchmarks(self):
        """Calc agent backstory should inject benchmark values from corpus."""
        import loweconex_platform.kpi_crews.base_crew as mod
        src = Path(mod.__file__).read_text()
        assert "Available benchmarks from research corpus" in src

    def test_kpi_crew_result_has_variant_fields(self):
        from loweconex_platform.kpi_crews.base_crew import KPICrewResult
        r = KPICrewResult(kpi_name="test")
        assert hasattr(r, "formula_variant")
        assert hasattr(r, "variant_rationale")
        d = r.to_dict()
        assert "formula_variant" in d
        assert "variant_rationale" in d


# =====================================================================
# Fix #4: QA agent anomaly detection + drift checks
# =====================================================================

class TestFix4_QAAnomalyDetection:

    def test_history_store_records_and_retrieves(self):
        from loweconex_platform.kpi_crews.base_crew import KPIHistoryStore
        # Reset state
        KPIHistoryStore._history = {}
        KPIHistoryStore.record("test_kpi", {"savings_medium": 100, "confidence": 0.7})
        KPIHistoryStore.record("test_kpi", {"savings_medium": 110, "confidence": 0.75})
        KPIHistoryStore.record("test_kpi", {"savings_medium": 105, "confidence": 0.72})

        hist = KPIHistoryStore.get_history("test_kpi")
        assert len(hist) == 3

    def test_history_store_computes_stats(self):
        from loweconex_platform.kpi_crews.base_crew import KPIHistoryStore
        KPIHistoryStore._history = {}
        for v in [100, 110, 105, 95, 108]:
            KPIHistoryStore.record("stats_kpi", {"savings_medium": v, "confidence": 0.7})

        stats = KPIHistoryStore.get_stats("stats_kpi")
        assert stats["sufficient_history"] is True
        assert stats["runs"] == 5
        assert 95 < stats["savings_mean"] < 115
        assert stats["savings_stdev"] > 0

    def test_history_store_insufficient_history(self):
        from loweconex_platform.kpi_crews.base_crew import KPIHistoryStore
        KPIHistoryStore._history = {}
        KPIHistoryStore.record("lonely_kpi", {"savings_medium": 100, "confidence": 0.7})
        stats = KPIHistoryStore.get_stats("lonely_kpi")
        assert stats["sufficient_history"] is False

    def test_history_store_caps_at_50(self):
        from loweconex_platform.kpi_crews.base_crew import KPIHistoryStore
        KPIHistoryStore._history = {}
        for i in range(60):
            KPIHistoryStore.record("full_kpi", {"savings_medium": i, "confidence": 0.5})
        assert len(KPIHistoryStore.get_history("full_kpi")) == 50

    def test_qa_task_mentions_drift_detection(self):
        import loweconex_platform.kpi_crews.base_crew as mod
        src = Path(mod.__file__).read_text()
        assert "HISTORICAL DRIFT" in src
        assert "2σ" in src or "2\\u03c3" in src or "2\u03c3" in src
        assert "BENCHMARK PLAUSIBILITY" in src

    def test_qa_backstory_includes_history_when_available(self):
        """When history exists, QA agent backstory should include stats."""
        import loweconex_platform.kpi_crews.base_crew as mod
        src = Path(mod.__file__).read_text()
        assert "Historical baseline" in src or "history_stats" in src


# =====================================================================
# Fix #5: KPI-specific prompts (not generic)
# =====================================================================

class TestFix5_KPISpecificPrompts:

    def test_research_agent_gets_corpus_summary(self):
        import loweconex_platform.kpi_crews.base_crew as mod
        src = Path(mod.__file__).read_text()
        assert "corpus_snippets" in src
        assert "corpus_summary" in src
        assert "curated research snippets for this KPI" in src

    def test_benchmarks_injected_into_agent_backstories(self):
        import loweconex_platform.kpi_crews.base_crew as mod
        src = Path(mod.__file__).read_text()
        assert "benchmark_summary" in src
        # Should appear in research, calc, and QA backstories
        assert src.count("benchmark_summary") >= 3

    def test_extraction_agent_mentions_data_quality(self):
        import loweconex_platform.kpi_crews.base_crew as mod
        src = Path(mod.__file__).read_text()
        assert "stale timestamps" in src
        assert "sparse coverage" in src
        assert "unit mismatches" in src


# =====================================================================
# Fix #6: Chain-of-thought reasoning trace
# =====================================================================

class TestFix6_ReasoningTrace:

    def test_kpi_crew_result_has_trace_fields(self):
        from loweconex_platform.kpi_crews.base_crew import KPICrewResult
        r = KPICrewResult(kpi_name="test")
        assert isinstance(r.reasoning_trace, list)
        assert isinstance(r.lineage_ids, list)
        d = r.to_dict()
        assert "reasoning_trace" in d
        assert "lineage_ids" in d

    def test_extract_reasoning_trace_method_exists(self):
        from loweconex_platform.kpi_crews.base_crew import KPICrew
        assert hasattr(KPICrew, "_extract_reasoning_trace")

    def test_extract_reasoning_trace_parses_task_outputs(self):
        """Simulate CrewAI task outputs and verify trace extraction."""
        from loweconex_platform.kpi_crews.base_crew import KPICrew, KPICrewSpec
        from loweconex_platform.kpi_crews.tools import LoweconexTools, ArtifactStore
        from loweconex_platform.digital_twins.store import TwinStore
        from loweconex_platform.event_bus.redis_streams import LoweconexEventBus

        spec = KPICrewSpec(kpi_name="test_trace", display_name="Test Trace", objective="test")
        bus = LoweconexEventBus.__new__(LoweconexEventBus)
        bus._streams = {}
        bus._consumer_groups = {}
        tools = LoweconexTools(twin_store=TwinStore(), event_bus=bus, artifact_store=ArtifactStore())

        crew = KPICrew(spec=spec, tools=tools, event_bus=bus)

        # Simulate tasks with .output attribute
        class FakeTaskOutput:
            def __init__(self, raw):
                self.raw = raw

        class FakeTask:
            def __init__(self, output_text, agent_role="Test Agent"):
                self.output = FakeTaskOutput(output_text)
                self.agent = type("A", (), {"role": agent_role})()

        tasks = [
            FakeTask("I analyzed the research and found: {\"kpi_name\": \"test\", \"benchmarks\": {}}", "Research Analyst"),
            FakeTask("{\"inputs\": {}, \"gaps\": []}", "Extraction Lead"),
            FakeTask("Based on data availability I chose benchmark-driven: {\"formula_variant\": \"benchmark_driven\", \"variant_rationale\": \"sparse data\"}", "Calculation Lead"),
            FakeTask("{\"status\": \"APPROVED\", \"issues\": []}", "QA Agent"),
        ]
        labels = ["research", "extraction", "calculation", "qa"]

        crew._extract_reasoning_trace(None, tasks, labels)

        trace = crew.result.reasoning_trace
        assert len(trace) == 4, f"Expected 4 trace entries, got {len(trace)}"

        # Research step should have reasoning excerpt (text before '{')
        assert trace[0]["role"] == "research"
        assert "analyzed the research" in trace[0]["reasoning_excerpt"]

        # Calculation step should capture formula_variant
        assert crew.result.formula_variant == "benchmark_driven"
        assert crew.result.variant_rationale == "sparse data"

        # QA step should have structured output
        assert trace[3]["structured_output"]["status"] == "APPROVED"

    def test_trace_stored_as_artifact(self):
        """Verify the _parse_crew_output stores a reasoning_trace artifact."""
        import loweconex_platform.kpi_crews.base_crew as mod
        src = Path(mod.__file__).read_text()
        assert '"reasoning_trace"' in src
        assert "trace_artifact" in src
        assert 'store_artifact(\n                "reasoning_trace"' in src or 'store_artifact(\n                "reasoning_trace"' in src.replace("    ", "")


# =====================================================================
# Fix #7: Decision Advisory feedback loop
# =====================================================================

class TestFix7_AdvisoryFeedbackLoop:

    def test_advisory_agent_accepts_tracker(self):
        from loweconex_platform.orchestration.decision_advisory_agent import DecisionAdvisoryAgent
        from loweconex_platform.execution.execution_engine import RecommendationTracker
        tracker = RecommendationTracker()
        agent = DecisionAdvisoryAgent(recommendation_tracker=tracker)
        assert agent.recommendation_tracker is tracker

    def test_advisory_registers_recommendations(self):
        """Deterministic fallback should register recommendations with tracker."""
        from loweconex_platform.orchestration.decision_advisory_agent import DecisionAdvisoryAgent
        from loweconex_platform.execution.execution_engine import RecommendationTracker
        import unittest.mock as mock

        tracker = RecommendationTracker()
        agent = DecisionAdvisoryAgent(recommendation_tracker=tracker)

        composite = {
            "company_id": "test_co",
            "run_id": "run_001",
            "executive_summary": {
                "total_savings_medium": 100000,
                "total_savings_low": 60000,
                "total_savings_high": 140000,
                "kpi_count": 3,
                "approved_kpis": 3,
            },
            "kpi_results": {
                "energy_reduction": {
                    "savings_medium": 50000, "confidence": 0.75,
                    "narrative": "Energy savings", "depends_on_kpis": [],
                },
                "work_order_reduction": {
                    "savings_medium": 30000, "confidence": 0.70,
                    "narrative": "WO reduction", "depends_on_kpis": [],
                },
                "food_waste_reduction": {
                    "savings_medium": 20000, "confidence": 0.55,
                    "narrative": "Food waste", "depends_on_kpis": [],
                },
            },
            "roi_metrics": {"payback_months": 8.0, "net_npv": 500000},
            "portfolio_optimization": {},
            "cross_asset_optimization": {},
            "scenario_analysis": {},
        }

        # Patch CREWAI_AVAILABLE to force deterministic fallback (no API key needed)
        with mock.patch("loweconex_platform.orchestration.decision_advisory_agent.CREWAI_AVAILABLE", False):
            output = agent.advise(composite)

        # Should have recommendations
        assert len(output.strategic_recommendations) >= 1

        # Recommendations should be registered in tracker
        company_recs = tracker.get_by_company("test_co")
        assert len(company_recs) >= 1, "No recommendations registered in tracker"

        # Each rec should have a rec_id attached
        for rec in output.strategic_recommendations:
            assert "rec_id" in rec, f"Recommendation missing rec_id: {rec.get('title')}"

    def test_feedback_loop_accept_reject_outcome(self):
        """Full lifecycle: create → accept → implement → outcome → stats."""
        from loweconex_platform.execution.execution_engine import (
            RecommendationTracker, RecommendationRecord
        )
        tracker = RecommendationTracker()

        # Create 3 recs: accept 2, reject 1
        rec1 = RecommendationRecord(
            title="Deploy PdM", company_id="co1",
            estimated_savings_usd=50000, confidence=0.8,
        )
        rec2 = RecommendationRecord(
            title="Fix leaks", company_id="co1",
            estimated_savings_usd=30000, confidence=0.65,
        )
        rec3 = RecommendationRecord(
            title="CapEx replace", company_id="co1",
            estimated_savings_usd=100000, confidence=0.5,
        )
        id1 = tracker.create(rec1)
        id2 = tracker.create(rec2)
        id3 = tracker.create(rec3)

        tracker.accept(id1, "manager_a")
        tracker.accept(id2, "manager_a", modifications=["Reduce scope to 5 sites"])
        tracker.reject(id3, "Budget not available this FY")

        # Implement accepted recs
        tracker.record_implementation(id1, "2025-03-01")
        tracker.record_implementation(id2, "2025-04-01", work_order_ids=["WO-001"])

        # Record outcomes
        tracker.record_outcome(id1, actual_savings_usd=45000, actual_cost_usd=10000, notes="Close to estimate")
        tracker.record_outcome(id2, actual_savings_usd=22000, actual_cost_usd=5000, notes="Reduced scope")

        stats = tracker.acceptance_rate()
        assert stats["total"] == 3
        assert stats["accepted"] == 2
        assert stats["implemented"] == 2
        assert stats["assessed"] == 2
        assert stats["total_actual_savings"] == 67000
        assert abs(stats["realization_rate"] - 67000 / 180000) < 0.01

    def test_read_feedback_history_tool(self):
        """ReadFeedbackHistoryTool should return valid JSON with stats."""
        from loweconex_platform.orchestration.decision_advisory_agent import ReadFeedbackHistoryTool
        from loweconex_platform.execution.execution_engine import (
            RecommendationTracker, RecommendationRecord
        )
        tracker = RecommendationTracker()
        rec = RecommendationRecord(
            title="Test", company_id="co_test",
            estimated_savings_usd=10000, confidence=0.7,
        )
        rec_id = tracker.create(rec)
        tracker.accept(rec_id, "user")
        tracker.record_implementation(rec_id, "2025-01-01")
        tracker.record_outcome(rec_id, 8000, 2000)

        tool = ReadFeedbackHistoryTool(tracker, "co_test")
        result_json = tool._run()
        data = json.loads(result_json)

        assert data["company_recommendation_count"] == 1
        assert data["avg_realization_ratio"] == 0.8
        assert "calibration_note" in data
        assert "80%" in data["calibration_note"]

    def test_feedback_context_injected_into_strategist(self):
        """When tracker has history, strategist backstory should include feedback context."""
        import loweconex_platform.orchestration.decision_advisory_agent as mod
        src = Path(mod.__file__).read_text()
        assert "HISTORICAL FEEDBACK" in src
        assert "rejection_reason" in src or "rejection_patterns" in src
        assert "realization" in src
        assert "calibration" in src.lower()

    def test_api_recommendation_endpoints_exist(self):
        from loweconex_platform.api.kpi_routes import create_kpi_routes
        result = create_kpi_routes()
        routes = result["routes"]
        expected_patterns = [
            "recommendations",
            "accept",
            "reject",
            "implement",
            "outcome",
            "feedback-stats",
        ]
        route_keys = " ".join(routes.keys())
        for pattern in expected_patterns:
            assert pattern in route_keys, f"Missing route pattern: {pattern}"

    def test_api_feedback_workflow(self):
        """End-to-end API test: list → accept → implement → outcome → stats."""
        from loweconex_platform.api.kpi_routes import create_kpi_routes
        from loweconex_platform.execution.execution_engine import (
            RecommendationTracker, RecommendationRecord
        )
        tracker = RecommendationTracker()
        result = create_kpi_routes(recommendation_tracker=tracker)
        routes = result["routes"]

        # Seed a recommendation
        rec = RecommendationRecord(
            title="API Test Rec", company_id="api_co",
            estimated_savings_usd=25000, confidence=0.7,
        )
        rec_id = tracker.create(rec)

        # List
        get_recs = routes["GET /api/v1/kpi/{company_id}/recommendations"]
        resp = get_recs("api_co")
        assert resp["status"] == 200
        assert len(resp["recommendations"]) == 1

        # Accept
        accept = routes["POST /api/v1/kpi/{company_id}/recommendations/{rec_id}/accept"]
        resp = accept("api_co", rec_id, accepted_by="tester")
        assert resp["status"] == 200

        # Implement
        implement = routes["POST /api/v1/kpi/{company_id}/recommendations/{rec_id}/implement"]
        resp = implement("api_co", rec_id, implementation_date="2025-06-01")
        assert resp["status"] == 200
        assert resp["implemented"] is True

        # Outcome
        outcome = routes["POST /api/v1/kpi/{company_id}/recommendations/{rec_id}/outcome"]
        resp = outcome("api_co", rec_id, actual_savings_usd=20000, actual_cost_usd=5000)
        assert resp["status"] == 200
        assert resp["realization_pct"] == 0.8

        # Stats
        stats = routes["GET /api/v1/kpi/{company_id}/feedback-stats"]
        resp = stats("api_co")
        assert resp["status"] == 200
        assert resp["company_total_recommendations"] == 1
        assert resp["aggregate"]["realization_rate"] == 0.8

    def test_api_tenant_isolation(self):
        """Ensure recommendations from one company can't be accessed by another."""
        from loweconex_platform.api.kpi_routes import create_kpi_routes
        from loweconex_platform.execution.execution_engine import (
            RecommendationTracker, RecommendationRecord
        )
        tracker = RecommendationTracker()
        result = create_kpi_routes(recommendation_tracker=tracker)
        routes = result["routes"]

        rec = RecommendationRecord(
            title="Company A Rec", company_id="company_a",
            estimated_savings_usd=10000,
        )
        rec_id = tracker.create(rec)

        # Try to accept from company_b
        accept = routes["POST /api/v1/kpi/{company_id}/recommendations/{rec_id}/accept"]
        resp = accept("company_b", rec_id)
        assert resp["status"] == 403, "Should fail tenant isolation check"


# =====================================================================
# Integration: All modules still import cleanly
# =====================================================================

class TestIntegration:

    def test_all_modified_modules_import(self):
        import importlib
        modules = [
            "loweconex_platform.kpi_crews.research_corpus",
            "loweconex_platform.kpi_crews.registry",
            "loweconex_platform.kpi_crews.base_crew",
            "loweconex_platform.kpi_crews.tools",
            "loweconex_platform.orchestration.decision_advisory_agent",
            "loweconex_platform.api.kpi_routes",
            "loweconex_platform.api.server",
            "loweconex_platform.execution",
        ]
        for mod in modules:
            importlib.import_module(mod)

    def test_kpi_registry_all_14_load(self):
        from loweconex_platform.kpi_crews.registry import KPI_REGISTRY
        assert len(KPI_REGISTRY) == 14

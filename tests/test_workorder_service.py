"""
Unit tests for the AI Work Order system.

Covers:
- All 7 LLM service fallback methods (no OpenAI required)
- _parse_json edge cases
- _verify_fallback logic correctness (regression test for the higher-is-better fix)
- Pydantic model validation
- WorkOrderRepository CRUD operations (SQLite in-memory)
- A/B improvement factor application
"""

import sys
import os
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

# Ensure project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from predictive_maintenance.services.workorder.models import (
    ABBaselineMetrics,
    ABBaselineResponse,
    ABMetricProvenance,
    AB_IMPROVEMENT_FACTORS,
    ABTestRequest,
    ABTestResponse,
    AutoCreateWORequest,
    AutoCreateWOResponse,
    CostRecommendRequest,
    CostRecommendResponse,
    ForecastRequest,
    ForecastResponse,
    MatchRequest,
    MatchResponse,
    NLInterpretRequest,
    NLInterpretResponse,
    PrioritizeRequest,
    PrioritizeResponse,
    Provider,
    SensorSignal,
    VerificationRequest,
    VerificationResponse,
    WorkOrder,
    WorkOrderPriority,
    WorkOrderSource,
    WorkOrderStatus,
)


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def service():
    """WorkOrderLLMService with LLM disabled (tests fallback paths)."""
    from predictive_maintenance.services.workorder.llm_service import WorkOrderLLMService
    svc = WorkOrderLLMService.__new__(WorkOrderLLMService)
    svc._client = None  # Force fallback mode
    return svc


@pytest.fixture
def interpret_request():
    return NLInterpretRequest(text="RTU-001 is making a grinding noise and the compressor trips every 20 minutes")


@pytest.fixture
def auto_create_request():
    return AutoCreateWORequest(
        signals=[
            SensorSignal(
                asset_id="RTU-001",
                sensor_type="vibration",
                anomaly_type="bearing_degradation",
                change_score=0.85,
                persistence_hours=12.0,
                regime="cooling",
                fault_hypothesis="Compressor bearing wear",
                fault_probability=0.82,
                sensor_trust=0.95,
            ),
        ],
        site_id="test-site",
    )


@pytest.fixture
def prioritize_request():
    return PrioritizeRequest(
        work_order_id="WO-2025-TEST0001",
        title="Compressor grinding noise",
        description="RTU-001 compressor making grinding noise",
        asset_id="RTU-001",
        estate="North Campus",
        location="Building A, Roof",
        priority=WorkOrderPriority.HIGH,
        source=WorkOrderSource.AI_SENSOR,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


@pytest.fixture
def match_request():
    return MatchRequest(
        work_order_id="WO-2025-TEST0001",
        title="Compressor repair",
        description="RTU-001 compressor needs repair",
        asset_id="RTU-001",
        priority=WorkOrderPriority.HIGH,
        problem_type="Mechanical",
        location="Building A",
        providers=[
            Provider(
                id="P1", name="CoolFix HVAC", specialty="HVAC Repair",
                rating=4.5, ftfr=0.88, avg_cost=650, avg_response_hrs=3.5,
                proximity_miles=8, certifications=["EPA 608"], available=True,
            ),
            Provider(
                id="P2", name="QuickCool", specialty="Emergency Repair",
                rating=4.2, ftfr=0.76, avg_cost=900, avg_response_hrs=1.5,
                proximity_miles=12, certifications=["EPA 608", "NATE"], available=True,
            ),
        ],
    )


@pytest.fixture
def cost_request():
    return CostRecommendRequest(
        work_order_id="WO-2025-TEST0001",
        title="Compressor repair",
        description="RTU-001 compressor needs repair",
        asset_id="RTU-001",
        priority=WorkOrderPriority.HIGH,
        estimated_cost=1200.0,
    )


@pytest.fixture
def verify_request():
    return VerificationRequest(
        work_order_id="WO-2025-TEST0001",
        title="Compressor repair",
        asset_id="RTU-001",
        problem_type="Mechanical",
        pre_service_metrics={"anomaly_score": 0.72, "temp_deviation": 8.5, "vibration_level": 0.65, "efficiency": 0.78},
        post_service_metrics={"anomaly_score": 0.18, "temp_deviation": 1.2, "vibration_level": 0.22, "efficiency": 0.94},
    )


@pytest.fixture
def forecast_request():
    return ForecastRequest(
        site_id="test-site",
        horizon_days=14,
        historical_wo_counts=[{"date": "2025-01-15", "count": 3}, {"date": "2025-01-16", "count": 5}],
        asset_risk_scores={"RTU-001": 0.82, "AHU-003": 0.45},
    )


# ── 1. NL Interpretation Fallback ────────────────────────────────────

class TestInterpretFallback:
    def test_extracts_asset_id(self, service, interpret_request):
        result = service.interpret(interpret_request)
        assert isinstance(result, NLInterpretResponse)
        assert result.asset_id == "RTU-001"

    def test_detects_mechanical_problem(self, service, interpret_request):
        result = service.interpret(interpret_request)
        assert result.problem_type == "Mechanical"
        assert "abnormal_noise" in result.symptoms

    def test_no_asset_id_asks_clarification(self, service):
        req = NLInterpretRequest(text="There's a weird noise coming from somewhere")
        result = service.interpret(req)
        assert result.asset_id is None
        assert len(result.clarifications) > 0
        assert result.confidence < 0.7

    def test_emergency_keywords_raise_priority(self, service):
        req = NLInterpretRequest(text="EMERGENCY: RTU-003 is on fire, safety concern!")
        result = service.interpret(req)
        assert result.priority == WorkOrderPriority.CRITICAL

    def test_leak_keywords(self, service):
        req = NLInterpretRequest(text="RTU-005 has a refrigerant leak")
        result = service.interpret(req)
        assert result.problem_type == "Refrigerant/Leak"
        assert result.priority == WorkOrderPriority.HIGH

    def test_raw_llm_response_is_none_in_fallback(self, service, interpret_request):
        result = service.interpret(interpret_request)
        assert result.raw_llm_response is None


# ── 2. Auto-Create Fallback ──────────────────────────────────────────

class TestAutoCreateFallback:
    def test_should_create_when_thresholds_met(self, service, auto_create_request):
        result = service.auto_create(auto_create_request)
        assert isinstance(result, AutoCreateWOResponse)
        assert result.should_create is True
        assert result.asset_id == "RTU-001"

    def test_high_fault_prob_sets_critical(self, service, auto_create_request):
        result = service.auto_create(auto_create_request)
        assert result.priority == WorkOrderPriority.CRITICAL

    def test_no_signals_returns_no_create(self, service):
        req = AutoCreateWORequest(signals=[], site_id="test")
        result = service.auto_create(req)
        assert result.should_create is False
        assert result.confidence == 0.0

    def test_low_score_no_create(self, service):
        req = AutoCreateWORequest(
            signals=[SensorSignal(
                asset_id="AHU-003", sensor_type="temperature",
                anomaly_type="drift", change_score=0.3,
                persistence_hours=2.0, sensor_trust=0.9,
            )],
            site_id="test",
        )
        result = service.auto_create(req)
        assert result.should_create is False


# ── 3. Prioritize Fallback ───────────────────────────────────────────

class TestPrioritizeFallback:
    def test_returns_valid_response(self, service, prioritize_request):
        result = service.prioritize(prioritize_request)
        assert isinstance(result, PrioritizeResponse)
        assert result.work_order_id == "WO-2025-TEST0001"
        assert 0 <= result.assessment.priority_score <= 100

    def test_high_priority_gets_high_score(self, service, prioritize_request):
        result = service.prioritize(prioritize_request)
        assert result.assessment.priority_score >= 50


# ── 4. Provider Match Fallback ───────────────────────────────────────

class TestMatchFallback:
    def test_returns_all_providers(self, service, match_request):
        result = service.match_providers(match_request)
        assert isinstance(result, MatchResponse)
        assert len(result.matches) == 2

    def test_top_provider_is_recommended(self, service, match_request):
        result = service.match_providers(match_request)
        recommended = [m for m in result.matches if m.recommended]
        assert len(recommended) == 1

    def test_scores_are_bounded(self, service, match_request):
        result = service.match_providers(match_request)
        for m in result.matches:
            assert 0 <= m.match_score <= 100


# ── 5. Cost Recommendation Fallback ──────────────────────────────────

class TestCostFallback:
    def test_returns_valid_recommendation(self, service, cost_request):
        result = service.recommend_cost(cost_request)
        assert isinstance(result, CostRecommendResponse)
        assert result.recommendation.action in ("approve", "reject", "review")
        assert 0 <= result.recommendation.confidence <= 1.0

    def test_high_cost_triggers_review(self, service):
        req = CostRecommendRequest(
            work_order_id="WO-HIGH", title="Expensive repair",
            description="", asset_id="X", priority=WorkOrderPriority.LOW,
            estimated_cost=50000.0,
        )
        result = service.recommend_cost(req)
        assert result.recommendation.action == "review"


# ── 6. Verify Fallback (regression test for logic bug fix) ──────────

class TestVerifyFallback:
    def test_all_improved_passes(self, service, verify_request):
        result = service.verify(verify_request)
        assert isinstance(result, VerificationResponse)
        assert result.verification.passed is True
        assert result.verification.confidence > 0.5

    def test_efficiency_decrease_is_not_improved(self, service):
        """Regression: before the fix, efficiency drop was counted as improved."""
        req = VerificationRequest(
            work_order_id="WO-REG",
            title="Regression test",
            asset_id="RTU-001",
            problem_type="General",
            pre_service_metrics={"efficiency": 0.95, "anomaly_score": 0.80},
            post_service_metrics={"efficiency": 0.40, "anomaly_score": 0.10},
        )
        result = service.verify(req)
        # anomaly_score improved (lower is better), efficiency NOT improved (higher is better)
        # ratio = 1/2 = 0.5; post_metrics_improved requires ratio > 0.5 → False
        assert result.verification.post_metrics_improved is False
        assert result.verification.passed is False  # ratio 0.5 < 0.6 threshold
        assert result.verification.confidence <= 0.5

    def test_no_overlapping_metrics(self, service):
        req = VerificationRequest(
            work_order_id="WO-NONE",
            title="No overlap",
            asset_id="RTU-001",
            problem_type="General",
            pre_service_metrics={"temp": 25.0},
            post_service_metrics={"humidity": 60.0},
        )
        result = service.verify(req)
        assert "No overlapping" in result.verification.evidence_summary

    def test_all_metrics_worsened_fails(self, service):
        req = VerificationRequest(
            work_order_id="WO-FAIL",
            title="Failed repair",
            asset_id="RTU-001",
            problem_type="Mechanical",
            pre_service_metrics={"anomaly_score": 0.3, "vibration_level": 0.2, "efficiency": 0.9},
            post_service_metrics={"anomaly_score": 0.8, "vibration_level": 0.7, "efficiency": 0.5},
        )
        result = service.verify(req)
        assert result.verification.passed is False
        assert result.verification.reopen_reason is not None


# ── 7. Forecast Fallback ─────────────────────────────────────────────

class TestForecastFallback:
    def test_returns_correct_horizon(self, service, forecast_request):
        result = service.forecast(forecast_request)
        assert isinstance(result, ForecastResponse)
        assert len(result.points) == 14  # horizon_days

    def test_points_have_confidence_bands(self, service, forecast_request):
        result = service.forecast(forecast_request)
        for pt in result.points:
            assert pt.confidence_low <= pt.predicted_count <= pt.confidence_high

    def test_narrative_is_generated(self, service, forecast_request):
        result = service.forecast(forecast_request)
        assert len(result.narrative) > 0


# ── _parse_json Edge Cases ───────────────────────────────────────────

class TestParseJson:
    def test_plain_json(self, service):
        assert service._parse_json('{"key": "value"}') == {"key": "value"}

    def test_markdown_fences(self, service):
        text = '```json\n{"key": "value"}\n```'
        assert service._parse_json(text) == {"key": "value"}

    def test_json_in_prose(self, service):
        text = 'Here is the result:\n{"key": "value"}\nDone!'
        assert service._parse_json(text) == {"key": "value"}

    def test_empty_returns_none(self, service):
        assert service._parse_json(None) is None
        assert service._parse_json("") is None

    def test_garbage_returns_none(self, service):
        assert service._parse_json("not json at all!!!") is None


# ── Pydantic Model Validation ────────────────────────────────────────

class TestModels:
    def test_work_order_id_generation(self):
        wo = WorkOrder(title="Test", description="Test WO", asset_id="RTU-001")
        assert wo.id.startswith("WO-")
        assert wo.status == WorkOrderStatus.OPEN

    def test_priority_enum_values(self):
        assert WorkOrderPriority.EMERGENCY.value == "emergency"
        assert WorkOrderPriority.CRITICAL.value == "critical"
        assert WorkOrderPriority.HIGH.value == "high"
        assert WorkOrderPriority.MEDIUM.value == "medium"
        assert WorkOrderPriority.LOW.value == "low"
        assert WorkOrderPriority.PLANNED.value == "planned"

    def test_sensor_signal_bounds(self):
        with pytest.raises(Exception):
            SensorSignal(
                asset_id="X", sensor_type="t", anomaly_type="a",
                change_score=1.5,  # > 1.0
                persistence_hours=1.0,
            )

    def test_ab_improvement_factors_cover_all_metrics(self):
        metric_fields = set(ABBaselineMetrics.model_fields.keys())
        factor_keys = set(AB_IMPROVEMENT_FACTORS.keys())
        assert metric_fields == factor_keys, f"Missing factors: {metric_fields - factor_keys}"


# ── A/B Improvement Factor Application ──────────────────────────────

class TestABFactors:
    def test_target_mode(self):
        baseline = {"reactive_pct": 62}
        factor = AB_IMPROVEMENT_FACTORS["reactive_pct"]
        assert factor["mode"] == "target"
        predicted = factor["value"]
        assert predicted == 22

    def test_multiply_mode(self):
        baseline_cost = 780
        factor = AB_IMPROVEMENT_FACTORS["avg_cost"]
        assert factor["mode"] == "multiply"
        predicted = baseline_cost * factor["value"]
        assert predicted < baseline_cost

    def test_all_factors_have_valid_mode(self):
        for key, factor in AB_IMPROVEMENT_FACTORS.items():
            assert factor["mode"] in ("target", "multiply"), f"Invalid mode for {key}"
            assert "value" in factor, f"Missing value for {key}"


# ── WorkOrderRepository (SQLite in-memory) ───────────────────────────

class TestWorkOrderRepository:
    @pytest.fixture(autouse=True)
    def setup_db(self):
        """Create an in-memory SQLite database for each test."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from predictive_maintenance.persistence.database import Base
        from predictive_maintenance.persistence.models import WorkOrderModel  # noqa

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        self.session = SessionLocal()

        from predictive_maintenance.persistence.workorder_repository import WorkOrderRepository
        self.repo = WorkOrderRepository(self.session)
        yield
        self.session.close()

    def test_create_and_retrieve(self):
        wo = self.repo.create(
            asset_id="RTU-001", site_id="site-1",
            title="Test WO", description="Testing",
            priority="high", source="ai_nlp",
        )
        assert wo.wo_id.startswith("WO-")
        assert wo.status == "open"

        fetched = self.repo.get_by_wo_id(wo.wo_id)
        assert fetched is not None
        assert fetched.asset_id == "RTU-001"

    def test_create_from_interpret(self):
        interpret_result = {
            "title": "Temperature anomaly on RTU-003",
            "description": "High discharge temp detected",
            "asset_id": "RTU-003",
            "priority": "high",
        }
        wo = self.repo.create_from_interpret(interpret_result, site_id="site-1")
        assert "ai_nlp" in wo.description
        assert wo.asset_id == "RTU-003"

    def test_create_from_auto(self):
        auto_result = {
            "title": "PdM: bearing degradation on RTU-001",
            "description": "Vibration anomaly detected",
            "asset_id": "RTU-001",
            "priority": "critical",
        }
        wo = self.repo.create_from_auto(auto_result, site_id="site-1", source_alert_id="ALT-001")
        assert wo.source_alert_id == "ALT-001"
        assert wo.wo_type == "planned"

    def test_update_status(self):
        wo = self.repo.create(asset_id="X", site_id="s", title="T")
        assert self.repo.update_status(wo.wo_id, "in_progress")
        self.session.expire_all()
        assert self.repo.get_by_wo_id(wo.wo_id).status == "in_progress"

    def test_dispatch(self):
        wo = self.repo.create(asset_id="X", site_id="s", title="T")
        assert self.repo.dispatch(wo.wo_id, "CoolFix HVAC")
        self.session.expire_all()
        updated = self.repo.get_by_wo_id(wo.wo_id)
        assert updated.status == "in_progress"
        assert updated.provider == "CoolFix HVAC"
        assert updated.dispatched_at is not None

    def test_close_and_reopen(self):
        wo = self.repo.create(asset_id="X", site_id="s", title="T")
        self.repo.close(wo.wo_id, resolution="Fixed", actual_cost=500.0)
        self.session.expire_all()
        assert self.repo.get_by_wo_id(wo.wo_id).status == "completed"

        self.repo.reopen(wo.wo_id, reason="Issue recurred")
        self.session.expire_all()
        assert self.repo.get_by_wo_id(wo.wo_id).status == "open"

    def test_list_by_site(self):
        self.repo.create(asset_id="A", site_id="site-1", title="WO1")
        self.repo.create(asset_id="B", site_id="site-1", title="WO2")
        self.repo.create(asset_id="C", site_id="site-2", title="WO3")
        self.session.flush()

        results = self.repo.list_by_site("site-1")
        assert len(results) == 2

    def test_list_by_asset(self):
        self.repo.create(asset_id="RTU-001", site_id="s", title="WO1")
        self.repo.create(asset_id="RTU-001", site_id="s", title="WO2")
        self.repo.create(asset_id="AHU-003", site_id="s", title="WO3")
        self.session.flush()

        results = self.repo.list_by_asset("RTU-001")
        assert len(results) == 2

    def test_update_nonexistent_returns_false(self):
        assert self.repo.update_status("DOES-NOT-EXIST", "completed") is False

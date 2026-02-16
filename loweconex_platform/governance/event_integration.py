"""
Event-Aware Governance Integration — wires enterprise modules to the event bus.

Provides event-emitting wrappers around enterprise modules so that significant
governance events (data quality blocks, drift alerts, action lifecycle, exceptions)
are automatically published to the platform event bus.

Phase 2 integration layer — does NOT modify the standalone enterprise modules.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Graceful imports
try:
    from loweconex_platform.event_bus.events import EventType, EventEnvelope, create_envelope
    from loweconex_platform.event_bus.redis_streams import LoweconexEventBus
    EVENT_BUS_AVAILABLE = True
except ImportError:
    EVENT_BUS_AVAILABLE = False

try:
    from loweconex_platform.data_quality.quality_engine import (
        DataQualityEngine, GateDecision, QualityReport,
    )
    DQ_AVAILABLE = True
except ImportError:
    DQ_AVAILABLE = False

try:
    from loweconex_platform.mlops.model_registry import (
        ModelRegistry, DriftMonitor, DriftAlert, DriftSeverity,
    )
    MLOPS_AVAILABLE = True
except ImportError:
    MLOPS_AVAILABLE = False

try:
    from loweconex_platform.execution.execution_engine import (
        ExecutionEngine, ControlAction, ActionStatus,
    )
    EXECUTION_AVAILABLE = True
except ImportError:
    EXECUTION_AVAILABLE = False

try:
    from loweconex_platform.operating_model.operating_model import (
        ExceptionManager, ExceptionRecord, ExceptionStatus,
    )
    OPERATING_MODEL_AVAILABLE = True
except ImportError:
    OPERATING_MODEL_AVAILABLE = False

try:
    from loweconex_platform.operating_model.operating_model import SLATracker
    SLA_AVAILABLE = True
except ImportError:
    SLA_AVAILABLE = False

try:
    from loweconex_platform.benchmarking.benchmark_engine import BenchmarkEngine, BenchmarkComparison
    BENCHMARK_AVAILABLE = True
except ImportError:
    BENCHMARK_AVAILABLE = False


# =========================================================================
# Event-emitting wrapper: DataQualityEngine
# =========================================================================

class EventAwareDataQualityEngine:
    """Wraps DataQualityEngine to emit events on BLOCK/WARN decisions."""

    def __init__(self, engine: Any, event_bus: Any, company_id: str = ""):
        self._engine = engine
        self._bus = event_bus
        self._company_id = company_id

    def __getattr__(self, name):
        return getattr(self._engine, name)

    def validate(self, suite_id: str, data: List[Dict[str, Any]],
                 metadata: Optional[Dict[str, Any]] = None) -> Any:
        report = self._engine.validate(suite_id, data, metadata)
        if self._bus and report:
            try:
                if report.gate_decision == GateDecision.BLOCK.value:
                    self._emit("DATA_QUALITY_REPORT", {
                        "gate_decision": "BLOCK",
                        "dataset": report.dataset_name,
                        "pass_rate": report.pass_rate,
                        "reason": report.gate_reason,
                        "failed_count": report.failed,
                    }, severity="critical")
                elif report.gate_decision == GateDecision.WARN.value:
                    self._emit("DATA_QUALITY_REPORT", {
                        "gate_decision": "WARN",
                        "dataset": report.dataset_name,
                        "pass_rate": report.pass_rate,
                        "reason": report.gate_reason,
                        "warning_count": report.warnings,
                    }, severity="warning")
            except Exception as e:
                logger.warning(f"DQ event emission failed: {e}")
        return report

    def _emit(self, event_type: str, payload: Dict[str, Any], severity: str = "info"):
        payload["severity"] = severity
        payload["ts"] = datetime.utcnow().isoformat()
        self._bus.publish(EventEnvelope(
            event_type=event_type,
            company_id=self._company_id,
            producer="data_quality_engine",
            payload=payload,
        ))


# =========================================================================
# Event-emitting wrapper: DriftMonitor
# =========================================================================

class EventAwareDriftMonitor:
    """Wraps DriftMonitor to emit events on drift alerts."""

    def __init__(self, monitor: Any, event_bus: Any, company_id: str = ""):
        self._monitor = monitor
        self._bus = event_bus
        self._company_id = company_id

    def __getattr__(self, name):
        return getattr(self._monitor, name)

    def check_performance_drift(self, model_name: str, current_metrics: Dict[str, float]) -> Any:
        alerts = self._monitor.check_performance_drift(model_name, current_metrics)
        self._emit_alerts(alerts)
        return alerts

    def check_data_drift(self, model_name: str, current_distributions: Dict[str, List[float]]) -> Any:
        alerts = self._monitor.check_data_drift(model_name, current_distributions)
        self._emit_alerts(alerts)
        return alerts

    def _emit_alerts(self, alerts: List[Any]):
        if not self._bus or not alerts:
            return
        for alert in alerts:
            try:
                self._bus.publish(EventEnvelope(
                    event_type="MODEL_DRIFT_DETECTED",
                    company_id=self._company_id,
                    producer="drift_monitor",
                    payload={
                        "model_name": alert.model_name,
                        "drift_type": alert.drift_type,
                        "severity": alert.severity,
                        "metric_name": alert.metric_name,
                        "current_value": alert.current_value,
                        "threshold": alert.threshold,
                        "description": alert.description,
                        "ts": datetime.utcnow().isoformat(),
                    },
                ))
            except Exception as e:
                logger.warning(f"Drift event emission failed: {e}")


# =========================================================================
# Event-emitting wrapper: ExecutionEngine
# =========================================================================

class EventAwareExecutionEngine:
    """Wraps ExecutionEngine to emit events on action lifecycle transitions."""

    def __init__(self, engine: Any, event_bus: Any, company_id: str = ""):
        self._engine = engine
        self._bus = event_bus
        self._company_id = company_id

    def __getattr__(self, name):
        return getattr(self._engine, name)

    def propose_action(self, action: Any) -> Dict[str, Any]:
        result = self._engine.propose_action(action)
        self._emit("CONTROL_ACTION_PROPOSED", {
            "action_id": action.action_id,
            "action_type": action.action_type,
            "status": result.get("status"),
            "target_asset": getattr(action, "asset_id", None),
        })
        return result

    def execute_action(self, action_id: str) -> Dict[str, Any]:
        result = self._engine.execute_action(action_id)
        self._emit("CONTROL_ACTION_EXECUTED", {
            "action_id": action_id,
            "status": result.get("status"),
        })
        return result

    def rollback_action(self, action_id: str, reason: str = "") -> Dict[str, Any]:
        result = self._engine.rollback_action(action_id, reason)
        self._emit("CONTROL_ACTION_ROLLED_BACK", {
            "action_id": action_id,
            "reason": reason,
        })
        return result

    def _emit(self, event_type: str, payload: Dict[str, Any]):
        if not self._bus:
            return
        try:
            payload["ts"] = datetime.utcnow().isoformat()
            self._bus.publish(EventEnvelope(
                event_type=event_type,
                company_id=self._company_id,
                producer="execution_engine",
                payload=payload,
            ))
        except Exception as e:
            logger.warning(f"Execution event emission failed: {e}")


# =========================================================================
# Event-emitting wrapper: ExceptionManager
# =========================================================================

class EventAwareExceptionManager:
    """Wraps ExceptionManager to emit events on create/resolve."""

    def __init__(self, manager: Any, event_bus: Any, company_id: str = ""):
        self._manager = manager
        self._bus = event_bus
        self._company_id = company_id

    def __getattr__(self, name):
        return getattr(self._manager, name)

    def create(self, exc: Any) -> str:
        exc_id = self._manager.create(exc)
        self._emit("EXCEPTION_CREATED", {
            "exception_id": exc_id,
            "exception_type": exc.exception_type,
            "priority": exc.priority,
            "title": exc.title,
            "kpi_name": exc.kpi_name,
            "blocked_kpis": exc.blocked_kpis,
        })
        return exc_id

    def resolve(self, exception_id: str, resolution: str,
                root_cause: str = "", preventive: str = ""):
        self._manager.resolve(exception_id, resolution, root_cause, preventive)
        self._emit("EXCEPTION_RESOLVED", {
            "exception_id": exception_id,
            "resolution": resolution,
            "root_cause": root_cause,
        })

    def escalate(self, exception_id: str, escalated_to: str, reason: str = ""):
        self._manager.escalate(exception_id, escalated_to, reason)
        self._emit("EXCEPTION_ESCALATED", {
            "exception_id": exception_id,
            "escalated_to": escalated_to,
            "reason": reason,
        })

    def _emit(self, event_type: str, payload: Dict[str, Any]):
        if not self._bus:
            return
        try:
            payload["ts"] = datetime.utcnow().isoformat()
            self._bus.publish(EventEnvelope(
                event_type=event_type,
                company_id=self._company_id,
                producer="exception_manager",
                payload=payload,
            ))
        except Exception as e:
            logger.warning(f"Exception event emission failed: {e}")


# =========================================================================
# SLA monitoring integration
# =========================================================================

class SLAEventHook:
    """
    Hook that records SLA measurements and emits events on breach.

    Wire into ingestion scheduler (data freshness) and KPI publication (latency).
    """

    def __init__(self, sla_tracker: Any, event_bus: Any, company_id: str = ""):
        self._tracker = sla_tracker
        self._bus = event_bus
        self._company_id = company_id

    def record_ingestion_freshness(self, connector_name: str, age_hours: float):
        """Record data freshness measurement."""
        if not self._tracker:
            return
        try:
            result = self._tracker.record_measurement(
                f"data_freshness_{connector_name}", age_hours
            )
            if result and result.get("breached"):
                self._emit("SLA_BREACHED", {
                    "sla_name": f"data_freshness_{connector_name}",
                    "measured_value": age_hours,
                    "threshold": result.get("threshold"),
                    "measurement_type": "data_freshness",
                })
            return result
        except Exception as e:
            logger.warning(f"SLA freshness recording failed: {e}")

    def record_kpi_latency(self, kpi_name: str, latency_ms: int):
        """Record KPI computation latency."""
        if not self._tracker:
            return
        try:
            result = self._tracker.record_measurement(
                f"kpi_latency_{kpi_name}", latency_ms
            )
            if result and result.get("breached"):
                self._emit("SLA_BREACHED", {
                    "sla_name": f"kpi_latency_{kpi_name}",
                    "measured_value": latency_ms,
                    "threshold": result.get("threshold"),
                    "measurement_type": "kpi_latency",
                })
            return result
        except Exception as e:
            logger.warning(f"SLA latency recording failed: {e}")

    def _emit(self, event_type: str, payload: Dict[str, Any]):
        if not self._bus:
            return
        try:
            payload["ts"] = datetime.utcnow().isoformat()
            self._bus.publish(EventEnvelope(
                event_type=event_type,
                company_id=self._company_id,
                producer="sla_monitor",
                payload=payload,
            ))
        except Exception as e:
            logger.warning(f"SLA event emission failed: {e}")


# =========================================================================
# Benchmark post-KPI hook
# =========================================================================

class BenchmarkPostKPIHook:
    """
    After a KPI result, auto-run BenchmarkEngine.compare() and attach
    z-score/percentile to the result.
    """

    def __init__(self, benchmark_engine: Any, event_bus: Optional[Any] = None,
                 company_id: str = ""):
        self._engine = benchmark_engine
        self._bus = event_bus
        self._company_id = company_id

    def enrich_kpi_result(
        self,
        kpi_name: str,
        entity_id: str,
        metric_name: str,
        metric_value: float,
        entity_attributes: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Compare a KPI metric against benchmarks and return comparison."""
        if not self._engine:
            return None
        try:
            comparison = self._engine.compare(
                entity_id=entity_id,
                entity_value=metric_value,
                kpi_name=kpi_name,
                metric_name=metric_name,
                entity_attributes=entity_attributes,
            )
            result = comparison.to_dict()

            if self._bus and comparison.comparison_valid:
                self._bus.publish(EventEnvelope(
                    event_type="BENCHMARK_COMPARISON",
                    company_id=self._company_id,
                    producer="benchmark_engine",
                    payload={
                        "kpi_name": kpi_name,
                        "entity_id": entity_id,
                        "z_score": comparison.z_score,
                        "percentile_rank": comparison.percentile_rank,
                        "cohort_id": comparison.cohort_id,
                        "ts": datetime.utcnow().isoformat(),
                    },
                ))

            return result
        except Exception as e:
            logger.warning(f"Benchmark comparison failed for {kpi_name}: {e}")
            return None


# =========================================================================
# Factory: create event-aware wrappers from raw modules + bus
# =========================================================================

def create_event_aware_modules(
    event_bus: Any,
    company_id: str = "",
    dq_engine: Any = None,
    model_registry: Any = None,
    execution_engine: Any = None,
    exception_manager: Any = None,
    sla_tracker: Any = None,
    benchmark_engine: Any = None,
) -> Dict[str, Any]:
    """
    Factory that wraps enterprise modules with event-emitting wrappers.

    Returns a dict of wrapped instances keyed by module name.
    """
    modules: Dict[str, Any] = {}

    if dq_engine and DQ_AVAILABLE:
        modules["dq_engine"] = EventAwareDataQualityEngine(
            dq_engine, event_bus, company_id
        )

    if model_registry and MLOPS_AVAILABLE:
        modules["drift_monitor"] = EventAwareDriftMonitor(
            model_registry.drift_monitor, event_bus, company_id
        )

    if execution_engine and EXECUTION_AVAILABLE:
        modules["execution_engine"] = EventAwareExecutionEngine(
            execution_engine, event_bus, company_id
        )

    if exception_manager and OPERATING_MODEL_AVAILABLE:
        modules["exception_manager"] = EventAwareExceptionManager(
            exception_manager, event_bus, company_id
        )

    if sla_tracker and SLA_AVAILABLE:
        modules["sla_hook"] = SLAEventHook(sla_tracker, event_bus, company_id)

    if benchmark_engine and BENCHMARK_AVAILABLE:
        modules["benchmark_hook"] = BenchmarkPostKPIHook(
            benchmark_engine, event_bus, company_id
        )

    return modules

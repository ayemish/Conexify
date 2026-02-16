"""
PDM Service Registry & Dependency Injection Container

Centralizes service creation and lifecycle management.  Instead of each
``HVACRPdMAdvancedSystem`` manually instantiating ~15 services, consumers
request them from the registry which handles:

- Lazy singleton construction (per asset where appropriate)
- Dependency wiring (e.g. drift detector → retraining trigger)
- Configuration injection from ``PDMSettings``
- Graceful degradation when optional deps are missing
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Type

from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class _ServiceEntry:
    factory: Callable[..., Any]
    singleton: bool = True
    instance: Any = None


class ServiceRegistry:
    """
    Central service container.

    Usage::

        registry = ServiceRegistry()
        regime_svc = registry.get("regime", asset_id="RTU_001")
    """

    def __init__(self):
        self._factories: Dict[str, _ServiceEntry] = {}
        self._asset_scoped: Dict[str, Dict[str, Any]] = {}
        self._register_defaults()

    # ── Registration ─────────────────────────────────────────────

    def register(
        self,
        name: str,
        factory: Callable[..., Any],
        singleton: bool = True,
    ):
        """Register a service factory."""
        self._factories[name] = _ServiceEntry(factory=factory, singleton=singleton)

    # ── Resolution ───────────────────────────────────────────────

    def get(self, name: str, *, asset_id: Optional[str] = None, **kwargs) -> Any:
        """
        Resolve a service by name.

        If *asset_id* is given the instance is cached per-asset (useful for
        stateful per-equipment services like change-detection or RUL).
        """
        entry = self._factories.get(name)
        if entry is None:
            raise KeyError(f"Service '{name}' not registered")

        # Asset-scoped caching
        if asset_id is not None:
            key = f"{name}:{asset_id}"
            if key in self._asset_scoped:
                return self._asset_scoped[key]
            instance = entry.factory(asset_id=asset_id, **kwargs)
            self._asset_scoped[key] = instance
            return instance

        # Global singleton
        if entry.singleton and entry.instance is not None:
            return entry.instance

        instance = entry.factory(**kwargs)
        if entry.singleton:
            entry.instance = instance
        return instance

    def has(self, name: str) -> bool:
        return name in self._factories

    def clear_asset(self, asset_id: str):
        """Evict all per-asset service instances."""
        to_remove = [k for k in self._asset_scoped if k.endswith(f":{asset_id}")]
        for k in to_remove:
            del self._asset_scoped[k]

    def clear_all(self):
        """Reset all instances (useful in tests)."""
        for entry in self._factories.values():
            entry.instance = None
        self._asset_scoped.clear()

    # ── Default Registrations ────────────────────────────────────

    def _register_defaults(self):
        """Register the standard PDM service set."""
        self._register_safe("regime", self._make_regime)
        self._register_safe("sensor_trust", self._make_sensor_trust)
        self._register_safe("behavior_model", self._make_behavior_model)
        self._register_safe("residual_model", self._make_residual_model)
        self._register_safe("change_detection", self._make_change_detection)
        self._register_safe("fault_hypothesis", self._make_fault_hypothesis)
        self._register_safe("decision_policy", self._make_decision_policy)
        self._register_safe("fingerprint", self._make_fingerprint)
        self._register_safe("rul", self._make_rul)
        self._register_safe("health_index", self._make_health_index)
        self._register_safe("drift_detection", self._make_drift_detection)
        self._register_safe("retraining_trigger", self._make_retraining_trigger)
        self._register_safe("alert_incident_bridge", self._make_alert_bridge)
        self._register_safe("event_bus", self._make_event_bus)
        self._register_safe("ensemble_calibration", self._make_ensemble_calibration)
        self._register_safe("adaptive_weights", self._make_adaptive_weights)
        self._register_safe("explainability", self._make_explainability)
        self._register_safe("fleet_correlation", self._make_fleet_correlation)
        self._register_safe("tft_predictor", self._make_tft_predictor)
        self._register_safe("physics_constraints", self._make_physics_constraints)

    def _register_safe(self, name: str, factory: Callable):
        try:
            self.register(name, factory)
        except Exception as exc:
            logger.debug("Skipping default service '%s': %s", name, exc)

    # ── Factories ────────────────────────────────────────────────

    @staticmethod
    def _make_regime(**kw):
        from ..services.regime_service import RegimeSegmentationService
        return RegimeSegmentationService()

    @staticmethod
    def _make_sensor_trust(**kw):
        from ..services.sensor_trust_service import SensorTrustService
        return SensorTrustService()

    @staticmethod
    def _make_behavior_model(**kw):
        from ..services.behavior_service import BehaviorModelService
        return BehaviorModelService()

    @staticmethod
    def _make_residual_model(**kw):
        from ..services.residual_service import ResidualErrorModelService
        return ResidualErrorModelService()

    @staticmethod
    def _make_change_detection(asset_id: str = "default", **kw):
        from ..services.change_detection_service import (
            ChangeDetectorConfig,
            SequentialChangeDetectionService,
        )
        cfg = ChangeDetectorConfig(
            cusum_threshold=settings.change_detection.cusum_threshold,
            cusum_slack=settings.change_detection.cusum_slack,
            glr_threshold=settings.change_detection.glr_threshold,
            min_persistence_minutes=settings.change_detection.min_persistence_minutes,
            min_steady_state_regimes=settings.change_detection.min_steady_state_regimes,
            stability_window=settings.change_detection.stability_window,
        )
        return SequentialChangeDetectionService(config=cfg)

    @staticmethod
    def _make_fault_hypothesis(**kw):
        from ..services.fault_hypothesis_service import FaultHypothesisService
        return FaultHypothesisService()

    @staticmethod
    def _make_decision_policy(**kw):
        from ..services.decision_policy_service import DecisionPolicyService
        return DecisionPolicyService()

    @staticmethod
    def _make_fingerprint(asset_id: str = "default", **kw):
        from ..services.fingerprint_service import EquipmentFingerprintService
        return EquipmentFingerprintService(asset_id=asset_id)

    @staticmethod
    def _make_rul(asset_id: str = "default", **kw):
        from ..services.rul_estimation_service import RULEstimationService
        return RULEstimationService(asset_id=asset_id)

    @staticmethod
    def _make_health_index(asset_id: str = "default", **kw):
        from ..services.health_index_service import HealthIndexService
        return HealthIndexService(asset_id=asset_id)

    @staticmethod
    def _make_drift_detection(asset_id: str = "default", **kw):
        from ..services.drift_detection_service import DriftDetectionService
        return DriftDetectionService(asset_id=asset_id)

    @staticmethod
    def _make_retraining_trigger(**kw):
        from ..services.retraining_trigger_service import RetrainingTriggerService
        return RetrainingTriggerService()

    @staticmethod
    def _make_alert_bridge(**kw):
        from ..services.alert_incident_bridge import AlertIncidentBridge
        return AlertIncidentBridge()

    @staticmethod
    def _make_event_bus(**kw):
        from ..integration.event_bus import RedisEventBus, InMemoryEventBus
        try:
            bus = RedisEventBus(redis_url=settings.redis.url)
            return bus
        except Exception:
            logger.warning("Redis unavailable, falling back to in-memory event bus")
            return InMemoryEventBus()

    @staticmethod
    def _make_ensemble_calibration(**kw):
        from ..services.ensemble_calibration_service import EnsembleCalibrationService
        return EnsembleCalibrationService(
            model_ids=["weibull", "degradation", "trend", "ensemble"],
            coverage_level=0.90,
        )

    @staticmethod
    def _make_adaptive_weights(**kw):
        from ..services.adaptive_agent_weights import AdaptiveAgentWeights
        return AdaptiveAgentWeights(
            agent_roles=[
                "regime_detector",
                "sensor_trust",
                "behavior_modeler",
                "change_detector",
                "fault_hypothesis",
                "decision_policy",
            ],
        )

    @staticmethod
    def _make_explainability(**kw):
        from ..services.explainability_service import ExplainabilityService
        return ExplainabilityService(
            feature_baselines={
                "suction_pressure": 70,
                "discharge_pressure": 250,
                "superheat": 10,
                "subcooling": 12,
                "compressor_current": 15,
            },
        )

    @staticmethod
    def _make_fleet_correlation(**kw):
        from ..services.fleet_correlation_service import FleetCorrelationService
        return FleetCorrelationService()

    @staticmethod
    def _make_tft_predictor(**kw):
        from ..models.temporal_fusion_transformer import TFTRULPredictor
        return TFTRULPredictor()

    @staticmethod
    def _make_physics_constraints(**kw):
        from ..models.physics_informed_constraints import PhysicsInformedLoss
        return PhysicsInformedLoss()


# ── Module-level singleton ───────────────────────────────────────

_registry: Optional[ServiceRegistry] = None


def get_registry() -> ServiceRegistry:
    """Return the global service registry (lazy-init)."""
    global _registry
    if _registry is None:
        _registry = ServiceRegistry()
    return _registry


def reset_registry():
    """Reset the global registry (for tests)."""
    global _registry
    if _registry is not None:
        _registry.clear_all()
    _registry = None

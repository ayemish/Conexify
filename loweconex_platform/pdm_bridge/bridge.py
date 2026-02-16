"""
PdM Integration Bridge — feeds predictive maintenance model outputs into
the Loweconex digital twin platform.

This module provides:

1. **PdMAssetSnapshot** — normalized container for PdM outputs per asset
2. **PdMBridge** — connector that:
   a. Reads PdM system state (HVACRPdMAdvancedSystem instances or stored snapshots)
   b. Maps PdM outputs → AssetTwin HealthState, AssetEconomics, anomaly flags
   c. Publishes PdM events onto the Loweconex event bus
   d. Provides aggregated PdM data for KPI crew consumption

Integration points:
- AssetTwin.health (HealthState) ← health_score, failure_risk, anomaly_flags
- AssetTwin.economics (AssetEconomics) ← remaining_useful_life_months
- KPI registry functions ← PdM-enriched scenario_params and asset dicts
- Event bus ← PdM alert and health change events
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class PdMBridgeConfig:
    """Configuration for the PdM integration bridge."""
    # Minimum health score change to trigger a twin patch
    health_score_patch_threshold: float = 2.0
    # Minimum RUL change (hours) to trigger a twin patch
    rul_patch_threshold_hours: float = 24.0
    # Map PdM health bands to loweconex anomaly severity
    band_severity_map: Dict[str, str] = field(default_factory=lambda: {
        "healthy": "none",
        "monitoring": "low",
        "alert": "medium",
        "action": "high",
        "critical": "critical",
    })
    # Whether to publish events to the loweconex event bus
    publish_events: bool = True
    # Maximum number of assets to process in one sync pass
    batch_size: int = 500


# =============================================================================
# Normalized PdM Snapshot (per asset)
# =============================================================================

@dataclass
class PdMAssetSnapshot:
    """
    Normalized container for PdM model outputs for a single asset.

    Can be populated from:
    - A live HVACRPdMAdvancedSystem instance
    - A stored JSON snapshot (e.g. from Redis or PostgreSQL)
    - A manual dict for testing
    """
    asset_id: str = ""
    site_id: Optional[str] = None
    timestamp: Optional[datetime] = None

    # Health index (0-100, higher = healthier)
    health_score: float = 100.0
    health_band: str = "healthy"
    health_confidence: float = 0.0
    health_trend: float = 0.0  # positive = improving
    pf_position: float = 0.0  # P-F curve position (0=potential, 1=functional failure)

    # Component scores (0-100)
    sensor_trust_score: float = 100.0
    change_detection_score: float = 100.0
    fault_probability_score: float = 100.0
    rul_score: float = 100.0
    degradation_score: float = 100.0

    # RUL (remaining useful life)
    rul_hours: float = float("inf")
    rul_lower_bound_hours: float = 0.0
    rul_upper_bound_hours: float = float("inf")
    rul_confidence: float = 0.0
    degradation_index: float = 0.0
    degradation_rate: float = 0.0

    # Fault diagnosis
    top_fault: Optional[str] = None
    top_fault_probability: float = 0.0
    fault_beliefs: Dict[str, float] = field(default_factory=dict)

    # Alert state
    alert_type: Optional[str] = None  # "normal", "watch", "actionable", "sensor_integrity"
    alert_confidence: float = 0.0
    recommended_action: str = ""

    # Sensor trust summary
    n_sensors_total: int = 0
    n_sensors_trusted: int = 0
    untrusted_sensors: List[str] = field(default_factory=list)

    # Anomaly flags detected by PdM
    anomaly_flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "asset_id": self.asset_id,
            "site_id": self.site_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "health_score": self.health_score,
            "health_band": self.health_band,
            "health_confidence": self.health_confidence,
            "health_trend": self.health_trend,
            "pf_position": self.pf_position,
            "sensor_trust_score": self.sensor_trust_score,
            "change_detection_score": self.change_detection_score,
            "fault_probability_score": self.fault_probability_score,
            "rul_score": self.rul_score,
            "degradation_score": self.degradation_score,
            "rul_hours": self.rul_hours if math.isfinite(self.rul_hours) else None,
            "rul_lower_bound_hours": self.rul_lower_bound_hours,
            "rul_upper_bound_hours": (
                self.rul_upper_bound_hours
                if math.isfinite(self.rul_upper_bound_hours) else None
            ),
            "rul_confidence": self.rul_confidence,
            "degradation_index": self.degradation_index,
            "degradation_rate": self.degradation_rate,
            "top_fault": self.top_fault,
            "top_fault_probability": self.top_fault_probability,
            "fault_beliefs": self.fault_beliefs,
            "alert_type": self.alert_type,
            "alert_confidence": self.alert_confidence,
            "recommended_action": self.recommended_action,
            "n_sensors_total": self.n_sensors_total,
            "n_sensors_trusted": self.n_sensors_trusted,
            "untrusted_sensors": self.untrusted_sensors,
            "anomaly_flags": self.anomaly_flags,
        }
        return result

    @classmethod
    def from_pdm_system(cls, system: Any) -> "PdMAssetSnapshot":
        """
        Extract a snapshot from a live HVACRPdMAdvancedSystem instance.

        Args:
            system: An instance of predictive_maintenance.integration.advanced_system.HVACRPdMAdvancedSystem
        """
        snap = cls(
            asset_id=getattr(system, "asset_id", ""),
            site_id=getattr(system, "site_id", None),
            timestamp=datetime.utcnow(),
        )

        # Health index
        health = getattr(system, "current_health", None)
        if health is not None:
            snap.health_score = getattr(health, "health_score", 100.0)
            snap.health_band = getattr(health, "health_band", "healthy")
            snap.health_confidence = getattr(health, "confidence", 0.0)
            snap.health_trend = getattr(health, "score_trend", 0.0)
            snap.pf_position = getattr(health, "pf_position", 0.0)
            snap.sensor_trust_score = getattr(health, "sensor_trust_score", 100.0)
            snap.change_detection_score = getattr(health, "change_detection_score", 100.0)
            snap.fault_probability_score = getattr(health, "fault_probability_score", 100.0)
            snap.rul_score = getattr(health, "rul_score", 100.0)
            snap.degradation_score = getattr(health, "degradation_score", 100.0)

        # RUL estimate
        rul = getattr(system, "current_rul", None)
        if rul is not None:
            snap.rul_hours = getattr(rul, "rul_hours", float("inf"))
            snap.rul_lower_bound_hours = getattr(rul, "rul_lower_bound_hours", 0.0)
            snap.rul_upper_bound_hours = getattr(rul, "rul_upper_bound_hours", float("inf"))
            snap.rul_confidence = getattr(rul, "confidence", 0.0)
            snap.degradation_index = getattr(rul, "degradation_index", 0.0)
            snap.degradation_rate = getattr(rul, "degradation_rate", 0.0)

        # Fault hypothesis
        fault_hyp = getattr(system, "fault_hypothesis", None)
        if fault_hyp is not None:
            try:
                hyp = fault_hyp.get_current_hypothesis()
                if hyp is not None:
                    top = getattr(hyp, "top_fault", None)
                    snap.top_fault = top.value if hasattr(top, "value") else str(top) if top else None
                    snap.top_fault_probability = getattr(hyp, "top_probability", 0.0)
                    beliefs = getattr(hyp, "beliefs", {})
                    snap.fault_beliefs = {
                        (k.value if hasattr(k, "value") else str(k)): float(v)
                        for k, v in beliefs.items()
                    }
            except Exception:
                pass

        # Alert state
        alert = getattr(system, "current_alert", None)
        if alert is not None:
            at = getattr(alert, "alert_type", None)
            snap.alert_type = at.value if hasattr(at, "value") else str(at) if at else None
            snap.alert_confidence = getattr(alert, "confidence", 0.0)
            snap.recommended_action = getattr(alert, "recommended_action", "")

        # Sensor trust
        trust_scores = getattr(system, "current_trust_scores", {})
        snap.n_sensors_total = len(trust_scores)
        snap.n_sensors_trusted = sum(
            1 for t in trust_scores.values()
            if hasattr(t, "is_trusted") and t.is_trusted()
        )
        snap.untrusted_sensors = [
            sid for sid, t in trust_scores.items()
            if hasattr(t, "is_trusted") and not t.is_trusted()
        ]

        return snap

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PdMAssetSnapshot":
        """Create from a stored dictionary."""
        snap = cls()
        for k, v in data.items():
            if hasattr(snap, k):
                if k == "timestamp" and isinstance(v, str):
                    try:
                        v = datetime.fromisoformat(v)
                    except (ValueError, TypeError):
                        v = None
                setattr(snap, k, v)
        return snap


# =============================================================================
# PdM Bridge
# =============================================================================

class PdMBridge:
    """
    Connector that feeds PdM model outputs into the Loweconex platform.

    Usage:
        bridge = PdMBridge(twin_store, event_bus)
        bridge.sync_from_pdm_systems({"asset_001": pdm_system_001, ...})
        enriched = bridge.enrich_kpi_inputs(company_id, scenario_params)
    """

    def __init__(
        self,
        twin_store: Any = None,
        event_bus: Any = None,
        config: Optional[PdMBridgeConfig] = None,
    ):
        self.twin_store = twin_store
        self.event_bus = event_bus
        self.config = config or PdMBridgeConfig()
        # Cache of latest snapshots keyed by asset_id
        self._snapshots: Dict[str, PdMAssetSnapshot] = {}

    # -------------------------------------------------------------------------
    # Ingestion: from live PdM systems
    # -------------------------------------------------------------------------

    def sync_from_pdm_systems(
        self,
        systems: Dict[str, Any],
    ) -> Dict[str, PdMAssetSnapshot]:
        """
        Extract snapshots from live HVACRPdMAdvancedSystem instances and
        apply patches to the corresponding AssetTwins.

        Args:
            systems: Mapping of asset_id → HVACRPdMAdvancedSystem instance

        Returns:
            Dict of asset_id → PdMAssetSnapshot
        """
        results: Dict[str, PdMAssetSnapshot] = {}
        count = 0

        for asset_id, system in systems.items():
            if count >= self.config.batch_size:
                logger.warning(f"PdM bridge batch limit reached ({self.config.batch_size})")
                break

            try:
                snapshot = PdMAssetSnapshot.from_pdm_system(system)
                self._snapshots[asset_id] = snapshot
                results[asset_id] = snapshot

                # Apply to twin store
                self._apply_twin_patch(asset_id, snapshot)

                # Publish events
                if self.config.publish_events and self.event_bus:
                    self._publish_pdm_events(snapshot)

                count += 1
            except Exception as e:
                logger.error(f"PdM bridge sync failed for {asset_id}: {e}")

        logger.info(f"PdM bridge synced {count} assets")
        return results

    def sync_from_snapshots(
        self,
        snapshots: List[Dict[str, Any]],
    ) -> Dict[str, PdMAssetSnapshot]:
        """
        Ingest pre-serialized PdM snapshots (e.g. from Redis or a REST API).

        Args:
            snapshots: List of snapshot dicts (each must have 'asset_id')
        """
        results: Dict[str, PdMAssetSnapshot] = {}
        for data in snapshots:
            asset_id = data.get("asset_id", "")
            if not asset_id:
                continue
            snap = PdMAssetSnapshot.from_dict(data)
            self._snapshots[asset_id] = snap
            results[asset_id] = snap
            self._apply_twin_patch(asset_id, snap)

        logger.info(f"PdM bridge ingested {len(results)} stored snapshots")
        return results

    # -------------------------------------------------------------------------
    # Twin patching
    # -------------------------------------------------------------------------

    def _apply_twin_patch(self, asset_id: str, snap: PdMAssetSnapshot):
        """Patch the AssetTwin in the twin store with PdM data."""
        if self.twin_store is None:
            return

        try:
            twin = self.twin_store.get_asset(asset_id)
            if twin is None:
                logger.debug(f"No twin found for asset {asset_id}, skipping patch")
                return

            # --- HealthState patch ---
            health = getattr(twin, "health", None)
            if health is not None:
                health.health_score = snap.health_score
                # Convert RUL hours → 30d/90d failure risk
                health.failure_risk_30d = self._rul_to_failure_risk(snap.rul_hours, 30 * 24)
                health.failure_risk_90d = self._rul_to_failure_risk(snap.rul_hours, 90 * 24)
                health.last_assessment_ts = snap.timestamp or datetime.utcnow()
                health.assessment_source = "pdm_bridge"

                # Map PdM anomaly flags
                health.anomaly_flags = self._map_anomaly_flags(snap)

            # --- Economics patch ---
            economics = getattr(twin, "economics", None)
            if economics is not None and math.isfinite(snap.rul_hours) and snap.rul_hours > 0:
                economics.remaining_useful_life_months = snap.rul_hours / (24 * 30)

            # Write back
            if hasattr(self.twin_store, "update_asset"):
                self.twin_store.update_asset(twin)
            elif hasattr(self.twin_store, "upsert_asset"):
                self.twin_store.upsert_asset(twin)

        except Exception as e:
            logger.error(f"Twin patch failed for {asset_id}: {e}")

    @staticmethod
    def _rul_to_failure_risk(rul_hours: float, horizon_hours: float) -> float:
        """
        Convert RUL estimate to failure probability within a time horizon.

        Uses exponential CDF: P(fail within H) = 1 - exp(-H / RUL)
        """
        if not math.isfinite(rul_hours) or rul_hours <= 0:
            return 1.0 if rul_hours == 0 else 0.01
        return round(1.0 - math.exp(-horizon_hours / rul_hours), 4)

    def _map_anomaly_flags(self, snap: PdMAssetSnapshot) -> List:
        """Map PdM fault types and anomaly indicators to AnomalyFlag enums."""
        from loweconex_platform.digital_twins.models import AnomalyFlag

        flag_mapping = {
            "refrigerant_undercharge": AnomalyFlag.REFRIGERANT_UNDERCHARGE,
            "refrigerant_overcharge": AnomalyFlag.HIGH_HEAD_PRESSURE,
            "condenser_fouling": AnomalyFlag.HIGH_HEAD_PRESSURE,
            "evaporator_icing": AnomalyFlag.COIL_ICING,
            "compressor_degradation": AnomalyFlag.PERFORMANCE_DEGRADATION,
            "fan_degradation": AnomalyFlag.FAN_DEGRADATION,
            "sensor_drift": AnomalyFlag.SENSOR_DRIFT,
            "short_cycling": AnomalyFlag.SHORT_CYCLING,
            "high_energy": AnomalyFlag.HIGH_ENERGY,
            "temp_excursion": AnomalyFlag.TEMP_EXCURSION,
            "vibration_anomaly": AnomalyFlag.VIBRATION_ANOMALY,
        }

        flags = []

        # From top fault
        if snap.top_fault and snap.top_fault_probability > 0.3:
            fault_key = snap.top_fault.lower().replace(" ", "_")
            mapped = flag_mapping.get(fault_key)
            if mapped:
                flags.append(mapped)

        # From explicit anomaly flags
        for af in snap.anomaly_flags:
            mapped = flag_mapping.get(af.lower().replace(" ", "_"))
            if mapped and mapped not in flags:
                flags.append(mapped)

        # Health-band-derived flags
        if snap.health_band in ("action", "critical"):
            if AnomalyFlag.PERFORMANCE_DEGRADATION not in flags:
                flags.append(AnomalyFlag.PERFORMANCE_DEGRADATION)

        return flags

    # -------------------------------------------------------------------------
    # Event publishing
    # -------------------------------------------------------------------------

    def _publish_pdm_events(self, snap: PdMAssetSnapshot):
        """Publish PdM state changes onto the Loweconex event bus."""
        if self.event_bus is None:
            return

        try:
            severity = self.config.band_severity_map.get(snap.health_band, "low")

            # Health update event
            self.event_bus.publish_event(
                stream="loweconex:pdm_health",
                event_data={
                    "event_type": "pdm_health_update",
                    "asset_id": snap.asset_id,
                    "site_id": snap.site_id,
                    "health_score": snap.health_score,
                    "health_band": snap.health_band,
                    "rul_hours": snap.rul_hours if math.isfinite(snap.rul_hours) else None,
                    "top_fault": snap.top_fault,
                    "top_fault_probability": snap.top_fault_probability,
                    "severity": severity,
                    "timestamp": (snap.timestamp or datetime.utcnow()).isoformat(),
                },
            )

            # Alert event (only for actionable)
            if snap.alert_type == "actionable":
                self.event_bus.publish_event(
                    stream="loweconex:pdm_alerts",
                    event_data={
                        "event_type": "pdm_actionable_alert",
                        "asset_id": snap.asset_id,
                        "site_id": snap.site_id,
                        "alert_confidence": snap.alert_confidence,
                        "top_fault": snap.top_fault,
                        "recommended_action": snap.recommended_action,
                        "rul_hours": snap.rul_hours if math.isfinite(snap.rul_hours) else None,
                        "timestamp": (snap.timestamp or datetime.utcnow()).isoformat(),
                    },
                )
        except Exception as e:
            logger.debug(f"PdM event publish failed for {snap.asset_id}: {e}")

    # -------------------------------------------------------------------------
    # KPI enrichment
    # -------------------------------------------------------------------------

    def get_snapshot(self, asset_id: str) -> Optional[PdMAssetSnapshot]:
        """Get the latest PdM snapshot for an asset."""
        return self._snapshots.get(asset_id)

    def get_all_snapshots(self) -> Dict[str, PdMAssetSnapshot]:
        """Get all cached PdM snapshots."""
        return dict(self._snapshots)

    def enrich_kpi_inputs(
        self,
        company_id: str,
        assets: List[Dict[str, Any]],
        scenario_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Enrich KPI crew inputs with PdM model outputs.

        Returns a dict of PdM-derived parameters that can be merged into
        scenario_params for KPI crews.

        Provides:
        - pdm_avg_health_score: fleet-wide average health
        - pdm_avg_rul_hours: fleet-wide average RUL
        - pdm_failure_rate_30d: empirical 30-day failure rate from PdM
        - pdm_assets_at_risk: count of assets in action/critical band
        - pdm_prediction_accuracy: average RUL confidence
        - pdm_fault_distribution: {fault_type: count}
        - pdm_asset_details: per-asset PdM summary
        """
        enriched: Dict[str, Any] = {}
        matched = []

        for asset in assets:
            aid = asset.get("asset_id", "")
            snap = self._snapshots.get(aid)
            if snap is None:
                continue
            matched.append(snap)

        if not matched:
            logger.debug(f"No PdM snapshots matched for company {company_id}")
            return enriched

        # Fleet-level aggregates
        health_scores = [s.health_score for s in matched]
        rul_values = [s.rul_hours for s in matched if math.isfinite(s.rul_hours)]
        rul_confidences = [s.rul_confidence for s in matched if s.rul_confidence > 0]

        enriched["pdm_avg_health_score"] = sum(health_scores) / len(health_scores)
        enriched["pdm_avg_rul_hours"] = (
            sum(rul_values) / len(rul_values) if rul_values else float("inf")
        )
        enriched["pdm_prediction_accuracy"] = (
            sum(rul_confidences) / len(rul_confidences) if rul_confidences else 0.0
        )

        # Empirical failure rate (assets in action/critical band)
        at_risk = [s for s in matched if s.health_band in ("action", "critical")]
        enriched["pdm_assets_at_risk"] = len(at_risk)
        enriched["pdm_failure_rate_30d"] = (
            len(at_risk) / len(matched) if matched else 0.0
        )

        # Override deterministic defaults with PdM-grounded values
        if rul_confidences:
            enriched["prediction_accuracy"] = enriched["pdm_prediction_accuracy"]
        if at_risk:
            enriched["baseline_failure_rate"] = enriched["pdm_failure_rate_30d"]

        # Fault distribution
        fault_dist: Dict[str, int] = {}
        for s in matched:
            if s.top_fault and s.top_fault_probability > 0.3:
                fault_dist[s.top_fault] = fault_dist.get(s.top_fault, 0) + 1
        enriched["pdm_fault_distribution"] = fault_dist

        # Per-asset summary (compact, for KPI crew context)
        asset_details = []
        for s in matched:
            asset_details.append({
                "asset_id": s.asset_id,
                "health_score": round(s.health_score, 1),
                "health_band": s.health_band,
                "rul_hours": round(s.rul_hours, 1) if math.isfinite(s.rul_hours) else None,
                "top_fault": s.top_fault,
                "failure_risk_30d": self._rul_to_failure_risk(s.rul_hours, 30 * 24),
                "failure_risk_90d": self._rul_to_failure_risk(s.rul_hours, 90 * 24),
                "degradation_index": round(s.degradation_index, 3),
                "pf_position": round(s.pf_position, 3),
            })
        enriched["pdm_asset_details"] = asset_details

        logger.info(
            f"PdM enrichment: {len(matched)}/{len(assets)} assets matched, "
            f"avg_health={enriched['pdm_avg_health_score']:.1f}, "
            f"at_risk={len(at_risk)}"
        )

        return enriched

    def enrich_asset_dicts(
        self,
        assets: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Enrich asset dicts (as consumed by KPI calculation functions) with
        PdM-derived health and risk fields.

        Mutates and returns the same list.
        """
        for asset in assets:
            aid = asset.get("asset_id", "")
            snap = self._snapshots.get(aid)
            if snap is None:
                continue

            # Inject PdM fields into the asset dict
            health = asset.get("health", {})
            if not isinstance(health, dict):
                health = {}

            health["health_score"] = snap.health_score
            health["failure_risk_30d"] = self._rul_to_failure_risk(snap.rul_hours, 30 * 24)
            health["failure_risk_90d"] = self._rul_to_failure_risk(snap.rul_hours, 90 * 24)
            health["pdm_health_band"] = snap.health_band
            health["pdm_pf_position"] = snap.pf_position
            health["pdm_degradation_index"] = snap.degradation_index
            health["pdm_source"] = "pdm_bridge"
            asset["health"] = health

            # Economics
            econ = asset.get("economics", {})
            if not isinstance(econ, dict):
                econ = {}
            if math.isfinite(snap.rul_hours) and snap.rul_hours > 0:
                econ["remaining_useful_life_months"] = round(snap.rul_hours / (24 * 30), 1)
            asset["economics"] = econ

            # Top fault (for fault-aware KPI calculations)
            if snap.top_fault and snap.top_fault_probability > 0.3:
                asset["pdm_top_fault"] = snap.top_fault
                asset["pdm_top_fault_probability"] = snap.top_fault_probability

        return assets

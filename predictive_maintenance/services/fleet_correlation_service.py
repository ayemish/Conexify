"""
Fleet-Wide Cross-Asset Correlation Service

Detects patterns that span multiple co-located or similar assets:
1. **Common-cause analysis** — simultaneous faults across units on the
   same site (e.g. utility failure, ambient event, refrigerant supplier batch)
2. **Fleet degradation curves** — age/type cohort degradation tracking
3. **Transfer learning** — propagates fingerprint priors from similar units

Tracks its own error model:
- False correlation rate (flagged correlation that turned out coincidental)
- Missed correlation rate (correlated events not detected)

References:
- ISO 14224: Collection and exchange of reliability data
- Jardine et al., "A review on machinery diagnostics and prognostics
  implementing CBM", Mechanical Systems and Signal Processing, 2006
"""

import logging
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ── Data classes ─────────────────────────────────────────────────────

@dataclass
class AssetSnapshot:
    """Lightweight snapshot of one asset's current state."""
    asset_id: str
    site_id: str = ""
    asset_type: str = ""
    age_hours: float = 0.0
    health_score: float = 100.0
    fault_type: Optional[str] = None
    fault_probability: float = 0.0
    alert_active: bool = False
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CorrelationEvent:
    """A detected cross-asset correlation."""
    event_id: str = field(default_factory=lambda: f"CORR-{uuid.uuid4().hex[:10].upper()}")
    timestamp: datetime = field(default_factory=datetime.utcnow)
    correlation_type: str = ""  # common_cause | cohort_degradation | transfer_prior
    site_id: str = ""
    asset_ids: List[str] = field(default_factory=list)
    description: str = ""
    confidence: float = 0.0

    # Fault details
    common_fault_type: Optional[str] = None
    avg_fault_probability: float = 0.0
    n_affected_assets: int = 0

    # Error model
    false_correlation_rate: float = 0.0
    missed_correlation_rate: float = 0.0

    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "correlation_type": self.correlation_type,
            "site_id": self.site_id,
            "asset_ids": self.asset_ids,
            "description": self.description,
            "confidence": round(self.confidence, 3),
            "common_fault_type": self.common_fault_type,
            "n_affected_assets": self.n_affected_assets,
            "false_correlation_rate": round(self.false_correlation_rate, 3),
            "missed_correlation_rate": round(self.missed_correlation_rate, 3),
        }


@dataclass
class CohortDegradation:
    """Degradation trend for an asset cohort (type + age band)."""
    cohort_key: str = ""
    asset_type: str = ""
    age_band: str = ""
    n_assets: int = 0
    mean_health: float = 100.0
    std_health: float = 0.0
    degradation_rate_per_month: float = 0.0
    common_fault_types: List[str] = field(default_factory=list)


# ── Service ──────────────────────────────────────────────────────────

class FleetCorrelationService:
    """
    Monitors a fleet of assets for cross-asset patterns.

    Call ``update_asset()`` every time an asset's state changes, then
    periodically call ``analyze()`` (e.g. every 5 minutes) to scan for
    correlations.
    """

    def __init__(
        self,
        common_cause_window_minutes: float = 30.0,
        common_cause_min_assets: int = 2,
        cohort_min_assets: int = 3,
    ):
        self.common_cause_window = timedelta(minutes=common_cause_window_minutes)
        self.common_cause_min_assets = common_cause_min_assets
        self.cohort_min_assets = cohort_min_assets

        # Current fleet state
        self._snapshots: Dict[str, AssetSnapshot] = {}

        # Alert history for common-cause detection
        self._alert_history: deque = deque(maxlen=10000)

        # Historical correlations
        self.detected_events: List[CorrelationEvent] = []

        # Error calibration
        self._confirmed: int = 0
        self._false_corr: int = 0
        self._missed: int = 0

    # ── Public API ───────────────────────────────────────────────────

    def update_asset(self, snapshot: AssetSnapshot):
        """Update the fleet state with a new asset snapshot."""
        self._snapshots[snapshot.asset_id] = snapshot
        if snapshot.alert_active:
            self._alert_history.append(snapshot)

    def analyze(self, now: Optional[datetime] = None) -> List[CorrelationEvent]:
        """Run all correlation analyses and return new events."""
        now = now or datetime.utcnow()
        events: List[CorrelationEvent] = []

        cc = self._detect_common_cause(now)
        if cc:
            events.extend(cc)

        cohorts = self._detect_cohort_degradation(now)
        if cohorts:
            events.extend(cohorts)

        self.detected_events.extend(events)
        return events

    def get_cohort_summary(self) -> List[CohortDegradation]:
        """Return degradation summary for each asset cohort."""
        cohorts = self._build_cohorts()
        return [self._summarize_cohort(key, assets) for key, assets in cohorts.items()]

    def get_transfer_priors(
        self, asset_id: str,
    ) -> Dict[str, Any]:
        """
        Get fingerprint/degradation priors from similar assets.

        Useful for new assets with little data: bootstrap their behaviour
        model from the fleet cohort.
        """
        snap = self._snapshots.get(asset_id)
        if not snap:
            return {}

        similar = [
            s for s in self._snapshots.values()
            if s.asset_type == snap.asset_type
            and s.asset_id != asset_id
        ]
        if not similar:
            return {}

        health_scores = [s.health_score for s in similar]
        fault_counts: Dict[str, int] = defaultdict(int)
        for s in similar:
            if s.fault_type:
                fault_counts[s.fault_type] += 1

        return {
            "cohort_size": len(similar),
            "mean_health": float(np.mean(health_scores)),
            "std_health": float(np.std(health_scores)),
            "common_faults": dict(fault_counts),
            "age_range_hours": (
                min(s.age_hours for s in similar),
                max(s.age_hours for s in similar),
            ),
        }

    def confirm_correlation(self, was_real: bool):
        """Ground truth feedback for error calibration."""
        if was_real:
            self._confirmed += 1
        else:
            self._false_corr += 1

    def record_missed(self):
        self._missed += 1

    @property
    def false_correlation_rate(self) -> float:
        total = self._confirmed + self._false_corr
        return self._false_corr / max(total, 1)

    @property
    def missed_correlation_rate(self) -> float:
        total = self._confirmed + self._missed
        return self._missed / max(total, 1)

    # ── Common-cause detection ───────────────────────────────────────

    def _detect_common_cause(self, now: datetime) -> List[CorrelationEvent]:
        """Detect simultaneous alerts across co-located assets."""
        events: List[CorrelationEvent] = []
        cutoff = now - self.common_cause_window

        # Group recent alerts by (site, fault_type)
        recent = [s for s in self._alert_history if s.timestamp >= cutoff]
        groups: Dict[Tuple[str, Optional[str]], List[AssetSnapshot]] = defaultdict(list)
        for s in recent:
            groups[(s.site_id, s.fault_type)].append(s)

        for (site_id, fault_type), assets in groups.items():
            unique_assets = {a.asset_id for a in assets}
            if len(unique_assets) < self.common_cause_min_assets:
                continue

            avg_prob = float(np.mean([a.fault_probability for a in assets]))
            confidence = min(
                avg_prob * len(unique_assets) / 5.0,
                1.0,
            )

            events.append(CorrelationEvent(
                timestamp=now,
                correlation_type="common_cause",
                site_id=site_id,
                asset_ids=list(unique_assets),
                description=(
                    f"{len(unique_assets)} assets at site {site_id} "
                    f"alerting for {fault_type or 'unknown'} within "
                    f"{self.common_cause_window.total_seconds()/60:.0f} min"
                ),
                confidence=confidence,
                common_fault_type=fault_type,
                avg_fault_probability=avg_prob,
                n_affected_assets=len(unique_assets),
                false_correlation_rate=self.false_correlation_rate,
                missed_correlation_rate=self.missed_correlation_rate,
                evidence={
                    "window_minutes": self.common_cause_window.total_seconds() / 60,
                    "asset_probs": {
                        a.asset_id: a.fault_probability for a in assets
                    },
                },
            ))

        return events

    # ── Cohort degradation ───────────────────────────────────────────

    def _detect_cohort_degradation(self, now: datetime) -> List[CorrelationEvent]:
        """Detect fleet-wide degradation in asset cohorts."""
        events: List[CorrelationEvent] = []
        cohorts = self._build_cohorts()

        for key, assets in cohorts.items():
            if len(assets) < self.cohort_min_assets:
                continue

            summary = self._summarize_cohort(key, assets)

            # Flag if cohort mean health is in alert band
            if summary.mean_health < 60:
                events.append(CorrelationEvent(
                    timestamp=now,
                    correlation_type="cohort_degradation",
                    site_id="fleet",
                    asset_ids=[a.asset_id for a in assets],
                    description=(
                        f"Cohort {key} ({summary.n_assets} assets): "
                        f"mean health={summary.mean_health:.0f}, "
                        f"rate={summary.degradation_rate_per_month:.1f}/month"
                    ),
                    confidence=min(summary.n_assets / 10.0, 1.0),
                    n_affected_assets=summary.n_assets,
                    false_correlation_rate=self.false_correlation_rate,
                    missed_correlation_rate=self.missed_correlation_rate,
                    evidence={
                        "cohort_key": key,
                        "mean_health": summary.mean_health,
                        "std_health": summary.std_health,
                        "common_faults": summary.common_fault_types,
                    },
                ))

        return events

    def _build_cohorts(self) -> Dict[str, List[AssetSnapshot]]:
        """Group assets into (type, age_band) cohorts."""
        cohorts: Dict[str, List[AssetSnapshot]] = defaultdict(list)
        for snap in self._snapshots.values():
            age_band = self._age_band(snap.age_hours)
            key = f"{snap.asset_type}:{age_band}"
            cohorts[key].append(snap)
        return cohorts

    @staticmethod
    def _summarize_cohort(key: str, assets: List[AssetSnapshot]) -> CohortDegradation:
        parts = key.split(":", 1)
        asset_type = parts[0] if parts else ""
        age_band = parts[1] if len(parts) > 1 else ""

        health_scores = [a.health_score for a in assets]
        fault_counts: Dict[str, int] = defaultdict(int)
        for a in assets:
            if a.fault_type:
                fault_counts[a.fault_type] += 1

        return CohortDegradation(
            cohort_key=key,
            asset_type=asset_type,
            age_band=age_band,
            n_assets=len(assets),
            mean_health=float(np.mean(health_scores)),
            std_health=float(np.std(health_scores)),
            common_fault_types=sorted(fault_counts, key=fault_counts.get, reverse=True)[:3],
        )

    @staticmethod
    def _age_band(hours: float) -> str:
        years = hours / 8760
        if years < 1:
            return "0-1y"
        if years < 3:
            return "1-3y"
        if years < 5:
            return "3-5y"
        if years < 10:
            return "5-10y"
        return "10y+"

    # ── Agent Voting Context Integration ─────────────────────────────

    def get_voting_context(self, asset_id: str) -> Dict[str, Any]:
        """
        Get fleet correlation context for agent voting decisions.
        
        Returns context that agents can use to adjust their votes:
        - Similar assets with same fault → increase confidence
        - Fleet-wide degradation pattern → increase urgency
        - Isolated anomaly → may reduce confidence
        
        Args:
            asset_id: Asset being evaluated
            
        Returns:
            Dict with fleet context for agent voting
        """
        snap = self._snapshots.get(asset_id)
        if not snap:
            return {"fleet_context_available": False}
        
        # Get recent correlations involving this asset
        recent_correlations = [
            e for e in self.detected_events[-50:]
            if asset_id in e.asset_ids
        ]
        
        # Get similar assets on same site
        site_peers = [
            s for s in self._snapshots.values()
            if s.site_id == snap.site_id and s.asset_id != asset_id
        ]
        
        # Get assets with same fault type
        same_fault_assets = [
            s for s in self._snapshots.values()
            if s.fault_type == snap.fault_type 
            and s.fault_type is not None
            and s.asset_id != asset_id
        ]
        
        # Calculate fleet signal strength
        fleet_signal = self._calculate_fleet_signal(snap, site_peers, same_fault_assets)
        
        # Get cohort priors
        cohort_priors = self.get_transfer_priors(asset_id)
        
        return {
            "fleet_context_available": True,
            "asset_id": asset_id,
            "site_id": snap.site_id,
            
            # Correlation signals
            "recent_correlations": len(recent_correlations),
            "active_common_cause": any(
                e.correlation_type == "common_cause" 
                for e in recent_correlations
            ),
            "cohort_degradation_active": any(
                e.correlation_type == "cohort_degradation"
                for e in recent_correlations
            ),
            
            # Site context
            "site_peer_count": len(site_peers),
            "site_peers_alerting": sum(1 for s in site_peers if s.alert_active),
            "site_avg_health": float(np.mean([s.health_score for s in site_peers])) if site_peers else 100.0,
            
            # Fleet-wide fault signal
            "same_fault_count": len(same_fault_assets),
            "fleet_signal_strength": fleet_signal,
            
            # Cohort priors for Bayesian update
            "cohort_priors": cohort_priors,
            
            # Voting weight adjustments
            "confidence_adjustment": self._calculate_confidence_adjustment(
                fleet_signal, len(recent_correlations), snap
            ),
            "urgency_adjustment": self._calculate_urgency_adjustment(
                site_peers, same_fault_assets, snap
            ),
            
            # Error model for calibration
            "false_correlation_rate": self.false_correlation_rate,
            "missed_correlation_rate": self.missed_correlation_rate,
        }

    def _calculate_fleet_signal(
        self,
        snap: AssetSnapshot,
        site_peers: List[AssetSnapshot],
        same_fault_assets: List[AssetSnapshot],
    ) -> float:
        """
        Calculate fleet-wide signal strength for this fault pattern.
        
        Higher signal = more likely a real fault (corroborated by fleet).
        Lower signal = may be isolated anomaly or sensor issue.
        """
        signal = 0.0
        
        # Same site, same fault type
        site_same_fault = sum(
            1 for s in site_peers 
            if s.fault_type == snap.fault_type and s.fault_type is not None
        )
        if site_same_fault > 0:
            signal += 0.3 * min(site_same_fault / 3.0, 1.0)
        
        # Fleet-wide same fault
        if len(same_fault_assets) > 2:
            signal += 0.2 * min(len(same_fault_assets) / 10.0, 1.0)
        
        # Peer correlation (similar health degradation)
        if site_peers:
            peer_health_scores = [s.health_score for s in site_peers]
            if np.std(peer_health_scores) < 10 and np.mean(peer_health_scores) < 70:
                signal += 0.2
        
        # Recent common cause events
        recent_cc = [
            e for e in self.detected_events[-20:]
            if e.correlation_type == "common_cause"
            and snap.site_id == e.site_id
        ]
        if recent_cc:
            signal += 0.3 * min(len(recent_cc) / 3.0, 1.0)
        
        return min(signal, 1.0)

    def _calculate_confidence_adjustment(
        self,
        fleet_signal: float,
        correlation_count: int,
        snap: AssetSnapshot,
    ) -> float:
        """
        Calculate confidence adjustment for agent votes.
        
        Returns a multiplier:
        - > 1.0: Increase confidence (fleet corroboration)
        - < 1.0: Decrease confidence (isolated anomaly)
        - = 1.0: No adjustment
        """
        adjustment = 1.0
        
        if fleet_signal > 0.5:
            adjustment += 0.15 * fleet_signal
        elif fleet_signal < 0.1 and snap.alert_active:
            adjustment -= 0.1
        
        if correlation_count > 2:
            adjustment += 0.05 * min(correlation_count, 5)
        
        return max(0.7, min(1.3, adjustment))

    def _calculate_urgency_adjustment(
        self,
        site_peers: List[AssetSnapshot],
        same_fault_assets: List[AssetSnapshot],
        snap: AssetSnapshot,
    ) -> float:
        """
        Calculate urgency adjustment for prioritization.
        
        Returns a multiplier:
        - > 1.0: Increase urgency (spreading issue)
        - < 1.0: Decrease urgency (stable/isolated)
        - = 1.0: No adjustment
        """
        adjustment = 1.0
        
        alerting_peers = sum(1 for s in site_peers if s.alert_active)
        if alerting_peers > 2:
            adjustment += 0.2 * min(alerting_peers / 5.0, 1.0)
        
        if len(same_fault_assets) > 3:
            recent_same = [
                s for s in same_fault_assets
                if (datetime.utcnow() - s.timestamp).total_seconds() < 3600
            ]
            if len(recent_same) > 1:
                adjustment += 0.15
        
        if snap.health_score < 40:
            adjustment += 0.1
        
        return max(0.8, min(1.5, adjustment))

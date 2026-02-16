"""
MLOps Model Registry, Model Cards, Drift Monitoring & Rollback.

Provides:
- Model registry (MLflow-inspired): versioning, lineage, stages/aliases, metadata
- Model cards (arXiv:1810.03993): structured documentation per model
- Drift monitoring: data drift (PSI/KL), concept drift (performance decay)
- Automated rollback gates with configurable thresholds

References:
- MLflow Model Registry (mlflow.org)
- Model Cards for Model Reporting (Mitchell et al., 2019)
- Evidently AI drift detection methodology
"""

from __future__ import annotations

import logging
import math
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Model stages and types
# =============================================================================

class ModelStage(str, Enum):
    """Model lifecycle stages (MLflow-compatible)."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    ARCHIVED = "archived"
    ROLLBACK = "rollback"


class ModelType(str, Enum):
    """Types of models in the platform."""
    KPI_CALCULATION = "kpi_calculation"
    SCENARIO_POLICY = "scenario_policy"
    ANOMALY_DETECTION = "anomaly_detection"
    FAULT_DIAGNOSIS = "fault_diagnosis"
    FORECASTING = "forecasting"
    OPTIMIZATION = "optimization"
    LLM_PROMPT = "llm_prompt"
    BENCHMARK = "benchmark"


class DriftType(str, Enum):
    """Types of drift detected."""
    DATA_DRIFT = "data_drift"           # Input distribution shift
    CONCEPT_DRIFT = "concept_drift"     # Target relationship change
    PERFORMANCE_DECAY = "performance_decay"
    SCHEMA_DRIFT = "schema_drift"       # Input schema changed


class DriftSeverity(str, Enum):
    WARNING = "warning"
    CRITICAL = "critical"
    ROLLBACK_TRIGGERED = "rollback_triggered"


# =============================================================================
# Model version
# =============================================================================

@dataclass
class ModelVersion:
    """
    A specific version of a registered model.
    """
    version_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    model_name: str = ""
    version: str = "1.0.0"
    model_type: str = ModelType.KPI_CALCULATION.value
    stage: str = ModelStage.DEVELOPMENT.value

    # Artifact location
    artifact_uri: Optional[str] = None
    artifact_hash: Optional[str] = None

    # Lineage
    training_run_id: Optional[str] = None
    training_dataset_id: Optional[str] = None
    parent_version_id: Optional[str] = None

    # Performance metrics
    metrics: Dict[str, float] = field(default_factory=dict)

    # Parameters / hyperparameters
    parameters: Dict[str, Any] = field(default_factory=dict)

    # Tags
    tags: Dict[str, str] = field(default_factory=dict)

    # Metadata
    description: str = ""
    created_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_by: str = ""
    promoted_ts: Optional[str] = None
    promoted_by: Optional[str] = None

    # Rollback info
    rolled_back_from: Optional[str] = None
    rollback_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version_id": self.version_id,
            "model_name": self.model_name,
            "version": self.version,
            "model_type": self.model_type,
            "stage": self.stage,
            "artifact_uri": self.artifact_uri,
            "artifact_hash": self.artifact_hash,
            "training_run_id": self.training_run_id,
            "training_dataset_id": self.training_dataset_id,
            "parent_version_id": self.parent_version_id,
            "metrics": self.metrics,
            "parameters": self.parameters,
            "tags": self.tags,
            "description": self.description,
            "created_ts": self.created_ts,
            "created_by": self.created_by,
            "promoted_ts": self.promoted_ts,
            "promoted_by": self.promoted_by,
            "rolled_back_from": self.rolled_back_from,
            "rollback_reason": self.rollback_reason,
        }


# =============================================================================
# Model card (structured documentation)
# =============================================================================

@dataclass
class ModelCard:
    """
    Model Card per Mitchell et al. (2019).

    Structured documentation for every predictive/diagnostic model
    used in KPI calculations.
    """
    card_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    model_name: str = ""
    version: str = ""

    # Model details
    model_type: str = ""
    description: str = ""
    intended_use: str = ""
    out_of_scope_uses: List[str] = field(default_factory=list)

    # Training data
    training_data_description: str = ""
    training_data_size: Optional[int] = None
    training_date_range: str = ""
    preprocessing_steps: List[str] = field(default_factory=list)

    # Evaluation
    evaluation_metrics: Dict[str, float] = field(default_factory=dict)
    evaluation_dataset: str = ""
    performance_across_groups: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # Ethical considerations
    ethical_considerations: List[str] = field(default_factory=list)
    fairness_analysis: str = ""

    # Limitations and caveats
    limitations: List[str] = field(default_factory=list)
    known_failure_modes: List[str] = field(default_factory=list)
    caveats_and_recommendations: List[str] = field(default_factory=list)

    # Quantitative analyses
    confidence_interval_method: str = ""
    uncertainty_quantification: str = ""

    # Ownership
    owner: str = ""
    contact: str = ""
    last_reviewed: Optional[str] = None
    review_frequency: str = "quarterly"

    # References
    references: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "card_id": self.card_id,
            "model_name": self.model_name,
            "version": self.version,
            "model_type": self.model_type,
            "description": self.description,
            "intended_use": self.intended_use,
            "out_of_scope_uses": self.out_of_scope_uses,
            "training_data_description": self.training_data_description,
            "training_data_size": self.training_data_size,
            "training_date_range": self.training_date_range,
            "preprocessing_steps": self.preprocessing_steps,
            "evaluation_metrics": self.evaluation_metrics,
            "evaluation_dataset": self.evaluation_dataset,
            "performance_across_groups": self.performance_across_groups,
            "ethical_considerations": self.ethical_considerations,
            "fairness_analysis": self.fairness_analysis,
            "limitations": self.limitations,
            "known_failure_modes": self.known_failure_modes,
            "caveats_and_recommendations": self.caveats_and_recommendations,
            "confidence_interval_method": self.confidence_interval_method,
            "uncertainty_quantification": self.uncertainty_quantification,
            "owner": self.owner,
            "contact": self.contact,
            "last_reviewed": self.last_reviewed,
            "review_frequency": self.review_frequency,
            "references": self.references,
        }

    def completeness_score(self) -> float:
        """Score 0–1 for how complete the model card is."""
        required = [
            self.description, self.intended_use, self.training_data_description,
            self.evaluation_dataset, self.owner,
        ]
        filled = sum(1 for r in required if r)
        has_metrics = 1 if self.evaluation_metrics else 0
        has_limitations = 1 if self.limitations else 0
        has_failure_modes = 1 if self.known_failure_modes else 0

        total = len(required) + 3
        score = (filled + has_metrics + has_limitations + has_failure_modes) / total
        return round(score, 2)


# =============================================================================
# Drift monitoring
# =============================================================================

@dataclass
class DriftAlert:
    """An alert generated by drift monitoring."""
    alert_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    model_name: str = ""
    version_id: str = ""
    drift_type: str = DriftType.DATA_DRIFT.value
    severity: str = DriftSeverity.WARNING.value
    metric_name: str = ""
    baseline_value: float = 0.0
    current_value: float = 0.0
    threshold: float = 0.0
    description: str = ""
    detected_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    resolved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "model_name": self.model_name,
            "version_id": self.version_id,
            "drift_type": self.drift_type,
            "severity": self.severity,
            "metric_name": self.metric_name,
            "baseline_value": self.baseline_value,
            "current_value": self.current_value,
            "threshold": self.threshold,
            "description": self.description,
            "detected_ts": self.detected_ts,
            "resolved": self.resolved,
        }


class DriftMonitor:
    """
    Monitors models for data drift, concept drift, and performance decay.

    Methods:
    - PSI (Population Stability Index) for data drift
    - Performance metric tracking with threshold alerts
    - Automated rollback trigger when critical thresholds breached
    """

    def __init__(
        self,
        psi_warning: float = 0.10,
        psi_critical: float = 0.25,
        perf_decay_warning: float = 0.10,
        perf_decay_critical: float = 0.25,
    ):
        self.psi_warning = psi_warning
        self.psi_critical = psi_critical
        self.perf_decay_warning = perf_decay_warning
        self.perf_decay_critical = perf_decay_critical

        self._baselines: Dict[str, Dict[str, Any]] = {}
        self._alerts: List[DriftAlert] = []
        self._metric_history: Dict[str, List[Tuple[str, float]]] = defaultdict(list)

    def set_baseline(
        self,
        model_name: str,
        metrics: Dict[str, float],
        feature_distributions: Optional[Dict[str, List[float]]] = None,
    ):
        """Set the baseline metrics and distributions for a model."""
        self._baselines[model_name] = {
            "metrics": metrics,
            "feature_distributions": feature_distributions or {},
            "set_ts": datetime.utcnow().isoformat(),
        }
        logger.info(f"Set drift baseline for {model_name}")

    def check_performance_drift(
        self, model_name: str, current_metrics: Dict[str, float]
    ) -> List[DriftAlert]:
        """Check if model performance has decayed beyond thresholds."""
        baseline = self._baselines.get(model_name)
        if not baseline:
            return []

        alerts = []
        base_metrics = baseline["metrics"]

        for metric_name, current_val in current_metrics.items():
            if metric_name not in base_metrics:
                continue

            base_val = base_metrics[metric_name]
            self._metric_history[f"{model_name}:{metric_name}"].append(
                (datetime.utcnow().isoformat(), current_val)
            )

            if base_val == 0:
                continue

            # For metrics where higher is better (accuracy, R², etc.)
            decay = (base_val - current_val) / abs(base_val)

            if decay > self.perf_decay_critical:
                alert = DriftAlert(
                    model_name=model_name,
                    drift_type=DriftType.PERFORMANCE_DECAY.value,
                    severity=DriftSeverity.CRITICAL.value,
                    metric_name=metric_name,
                    baseline_value=base_val,
                    current_value=current_val,
                    threshold=self.perf_decay_critical,
                    description=(
                        f"Performance decay {decay:.1%} exceeds critical "
                        f"threshold {self.perf_decay_critical:.0%}"
                    ),
                )
                alerts.append(alert)
                self._alerts.append(alert)

            elif decay > self.perf_decay_warning:
                alert = DriftAlert(
                    model_name=model_name,
                    drift_type=DriftType.PERFORMANCE_DECAY.value,
                    severity=DriftSeverity.WARNING.value,
                    metric_name=metric_name,
                    baseline_value=base_val,
                    current_value=current_val,
                    threshold=self.perf_decay_warning,
                    description=(
                        f"Performance decay {decay:.1%} exceeds warning "
                        f"threshold {self.perf_decay_warning:.0%}"
                    ),
                )
                alerts.append(alert)
                self._alerts.append(alert)

        return alerts

    def compute_psi(
        self, baseline_dist: List[float], current_dist: List[float], n_bins: int = 10
    ) -> float:
        """
        Compute Population Stability Index (PSI).

        PSI < 0.10: No significant change
        PSI 0.10–0.25: Moderate change (warning)
        PSI > 0.25: Significant change (critical)
        """
        if not baseline_dist or not current_dist:
            return 0.0

        b_min = min(baseline_dist)
        b_max = max(baseline_dist)
        if b_max == b_min:
            return 0.0

        bin_width = (b_max - b_min) / n_bins
        bins = [b_min + i * bin_width for i in range(n_bins + 1)]

        def histogram(data: List[float]) -> List[float]:
            counts = [0] * n_bins
            for val in data:
                idx = min(int((val - b_min) / bin_width), n_bins - 1)
                idx = max(idx, 0)
                counts[idx] += 1
            total = sum(counts)
            return [c / total if total > 0 else 1 / n_bins for c in counts]

        base_hist = histogram(baseline_dist)
        curr_hist = histogram(current_dist)

        psi = 0.0
        eps = 1e-6
        for b, c in zip(base_hist, curr_hist):
            b = max(b, eps)
            c = max(c, eps)
            psi += (c - b) * math.log(c / b)

        return psi

    def check_data_drift(
        self, model_name: str, current_distributions: Dict[str, List[float]]
    ) -> List[DriftAlert]:
        """Check feature distributions for data drift using PSI."""
        baseline = self._baselines.get(model_name)
        if not baseline:
            return []

        base_dists = baseline.get("feature_distributions", {})
        alerts = []

        for feature, current_dist in current_distributions.items():
            base_dist = base_dists.get(feature)
            if not base_dist:
                continue

            psi = self.compute_psi(base_dist, current_dist)

            if psi > self.psi_critical:
                alert = DriftAlert(
                    model_name=model_name,
                    drift_type=DriftType.DATA_DRIFT.value,
                    severity=DriftSeverity.CRITICAL.value,
                    metric_name=f"PSI_{feature}",
                    baseline_value=0.0,
                    current_value=psi,
                    threshold=self.psi_critical,
                    description=f"Feature '{feature}' PSI={psi:.3f} (critical>{self.psi_critical})",
                )
                alerts.append(alert)
                self._alerts.append(alert)

            elif psi > self.psi_warning:
                alert = DriftAlert(
                    model_name=model_name,
                    drift_type=DriftType.DATA_DRIFT.value,
                    severity=DriftSeverity.WARNING.value,
                    metric_name=f"PSI_{feature}",
                    baseline_value=0.0,
                    current_value=psi,
                    threshold=self.psi_warning,
                    description=f"Feature '{feature}' PSI={psi:.3f} (warning>{self.psi_warning})",
                )
                alerts.append(alert)
                self._alerts.append(alert)

        return alerts

    def should_rollback(self, model_name: str) -> Tuple[bool, List[DriftAlert]]:
        """Check if critical alerts warrant an automated rollback."""
        critical = [
            a for a in self._alerts
            if a.model_name == model_name
            and a.severity == DriftSeverity.CRITICAL.value
            and not a.resolved
        ]
        return len(critical) > 0, critical

    def get_alerts(
        self, model_name: Optional[str] = None, unresolved_only: bool = True
    ) -> List[DriftAlert]:
        alerts = self._alerts
        if model_name:
            alerts = [a for a in alerts if a.model_name == model_name]
        if unresolved_only:
            alerts = [a for a in alerts if not a.resolved]
        return alerts

    def resolve_alert(self, alert_id: str):
        for a in self._alerts:
            if a.alert_id == alert_id:
                a.resolved = True
                break


# =============================================================================
# Model Registry
# =============================================================================

class ModelRegistry:
    """
    Central registry for all models in the platform.

    MLflow-inspired with versioning, stage transitions, lineage,
    model cards, and drift monitoring integration.
    """

    def __init__(self):
        self._versions: Dict[str, ModelVersion] = {}
        self._by_name: Dict[str, List[str]] = defaultdict(list)
        self._cards: Dict[str, ModelCard] = {}
        self._aliases: Dict[str, str] = {}  # alias → version_id
        self.drift_monitor = DriftMonitor()

    def register_version(self, version: ModelVersion) -> str:
        """Register a new model version."""
        self._versions[version.version_id] = version
        self._by_name[version.model_name].append(version.version_id)
        logger.info(
            f"Registered model: {version.model_name} v{version.version} "
            f"({version.stage})"
        )
        return version.version_id

    def get_version(self, version_id: str) -> Optional[ModelVersion]:
        return self._versions.get(version_id)

    def get_production_version(self, model_name: str) -> Optional[ModelVersion]:
        """Get the current production version of a model."""
        versions = self._by_name.get(model_name, [])
        for vid in reversed(versions):
            v = self._versions[vid]
            if v.stage == ModelStage.PRODUCTION.value:
                return v
        return None

    def promote(
        self, version_id: str, to_stage: ModelStage, promoted_by: str = ""
    ) -> Dict[str, Any]:
        """Promote a model version to a new stage."""
        version = self._versions.get(version_id)
        if not version:
            return {"status": "not_found"}

        # If promoting to production, archive current production
        if to_stage == ModelStage.PRODUCTION:
            current_prod = self.get_production_version(version.model_name)
            if current_prod and current_prod.version_id != version_id:
                current_prod.stage = ModelStage.ARCHIVED.value
                logger.info(f"Archived previous production: {current_prod.version_id}")

        old_stage = version.stage
        version.stage = to_stage.value
        version.promoted_ts = datetime.utcnow().isoformat()
        version.promoted_by = promoted_by

        logger.info(
            f"Promoted {version.model_name} v{version.version}: "
            f"{old_stage} → {to_stage.value}"
        )
        return {"status": "promoted", "version_id": version_id, "stage": to_stage.value}

    def rollback(
        self, model_name: str, reason: str, rolled_back_by: str = ""
    ) -> Dict[str, Any]:
        """
        Rollback: archive current production, promote previous production.
        """
        current = self.get_production_version(model_name)
        if not current:
            return {"status": "no_production_version"}

        # Find previous production (most recent archived)
        versions = self._by_name.get(model_name, [])
        previous = None
        for vid in reversed(versions):
            v = self._versions[vid]
            if v.version_id != current.version_id and v.stage == ModelStage.ARCHIVED.value:
                previous = v
                break

        if not previous:
            return {"status": "no_previous_version"}

        # Archive current
        current.stage = ModelStage.ROLLBACK.value
        current.rollback_reason = reason

        # Restore previous
        previous.stage = ModelStage.PRODUCTION.value
        previous.promoted_ts = datetime.utcnow().isoformat()
        previous.promoted_by = rolled_back_by
        previous.rolled_back_from = current.version_id

        logger.warning(
            f"ROLLBACK: {model_name} from v{current.version} to v{previous.version}. "
            f"Reason: {reason}"
        )
        return {
            "status": "rolled_back",
            "from_version": current.version_id,
            "to_version": previous.version_id,
            "reason": reason,
        }

    def set_alias(self, alias: str, version_id: str):
        """Set a named alias (e.g., 'champion', 'challenger') for a version."""
        self._aliases[alias] = version_id

    def get_by_alias(self, alias: str) -> Optional[ModelVersion]:
        vid = self._aliases.get(alias)
        return self._versions.get(vid) if vid else None

    def register_card(self, card: ModelCard):
        self._cards[card.model_name] = card

    def get_card(self, model_name: str) -> Optional[ModelCard]:
        return self._cards.get(model_name)

    def audit_model_cards(self) -> Dict[str, Any]:
        """Audit all registered models for model card completeness."""
        results = {}
        for model_name in self._by_name:
            card = self._cards.get(model_name)
            if card:
                results[model_name] = {
                    "has_card": True,
                    "completeness": card.completeness_score(),
                }
            else:
                results[model_name] = {"has_card": False, "completeness": 0.0}

        return {
            "total_models": len(self._by_name),
            "models_with_cards": sum(1 for r in results.values() if r["has_card"]),
            "avg_completeness": (
                sum(r["completeness"] for r in results.values()) / len(results)
                if results else 0
            ),
            "details": results,
        }

    def get_all_versions(self, model_name: str) -> List[ModelVersion]:
        return [self._versions[vid] for vid in self._by_name.get(model_name, [])]

    def stats(self) -> Dict[str, Any]:
        stages = defaultdict(int)
        for v in self._versions.values():
            stages[v.stage] += 1

        return {
            "total_versions": len(self._versions),
            "total_models": len(self._by_name),
            "by_stage": dict(stages),
            "model_cards": len(self._cards),
            "active_drift_alerts": len(self.drift_monitor.get_alerts()),
        }

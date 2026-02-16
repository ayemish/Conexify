"""
PDM Domain Exception Hierarchy

Structured exception classes for all service layers.  Every exception carries
machine-readable attributes (error_code, context dict) so callers can map them
to HTTP status codes, Prometheus labels, or event-bus payloads without string
parsing.

Hierarchy:
    PDMError
    ├── ConfigurationError          – invalid or missing config
    ├── ServiceUnavailableError     – external dependency down (DB, Redis, LLM)
    │   ├── DatabaseUnavailableError
    │   ├── RedisUnavailableError
    │   └── LLMServiceError
    ├── BudgetExhaustedError        – FP budget or rate limit exceeded
    ├── ValidationError             – bad input / schema violation
    ├── AssetNotFoundError          – unknown asset_id
    ├── PipelineError               – telemetry pipeline failure
    │   ├── RegimeDetectionError
    │   ├── SensorTrustError
    │   ├── ChangeDetectionError
    │   ├── FaultHypothesisError
    │   └── DecisionPolicyError
    ├── AutopilotError              – orchestration / playbook failure
    │   ├── PlaybookNotFoundError
    │   ├── ApprovalTimeoutError
    │   └── RunExecutionError
    └── ModelLifecycleError         – training / drift / promotion failure
        ├── DriftDetectedError
        └── RetrainingError
"""

from typing import Any, Dict, Optional


class PDMError(Exception):
    """Base exception for all PDM domain errors."""

    error_code: str = "PDM_INTERNAL"
    http_status: int = 500

    def __init__(
        self,
        message: str = "",
        *,
        error_code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        if error_code is not None:
            self.error_code = error_code
        self.context = context or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": str(self),
            "context": self.context,
        }


# ── Configuration ────────────────────────────────────────────────

class ConfigurationError(PDMError):
    error_code = "PDM_CONFIG"
    http_status = 500


# ── External Dependencies ────────────────────────────────────────

class ServiceUnavailableError(PDMError):
    error_code = "PDM_SERVICE_UNAVAILABLE"
    http_status = 503


class DatabaseUnavailableError(ServiceUnavailableError):
    error_code = "PDM_DB_UNAVAILABLE"


class RedisUnavailableError(ServiceUnavailableError):
    error_code = "PDM_REDIS_UNAVAILABLE"


class LLMServiceError(ServiceUnavailableError):
    error_code = "PDM_LLM_UNAVAILABLE"


# ── Budget / Rate Limiting ───────────────────────────────────────

class BudgetExhaustedError(PDMError):
    error_code = "PDM_BUDGET_EXHAUSTED"
    http_status = 429


# ── Validation ───────────────────────────────────────────────────

class PDMValidationError(PDMError):
    error_code = "PDM_VALIDATION"
    http_status = 422


class AssetNotFoundError(PDMError):
    error_code = "PDM_ASSET_NOT_FOUND"
    http_status = 404


# ── Telemetry Pipeline ──────────────────────────────────────────

class PipelineError(PDMError):
    error_code = "PDM_PIPELINE"
    http_status = 500


class RegimeDetectionError(PipelineError):
    error_code = "PDM_REGIME_DETECTION"


class SensorTrustError(PipelineError):
    error_code = "PDM_SENSOR_TRUST"


class ChangeDetectionError(PipelineError):
    error_code = "PDM_CHANGE_DETECTION"


class FaultHypothesisError(PipelineError):
    error_code = "PDM_FAULT_HYPOTHESIS"


class DecisionPolicyError(PipelineError):
    error_code = "PDM_DECISION_POLICY"


# ── Autopilot ───────────────────────────────────────────────────

class AutopilotError(PDMError):
    error_code = "PDM_AUTOPILOT"
    http_status = 500


class PlaybookNotFoundError(AutopilotError):
    error_code = "PDM_PLAYBOOK_NOT_FOUND"
    http_status = 404


class ApprovalTimeoutError(AutopilotError):
    error_code = "PDM_APPROVAL_TIMEOUT"
    http_status = 408


class RunExecutionError(AutopilotError):
    error_code = "PDM_RUN_EXECUTION"


# ── Model Lifecycle ─────────────────────────────────────────────

class ModelLifecycleError(PDMError):
    error_code = "PDM_MODEL_LIFECYCLE"
    http_status = 500


class DriftDetectedError(ModelLifecycleError):
    error_code = "PDM_DRIFT_DETECTED"


class RetrainingError(ModelLifecycleError):
    error_code = "PDM_RETRAINING"

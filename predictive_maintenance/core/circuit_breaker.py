"""
Circuit Breaker Pattern for External Dependencies

Prevents cascading failures when Redis, PostgreSQL, or LLM APIs are
unavailable.  Three states:

    CLOSED   →  requests flow normally; failures increment counter
    OPEN     →  requests fail-fast with ServiceUnavailableError
    HALF_OPEN→  one probe request allowed; success → CLOSED, fail → OPEN

Thread-safe via threading.Lock.
"""

import logging
import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional, TypeVar, Generic

from .exceptions import ServiceUnavailableError

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_timeout_seconds: float = 30.0
    half_open_max_calls: int = 1
    success_threshold: int = 2


class CircuitBreaker:
    """
    Generic circuit breaker wrapping any callable.

    Usage::

        cb = CircuitBreaker("redis", config=CircuitBreakerConfig(failure_threshold=3))
        result = cb.call(redis_client.ping)
    """

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0.0
        self._half_open_calls = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.time() - self._last_failure_time >= self.config.recovery_timeout_seconds:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    self._success_count = 0
                    logger.info("Circuit '%s' → HALF_OPEN (recovery probe)", self.name)
            return self._state

    def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute *func* through the circuit breaker."""
        current = self.state

        if current == CircuitState.OPEN:
            raise ServiceUnavailableError(
                f"Circuit '{self.name}' is OPEN – dependency unavailable",
                error_code=f"PDM_CIRCUIT_{self.name.upper()}_OPEN",
                context={"circuit": self.name, "state": "open"},
            )

        if current == CircuitState.HALF_OPEN:
            with self._lock:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    raise ServiceUnavailableError(
                        f"Circuit '{self.name}' HALF_OPEN probe limit reached",
                        error_code=f"PDM_CIRCUIT_{self.name.upper()}_PROBE",
                        context={"circuit": self.name, "state": "half_open"},
                    )
                self._half_open_calls += 1

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except ServiceUnavailableError:
            self._on_failure()
            raise
        except Exception as exc:
            self._on_failure()
            raise ServiceUnavailableError(
                f"Circuit '{self.name}' caught error: {exc}",
                error_code=f"PDM_CIRCUIT_{self.name.upper()}",
                context={"circuit": self.name, "original_error": str(exc)},
            ) from exc

    async def call_async(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """Async variant of :meth:`call`."""
        current = self.state

        if current == CircuitState.OPEN:
            raise ServiceUnavailableError(
                f"Circuit '{self.name}' is OPEN",
                error_code=f"PDM_CIRCUIT_{self.name.upper()}_OPEN",
                context={"circuit": self.name, "state": "open"},
            )

        if current == CircuitState.HALF_OPEN:
            with self._lock:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    raise ServiceUnavailableError(
                        f"Circuit '{self.name}' HALF_OPEN probe limit",
                        error_code=f"PDM_CIRCUIT_{self.name.upper()}_PROBE",
                        context={"circuit": self.name, "state": "half_open"},
                    )
                self._half_open_calls += 1

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except ServiceUnavailableError:
            self._on_failure()
            raise
        except Exception as exc:
            self._on_failure()
            raise ServiceUnavailableError(
                f"Circuit '{self.name}' caught error: {exc}",
                error_code=f"PDM_CIRCUIT_{self.name.upper()}",
                context={"circuit": self.name, "original_error": str(exc)},
            ) from exc

    # ── Internal ─────────────────────────────────────────────────

    def _on_success(self):
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    logger.info("Circuit '%s' → CLOSED (recovered)", self.name)
            else:
                self._failure_count = 0

    def _on_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning("Circuit '%s' → OPEN (probe failed)", self.name)
            elif self._failure_count >= self.config.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit '%s' → OPEN (failures=%d >= threshold=%d)",
                    self.name, self._failure_count, self.config.failure_threshold,
                )

    def reset(self):
        """Manually reset to CLOSED."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "last_failure": self._last_failure_time,
        }


# ── Pre-built breakers for standard dependencies ────────────────

_breakers: Dict[str, CircuitBreaker] = {}
_breakers_lock = threading.Lock()


def get_breaker(name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
    """Get or create a named circuit breaker (thread-safe singleton)."""
    with _breakers_lock:
        if name not in _breakers:
            _breakers[name] = CircuitBreaker(name, config)
        return _breakers[name]


def get_all_breakers() -> Dict[str, Dict[str, Any]]:
    """Return status of all breakers (for health endpoints)."""
    with _breakers_lock:
        return {name: cb.to_dict() for name, cb in _breakers.items()}


# Convenience accessors
db_breaker = lambda: get_breaker("database", CircuitBreakerConfig(failure_threshold=3, recovery_timeout_seconds=15))
redis_breaker = lambda: get_breaker("redis", CircuitBreakerConfig(failure_threshold=5, recovery_timeout_seconds=10))
llm_breaker = lambda: get_breaker("llm", CircuitBreakerConfig(failure_threshold=3, recovery_timeout_seconds=60))

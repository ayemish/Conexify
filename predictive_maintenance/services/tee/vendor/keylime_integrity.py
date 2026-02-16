
"""Keylime TPM-based integrity verification integration (FR-5.x).

Includes circuit breaker pattern to prevent cascading failures when
Keylime is unavailable.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import httpx
try:
    import structlog  # type: ignore
except Exception:  # pragma: no cover
    structlog = None  # type: ignore

from ....config import settings

if structlog is not None:
    logger = structlog.get_logger()
else:
    import logging

    logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation, requests pass through
    OPEN = "open"          # Circuit is open, requests fail fast
    HALF_OPEN = "half_open"  # Testing if service has recovered


@dataclass
class CircuitBreaker:
    """
    Circuit breaker pattern implementation for external service calls.
    
    Prevents cascading failures by failing fast when a service is unhealthy,
    and automatically recovers when the service becomes available again.
    """
    failure_threshold: int = 5
    recovery_timeout_seconds: int = 30
    half_open_max_calls: int = 3
    
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _success_count: int = field(default=0, init=False)
    _last_failure_time: Optional[datetime] = field(default=None, init=False)
    _half_open_calls: int = field(default=0, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def is_closed(self) -> bool:
        return self._state == CircuitState.CLOSED

    async def can_execute(self) -> bool:
        """Check if a request can be executed."""
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            
            if self._state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                if self._last_failure_time:
                    elapsed = (datetime.now(timezone.utc) - self._last_failure_time).total_seconds()
                    if elapsed >= self.recovery_timeout_seconds:
                        self._state = CircuitState.HALF_OPEN
                        self._half_open_calls = 0
                        logger.info("Circuit breaker entering half-open state")
                        return True
                return False
            
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False
            
            return False

    async def record_success(self):
        """Record a successful call."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.half_open_max_calls:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    logger.info("Circuit breaker closed after recovery")
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success
                self._failure_count = max(0, self._failure_count - 1)

    async def record_failure(self):
        """Record a failed call."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = datetime.now(timezone.utc)
            
            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open state opens the circuit
                self._state = CircuitState.OPEN
                self._success_count = 0
                logger.warning("Circuit breaker opened after half-open failure")
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitState.OPEN
                    logger.warning(
                        "Circuit breaker opened",
                        failure_count=self._failure_count,
                        threshold=self.failure_threshold,
                    )

    def get_status(self) -> dict:
        """Get current circuit breaker status."""
        return {
            "state": self._state.value,
            "failure_count": self._failure_count,
            "last_failure": self._last_failure_time.isoformat() if self._last_failure_time else None,
        }


class KeylimeClient:
    """
    Client for Keylime verifier service integration.
    
    Includes circuit breaker pattern to prevent cascading failures
    when Keylime is unavailable.
    """

    def __init__(
        self,
        verifier_url: Optional[str] = None,
        enabled: Optional[bool] = None,
        fail_closed: Optional[bool] = None,
    ):
        self.verifier_url = verifier_url or settings.tee.keylime_verifier_url
        self.enabled = enabled if enabled is not None else settings.tee.keylime_enabled
        self.fail_closed = (
            fail_closed if fail_closed is not None else settings.tee.keylime_fail_closed
        )
        self.required_ima_policy_hashes = self._parse_required_ima_hashes(
            settings.tee.keylime_required_ima_policy_hashes
        )
        self._client = httpx.AsyncClient(timeout=30.0)
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout_seconds=30,
            half_open_max_calls=3,
        )

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()

    def get_circuit_status(self) -> dict:
        """Get circuit breaker status for monitoring."""
        return self._circuit_breaker.get_status()

    async def is_healthy(self) -> bool:
        """Check if the Keylime verifier is reachable."""
        if not self.enabled:
            return True

        # Check circuit breaker first
        if not await self._circuit_breaker.can_execute():
            logger.warning("Keylime health check skipped - circuit breaker open")
            return False

        try:
            response = await self._client.get(f"{self.verifier_url}/version")
            if response.status_code == 200:
                await self._circuit_breaker.record_success()
                return True
            else:
                await self._circuit_breaker.record_failure()
                return False
        except Exception as e:
            await self._circuit_breaker.record_failure()
            logger.error("Keylime health check failed", error=str(e))
            return False

    async def detect_tpm(self) -> dict:
        """
        Detect TPM presence and capability (FR-5.1).
        
        Returns information about TPM availability on the current node.
        """
        if not self.enabled:
            return {
                "available": False,
                "reason": "Keylime integration disabled",
            }

        # Check circuit breaker
        if not await self._circuit_breaker.can_execute():
            return {
                "available": False,
                "reason": "Circuit breaker open - Keylime service unavailable",
                "circuit_status": self._circuit_breaker.get_status(),
            }

        try:
            response = await self._client.get(
                f"{self.verifier_url}/v2.1/agents",
            )

            if response.status_code == 200:
                await self._circuit_breaker.record_success()
                agents = response.json().get("results", {})
                return {
                    "available": True,
                    "agent_count": len(agents),
                    "agents": list(agents.keys()),
                }
            else:
                await self._circuit_breaker.record_failure()
                return {
                    "available": False,
                    "reason": f"Verifier returned status {response.status_code}",
                }
        except Exception as e:
            await self._circuit_breaker.record_failure()
            logger.error("TPM detection failed", error=str(e))
            return {
                "available": False,
                "reason": str(e),
            }

    async def verify_agent_integrity(self, agent_id: str) -> tuple[bool, dict]:
        """
        Verify integrity of a specific agent using TPM quote (FR-5.2, FR-5.3).
        
        Returns: (is_verified, details)
        """
        if not self.enabled:
            return True, {"skipped": True, "reason": "Keylime disabled"}

        # Check circuit breaker
        if not await self._circuit_breaker.can_execute():
            logger.warning(
                "Skipping agent integrity check - circuit breaker open",
                agent_id=agent_id,
            )
            if self.fail_closed:
                return False, {
                    "error": "Circuit breaker open",
                    "circuit_status": self._circuit_breaker.get_status(),
                }
            return True, {
                "skipped": True,
                "reason": "Circuit breaker open",
                "circuit_status": self._circuit_breaker.get_status(),
            }

        try:
            response = await self._client.get(
                f"{self.verifier_url}/v2.1/agents/{agent_id}"
            )

            if response.status_code != 200:
                await self._circuit_breaker.record_failure()
                if self.fail_closed:
                    return False, {
                        "error": f"Agent not found: {response.status_code}"
                    }
                return True, {"warning": "Agent not found, but fail_closed=False"}

            agent_data = response.json().get("results", {})

            operational_state = agent_data.get("operational_state", "")

            verified_states = ["Get Quote", "Provide V", "Tenant Quote"]

            if any(state in operational_state for state in verified_states):
                ima_hash = self._compute_ima_policy_hash(agent_data)
                if self.required_ima_policy_hashes:
                    if not ima_hash or ima_hash not in self.required_ima_policy_hashes:
                        if self.fail_closed:
                            return False, {
                                "operational_state": operational_state,
                                "error": "IMA policy hash not allowed",
                                "ima_policy_hash": ima_hash,
                            }
                        return True, {
                            "warning": "IMA policy hash not allowed",
                            "ima_policy_hash": ima_hash,
                        }
                return True, {
                    "operational_state": operational_state,
                    "last_received_quote": agent_data.get("last_received_quote"),
                    "quote_hash": self._compute_quote_hash(agent_data),
                    "ima_policy_hash": ima_hash,
                }
            else:
                if self.fail_closed:
                    return False, {
                        "operational_state": operational_state,
                        "error": "Agent not in verified state",
                    }
                return True, {
                    "warning": f"Agent state: {operational_state}",
                }

        except Exception as e:
            logger.error("Integrity verification failed", agent_id=agent_id, error=str(e))
            if self.fail_closed:
                return False, {"error": str(e)}
            return True, {"warning": str(e)}

    async def verify_current_node(self) -> tuple[bool, dict]:
        """
        Verify integrity of the current node where release gate is running.
        
        This is used to gate high-risk actions (FR-5.4).
        """
        if not self.enabled:
            return True, {"skipped": True, "reason": "Keylime disabled"}

        tpm_info = await self.detect_tpm()

        if not tpm_info.get("available"):
            if self.fail_closed:
                return False, {"error": "TPM not available", "details": tpm_info}
            return True, {"warning": "TPM not available"}

        agents = tpm_info.get("agents", [])
        if not agents:
            if self.fail_closed:
                return False, {"error": "No registered agents"}
            return True, {"warning": "No registered agents"}

        all_verified = True
        results = {}

        for agent_id in agents:
            verified, details = await self.verify_agent_integrity(agent_id)
            results[agent_id] = details
            if not verified:
                all_verified = False

        return all_verified, {"agent_results": results}

    def _compute_quote_hash(self, agent_data: dict) -> Optional[str]:
        """Extract or compute a hash representing the TPM quote."""
        import hashlib
        import json

        quote_data = {
            "pcr_values": agent_data.get("tpm_policy", {}),
            "ima_policy": agent_data.get("ima_policy", {}),
        }
        quote_str = json.dumps(quote_data, sort_keys=True)
        return hashlib.sha256(quote_str.encode()).hexdigest()

    def _compute_ima_policy_hash(self, agent_data: dict) -> Optional[str]:
        """Compute a hash representing the IMA policy."""
        import hashlib
        import json

        ima_policy = agent_data.get("ima_policy")
        if ima_policy is None:
            return None
        try:
            policy_str = json.dumps(ima_policy, sort_keys=True)
        except TypeError:
            policy_str = str(ima_policy)
        return hashlib.sha256(policy_str.encode()).hexdigest()

    def _parse_required_ima_hashes(self, value: str) -> list[str]:
        """Parse a comma-separated list of required IMA policy hashes."""
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    async def should_allow_release(self) -> tuple[bool, Optional[str]]:
        """
        Determine if releases should be allowed based on integrity status.
        
        FR-5.4: Gate high-risk actions on Keylime verifier approval.
        """
        if not self.enabled:
            return True, None

        verified, details = await self.verify_current_node()

        if not verified:
            return False, f"Integrity verification failed: {details}"

        if details.get("warning"):
            logger.warning("Integrity warning", details=details)

        return True, details.get("agent_results", {}).get(
            list(details.get("agent_results", {}).keys())[0] if details.get("agent_results") else None,
            {}
        ).get("quote_hash")

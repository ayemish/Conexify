"""Enclave runtime abstraction for TEE jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, Optional

from ...config import settings
from .attestation import KeylimeAttestor
from .key_manager import KeyManager
from .egress_policy import EgressPolicy


@dataclass
class EnclaveRuntime:
    """Represents enclave runtime configuration and IO helpers."""

    runtime_class: str = settings.tee.enclave_runtime
    attestor: Optional[KeylimeAttestor] = None
    key_manager: Optional[KeyManager] = None
    egress_policy: Optional[EgressPolicy] = None

    def __post_init__(self):
        if self.attestor is None:
            self.attestor = KeylimeAttestor()
        if self.key_manager is None:
            self.key_manager = KeyManager()
        if self.egress_policy is None:
            self.egress_policy = EgressPolicy()

    def verify_runtime(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """Verify enclave runtime and (optionally) Keylime attestation."""
        result = {
            "runtime_class": self.runtime_class,
            "attestation": None,
            "egress_allowlist": self.egress_policy.allowlist,
        }
        if settings.tee.keylime_enabled and settings.tee.keylime_fail_closed and not agent_id:
            raise PermissionError("TEE attestation requires agent_id when fail-closed is enabled")
        if agent_id:
            ok, details = self.attestor.verify_agent(agent_id)
            result["attestation"] = {"verified": ok, "details": details}
            if settings.tee.keylime_enabled and settings.tee.keylime_fail_closed and not ok:
                raise PermissionError(f"TEE attestation failed for agent {agent_id}: {details}")
        return result

    def encrypt_payload(self, payload: bytes) -> bytes:
        return self.key_manager.encrypt(payload)

    def decrypt_payload(self, payload: bytes) -> bytes:
        return self.key_manager.decrypt(payload)

    def require_egress(self, url: str):
        self.egress_policy.require_allowed(url)

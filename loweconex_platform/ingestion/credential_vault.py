"""
Credential Vault — abstraction for secure credential storage.

Supports:
- In-memory vault (dev/testing)
- Environment variable backend
- Interface for HashiCorp Vault / AWS Secrets Manager / Azure Key Vault

Credentials are never logged or serialized in plain text.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CredentialEntry:
    """A stored credential with metadata."""
    credential_id: str
    connector_name: str
    credential_type: str = "api_key"  # api_key, bearer_token, basic_auth, connection_string
    created_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    rotated_ts: Optional[str] = None
    expires_ts: Optional[str] = None
    metadata: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "credential_id": self.credential_id,
            "connector_name": self.connector_name,
            "credential_type": self.credential_type,
            "created_ts": self.created_ts,
            "rotated_ts": self.rotated_ts,
            "expires_ts": self.expires_ts,
        }


class VaultBackend(ABC):
    """Abstract interface for credential storage backends."""

    @abstractmethod
    def store(self, key: str, value: str, metadata: Optional[Dict[str, str]] = None) -> bool:
        pass

    @abstractmethod
    def retrieve(self, key: str) -> Optional[str]:
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        pass

    @abstractmethod
    def list_keys(self) -> List[str]:
        pass


class InMemoryVault(VaultBackend):
    """In-memory vault for development and testing."""

    def __init__(self):
        self._store: Dict[str, str] = {}

    def store(self, key: str, value: str, metadata: Optional[Dict[str, str]] = None) -> bool:
        self._store[key] = value
        return True

    def retrieve(self, key: str) -> Optional[str]:
        return self._store.get(key)

    def delete(self, key: str) -> bool:
        return self._store.pop(key, None) is not None

    def list_keys(self) -> List[str]:
        return list(self._store.keys())


class EnvVarVault(VaultBackend):
    """Environment variable-based vault. Keys are mapped to env var names."""

    PREFIX = "LOWECONEX_CRED_"

    def store(self, key: str, value: str, metadata: Optional[Dict[str, str]] = None) -> bool:
        env_key = f"{self.PREFIX}{key.upper().replace('-', '_')}"
        os.environ[env_key] = value
        return True

    def retrieve(self, key: str) -> Optional[str]:
        env_key = f"{self.PREFIX}{key.upper().replace('-', '_')}"
        return os.environ.get(env_key)

    def delete(self, key: str) -> bool:
        env_key = f"{self.PREFIX}{key.upper().replace('-', '_')}"
        if env_key in os.environ:
            del os.environ[env_key]
            return True
        return False

    def list_keys(self) -> List[str]:
        return [
            k.replace(self.PREFIX, "").lower().replace("_", "-")
            for k in os.environ
            if k.startswith(self.PREFIX)
        ]


class CredentialVault:
    """
    High-level credential manager.
    
    Wraps a VaultBackend with audit logging, rotation tracking,
    and expiry monitoring. Never exposes credentials in logs or serialization.
    """

    def __init__(self, backend: Optional[VaultBackend] = None):
        self._backend = backend or InMemoryVault()
        self._entries: Dict[str, CredentialEntry] = {}
        self._access_log: List[Dict[str, Any]] = []

    def store_credential(
        self,
        credential_id: str,
        connector_name: str,
        value: str,
        credential_type: str = "api_key",
        expires_ts: Optional[str] = None,
    ) -> CredentialEntry:
        """Store a credential securely."""
        self._backend.store(credential_id, value)
        entry = CredentialEntry(
            credential_id=credential_id,
            connector_name=connector_name,
            credential_type=credential_type,
            expires_ts=expires_ts,
        )
        self._entries[credential_id] = entry
        self._log_access(credential_id, "store", connector_name)
        logger.info(f"Credential stored: {credential_id} (type={credential_type})")
        return entry

    def retrieve_credential(self, credential_id: str) -> Optional[str]:
        """Retrieve a credential value. Returns None if not found."""
        value = self._backend.retrieve(credential_id)
        self._log_access(credential_id, "retrieve")
        return value

    def rotate_credential(
        self, credential_id: str, new_value: str
    ) -> bool:
        """Rotate (replace) a credential with a new value."""
        entry = self._entries.get(credential_id)
        if not entry:
            return False
        self._backend.store(credential_id, new_value)
        entry.rotated_ts = datetime.utcnow().isoformat()
        self._log_access(credential_id, "rotate")
        logger.info(f"Credential rotated: {credential_id}")
        return True

    def delete_credential(self, credential_id: str) -> bool:
        """Delete a credential."""
        self._backend.delete(credential_id)
        self._entries.pop(credential_id, None)
        self._log_access(credential_id, "delete")
        return True

    def get_credentials_for_connector(self, connector_name: str) -> Dict[str, str]:
        """Get all credentials for a connector as a dict (key -> value)."""
        result = {}
        for cred_id, entry in self._entries.items():
            if entry.connector_name == connector_name:
                value = self._backend.retrieve(cred_id)
                if value is not None:
                    result[cred_id] = value
        return result

    def get_expired_credentials(self) -> List[CredentialEntry]:
        """Get credentials past their expiry date."""
        now = datetime.utcnow().isoformat()
        expired = []
        for entry in self._entries.values():
            if entry.expires_ts and entry.expires_ts < now:
                expired.append(entry)
        return expired

    def list_entries(self) -> List[CredentialEntry]:
        return list(self._entries.values())

    def _log_access(self, credential_id: str, action: str, connector_name: str = ""):
        self._access_log.append({
            "credential_id": credential_id,
            "action": action,
            "connector_name": connector_name,
            "ts": datetime.utcnow().isoformat(),
        })

    def stats(self) -> Dict[str, Any]:
        return {
            "credentials_stored": len(self._entries),
            "access_log_entries": len(self._access_log),
            "expired": len(self.get_expired_credentials()),
        }

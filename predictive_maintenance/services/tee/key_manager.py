"""Key management and encryption utilities for TEE layer."""

from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass
from typing import Optional

from ...config import settings

logger = logging.getLogger(__name__)

try:
    from cryptography.fernet import Fernet  # type: ignore
except Exception:  # pragma: no cover
    Fernet = None  # type: ignore


@dataclass
class KeyManager:
    """Manages encryption keys for enclave I/O."""

    key: Optional[bytes] = None

    def __post_init__(self):
        if self.key is None:
            env_key = settings.tee.encryption_key
            if env_key:
                try:
                    self.key = base64.urlsafe_b64decode(env_key)
                except Exception:
                    self.key = env_key.encode("utf-8")
            else:
                self.key = self._generate_key()

    def _generate_key(self) -> bytes:
        if Fernet is not None:
            return Fernet.generate_key()
        # Fallback: derive a weak key for local testing
        logger.warning("cryptography not available; using weak local key")
        raw = os.urandom(32)
        return base64.urlsafe_b64encode(raw)

    def encrypt(self, payload: bytes) -> bytes:
        if Fernet is None:
            # Weak fallback: XOR with key for local testing
            key = self.key or b""
            if not key:
                return payload
            return bytes([b ^ key[i % len(key)] for i, b in enumerate(payload)])
        return Fernet(self.key).encrypt(payload)

    def decrypt(self, token: bytes) -> bytes:
        if Fernet is None:
            key = self.key or b""
            if not key:
                return token
            return bytes([b ^ key[i % len(key)] for i, b in enumerate(token)])
        return Fernet(self.key).decrypt(token)

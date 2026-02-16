"""Strict egress policy enforcement for TEE outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional
from urllib.parse import urlparse

from ...config import settings


@dataclass
class EgressPolicy:
    """Enforces that outputs only go to approved endpoints."""

    allowlist: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.allowlist:
            self.allowlist = settings.tee.egress_allowlist or [settings.tee.release_gate_url]

    def is_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        for allowed in self.allowlist:
            if host in allowed or allowed in url:
                return True
        return False

    def require_allowed(self, url: str):
        if not self.is_allowed(url):
            raise PermissionError(f"Egress denied for URL: {url}")

    def validate_aggregate_type(self, aggregate_type: str, allowed: Optional[Iterable[str]] = None):
        allowed_types = set(allowed or ["count", "sum", "mean", "variance", "histogram", "quantile"])
        if aggregate_type not in allowed_types:
            raise ValueError(f"Aggregate type '{aggregate_type}' not permitted by egress policy")

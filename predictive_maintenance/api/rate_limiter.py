"""
Token-Bucket Rate Limiter Middleware

Enforces the rate limits configured in ``APISettings.rate_limit_requests``
and ``APISettings.rate_limit_window_seconds``.  Uses an in-memory token
bucket per client IP (or API key when present).

Adds ``X-RateLimit-Limit``, ``X-RateLimit-Remaining``, and
``X-RateLimit-Reset`` response headers.
"""

import logging
import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# ── Redis availability ──────────────────────────────────────────────
_redis_client: Optional[Any] = None

def _get_redis():
    """Lazily connect to Redis for distributed rate limiting."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        from predictive_maintenance.config import settings
        import redis
        _redis_client = redis.from_url(settings.redis.url, decode_responses=True)
        _redis_client.ping()
        logger.info("Redis rate limiter backend connected")
        return _redis_client
    except Exception:
        _redis_client = False  # sentinel: don't retry
        return None


@dataclass
class _Bucket:
    tokens: float
    last_refill: float
    capacity: int
    refill_rate: float  # tokens per second

    def consume(self) -> Tuple[bool, int, float]:
        """Try to consume one token. Returns (allowed, remaining, reset_seconds)."""
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        if self.tokens >= 1:
            self.tokens -= 1
            remaining = int(self.tokens)
            return True, remaining, 0.0
        else:
            wait = (1 - self.tokens) / self.refill_rate
            return False, 0, wait


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """
    Per-client token-bucket rate limiter.

    Reads config from ``PDMSettings`` at construction time so env-var
    changes require a restart.
    """

    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.refill_rate = max_requests / window_seconds
        self._buckets: Dict[str, _Bucket] = {}
        self._lock = threading.Lock()
        self._use_redis: Optional[bool] = None  # lazy detect

    def _get_bucket(self, key: str) -> _Bucket:
        with self._lock:
            if key not in self._buckets:
                self._buckets[key] = _Bucket(
                    tokens=float(self.max_requests),
                    last_refill=time.time(),
                    capacity=self.max_requests,
                    refill_rate=self.refill_rate,
                )
            return self._buckets[key]

    def _client_key(self, request: Request) -> str:
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return f"key:{api_key}"
        client = request.client
        return f"ip:{client.host}" if client else "ip:unknown"

    def _try_redis(self, key: str) -> Optional[Tuple[bool, int, float]]:
        """Attempt Redis-backed sliding window rate limit.

        Uses INCR + EXPIRE for a fixed-window counter per key.
        Returns (allowed, remaining, retry_after) or None if Redis unavailable.
        """
        if self._use_redis is False:
            return None
        r = _get_redis()
        if not r:
            self._use_redis = False
            return None
        self._use_redis = True
        try:
            redis_key = f"pdm_rl:{key}"
            count = r.incr(redis_key)
            if count == 1:
                r.expire(redis_key, self.window_seconds)
            ttl = r.ttl(redis_key)
            if ttl < 0:
                ttl = self.window_seconds

            if count > self.max_requests:
                return False, 0, float(ttl)
            return True, self.max_requests - count, 0.0
        except Exception as e:
            logger.debug("Redis rate limit failed, falling back to in-memory: %s", e)
            self._use_redis = False
            return None

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health/readiness probes
        if request.url.path in ("/health", "/live", "/ready"):
            return await call_next(request)

        key = self._client_key(request)

        # Try Redis first (distributed), fall back to in-memory
        redis_result = self._try_redis(key)
        if redis_result is not None:
            allowed, remaining, retry_after = redis_result
        else:
            bucket = self._get_bucket(key)
            allowed, remaining, retry_after = bucket.consume()

        if not allowed:
            logger.warning("Rate limit exceeded for %s", key)
            return JSONResponse(
                status_code=429,
                content={
                    "error_code": "PDM_RATE_LIMIT",
                    "message": "Rate limit exceeded",
                    "context": {"retry_after_seconds": round(retry_after, 1)},
                },
                headers={
                    "Retry-After": str(int(retry_after) + 1),
                    "X-RateLimit-Limit": str(self.max_requests),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response: Response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

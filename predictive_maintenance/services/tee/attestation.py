"""Attestation wrapper integrating vendored Keylime client."""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Tuple, Dict, Any, Callable

from .vendor.keylime_integrity import KeylimeClient

logger = logging.getLogger(__name__)


class KeylimeAttestor:
    """Wrapper around vendored KeylimeClient with sync helpers."""

    def __init__(
        self,
        verifier_url: Optional[str] = None,
        enabled: Optional[bool] = None,
        fail_closed: Optional[bool] = None,
    ):
        self._client = KeylimeClient(
            verifier_url=verifier_url,
            enabled=enabled,
            fail_closed=fail_closed,
        )
        self._executor = ThreadPoolExecutor(max_workers=2)

    def _run(self, coro_factory: Callable[[], asyncio.Future] | asyncio.Future):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            coro = coro_factory() if callable(coro_factory) else coro_factory
            return asyncio.run(coro)
        if loop.is_running():
            def runner():
                inner_coro = coro_factory() if callable(coro_factory) else coro_factory
                return asyncio.run(inner_coro)

            future = self._executor.submit(runner)
            return future.result()
        coro = coro_factory() if callable(coro_factory) else coro_factory
        return loop.run_until_complete(coro)

    async def verify_agent_async(self, agent_id: str) -> Tuple[bool, Dict[str, Any]]:
        return await self._client.verify_agent_integrity(agent_id)

    async def health_async(self) -> bool:
        return await self._client.is_healthy()

    def verify_agent(self, agent_id: str) -> Tuple[bool, Dict[str, Any]]:
        try:
            return self._run(lambda: self.verify_agent_async(agent_id))
        except Exception as exc:
            logger.error("Keylime attestation failed", exc_info=exc)
            raise

    def health_check(self) -> bool:
        try:
            return self._run(self.health_async)
        except Exception as exc:
            logger.error("Keylime health check failed", exc_info=exc)
            raise

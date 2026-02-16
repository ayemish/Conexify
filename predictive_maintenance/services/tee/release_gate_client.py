"""Client for VCDA Release Gate API (TEE-controlled egress), using vendored TEE code."""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from ...config import settings
from .egress_policy import EgressPolicy
from .vendor.release_client import VCDAReleaseClient

logger = logging.getLogger(__name__)


@dataclass
class ReleaseReceipt:
    receipt_id: str
    released_value: Any
    epsilon_consumed: float
    delta_consumed: float
    remaining_epsilon: float
    remaining_delta: float
    mechanism: str
    zk_proof_id: Optional[str] = None


class ReleaseGateClient:
    """Synchronous wrapper around the vendored async VCDAReleaseClient."""

    def __init__(self, base_url: Optional[str] = None, policy: Optional[EgressPolicy] = None):
        self.base_url = base_url or settings.tee.release_gate_url
        self.policy = policy or EgressPolicy()
        self._executor = ThreadPoolExecutor(max_workers=2)

    def _run(self, coro_factory: Callable[[], asyncio.Future] | asyncio.Future):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            coro = coro_factory() if callable(coro_factory) else coro_factory
            return asyncio.run(coro)
        if loop.is_running():
            # Run in a dedicated thread to avoid nested event loop issues.
            def runner():
                inner_coro = coro_factory() if callable(coro_factory) else coro_factory
                return asyncio.run(inner_coro)

            future = self._executor.submit(runner)
            return future.result()
        coro = coro_factory() if callable(coro_factory) else coro_factory
        return loop.run_until_complete(coro)

    def release_metric(
        self,
        job_id: str,
        dataset_id: str,
        metric_name: str,
        aggregate_type: str,
        raw_value: Any,
        epsilon: float = 1.0,
        delta: float = 1e-6,
        contribution_bounds: Optional[Dict[str, Any]] = None,
        population_filter: Optional[str] = None,
        request_zk_proof: bool = False,
        time_window_start: Optional[datetime] = None,
        time_window_end: Optional[datetime] = None,
    ) -> ReleaseReceipt:
        self.policy.require_allowed(self.base_url)
        self.policy.validate_aggregate_type(aggregate_type)

        if not settings.tee.enabled:
            return self._mock_release(job_id, aggregate_type, raw_value, epsilon, delta)

        async def _do_release():
            client = VCDAReleaseClient(base_url=self.base_url)
            # Override env-derived policy/binding with configured settings
            if settings.tee.release_policy_name:
                client.release_policy_name = settings.tee.release_policy_name
                client.release_policy_namespace = settings.tee.release_policy_namespace
            if settings.tee.dataset_binding_name:
                client.dataset_binding_name = settings.tee.dataset_binding_name
                client.dataset_binding_namespace = settings.tee.dataset_binding_namespace
            try:
                return await client._release(
                    job_id=job_id,
                    dataset_id=dataset_id,
                    aggregate_type=aggregate_type,
                    raw_value=raw_value,
                    epsilon=epsilon,
                    delta=delta,
                    mechanism="laplace" if aggregate_type != "histogram" else "thresholded_laplace",
                    contribution_bounds=contribution_bounds,
                    population_filter=population_filter,
                    query_template_id=metric_name,
                    request_zk_proof=request_zk_proof,
                )
            finally:
                await client.close()

        try:
            receipt = self._run(_do_release)
        except Exception as exc:
            logger.error("TEE release gate failed", exc_info=exc)
            # Fail-closed when TEE is enabled.
            raise RuntimeError("TEE release gate failed") from exc
        return ReleaseReceipt(
            receipt_id=receipt.receipt_id,
            released_value=receipt.released_value,
            epsilon_consumed=receipt.epsilon_consumed,
            delta_consumed=receipt.delta_consumed,
            remaining_epsilon=receipt.remaining_epsilon,
            remaining_delta=receipt.remaining_delta,
            mechanism=receipt.mechanism,
            zk_proof_id=receipt.zk_proof_id,
        )

    def _mock_release(
        self,
        job_id: str,
        aggregate_type: str,
        raw_value: Any,
        epsilon: float,
        delta: float,
    ) -> ReleaseReceipt:
        from random import gauss

        if isinstance(raw_value, (int, float)):
            scale = 1.0 / max(epsilon, 1e-6)
            noisy = raw_value + gauss(0, scale)
        else:
            noisy = raw_value
        return ReleaseReceipt(
            receipt_id=f"mock-{job_id}",
            released_value=noisy,
            epsilon_consumed=epsilon,
            delta_consumed=delta,
            remaining_epsilon=max(0.0, 10.0 - epsilon),
            remaining_delta=max(0.0, 1e-5 - delta),
            mechanism="laplace" if aggregate_type != "histogram" else "thresholded_laplace",
            zk_proof_id=None,
        )

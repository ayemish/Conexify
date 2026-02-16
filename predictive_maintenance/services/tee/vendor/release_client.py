
"""
Example Python client for the VCDA Release Gate.

This client demonstrates how analytics jobs submit results through
the DP release gate and receive privacy-protected outputs.
"""

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import httpx


@dataclass
class ReleaseReceipt:
    """Receipt from a DP release."""
    receipt_id: str
    released_value: Any
    epsilon_consumed: float
    delta_consumed: float
    remaining_epsilon: float
    remaining_delta: float
    mechanism: str
    zk_proof_id: Optional[str] = None


class VCDAReleaseClient:
    """Client for VCDA Release Gate API."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or os.getenv(
            "RELEASE_GATE_URL", "http://vcda-release-gate:8080"
        )
        self.release_policy_name = os.getenv("RELEASE_POLICY_NAME")
        self.release_policy_namespace = os.getenv("RELEASE_POLICY_NAMESPACE")
        self.dataset_binding_name = os.getenv("DATASET_BINDING_NAME")
        self.dataset_binding_namespace = os.getenv("DATASET_BINDING_NAMESPACE")
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def release_count(
        self,
        job_id: str,
        dataset_id: str,
        count: int,
        epsilon: float = 1.0,
        delta: float = 1e-6,
        population_filter: Optional[str] = None,
        request_zk_proof: bool = False,
    ) -> ReleaseReceipt:
        """Release a count aggregate with DP protection."""
        return await self._release(
            job_id=job_id,
            dataset_id=dataset_id,
            aggregate_type="count",
            raw_value=count,
            epsilon=epsilon,
            delta=delta,
            mechanism="laplace",
            population_filter=population_filter,
            query_template_id="cohort_count" if request_zk_proof else None,
            request_zk_proof=request_zk_proof,
        )

    async def release_sum(
        self,
        job_id: str,
        dataset_id: str,
        total: float,
        lower_bound: float,
        upper_bound: float,
        epsilon: float = 1.0,
        delta: float = 1e-6,
        max_contributions: int = 1,
    ) -> ReleaseReceipt:
        """Release a sum aggregate with DP protection."""
        return await self._release(
            job_id=job_id,
            dataset_id=dataset_id,
            aggregate_type="sum",
            raw_value=total,
            epsilon=epsilon,
            delta=delta,
            mechanism="laplace",
            contribution_bounds={
                "max_contributions": max_contributions,
                "lower_bound": lower_bound,
                "upper_bound": upper_bound,
            },
        )

    async def release_histogram(
        self,
        job_id: str,
        dataset_id: str,
        histogram: dict[str, int],
        epsilon: float = 1.0,
        delta: float = 1e-6,
    ) -> ReleaseReceipt:
        """Release a histogram with DP protection and thresholding."""
        return await self._release(
            job_id=job_id,
            dataset_id=dataset_id,
            aggregate_type="histogram",
            raw_value=histogram,
            epsilon=epsilon,
            delta=delta,
            mechanism="thresholded_laplace",
        )

    async def _release(
        self,
        job_id: str,
        dataset_id: str,
        aggregate_type: str,
        raw_value: Any,
        epsilon: float,
        delta: float,
        mechanism: str = "laplace",
        contribution_bounds: Optional[dict] = None,
        population_filter: Optional[str] = None,
        query_template_id: Optional[str] = None,
        request_zk_proof: bool = False,
        release_policy_name: Optional[str] = None,
        release_policy_namespace: Optional[str] = None,
        dataset_binding_name: Optional[str] = None,
        dataset_binding_namespace: Optional[str] = None,
    ) -> ReleaseReceipt:
        """Internal method to submit a release request."""
        payload = {
            "job_id": job_id,
            "dataset_id": dataset_id,
            "aggregate_type": aggregate_type,
            "raw_value": raw_value,
            "epsilon": epsilon,
            "delta": delta,
            "mechanism": mechanism,
        }

        if contribution_bounds:
            payload["contribution_bounds"] = contribution_bounds
        if population_filter:
            payload["population_filter"] = population_filter
        if query_template_id:
            payload["query_template_id"] = query_template_id
        if request_zk_proof:
            payload["request_zk_proof"] = request_zk_proof

        policy_name = release_policy_name or self.release_policy_name
        policy_namespace = release_policy_namespace or self.release_policy_namespace
        if policy_name:
            payload["release_policy_ref"] = {
                "name": policy_name,
                "namespace": policy_namespace,
            }

        binding_name = dataset_binding_name or self.dataset_binding_name
        binding_namespace = dataset_binding_namespace or self.dataset_binding_namespace
        if binding_name:
            payload["dataset_binding_ref"] = {
                "name": binding_name,
                "namespace": binding_namespace,
            }

        response = await self._client.post(
            f"{self.base_url}/v1/release",
            json=payload,
        )
        response.raise_for_status()
        result = response.json()

        if not result["success"]:
            raise ValueError(f"Release failed: {result['error']} ({result['error_code']})")

        receipt = result["receipt"]
        return ReleaseReceipt(
            receipt_id=receipt["receipt_id"],
            released_value=receipt["released_value"],
            epsilon_consumed=receipt["epsilon_consumed"],
            delta_consumed=receipt["delta_consumed"],
            remaining_epsilon=receipt["remaining_epsilon"],
            remaining_delta=receipt["remaining_delta"],
            mechanism=receipt["mechanism"],
            zk_proof_id=receipt.get("zk_proof_id"),
        )

    async def get_budget(self, dataset_id: str) -> dict:
        """Get budget status for a dataset."""
        response = await self._client.get(f"{self.base_url}/v1/budget/{dataset_id}")
        response.raise_for_status()
        return response.json()

    async def health_check(self) -> dict:
        """Check Release Gate health."""
        response = await self._client.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()


async def example_analytics_job():
    """Example analytics job that uses the Release Gate."""
    job_id = os.getenv("JOB_ID", "example-job-001")
    dataset_id = os.getenv("DATASET_ID", "sales_2024")

    async with VCDAReleaseClient() as client:
        # Check health
        health = await client.health_check()
        print(f"Release Gate status: {health['status']}")

        # Check available budget
        budget = await client.get_budget(dataset_id)
        print(f"Remaining epsilon: {budget['remaining_epsilon']}")

        if budget["is_exhausted"]:
            print("Budget exhausted - cannot release")
            return

        # Simulate computing a count
        raw_count = 15847  # This would come from your actual query

        # Release with DP protection
        receipt = await client.release_count(
            job_id=job_id,
            dataset_id=dataset_id,
            count=raw_count,
            epsilon=1.0,
            population_filter="region = 'US'",
        )

        print(f"Released count: {receipt.released_value}")
        print(f"Epsilon consumed: {receipt.epsilon_consumed}")
        print(f"Remaining epsilon: {receipt.remaining_epsilon}")
        print(f"Receipt ID: {receipt.receipt_id}")

        # Example: Release a histogram with small cohort protection
        raw_histogram = {
            "category_a": 1500,
            "category_b": 8,      # This will likely be suppressed
            "category_c": 2300,
            "category_d": 15,     # This might be suppressed
        }

        receipt = await client.release_histogram(
            job_id=job_id,
            dataset_id=dataset_id,
            histogram=raw_histogram,
            epsilon=2.0,
        )

        print(f"\nReleased histogram: {receipt.released_value}")
        print("(Small categories may have been suppressed)")


if __name__ == "__main__":
    asyncio.run(example_analytics_job())

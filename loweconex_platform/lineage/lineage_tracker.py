"""
Digital Thread & Lineage Tracker — OpenLineage-compatible provenance.

Implements the OpenLineage event model (Job → Run → Dataset) to capture
end-to-end lineage: dataset → transformation → model run → KPI artifact →
ROI rollup → report paragraph.

Aligns with:
- OpenLineage spec (openlineage.io)
- Digital Twin Consortium digital-thread interoperability
- ISO 23247 digital twin manufacturing framework (lineage extension)

Every numbered output in the platform carries a lineage_id that traces
back through the full chain of provenance.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# OpenLineage-aligned facet model
# =============================================================================

class LineageEventType(str, Enum):
    """OpenLineage-compatible event types."""
    START = "START"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAIL = "FAIL"
    ABORT = "ABORT"


class DatasetType(str, Enum):
    """Classification of datasets in the lineage graph."""
    RAW_TELEMETRY = "raw_telemetry"
    RAW_WORK_ORDER = "raw_work_order"
    RAW_EVENT = "raw_event"
    RAW_TARIFF = "raw_tariff"
    NORMALIZED = "normalized"
    FEATURE_TABLE = "feature_table"
    TWIN_SNAPSHOT = "twin_snapshot"
    KPI_INPUT_CONTRACT = "kpi_input_contract"
    KPI_ARTIFACT = "kpi_artifact"
    SCENARIO_RESULT = "scenario_result"
    ROI_ROLLUP = "roi_rollup"
    REPORT_SECTION = "report_section"
    REPORT_EXPORT = "report_export"
    BENCHMARK_COHORT = "benchmark_cohort"
    MV_BASELINE = "mv_baseline"


class JobType(str, Enum):
    """Classification of jobs (transformation steps)."""
    INGESTION = "ingestion"
    NORMALIZATION = "normalization"
    IDENTITY_RESOLUTION = "identity_resolution"
    FEATURE_ENGINEERING = "feature_engineering"
    KPI_RESEARCH = "kpi_research"
    KPI_EXTRACTION = "kpi_extraction"
    KPI_CALCULATION = "kpi_calculation"
    KPI_QA = "kpi_qa"
    SCENARIO_SIMULATION = "scenario_simulation"
    PORTFOLIO_OPTIMIZATION = "portfolio_optimization"
    DOUBLE_COUNTING_RESOLUTION = "double_counting_resolution"
    ROI_COMPUTATION = "roi_computation"
    REPORT_GENERATION = "report_generation"
    MV_RECONCILIATION = "mv_reconciliation"
    BENCHMARK_UPDATE = "benchmark_update"
    MODEL_INFERENCE = "model_inference"
    MODEL_TRAINING = "model_training"


@dataclass
class DatasetFacet:
    """
    OpenLineage Dataset facet — describes a versioned dataset.

    Fields mirror OpenLineage InputDatasetFacet / OutputDatasetFacet.
    """
    dataset_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    namespace: str = "loweconex"
    name: str = ""
    dataset_type: str = DatasetType.RAW_TELEMETRY.value
    version: str = "1"

    # Schema facet
    schema_fields: List[Dict[str, str]] = field(default_factory=list)

    # Data quality facet
    row_count: Optional[int] = None
    byte_size: Optional[int] = None
    quality_score: Optional[float] = None

    # Ownership
    company_id: Optional[str] = None
    location_id: Optional[str] = None

    # Content hash for dedup / reproducibility
    content_hash: Optional[str] = None

    # Timestamp
    created_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "namespace": self.namespace,
            "name": self.name,
            "dataset_type": self.dataset_type,
            "version": self.version,
            "schema_fields": self.schema_fields,
            "row_count": self.row_count,
            "byte_size": self.byte_size,
            "quality_score": self.quality_score,
            "company_id": self.company_id,
            "location_id": self.location_id,
            "content_hash": self.content_hash,
            "created_ts": self.created_ts,
        }


@dataclass
class JobFacet:
    """
    OpenLineage Job facet — describes a transformation or computation step.
    """
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    namespace: str = "loweconex"
    name: str = ""
    job_type: str = JobType.INGESTION.value

    # Owner / producer
    owner: str = ""
    description: str = ""

    # Code version / reproducibility
    code_version: Optional[str] = None
    code_hash: Optional[str] = None

    # Configuration snapshot (parameters that affect output)
    config_snapshot: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "namespace": self.namespace,
            "name": self.name,
            "job_type": self.job_type,
            "owner": self.owner,
            "description": self.description,
            "code_version": self.code_version,
            "code_hash": self.code_hash,
            "config_snapshot": self.config_snapshot,
        }


@dataclass
class RunFacet:
    """
    OpenLineage Run facet — a specific execution of a Job.
    """
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = ""
    parent_run_id: Optional[str] = None

    # Timing
    started_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    ended_ts: Optional[str] = None
    duration_ms: Optional[int] = None

    # Status
    status: str = LineageEventType.START.value

    # Error info
    error_message: Optional[str] = None
    error_stacktrace: Optional[str] = None

    # Environment
    environment: str = "production"
    agent_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "job_id": self.job_id,
            "parent_run_id": self.parent_run_id,
            "started_ts": self.started_ts,
            "ended_ts": self.ended_ts,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "error_message": self.error_message,
            "error_stacktrace": self.error_stacktrace,
            "environment": self.environment,
            "agent_id": self.agent_id,
        }


@dataclass
class LineageEvent:
    """
    OpenLineage-compatible lineage event.

    Captures: which Job/Run consumed which input Datasets and produced
    which output Datasets.
    """
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = LineageEventType.COMPLETE.value
    event_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    job: Optional[JobFacet] = None
    run: Optional[RunFacet] = None

    input_datasets: List[DatasetFacet] = field(default_factory=list)
    output_datasets: List[DatasetFacet] = field(default_factory=list)

    # Correlation
    correlation_id: Optional[str] = None
    company_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "event_ts": self.event_ts,
            "job": self.job.to_dict() if self.job else None,
            "run": self.run.to_dict() if self.run else None,
            "input_datasets": [d.to_dict() for d in self.input_datasets],
            "output_datasets": [d.to_dict() for d in self.output_datasets],
            "correlation_id": self.correlation_id,
            "company_id": self.company_id,
        }


# =============================================================================
# Lineage Graph — in-memory DAG of provenance
# =============================================================================

class LineageGraph:
    """
    In-memory directed acyclic graph of dataset → job → dataset lineage.

    Supports:
    - Forward trace (what did this dataset produce?)
    - Backward trace (where did this number come from?)
    - Subgraph extraction for a specific KPI or report section
    - Content-hash-based reproducibility checks
    """

    def __init__(self):
        self._datasets: Dict[str, DatasetFacet] = {}
        self._jobs: Dict[str, JobFacet] = {}
        self._runs: Dict[str, RunFacet] = {}
        self._events: List[LineageEvent] = []

        # Edges: job_id → (input_dataset_ids, output_dataset_ids)
        self._job_inputs: Dict[str, Set[str]] = {}
        self._job_outputs: Dict[str, Set[str]] = {}

        # Reverse index: dataset_id → producing job_ids
        self._produced_by: Dict[str, Set[str]] = {}
        # Reverse index: dataset_id → consuming job_ids
        self._consumed_by: Dict[str, Set[str]] = {}

    def record_event(self, event: LineageEvent):
        """Record a lineage event and update the graph."""
        self._events.append(event)

        if event.job:
            self._jobs[event.job.job_id] = event.job
        if event.run:
            self._runs[event.run.run_id] = event.run

        job_id = event.job.job_id if event.job else "unknown"

        if job_id not in self._job_inputs:
            self._job_inputs[job_id] = set()
        if job_id not in self._job_outputs:
            self._job_outputs[job_id] = set()

        for ds in event.input_datasets:
            self._datasets[ds.dataset_id] = ds
            self._job_inputs[job_id].add(ds.dataset_id)
            if ds.dataset_id not in self._consumed_by:
                self._consumed_by[ds.dataset_id] = set()
            self._consumed_by[ds.dataset_id].add(job_id)

        for ds in event.output_datasets:
            self._datasets[ds.dataset_id] = ds
            self._job_outputs[job_id].add(ds.dataset_id)
            if ds.dataset_id not in self._produced_by:
                self._produced_by[ds.dataset_id] = set()
            self._produced_by[ds.dataset_id].add(job_id)

        logger.debug(
            f"Lineage event: {job_id} consumed {len(event.input_datasets)} "
            f"datasets, produced {len(event.output_datasets)} datasets"
        )

    def trace_backward(self, dataset_id: str, max_depth: int = 20) -> List[Dict[str, Any]]:
        """
        Backward trace: given an output dataset, find all upstream
        datasets and jobs that contributed to it.

        Returns a list of lineage steps (newest to oldest).
        """
        visited: Set[str] = set()
        trace: List[Dict[str, Any]] = []
        self._trace_backward_recursive(dataset_id, trace, visited, 0, max_depth)
        return trace

    def _trace_backward_recursive(
        self, dataset_id: str, trace: List[Dict[str, Any]],
        visited: Set[str], depth: int, max_depth: int
    ):
        if depth >= max_depth or dataset_id in visited:
            return
        visited.add(dataset_id)

        ds = self._datasets.get(dataset_id)
        if not ds:
            return

        producing_jobs = self._produced_by.get(dataset_id, set())
        for job_id in producing_jobs:
            job = self._jobs.get(job_id)
            step = {
                "depth": depth,
                "dataset": ds.to_dict(),
                "produced_by_job": job.to_dict() if job else None,
                "job_inputs": [],
            }

            input_ids = self._job_inputs.get(job_id, set())
            for input_id in input_ids:
                input_ds = self._datasets.get(input_id)
                if input_ds:
                    step["job_inputs"].append(input_ds.to_dict())
                    self._trace_backward_recursive(
                        input_id, trace, visited, depth + 1, max_depth
                    )

            trace.append(step)

    def trace_forward(self, dataset_id: str, max_depth: int = 20) -> List[Dict[str, Any]]:
        """
        Forward trace: given an input dataset, find all downstream
        datasets and jobs it feeds into.
        """
        visited: Set[str] = set()
        trace: List[Dict[str, Any]] = []
        self._trace_forward_recursive(dataset_id, trace, visited, 0, max_depth)
        return trace

    def _trace_forward_recursive(
        self, dataset_id: str, trace: List[Dict[str, Any]],
        visited: Set[str], depth: int, max_depth: int
    ):
        if depth >= max_depth or dataset_id in visited:
            return
        visited.add(dataset_id)

        ds = self._datasets.get(dataset_id)
        if not ds:
            return

        consuming_jobs = self._consumed_by.get(dataset_id, set())
        for job_id in consuming_jobs:
            job = self._jobs.get(job_id)
            step = {
                "depth": depth,
                "dataset": ds.to_dict(),
                "consumed_by_job": job.to_dict() if job else None,
                "job_outputs": [],
            }

            output_ids = self._job_outputs.get(job_id, set())
            for output_id in output_ids:
                output_ds = self._datasets.get(output_id)
                if output_ds:
                    step["job_outputs"].append(output_ds.to_dict())
                    self._trace_forward_recursive(
                        output_id, trace, visited, depth + 1, max_depth
                    )

            trace.append(step)

    def get_kpi_lineage(self, kpi_name: str) -> List[Dict[str, Any]]:
        """Extract the full lineage subgraph for a specific KPI."""
        kpi_datasets = [
            ds for ds in self._datasets.values()
            if kpi_name in ds.name or ds.dataset_type == DatasetType.KPI_ARTIFACT.value
        ]
        all_steps = []
        for ds in kpi_datasets:
            all_steps.extend(self.trace_backward(ds.dataset_id))
        return all_steps

    def verify_reproducibility(self, dataset_id: str) -> Dict[str, Any]:
        """
        Check if a dataset can be reproduced from its inputs.

        Returns verification result with content hash comparison.
        """
        ds = self._datasets.get(dataset_id)
        if not ds:
            return {"status": "not_found", "dataset_id": dataset_id}

        producing_jobs = self._produced_by.get(dataset_id, set())
        if not producing_jobs:
            return {
                "status": "root_dataset",
                "dataset_id": dataset_id,
                "message": "No producing job found; this is a root input.",
            }

        result = {
            "status": "verifiable",
            "dataset_id": dataset_id,
            "content_hash": ds.content_hash,
            "producing_jobs": [],
        }

        for job_id in producing_jobs:
            job = self._jobs.get(job_id)
            input_ids = self._job_inputs.get(job_id, set())
            input_hashes = []
            for iid in input_ids:
                ids = self._datasets.get(iid)
                if ids:
                    input_hashes.append(ids.content_hash)

            result["producing_jobs"].append({
                "job_id": job_id,
                "job_name": job.name if job else None,
                "code_hash": job.code_hash if job else None,
                "config_snapshot": job.config_snapshot if job else None,
                "input_content_hashes": input_hashes,
            })

        return result

    def stats(self) -> Dict[str, int]:
        return {
            "datasets": len(self._datasets),
            "jobs": len(self._jobs),
            "runs": len(self._runs),
            "events": len(self._events),
        }


# =============================================================================
# Lineage Tracker — high-level API for recording lineage
# =============================================================================

class LineageTracker:
    """
    High-level API for recording lineage events throughout the platform.

    Every pipeline step (ingestion, normalization, KPI calc, ROI, report)
    calls the tracker to record what it consumed and produced.

    Usage:
        tracker = LineageTracker()
        run_id = tracker.start_job("kpi_calculation", "energy_waste_kpi", ...)
        tracker.add_input(run_id, dataset_facet)
        tracker.add_output(run_id, output_facet)
        tracker.complete_job(run_id)
    """

    def __init__(self, graph: Optional[LineageGraph] = None):
        self.graph = graph or LineageGraph()
        self._active_runs: Dict[str, Dict[str, Any]] = {}

    def start_job(
        self,
        job_type: str,
        job_name: str,
        company_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        code_version: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> str:
        """Start a new lineage-tracked job. Returns run_id."""
        job = JobFacet(
            name=job_name,
            job_type=job_type,
            config_snapshot=config or {},
            code_version=code_version,
        )
        run = RunFacet(
            job_id=job.job_id,
            parent_run_id=parent_run_id,
            status=LineageEventType.START.value,
            agent_id=agent_id,
        )

        self._active_runs[run.run_id] = {
            "job": job,
            "run": run,
            "inputs": [],
            "outputs": [],
            "company_id": company_id,
            "correlation_id": correlation_id,
        }

        # Record START event
        event = LineageEvent(
            event_type=LineageEventType.START.value,
            job=job,
            run=run,
            company_id=company_id,
            correlation_id=correlation_id,
        )
        self.graph.record_event(event)

        logger.debug(f"Started lineage job: {job_name} (run={run.run_id})")
        return run.run_id

    def add_input(self, run_id: str, dataset: DatasetFacet):
        """Register an input dataset for an active run."""
        if run_id not in self._active_runs:
            logger.warning(f"Unknown run_id {run_id}")
            return
        self._active_runs[run_id]["inputs"].append(dataset)

    def add_output(self, run_id: str, dataset: DatasetFacet):
        """Register an output dataset for an active run."""
        if run_id not in self._active_runs:
            logger.warning(f"Unknown run_id {run_id}")
            return
        self._active_runs[run_id]["outputs"].append(dataset)

    def complete_job(self, run_id: str) -> Optional[LineageEvent]:
        """Mark a job as completed and emit COMPLETE lineage event."""
        return self._finish_job(run_id, LineageEventType.COMPLETE)

    def fail_job(self, run_id: str, error: str) -> Optional[LineageEvent]:
        """Mark a job as failed and emit FAIL lineage event."""
        if run_id in self._active_runs:
            self._active_runs[run_id]["run"].error_message = error
        return self._finish_job(run_id, LineageEventType.FAIL)

    def _finish_job(self, run_id: str, status: LineageEventType) -> Optional[LineageEvent]:
        ctx = self._active_runs.pop(run_id, None)
        if not ctx:
            logger.warning(f"Cannot finish unknown run {run_id}")
            return None

        run: RunFacet = ctx["run"]
        run.status = status.value
        run.ended_ts = datetime.utcnow().isoformat()

        started = datetime.fromisoformat(run.started_ts)
        ended = datetime.fromisoformat(run.ended_ts)
        run.duration_ms = int((ended - started).total_seconds() * 1000)

        event = LineageEvent(
            event_type=status.value,
            job=ctx["job"],
            run=run,
            input_datasets=ctx["inputs"],
            output_datasets=ctx["outputs"],
            company_id=ctx.get("company_id"),
            correlation_id=ctx.get("correlation_id"),
        )
        self.graph.record_event(event)

        logger.debug(
            f"Finished lineage job: {ctx['job'].name} ({status.value}) "
            f"in {run.duration_ms}ms"
        )
        return event

    def create_dataset(
        self,
        name: str,
        dataset_type: str,
        company_id: Optional[str] = None,
        location_id: Optional[str] = None,
        schema_fields: Optional[List[Dict[str, str]]] = None,
        row_count: Optional[int] = None,
        content: Optional[str] = None,
    ) -> DatasetFacet:
        """Create a dataset facet with optional content hashing."""
        content_hash = None
        if content:
            content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

        return DatasetFacet(
            name=name,
            dataset_type=dataset_type,
            company_id=company_id,
            location_id=location_id,
            schema_fields=schema_fields or [],
            row_count=row_count,
            content_hash=content_hash,
        )

    def get_full_thread(self, dataset_id: str) -> Dict[str, Any]:
        """
        Get the complete digital thread for a dataset — full backward
        trace showing every step from raw input to final output.
        """
        backward = self.graph.trace_backward(dataset_id)
        forward = self.graph.trace_forward(dataset_id)
        reproducibility = self.graph.verify_reproducibility(dataset_id)

        return {
            "dataset_id": dataset_id,
            "backward_trace": backward,
            "forward_trace": forward,
            "reproducibility": reproducibility,
            "graph_stats": self.graph.stats(),
        }

    def export_lineage_events(self) -> List[Dict[str, Any]]:
        """Export all lineage events as OpenLineage-compatible JSON."""
        return [e.to_dict() for e in self.graph._events]

    def get_all_events(self) -> List[Dict[str, Any]]:
        """Backward-compatible alias for callers expecting raw event export."""
        return self.export_lineage_events()

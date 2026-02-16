"""
Ingestion Scheduler — manages scheduled and backfill data ingestion runs.

Supports:
- Scheduled ingestion (once, hourly, daily, weekly)
- Backfill by date range
- Distinct run_id per ingestion run for idempotency
- Integration with LineageTracker for provenance
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ScheduledJob:
    """A scheduled ingestion job."""
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    connector_name: str = ""
    mapping_id: str = ""
    company_id: str = ""
    source_system: str = ""
    schedule: str = "once"  # "once", "hourly", "daily", "weekly"
    enabled: bool = True
    last_run_ts: Optional[str] = None
    last_run_id: Optional[str] = None
    last_status: Optional[str] = None
    next_run_ts: Optional[str] = None
    created_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "connector_name": self.connector_name,
            "mapping_id": self.mapping_id,
            "company_id": self.company_id,
            "source_system": self.source_system,
            "schedule": self.schedule,
            "enabled": self.enabled,
            "last_run_ts": self.last_run_ts,
            "last_run_id": self.last_run_id,
            "last_status": self.last_status,
            "next_run_ts": self.next_run_ts,
        }


@dataclass
class BackfillRequest:
    """Request to backfill data for a date range."""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    connector_name: str = ""
    mapping_id: str = ""
    company_id: str = ""
    source_system: str = ""
    start_date: str = ""
    end_date: str = ""
    status: str = "pending"  # pending, running, completed, failed
    run_id: Optional[str] = None
    created_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "connector_name": self.connector_name,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "status": self.status,
            "run_id": self.run_id,
        }


# Schedule intervals in seconds
SCHEDULE_INTERVALS = {
    "once": 0,
    "hourly": 3600,
    "daily": 86400,
    "weekly": 604800,
}


class IngestionScheduler:
    """
    Manages scheduled and backfill ingestion jobs.
    
    Each run gets a unique run_id for idempotent deduplication.
    Runs execute a user-provided callback with (job, run_id) args.
    """

    def __init__(self):
        self._jobs: Dict[str, ScheduledJob] = {}
        self._backfill_queue: List[BackfillRequest] = []
        self._run_history: List[Dict[str, Any]] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._run_callback: Optional[Callable] = None

    def register_job(self, job: ScheduledJob) -> ScheduledJob:
        """Register a scheduled ingestion job."""
        if job.schedule in SCHEDULE_INTERVALS:
            interval = SCHEDULE_INTERVALS[job.schedule]
            if interval > 0:
                next_ts = datetime.utcnow() + timedelta(seconds=interval)
                job.next_run_ts = next_ts.isoformat()
        self._jobs[job.job_id] = job
        logger.info(f"Registered job {job.job_id}: {job.connector_name} ({job.schedule})")
        return job

    def remove_job(self, job_id: str) -> bool:
        return self._jobs.pop(job_id, None) is not None

    def get_job(self, job_id: str) -> Optional[ScheduledJob]:
        return self._jobs.get(job_id)

    def list_jobs(self) -> List[ScheduledJob]:
        return list(self._jobs.values())

    def request_backfill(self, request: BackfillRequest) -> BackfillRequest:
        """Queue a backfill request for processing."""
        self._backfill_queue.append(request)
        logger.info(f"Backfill queued: {request.request_id} ({request.start_date} to {request.end_date})")
        return request

    def set_run_callback(self, callback: Callable):
        """Set the callback invoked for each scheduled run: callback(job, run_id)."""
        self._run_callback = callback

    def execute_job(self, job: ScheduledJob) -> Dict[str, Any]:
        """Execute a single job immediately. Returns run result."""
        run_id = str(uuid.uuid4())
        job.last_run_id = run_id
        job.last_run_ts = datetime.utcnow().isoformat()

        result = {"job_id": job.job_id, "run_id": run_id, "status": "success", "ts": job.last_run_ts}

        try:
            if self._run_callback:
                self._run_callback(job, run_id)
            job.last_status = "success"
        except Exception as e:
            job.last_status = "failed"
            result["status"] = "failed"
            result["error"] = str(e)
            logger.error(f"Job {job.job_id} failed: {e}")

        # Schedule next run
        interval = SCHEDULE_INTERVALS.get(job.schedule, 0)
        if interval > 0:
            job.next_run_ts = (datetime.utcnow() + timedelta(seconds=interval)).isoformat()

        self._run_history.append(result)
        return result

    def execute_backfill(self, request: BackfillRequest) -> Dict[str, Any]:
        """Execute a backfill request immediately."""
        run_id = str(uuid.uuid4())
        request.run_id = run_id
        request.status = "running"

        result = {"request_id": request.request_id, "run_id": run_id, "status": "completed"}

        try:
            if self._run_callback:
                # Create a temporary job-like object for the callback
                temp_job = ScheduledJob(
                    connector_name=request.connector_name,
                    mapping_id=request.mapping_id,
                    company_id=request.company_id,
                    source_system=request.source_system,
                    schedule="once",
                )
                self._run_callback(temp_job, run_id)
            request.status = "completed"
        except Exception as e:
            request.status = "failed"
            result["status"] = "failed"
            result["error"] = str(e)

        self._run_history.append(result)
        return result

    def tick(self):
        """Check for due jobs and execute them. Call periodically."""
        now = datetime.utcnow()
        for job in self._jobs.values():
            if not job.enabled or job.schedule == "once":
                continue
            if job.next_run_ts:
                next_ts = datetime.fromisoformat(job.next_run_ts)
                if now >= next_ts:
                    logger.info(f"Executing scheduled job: {job.job_id}")
                    self.execute_job(job)

        # Process backfill queue
        pending = [r for r in self._backfill_queue if r.status == "pending"]
        for request in pending:
            self.execute_backfill(request)

    def start(self, interval_seconds: int = 60):
        """Start the scheduler loop in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, args=(interval_seconds,), daemon=True)
        self._thread.start()
        logger.info(f"Scheduler started (interval={interval_seconds}s)")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self, interval: int):
        while self._running:
            try:
                self.tick()
            except Exception as e:
                logger.error(f"Scheduler tick error: {e}")
            time.sleep(interval)

    def get_run_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._run_history[-limit:]

    def stats(self) -> Dict[str, Any]:
        return {
            "jobs": len(self._jobs),
            "backfill_pending": sum(1 for r in self._backfill_queue if r.status == "pending"),
            "total_runs": len(self._run_history),
        }

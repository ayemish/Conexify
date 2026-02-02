"""
Phase 5: Observability & API Layer - Job Scheduler

Scheduled job runner for retraining, metrics aggregation, and maintenance tasks.
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from .observability_models import (
    JobExecution,
    JobStatus,
    ScheduledJob,
)
from .learning_loop_hvacr import HVACRPdMSystem
from .observability_metrics import MetricsCollector

logger = logging.getLogger(__name__)


class CronParser:
    """Simple cron expression parser"""
    
    @staticmethod
    def _matches_field(field: str, value: int, max_val: int) -> bool:
        """Check if a value matches a cron field expression"""
        if field == "*":
            return True
        
        # Handle step values like */15
        if field.startswith("*/"):
            step = int(field[2:])
            return value % step == 0
        
        # Handle ranges like 1-5
        if "-" in field:
            start, end = field.split("-")
            return int(start) <= value <= int(end)
        
        # Handle lists like 1,3,5
        if "," in field:
            values = [int(v) for v in field.split(",")]
            return value in values
        
        # Simple value
        return int(field) == value
    
    @staticmethod
    def matches(cron_expr: str, dt: datetime) -> bool:
        """
        Check if datetime matches cron expression.
        Format: minute hour day_of_month month day_of_week
        Supports: * (any), specific values, */step, ranges (1-5), lists (1,3,5).
        """
        parts = cron_expr.split()
        if len(parts) != 5:
            return False
        
        minute, hour, dom, month, dow = parts
        
        if not CronParser._matches_field(minute, dt.minute, 59):
            return False
        if not CronParser._matches_field(hour, dt.hour, 23):
            return False
        if not CronParser._matches_field(dom, dt.day, 31):
            return False
        if not CronParser._matches_field(month, dt.month, 12):
            return False
        if not CronParser._matches_field(dow, dt.weekday(), 6):
            return False
        
        return True
    
    @staticmethod
    def next_run(cron_expr: str, from_dt: datetime = None) -> Optional[datetime]:
        """Calculate next run time for cron expression"""
        if from_dt is None:
            from_dt = datetime.utcnow()
        
        # Simple implementation: check next 48 hours minute by minute
        check_dt = from_dt + timedelta(minutes=1)
        check_dt = check_dt.replace(second=0, microsecond=0)
        
        for _ in range(48 * 60):  # 48 hours of minutes
            if CronParser.matches(cron_expr, check_dt):
                return check_dt
            check_dt += timedelta(minutes=1)
        
        return None


class JobRunner:
    """
    Executes scheduled jobs with retry and error handling.
    """
    
    def __init__(self, system: HVACRPdMSystem, 
                 metrics: Optional[MetricsCollector] = None):
        self.system = system
        self.metrics = metrics or MetricsCollector()
        self._job_handlers: Dict[str, Callable] = {}
        self._register_default_handlers()
    
    def _register_default_handlers(self):
        """Register default job handlers"""
        self._job_handlers["retraining_check"] = self._handle_retraining_check
        self._job_handlers["metrics_aggregation"] = self._handle_metrics_aggregation
        self._job_handlers["alert_check"] = self._handle_alert_check
        self._job_handlers["cleanup"] = self._handle_cleanup
        self._job_handlers["health_check"] = self._handle_health_check
    
    def register_handler(self, job_type: str, handler: Callable):
        """Register a custom job handler"""
        self._job_handlers[job_type] = handler
        logger.info(f"Registered job handler: {job_type}")
    
    def execute(self, job: ScheduledJob) -> JobExecution:
        """Execute a scheduled job"""
        execution = JobExecution(
            job_id=job.job_id,
            job_name=job.name,
        )
        execution.start()
        
        handler = self._job_handlers.get(job.job_type)
        if not handler:
            execution.fail(f"No handler for job type: {job.job_type}")
            return execution
        
        retry_count = 0
        last_error = None
        
        while retry_count <= job.retry_count:
            try:
                result = handler(job, self.system, self.metrics)
                execution.complete(result)
                
                self.metrics.increment("scheduler_jobs_completed")
                logger.info(f"Job completed: {job.name}")
                return execution
                
            except Exception as e:
                last_error = str(e)
                retry_count += 1
                execution.retry_attempt = retry_count
                
                if retry_count <= job.retry_count:
                    logger.warning(f"Job {job.name} failed, retry {retry_count}/{job.retry_count}: {e}")
                    time.sleep(job.retry_delay_seconds)
                else:
                    logger.error(f"Job {job.name} failed after {retry_count} attempts: {e}")
        
        execution.fail(last_error or "Unknown error")
        self.metrics.increment("scheduler_jobs_failed")
        return execution
    
    def _handle_retraining_check(self, job: ScheduledJob, 
                                  system: HVACRPdMSystem,
                                  metrics: MetricsCollector) -> Dict[str, Any]:
        """Check retraining triggers and create jobs"""
        triggered_jobs = system.check_retraining_triggers()
        
        for tj in triggered_jobs:
            metrics.record_retraining_trigger(tj["model_name"], tj["trigger_type"])
        
        return {
            "triggers_evaluated": len(system.retraining_pipeline.triggers),
            "jobs_created": len(triggered_jobs),
            "job_ids": [tj["job_id"] for tj in triggered_jobs],
        }
    
    def _handle_metrics_aggregation(self, job: ScheduledJob,
                                     system: HVACRPdMSystem,
                                     metrics: MetricsCollector) -> Dict[str, Any]:
        """Aggregate metrics for all models"""
        aggregated = []
        
        for model_name in system.model_registry.list_all_models():
            result = system.aggregate_metrics(model_name)
            if result:
                metrics.record_model_metrics(model_name, "latest", result)
                aggregated.append(model_name)
        
        return {
            "models_aggregated": len(aggregated),
            "model_names": aggregated,
        }
    
    def _handle_alert_check(self, job: ScheduledJob,
                            system: HVACRPdMSystem,
                            metrics: MetricsCollector) -> Dict[str, Any]:
        """Check for expired approvals and other alerts"""
        expired = system.governance.check_expired_approvals()
        
        return {
            "expired_approvals": len(expired),
            "approval_ids": [a.approval_id for a in expired],
        }
    
    def _handle_cleanup(self, job: ScheduledJob,
                        system: HVACRPdMSystem,
                        metrics: MetricsCollector) -> Dict[str, Any]:
        """Cleanup old data"""
        # Cleanup old prediction buffer
        cutoff = datetime.utcnow() - timedelta(days=7)
        original_count = len(system.prediction_buffer)
        system.prediction_buffer = [
            p for p in system.prediction_buffer
            if datetime.fromisoformat(p["timestamp"]) > cutoff
        ]
        cleaned = original_count - len(system.prediction_buffer)
        
        return {
            "predictions_cleaned": cleaned,
            "remaining": len(system.prediction_buffer),
        }
    
    def _handle_health_check(self, job: ScheduledJob,
                             system: HVACRPdMSystem,
                             metrics: MetricsCollector) -> Dict[str, Any]:
        """Perform health check"""
        status = system.get_system_status()
        
        # Record system metrics
        metrics.record_system_metric("active_models", len(status["active_models"]))
        metrics.record_system_metric("pending_jobs", status["pending_jobs"])
        metrics.record_system_metric("cases_tracked", status["cases_tracked"])
        
        return {
            "status": "healthy",
            "active_models": len(status["active_models"]),
            "active_experiments": len(status["active_experiments"]),
        }


class Scheduler:
    """
    Job scheduler with cron-like scheduling.
    Runs jobs based on their cron expressions.
    """
    
    def __init__(self, system: HVACRPdMSystem,
                 metrics: Optional[MetricsCollector] = None):
        self.system = system
        self.metrics = metrics or MetricsCollector()
        self.runner = JobRunner(system, self.metrics)
        
        self.jobs: Dict[str, ScheduledJob] = {}
        self.executions: List[JobExecution] = []
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        self._initialize_default_jobs()
        logger.info("Scheduler initialized")
    
    def _initialize_default_jobs(self):
        """Set up default scheduled jobs"""
        # Retraining check every hour
        self.add_job(ScheduledJob(
            job_id="retraining-check",
            name="Retraining Trigger Check",
            description="Check retraining triggers and create jobs",
            job_type="retraining_check",
            cron_expression="0 * * * *",  # Every hour at :00
            timeout_seconds=300,
        ))
        
        # Metrics aggregation every 15 minutes
        self.add_job(ScheduledJob(
            job_id="metrics-aggregation",
            name="Metrics Aggregation",
            description="Aggregate model performance metrics",
            job_type="metrics_aggregation",
            cron_expression="*/15 * * * *",  # Every 15 minutes
            timeout_seconds=120,
        ))
        
        # Alert check every 5 minutes
        self.add_job(ScheduledJob(
            job_id="alert-check",
            name="Alert Check",
            description="Check for expired approvals and alerts",
            job_type="alert_check",
            cron_expression="*/5 * * * *",  # Every 5 minutes
            timeout_seconds=60,
        ))
        
        # Cleanup daily at 3 AM
        self.add_job(ScheduledJob(
            job_id="daily-cleanup",
            name="Daily Cleanup",
            description="Clean up old data",
            job_type="cleanup",
            cron_expression="0 3 * * *",  # Daily at 3 AM
            timeout_seconds=600,
        ))
        
        # Health check every 10 minutes
        self.add_job(ScheduledJob(
            job_id="health-check",
            name="Health Check",
            description="System health check",
            job_type="health_check",
            cron_expression="*/10 * * * *",  # Every 10 minutes
            timeout_seconds=60,
        ))
    
    def add_job(self, job: ScheduledJob):
        """Add a scheduled job"""
        job.next_run_at = CronParser.next_run(job.cron_expression)
        
        with self._lock:
            self.jobs[job.job_id] = job
        
        logger.info(f"Added job: {job.name} (next run: {job.next_run_at})")
    
    def remove_job(self, job_id: str):
        """Remove a scheduled job"""
        with self._lock:
            if job_id in self.jobs:
                del self.jobs[job_id]
                logger.info(f"Removed job: {job_id}")
    
    def enable_job(self, job_id: str):
        """Enable a job"""
        with self._lock:
            if job_id in self.jobs:
                self.jobs[job_id].is_enabled = True
    
    def disable_job(self, job_id: str):
        """Disable a job"""
        with self._lock:
            if job_id in self.jobs:
                self.jobs[job_id].is_enabled = False
    
    def run_now(self, job_id: str) -> Optional[JobExecution]:
        """Run a job immediately"""
        job = self.jobs.get(job_id)
        if not job:
            logger.warning(f"Job not found: {job_id}")
            return None
        
        execution = self.runner.execute(job)
        
        with self._lock:
            self.executions.append(execution)
            job.last_run_at = datetime.utcnow()
            job.next_run_at = CronParser.next_run(job.cron_expression)
        
        return execution
    
    def start(self):
        """Start the scheduler in a background thread"""
        if self._running:
            logger.warning("Scheduler already running")
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("Scheduler started")
    
    def stop(self):
        """Stop the scheduler"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Scheduler stopped")
    
    def _run_loop(self):
        """Main scheduler loop"""
        while self._running:
            now = datetime.utcnow()
            
            with self._lock:
                jobs_to_run = []
                for job in self.jobs.values():
                    if not job.is_enabled:
                        continue
                    if job.next_run_at and job.next_run_at <= now:
                        jobs_to_run.append(job)
            
            for job in jobs_to_run:
                try:
                    execution = self.runner.execute(job)
                    
                    with self._lock:
                        self.executions.append(execution)
                        job.last_run_at = now
                        job.next_run_at = CronParser.next_run(job.cron_expression)
                        
                except Exception as e:
                    logger.error(f"Error running job {job.name}: {e}")
            
            # Sleep for 1 minute before next check
            time.sleep(60)
    
    def tick(self):
        """
        Manual tick for testing - check and run due jobs.
        Use this instead of start() for synchronous execution.
        """
        now = datetime.utcnow()
        
        with self._lock:
            jobs_to_run = []
            for job in self.jobs.values():
                if not job.is_enabled:
                    continue
                if job.next_run_at and job.next_run_at <= now:
                    jobs_to_run.append(job)
        
        executions = []
        for job in jobs_to_run:
            execution = self.runner.execute(job)
            
            with self._lock:
                self.executions.append(execution)
                job.last_run_at = now
                job.next_run_at = CronParser.next_run(job.cron_expression)
            
            executions.append(execution)
        
        return executions
    
    def get_job_status(self) -> List[Dict[str, Any]]:
        """Get status of all jobs"""
        result = []
        
        with self._lock:
            for job in self.jobs.values():
                result.append({
                    "job_id": job.job_id,
                    "name": job.name,
                    "job_type": job.job_type,
                    "is_enabled": job.is_enabled,
                    "cron_expression": job.cron_expression,
                    "last_run_at": job.last_run_at.isoformat() if job.last_run_at else None,
                    "next_run_at": job.next_run_at.isoformat() if job.next_run_at else None,
                })
        
        return result
    
    def get_execution_history(self, job_id: Optional[str] = None,
                               limit: int = 50) -> List[Dict[str, Any]]:
        """Get job execution history"""
        with self._lock:
            executions = self.executions
            if job_id:
                executions = [e for e in executions if e.job_id == job_id]
            
            executions = sorted(executions, 
                               key=lambda e: e.started_at or datetime.min, 
                               reverse=True)[:limit]
        
        return [
            {
                "execution_id": e.execution_id,
                "job_id": e.job_id,
                "job_name": e.job_name,
                "status": e.status.value,
                "started_at": e.started_at.isoformat() if e.started_at else None,
                "completed_at": e.completed_at.isoformat() if e.completed_at else None,
                "duration_seconds": e.duration_seconds,
                "error_message": e.error_message,
                "result": e.result,
            }
            for e in executions
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics"""
        with self._lock:
            total = len(self.executions)
            completed = len([e for e in self.executions if e.status == JobStatus.COMPLETED])
            failed = len([e for e in self.executions if e.status == JobStatus.FAILED])
            
            by_job = {}
            for e in self.executions:
                if e.job_id not in by_job:
                    by_job[e.job_id] = {"total": 0, "completed": 0, "failed": 0}
                by_job[e.job_id]["total"] += 1
                if e.status == JobStatus.COMPLETED:
                    by_job[e.job_id]["completed"] += 1
                elif e.status == JobStatus.FAILED:
                    by_job[e.job_id]["failed"] += 1
        
        return {
            "is_running": self._running,
            "total_jobs": len(self.jobs),
            "enabled_jobs": len([j for j in self.jobs.values() if j.is_enabled]),
            "total_executions": total,
            "completed": completed,
            "failed": failed,
            "success_rate": completed / total if total > 0 else 0,
            "by_job": by_job,
        }

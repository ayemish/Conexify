"""
Phase 5: Observability & API Layer - Health Checks

System health monitoring and diagnostics.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from .observability_models import (
    ComponentHealth,
    HealthStatus,
    SystemHealth,
)
from .learning_loop_hvacr import HVACRPdMSystem
from .observability_metrics import MetricsCollector

logger = logging.getLogger(__name__)


class HealthChecker:
    """
    System health monitoring with component checks.
    """
    
    def __init__(self, system: HVACRPdMSystem,
                 metrics: Optional[MetricsCollector] = None):
        self.system = system
        self.metrics = metrics or MetricsCollector()
        self._start_time = datetime.utcnow()
        self._custom_checks: Dict[str, Callable[[], ComponentHealth]] = {}
        
        logger.info("HealthChecker initialized")
    
    def register_check(self, name: str, check_func: Callable[[], ComponentHealth]):
        """Register a custom health check"""
        self._custom_checks[name] = check_func
    
    def check_all(self) -> SystemHealth:
        """Run all health checks and return overall status"""
        health = SystemHealth(
            version="1.0.0",
            uptime_seconds=self.get_uptime_seconds(),
        )
        
        # Core component checks
        health.components.append(self._check_model_registry())
        health.components.append(self._check_ab_testing())
        health.components.append(self._check_retraining_pipeline())
        health.components.append(self._check_governance())
        health.components.append(self._check_metrics_collector())
        
        # Custom checks
        for name, check_func in self._custom_checks.items():
            try:
                component = check_func()
                health.components.append(component)
            except Exception as e:
                health.components.append(ComponentHealth(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=str(e),
                ))
        
        # Compute overall status
        health.compute_overall_status()
        
        # Record metric
        status_value = {
            HealthStatus.HEALTHY: 1,
            HealthStatus.DEGRADED: 0.5,
            HealthStatus.UNHEALTHY: 0,
            HealthStatus.UNKNOWN: -1,
        }.get(health.overall_status, -1)
        self.metrics.record_system_metric("health_status", status_value)
        
        return health
    
    def get_uptime_seconds(self) -> float:
        """Get system uptime in seconds"""
        return (datetime.utcnow() - self._start_time).total_seconds()
    
    def _check_model_registry(self) -> ComponentHealth:
        """Check model registry health"""
        start = time.time()
        
        try:
            stats = self.system.model_registry.get_registry_stats()
            response_time = (time.time() - start) * 1000
            
            # Check for issues
            issues = []
            
            if stats["total_versions"] == 0:
                issues.append("No models registered")
            
            prod_count = stats["by_stage"].get("production", 0)
            if prod_count == 0:
                issues.append("No production models")
            
            if issues:
                return ComponentHealth(
                    name="model_registry",
                    status=HealthStatus.DEGRADED,
                    message="; ".join(issues),
                    response_time_ms=response_time,
                    details=stats,
                )
            
            return ComponentHealth(
                name="model_registry",
                status=HealthStatus.HEALTHY,
                message=f"{stats['total_versions']} model versions, {prod_count} in production",
                response_time_ms=response_time,
                details=stats,
            )
            
        except Exception as e:
            return ComponentHealth(
                name="model_registry",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                response_time_ms=(time.time() - start) * 1000,
            )
    
    def _check_ab_testing(self) -> ComponentHealth:
        """Check A/B testing framework health"""
        start = time.time()
        
        try:
            active_experiments = len(self.system.ab_testing.active_experiments)
            total_experiments = len(self.system.ab_testing.experiments)
            response_time = (time.time() - start) * 1000
            
            return ComponentHealth(
                name="ab_testing",
                status=HealthStatus.HEALTHY,
                message=f"{active_experiments} active experiments, {total_experiments} total",
                response_time_ms=response_time,
                details={
                    "active_experiments": active_experiments,
                    "total_experiments": total_experiments,
                },
            )
            
        except Exception as e:
            return ComponentHealth(
                name="ab_testing",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                response_time_ms=(time.time() - start) * 1000,
            )
    
    def _check_retraining_pipeline(self) -> ComponentHealth:
        """Check retraining pipeline health"""
        start = time.time()
        
        try:
            triggers = self.system.retraining_pipeline.triggers
            jobs = self.system.retraining_pipeline.jobs
            response_time = (time.time() - start) * 1000
            
            active_triggers = len([t for t in triggers.values() if t.is_active])
            pending_jobs = len([j for j in jobs.values() if j.status == "pending"])
            failed_jobs = len([j for j in jobs.values() if j.status == "failed"])
            
            issues = []
            status = HealthStatus.HEALTHY
            
            if active_triggers == 0:
                issues.append("No active triggers")
                status = HealthStatus.DEGRADED
            
            if failed_jobs > 0:
                issues.append(f"{failed_jobs} failed jobs")
                status = HealthStatus.DEGRADED
            
            message = f"{active_triggers} active triggers, {pending_jobs} pending jobs"
            if issues:
                message = f"{message}; Issues: {'; '.join(issues)}"
            
            return ComponentHealth(
                name="retraining_pipeline",
                status=status,
                message=message,
                response_time_ms=response_time,
                details={
                    "active_triggers": active_triggers,
                    "total_triggers": len(triggers),
                    "pending_jobs": pending_jobs,
                    "failed_jobs": failed_jobs,
                },
            )
            
        except Exception as e:
            return ComponentHealth(
                name="retraining_pipeline",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                response_time_ms=(time.time() - start) * 1000,
            )
    
    def _check_governance(self) -> ComponentHealth:
        """Check governance controller health"""
        start = time.time()
        
        try:
            stats = self.system.governance.get_governance_stats()
            response_time = (time.time() - start) * 1000
            
            issues = []
            status = HealthStatus.HEALTHY
            
            pending = stats["pending_count"]
            if pending > 10:
                issues.append(f"{pending} pending approvals")
                status = HealthStatus.DEGRADED
            
            expired = stats.get("expired", 0)
            if expired > 5:
                issues.append(f"{expired} expired approvals")
                status = HealthStatus.DEGRADED
            
            message = f"{pending} pending, {stats['total_processed']} processed"
            if issues:
                message = f"{message}; Issues: {'; '.join(issues)}"
            
            return ComponentHealth(
                name="governance",
                status=status,
                message=message,
                response_time_ms=response_time,
                details=stats,
            )
            
        except Exception as e:
            return ComponentHealth(
                name="governance",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                response_time_ms=(time.time() - start) * 1000,
            )
    
    def _check_metrics_collector(self) -> ComponentHealth:
        """Check metrics collector health"""
        start = time.time()
        
        try:
            n_series = len(self.metrics.series)
            n_alerts = len(self.metrics.active_alerts)
            firing = len(self.metrics.get_firing_alerts())
            response_time = (time.time() - start) * 1000
            
            status = HealthStatus.HEALTHY
            issues = []
            
            if firing > 0:
                issues.append(f"{firing} firing alerts")
                status = HealthStatus.DEGRADED
            
            message = f"{n_series} metric series, {n_alerts} active alerts"
            if issues:
                message = f"{message}; {'; '.join(issues)}"
            
            return ComponentHealth(
                name="metrics_collector",
                status=status,
                message=message,
                response_time_ms=response_time,
                details={
                    "metric_series": n_series,
                    "active_alerts": n_alerts,
                    "firing_alerts": firing,
                },
            )
            
        except Exception as e:
            return ComponentHealth(
                name="metrics_collector",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                response_time_ms=(time.time() - start) * 1000,
            )
    
    def check_component(self, component_name: str) -> Optional[ComponentHealth]:
        """Check a specific component"""
        check_methods = {
            "model_registry": self._check_model_registry,
            "ab_testing": self._check_ab_testing,
            "retraining_pipeline": self._check_retraining_pipeline,
            "governance": self._check_governance,
            "metrics_collector": self._check_metrics_collector,
        }
        
        if component_name in check_methods:
            return check_methods[component_name]()
        elif component_name in self._custom_checks:
            return self._custom_checks[component_name]()
        
        return None
    
    def is_healthy(self) -> bool:
        """Quick health check - returns True if system is healthy"""
        health = self.check_all()
        return health.overall_status == HealthStatus.HEALTHY
    
    def is_ready(self) -> bool:
        """Readiness check - returns True if system can accept traffic"""
        try:
            # Check if at least model registry is working
            registry_health = self._check_model_registry()
            return registry_health.status != HealthStatus.UNHEALTHY
        except:
            return False
    
    def is_live(self) -> bool:
        """Liveness check - returns True if system is alive"""
        return True  # If we can execute this, we're alive


class DiagnosticsRunner:
    """
    System diagnostics for troubleshooting.
    """
    
    def __init__(self, system: HVACRPdMSystem,
                 metrics: Optional[MetricsCollector] = None):
        self.system = system
        self.metrics = metrics or MetricsCollector()
    
    def run_full_diagnostics(self) -> Dict[str, Any]:
        """Run comprehensive system diagnostics"""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "system_status": self.system.get_system_status(),
            "model_summary": self._diagnose_models(),
            "experiment_summary": self._diagnose_experiments(),
            "retraining_summary": self._diagnose_retraining(),
            "governance_summary": self._diagnose_governance(),
            "metrics_summary": self._diagnose_metrics(),
            "recommendations": self._generate_recommendations(),
        }
    
    def _diagnose_models(self) -> Dict[str, Any]:
        """Diagnose model registry"""
        stats = self.system.model_registry.get_registry_stats()
        
        issues = []
        if stats["by_stage"].get("production", 0) == 0:
            issues.append("No models in production")
        
        stale_count = 0
        for model_name in self.system.model_registry.list_all_models():
            prod = self.system.model_registry.get_production_model(model_name)
            if prod and prod.deployed_at:
                age_days = (datetime.utcnow() - prod.deployed_at).days
                if age_days > 90:
                    stale_count += 1
        
        if stale_count > 0:
            issues.append(f"{stale_count} models deployed > 90 days ago")
        
        return {
            **stats,
            "issues": issues,
            "stale_models": stale_count,
        }
    
    def _diagnose_experiments(self) -> Dict[str, Any]:
        """Diagnose A/B testing"""
        active = list(self.system.ab_testing.active_experiments.values())
        all_exp = list(self.system.ab_testing.experiments.values())
        
        long_running = []
        for exp in active:
            if exp.actual_start:
                days = (datetime.utcnow() - exp.actual_start).days
                if days > exp.max_duration_days:
                    long_running.append(exp.experiment_id)
        
        return {
            "total_experiments": len(all_exp),
            "active_experiments": len(active),
            "long_running": long_running,
            "issues": [f"Experiment {eid} exceeds max duration" for eid in long_running],
        }
    
    def _diagnose_retraining(self) -> Dict[str, Any]:
        """Diagnose retraining pipeline"""
        jobs = list(self.system.retraining_pipeline.jobs.values())
        
        failed = [j for j in jobs if j.status == "failed"]
        pending = [j for j in jobs if j.status == "pending"]
        
        return {
            "total_jobs": len(jobs),
            "pending_jobs": len(pending),
            "failed_jobs": len(failed),
            "failed_job_ids": [j.job_id for j in failed[-5:]],  # Last 5
            "issues": [f"{len(failed)} failed retraining jobs"] if failed else [],
        }
    
    def _diagnose_governance(self) -> Dict[str, Any]:
        """Diagnose governance"""
        stats = self.system.governance.get_governance_stats()
        pending = self.system.governance.get_pending_approvals()
        
        urgent = [a for a in pending if a.expires_at and 
                 (a.expires_at - datetime.utcnow()).total_seconds() < 3600]
        
        return {
            **stats,
            "urgent_approvals": len(urgent),
            "issues": [f"{len(urgent)} approvals expiring within 1 hour"] if urgent else [],
        }
    
    def _diagnose_metrics(self) -> Dict[str, Any]:
        """Diagnose metrics collector"""
        firing = self.metrics.get_firing_alerts()
        
        return {
            "metric_series": len(self.metrics.series),
            "active_alerts": len(self.metrics.active_alerts),
            "firing_alerts": len(firing),
            "alert_rules": len(self.metrics.alert_rules),
            "issues": [f"{len(firing)} firing alerts"] if firing else [],
        }
    
    def _generate_recommendations(self) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []
        
        # Check models
        stats = self.system.model_registry.get_registry_stats()
        if stats["by_stage"].get("production", 0) == 0:
            recommendations.append("Deploy at least one model to production")
        
        # Check experiments
        active = list(self.system.ab_testing.active_experiments.values())
        for exp in active:
            if exp.actual_start:
                days = (datetime.utcnow() - exp.actual_start).days
                if days > 14:
                    recommendations.append(f"Review experiment {exp.experiment_id} - running for {days} days")
        
        # Check approvals
        pending = self.system.governance.get_pending_approvals()
        if len(pending) > 5:
            recommendations.append(f"Process pending approvals ({len(pending)} waiting)")
        
        # Check alerts
        firing = self.metrics.get_firing_alerts()
        if firing:
            recommendations.append(f"Investigate {len(firing)} firing alerts")
        
        # Check retraining
        failed = [j for j in self.system.retraining_pipeline.jobs.values() 
                 if j.status == "failed"]
        if failed:
            recommendations.append(f"Review {len(failed)} failed retraining jobs")
        
        if not recommendations:
            recommendations.append("System is healthy - no immediate actions required")
        
        return recommendations

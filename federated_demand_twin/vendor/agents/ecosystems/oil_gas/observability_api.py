"""
Phase 5: Observability & API Layer - REST API

REST API endpoints for HVACRPdMSystem operations.
Provides external access to model management, experiments, and monitoring.
"""

import logging
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional
from functools import wraps

from .learning_loop_hvacr import HVACRPdMSystem
from .learning_loop_models import (
    ModelType,
    ModelStage,
    ModelVersion,
    PerformanceMetrics,
    ExperimentStatus,
)
from .observability_metrics import MetricsCollector
from .observability_models import HealthStatus

logger = logging.getLogger(__name__)


class APIError(Exception):
    """API error with status code"""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class APIResponse:
    """Standard API response wrapper"""
    
    @staticmethod
    def success(data: Any = None, message: str = "Success") -> Dict[str, Any]:
        return {
            "success": True,
            "message": message,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    @staticmethod
    def error(message: str, status_code: int = 400, details: Any = None) -> Dict[str, Any]:
        return {
            "success": False,
            "message": message,
            "status_code": status_code,
            "details": details,
            "timestamp": datetime.utcnow().isoformat(),
        }


class HVACRPdMAPI:
    """
    REST API layer for HVACRPdMSystem.
    
    Provides endpoints for:
    - Model management (list, deploy, rollback)
    - A/B experiments (create, start, conclude)
    - Retraining (trigger, status)
    - Metrics and health
    """
    
    def __init__(self, system: HVACRPdMSystem, 
                 metrics_collector: Optional[MetricsCollector] = None):
        self.system = system
        self.metrics = metrics_collector or MetricsCollector()
        self._request_count = 0
        logger.info(f"HVACRPdMAPI initialized for site: {system.site_id}")
    
    def _validate_required(self, data: Dict, required_fields: List[str]):
        """Validate required fields in request"""
        missing = [f for f in required_fields if f not in data or data[f] is None]
        if missing:
            raise APIError(f"Missing required fields: {', '.join(missing)}")
    
    def _increment_request_count(self):
        """Track API requests"""
        self._request_count += 1
        self.metrics.increment("api_requests_total")
    
    # =========================================================================
    # Model Endpoints
    # =========================================================================
    
    def list_models(self, model_type: Optional[str] = None,
                    stage: Optional[str] = None) -> Dict[str, Any]:
        """
        GET /api/v1/models
        List all registered models with optional filters.
        """
        self._increment_request_count()
        
        try:
            models = []
            for model_name in self.system.model_registry.list_all_models():
                versions = self.system.model_registry.list_versions(model_name)
                
                for model in versions:
                    if model_type and model.model_type.value != model_type:
                        continue
                    if stage and model.stage.value != stage:
                        continue
                    
                    models.append({
                        "version_id": model.version_id,
                        "model_name": model.model_name,
                        "model_type": model.model_type.value,
                        "version_number": model.version_number,
                        "stage": model.stage.value,
                        "created_at": model.created_at.isoformat(),
                        "deployed_at": model.deployed_at.isoformat() if model.deployed_at else None,
                    })
            
            return APIResponse.success(models)
        except Exception as e:
            logger.error(f"Error listing models: {e}")
            return APIResponse.error(str(e), 500)
    
    def get_model(self, version_id: str) -> Dict[str, Any]:
        """
        GET /api/v1/models/{version_id}
        Get model details by version ID.
        """
        self._increment_request_count()
        
        model = self.system.model_registry.get_model(version_id)
        if not model:
            return APIResponse.error("Model not found", 404)
        
        return APIResponse.success(model.to_dict())
    
    def get_production_model(self, model_name: str) -> Dict[str, Any]:
        """
        GET /api/v1/models/production/{model_name}
        Get current production model for a model name.
        """
        self._increment_request_count()
        
        model = self.system.model_registry.get_production_model(model_name)
        if not model:
            return APIResponse.error(f"No production model for {model_name}", 404)
        
        return APIResponse.success(model.to_dict())
    
    def deploy_model(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        POST /api/v1/models/deploy
        Deploy a model to production.
        
        Body: {version_id, deployed_by, skip_approval?}
        """
        self._increment_request_count()
        
        try:
            self._validate_required(data, ["version_id", "deployed_by"])
            
            success, msg = self.system.deploy_model(
                version_id=data["version_id"],
                deployed_by=data["deployed_by"],
                skip_approval=data.get("skip_approval", False),
            )
            
            if success:
                self.metrics.increment("models_deployed_total")
                return APIResponse.success({"version_id": data["version_id"]}, msg)
            else:
                return APIResponse.error(msg, 400)
                
        except APIError as e:
            return APIResponse.error(e.message, e.status_code)
        except Exception as e:
            logger.error(f"Error deploying model: {e}")
            return APIResponse.error(str(e), 500)
    
    def rollback_model(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        POST /api/v1/models/rollback
        Rollback to previous model version.
        
        Body: {model_name, reason, rolled_back_by}
        """
        self._increment_request_count()
        
        try:
            self._validate_required(data, ["model_name", "reason", "rolled_back_by"])
            
            success, msg = self.system.rollback_model(
                model_name=data["model_name"],
                reason=data["reason"],
                rolled_back_by=data["rolled_back_by"],
            )
            
            if success:
                self.metrics.increment("models_rolled_back_total")
                return APIResponse.success(None, msg)
            else:
                return APIResponse.error(msg, 400)
                
        except APIError as e:
            return APIResponse.error(e.message, e.status_code)
        except Exception as e:
            logger.error(f"Error rolling back model: {e}")
            return APIResponse.error(str(e), 500)
    
    def get_model_health(self, model_name: str) -> Dict[str, Any]:
        """
        GET /api/v1/models/{model_name}/health
        Get health status for a model.
        """
        self._increment_request_count()
        
        health = self.system.get_model_health(model_name)
        return APIResponse.success(health)
    
    # =========================================================================
    # Experiment Endpoints
    # =========================================================================
    
    def list_experiments(self, status: Optional[str] = None) -> Dict[str, Any]:
        """
        GET /api/v1/experiments
        List all experiments with optional status filter.
        """
        self._increment_request_count()
        
        try:
            status_filter = ExperimentStatus(status) if status else None
            experiments = self.system.ab_testing.list_experiments(status=status_filter)
            
            result = []
            for exp in experiments:
                result.append({
                    "experiment_id": exp.experiment_id,
                    "experiment_name": exp.experiment_name,
                    "model_type": exp.model_type.value,
                    "status": exp.status.value,
                    "created_at": exp.created_at.isoformat(),
                    "n_variants": len(exp.variants),
                })
            
            return APIResponse.success(result)
        except Exception as e:
            logger.error(f"Error listing experiments: {e}")
            return APIResponse.error(str(e), 500)
    
    def get_experiment(self, experiment_id: str) -> Dict[str, Any]:
        """
        GET /api/v1/experiments/{experiment_id}
        Get experiment details.
        """
        self._increment_request_count()
        
        exp = self.system.ab_testing.get_experiment(experiment_id)
        if not exp:
            return APIResponse.error("Experiment not found", 404)
        
        return APIResponse.success({
            "experiment_id": exp.experiment_id,
            "experiment_name": exp.experiment_name,
            "description": exp.description,
            "model_type": exp.model_type.value,
            "status": exp.status.value,
            "variants": [
                {
                    "variant_id": v.variant_id,
                    "variant_name": v.variant_name,
                    "model_version_id": v.model_version_id,
                    "traffic_percentage": v.traffic_percentage,
                    "is_control": v.is_control,
                    "n_predictions": v.n_predictions,
                }
                for v in exp.variants
            ],
            "created_at": exp.created_at.isoformat(),
            "winner_variant_id": exp.winner_variant_id,
        })
    
    def create_experiment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        POST /api/v1/experiments
        Create a new A/B experiment.
        
        Body: {name, description, model_type, control_version_id, 
               treatment_version_id, control_traffic_pct?, created_by}
        """
        self._increment_request_count()
        
        try:
            self._validate_required(data, [
                "name", "model_type", "control_version_id", 
                "treatment_version_id", "created_by"
            ])
            
            model_type = ModelType(data["model_type"])
            
            success, result = self.system.create_ab_test(
                name=data["name"],
                description=data.get("description", ""),
                model_type=model_type,
                control_version_id=data["control_version_id"],
                treatment_version_id=data["treatment_version_id"],
                control_traffic_pct=data.get("control_traffic_pct", 50.0),
                created_by=data["created_by"],
            )
            
            if success:
                self.metrics.increment("experiments_created_total")
                return APIResponse.success({"experiment_id": result}, "Experiment created")
            else:
                return APIResponse.error(result, 400)
                
        except ValueError as e:
            return APIResponse.error(f"Invalid model_type: {e}", 400)
        except APIError as e:
            return APIResponse.error(e.message, e.status_code)
        except Exception as e:
            logger.error(f"Error creating experiment: {e}")
            return APIResponse.error(str(e), 500)
    
    def start_experiment(self, experiment_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        POST /api/v1/experiments/{experiment_id}/start
        Start an experiment.
        
        Body: {started_by}
        """
        self._increment_request_count()
        
        try:
            self._validate_required(data, ["started_by"])
            
            success, msg = self.system.start_ab_test(
                experiment_id=experiment_id,
                started_by=data["started_by"],
            )
            
            if success:
                self.metrics.increment("experiments_started_total")
                return APIResponse.success(None, msg)
            else:
                return APIResponse.error(msg, 400)
                
        except APIError as e:
            return APIResponse.error(e.message, e.status_code)
        except Exception as e:
            logger.error(f"Error starting experiment: {e}")
            return APIResponse.error(str(e), 500)
    
    def conclude_experiment(self, experiment_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        POST /api/v1/experiments/{experiment_id}/conclude
        Conclude an experiment.
        
        Body: {concluded_by, promote_winner?}
        """
        self._increment_request_count()
        
        try:
            self._validate_required(data, ["concluded_by"])
            
            success, msg = self.system.conclude_ab_test(
                experiment_id=experiment_id,
                concluded_by=data["concluded_by"],
                promote_winner=data.get("promote_winner", False),
            )
            
            if success:
                self.metrics.increment("experiments_concluded_total")
                return APIResponse.success(None, msg)
            else:
                return APIResponse.error(msg, 400)
                
        except APIError as e:
            return APIResponse.error(e.message, e.status_code)
        except Exception as e:
            logger.error(f"Error concluding experiment: {e}")
            return APIResponse.error(str(e), 500)
    
    def get_experiment_stats(self, experiment_id: str) -> Dict[str, Any]:
        """
        GET /api/v1/experiments/{experiment_id}/stats
        Get experiment statistics.
        """
        self._increment_request_count()
        
        stats = self.system.get_ab_test_status(experiment_id)
        if "error" in stats:
            return APIResponse.error(stats["error"], 404)
        
        return APIResponse.success(stats)
    
    # =========================================================================
    # Retraining Endpoints
    # =========================================================================
    
    def list_retraining_jobs(self, model_name: Optional[str] = None,
                              status: Optional[str] = None) -> Dict[str, Any]:
        """
        GET /api/v1/retraining/jobs
        List retraining jobs.
        """
        self._increment_request_count()
        
        jobs = self.system.retraining_pipeline.list_jobs(
            model_name=model_name,
            status=status,
        )
        
        result = []
        for job in jobs:
            result.append({
                "job_id": job.job_id,
                "model_name": job.model_name,
                "trigger_type": job.trigger_type.value,
                "status": job.status,
                "created_at": job.created_at.isoformat(),
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "improvement_detected": job.improvement_detected,
            })
        
        return APIResponse.success(result)
    
    def trigger_retraining(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        POST /api/v1/retraining/trigger
        Manually trigger retraining.
        
        Body: {model_name, triggered_by}
        """
        self._increment_request_count()
        
        try:
            self._validate_required(data, ["model_name", "triggered_by"])
            
            success, job_id = self.system.trigger_manual_retrain(
                model_name=data["model_name"],
                triggered_by=data["triggered_by"],
            )
            
            if success:
                self.metrics.record_retraining_trigger(data["model_name"], "manual")
                return APIResponse.success({"job_id": job_id}, "Retraining job created")
            else:
                return APIResponse.error(job_id, 400)
                
        except APIError as e:
            return APIResponse.error(e.message, e.status_code)
        except Exception as e:
            logger.error(f"Error triggering retraining: {e}")
            return APIResponse.error(str(e), 500)
    
    def get_trigger_status(self) -> Dict[str, Any]:
        """
        GET /api/v1/retraining/triggers
        Get status of all retraining triggers.
        """
        self._increment_request_count()
        
        triggers = self.system.retraining_pipeline.get_trigger_status()
        return APIResponse.success(triggers)
    
    # =========================================================================
    # Governance Endpoints
    # =========================================================================
    
    def list_pending_approvals(self) -> Dict[str, Any]:
        """
        GET /api/v1/governance/approvals/pending
        List pending approvals.
        """
        self._increment_request_count()
        
        approvals = self.system.governance.get_pending_approvals()
        
        result = []
        for approval in approvals:
            result.append({
                "approval_id": approval.approval_id,
                "action_type": approval.action_type.value,
                "target_id": approval.target_id,
                "target_type": approval.target_type,
                "requested_by": approval.requested_by,
                "requested_at": approval.requested_at.isoformat(),
                "risk_level": approval.risk_level,
                "expires_at": approval.expires_at.isoformat() if approval.expires_at else None,
            })
        
        return APIResponse.success(result)
    
    def process_approval(self, approval_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        POST /api/v1/governance/approvals/{approval_id}
        Process an approval decision.
        
        Body: {approved, reviewer, notes?}
        """
        self._increment_request_count()
        
        try:
            self._validate_required(data, ["approved", "reviewer"])
            
            success, msg = self.system.governance.process_approval(
                approval_id=approval_id,
                approved=data["approved"],
                reviewer=data["reviewer"],
                notes=data.get("notes", ""),
            )
            
            if success:
                return APIResponse.success(None, msg)
            else:
                return APIResponse.error(msg, 400)
                
        except APIError as e:
            return APIResponse.error(e.message, e.status_code)
        except Exception as e:
            logger.error(f"Error processing approval: {e}")
            return APIResponse.error(str(e), 500)
    
    # =========================================================================
    # Metrics & Health Endpoints
    # =========================================================================
    
    def get_metrics_prometheus(self) -> str:
        """
        GET /api/v1/metrics
        Export metrics in Prometheus format.
        """
        self._increment_request_count()
        return self.metrics.export_prometheus()
    
    def get_metrics_json(self) -> Dict[str, Any]:
        """
        GET /api/v1/metrics/json
        Export metrics as JSON.
        """
        self._increment_request_count()
        return APIResponse.success(self.metrics.export_json())
    
    def get_dashboard(self) -> Dict[str, Any]:
        """
        GET /api/v1/dashboard
        Get dashboard summary.
        """
        self._increment_request_count()
        
        dashboard = self.metrics.get_dashboard_summary()
        system_status = self.system.get_system_status()
        
        dashboard["system"] = system_status
        return APIResponse.success(dashboard)
    
    def get_health(self) -> Dict[str, Any]:
        """
        GET /api/v1/health
        Health check endpoint.
        """
        return APIResponse.success({
            "status": "healthy",
            "site_id": self.system.site_id,
            "uptime_seconds": self.metrics.get_uptime_seconds(),
            "request_count": self._request_count,
        })
    
    def get_health_detailed(self) -> Dict[str, Any]:
        """
        GET /api/v1/health/detailed
        Detailed health check with component status.
        """
        self._increment_request_count()
        
        from .observability_health import HealthChecker
        checker = HealthChecker(self.system, self.metrics)
        health = checker.check_all()
        
        return APIResponse.success(health.to_dict())
    
    # =========================================================================
    # Alerts Endpoints
    # =========================================================================
    
    def get_active_alerts(self) -> Dict[str, Any]:
        """
        GET /api/v1/alerts
        Get active alerts.
        """
        self._increment_request_count()
        
        alerts = self.metrics.get_active_alerts()
        return APIResponse.success([a.to_dict() for a in alerts])
    
    def acknowledge_alert(self, alert_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        POST /api/v1/alerts/{alert_id}/acknowledge
        Acknowledge an alert.
        
        Body: {user_id}
        """
        self._increment_request_count()
        
        try:
            self._validate_required(data, ["user_id"])
            
            success = self.metrics.acknowledge_alert(alert_id, data["user_id"])
            
            if success:
                return APIResponse.success(None, "Alert acknowledged")
            else:
                return APIResponse.error("Alert not found", 404)
                
        except APIError as e:
            return APIResponse.error(e.message, e.status_code)
    
    def silence_alert(self, alert_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        POST /api/v1/alerts/{alert_id}/silence
        Silence an alert.
        
        Body: {duration_minutes}
        """
        self._increment_request_count()
        
        try:
            self._validate_required(data, ["duration_minutes"])
            
            success = self.metrics.silence_alert(alert_id, data["duration_minutes"])
            
            if success:
                return APIResponse.success(None, f"Alert silenced for {data['duration_minutes']} minutes")
            else:
                return APIResponse.error("Alert not found", 404)
                
        except APIError as e:
            return APIResponse.error(e.message, e.status_code)

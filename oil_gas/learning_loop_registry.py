"""
ML Learning Loop - Model Registry

Model versioning and registry with lineage tracking.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .learning_loop_models import (
    ApprovalStatus,
    ModelStage,
    ModelType,
    ModelVersion,
    PerformanceMetrics,
)
from .governance import AuditLogger

logger = logging.getLogger(__name__)


class ModelRegistry:
    """
    Central registry for model versions with versioning and lineage.
    """
    
    def __init__(self, audit_logger: Optional[AuditLogger] = None):
        self.models: Dict[str, Dict[str, ModelVersion]] = {}
        self.audit_logger = audit_logger or AuditLogger()
        self._version_index: Dict[str, ModelVersion] = {}
    
    def register_model(self, model: ModelVersion) -> str:
        """Register a new model version"""
        if model.model_name not in self.models:
            self.models[model.model_name] = {}
        
        self.models[model.model_name][model.version_id] = model
        self._version_index[model.version_id] = model
        
        self.audit_logger.log(
            action_type="model_registered",
            actor_id=model.created_by,
            parameters={
                "model_name": model.model_name,
                "version_id": model.version_id,
                "version_number": model.version_number,
            },
        )
        
        logger.info(f"Registered model: {model.model_name} v{model.version_number}")
        return model.version_id
    
    def get_model(self, version_id: str) -> Optional[ModelVersion]:
        """Get model by version ID"""
        return self._version_index.get(version_id)
    
    def get_model_by_name_version(self, model_name: str, version_number: str) -> Optional[ModelVersion]:
        """Get model by name and version number"""
        if model_name not in self.models:
            return None
        for model in self.models[model_name].values():
            if model.version_number == version_number:
                return model
        return None
    
    def get_latest_version(self, model_name: str, stage: Optional[ModelStage] = None) -> Optional[ModelVersion]:
        """Get the latest version of a model, optionally filtered by stage"""
        if model_name not in self.models:
            return None
        
        versions = list(self.models[model_name].values())
        if stage:
            versions = [v for v in versions if v.stage == stage]
        
        if not versions:
            return None
        
        versions.sort(key=lambda v: tuple(map(int, v.version_number.split("."))), reverse=True)
        return versions[0]
    
    def get_production_model(self, model_name: str) -> Optional[ModelVersion]:
        """Get the current production model"""
        return self.get_latest_version(model_name, ModelStage.PRODUCTION)
    
    def list_versions(self, model_name: str, 
                      stage: Optional[ModelStage] = None,
                      limit: int = 10) -> List[ModelVersion]:
        """List model versions with optional filters"""
        if model_name not in self.models:
            return []
        
        versions = list(self.models[model_name].values())
        if stage:
            versions = [v for v in versions if v.stage == stage]
        
        versions.sort(key=lambda v: v.created_at, reverse=True)
        return versions[:limit]
    
    def list_all_models(self) -> List[str]:
        """List all registered model names"""
        return list(self.models.keys())
    
    def promote_model(self, version_id: str, target_stage: ModelStage, 
                      promoted_by: str) -> Tuple[bool, str]:
        """Promote a model to a new stage"""
        model = self.get_model(version_id)
        if not model:
            return False, "Model not found"
        
        valid_transitions = {
            ModelStage.DEVELOPMENT: [ModelStage.STAGING],
            ModelStage.STAGING: [ModelStage.CANARY, ModelStage.PRODUCTION],
            ModelStage.CANARY: [ModelStage.PRODUCTION, ModelStage.STAGING],
            ModelStage.PRODUCTION: [ModelStage.ARCHIVED],
            ModelStage.ARCHIVED: [ModelStage.ROLLBACK],
            ModelStage.ROLLBACK: [ModelStage.PRODUCTION],
        }
        
        if target_stage not in valid_transitions.get(model.stage, []):
            return False, f"Invalid transition: {model.stage.value} → {target_stage.value}"
        
        old_stage = model.stage
        
        # Check for existing production model BEFORE changing stage
        old_prod = None
        if target_stage == ModelStage.PRODUCTION:
            old_prod = self.get_production_model(model.model_name)
        
        model.stage = target_stage
        
        if target_stage == ModelStage.PRODUCTION:
            if old_prod and old_prod.version_id != version_id:
                old_prod.stage = ModelStage.ARCHIVED
                model.can_rollback_to.append(old_prod.version_id)
            
            model.deployed_at = datetime.utcnow()
            model.deployed_by = promoted_by
        
        self.audit_logger.log(
            action_type="model_promoted",
            actor_id=promoted_by,
            parameters={
                "version_id": version_id,
                "from_stage": old_stage.value,
                "to_stage": target_stage.value,
            },
        )
        
        logger.info(f"Promoted {model.model_name} v{model.version_number}: {old_stage.value} → {target_stage.value}")
        return True, "Success"
    
    def rollback_model(self, model_name: str, target_version_id: str,
                       rolled_back_by: str, reason: str) -> Tuple[bool, str]:
        """Rollback to a previous model version"""
        current_prod = self.get_production_model(model_name)
        target = self.get_model(target_version_id)
        
        if not target:
            return False, "Target version not found"
        
        if current_prod and target_version_id not in current_prod.can_rollback_to:
            return False, "Target version not in rollback list"
        
        if current_prod:
            current_prod.stage = ModelStage.ARCHIVED
        
        target.stage = ModelStage.PRODUCTION
        target.rolled_back_from = current_prod.version_id if current_prod else None
        target.deployed_at = datetime.utcnow()
        target.deployed_by = rolled_back_by
        
        self.audit_logger.log(
            action_type="model_rollback",
            actor_id=rolled_back_by,
            parameters={
                "model_name": model_name,
                "from_version": current_prod.version_id if current_prod else None,
                "to_version": target_version_id,
                "reason": reason,
            },
        )
        
        logger.warning(f"Rollback: {model_name} → v{target.version_number}. Reason: {reason}")
        return True, "Rollback successful"
    
    def compare_versions(self, version_id_a: str, version_id_b: str) -> Dict[str, Any]:
        """Compare two model versions"""
        model_a = self.get_model(version_id_a)
        model_b = self.get_model(version_id_b)
        
        if not model_a or not model_b:
            return {"error": "One or both versions not found"}
        
        comparison = {
            "version_a": model_a.to_dict(),
            "version_b": model_b.to_dict(),
            "hyperparameter_diff": {},
            "metrics_comparison": {},
        }
        
        all_keys = set(model_a.hyperparameters.keys()) | set(model_b.hyperparameters.keys())
        for key in all_keys:
            val_a = model_a.hyperparameters.get(key)
            val_b = model_b.hyperparameters.get(key)
            if val_a != val_b:
                comparison["hyperparameter_diff"][key] = {"a": val_a, "b": val_b}
        
        if model_a.validation_metrics and model_b.validation_metrics:
            comparison["metrics_comparison"] = {
                "accuracy": {
                    "a": model_a.validation_metrics.accuracy,
                    "b": model_b.validation_metrics.accuracy,
                },
                "f1_score": {
                    "a": model_a.validation_metrics.f1_score,
                    "b": model_b.validation_metrics.f1_score,
                },
            }
        
        return comparison
    
    def update_production_metrics(self, version_id: str, metrics: PerformanceMetrics):
        """Update production metrics for a deployed model"""
        model = self.get_model(version_id)
        if model:
            model.production_metrics = metrics
            logger.info(f"Updated production metrics for {model.model_name} v{model.version_number}")
    
    def get_model_lineage(self, version_id: str) -> List[ModelVersion]:
        """Get the lineage chain for a model version"""
        lineage = []
        current = self.get_model(version_id)
        
        while current:
            lineage.append(current)
            if current.parent_version_id:
                current = self.get_model(current.parent_version_id)
            else:
                break
        
        return lineage
    
    def search_models(self, model_type: Optional[ModelType] = None,
                      stage: Optional[ModelStage] = None,
                      tags: Optional[List[str]] = None,
                      created_after: Optional[datetime] = None) -> List[ModelVersion]:
        """Search models with filters"""
        results = []
        
        for model_dict in self.models.values():
            for model in model_dict.values():
                if model_type and model.model_type != model_type:
                    continue
                if stage and model.stage != stage:
                    continue
                if tags and not all(t in model.tags for t in tags):
                    continue
                if created_after and model.created_at < created_after:
                    continue
                results.append(model)
        
        results.sort(key=lambda m: m.created_at, reverse=True)
        return results
    
    def get_registry_stats(self) -> Dict[str, Any]:
        """Get registry statistics"""
        all_models = list(self._version_index.values())
        
        return {
            "total_models": len(self.models),
            "total_versions": len(all_models),
            "by_stage": {
                stage.value: len([m for m in all_models if m.stage == stage])
                for stage in ModelStage
            },
            "by_type": {
                mt.value: len([m for m in all_models if m.model_type == mt])
                for mt in ModelType
            },
            "production_models": [
                {"name": name, "version": self.get_production_model(name).version_number if self.get_production_model(name) else None}
                for name in self.models.keys()
            ],
        }

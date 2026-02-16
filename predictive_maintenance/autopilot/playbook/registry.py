"""
Playbook Registry

Manages playbook lifecycle: CRUD, versioning, and matching.
"""

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from .schema import PlaybookDefinition
from .parser import PlaybookParser, PlaybookValidationError
from .expressions import ExpressionEvaluator, EvalContext
from ..models import PlaybookModel, PlaybookVersionModel
from ..repositories import PlaybookRepository, PlaybookVersionRepository

logger = logging.getLogger(__name__)


class PlaybookRegistry:
    """
    Registry for playbook management.
    
    Responsibilities:
    - CRUD operations with versioning
    - Playbook matching based on asset class, fault type, and context
    - Version history and audit trail
    - Expression validation
    """
    
    def __init__(self, session_factory: Callable[[], Session]):
        """
        Initialize registry.
        
        Args:
            session_factory: Factory function to create database sessions
        """
        self.session_factory = session_factory
        self.parser = PlaybookParser(strict=False)
        self.evaluator = ExpressionEvaluator()
    
    def create(
        self,
        definition: Dict[str, Any],
        created_by: str = "system",
    ) -> Tuple[str, str]:
        """
        Create a new playbook.
        
        Args:
            definition: Playbook definition dictionary
            created_by: User/system creating the playbook
            
        Returns:
            (playbook_id, version)
            
        Raises:
            PlaybookValidationError: If validation fails
        """
        # Validate and parse
        playbook = self.parser.parse_dict(definition)
        content_hash = self.parser.compute_hash(definition)
        
        session = self.session_factory()
        try:
            playbook_repo = PlaybookRepository(session)
            version_repo = PlaybookVersionRepository(session)
            
            # Check if playbook already exists
            existing = playbook_repo.get_by_id(playbook.id)
            if existing:
                raise PlaybookValidationError(
                    f"Playbook {playbook.id} already exists. Use update() to create new version."
                )
            
            # Create playbook
            playbook_model = playbook_repo.create(
                playbook_id=playbook.id,
                name=playbook.name,
                asset_class=playbook.asset_class,
                fault_type=playbook.fault_type,
                risk_tier=playbook.risk_tier,
                description=playbook.description,
            )
            
            # Create initial version
            version_repo.create(
                playbook_id=playbook.id,
                version=playbook.version,
                definition=definition,
                content_hash=content_hash,
                created_by=created_by,
            )
            
            session.commit()
            
            logger.info(f"Created playbook {playbook.id} version {playbook.version}")
            return playbook.id, playbook.version
            
        except PlaybookValidationError:
            session.rollback()
            raise
        except Exception as e:
            session.rollback()
            raise PlaybookValidationError(f"Failed to create playbook: {e}")
        finally:
            session.close()
    
    def update(
        self,
        playbook_id: str,
        definition: Dict[str, Any],
        created_by: str = "system",
    ) -> str:
        """
        Create a new version of an existing playbook.
        
        The old version remains for audit; this creates a new version.
        
        Args:
            playbook_id: ID of playbook to update
            definition: New playbook definition
            created_by: User/system updating the playbook
            
        Returns:
            New version string
            
        Raises:
            PlaybookValidationError: If validation fails or playbook not found
        """
        # Validate and parse
        playbook = self.parser.parse_dict(definition)
        content_hash = self.parser.compute_hash(definition)
        
        # Ensure IDs match
        if playbook.id != playbook_id:
            raise PlaybookValidationError(
                f"Playbook ID in definition ({playbook.id}) does not match "
                f"requested update ID ({playbook_id})"
            )
        
        session = self.session_factory()
        try:
            playbook_repo = PlaybookRepository(session)
            version_repo = PlaybookVersionRepository(session)
            
            # Check playbook exists
            existing = playbook_repo.get_by_id(playbook_id)
            if not existing:
                raise PlaybookValidationError(f"Playbook {playbook_id} not found")
            
            # Check version doesn't already exist
            existing_version = version_repo.get_version(playbook_id, playbook.version)
            if existing_version:
                raise PlaybookValidationError(
                    f"Version {playbook.version} already exists for playbook {playbook_id}"
                )
            
            # Create new version
            version_repo.create(
                playbook_id=playbook_id,
                version=playbook.version,
                definition=definition,
                content_hash=content_hash,
                created_by=created_by,
            )
            
            # Update playbook metadata
            existing.name = playbook.name
            existing.asset_class = playbook.asset_class
            existing.fault_type = playbook.fault_type
            existing.risk_tier = playbook.risk_tier
            existing.description = playbook.description
            existing.current_version = playbook.version
            existing.updated_at = datetime.utcnow()
            
            session.commit()
            
            logger.info(f"Updated playbook {playbook_id} to version {playbook.version}")
            return playbook.version
            
        except PlaybookValidationError:
            session.rollback()
            raise
        except Exception as e:
            session.rollback()
            raise PlaybookValidationError(f"Failed to update playbook: {e}")
        finally:
            session.close()
    
    def retire(self, playbook_id: str) -> bool:
        """
        Retire a playbook (mark inactive, don't delete).
        
        Args:
            playbook_id: ID of playbook to retire
            
        Returns:
            True if retired, False if not found
        """
        session = self.session_factory()
        try:
            repo = PlaybookRepository(session)
            result = repo.retire(playbook_id)
            session.commit()
            
            if result:
                logger.info(f"Retired playbook {playbook_id}")
            
            return result
        finally:
            session.close()
    
    def get(self, playbook_id: str, version: str = None) -> Optional[PlaybookDefinition]:
        """
        Get a playbook definition.
        
        Args:
            playbook_id: Playbook ID
            version: Specific version (None for latest)
            
        Returns:
            PlaybookDefinition or None if not found
        """
        session = self.session_factory()
        try:
            version_repo = PlaybookVersionRepository(session)
            
            if version:
                version_model = version_repo.get_version(playbook_id, version)
            else:
                version_model = version_repo.get_latest(playbook_id)
            
            if not version_model:
                return None
            
            return PlaybookDefinition.from_dict(version_model.definition)
        finally:
            session.close()
    
    def list(
        self,
        asset_class: str = None,
        fault_type: str = None,
        risk_tier: str = None,
        active_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        List playbooks with optional filtering.
        
        Returns list of playbook summaries (not full definitions).
        """
        session = self.session_factory()
        try:
            repo = PlaybookRepository(session)
            playbooks = repo.list_active(
                asset_class=asset_class,
                fault_type=fault_type,
                risk_tier=risk_tier,
            ) if active_only else []
            
            return [
                {
                    "playbook_id": p.playbook_id,
                    "name": p.name,
                    "asset_class": p.asset_class,
                    "fault_type": p.fault_type,
                    "risk_tier": p.risk_tier,
                    "current_version": p.current_version,
                    "is_active": p.is_active,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                }
                for p in playbooks
            ]
        finally:
            session.close()
    
    def list_versions(self, playbook_id: str) -> List[Dict[str, Any]]:
        """List all versions of a playbook"""
        session = self.session_factory()
        try:
            repo = PlaybookVersionRepository(session)
            versions = repo.list_versions(playbook_id)
            
            return [
                {
                    "version": v.version,
                    "content_hash": v.content_hash,
                    "effective_from": v.effective_from.isoformat() if v.effective_from else None,
                    "retired_at": v.retired_at.isoformat() if v.retired_at else None,
                    "created_at": v.created_at.isoformat() if v.created_at else None,
                    "created_by": v.created_by,
                }
                for v in versions
            ]
        finally:
            session.close()
    
    def match(
        self,
        asset_class: str,
        fault_type: str,
        context: EvalContext = None,
    ) -> List[Tuple[PlaybookDefinition, str]]:
        """
        Find playbooks matching the given criteria.
        
        Args:
            asset_class: Asset class to match
            fault_type: Fault type to match
            context: Optional evaluation context for trigger matching
            
        Returns:
            List of (playbook, match_reason) tuples, sorted by specificity
        """
        session = self.session_factory()
        try:
            repo = PlaybookRepository(session)
            version_repo = PlaybookVersionRepository(session)
            
            matches = []
            
            # Get playbooks matching asset_class and fault_type
            candidates = repo.list_active(asset_class=asset_class, fault_type=fault_type)
            
            for pb_model in candidates:
                version_model = version_repo.get_latest(pb_model.playbook_id)
                if not version_model:
                    continue
                
                playbook = PlaybookDefinition.from_dict(version_model.definition)
                match_reason = f"Matched asset_class={asset_class}, fault_type={fault_type}"
                
                # Evaluate triggers if context provided
                if context and playbook.triggers:
                    all_triggers_pass = True
                    for trigger in playbook.triggers:
                        try:
                            result = self.evaluator.evaluate(trigger.expr, context)
                            if not result:
                                all_triggers_pass = False
                                break
                        except Exception as e:
                            logger.warning(f"Trigger evaluation failed: {e}")
                            all_triggers_pass = False
                            break
                    
                    if not all_triggers_pass:
                        continue
                    
                    match_reason += " (triggers passed)"
                
                matches.append((playbook, match_reason))
            
            # Also check for asset_class-only matches (less specific)
            if not matches:
                candidates = repo.list_active(asset_class=asset_class)
                for pb_model in candidates:
                    if pb_model.fault_type != fault_type:
                        version_model = version_repo.get_latest(pb_model.playbook_id)
                        if version_model:
                            playbook = PlaybookDefinition.from_dict(version_model.definition)
                            matches.append((
                                playbook,
                                f"Partial match: asset_class={asset_class}"
                            ))
            
            return matches
        finally:
            session.close()
    
    def check_preconditions(
        self,
        playbook: PlaybookDefinition,
        context: EvalContext,
    ) -> Tuple[bool, List[str]]:
        """
        Check if all preconditions are met.
        
        Args:
            playbook: Playbook to check
            context: Evaluation context
            
        Returns:
            (all_passed, list of failure messages)
        """
        failures = []
        
        for precondition in playbook.preconditions:
            try:
                result = self.evaluator.evaluate(precondition.expr, context)
                if not result:
                    failures.append(
                        f"Precondition failed: {precondition.description or precondition.expr}"
                    )
            except Exception as e:
                failures.append(f"Precondition evaluation error: {e}")
        
        return len(failures) == 0, failures
    
    def validate_definition(self, definition: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate a playbook definition without persisting.
        
        Returns:
            (is_valid, list of error messages)
        """
        try:
            self.parser.parse_dict(definition)
            return True, []
        except PlaybookValidationError as e:
            return False, e.errors


def get_playbook_registry(session_factory: Callable[[], Session]) -> PlaybookRegistry:
    """Factory function to create PlaybookRegistry"""
    return PlaybookRegistry(session_factory)

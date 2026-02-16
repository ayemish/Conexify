"""
Checkpoint Manager

Manages durable workflow checkpoints for:
- Pause/resume execution
- Human approval interrupts
- Replay from any point for debugging/audit
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
import uuid

from sqlalchemy.orm import Session

from ..models import CheckpointModel, AutopilotRunModel
from ..repositories import CheckpointRepository, AutopilotRunRepository
from ..schemas import RunStatus

logger = logging.getLogger(__name__)


@dataclass
class CheckpointState:
    """
    Serializable state for a checkpoint.
    
    Contains everything needed to resume execution from this point.
    """
    run_id: str
    thread_id: str
    step_index: int
    run_status: str
    
    # Step results so far
    step_results: Dict[str, Any] = field(default_factory=dict)
    
    # Current context
    points: Dict[str, float] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)
    
    # Approval state
    pending_approval_id: Optional[str] = None
    approval_decision: Optional[str] = None
    edited_params: Dict[str, Any] = field(default_factory=dict)
    
    # Actions taken
    actions_taken: List[Dict[str, Any]] = field(default_factory=list)
    
    # Errors encountered
    errors: List[str] = field(default_factory=list)
    
    # Metadata
    created_at: str = ""
    reason: str = ""
    
    def to_json(self) -> str:
        """Serialize to JSON"""
        data = asdict(self)
        return json.dumps(data, default=str)
    
    @classmethod
    def from_json(cls, json_str: str) -> "CheckpointState":
        """Deserialize from JSON"""
        data = json.loads(json_str)
        return cls(**data)
    
    def clone(self) -> "CheckpointState":
        """Create a deep copy"""
        return CheckpointState.from_json(self.to_json())


class CheckpointManager:
    """
    Manages checkpoint lifecycle for autopilot runs.
    
    Provides:
    - Create checkpoints at key execution points
    - Resume from checkpoints
    - Replay from any historical checkpoint
    - Checkpoint history for audit
    """
    
    def __init__(self, session_factory: Callable[[], Session]):
        self.session_factory = session_factory
    
    def create(
        self,
        state: CheckpointState,
        reason: str = "",
        parent_checkpoint_id: Optional[str] = None,
    ) -> str:
        """
        Create a new checkpoint.
        
        Args:
            state: Current execution state
            reason: Why checkpoint was created (e.g., "approval_pending", "step_completed")
            parent_checkpoint_id: ID of parent checkpoint for replay tracking
            
        Returns:
            Checkpoint ID
        """
        checkpoint_id = f"CHK-{uuid.uuid4().hex[:12].upper()}"
        state.created_at = datetime.utcnow().isoformat()
        state.reason = reason
        
        session = self.session_factory()
        try:
            repo = CheckpointRepository(session)
            run_repo = AutopilotRunRepository(session)
            
            repo.create(
                checkpoint_id=checkpoint_id,
                run_id=state.run_id,
                thread_id=state.thread_id,
                step_index=state.step_index,
                run_status=state.run_status,
                state_json=state.to_json(),
                reason=reason,
                parent_checkpoint_id=parent_checkpoint_id,
            )
            
            # Update run with current checkpoint
            run_repo.set_checkpoint(state.run_id, checkpoint_id)
            
            session.commit()
            
            logger.info(
                f"Created checkpoint {checkpoint_id} for run {state.run_id} "
                f"at step {state.step_index} (reason: {reason})"
            )
            
            return checkpoint_id
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create checkpoint: {e}")
            raise
        finally:
            session.close()
    
    def get(self, checkpoint_id: str) -> Optional[CheckpointState]:
        """
        Get a checkpoint by ID.
        
        Returns:
            CheckpointState or None if not found
        """
        session = self.session_factory()
        try:
            repo = CheckpointRepository(session)
            checkpoint = repo.get_by_id(checkpoint_id)
            
            if not checkpoint:
                return None
            
            return CheckpointState.from_json(checkpoint.state_json)
        finally:
            session.close()
    
    def get_latest(self, run_id: str) -> Optional[CheckpointState]:
        """
        Get the latest checkpoint for a run.
        
        Returns:
            CheckpointState or None if no checkpoints
        """
        session = self.session_factory()
        try:
            repo = CheckpointRepository(session)
            checkpoint = repo.get_latest(run_id)
            
            if not checkpoint:
                return None
            
            return CheckpointState.from_json(checkpoint.state_json)
        finally:
            session.close()
    
    def list_for_run(self, run_id: str) -> List[Dict[str, Any]]:
        """
        List all checkpoints for a run (for audit/replay).
        
        Returns:
            List of checkpoint summaries
        """
        session = self.session_factory()
        try:
            repo = CheckpointRepository(session)
            checkpoints = repo.list_for_run(run_id)
            
            return [
                {
                    "checkpoint_id": c.checkpoint_id,
                    "step_index": c.step_index,
                    "run_status": c.run_status,
                    "reason": c.reason,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "parent_checkpoint_id": c.parent_checkpoint_id,
                    "is_replay": c.is_replay,
                }
                for c in checkpoints
            ]
        finally:
            session.close()
    
    def create_replay_checkpoint(
        self,
        source_checkpoint_id: str,
        run_id: str,
    ) -> str:
        """
        Create a replay checkpoint from a historical checkpoint.
        
        This allows "time travel" debugging - resume from any past state.
        
        Args:
            source_checkpoint_id: Checkpoint to replay from
            run_id: Run ID for the replay
            
        Returns:
            New checkpoint ID for the replay
        """
        # Get source checkpoint
        source_state = self.get(source_checkpoint_id)
        if not source_state:
            raise ValueError(f"Checkpoint {source_checkpoint_id} not found")
        
        # Clone state for replay
        replay_state = source_state.clone()
        replay_state.run_id = run_id
        replay_state.run_status = RunStatus.PLANNING.value
        
        # Create new checkpoint marked as replay
        checkpoint_id = f"CHK-{uuid.uuid4().hex[:12].upper()}"
        replay_state.created_at = datetime.utcnow().isoformat()
        replay_state.reason = f"replay_from_{source_checkpoint_id}"
        
        session = self.session_factory()
        try:
            repo = CheckpointRepository(session)
            
            checkpoint = CheckpointModel(
                checkpoint_id=checkpoint_id,
                run_id=run_id,
                thread_id=replay_state.thread_id,
                step_index=replay_state.step_index,
                run_status=replay_state.run_status,
                state_json=replay_state.to_json(),
                reason=f"replay_from_{source_checkpoint_id}",
                parent_checkpoint_id=source_checkpoint_id,
                is_replay=True,
            )
            session.add(checkpoint)
            session.commit()
            
            logger.info(
                f"Created replay checkpoint {checkpoint_id} from {source_checkpoint_id}"
            )
            
            return checkpoint_id
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create replay checkpoint: {e}")
            raise
        finally:
            session.close()
    
    def should_checkpoint(
        self,
        current_step: int,
        previous_step: int,
        event: str,
    ) -> bool:
        """
        Determine if a checkpoint should be created.
        
        Checkpoints are created:
        - After each step completion
        - Before approval requests
        - On errors
        - On pause/resume
        
        Args:
            current_step: Current step index
            previous_step: Previous step index
            event: Event type triggering the check
            
        Returns:
            True if checkpoint should be created
        """
        # Always checkpoint on these events
        checkpoint_events = {
            "step_completed",
            "approval_pending",
            "approval_received",
            "error",
            "pause",
            "resume",
            "verification_started",
            "verification_completed",
        }
        
        if event in checkpoint_events:
            return True
        
        # Checkpoint on step change
        if current_step != previous_step:
            return True
        
        return False

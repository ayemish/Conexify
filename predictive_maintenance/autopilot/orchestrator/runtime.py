"""
Orchestration Runtime

Main execution engine for autopilot runs with durable checkpointing.
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid

from sqlalchemy.orm import Session

from ..schemas import (
    RiskTier, RunStatus, StepStatus, ActionType,
    AutopilotRun, RunStep, RunAction,
)
from ..models import AutopilotRunModel, RunStepModel, RunActionModel
from ..repositories import AutopilotRunRepository, IncidentRepository, PolicyRepository
from ..playbook.schema import PlaybookDefinition, PlaybookStep, StepType
from ..playbook.expressions import ExpressionEvaluator, EvalContext
from ..playbook.registry import PlaybookRegistry
from .checkpoint import CheckpointManager, CheckpointState
from .approval import ApprovalManager, ApprovalRequest, ApprovalResult

logger = logging.getLogger(__name__)


@dataclass
class RunContext:
    """
    Runtime context for a run.
    
    Contains all data needed for step execution and expression evaluation.
    """
    run_id: str
    thread_id: str
    tenant_id: str
    site_id: str
    asset_id: str
    
    # Playbook
    playbook: PlaybookDefinition = None
    
    # Current state
    step_index: int = 0
    status: RunStatus = RunStatus.PLANNING
    
    # Point values
    points: Dict[str, float] = field(default_factory=dict)
    point_history: Dict[str, List[float]] = field(default_factory=dict)
    
    # Variables computed during execution
    variables: Dict[str, Any] = field(default_factory=dict)
    
    # Policy constraints
    policy: Dict[str, Any] = field(default_factory=dict)
    
    # Override status
    overrides: Dict[str, bool] = field(default_factory=dict)
    
    # Results
    step_results: Dict[str, Any] = field(default_factory=dict)
    actions_taken: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    def to_eval_context(self) -> EvalContext:
        """Convert to expression evaluation context"""
        return EvalContext(
            points=self.points,
            point_history=self.point_history,
            asset_id=self.asset_id,
            regime=self.variables.get("regime", ""),
            policy=self.policy,
            overrides=self.overrides,
        )
    
    def to_checkpoint_state(self) -> CheckpointState:
        """Convert to checkpoint state"""
        return CheckpointState(
            run_id=self.run_id,
            thread_id=self.thread_id,
            step_index=self.step_index,
            run_status=self.status.value,
            step_results=self.step_results,
            points=self.points,
            variables=self.variables,
            actions_taken=self.actions_taken,
            errors=self.errors,
        )


class StepExecutor:
    """
    Executes individual playbook steps.
    
    Each step type has a dedicated handler method.
    """
    
    def __init__(
        self,
        session_factory: Callable[[], Session],
        connectors: Dict[str, Any] = None,
    ):
        self.session_factory = session_factory
        self.connectors = connectors or {}
        self.evaluator = ExpressionEvaluator()
    
    def execute(
        self,
        step: PlaybookStep,
        context: RunContext,
    ) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        Execute a single step.
        
        Args:
            step: Step to execute
            context: Run context
            
        Returns:
            (success, result_data, error_message)
        """
        handler = self._get_handler(step.type)
        if not handler:
            return False, {}, f"Unknown step type: {step.type}"
        
        try:
            result = handler(step, context)
            return True, result, None
        except Exception as e:
            logger.error(f"Step {step.id} failed: {e}", exc_info=True)
            return False, {}, str(e)
    
    def _get_handler(self, step_type: StepType) -> Optional[Callable]:
        """Get handler for step type"""
        handlers = {
            StepType.READ: self._execute_read,
            StepType.WRITE_POINT: self._execute_write_point,
            StepType.CREATE_TICKET: self._execute_create_ticket,
            StepType.UPDATE_TICKET: self._execute_update_ticket,
            StepType.NOTIFY: self._execute_notify,
            StepType.WAIT: self._execute_wait,
            StepType.COMPUTE: self._execute_compute,
            StepType.RUN_TEST: self._execute_run_test,
            StepType.ESCALATE: self._execute_escalate,
        }
        return handlers.get(step_type)
    
    def _execute_read(self, step: PlaybookStep, context: RunContext) -> Dict[str, Any]:
        """Read point values"""
        point_ids = step.params.get("point_ids", [])
        
        # Use BMS connector if available
        bms = self.connectors.get("bms")
        if bms:
            values = bms.read_points(point_ids)
            context.points.update(values)
            return {"points": values}
        
        # Otherwise return current context values
        values = {pid: context.points.get(pid) for pid in point_ids}
        return {"points": values}
    
    def _execute_write_point(self, step: PlaybookStep, context: RunContext) -> Dict[str, Any]:
        """Write a point value"""
        point_id = step.params.get("point_id")
        value = step.params.get("value")
        ttl = step.params.get("ttl_seconds", 3600)
        
        # Resolve value if it's an expression
        if isinstance(value, str) and not value.replace(".", "").replace("-", "").isdigit():
            value = self.evaluator.evaluate(value, context.to_eval_context())
        
        # Get current value for logging
        value_before = context.points.get(point_id)
        
        # Use BMS connector if available
        bms = self.connectors.get("bms")
        if bms:
            correlation_id = str(uuid.uuid4())
            result = bms.write_point(point_id, value, ttl, correlation_id)
            
            # Record action
            action = {
                "action_type": "WRITE_POINT",
                "point_id": point_id,
                "value_before": value_before,
                "value_after": value,
                "ttl_seconds": ttl,
                "correlation_id": correlation_id,
                "executed_at": datetime.utcnow().isoformat(),
            }
            context.actions_taken.append(action)
            
            return {
                "point_id": point_id,
                "value_before": value_before,
                "value_after": value,
                "correlation_id": correlation_id,
            }
        
        # Mock execution (no connector)
        logger.info(f"[MOCK] Write {point_id} = {value} (was {value_before})")
        context.points[point_id] = value
        
        return {
            "point_id": point_id,
            "value_before": value_before,
            "value_after": value,
            "mock": True,
        }
    
    def _execute_create_ticket(self, step: PlaybookStep, context: RunContext) -> Dict[str, Any]:
        """Create a CMMS ticket"""
        title = step.params.get("title", "Autopilot Ticket")
        description = step.params.get("description", "")
        priority = step.params.get("priority", "P2")
        
        # Use CMMS connector if available
        cmms = self.connectors.get("cmms")
        if cmms:
            ticket = cmms.create_ticket(
                title=title,
                description=description,
                priority=priority,
                asset_id=context.asset_id,
                site_id=context.site_id,
                run_id=context.run_id,
            )
            
            context.variables["ticket_id"] = ticket.get("ticket_id")
            
            return ticket
        
        # Mock execution
        ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
        logger.info(f"[MOCK] Created ticket {ticket_id}: {title}")
        
        context.variables["ticket_id"] = ticket_id
        
        return {
            "ticket_id": ticket_id,
            "title": title,
            "priority": priority,
            "mock": True,
        }
    
    def _execute_update_ticket(self, step: PlaybookStep, context: RunContext) -> Dict[str, Any]:
        """Update a CMMS ticket"""
        ticket_id = step.params.get("ticket_id") or context.variables.get("ticket_id")
        updates = step.params.get("updates", {})
        
        cmms = self.connectors.get("cmms")
        if cmms:
            return cmms.update_ticket(ticket_id, updates)
        
        logger.info(f"[MOCK] Updated ticket {ticket_id}: {updates}")
        return {"ticket_id": ticket_id, "updates": updates, "mock": True}
    
    def _execute_notify(self, step: PlaybookStep, context: RunContext) -> Dict[str, Any]:
        """Send notifications"""
        recipients = step.params.get("recipients", [])
        message = step.params.get("message", "")
        channel = step.params.get("channel", "email")
        
        notification = self.connectors.get("notification")
        if notification:
            return notification.send(recipients, message, channel)
        
        logger.info(f"[MOCK] Notify {recipients} via {channel}: {message}")
        return {"recipients": recipients, "channel": channel, "mock": True}
    
    def _execute_wait(self, step: PlaybookStep, context: RunContext) -> Dict[str, Any]:
        """Wait for a duration"""
        import time
        
        duration = step.params.get("duration_seconds", 60)
        
        # In production, this would be non-blocking with checkpointing
        logger.info(f"Waiting {duration} seconds...")
        time.sleep(min(duration, 5))  # Cap at 5 seconds for dev
        
        return {"waited_seconds": duration}
    
    def _execute_compute(self, step: PlaybookStep, context: RunContext) -> Dict[str, Any]:
        """Compute a value and store in variables"""
        expression = step.params.get("expression", "")
        output_var = step.params.get("output", "result")
        
        result = self.evaluator.evaluate(expression, context.to_eval_context())
        context.variables[output_var] = result
        
        return {"expression": expression, "output": output_var, "value": result}
    
    def _execute_run_test(self, step: PlaybookStep, context: RunContext) -> Dict[str, Any]:
        """Run a diagnostic test"""
        test_id = step.params.get("test_id")
        test_params = step.params.get("test_params", {})
        
        # Placeholder for test execution
        logger.info(f"[MOCK] Running test {test_id} with params {test_params}")
        
        return {"test_id": test_id, "status": "completed", "mock": True}
    
    def _execute_escalate(self, step: PlaybookStep, context: RunContext) -> Dict[str, Any]:
        """Escalate to human or vendor"""
        reason = step.params.get("reason", "Manual escalation")
        escalation_type = step.params.get("type", "human")
        
        logger.info(f"Escalation ({escalation_type}): {reason}")
        
        return {"escalation_type": escalation_type, "reason": reason}


class OrchestrationRuntime:
    """
    Main orchestration runtime for autopilot runs.
    
    Coordinates:
    - Playbook loading and step sequencing
    - Checkpoint creation and restoration
    - Approval workflow
    - Step execution
    - Error handling and escalation
    """
    
    def __init__(
        self,
        session_factory: Callable[[], Session],
        connectors: Dict[str, Any] = None,
    ):
        connectors = connectors or {}
        self.session_factory = session_factory
        self.checkpoint_mgr = CheckpointManager(session_factory)
        dev_mode = os.getenv("PDM_DEV_MODE", "").lower() in {"1", "true", "yes"}
        if not dev_mode:
            dev_mode = os.getenv("PDM_ENVIRONMENT", "development").lower() != "production"
        self.approval_mgr = ApprovalManager(
            session_factory,
            notification_connector=connectors.get("notification"),
            dev_mode=dev_mode,
        )
        self.step_executor = StepExecutor(session_factory, connectors)
        self.playbook_registry = PlaybookRegistry(session_factory)
        self.evaluator = ExpressionEvaluator()
    
    def start_run(self, run_id: str) -> RunContext:
        """
        Start executing a run.
        
        Args:
            run_id: Run ID to start
            
        Returns:
            RunContext with initial state
        """
        session = self.session_factory()
        try:
            run_repo = AutopilotRunRepository(session)
            run = run_repo.get_by_id(run_id)
            
            if not run:
                raise ValueError(f"Run {run_id} not found")
            
            # Load playbook
            playbook = self.playbook_registry.get(run.playbook_id, run.playbook_version)
            if not playbook:
                raise ValueError(f"Playbook {run.playbook_id} v{run.playbook_version} not found")
            
            # Load policy
            policy_repo = PolicyRepository(session)
            policy_model = policy_repo.get_effective_policy(
                run.tenant_id, run.site_id, run.asset_id
            )
            policy = {}
            if policy_model:
                policy = {
                    "max_setpoint_delta": policy_model.max_setpoint_delta,
                    "max_override_duration_seconds": policy_model.max_override_duration_seconds,
                    "max_commands_per_asset_per_hour": policy_model.max_commands_per_asset_per_hour,
                    "store_hours_start": policy_model.store_hours_start,
                    "store_hours_end": policy_model.store_hours_end,
                    "auto_approve_risk_tiers": policy_model.auto_approve_risk_tiers,
                }
            
            # Create context
            context = RunContext(
                run_id=run_id,
                thread_id=run.thread_id,
                tenant_id=run.tenant_id,
                site_id=run.site_id,
                asset_id=run.asset_id,
                playbook=playbook,
                status=RunStatus.EXECUTING,
                policy=policy,
            )
            
            # Update run status
            run_repo.update_status(run_id, RunStatus.EXECUTING.value)
            session.commit()
            
            # Create initial checkpoint
            self.checkpoint_mgr.create(
                context.to_checkpoint_state(),
                reason="run_started",
            )
            
            return context
            
        finally:
            session.close()
    
    def resume_run(self, run_id: str, checkpoint_id: str = None) -> RunContext:
        """
        Resume a run from checkpoint.
        
        Args:
            run_id: Run ID to resume
            checkpoint_id: Specific checkpoint (None for latest)
            
        Returns:
            RunContext restored from checkpoint
        """
        # Get checkpoint state
        if checkpoint_id:
            state = self.checkpoint_mgr.get(checkpoint_id)
        else:
            state = self.checkpoint_mgr.get_latest(run_id)
        
        if not state:
            raise ValueError(f"No checkpoint found for run {run_id}")
        
        # Load playbook
        session = self.session_factory()
        try:
            run_repo = AutopilotRunRepository(session)
            run = run_repo.get_by_id(run_id)
            
            playbook = self.playbook_registry.get(run.playbook_id, run.playbook_version)
            
            # Restore context
            context = RunContext(
                run_id=run_id,
                thread_id=state.thread_id,
                tenant_id=run.tenant_id,
                site_id=run.site_id,
                asset_id=run.asset_id,
                playbook=playbook,
                step_index=state.step_index,
                status=RunStatus(state.run_status),
                points=state.points,
                variables=state.variables,
                step_results=state.step_results,
                actions_taken=state.actions_taken,
                errors=state.errors,
            )
            
            return context
            
        finally:
            session.close()
    
    def execute_run(self, context: RunContext) -> Tuple[str, str]:
        """
        Execute a run to completion (or until approval needed).
        
        Args:
            context: Run context
            
        Returns:
            (outcome, outcome_reason)
        """
        playbook = context.playbook
        
        # Check preconditions
        passed, failures = self.playbook_registry.check_preconditions(
            playbook, context.to_eval_context()
        )
        if not passed:
            self._update_run_status(
                context.run_id,
                RunStatus.FAILED,
                "FAILED",
                f"Preconditions failed: {'; '.join(failures)}"
            )
            return "FAILED", f"Preconditions failed: {'; '.join(failures)}"
        
        # Execute steps
        while context.step_index < len(playbook.steps):
            step = playbook.steps[context.step_index]
            
            logger.info(f"Executing step {context.step_index}: {step.id} ({step.type.value})")
            
            # Check if approval is required
            risk_tier = RiskTier(playbook.risk_tier)
            if step.requires_approval or self.approval_mgr.requires_approval(
                risk_tier, step.type.value, context.policy
            ):
                # Create approval request
                approval_id = self._request_approval(context, step)
                
                # Checkpoint before waiting
                self.checkpoint_mgr.create(
                    context.to_checkpoint_state(),
                    reason="approval_pending",
                )
                
                # Return - run will resume after approval
                return "AWAITING_APPROVAL", f"Waiting for approval {approval_id}"
            
            # Execute step
            success, result, error = self.step_executor.execute(step, context)
            
            # Store result
            context.step_results[step.id] = {
                "success": success,
                "result": result,
                "error": error,
                "executed_at": datetime.utcnow().isoformat(),
            }
            
            if not success:
                # Handle error based on on_error setting
                outcome = self._handle_step_error(context, step, error)
                if outcome:
                    return outcome
            
            # Checkpoint after step
            context.step_index += 1
            self.checkpoint_mgr.create(
                context.to_checkpoint_state(),
                reason="step_completed",
            )
        
        # All steps completed - run verification
        verification_passed = self._run_verification(context)
        
        if verification_passed:
            outcome = "RESOLVED"
            outcome_reason = "All steps completed and verification passed"
        else:
            outcome = "PARTIAL"
            outcome_reason = "Steps completed but verification failed"
        
        self._update_run_status(
            context.run_id,
            RunStatus.COMPLETED,
            outcome,
            outcome_reason,
        )
        
        return outcome, outcome_reason
    
    def _request_approval(self, context: RunContext, step: PlaybookStep) -> str:
        """Create an approval request for a step"""
        request = ApprovalRequest(
            run_id=context.run_id,
            step_id=step.id,
            tenant_id=context.tenant_id,
            approval_type="step",
            risk_tier=RiskTier(context.playbook.risk_tier),
            proposed_actions=[{
                "step_id": step.id,
                "type": step.type.value,
                "params": step.params,
                "description": step.description,
            }],
            rationale=f"Step {step.id} requires approval (type={step.type.value})",
            evidence_snapshot={
                "points": context.points,
                "variables": context.variables,
            },
        )
        
        return self.approval_mgr.create_approval(request)
    
    def _handle_step_error(
        self,
        context: RunContext,
        step: PlaybookStep,
        error: str,
    ) -> Optional[Tuple[str, str]]:
        """Handle step execution error"""
        context.errors.append(f"Step {step.id}: {error}")

        on_error = step.on_error.value if hasattr(step.on_error, 'value') else step.on_error

        if on_error == "RETRY":
            import time

            max_retries = max(0, int(getattr(step, "max_retries", 3) or 3))
            base_backoff = float(step.params.get("retry_backoff_seconds", 1.0))
            base_backoff = max(0.1, base_backoff)
            retry_key = f"_retry_count:{step.id}"
            attempted = int(context.variables.get(retry_key, 0))

            if attempted < max_retries:
                delay = min(base_backoff * (2 ** attempted), 30.0)
                context.variables[retry_key] = attempted + 1
                audit_entry = {
                    "action_type": "RETRY_STEP",
                    "step_id": step.id,
                    "attempt": attempted + 1,
                    "max_retries": max_retries,
                    "backoff_seconds": round(delay, 3),
                    "error": error,
                    "executed_at": datetime.utcnow().isoformat(),
                }
                context.actions_taken.append(audit_entry)
                logger.warning(
                    "Retrying step %s for run %s (%d/%d) after %.2fs due to error: %s",
                    step.id,
                    context.run_id,
                    attempted + 1,
                    max_retries,
                    delay,
                    error,
                )
                time.sleep(min(delay, 5.0))
                return None

            logger.error(
                "Step %s exceeded retry budget (%d retries), failing run %s",
                step.id,
                max_retries,
                context.run_id,
            )
            self._update_run_status(
                context.run_id,
                RunStatus.FAILED,
                "FAILED",
                f"Step {step.id} exceeded retry budget after {max_retries} retries: {error}",
            )
            return "FAILED", f"Step {step.id} exceeded retry budget: {error}"
        elif on_error == "SKIP":
            logger.warning(f"Skipping failed step {step.id}")
            context.step_index += 1
            return None
        elif on_error == "ESCALATE":
            # Continue but mark for escalation
            context.variables["escalation_required"] = True
            context.step_index += 1
            return None
        elif on_error == "ABORT":
            self._update_run_status(
                context.run_id,
                RunStatus.FAILED,
                "FAILED",
                f"Step {step.id} failed: {error}"
            )
            return "FAILED", f"Step {step.id} failed: {error}"
        
        return None
    
    def _run_verification(self, context: RunContext) -> bool:
        """Run verification checks"""
        playbook = context.playbook
        
        if not playbook.verification:
            return True
        
        all_passed = True
        
        for verification in playbook.verification:
            try:
                result = self.evaluator.evaluate(
                    verification.expr,
                    context.to_eval_context()
                )
                if not result:
                    logger.warning(f"Verification failed: {verification.expr}")
                    all_passed = False
            except Exception as e:
                logger.error(f"Verification error: {e}")
                all_passed = False
        
        return all_passed
    
    def _update_run_status(
        self,
        run_id: str,
        status: RunStatus,
        outcome: str = None,
        outcome_reason: str = None,
    ):
        """Update run status in database"""
        session = self.session_factory()
        try:
            repo = AutopilotRunRepository(session)
            repo.update_status(run_id, status.value, outcome, outcome_reason)
            session.commit()
        finally:
            session.close()

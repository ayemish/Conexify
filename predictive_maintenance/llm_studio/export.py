"""
Training Data Exporter

Exports captured workflow data in formats suitable for LLM fine-tuning.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import (
    AgentDecision,
    TrainingExample,
    ExportFormat,
    WorkflowTrace,
)

logger = logging.getLogger(__name__)


# System prompts for different decision types
SYSTEM_PROMPTS = {
    "fault_detection": """You are an expert HVAC/R fault detection system. Given equipment telemetry and operating context, identify potential faults with high precision and low false positive rates. Explain your reasoning step by step.""",
    
    "playbook_selection": """You are an operations autopilot that selects the appropriate remediation playbook for detected faults. Consider the fault type, asset class, risk level, and site policies when making your selection.""",
    
    "action_execution": """You are an automated remediation agent that executes control actions on HVAC/R equipment. Determine the optimal action parameters and explain your reasoning, considering safety constraints and operational policies.""",
    
    "risk_assessment": """You are a risk assessment agent for building operations. Evaluate the risk level of proposed actions considering equipment criticality, business impact, and safety implications.""",
    
    "verification": """You are a verification agent that validates whether remediation actions achieved their intended outcomes. Analyze before/after telemetry and determine if the issue was resolved.""",
    
    "default": """You are an intelligent building operations assistant that helps diagnose and resolve HVAC/R equipment issues. Provide clear, actionable recommendations based on telemetry data and operational context.""",
}


class TrainingDataExporter:
    """
    Exports workflow traces and decisions as LLM training data.
    
    Supports formats:
    - JSONL (one example per line)
    - OpenAI conversation format
    - Alpaca instruction format
    - ShareGPT format
    """
    
    def __init__(self):
        self.examples: List[TrainingExample] = []
    
    def decision_to_example(
        self,
        decision: AgentDecision,
        include_outcome: bool = True,
    ) -> TrainingExample:
        """Convert an AgentDecision to a TrainingExample"""
        decision_type = decision.decision_type.value
        system_prompt = SYSTEM_PROMPTS.get(decision_type, SYSTEM_PROMPTS["default"])
        
        # Build instruction
        instruction = f"Analyze the following {decision_type.replace('_', ' ')} scenario and provide your assessment."
        
        # Build input context
        context_parts = []
        
        if decision.context.asset_id:
            context_parts.append(f"**Asset:** {decision.context.asset_id}")
        
        if decision.context.regime:
            context_parts.append(f"**Operating Regime:** {decision.context.regime}")
        
        if decision.context.telemetry:
            telemetry_str = ", ".join(
                f"{k}: {v}" for k, v in decision.context.telemetry.items()
            )
            context_parts.append(f"**Telemetry:** {telemetry_str}")
        
        if decision.context.ambient_conditions:
            ambient_str = ", ".join(
                f"{k}: {v}" for k, v in decision.context.ambient_conditions.items()
            )
            context_parts.append(f"**Ambient Conditions:** {ambient_str}")
        
        if decision.context.active_alerts:
            alerts_str = ", ".join(
                a.get("type", "unknown") for a in decision.context.active_alerts
            )
            context_parts.append(f"**Active Alerts:** {alerts_str}")
        
        if decision.context.fault_hypotheses:
            hypotheses_str = "; ".join(
                f"{h.get('fault_type', 'unknown')} ({h.get('confidence', 0):.0%})"
                for h in decision.context.fault_hypotheses
            )
            context_parts.append(f"**Fault Hypotheses:** {hypotheses_str}")
        
        input_context = "\n".join(context_parts)
        
        # Build expected output (reasoning + decision)
        output_parts = []
        
        if decision.reasoning_steps:
            output_parts.append("**Reasoning:**")
            for i, step in enumerate(decision.reasoning_steps, 1):
                output_parts.append(f"{i}. {step}")
            output_parts.append("")
        
        output_parts.append(f"**Decision:** {decision.decision}")
        
        if decision.confidence > 0:
            output_parts.append(f"**Confidence:** {decision.confidence:.0%}")
        
        if decision.action_taken:
            action_str = json.dumps(decision.action_taken, indent=2)
            output_parts.append(f"**Action:**\n```json\n{action_str}\n```")
        
        if include_outcome and decision.outcome:
            output_parts.append(f"\n**Outcome:** {decision.outcome.result_summary}")
        
        expected_output = "\n".join(output_parts)
        
        # Determine quality score
        quality_score = decision.confidence
        if decision.outcome:
            if decision.outcome.human_verified:
                quality_score = max(quality_score, 0.9)
            if decision.outcome.status.value == "success":
                quality_score = max(quality_score, 0.7)
        
        return TrainingExample(
            source_decision_id=decision.decision_id,
            source_trace_id=decision.trace_id,
            system_prompt=system_prompt,
            instruction=instruction,
            input_context=input_context,
            expected_output=expected_output,
            decision_type=decision_type,
            quality_score=quality_score,
            is_human_verified=decision.outcome.human_verified if decision.outcome else False,
            tags=[decision_type, decision.agent_name],
        )
    
    def trace_to_conversation(
        self,
        trace: WorkflowTrace,
    ) -> List[Dict[str, Any]]:
        """Convert a full trace to a multi-turn conversation"""
        messages = []
        
        # System message
        messages.append({
            "role": "system",
            "content": SYSTEM_PROMPTS["default"],
        })
        
        # Each decision becomes a turn
        for decision in trace.decisions:
            # User turn (context)
            user_content = f"[{decision.decision_type.value.upper()}]\n\n"
            user_content += f"Asset: {decision.context.asset_id}\n"
            
            if decision.context.telemetry:
                user_content += f"Telemetry: {decision.context.telemetry}\n"
            
            if decision.context.fault_hypotheses:
                user_content += f"Hypotheses: {decision.context.fault_hypotheses}\n"
            
            messages.append({"role": "user", "content": user_content})
            
            # Assistant turn (reasoning + decision)
            assistant_content = ""
            if decision.reasoning_steps:
                assistant_content += "Reasoning:\n"
                for step in decision.reasoning_steps:
                    assistant_content += f"- {step}\n"
                assistant_content += "\n"
            
            assistant_content += f"Decision: {decision.decision}"
            
            if decision.outcome:
                assistant_content += f"\n\nOutcome: {decision.outcome.result_summary}"
            
            messages.append({"role": "assistant", "content": assistant_content})
        
        return messages
    
    def export_decisions(
        self,
        decisions: List[AgentDecision],
        output_path: str,
        format: ExportFormat = ExportFormat.JSONL,
        include_outcome: bool = True,
    ) -> Dict[str, Any]:
        """Export decisions to a file"""
        examples = [
            self.decision_to_example(d, include_outcome)
            for d in decisions
        ]
        
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w') as f:
            for example in examples:
                if format == ExportFormat.JSONL:
                    f.write(json.dumps(example.to_jsonl()) + "\n")
                elif format == ExportFormat.CONVERSATION:
                    f.write(json.dumps(example.to_conversation()) + "\n")
                elif format == ExportFormat.ALPACA:
                    f.write(json.dumps(example.to_alpaca()) + "\n")
                elif format == ExportFormat.SHAREGPT:
                    f.write(json.dumps(example.to_sharegpt()) + "\n")
        
        logger.info(f"Exported {len(examples)} examples to {output_path}")
        
        return {
            "output_path": str(output_path),
            "format": format.value,
            "total_examples": len(examples),
            "human_verified": sum(1 for e in examples if e.is_human_verified),
            "avg_quality_score": (
                sum(e.quality_score for e in examples) / len(examples)
                if examples else 0
            ),
        }
    
    def export_traces_as_conversations(
        self,
        traces: List[WorkflowTrace],
        output_path: str,
    ) -> Dict[str, Any]:
        """Export traces as multi-turn conversations"""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w') as f:
            for trace in traces:
                if not trace.include_in_training:
                    continue
                
                messages = self.trace_to_conversation(trace)
                f.write(json.dumps({
                    "trace_id": trace.trace_id,
                    "messages": messages,
                }) + "\n")
        
        logger.info(f"Exported {len(traces)} traces to {output_path}")
        
        return {
            "output_path": str(output_path),
            "format": "conversation",
            "total_traces": len(traces),
            "total_turns": sum(len(t.decisions) * 2 for t in traces),
        }
    
    def create_train_val_split(
        self,
        decisions: List[AgentDecision],
        output_dir: str,
        val_ratio: float = 0.1,
        format: ExportFormat = ExportFormat.JSONL,
    ) -> Dict[str, Any]:
        """Create train/validation split"""
        import random
        
        examples = [self.decision_to_example(d) for d in decisions]
        random.shuffle(examples)
        
        split_idx = int(len(examples) * (1 - val_ratio))
        train_examples = examples[:split_idx]
        val_examples = examples[split_idx:]
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        train_file = output_path / f"train.{format.value}"
        val_file = output_path / f"val.{format.value}"
        
        for file_path, file_examples in [(train_file, train_examples), (val_file, val_examples)]:
            with open(file_path, 'w') as f:
                for example in file_examples:
                    if format == ExportFormat.JSONL:
                        f.write(json.dumps(example.to_jsonl()) + "\n")
                    elif format == ExportFormat.CONVERSATION:
                        f.write(json.dumps(example.to_conversation()) + "\n")
                    elif format == ExportFormat.ALPACA:
                        f.write(json.dumps(example.to_alpaca()) + "\n")
        
        return {
            "output_dir": str(output_dir),
            "train_file": str(train_file),
            "val_file": str(val_file),
            "train_examples": len(train_examples),
            "val_examples": len(val_examples),
            "val_ratio": val_ratio,
        }

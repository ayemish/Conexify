"""
DAG Orchestration Agent (N1)

CrewAI agent that manages directed acyclic graph (DAG) execution of
multi-agent workflows. Replaces the TypeScript DAG orchestrator from
quest-agent-forge-main with a Python CrewAI implementation.

Responsibilities:
- Build and validate DAG topologies from agent dependency declarations
- Topological sort for execution ordering
- Parallel-safe scheduling of independent nodes
- Cycle detection and error recovery
- Run-level state tracking (pending → running → done / failed)

Addresses N1 from the FRD implementation plan.
"""

import json
import logging
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from shared.agents.crewai_base import (
    Agent, Task, Crew, Process, CREWAI_AVAILABLE,
    BaseCrewAgent, CrewAIAgentConfig, AgentCategory, AgentRole,
)

logger = logging.getLogger(__name__)

# CrewAI @tool decorator with fallback
try:
    from crewai.tools import tool as crewai_tool
except ImportError:
    def crewai_tool(name_or_func=None):
        def decorator(func):
            func.tool_name = name_or_func if isinstance(name_or_func, str) else func.__name__
            return func
        if callable(name_or_func):
            return decorator(name_or_func)
        return decorator


# =============================================================================
# DAG Data Structures
# =============================================================================

class NodeStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class DAGNode:
    """A single node in the execution DAG."""
    node_id: str
    agent_id: str
    task_description: str
    depends_on: List[str] = field(default_factory=list)
    status: NodeStatus = NodeStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "agent_id": self.agent_id,
            "task_description": self.task_description,
            "depends_on": self.depends_on,
            "status": self.status.value,
            "result": self.result,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
        }


@dataclass
class DAGRun:
    """Tracks the state of a single DAG execution."""
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    nodes: Dict[str, DAGNode] = field(default_factory=dict)
    execution_order: List[str] = field(default_factory=list)
    status: str = "pending"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "node_count": len(self.nodes),
            "execution_order": self.execution_order,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


# =============================================================================
# DAG Engine (deterministic, no LLM needed)
# =============================================================================

class DAGEngine:
    """Core DAG execution engine — topological sort, cycle detection, scheduling."""

    @staticmethod
    def topological_sort(nodes: Dict[str, DAGNode]) -> List[str]:
        """Kahn's algorithm for topological ordering. Raises ValueError on cycles."""
        in_degree: Dict[str, int] = {nid: 0 for nid in nodes}
        adjacency: Dict[str, List[str]] = defaultdict(list)

        for nid, node in nodes.items():
            for dep in node.depends_on:
                if dep not in nodes:
                    raise ValueError(f"Node '{nid}' depends on unknown node '{dep}'")
                adjacency[dep].append(nid)
                in_degree[nid] += 1

        queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
        order: List[str] = []

        while queue:
            current = queue.popleft()
            order.append(current)
            for neighbor in adjacency[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(nodes):
            visited = set(order)
            cycle_nodes = [nid for nid in nodes if nid not in visited]
            raise ValueError(f"Cycle detected involving nodes: {cycle_nodes}")

        return order

    @staticmethod
    def get_ready_nodes(nodes: Dict[str, DAGNode]) -> List[str]:
        """Return node IDs whose dependencies are all DONE."""
        ready = []
        for nid, node in nodes.items():
            if node.status != NodeStatus.PENDING:
                continue
            deps_met = all(
                nodes[dep].status == NodeStatus.DONE
                for dep in node.depends_on
                if dep in nodes
            )
            if deps_met:
                ready.append(nid)
        return ready

    @staticmethod
    def validate_dag(nodes: Dict[str, DAGNode]) -> Dict[str, Any]:
        """Validate DAG structure — check for cycles, missing deps, orphans."""
        issues = []

        # Check missing dependencies
        all_ids = set(nodes.keys())
        for nid, node in nodes.items():
            for dep in node.depends_on:
                if dep not in all_ids:
                    issues.append(f"Node '{nid}' references missing dependency '{dep}'")

        # Check cycles
        try:
            order = DAGEngine.topological_sort(nodes)
        except ValueError as e:
            issues.append(str(e))
            order = []

        # Check orphans (no dependents and not terminal)
        has_dependents = set()
        for node in nodes.values():
            has_dependents.update(node.depends_on)
        terminal = all_ids - has_dependents
        roots = {nid for nid, node in nodes.items() if not node.depends_on}

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "node_count": len(nodes),
            "root_nodes": sorted(roots),
            "terminal_nodes": sorted(terminal),
            "execution_order": order,
        }


# =============================================================================
# @tool Functions
# =============================================================================

@crewai_tool("build_dag")
def build_dag(nodes_json: str) -> dict:
    """Build and validate a DAG from a JSON array of node definitions.
    Each node: {"node_id": str, "agent_id": str, "task": str, "depends_on": [str]}.
    Returns validated DAG with execution order."""
    try:
        raw = json.loads(nodes_json)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON", "valid": False}

    nodes = {}
    for n in raw:
        nid = n.get("node_id", str(uuid.uuid4())[:8])
        nodes[nid] = DAGNode(
            node_id=nid,
            agent_id=n.get("agent_id", "unknown"),
            task_description=n.get("task", ""),
            depends_on=n.get("depends_on", []),
        )

    result = DAGEngine.validate_dag(nodes)
    return result


@crewai_tool("get_next_executable_nodes")
def get_next_executable_nodes(dag_state_json: str) -> dict:
    """Given current DAG state, return which nodes are ready to execute.
    dag_state_json maps node_id to status string."""
    try:
        state = json.loads(dag_state_json)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON"}

    # Reconstruct minimal nodes for scheduling
    # state format: {"node_id": {"status": "...", "depends_on": [...]}}
    nodes = {}
    for nid, info in state.items():
        nodes[nid] = DAGNode(
            node_id=nid,
            agent_id=info.get("agent_id", ""),
            task_description="",
            depends_on=info.get("depends_on", []),
            status=NodeStatus(info.get("status", "pending")),
        )

    ready = DAGEngine.get_ready_nodes(nodes)
    all_done = all(n.status == NodeStatus.DONE for n in nodes.values())
    any_failed = any(n.status == NodeStatus.FAILED for n in nodes.values())

    return {
        "ready_nodes": ready,
        "all_done": all_done,
        "any_failed": any_failed,
        "pending_count": sum(1 for n in nodes.values() if n.status == NodeStatus.PENDING),
        "running_count": sum(1 for n in nodes.values() if n.status == NodeStatus.RUNNING),
        "done_count": sum(1 for n in nodes.values() if n.status == NodeStatus.DONE),
    }


@crewai_tool("detect_dag_cycles")
def detect_dag_cycles(edges_json: str) -> dict:
    """Detect cycles in a DAG given edges as JSON array of [from, to] pairs."""
    try:
        edges = json.loads(edges_json)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON"}

    # Build adjacency
    all_nodes: Set[str] = set()
    adj: Dict[str, List[str]] = defaultdict(list)
    for edge in edges:
        if len(edge) >= 2:
            adj[edge[0]].append(edge[1])
            all_nodes.add(edge[0])
            all_nodes.add(edge[1])

    # DFS cycle detection
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in all_nodes}
    cycle_nodes = []

    def dfs(node):
        color[node] = GRAY
        for neighbor in adj.get(node, []):
            if color.get(neighbor, WHITE) == GRAY:
                cycle_nodes.append(neighbor)
                return True
            if color.get(neighbor, WHITE) == WHITE and dfs(neighbor):
                cycle_nodes.append(node)
                return True
        color[node] = BLACK
        return False

    has_cycle = any(dfs(n) for n in all_nodes if color[n] == WHITE)
    return {
        "has_cycle": has_cycle,
        "cycle_nodes": cycle_nodes if has_cycle else [],
        "total_nodes": len(all_nodes),
        "total_edges": len(edges),
    }


# =============================================================================
# DAG Orchestration CrewAI Agent
# =============================================================================

class DAGOrchestrationAgent(BaseCrewAgent):
    """
    CrewAI agent that manages DAG-based multi-agent workflow execution.

    Uses networkx-style DAG operations internally but exposes everything
    through @tool functions for LLM reasoning about execution plans.
    """

    def __init__(self, **kwargs):
        config = CrewAIAgentConfig(
            agent_id="dag_orchestration",
            role=AgentRole.RESOURCE_ALLOCATOR,
            category=AgentCategory.OPTIMIZATION,
            name="DAG Workflow Orchestrator",
            goal=(
                "Plan and execute multi-agent workflows as directed acyclic graphs. "
                "Determine optimal execution order, parallelize independent tasks, "
                "and handle failures gracefully."
            ),
            backstory=(
                "You are a workflow orchestration expert who designs and manages "
                "complex multi-step processes. You understand dependency graphs, "
                "parallel execution, and failure recovery patterns."
            ),
        )
        super().__init__(config, **kwargs)
        self._runs: Dict[str, DAGRun] = {}

    @property
    def tools(self) -> list:
        return [build_dag, get_next_executable_nodes, detect_dag_cycles]

    def create_run(self, nodes: List[Dict[str, Any]]) -> DAGRun:
        """Create a new DAG run from node definitions."""
        run = DAGRun()
        for n in nodes:
            nid = n.get("node_id", str(uuid.uuid4())[:8])
            run.nodes[nid] = DAGNode(
                node_id=nid,
                agent_id=n.get("agent_id", "unknown"),
                task_description=n.get("task", ""),
                depends_on=n.get("depends_on", []),
            )
        run.execution_order = DAGEngine.topological_sort(run.nodes)
        run.status = "ready"
        self._runs[run.run_id] = run
        return run

    def get_run(self, run_id: str) -> Optional[DAGRun]:
        return self._runs.get(run_id)

    def mark_node(self, run_id: str, node_id: str, status: NodeStatus,
                  result: Optional[Dict] = None, error: Optional[str] = None):
        """Update a node's status within a run."""
        run = self._runs.get(run_id)
        if not run or node_id not in run.nodes:
            return
        node = run.nodes[node_id]
        node.status = status
        if status == NodeStatus.RUNNING:
            node.started_at = datetime.utcnow().isoformat()
        if status in (NodeStatus.DONE, NodeStatus.FAILED):
            node.completed_at = datetime.utcnow().isoformat()
            node.result = result
            node.error = error

        # Check if run is complete
        if all(n.status in (NodeStatus.DONE, NodeStatus.FAILED, NodeStatus.SKIPPED)
               for n in run.nodes.values()):
            run.status = "completed" if not any(
                n.status == NodeStatus.FAILED for n in run.nodes.values()
            ) else "completed_with_errors"
            run.completed_at = datetime.utcnow().isoformat()

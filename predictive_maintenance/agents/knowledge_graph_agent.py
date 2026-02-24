"""
Knowledge Graph Agent (N2)

CrewAI agent that builds and queries an asset-fault-sensor knowledge graph
using networkx. Replaces the TypeScript KG implementation from
quest-agent-forge-main with a Python CrewAI agent.

Responsibilities:
- Build knowledge graph from asset, fault, and sensor relationships
- Query shortest paths between entities (e.g., symptom → root cause)
- Identify related faults for a given asset type
- Discover sensor clusters that co-indicate failure modes
- Support the diagnostic reasoning pipeline

Addresses N2 from the FRD implementation plan.
"""

import json
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

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

# networkx availability
NX_AVAILABLE = False
try:
    import networkx as nx
    NX_AVAILABLE = True
except ImportError:
    logger.info("networkx not installed. KG agent runs with built-in graph.")


# =============================================================================
# Lightweight Graph (fallback when networkx unavailable)
# =============================================================================

class _SimpleGraph:
    """Minimal directed graph for use when networkx is not installed."""

    def __init__(self):
        self._nodes: Dict[str, Dict[str, Any]] = {}
        self._edges: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)

    def add_node(self, node_id: str, **attrs):
        self._nodes[node_id] = attrs

    def add_edge(self, src: str, dst: str, **attrs):
        self._edges[src][dst] = attrs
        # Ensure nodes exist
        if src not in self._nodes:
            self._nodes[src] = {}
        if dst not in self._nodes:
            self._nodes[dst] = {}

    def has_node(self, node_id: str) -> bool:
        return node_id in self._nodes

    def neighbors(self, node_id: str) -> List[str]:
        return list(self._edges.get(node_id, {}).keys())

    def predecessors(self, node_id: str) -> List[str]:
        return [src for src, dsts in self._edges.items() if node_id in dsts]

    def nodes(self, data=False):
        if data:
            return list(self._nodes.items())
        return list(self._nodes.keys())

    def number_of_nodes(self) -> int:
        return len(self._nodes)

    def number_of_edges(self) -> int:
        return sum(len(d) for d in self._edges.values())

    def get_node_data(self, node_id: str) -> Dict[str, Any]:
        return self._nodes.get(node_id, {})


# =============================================================================
# Knowledge Graph Store
# =============================================================================

class KnowledgeGraphStore:
    """
    In-memory knowledge graph of asset-fault-sensor relationships.
    Uses networkx when available, falls back to _SimpleGraph.
    """

    def __init__(self):
        if NX_AVAILABLE:
            self._graph = nx.DiGraph()
        else:
            self._graph = _SimpleGraph()

    def add_entity(self, entity_id: str, entity_type: str, **attrs):
        """Add a node (asset, fault, sensor, symptom, etc.)."""
        self._graph.add_node(entity_id, entity_type=entity_type, **attrs)

    def add_relationship(self, src: str, dst: str, rel_type: str, **attrs):
        """Add a directed edge between entities."""
        self._graph.add_edge(src, dst, rel_type=rel_type, **attrs)

    def get_related(self, entity_id: str, rel_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get entities related to a given entity, optionally filtered by relationship type."""
        if not self._graph.has_node(entity_id):
            return []

        results = []
        for neighbor in self._graph.neighbors(entity_id):
            if NX_AVAILABLE:
                edge_data = self._graph[entity_id][neighbor]
                node_data = self._graph.nodes[neighbor]
            else:
                edge_data = self._graph._edges.get(entity_id, {}).get(neighbor, {})
                node_data = self._graph.get_node_data(neighbor)

            if rel_type and edge_data.get("rel_type") != rel_type:
                continue
            results.append({
                "entity_id": neighbor,
                "entity_type": node_data.get("entity_type", "unknown"),
                "rel_type": edge_data.get("rel_type", "related"),
                **{k: v for k, v in node_data.items() if k != "entity_type"},
            })
        return results

    def find_path(self, src: str, dst: str) -> List[str]:
        """Find shortest path between two entities."""
        if NX_AVAILABLE:
            try:
                return nx.shortest_path(self._graph, src, dst)
            except (nx.NodeNotFound, nx.NetworkXNoPath):
                return []
        # BFS fallback
        from collections import deque
        visited = {src}
        queue = deque([(src, [src])])
        while queue:
            current, path = queue.popleft()
            for neighbor in self._graph.neighbors(current):
                if neighbor == dst:
                    return path + [neighbor]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        return []

    def get_subgraph(self, entity_id: str, depth: int = 2) -> Dict[str, Any]:
        """Get the local subgraph around an entity up to a given depth."""
        if not self._graph.has_node(entity_id):
            return {"center": entity_id, "nodes": [], "edges": []}

        visited: Set[str] = set()
        nodes_out = []
        edges_out = []
        frontier = [(entity_id, 0)]

        while frontier:
            current, d = frontier.pop(0)
            if current in visited or d > depth:
                continue
            visited.add(current)

            if NX_AVAILABLE:
                node_data = dict(self._graph.nodes[current])
            else:
                node_data = dict(self._graph.get_node_data(current))
            nodes_out.append({"id": current, **node_data})

            for neighbor in self._graph.neighbors(current):
                if NX_AVAILABLE:
                    edge_data = dict(self._graph[current][neighbor])
                else:
                    edge_data = dict(self._graph._edges.get(current, {}).get(neighbor, {}))
                edges_out.append({"from": current, "to": neighbor, **edge_data})
                if neighbor not in visited:
                    frontier.append((neighbor, d + 1))

        return {
            "center": entity_id,
            "nodes": nodes_out,
            "edges": edges_out,
            "node_count": len(nodes_out),
            "edge_count": len(edges_out),
        }

    def stats(self) -> Dict[str, Any]:
        return {
            "node_count": self._graph.number_of_nodes(),
            "edge_count": self._graph.number_of_edges(),
            "networkx_available": NX_AVAILABLE,
        }


# Singleton store
_kg_store = KnowledgeGraphStore()


def get_kg_store() -> KnowledgeGraphStore:
    return _kg_store


# =============================================================================
# @tool Functions
# =============================================================================

@crewai_tool("add_kg_entity")
def add_kg_entity(entity_id: str, entity_type: str, attributes_json: str = "{}") -> dict:
    """Add an entity (asset, fault, sensor, symptom) to the knowledge graph.
    entity_type: asset | fault | sensor | symptom | component | action.
    attributes_json: optional JSON object of additional properties."""
    try:
        attrs = json.loads(attributes_json) if attributes_json != "{}" else {}
    except json.JSONDecodeError:
        attrs = {}

    store = get_kg_store()
    store.add_entity(entity_id, entity_type, **attrs)
    return {"entity_id": entity_id, "entity_type": entity_type, "status": "added"}


@crewai_tool("add_kg_relationship")
def add_kg_relationship(
    source_id: str, target_id: str, rel_type: str, attributes_json: str = "{}"
) -> dict:
    """Add a directed relationship between two entities in the knowledge graph.
    rel_type examples: causes, indicates, monitors, mitigates, contains."""
    try:
        attrs = json.loads(attributes_json) if attributes_json != "{}" else {}
    except json.JSONDecodeError:
        attrs = {}

    store = get_kg_store()
    store.add_relationship(source_id, target_id, rel_type, **attrs)
    return {"source": source_id, "target": target_id, "rel_type": rel_type, "status": "added"}


@crewai_tool("query_kg_related")
def query_kg_related(entity_id: str, rel_type: str = "") -> dict:
    """Query entities related to a given entity, optionally filtered by relationship type.
    Returns list of related entities with their types and relationship info."""
    store = get_kg_store()
    related = store.get_related(entity_id, rel_type if rel_type else None)
    return {
        "entity_id": entity_id,
        "filter_rel_type": rel_type or "all",
        "related_count": len(related),
        "related": related,
    }


@crewai_tool("find_kg_path")
def find_kg_path(source_id: str, target_id: str) -> dict:
    """Find the shortest path between two entities in the knowledge graph.
    Useful for tracing symptom → root-cause chains."""
    store = get_kg_store()
    path = store.find_path(source_id, target_id)
    return {
        "source": source_id,
        "target": target_id,
        "path": path,
        "path_length": len(path) - 1 if path else -1,
        "found": len(path) > 0,
    }


@crewai_tool("get_kg_subgraph")
def get_kg_subgraph(entity_id: str, depth: int = 2) -> dict:
    """Get the local subgraph around an entity up to a given depth.
    Returns nodes and edges for visualization or reasoning."""
    store = get_kg_store()
    return store.get_subgraph(entity_id, depth)


@crewai_tool("get_kg_stats")
def get_kg_stats() -> dict:
    """Get knowledge graph statistics — node count, edge count, backend info."""
    store = get_kg_store()
    return store.stats()


# =============================================================================
# Knowledge Graph CrewAI Agent
# =============================================================================

class KnowledgeGraphAgent(BaseCrewAgent):
    """
    CrewAI agent that builds and queries an asset-fault-sensor knowledge graph.

    Uses networkx (when available) for graph operations and exposes
    @tool functions for LLM-powered diagnostic reasoning.
    """

    def __init__(self, **kwargs):
        config = CrewAIAgentConfig(
            agent_id="knowledge_graph",
            role=AgentRole.DATA_STEWARD,
            category=AgentCategory.DATA,
            name="Knowledge Graph Specialist",
            goal=(
                "Build and maintain a knowledge graph of asset-fault-sensor "
                "relationships. Answer diagnostic queries by traversing the graph "
                "to find root causes, related faults, and sensor correlations."
            ),
            backstory=(
                "You are a knowledge engineering expert who models complex "
                "relationships between HVAC/R equipment, failure modes, sensors, "
                "and maintenance actions. Your graph enables rapid diagnostic "
                "reasoning and root-cause analysis."
            ),
        )
        super().__init__(config, **kwargs)
        self._store = get_kg_store()

    @property
    def tools(self) -> list:
        return [
            add_kg_entity,
            add_kg_relationship,
            query_kg_related,
            find_kg_path,
            get_kg_subgraph,
            get_kg_stats,
        ]

    @property
    def store(self) -> KnowledgeGraphStore:
        return self._store

"""
Cross-asset relationship graph for digital twins.

Supports typed edges (SERVES, REJECTS_HEAT_TO, AFFECTS_LOAD_OF, etc.)
enabling cross-asset KPI computation (e.g., refrigeration efficiency
degrading HVAC energy, HVAC failures increasing refrigeration head pressure).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from loweconex_platform.digital_twins.models import RelationshipType, TwinRelationship

logger = logging.getLogger(__name__)


class RelationshipGraph:
    """
    In-memory directed graph of twin relationships.
    
    Provides traversal, impact analysis, and cross-asset dependency
    resolution for KPI computations.
    """

    def __init__(self):
        # adjacency: source_id -> [(target_id, rel_type, properties)]
        self._outgoing: Dict[str, List[TwinRelationship]] = defaultdict(list)
        self._incoming: Dict[str, List[TwinRelationship]] = defaultdict(list)
        self._all_edges: List[TwinRelationship] = []

    @staticmethod
    def _coerce_rel_type(rel_type: RelationshipType | str) -> RelationshipType:
        """Coerce string relationship values to RelationshipType enum."""
        if isinstance(rel_type, RelationshipType):
            return rel_type
        try:
            return RelationshipType(rel_type)
        except Exception:
            normalized = str(rel_type).strip().upper().replace(" ", "_")
            return RelationshipType[normalized]

    def add_relationship(self, rel: TwinRelationship):
        if not isinstance(rel.relationship_type, RelationshipType):
            rel.relationship_type = self._coerce_rel_type(rel.relationship_type)
        self._outgoing[rel.source_id].append(rel)
        self._incoming[rel.target_id].append(rel)
        self._all_edges.append(rel)

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        rel_type: RelationshipType | str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> TwinRelationship:
        coerced = self._coerce_rel_type(rel_type)
        rel = TwinRelationship(
            source_id=source_id,
            target_id=target_id,
            relationship_type=coerced,
            properties=properties or {},
        )
        self.add_relationship(rel)
        return rel

    def get_outgoing(
        self, source_id: str, rel_type: Optional[RelationshipType] = None
    ) -> List[TwinRelationship]:
        edges = self._outgoing.get(source_id, [])
        if rel_type:
            edges = [e for e in edges if e.relationship_type == rel_type]
        return edges

    def get_incoming(
        self, target_id: str, rel_type: Optional[RelationshipType] = None
    ) -> List[TwinRelationship]:
        edges = self._incoming.get(target_id, [])
        if rel_type:
            edges = [e for e in edges if e.relationship_type == rel_type]
        return edges

    def get_neighbors(self, node_id: str) -> Set[str]:
        """Get all directly connected node IDs."""
        neighbors = set()
        for rel in self._outgoing.get(node_id, []):
            neighbors.add(rel.target_id)
        for rel in self._incoming.get(node_id, []):
            neighbors.add(rel.source_id)
        return neighbors

    def get_impact_chain(
        self, source_id: str, rel_types: Optional[List[RelationshipType]] = None, max_depth: int = 5
    ) -> List[Tuple[str, List[TwinRelationship]]]:
        """
        BFS to find all assets impacted by a source asset through
        specified relationship types.
        
        Returns list of (asset_id, path_of_relationships).
        Used for cross-asset KPI computation (e.g., condenser failure
        impacts downstream cases via REJECTS_HEAT_TO → AFFECTS_LOAD_OF).
        """
        visited: Set[str] = {source_id}
        queue: List[Tuple[str, List[TwinRelationship]]] = [(source_id, [])]
        results: List[Tuple[str, List[TwinRelationship]]] = []

        while queue:
            current_id, path = queue.pop(0)
            if len(path) >= max_depth:
                continue

            for rel in self._outgoing.get(current_id, []):
                if rel_types and rel.relationship_type not in rel_types:
                    continue
                if rel.target_id not in visited:
                    visited.add(rel.target_id)
                    new_path = path + [rel]
                    results.append((rel.target_id, new_path))
                    queue.append((rel.target_id, new_path))

        return results

    def get_thermal_interaction_group(self, asset_id: str) -> List[str]:
        """
        Find all assets in the same thermal interaction group.
        
        Traverses REJECTS_HEAT_TO and AFFECTS_LOAD_OF edges to find
        HVAC ↔ refrigeration coupling (e.g., condenser waste heat
        impacting HVAC cooling load).
        """
        thermal_types = [RelationshipType.REJECTS_HEAT_TO, RelationshipType.AFFECTS_LOAD_OF]
        impacts = self.get_impact_chain(asset_id, rel_types=thermal_types)
        return [asset_id] + [aid for aid, _ in impacts]

    def get_served_assets(self, asset_id: str) -> List[str]:
        """Get all assets served by this asset (SERVES relationship)."""
        return [r.target_id for r in self.get_outgoing(asset_id, RelationshipType.SERVES)]

    def get_circuit_group(self, asset_id: str) -> List[str]:
        """Get all assets sharing a circuit with this asset."""
        group = set()
        for rel in self.get_outgoing(asset_id, RelationshipType.SHARES_CIRCUIT_WITH):
            group.add(rel.target_id)
        for rel in self.get_incoming(asset_id, RelationshipType.SHARES_CIRCUIT_WITH):
            group.add(rel.source_id)
        return list(group)

    def find_cross_asset_kpi_dependencies(self, asset_id: Optional[str] = None) -> Dict[str, List[str]]:
        """
        For a given asset, find all cross-asset dependencies grouped
        by KPI relevance. Used by orchestration to determine which
        KPI crews need cross-asset data.

        When ``asset_id`` is not provided, returns aggregate dependencies
        across all known graph nodes.
        """
        if not asset_id:
            aggregate: Dict[str, Set[str]] = {
                "energy": set(),
                "refrigerant": set(),
                "food_safety": set(),
                "maintenance": set(),
            }
            node_ids = set(self._outgoing.keys()) | set(self._incoming.keys())
            for node_id in node_ids:
                deps = self.find_cross_asset_kpi_dependencies(node_id)
                for k, vals in deps.items():
                    aggregate[k].update(vals)
            return {k: sorted(v) for k, v in aggregate.items()}

        deps: Dict[str, List[str]] = {
            "energy": [],
            "refrigerant": [],
            "food_safety": [],
            "maintenance": [],
        }

        thermal_group = self.get_thermal_interaction_group(asset_id)
        deps["energy"] = thermal_group

        served = self.get_served_assets(asset_id)
        deps["food_safety"] = served
        deps["refrigerant"] = served

        circuit = self.get_circuit_group(asset_id)
        deps["energy"].extend(circuit)

        # Deduplicate
        for k in deps:
            deps[k] = list(set(deps[k]) - {asset_id})

        return deps

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edges": [e.to_dict() for e in self._all_edges],
            "node_count": len(set(
                [e.source_id for e in self._all_edges] +
                [e.target_id for e in self._all_edges]
            )),
            "edge_count": len(self._all_edges),
        }

    def stats(self) -> Dict[str, int]:
        nodes = set()
        for e in self._all_edges:
            nodes.add(e.source_id)
            nodes.add(e.target_id)
        by_type = defaultdict(int)
        for e in self._all_edges:
            by_type[e.relationship_type.value] += 1
        return {
            "nodes": len(nodes),
            "edges": len(self._all_edges),
            "by_type": dict(by_type),
        }

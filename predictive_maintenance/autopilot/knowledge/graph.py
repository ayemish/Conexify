"""
Knowledge Graph

Lightweight knowledge graph for asset relationships with ontology grounding.
Supports Brick Schema and Project Haystack concepts.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

logger = logging.getLogger(__name__)


class EntityType(str, Enum):
    """Entity types based on Brick Schema"""
    # Equipment
    EQUIPMENT = "Equipment"
    HVAC = "HVAC"
    AHU = "Air_Handling_Unit"
    RTU = "Rooftop_Unit"
    CHILLER = "Chiller"
    BOILER = "Boiler"
    VAV = "Variable_Air_Volume_Box"
    FCU = "Fan_Coil_Unit"
    CONDENSER = "Condenser"
    COMPRESSOR = "Compressor"
    
    # Locations
    LOCATION = "Location"
    BUILDING = "Building"
    FLOOR = "Floor"
    ZONE = "Zone"
    ROOM = "Room"
    
    # Points
    POINT = "Point"
    SENSOR = "Sensor"
    SETPOINT = "Setpoint"
    COMMAND = "Command"
    STATUS = "Status"
    
    # Documents
    DOCUMENT = "Document"
    MANUAL = "Manual"
    SOP = "Standard_Operating_Procedure"
    SPEC_SHEET = "Specification_Sheet"
    
    # Other
    SYSTEM = "System"
    MANUFACTURER = "Manufacturer"
    MODEL = "Model"


class RelationType(str, Enum):
    """Relationship types based on Brick Schema"""
    # Spatial
    HAS_LOCATION = "hasLocation"
    IS_LOCATION_OF = "isLocationOf"
    IS_PART_OF = "isPartOf"
    HAS_PART = "hasPart"
    
    # Points
    HAS_POINT = "hasPoint"
    IS_POINT_OF = "isPointOf"
    
    # Feeds
    FEEDS = "feeds"
    IS_FED_BY = "isFedBy"
    
    # Control
    CONTROLS = "controls"
    IS_CONTROLLED_BY = "isControlledBy"
    
    # Documents
    HAS_DOCUMENTATION = "hasDocumentation"
    DOCUMENTS = "documents"
    
    # Manufacturer
    HAS_MANUFACTURER = "hasManufacturer"
    HAS_MODEL = "hasModel"
    
    # Similar/Related
    SIMILAR_TO = "similarTo"
    RELATED_TO = "relatedTo"


@dataclass
class Entity:
    """Knowledge graph entity"""
    entity_id: str
    entity_type: EntityType
    name: str
    
    # Properties
    properties: Dict[str, Any] = field(default_factory=dict)
    
    # Metadata
    tenant_id: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # External references
    external_ids: Dict[str, str] = field(default_factory=dict)  # system -> id
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type.value,
            "name": self.name,
            "properties": self.properties,
            "tenant_id": self.tenant_id,
            "external_ids": self.external_ids,
        }


@dataclass
class Relationship:
    """Knowledge graph relationship"""
    relationship_id: str
    source_id: str
    target_id: str
    relation_type: RelationType
    
    # Properties
    properties: Dict[str, Any] = field(default_factory=dict)
    
    # Metadata
    tenant_id: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "relationship_id": self.relationship_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type.value,
            "properties": self.properties,
        }


class KnowledgeGraph:
    """
    In-memory knowledge graph with Brick Schema ontology support.
    
    Provides:
    - Entity and relationship management
    - Graph traversal and querying
    - Ontology-aware inference
    - Tenant isolation
    """
    
    def __init__(self):
        self._entities: Dict[str, Entity] = {}
        self._relationships: Dict[str, Relationship] = {}
        
        # Indexes for efficient querying
        self._by_type: Dict[EntityType, Set[str]] = {}
        self._by_tenant: Dict[str, Set[str]] = {}
        self._outgoing: Dict[str, List[str]] = {}  # entity_id -> relationship_ids
        self._incoming: Dict[str, List[str]] = {}  # entity_id -> relationship_ids
    
    def add_entity(self, entity: Entity) -> str:
        """Add an entity to the graph"""
        self._entities[entity.entity_id] = entity
        
        # Update indexes
        if entity.entity_type not in self._by_type:
            self._by_type[entity.entity_type] = set()
        self._by_type[entity.entity_type].add(entity.entity_id)
        
        if entity.tenant_id:
            if entity.tenant_id not in self._by_tenant:
                self._by_tenant[entity.tenant_id] = set()
            self._by_tenant[entity.tenant_id].add(entity.entity_id)
        
        logger.debug(f"Added entity {entity.entity_id} ({entity.entity_type.value})")
        return entity.entity_id
    
    def add_relationship(self, relationship: Relationship) -> str:
        """Add a relationship to the graph"""
        self._relationships[relationship.relationship_id] = relationship
        
        # Update indexes
        if relationship.source_id not in self._outgoing:
            self._outgoing[relationship.source_id] = []
        self._outgoing[relationship.source_id].append(relationship.relationship_id)
        
        if relationship.target_id not in self._incoming:
            self._incoming[relationship.target_id] = []
        self._incoming[relationship.target_id].append(relationship.relationship_id)
        
        logger.debug(
            f"Added relationship {relationship.source_id} "
            f"-[{relationship.relation_type.value}]-> {relationship.target_id}"
        )
        return relationship.relationship_id
    
    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get entity by ID"""
        return self._entities.get(entity_id)
    
    def get_entities_by_type(
        self,
        entity_type: EntityType,
        tenant_id: str = None,
    ) -> List[Entity]:
        """Get all entities of a type"""
        entity_ids = self._by_type.get(entity_type, set())
        
        entities = [self._entities[eid] for eid in entity_ids]
        
        if tenant_id:
            entities = [e for e in entities if e.tenant_id == tenant_id]
        
        return entities
    
    def get_related(
        self,
        entity_id: str,
        relation_type: RelationType = None,
        direction: str = "outgoing",
    ) -> List[Tuple[Entity, Relationship]]:
        """
        Get related entities.
        
        Args:
            entity_id: Source entity
            relation_type: Filter by relationship type
            direction: "outgoing", "incoming", or "both"
            
        Returns:
            List of (related_entity, relationship) tuples
        """
        results = []
        
        if direction in ["outgoing", "both"]:
            rel_ids = self._outgoing.get(entity_id, [])
            for rel_id in rel_ids:
                rel = self._relationships[rel_id]
                if relation_type and rel.relation_type != relation_type:
                    continue
                target = self._entities.get(rel.target_id)
                if target:
                    results.append((target, rel))
        
        if direction in ["incoming", "both"]:
            rel_ids = self._incoming.get(entity_id, [])
            for rel_id in rel_ids:
                rel = self._relationships[rel_id]
                if relation_type and rel.relation_type != relation_type:
                    continue
                source = self._entities.get(rel.source_id)
                if source:
                    results.append((source, rel))
        
        return results
    
    def find_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5,
    ) -> Optional[List[str]]:
        """
        Find shortest path between two entities.
        
        Returns:
            List of entity IDs in path, or None if no path
        """
        if source_id == target_id:
            return [source_id]
        
        visited = {source_id}
        queue = [(source_id, [source_id])]
        
        while queue:
            current_id, path = queue.pop(0)
            
            if len(path) > max_depth:
                continue
            
            for rel_id in self._outgoing.get(current_id, []):
                rel = self._relationships[rel_id]
                if rel.target_id == target_id:
                    return path + [target_id]
                
                if rel.target_id not in visited:
                    visited.add(rel.target_id)
                    queue.append((rel.target_id, path + [rel.target_id]))
        
        return None
    
    def query(
        self,
        entity_type: EntityType = None,
        properties: Dict[str, Any] = None,
        tenant_id: str = None,
        limit: int = 100,
    ) -> List[Entity]:
        """
        Query entities with filters.
        
        Args:
            entity_type: Filter by type
            properties: Filter by property values
            tenant_id: Filter by tenant
            limit: Maximum results
            
        Returns:
            List of matching entities
        """
        # Start with all entities or type-filtered
        if entity_type:
            entity_ids = self._by_type.get(entity_type, set())
        else:
            entity_ids = set(self._entities.keys())
        
        # Apply tenant filter
        if tenant_id:
            tenant_entities = self._by_tenant.get(tenant_id, set())
            entity_ids = entity_ids.intersection(tenant_entities)
        
        # Apply property filters
        results = []
        for eid in entity_ids:
            entity = self._entities[eid]
            
            if properties:
                match = all(
                    entity.properties.get(k) == v
                    for k, v in properties.items()
                )
                if not match:
                    continue
            
            results.append(entity)
            
            if len(results) >= limit:
                break
        
        return results
    
    def get_equipment_hierarchy(
        self,
        equipment_id: str,
    ) -> Dict[str, Any]:
        """
        Get equipment hierarchy (parent systems, child components, points).
        
        Returns:
            Hierarchical dict representation
        """
        entity = self.get_entity(equipment_id)
        if not entity:
            return {}
        
        hierarchy = {
            "entity": entity.to_dict(),
            "parent_systems": [],
            "child_components": [],
            "points": [],
            "documentation": [],
        }
        
        # Get parent systems
        for related, rel in self.get_related(equipment_id, RelationType.IS_PART_OF, "outgoing"):
            hierarchy["parent_systems"].append(related.to_dict())
        
        # Get child components
        for related, rel in self.get_related(equipment_id, RelationType.HAS_PART, "outgoing"):
            hierarchy["child_components"].append(related.to_dict())
        
        # Get points
        for related, rel in self.get_related(equipment_id, RelationType.HAS_POINT, "outgoing"):
            hierarchy["points"].append(related.to_dict())
        
        # Get documentation
        for related, rel in self.get_related(equipment_id, RelationType.HAS_DOCUMENTATION, "outgoing"):
            hierarchy["documentation"].append(related.to_dict())
        
        return hierarchy
    
    def get_similar_equipment(
        self,
        equipment_id: str,
        tenant_id: str = None,
    ) -> List[Entity]:
        """
        Find similar equipment (same type, manufacturer, model).
        
        Returns:
            List of similar equipment entities
        """
        entity = self.get_entity(equipment_id)
        if not entity:
            return []
        
        # Get equipment of same type
        candidates = self.get_entities_by_type(entity.entity_type, tenant_id)
        
        # Filter by manufacturer/model
        manufacturer = entity.properties.get("manufacturer")
        model = entity.properties.get("model")
        
        similar = []
        for candidate in candidates:
            if candidate.entity_id == equipment_id:
                continue
            
            # Same manufacturer and model = very similar
            if (manufacturer and candidate.properties.get("manufacturer") == manufacturer and
                model and candidate.properties.get("model") == model):
                similar.append(candidate)
        
        return similar
    
    def export(self) -> Dict[str, Any]:
        """Export graph to serializable format"""
        return {
            "entities": [e.to_dict() for e in self._entities.values()],
            "relationships": [r.to_dict() for r in self._relationships.values()],
        }
    
    def import_data(self, data: Dict[str, Any]):
        """Import graph from serialized format"""
        for e_data in data.get("entities", []):
            entity = Entity(
                entity_id=e_data["entity_id"],
                entity_type=EntityType(e_data["entity_type"]),
                name=e_data["name"],
                properties=e_data.get("properties", {}),
                tenant_id=e_data.get("tenant_id", ""),
                external_ids=e_data.get("external_ids", {}),
            )
            self.add_entity(entity)
        
        for r_data in data.get("relationships", []):
            rel = Relationship(
                relationship_id=r_data["relationship_id"],
                source_id=r_data["source_id"],
                target_id=r_data["target_id"],
                relation_type=RelationType(r_data["relation_type"]),
                properties=r_data.get("properties", {}),
                tenant_id=r_data.get("tenant_id", ""),
            )
            self.add_relationship(rel)

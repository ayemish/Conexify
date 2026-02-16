"""
Estate Brain

Enhanced knowledge layer combining RAG retrieval with knowledge graph.
Provides context-aware answers with citations for autopilot planning.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
import uuid

from .graph import KnowledgeGraph, Entity, EntityType, RelationType

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeQuery:
    """Query to the Estate Brain"""
    query_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    
    # Query content
    question: str = ""
    
    # Context
    tenant_id: str = ""
    asset_id: Optional[str] = None
    fault_type: Optional[str] = None
    
    # Options
    include_similar_cases: bool = True
    include_documentation: bool = True
    include_graph_context: bool = True
    max_results: int = 10


@dataclass
class Citation:
    """Citation for a knowledge result"""
    source_id: str
    source_type: str  # document, equipment, case, graph
    title: str
    excerpt: str
    confidence: float = 0.0
    url: Optional[str] = None


@dataclass
class KnowledgeResult:
    """Result from Estate Brain query"""
    query_id: str
    
    # Answer
    answer: str
    confidence: float = 0.0
    
    # Citations
    citations: List[Citation] = field(default_factory=list)
    
    # Related entities
    related_entities: List[Dict[str, Any]] = field(default_factory=list)
    
    # Similar cases
    similar_cases: List[Dict[str, Any]] = field(default_factory=list)
    
    # Suggested actions
    suggested_actions: List[str] = field(default_factory=list)
    
    # Metadata
    processed_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query_id": self.query_id,
            "answer": self.answer,
            "confidence": self.confidence,
            "citations": [
                {
                    "source_id": c.source_id,
                    "source_type": c.source_type,
                    "title": c.title,
                    "excerpt": c.excerpt,
                    "confidence": c.confidence,
                }
                for c in self.citations
            ],
            "related_entities": self.related_entities,
            "similar_cases": self.similar_cases,
            "suggested_actions": self.suggested_actions,
            "processed_at": self.processed_at.isoformat(),
        }


class EstateBrain:
    """
    Estate Brain knowledge layer.
    
    Combines:
    - RAG document retrieval with citations
    - Knowledge graph for asset relationships
    - Case history for similar fault resolution
    - Tenant-isolated knowledge stores
    """
    
    def __init__(
        self,
        rag_service: Any = None,
        knowledge_graph: KnowledgeGraph = None,
        session_factory: Callable = None,
    ):
        self.rag_service = rag_service
        self.graph = knowledge_graph or KnowledgeGraph()
        self.session_factory = session_factory
        
        # In-memory document store (would be vector DB in production)
        self._documents: Dict[str, Dict[str, Any]] = {}
        self._case_history: List[Dict[str, Any]] = []
    
    def query(self, query: KnowledgeQuery) -> KnowledgeResult:
        """
        Query the Estate Brain for knowledge.
        
        Args:
            query: Knowledge query
            
        Returns:
            KnowledgeResult with answer and citations
        """
        result = KnowledgeResult(query_id=query.query_id)
        
        # 1. RAG document retrieval
        if query.include_documentation:
            doc_results = self._search_documents(query)
            result.citations.extend(doc_results)
        
        # 2. Knowledge graph context
        if query.include_graph_context and query.asset_id:
            graph_results = self._get_graph_context(query)
            result.related_entities = graph_results
        
        # 3. Similar case lookup
        if query.include_similar_cases:
            similar = self._find_similar_cases(query)
            result.similar_cases = similar
        
        # 4. Generate answer
        result.answer = self._generate_answer(query, result)
        result.confidence = self._compute_confidence(result)
        
        # 5. Suggest actions
        result.suggested_actions = self._suggest_actions(query, result)
        
        return result
    
    def _search_documents(self, query: KnowledgeQuery) -> List[Citation]:
        """Search indexed documents"""
        citations = []
        
        # Use RAG service if available
        if self.rag_service:
            try:
                results = self.rag_service.search(
                    query=query.question,
                    tenant_id=query.tenant_id,
                    limit=query.max_results,
                )
                
                for r in results:
                    citations.append(Citation(
                        source_id=r.get("doc_id", ""),
                        source_type="document",
                        title=r.get("title", ""),
                        excerpt=r.get("excerpt", ""),
                        confidence=r.get("score", 0.0),
                    ))
            except Exception as e:
                logger.warning(f"RAG search failed: {e}")
        
        # Search in-memory documents
        for doc_id, doc in self._documents.items():
            if query.tenant_id and doc.get("tenant_id") != query.tenant_id:
                continue
            
            # Simple keyword matching (would be vector similarity in production)
            content = doc.get("content", "").lower()
            if query.question.lower() in content:
                citations.append(Citation(
                    source_id=doc_id,
                    source_type=doc.get("doc_type", "document"),
                    title=doc.get("title", ""),
                    excerpt=content[:200],
                    confidence=0.5,
                ))
        
        return citations[:query.max_results]
    
    def _get_graph_context(self, query: KnowledgeQuery) -> List[Dict[str, Any]]:
        """Get knowledge graph context for an asset"""
        context = []
        
        if not query.asset_id:
            return context
        
        # Get equipment hierarchy
        hierarchy = self.graph.get_equipment_hierarchy(query.asset_id)
        if hierarchy:
            context.append({
                "type": "hierarchy",
                "data": hierarchy,
            })
        
        # Get similar equipment
        similar = self.graph.get_similar_equipment(query.asset_id, query.tenant_id)
        for eq in similar[:5]:
            context.append({
                "type": "similar_equipment",
                "data": eq.to_dict(),
            })
        
        # Get related points
        related = self.graph.get_related(query.asset_id, RelationType.HAS_POINT)
        for entity, rel in related[:20]:
            context.append({
                "type": "point",
                "data": entity.to_dict(),
            })
        
        return context
    
    def _find_similar_cases(self, query: KnowledgeQuery) -> List[Dict[str, Any]]:
        """Find similar past cases"""
        similar = []
        
        for case in self._case_history:
            # Match by fault type
            if query.fault_type and case.get("fault_type") == query.fault_type:
                similar.append(case)
                continue
            
            # Match by asset
            if query.asset_id and case.get("asset_id") == query.asset_id:
                similar.append(case)
        
        # Sort by recency
        similar.sort(key=lambda c: c.get("resolved_at", ""), reverse=True)
        
        return similar[:5]
    
    def _generate_answer(
        self,
        query: KnowledgeQuery,
        result: KnowledgeResult,
    ) -> str:
        """Generate answer based on retrieved knowledge"""
        parts = []
        
        # Summarize from citations
        if result.citations:
            parts.append("Based on available documentation:")
            for citation in result.citations[:3]:
                parts.append(f"- {citation.excerpt[:100]}...")
        
        # Add graph context
        if result.related_entities:
            parts.append("\nRelated equipment and points found in knowledge graph.")
        
        # Add similar cases
        if result.similar_cases:
            parts.append(f"\nFound {len(result.similar_cases)} similar past cases:")
            for case in result.similar_cases[:2]:
                resolution = case.get("resolution", "Unknown resolution")
                parts.append(f"- {resolution}")
        
        if not parts:
            return "No relevant knowledge found for this query."
        
        return "\n".join(parts)
    
    def _compute_confidence(self, result: KnowledgeResult) -> float:
        """Compute confidence score for the result"""
        if not result.citations and not result.similar_cases:
            return 0.0
        
        # Average citation confidence
        if result.citations:
            avg_citation = sum(c.confidence for c in result.citations) / len(result.citations)
        else:
            avg_citation = 0.0
        
        # Boost if similar cases found
        case_boost = min(0.2 * len(result.similar_cases), 0.4)
        
        # Boost if graph context
        graph_boost = 0.1 if result.related_entities else 0.0
        
        return min(avg_citation + case_boost + graph_boost, 1.0)
    
    def _suggest_actions(
        self,
        query: KnowledgeQuery,
        result: KnowledgeResult,
    ) -> List[str]:
        """Suggest actions based on knowledge"""
        suggestions = []
        
        # From similar cases
        for case in result.similar_cases:
            action = case.get("resolution_action")
            if action and action not in suggestions:
                suggestions.append(action)
        
        # Default suggestions by fault type
        fault_suggestions = {
            "condenser_fouling": [
                "Check condenser coil cleanliness",
                "Verify airflow across condenser",
                "Consider scheduling coil cleaning",
            ],
            "low_refrigerant": [
                "Check for refrigerant leaks",
                "Verify superheat and subcool values",
                "Contact refrigerant technician",
            ],
            "compressor_degradation": [
                "Monitor compressor current draw",
                "Check suction and discharge pressures",
                "Schedule compressor inspection",
            ],
        }
        
        if query.fault_type and query.fault_type in fault_suggestions:
            for suggestion in fault_suggestions[query.fault_type]:
                if suggestion not in suggestions:
                    suggestions.append(suggestion)
        
        return suggestions[:5]
    
    # Document management
    
    def index_document(
        self,
        doc_id: str,
        title: str,
        content: str,
        doc_type: str = "document",
        tenant_id: str = "",
        metadata: Dict[str, Any] = None,
    ):
        """Index a document for retrieval"""
        self._documents[doc_id] = {
            "doc_id": doc_id,
            "title": title,
            "content": content,
            "doc_type": doc_type,
            "tenant_id": tenant_id,
            "metadata": metadata or {},
            "indexed_at": datetime.utcnow().isoformat(),
        }
        
        # Also use RAG service if available
        if self.rag_service:
            try:
                self.rag_service.index_document(
                    doc_id=doc_id,
                    content=content,
                    metadata={
                        "title": title,
                        "doc_type": doc_type,
                        "tenant_id": tenant_id,
                        **(metadata or {}),
                    },
                )
            except Exception as e:
                logger.warning(f"RAG indexing failed: {e}")
        
        logger.info(f"Indexed document {doc_id}: {title}")
    
    def add_case(
        self,
        case_id: str,
        tenant_id: str,
        asset_id: str,
        fault_type: str,
        resolution: str,
        resolution_action: str = "",
        resolved_at: datetime = None,
    ):
        """Add a resolved case to history"""
        case = {
            "case_id": case_id,
            "tenant_id": tenant_id,
            "asset_id": asset_id,
            "fault_type": fault_type,
            "resolution": resolution,
            "resolution_action": resolution_action,
            "resolved_at": (resolved_at or datetime.utcnow()).isoformat(),
        }
        self._case_history.append(case)
        logger.info(f"Added case {case_id} to history")
    
    # Graph management
    
    def add_equipment(
        self,
        equipment_id: str,
        name: str,
        equipment_type: EntityType,
        tenant_id: str,
        properties: Dict[str, Any] = None,
    ) -> str:
        """Add equipment to knowledge graph"""
        entity = Entity(
            entity_id=equipment_id,
            entity_type=equipment_type,
            name=name,
            tenant_id=tenant_id,
            properties=properties or {},
        )
        return self.graph.add_entity(entity)
    
    def add_point(
        self,
        point_id: str,
        name: str,
        equipment_id: str,
        point_type: EntityType = EntityType.POINT,
        tenant_id: str = "",
        properties: Dict[str, Any] = None,
    ) -> str:
        """Add a point and link to equipment"""
        # Add point entity
        entity = Entity(
            entity_id=point_id,
            entity_type=point_type,
            name=name,
            tenant_id=tenant_id,
            properties=properties or {},
        )
        self.graph.add_entity(entity)
        
        # Link to equipment
        rel = Relationship(
            relationship_id=f"rel_{uuid.uuid4().hex[:8]}",
            source_id=equipment_id,
            target_id=point_id,
            relation_type=RelationType.HAS_POINT,
            tenant_id=tenant_id,
        )
        self.graph.add_relationship(rel)
        
        return point_id
    
    def link_documentation(
        self,
        equipment_id: str,
        doc_id: str,
        tenant_id: str = "",
    ):
        """Link documentation to equipment"""
        rel = Relationship(
            relationship_id=f"rel_{uuid.uuid4().hex[:8]}",
            source_id=equipment_id,
            target_id=doc_id,
            relation_type=RelationType.HAS_DOCUMENTATION,
            tenant_id=tenant_id,
        )
        self.graph.add_relationship(rel)

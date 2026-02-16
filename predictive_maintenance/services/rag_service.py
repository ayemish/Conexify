"""RAG Service for embeddings, indexing, and conversational querying."""

import logging
import uuid
import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable, Tuple

import numpy as np

try:
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore

try:
    from sqlalchemy.orm import Session  # type: ignore
except Exception:  # pragma: no cover
    Session = None  # type: ignore

from ..config import settings
from ..persistence.repositories import RagRepository
from ..persistence.models import RagDocumentModel

logger = logging.getLogger(__name__)


@dataclass
class RagDocument:
    doc_id: str
    doc_type: str
    content: str
    embedding: List[float]
    asset_id: Optional[str] = None
    site_id: Optional[str] = None
    metadata: Dict[str, Any] = None
    created_at: Optional[datetime] = None


@dataclass
class RagSearchResult:
    doc_id: str
    doc_type: str
    content: str
    score: float
    asset_id: Optional[str]
    site_id: Optional[str]
    metadata: Dict[str, Any]


class RagService:
    """Embeddings + retrieval with optional pgvector storage."""

    def __init__(self, session_factory: Optional[Callable[[], Session]] = None):
        self.session_factory = session_factory
        self.embedding_model = settings.openai.embedding_model
        self.chat_model = settings.openai.chat_model
        self.transcription_model = settings.openai.transcription_model
        self.max_context_docs = settings.openai.max_context_docs
        self._client = None
        self._memory_store: List[RagDocument] = []

    def _client_or_raise(self):
        if OpenAI is None:
            raise RuntimeError("OpenAI client not available. Install openai>=1.30.0")
        if self._client is None:
            self._client = OpenAI(api_key=settings.openai.api_key)
        return self._client

    def embed_text(self, text: str) -> List[float]:
        client = self._client_or_raise()
        response = client.embeddings.create(
            model=self.embedding_model,
            input=text,
        )
        return list(response.data[0].embedding)

    def format_document(self, doc_type: str, payload: Dict[str, Any]) -> str:
        """Create structured RAG content for consistent embeddings."""
        lines = [f"Type: {doc_type}"]
        for key, value in payload.items():
            lines.append(f"{key}: {value}")
        return "\n".join(lines)

    def _make_doc_id(self, doc_type: str, content: str, asset_id: Optional[str]) -> str:
        base = f"{doc_type}|{asset_id or 'global'}|{content}".encode("utf-8")
        digest = hashlib.sha256(base).hexdigest()[:16]
        return f"{doc_type}_{asset_id or 'global'}_{digest}"

    def index_document(
        self,
        doc_type: str,
        content: str,
        asset_id: Optional[str] = None,
        site_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        doc_id: Optional[str] = None,
    ) -> str:
        """Index a document by embedding and storing it."""
        doc_id = doc_id or self._make_doc_id(doc_type, content, asset_id)
        embedding = self.embed_text(content)
        metadata = metadata or {}
        metadata.setdefault("content_hash", doc_id.split("_")[-1])

        if self.session_factory is None:
            # Dedupe by doc_id in memory
            for i, existing in enumerate(self._memory_store):
                if existing.doc_id == doc_id and existing.content == content:
                    return doc_id
                if existing.doc_id == doc_id:
                    self._memory_store[i] = RagDocument(
                        doc_id=doc_id,
                        doc_type=doc_type,
                        content=content,
                        embedding=embedding,
                        asset_id=asset_id,
                        site_id=site_id,
                        metadata=metadata,
                        created_at=datetime.utcnow(),
                    )
                    return doc_id
            self._memory_store.append(
                RagDocument(
                    doc_id=doc_id,
                    doc_type=doc_type,
                    content=content,
                    embedding=embedding,
                    asset_id=asset_id,
                    site_id=site_id,
                    metadata=metadata,
                    created_at=datetime.utcnow(),
                )
            )
            return doc_id

        session = self.session_factory()
        try:
            repo = RagRepository(session)
            repo.upsert(
                doc_id=doc_id,
                doc_type=doc_type,
                content=content,
                embedding=embedding,
                embedding_dim=len(embedding),
                asset_id=asset_id,
                site_id=site_id,
                metadata=metadata,
            )
            session.commit()
            return doc_id
        except Exception as exc:  # pragma: no cover
            session.rollback()
            logger.warning(f"RAG index failed, falling back to memory: {exc}")
            self._memory_store.append(
                RagDocument(
                    doc_id=doc_id,
                    doc_type=doc_type,
                    content=content,
                    embedding=embedding,
                    asset_id=asset_id,
                    site_id=site_id,
                    metadata=metadata,
                    created_at=datetime.utcnow(),
                )
            )
            return doc_id
        finally:
            session.close()

    def search(
        self,
        query: str,
        asset_id: Optional[str] = None,
        site_id: Optional[str] = None,
        top_k: int = 5,
    ) -> List[RagSearchResult]:
        """Retrieve top documents by cosine similarity."""
        query_embedding = np.array(self.embed_text(query), dtype=float)

        # Memory-only search
        if self.session_factory is None:
            return self._search_memory(query_embedding, asset_id, site_id, top_k)

        session = self.session_factory()
        try:
            query_q = session.query(RagDocumentModel)
            if asset_id:
                query_q = query_q.filter(RagDocumentModel.asset_id == asset_id)
            if site_id:
                query_q = query_q.filter(RagDocumentModel.site_id == site_id)

            # If pgvector available, use database distance. Otherwise fallback to in-memory scoring.
            if hasattr(RagDocumentModel.embedding, "cosine_distance"):
                distance = RagDocumentModel.embedding.cosine_distance(query_embedding)
                rows = (
                    query_q.add_columns(distance.label("distance"))
                    .order_by("distance")
                    .limit(top_k)
                    .all()
                )
                results = []
                for doc, dist in rows:
                    score = float(1.0 - dist) if dist is not None else 0.0
                    results.append(
                        RagSearchResult(
                            doc_id=doc.doc_id,
                            doc_type=doc.doc_type,
                            content=doc.content,
                            score=score,
                            asset_id=doc.asset_id,
                            site_id=doc.site_id,
                            metadata=doc.doc_metadata or {},
                        )
                    )
                return results

            # Fallback: retrieve recent docs and score in Python
            docs = query_q.order_by(RagDocumentModel.created_at.desc()).limit(200).all()
            return self._score_docs(query_embedding, docs, top_k)
        finally:
            session.close()

    def _score_docs(self, query_embedding: np.ndarray, docs, top_k: int) -> List[RagSearchResult]:
        scored = []
        q = query_embedding / (np.linalg.norm(query_embedding) + 1e-8)
        for doc in docs:
            emb = np.array(doc.embedding or [], dtype=float)
            if emb.size == 0:
                continue
            emb = emb / (np.linalg.norm(emb) + 1e-8)
            score = float(np.dot(q, emb))
            scored.append((score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, doc in scored[:top_k]:
            results.append(
                RagSearchResult(
                    doc_id=doc.doc_id,
                    doc_type=doc.doc_type,
                    content=doc.content,
                    score=score,
                    asset_id=doc.asset_id,
                    site_id=doc.site_id,
                    metadata=doc.doc_metadata or {},
                )
            )
        return results

    def _search_memory(
        self,
        query_embedding: np.ndarray,
        asset_id: Optional[str],
        site_id: Optional[str],
        top_k: int,
    ) -> List[RagSearchResult]:
        q = query_embedding / (np.linalg.norm(query_embedding) + 1e-8)
        scored = []
        for doc in self._memory_store:
            if asset_id and doc.asset_id != asset_id:
                continue
            if site_id and doc.site_id != site_id:
                continue
            emb = np.array(doc.embedding, dtype=float)
            emb = emb / (np.linalg.norm(emb) + 1e-8)
            score = float(np.dot(q, emb))
            scored.append((score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, doc in scored[:top_k]:
            results.append(
                RagSearchResult(
                    doc_id=doc.doc_id,
                    doc_type=doc.doc_type,
                    content=doc.content,
                    score=score,
                    asset_id=doc.asset_id,
                    site_id=doc.site_id,
                    metadata=doc.doc_metadata or {},
                )
            )
        return results

    def answer(self, query: str, results: List[RagSearchResult]) -> str:
        """Use OpenAI Responses API to answer based on retrieved context."""
        client = self._client_or_raise()
        context_chunks = []
        for r in results[: self.max_context_docs]:
            context_chunks.append(f"[{r.doc_type}] {r.content}")
        context_text = "\n\n".join(context_chunks)
        prompt = (
            "You are a predictive maintenance assistant. Answer the user question using the provided context. "
            "If the context is insufficient, say what is missing.\n\n"
            f"Context:\n{context_text}\n\nQuestion: {query}"
        )
        response = client.responses.create(
            model=self.chat_model,
            input=prompt,
        )
        # The Responses API returns output_text for convenience
        return response.output_text

    def transcribe_audio(self, audio_file) -> str:
        """Transcribe audio to text using Whisper."""
        client = self._client_or_raise()
        transcript = client.audio.transcriptions.create(
            model=self.transcription_model,
            file=audio_file,
        )
        return transcript.text


_rag_service: Optional[RagService] = None


def get_rag_service(session_factory: Optional[Callable[[], Session]] = None) -> RagService:
    global _rag_service
    if _rag_service is None:
        _rag_service = RagService(session_factory=session_factory)
    return _rag_service

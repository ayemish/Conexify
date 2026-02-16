"""RAG Store for the Scenario Advisor conversational interface.

Dual-mode embedding strategy:
- OpenAI embeddings when API key is available
- Hash-based fallback for offline/dev use

Provides semantic memory for scenario catalog indexing and execution result retrieval.
"""

import hashlib
import json
import logging
import math
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Attempt OpenAI import
try:
    import openai as _openai_mod  # type: ignore
except Exception:
    _openai_mod = None


@dataclass
class RagDocument:
    """A single indexed document in the RAG store."""
    doc_id: str
    doc_type: str  # "scenario_catalog" | "scenario_result" | "knowledge"
    content: str
    embedding: List[float]
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RagSearchResult:
    """A scored search result from the RAG store."""
    doc_id: str
    doc_type: str
    content: str
    score: float
    asset_id: Optional[str] = None
    site_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class RagStore:
    """In-memory RAG store with dual-mode embedding and JSON persistence.

    Parameters
    ----------
    namespace : str
        Namespace prefix for document IDs.
    dim : int
        Embedding dimension for hash-based fallback.
    embedding_model : str
        OpenAI embedding model name.
    """

    def __init__(
        self,
        namespace: str = "scenario_advisor",
        dim: int = 256,
        embedding_model: Optional[str] = None,
    ):
        self.namespace = namespace
        self.dim = dim
        self.embedding_model = embedding_model or os.environ.get(
            "RMN_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
        )
        self._docs: List[RagDocument] = []
        self._openai_client = None
        self._use_openai = self._init_openai()
        self._store_path = self._resolve_store_path()
        self._load()

    # ------------------------------------------------------------------
    # Embedding modes
    # ------------------------------------------------------------------

    def _init_openai(self) -> bool:
        """Try to initialize OpenAI client for embeddings."""
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            for k, v in os.environ.items():
                if k.lower() == "openai_api_key":
                    api_key = v
                    break
        if not api_key:
            try:
                from predictive_maintenance.config import settings
                api_key = settings.openai.api_key
            except Exception:
                api_key = None
        if not api_key or _openai_mod is None:
            return False
        try:
            self._openai_client = _openai_mod.OpenAI(api_key=api_key)
            return True
        except Exception:
            return False

    def embed_text(self, text: str) -> List[float]:
        """Embed text using OpenAI or hash-based fallback."""
        if self._use_openai and self._openai_client is not None:
            try:
                resp = self._openai_client.embeddings.create(
                    model=self.embedding_model,
                    input=text,
                )
                return list(resp.data[0].embedding)
            except Exception as exc:
                logger.warning("OpenAI embedding failed, falling back to hash: %s", exc)
        return self._hash_embed(text)

    def _hash_embed(self, text: str, dim: Optional[int] = None) -> List[float]:
        """Deterministic hash-based embedding fallback.

        Algorithm:
        1. Tokenize on word boundaries, lowercase.
        2. For each token, MD5 → bucket index → increment.
        3. L2-normalize the vector.
        """
        dim = dim or self.dim
        vec = [0.0] * dim
        tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
        for token in tokens:
            digest = hashlib.md5(token.encode("utf-8")).hexdigest()
            bucket = int(digest, 16) % dim
            vec[bucket] += 1.0
        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    # ------------------------------------------------------------------
    # Document ID generation
    # ------------------------------------------------------------------

    def _make_doc_id(self, doc_type: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        meta_id = ""
        if metadata:
            meta_id = metadata.get("scenario_id", "") or metadata.get("id", "")
        raw = f"{doc_type}|{meta_id}|{content}".encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()[:16]
        return f"{self.namespace}_{doc_type}_{digest}"

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index_document(
        self,
        doc_type: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        doc_id: Optional[str] = None,
        persist: bool = True,
    ) -> str:
        """Index a document with upsert semantics.

        If a document with the same doc_id exists, it is replaced in-place.
        """
        metadata = metadata or {}
        doc_id = doc_id or self._make_doc_id(doc_type, content, metadata)
        embedding = self.embed_text(content)
        new_doc = RagDocument(
            doc_id=doc_id,
            doc_type=doc_type,
            content=content,
            embedding=embedding,
            metadata=metadata,
            created_at=datetime.utcnow(),
        )
        # Upsert: replace if exists
        for i, existing in enumerate(self._docs):
            if existing.doc_id == doc_id:
                self._docs[i] = new_doc
                if persist:
                    self._save()
                return doc_id
        self._docs.append(new_doc)
        if persist:
            self._save()
        return doc_id

    def bulk_index(self, documents: List[Dict[str, Any]]) -> List[str]:
        """Index multiple documents efficiently (single persist at end)."""
        ids = []
        for doc in documents:
            doc_id = self.index_document(
                doc_type=doc.get("doc_type", "knowledge"),
                content=doc.get("content", ""),
                metadata=doc.get("metadata"),
                doc_id=doc.get("doc_id"),
                persist=False,
            )
            ids.append(doc_id)
        self._save()
        return ids

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        top_k: int = 5,
        asset_id: Optional[str] = None,
        site_id: Optional[str] = None,
        doc_type: Optional[str] = None,
    ) -> List[RagSearchResult]:
        """Search for documents by cosine similarity."""
        query_vec = self._l2_normalize(self.embed_text(query))
        scored = []
        for doc in self._docs:
            if doc_type and doc.doc_type != doc_type:
                continue
            doc_asset_id = str(doc.metadata.get("asset_id", "") or "")
            doc_site_id = str(doc.metadata.get("site_id", "") or "")
            if asset_id and doc_asset_id and doc_asset_id != asset_id:
                continue
            if site_id and doc_site_id and doc_site_id != site_id:
                continue
            doc_vec = self._l2_normalize(doc.embedding)
            score = self._dot(query_vec, doc_vec)
            scored.append(RagSearchResult(
                doc_id=doc.doc_id,
                doc_type=doc.doc_type,
                content=doc.content,
                score=score,
                asset_id=doc_asset_id or None,
                site_id=doc_site_id or None,
                metadata=doc.metadata,
            ))
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    def answer(self, query: str, results: List[RagSearchResult]) -> str:
        """Generate an answer from retrieved context, with OpenAI when available."""
        context_chunks = [f"[{r.doc_type}] {r.content}" for r in results[:5]]
        context_text = "\n\n".join(context_chunks)

        if self._use_openai and self._openai_client is not None:
            try:
                model = os.environ.get("RMN_OPENAI_CHAT_MODEL")
                if not model:
                    try:
                        from predictive_maintenance.config import settings
                        model = settings.openai.chat_model
                    except Exception:
                        model = "gpt-4o-mini"
                prompt = (
                    "You are a predictive maintenance assistant for HVAC/R assets. "
                    "Answer using only the provided context; if insufficient, state what is missing.\n\n"
                    f"Context:\n{context_text}\n\nQuestion: {query}"
                )
                response = self._openai_client.responses.create(
                    model=model or "gpt-4o-mini",
                    input=prompt,
                )
                text = getattr(response, "output_text", None)
                if text:
                    return text
            except Exception as exc:
                logger.warning("RAG answer generation failed, falling back to extractive mode: %s", exc)

        if not results:
            return "I could not find matching context for that question."
        bullets = []
        for r in results[:3]:
            snippet = (r.content or "").strip().replace("\n", " ")
            bullets.append(f"- [{r.doc_type}] {snippet[:220]}")
        return "Based on indexed context:\n" + "\n".join(bullets)

    def transcribe_audio(self, audio_file) -> str:
        """Transcribe audio with OpenAI Whisper when available."""
        if not (self._use_openai and self._openai_client is not None):
            raise RuntimeError("Audio transcription unavailable: OpenAI API key not configured")
        model = os.environ.get("RMN_OPENAI_TRANSCRIPTION_MODEL", "whisper-1")
        transcript = self._openai_client.audio.transcriptions.create(
            model=model,
            file=audio_file,
        )
        return transcript.text

    @staticmethod
    def _l2_normalize(vec: List[float]) -> List[float]:
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            return [v / norm for v in vec]
        return vec

    @staticmethod
    def _dot(a: List[float], b: List[float]) -> float:
        return sum(x * y for x, y in zip(a, b))

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _resolve_store_path(self) -> Optional[str]:
        env_path = os.environ.get("RMN_RAG_STORE_PATH")
        if env_path:
            return env_path
        # Default: repo_root/data/rmn_rag_store.json
        try:
            base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            data_dir = os.path.join(base, "data")
            os.makedirs(data_dir, exist_ok=True)
            return os.path.join(data_dir, "rmn_rag_store.json")
        except Exception:
            return None

    def _load(self):
        if not self._store_path or not os.path.exists(self._store_path):
            return
        try:
            with open(self._store_path, "r") as f:
                data = json.load(f)
            for doc_data in data.get("documents", []):
                self._docs.append(RagDocument(
                    doc_id=doc_data["doc_id"],
                    doc_type=doc_data["doc_type"],
                    content=doc_data["content"],
                    embedding=doc_data.get("embedding", []),
                    metadata=doc_data.get("metadata", {}),
                    created_at=datetime.fromisoformat(doc_data["created_at"])
                    if doc_data.get("created_at") else datetime.utcnow(),
                ))
            logger.info("RAG store loaded %d documents from %s", len(self._docs), self._store_path)
        except Exception as exc:
            logger.warning("Failed to load RAG store: %s", exc)

    def _save(self):
        if not self._store_path:
            return
        try:
            data = {
                "namespace": self.namespace,
                "documents": [
                    {
                        "doc_id": d.doc_id,
                        "doc_type": d.doc_type,
                        "content": d.content,
                        "embedding": d.embedding,
                        "metadata": d.metadata,
                        "created_at": d.created_at.isoformat() if d.created_at else None,
                    }
                    for d in self._docs
                ],
            }
            os.makedirs(os.path.dirname(self._store_path), exist_ok=True)
            with open(self._store_path, "w") as f:
                json.dump(data, f)
        except Exception as exc:
            logger.warning("Failed to save RAG store: %s", exc)

    @property
    def document_count(self) -> int:
        return len(self._docs)

    def get_documents_by_type(self, doc_type: str) -> List[RagDocument]:
        return [d for d in self._docs if d.doc_type == doc_type]

import os
import uuid
import sys
import pathlib

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from predictive_maintenance.persistence.database import Base, get_engine
from predictive_maintenance.persistence.models import RagDocumentModel


@pytest.mark.integration
def test_pgvector_insert_and_query():
    db_url = os.getenv("PDM_PGVECTOR_TEST_URL")
    if not db_url:
        pytest.skip("PDM_PGVECTOR_TEST_URL not set; skipping pgvector integration test")

    try:
        from pgvector.sqlalchemy import Vector  # noqa: F401
    except Exception:
        pytest.skip("pgvector not installed; skipping pgvector integration test")

    if not db_url.startswith("postgresql"):
        pytest.skip("pgvector test requires a Postgres URL")

    engine = get_engine(database_url=db_url)

    # Ensure extension + tables
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    Base.metadata.create_all(bind=engine)

    doc_id_a = "test-" + uuid.uuid4().hex[:24]
    doc_id_b = "test-" + uuid.uuid4().hex[:24]

    embedding_a = [0.0] * 1536
    embedding_b = [1.0] + [0.0] * 1535

    try:
        with Session(engine) as session:
            session.add_all(
                [
                    RagDocumentModel(
                        doc_id=doc_id_a,
                        doc_type="agent_summary",
                        content="test document A",
                        embedding=embedding_a,
                        embedding_dim=1536,
                    ),
                    RagDocumentModel(
                        doc_id=doc_id_b,
                        doc_type="agent_summary",
                        content="test document B",
                        embedding=embedding_b,
                        embedding_dim=1536,
                    ),
                ]
            )
            session.commit()

        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT doc_id FROM pdm_rag_documents "
                    "ORDER BY embedding <-> :vec LIMIT 1"
                ),
                {"vec": embedding_a},
            ).scalar_one()

        assert result == doc_id_a
    finally:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "DELETE FROM pdm_rag_documents WHERE doc_id IN (:a, :b)"
                ),
                {"a": doc_id_a, "b": doc_id_b},
            )

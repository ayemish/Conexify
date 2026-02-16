import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from predictive_maintenance.services.rag_service import RagService
from predictive_maintenance.persistence import models


def test_rag_document_model_fields():
    assert hasattr(models.RagDocumentModel, "doc_metadata")


def test_rag_formatting_and_dedupe():
    rag = RagService(session_factory=None)
    rag.embed_text = lambda text: [0.1, 0.2, 0.3]

    payload = {
        "asset_id": "A1",
        "current_regime": "steady_cool",
        "confidence": 0.9,
    }
    content = rag.format_document("digital_twin", payload)

    doc_id_1 = rag.index_document(
        doc_type="digital_twin",
        content=content,
        asset_id="A1",
        site_id="S1",
        metadata={"source": "test"},
    )
    doc_id_2 = rag.index_document(
        doc_type="digital_twin",
        content=content,
        asset_id="A1",
        site_id="S1",
        metadata={"source": "test"},
    )

    assert doc_id_1 == doc_id_2
    assert len(rag._memory_store) == 1
    assert "Type: digital_twin" in content
    assert "current_regime: steady_cool" in content

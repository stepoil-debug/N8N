from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import ai_bounded_routes as bounded


def test_extract_fallback_keeps_client_scope() -> None:
    result = bounded._fallback_extract(
        {
            "path": "01 - RFQ/client.pdf",
            "source_owner": "client",
        },
        "Material, prazo e inspeção conforme documento do cliente.",
        "TimeoutError",
    )
    assert len(result["requirements"]) == 1
    assert result["commitments"] == []
    assert result["requirements"][0]["source_document"] == "01 - RFQ/client.pdf"
    assert result["not_verifiable"][0]["reason"] == "TimeoutError"


def test_extract_fallback_keeps_step_scope() -> None:
    result = bounded._fallback_extract(
        {
            "path": "05 - Proposal/step.docx",
            "source_owner": "step",
        },
        "Escopo ofertado pela STEP.",
        "HTTP 503",
    )
    assert result["requirements"] == []
    assert len(result["commitments"]) == 1
    assert result["commitments"][0]["source_document"] == "05 - Proposal/step.docx"


def test_audit_fallback_preserves_requirement_ids() -> None:
    result = bounded._fallback_audit(
        [{"id": "REQ-001"}, {"id": "REQ-002"}],
        "limite operacional",
    )
    assert [item["requirement_id"] for item in result["requirement_assessments"]] == [
        "REQ-001",
        "REQ-002",
    ]
    assert all(item["status"] == "not_verifiable" for item in result["requirement_assessments"])


def test_runtime_limits_are_bounded() -> None:
    assert bounded.MAX_CHUNKS_PER_DOCUMENT >= 1
    assert bounded.MAX_TOTAL_CHUNKS >= bounded.MAX_CHUNKS_PER_DOCUMENT
    assert bounded.AI_CONCURRENCY >= 1
    assert bounded.CHUNK_TIMEOUT_SECONDS < 300
    assert bounded.AUDIT_BATCH_TIMEOUT_SECONDS < 300

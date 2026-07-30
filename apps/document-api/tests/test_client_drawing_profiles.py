from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.client_knowledge import resolve_client_knowledge
from app.drawing_audit_service import _agent_metadata, _classify_drawing_package
from app.drawing_profile_guard import guarded_client_context


def pdf_entry(path: str, text: str = "") -> dict:
    return {
        "path": path,
        "filename": path.split("/")[-1],
        "extension": ".pdf",
        "document_type": "pdf",
        "source_owner": "unknown",
        "group": "unclassified",
        "extraction_status": "extracted",
        "extracted": {
            "kind": "pdf",
            "content": [{"page": 1, "text": text}],
        },
    }


def test_package_separates_drawings_and_client_conditions() -> None:
    package = {
        "entries": [
            pdf_entry("01_DESENHOS/WZ-V21610-01K01.pdf", "PIPING ISOMETRIC WZ FRESH WATER"),
            pdf_entry(
                "02_CONDICIONAIS/VESSEL PIPING MATERIAL CLASSES SPECIFICATION.pdf",
                "VESSEL PIPING MATERIAL CLASSES SPECIFICATION NORMATIVE REFERENCES",
            ),
            {"path": "README.txt", "filename": "README.txt", "extension": ".txt"},
        ]
    }
    drawings, conditions, other = _classify_drawing_package(package)
    assert [item["path"] for item in drawings] == ["01_DESENHOS/WZ-V21610-01K01.pdf"]
    assert [item["path"] for item in conditions] == ["02_CONDICIONAIS/VESSEL PIPING MATERIAL CLASSES SPECIFICATION.pdf"]
    assert [item["path"] for item in other] == ["README.txt"]
    assert drawings[0]["source_owner"] == "client"
    assert conditions[0]["document_type"] == "client_condition"


def test_agent_metadata_keeps_profile_area_and_project_separate() -> None:
    metadata = _agent_metadata([
        "drawing",
        "client-profile:sbm-hi39520-cidade-de-ilhabela",
        "area:vessel",
        "project:FPSO Cidade de Ilhabela — HI39520",
    ])
    assert metadata == {
        "profile_id": "sbm-hi39520-cidade-de-ilhabela",
        "area": "vessel",
        "project": "FPSO Cidade de Ilhabela — HI39520",
    }


def test_sbm_profile_is_detected_only_with_matching_evidence() -> None:
    context = resolve_client_knowledge(
        {"client": "SBM Offshore / Petrobras", "project": "FPSO Cidade de Ilhabela", "area": "topsides"},
        {
            "document_summary": [
                {
                    "source_document": "HI39520 drawing.pdf",
                    "summary": "TOPSIDES PIPING ISOMETRIC CLASS 01K01 SERVICE WF",
                }
            ],
            "requirements": [],
            "commitments": [],
            "drawing_analysis": [],
        },
    )
    assert context["matched"] is True
    assert context["profile_id"] == "sbm-hi39520-cidade-de-ilhabela"
    assert "topsides:01K01" in context["pmc_profiles"]


def test_server_rejects_profile_from_another_client() -> None:
    drawing = pdf_entry("PERENCO-WP-PCH2-2025-007.pdf", "PERENCO PIPING ISOMETRIC")
    with pytest.raises(HTTPException) as exc:
        guarded_client_context(
            {"client": "PERENCO", "project": "WP-PCH2-2025-007"},
            {"package_name": "PERENCO-DRAWINGS.zip"},
            [drawing],
            [],
            [],
            "sbm-hi39520-cidade-de-ilhabela",
        )
    assert exc.value.status_code == 422
    assert "não será aplicada" in str(exc.value.detail)

import io
import os
import sys
import zipfile
from pathlib import Path

os.environ["API_KEY"] = "test-key"
os.environ["ARTIFACT_ROOT"] = "/tmp/step-industrial-audit-tests"
os.environ.pop("N8N_AUDIT_WEBHOOK_URL", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.cors_entrypoint import app

client = TestClient(app)
headers = {"x-step-api-key": "test-key"}


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_authentication():
    response = client.post("/v1/opportunities/prepare", json={"opportunity_id": "TEST"})
    assert response.status_code == 401


def test_prepare():
    response = client.post("/v1/opportunities/prepare", headers=headers, json={"opportunity_id": "TEST", "client": "Cliente"})
    assert response.status_code == 200
    assert response.json()["status"] == "prepared"


def test_package_inventory():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("BEP-26-762/01 - RFQ/requisitos.txt", "Prazo máximo de 30 dias")
        archive.writestr("BEP-26-762/05 - Proposal/proposta.txt", "Prazo ofertado de 45 dias")
        archive.writestr("BEP-26-762/Thumbs.db", b"system")
    response = client.post(
        "/v1/packages/analyze",
        headers=headers,
        files={"file": ("BEP-26-762 PERENCO.zip", buffer.getvalue(), "application/zip")},
        data={"opportunity_id": "BEP-26-762", "include_content": "true"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["total_files"] == 2
    assert body["summary"]["ignored_files"] == 1
    assert body["summary"]["source_owners"]["client"] == 1
    assert body["summary"]["source_owners"]["step"] == 1


def test_dispatch_does_not_fake_success_without_n8n():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("BEP-26-762/01 - RFQ/requisitos.txt", "Prazo máximo de 30 dias")
        archive.writestr("BEP-26-762/05 - Proposal/proposta.txt", "Prazo ofertado de 45 dias")
    response = client.post(
        "/v1/audits/from-package",
        headers=headers,
        files={"file": ("BEP-26-762 PERENCO.zip", buffer.getvalue(), "application/zip")},
        data={"opportunity_id": "BEP-26-762", "client": "PERENCO", "agents_json": "[]"},
    )
    assert response.status_code == 503
    assert "Motor de IA não implantado" in str(response.json())


def test_finalize_generates_report_and_corrected_proposal():
    analysis = {
        "summary": {
            "recommendation": "review_before_submit",
            "risk_level": "critical",
            "executive_opinion": "A proposta não deve ser enviada antes da correção do prazo.",
        },
        "requirements": [{
            "id": "REQ-001",
            "category": "schedule",
            "requirement": "Entrega em até 30 dias",
            "status": "not_met",
            "source_document": "01 - RFQ/requisitos.txt",
            "source_location": "linha 1",
            "source_evidence": "Prazo máximo de 30 dias",
        }],
        "commitments": [{
            "id": "COM-001",
            "category": "schedule",
            "commitment": "Entrega em 45 dias",
            "source_document": "05 - Proposal/proposta.txt",
            "source_location": "linha 1",
            "source_evidence": "Prazo ofertado de 45 dias",
        }],
        "findings": [{
            "id": "F-001",
            "severity": "critical",
            "category": "schedule",
            "title": "Prazo incompatível",
            "impact": "Risco de rejeição",
            "client_evidence": "RFQ: 30 dias",
            "step_evidence": "Proposta: 45 dias",
            "required_correction": "Ajustar o prazo para 30 dias ou registrar desvio formal.",
            "blocking": True,
        }],
        "corrections": [{
            "id": "C-001",
            "section": "Prazo",
            "current_text": "45 dias",
            "corrected_text": "30 dias após a ordem de início, sujeito à confirmação do planejamento.",
            "reason": "Aderência à RFQ",
            "requires_human_validation": True,
        }],
        "corrected_proposal": {
            "introduction": "A STEP apresenta a proposta revisada para atendimento da RFQ.",
            "sections": [{"title": "Prazo", "paragraphs": ["Entrega em 30 dias após a ordem de início."]}],
        },
    }
    response = client.post(
        "/v1/audits/finalize",
        headers=headers,
        json={
            "opportunity": {"opportunity_id": "TEST-FINAL", "client": "Cliente", "rfq_id": "RFQ-1"},
            "package": {"package_name": "teste.zip", "summary": {"total_files": 2}},
            "analysis": analysis,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "analysis_completed"
    assert body["summary"]["blocking_risks"] == 1
    names = {item["artifact_name"] for item in body["artifacts"]}
    assert any(name.endswith(".docx") for name in names)
    assert len([name for name in names if name.endswith(".pdf")]) == 2
    assert any(name.endswith(".xlsx") for name in names)
    assert any(name.endswith(".json") for name in names)

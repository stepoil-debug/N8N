import os
import sys
from pathlib import Path

os.environ["API_KEY"] = "test-key"
os.environ["ARTIFACT_ROOT"] = "/tmp/step-industrial-audit-tests"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app

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


def test_checklist_generation():
    body = {"opportunity_id": "TEST", "analysis": {"summary": {"client": "Cliente", "rfq_id": "RFQ-1"}, "requirements": [{"id": "RFQ-001", "category": "Escopo técnico", "requirement": "Fabricar 12 spools", "source_document": "RFQ.pdf"}]}}
    response = client.post("/v1/triage/checklist", headers=headers, json=body)
    assert response.status_code == 200
    assert response.json()["artifact_name"].endswith(".xlsx")

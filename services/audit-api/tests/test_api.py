from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "audit-api"}


def test_skills_require_internal_token(monkeypatch) -> None:
    monkeypatch.setenv("AUDIT_API_SHARED_SECRET", "test-secret")

    response = client.get("/v1/skills")

    assert response.status_code == 401


def test_skill_catalog(monkeypatch) -> None:
    monkeypatch.setenv("AUDIT_API_SHARED_SECRET", "test-secret")

    response = client.get(
        "/v1/skills",
        headers={"X-STEP-Internal-Token": "test-secret"},
    )

    assert response.status_code == 200
    skill_names = {item["name"] for item in response.json()}
    assert skill_names == {"triagem-rfq", "validacao-aderencia-proposta"}


def test_pending_adapter_refuses_execution(monkeypatch) -> None:
    monkeypatch.setenv("AUDIT_API_SHARED_SECRET", "test-secret")

    payload = {
        "correlation_id": "d670d408-a41a-4988-b2e5-e37f46c0e8c8",
        "opportunity_id": "1c5ac27f-9371-47c6-acf5-590f1cb3101f",
        "audit_run_id": "067ca741-cbbe-4c62-8b9d-556b02adfdd8",
        "idempotency_key": "test-idempotency-key",
        "input_refs": [
            {
                "document_id": "db0619ce-b69c-4c89-8984-e63f4c43fba5",
                "revision_id": "211919b3-f5f7-422b-bf1e-4843ddeaa441",
                "storage_path": "private/test.pdf",
                "sha256": "a" * 64,
            }
        ],
        "options": {},
    }

    response = client.post(
        "/v1/skills/triagem-rfq/runs",
        headers={"X-STEP-Internal-Token": "test-secret"},
        json=payload,
    )

    assert response.status_code == 503
    assert response.json()["detail"]["status"] == "adapter_pending"

import io
import json
import os
import sys
import zipfile
from pathlib import Path

os.environ["API_KEY"] = "test-key"
os.environ["ARTIFACT_ROOT"] = "/tmp/step-industrial-audit-package-tests"
os.environ.pop("N8N_AUDIT_WEBHOOK_URL", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.cors_entrypoint import app

client = TestClient(app)
headers = {"x-step-api-key": "test-key"}


def make_zip(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items(): archive.writestr(name, content)
    return output.getvalue()


def test_single_zip_classification():
    data = make_zip({
        "26-762 BEP PERENCO - ENC WP-PCH2-2025-007/01 - RFQ/requisito.txt": b"fabricar escada",
        "26-762 BEP PERENCO - ENC WP-PCH2-2025-007/04 - Estimate/custo.csv": b"item,valor\naco,100",
        "26-762 BEP PERENCO - ENC WP-PCH2-2025-007/05 - Proposal/proposta.md": b"prazo: 30 dias",
        "26-762 BEP PERENCO - ENC WP-PCH2-2025-007/01 - RFQ/Thumbs.db": b"ignored",
    })
    response = client.post("/v1/packages/analyze", headers=headers, files={"file": ("26-762 BEP PERENCO - ENC WP-PCH2-2025-007.zip", data, "application/zip")})
    assert response.status_code == 200
    body = response.json()
    assert body["inferred"] == {"opportunity_id": "BEP-26-762", "client": "PERENCO", "rfq_id": "WP-PCH2-2025-007"}
    assert body["summary"]["total_files"] == 3
    assert body["summary"]["ignored_files"] == 1
    assert body["summary"]["groups"] == {"rfq": 1, "estimate": 1, "proposal": 1}


def test_zip_path_traversal_is_rejected():
    data = make_zip({"../segredo.txt": b"nao pode"})
    response = client.post("/v1/packages/analyze", headers=headers, files={"file": ("unsafe.zip", data, "application/zip")})
    assert response.status_code == 422


def test_single_zip_dispatch_without_n8n():
    data = make_zip({"BEP 26-762 PERENCO/01 - RFQ/rfq.txt": b"requisito", "BEP 26-762 PERENCO/05 - Proposal/proposta.txt": b"compromisso"})
    response = client.post("/v1/audits/from-package", headers=headers, data={"opportunity_id": "BEP-26-762", "client": "PERENCO", "agents_json": json.dumps(["technical"])}, files={"file": ("package.zip", data, "application/zip")})
    assert response.status_code == 200
    assert response.json()["status"] == "package_classified"

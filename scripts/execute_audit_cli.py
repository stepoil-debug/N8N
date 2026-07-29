#!/usr/bin/env python3
"""Execute the STEP audit workflow directly through the n8n CLI.

The final n8n node persists the completed result to a private temporary file.
This avoids relying on version-specific CLI stdout formatting.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx

JOB_FILE = Path(os.environ.get("STEP_AUDIT_JOB_FILE", "/tmp/step-audit-job.json"))
RESULT_FILE = Path(os.environ.get("STEP_AUDIT_RESULT_FILE", "/tmp/step-audit-result.json"))
INPUT_FILE = Path(os.environ.get("STEP_AUDIT_INPUT_FILE", "/tmp/step-audit-input.zip"))
PAYLOAD_FILE = Path(os.environ.get("STEP_AUDIT_PAYLOAD_PATH", "/tmp/step-audit-n8n-input.json"))
API_URL = os.environ.get("DOCUMENT_API_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")
API_KEY = os.environ.get("DOCUMENT_API_KEY", "step-audit-actions")
WORKFLOW_ID = os.environ.get("STEP_AUDIT_WORKFLOW_ID", "STEP_AUDIT_FULL_01")


def fail(message: str) -> None:
    raise RuntimeError(message)


def analyze_package(job: dict[str, Any]) -> dict[str, Any]:
    if not INPUT_FILE.is_file():
        fail(f"ZIP de entrada não encontrado: {INPUT_FILE}")
    with INPUT_FILE.open("rb") as handle:
        files = {
            "file": (
                job.get("package_name") or "opportunity.zip",
                handle,
                "application/zip",
            )
        }
        data = {
            "opportunity_id": job.get("opportunity_id") or "",
            "include_content": "true",
        }
        with httpx.Client(timeout=httpx.Timeout(900.0, connect=30.0)) as client:
            response = client.post(
                f"{API_URL}/v1/packages/analyze",
                headers={"x-step-api-key": API_KEY},
                data=data,
                files=files,
            )
    try:
        body = response.json()
    except ValueError:
        body = {"detail": response.text}
    if response.is_error:
        detail = body.get("detail") if isinstance(body, dict) else None
        if isinstance(detail, dict):
            detail = detail.get("message") or json.dumps(detail, ensure_ascii=False)
        fail(str(detail or body.get("message") or f"API respondeu HTTP {response.status_code}"))
    if not isinstance(body, dict) or not body.get("entries"):
        fail("A extração documental não retornou arquivos utilizáveis")
    return body


def build_payload(job: dict[str, Any], package: dict[str, Any]) -> dict[str, Any]:
    inferred = package.get("inferred") if isinstance(package.get("inferred"), dict) else {}
    opportunity = {
        "opportunity_id": job.get("opportunity_id") or package.get("opportunity_id"),
        "client": job.get("client") or inferred.get("client"),
        "rfq_id": job.get("rfq_id") or inferred.get("rfq_id"),
        "owner": job.get("owner_name") or "",
        "agents": job.get("agents") or [],
    }
    return {
        "opportunity": opportunity,
        "package": package,
        "channel": "github-actions-n8n-cli",
        "requested_outputs": [
            "audit_pdf",
            "corrected_docx",
            "corrected_pdf",
            "xlsx",
            "json",
        ],
    }


def load_completed_result() -> dict[str, Any]:
    if not RESULT_FILE.is_file():
        fail(
            "O n8n terminou sem gerar o arquivo de resultado final. "
            f"Arquivo esperado: {RESULT_FILE}"
        )
    try:
        result = json.loads(RESULT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"O arquivo de resultado do n8n é inválido: {exc}")
    if not isinstance(result, dict) or result.get("status") != "analysis_completed":
        fail("O n8n não confirmou analysis_completed no resultado persistido")
    return result


def execute_workflow() -> dict[str, Any]:
    if RESULT_FILE.exists():
        RESULT_FILE.unlink()

    env = os.environ.copy()
    env["STEP_AUDIT_PAYLOAD_PATH"] = str(PAYLOAD_FILE)
    env["STEP_AUDIT_RESULT_FILE"] = str(RESULT_FILE)
    command = ["n8n", "execute", f"--id={WORKFLOW_ID}"]
    process = subprocess.run(
        command,
        env=env,
        text=True,
        capture_output=True,
        timeout=1500,
        check=False,
    )
    if process.stdout:
        print(process.stdout)
    if process.stderr:
        print(process.stderr, file=sys.stderr)
    if process.returncode != 0:
        fail(
            "Falha ao executar o workflow n8n.\n"
            f"STDOUT:\n{process.stdout[-6000:]}\n"
            f"STDERR:\n{process.stderr[-6000:]}"
        )
    return load_completed_result()


def main() -> int:
    payload = json.loads(JOB_FILE.read_text(encoding="utf-8"))
    job = payload.get("job")
    if not isinstance(job, dict):
        fail("Arquivo do trabalho não contém job válido")

    package = analyze_package(job)
    n8n_payload = build_payload(job, package)
    PAYLOAD_FILE.write_text(
        json.dumps(n8n_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    print(
        f"Dossiê preparado: {package.get('summary', {}).get('total_files', 0)} "
        "arquivo(s) extraído(s)."
    )

    result = execute_workflow()
    RESULT_FILE.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    findings = result.get("findings")
    if not isinstance(findings, list):
        analysis = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}
        findings = analysis.get("findings") if isinstance(analysis.get("findings"), list) else []
    print(f"Auditoria concluída com {len(findings)} achado(s).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERRO: {exc}", file=sys.stderr)
        raise

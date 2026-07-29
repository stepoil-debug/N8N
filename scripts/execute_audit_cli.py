#!/usr/bin/env python3
"""Execute the STEP audit workflow directly through the n8n CLI.

This avoids production webhook registration in short-lived GitHub Actions runners
while preserving n8n as the orchestration engine.
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


def json_candidates(text: str):
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character not in "[{":
            continue
        try:
            value, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        yield value, index, index + end


def find_completed(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if value.get("status") == "analysis_completed":
            return value
        for child in value.values():
            found = find_completed(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_completed(child)
            if found:
                return found
    return None


def parse_execution_output(stdout: str) -> dict[str, Any]:
    direct = None
    try:
        direct = json.loads(stdout)
    except json.JSONDecodeError:
        pass
    if direct is not None:
        found = find_completed(direct)
        if found:
            return found
    parsed = list(json_candidates(stdout))
    for value, _start, _end in reversed(parsed):
        found = find_completed(value)
        if found:
            return found
    tail = stdout[-6000:]
    fail(f"O n8n terminou sem retornar analysis_completed. Saída final:\n{tail}")


def execute_workflow() -> dict[str, Any]:
    env = os.environ.copy()
    env["STEP_AUDIT_PAYLOAD_PATH"] = str(PAYLOAD_FILE)
    command = ["n8n", "execute", f"--id={WORKFLOW_ID}", "--rawOutput"]
    process = subprocess.run(
        command,
        env=env,
        text=True,
        capture_output=True,
        timeout=1500,
        check=False,
    )
    if process.stderr:
        print(process.stderr, file=sys.stderr)
    if process.returncode != 0:
        fail(
            "Falha ao executar o workflow n8n.\n"
            f"STDOUT:\n{process.stdout[-6000:]}\n"
            f"STDERR:\n{process.stderr[-6000:]}"
        )
    return parse_execution_output(process.stdout)


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
    print(f"Auditoria concluída com {len(result.get('findings') or [])} achado(s).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERRO: {exc}", file=sys.stderr)
        raise

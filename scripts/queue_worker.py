#!/usr/bin/env python3
"""Worker bridge between Supabase queue, local n8n, and generated artifacts."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
from pathlib import Path
from typing import Any, NoReturn

import httpx

QUEUE_URL = os.environ.get("STEP_AUDIT_QUEUE_URL", "").rstrip("/")
OIDC_TOKEN = os.environ.get("WORKER_OIDC_TOKEN", "")
JOB_FILE = Path(os.environ.get("STEP_AUDIT_JOB_FILE", "/tmp/step-audit-job.json"))
RESULT_FILE = Path(os.environ.get("STEP_AUDIT_RESULT_FILE", "/tmp/step-audit-result.json"))
INPUT_FILE = Path(os.environ.get("STEP_AUDIT_INPUT_FILE", "/tmp/step-audit-input.zip"))
API_URL = os.environ.get("DOCUMENT_API_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")
API_KEY = os.environ.get("DOCUMENT_API_KEY", "step-audit-actions")


def fail(message: str) -> NoReturn:
    raise RuntimeError(message)


def auth_headers() -> dict[str, str]:
    if not QUEUE_URL:
        fail("STEP_AUDIT_QUEUE_URL não configurada")
    if not OIDC_TOKEN:
        fail("WORKER_OIDC_TOKEN não configurado")
    return {"Authorization": f"Bearer {OIDC_TOKEN}"}


def queue_post(route: str, *, json_body: dict[str, Any] | None = None, files=None, data=None, timeout: float = 120.0) -> dict[str, Any]:
    with httpx.Client(timeout=httpx.Timeout(timeout, connect=30.0), follow_redirects=True) as client:
        response = client.post(f"{QUEUE_URL}/{route}", headers=auth_headers(), json=json_body, files=files, data=data)
    try:
        body = response.json()
    except ValueError:
        body = {"error": response.text}
    if response.is_error:
        fail(str(body.get("error") or body.get("message") or f"HTTP {response.status_code}"))
    return body


def write_output(name: str, value: str) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def claim() -> int:
    body = queue_post("claim", json_body={"worker_id": f"github-actions-{os.environ.get('GITHUB_RUN_ID', 'manual')}", "workflow_run_id": os.environ.get("GITHUB_RUN_ID", "")})
    if body.get("status") == "idle":
        print("Nenhum trabalho pendente.")
        write_output("has_job", "false")
        return 0
    if body.get("status") != "claimed" or not isinstance(body.get("job"), dict):
        fail(f"Resposta inválida ao reivindicar trabalho: {body}")
    payload = {"job": body["job"], "input_download_url": body.get("input_download_url")}
    JOB_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_output("has_job", "true")
    write_output("job_id", str(body["job"]["id"]))
    print(f"Trabalho reivindicado: {body['job']['id']}")
    return 0


def download() -> int:
    payload = json.loads(JOB_FILE.read_text(encoding="utf-8"))
    url = str(payload.get("input_download_url") or "")
    if not url:
        fail("URL de download do ZIP ausente")
    with httpx.stream("GET", url, timeout=httpx.Timeout(300.0, connect=30.0), follow_redirects=True) as response:
        response.raise_for_status()
        with INPUT_FILE.open("wb") as handle:
            for chunk in response.iter_bytes():
                handle.write(chunk)
    expected = int(payload["job"].get("package_size_bytes") or 0)
    actual = INPUT_FILE.stat().st_size
    if expected and actual != expected:
        fail(f"Tamanho do ZIP divergente: esperado {expected}, recebido {actual}")
    print(f"ZIP baixado: {INPUT_FILE} ({actual} bytes)")
    return 0


def process() -> int:
    payload = json.loads(JOB_FILE.read_text(encoding="utf-8"))
    job = payload["job"]
    with INPUT_FILE.open("rb") as handle:
        files = {"file": (job.get("package_name") or "opportunity.zip", handle, "application/zip")}
        form = {
            "opportunity_id": job.get("opportunity_id") or "",
            "client": job.get("client") or "",
            "rfq_id": job.get("rfq_id") or "",
            "owner": job.get("owner_name") or "",
            "agents_json": json.dumps(job.get("agents") or []),
        }
        with httpx.Client(timeout=httpx.Timeout(1500.0, connect=30.0)) as client:
            response = client.post(f"{API_URL}/v1/audits/from-package", headers={"x-step-api-key": API_KEY}, data=form, files=files)
    try:
        body = response.json()
    except ValueError:
        body = {"detail": response.text}
    if response.is_error:
        detail = body.get("detail") if isinstance(body, dict) else None
        if isinstance(detail, dict):
            detail = detail.get("message") or json.dumps(detail, ensure_ascii=False)
        fail(str(detail or body.get("message") or f"API respondeu HTTP {response.status_code}"))
    if body.get("status") != "analysis_completed":
        fail(str(body.get("message") or "A auditoria não retornou analysis_completed"))
    RESULT_FILE.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Auditoria concluída com {len(body.get('findings') or [])} achado(s).")
    return 0


def upload_artifact(job_id: str, artifact: dict[str, Any]) -> dict[str, Any]:
    artifact_path = Path(str(artifact.get("artifact_path") or ""))
    if not artifact_path.is_file():
        fail(f"Artefato não encontrado: {artifact_path}")
    mime = mimetypes.guess_type(artifact_path.name)[0] or "application/octet-stream"
    with artifact_path.open("rb") as handle:
        return queue_post("upload-output", files={"file": (artifact_path.name, handle, mime)}, data={"job_id": job_id}, timeout=300.0)


def publish() -> int:
    payload = json.loads(JOB_FILE.read_text(encoding="utf-8"))
    job_id = str(payload["job"]["id"])
    result = json.loads(RESULT_FILE.read_text(encoding="utf-8"))
    output_paths = [upload_artifact(job_id, item) for item in (result.get("artifacts") or [])]
    if not output_paths:
        fail("Nenhum artefato foi produzido")
    result_data = dict(result)
    result_data["artifacts"] = [{"artifact_name": item.get("artifact_name"), "size_bytes": item.get("size_bytes")} for item in output_paths]
    queue_post("complete", json_body={"job_id": job_id, "output_paths": output_paths, "summary": result.get("summary") or {}, "result_data": result_data})
    print(f"Resultados publicados para {job_id}.")
    return 0


def mark_failed(message: str) -> int:
    if not JOB_FILE.is_file():
        print(f"Falha antes de reivindicar trabalho: {message}", file=sys.stderr)
        return 0
    payload = json.loads(JOB_FILE.read_text(encoding="utf-8"))
    job_id = str(payload.get("job", {}).get("id") or "")
    if job_id:
        try:
            queue_post("fail", json_body={"job_id": job_id, "error_message": message[:4000]})
        except Exception as exc:  # noqa: BLE001
            print(f"Não foi possível registrar a falha: {exc}", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("claim", "download", "process", "publish"):
        sub.add_parser(command)
    failed = sub.add_parser("fail")
    failed.add_argument("message")
    args = parser.parse_args()
    if args.command == "claim": return claim()
    if args.command == "download": return download()
    if args.command == "process": return process()
    if args.command == "publish": return publish()
    return mark_failed(args.message)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERRO: {exc}", file=sys.stderr)
        raise

#!/usr/bin/env python3
"""Execute the proposal audit through n8n with heartbeat and bounded timeout."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import execute_audit_cli as legacy

WORKFLOW_TIMEOUT_SECONDS = int(os.getenv("STEP_AUDIT_WORKFLOW_TIMEOUT_SECONDS", "2100"))
HEARTBEAT_SECONDS = max(15, int(os.getenv("STEP_AUDIT_HEARTBEAT_SECONDS", "60")))
DOCUMENT_API_LOG = Path(os.getenv("DOCUMENT_API_LOG", "/tmp/document-api.log"))


def _log_tail(path: Path, maximum: int = 14000) -> str:
    if not path.is_file():
        return "log da Document API não encontrado"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"não foi possível ler {path}: {exc}"
    return text[-maximum:]


def _stop(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def execute_workflow() -> dict[str, Any]:
    if legacy.RESULT_FILE.exists():
        legacy.RESULT_FILE.unlink()

    env = os.environ.copy()
    env["STEP_AUDIT_PAYLOAD_PATH"] = str(legacy.PAYLOAD_FILE)
    env["STEP_AUDIT_RESULT_FILE"] = str(legacy.RESULT_FILE)
    command = ["n8n", "execute", f"--id={legacy.WORKFLOW_ID}"]
    print(
        f"[worker-v2] iniciando n8n; limite total {WORKFLOW_TIMEOUT_SECONDS}s; "
        f"heartbeat a cada {HEARTBEAT_SECONDS}s",
        flush=True,
    )
    process = subprocess.Popen(command, env=env)
    started = time.monotonic()
    next_heartbeat = started + HEARTBEAT_SECONDS

    while process.poll() is None:
        now = time.monotonic()
        elapsed = int(now - started)
        if now >= next_heartbeat:
            print(
                f"[worker-v2] n8n em execução há {elapsed}s; aguardando conclusão dos lotes de IA...",
                flush=True,
            )
            next_heartbeat = now + HEARTBEAT_SECONDS
        if elapsed >= WORKFLOW_TIMEOUT_SECONDS:
            _stop(process)
            legacy.fail(
                "O workflow n8n excedeu o limite seguro de execução.\n"
                f"Tempo: {elapsed}s.\n"
                "Últimas linhas da Document API:\n"
                f"{_log_tail(DOCUMENT_API_LOG)}"
            )
        time.sleep(5)

    return_code = int(process.returncode or 0)
    elapsed = int(time.monotonic() - started)
    if return_code != 0:
        legacy.fail(
            f"O workflow n8n terminou com código {return_code} após {elapsed}s.\n"
            "Últimas linhas da Document API:\n"
            f"{_log_tail(DOCUMENT_API_LOG)}"
        )
    print(f"[worker-v2] n8n finalizado em {elapsed}s", flush=True)
    return legacy.load_completed_result()


def main() -> int:
    payload = json.loads(legacy.JOB_FILE.read_text(encoding="utf-8"))
    job = payload.get("job")
    if not isinstance(job, dict):
        legacy.fail("Arquivo do trabalho não contém job válido")

    package = legacy.analyze_package(job)
    n8n_payload = legacy.build_payload(job, package)
    legacy.PAYLOAD_FILE.write_text(
        json.dumps(n8n_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    summary = package.get("summary") if isinstance(package.get("summary"), dict) else {}
    print(
        f"Dossiê preparado: {summary.get('total_files', 0)} arquivo(s), "
        f"{summary.get('drawings_prepared', 0)} desenho(s) preparado(s).",
        flush=True,
    )

    result = execute_workflow()
    legacy.RESULT_FILE.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    findings = result.get("findings")
    if not isinstance(findings, list):
        analysis = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}
        findings = analysis.get("findings") if isinstance(analysis.get("findings"), list) else []
    print(f"Auditoria concluída com {len(findings)} achado(s).", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERRO: {exc}", file=sys.stderr, flush=True)
        raise

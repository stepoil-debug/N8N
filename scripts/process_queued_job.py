#!/usr/bin/env python3
"""Dispatch the claimed queue job to proposal audit or drawing audit."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

JOB_FILE = Path(os.environ.get("STEP_AUDIT_JOB_FILE", "/tmp/step-audit-job.json"))


def main() -> int:
    if not JOB_FILE.is_file():
        raise RuntimeError(f"Arquivo do trabalho não encontrado: {JOB_FILE}")
    payload = json.loads(JOB_FILE.read_text(encoding="utf-8"))
    job = payload.get("job") if isinstance(payload, dict) else None
    if not isinstance(job, dict):
        raise RuntimeError("Payload da fila não contém job válido")
    agents = job.get("agents") if isinstance(job.get("agents"), list) else []
    if "drawing" in agents:
        command = [sys.executable, "scripts/queue_worker.py", "process"]
        label = "análise de desenhos"
    else:
        command = [sys.executable, "scripts/execute_audit_cli.py"]
        label = "auditoria de proposta"
    print(f"Roteando trabalho {job.get('id')} para {label}.", flush=True)
    completed = subprocess.run(command, check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())

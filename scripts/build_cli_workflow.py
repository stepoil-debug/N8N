#!/usr/bin/env python3
"""Build a CLI-safe n8n workflow from the canonical STEP audit workflow.

The canonical JSON keeps the production webhook for Docker/server deployments.
GitHub Actions uses a short-lived runner, so this script replaces only the
entry trigger and request payload at runtime, preserving n8n orchestration.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

SOURCE = Path(os.environ.get("STEP_AUDIT_WORKFLOW_SOURCE", "workflows/40-auditoria-completa.json"))
OUTPUT = Path(os.environ.get("STEP_AUDIT_WORKFLOW_OUTPUT", "/tmp/audit-workflow.json"))
WORKFLOW_ID = os.environ.get("STEP_AUDIT_WORKFLOW_ID", "STEP_AUDIT_FULL_01")
PAYLOAD_PATH = os.environ.get("STEP_AUDIT_PAYLOAD_PATH", "/tmp/step-audit-n8n-input.json")
RESULT_PATH = os.environ.get("STEP_AUDIT_RESULT_FILE", "/tmp/step-audit-result.json")


def node_by_name(workflow: dict[str, Any], name: str) -> dict[str, Any]:
    for node in workflow.get("nodes", []):
        if node.get("name") == name:
            return node
    raise RuntimeError(f"Nó obrigatório não encontrado: {name}")


def main() -> int:
    workflow = json.loads(SOURCE.read_text(encoding="utf-8"))
    workflow["id"] = WORKFLOW_ID
    workflow["active"] = False

    trigger = node_by_name(workflow, "Receber ZIP Classificado")
    trigger["type"] = "n8n-nodes-base.manualTrigger"
    trigger["typeVersion"] = 1
    trigger["parameters"] = {}
    trigger.pop("webhookId", None)

    prepare = node_by_name(workflow, "Preparar Dossiê")
    js_code = prepare.get("parameters", {}).get("jsCode", "")
    marker = "const incoming = $json;"
    replacement = (
        "const fs = require('fs');\n"
        f"const payloadPath = $env.STEP_AUDIT_PAYLOAD_PATH || {json.dumps(PAYLOAD_PATH)};\n"
        "if (!fs.existsSync(payloadPath)) throw new Error(`Payload da auditoria não encontrado: ${payloadPath}`);\n"
        "const incoming = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));"
    )
    if marker not in js_code:
        raise RuntimeError("Marcador de entrada não encontrado no nó Preparar Dossiê")
    prepare["parameters"]["jsCode"] = js_code.replace(marker, replacement, 1)

    common_headers = {
        "parameters": [
            {"name": "Accept", "value": "application/vnd.github+json"},
            {"name": "Content-Type", "value": "application/json"},
            {"name": "Authorization", "value": "={{ $env.LLM_API_KEY ? 'Bearer ' + $env.LLM_API_KEY : '' }}"},
        ]
    }

    extract = node_by_name(workflow, "IA Extrair Requisitos")
    extract["parameters"]["headerParameters"] = common_headers
    extract["parameters"]["jsonBody"] = (
        "={{ { model: $env.LLM_MODEL, messages: ["
        "{ role: 'system', content: $json.systemPrompt }, "
        "{ role: 'user', content: $json.extractionPrompt }], "
        "stream: false, temperature: 0.1, max_tokens: 12000, "
        "response_format: { type: 'json_object' } } }}"
    )

    audit = node_by_name(workflow, "IA Auditar e Corrigir")
    audit["parameters"]["headerParameters"] = common_headers
    audit["parameters"]["jsonBody"] = (
        "={{ { model: $env.LLM_MODEL, messages: ["
        "{ role: 'system', content: $json.systemPrompt }, "
        "{ role: 'user', content: $json.auditPrompt }], "
        "stream: false, temperature: 0.1, max_tokens: 16000, "
        "response_format: { type: 'json_object' } } }}"
    )

    final_node = node_by_name(workflow, "Resposta Completa")
    final_node["parameters"]["jsCode"] = (
        "const fs = require('fs');\n"
        "const result = {...$json, status: 'analysis_completed'};\n"
        f"const resultPath = $env.STEP_AUDIT_RESULT_FILE || {json.dumps(RESULT_PATH)};\n"
        "fs.writeFileSync(resultPath, JSON.stringify(result), 'utf8');\n"
        "return [{json: result}];"
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")

    required = {
        "Receber ZIP Classificado",
        "Preparar Dossiê",
        "IA Extrair Requisitos",
        "IA Auditar e Corrigir",
        "Gerar Relatório e Proposta",
        "Resposta Completa",
    }
    present = {node.get("name") for node in workflow.get("nodes", [])}
    missing = sorted(required - present)
    if missing:
        raise RuntimeError(f"Workflow CLI incompleto: {', '.join(missing)}")

    print(f"Workflow CLI gerado em {OUTPUT} com id {WORKFLOW_ID}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

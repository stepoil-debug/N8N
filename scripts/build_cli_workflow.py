#!/usr/bin/env python3
"""Build the CLI-safe STEP audit workflow used by GitHub Actions."""

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


def configure_local_request(node: dict[str, Any], path: str, body: str) -> None:
    parameters = node.setdefault("parameters", {})
    parameters.update(
        {
            "method": "POST",
            "url": f"={{{{ $env.DOCUMENT_API_URL + '{path}' }}}}",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Content-Type", "value": "application/json"},
                    {"name": "x-step-api-key", "value": "={{ $env.DOCUMENT_API_KEY }}"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": body,
            "options": {"timeout": 1200000},
        }
    )


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

    configure_local_request(
        node_by_name(workflow, "IA Extrair Requisitos"),
        "/v1/ai/extract-v2",
        "={{ { opportunity: $json.opportunity, package: $json.package } }}",
    )
    configure_local_request(
        node_by_name(workflow, "IA Auditar e Corrigir"),
        "/v1/ai/audit-v2",
        "={{ { opportunity: $json.opportunity, package: $json.package, extraction: $json.extraction } }}",
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
        "Receber ZIP Classificado", "Preparar Dossiê", "IA Extrair Requisitos",
        "IA Auditar e Corrigir", "Gerar Relatório e Proposta", "Resposta Completa",
    }
    present = {node.get("name") for node in workflow.get("nodes", [])}
    missing = sorted(required - present)
    if missing:
        raise RuntimeError(f"Workflow CLI incompleto: {', '.join(missing)}")

    built = json.loads(OUTPUT.read_text(encoding="utf-8"))
    extract_url = node_by_name(built, "IA Extrair Requisitos").get("parameters", {}).get("url", "")
    audit_url = node_by_name(built, "IA Auditar e Corrigir").get("parameters", {}).get("url", "")
    if "extract-v2" not in extract_url or "audit-v2" not in audit_url:
        raise RuntimeError("Workflow CLI não foi ligado às rotas de IA limitadas")

    print(f"Workflow CLI gerado em {OUTPUT} com id {WORKFLOW_ID} e IA limitada em lotes paralelos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

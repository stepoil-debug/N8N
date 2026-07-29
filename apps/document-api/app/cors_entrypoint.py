from __future__ import annotations

import json
import os

import httpx
from fastapi import Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .main import app, auth
from .package_service import analyze_package


def allowed_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5678,https://stepoil-debug.github.io")
    return [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]


app.add_middleware(CORSMiddleware, allow_origins=allowed_origins(), allow_credentials=False, allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type", "X-STEP-API-KEY"], expose_headers=["Content-Disposition"], max_age=3600)


async def post_to_n8n(payload: dict) -> dict:
    webhook_url = os.getenv("N8N_AUDIT_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return {"status": "package_classified", "message": "Pacote classificado. Workflow n8n ainda não publicado neste ambiente.", "summary": payload.get("package", {}).get("summary", {})}
    headers = {"Content-Type": "application/json"}
    token = os.getenv("N8N_AUDIT_WEBHOOK_TOKEN", "").strip()
    if token: headers["X-STEP-INTERNAL-TOKEN"] = token
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=20.0)) as client:
            response = await client.post(webhook_url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao chamar o n8n: {exc}") from exc
    try: body = response.json()
    except ValueError: body = {"message": response.text}
    if response.is_error:
        raise HTTPException(status_code=502, detail=(body.get("message") if isinstance(body, dict) else None) or f"n8n respondeu HTTP {response.status_code}")
    return body if isinstance(body, dict) else {"result": body}


@app.post("/v1/audits/dispatch", dependencies=[Depends(auth)])
async def dispatch_audit(request: Request) -> dict:
    return await post_to_n8n(await request.json())


@app.post("/v1/packages/analyze", dependencies=[Depends(auth)])
async def analyze_zip(file: UploadFile = File(...), opportunity_id: str = Form(default=""), include_content: bool = Form(default=False)) -> dict:
    return analyze_package(file.filename or "opportunity.zip", await file.read(), opportunity_id.strip() or None, include_content=include_content)


@app.post("/v1/audits/from-package", dependencies=[Depends(auth)])
async def audit_from_package(file: UploadFile = File(...), opportunity_id: str = Form(default=""), client: str = Form(default=""), rfq_id: str = Form(default=""), owner: str = Form(default=""), agents_json: str = Form(default="[]")) -> dict:
    if not (file.filename or "").casefold().endswith(".zip"): raise HTTPException(status_code=415, detail="Envie um único arquivo ZIP")
    package = analyze_package(file.filename or "opportunity.zip", await file.read(), opportunity_id.strip() or None, include_content=True)
    try: agents = json.loads(agents_json)
    except json.JSONDecodeError as exc: raise HTTPException(status_code=422, detail="agents_json inválido") from exc
    if not isinstance(agents, list): raise HTTPException(status_code=422, detail="agents_json deve ser uma lista")
    inferred = package.get("inferred") or {}
    opportunity = {"opportunity_id": opportunity_id.strip() or package.get("opportunity_id"), "client": client.strip() or inferred.get("client"), "rfq_id": rfq_id.strip() or inferred.get("rfq_id"), "owner": owner.strip(), "agents": agents}
    result = await post_to_n8n({"opportunity": opportunity, "package": package, "channel": "single-zip-upload", "requested_outputs": ["xlsx", "pdf", "json"]})
    result.setdefault("opportunity", opportunity); result.setdefault("package_summary", package.get("summary", {})); result.setdefault("manifest_artifact", package.get("manifest_artifact"))
    return result

from __future__ import annotations

import os

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from .main import app, auth


def allowed_origins() -> list[str]:
    raw = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:5678,https://stepoil-debug.github.io",
    )
    return [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-STEP-API-KEY"],
    expose_headers=["Content-Disposition"],
    max_age=3600,
)


@app.post("/v1/audits/dispatch", dependencies=[Depends(auth)])
async def dispatch_audit(request: Request) -> dict:
    webhook_url = os.getenv("N8N_AUDIT_WEBHOOK_URL", "").strip()
    if not webhook_url:
        raise HTTPException(status_code=503, detail="N8N_AUDIT_WEBHOOK_URL não configurada")

    payload = await request.json()
    headers = {"Content-Type": "application/json"}
    internal_token = os.getenv("N8N_AUDIT_WEBHOOK_TOKEN", "").strip()
    if internal_token:
        headers["X-STEP-INTERNAL-TOKEN"] = internal_token

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=15.0)) as client:
            response = await client.post(webhook_url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao chamar o n8n: {exc}") from exc

    try:
        body = response.json()
    except ValueError:
        body = {"message": response.text}

    if response.is_error:
        detail = body.get("message") if isinstance(body, dict) else None
        raise HTTPException(status_code=502, detail=detail or f"n8n respondeu HTTP {response.status_code}")

    return body if isinstance(body, dict) else {"result": body}

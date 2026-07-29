from __future__ import annotations

import os

from fastapi.middleware.cors import CORSMiddleware

from .main import app


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

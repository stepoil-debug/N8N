from __future__ import annotations

import os
from enum import StrEnum
from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field


class SkillStatus(StrEnum):
    AVAILABLE = "available"
    ADAPTER_PENDING = "adapter_pending"
    DISABLED = "disabled"


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "audit-api"


class SkillInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    status: SkillStatus
    description: str


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    revision_id: UUID
    storage_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")


class SkillRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correlation_id: UUID
    opportunity_id: UUID
    audit_run_id: UUID
    idempotency_key: str = Field(min_length=16, max_length=512)
    input_refs: list[EvidenceRef] = Field(min_length=1)
    options: dict[str, Any] = Field(default_factory=dict)


class SkillRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    correlation_id: UUID
    skill: str
    skill_version: str
    result_ref: str | None = None
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, int | float | str] = Field(default_factory=dict)


SKILLS: dict[str, SkillInfo] = {
    "triagem-rfq": SkillInfo(
        name="triagem-rfq",
        version="0.2.0",
        status=SkillStatus.ADAPTER_PENDING,
        description="Classifica documentos e extrai requisitos da RFQ com evidências.",
    ),
    "validacao-aderencia-proposta": SkillInfo(
        name="validacao-aderencia-proposta",
        version="0.4.0",
        status=SkillStatus.ADAPTER_PENDING,
        description="Compara requisitos do cliente com compromissos da proposta STEP.",
    ),
}

app = FastAPI(
    title="STEP Audit API",
    version="0.1.0",
    docs_url="/docs" if os.getenv("ENABLE_API_DOCS", "false").lower() == "true" else None,
    redoc_url=None,
)


def require_internal_token(
    x_step_internal_token: str | None = Header(default=None),
) -> None:
    expected = os.getenv("AUDIT_API_SHARED_SECRET")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal authentication is not configured.",
        )
    if x_step_internal_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal token.",
        )


@app.get("/health", response_model=HealthResponse, include_in_schema=False)
def health() -> HealthResponse:
    return HealthResponse()


@app.get(
    "/v1/skills",
    response_model=list[SkillInfo],
    dependencies=[Depends(require_internal_token)],
)
def list_skills() -> list[SkillInfo]:
    return list(SKILLS.values())


@app.post(
    "/v1/skills/{skill_name}/runs",
    response_model=SkillRunResponse,
    dependencies=[Depends(require_internal_token)],
)
def run_skill(skill_name: str, request: SkillRunRequest) -> SkillRunResponse:
    skill = SKILLS.get(skill_name)
    if skill is None:
        raise HTTPException(status_code=404, detail="Unknown skill.")

    if skill.status is not SkillStatus.AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": "The skill adapter has not been installed yet.",
                "skill": skill.name,
                "version": skill.version,
                "status": skill.status,
            },
        )

    # The adapters will be connected in the next implementation stage.
    # This explicit failure prevents a scaffold from being mistaken for a real audit.
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Skill adapter execution is not implemented.",
    )

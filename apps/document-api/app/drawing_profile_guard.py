from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from . import drawing_audit_service
from .ai_batch_service import entry_text

_ORIGINAL_CLIENT_CONTEXT = drawing_audit_service._client_context


def _fold(value: Any) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in text if not unicodedata.combining(char)).casefold()


def _identity_groups(profile: dict[str, Any]) -> tuple[list[str], list[str]]:
    identity = profile.get("identity") if isinstance(profile.get("identity"), dict) else {}
    client_terms: set[str] = set()
    project_terms: set[str] = set()

    for value in (identity.get("engineering_client"), identity.get("operator_client")):
        normalized = _fold(value).strip()
        if normalized:
            client_terms.add(normalized)
    for alias in identity.get("aliases") or []:
        normalized = _fold(alias).strip()
        if not normalized:
            continue
        if any(token in normalized for token in ("fps", "hi", "project", "cidade", "ilha")):
            project_terms.add(normalized)
        elif normalized not in {"petrobras", "offshore"}:
            client_terms.add(normalized)

    project = _fold(identity.get("project")).strip()
    project_code = _fold(identity.get("project_code")).strip()
    if project:
        project_terms.add(project)
        simplified = project.replace("fpsо", "").replace("fpso", "").strip()
        if simplified:
            project_terms.add(simplified)
    if project_code:
        project_terms.add(project_code)
    return sorted(client_terms, key=len, reverse=True), sorted(project_terms, key=len, reverse=True)


def guarded_client_context(
    opportunity: dict[str, Any],
    package: dict[str, Any],
    drawings: list[dict[str, Any]],
    conditionals: list[dict[str, Any]],
    temporary_rules: list[dict[str, Any]],
    profile_id: str,
) -> dict[str, Any]:
    if profile_id:
        profile = drawing_audit_service._profile_by_id(profile_id)
        if profile is None:
            raise HTTPException(status_code=422, detail=f"Perfil permanente desconhecido: {profile_id}")
        evidence_text = _fold(
            "\n".join(
                [
                    str(opportunity),
                    str(package.get("package_name") or ""),
                    *(str(entry.get("path") or "") for entry in [*drawings, *conditionals]),
                    *(entry_text(entry)[:2500] for entry in [*drawings[:3], *conditionals[:3]]),
                ]
            )
        )
        client_terms, project_terms = _identity_groups(profile)
        client_match = not client_terms or any(term in evidence_text for term in client_terms)
        project_match = not project_terms or any(term in evidence_text for term in project_terms)
        # A project-specific profile requires project evidence. A generic operator name,
        # such as Petrobras, can never authorize rules from another FPSO by itself.
        if not client_match or not project_match:
            identity = profile.get("identity") or {}
            raise HTTPException(
                status_code=422,
                detail=(
                    f"O perfil {profile_id} pertence a {identity.get('engineering_client') or 'cliente específico'} / "
                    f"{identity.get('project') or identity.get('project_code') or 'projeto específico'}. "
                    "Cliente e projeto dos documentos enviados não confirmam essa identidade; a regra não será aplicada."
                ),
            )
    return _ORIGINAL_CLIENT_CONTEXT(
        opportunity,
        package,
        drawings,
        conditionals,
        temporary_rules,
        profile_id,
    )


drawing_audit_service._client_context = guarded_client_context

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


def _identity_terms(profile: dict[str, Any]) -> list[str]:
    identity = profile.get("identity") if isinstance(profile.get("identity"), dict) else {}
    values = [
        identity.get("engineering_client"),
        identity.get("operator_client"),
        identity.get("project"),
        identity.get("project_code"),
        *(identity.get("aliases") or []),
    ]
    terms: set[str] = set()
    for value in values:
        normalized = _fold(value).strip()
        if len(normalized) >= 4:
            terms.add(normalized)
        for piece in normalized.replace("/", " ").replace("—", " ").replace("-", " ").split():
            if len(piece) >= 4 and piece not in {"offshore", "project", "piping", "petrobras", "single"}:
                terms.add(piece)
    # Petrobras and SBM are meaningful client identifiers even though one is broad.
    if "petrobras" in _fold(values):
        terms.add("petrobras")
    if "sbm" in _fold(values):
        terms.add("sbm")
    return sorted(terms, key=len, reverse=True)


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
        terms = _identity_terms(profile)
        if not any(term in evidence_text for term in terms):
            identity = profile.get("identity") or {}
            raise HTTPException(
                status_code=422,
                detail=(
                    f"O perfil {profile_id} pertence a {identity.get('engineering_client') or identity.get('project')}. "
                    "Cliente, projeto e documentos enviados não confirmam essa identidade; a regra não será aplicada."
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

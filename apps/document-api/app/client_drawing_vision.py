from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from . import drawing_vision

_CONTEXT_LOCK = asyncio.Lock()


def compact_client_context(context: dict[str, Any], temporary_rules: list[dict[str, Any]], max_chars: int = 11000) -> str:
    applicable = [
        rule for rule in (context.get("rules") or [])
        if isinstance(rule, dict) and rule.get("context_match", True)
    ]
    payload = {
        "scope_policy": {
            "client_profile_isolated": True,
            "temporary_rules_apply_only_to_this_execution": True,
            "do_not_transfer_rules_to_another_client": True,
            "ambiguous_context": "not_verifiable",
        },
        "profile_id": context.get("profile_id"),
        "identity": context.get("identity") or {},
        "resolution_order": context.get("resolution_order") or [],
        "inferred_context": context.get("inferred_context") or {},
        "governance": context.get("governance") or {},
        "applicable_rules": applicable,
        "pmc_profiles": context.get("pmc_profiles") or {},
        "profile_alerts": context.get("alerts") or [],
        "temporary_client_conditions": temporary_rules,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))[:max_chars]


def overview_prompt(
    entry: dict[str, Any],
    page: dict[str, Any],
    knowledge: dict[str, Any],
    context_text: str,
) -> str:
    return drawing_vision._overview_prompt(entry, page, knowledge) + f"""

CONDICIONAIS EXCLUSIVAS DESTA EXECUÇÃO E DESTE CLIENTE:
{context_text}

REGRAS DE ESCOPO:
- Aplique apenas regras compatíveis com cliente, projeto, área, classe, serviço, componente e revisão identificados.
- Não transfira uma regra de Vessel para Topsides, de um projeto para outro ou de um cliente para outro.
- Quando o contexto de aplicabilidade não puder ser confirmado, classifique como not_verifiable.
- Quando um achado depender de regra específica do cliente, informe seu rule_id ou conditional_id.
"""


def tile_prompt(
    entry: dict[str, Any],
    page: dict[str, Any],
    tile_name: str,
    overview: dict[str, Any],
    knowledge: dict[str, Any],
    context_text: str,
) -> str:
    return drawing_vision._tile_prompt(entry, page, tile_name, overview, knowledge) + f"""

CONDICIONAIS EXCLUSIVAS DESTA EXECUÇÃO E DESTE CLIENTE:
{context_text}
"""


async def analyze_drawing_with_client_context(
    entry: dict[str, Any],
    client_context: dict[str, Any],
    temporary_rules: list[dict[str, Any]],
) -> dict[str, Any]:
    visuals = entry.get("drawing_visuals") or {}
    pages = visuals.get("pages") or []
    if not pages:
        return {
            "source_document": entry.get("path"),
            "source_owner": entry.get("source_owner"),
            "status": "not_analyzed",
            "pages": [],
            "issues": [],
            "warnings": visuals.get("warnings") or ["Desenho sem imagem renderizada."],
        }

    context_text = compact_client_context(client_context, temporary_rules)
    knowledge = drawing_vision.load_knowledge()
    page_results: list[dict[str, Any]] = []
    all_issues: list[dict[str, Any]] = []
    warnings = list(visuals.get("warnings") or [])

    async with _CONTEXT_LOCK:
        for page in pages[: drawing_vision.MAX_PAGES]:
            page_number = int(page.get("page") or 0)
            try:
                overview = await drawing_vision._vision_request(
                    Path(str(page["overview_path"])),
                    overview_prompt(entry, page, knowledge, context_text),
                )
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"Página {page_number}: análise visual indisponível: {exc}")
                all_issues.append(
                    drawing_vision._normalize_issue(
                        {
                            "rule_id": "D00",
                            "title": "Página de desenho não verificada visualmente",
                            "evidence": f"Página {page_number}",
                            "contradiction": "",
                            "required_correction": "Realizar revisão humana da página em resolução original.",
                            "severity": "informational",
                            "blocking": False,
                            "confidence": 0.0,
                            "requires_human_review": True,
                        },
                        entry,
                        page_number,
                        "overview",
                    )
                )
                continue

            for issue in drawing_vision._objects(overview.get("issues")):
                all_issues.append(drawing_vision._normalize_issue(issue, entry, page_number, "overview"))

            requested = [
                name for name in (overview.get("needs_detail_tiles") or [])
                if name in drawing_vision._TILE_ORDER
            ]
            detail_results: list[dict[str, Any]] = []
            for tile_name in requested[: drawing_vision.MAX_DETAIL_TILES]:
                tile_path = (page.get("tile_paths") or {}).get(tile_name)
                if not tile_path:
                    continue
                try:
                    detail = await drawing_vision._vision_request(
                        Path(tile_path),
                        tile_prompt(entry, page, tile_name, overview, knowledge, context_text),
                    )
                    detail_results.append({"tile": tile_name, **detail})
                    for issue in drawing_vision._objects(detail.get("issues")):
                        all_issues.append(drawing_vision._normalize_issue(issue, entry, page_number, tile_name))
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"Página {page_number}/{tile_name}: detalhe não analisado: {exc}")

            page_results.append({"page": page_number, "overview": overview, "details": detail_results})

    all_issues = drawing_vision._dedupe(
        all_issues,
        ("rule_id", "title", "source_document", "page", "region", "evidence"),
    )
    return {
        "source_document": entry.get("path"),
        "source_owner": entry.get("source_owner"),
        "document_type": entry.get("document_type"),
        "status": "analyzed" if page_results else "not_verifiable",
        "pages": page_results,
        "issues": all_issues,
        "warnings": warnings,
        "pages_analyzed": len(page_results),
        "client_profile_id": client_context.get("profile_id"),
        "temporary_conditionals_applied": len(temporary_rules),
    }

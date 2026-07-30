from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_CLASS_RE = re.compile(r"\b\d{2}[A-Z]\d{2}\b", re.I)


def _root() -> Path:
    configured = os.getenv("CLIENT_KNOWLEDGE_ROOT", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3] / "knowledge" / "clients"


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


@lru_cache(maxsize=1)
def load_client_profiles() -> tuple[dict[str, Any], ...]:
    profiles: list[dict[str, Any]] = []
    root = _root()
    if not root.is_dir():
        return tuple()
    for path in sorted(root.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or not data.get("profile_id"):
            continue
        data = {**data, "_source_path": str(path)}
        profiles.append(data)
    return tuple(profiles)


def _document_text(extraction: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in extraction.get("document_summary") or []:
        if isinstance(item, dict):
            parts.extend([_clean(item.get("source_document")), _clean(item.get("summary"))])
    for item in extraction.get("drawing_analysis") or []:
        if isinstance(item, dict):
            parts.extend([
                _clean(item.get("source_document")),
                _clean(item.get("drawing_class")),
                _clean(item.get("title_block")),
                _clean(item.get("observations")),
            ])
    for key in ("requirements", "commitments"):
        for item in (extraction.get(key) or [])[:80]:
            if isinstance(item, dict):
                parts.extend([
                    _clean(item.get("source_document")),
                    _clean(item.get("requirement") or item.get("commitment")),
                    _clean(item.get("source_evidence")),
                ])
    return "\n".join(part for part in parts if part)


def _haystack(opportunity: dict[str, Any], extraction: dict[str, Any]) -> str:
    return "\n".join([
        _clean(opportunity),
        _document_text(extraction),
    ]).casefold()


def _profile_score(profile: dict[str, Any], text: str) -> int:
    identity = profile.get("identity") if isinstance(profile.get("identity"), dict) else {}
    score = 0
    project_code = _clean(identity.get("project_code")).casefold()
    project = _clean(identity.get("project")).casefold()
    engineering_client = _clean(identity.get("engineering_client")).casefold()
    operator_client = _clean(identity.get("operator_client")).casefold()
    if project_code and project_code in text:
        score += 12
    if project and project in text:
        score += 10
    if engineering_client and engineering_client in text:
        score += 8
    if operator_client and operator_client in text:
        score += 8
    for alias in identity.get("aliases") or []:
        normalized = _clean(alias).casefold()
        if normalized and normalized in text:
            score += 2
    for source in profile.get("source_registry") or []:
        if not isinstance(source, dict):
            continue
        document_id = _clean(source.get("document_id")).replace("-", "").casefold()
        normalized_text = text.replace("-", "").replace(" ", "")
        if document_id and document_id in normalized_text:
            score += 8
    return score


def select_client_profile(opportunity: dict[str, Any], extraction: dict[str, Any]) -> tuple[dict[str, Any] | None, int]:
    text = _haystack(opportunity, extraction)
    ranked = sorted(
        ((_profile_score(profile, text), profile) for profile in load_client_profiles()),
        key=lambda item: item[0],
        reverse=True,
    )
    if not ranked or ranked[0][0] < 4:
        return None, 0
    return ranked[0][1], ranked[0][0]


def _detect_area(opportunity: dict[str, Any], text: str) -> str:
    explicit = _clean(opportunity.get("area") or opportunity.get("location") or opportunity.get("discipline")).casefold()
    if explicit:
        if any(token in explicit for token in ("vessel", "marine", "navio")):
            return "vessel"
        if any(token in explicit for token in ("topsides", "turret", "process")):
            return "topsides"
    vessel_hits = sum(text.count(token) for token in (" vessel", "marine piping", "navio"))
    topsides_hits = sum(text.count(token) for token in ("topsides", "turret"))
    if vessel_hits and topsides_hits:
        if vessel_hits >= topsides_hits * 2:
            return "vessel"
        if topsides_hits >= vessel_hits * 2:
            return "topsides"
        return "mixed"
    if vessel_hits:
        return "vessel"
    if topsides_hits:
        return "topsides"
    return "unknown"


def _detected_classes(text: str) -> list[str]:
    return sorted({match.upper() for match in _CLASS_RE.findall(text.upper())})


def _detected_services(profile: dict[str, Any], text: str) -> list[str]:
    dictionary = profile.get("service_dictionary") if isinstance(profile.get("service_dictionary"), dict) else {}
    found: set[str] = set()
    upper = text.upper()
    for code, description in dictionary.items():
        if re.search(rf"(?<![A-Z0-9]){re.escape(str(code).upper())}(?![A-Z0-9])", upper):
            found.add(str(code).upper())
        elif _clean(description).casefold() in text:
            found.add(str(code).upper())
    return sorted(found)


def _active_rules(profile: dict[str, Any], area: str, classes: list[str], services: list[str]) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    rules.extend(item for item in profile.get("area_router") or [] if isinstance(item, dict))
    rules.extend(item for item in profile.get("conditional_rules") or [] if isinstance(item, dict))
    rules.extend(item for item in profile.get("project_specific_checks") or [] if isinstance(item, dict))
    # Keep all governance rules, but annotate simple context matches so the model never
    # mistakes an inactive conditional for an unconditional requirement.
    annotated: list[dict[str, Any]] = []
    for rule in rules:
        when = rule.get("when") if isinstance(rule.get("when"), dict) else {}
        areas = {str(value).casefold() for value in when.get("area") or []}
        class_codes = {str(value).upper() for value in when.get("class_codes") or []}
        service_codes = {str(value).upper() for value in when.get("service_codes") or []}
        matches = True
        if areas and area not in areas and "any" not in areas:
            matches = False
        if class_codes and not class_codes.intersection(classes):
            matches = False
        if service_codes and not service_codes.intersection(services):
            matches = False
        annotated.append({**rule, "context_match": matches})
    return annotated


def _context_alerts(profile: dict[str, Any], area: str, classes: list[str], services: list[str]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    pmcs = profile.get("pmc_profiles") if isinstance(profile.get("pmc_profiles"), dict) else {}
    for class_code in classes:
        keys = [key for key in pmcs if key.casefold().endswith(f":{class_code.casefold()}")]
        if not keys:
            continue
        area_keys = [key for key in keys if key.casefold().startswith(f"{area.casefold()}:")]
        if area in {"vessel", "topsides"} and not area_keys:
            alerts.append({
                "check_id": "HI39520-XAREA-001",
                "severity": "high",
                "status": "not_verifiable",
                "message": f"A classe {class_code} foi encontrada, mas o perfil conhecido está registrado para outra área. Exigir base formal de cross-reference ou desvio.",
            })
        for key in area_keys or keys:
            profile_services = {str(value).upper() for value in (pmcs[key].get("service_codes") or [])}
            if services and profile_services and not profile_services.intersection(services):
                alerts.append({
                    "check_id": "HI39520-SERVICE-001",
                    "severity": "high",
                    "status": "candidate_finding",
                    "message": f"A classe {class_code} permite {sorted(profile_services)}, mas o pacote indica serviço(s) {services}. Confirmar P&ID, classe e aprovação de engenharia.",
                })
    return alerts


def resolve_client_knowledge(opportunity: dict[str, Any], extraction: dict[str, Any]) -> dict[str, Any]:
    profile, score = select_client_profile(opportunity, extraction)
    if profile is None:
        return {
            "matched": False,
            "profile_id": None,
            "message": "Nenhum perfil condicional específico foi reconhecido; aplicar apenas evidências do pacote e conhecimento geral.",
        }
    text = _haystack(opportunity, extraction)
    area = _detect_area(opportunity, text)
    classes = _detected_classes(text)
    services = _detected_services(profile, text)
    pmcs = profile.get("pmc_profiles") if isinstance(profile.get("pmc_profiles"), dict) else {}
    selected_pmcs = {
        key: value for key, value in pmcs.items()
        if any(key.casefold().endswith(f":{code.casefold()}") for code in classes)
    }
    return {
        "matched": True,
        "profile_id": profile.get("profile_id"),
        "match_score": score,
        "identity": profile.get("identity") or {},
        "source_registry": profile.get("source_registry") or [],
        "resolution_order": profile.get("resolution_order") or [],
        "governance": profile.get("governance") or {},
        "inferred_context": {
            "area": area,
            "class_codes": classes,
            "service_codes": services,
        },
        "rules": _active_rules(profile, area, classes, services),
        "pmc_profiles": selected_pmcs,
        "alerts": _context_alerts(profile, area, classes, services),
    }


def client_knowledge_prompt(context: dict[str, Any], max_chars: int = 12000) -> str:
    if not context.get("matched"):
        return "Nenhuma base condicional específica do cliente foi reconhecida."
    compact = {
        "profile_id": context.get("profile_id"),
        "identity": context.get("identity"),
        "resolution_order": context.get("resolution_order"),
        "governance": context.get("governance"),
        "inferred_context": context.get("inferred_context"),
        "rules": context.get("rules"),
        "pmc_profiles": context.get("pmc_profiles"),
        "alerts": context.get("alerts"),
    }
    encoded = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    return encoded[:max_chars]


def client_knowledge_summary(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "matched": bool(context.get("matched")),
        "profile_id": context.get("profile_id"),
        "match_score": context.get("match_score"),
        "inferred_context": context.get("inferred_context") or {},
        "rules_loaded": len(context.get("rules") or []),
        "pmc_profiles_loaded": sorted((context.get("pmc_profiles") or {}).keys()),
        "alerts": context.get("alerts") or [],
    }

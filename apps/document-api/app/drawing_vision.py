from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException
from PIL import Image
from pdf2image import convert_from_bytes

from .main import safe, workspace

MAX_PAGES = int(os.getenv("DRAWING_VISION_MAX_PAGES", "8"))
MAX_DETAIL_TILES = int(os.getenv("DRAWING_VISION_MAX_DETAIL_TILES", "1"))
DRAWING_DPI = int(os.getenv("DRAWING_VISION_DPI", "190"))
MAX_IMAGE_DIMENSION = int(os.getenv("DRAWING_VISION_MAX_IMAGE_DIMENSION", "2600"))
MIN_INTERVAL = float(os.getenv("DRAWING_VISION_MIN_INTERVAL_SECONDS", "5"))
MAX_RETRIES = int(os.getenv("DRAWING_VISION_MAX_RETRIES", "3"))
VISION_MAX_TOKENS = int(os.getenv("DRAWING_VISION_MAX_TOKENS", "2600"))

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
_DRAWING_WORDS = {
    "drawing", "desenho", "dwg", "sob-", "str-", "fabrication", "assembly",
    "montagem", "isometric", "isometrico", "isométrico", "spool", "weld map",
    "mapa de solda", "support", "suporte", "flange", "nozzle", "croqui",
}
_TILE_ORDER = ("top_left", "top_right", "bottom_left", "bottom_right")
_last_call = 0.0
_call_lock = asyncio.Lock()


def _knowledge_path() -> Path:
    configured = os.getenv("DRAWING_KNOWLEDGE_PATH", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3] / "knowledge" / "offshore_drawing_rules.json"


def load_knowledge() -> dict[str, Any]:
    path = _knowledge_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Base de conhecimento de desenhos inválida: {path}: {exc}") from exc
    if not isinstance(data, dict) or not data.get("drawing_families"):
        raise RuntimeError("Base de conhecimento de desenhos está incompleta")
    return data


def is_drawing_candidate(path: str, document_type: str = "") -> bool:
    suffix = Path(path).suffix.casefold()
    text = path.casefold()
    return (
        document_type == "drawing"
        or suffix in _IMAGE_SUFFIXES
        or (suffix == ".pdf" and any(word in text for word in _DRAWING_WORDS))
    )


def _resize(image: Image.Image, maximum: int = MAX_IMAGE_DIMENSION) -> Image.Image:
    image = image.convert("RGB")
    width, height = image.size
    scale = min(1.0, maximum / max(width, height))
    if scale < 1.0:
        image = image.resize((max(1, int(width * scale)), max(1, int(height * scale))), Image.Resampling.LANCZOS)
    return image


def _save_jpeg(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(path, format="JPEG", quality=88, optimize=True)


def _tiles(image: Image.Image) -> dict[str, Image.Image]:
    width, height = image.size
    overlap_x = int(width * 0.08)
    overlap_y = int(height * 0.08)
    mid_x, mid_y = width // 2, height // 2
    boxes = {
        "top_left": (0, 0, min(width, mid_x + overlap_x), min(height, mid_y + overlap_y)),
        "top_right": (max(0, mid_x - overlap_x), 0, width, min(height, mid_y + overlap_y)),
        "bottom_left": (0, max(0, mid_y - overlap_y), min(width, mid_x + overlap_x), height),
        "bottom_right": (max(0, mid_x - overlap_x), max(0, mid_y - overlap_y), width, height),
    }
    return {name: _resize(image.crop(box)) for name, box in boxes.items()}


def prepare_drawing_visuals(filename: str, data: bytes, opportunity_id: str) -> dict[str, Any]:
    suffix = Path(filename).suffix.casefold()
    warnings: list[str] = []
    try:
        if suffix == ".pdf":
            images = convert_from_bytes(
                data,
                dpi=DRAWING_DPI,
                first_page=1,
                last_page=MAX_PAGES,
                fmt="jpeg",
                thread_count=2,
            )
        elif suffix in _IMAGE_SUFFIXES:
            with Image.open(io.BytesIO(data)) as source:
                images = [source.convert("RGB")]
        else:
            return {"status": "not_supported", "pages": [], "warnings": [f"Formato visual não suportado: {suffix}"]}
    except Exception as exc:  # noqa: BLE001
        return {"status": "render_error", "pages": [], "warnings": [f"Falha ao renderizar desenho: {exc}"]}

    root = workspace(opportunity_id) / "drawing-vision" / safe(Path(filename).stem, "drawing")
    pages: list[dict[str, Any]] = []
    for page_number, source in enumerate(images[:MAX_PAGES], 1):
        overview = _resize(source)
        overview_path = root / f"page-{page_number:03d}-overview.jpg"
        _save_jpeg(overview, overview_path)
        tile_paths: dict[str, str] = {}
        if min(overview.size) >= 900:
            for tile_name, tile in _tiles(overview).items():
                tile_path = root / f"page-{page_number:03d}-{tile_name}.jpg"
                _save_jpeg(tile, tile_path)
                tile_paths[tile_name] = str(tile_path)
        pages.append(
            {
                "page": page_number,
                "width": overview.size[0],
                "height": overview.size[1],
                "overview_path": str(overview_path),
                "tile_paths": tile_paths,
            }
        )

    if suffix == ".pdf" and len(images) >= MAX_PAGES:
        warnings.append(f"Análise visual limitada às primeiras {MAX_PAGES} páginas por arquivo.")
    return {
        "status": "prepared" if pages else "empty",
        "source_filename": filename,
        "pages": pages,
        "warnings": warnings,
        "render_dpi": DRAWING_DPI,
    }


def _compact_rules(knowledge: dict[str, Any]) -> str:
    sections: list[str] = []
    for key in ("weld_checks", "bolting_checks", "piping_checks", "drawing_integrity_checks"):
        rules = knowledge.get(key) or []
        lines = [f"{item.get('id')}: {item.get('question')}" for item in rules if isinstance(item, dict)]
        sections.append(f"{key}:\n" + "\n".join(lines))
    policy = "\n".join(str(item) for item in (knowledge.get("governance") or {}).get("evidence_policy") or [])
    return f"POLÍTICA DE EVIDÊNCIA:\n{policy}\n\nREGRAS:\n" + "\n\n".join(sections)


def _parse_json(value: Any) -> dict[str, Any]:
    text = str(value or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("resposta visual sem objeto JSON")
        result = json.loads(text[start : end + 1])
    if not isinstance(result, dict):
        raise ValueError("resposta visual não é objeto JSON")
    return result


def _data_url(path: Path) -> str:
    mime = "image/png" if path.suffix.casefold() == ".png" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


async def _rate_limit() -> None:
    global _last_call
    async with _call_lock:
        elapsed = time.monotonic() - _last_call
        if elapsed < MIN_INTERVAL:
            await asyncio.sleep(MIN_INTERVAL - elapsed)
        _last_call = time.monotonic()


async def _vision_request(image_path: Path, prompt: str) -> dict[str, Any]:
    token = os.getenv("LLM_API_KEY", "").strip()
    if not token:
        raise HTTPException(status_code=503, detail="LLM_API_KEY não configurada para análise visual")
    payload = {
        "model": os.getenv("DRAWING_VISION_MODEL", os.getenv("LLM_MODEL", "openai/gpt-4.1-mini")),
        "messages": [
            {
                "role": "system",
                "content": (
                    "Você é especialista sênior em desenhos offshore, fabricação, estruturas, piping, soldagem e conexões aparafusadas. "
                    "Use somente o que estiver visualmente legível e o contexto fornecido. Não invente dimensões, quantidades, normas ou componentes. "
                    "Retorne exclusivamente JSON válido."
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": _data_url(image_path), "detail": "high"}},
                ],
            },
        ],
        "temperature": 0.0,
        "max_tokens": VISION_MAX_TOKENS,
        "stream": False,
    }
    headers = {
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": os.getenv("GITHUB_MODELS_API_VERSION", "2026-03-10"),
    }
    url = os.getenv("LLM_BASE_URL", "https://models.github.ai/inference/chat/completions")
    last_error = "modelo visual indisponível"
    async with httpx.AsyncClient(timeout=httpx.Timeout(360.0, connect=30.0)) as client:
        for attempt in range(1, MAX_RETRIES + 1):
            await _rate_limit()
            try:
                response = await client.post(url, json=payload, headers=headers)
                if response.is_error:
                    last_error = f"HTTP {response.status_code}: {response.text[:1200]}"
                    print(f"[drawing-vision] tentativa {attempt}/{MAX_RETRIES}: {last_error}", file=sys.stderr, flush=True)
                    if response.status_code in {408, 409, 429, 500, 502, 503, 504} and attempt < MAX_RETRIES:
                        await asyncio.sleep(min(10 * attempt, 40))
                        continue
                    break
                body = response.json()
                return _parse_json(body["choices"][0]["message"]["content"])
            except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                print(f"[drawing-vision] tentativa {attempt}/{MAX_RETRIES}: {last_error}", file=sys.stderr, flush=True)
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(min(8 * attempt, 30))
    raise HTTPException(status_code=502, detail=f"Falha na análise visual: {last_error}")


def _page_text(entry: dict[str, Any], page_number: int) -> str:
    extracted = entry.get("extracted") or {}
    if extracted.get("kind") != "pdf":
        return ""
    for page in extracted.get("content") or []:
        if int(page.get("page") or 0) == page_number:
            return str(page.get("text") or "")[:5000]
    return ""


def _overview_prompt(entry: dict[str, Any], page: dict[str, Any], knowledge: dict[str, Any]) -> str:
    return f"""ARQUIVO: {entry.get('path')}
ORIGEM: {entry.get('source_owner')}
PÁGINA: {page.get('page')}
TEXTO EXTRAÍDO DA PÁGINA:
{_page_text(entry, int(page.get('page') or 0))}

{_compact_rules(knowledge)}

TAREFA:
1. Classifique o desenho e leia o carimbo, revisão, escala, unidades e normas somente quando legíveis.
2. Identifique vistas, cortes, detalhes, BOM, balões, materiais, soldas, flanges, furos, parafusos/prisioneiros/porcas/arruelas, suportes e interfaces.
3. Procure inconsistências internas e indícios de itens ausentes, mas respeite a política de evidência.
4. Para parafuso ausente, confirme conexão de montagem e cruze padrão de furos com BOM/callout; um círculo isolado não é prova.
5. Para solda ausente, confirme que a união é permanente e que não há símbolo, nota geral, detalhe ou conexão alternativa.
6. Aponte no máximo 12 problemas prioritários. Problemas sem confirmação ficam informational/not_verifiable e requerem revisão humana.
7. Escolha no máximo {MAX_DETAIL_TILES} regiões que realmente precisam de ampliação.

RETORNE JSON:
{{
  "drawing_class":"general_arrangement|fabrication_detail|assembly|weld_map|piping_isometric|piping_support|structural|flange_nozzle|other",
  "title_block":{{"drawing_number":"","revision":"","title":"","scale":"","units":"","status":""}},
  "standards_detected":[],
  "observations":[{{"type":"","description":"","evidence":"","region":""}}],
  "welds":[{{"joint":"","symbol_interpretation":"","size":"","length_pitch":"","side":"","process_or_wps":"","nde":"","evidence":"","confidence":0.0}}],
  "bolted_connections":[{{"connection":"","hole_count":null,"fastener_count":null,"fastener_spec":"","gasket_or_washer":"","evidence":"","confidence":0.0}}],
  "holes_and_patterns":[{{"description":"","count":null,"purpose":"","evidence":"","confidence":0.0}}],
  "bom_items":[{{"item":"","description":"","quantity":null,"evidence":""}}],
  "issues":[{{"rule_id":"W01|B02|D02|...","title":"","evidence":"","contradiction":"","required_correction":"","severity":"critical|high|medium|low|informational","blocking":false,"confidence":0.0,"requires_human_review":true}}],
  "needs_detail_tiles":["top_left|top_right|bottom_left|bottom_right"],
  "confidence":0.0
}}"""


def _tile_prompt(entry: dict[str, Any], page: dict[str, Any], tile_name: str, overview: dict[str, Any], knowledge: dict[str, Any]) -> str:
    relevant = [item for item in overview.get("issues") or [] if tile_name in str(item.get("evidence") or "").casefold()]
    return f"""ARQUIVO: {entry.get('path')}
PÁGINA: {page.get('page')}
REGIÃO AMPLIADA: {tile_name}
TIPO DE DESENHO JÁ ESTIMADO: {overview.get('drawing_class')}
PROBLEMAS PRELIMINARES RELACIONADOS: {json.dumps(relevant, ensure_ascii=False)}

{_compact_rules(knowledge)}

Revise esta região em alta resolução. Confirme ou rejeite suspeitas de solda, parafuso, furo, flange, BOM, dimensão, material, revisão ou detalhe ausente. Não conte elementos cortados pela borda da região como padrão completo. Retorne somente JSON:
{{"observations":[],"welds":[],"bolted_connections":[],"holes_and_patterns":[],"bom_items":[],"issues":[{{"rule_id":"","title":"","evidence":"","contradiction":"","required_correction":"","severity":"critical|high|medium|low|informational","blocking":false,"confidence":0.0,"requires_human_review":true}}],"confidence":0.0}}"""


def _objects(value: Any) -> list[dict[str, Any]]:
    return [item for item in (value or []) if isinstance(item, dict)]


def _dedupe(items: list[dict[str, Any]], fields: tuple[str, ...]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = "|".join(re.sub(r"\s+", " ", str(item.get(field) or "").casefold()).strip() for field in fields)
        if key.strip("|") and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _normalize_issue(issue: dict[str, Any], entry: dict[str, Any], page_number: int, region: str) -> dict[str, Any]:
    knowledge = load_knowledge()
    governance = knowledge.get("governance") or {}
    confidence = max(0.0, min(1.0, float(issue.get("confidence") or 0.0)))
    finding_threshold = float(governance.get("finding_threshold") or 0.72)
    blocking_threshold = float(governance.get("blocking_threshold") or 0.88)
    severity = str(issue.get("severity") or "informational").casefold()
    if confidence < finding_threshold:
        severity = "informational"
    blocking = bool(issue.get("blocking")) and confidence >= blocking_threshold and bool(issue.get("contradiction"))
    requires_human = bool(issue.get("requires_human_review")) or confidence < blocking_threshold
    return {
        **issue,
        "severity": severity,
        "blocking": blocking,
        "confidence": confidence,
        "requires_human_review": requires_human,
        "source_document": entry.get("path"),
        "source_owner": entry.get("source_owner"),
        "page": page_number,
        "region": region,
        "status": "candidate_finding" if confidence >= finding_threshold else "not_verifiable",
    }


async def analyze_drawing_entry(entry: dict[str, Any]) -> dict[str, Any]:
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

    knowledge = load_knowledge()
    page_results: list[dict[str, Any]] = []
    all_issues: list[dict[str, Any]] = []
    warnings = list(visuals.get("warnings") or [])
    for page in pages[:MAX_PAGES]:
        page_number = int(page.get("page") or 0)
        try:
            overview = await _vision_request(Path(str(page["overview_path"])), _overview_prompt(entry, page, knowledge))
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Página {page_number}: análise visual indisponível: {exc}")
            all_issues.append(
                _normalize_issue(
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

        for issue in _objects(overview.get("issues")):
            all_issues.append(_normalize_issue(issue, entry, page_number, "overview"))

        requested = [name for name in overview.get("needs_detail_tiles") or [] if name in _TILE_ORDER]
        detail_results: list[dict[str, Any]] = []
        for tile_name in requested[:MAX_DETAIL_TILES]:
            tile_path = (page.get("tile_paths") or {}).get(tile_name)
            if not tile_path:
                continue
            try:
                detail = await _vision_request(Path(tile_path), _tile_prompt(entry, page, tile_name, overview, knowledge))
                detail_results.append({"tile": tile_name, **detail})
                for issue in _objects(detail.get("issues")):
                    all_issues.append(_normalize_issue(issue, entry, page_number, tile_name))
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"Página {page_number}/{tile_name}: detalhe não analisado: {exc}")

        page_results.append({"page": page_number, "overview": overview, "details": detail_results})

    all_issues = _dedupe(all_issues, ("rule_id", "title", "source_document", "page", "region", "evidence"))
    return {
        "source_document": entry.get("path"),
        "source_owner": entry.get("source_owner"),
        "document_type": entry.get("document_type"),
        "status": "analyzed" if page_results else "not_verifiable",
        "pages": page_results,
        "issues": all_issues,
        "warnings": warnings,
        "pages_analyzed": len(page_results),
    }


def drawing_findings(analyses: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    corrections: list[dict[str, Any]] = []
    unverifiable: list[dict[str, Any]] = []
    for analysis in analyses:
        for issue in _objects(analysis.get("issues")):
            evidence = f"{issue.get('source_document')} | página {issue.get('page')} | região {issue.get('region')}: {issue.get('evidence')}"
            if issue.get("status") != "candidate_finding":
                unverifiable.append(
                    {
                        "topic": issue.get("title") or "Observação visual",
                        "reason": issue.get("required_correction") or "Evidência visual insuficiente.",
                        "source_document": issue.get("source_document"),
                        "source_location": f"página {issue.get('page')} / {issue.get('region')}",
                        "source_evidence": issue.get("evidence"),
                    }
                )
                continue
            rule_id = str(issue.get("rule_id") or "D00")
            category = "technical"
            if rule_id.startswith("W"):
                category = "quality"
            elif rule_id.startswith("B"):
                category = "technical"
            elif rule_id.startswith("P"):
                category = "scope"
            findings.append(
                {
                    "severity": issue.get("severity") or "informational",
                    "category": category,
                    "title": issue.get("title") or f"Achado visual {rule_id}",
                    "inconsistency": issue.get("contradiction") or issue.get("title") or "Inconsistência visual candidata.",
                    "impact": "Risco de fabricação, montagem, inspeção ou fornecimento incorreto; confirmar por revisão de engenharia.",
                    "client_evidence": evidence if issue.get("source_owner") == "client" else "",
                    "step_evidence": evidence if issue.get("source_owner") == "step" else "",
                    "required_correction": issue.get("required_correction") or "Corrigir o desenho ou documentar a intenção de projeto.",
                    "blocking": bool(issue.get("blocking")),
                    "requires_human_validation": bool(issue.get("requires_human_review")),
                    "drawing_rule_id": rule_id,
                    "visual_confidence": issue.get("confidence"),
                    "source_document": issue.get("source_document"),
                    "source_location": f"página {issue.get('page')} / {issue.get('region')}",
                }
            )
            corrections.append(
                {
                    "section": f"Desenho {issue.get('source_document')} — página {issue.get('page')}",
                    "current_text": issue.get("contradiction") or issue.get("evidence") or "",
                    "corrected_text": issue.get("required_correction") or "",
                    "reason": f"Regra visual {rule_id}; confiança {issue.get('confidence')}",
                    "requires_human_validation": True,
                    "source_document": issue.get("source_document"),
                }
            )
    return findings, corrections, unverifiable

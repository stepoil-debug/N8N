from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any

import httpx
from fastapi import Depends, HTTPException, Request

from .main import app, auth

MAX_CHARS = int(os.getenv("LLM_MAX_CHUNK_CHARS", "14000"))
API_VERSION = os.getenv("GITHUB_MODELS_API_VERSION", "2026-03-10")


def clean(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def entry_text(entry: dict[str, Any]) -> str:
    extracted = entry.get("extracted") or {}
    content = extracted.get("content") or []
    kind = extracted.get("kind")
    blocks: list[str] = []
    if kind == "pdf":
        blocks = [f"[Página {p.get('page', '?')}] {clean(p.get('text'))}" for p in content if clean(p.get("text"))]
    elif kind == "document":
        for part in content:
            paragraphs = [clean(p) for p in part.get("paragraphs") or [] if clean(p)]
            if paragraphs:
                blocks.append("\n".join(paragraphs))
            for table in part.get("tables") or []:
                blocks.append("\n".join(" | ".join(clean(c) for c in row) for row in table))
    elif kind == "spreadsheet":
        for sheet in content:
            rows = [" | ".join(clean(c) for c in row) for row in sheet.get("rows") or []]
            if rows:
                blocks.append(f"[Planilha {clean(sheet.get('sheet') or 'Dados')}]\n" + "\n".join(rows))
    elif kind == "email":
        for mail in content:
            blocks.append("\n".join([
                f"Assunto: {clean(mail.get('subject'))}", f"De: {clean(mail.get('from'))}",
                f"Para: {clean(mail.get('to'))}", f"Data: {clean(mail.get('date'))}", clean(mail.get("body")),
            ]))
    else:
        for part in content:
            blocks.append(clean(part.get("text") if isinstance(part, dict) else part))
    return "\n\n".join(x for x in blocks if x).strip()


def chunks(text: str, limit: int = MAX_CHARS) -> list[str]:
    text = clean(text)
    result: list[str] = []
    cursor = 0
    while cursor < len(text):
        end = min(cursor + limit, len(text))
        if end < len(text):
            cut = max(text.rfind("\n\n", cursor, end), text.rfind("\n", cursor, end), text.rfind(". ", cursor, end))
            if cut > cursor + limit // 2:
                end = cut + 1
        piece = text[cursor:end].strip()
        if piece:
            result.append(piece)
        cursor = max(end, cursor + 1)
    return result


def parse_json(value: Any) -> dict[str, Any]:
    text = clean(value)
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise HTTPException(status_code=502, detail="O modelo não retornou JSON válido")
        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=502, detail=f"JSON inválido do modelo: {exc}") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="O modelo não retornou objeto JSON")
    return data


async def model(system: str, user: str, max_tokens: int = 3000) -> dict[str, Any]:
    key = os.getenv("LLM_API_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="LLM_API_KEY não configurada")
    payload = {
        "model": os.getenv("LLM_MODEL", "openai/gpt-4.1-mini"),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False, "temperature": 0.1, "max_tokens": min(max_tokens, 3500),
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Accept": "application/vnd.github+json", "Content-Type": "application/json",
        "Authorization": f"Bearer {key}", "X-GitHub-Api-Version": API_VERSION,
    }
    url = os.getenv("LLM_BASE_URL", "https://models.github.ai/inference/chat/completions")
    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=20.0)) as client:
        for attempt in range(1, 4):
            try:
                response = await client.post(url, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                if attempt < 3:
                    await asyncio.sleep(attempt * 2)
                    continue
                raise HTTPException(status_code=502, detail=f"Falha de rede no GitHub Models: {exc}") from exc
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 3:
                    await asyncio.sleep(min(float(response.headers.get("retry-after") or attempt * 3), 20))
                    continue
            if response.is_error:
                raise HTTPException(status_code=502, detail=f"GitHub Models HTTP {response.status_code}: {response.text[:1400]}")
            try:
                return parse_json(response.json()["choices"][0]["message"]["content"])
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise HTTPException(status_code=502, detail="Resposta inválida do GitHub Models") from exc
    raise HTTPException(status_code=502, detail="GitHub Models indisponível")


def objects(value: Any) -> list[dict[str, Any]]:
    return [x for x in (value or []) if isinstance(x, dict)]


def dedupe(items: list[dict[str, Any]], fields: tuple[str, ...]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = re.sub(r"\s+", " ", "|".join(clean(item.get(f)).casefold() for f in fields))
        if key.strip("| ") and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def renumber(items: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    return [{**item, "id": f"{prefix}-{i:03d}"} for i, item in enumerate(items, 1)]


async def extract_piece(entry: dict[str, Any], text: str, index: int, total: int) -> dict[str, Any]:
    path = clean(entry.get("path") or entry.get("filename") or "documento")
    owner = clean(entry.get("source_owner") or "unknown")
    system = "Você extrai requisitos e compromissos de documentos industriais. Use somente evidências fornecidas, nunca invente dados e retorne exclusivamente JSON válido."
    user = f'''Documento: {path}\nOrigem: {owner}\nTipo: {clean(entry.get("document_type"))}\nBloco: {index}/{total}\n\nTEXTO\n{text}\n\nExtraia requisitos quando a origem for client; compromissos quando for step; ambos quando unknown. Inclua caminho, localização e evidência. Itens incompletos vão para not_verifiable.\nFormato: {{"requirements":[{{"category":"technical|commercial|contractual|quality|schedule|documentation|other","requirement":"...","mandatory":true,"source_document":"{path}","source_location":"...","source_evidence":"..."}}],"commitments":[{{"category":"technical|commercial|contractual|quality|schedule|documentation|scope|other","commitment":"...","source_document":"{path}","source_location":"...","source_evidence":"..."}}],"not_verifiable":[{{"topic":"...","reason":"...","source_document":"{path}"}}],"document_summary":{{"source_document":"{path}","role":"client|step|unknown","summary":"..."}}}}'''
    return await model(system, user, 3000)


@app.post("/v1/ai/extract", dependencies=[Depends(auth)])
async def batched_extract(request: Request) -> dict[str, Any]:
    body = await request.json()
    package = body.get("package")
    if not isinstance(package, dict) or not isinstance(package.get("entries"), list):
        raise HTTPException(status_code=422, detail="package.entries é obrigatório")
    requirements: list[dict[str, Any]] = []
    commitments: list[dict[str, Any]] = []
    unverifiable: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    processed = 0
    for entry in package["entries"]:
        if not isinstance(entry, dict) or entry.get("extraction_status") != "extracted":
            continue
        parts = chunks(entry_text(entry))
        for index, part in enumerate(parts, 1):
            result = await extract_piece(entry, part, index, len(parts))
            requirements.extend(objects(result.get("requirements")))
            commitments.extend(objects(result.get("commitments")))
            unverifiable.extend(objects(result.get("not_verifiable")))
            if isinstance(result.get("document_summary"), dict):
                summaries.append(result["document_summary"])
            processed += 1
    requirements = renumber(dedupe(requirements, ("source_document", "source_location", "requirement")), "REQ")
    commitments = renumber(dedupe(commitments, ("source_document", "source_location", "commitment")), "COM")
    if not requirements:
        raise HTTPException(status_code=422, detail="Nenhum requisito do cliente foi extraído")
    if not commitments:
        raise HTTPException(status_code=422, detail="Nenhum compromisso STEP foi extraído")
    result = {
        "requirements": requirements, "commitments": commitments,
        "not_verifiable": dedupe(unverifiable, ("source_document", "topic", "reason")),
        "document_summary": dedupe(summaries, ("source_document", "summary")),
        "batch_info": {"processed_chunks": processed, "max_chunk_chars": MAX_CHARS, "model": os.getenv("LLM_MODEL", "")},
    }
    return {"response": json.dumps(result, ensure_ascii=False)}


def requirement_batches(items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    size = 0
    for item in items:
        encoded = json.dumps(item, ensure_ascii=False)
        if current and (len(current) >= 8 or size + len(encoded) > 7000):
            batches.append(current); current = []; size = 0
        current.append(item); size += len(encoded)
    if current:
        batches.append(current)
    return batches


def related_commitments(batch: list[dict[str, Any]], all_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    categories = {clean(x.get("category")).casefold() for x in batch}
    ordered = [x for x in all_items if clean(x.get("category")).casefold() in categories]
    ordered += [x for x in all_items if x not in ordered]
    selected: list[dict[str, Any]] = []
    size = 0
    for item in ordered:
        encoded = json.dumps(item, ensure_ascii=False)
        if selected and size + len(encoded) > 8000:
            break
        selected.append(item); size += len(encoded)
    return selected


async def audit_piece(opportunity: dict[str, Any], reqs: list[dict[str, Any]], commitments: list[dict[str, Any]], index: int, total: int) -> dict[str, Any]:
    system = "Você é auditor adversarial sênior da STEP Oil & Gas. Compare cada requisito com evidências da proposta. Sem evidência use not_verifiable. Retorne somente JSON válido."
    user = f'''OPORTUNIDADE\n{json.dumps(opportunity, ensure_ascii=False)}\n\nLOTE {index}/{total}\nREQUISITOS\n{json.dumps(reqs, ensure_ascii=False)}\n\nCOMPROMISSOS\n{json.dumps(commitments, ensure_ascii=False)}\n\nRetorne: {{"requirement_assessments":[{{"requirement_id":"REQ-001","status":"met|partial|not_met|not_verifiable","matched_commitment_ids":["COM-001"],"assessment_reason":"..."}}],"findings":[{{"severity":"critical|high|medium|low|informational","category":"technical|commercial|contractual|quality|schedule|documentation|scope","title":"...","inconsistency":"...","impact":"...","client_evidence":"...","step_evidence":"...","required_correction":"...","blocking":true,"requirement_ids":["REQ-001"]}}],"corrections":[{{"section":"...","current_text":"...","corrected_text":"...","reason":"...","requires_human_validation":false,"requirement_ids":["REQ-001"]}}]}}'''
    return await model(system, user, 3300)


def summary(assessments: list[dict[str, Any]], findings: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = [x.get("status") for x in assessments]
    valid = [x for x in statuses if x != "not_verifiable"]
    score = {"met": 1.0, "partial": 0.5, "not_met": 0.0}
    adherence = round(sum(score.get(x, 0) for x in valid) / len(valid) * 100, 1) if valid else None
    coverage = round(len(valid) / len(statuses) * 100, 1) if statuses else None
    blockers = [x for x in findings if x.get("blocking")]
    sev = {clean(x.get("severity")).casefold() for x in findings}
    if "critical" in sev:
        risk, rec = "critical", "do_not_submit"
    elif "high" in sev or blockers:
        risk, rec = "high", "review_before_submit"
    elif "medium" in sev:
        risk, rec = "medium", "submit_with_reservations"
    else:
        risk, rec = "low", "submit"
    return {"recommendation": rec, "risk_level": risk, "executive_opinion": f"Foram avaliados {len(statuses)} requisitos, com {len(findings)} achados e {len(blockers)} bloqueio(s).", "adherence_percent": adherence, "coverage_percent": coverage, "findings_total": len(findings), "blocking_risks": len(blockers)}


async def proposal(opportunity: dict[str, Any], findings: list[dict[str, Any]], corrections: list[dict[str, Any]]) -> dict[str, Any]:
    compact = json.dumps({"opportunity": opportunity, "findings": findings[:25], "corrections": corrections[:35]}, ensure_ascii=False)[:17000]
    system = "Redija proposta técnico-comercial STEP aplicando somente correções evidenciadas. Não invente preço, prazo ou obrigação. Retorne apenas JSON válido."
    user = f'''DADOS\n{compact}\n\nFormato: {{"corrected_proposal":{{"title":"Proposta Técnico-Comercial Revisada","introduction":"...","sections":[{{"title":"...","paragraphs":["..."],"bullets":["..."]}}],"exclusions":["..."]}},"assumptions":["..."]}}'''
    try:
        return await model(system, user, 3000)
    except HTTPException:
        return {"corrected_proposal": {"title": "Proposta Técnico-Comercial Revisada", "introduction": "Versão para revisão humana.", "sections": [{"title": "Correções requeridas", "paragraphs": [], "bullets": [clean(x.get("corrected_text")) for x in corrections if clean(x.get("corrected_text"))]}], "exclusions": ["Dados sem evidência exigem validação humana."]}, "assumptions": ["Baseada nas evidências disponíveis."]}


@app.post("/v1/ai/audit", dependencies=[Depends(auth)])
async def batched_audit(request: Request) -> dict[str, Any]:
    body = await request.json()
    opportunity, extraction = body.get("opportunity"), body.get("extraction")
    if not isinstance(opportunity, dict) or not isinstance(extraction, dict):
        raise HTTPException(status_code=422, detail="opportunity e extraction são obrigatórias")
    reqs, commitments = objects(extraction.get("requirements")), objects(extraction.get("commitments"))
    if not reqs or not commitments:
        raise HTTPException(status_code=422, detail="Extração sem requisitos ou compromissos")
    assessments: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    corrections: list[dict[str, Any]] = []
    batches = requirement_batches(reqs)
    for index, batch in enumerate(batches, 1):
        result = await audit_piece(opportunity, batch, related_commitments(batch, commitments), index, len(batches))
        assessments.extend(objects(result.get("requirement_assessments")))
        findings.extend(objects(result.get("findings")))
        corrections.extend(objects(result.get("corrections")))
    assessments = dedupe(assessments, ("requirement_id",))
    amap = {clean(x.get("requirement_id")): x for x in assessments}
    normalized = [{**r, "status": (amap.get(clean(r.get("id"))) or {}).get("status", "not_verifiable"), "matched_commitment_ids": (amap.get(clean(r.get("id"))) or {}).get("matched_commitment_ids", []), "assessment_reason": (amap.get(clean(r.get("id"))) or {}).get("assessment_reason", "")} for r in reqs]
    findings = renumber(dedupe(findings, ("title", "inconsistency", "required_correction")), "F")
    corrections = renumber(dedupe(corrections, ("section", "corrected_text", "reason")), "C")
    draft = await proposal(opportunity, findings, corrections)
    final = {"summary": summary(assessments, findings), "requirements": normalized, "commitments": commitments, "findings": findings, "corrections": corrections, "corrected_proposal": draft.get("corrected_proposal") or {}, "assumptions": draft.get("assumptions") or [], "not_verifiable": extraction.get("not_verifiable") or [], "batch_info": {"audit_batches": len(batches), "extraction": extraction.get("batch_info") or {}, "model": os.getenv("LLM_MODEL", "")}}
    return {"response": json.dumps(final, ensure_ascii=False)}

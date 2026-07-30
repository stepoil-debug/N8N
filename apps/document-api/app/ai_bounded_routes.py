from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Any

from fastapi import Depends, HTTPException, Request

from . import ai_batch_service as base
from .main import app, auth

MAX_CHUNKS_PER_DOCUMENT = int(os.getenv("LLM_MAX_CHUNKS_PER_DOCUMENT", "2"))
MAX_TOTAL_CHUNKS = int(os.getenv("LLM_MAX_TOTAL_CHUNKS", "24"))
MAX_PROPOSAL_DRAWINGS = int(os.getenv("LLM_MAX_PROPOSAL_DRAWINGS", "2"))
MAX_AUDIT_BATCHES = int(os.getenv("LLM_MAX_AUDIT_BATCHES", "18"))
AI_CONCURRENCY = max(1, int(os.getenv("LLM_AUDIT_CONCURRENCY", "2")))
CHUNK_TIMEOUT_SECONDS = float(os.getenv("LLM_CHUNK_TIMEOUT_SECONDS", "90"))
DRAWING_TIMEOUT_SECONDS = float(os.getenv("LLM_PROPOSAL_DRAWING_TIMEOUT_SECONDS", "180"))
AUDIT_BATCH_TIMEOUT_SECONDS = float(os.getenv("LLM_AUDIT_BATCH_TIMEOUT_SECONDS", "90"))
PROPOSAL_TIMEOUT_SECONDS = float(os.getenv("LLM_PROPOSAL_TIMEOUT_SECONDS", "90"))


def _clean(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def _fallback_extract(entry: dict[str, Any], part: str, reason: str) -> dict[str, Any]:
    path = _clean(entry.get("path") or entry.get("filename") or "documento")
    owner = _clean(entry.get("source_owner") or "unknown").casefold()
    evidence = _clean(part)[:700]
    common = {
        "category": "other",
        "source_document": path,
        "source_location": "bloco preservado para revisão humana",
        "source_evidence": evidence,
    }
    requirements: list[dict[str, Any]] = []
    commitments: list[dict[str, Any]] = []
    if owner in {"client", "unknown"}:
        requirements.append(
            {
                **common,
                "requirement": "Revisar manualmente este trecho do documento do cliente.",
                "mandatory": True,
            }
        )
    if owner in {"step", "unknown"}:
        commitments.append(
            {
                **common,
                "commitment": "Revisar manualmente este trecho do documento STEP.",
            }
        )
    return {
        "requirements": requirements,
        "commitments": commitments,
        "not_verifiable": [
            {
                "topic": "Lote não concluído automaticamente",
                "reason": reason,
                "source_document": path,
            }
        ],
        "document_summary": {
            "source_document": path,
            "role": owner if owner in {"client", "step"} else "unknown",
            "summary": "Conteúdo preservado; este bloco exige revisão humana.",
        },
    }


async def _safe_extract(
    entry: dict[str, Any],
    part: str,
    index: int,
    total: int,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    path = _clean(entry.get("path") or entry.get("filename") or "documento")
    started = time.monotonic()
    async with semaphore:
        print(f"[audit-v2] extração iniciada: {path} bloco {index}/{total}", flush=True)
        try:
            result = await asyncio.wait_for(
                base.extract_piece(entry, part, index, total),
                timeout=CHUNK_TIMEOUT_SECONDS,
            )
            print(
                f"[audit-v2] extração concluída: {path} bloco {index}/{total} "
                f"em {time.monotonic() - started:.1f}s",
                flush=True,
            )
            return result
        except Exception as exc:  # noqa: BLE001
            reason = f"{type(exc).__name__}: {exc}"
            print(f"[audit-v2] extração em contingência: {path}: {reason}", file=sys.stderr, flush=True)
            return _fallback_extract(entry, part, reason)


async def _safe_drawing(entry: dict[str, Any]) -> dict[str, Any]:
    path = _clean(entry.get("path") or entry.get("filename") or "desenho")
    try:
        print(f"[audit-v2] leitura visual iniciada: {path}", flush=True)
        result = await asyncio.wait_for(
            base.analyze_drawing_entry(entry),
            timeout=DRAWING_TIMEOUT_SECONDS,
        )
        print(f"[audit-v2] leitura visual concluída: {path}", flush=True)
        return result
    except Exception as exc:  # noqa: BLE001
        reason = f"{type(exc).__name__}: {exc}"
        print(f"[audit-v2] desenho em contingência: {path}: {reason}", file=sys.stderr, flush=True)
        return {
            "source_document": path,
            "source_owner": entry.get("source_owner"),
            "document_type": entry.get("document_type"),
            "status": "not_verifiable",
            "pages": [],
            "issues": [],
            "warnings": [f"Análise visual limitada pelo tempo da execução: {reason}"],
            "pages_analyzed": 0,
        }


@app.post("/v1/ai/extract-v2", dependencies=[Depends(auth)])
async def bounded_extract(request: Request) -> dict[str, Any]:
    body = await request.json()
    package = body.get("package")
    if not isinstance(package, dict) or not isinstance(package.get("entries"), list):
        raise HTTPException(status_code=422, detail="package.entries é obrigatório")

    entries = [
        entry
        for entry in package["entries"]
        if isinstance(entry, dict) and entry.get("extraction_status") == "extracted"
    ]
    entries.sort(
        key=lambda item: {"client": 0, "step": 1, "unknown": 2}.get(
            _clean(item.get("source_owner")).casefold(), 3
        )
    )

    drawing_entries = [
        entry
        for entry in entries
        if (entry.get("drawing_visuals") or {}).get("status") == "prepared"
    ]
    drawing_analysis = await asyncio.gather(
        *[_safe_drawing(entry) for entry in drawing_entries[:MAX_PROPOSAL_DRAWINGS]]
    ) if drawing_entries else []

    requirements: list[dict[str, Any]] = []
    commitments: list[dict[str, Any]] = []
    unverifiable: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []

    for omitted in drawing_entries[MAX_PROPOSAL_DRAWINGS:]:
        unverifiable.append(
            {
                "topic": "Desenho não revisado visualmente nesta auditoria de proposta",
                "reason": "Use a aba Análise de desenhos para revisão visual profunda; a auditoria de proposta limita desenhos para concluir dentro do tempo seguro.",
                "source_document": omitted.get("path"),
            }
        )
    for visual in drawing_analysis:
        for warning in visual.get("warnings") or []:
            unverifiable.append(
                {
                    "topic": "Cobertura visual do desenho",
                    "reason": warning,
                    "source_document": visual.get("source_document"),
                }
            )

    jobs: list[tuple[dict[str, Any], str, int, int]] = []
    for entry in entries:
        parts = base.chunks(base.entry_text(entry))
        selected = parts[:MAX_CHUNKS_PER_DOCUMENT]
        for index, part in enumerate(selected, 1):
            if len(jobs) >= MAX_TOTAL_CHUNKS:
                break
            jobs.append((entry, part, index, len(selected)))
        if len(parts) > len(selected):
            unverifiable.append(
                {
                    "topic": "Conteúdo documental excedente",
                    "reason": f"{len(parts) - len(selected)} bloco(s) adicional(is) foram preservados para revisão humana por limite operacional.",
                    "source_document": entry.get("path"),
                }
            )
        if len(jobs) >= MAX_TOTAL_CHUNKS:
            break

    if not jobs:
        raise HTTPException(status_code=422, detail="Nenhum conteúdo textual utilizável foi identificado")

    semaphore = asyncio.Semaphore(AI_CONCURRENCY)
    results = await asyncio.gather(
        *[_safe_extract(entry, part, index, total, semaphore) for entry, part, index, total in jobs]
    )
    for result in results:
        requirements.extend(base.objects(result.get("requirements")))
        commitments.extend(base.objects(result.get("commitments")))
        unverifiable.extend(base.objects(result.get("not_verifiable")))
        if isinstance(result.get("document_summary"), dict):
            summaries.append(result["document_summary"])

    requirements = base.renumber(
        base.dedupe(requirements, ("source_document", "source_location", "requirement")),
        "REQ",
    )
    commitments = base.renumber(
        base.dedupe(commitments, ("source_document", "source_location", "commitment")),
        "COM",
    )
    if not requirements:
        raise HTTPException(status_code=422, detail="Nenhum requisito do cliente foi extraído")
    if not commitments:
        raise HTTPException(status_code=422, detail="Nenhum compromisso STEP foi extraído")

    result = {
        "requirements": requirements,
        "commitments": commitments,
        "not_verifiable": base.dedupe(unverifiable, ("source_document", "topic", "reason")),
        "document_summary": base.dedupe(summaries, ("source_document", "summary")),
        "drawing_analysis": list(drawing_analysis),
        "batch_info": {
            "processed_chunks": len(jobs),
            "max_chunks_per_document": MAX_CHUNKS_PER_DOCUMENT,
            "max_total_chunks": MAX_TOTAL_CHUNKS,
            "concurrency": AI_CONCURRENCY,
            "model": os.getenv("LLM_MODEL", ""),
            "drawings_analyzed": len(drawing_analysis),
            "drawings_deferred": max(0, len(drawing_entries) - len(drawing_analysis)),
        },
    }
    print(
        f"[audit-v2] extração finalizada: {len(requirements)} requisitos, "
        f"{len(commitments)} compromissos e {len(jobs)} blocos",
        flush=True,
    )
    return {"response": json.dumps(result, ensure_ascii=False)}


def _fallback_audit(batch: list[dict[str, Any]], reason: str) -> dict[str, Any]:
    return {
        "requirement_assessments": [
            {
                "requirement_id": _clean(item.get("id")),
                "status": "not_verifiable",
                "matched_commitment_ids": [],
                "assessment_reason": f"Lote preservado para revisão humana: {reason}",
            }
            for item in batch
            if _clean(item.get("id"))
        ],
        "findings": [],
        "corrections": [],
    }


async def _safe_audit(
    opportunity: dict[str, Any],
    batch: list[dict[str, Any]],
    commitments: list[dict[str, Any]],
    index: int,
    total: int,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    started = time.monotonic()
    async with semaphore:
        print(f"[audit-v2] comparação iniciada: lote {index}/{total}", flush=True)
        try:
            result = await asyncio.wait_for(
                base.audit_piece(opportunity, batch, commitments, index, total),
                timeout=AUDIT_BATCH_TIMEOUT_SECONDS,
            )
            print(
                f"[audit-v2] comparação concluída: lote {index}/{total} "
                f"em {time.monotonic() - started:.1f}s",
                flush=True,
            )
            return result
        except Exception as exc:  # noqa: BLE001
            reason = f"{type(exc).__name__}: {exc}"
            print(f"[audit-v2] comparação em contingência: lote {index}/{total}: {reason}", file=sys.stderr, flush=True)
            return _fallback_audit(batch, reason)


async def _safe_proposal(
    opportunity: dict[str, Any],
    findings: list[dict[str, Any]],
    corrections: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        return await asyncio.wait_for(
            base.proposal(opportunity, findings, corrections),
            timeout=PROPOSAL_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "corrected_proposal": {
                "title": "Proposta Técnico-Comercial Revisada",
                "introduction": "Versão de contingência para revisão humana.",
                "sections": [
                    {
                        "title": "Correções requeridas",
                        "paragraphs": [],
                        "bullets": [
                            _clean(item.get("corrected_text"))
                            for item in corrections
                            if _clean(item.get("corrected_text"))
                        ],
                    }
                ],
                "exclusions": [
                    "Nenhum preço, prazo ou obrigação foi alterado sem evidência.",
                    f"Redação automática parcial: {type(exc).__name__}.",
                ],
            },
            "assumptions": ["Documento de contingência; exige revisão humana antes da submissão."],
        }


@app.post("/v1/ai/audit-v2", dependencies=[Depends(auth)])
async def bounded_audit(request: Request) -> dict[str, Any]:
    body = await request.json()
    opportunity, extraction = body.get("opportunity"), body.get("extraction")
    if not isinstance(opportunity, dict) or not isinstance(extraction, dict):
        raise HTTPException(status_code=422, detail="opportunity e extraction são obrigatórias")
    reqs = base.objects(extraction.get("requirements"))
    commitments = base.objects(extraction.get("commitments"))
    if not reqs or not commitments:
        raise HTTPException(status_code=422, detail="Extração sem requisitos ou compromissos")

    batches = base.requirement_batches(reqs)
    selected_batches = batches[:MAX_AUDIT_BATCHES]
    semaphore = asyncio.Semaphore(AI_CONCURRENCY)
    results = await asyncio.gather(
        *[
            _safe_audit(
                opportunity,
                batch,
                base.related_commitments(batch, commitments),
                index,
                len(selected_batches),
                semaphore,
            )
            for index, batch in enumerate(selected_batches, 1)
        ]
    )

    assessments: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    corrections: list[dict[str, Any]] = []
    for result in results:
        assessments.extend(base.objects(result.get("requirement_assessments")))
        findings.extend(base.objects(result.get("findings")))
        corrections.extend(base.objects(result.get("corrections")))

    if len(batches) > len(selected_batches):
        for batch in batches[len(selected_batches):]:
            assessments.extend(
                _fallback_audit(batch, "limite operacional de lotes atingido")["requirement_assessments"]
            )

    visual_findings, visual_corrections, visual_unverifiable = base.drawing_findings(
        base.objects(extraction.get("drawing_analysis"))
    )
    findings.extend(visual_findings)
    corrections.extend(visual_corrections)

    assessments = base.dedupe(assessments, ("requirement_id",))
    assessment_map = {_clean(item.get("requirement_id")): item for item in assessments}
    normalized = [
        {
            **requirement,
            "status": (assessment_map.get(_clean(requirement.get("id"))) or {}).get("status", "not_verifiable"),
            "matched_commitment_ids": (assessment_map.get(_clean(requirement.get("id"))) or {}).get("matched_commitment_ids", []),
            "assessment_reason": (assessment_map.get(_clean(requirement.get("id"))) or {}).get("assessment_reason", ""),
        }
        for requirement in reqs
    ]
    findings = base.renumber(
        base.dedupe(
            findings,
            ("title", "inconsistency", "required_correction", "source_document", "source_location"),
        ),
        "F",
    )
    corrections = base.renumber(
        base.dedupe(corrections, ("section", "corrected_text", "reason", "source_document")),
        "C",
    )
    combined_unverifiable = base.dedupe(
        base.objects(extraction.get("not_verifiable")) + visual_unverifiable,
        ("source_document", "source_location", "topic", "reason"),
    )
    draft = await _safe_proposal(opportunity, findings, corrections)
    final = {
        "summary": base.summary(normalized, findings),
        "requirements": normalized,
        "commitments": commitments,
        "findings": findings,
        "corrections": corrections,
        "corrected_proposal": draft.get("corrected_proposal") or {},
        "assumptions": draft.get("assumptions") or [],
        "not_verifiable": combined_unverifiable,
        "drawing_analysis": extraction.get("drawing_analysis") or [],
        "batch_info": {
            "audit_batches": len(selected_batches),
            "deferred_audit_batches": max(0, len(batches) - len(selected_batches)),
            "concurrency": AI_CONCURRENCY,
            "extraction": extraction.get("batch_info") or {},
            "model": os.getenv("LLM_MODEL", ""),
            "drawing_findings": len(visual_findings),
            "drawing_not_verifiable": len(visual_unverifiable),
        },
    }
    print(
        f"[audit-v2] auditoria finalizada: {len(normalized)} requisitos, "
        f"{len(findings)} achados e {len(selected_batches)} lotes",
        flush=True,
    )
    return {"response": json.dumps(final, ensure_ascii=False)}

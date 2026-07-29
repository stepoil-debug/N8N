from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from typing import Any

import httpx

from . import ai_batch_service as base

_MIN_INTERVAL = float(os.getenv("LLM_MIN_INTERVAL_SECONDS", "3"))
_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))
_MAX_DOC_CHARS = int(os.getenv("LLM_MAX_DOCUMENT_CHARS", "30000"))
_lock = asyncio.Lock()
_last_call = 0.0


def _clean(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def _chunks(text: str, limit: int = 10000) -> list[str]:
    text = _clean(text)
    if len(text) > _MAX_DOC_CHARS:
        omitted = len(text) - _MAX_DOC_CHARS
        text = (
            text[:_MAX_DOC_CHARS]
            + f"\n\n[CONTEÚDO ADICIONAL NÃO ENVIADO AO MODELO: {omitted} caracteres. "
            "Marcar este excedente como não verificável e exigir revisão humana.]"
        )
    result: list[str] = []
    cursor = 0
    while cursor < len(text):
        end = min(cursor + limit, len(text))
        if end < len(text):
            cut = max(
                text.rfind("\n\n", cursor, end),
                text.rfind("\n", cursor, end),
                text.rfind(". ", cursor, end),
            )
            if cut > cursor + limit // 2:
                end = cut + 1
        piece = text[cursor:end].strip()
        if piece:
            result.append(piece)
        cursor = max(end, cursor + 1)
    return result


def _json_from_content(value: Any) -> dict[str, Any]:
    text = _clean(value)
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("resposta sem objeto JSON")
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("resposta JSON não é objeto")
    return data


def _fallback(user: str, reason: str) -> dict[str, Any]:
    if "requirement_assessments" in user:
        ids = list(dict.fromkeys(re.findall(r'"id"\s*:\s*"(REQ-[^"]+)"', user)))
        return {
            "requirement_assessments": [
                {
                    "requirement_id": item,
                    "status": "not_verifiable",
                    "matched_commitment_ids": [],
                    "assessment_reason": f"Lote preservado para revisão humana: {reason}",
                }
                for item in ids
            ],
            "findings": [],
            "corrections": [],
        }

    if "corrected_proposal" in user and "DADOS" in user:
        return {
            "corrected_proposal": {
                "title": "Proposta Técnico-Comercial Revisada",
                "introduction": "Versão de contingência para revisão humana.",
                "sections": [
                    {
                        "title": "Validações pendentes",
                        "paragraphs": [
                            "A análise automática encontrou indisponibilidade temporária em parte do processamento."
                        ],
                        "bullets": ["Confirmar manualmente os pontos marcados como não verificáveis."],
                    }
                ],
                "exclusions": ["Nenhum preço, prazo ou obrigação foi alterado sem evidência."],
            },
            "assumptions": ["Documento de contingência; exige revisão humana antes da submissão."],
        }

    path_match = re.search(r"Documento:\s*(.+)", user)
    owner_match = re.search(r"Origem:\s*(\w+)", user)
    path = _clean(path_match.group(1) if path_match else "documento")
    owner = _clean(owner_match.group(1) if owner_match else "unknown").casefold()
    evidence_match = re.search(r"TEXTO\s*(.*?)(?:\n\nExtraia|$)", user, flags=re.S)
    evidence = _clean(evidence_match.group(1) if evidence_match else "")[:600]
    requirements: list[dict[str, Any]] = []
    commitments: list[dict[str, Any]] = []
    common = {
        "category": "other",
        "source_document": path,
        "source_location": "bloco com processamento parcial",
        "source_evidence": evidence,
    }
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
                "topic": "Lote dependente de revisão manual",
                "reason": reason,
                "source_document": path,
            }
        ],
        "document_summary": {
            "source_document": path,
            "role": owner if owner in {"client", "step"} else "unknown",
            "summary": "Conteúdo preservado; o modelo não concluiu este lote.",
        },
    }


async def _wait() -> None:
    global _last_call
    async with _lock:
        elapsed = time.monotonic() - _last_call
        if elapsed < _MIN_INTERVAL:
            await asyncio.sleep(_MIN_INTERVAL - elapsed)
        _last_call = time.monotonic()


async def resilient_model(system: str, user: str, max_tokens: int = 2200) -> dict[str, Any]:
    key = os.getenv("LLM_API_KEY", "").strip()
    if not key:
        return _fallback(user, "LLM_API_KEY não configurada")

    payload = {
        "model": os.getenv("LLM_MODEL", "openai/gpt-4.1-mini"),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "temperature": 0.1,
        "max_tokens": min(max_tokens, 2400),
    }
    headers = {
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
        "X-GitHub-Api-Version": os.getenv("GITHUB_MODELS_API_VERSION", "2026-03-10"),
    }
    url = os.getenv("LLM_BASE_URL", "https://models.github.ai/inference/chat/completions")
    last_error = "GitHub Models indisponível"

    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=20.0)) as client:
        for attempt in range(1, _MAX_RETRIES + 1):
            await _wait()
            try:
                response = await client.post(url, json=payload, headers=headers)
                if response.is_error:
                    last_error = f"HTTP {response.status_code}: {response.text[:1200]}"
                    print(
                        f"[step-audit-ai] tentativa {attempt}/{_MAX_RETRIES}: {last_error}",
                        file=sys.stderr,
                        flush=True,
                    )
                    if response.status_code in {408, 409, 429, 500, 502, 503, 504} and attempt < _MAX_RETRIES:
                        retry_after = response.headers.get("retry-after")
                        try:
                            delay = float(retry_after) if retry_after else min(6 * attempt, 20)
                        except ValueError:
                            delay = min(6 * attempt, 20)
                        await asyncio.sleep(max(delay, _MIN_INTERVAL))
                        continue
                    break
                data = response.json()
                return _json_from_content(data["choices"][0]["message"]["content"])
            except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                print(
                    f"[step-audit-ai] tentativa {attempt}/{_MAX_RETRIES}: {last_error}",
                    file=sys.stderr,
                    flush=True,
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(min(5 * attempt, 15))
                    continue

    print(
        f"[step-audit-ai] lote concluído em contingência: {last_error}",
        file=sys.stderr,
        flush=True,
    )
    return _fallback(user, last_error)


def resilient_summary(
    assessments: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    original = _original_summary(assessments, findings)
    statuses = [_clean(item.get("status")) for item in assessments]
    verifiable = [status for status in statuses if status != "not_verifiable"]
    coverage = round(len(verifiable) / len(statuses) * 100, 1) if statuses else None
    original["coverage_percent"] = coverage
    if coverage is None or coverage < 100:
        original["recommendation"] = "review_before_submit"
        if original.get("risk_level") == "low":
            original["risk_level"] = "high"
        original["executive_opinion"] = (
            f"{original.get('executive_opinion', '')} "
            f"Cobertura verificável: {coverage if coverage is not None else 0}%. "
            "Itens não verificáveis exigem revisão humana."
        ).strip()
    return original


_original_summary = base.summary
base.chunks = _chunks
base.model = resilient_model
base.summary = resilient_summary

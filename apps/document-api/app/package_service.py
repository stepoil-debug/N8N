from __future__ import annotations

import io
import json
import os
import re
import unicodedata
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from fastapi import HTTPException

from .main import artifact, extract, safe, workspace

MAX_PACKAGE = int(os.getenv("MAX_PACKAGE_MB", "250")) * 1024 * 1024
MAX_ENTRIES = int(os.getenv("MAX_ZIP_ENTRIES", "2500"))
MAX_UNCOMPRESSED = int(os.getenv("MAX_ZIP_UNCOMPRESSED_MB", "1500")) * 1024 * 1024
MAX_ENTRY = int(os.getenv("MAX_ZIP_ENTRY_MB", "250")) * 1024 * 1024
IGNORED = {"thumbs.db", ".ds_store", "desktop.ini"}
SUPPORTED = {".pdf", ".xlsx", ".xlsm", ".docx", ".csv", ".txt", ".md", ".json", ".eml", ".msg"}
GROUPS = (
    (("01 - rfq", "/rfq/", "request for quotation"), "rfq", "client"),
    (("02 - clarifications", "clarification", "esclarecimento"), "clarifications", "client"),
    (("03 - material quotes", "material quote", "cotacao", "cotação"), "material_quotes", "step"),
    (("04 - estimate", "estimate", "orcament", "orçament"), "estimate", "step"),
    (("05 - proposal", "proposal", "proposta"), "proposal", "step"),
    (("06 - po", "/po/", "purchase order", "pedido de compra"), "purchase_order", "client"),
)


def fold(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    return "".join(c for c in value if not unicodedata.combining(c)).casefold()


def normalize_path(name: str) -> str:
    value = name.replace("\\", "/").lstrip("/")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise HTTPException(status_code=422, detail=f"Caminho inseguro no ZIP: {name}")
    return str(path)


def classify_group(path: str) -> tuple[str, str]:
    text = f"/{fold(path)}/"
    for terms, group, owner in GROUPS:
        if any(fold(term) in text for term in terms):
            return group, owner
    return "unclassified", "unknown"


def classify_type(path: str, group: str) -> str:
    name = fold(PurePosixPath(path).name)
    ext = PurePosixPath(path).suffix.casefold()
    if ext in {".msg", ".eml"}: return "email"
    if "lista de materiais" in name or "material list" in name or "bom" in name: return "material_list"
    if group == "proposal" or "proposta" in name or "proposal" in name: return "proposal"
    if group == "estimate" or "orcament" in name or "estimate" in name: return "estimate"
    if group == "material_quotes" or "cotacao" in name or "quotation" in name: return "material_quote"
    if group == "purchase_order": return "purchase_order"
    if ext == ".pdf" and any(token in name for token in ("sob-", "str-", "dwg", "drawing", "desenho", "croqui")): return "drawing"
    if group == "rfq": return "rfq_document"
    if group == "clarifications": return "clarification"
    if ext in {".xlsx", ".xlsm", ".csv"}: return "spreadsheet"
    if ext == ".docx": return "document"
    if ext == ".pdf": return "pdf"
    return "generic"


def infer_metadata(filename: str, root: str | None) -> dict[str, str | None]:
    text = fold(f"{Path(filename).stem} {root or ''}")
    match = re.search(r"bep\s*[-_. ]?\s*(\d{2})\s*[-_. ]\s*(\d{3})", text)
    if not match: match = re.search(r"(\d{2})\s*[-_. ]\s*(\d{3})\s*bep", text)
    opportunity = f"BEP-{match.group(1)}-{match.group(2)}" if match else None
    rfq_match = re.search(r"wp-[a-z0-9]+-\d{4}-\d{3}", text)
    rfq = rfq_match.group(0).upper() if rfq_match else None
    client = None
    client_match = re.search(r"bep(?:\s*[-_. ]?\s*\d{2}\s*[-_. ]\s*\d{3})?\s+([a-z0-9&]+)", text)
    if client_match and client_match.group(1) not in {"enc", "rev"}: client = client_match.group(1).upper()
    if not client and "perenco" in text: client = "PERENCO"
    return {"opportunity_id": opportunity, "client": client, "rfq_id": rfq}


def preview(extracted: dict[str, Any]) -> dict[str, Any]:
    content = extracted.get("content") or []
    text = ""
    if extracted.get("kind") == "pdf": text = "\n".join(str(p.get("text", "")) for p in content[:2])
    elif extracted.get("kind") == "email" and content: text = f"{content[0].get('subject', '')}\n{content[0].get('body', '')}"
    elif extracted.get("kind") == "document" and content: text = "\n".join(content[0].get("paragraphs", [])[:20])
    elif extracted.get("kind") == "spreadsheet" and content:
        text = "\n".join(" | ".join(map(str, row)) for sheet in content[:2] for row in (sheet.get("rows") or [])[:8])
    return {"kind": extracted.get("kind"), "extension": extracted.get("extension"), "warnings": extracted.get("warnings") or [], "preview": text[:1600]}


def analyze_package(filename: str, data: bytes, opportunity_id: str | None = None, *, include_content: bool = True) -> dict[str, Any]:
    if len(data) > MAX_PACKAGE: raise HTTPException(status_code=413, detail="ZIP acima do limite configurado")
    if not zipfile.is_zipfile(io.BytesIO(data)): raise HTTPException(status_code=415, detail="O arquivo enviado não é um ZIP válido")
    entries: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []
    folders: set[str] = set()
    roots: list[str] = []
    proposal_sources: list[tuple[int, str, bytes]] = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_ENTRIES: raise HTTPException(status_code=413, detail="ZIP contém entradas demais")
        if sum(item.file_size for item in infos) > MAX_UNCOMPRESSED: raise HTTPException(status_code=413, detail="Conteúdo descompactado excede o limite")
        for info in infos:
            path = normalize_path(info.filename)
            roots.append(PurePosixPath(path).parts[0])
            if info.is_dir(): folders.add(path.rstrip("/")); continue
            if info.file_size > MAX_ENTRY: raise HTTPException(status_code=413, detail=f"Arquivo interno excede o limite: {path}")
            if info.compress_size and info.file_size > 10 * 1024 * 1024 and info.file_size / info.compress_size > 200:
                raise HTTPException(status_code=413, detail=f"Taxa de compressão suspeita: {path}")
            name = PurePosixPath(path).name
            ext = PurePosixPath(path).suffix.casefold()
            if name.casefold() in IGNORED or name.startswith("~$"):
                ignored.append({"path": path, "reason": "system_file", "size_bytes": info.file_size}); continue
            group, owner = classify_group(path)
            item: dict[str, Any] = {"path": path, "filename": name, "extension": ext, "size_bytes": info.file_size, "group": group, "source_owner": owner, "document_type": classify_type(path, group), "evidence_reference": path, "extraction_status": "not_supported", "warnings": []}
            raw: bytes | None = None
            if ext in SUPPORTED:
                try:
                    raw = archive.read(info)
                    extracted = extract(name, raw)
                    item["extraction_status"] = "extracted"
                    item["warnings"] = extracted.get("warnings") or []
                    item["extracted"] = extracted if include_content else preview(extracted)
                except Exception as exc:
                    item["extraction_status"] = "error"; item["warnings"] = [str(exc)]
            entries.append(item)
            if group == "proposal" and ext == ".docx" and raw is not None:
                proposal_sources.append((len(entries) - 1, name, raw))
    root = roots[0] if roots and len(set(roots)) == 1 else None
    inferred = infer_metadata(filename, root)
    resolved = opportunity_id or inferred.get("opportunity_id") or safe(Path(filename).stem, "opportunity")
    for entry_index, source_name, source_bytes in proposal_sources:
        source_path = workspace(str(resolved)) / safe(f"Proposta_Original_{source_name}")
        source_path.write_bytes(source_bytes)
        entries[entry_index]["source_artifact"] = artifact(str(resolved), source_path)
    summary = {"total_files": len(entries), "total_folders": len(folders), "ignored_files": len(ignored), "groups": dict(Counter(x["group"] for x in entries)), "source_owners": dict(Counter(x["source_owner"] for x in entries)), "document_types": dict(Counter(x["document_type"] for x in entries)), "extraction": dict(Counter(x["extraction_status"] for x in entries))}
    result: dict[str, Any] = {"status": "classified", "package_name": Path(filename).name, "package_size_bytes": len(data), "root_folder": root, "opportunity_id": resolved, "inferred": inferred, "summary": summary, "folders": sorted(folders), "entries": entries, "ignored": ignored, "classified_at": datetime.now(UTC).isoformat()}
    output = workspace(str(resolved)) / "package_manifest.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["manifest_artifact"] = artifact(str(resolved), output)
    return result

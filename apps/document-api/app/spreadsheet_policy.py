from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any, Callable

from . import main, package_service

_ORIGINAL_EXTRACT: Callable[[str, bytes], dict[str, Any]] = main.extract
_FABRICATION_ROUTE = re.compile(r"(?:^|\b)roteiro\s+de\s+fabricacao(?:\b|$)")


def _fold(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold().strip()


def is_fabrication_route_sheet(title: Any) -> bool:
    """Reconhece variações como ROTEIRO DE FABRICAÇÃO, Roteiro de Fabricacao 1 etc."""
    return bool(_FABRICATION_ROUTE.search(_fold(title)))


def _has_meaningful_rows(sheet: dict[str, Any]) -> bool:
    for row in sheet.get("rows") or []:
        if any(str(value or "").strip() for value in row):
            return True
    return False


def apply_spreadsheet_policy(extracted: dict[str, Any]) -> dict[str, Any]:
    """Remove apenas roteiros de fabricação vazios, sem gerar warnings ou pendências."""
    if extracted.get("kind") != "spreadsheet":
        return extracted

    kept: list[dict[str, Any]] = []
    intentionally_blank: list[dict[str, str]] = []
    for sheet in extracted.get("content") or []:
        if not isinstance(sheet, dict):
            kept.append(sheet)
            continue
        title = str(sheet.get("sheet") or "")
        if is_fabrication_route_sheet(title) and not _has_meaningful_rows(sheet):
            intentionally_blank.append(
                {
                    "sheet": title,
                    "reason": "intentional_blank_fabrication_route",
                    "treatment": "ignored_without_notification",
                }
            )
            continue
        kept.append(sheet)

    extracted["content"] = kept
    if intentionally_blank:
        extracted.setdefault("ignored_sheets", []).extend(intentionally_blank)
        extracted["spreadsheet_policy"] = {
            "intentional_blank_sheets": len(intentionally_blank),
            "notification_generated": False,
        }
    return extracted


def extract_with_spreadsheet_policy(filename: str, data: bytes) -> dict[str, Any]:
    extracted = _ORIGINAL_EXTRACT(filename, data)
    if Path(filename).suffix.casefold() in {".xlsx", ".xlsm"}:
        return apply_spreadsheet_policy(extracted)
    return extracted


# O package_service importou extract diretamente de main. Atualizamos as duas
# referências para que uploads unitários e ZIPs usem a mesma política.
main.extract = extract_with_spreadsheet_policy
package_service.extract = extract_with_spreadsheet_policy

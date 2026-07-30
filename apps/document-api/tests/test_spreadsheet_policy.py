from __future__ import annotations

import io
import os
import sys
from pathlib import Path

from openpyxl import Workbook

os.environ["ARTIFACT_ROOT"] = "/tmp/step-industrial-audit-spreadsheet-tests"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main
from app.spreadsheet_policy import is_fabrication_route_sheet


def workbook_bytes(*, route_value: str | None = None) -> bytes:
    workbook = Workbook()
    route = workbook.active
    route.title = "ROTEIRO DE FABRICAÇÃO"
    if route_value is not None:
        route["A1"] = route_value
    data = workbook.create_sheet("Dados")
    data.append(["Item", "Quantidade"])
    data.append(["Tubo", 2])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_empty_fabrication_route_is_ignored_without_warning() -> None:
    extracted = main.extract("estimativa.xlsx", workbook_bytes())

    assert [sheet["sheet"] for sheet in extracted["content"]] == ["Dados"]
    assert extracted["warnings"] == []
    assert extracted["ignored_sheets"] == [
        {
            "sheet": "ROTEIRO DE FABRICAÇÃO",
            "reason": "intentional_blank_fabrication_route",
            "treatment": "ignored_without_notification",
        }
    ]
    assert extracted["spreadsheet_policy"]["notification_generated"] is False


def test_nonempty_fabrication_route_remains_available_for_analysis() -> None:
    extracted = main.extract("estimativa.xlsm", workbook_bytes(route_value="OP-001"))

    assert [sheet["sheet"] for sheet in extracted["content"]] == [
        "ROTEIRO DE FABRICAÇÃO",
        "Dados",
    ]
    assert "ignored_sheets" not in extracted


def test_title_matching_accepts_accents_and_numbered_pages() -> None:
    assert is_fabrication_route_sheet("ROTEIRO DE FABRICAÇÃO")
    assert is_fabrication_route_sheet("Roteiro de Fabricacao 02")
    assert not is_fabrication_route_sheet("Roteiro de Inspeção")

from __future__ import annotations

from app import drawing_vision
from app.isometric_extension import is_isometric_entry, overview_prompt, tile_prompt


def sample_entry() -> dict:
    return {
        "path": "01 - RFQ/WZ-V21610-01K01.pdf",
        "filename": "WZ-V21610-01K01.pdf",
        "document_type": "drawing",
        "source_owner": "client",
        "extracted": {
            "kind": "pdf",
            "content": [
                {
                    "page": 1,
                    "text": (
                        "VESSEL FRESH WATER SYSTEM ISOMETRICS BILL OF MATERIALS "
                        "LINE IDENTIFICATION CONT'D ON FWD : 20489 SB : 9141 EL : +23249"
                    ),
                }
            ],
        },
    }


def test_dense_piping_isometric_is_detected():
    assert is_isometric_entry(sample_entry()) is True


def test_generic_drawing_is_not_forced_into_isometric_mode():
    entry = {
        "path": "estrutura/plate-detail.pdf",
        "document_type": "drawing",
        "extracted": {"kind": "pdf", "content": [{"page": 1, "text": "PLATE DETAIL"}]},
    }
    assert is_isometric_entry(entry) is False


def test_overview_prompt_requires_bom_dimension_and_flange_reconciliation():
    prompt = overview_prompt(sample_entry(), {"page": 1}, drawing_vision.load_knowledge())
    assert "MODO DE AUDITORIA ISOMÉTRICA PROFUNDA" in prompt
    assert "BOM/MTO E BALÕES" in prompt
    assert "JUNTAS FLANGEADAS E PARAFUSOS" in prompt
    assert "DIMENSÕES E SPOOLS" in prompt
    assert "dimension_chains" in prompt
    assert "flange_joint_sets" in prompt


def test_tile_prompt_assigns_bom_focus_to_top_right():
    prompt = tile_prompt(
        sample_entry(),
        {"page": 1},
        "top_right",
        {"drawing_class": "piping_isometric", "issues": []},
        drawing_vision.load_knowledge(),
    )
    assert "BOM/MTO" in prompt
    assert "flanges" in prompt
    assert "stud bolts" in prompt

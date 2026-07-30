import io
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw

os.environ["ARTIFACT_ROOT"] = "/tmp/step-industrial-audit-drawing-tests"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.drawing_vision import drawing_findings, load_knowledge, prepare_drawing_visuals


def sample_drawing() -> bytes:
    image = Image.new("RGB", (1800, 1200), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((80, 80, 1720, 1120), outline="black", width=5)
    draw.rectangle((1180, 900, 1720, 1120), outline="black", width=3)
    draw.line((300, 300, 900, 300), fill="black", width=8)
    draw.line((600, 150, 600, 600), fill="black", width=8)
    for x in (1100, 1250, 1400, 1550):
        draw.ellipse((x - 24, 360, x + 24, 408), outline="black", width=5)
    draw.text((1210, 930), "TEST DRAWING REV A", fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_knowledge_has_weld_bolting_and_spool_rules():
    knowledge = load_knowledge()
    assert any(item["id"] == "W01" for item in knowledge["weld_checks"])
    assert any(item["id"] == "B02" for item in knowledge["bolting_checks"])
    assert any(item["id"] == "P08" for item in knowledge["piping_checks"])
    assert knowledge["governance"]["default_decision"] == "not_verifiable"
    convention = knowledge["spool_counting_convention"]
    assert "flange connection at each end" in convention["definition"]
    assert "field weld" in convention["not_boundaries_by_themselves"]
    assert "spools" in knowledge["vision_output_schema"]


def test_prepare_visual_assets_from_image():
    result = prepare_drawing_visuals("assembly-drawing.png", sample_drawing(), "TEST-DRAWING")
    assert result["status"] == "prepared"
    assert len(result["pages"]) == 1
    page = result["pages"][0]
    assert Path(page["overview_path"]).is_file()
    assert set(page["tile_paths"]) == {"top_left", "top_right", "bottom_left", "bottom_right"}
    assert all(Path(path).is_file() for path in page["tile_paths"].values())


def test_visual_findings_require_confidence_and_contradiction_for_blocking():
    analyses = [
        {
            "issues": [
                {
                    "rule_id": "B02",
                    "title": "Quantidade de parafusos diverge do padrão de furos",
                    "evidence": "8 furos no detalhe e BOM com 4 parafusos",
                    "contradiction": "Padrão de 8 furos versus quantidade 4 no BOM",
                    "required_correction": "Corrigir a quantidade ou esclarecer uso por conjunto.",
                    "severity": "high",
                    "blocking": True,
                    "confidence": 0.94,
                    "requires_human_review": True,
                    "source_document": "05 - Proposal/assembly.pdf",
                    "source_owner": "step",
                    "page": 1,
                    "region": "bottom_right",
                    "status": "candidate_finding",
                },
                {
                    "rule_id": "W01",
                    "title": "Possível solda ausente",
                    "evidence": "Duas linhas se encontram",
                    "contradiction": "",
                    "required_correction": "Confirmar a intenção da união.",
                    "severity": "high",
                    "blocking": True,
                    "confidence": 0.42,
                    "requires_human_review": True,
                    "source_document": "01 - RFQ/detail.pdf",
                    "source_owner": "client",
                    "page": 2,
                    "region": "overview",
                    "status": "not_verifiable",
                },
            ]
        }
    ]
    findings, corrections, unverifiable = drawing_findings(analyses)
    assert len(findings) == 1
    assert findings[0]["blocking"] is True
    assert findings[0]["drawing_rule_id"] == "B02"
    assert len(corrections) == 1
    assert len(unverifiable) == 1
    assert unverifiable[0]["topic"] == "Possível solda ausente"

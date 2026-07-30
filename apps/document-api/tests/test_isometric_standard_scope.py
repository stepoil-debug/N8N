from app import drawing_vision
from app.isometric_extension import overview_prompt


def test_isometric_prompt_checks_material_against_standard_scope():
    entry = {
        "path": "RFQ/fresh-water-isometric.pdf",
        "document_type": "drawing",
        "source_owner": "client",
        "extracted": {
            "kind": "pdf",
            "content": [{"page": 1, "text": "ISOMETRICS BILL OF MATERIALS LINE IDENTIFICATION CONT'D ON FWD : 1 SB : 2 EL : 3"}],
        },
    }
    prompt = overview_prompt(entry, {"page": 1}, drawing_vision.load_knowledge())
    assert "escopo material da norma citada" in prompt
    assert "restrita a aço" in prompt
    assert "Referências retiradas/substituídas" in prompt

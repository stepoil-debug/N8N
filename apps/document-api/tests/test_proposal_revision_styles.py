from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["ARTIFACT_ROOT"] = "/tmp/step-industrial-audit-proposal-style-tests"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.proposal_revision import _bullet_paragraph


class FakeParagraph:
    def __init__(self) -> None:
        self.runs: list[str] = []
        self.paragraph_format = type("Format", (), {"left_indent": object()})()

    def add_run(self, text: str):
        self.runs.append(text)
        return type("Run", (), {"bold": False})()


class CustomStyleDocument:
    def __init__(self) -> None:
        self.calls: list[str | None] = []
        self.paragraph = FakeParagraph()

    def add_paragraph(self, style=None):
        self.calls.append(style)
        if style == "List Bullet":
            raise KeyError("no style with name 'List Bullet'")
        return self.paragraph


def test_bullet_falls_back_when_source_template_has_no_builtin_style() -> None:
    document = CustomStyleDocument()
    paragraph = _bullet_paragraph(document)
    assert paragraph is document.paragraph
    assert document.calls == ["List Bullet", None]
    assert paragraph.runs == ["• "]
    assert paragraph.paragraph_format.left_indent is None

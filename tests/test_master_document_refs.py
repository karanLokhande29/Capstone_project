"""Master Document §15 References: the bib -> Markdown conversion leaves no LaTeX behind (Command Center Part A, A1)."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("build_master_document_under_test", ROOT / "scripts" / "build_master_document.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_every_bib_entry_converts_cleanly(mod):
    lines = mod.refs_md().splitlines()
    assert len(lines) == len(mod.bib_fields()) == 20
    for line in lines:
        body = line.split("] ", 1)[1]
        assert "\\" not in body, line
        assert "{" not in body and "}" not in body, line
        assert not re.search(r"(?<![\w/])url(?=https?:)", body), line
        assert "`" not in body and '"' not in body, line


def test_known_accents_and_urls(mod):
    text = mod.refs_md()
    assert "Xing Han Lù" in text
    assert "Stefan Büttcher" in text
    assert "https://github.com/RegNLP/RePASs." in text
    assert "gpt-oss-120b & gpt-oss-20b" in text


@pytest.mark.parametrize("tex, plain", [
    ("L{\\`u}", "Lù"), ("B{\\\"u}ttcher", "Büttcher"), ("\\'{e}t\\'e", "été"), ("\\c{c}a", "ça"), ("\\v{s}", "š"),
    ("\\url{https://x.org/a_b}", "https://x.org/a_b"), ("\\href{https://x.org}{X}", "X (https://x.org)"),
    ("{{RIRAG}}: A \\& B", "RIRAG: A & B"), ("pp. 1--4", "pp. 1–4"),
])
def test_tex_to_text(mod, tex, plain):
    assert mod.tex_to_text(tex) == plain

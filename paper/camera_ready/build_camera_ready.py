"""Build the AISIGH-SD 2026 camera-ready PDF (Paper ID 1954) from the accepted PDF, without re-typesetting it.

Additions only; every original line stays where it was and the paper stays at 6 pages:
  1. Page 1: the IEEE copyright notice at the bottom-left of the footer (camera-ready guideline).
  2. Page 6: a citation "[33]" at the end of the Conclusion's data/code sentence, written into the original
     content stream with the paper's own embedded font (NimbusRomNo9L-Regu, all glyphs present in the subset).
  3. Page 6: reference [33] (public code and pointer-only data release) in the free space under [32], set to the
     reference list's measured geometry (8 pt, 8.966 pt leading, label x 311.98, text x 330.237-563.04).
     Times New Roman is embedded for it because the paper's font subset has no underscore glyph for the URL.

Run: .venv/bin/python paper/camera_ready/build_camera_ready.py
"""

from __future__ import annotations

import io
from pathlib import Path

import pypdf
from pypdf.generic import ContentStream, NameObject
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
SRC = HERE / "RBI-ObliBench_accepted_original.pdf"
OUT = HERE / "RBI-ObliBench_AISIGH-SD2026_1954_camera_ready.pdf"
TNR = "/System/Library/Fonts/Supplemental/Times New Roman.ttf"

COPYRIGHT = "979-8-3315-7088-0/26/$31.00 ©2026 IEEE"
REPO = "https://github.com/karanLokhande29/Capstone_project"
REF33 = ("M. D. Magia, K. M. Lokhande, A. Goyal, J. E. Joy, and H. D. Vankayalapati, "
         "“RBI-ObliBench: Code and pointer-only data release,” " + REPO + ", 2026.")

# Reference-list geometry measured from the accepted PDF (page 6, right column).
REF_SIZE, REF_LEAD = 7.9701, 8.966
LABEL_X, TEXT_X, RIGHT_X = 311.98, 330.237, 563.04
REF32_LAST_BASELINE = 114.41
LOWEST_BASELINE = 75.0  # left column's last baseline is ~75.5; stay above the bottom margin

pdfmetrics.registerFont(TTFont("TimesNR", TNR))


def overlay(draw) -> pypdf.PageObject:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792), initialFontName="TimesNR", initialFontSize=8)
    draw(c)
    c.save()
    return pypdf.PdfReader(io.BytesIO(buf.getvalue())).pages[0]


def draw_copyright(c: canvas.Canvas) -> None:
    c.setFont("TimesNR", 8)
    c.drawString(48.96, 50, COPYRIGHT)


def justified_lines(text: str, width: float) -> list[list[str]]:
    space = pdfmetrics.stringWidth(" ", "TimesNR", REF_SIZE)
    lines, cur = [], []
    for word in text.split():
        trial = cur + [word]
        w = sum(pdfmetrics.stringWidth(x, "TimesNR", REF_SIZE) for x in trial) + space * (len(trial) - 1)
        if cur and w > width:
            lines.append(cur)
            cur = [word]
        else:
            cur = trial
    lines.append(cur)
    return lines


def draw_ref33(c: canvas.Canvas) -> None:
    c.setFont("TimesNR", REF_SIZE)
    width = RIGHT_X - TEXT_X
    lines = justified_lines(REF33, width)
    y = REF32_LAST_BASELINE - REF_LEAD
    assert y - REF_LEAD * (len(lines) - 1) >= LOWEST_BASELINE, "reference [33] would run past the column"
    c.drawString(LABEL_X, y, "[33]")
    space = pdfmetrics.stringWidth(" ", "TimesNR", REF_SIZE)
    for i, words in enumerate(lines):
        widths = [pdfmetrics.stringWidth(w, "TimesNR", REF_SIZE) for w in words]
        last = i == len(lines) - 1
        gap = space if last or len(words) == 1 else (width - sum(widths)) / (len(words) - 1)
        x = TEXT_X
        for w, wd in zip(words, widths):
            c.drawString(x, y, w)
            x += wd + gap
        y -= REF_LEAD


def main() -> None:
    reader = pypdf.PdfReader(SRC)
    w = pypdf.PdfWriter(clone_from=reader)
    w.pdf_header = "%PDF-1.5"
    w.pages[0].merge_page(overlay(draw_copyright))
    p6 = w.pages[5]
    data = p6.get_contents().get_data()
    old, new = b"(accepted.)]TJ", b"(accepted)-350([33].)]TJ"
    assert data.count(old) == 1, "Conclusion sentence not found exactly once"
    cs = ContentStream(None, w)
    cs.set_data(data.replace(old, new))
    p6.replace_contents(cs)
    p6.merge_page(overlay(draw_ref33))
    w.add_metadata({
        "/Title": "Same Subject, Different Duties: RBI-ObliBench for Differential Obligations across Entity "
                  "Classes in RBI Master Directions",
        "/Author": "Meer Darshit Magia; Karan Madhukar Lokhande; Akash Goyal; Jish Elizabeth Joy; "
                   "Hima Deepthi Vankayalapati",
        "/Subject": "IEEE AISIGH-SD 2026, Paper ID 1954",
        "/Keywords": "regulatory NLP, legal NLP, benchmark, retrieval-augmented generation, differential "
                     "obligations, faithfulness metrics",
    })
    with OUT.open("wb") as f:
        w.write(f)
    print(f"wrote {OUT} ({len(w.pages)} pages)")


if __name__ == "__main__":
    main()

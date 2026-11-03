"""UI demo test checklist (Word, landscape): one row per step with input, expected result and a pass/fail box.
Reuses the steps of build_ui_demo_script.py so both documents always match.

    python3 docs/presentation/build_ui_test_checklist.py
"""
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.shared import Cm, Pt, RGBColor

import build_ui_demo_script as S

HERE = Path(__file__).parent
MAROON, GREY = RGBColor(0x62, 0x24, 0x23), RGBColor(0x59, 0x59, 0x59)

doc = Document()
sec = doc.sections[0]
sec.orientation = WD_ORIENT.LANDSCAPE
sec.page_width, sec.page_height = sec.page_height, sec.page_width
for m in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
    setattr(sec, m, Cm(1.3))
doc.styles["Normal"].font.name = "Calibri"
doc.styles["Normal"].font.size = Pt(9.5)


def para(text, size=10, color=None, bold=False, after=3):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(after)
    r = p.add_run(text)
    r.font.size, r.bold = Pt(size), bold
    if color:
        r.font.color.rgb = color
    return p


para("RBI-ObliBench · UI demo test checklist", 18, MAROON, True, 2)
para(f"Site: {S.SITE}   ·   ★ = 4-minute exam path   ·   Tester: ____________   Date: ____________   Browser: ____________", 9.5, GREY, after=6)
para("Pre-flight (tick before you start)", 12, MAROON, True)
pre = ["Opened /auditgen at least 10 min before; green badge “live · hosted service” visible",
       "/auditgen/ai shows “assistant ready · gemini-3.5-flash-lite”",
       "Demo pack “Shubh Small Finance Bank” already generated and listed as “(yours)”",
       "Browser zoom 110–125%; tabs open: Home · Governance case · /auditgen",
       "Rehearsal used no more than ~11 AI answers today (site limit 30 / day)",
       "Backup ready: sample packs (no server needed) and local version (localhost:5181)"]
for p in pre:
    para("☐  " + p, 10, after=1)

for part, steps in S.PARTS:
    para(part, 12, MAROON, True, 3).paragraph_format.space_before = Pt(10)
    t = doc.add_table(rows=1, cols=6)
    t.style = "Light Grid Accent 2"
    widths = [Cm(1.2), Cm(4.0), Cm(7.6), Cm(8.4), Cm(1.4), Cm(3.4)]
    for c, h, w in zip(t.rows[0].cells, ["Step", "Page", "Do / input", "Expected result (pass if you see this)", "Pass", "Notes"], widths):
        c.text = h; c.width = w
        for r in c.paragraphs[0].runs:
            r.bold = True
    for sid, star, page, do, inp, say, proof in steps:
        cells = t.add_row().cells
        vals = [("★ " if star else "") + sid, page, f"{do} {inp}", proof, "☐", ""]
        for c, v, w in zip(cells, vals, widths):
            c.text = v; c.width = w
            for r in c.paragraphs[0].runs:
                r.font.size = Pt(9)

para("Proof points to show the panel (tick when shown)", 12, MAROON, True, 3).paragraph_format.space_before = Pt(10)
for a, b in S.PROOF:
    para(f"☐  {a}: {b}", 9.5, after=1)
para("If something fails", 12, MAROON, True, 3).paragraph_format.space_before = Pt(10)
for a, b in S.FALLBACK:
    para(f"•  {a}: {b}", 9.5, after=1)
para("Result:  ☐ all ★ steps passed     ☐ issues noted above     Signed: ____________", 10.5, MAROON, True, 2).paragraph_format.space_before = Pt(10)
doc.save(str(HERE / "RBI-ObliBench_UI_Test_Checklist.docx"))
print("saved")

"""Convert PROJECT_EXPLAINER.md to a formatted Word file (headings, lists, tables, bold / italic / code)."""
import re
from pathlib import Path
from docx import Document
from docx.shared import Cm, Pt, RGBColor

HERE = Path(__file__).parent
MAROON, GREY = RGBColor(0x62, 0x24, 0x23), RGBColor(0x59, 0x59, 0x59)
doc = Document()
for s in doc.sections:
    s.left_margin = s.right_margin = Cm(2)
    s.top_margin = s.bottom_margin = Cm(1.8)
doc.styles["Normal"].font.name = "Calibri"
doc.styles["Normal"].font.size = Pt(11)


def inline(p, text, size=None, color=None):
    for part in re.split(r"(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)", text):
        if not part:
            continue
        if part.startswith("**"):
            r = p.add_run(part[2:-2]); r.bold = True
        elif part.startswith("`"):
            r = p.add_run(part[1:-1]); r.font.name = "Menlo"; r.font.size = Pt(9.5)
        elif part.startswith("*") and len(part) > 2:
            r = p.add_run(part[1:-1]); r.italic = True
        else:
            r = p.add_run(part)
        if size and not part.startswith("`"):
            r.font.size = Pt(size)
        if color:
            r.font.color.rgb = color


lines = (HERE / "PROJECT_EXPLAINER.md").read_text(encoding="utf-8").splitlines()
i = 0
while i < len(lines):
    ln = lines[i]
    if ln.startswith("# "):
        p = doc.add_paragraph(); r = p.add_run(ln[2:]); r.bold = True; r.font.size = Pt(22); r.font.color.rgb = MAROON; r.font.name = "Times New Roman"
    elif ln.startswith("## "):
        p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(14); p.paragraph_format.keep_with_next = True
        r = p.add_run(ln[3:]); r.bold = True; r.font.size = Pt(15); r.font.color.rgb = MAROON
    elif ln.startswith("### "):
        p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(8); p.paragraph_format.keep_with_next = True
        r = p.add_run(ln[4:]); r.bold = True; r.font.size = Pt(12.5)
    elif ln.startswith("|"):
        rows = []
        while i < len(lines) and lines[i].startswith("|"):
            cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                rows.append(cells)
            i += 1
        t = doc.add_table(rows=0, cols=len(rows[0])); t.style = "Light Grid Accent 2"
        for ri, row in enumerate(rows):
            cells = t.add_row().cells
            for c, v in zip(cells, row):
                c.text = ""
                inline(c.paragraphs[0], v, size=9.5)
                if ri == 0:
                    for r in c.paragraphs[0].runs:
                        r.bold = True
        doc.add_paragraph().paragraph_format.space_after = Pt(2)
        continue
    elif re.match(r"^\d+\. ", ln):
        # Literal numbers: Word's List Number style keeps counting across sections.
        p = doc.add_paragraph(); inline(p, ln); p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.left_indent = Cm(0.6); p.paragraph_format.first_line_indent = Cm(-0.6)
    elif ln.startswith("- "):
        p = doc.add_paragraph(style="List Bullet"); inline(p, ln[2:]); p.paragraph_format.space_after = Pt(2)
    elif ln.startswith("  - "):
        p = doc.add_paragraph(style="List Bullet 2"); inline(p, ln[4:]); p.paragraph_format.space_after = Pt(2)
    elif ln.strip():
        p = doc.add_paragraph(); inline(p, ln.strip()); p.paragraph_format.space_after = Pt(5)
        if i <= 3:
            for r in p.runs:
                r.font.color.rgb = GREY; r.font.size = Pt(10)
    i += 1
doc.save(str(HERE / "RBI-ObliBench_Project_Explainer.docx"))
print("saved")

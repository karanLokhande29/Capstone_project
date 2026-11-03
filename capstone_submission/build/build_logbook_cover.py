"""First page of the capstone log book (Annexure A.7), filled from details.json.

    python build/build_logbook_cover.py        # from capstone_submission/
"""

import json
import sys
from pathlib import Path

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt

sys.path.insert(0, str(Path(__file__).parent))
from docx_kit import Report  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
D = json.loads((ROOT / "build" / "details.json").read_text())
TITLE = D["title"]
L, C = WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER
students = D["students"]

R = Report("", "")
doc = R.doc
doc.styles["Normal"].paragraph_format.line_spacing = 1.15
lp = doc.add_paragraph()
lp.alignment = C
lp.paragraph_format.space_after = Pt(4)
lp.add_run().add_picture(str(ROOT / "figures" / "nmims_logo.jpeg"), width=Inches(1.2))
R.center("**Mukesh Patel School of Technology Management & Engineering**", size=14.5, space_after=6)
R.center("**Log Book for Capstone Project**", size=14, space_after=14)
for label, value in (("Department", D["department"]), ("Program", f"{D['program']} in {D['stream']}"),
                     ("Semester", "VII"), ("TITLE OF THE PROJECT", TITLE)):
    R.p(f"**{label} :** {value}", align=L, size=13, space_after=4)
R.p(f"Name of the Faculty Mentor: **{D['mentor']}**", align=L, space_after=12)
R.center("**STUDENT DETAILS**", size=13, space_after=8)
R.table("", ["", "NAME", "ROLL NO.", "CONTACT"],
        [[f"**Student {i}**", s["name"], s["roll"], ""] for i, s in enumerate(students, 1)],
        [1.0, 2.2, 1.1, 1.5], font=11, label_prefix="-")
for row in doc.tables[-1].rows[1:]:
    row.height = Inches(0.32)
R.p("Name of group members:", align=L, space_after=4)
R.table("", ["Roll No.", "Name", "Sign (Students)", "Grades (By Faculty Mentor)"],
        [[s["roll"], s["name"], "", ""] for s in students],
        [0.9, 2.1, 1.4, 1.4], font=11, label_prefix="-")
for row in doc.tables[-1].rows[1:]:
    row.height = Inches(0.36)
for p in [p for p in doc.paragraphs if p.text.startswith("Table -")]:
    p._p.getparent().remove(p._p)
end = doc.add_paragraph()
end.paragraph_format.space_after = Pt(0)
end.add_run("").font.size = Pt(1)
out = ROOT / "output" / "Logbook_First_Page.docx"
R.save(out, update_fields_on_open=False)
print(out)

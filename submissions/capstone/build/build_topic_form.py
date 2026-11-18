"""Pre-filled topic approval form (Annexure A.2 of the capstone guidelines), for printing and signing.

    python build/build_topic_form.py        # from submissions/capstone/
"""

import json
import sys
from pathlib import Path

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt

sys.path.insert(0, str(Path(__file__).parent))
from docx_kit import Report  # noqa: E402
from references import REFS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
D = json.loads((ROOT / "build" / "details.json").read_text())
STUDENTS = D["students"]
TITLE = D["title"]
L = WD_ALIGN_PARAGRAPH.LEFT

R = Report("", "")
doc = R.doc
doc.styles["Normal"].paragraph_format.line_spacing = 1.15
lp = doc.add_paragraph()
lp.alignment = WD_ALIGN_PARAGRAPH.CENTER
lp.add_run().add_picture(str(ROOT / "figures" / "nmims_logo.jpeg"), width=Inches(1.2))
R.center("**Mukesh Patel School of Technology Management & Engineering**", size=15, space_after=2)
R.center("**Topic approval form**", size=13, space_after=10)
for label, value in (("Department", D["department"]), ("Program", D["program"]),
                     ("Semester", "VII")):
    R.p(f"**{label}:** {value}", align=L, space_after=0)
R.p("**Project Team details**", align=L, space_after=2)
R.table("", ["S No", "SAP ID", "Roll No", "Name", "Signature"],
        [[str(i), s["sap"], s["roll"], s["name"], ""] for i, s in enumerate(STUDENTS, 1)],
        [0.5, 1.1, 0.9, 1.9, 1.4], font=11, label_prefix="-")
for row in doc.tables[-1].rows[1:]:
    row.height = Inches(0.33)
R.p("**Type of Project** (Tick any one)", align=L, space_after=2)
R.table("", ["Type of project", "✓"], [["Application", ""], ["Product", ""], ["Research", "✓"]],
        [2.5, 1.0], font=11, label_prefix="-")
R.p("**Project details**", align=L, space_after=2)
R.table("", ["Item", "Details"], [
    ["Project Title", TITLE],
    ["Project Objectives", "1. Build a benchmark on all RBI Master Directions that tests entity-class applicability "
                           "and differential obligations across classes of regulated entities. 2. Build and evaluate "
                           "class- and date-aware retrieval and LLM systems on it. 3. Test whether the RePASs "
                           "faithfulness metric can be gamed on Indian regulatory text."],
    ["Domain", "Natural language processing for regulatory compliance (RegTech); information retrieval; generative AI"],
    ["Motivation", "The same obligation recurs in the Master Directions of several entity classes, sometimes with a "
                   "different threshold, deadline or scope. Compliance teams need these differences; existing "
                   "regulatory QA benchmarks do not test them."],
    ["Expected outcomes", "A released benchmark (T1-T4), an evaluated RAG pipeline, a research paper, and a "
                          "compliance tool built on the benchmark."],
], [1.6, 4.2], font=11, label_prefix="-")
R.p("**Latest References**", align=L, space_after=2).paragraph_format.page_break_before = True
R.table("", ["S No", "Publication"], [
    ["1", REFS["gokhan2024regnlp"]], ["2", REFS["gokhan2025riragtask"]], ["3", REFS["aueb2025rirag"]],
    ["4", REFS["obliqamp"]], ["5", REFS["indiafinbench"]],
], [0.5, 5.3], font=10, label_prefix="-")
R.p("**Status of the project after Review 1**", align=L, space_after=2)
R.table("", ["Item", ""], [
    ["Comments/Remarks", ""], ["Name and Signature of the guide", D["mentor"]],
    ["Name and signature of panel members for review 1", ""], ["Signature of HoD", ""],
], [2.6, 3.2], font=11, label_prefix="-")
for row in doc.tables[-1].rows[1:]:
    row.height = Inches(0.5)
R.p("**If any change in project title after review 1 presentation as per comments received from panel and areas of "
    "concern to be noted here**", align=L)
# The form's tables carry no captions.
for p in [p for p in doc.paragraphs if p.text.startswith("Table -")]:
    p._p.getparent().remove(p._p)
out = ROOT / "output" / "Topic_Approval_Form_prefilled.docx"
R.save(out, update_fields_on_open=False)
print(out)

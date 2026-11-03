"""Blank topic approval form (Annexure A.2, to fill by hand) and a standalone certificate page.

    python build/build_blank_forms.py        # from capstone_submission/
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
LOGO = ROOT / "figures" / "nmims_logo.jpeg"
OUT = ROOT / "output"
TITLE = D["title"]
L, C = WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER
BLANK = "______________________________"


def known(value):
    """A value from details.json, or a blank line to write on when it is still a placeholder."""
    return BLANK if "«" in value else value


def logo(R, width):
    para = R.doc.add_paragraph()
    para.alignment = C
    para.paragraph_format.space_after = Pt(2)
    para.add_run().add_picture(str(LOGO), width=Inches(width))


def drop_captions(doc):
    for p in [p for p in doc.paragraphs if p.text.startswith("Table -")]:
        p._p.getparent().remove(p._p)


def tall(doc, height, first=1):
    for row in doc.tables[-1].rows[first:]:
        row.height = Inches(height)


# ------------------------------------------------------------------------------------------- blank topic form
R = Report("", "")
doc = R.doc
doc.styles["Normal"].paragraph_format.line_spacing = 1.15
logo(R, 1.2)
R.center("**Mukesh Patel School of Technology Management & Engineering**", size=15, space_after=2)
R.center("**Topic approval form**", size=13, space_after=12)
for label in ("Department", "Program", "Semester"):
    R.p(f"**{label}:** ______________________________________________", align=L, space_after=4)
R.p("**Project Team details**", align=L, space_after=2)
R.table("", ["S No", "SAP ID", "Roll No", "Name", "Signature"], [["1", "", "", "", ""], ["2", "", "", "", ""],
                                                                  ["3", "", "", "", ""]],
        [0.5, 1.2, 1.0, 1.8, 1.3], font=11, label_prefix="-")
tall(doc, 0.4)
R.p("**Type of Project** (Tick any one)", align=L, space_after=2)
R.table("", ["Type of project", ""], [["Application", ""], ["Product", ""], ["Research", ""]],
        [2.5, 1.2], font=11, label_prefix="-")
tall(doc, 0.32)
R.p("**Project details**", align=L, space_after=2)
R.table("", ["Project Title", ""], [["Project Objectives", ""], ["Domain", ""]], [1.6, 4.2], font=11,
        label_prefix="-")
doc.tables[-1].rows[0].height = Inches(0.6)
doc.tables[-1].rows[1].height = Inches(1.3)
doc.tables[-1].rows[2].height = Inches(0.4)
# The header row of this table is a normal field row: drop its grey shading and bold.
for cell in doc.tables[-1].rows[0].cells:
    for shd in cell._tc.tcPr.findall("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}shd"):
        cell._tc.tcPr.remove(shd)
    for r in cell.paragraphs[0].runs:
        r.bold = False
    cell.paragraphs[0].alignment = L

R.page_break()
R.table("", ["Motivation", ""], [["Expected outcomes", ""]], [1.6, 4.2], font=11, label_prefix="-")
doc.tables[-1].rows[0].height = Inches(1.0)
doc.tables[-1].rows[1].height = Inches(0.7)
for cell in doc.tables[-1].rows[0].cells:
    for shd in cell._tc.tcPr.findall("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}shd"):
        cell._tc.tcPr.remove(shd)
    for r in cell.paragraphs[0].runs:
        r.bold = False
    cell.paragraphs[0].alignment = L
R.p("", space_after=4)
R.p("**Latest References**", align=L, space_after=2)
R.table("", ["S No", "Publication (Author, “Title”, Journal/Book/Conference, Date, Page, Volume, year)"],
        [[str(i), ""] for i in range(1, 6)], [0.6, 5.2], font=10.5, label_prefix="-")
tall(doc, 0.45)
R.p("", space_after=6)
R.p("**Status of the project after Review 1**", align=L, space_after=2)
R.table("", ["Comments/Remarks", ""], [["Name and Signature of the guide", ""],
                                         ["Name and signature of panel members for review 1", ""],
                                         ["Signature of HoD", ""]], [2.6, 3.2], font=11, label_prefix="-")
tall(doc, 0.5, first=0)
for cell in doc.tables[-1].rows[0].cells:
    for shd in cell._tc.tcPr.findall("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}shd"):
        cell._tc.tcPr.remove(shd)
    cell.paragraphs[0].alignment = L
R.p("", space_after=6)
R.p("**If any change in project title after review 1 presentation as per comments received from panel and areas of "
    "concern to be noted here**", align=L)
drop_captions(doc)
form = OUT / "Topic_Approval_Form_blank.docx"
R.save(form, update_fields_on_open=False)
print(form)

# ------------------------------------------------------------------------------------------- certificate
R = Report("", "")
doc = R.doc
logo(R, 1.5)
R.center("**SVKM's NMIMS (Deemed-to-be University)**", size=14, space_after=0)
R.center("**Mukesh Patel School of Technology Management & Engineering**", size=14, space_after=0)
R.center("Vile Parle (W), Mumbai-56", size=12, space_after=0)
R.center(f"({D['academic_year']})", size=12, space_after=24)
R.center("**CERTIFICATE**", size=20, space_after=24, underline=True)
students = D["students"]
by = ", ".join(f"{s['name']} (Roll No. {s['roll']})" for s in students[:-1]) + \
     f" and {students[-1]['name']} (Roll No. {students[-1]['roll']})"
R.p(f"This is to certify that the project entitled **“{TITLE}”** has been done by {by} under my guidance "
    f"and supervision, and has been submitted in partial fulfilment of the degree of {known(D['program'])} in "
    f"{known(D['stream'])} of MPSTME, SVKM's NMIMS (Deemed-to-be University), Mumbai, India.")
for para in doc.paragraphs[-1:]:
    para.paragraph_format.line_spacing = 1.8
R.blank(1)
R.borderless_table([
    [("_____________________________", L), ("_____________________________", L)],
    [(f"**{D['mentor']}**", L), ("**Examiner**", L)],
    [("Project Mentor (Internal Guide)", L), ("(Name and Signature)", L)],
    [("(Name and Signature)", L), ("", L)],
], [3.0, 2.8])
R.blank(2)
R.p("**Date:** ____________________", align=L, space_after=4)
R.p("**Place:** Mumbai", align=L, space_after=0)
R.blank(1)
hod = D["hod"]
R.borderless_table([
    [("", L), ("_____________________________", L)],
    [("", L), (f"**{hod}**" if "«" not in hod else "", L)],
    [("", L), ("Head of Department (HoD)", L)],
    [("", L), ("(Name and Signature)", L)],
], [3.0, 2.8])
end = doc.add_paragraph()  # Word needs a paragraph after a table; keep it tiny so it cannot start a page
end.paragraph_format.space_after = Pt(0)
end.paragraph_format.line_spacing = 1.0
end.add_run("").font.size = Pt(1)
cert = OUT / "Certificate.docx"
R.save(cert, update_fields_on_open=False)
print(cert)

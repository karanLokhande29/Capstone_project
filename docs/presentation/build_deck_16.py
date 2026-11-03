"""Capstone final presentation, 16-slide version (15-minute talk with a live demo), built on the department template (FirstTwoSlides.ppt -> template.pptx).

Slides 1-2 are the template's own slides with the project's details; every other slide reuses the template's master
(background, date and slide-number footers) and adds native shapes, flowcharts and charts. Numbers come from the
capstone report / submitted paper (results_v2) and the sprint extension results.
"""

from __future__ import annotations

import copy
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_TICK_LABEL_POSITION
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

HERE = Path(__file__).parent
ICONS = HERE / "icons_rgba"
OUT = HERE / "RBI-ObliBench_Final_Presentation_16slides.pptx"

MAROON = RGBColor(0x62, 0x24, 0x23)
MAROON_SOFT = RGBColor(0xF1, 0xE4, 0xE2)
DARK = RGBColor(0x26, 0x26, 0x26)
GREY = RGBColor(0x59, 0x59, 0x59)
MUTED = RGBColor(0x8C, 0x8C, 0x8C)
LINE = RGBColor(0xD6, 0xD0, 0xC4)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
AMBER = RGBColor(0xB8, 0x86, 0x2B)
AMBER_SOFT = RGBColor(0xF6, 0xEC, 0xD6)
SLATE = RGBColor(0x3B, 0x4A, 0x5A)
SLATE_SOFT = RGBColor(0xE3, 0xE8, 0xEE)
GREEN = RGBColor(0x2E, 0x6B, 0x4F)
GREEN_SOFT = RGBColor(0xE2, 0xEF, 0xE7)
HEAD, BODY = "Times New Roman", "Calibri"

prs = Presentation(str(HERE / "template.pptx"))
LAYOUT = prs.slide_layouts[0]
FOOTER_XML = [copy.deepcopy(sh._element) for sh in prs.slides[1].shapes if sh.name.startswith(("Date", "Slide Number"))]


# -- helpers -----------------------------------------------------------------------------------------

def new_slide(title: str, takeaway: str | None = None):
    s = prs.slides.add_slide(LAYOUT)
    for ph in list(s.placeholders):
        ph._element.getparent().remove(ph._element)
    for el in FOOTER_XML:
        s.shapes._spTree.append(copy.deepcopy(el))
    tb = s.shapes.add_textbox(Inches(0.5), Inches(0.32), Inches(9.0), Inches(0.62))
    tf = tb.text_frame
    tf.margin_left = tf.margin_right = 0
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = title
    r.font.name, r.font.size, r.font.bold, r.font.color.rgb = HEAD, Pt(28), True, DARK
    tb.name = "Title"
    if takeaway:
        t = text(s, takeaway, 0.5, 0.95, 9.0, 0.42, size=15, color=MAROON, italic=True)
        t.name = "Takeaway"
    return s


def text(s, value, x, y, w, h, *, size=14, color=DARK, bold=False, italic=False, align=PP_ALIGN.LEFT, font=BODY,
         anchor=MSO_ANCHOR.TOP, margin=0.0, spacing=None):
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = Inches(margin)
    lines = value if isinstance(value, list) else [value]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if spacing:
            p.space_after = Pt(spacing)
        runs = line if isinstance(line, list) else [(line, {})]
        for seg, opt in runs:
            r = p.add_run()
            r.text = seg
            r.font.name = opt.get("font", font)
            r.font.size = Pt(opt.get("size", size))
            r.font.bold = opt.get("bold", bold)
            r.font.italic = opt.get("italic", italic)
            r.font.color.rgb = opt.get("color", color)
    return tb


def box(s, x, y, w, h, *, fill=WHITE, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12, line_w=1.0, label=None,
        size=13, color=DARK, bold=False, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, font=BODY, name=None):
    sh = s.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        sh.adjustments[0] = radius
    if fill is None:
        sh.fill.background()
    else:
        sh.fill.solid()
        sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
        sh.line.width = Pt(line_w)
    sh.shadow.inherit = False
    if name:
        sh.name = name
    if label is not None:
        tf = sh.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = anchor
        for m in ("margin_left", "margin_right"):
            setattr(tf, m, Inches(0.06))
        tf.margin_top = tf.margin_bottom = Inches(0.03)
        lines = label if isinstance(label, list) else [label]
        for i, line_ in enumerate(lines):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = align
            runs = line_ if isinstance(line_, list) else [(line_, {})]
            for seg, opt in runs:
                r = p.add_run()
                r.text = seg
                r.font.name = opt.get("font", font)
                r.font.size = Pt(opt.get("size", size))
                r.font.bold = opt.get("bold", bold)
                r.font.italic = opt.get("italic", False)
                r.font.color.rgb = opt.get("color", color)
    return sh


def arrow(s, x1, y1, x2, y2, *, color=MAROON, width=1.75, head=True, dash=False):
    c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = color
    c.line.width = Pt(width)
    ln = c.line._get_or_add_ln()
    if dash:
        d = etree.SubElement(ln, qn("a:prstDash"))
        d.set("val", "dash")
    if head:
        t = etree.SubElement(ln, qn("a:tailEnd"))
        t.set("type", "triangle")
        t.set("w", "med")
        t.set("len", "med")
    return c


def elbow(s, pts, **kw):
    """Poly-line through points with an arrow head on the last segment."""
    for i in range(len(pts) - 1):
        arrow(s, *pts[i], *pts[i + 1], head=(i == len(pts) - 2), **kw)


def icon(s, name, x, y, size, variant="m"):
    return s.shapes.add_picture(str(ICONS / f"{name}_{variant}.png"), Inches(x), Inches(y), Inches(size), Inches(size))


def icon_circle(s, name, x, y, d, *, fill=MAROON, variant="w"):
    box(s, x, y, d, d, fill=fill, line=None, shape=MSO_SHAPE.OVAL)
    pad = d * 0.24
    icon(s, name, x + pad, y + pad, d - 2 * pad, variant)


def numbered(s, n, x, y, d=0.42, fill=MAROON, size=14):
    sh = box(s, x, y, d, d, fill=fill, line=None, shape=MSO_SHAPE.OVAL, label=str(n), size=size, color=WHITE, bold=True)
    tf = sh.text_frame
    tf.word_wrap = False
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    return sh


def notes(s, value: str):
    s.notes_slide.notes_text_frame.text = value


def style_chart(ch, *, legend=True, size=12):
    ch.font.name = BODY
    ch.font.size = Pt(size)
    ch.font.color.rgb = GREY
    ch.has_legend = legend
    if legend:
        ch.legend.position = XL_LEGEND_POSITION.BOTTOM
        ch.legend.include_in_layout = False
        ch.legend.font.size = Pt(size)


def quiet_axes(ch, *, vmax=None, vmin=None, fmt="0.0", gridlines=True):
    va = ch.value_axis
    va.has_major_gridlines = gridlines
    if gridlines:
        va.major_gridlines.format.line.color.rgb = RGBColor(0xE2, 0xDE, 0xD5)
        va.major_gridlines.format.line.width = Pt(0.75)
    va.format.line.fill.background()
    va.tick_labels.number_format = fmt
    va.tick_labels.number_format_is_linked = False
    if vmax is not None:
        va.maximum_scale = vmax
    if vmin is not None:
        va.minimum_scale = vmin
    ca = ch.category_axis
    ca.format.line.color.rgb = LINE
    ca.has_major_gridlines = False


def color_series(ch, colors):
    for ser, col in zip(ch.plots[0].series, colors):
        ser.format.fill.solid()
        ser.format.fill.fore_color.rgb = col
        ser.format.line.fill.background()


def labels(plot, fmt="0.000", size=11, pos=XL_LABEL_POSITION.OUTSIDE_END, color=DARK):
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.number_format = fmt
    dl.number_format_is_linked = False
    dl.font.size = Pt(size)
    dl.font.color.rgb = color
    if pos is not None:
        dl.position = pos


def stat(s, value, label, x, y, w, *, color=MAROON, vsize=34, lsize=13):
    text(s, value, x, y, w, 0.62, size=vsize, color=color, bold=True, font=HEAD)
    text(s, label, x, y + 0.62, w, 0.5, size=lsize, color=GREY)


# -- 1-2: template slides ---------------------------------------------------------------------------------

def edit_runs(shape, mapping):
    for p in shape.text_frame.paragraphs:
        for r in p.runs:
            if r.text in mapping:
                r.text = mapping[r.text]


s1 = prs.slides[0]
for sh in s1.shapes:
    if sh.name == "TextBox 3":
        edit_runs(sh, {"Capstone Project Topic Approval Presentation": "Capstone Project Final Examination Presentation",
                       "Academic Year 2024-25": "Academic Year 2026-27"})

s2 = prs.slides[1]
tb2 = next(sh for sh in s2.shapes if sh.name == "TextBox 1")
paras = tb2.text_frame.paragraphs
paras[2].runs[0].text = "“Same Subject, Different Duties: RBI-ObliBench for Differential Obligations across Entity Classes”"
paras[2].runs[0].font.size = Pt(24)
# Student details: one line per student (name, roll no, SAP ID), group number first.
student_p = paras[6]
for r in list(student_p.runs)[1:]:
    r._r.getparent().remove(r._r)
student_p.runs[0].text = "Group 10"
student_p.runs[0].font.size = Pt(18)
anchor_el = student_p._p
for line in ["Akash Goyal  ·  Roll No. I025  ·  SAP ID 70122300034",
             "Karan Lokhande  ·  Roll No. I039  ·  SAP ID 70122300054",
             "Meer Magia  ·  Roll No. I040  ·  SAP ID 70122300013"][::-1]:
    np_ = copy.deepcopy(student_p._p)
    for t in np_.iter(qn("a:t")):
        t.text = line
    for rpr in np_.iter(qn("a:rPr")):
        rpr.set("sz", "1600")
        rpr.set("b", "0")
    anchor_el.addnext(np_)
# Drop two spacer paragraphs so the block still fits above the footer.
for idx in (17, 15, 10, 7):
    el = tb2.text_frame.paragraphs[idx]._p
    if not "".join(t.text or "" for t in el.iter(qn("a:t"))).strip():
        el.getparent().remove(el)
for p in tb2.text_frame.paragraphs:
    for r in p.runs:
        if r.text.strip() == "PROJECT MENTOR NAME":
            r.text = "Prof. Jish Elizabeth Joy"
        elif r.text.strip() == "Prof./Dr.":
            r.text = "Assistant Professor, Department of Artificial Intelligence"
            r.font.size = Pt(16)
            r.font.bold = False
notes(s1, "Good morning. We are Group 10 from the Department of Artificial Intelligence, presenting our capstone project. (About 9 minutes of slides, a 5-minute live demo after the RQ3 slide, then 5 minutes of Q&A.)")
notes(s2, "Our project is RBI-ObliBench: a benchmark and tools for finding where parallel RBI Master Directions impose different duties on different kinds of regulated entities. Mentor: Prof. Jish Elizabeth Joy; co-author Dr. Hima Deepthi Vankayalapati.")

# -- 4: introduction ------------------------------------------------------------------------------------------------
s = new_slide("Introduction: one subject, many Master Directions",
              "RBI writes a separate Direction for each kind of regulated entity, so the same duty can quietly differ")
# Tree: one subject at the top, a bus line, four parallel Directions below.
box(s, 3.2, 1.5, 3.6, 0.95, fill=MAROON, line=None, radius=0.2,
    label=[[("One subject", {"size": 11, "color": RGBColor(0xF0, 0xD8, 0xD6)})], [("Board-approved outsourcing policy", {"bold": True, "size": 15})]],
    color=WHITE)
cards = [("Commercial Banks", "same duty?"), ("Small Finance Banks", "different approver?"),
         ("NBFCs", "different scope?"), ("Urban Co-op Banks", "no counterpart?")]
CW, GAP, CY, BUS = 2.1, 0.2, 3.1, 2.78
cx = [0.5 + i * (CW + GAP) + CW / 2 for i in range(4)]
arrow(s, 5.0, 2.45, 5.0, BUS, color=MUTED, width=1.5, head=False)
arrow(s, cx[0], BUS, cx[-1], BUS, color=MUTED, width=1.5, head=False)
for i, (cls, q) in enumerate(cards):
    arrow(s, cx[i], BUS, cx[i], CY - 0.02, color=MUTED, width=1.5)
    box(s, cx[i] - CW / 2, CY, CW, 0.95, fill=WHITE, line=LINE,
        label=[[(cls, {"bold": True, "size": 14})], [(q, {"size": 12, "color": MAROON, "italic": True})]])
text(s, "Each class has its own Master Direction. Illustrative: which of these hold is exactly what the benchmark asks a system to decide.",
     0.5, 4.15, 9.0, 0.4, size=11, color=MUTED, italic=True, align=PP_ALIGN.CENTER)
for i, (v, l, ic) in enumerate([("381", "Master Directions harvested", "BookOpen"), ("76,188", "paragraphs with stable ids", "FileText"),
                                ("11", "regulated-entity classes", "Building2")]):
    x = 0.5 + i * 3.05
    box(s, x, 4.8, 2.85, 1.45, fill=WHITE, line=LINE, radius=0.08)
    icon_circle(s, ic, x + 0.2, 5.12, 0.8)
    stat(s, v, l, x + 1.15, 4.97, 1.65, vsize=30, lsize=12)
notes(s, "Regulated entities follow Master Directions written per class: commercial banks, small finance banks, payments banks, co-operative banks, NBFCs and others. One subject such as outsourcing appears in several near-parallel Directions. A group owning a bank and an NBFC, an auditor, or a RegTech vendor has to notice where they differ. A threshold, deadline, approving body or scope can change between classes: a false difference wastes review time, a missed one can leave an entity non-compliant.")

# -- 4: literature review -> gap -> problem statement ----------------------------------------------------------------------
s = new_slide("Literature review and problem statement", "Regulatory QA treats a regulation as one rulebook; nobody compares duties across entity classes")
rows = [("ObliQA / RIRAG [7]", "ADGM financial regulations", "Retrieval + answer generation", False, "Introduces RePASs"),
        ("AUEB-Archimedes [38]", "ADGM (ObliQA)", "RAG system", False, "Concatenation games RePASs"),
        ("ObliQA-MP [39]", "ADGM", "Multi-passage, learning-to-rank", False, "—"),
        ("IndiaFinBench [40]", "SEBI and RBI text", "LLM QA, 4 question types", False, "—"),
        ("RAGAS [17]", "General", "RAG evaluation framework", False, "Reference-free metrics"),
        ("RBI-ObliBench (ours)", "381 RBI Master Directions", "Applicability, differential, retrieval, temporal", True, "Audits RePASs (T4)")]
tbl = s.shapes.add_table(len(rows) + 1, 5, Inches(0.5), Inches(1.42), Inches(9.0), Inches(2.6)).table
for i, w in enumerate([2.05, 2.0, 2.45, 1.05, 1.45]):
    tbl.columns[i].width = Inches(w)
for c, h in enumerate(["Work", "Domain / data", "Task", "Cross-class", "Metric audit"]):
    cell = tbl.cell(0, c)
    cell.fill.solid()
    cell.fill.fore_color.rgb = MAROON
    cell.text = h
    p = cell.text_frame.paragraphs[0]
    p.runs[0].font.size, p.runs[0].font.bold, p.runs[0].font.color.rgb, p.runs[0].font.name = Pt(12), True, WHITE, BODY
for r, (w, d, t, cc, m) in enumerate(rows, start=1):
    ours = r == len(rows)
    for c, v in enumerate([w, d, t, "✓" if cc else "✗", m]):
        cell = tbl.cell(r, c)
        cell.fill.solid()
        cell.fill.fore_color.rgb = MAROON_SOFT if ours else (WHITE if r % 2 else RGBColor(0xF7, 0xF4, 0xEE))
        cell.text = v
        cell.margin_top = cell.margin_bottom = Inches(0.02)
        p = cell.text_frame.paragraphs[0]
        run = p.runs[0]
        run.font.name, run.font.size = BODY, Pt(11)
        run.font.bold = ours or c == 0
        run.font.color.rgb = DARK
        if c == 3:
            p.alignment = PP_ALIGN.CENTER
            run.font.size = Pt(14)
            run.font.color.rgb = GREEN if cc else MAROON
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
box(s, 0.5, 4.3, 9.0, 1.05, fill=MAROON, line=None, radius=0.1, align=PP_ALIGN.LEFT,
    label=[[("Problem statement: ", {"bold": True, "size": 13, "color": WHITE}),
            ("for an obligation in one entity class's Master Direction, decide for every other class whether a counterpart exists and "
             "whether it imposes the same or a different duty; retrieve it; tell whether a paragraph is in force on a date; and test "
             "whether the usual faithfulness metric can be gamed on Indian regulatory text.", {"size": 12, "color": WHITE})]])
tasks = [("T1", "Applicability and differential", "106 expert items · 412 class judgements", "RQ1, RQ2"),
         ("T2", "Counterpart retrieval", "291 / 53 / 25 queries · nDCG@10", "RQ1"),
         ("T3", "Temporal status", "52 items: in force · amended · deleted", "diagnostic"),
         ("T4", "RePASs metric audit", "30 questions × 4 answer types", "RQ3")]
for i, (t, h, d, rq) in enumerate(tasks):
    x = 0.5 + i * 2.29
    box(s, x, 5.5, 2.15, 1.15, fill=WHITE, line=LINE, radius=0.08, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
        label=[[(t + "  ", {"bold": True, "color": MAROON, "size": 14, "font": HEAD}), (rq, {"size": 10, "color": MAROON, "bold": True})],
               [(h, {"bold": True, "size": 11})], [(d, {"size": 10, "color": GREY})]])
notes(s, "Related work: ObliQA and RePASs set up regulatory retrieve-then-answer on one rulebook; AUEB-Archimedes showed RePASs rewards concatenating obligations; IndiaFinBench is the closest Indian benchmark but tests single documents. None compares obligations across entity classes. That gap is our problem statement, split into four tasks: T1 same / different / none for each compared class, T2 counterpart retrieval, T3 temporal status, T4 the RePASs audit.")

# -- 9: block diagram ----------------------------------------------------------------------------------------------------
s = new_slide("Methodology: overall block diagram", "Three stages, built and validated one after another")
lanes = [("1  Data collection", ["Harvest 381 Master Directions", "PDF → text (pdfplumber)", "Segment 76,188 paragraphs, stable ids", "Tag entity class × subject family"]),
         ("2  Benchmark construction", ["Extract obligation candidates (28,694)", "Cross-class matching (bge + lexical)", "Expert labels: T1 gold (106 items)", "T2 · T3 · T4 sets (FAQs, penalties, amendments)"]),
         ("3  Evaluation and outputs", ["Retrieval + LLM judgement systems", "Paired bootstrap scoring", "Paper + pointer-only data release", "Website + audit generator"])]
for li, (lane, steps) in enumerate(lanes):
    y = 1.55 + li * 1.72
    box(s, 0.5, y, 9.0, 1.45, fill=RGBColor(0xFA, 0xF8, 0xF3), line=LINE, radius=0.06)
    text(s, lane, 0.65, y + 0.06, 4.0, 0.35, size=13, bold=True, color=MAROON)
    for si_, st in enumerate(steps):
        x = 0.68 + si_ * 2.22
        box(s, x, y + 0.45, 1.92, 0.85, fill=WHITE if li < 2 else MAROON, line=MAROON if li < 2 else None, line_w=1.25,
            label=st, size=12, color=DARK if li < 2 else WHITE, bold=li == 2)
        if si_ < 3:
            arrow(s, x + 1.94, y + 0.875, x + 2.2, y + 0.875, width=1.5)
    if li < 2:
        arrow(s, 9.1 - 1.0, y + 1.3, 9.1 - 1.0, y + 1.72 + 0.45, width=1.5)
notes(s, "Row one collects the data; row two builds the benchmark; row three runs the systems and produces the paper, data release and applications. Phase 1 was split: Akash harvested and segmented the corpus, Karan built the metadata and class × family matrix, Meer ran the quality checks, annotation protocol and three-rater pilot.")
# -- 11: evaluation architecture flowchart ---------------------------------------------------------------------------------------------
s = new_slide("Methodology: evaluation flowchart", "Every system shares one pipeline; filters and the verifier switch on and off (ablations A–C)")
Y = 1.7
row = [(0.45, 1.5, SLATE_SOFT, None, DARK, [[("Input", {"bold": True})], [("obligation o · class c · date t", {"size": 11})]]),
       (2.2, 1.65, WHITE, MAROON, DARK, [[("Hybrid retrieval", {"bold": True})], [("BM25 + bge · RRF k = 60", {"size": 11})]]),
       (4.1, 1.4, AMBER_SOFT, None, DARK, [[("A  Class filter", {"bold": True})], [("only class c", {"size": 11})]]),
       (5.75, 1.4, AMBER_SOFT, None, DARK, [[("B  Temporal filter", {"bold": True})], [("in force on t", {"size": 11})]]),
       (7.4, 1.5, MAROON, None, WHITE, [[("LLM judge", {"bold": True})], [("same / different / none", {"size": 11})]])]
for i, (x, w, fill, line_, col, lab) in enumerate(row):
    box(s, x, Y, w, 1.0, fill=fill, line=line_, color=col, label=lab, size=13)
    if i < len(row) - 1:
        arrow(s, x + w + 0.02, Y + 0.5, row[i + 1][0] - 0.02, Y + 0.5)
JX = 7.4 + 0.75
Y2 = 3.3
arrow(s, JX, Y + 1.02, JX, Y2 - 0.02)
box(s, JX - 1.15, Y2, 2.3, 1.3, fill=WHITE, line=MAROON, line_w=1.5, shape=MSO_SHAPE.DIAMOND,
    label=[[("C  NLI verifier:", {"bold": True, "size": 11})], [("rationale", {"size": 11})], [("entailed?", {"size": 11})]])
arrow(s, JX - 1.17, Y2 + 0.65, 6.32, Y2 + 0.65)
text(s, "yes", 6.45, Y2 + 0.28, 0.5, 0.3, size=11, color=GREEN, bold=True)
box(s, 4.6, Y2 + 0.2, 1.7, 0.9, fill=GREEN_SOFT, line=None, label=[[("Flag rule v3.6", {"bold": True})], [("any different → class-specific", {"size": 10})]])
arrow(s, 5.45, Y2 + 1.12, 5.45, Y2 + 1.6)
box(s, 4.6, Y2 + 1.62, 1.7, 0.85, fill=SLATE, line=None, color=WHITE, label=[[("Item flag", {"bold": True})], [("shared · class-specific · absent", {"size": 10})]])
arrow(s, JX, Y2 + 1.32, JX, Y2 + 1.7)
text(s, "no", JX + 0.08, Y2 + 1.33, 0.4, 0.3, size=11, color=MAROON, bold=True)
box(s, JX - 0.8, Y2 + 1.72, 1.6, 0.75, fill=MAROON_SOFT, line=None, label=[[("Retry once", {"bold": True})], [("then abstain", {"size": 11})]])
box(s, 0.45, 3.3, 3.7, 1.25, fill=WHITE, line=LINE, align=PP_ALIGN.LEFT,
    label=[[("Alternative: long-context system", {"bold": True, "color": SLATE})], [("Every Direction of the compared classes, up to 100K tokens; no retrieval", {"size": 12})]])
box(s, 0.45, 4.75, 3.7, 1.25, fill=WHITE, line=LINE, align=PP_ALIGN.LEFT,
    label=[[("Targeted: structured comparator", {"bold": True, "color": MAROON})], [("13 fields compared, a fixed rule decides (next slide)", {"size": 12})]])
text(s, "gemini-3.5-flash-lite · temperature 0 · frozen, hashed prompts · predictions sealed before scoring", 0.45, 6.3, 9.0, 0.4, size=12, color=MUTED, italic=True)
notes(s, "Hybrid retrieval with optional class and temporal filters feeds the LLM judge. In the final agentic system an NLI verifier checks the rationale: retry once, then abstain. Rule v3.6 turns per-class judgements into an item flag. Long-context and the comparator are the alternatives.")

# -- 12: comparator algorithm --------------------------------------------------------------------------------------------------------
s = new_slide("Implementation algorithm: structured comparator", "The model extracts fields; a fixed rule, not the model, makes the call")
box(s, 0.5, 1.5, 2.6, 0.9, fill=SLATE_SOFT, line=None, label=[[("Start", {"bold": True})], [("source s + candidates c1, c2", {"size": 12})]])
arrow(s, 1.8, 2.42, 1.8, 2.75)
box(s, 0.5, 2.77, 2.6, 1.05, fill=WHITE, line=MAROON, label=[[("Extract 13 fields", {"bold": True})], [("from s and each candidate (JSON, frozen prompt)", {"size": 11})]])
arrow(s, 3.12, 3.3, 3.42, 3.3)
box(s, 3.44, 2.62, 2.2, 1.35, fill=WHITE, line=MAROON, line_w=1.5, shape=MSO_SHAPE.DIAMOND, label=[[("Same duty?", {"bold": True})]])
arrow(s, 4.54, 3.99, 4.54, 4.55)
text(s, "no", 4.62, 4.05, 0.4, 0.3, size=11, bold=True, color=MAROON)
box(s, 3.79, 4.57, 1.5, 0.65, fill=AMBER, line=None, color=WHITE, label=[[("none", {"bold": True, "size": 15})]])
arrow(s, 5.66, 3.3, 5.98, 3.3)
text(s, "yes", 5.62, 2.92, 0.45, 0.3, size=11, bold=True, color=GREEN)
box(s, 6.0, 2.35, 3.0, 1.9, fill=WHITE, line=MAROON, line_w=1.5, shape=MSO_SHAPE.DIAMOND,
    label=[[("Any field differs,", {"bold": True, "size": 11})], [("or a material field", {"bold": True, "size": 11})], [("on one side only?", {"bold": True, "size": 11})]])
arrow(s, 7.5, 4.27, 7.5, 4.55)
text(s, "yes", 7.58, 4.25, 0.45, 0.3, size=11, bold=True, color=GREEN)
box(s, 6.75, 4.57, 1.5, 0.65, fill=MAROON, line=None, color=WHITE, label=[[("different", {"bold": True, "size": 15})]])
arrow(s, 9.02, 3.3, 9.3, 3.3, head=False)
arrow(s, 9.3, 3.3, 9.3, 2.1)
text(s, "no", 8.95, 2.92, 0.4, 0.3, size=11, bold=True, color=MAROON)
box(s, 8.25, 1.42, 1.25, 0.65, fill=SLATE, line=None, color=WHITE, label=[[("same", {"bold": True, "size": 15})]])
text(s, [[("13 fields", {"bold": True, "color": MAROON, "size": 12})],
         [("actor · action · object · scope · condition · threshold · amount · percentage · frequency · deadline · exception · documentation · reporting", {"size": 11, "color": GREY})]],
     0.5, 4.05, 2.85, 1.3)
box(s, 0.5, 5.4, 1.55, 1.0, fill=MAROON, line=None, label=[[("Result", {"bold": True, "size": 14})], [("106-item gold", {"size": 11})]], color=WHITE)
for i, (v, l) in enumerate([("0.154 → 0.409", "‘different’ F1 vs class-aware LLM"), ("+0.397", "‘different’ recall [+0.250, +0.543]"),
                            ("26 / 56", "differences every LLM missed, now found"), ("40 / 78", "still missed: honest limit")]):
    x = 2.15 + i * 1.85
    box(s, x, 5.4, 1.75, 1.0, fill=AMBER_SOFT if i == 3 else MAROON_SOFT, line=None,
        label=[[(v, {"bold": True, "size": 15, "color": AMBER if i == 3 else MAROON})], [(l, {"size": 10, "color": DARK})]])
notes(s, "Algorithm A.1. The model fills a 13-field table for the source and each candidate; the rule decides. Class verdict: strongest candidate verdict, precedence same > different > none. Result: against the class-aware LLM, different F1 rises from 0.154 to 0.409 and recall by +0.397; it recovers 26 of the 56 differences every LLM system missed, but still misses 40 of 78. Developed only on a separate 30-item set, one bug-fix revision, frozen by hash before touching the gold. Comparisons were pre-registered.")


# -- 8: the five LLM systems + models and stack ------------------------------------------------------------------------------
s = new_slide("Implementation: LLM systems, tools and technology", "Same model, same frozen prompts; only what each system sees and checks changes")
CHIP = {"H": ("Hybrid retrieval", SLATE_SOFT, DARK), "HA": ("Hybrid retrieval, all classes", SLATE_SOFT, DARK),
        "A": ("Class filter", AMBER_SOFT, DARK), "B": ("Temporal filter", AMBER_SOFT, DARK),
        "J": ("LLM judge", MAROON, WHITE), "C": ("NLI verifier", GREEN_SOFT, DARK),
        "L": ("Whole Directions, ≤100K tokens", SLATE_SOFT, DARK), "K": ("Candidate counterparts", SLATE_SOFT, DARK),
        "X": ("Extract 13 fields", MAROON, WHITE), "R": ("Fixed rule decides", GREEN_SOFT, DARK)}
systems = [("Class-blind LLM", "no entity-class information", ["HA", "J"], "0.602", "0.321"),
           ("Class-aware LLM", "retrieves only the compared class", ["H", "A", "J"], "0.551", "0.154"),
           ("Final agentic", "abstains when not entailed (coverage 0.774)", ["H", "A", "B", "J", "C"], "0.483", "0.047"),
           ("Long-context LLM", "no retrieval (n = 102)", ["L", "J"], "0.509", "0.074"),
           ("Structured comparator", "the model extracts, a rule decides", ["K", "X", "R"], "0.616", "0.409")]
text(s, "3-way F1", 7.55, 1.3, 0.95, 0.25, size=9.5, bold=True, color=GREY, align=PP_ALIGN.CENTER)
text(s, "‘different’ F1", 8.5, 1.3, 1.05, 0.25, size=9.5, bold=True, color=GREY, align=PP_ALIGN.CENTER)
for i, (name, sub, chips, f3, fd) in enumerate(systems):
    y = 1.58 + i * 0.72
    best = i == 4
    box(s, 0.5, y, 2.15, 0.62, fill=MAROON if best else WHITE, line=None if best else MAROON, line_w=1.25, align=PP_ALIGN.LEFT,
        label=[[(name, {"bold": True, "size": 11.5, "color": WHITE if best else DARK})],
               [(sub, {"size": 8.5, "color": RGBColor(0xF0, 0xD8, 0xD6) if best else GREY})]])
    n = len(chips)
    gap = 0.12
    w = (4.65 - gap * (n - 1)) / n
    for k, c in enumerate(chips):
        lab, fill, col = CHIP[c]
        x = 2.8 + k * (w + gap)
        box(s, x, y + 0.08, w, 0.46, fill=fill, line=None, label=lab, size=9, color=col, bold=c in ("J", "X"))
        if k < n - 1:
            arrow(s, x + w + 0.005, y + 0.31, x + w + gap - 0.005, y + 0.31, width=1.25)
    for x, v, hl in ((7.55, f3, False), (8.5, fd, True)):
        box(s, x, y + 0.06, 0.95 if x < 8 else 1.0, 0.5, fill=MAROON_SOFT if (best and hl) else RGBColor(0xF7, 0xF4, 0xEE), line=None,
            label=[[(v, {"bold": True, "size": 14, "color": MAROON if (best and hl) else DARK, "font": HEAD})]])
box(s, 0.5, 5.25, 9.0, 0.38, fill=MAROON_SOFT, line=None,
    label=[[("All five: gemini-3.5-flash-lite (Google, free tier) · temperature 0 · frozen, hashed prompts · predictions sealed before scoring · 106-item gold", {"size": 10, "color": MAROON, "bold": True})]])
text(s, [[("Tools and technology  ", {"bold": True, "size": 11, "color": MAROON}),
          ("Python · pdfplumber · BM25S + bge, RRF k = 60 · LangGraph port · NumPy / SciPy, bootstrap 2,000 · React 19 + Vite · FastAPI · "
           "ONNX Runtime · Azure static site + Functions · Kaggle · pytest 1,200+", {"size": 11, "color": DARK})]],
     0.5, 5.8, 9.0, 0.8)
notes(s, "The five LLM systems we compare on T1, all on Gemini 3.5 Flash Lite at temperature 0 with frozen prompts. Class-blind retrieves across every class and lets the model judge. Class-aware adds the class filter. Final agentic adds the temporal filter and the NLI verifier, so it abstains when its rationale is not entailed, which costs coverage. Long-context skips retrieval and reads the whole Directions up to 100,000 tokens. The structured comparator has the model extract 13 fields and lets a fixed rule decide. The comparator is best on ‘different’, 0.409, and on three-way F1, 0.616.")

# -- 9: use case diagram + deployment ----------------------------------------------------------------------------
s = new_slide("Use case diagram and deployment", "Applying the pipeline to a compliance team's routine work: the audit generator")
box(s, 1.6, 1.45, 3.5, 5.2, fill=RGBColor(0xFA, 0xF8, 0xF3), line=MAROON, line_w=1.5, radius=0.04)
text(s, "Audit generator", 1.6, 1.5, 3.5, 0.32, size=12, bold=True, color=MAROON, align=PP_ALIGN.CENTER)
cases = ["Generate audit pack", "Applicability register + changes", "Compliance calendar", "Cross-class differential",
         "Policy gap analysis (installed)", "Ask the AI assistant", "Review and sign off", "Export Excel · DOCX · PDF · ICS"]
cy = []
for i, c in enumerate(cases):
    y = 1.9 + i * 0.58
    cy.append(y + 0.22)
    box(s, 1.75, y, 3.2, 0.44, fill=WHITE, line=MAROON, shape=MSO_SHAPE.OVAL, label=c, size=10.5)


def actor(x, y, name, ic):
    # Name above the icon, so the association lines leaving the icon never cross it.
    icon_circle(s, ic, x, y, 0.6, fill=SLATE)
    text(s, name, x - 0.45, y - 0.32, 1.5, 0.3, size=10, bold=True, align=PP_ALIGN.CENTER)


actor(0.6, 2.0, "Compliance officer", "UserCheck")
actor(0.6, 4.35, "Policy owner", "FileText")
actor(5.4, 2.55, "Reviewer", "ClipboardCheck")
actor(5.4, 4.7, "RBI corpus", "Landmark")
for idx in (0, 1, 2, 3, 5):
    arrow(s, 1.22, 2.3, 1.75, cy[idx], color=MUTED, width=0.9, head=False)
arrow(s, 1.22, 4.65, 1.75, cy[4], color=MUTED, width=0.9, head=False)
for idx in (6, 7):
    arrow(s, 5.38, 2.85, 4.95, cy[idx], color=MUTED, width=0.9, head=False)
arrow(s, 5.38, 5.0, 4.95, cy[3], color=MUTED, width=0.9, head=False, dash=True)
text(s, "Deployment (live demo)", 6.45, 1.45, 3.05, 0.3, size=12, bold=True, color=MAROON)
flow = [(SLATE_SOFT, DARK, "Browser", "visitor or compliance team"),
        (WHITE, DARK, "Azure static website", "React build · 11 sample packs"),
        (MAROON, WHITE, "Azure Function (Python)", "generate · review · exports · jobs"),
        (WHITE, DARK, "Gemini API (free tier)", "writes the AI drafts"),
        (GREEN_SOFT, DARK, "ONNX bge + NLI verifier", "retrieves, then checks every sentence")]
for i, (fill, col, h, d) in enumerate(flow):
    y = 1.82 + i * 0.86
    box(s, 6.45, y, 3.05, 0.66, fill=fill, line=MAROON if fill == WHITE else None, color=col,
        label=[[(h, {"bold": True, "size": 11})], [(d, {"size": 9.5})]])
    if i < len(flow) - 1:
        arrow(s, 7.975, y + 0.67, 7.975, y + 0.85, width=1.25)
box(s, 6.45, 6.15, 3.05, 0.5, fill=AMBER_SOFT, line=None, label=[[("Installed: same code on 127.0.0.1 · local Qwen via Ollama · uploads stay inside", {"size": 9})]])
text(s, "Every row cites its RBI paragraph · decision support only, not legal advice", 1.6, 6.68, 3.5, 0.3, size=9, color=MUTED, italic=True, align=PP_ALIGN.CENTER)
notes(s, "The user enters a profile (class, as-of date, last review, activities) and gets an audit pack in which every row cites its RBI paragraph; reviewers confirm or dispute rows and sign off; exports go to Excel, DOCX, PDF, iCalendar and a JSON audit trail. Policy uploads run only in the installed version, so company documents never leave the network. Deployment: the public site is an Azure static website; Generate, review, exports and the AI assistant run on an Azure Function, where Gemini (free tier) writes drafts and the ONNX bge + NLI models retrieve evidence and check every sentence. The installed version runs the same code on the user's machine with a local Qwen model, so uploaded policies never leave the network.")


# -- 10: the product, key features (screenshots of the live site) -----------------------------------------------------------
s = new_slide("The product: key features", "Live at rbioblibench5qbvp2.z29.web.core.windows.net · benchmark explorer, audit generator, AI assistant")
SHOTS = HERE / "ui_shots"
tiles = [("1_home.jpg", "Spot the difference", "None of five AI systems noticed this one"),
         ("2_case.jpg", "Comparator vs LLMs", "Every LLM says ‘same’; only our comparator says ‘different’"),
         ("3_pack.jpg", "Audit pack in ~30 s", "Register, changes, calendar, differential, each row cited"),
         ("4_enforcement.jpg", "Penalty context", "Past RBI penalties on similar entities, linked to the release"),
         ("5_ask.jpg", "Verified AI answers", "Every sentence cited and NLI-checked, or an honest abstention"),
         ("6_memo.jpg", "Board memo and plan", "Every figure must match the pack's facts, or it is held back")]
W, H, GX, GY = 2.9, 2.15, 0.15, 0.62
for i, (f, h, d) in enumerate(tiles):
    col, row = i % 3, i // 3
    x, y = 0.5 + col * (W + GX), 1.42 + row * (H + GY)
    box(s, x - 0.03, y - 0.03, W + 0.06, H + 0.06, fill=None, line=LINE, shape=MSO_SHAPE.RECTANGLE, line_w=0.75)
    pic = s.shapes.add_picture(str(SHOTS / f), Inches(x), Inches(y), Inches(W), Inches(H))
    pic.name = f"Screenshot {i + 1}"
    numbered(s, i + 1, x - 0.12, y - 0.12, d=0.32, size=11)
    text(s, [[(h + "  ", {"bold": True, "size": 11, "color": MAROON}), (d, {"size": 9.5, "color": GREY})]], x, y + H + 0.04, W, 0.5)
notes(s, "Six things to notice on the live site, which we will now show. One: the home page opens with a real case that none of the five AI systems got right. Two: on a case page, every LLM says same, the expert says different, and only our comparator catches it, field by field. Three: the audit generator builds a full audit pack in about thirty seconds, every row citing its RBI paragraph. Four: past RBI penalties on similar entities, linked to the press releases. Five: the AI assistant cites every sentence and the NLI verifier holds back what it cannot confirm, or it abstains honestly. Six: a board memo where every figure must match the pack's own facts.")

# -- 8: result analysis RQ1 + RQ2 -------------------------------------------------------------------------------------------
s = new_slide("Result analysis: RQ1 and RQ2", "The class filter doubles retrieval quality, but LLMs still miss most real differences")
text(s, "RQ1 · counterpart retrieval, nDCG@10", 0.4, 1.4, 4.6, 0.3, size=12, bold=True, color=MAROON)
cd = CategoryChartData()
cd.categories = ["BM25", "Dense", "Hybrid", "Hybrid − src", "Class-aware"]
cd.add_series("xclass_t1 (291)", (0.458, 0.421, 0.443, 0.464, 0.894))
cd.add_series("xclass_p2002 (53)", (0.277, 0.334, 0.319, 0.337, 0.741))
cd.add_series("supp_p2003 (25)", (0.616, 0.362, 0.504, 0.504, 0.675))
ch = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.3), Inches(1.7), Inches(4.7), Inches(3.55), cd).chart
style_chart(ch, legend=True, size=9)
quiet_axes(ch, vmin=0, vmax=1.0, fmt="0.0")
color_series(ch, [MAROON, AMBER, SLATE])
ch.plots[0].gap_width = 55
ch.plots[0].overlap = -5
labels(ch.plots[0], fmt="0.00", size=7)
text(s, "RQ2 · T1 on the 106-item gold", 5.15, 1.4, 4.4, 0.3, size=12, bold=True, color=MAROON)
cd = CategoryChartData()
cd.categories = ["P2-002 candidates", "Class-blind LLM", "Class-aware LLM", "Final agentic", "Long-context", "Structured comparator"]
cd.add_series("3-way flag F1", (0.459, 0.602, 0.551, 0.483, 0.509, 0.616))
cd.add_series("‘different’ F1", (0.000, 0.321, 0.154, 0.047, 0.074, 0.409))
ch = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(5.1), Inches(1.7), Inches(4.6), Inches(3.55), cd).chart
style_chart(ch, legend=True, size=9)
quiet_axes(ch, vmin=0, vmax=0.8, fmt="0.0")
ch.category_axis.reverse_order = True
ch.value_axis.tick_label_position = XL_TICK_LABEL_POSITION.LOW
color_series(ch, [SLATE, MAROON])
ch.plots[0].gap_width = 45
labels(ch.plots[0], fmt="0.00", size=8)
for i, (v, l, col) in enumerate([("+0.451", "nDCG@10 from the class filter [+0.421, +0.481]", MAROON),
                                 ("−0.050", "but no significant effect on T1 judgement [−0.133, +0.027]", SLATE),
                                 ("56 / 78", "gold ‘different’ units missed by every LLM system", MAROON),
                                 ("262 / 350", "‘different’ errors with the counterpart already in context", AMBER)]):
    x = 0.5 + i * 2.28
    box(s, x, 5.45, 2.15, 1.2, fill=MAROON_SOFT if col != AMBER else AMBER_SOFT, line=None, radius=0.08,
        label=[[(v, {"bold": True, "size": 18, "color": col, "font": HEAD})], [(l, {"size": 10, "color": DARK})]])
notes(s, "RQ1: the class filter raises nDCG@10 from 0.443 to 0.894 on the T1-derived set and helps on all three sets, but on T1 judgement it makes no significant difference. RQ2: no LLM system significantly beats the embedding baseline on collapsed F1; the ‘different’ judgement is the core failure, 56 of 78 missed by every system, mostly with the counterpart already in context: reasoning, not retrieval. The structured comparator lifts ‘different’ F1 to 0.409.")

# -- 20: RQ3 --------------------------------------------------------------------------------------------------------------------------------
s = new_slide("Result analysis: RQ3, RePASs rewards copying", "RePASs composite by answer type on 30 T4 questions (mean)")
cd = CategoryChartData()
cd.categories = ["Genuine", "Concatenated", "Negated", "Off-topic"]
cd.add_series("RePASs", (0.371, 0.746, 0.049, 0.229))
gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.35), Inches(1.45), Inches(5.9), Inches(5.2), cd)
ch = gf.chart
style_chart(ch, legend=False, size=12)
ch.has_title = False
quiet_axes(ch, vmin=0, vmax=0.9, fmt="0.0")
pl = ch.plots[0]
pl.gap_width = 55
pl.vary_by_categories = False
ser = pl.series[0]
for idx, col in enumerate([SLATE, MAROON, MUTED, MUTED]):
    pt = ser.points[idx]
    pt.format.fill.solid()
    pt.format.fill.fore_color.rgb = col
labels(pl, fmt="0.000", size=12)
stat(s, "+0.375", "concatenated − genuine [+0.325, +0.427]: gameability reproduces (pre-registered)", 6.5, 1.5, 3.1)
stat(s, "ρ 0.731", "RePASs vs human faithfulness ratings", 6.5, 3.0, 3.1, color=SLATE)
stat(s, "ρ 0.008", "RePASs vs “does it answer the question?”", 6.5, 4.25, 3.1, color=AMBER)
text(s, "An exploratory repair ranked genuine answers first but lost agreement with human faithfulness (ρ −0.126): not usable.", 6.5, 5.6, 3.1, 1.0, size=12, color=GREY)
notes(s, "As on ObliQA, simply concatenating the retrieved obligation sentences scores 0.375 higher than a genuine answer. RePASs follows faithfulness but not relevance, so a faithfulness metric needs a relevance term that copied text cannot satisfy. → Switch to the LIVE DEMO now (website, then audit generator), about 4 minutes, then come back for the conclusion.")
# -- 12: additional experiments ------------------------------------------------------------------------------------------------
s = new_slide("Result analysis: additional experiments", "Pre-registered checks: a reranker, a bigger open model, another benchmark, another framework")
text(s, "Ext. 8 · IndiaFinBench accuracy by question type (268 of 406 items)", 0.4, 1.4, 4.9, 0.3, size=12, bold=True, color=MAROON)
cd = CategoryChartData()
cd.categories = ["Regulatory interpretation", "Temporal reasoning", "Contradiction detection", "Numerical reasoning"]
cd.add_series("Accuracy", (0.951, 0.742, 0.729, 0.561))
ch = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(0.3), Inches(1.7), Inches(5.0), Inches(3.4), cd).chart
style_chart(ch, legend=False, size=10)
ch.has_title = False
quiet_axes(ch, vmin=0, vmax=1.0, fmt="0.0")
ch.category_axis.reverse_order = True
ch.value_axis.tick_label_position = XL_TICK_LABEL_POSITION.LOW
color_series(ch, [MAROON])
ch.plots[0].gap_width = 60
labels(ch.plots[0], fmt="0.000", size=10)
box(s, 0.5, 5.25, 4.75, 1.35, fill=MAROON_SOFT, line=None, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
    label=[[("Overall 0.757 ", {"bold": True, "size": 16, "color": MAROON, "font": HEAD}), ("[0.703, 0.805]", {"size": 11})],
           [("Frozen answer step, automated scoring only (a lower bound). Dataset card: twelve models 70.4–89.7%, non-specialist humans 69.0%.", {"size": 10.5})]])
cards = [("Filter", "Ext. 3 · cross-encoder reranking", "−0.064", "class-blind 3-way F1 (0.602 → 0.538) [−0.115, −0.017]: reranking hurts", AMBER),
         ("Brain", "Ext. 4 · gpt-oss-120b (103 items)", "0.614 vs 0.624", "3-way F1 vs Gemini, no significant change; ‘different’ F1 0.289 vs 0.353: scale does not fix it", MAROON),
         ("Workflow", "Ext. 9 · LangGraph port", "4 × 106 identical", "prompts and outputs match the sealed runs for four systems, 0 API calls", GREEN)]
for i, (ic, h, v, d, col) in enumerate(cards):
    y = 1.45 + i * 1.75
    box(s, 5.55, y, 3.95, 1.58, fill=WHITE, line=LINE, radius=0.08)
    icon_circle(s, ic, 5.7, y + 0.18, 0.55, fill=col)
    text(s, h, 6.4, y + 0.12, 3.0, 0.3, size=11.5, bold=True)
    text(s, v, 6.4, y + 0.42, 3.0, 0.42, size=17, bold=True, color=col, font=HEAD)
    text(s, d, 5.7, y + 0.88, 3.7, 0.66, size=10, color=GREY)
notes(s, "Four pre-registered extensions. Reranking with a MiniLM cross-encoder lowered class-blind three-way F1 by 0.064, so retrieval order was not the bottleneck. A larger open model, gpt-oss-120b, matched Gemini on three-way F1 but did no better on ‘different’, so model scale alone does not solve the core failure. On IndiaFinBench, our frozen answer step scored 0.757 on the completed 268 items, strongest on regulatory interpretation and weakest on numerical reasoning. A LangGraph port reproduced every prompt and output exactly.")

# -- 23: conclusion and future scope -------------------------------------------------------------------------------------
s = new_slide("Conclusion and future scope", "Retrieval accuracy alone does not measure cross-class obligation reasoning")
concl = [("RQ1", "Applicability", "Yes for retrieval · no for judgement", "class filter +0.451 nDCG@10; no significant T1 difference", SLATE),
         ("RQ2", "Differential obligation", "Not yet, with free-form LLMs", "56 of 78 missed by all; comparator ‘different’ F1 0.409, recovers 26 of 56", MAROON),
         ("RQ3", "Metric integrity", "Yes: RePASs is gameable", "concatenation +0.375; a metric needs a relevance term copying cannot satisfy", AMBER)]
for i, (rq, h, v, e, col) in enumerate(concl):
    y = 1.45 + i * 0.98
    box(s, 0.5, y, 0.95, 0.85, fill=col, line=None, label=rq, size=18, bold=True, color=WHITE, font=HEAD)
    box(s, 1.55, y, 7.95, 0.85, fill=WHITE, line=LINE, radius=0.08, align=PP_ALIGN.LEFT,
        label=[[(h + ":  ", {"bold": True, "size": 14}), (v, {"bold": True, "size": 14, "color": col})], [(e, {"size": 12, "color": GREY})]])
text(s, "Future scope", 0.5, 4.45, 3.0, 0.4, size=16, bold=True, color=MAROON, font=HEAD)
steps = [("Users", "Stronger labels", "independent second raters"), ("Brain", "Frontier LLMs", "rerun T1 and comparator"),
         ("Target", "Better comparator", "retrieved evidence, topic matching"), ("Gauge", "Larger T3 / T4", "and a working RePASs repair"),
         ("Rocket", "Real-world pilot", "audit generator with a compliance team")]
arrow(s, 0.6, 5.2, 9.4, 5.2, color=LINE, width=3.5, head=True)
for i, (ic, h, d) in enumerate(steps):
    x = 0.55 + i * 1.82
    icon_circle(s, ic, x + 0.55, 4.88, 0.62, fill=MAROON if i == 0 else (SLATE if i % 2 else RGBColor(0x8A, 0x3E, 0x3C)))
    text(s, h, x, 5.55, 1.72, 0.35, size=13, bold=True, align=PP_ALIGN.CENTER)
    text(s, d, x, 5.88, 1.72, 0.55, size=11, color=GREY, align=PP_ALIGN.CENTER)
notes(s, "Answers to the three research questions (Table 6.1 of the report). Delivered: a 381-Direction corpus, a four-task benchmark, tested code, a pointer-only release, the website, the audit generator and the paper. Future scope, most urgent first: label reliability, stronger models, a comparator that uses retrieved evidence with better topic matching, larger T3/T4 studies, and a pilot of the audit generator with a compliance team.")

# -- 11: paper status + SDG mapping -----------------------------------------------------------------------------------------
s = new_slide("Paper status and SDG mapping")
box(s, 0.5, 1.2, 9.0, 0.95, fill=WHITE, line=LINE, radius=0.06, align=PP_ALIGN.LEFT,
    label=[[("“Same Subject, Different Duties: RBI-ObliBench for Differential Obligations across Entity Classes”", {"bold": True, "size": 13, "font": HEAD})],
           [("Submitted to AISIGH-SD 2026 (IEEE Bhubaneswar Section) · Paper ID 1954 · under review · accepted papers go to IEEE Xplore", {"size": 11, "color": GREY})]])
tl = [("10 Oct 2026", "Submitted (CMT)", "done"), ("15 Nov 2026", "Acceptance notice", "next"),
      ("30 Nov 2026", "Camera-ready", "later"), ("10 Dec 2026", "Registration", "later"), ("28–30 Dec 2026", "Conference", "later")]
arrow(s, 1.2, 2.85, 8.6, 2.85, color=LINE, width=3.0, head=False)
for i, (dt, ev, st) in enumerate(tl):
    x = 0.75 + i * 1.8
    fill = GREEN if st == "done" else (AMBER if st == "next" else WHITE)
    box(s, x + 0.7, 2.67, 0.36, 0.36, fill=fill, line=MAROON if st == "later" else None, shape=MSO_SHAPE.OVAL, line_w=1.25)
    if st == "done":
        icon(s, "CheckCircle2", x + 0.75, 2.72, 0.26, "w")
    text(s, dt, x, 2.27, 1.75, 0.35, size=11.5, bold=True, align=PP_ALIGN.CENTER, color=MAROON)
    text(s, ev, x, 3.07, 1.75, 0.35, size=11, align=PP_ALIGN.CENTER, color=DARK)
text(s, [[("Proof: ", {"bold": True, "color": GREEN, "size": 11}), ("CMT confirmation e-mail of 10 Oct 2026 (Annexure III of the report); the decision is due 15 Nov 2026.", {"size": 11, "color": GREY})]],
     0.5, 3.48, 9.0, 0.3)
sdgs = [("16", "Peace, Justice and Strong Institutions", RGBColor(0x00, 0x68, 0x9D), "16.6 transparent, accountable institutions",
         "Every audit row cites its RBI paragraph; sealed system answers; human sign-off"),
        ("8", "Decent Work and Economic Growth", RGBColor(0xA2, 0x19, 0x42), "8.10 strengthen domestic financial institutions",
         "Banks, NBFCs and co-operative banks see which duties bind them and where they differ"),
        ("9", "Industry, Innovation and Infrastructure", RGBColor(0xFD, 0x69, 0x25), "9.5 enhance research and innovation",
         "Open benchmark, tested code and a pointer-only data release for Indian RegTech")]
for i, (n, name, col, tgt, how) in enumerate(sdgs):
    x = 0.5 + i * 3.05
    box(s, x, 3.95, 2.85, 0.95, fill=col, line=None, radius=0.04)
    text(s, n, x + 0.12, 3.97, 0.7, 0.85, size=30, bold=True, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)
    text(s, name.upper(), x + 0.85, 4.02, 1.95, 0.85, size=10.5, bold=True, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)
    box(s, x, 4.98, 2.85, 1.65, fill=WHITE, line=LINE, radius=0.06, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
        label=[[("Target " + tgt, {"bold": True, "size": 11, "color": col})], [("", {"size": 4})], [(how, {"size": 11})]])
notes(s, "The paper was submitted on 10 October through Microsoft CMT, Paper ID 1954; the decision is due on 15 November, after this presentation, and the CMT confirmation is in the report as proof. SDG 16 through transparent, citation-backed compliance; SDG 8 by helping domestic financial institutions meet their obligations; SDG 9 through open research infrastructure for Indian regulatory AI.")


# -- 12: references + thank you ---------------------------------------------------------------------------------------------
s = new_slide("References (selected)")
refs = ["[1] Reserve Bank of India, “Master Directions,” rbi.org.in, harvested Aug–Sep 2026.",
        "[6] P. Lewis et al., “Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks,” NeurIPS 2020.",
        "[7] T. Gokhan, K. Wang, I. Gurevych, T. Briscoe, “RIRAG: Regulatory Information Retrieval and Answer Generation,” arXiv:2409.05677, 2024.",
        "[9] S. Robertson, H. Zaragoza, “The Probabilistic Relevance Framework: BM25 and Beyond,” FnTIR 3(4), 2009.",
        "[13] S. Xiao et al., “C-Pack: Packed Resources for General Chinese Embeddings,” SIGIR 2024.",
        "[14] G. V. Cormack, C. L. A. Clarke, S. Büttcher, “Reciprocal Rank Fusion Outperforms Condorcet…,” SIGIR 2009.",
        "[17] S. Es et al., “RAGAS: Automated Evaluation of Retrieval Augmented Generation,” EACL 2024.",
        "[22] N. F. Liu et al., “Lost in the Middle: How Language Models Use Long Contexts,” TACL 12, 2024.",
        "[38] I. Chasandras et al., “AUEB-Archimedes at RIRAG-2025: Is Obligation Concatenation Really All You Need?” RegNLP 2025.",
        "[40] R. S. Pall, “IndiaFinBench,” arXiv:2604.19298, 2026.",
        "Full list: 44 references in the project report (IEEE style)."]
text(s, refs, 0.5, 1.25, 9.0, 4.3, size=13, color=DARK, spacing=6)
box(s, 0.5, 5.65, 9.0, 1.0, fill=MAROON, line=None, radius=0.08,
    label=[[("Thank you · Questions?", {"bold": True, "size": 20, "font": HEAD, "color": WHITE})],
           [("Group 10 · Akash Goyal · Karan Lokhande · Meer Magia · Mentor: Prof. Jish Elizabeth Joy · Live demo: rbioblibench5qbvp2.z29.web.core.windows.net", {"size": 11, "color": RGBColor(0xF0, 0xD8, 0xD6)})]])
notes(s, "Selected references; numbering matches the project report. Thank you; we are happy to take questions.")


prs.save(str(OUT))
print("saved", OUT, len(prs.slides), "slides")

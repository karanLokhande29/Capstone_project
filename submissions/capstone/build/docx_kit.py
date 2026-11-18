"""Small python-docx toolkit that applies the MPSTME capstone report format (Annexure A.8).

Font Times New Roman; text 12 pt at 1.5 line spacing; left margin 1.5", others 1"; chapter titles 18 pt bold,
section titles 14 pt bold, subsection titles 12 pt bold; figure captions below and table captions above, 10 pt;
header: project title (left) and academic year (right); footer: page number (right).
"""

import re

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_COLOR_INDEX, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

FONT = "Times New Roman"
PLACEHOLDER = re.compile(r"(«[^»]*»)")
MARKUP = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*|«[^»]*»)")


def _fonts(rpr_owner, size=None, bold=None):
    rpr = rpr_owner.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        rfonts.attrib.pop(qn(attr), None)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), FONT)


def add_field(paragraph, instr, placeholder=""):
    """Insert a complex field (PAGE, TOC, ...). Word fills it when fields are updated."""
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    begin.set(qn("w:dirty"), "true")
    run._r.append(begin)
    run = paragraph.add_run()
    text = OxmlElement("w:instrText")
    text.set(qn("xml:space"), "preserve")
    text.text = f" {instr} "
    run._r.append(text)
    run = paragraph.add_run()
    sep = OxmlElement("w:fldChar")
    sep.set(qn("w:fldCharType"), "separate")
    run._r.append(sep)
    paragraph.add_run(placeholder)
    run = paragraph.add_run()
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(end)


class Report:
    def __init__(self, title_short, academic_year):
        self.doc = Document()
        self.title_short = title_short
        self.year = academic_year
        self.chapter = 0
        self.fig_n = 0
        self.tab_n = 0
        self.cites = {}  # key -> number, in order of first citation
        self._styles()
        sec = self.doc.sections[0]
        self._page(sec)

    # ---------------------------------------------------------------- setup
    def _page(self, sec):
        sec.page_width, sec.page_height = Inches(8.27), Inches(11.69)  # A4
        sec.left_margin = Inches(1.5)
        sec.right_margin = sec.top_margin = sec.bottom_margin = Inches(1)
        sec.header_distance = sec.footer_distance = Inches(0.5)

    def _styles(self):
        st = self.doc.styles
        normal = st["Normal"]
        normal.font.name = FONT
        normal.font.size = Pt(12)
        _fonts(normal.element)
        pf = normal.paragraph_format
        pf.line_spacing = 1.5
        pf.space_after = Pt(6)
        for name, size, before, after in (("Heading 1", 18, 0, 18), ("Heading 2", 14, 12, 6),
                                          ("Heading 3", 12, 10, 4)):
            s = st[name]
            s.font.name = FONT
            s.font.size = Pt(size)
            s.font.bold = True
            s.font.italic = False
            s.font.color.rgb = RGBColor(0, 0, 0)
            _fonts(s.element)
            s.paragraph_format.space_before = Pt(before)
            s.paragraph_format.space_after = Pt(after)
            s.paragraph_format.line_spacing = 1.15
            s.paragraph_format.keep_with_next = True
        st["Heading 1"].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
        from docx.enum.style import WD_STYLE_TYPE
        for name in ("Figure Caption", "Table Caption"):
            s = st.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
            s.base_style = normal
            s.font.size = Pt(10)
            s.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
            s.paragraph_format.line_spacing = 1.15
            s.paragraph_format.space_before = Pt(4)
            s.paragraph_format.space_after = Pt(10)
        st["Table Caption"].paragraph_format.keep_with_next = True
        for name in ("TOC 1", "TOC 2", "TOC 3"):
            try:
                s = st[name]
            except KeyError:
                s = st.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
            s.base_style = normal
            s.paragraph_format.line_spacing = 1.15
            s.paragraph_format.space_after = Pt(3)
        st["List Bullet"].font.name = FONT
        st["List Number"].font.name = FONT

    def new_section(self, page_format=None, start=None, header=True):
        sec = self.doc.add_section(WD_SECTION.NEW_PAGE)
        self._page(sec)
        sec.header.is_linked_to_previous = False
        sec.footer.is_linked_to_previous = False
        for part in (sec.header, sec.footer):
            for p in part.paragraphs:
                p.text = ""
        if page_format:
            pg = OxmlElement("w:pgNumType")
            pg.set(qn("w:fmt"), page_format)
            if start:
                pg.set(qn("w:start"), str(start))
            sec._sectPr.append(pg)
        if header:
            hp = sec.header.paragraphs[0]
            # The Header style carries default centre (3.25") and right (6.5") tabs; clear them so the year
            # always lands on the right margin.
            for pos in (3.25, 6.5):
                hp.paragraph_format.tab_stops.add_tab_stop(Inches(pos), WD_TAB_ALIGNMENT.CLEAR)
            hp.paragraph_format.tab_stops.add_tab_stop(Inches(5.77), WD_TAB_ALIGNMENT.RIGHT)
            r = hp.add_run(f"{self.title_short}\t{self.year}")
            r.font.size = Pt(10)
            self._border(hp, "bottom")
            fp = sec.footer.paragraphs[0]
            fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            add_field(fp, "PAGE", "1")
        return sec

    def _border(self, paragraph, side):
        ppr = paragraph._p.get_or_add_pPr()
        bdr = OxmlElement("w:pBdr")
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "6")
        el.set(qn("w:space"), "1")
        el.set(qn("w:color"), "808080")
        bdr.append(el)
        ppr.append(bdr)

    # ---------------------------------------------------------------- text
    def cite(self, text):
        def repl(m):
            nums = []
            for key in [k.strip().lstrip("@") for k in m.group(1).split(",")]:
                if key not in self.cites:
                    self.cites[key] = len(self.cites) + 1
                nums.append(self.cites[key])
            return "[" + ", ".join(str(n) for n in nums) + "]"
        return re.sub(r"\[(@[^\]]+)\]", repl, text)

    def runs(self, paragraph, text, size=None, bold=None):
        """Add text with **bold**, *italic* and «placeholder» (yellow highlight) markup and [@key] citations."""
        text = self.cite(text)
        for part in MARKUP.split(text):
            if not part:
                continue
            if part.startswith("**") or (part.startswith("*") and len(part) > 2 and not part.startswith("«")):
                inner = part[2:-2] if part.startswith("**") else part[1:-1]
                for sub in PLACEHOLDER.split(inner):
                    if not sub:
                        continue
                    r = paragraph.add_run(sub.strip("«»"))
                    if part.startswith("**"):
                        r.bold = True
                    else:
                        r.italic = True
                    if sub.startswith("«"):
                        r.font.highlight_color = WD_COLOR_INDEX.YELLOW
                    if size:
                        r.font.size = Pt(size)
                continue
            elif part.startswith("«"):
                r = paragraph.add_run(part[1:-1])
                r.font.highlight_color = WD_COLOR_INDEX.YELLOW
            else:
                r = paragraph.add_run(part)
            if size:
                r.font.size = Pt(size)
            if bold:
                r.bold = True
        return paragraph

    def p(self, text, align=WD_ALIGN_PARAGRAPH.JUSTIFY, size=None, bold=None, space_after=None, style=None):
        para = self.doc.add_paragraph(style=style)
        para.alignment = align
        if space_after is not None:
            para.paragraph_format.space_after = Pt(space_after)
        return self.runs(para, text, size=size, bold=bold)

    def center(self, text, size=12, bold=False, space_after=6, underline=False):
        para = self.p(text, align=WD_ALIGN_PARAGRAPH.CENTER, size=size, bold=bold, space_after=space_after)
        para.paragraph_format.line_spacing = 1.15
        if underline:
            for r in para.runs:
                r.underline = True
        return para

    def bullets(self, items, numbered=False):
        for n, it in enumerate(items, 1):
            if numbered:
                para = self.doc.add_paragraph()
                para.paragraph_format.left_indent = Inches(0.35)
                para.paragraph_format.first_line_indent = Inches(-0.3)
                para.paragraph_format.tab_stops.add_tab_stop(Inches(0.35))
                it = f"{n}.\t{it}"
            else:
                para = self.doc.add_paragraph(style="List Bullet")
            para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            para.paragraph_format.space_after = Pt(3)
            self.runs(para, it)

    def page_break(self):
        self.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    def blank(self, n=1):
        for _ in range(n):
            self.doc.add_paragraph().paragraph_format.space_after = Pt(0)

    # ---------------------------------------------------------------- headings
    def chapter_heading(self, title, numbered=True, new_page=True):
        if numbered:
            self.chapter += 1
            self.fig_n = self.tab_n = 0
            text = f"Chapter {self.chapter}: {title}"
        else:
            text = title
        h = self.doc.add_heading(text, level=1)
        h.paragraph_format.page_break_before = new_page
        return h

    def h2(self, text):
        return self.doc.add_heading(text, level=2)

    def h3(self, text):
        return self.doc.add_heading(text, level=3)

    def front_title(self, text):
        """A centred 18 pt title that does not enter the table of contents."""
        para = self.center(f"**{text}**", size=18, space_after=18)
        para.paragraph_format.page_break_before = True
        return para

    # ---------------------------------------------------------------- floats
    def _label(self, kind):
        if kind == "fig":
            self.fig_n += 1
            n = self.fig_n
        else:
            self.tab_n += 1
            n = self.tab_n
        prefix = self.chapter if self.chapter else "A"
        return f"{prefix}.{n}"

    def figure(self, path, caption, width=6.0, label_prefix=None):
        para = self.doc.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        para.paragraph_format.keep_with_next = True
        para.add_run().add_picture(str(path), width=Inches(width))
        label = label_prefix or self._label("fig")
        cap = self.doc.add_paragraph(style="Figure Caption")
        self.runs(cap, f"**Fig. {label}** {caption}")
        return label

    def table(self, caption, header, rows, widths, font=10, label_prefix=None, align_first_left=True):
        label = label_prefix or self._label("tab")
        cap = self.doc.add_paragraph(style="Table Caption")
        self.runs(cap, f"**Table {label}** {caption}")
        t = self.doc.add_table(rows=1, cols=len(header))
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, h in enumerate(header):
            self._cell(t.rows[0].cells[i], h, font, bold=True, shade="D9D9D9", width=widths[i],
                       align=WD_ALIGN_PARAGRAPH.CENTER)
        self._repeat_header(t.rows[0])
        for row in rows:
            cells = t.add_row().cells
            for i, v in enumerate(row):
                numeric = re.fullmatch(r"[*\d\s.,\[\]+\-\u2212/()%:\u00d7]+(\(reproduces\))?", str(v).strip("*"))
                al = WD_ALIGN_PARAGRAPH.CENTER if numeric and not (i == 0 and align_first_left) \
                    else WD_ALIGN_PARAGRAPH.LEFT
                self._cell(cells[i], str(v), font, width=widths[i], align=al)
        after = self.doc.add_paragraph()
        after.paragraph_format.space_after = Pt(4)
        return label

    def _repeat_header(self, row):
        trpr = row._tr.get_or_add_trPr()
        el = OxmlElement("w:tblHeader")
        el.set(qn("w:val"), "true")
        trpr.append(el)

    def _cell(self, cell, text, font, bold=False, shade=None, width=None, align=WD_ALIGN_PARAGRAPH.LEFT):
        cell.width = Inches(width)
        para = cell.paragraphs[0]
        para.alignment = align
        para.paragraph_format.line_spacing = 1.0
        para.paragraph_format.space_after = Pt(1)
        para.paragraph_format.space_before = Pt(1)
        self.runs(para, text, size=font, bold=bold or None)
        if shade:
            tcpr = cell._tc.get_or_add_tcPr()
            sh = OxmlElement("w:shd")
            sh.set(qn("w:val"), "clear")
            sh.set(qn("w:color"), "auto")
            sh.set(qn("w:fill"), shade)
            tcpr.append(sh)

    def borderless_table(self, rows, widths, font=12):
        t = self.doc.add_table(rows=0, cols=len(widths))
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for row in rows:
            cells = t.add_row().cells
            for i, (text, align) in enumerate(row):
                self._cell(cells[i], text, font, width=widths[i], align=align)
        return t

    # ---------------------------------------------------------------- lists
    def toc(self, instr, placeholder):
        para = self.doc.add_paragraph()
        add_field(para, instr, placeholder)

    def save(self, path, update_fields_on_open=True):
        if update_fields_on_open:
            upd = OxmlElement("w:updateFields")
            upd.set(qn("w:val"), "true")
            self.doc.settings.element.append(upd)
        self.doc.save(str(path))

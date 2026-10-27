"""Exports: Excel workbook, DOCX and PDF report, .ics calendar, JSON audit trail.

Every export carries the corpus snapshot date and sha256, the tool and rules versions, the as-of date, the entity
profile, the validation box and the disclaimer. Uploaded policy text appears only as matched-clause excerpts in the
user's own Excel / DOCX / PDF report; the JSON audit trail records the uploaded files' hashes, never their text.
"""

from __future__ import annotations

import io
import json
from datetime import date, timedelta
from typing import Any, Mapping, Sequence

from src.auditgen import calendar_extract as CAL
from src.auditgen.review import REVIEW_STATUSES

SHEETS = ("Summary", "Applicability", "Changes", "Calendar", "Differential", "Enforcement", "Gap analysis", "Sources", "About")
REVIEW_COLS = ["review_status", "reviewer", "note", "timestamp"]
COLUMNS = {
    "Applicability": ["row_id", "obligation_id", "md_id", "direction_title", "section", "clause", "paragraph_id", "excerpt",
                      "applies_to", "status", "effective_from", "amended_by", "governing_instrument", "deadline_frequency",
                      "subject_family", "source_url", "confidence", "needs_review", "hidden_reason", "scope_note"],
    "Changes": ["row_id", "md_id", "direction_title", "paragraph_id", "change", "excerpt", "governing_instrument",
                "governing_title", "instrument_date", "effective", "governing_url", "source_url", "confidence", "needs_review"],
    "Calendar": ["row_id", "md_id", "direction_title", "paragraph_id", "kind", "frequency", "offset_days", "summary", "phrase",
                 "next_due", "confidence", "verify", "source_url"],
    "Differential": ["row_id", "source_class", "target_class", "md_id", "direction_title", "paragraph_id", "excerpt",
                     "differential", "confidence", "semantic_score", "lexical_score", "counterpart_paragraph_id",
                     "counterpart_title", "counterpart_excerpt", "counterpart_url", "source_url", "needs_review", "caution"],
    "Enforcement": ["row_id", "md_id", "direction_title", "subject_family", "penalty_count", "first_date", "last_date",
                    "press_release_links", "cited_subjects", "link_basis", "obligations_in_register", "source_url", "label",
                    "link_note", "needs_review"],
    "Gap analysis": ["row_id", "md_id", "direction_title", "paragraph_id", "excerpt", "coverage", "confidence",
                     "matched_clause_ids", "matched_clause_excerpts", "best_entailment", "best_cosine", "enforcement_risk",
                     "explanation", "source_url", "needs_review"],
}
SECTION_OF = {"Applicability": "register", "Changes": "changes", "Calendar": "calendar", "Differential": "differential",
              "Enforcement": "enforcement", "Gap analysis": "gaps"}


def _rows(pack: Mapping[str, Any], sec: str) -> list[dict[str, Any]]:
    v = pack.get(sec)
    return (v.get("rows") or []) if isinstance(v, dict) else (v or [])


def _cell(row: Mapping[str, Any], col: str) -> Any:
    if col == "amended_by":
        return "; ".join(f"{a['id']} ({a.get('effective')})" for a in row.get("amended_by") or [])
    if col == "next_due":
        return ", ".join((row.get("next_due") or [])[:6])
    if col == "press_release_links":
        return "\n".join(f"{p['date']}: {p['url']}" for p in row.get("press_releases") or [])
    if col == "cited_subjects":
        return "; ".join(row.get("cited_subjects") or [])
    if col == "link_basis":
        return "; ".join(row.get("link_basis") or [])
    if col == "matched_clause_ids":
        return "; ".join(c["clause_id"] for c in row.get("matched_clauses") or [])
    if col == "matched_clause_excerpts":
        return "\n".join(c["excerpt"] for c in row.get("matched_clauses") or [])
    if col == "best_entailment":
        return max((c["entailment"] for c in row.get("top_clauses") or []), default=None)
    if col == "best_cosine":
        return max((c["cosine"] for c in row.get("top_clauses") or []), default=None)
    v = row.get(col)
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    return v


def about_lines(pack: Mapping[str, Any]) -> list[tuple[str, str]]:
    a = pack["about"]
    v = a["validation"]
    ap, tm, ca, ga, di = v["applicability"], v["temporal"], v["calendar"], v["gap_analysis"], v["differential"]
    gap_txt = (f"SYNTHETIC check: 'missing' recall {ga.get('missing_recall')} (precision {ga.get('missing_precision')}); "
               f"not-covered recall {ga.get('not_covered_recall')}; {ga.get('note', '')}") if ga.get("kind") == "synthetic" else "not computed"
    cal_txt = (f"precision {ca['precision']} on {ca['n']} checks" if ca.get("status") == "done"
               else f"pending ({ca.get('labelled', 0)}/{ca.get('n', 30)} labelled in {ca.get('sheet', 'the check sheet')})")
    return [
        ("Disclaimer", a["disclaimer"]),
        ("Tool", f"{a['tool']} {a['tool_version']} · rules {a['rules_version']} (sha256 {a['rules_sha256'][:12]}…)"),
        ("Corpus snapshot", f"{a['corpus']['kind']} · {a['corpus']['snapshot_date']} · sha256 {a['corpus']['sha256']}"),
        ("Freshness", a["freshness"]["message"]),
        ("As-of date", a["as_of"]), ("Last review", a["last_review"]),
        ("Entity profile", json.dumps(a["entity_profile"], ensure_ascii=False)),
        ("Validation: applicability", f"precision {ap.get('precision')} {ap.get('precision_ci')}, recall {ap.get('recall')} "
                                      f"{ap.get('recall_ci')} vs T1 gold v1 ({ap.get('units', '')}). {ap.get('note', '')}"),
        ("Validation: temporal status", f"accuracy {tm.get('accuracy')} {tm.get('accuracy_ci')} on {tm.get('n_items')} T3 items. {tm.get('note', '')}"),
        ("Validation: calendar extraction", cal_txt),
        ("Validation: gap analysis", gap_txt),
        ("Caution: differential", di.get("note", "")),
        ("Privacy", a["privacy"]), ("Excerpts", a["excerpt_rule"]),
        ("Rows dropped (no citation)", json.dumps(pack.get("dropped_without_citation") or {}) +
         " · a row is dropped when its Direction has no title or link in the corpus (no citation, no row)"),
        ("Pack", f"{pack['pack_id']} · created {pack['created_utc']}" + (f" · derived from {pack['derived_from']}" if pack.get("derived_from") else "")),
        ("Sign-off", (f"{pack['signoff']['signer']} at {pack['signoff']['signed_utc']} "
                      f"({pack['signoff']['progress']['reviewed']}/{pack['signoff']['progress']['total']} rows reviewed)")
         if pack.get("signoff") else "not signed off"),
    ]


def sources(pack: Mapping[str, Any]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for sec in ("register", "changes", "calendar", "differential", "enforcement", "gaps"):
        for r in _rows(pack, sec):
            if r.get("md_id") and r["md_id"] not in seen:
                seen[r["md_id"]] = {"kind": "Master Direction", "id": r["md_id"], "title": r.get("direction_title"), "url": r.get("source_url")}
            for a in r.get("amended_by") or []:
                seen.setdefault(a["id"], {"kind": "Amendment Direction", "id": a["id"], "title": "", "url": a.get("url")})
            if (r.get("governing_instrument") or "").startswith(("amd_", "wdr_")):
                seen.setdefault(r["governing_instrument"], {"kind": "Amendment / withdrawal", "id": r["governing_instrument"],
                                                             "title": r.get("governing_title", ""), "url": r.get("governing_url")})
            for p in r.get("press_releases") or []:
                seen.setdefault(p["id"], {"kind": "Press release (penalty)", "id": p["id"], "title": p.get("entity") or "", "url": p.get("url")})
    return sorted(seen.values(), key=lambda s: (s["kind"], s["id"]))


# -- Excel -------------------------------------------------------------------------------------------

def to_excel(pack: Mapping[str, Any]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    bold = Font(bold=True)
    head_fill = PatternFill("solid", fgColor="DCE6F1")
    ws = wb.active
    ws.title = "Summary"
    s = pack["summary"]
    ws.append(["RBI compliance audit pack", pack["profile"]["name"]])
    ws.append(["Disclaimer", pack["disclaimer"]])
    ws.append(["As of", pack["profile"]["as_of"]])
    ws.append(["Corpus", f"{pack['about']['corpus']['snapshot_date']} · sha256 {pack['about']['corpus']['sha256']}"])
    ws.append([])
    for k in ("register_visible", "register_hidden", "needs_review", "changes", "calendar_entries", "calendar_verify",
              "differential_rows", "differential_needs_review", "enforcement_directions", "enforcement_releases"):
        ws.append([k.replace("_", " "), s.get(k)])
    ws.append([])
    ws.append(["Status", "Obligations"])
    for k, v in sorted(s["by_status"].items()):
        ws.append([k, v])
    if s.get("gaps"):
        ws.append([])
        ws.append(["Gap analysis", json.dumps(s["gaps"])])
    ws.append([])
    ws.append(["Review progress", f"{s['review_progress']['reviewed']} / {s['review_progress']['total']}"])
    for c in ws["A"]:
        c.font = bold
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 110
    dv_list = '"' + ",".join(REVIEW_STATUSES) + '"'
    for sheet, cols in COLUMNS.items():
        w = wb.create_sheet(sheet)
        rows = _rows(pack, SECTION_OF[sheet])
        header = cols + REVIEW_COLS
        w.append(header)
        for r in rows:
            w.append([_cell(r, c) for c in cols] + [r.get(c, "") for c in REVIEW_COLS])
        for i, h in enumerate(header, 1):
            cell = w.cell(row=1, column=i)
            cell.font, cell.fill = bold, head_fill
            w.column_dimensions[get_column_letter(i)].width = 14 if h not in ("direction_title", "excerpt", "counterpart_excerpt",
                                                                                "matched_clause_excerpts", "phrase", "note") else 48
        url_cols = [i + 1 for i, h in enumerate(header) if h.endswith("url")]
        for row_i in range(2, len(rows) + 2):
            for ci in url_cols:
                c = w.cell(row=row_i, column=ci)
                if c.value:
                    c.hyperlink, c.style = c.value, "Hyperlink"
            for ci in range(1, len(header) + 1):
                w.cell(row=row_i, column=ci).alignment = Alignment(wrap_text=False, vertical="top")
        w.freeze_panes = "B2"
        if rows:
            w.auto_filter.ref = f"A1:{get_column_letter(len(header))}{len(rows) + 1}"
            dv = DataValidation(type="list", formula1=dv_list, allow_blank=True)
            col = get_column_letter(header.index("review_status") + 1)
            dv.add(f"{col}2:{col}{len(rows) + 1}")
            w.add_data_validation(dv)
        w.cell(row=len(rows) + 3, column=1, value=pack["disclaimer"]).font = Font(italic=True)
    w = wb.create_sheet("Sources")
    w.append(["kind", "id", "title", "url"])
    for src in sources(pack):
        w.append([src["kind"], src["id"], src["title"], src["url"]])
    w.freeze_panes = "A2"
    w = wb.create_sheet("About")
    for k, v in about_lines(pack):
        w.append([k, v])
    w.column_dimensions["A"].width = 32
    w.column_dimensions["B"].width = 140
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# -- report (DOCX / PDF) -------------------------------------------------------------------------------

REPORT_LIMIT = 150


def _report_tables(pack: Mapping[str, Any]) -> list[tuple[str, list[str], list[list[str]], int]]:
    def t(x, n=None):
        s = "" if x is None else str(x)
        return s if n is None or len(s) <= n else s[:n - 1] + "…"

    reg = [r for r in pack["register"] if not r["hidden"]]
    out = [("Applicability register (visible rows)", ["Direction", "Para", "Excerpt", "Status", "Conf.", "Review"],
            [[t(r["direction_title"], 50), r["paragraph_id"].split("::")[1], t(r["excerpt"]), r["status"], f"{r['confidence']:.2f}",
              ("needs review" if r["needs_review"] else "") + (f" · {r['review_status']}" if r["review_status"] != "unreviewed" else "")]
             for r in reg[:REPORT_LIMIT]], len(reg)),
           ("Change-impact log", ["Direction", "Para", "Change", "Instrument", "Effective"],
            [[t(r["direction_title"], 50), (r["paragraph_id"] or "Direction").split("::")[-1], r["change"], r["governing_instrument"],
              t(r.get("effective"))] for r in pack["changes"][:REPORT_LIMIT]], len(pack["changes"])),
           ("Compliance calendar", ["Next due", "What", "Kind", "Conf.", "Para"],
            [[", ".join(e["next_due"][:2]) or "event-triggered", t(e["summary"], 70), e["kind"], f"{e['confidence']:.2f}" + (" verify" if e["verify"] else ""),
              e["paragraph_id"]] for e in pack["calendar"][:REPORT_LIMIT]], len(pack["calendar"]))]
    if pack["differential"]:
        out.append(("Cross-class differential", ["Classes", "Para", "Call", "Score", "Counterpart"],
                    [[f"{r['source_class']} → {r['target_class']}", r["paragraph_id"], r["differential"], t(r["confidence"]),
                      t(r["counterpart_paragraph_id"])] for r in pack["differential"][:REPORT_LIMIT]], len(pack["differential"])))
    out.append(("Enforcement-risk view (not a prediction)", ["Direction", "Penalties", "Latest", "Basis"],
                [[t(r["direction_title"], 60), str(r["penalty_count"]), t(r["last_date"]), t("; ".join(r["link_basis"]), 40)]
                 for r in pack["enforcement"][:REPORT_LIMIT]], len(pack["enforcement"])))
    gaps = pack.get("gaps")
    if gaps:
        out.append(("Policy gap analysis (local models)", ["Para", "Coverage", "Conf.", "Matched clause", "Risk"],
                    [[r["paragraph_id"], r["coverage"], f"{r['confidence']:.2f}", t((r["matched_clauses"] or [{}])[0].get("excerpt", ""), 90),
                      str(r["enforcement_risk"])] for r in gaps["rows"][:REPORT_LIMIT]], len(gaps["rows"])))
    return out


def _exec_summary(pack: Mapping[str, Any]) -> list[str]:
    s = pack["summary"]
    lines = [f"{s['register_visible']} applicable obligations as of {pack['profile']['as_of']} "
             f"({s['register_hidden']} more kept but hidden: filtered by activity, deleted or not yet in force); "
             f"{s['needs_review']} need human review.",
             "By status: " + "; ".join(f"{k} {v}" for k, v in sorted(s["by_status"].items())) + ".",
             "Largest Directions: " + "; ".join(f"{d['direction_title'][:60]} ({d['obligations']})" for d in s["by_direction"][:5]) + ".",
             f"{s['changes']} changes since {pack['profile']['last_review']}.",
             f"{s['calendar_entries']} calendar entries ({s['calendar_verify']} marked verify); next 90 days: "
             + ("; ".join(f"{x['date']} {x['summary'][:50]}" for x in s["next_90_days"][:8]) or "none dated") + ".",
             f"Enforcement context: {s['enforcement_releases']} penalty releases against the class, linked to "
             f"{s['enforcement_directions']} Directions (prioritisation context only, not a prediction)."]
    if s.get("gaps"):
        lines.append(f"Policy gaps: {s['gaps']}. Highest-risk missing: "
                     + "; ".join(f"{g['paragraph_id']} (risk {g['enforcement_risk']})" for g in s["highest_risk_gaps"][:5]) + ".")
    return lines


def to_docx(pack: Mapping[str, Any]) -> bytes:
    import docx
    from docx.shared import Pt

    d = docx.Document()
    st = d.styles["Normal"]
    st.font.name, st.font.size = "Calibri", Pt(9)
    d.add_heading(f"RBI compliance audit pack: {pack['profile']['name']}", 0)
    p = d.add_paragraph()
    p.add_run(pack["disclaimer"]).bold = True
    d.add_heading("Executive summary", 1)
    for line in _exec_summary(pack):
        d.add_paragraph(line, style="List Bullet")
    for title, header, rows, total in _report_tables(pack):
        d.add_heading(title, 1)
        if total > len(rows):
            d.add_paragraph(f"First {len(rows)} of {total} rows; the full table is in the Excel export.")
        tbl = d.add_table(rows=1, cols=len(header))
        tbl.style = "Light Grid Accent 1"
        for i, h in enumerate(header):
            tbl.rows[0].cells[i].text = h
        for r in rows:
            cells = tbl.add_row().cells
            for i, v in enumerate(r):
                cells[i].text = str(v)
    d.add_heading("About this pack", 1)
    for k, v in about_lines(pack):
        p = d.add_paragraph()
        p.add_run(k + ": ").bold = True
        p.add_run(str(v))
    d.add_paragraph("Every row cites its RBI source in the Excel export (Direction, paragraph id, rbi.org.in link).")
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def to_pdf(pack: Mapping[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape

    ss = getSampleStyleSheet()
    small = ss["BodyText"].clone("small", fontSize=7.5, leading=9)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                            title=f"Audit pack {pack['pack_id']}")
    disc = pack["disclaimer"]

    def footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.drawString(12 * mm, 7 * mm, f"{disc}  ·  corpus {pack['about']['corpus']['snapshot_date']} sha256 "
                                          f"{pack['about']['corpus']['sha256'][:16]}…  ·  as of {pack['profile']['as_of']}  ·  page {_doc.page}")
        canvas.restoreState()

    el = [Paragraph(escape(f"RBI compliance audit pack: {pack['profile']['name']}"), ss["Title"]),
          Paragraph("<b>" + escape(disc) + "</b>", ss["BodyText"]), Spacer(1, 4 * mm), Paragraph("Executive summary", ss["Heading2"])]
    el += [Paragraph("• " + escape(x), small) for x in _exec_summary(pack)]
    for title, header, rows, total in _report_tables(pack):
        el += [Spacer(1, 3 * mm), Paragraph(escape(title), ss["Heading2"])]
        if total > len(rows):
            el.append(Paragraph(escape(f"First {len(rows)} of {total} rows; the full table is in the Excel export."), small))
        data = [[Paragraph("<b>" + escape(h) + "</b>", small) for h in header]] + [[Paragraph(escape(str(v)), small) for v in r] for r in rows]
        tb = Table(data, repeatRows=1)
        tb.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE6F1")),
                                ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        el.append(tb)
    el += [Spacer(1, 4 * mm), Paragraph("About this pack", ss["Heading2"])]
    el += [Paragraph(f"<b>{escape(k)}:</b> {escape(str(v))}", small) for k, v in about_lines(pack)]
    doc.build(el, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def to_ics(pack: Mapping[str, Any]) -> str:
    start = date.fromisoformat(pack["profile"]["as_of"])
    return CAL.to_ics(pack["calendar"], prodid=f"-//RBI-ObliBench audit generator {pack['about']['tool_version']}//EN",
                      start=start, end=start + timedelta(days=365), fy_end="03-31")


def audit_trail(pack: Mapping[str, Any]) -> dict[str, Any]:
    """Inputs, versions, hashes and the source of every row. For gap analysis: uploaded file hashes only."""
    a = pack["about"]
    trail_rows = []
    for sec in ("register", "changes", "calendar", "differential", "enforcement"):
        for r in pack.get(sec) or []:
            trail_rows.append({"section": sec, "row_id": r["row_id"], "md_id": r.get("md_id"), "paragraph_id": r.get("paragraph_id"),
                               "source_url": r.get("source_url"), "governing_instrument": r.get("governing_instrument"),
                               "confidence": r.get("confidence"), "needs_review": r.get("needs_review"),
                               "review_status": r.get("review_status"), "reviewer": r.get("reviewer"), "timestamp": r.get("timestamp")})
    gaps = pack.get("gaps")
    gap_part = None
    if gaps:
        gap_part = {"files": [{"name": f["name"], "sha256": f["sha256"], "bytes": f["bytes"], "clauses": f["clauses"]} for f in gaps["files"]],
                    "models": gaps["models"], "thresholds": gaps["thresholds"], "counts": gaps["counts"],
                    "rows": [{"row_id": r["row_id"], "md_id": r["md_id"], "paragraph_id": r["paragraph_id"], "source_url": r["source_url"],
                              "coverage": r["coverage"], "confidence": r["confidence"],
                              "matched_clause_ids": [c["clause_id"] for c in r["matched_clauses"]],
                              "review_status": r["review_status"], "reviewer": r["reviewer"]} for r in gaps["rows"]]}
    return {"kind": "audit_trail", "pack_id": pack["pack_id"], "created_utc": pack["created_utc"], "derived_from": pack.get("derived_from"),
            "disclaimer": pack["disclaimer"], "tool_version": a["tool_version"], "rules_version": a["rules_version"],
            "rules_sha256": a["rules_sha256"], "corpus": a["corpus"], "inputs": {"profile": pack["profile"]},
            "validation": a["validation"], "signoff": pack.get("signoff"), "dropped_without_citation": pack.get("dropped_without_citation"),
            "rows": trail_rows, "gap_analysis": gap_part,
            "privacy": "Uploaded documents: hashes only. No document text is recorded here."}


def write_all(pack: Mapping[str, Any], directory) -> dict[str, str]:
    from pathlib import Path

    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    files = {"xlsx": d / "audit_pack.xlsx", "docx": d / "audit_report.docx", "pdf": d / "audit_report.pdf",
             "ics": d / "compliance_calendar.ics", "json": d / "audit_trail.json"}
    files["xlsx"].write_bytes(to_excel(pack))
    files["docx"].write_bytes(to_docx(pack))
    files["pdf"].write_bytes(to_pdf(pack))
    files["ics"].write_text(to_ics(pack), encoding="utf-8")
    files["json"].write_text(json.dumps(audit_trail(pack), indent=1, ensure_ascii=False), encoding="utf-8")
    return {k: str(v) for k, v in files.items()}

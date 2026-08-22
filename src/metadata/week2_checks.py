"""Week 2 mandatory risk checks: cross-class alignment, FAQ/enforcement mapping, annotation pilot."""

from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.utils import load_config, resolve_path, setup_logging


def _tokens(text: str) -> set[str]:
    t = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return {w for w in t.split() if len(w) > 2}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class Week2RiskChecks:
    def __init__(self, config: dict[str, Any] | None = None):
        self.cfg = config or load_config()
        self.logger = setup_logging("week2.risk", self.cfg)
        self.reports = resolve_path(self.cfg, "reports")
        self.meta = resolve_path(self.cfg, "metadata")
        self.extracted = resolve_path(self.cfg, "extracted")
        self.processed = resolve_path(self.cfg, "processed")
        self.matrix = resolve_path(self.cfg, "matrix")

    def cross_class_alignment_risk(
        self,
        n_subjects: int = 3,
        n_entities: int = 3,
        sim_threshold: float = 0.45,
    ) -> dict[str, Any]:
        """
        Semi-automated paragraph alignment across entity classes for shared subjects.
        Method: for each selected subject family present in ≥ n_entities classes,
        greedily match paragraphs by token Jaccard; one-to-one alignment rate =
        matched_pairs / min(n_paras_class_a, n_paras_class_b) averaged over pairs.
        A human should spot-check the reported pairs in the report appendix.
        """
        import pandas as pd

        v0 = self.matrix / "matrix_v0.csv"
        if not v0.exists():
            return {
                "alignment_rate": "FAILED — matrix_v0 missing",
                "triggered_fallback_flag": None,
            }
        df = pd.read_csv(v0)
        # Prefer subjects appearing across many entity classes
        subj_ent = (
            df.groupby("subject_family_raw")["entity_class"]
            .nunique()
            .sort_values(ascending=False)
        )
        subjects = [s for s in subj_ent.index.tolist() if isinstance(s, str) and s.strip()][
            : max(n_subjects * 3, n_subjects)
        ]

        # Load paragraphs for pilot-extracted docs only (or any processed)
        paras_by_doc: dict[str, list[dict[str, Any]]] = {}
        for path in self.processed.glob("*.jsonl"):
            if path.name == "paragraphs_index.jsonl":
                continue
            rows = []
            with path.open(encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        rows.append(json.loads(line))
            if rows:
                paras_by_doc[rows[0]["document_id"]] = rows

        if not paras_by_doc:
            # Fall back to splitting extracted text on the fly for pilot docs
            for txt in list(self.extracted.glob("*.txt"))[:30]:
                did = txt.stem
                text = txt.read_text(encoding="utf-8", errors="replace")
                chunks = [c.strip() for c in re.split(r"\n\s*\n+", text) if len(c.strip()) > 40]
                paras_by_doc[did] = [
                    {
                        "paragraph_id": f"{did}::p{i:05d}",
                        "document_id": did,
                        "text": c,
                    }
                    for i, c in enumerate(chunks)
                ]

        pair_rates: list[float] = []
        details: list[dict[str, Any]] = []
        used_subjects = []
        for subject in subjects:
            if len(used_subjects) >= n_subjects:
                break
            sub = df[df["subject_family_raw"] == subject]
            entities = [e for e in sub["entity_class"].dropna().unique().tolist() if e][:n_entities]
            if len(entities) < 2:
                continue
            # Map entity -> document_id with available paragraphs
            ent_docs = {}
            for _, row in sub.iterrows():
                ent = row["entity_class"]
                did = row["document_id"]
                if ent in entities and did in paras_by_doc and ent not in ent_docs:
                    ent_docs[ent] = did
            if len(ent_docs) < 2:
                continue
            used_subjects.append(subject)
            ents = list(ent_docs.keys())[:n_entities]
            for i, ea in enumerate(ents):
                for eb in ents[i + 1 :]:
                    pa = paras_by_doc[ent_docs[ea]]
                    pb = paras_by_doc[ent_docs[eb]]
                    used_b = set()
                    matches = 0
                    for a in pa:
                        ta = _tokens(a.get("text", ""))
                        best_j, best_b = 0.0, None
                        for bi, b in enumerate(pb):
                            if bi in used_b:
                                continue
                            jb = jaccard(ta, _tokens(b.get("text", "")))
                            if jb > best_j:
                                best_j, best_b = jb, bi
                        if best_b is not None and best_j >= sim_threshold:
                            used_b.add(best_b)
                            matches += 1
                    denom = max(1, min(len(pa), len(pb)))
                    rate = matches / denom
                    pair_rates.append(rate)
                    details.append(
                        {
                            "subject_family_raw": subject,
                            "entity_a": ea,
                            "entity_b": eb,
                            "doc_a": ent_docs[ea],
                            "doc_b": ent_docs[eb],
                            "matched": matches,
                            "denom": denom,
                            "pair_alignment_rate": rate,
                        }
                    )

        if not pair_rates:
            alignment_rate: float | str = "FAILED — insufficient overlapping subject×entity paragraphs in pilot"
            triggered = None
        else:
            alignment_rate = sum(pair_rates) / len(pair_rates)
            triggered = alignment_rate < 0.60

        report = self.reports / "week2_alignment_risk.md"
        lines = [
            "# Week 2 — Cross-Class Alignment Risk Check",
            "",
            "## Method",
            "",
            "Semi-automated one-to-one greedy matching of paragraphs across entity classes",
            f"sharing a subject family, using token Jaccard ≥ {sim_threshold}.",
            "This is a **risk measurement**, not gold alignment. Spot-check recommended.",
            "",
            f"- Subjects used: {used_subjects}",
            f"- Pair comparisons: {len(pair_rates)}",
            f"- Mean one-to-one alignment rate: **{alignment_rate if isinstance(alignment_rate, str) else f'{alignment_rate:.4f}'}**",
            f"- <60% fallback trigger: **{triggered}**",
            "",
        ]
        if triggered is True:
            lines += [
                "## Fallback flag",
                "",
                "Alignment rate is below 60%. Do **not** assume paragraph-level alignment",
                "will work at scale. For Week 4 cross-class matching, **section-level**",
                "alignment should be considered as the fallback strategy.",
                "",
            ]
        lines += ["## Pair details", ""]
        for d in details:
            lines.append(
                f"- {d['subject_family_raw']} | {d['entity_a']} vs {d['entity_b']}: "
                f"{d['matched']}/{d['denom']} = {d['pair_alignment_rate']:.4f}"
            )
        report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {
            "alignment_rate": alignment_rate,
            "triggered_fallback_flag": triggered,
            "pair_details": details,
            "subjects_used": used_subjects,
            "report_path": str(report),
        }

    def faq_enforcement_alignment_check(self, max_items: int = 30) -> dict[str, Any]:
        """
        Heuristic hand-check assist: map FAQ / enforcement titles to Master Direction
        paragraphs via token overlap. Report how many map cleanly to a specific paragraph.
        """
        # Collect MD paragraph tokens (from processed or extracted)
        md_paras: list[dict[str, Any]] = []
        for path in list(self.processed.glob("*.jsonl"))[:80]:
            if path.name == "paragraphs_index.jsonl":
                continue
            with path.open(encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        row = json.loads(line)
                        md_paras.append(row)
        if not md_paras:
            for txt in list(self.extracted.glob("*.txt"))[:20]:
                text = txt.read_text(encoding="utf-8", errors="replace")
                for i, c in enumerate(re.split(r"\n\s*\n+", text)):
                    if len(c.strip()) > 40:
                        md_paras.append(
                            {
                                "paragraph_id": f"{txt.stem}::p{i:05d}",
                                "text": c.strip(),
                                "document_id": txt.stem,
                            }
                        )

        supp_path = self.meta / "supplementary_manifest.json"
        faq_items = []
        enf_items = []
        if supp_path.exists():
            for row in json.loads(supp_path.read_text(encoding="utf-8")):
                if row.get("download_status") not in {"success", "cached"}:
                    continue
                if row.get("source_type") == "faq":
                    faq_items.append(row)
                elif row.get("source_type") == "enforcement":
                    enf_items.append(row)

        def map_items(items: list[dict[str, Any]], kind: str) -> dict[str, Any]:
            checked = items[:max_items]
            clean = 0
            mappings = []
            for it in checked:
                # Use title + first 1500 chars of local HTML if present
                blob = it.get("title") or ""
                lp = it.get("local_path")
                if lp and Path(lp).exists():
                    try:
                        from bs4 import BeautifulSoup

                        html = Path(lp).read_text(encoding="utf-8", errors="replace")
                        blob += " " + BeautifulSoup(html, "lxml").get_text(" ", strip=True)[:1500]
                    except Exception:  # noqa: BLE001
                        pass
                tt = _tokens(blob)
                best = (0.0, None)
                for p in md_paras:
                    sc = jaccard(tt, _tokens(p.get("text", "")[:800]))
                    if sc > best[0]:
                        best = (sc, p["paragraph_id"])
                # "Clean" map: high overlap to a single paragraph
                is_clean = best[0] >= 0.22 and best[1] is not None
                if is_clean:
                    clean += 1
                mappings.append(
                    {
                        "document_id": it.get("document_id"),
                        "title": it.get("title"),
                        "best_paragraph_id": best[1],
                        "score": round(best[0], 4),
                        "clean_map": is_clean,
                    }
                )
            rate = (clean / len(checked)) if checked else "NOT YET MEASURED — no items harvested"
            return {
                "kind": kind,
                "items_checked": len(checked),
                "clean_paragraph_maps": clean if checked else 0,
                "paragraph_alignment_rate": rate,
                "mappings_sample": mappings[:10],
            }

        faq_res = map_items(faq_items, "faq")
        enf_res = map_items(enf_items, "enforcement")

        demote = False
        faq_rate = faq_res["paragraph_alignment_rate"]
        enf_rate = enf_res["paragraph_alignment_rate"]
        if isinstance(faq_rate, float) and faq_rate < 0.5:
            demote = True
        if isinstance(enf_rate, float) and enf_rate < 0.5:
            demote = True
        if faq_res["items_checked"] == 0 and enf_res["items_checked"] == 0:
            demote_note = (
                "FAILED — no FAQ/enforcement items available to align in this run; "
                "treat as validation/motivation pending successful harvest."
            )
        elif demote:
            demote_note = (
                "FAQ/enforcement do **not** map reliably to specific Master Direction "
                "paragraphs under the heuristic threshold. Demote to "
                "**validation/motivation source** rather than paragraph-level gold labels for T1."
            )
        else:
            demote_note = (
                "Heuristic mapping rates were relatively high on this sample; still treat "
                "as provisional — human review required before any gold use."
            )

        report = self.reports / "week2_faq_enforcement_check.md"
        report.write_text(
            "\n".join(
                [
                    "# Week 2 — FAQ / Enforcement Source Check",
                    "",
                    f"- FAQ items checked: {faq_res['items_checked']}",
                    f"- FAQ clean paragraph-alignment rate: {faq_res['paragraph_alignment_rate']}",
                    f"- Enforcement items checked: {enf_res['items_checked']}",
                    f"- Enforcement clean paragraph-alignment rate: {enf_res['paragraph_alignment_rate']}",
                    "",
                    "## Decision",
                    "",
                    demote_note,
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return {
            "faq": faq_res,
            "enforcement": enf_res,
            "demote_to_validation_motivation": demote
            or (faq_res["items_checked"] == 0 and enf_res["items_checked"] == 0),
            "report_path": str(report),
        }

    def annotation_feasibility_pilot(self, n_items: int = 12) -> dict[str, Any]:
        """
        Process pilot: create a tiny annotation set and record measured/estimated time.
        If no human timing was logged, report NOT YET MEASURED for average time.
        """
        timing_log = self.reports / "annotation_pilot_timings.json"
        items = []
        # Prefer T1 candidates if present; else synthetic refs from paragraphs
        cand = resolve_path(self.cfg, "benchmark_candidate") / "t1_candidates.csv"
        if cand.exists():
            import pandas as pd

            try:
                df = pd.read_csv(cand)
            except pd.errors.EmptyDataError:
                df = pd.DataFrame()
            for _, row in df.head(n_items).iterrows():
                items.append(
                    {
                        "paragraph_id": row.get("paragraph_id"),
                        "entity_class": row.get("entity_class"),
                        "subject_family": row.get("subject_family"),
                        "differential_flag_candidate": row.get("differential_flag"),
                    }
                )
        if not items:
            for path in list(self.processed.glob("*.jsonl"))[:5]:
                if path.name == "paragraphs_index.jsonl":
                    continue
                with path.open(encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        row = json.loads(line)
                        items.append(
                            {
                                "paragraph_id": row["paragraph_id"],
                                "entity_class": row.get("entity_class"),
                                "subject_family": row.get("subject_family"),
                            }
                        )
                        if len(items) >= n_items:
                            break
                if len(items) >= n_items:
                    break

        pilot_path = self.reports / "annotation_feasibility_pilot_items.json"
        pilot_path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")

        if timing_log.exists():
            timings = json.loads(timing_log.read_text(encoding="utf-8"))
            secs = [float(t["seconds"]) for t in timings if "seconds" in t]
            avg = sum(secs) / len(secs) if secs else "NOT YET MEASURED"
        else:
            # Self-timing of loading + reviewing first item structure (process smoke test only)
            t0 = time.perf_counter()
            _ = items[:1]
            elapsed = time.perf_counter() - t0
            avg = "NOT YET MEASURED — human annotation timings not logged yet"
            timing_log.write_text(
                json.dumps(
                    [
                        {
                            "note": "No multi-annotator human timings recorded in this run",
                            "smoke_test_seconds": elapsed,
                        }
                    ],
                    indent=2,
                ),
                encoding="utf-8",
            )

        return {
            "annotation_pilot_item_count": len(items),
            "average_time_per_item_seconds": avg,
            "pilot_items_path": str(pilot_path),
        }

    def write_licensing_note(self) -> str:
        path = self.reports / "week2_licensing_note.md"
        path.write_text(
            "\n".join(
                [
                    "# Week 2 — Licensing / IPR Note",
                    "",
                    "## Open question",
                    "",
                    "Whether Reserve Bank of India (RBI) Master Directions, FAQs, circulars,",
                    "and enforcement press releases may be **freely redistributed** (in full text",
                    "or substantial excerpts) as part of a public research benchmark remains an",
                    "**open IPR / licensing question**.",
                    "",
                    "## What this project does for now",
                    "",
                    "- Cache source documents **locally** for research processing.",
                    "- Prefer storing **offsets / paragraph IDs / URLs** in benchmark artifacts",
                    "  rather than republishing full regulatory text.",
                    "- Do **not** assume that public availability on rbi.org.in equals a license",
                    "  to redistribute.",
                    "",
                    "## Action required",
                    "",
                    "Raise with the **mentor / institutional IPR cell** before any public",
                    "release of RBI-ObliBench corpus text. Until cleared, treat full-text",
                    "corpus files as non-redistributable working data.",
                    "",
                    "This note deliberately does **not** assert a legal conclusion.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return str(path)

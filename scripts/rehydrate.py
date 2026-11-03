#!/usr/bin/env python3
"""Rehydrate RBI-ObliBench: rebuild the corpus paragraphs and benchmark texts from RBI's own URLs (P5-001 task 4).

    python3 scripts/rehydrate.py                          # every Direction (downloads ~381 PDFs from rbi.org.in)
    python3 scripts/rehydrate.py --sample 5               # the Directions behind the first 5 T1 validated items
    python3 scripts/rehydrate.py --md md_12925 md_13139   # named Directions
    python3 scripts/rehydrate.py --offline <processed_dir> --out rehydrated/   # from a local md_*.jsonl corpus (tests)

For each Direction it downloads the page or PDF, re-extracts and re-segments the text with the repository's own
pipeline (src/extraction, src/preprocessing), and checks every paragraph against the sha256 in
release/data/paragraphs.jsonl:
  matched  - the paragraph id exists and its text hash is unchanged;
  drifted  - the paragraph id exists but the text differs (RBI updated the Direction: "Updated as on ...");
  missing  - the paragraph id is not produced any more (document gone, or re-segmented differently).
With --out it also rebuilds the derived texts (T1 spans, T2 queries, T4 non-LLM answers) from matched paragraphs and
checks each against its text_sha256. RBI updates consolidated Directions in place, so some drift is expected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.release.rebuild import negate, raw_slice, span_text, spans_text  # noqa: E402


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def jl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []


def offline_paragraphs(processed_dir: Path, md_ids: Iterable[str]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for md in md_ids:
        rows = jl(processed_dir / f"{md}.jsonl")
        if rows:
            out[md] = {r["paragraph_id"]: r["text"] for r in rows}
    return out


def online_paragraphs(docs: dict[str, dict], md_ids: Iterable[str]) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    """Download, extract and segment each Direction with the repository's pipeline. Returns (paragraphs, notes)."""
    from src.common.config import load_config
    from src.common.logging_setup import get_logger
    from src.extraction.text_extractor import _extract_html_text, _extract_pdf_text
    from src.preprocessing.segmenter import segment_document
    from src.schemas.provenance import DocumentRecord
    from src.scraper.rbi_scraper import _fetch, build_session

    cfg = load_config()
    session = build_session(cfg)
    logger = get_logger("rehydrate", cfg)
    out, notes = {}, {}
    for md in md_ids:
        d = docs[md]
        try:
            data = _fetch(d["source_url"], session, cfg, logger=logger, description=md)
        except Exception as exc:  # noqa: BLE001 - any network failure is a 'missing' Direction
            notes[md] = f"download failed: {type(exc).__name__}"
            continue
        notes[md] = "payload identical to harvest" if hashlib.sha256(data).hexdigest() == d.get("payload_sha256") else "payload changed since harvest"
        text = _extract_pdf_text(data, document_id=md) if data[:4] == b"%PDF" else _extract_html_text(data, document_id=md)
        rec = DocumentRecord.from_dict({"document_id": md, "source_url": d["source_url"], "title": d.get("title"),
                                        "entity_class": d.get("entity_class"), "subject_family": d.get("subject_family"),
                                        "update_date": d.get("update_date"), "extraction_source": "rbi_master_directions"},
                                       strict=False)
        out[md] = {p.paragraph_id: p.text for p in segment_document(rec, text, cfg, logger=logger)}
    return out, notes


def compare(expected: list[dict], got: dict[str, dict[str, str]]) -> tuple[Counter, dict[str, str]]:
    status, matched = Counter(), {}
    for p in expected:
        text = got.get(p["md_id"], {}).get(p["paragraph_id"])
        if text is None:
            status["missing"] += 1
        elif sha(text) == p["text_sha256"]:
            status["matched"] += 1
            matched[p["paragraph_id"]] = text
        else:
            status["drifted"] += 1
    return status, matched


def rebuild(release: Path, raw: dict[str, str], out: Path | None) -> Counter:
    """Rebuild every derived text whose paragraphs all matched; count rebuilt / failed / skipped."""
    c = Counter()
    texts: dict[str, dict[str, str]] = {}

    def emit(group: str, key: str, text: str | None, want: str) -> None:
        if text is None:
            c["skipped (a source paragraph did not match)"] += 1
        elif sha(text) == want:
            c["rebuilt"] += 1
            texts.setdefault(group, {})[key] = text
        else:
            c["failed (hash differs)"] += 1

    def have(*pids: str) -> bool:
        return all(p in raw for p in pids)

    for name in ("validated.jsonl", "candidates_part1.jsonl", "candidates_part2.jsonl"):
        for it in jl(release / "data" / "t1" / name):
            sp = it["obligation_span"]
            emit("t1_spans", it["item_id"], span_text(raw[sp["paragraph_id"]], sp["units"]) if have(sp["paragraph_id"]) else None,
                 sp["text_sha256"])
    for f in sorted((release / "data" / "t2").glob("*.jsonl")):
        for q in jl(f):
            qp = q["query"]
            if qp["rule"] in ("span_text", "raw_slice"):
                fn = span_text if qp["rule"] == "span_text" else raw_slice
                emit("t2_queries", q["query_id"], fn(raw[qp["paragraph_id"]], qp["units"]) if have(qp["paragraph_id"]) else None,
                     qp["text_sha256"])
            else:
                c["not rebuilt (FAQ / press-release text; see the dataset card)"] += 1
    conc = {}
    for t in ("concatenated", "adv_offtopic"):
        for a in jl(release / "data" / "t4" / f"answers_{t}.jsonl"):
            sp = [(s["paragraph_id"], s["start"], s["end"]) for s in a["spans"]]
            text = spans_text(sp, raw) if have(*(p for p, _, _ in sp)) else None
            if t == "concatenated":
                conc[a["question_id"]] = text
            emit(f"t4_{t}", a["question_id"], text, a["text_sha256"])
    for a in jl(release / "data" / "t4" / "answers_adv_negated.jsonl"):
        base = conc.get(a["question_id"])
        emit("t4_adv_negated", a["question_id"], negate(base) if base is not None else None, a["text_sha256"])
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        for g, m in texts.items():
            (out / f"{g}.jsonl").write_text("".join(json.dumps({"id": k, "text": v}, ensure_ascii=False) + "\n"
                                                    for k, v in sorted(m.items())), encoding="utf-8")
    return c


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--release", default=str(ROOT / "release"))
    ap.add_argument("--offline", metavar="PROCESSED_DIR", help="read md_*.jsonl paragraphs from a local directory")
    ap.add_argument("--md", nargs="*", help="only these Directions")
    ap.add_argument("--sample", type=int, help="only the Directions behind the first N T1 validated items")
    ap.add_argument("--out", help="write rebuilt texts here (paragraphs.jsonl and the derived texts)")
    ap.add_argument("--json", action="store_true", help="print the summary as JSON")
    args = ap.parse_args(argv)
    release = Path(args.release)
    docs = {d["md_id"]: d for d in jl(release / "data" / "documents.jsonl")}
    paras = jl(release / "data" / "paragraphs.jsonl")
    if args.md:
        wanted = list(dict.fromkeys(args.md))
    elif args.sample:
        wanted = list(dict.fromkeys(it["md_id"] for it in jl(release / "data" / "t1" / "validated.jsonl")[: args.sample]))
    else:
        wanted = sorted(docs)
    unknown = [m for m in wanted if m not in docs]
    if unknown:
        ap.error(f"unknown Direction ids: {unknown}")
    if args.offline:
        got, notes = offline_paragraphs(Path(args.offline), wanted), {}
    else:
        got, notes = online_paragraphs(docs, wanted)
    expected = [p for p in paras if p["md_id"] in set(wanted)]
    status, matched = compare(expected, got)
    out = Path(args.out) if args.out else None
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        (out / "paragraphs.jsonl").write_text("".join(json.dumps({"paragraph_id": k, "text": v}, ensure_ascii=False) + "\n"
                                                      for k, v in sorted(matched.items())), encoding="utf-8")
    rb = rebuild(release, matched, out) if (out is not None or args.json) else Counter()
    summary = {"directions": len(wanted), "paragraphs": len(expected), "matched": status["matched"],
               "drifted": status["drifted"], "missing": status["missing"], "documents": notes, "derived_texts": dict(rb)}
    if args.json:
        print(json.dumps(summary, indent=1))
    else:
        print(f"Directions {len(wanted)}; paragraphs {len(expected)}: matched {status['matched']}, drifted {status['drifted']}, "
              f"missing {status['missing']}")
        for md, n in sorted(notes.items()):
            print(f"  {md}: {n}")
        if rb:
            print("derived texts: " + ", ".join(f"{k} {v}" for k, v in rb.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

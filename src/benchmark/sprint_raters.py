"""2-day sprint human annotation round (Amendment 7): held packets, gates, ingest with the independence checks.

Reuses the t1v2 machinery (returned-file reading, shown-cell comparison, P2-004 validation, minutes-log parsing, the
D11 free-text guard, B3 packet checks) with the sprint's own files, so the t1v2 receipts and packets are never touched.
Raters: the two previous project raters, pseudonymised `rater_2` / `rater_3` (map in reports/private/rater_map.json).
Nothing here computes agreement except `analyse`, which runs the pre-registered statistics once every file is final.
"""

from __future__ import annotations

import csv
import io
import json
import random
import shutil
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.benchmark import t1 as T
from src.benchmark import t1v2 as V
from src.benchmark import t1v2_checks as C

NAMES = ("meer", "akash")
ORDER_SEED = {"rater_2": 20261091, "rater_3": 20261092}
T4_SEED = {"rater_2": 20261093, "rater_3": 20261094}
RETEST_ORDER_SEED = {"rater_2": 20261097, "rater_3": 20261098}
SITTING_SPLIT = 53
BLOCK = 20
T4_BLOCK = 10
MIN_RETEST_HOURS = 8.0
LAST_SESSION_START = datetime(2026, 10, 10, 6, 0, tzinfo=V.IST)
RETEST_HIDDEN_SHA256 = "7f022828e22ac8931c49b479a2557ec695df429951a26aa9ba2fd2be10818682"
AMENDMENTS_V6_SHA256 = "55cd08564a1baf408db735376950800f88c10cc5639385534ba25ce6c19aca40"
T1_MINUTES_COLUMNS = V.MINUTES_COLUMNS
T4_MINUTES_COLUMNS = ("block", "started_at", "ended_at")
SUPERVISION_COLUMNS = ("sitting", "rater", "supervisor", "date", "start_time", "end_time", "breaks",
                       "phones_and_devices_away", "no_ai_tools_confirmed", "no_discussion_confirmed",
                       "only_packet_files_open", "notes", "supervisor_signature", "rater_signature")
INSTRUCTIONS = "T1v2_ANNOTATION_INSTRUCTIONS.md"


def t1_header(what: str) -> str:
    return (f"# RBI-ObliBench T1, {what}. Guidelines v3.1 ({INSTRUCTIONS}, sent with your first sheet). Item rows: applies_to "
            "(from the span's own text; names separated by ';'), applies_to_rationale, not_obligation (yes, with the reason in "
            "note), note. Class rows: judgement = same | different | none | unsure, and matched_paragraph_id for "
            "same/different. Candidates are shown in random order with no scores. Rate each item as if new: don't open any "
            "earlier file or notes. Supervised sitting: label alone, no AI tools, no discussion of any item with anyone, don't "
            "open any other file. This file goes to one person only and is ingested once; keep the filename.")


class SprintError(T.T1Error):
    pass


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def t1_dir(self) -> Path:
        return self.root / "data/benchmark/t1"

    @property
    def t4_dir(self) -> Path:
        return self.root / "data/benchmark/t4"

    @property
    def hold(self) -> Path:
        return self.t1_dir / "sprint_packets" / "HOLD"

    @property
    def ready(self) -> Path:
        return self.t1_dir / "sprint_packets" / "ready_to_send"

    @property
    def supervision(self) -> Path:
        return self.root / "data/benchmark/sprint_supervision"

    @property
    def receipts(self) -> Path:
        return self.t1_dir / "sprint_receipts_v1.json"

    @property
    def private(self) -> Path:
        return self.root / "reports/private/final_push/sprint"

    @property
    def key(self) -> Path:
        return self.private / "packet_key_sprint_v1.json"

    @property
    def retest_hidden(self) -> Path:
        return self.private / "retest_subsets_hidden_sprint_v1.json"


def rater_map(paths: Paths) -> dict[str, str]:
    m = json.loads((paths.root / "reports/private/rater_map.json").read_text())["map"]
    return {n: m[n] for n in NAMES}


def _write_csv(path: Path, columns: Sequence[str], rows: Sequence[Mapping[str, str]], header: str | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise SprintError(f"refusing to overwrite {path}")
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        if header:
            fh.write(header + "\n")
        w = csv.DictWriter(fh, fieldnames=list(columns))
        w.writeheader()
        w.writerows(rows)
    return path


def drawn_rows(paths: Paths) -> list[dict[str, str]]:
    want = json.loads((paths.t1_dir / T.DRAW_LOG_FILE).read_text())["entries"][-1]["files"]
    key = next(k for k in want if k.endswith("pass1") and "sha256" in want[k])
    if V.sha256_file(paths.t1_dir / T.PASS1_SHEET) != want[key]["sha256"]:
        raise SprintError("the blank pass-1 sheet no longer matches the draw log")
    return T.read_sheet(paths.t1_dir / T.PASS1_SHEET)


def gold_ids(paths: Paths) -> list[dict]:
    return [json.loads(l) for l in (paths.t1_dir / "t1_validated_v1.jsonl").read_text().splitlines() if l.strip()]


def item_order(gold: Sequence[Mapping[str, Any]], seed: int) -> list[str]:
    by_cls: dict[str, list[str]] = defaultdict(list)
    for g in sorted(gold, key=lambda g: g["item_id"]):
        by_cls[g["entity_class"]].append(g["item_id"])
    rng = random.Random(seed)
    for c in sorted(by_cls):
        rng.shuffle(by_cls[c])
    return list(T.interleave(by_cls, seed))


def sheet_for(order: Sequence[str], drawn: Sequence[Mapping[str, str]], block_of: Mapping[str, int]) -> list[dict[str, str]]:
    by_item: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in drawn:
        by_item[r["item_id"]].append(r)
    rows = []
    for iid in order:
        for r in by_item[iid]:
            rows.append({**r, "block": str(block_of[iid])})
    return rows


# ---------------------------------------------------------------------------
# Build (held) packets
# ---------------------------------------------------------------------------


def build(paths: Paths, *, tc: T.T1Config, paragraph_class: Mapping[str, str]) -> dict[str, Any]:
    from src.t4 import audit as A

    if V.sha256_file(paths.retest_hidden) != RETEST_HIDDEN_SHA256:
        raise SprintError("the hidden retest subsets changed since Amendment 7")
    if paths.key.exists():
        raise SprintError(f"{paths.key} exists: packets were already built (archive, never overwrite)")
    rmap = rater_map(paths)
    drawn = drawn_rows(paths)
    gold = gold_ids(paths)
    ids = [g["item_id"] for g in gold]
    texts, cited = C.earlier_labels(C.default_label_files(paths.t1_dir, sorted((paths.t1_dir / "t1v2_excluded").rglob("*_pass1.csv"))),
                                    C.gold_rows(paths.t1_dir))
    scores = C.score_strings(json.loads((paths.t1_dir / T.KEY_FILE).read_text())["items"])
    t4_sheet = paths.t4_dir / "t4_faithfulness_sheet_v1.csv"
    t4_text = t4_sheet.read_text(encoding="utf-8-sig")
    t4_header = t4_text.splitlines()[0]
    t4_rows = A.read_sheet_text(t4_text)
    t4_cols = list(t4_rows[0])
    key: dict[str, Any] = {"built_utc": V.iso(V.utc_now()), "amendment": "Amendment 7 (reliability_plan_v2_amendments_v6.md)",
                           "amendments_v6_sha256": AMENDMENTS_V6_SHA256, "blank_pass1_sha256": V.sha256_file(paths.t1_dir / T.PASS1_SHEET),
                           "t4_sheet_sha256": V.sha256_file(t4_sheet), "module_sha256": V.sha256_file(Path(__file__)),
                           "raters": {}}
    instructions_src = paths.t1_dir / "t1v2_packets" / INSTRUCTIONS
    for name in NAMES:
        pseudo = rmap[name]
        order = item_order(gold, ORDER_SEED[pseudo])
        assert sorted(order) == sorted(ids)
        sittings = {1: order[:SITTING_SPLIT], 2: order[SITTING_SPLIT:]}
        out = paths.hold / name
        entry: dict[str, Any] = {"pseudonym": pseudo, "order_seed": ORDER_SEED[pseudo], "sittings": {}}
        for s, s_ids in sittings.items():
            block_of = {iid: (pos // BLOCK) + 1 + (0 if s == 1 else 3) for pos, iid in enumerate(s_ids)}
            rows = sheet_for(s_ids, drawn, block_of)
            sp = T.write_sheet(out / f"{name}_blind_sprint_s{s}.csv", rows, T.SHEET_COLUMNS,
                               header=t1_header(f"sprint sitting {s} of 2"), input_columns=T.INPUT_COLUMNS)
            blocks = sorted(set(block_of.values()))
            mp = _write_csv(out / f"{name}_sprint_s{s}_minutes.csv", T1_MINUTES_COLUMNS,
                            [{c: (str(b) if c == "block" else "") for c in T1_MINUTES_COLUMNS} for b in blocks])
            check = C.check_packet(sp, approved_ids=s_ids, drawn=drawn, tc=tc, paragraph_class=paragraph_class,
                                   texts=texts, cited=cited, scores=scores)
            if not check["PASS"]:
                raise SprintError(f"B3 check failed for {sp.name}: {check}")
            sup = _write_csv(paths.supervision / f"supervision_log_{pseudo}_s{s}.csv", SUPERVISION_COLUMNS,
                             [{c: (str(s) if c == "sitting" else pseudo if c == "rater" else "") for c in SUPERVISION_COLUMNS}])
            entry["sittings"][str(s)] = {"items": s_ids, "blocks": blocks,
                                         "sheet": {"path": str(sp.relative_to(paths.root)), "sha256": V.sha256_file(sp)},
                                         "minutes": {"path": str(mp.relative_to(paths.root)), "sha256": V.sha256_file(mp),
                                                     "header": list(T1_MINUTES_COLUMNS)},
                                         "supervision_template": str(sup.relative_to(paths.root)), "b3_check": check}
        ins = out / INSTRUCTIONS
        shutil.copyfile(instructions_src, ins)
        entry["instructions"] = {"path": str(ins.relative_to(paths.root)), "sha256": V.sha256_file(ins)}
        # T4: same 30 rows, same columns and header, fresh order, blocks of 10.
        rng = random.Random(T4_SEED[pseudo])
        t4o = list(t4_rows)
        rng.shuffle(t4o)
        if [r["row_id"] for r in t4o] == [r["row_id"] for r in t4_rows]:
            raise SprintError("T4 shuffle reproduced the original order")
        t4o = [{**r, "block": str(i // T4_BLOCK + 1)} for i, r in enumerate(t4o)]
        t4p = out / f"{name}_blind_sprint_t4.csv"
        t4p.parent.mkdir(parents=True, exist_ok=True)
        with t4p.open("w", encoding="utf-8-sig", newline="") as fh:
            fh.write(t4_header + "\n")
            w = csv.DictWriter(fh, fieldnames=t4_cols)
            w.writeheader()
            w.writerows(t4o)
        t4m = _write_csv(out / "t4_faithfulness_minutes.csv", T4_MINUTES_COLUMNS,
                         [{"block": str(b), "started_at": "", "ended_at": ""} for b in (1, 2, 3)])
        back = A.read_sheet_text(t4p.read_text(encoding="utf-8-sig"))
        orig = {r["row_id"]: r for r in t4_rows}
        t4check = {"rows": len(back), "same_row_set": sorted(r["row_id"] for r in back) == sorted(orig),
                   "shown_cells_differ": sum(1 for r in back for c in ("question", "passages", "answer") if r[c] != orig[r["row_id"]][c]),
                   "inputs_nonblank": sum(1 for r in back for c in ("faithful", "answers_question", "bad_question", "note") if (r.get(c) or "").strip()),
                   "name_hits": len(C.NAME_RE.findall(t4p.read_text(encoding="utf-8-sig"))),
                   "header_identical": t4p.read_text(encoding="utf-8-sig").splitlines()[0] == t4_header}
        t4check["PASS"] = (t4check["rows"] == 30 and t4check["same_row_set"] and not t4check["shown_cells_differ"]
                           and not t4check["inputs_nonblank"] and not t4check["name_hits"] and t4check["header_identical"])
        if not t4check["PASS"]:
            raise SprintError(f"T4 packet check failed: {t4check}")
        entry["t4"] = {"path": str(t4p.relative_to(paths.root)), "sha256": V.sha256_file(t4p), "seed": T4_SEED[pseudo],
                       "order": [r["row_id"] for r in t4o],
                       "minutes": {"path": str(t4m.relative_to(paths.root)), "sha256": V.sha256_file(t4m),
                                   "header": list(T4_MINUTES_COLUMNS)}, "check": t4check}
        key["raters"][name] = entry
    paths.private.mkdir(parents=True, exist_ok=True)
    paths.key.write_text(json.dumps(key, indent=1, ensure_ascii=False))
    paths.key.chmod(0o444)
    return key


# ---------------------------------------------------------------------------
# Receipts and releases
# ---------------------------------------------------------------------------


def load_rec(paths: Paths) -> dict[str, Any]:
    if paths.receipts.exists():
        return json.loads(paths.receipts.read_text(encoding="utf-8"))
    return {"note": "Append-only sprint receipts (Amendment 7). Entries are never edited.", "releases": [], "attempts": [],
            "frozen": {}, "excluded": {}, "retest_generated": {}}


def save_rec(paths: Paths, rec: Mapping[str, Any]) -> None:
    V.save_receipts(paths.receipts, rec)


def _key(paths: Paths) -> dict[str, Any]:
    return json.loads(paths.key.read_text())


def _release_files(paths: Paths, name: str, files: Sequence[tuple[str, str]]) -> list[str]:
    dest = paths.ready / name
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for rel, sha in files:
        src = paths.root / rel
        if V.sha256_file(src) != sha:
            raise SprintError(f"{src.name}: held packet changed since it was built")
        d = dest / src.name
        shutil.copyfile(src, d)
        out.append(str(d.relative_to(paths.root)))
    return out


def start(paths: Paths, sitting: int, now: datetime | None = None) -> dict[str, Any]:
    now = now or V.utc_now()
    if now > LAST_SESSION_START:
        raise SprintError("refused: no new annotation session may start after Sat 10 Oct 06:00 IST")
    key, rec = _key(paths), load_rec(paths)
    if any(r["sitting"] == sitting for r in rec["releases"] if r.get("what") == "sitting"):
        raise SprintError(f"sitting {sitting} was already released")
    if sitting == 2 and not any(r.get("what") == "sitting" and r["sitting"] == 1 for r in rec["releases"]):
        raise SprintError("sitting 1 has not been released")
    released = {}
    for name, e in key["raters"].items():
        s = e["sittings"][str(sitting)]
        files = [(s["sheet"]["path"], s["sheet"]["sha256"]), (s["minutes"]["path"], s["minutes"]["sha256"])]
        if sitting == 1:
            files.append((e["instructions"]["path"], e["instructions"]["sha256"]))
        else:
            files += [(e["t4"]["path"], e["t4"]["sha256"]), (e["t4"]["minutes"]["path"], e["t4"]["minutes"]["sha256"])]
        released[e["pseudonym"]] = _release_files(paths, name, files)
    rec["releases"].append({"what": "sitting", "sitting": sitting, "released_utc": V.iso(now), "released_ist": V.ist(now),
                            "files": released})
    save_rec(paths, rec)
    return {"sitting": sitting, "released": released}


# ---------------------------------------------------------------------------
# Independence checks (Amendment 7)
# ---------------------------------------------------------------------------


def fingerprint(path: Path) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    fp: dict[str, Any] = {"bytes": len(raw), "sha256": V.sha256_bytes(raw)}
    if raw[:2] == b"PK":
        fp["container"] = "xlsx"
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                props = {}
                for part in ("docProps/core.xml", "docProps/app.xml"):
                    if part in z.namelist():
                        for el in ET.fromstring(z.read(part)).iter():
                            tag = el.tag.split("}")[-1]
                            if tag in ("creator", "lastModifiedBy", "created", "modified", "Application", "AppVersion") and el.text:
                                props[tag] = el.text.strip()
                fp["props"] = props
        except (zipfile.BadZipFile, ET.ParseError):
            fp["props"] = {"unreadable": True}
    else:
        fp["container"] = "csv"
        fp["bom"] = raw[:3] == b"\xef\xbb\xbf"
        text, enc = V.decode_csv_bytes(raw)
        fp["encoding"] = enc
        fp["line_endings"] = "crlf" if b"\r\n" in raw else ("cr" if b"\r" in raw else "lf")
        first = text.splitlines()[1] if text.startswith("#") and len(text.splitlines()) > 1 else (text.splitlines() or [""])[0]
        fp["delimiter"] = ";" if first.count(";") > first.count(",") else ","
    return fp


def _jaccard(a: str, b: str) -> float:
    x, y = set(a.lower().split()), set(b.lower().split())
    return len(x & y) / len(x | y) if x | y else 0.0


def free_text_overlap(rows: Sequence[Mapping[str, str]], others: Mapping[str, Sequence[Mapping[str, str]]]) -> dict[str, Any]:
    mine = {k: v for k, v in T.item_text_cells(rows).items() if len(" ".join(v.split())) >= 15}
    identical, near = {}, {}
    for name, o in others.items():
        theirs = T.item_text_cells(o)
        identical[name] = sum(1 for k, v in mine.items() if " ".join(theirs.get(k, "").split()).lower() == " ".join(v.split()).lower())
        near[name] = sum(1 for k, v in mine.items() if k in theirs and _jaccard(v, theirs[k]) >= 0.9)
    return {"cells_checked": len(mine), "identical_by_source": identical, "near_identical_by_source": near,
            "identical_total": sum(identical.values())}


def minutes_header_check(path: Path, sent_header: Sequence[str], sent_blocks: Sequence[str]) -> dict[str, Any]:
    text, _enc = V.decode_csv_bytes(Path(path).read_bytes())
    rows = list(csv.reader(io.StringIO(text)))
    header = [h.strip() for h in (rows[0] if rows else [])]
    blocks = [r[0].strip() for r in rows[1:] if r and r[0].strip()]
    return {"header": header, "header_as_sent": header == list(sent_header), "blocks": blocks,
            "blocks_as_sent": blocks[:len(sent_blocks)] == [str(b) for b in sent_blocks],
            "deviation_signature": None if header == list(sent_header) and blocks[:len(sent_blocks)] == [str(b) for b in sent_blocks]
            else V.sha256_bytes(json.dumps({"h": header, "b": blocks}).encode())}


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


def _other_sources(paths: Paths, rec: Mapping[str, Any], name: str) -> dict[str, list[dict[str, str]]]:
    out = {}
    for slot, rc in rec["frozen"].items():
        if rc["name"] != name and rc["task"] in ("t1", "retest"):
            out[slot] = T.read_sheet(paths.root / rc["normalised"])
    for label, rel in (("rater_1_pass1", "pass1_received/annotation_p2004_karan_pass1.csv"),
                       ("team_review_a", "team_review_received/annotation_p2004_akash_pass1_completed.csv"),
                       ("team_review_m", "team_review_received/annotation_p2004_meer_pass1_completed.csv")):
        if (paths.t1_dir / rel).exists():
            out[label] = T.read_sheet(paths.t1_dir / rel)
    other = [n for n in NAMES if n != name][0]
    for p in sorted((paths.t1_dir / "t1v2_excluded" / "frozen").glob(f"{other}_pass1/*/{other}_blind_t1v2_pass1.csv")):
        out[f"excluded_t1v2_other_rater:{p.parent.name}"] = T.read_sheet(p)
    return out


def ingest(paths: Paths, *, name: str, task: str, sitting: int | None, file: Path, minutes: Path, photo: Path | None,
           tc: T.T1Config, paragraph_class: Mapping[str, str], received_at: str | None = None,
           now: datetime | None = None) -> dict[str, Any]:
    """task: t1 (sitting 1|2), t4, retest. Invalid -> attempt recorded (may be re-sent); FAIL -> excluded (final)."""
    from src.t4 import audit as A

    if name not in NAMES:
        raise SprintError(f"rater must be one of {NAMES}")
    now = now or V.utc_now()
    rec, key = load_rec(paths), _key(paths)
    e = key["raters"][name]
    slot = f"{e['pseudonym']}_{task}" + (f"_s{sitting}" if task == "t1" else "")
    if slot in rec["frozen"] or slot in rec["excluded"]:
        raise SprintError(f"{slot} is already final ({'frozen' if slot in rec['frozen'] else 'excluded'})")
    if photo is None or not Path(photo).exists():
        raise SprintError("the supervision-log photo for this sitting is required (Amendment 7, check 4); nothing ingested")
    file, raw = Path(file), Path(file).read_bytes()
    digest = V.sha256_bytes(raw)
    if task == "t1":
        meta = e["sittings"][str(sitting)]
        sent_meta, min_meta = meta["sheet"], meta["minutes"]
        sent_blocks = [str(b) for b in meta["blocks"]]
    elif task == "t4":
        sent_meta, min_meta = {"path": e["t4"]["path"], "sha256": e["t4"]["sha256"]}, e["t4"]["minutes"]
        sent_blocks = ["1", "2", "3"]
    elif task == "retest":
        g = rec["retest_generated"].get(e["pseudonym"])
        if not g:
            raise SprintError("no retest packet was released for this rater")
        sent_meta, min_meta, sent_blocks = g["sheet"], g["minutes"], [str(b) for b in g["blocks"]]
    else:
        raise SprintError("task must be t1, t4 or retest")
    sp = paths.root / sent_meta["path"]
    if V.sha256_file(sp) != sent_meta["sha256"]:
        raise SprintError("the sent packet changed since it was built")
    attempt_dir = paths.t1_dir / "sprint_attempts" / slot
    attempt_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    kept = attempt_dir / f"{stamp}_{digest[:12]}_{file.name}"
    if not kept.exists():  # the same bytes re-sent (e.g. with a corrected minutes log) are kept once
        shutil.copyfile(file, kept)
        kept.chmod(0o444)
    recv_dt, recv_src = V._received(file, received_at)
    problems: list[str] = []
    norm: list[dict[str, str]] = []
    if task in ("t1", "retest"):
        sent = T.read_sheet(sp)
        try:
            rows, _info = V.load_returned(file)
        except Exception as exc:  # noqa: BLE001 - any unreadable file is an invalid attempt
            rows = []
            problems.append(f"file unreadable: {type(exc).__name__}")
        if rows:
            problems += V.compare_to_sent(rows, sent, T.SHEET_COLUMNS, T.INPUT_COLUMNS)
            if not problems:
                norm = V.normalise_rows(rows, sent, T.SHEET_COLUMNS, T.INPUT_COLUMNS)
                problems += T.validate_labelled(norm, tc, paragraph_class)
    else:
        sent = A.read_sheet_text(sp.read_text(encoding="utf-8-sig"))
        try:
            rows, _info = V.load_returned(file, id_col="row_id")
        except Exception as exc:  # noqa: BLE001
            rows = []
            problems.append(f"file unreadable: {type(exc).__name__}")
        if rows:
            if [r.get("row_id", "").strip() for r in rows] != [r["row_id"] for r in sent]:
                problems.append("row_id order differs from the sent sheet")
            problems += A.validate_completed(rows, sent)
            norm = [{k: V.norm_cell(v) for k, v in r.items()} for r in rows]
    mh = minutes_header_check(Path(minutes), min_meta["header"], sent_blocks)
    mins = None
    try:
        mins = V.parse_minutes_log(Path(minutes))
        problems += mins["problems"]
    except V.T1v2Error as exc:
        problems.append(f"minutes log unreadable: {exc}")
    if not (mh["header_as_sent"] and mh["blocks_as_sent"]):
        problems.append("minutes log header or pre-listed blocks differ from what was sent (re-send the minutes log only)")
    fp = fingerprint(file)
    attempt = {"slot": slot, "attempted_at_utc": V.iso(now), "file_name": file.name, "sha256": digest, "kept_as": str(kept.relative_to(paths.root)),
               "received_at_utc": V.iso(recv_dt), "received_at_source": recv_src, "fingerprint": fp, "minutes_header": mh,
               "status": "invalid" if problems else "checked", "problems": problems[:200]}
    rec["attempts"].append(attempt)
    if problems:
        save_rec(paths, rec)
        return {"status": "invalid", "problems": problems, "attempt": attempt}
    # Independence checks (Amendment 7): FAIL is final.
    fails = []
    ov = free_text_overlap(norm, _other_sources(paths, rec, name)) if task in ("t1", "retest") else \
        free_text_overlap([{"item_id": r["row_id"], "row_type": T.ROW_ITEM, "note": r.get("note", "")} for r in norm],
                          {s: [{"item_id": x["row_id"], "row_type": T.ROW_ITEM, "note": x.get("note", "")} for x in
                               map(json.loads, (paths.root / rc["labels"]).read_text().splitlines())]
                           for s, rc in rec["frozen"].items() if rc["task"] == "t4" and rc["name"] != name})
    if ov["identical_total"]:
        fails.append("free-text overlap: identical item-level text with another source (D11)")
    for s, rc in rec["frozen"].items():
        if rc["name"] == name or rc["task"] != task or rc.get("sitting") != sitting:
            continue
        ofp = rc["fingerprint"]
        if ofp["sha256"] == fp["sha256"]:
            fails.append(f"format fingerprint: byte-identical to {s}")
        p1, p2 = fp.get("props") or {}, ofp.get("props") or {}
        if p1.get("created") and p1.get("creator") and (p1.get("created"), p1.get("creator")) == (p2.get("created"), p2.get("creator")):
            fails.append(f"format fingerprint: xlsx created+creator equal to {s}")
    receipt_base = {"slot": slot, "name": name, "pseudonym": e["pseudonym"], "task": task, "sitting": sitting,
                    "file_name": file.name, "sha256": digest, "received_at_utc": V.iso(recv_dt), "received_at_ist": V.ist(recv_dt),
                    "received_at_source": recv_src, "fingerprint": fp, "minutes_header": mh, "free_text_overlap": ov,
                    "photo": {"file_name": Path(photo).name, "sha256": V.sha256_file(Path(photo))},
                    "minutes_log": {k: mins[k] for k in ("sittings_logged", "total_minutes_given", "total_minutes_from_times",
                                                         "first_start_utc", "last_end_utc")} if mins else None,
                    "sent_packet_sha256": sent_meta["sha256"], "decided_at_utc": V.iso(now)}
    if fails:
        rec["excluded"][slot] = {**receipt_base, "reasons": fails, "note": "excluded under Amendment 7; no replacement is offered"}
        save_rec(paths, rec)
        return {"status": "excluded", "reasons": fails, "receipt": rec["excluded"][slot]}
    fdir = paths.t1_dir / "sprint_frozen" / slot / f"{stamp}_{digest[:12]}"
    fdir.mkdir(parents=True, exist_ok=False)
    for src_p in (file, Path(minutes), Path(photo)):
        shutil.copyfile(src_p, fdir / src_p.name)
        (fdir / src_p.name).chmod(0o444)
    receipt = dict(receipt_base)
    if task in ("t1", "retest"):
        normp = fdir / f"{slot}_normalised.csv"
        T.write_sheet(normp, norm, T.SHEET_COLUMNS, header=None, input_columns=())
        normp.chmod(0o444)
        receipt.update({"normalised": str(normp.relative_to(paths.root)), "normalised_sha256": V.sha256_file(normp),
                        "items": sum(r["row_type"] == T.ROW_ITEM for r in norm), "rows": len(norm)})
    else:
        labels = [{"row_id": r["row_id"].strip(), "faithful": int(r["faithful"]), "answers_question": int(r["answers_question"]),
                   "bad_question": (r.get("bad_question") or "").strip().lower() == "yes", "note": (r.get("note") or "").strip()}
                  for r in norm]
        lp = fdir / f"{slot}_labels.jsonl"
        lp.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in labels), encoding="utf-8")
        lp.chmod(0o444)
        receipt.update({"labels": str(lp.relative_to(paths.root)), "labels_sha256": V.sha256_file(lp), "rows": len(labels)})
    receipt["frozen_dir"] = str(fdir.relative_to(paths.root))
    if task == "t1" and sitting == 2:
        receipt["retest_earliest_utc"] = V.iso(recv_dt + timedelta(hours=MIN_RETEST_HOURS))
    rec["frozen"][slot] = receipt
    # Shared minutes-template check against the other rater's same sitting/task (FAIL for both is decided at analyse).
    save_rec(paths, rec)
    return {"status": "frozen", "receipt": receipt}


# ---------------------------------------------------------------------------
# Retest
# ---------------------------------------------------------------------------


def final_t1_freeze(rec: Mapping[str, Any], pseudo: str) -> datetime | None:
    rc = rec["frozen"].get(f"{pseudo}_t1_s2") or rec["excluded"].get(f"{pseudo}_t1_s2")
    return datetime.fromisoformat(rc["received_at_utc"]) if rc else None


def release_retest(paths: Paths, name: str, *, tc: T.T1Config, paragraph_class: Mapping[str, str],
                   now: datetime | None = None) -> dict[str, Any]:
    now = now or V.utc_now()
    if now > LAST_SESSION_START:
        raise SprintError("refused: no new annotation session (retest) may start after Sat 10 Oct 06:00 IST")
    rec, key = load_rec(paths), _key(paths)
    pseudo = key["raters"][name]["pseudonym"]
    if pseudo in rec["retest_generated"]:
        raise SprintError("the retest packet was already released")
    t_final = final_t1_freeze(rec, pseudo)
    if t_final is None:
        raise SprintError(f"{pseudo}'s final T1 sitting is not frozen")
    gap = (now - t_final).total_seconds() / 3600
    if gap < MIN_RETEST_HOURS:
        raise SprintError(f"refused: {gap:.2f} h since the final T1 freeze; the retest opens at "
                          f"{V.ist(t_final + timedelta(hours=MIN_RETEST_HOURS))}")
    if V.sha256_file(paths.retest_hidden) != RETEST_HIDDEN_SHA256:
        raise SprintError("the hidden retest subsets changed")
    ids = json.loads(paths.retest_hidden.read_text())["subsets"][pseudo]["items"]
    drawn = drawn_rows(paths)
    rng = random.Random(RETEST_ORDER_SEED[pseudo])
    order = sorted(ids)
    rng.shuffle(order)
    block_of = {iid: pos // BLOCK + 1 for pos, iid in enumerate(order)}
    out = paths.hold / name
    sp = T.write_sheet(out / f"{name}_blind_sprint_retest.csv", sheet_for(order, drawn, block_of), T.SHEET_COLUMNS,
                       header=t1_header("sprint retest sheet"), input_columns=T.INPUT_COLUMNS)
    blocks = sorted(set(block_of.values()))
    mp = _write_csv(out / f"{name}_sprint_retest_minutes.csv", T1_MINUTES_COLUMNS,
                    [{c: (str(b) if c == "block" else "") for c in T1_MINUTES_COLUMNS} for b in blocks])
    texts, cited = C.earlier_labels(C.default_label_files(paths.t1_dir), C.gold_rows(paths.t1_dir))
    scores = C.score_strings(json.loads((paths.t1_dir / T.KEY_FILE).read_text())["items"])
    check = C.check_packet(sp, approved_ids=ids, drawn=drawn, tc=tc, paragraph_class=paragraph_class, texts=texts,
                           cited=cited, scores=scores)
    if not check["PASS"]:
        raise SprintError(f"B3 check failed for the retest packet: {check}")
    files = _release_files(paths, name, [(str(sp.relative_to(paths.root)), V.sha256_file(sp)),
                                         (str(mp.relative_to(paths.root)), V.sha256_file(mp))])
    rec["retest_generated"][pseudo] = {"released_utc": V.iso(now), "released_ist": V.ist(now), "gap_hours": round(gap, 2),
                                       "final_t1_freeze_utc": V.iso(t_final), "items": sorted(ids), "blocks": blocks,
                                       "sheet": {"path": str(sp.relative_to(paths.root)), "sha256": V.sha256_file(sp)},
                                       "minutes": {"path": str(mp.relative_to(paths.root)), "sha256": V.sha256_file(mp),
                                                   "header": list(T1_MINUTES_COLUMNS)},
                                       "order_seed": RETEST_ORDER_SEED[pseudo], "files": files, "b3_check": check}
    save_rec(paths, rec)
    return rec["retest_generated"][pseudo]


# ---------------------------------------------------------------------------
# Analysis (pre-registered statistics only)
# ---------------------------------------------------------------------------


def shared_minutes_template_fails(rec: Mapping[str, Any]) -> list[str]:
    """Amendment 7 check 3: both raters' logs for one sitting/task carry the same deviation -> FAIL both."""
    by: dict[tuple, list[tuple[str, str]]] = defaultdict(list)
    for store in ("frozen", "excluded"):
        for slot, rc in rec[store].items():
            sig = rc["minutes_header"].get("deviation_signature")
            if sig:
                by[(rc["task"], rc.get("sitting"), sig)].append((slot, rc["pseudonym"]))
    return sorted(s for v in by.values() if len({p for _, p in v}) > 1 for s, _ in v)


def cross_rater_overlap_fails(paths: Paths, rec: Mapping[str, Any]) -> dict[str, list[str]]:
    """Amendment 7 check 1 over ALL frozen files, whatever order they arrived in: a cell identical to the other rater's
    cell for the same item fails both files (ingest-time checks only see files already frozen)."""
    def cells(rc):
        if rc["task"] == "t4":
            return {(x["row_id"], "note"): " ".join(x["note"].split()).lower() for x in
                    map(json.loads, (paths.root / rc["labels"]).read_text().splitlines()) if len(" ".join(x["note"].split())) >= 15}
        rows = T.read_sheet(paths.root / rc["normalised"])
        return {k: " ".join(v.split()).lower() for k, v in T.item_text_cells(rows).items() if len(" ".join(v.split())) >= 15}
    frozen = {s: rc for s, rc in rec["frozen"].items() if s not in rec["excluded"]}
    c = {s: cells(rc) for s, rc in frozen.items()}
    fails: dict[str, list[str]] = defaultdict(list)
    for a, ra in frozen.items():
        for b, rb in frozen.items():
            if ra["name"] == rb["name"] or (ra["task"] == "t4") != (rb["task"] == "t4"):
                continue
            same = sum(1 for k, v in c[a].items() if c[b].get(k) == v)
            if same:
                fails[a].append(f"free-text overlap: {same} item-level cell(s) identical to {b} (D11)")
    return dict(fails)


def analyse(paths: Paths) -> dict[str, Any]:
    from src.benchmark import t1v2_reliability as R

    rec, key = load_rec(paths), _key(paths)
    rmap = rater_map(paths)
    overlap = cross_rater_overlap_fails(paths, rec)
    shared = sorted(set(shared_minutes_template_fails(rec)) | set(overlap))
    expected = [f"{rmap[n]}_{s}" for n in NAMES for s in ("t1_s1", "t1_s2", "t4", "retest")]
    pending = [s for s in expected if s not in rec["frozen"] and s not in rec["excluded"]]
    if pending:
        raise SprintError(f"refused: files not final yet: {pending} (each must be frozen or excluded)")
    usable = {s: rc for s, rc in rec["frozen"].items() if s not in shared}
    primary, _rows = R.load_primary_pass1(paths.t1_dir)
    ids = [g["item_id"] for g in gold_ids(paths)]
    labels = {"rater_1": primary}
    t1_excluded = {}
    for n in NAMES:
        p = rmap[n]
        slots = [f"{p}_t1_s1", f"{p}_t1_s2"]
        if all(s in usable for s in slots):
            merged: dict[str, Any] = {}
            for s in slots:
                rc = usable[s]
                np_ = paths.root / rc["normalised"]
                if V.sha256_file(np_) != rc["normalised_sha256"]:
                    raise SprintError(f"{s}: frozen file changed")
                merged.update(T.parse_labelled_items(T.read_sheet(np_)))
            labels[p] = merged
        else:
            t1_excluded[p] = [s for s in slots if s not in usable]
    res: dict[str, Any] = {"amendment": "7", "amendments_v6_sha256": AMENDMENTS_V6_SHA256,
                           "disclosure": "annotators had previously seen the items in an earlier, excluded annotation round",
                           "excluded_files": {**{s: rec["excluded"][s]["reasons"] for s in rec["excluded"]},
                                              **{s: overlap.get(s) or ["shared minutes-log template (Amendment 7, check 3)"]
                                                 for s in shared}},
                           "gold": "t1_validated_v1 (unchanged; reliability evidence only)"}
    if len(labels) >= 2:
        res["t1_sprint"] = R.analyse_group("SPRINT", labels, ids, description="106 gold items, 412 class rows; rater_1 frozen "
                                           "P2-004 pass 1 + sprint raters (both sittings)")
    res["t1_raters_excluded"] = t1_excluded
    res["retest"] = {}
    for n in NAMES:
        p = rmap[n]
        if p in labels and f"{p}_retest" in usable:
            rc = usable[f"{p}_retest"]
            rt = T.parse_labelled_items(T.read_sheet(paths.root / rc["normalised"]))
            g = rec["retest_generated"][p]
            r = R.retest(p, labels[p], rt, g["items"], interval={"gap_hours_release": g["gap_hours"],
                                                                 "final_t1_freeze_utc": g["final_t1_freeze_utc"],
                                                                 "retest_received_utc": rc["received_at_utc"]})
            r["label"] = "8-hour blind short-interval test-retest (supplementary)"
            res["retest"][p] = r
    key4 = json.loads((paths.t4_dir / "t4_faithfulness_key_v1.json").read_text())["rows"]
    ratings: dict[str, dict] = {"rater_1": {}}
    for l in (paths.t4_dir / "t4_faithfulness_labels_v1.jsonl").read_text().splitlines():
        x = json.loads(l)
        k = key4[x["row_id"]]
        ratings["rater_1"][(k["question_id"], k["answer_type"])] = x
    for n in NAMES:
        p = rmap[n]
        if f"{p}_t4" in usable:
            ratings[p] = {}
            for l in (paths.root / usable[f"{p}_t4"]["labels"]).read_text().splitlines():
                x = json.loads(l)
                k = key4[x["row_id"]]
                ratings[p][(k["question_id"], k["answer_type"])] = x
    if len(ratings) >= 2:
        repass = {(d["question_id"], d["answer_type"]): d["composite_score"]
                  for d in map(json.loads, (paths.t4_dir / "t4_repass_scores_v1.jsonl").read_text().splitlines()) if d.get("scored")}
        res["t4"] = R.t4_analysis(ratings, repass)
    return res

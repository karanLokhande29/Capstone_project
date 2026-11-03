#!/usr/bin/env python3
"""Sprint human annotation round (Amendment 7): build held packets and run the gates.

    python3 scripts/run_sprint_raters.py build                         # held packets + key (once)
    python3 scripts/run_sprint_raters.py status
    python3 scripts/run_sprint_raters.py start 1|2                     # gate: sprint start <1|2>
    python3 scripts/run_sprint_raters.py received <rater> <1|2> --file F --minutes M --photo P [--received-at "YYYY-MM-DD HH:MM"]
    python3 scripts/run_sprint_raters.py t4-received <rater> --file F --minutes M --photo P
    python3 scripts/run_sprint_raters.py retest <rater>                # refuses before 8 h after the final T1 freeze
    python3 scripts/run_sprint_raters.py retest-received <rater> --file F --minutes M --photo P
    python3 scripts/run_sprint_raters.py analyse                       # gate: sprint analyse

<rater> is meer or akash (stored only as rater_2 / rater_3). Nothing prints agreement before `analyse`.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.benchmark import sprint_raters as S  # noqa: E402
from src.benchmark import t1 as T  # noqa: E402
from src.common.config import load_config  # noqa: E402

PATHS = S.Paths(ROOT)


def _tc() -> T.T1Config:
    return T.T1Config.from_cfg(load_config(None))


def _pclass() -> dict[str, str]:
    from scripts.run_t1 import paragraph_classes
    from src.common.paths import PathResolver

    return paragraph_classes(PathResolver.from_config(load_config(None)))


def cmd_build(_a) -> int:
    key = S.build(PATHS, tc=_tc(), paragraph_class=_pclass())
    for name, e in key["raters"].items():
        p = e["pseudonym"]
        for s, m in e["sittings"].items():
            print(f"{p} sitting {s}: {len(m['items'])} items, blocks {m['blocks']}, B3 {'PASS' if m['b3_check']['PASS'] else 'FAIL'}, "
                  f"sheet {m['sheet']['sha256'][:12]}")
        print(f"{p} T4: 30 rows, check {'PASS' if e['t4']['check']['PASS'] else 'FAIL'}, sheet {e['t4']['sha256'][:12]}")
    print(f"key: {PATHS.key.relative_to(ROOT)} (read-only). Packets are HELD in {PATHS.hold.relative_to(ROOT)}/")
    return 0


def cmd_status(_a) -> int:
    rec = S.load_rec(PATHS)
    print("releases:", [(r.get("what"), r.get("sitting"), r["released_ist"]) for r in rec["releases"]] or "none")
    print("frozen:", {s: rc["received_at_ist"] for s, rc in rec["frozen"].items()} or "none")
    print("excluded:", {s: rc["reasons"] for s, rc in rec["excluded"].items()} or "none")
    for s, rc in rec["frozen"].items():
        if rc.get("retest_earliest_utc"):
            print(f"  {s}: retest opens {S.V.ist(datetime.fromisoformat(rc['retest_earliest_utc']))}")
    print("retests released:", {p: g["released_ist"] for p, g in rec["retest_generated"].items()} or "none")
    return 0


def _ingest(a, task: str, sitting: int | None) -> int:
    res = S.ingest(PATHS, name=a.rater, task=task, sitting=sitting, file=Path(a.file), minutes=Path(a.minutes),
                   photo=Path(a.photo) if a.photo else None, tc=_tc(), paragraph_class=_pclass(), received_at=a.received_at)
    if res["status"] == "invalid":
        print(f"INVALID attempt ({len(res['problems'])} problem(s)); nothing frozen. The rater may correct and re-send:")
        for p in res["problems"][:30]:
            print("  -", p)
        return 1
    if res["status"] == "excluded":
        print("EXCLUDED under Amendment 7 (final; no replacement is offered):")
        for r in res["reasons"]:
            print("  -", r)
        return 2
    rc = res["receipt"]
    print(f"FROZEN {rc['slot']} · received {rc['received_at_ist']} · sha256 {rc['sha256'][:12]} · free-text identical "
          f"{rc['free_text_overlap']['identical_total']} · minutes header as sent")
    if rc.get("retest_earliest_utc"):
        print(f"  retest for this rater opens at {S.V.ist(datetime.fromisoformat(rc['retest_earliest_utc']))}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    sub.add_parser("status")
    st = sub.add_parser("start")
    st.add_argument("sitting", type=int, choices=(1, 2))
    for name in ("received", "t4-received", "retest-received"):
        p = sub.add_parser(name)
        p.add_argument("rater", choices=S.NAMES)
        if name == "received":
            p.add_argument("sitting", type=int, choices=(1, 2))
        p.add_argument("--file", required=True)
        p.add_argument("--minutes", required=True)
        p.add_argument("--photo", required=True)
        p.add_argument("--received-at")
    rt = sub.add_parser("retest")
    rt.add_argument("rater", choices=S.NAMES)
    sub.add_parser("analyse")
    a = ap.parse_args()
    try:
        if a.cmd == "build":
            return cmd_build(a)
        if a.cmd == "status":
            return cmd_status(a)
        if a.cmd == "start":
            r = S.start(PATHS, a.sitting)
            print(f"released sitting {a.sitting}: " + "; ".join(f"{p}: {len(f)} files" for p, f in r["released"].items()))
            print(f"  -> {PATHS.ready.relative_to(ROOT)}/<rater>/ (send each folder to that rater only)")
            return 0
        if a.cmd == "received":
            return _ingest(a, "t1", a.sitting)
        if a.cmd == "t4-received":
            return _ingest(a, "t4", None)
        if a.cmd == "retest-received":
            return _ingest(a, "retest", None)
        if a.cmd == "retest":
            g = S.release_retest(PATHS, a.rater, tc=_tc(), paragraph_class=_pclass())
            print(f"retest released: {len(g['items'])} items, gap {g['gap_hours']} h, B3 {'PASS' if g['b3_check']['PASS'] else 'FAIL'}")
            return 0
        if a.cmd == "analyse":
            res = S.analyse(PATHS)
            out = PATHS.private / f"sprint_reliability_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
            out.write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str))
            print(f"-> {out.relative_to(ROOT)}")
            return 0
    except S.SprintError as exc:
        print(f"REFUSED: {exc}")
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

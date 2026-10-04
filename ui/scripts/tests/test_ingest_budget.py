"""Snapshot invariants: ≤ 25 RBI words per paragraph across all bundled uses; no private / identity fields; calibration order."""

import json

from cc_common import UI, rbi_words

SNAP = json.loads((UI / "src/data/snapshot.json").read_text(encoding="utf-8"))


def test_word_budget_per_paragraph():
    # source extraction values repeat per compared class; count unique values per paragraph instead of per unit
    uniq = {}
    for uid, f in SNAP["comparatorFields"].items():
        src = uid.split("|")[0].removeprefix("t1_")
        for r in f.get("rows", []):
            if r.get("sourceValue"):
                uniq.setdefault(src, set()).add(r["sourceValue"])
            if r.get("targetValue") and f.get("decisivePid"):
                uniq.setdefault(f["decisivePid"], set()).add(r["targetValue"])
    for pid, vals in uniq.items():
        n = len(rbi_words(SNAP["pointers"].get(pid, {}).get("excerpt") or "")) + sum(len(rbi_words(v)) for v in vals)
        assert n <= 25, (pid, n)


def test_no_identity_or_private_fields():
    text = json.dumps(SNAP, ensure_ascii=False).lower()
    found = [bad for bad in ("karan", "akash", "meer", "reports/private", "applies_to_rationale", "annotator:") if bad in text]
    assert not found, found
    for it in SNAP["t1Items"]:
        assert it["route"] in ("single-pass", "retest-consistent", "adjudicated")


def test_confidence_frozen_before_evaluation():
    m = json.loads((UI / "src/data/confidence_model_v1.json").read_text())
    f = json.loads((UI / "src/data/confidence_frozen_v1.json").read_text())
    assert m["order"].index("M2 fitted on dev and frozen") < m["order"].index("gold labels read")
    assert f["frozenUtc"] <= m["evaluatedUtc"]
    assert m["models"]["M2"]["weights"] == f["M2"]["weights"]

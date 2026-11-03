"""P2-004 §T tests for Part A (guidelines v3): label rules, candidate labels, sampling, sheets and guards.

κ / Fleiss / bootstrap are the P1-005 implementations and are tested in
tests/test_benchmark_annotation.py; Parts C-E add their own ingest tests.
"""

from __future__ import annotations

import csv
import dataclasses
import logging
import re
from pathlib import Path

import pytest
import yaml

from src.benchmark import t1 as T
from src.benchmark.annotation import GUIDELINES_VERSION, TASK_FILE_COLUMNS, _read_vote_file

REPO = Path(__file__).resolve().parents[1]
GUIDELINES = REPO / "data" / "benchmark" / "templates" / "ANNOTATION_INSTRUCTIONS.md"
CORE = ("All India Financial Institutions", "Asset Reconstruction Companies", "Commercial Banks",
        "Credit Information Companies", "Local Area Banks", "Non-Banking Financial Companies", "Payments Banks",
        "Regional Rural Banks", "Rural Co-operative Banks", "Small Finance Banks", "Urban Co-operative Banks")
CB, SFB, PB, NBFC = "Commercial Banks", "Small Finance Banks", "Payments Banks", "Non-Banking Financial Companies"


def tc(**over) -> T.T1Config:
    cfg = yaml.safe_load((REPO / "config" / "config.yaml").read_text(encoding="utf-8"))
    return dataclasses.replace(T.T1Config.from_cfg(cfg), **over)


# -- guidelines v3 -------------------------------------------------------------


def test_guidelines_file_declares_the_version_the_tooling_records():
    text = GUIDELINES.read_text(encoding="utf-8")
    m = re.search(r"\*\*Guidelines version: (v[\d.]+)\*\*", text)
    assert m and m.group(1) == GUIDELINES_VERSION == tc().guidelines_version == "v3.1"
    for rule in ("v3.1", "v3.2", "v3.3", "v3.4", "v3.5", "v3.6", "v3.7", "v3.8", "v3.9", "v3.10"):
        assert f"## {rule} " in text, rule
    for kept in ("## v2.1 ", "## v2.2 ", "## v2.3 ", "## v2.4 ", "## v2.5 ", "## v2.6 "):
        assert kept in text, "v2 rules are kept"
    assert "This project has one annotator" not in text
    assert "Karan is the primary annotator" in text


# -- A2 / v3.6 flag rule -------------------------------------------------------


@pytest.mark.parametrize("judgements, flag, adjudicate", [
    ({CB: "same", SFB: "same"}, T.FLAG_SHARED, False),
    ({CB: "same", SFB: "none"}, T.FLAG_SHARED, False),
    ({CB: "same", SFB: "different"}, T.FLAG_CLASS_SPECIFIC, False),
    ({CB: "different", SFB: "none"}, T.FLAG_CLASS_SPECIFIC, False),
    ({CB: "none", SFB: "none"}, T.FLAG_ABSENT, False),
    ({CB: "none", SFB: "unsure"}, None, True),
    ({CB: "unsure", SFB: "unsure"}, None, True),
    ({CB: "same", SFB: "unsure"}, T.FLAG_SHARED, True),
    ({CB: "different", SFB: "unsure"}, T.FLAG_CLASS_SPECIFIC, True),
])
def test_flag_rule_v3_6(judgements, flag, adjudicate):
    out = T.derive_flag(judgements)
    assert out["flag"] == flag and out["ambiguous"] == (flag is None) and out["needs_adjudication"] == adjudicate


def test_flag_rule_rejects_unknown_or_empty_judgements():
    with pytest.raises(T.T1Error):
        T.derive_flag({CB: "maybe"})
    with pytest.raises(T.T1Error):
        T.derive_flag({})


# -- A3 candidate labels and the candidate benchmark ---------------------------


def test_candidate_labels_read_matched_as_positive_and_below_threshold_as_none():
    pos = T.candidate_labels(PB, {CB: T.STATUS_MATCHED, SFB: T.STATUS_BELOW})
    assert pos["applies_to_candidate"] == sorted([PB, CB])
    assert pos["differential_flag_candidate"] == T.CANDIDATE_FLAG_POSITIVE
    assert pos["label_status"] == "candidate" and pos["provenance"] == T.PROVENANCE_CANDIDATE
    neg = T.candidate_labels(PB, {CB: T.STATUS_BELOW, SFB: T.STATUS_BELOW})
    assert neg["applies_to_candidate"] == [PB] and neg["differential_flag_candidate"] == T.FLAG_ABSENT
    with pytest.raises(T.T1Error):
        T.candidate_labels(PB, {CB: T.STATUS_NO_DIRECTION})


class _Cand:
    def __init__(self, cid, cls):
        self.candidate_id = f"t1c_{cid}"
        self.paragraph_id = cid
        self.document_id = cid.split("::")[0]
        self.entity_class = cls


def _fixture_benchmark():
    cands = [_Cand("md_1::p00001", PB), _Cand("md_1::p00002", PB), _Cand("md_2::p00001", CB)]
    units = {"t1c_md_1::p00001": [{"start": 0, "end": 30, "text": "A payments bank shall report."}],
             "t1c_md_1::p00002": [{"start": 0, "end": 99, "text": "Further, the repeal of these directions, "
                                   "instructions, or guidelines shall not in any way prejudicially affect: x"}],
             "t1c_md_2::p00001": [{"start": 0, "end": 30, "text": "A bank shall report monthly."}]}
    rec = lambda src, tgt, st: {"source_candidate_id": src, "target_entity_class": tgt, "status": st,
                                "top_targets": [{"candidate_id": "t1c_md_9::p00001"}] if st != T.STATUS_NO_DIRECTION else []}
    records = {"t1c_md_1::p00001": [rec("t1c_md_1::p00001", CB, T.STATUS_MATCHED),
                                    rec("t1c_md_1::p00001", SFB, T.STATUS_BELOW),
                                    rec("t1c_md_1::p00001", NBFC, T.STATUS_NO_DIRECTION)],
               "t1c_md_2::p00001": [rec("t1c_md_2::p00001", PB, T.STATUS_BELOW)]}
    paragraphs = {c.paragraph_id: {"clause_path": "4(b)", "section_id": "4", "text": "t"} for c in cands}
    manifest = {"md_1": {"subject_family": "F1", "update_date": "December 29, 2025"},
                "md_2": {"subject_family": "F1", "update_date": None}}
    first = {"md_2": "RBI/2025-26/1\nNovember 28, 2025\nDirections"}
    amend = T.amendment_index([{"item_id": "amd_1", "published_date": "2026-03-01",
                                "text": "In paragraph 4, sub-paragraph 4(b) shall be deleted.",
                                "fields": {"linked_md_ids": ["md_1"], "paragraph_refs": ["sub-paragraph 4(b)"]}}])
    from src.benchmark.matching import boilerplate_kind

    return T.build_candidate_benchmark(eligible=cands, units_by_candidate=units, records_by_source=records,
                                       paragraphs=paragraphs, manifest=manifest, first_paragraph=first,
                                       amendments=amend, era_cutoff="2025-11-28", boilerplate_kind=boilerplate_kind)


def test_candidate_benchmark_excludes_boilerplate_and_never_compares_no_direction_classes():
    out, metrics = _fixture_benchmark()
    assert metrics["excluded_boilerplate"] == 1 and [r["item_id"] for r in out] == ["t1_md_1::p00001", "t1_md_2::p00001"]
    r = out[0]
    assert r["compared_classes"] == [CB, SFB]
    assert r["not_compared"] == {NBFC: T.STATUS_NO_DIRECTION}
    assert NBFC not in r["per_class_candidate"], "a no_direction class never becomes none"
    assert r["label_status"] == "candidate"
    assert (r["in_force_from"], r["in_force_from_basis"]) == ("2025-12-29", "updated_as_on")
    assert r["amended_by"] == ["amd_1"] and r["in_force_to"] == "2026-03-01"
    assert (out[1]["in_force_from"], out[1]["in_force_from_basis"]) == ("2025-11-28", "issue_date_letterhead")
    assert out[1]["in_force_to"] is None and out[1]["amended_by"] == []


def test_amendment_parsing_ranges_lists_and_nested_subparas():
    assert T.parse_paragraph_refs(["sub-paragraph 4 (10)", "paragraphs 86 to 88"]) == {"4(10)", "86", "87", "88"}
    text = ("modifications in Paragraph 4:- (i) Sub-paragraph 4 (6) shall be substituted. In paragraph 5, a) "
            "Sub-para (1) shall be substituted. paragraphs 28, 30 and 33 shall be deleted.")
    ends = T.amendment_index([{"item_id": "a", "published_date": "2026-01-01", "text": text,
                               "fields": {"linked_md_ids": ["m"], "paragraph_refs": []}}])["m"][0]["ends"]
    assert set(ends) == {"4(6)", "28", "30", "33"}, "paragraphs 4 and 5 themselves are not ended"
    assert T.ref_covers("4", "4(b)(ii)") and T.ref_covers("4(b)", "4(b)") and not T.ref_covers("4", "41")


# -- A4 size and the checkpoint ------------------------------------------------


def test_size_formula_reproduces_section_k():
    s = T.size_calc(tc())
    assert (s["n_target"], s["retest_items"], s["blocks"]) == (123, 25, 7) and not s["underpowered"]


def test_checkpoint_rederives_n_and_flags_underpowered_below_100():
    fast = T.checkpoint(tc(), measured_minutes=72.2, items_done=20, sample_size=123)
    assert fast["n_target"] == 123 and fast["blocks_to_keep"] == 7 and not fast["flag_underpowered"]
    slow = T.checkpoint(tc(), measured_minutes=120, items_done=20, sample_size=123)  # 6 min/item
    assert slow["n_target"] == 68 and slow["flag_underpowered"]
    assert slow["blocks_to_keep"] == 3 and slow["items_kept"] == 60, "whole blocks, dropped from the end"


# -- A5 sampling ---------------------------------------------------------------


def _pool(per_class: dict[str, int]):
    recs = []
    for cls, n in per_class.items():
        for i in range(n):
            fam = f"F{i % 3}"
            others = [c for c in CORE if c != cls][:5]
            recs.append({"item_id": f"t1_{cls[:3]}_{i:04d}", "source_candidate_id": f"t1c_{cls[:3]}_{i:04d}",
                         "paragraph_id": f"{cls[:3]}::p{i:05d}", "entity_class": cls, "subject_family": fam,
                         "compared_classes": others, "differential_flag_candidate":
                         T.FLAG_ABSENT if i % 4 == 0 else T.CANDIDATE_FLAG_POSITIVE,
                         "per_class_candidate": {c: T.STATUS_MATCHED for c in others},
                         "top_targets": {c: ["t1c_md_9::p00001", "t1c_md_9::p00002"] for c in others}})
    return recs


SIZES = {c: n for c, n in zip(CORE, (2400, 290, 4700, 280, 2300, 2000, 2300, 1800, 1470, 4290, 2580))}


def test_pool_excludes_pilot_validation_pairs_and_single_class_items():
    recs = _pool({CB: 40, SFB: 40})
    recs[0]["compared_classes"] = recs[0]["compared_classes"][:1]
    drawn = T.draw_sample(recs, tc(per_class_floor=6), 20, excluded_paragraphs={recs[1]["paragraph_id"]},
                          excluded_candidates={recs[2]["source_candidate_id"]})
    assert drawn["excluded"] == {"fewer_than_min_compared": 1, "pilot": 1, "p2002_validation_pair": 1}
    ids = {it["item_id"] for it in drawn["items"]}
    assert not ids & {recs[0]["item_id"], recs[1]["item_id"], recs[2]["item_id"]}


def test_sample_allocation_floors_k_cap_and_stratified_prefixes():
    cfg = tc()
    drawn = T.draw_sample(_pool(SIZES), cfg, 123, excluded_paragraphs=set(), excluded_candidates=set())
    items = drawn["items"]
    assert len(items) == 123 and all(v >= 6 for v in drawn["allocation"].values())
    assert all(len(it["sample_compared_classes"]) <= cfg.max_compared_classes for it in items)
    assert all(set(it["sample_compared_classes"]) <= set(it["compared_classes"]) for it in items)
    for blocks in range(3, 8):  # any prefix of >= 3 whole blocks keeps every class with >= 6 eligible
        prefix = [it for it in items if it["block"] <= blocks]
        assert {it["entity_class"] for it in prefix} == set(CORE), blocks


def test_retest_subset_is_20_percent_spread_across_blocks_and_second_raters_come_from_blocks_1_to_3():
    drawn = T.draw_sample(_pool(SIZES), tc(), 123, excluded_paragraphs=set(), excluded_candidates=set())
    items = {it["item_id"]: it for it in drawn["items"]}
    assert len(drawn["retest_ids"]) == 25
    blocks = {items[i]["block"] for i in drawn["retest_ids"]}
    assert len(blocks) >= 5, blocks
    assert len(drawn["second_rater_ids"]) == 30 and all(items[i]["block"] <= 3 for i in drawn["second_rater_ids"])
    again = T.draw_sample(_pool(SIZES), tc(), 123, excluded_paragraphs=set(), excluded_candidates=set())
    assert [it["item_id"] for it in again["items"]] == list(items) and again["retest_ids"] == drawn["retest_ids"]


# -- A6 sheets -----------------------------------------------------------------


def _sheet(n=3):
    cfg = tc(per_class_floor=1)
    drawn = T.draw_sample(_pool({CB: 30, SFB: 30}), cfg, n, excluded_paragraphs=set(), excluded_candidates=set())
    items = [{**it, "obligation_span": {"text": "A bank shall report."}} for it in drawn["items"]]
    paragraphs = {it["paragraph_id"]: {"text": "Paragraph text."} for it in items}
    paragraphs.update({"md_9::p00001": {"text": "Target one."}, "md_9::p00002": {"text": "Target two."}})
    return T.sheet_rows(items, paragraphs, cfg), drawn


def test_sheets_are_blind_long_format_and_hide_the_subsets():
    rows, drawn = _sheet()
    T.assert_blind(rows)
    assert [r["row_type"] for r in rows[:1]] == ["item"]
    assert sum(r["row_type"] == "class" for r in rows) == sum(len(it["sample_compared_classes"]) for it in drawn["items"])
    text = " ".join(v for r in rows for v in r.values())
    for hidden in ("matched", "below_threshold", "semantic", "0.9", "shared_or_class_specific", "retest"):
        assert hidden not in text, hidden
    with pytest.raises(T.T1Error):
        T.assert_blind([{**rows[0], "judgement": "same"}])
    with pytest.raises(T.T1Error):
        T.assert_blind([{**{c: "" for c in T.SHEET_COLUMNS}, "semantic_score": "0.9"}])


def test_write_sheet_has_bom_note_line_and_refuses_to_overwrite_labels(tmp_path):
    rows, _ = _sheet()
    path = T.write_sheet(tmp_path / "s.csv", rows, T.SHEET_COLUMNS, header=T.SHEET_HEADER, input_columns=T.INPUT_COLUMNS)
    assert path.read_bytes()[:3] == b"\xef\xbb\xbf"
    assert T.read_sheet(path) == rows
    labelled = [dict(r) for r in rows]
    labelled[0]["applies_to"] = CB
    T.write_sheet(path, labelled, T.SHEET_COLUMNS, header=T.SHEET_HEADER, input_columns=T.INPUT_COLUMNS)
    with pytest.raises(T.T1Error):
        T.write_sheet(path, rows, T.SHEET_COLUMNS, header=T.SHEET_HEADER, input_columns=T.INPUT_COLUMNS)


def test_excel_quoted_note_line_and_bom_are_read(tmp_path):
    path = tmp_path / "x.csv"
    body = '"# note, quoted by Excel",,,\r\nitem_id,judgement\r\nt1_a,same\r\n'
    path.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    assert T.read_sheet(path) == [{"item_id": "t1_a", "judgement": "same"}]


def test_pilot_reader_skips_the_note_line(tmp_path):
    path = tmp_path / "annotation_pilot_karan_pass2.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        fh.write("# Pilot retest (pass 2). Blind test-retest.\n")
        w = csv.DictWriter(fh, fieldnames=list(TASK_FILE_COLUMNS))
        w.writeheader()
        w.writerow({**{c: "" for c in TASK_FILE_COLUMNS}, "label_id": "t1_pilot_x", "applies_to": CB,
                    "differential_flag": "shared"})
    votes = _read_vote_file(path, rater_id="karan", pass_no=2, valid_label_ids={"t1_pilot_x"},
                            valid_classes=[CB], logger=logging.getLogger("t"))
    assert len(votes) == 1 and votes[0].applies_to == (CB,)


# -- ingest-side guards ----------------------------------------------------------


def _labelled(rows, fill):
    out = []
    for r in rows:
        r = dict(r)
        if r["row_type"] == "item":
            r.update(applies_to=r["source_class"], applies_to_rationale="Span names the class.")
        else:
            r.update(fill(r))
        out.append(r)
    return out


def test_validation_catches_vocabulary_blanks_ids_and_not_obligation_notes():
    rows, _ = _sheet(2)
    cls_of = {"md_9::p00001": rows[1]["target_class"]}
    good = _labelled(rows, lambda r: {"judgement": "same", "matched_paragraph_id": "md_9::p00001"}
                     if r["target_class"] == rows[1]["target_class"] else {"judgement": "none"})
    assert T.validate_labelled(good, tc(), cls_of) == []
    stand_in = [dict(r) for r in good]
    stand_in[0]["applies_to"] = f"{rows[0]['source_class']};Payment and Settlement System"
    assert T.validate_labelled(stand_in, tc(), cls_of) == [], "v2.2 stand-ins are allowed in applies_to"
    bad = [dict(r) for r in good]
    bad[0]["applies_to"] = "Banks"
    bad[1]["matched_paragraph_id"] = "md_9-p1"
    bad[2]["judgement"] = ""
    probs = T.validate_labelled(bad, tc(), cls_of)
    assert any("v2.2 vocabulary" in p for p in probs)
    assert any("not md_NNNNN" in p for p in probs)
    assert any("judgement is blank" in p for p in probs)
    wrong_class = [dict(r) for r in good]
    wrong_class[1]["matched_paragraph_id"] = "md_9::p00002"
    assert any("is not a paragraph of" in p for p in T.validate_labelled(wrong_class, tc(), cls_of))
    rejected = [dict(r) for r in rows]
    rejected[0].update(not_obligation="yes")
    assert any("needs the reason in note" in p for p in T.validate_labelled(rejected, tc(), cls_of))
    rejected[0].update(note="not an RE obligation — duty on customer")
    only_item = [r for r in rejected if r["item_id"] == rows[0]["item_id"]]
    assert T.validate_labelled(only_item, tc(), cls_of) == [], "class rows of a rejected item may stay blank"


def test_d11_guard_refuses_a_copied_second_rater_file():
    rows, _ = _sheet(6)
    karan = _labelled(rows, lambda r: {"judgement": "none", "note": "Checked both paragraphs carefully."})
    with pytest.raises(T.T1Error):
        T.assert_second_rater_independent(karan, [dict(r) for r in karan], "akash")
    own = _labelled(rows, lambda r: {"judgement": "none", "note": f"My own reading of {r['target_class']}."})
    for r in own:
        if r["row_type"] == "item":
            r["applies_to_rationale"] = f"Own words {r['item_id']}"
    T.assert_second_rater_independent(karan, own, "akash")


def test_no_date_lock_or_minimum_interval_remains():
    """Policy of 2026-09-27: blind test-retest with no enforced minimum inter-pass interval."""
    assert not hasattr(T, "check_date_lock") and not hasattr(T, "LOCKS_FILE")
    cfg = tc()
    assert not hasattr(cfg, "pilot_retest_earliest") and not hasattr(cfg, "retest_min_gap_days")
    raw = yaml.safe_load((REPO / "config" / "config.yaml").read_text(encoding="utf-8"))
    assert "min_gap_days" not in raw["benchmark"]["retest"]
    text = " ".join(GUIDELINES.read_text(encoding="utf-8").split())
    assert "blind test-retest with no enforced minimum inter-pass interval" in text
    assert "At least 5 days" not in text and "Five or more days later" not in text


def test_minutes_log_lists_karan_blocks_and_both_second_raters():
    rows = T.minutes_rows(tc(), 7)
    assert [r["block"] for r in rows if r["rater"] == "karan"] == [str(b) for b in range(1, 8)]
    assert {r["rater"] for r in rows} == {"karan", "akash", "meer"}
    assert all(not r["minutes"] for r in rows)


# -- IRR set ---------------------------------------------------------------------


def test_irr_draw_excludes_the_main_sample_and_stratifies_with_a_floor_of_two():
    recs = _pool(SIZES)
    recs[5]["compared_classes"] = recs[5]["compared_classes"][:1]
    main = {r["item_id"] for r in recs[:400]}
    from src.benchmark.matching import boilerplate_kind

    for r in recs:
        r["obligation_span"] = {"text": "A bank shall report."}
    recs[500]["obligation_span"] = {"text": "Further, the repeal of these directions, instructions, or guidelines "
                                            "shall not in any way prejudicially affect: rights"}
    drawn = T.draw_irr(recs, tc(), excluded_items=main, excluded_paragraphs={recs[501]["paragraph_id"]},
                       excluded_candidates={recs[502]["source_candidate_id"]}, boilerplate_kind=boilerplate_kind)
    items = drawn["items"]
    ids = [it["item_id"] for it in items]
    assert len(ids) == 30 == len(set(ids)) and not set(ids) & main
    assert not set(ids) & {recs[500]["item_id"], recs[501]["item_id"], recs[502]["item_id"]}
    assert drawn["excluded"]["main_sample"] == 400 and drawn["excluded"]["boilerplate"] == 1
    assert drawn["excluded"]["pilot"] == 1 and drawn["excluded"]["p2002_validation_pair"] == 1
    assert all(v >= 2 for v in drawn["allocation"].values()) and len(drawn["allocation"]) == 11
    assert all(len(it["sample_compared_classes"]) == min(4, len(it["compared_classes"])) for it in items)
    assert drawn["seed"] == T.IRR_SEED
    again = T.draw_irr(recs, tc(), excluded_items=main, excluded_paragraphs={recs[501]["paragraph_id"]},
                       excluded_candidates={recs[502]["source_candidate_id"]}, boilerplate_kind=boilerplate_kind)
    assert [it["item_id"] for it in again["items"]] == ids


def test_irr_minutes_rows_keep_existing_entries_and_are_added_once():
    existing = [{"rater": "karan", "block": "1", "started_at": "09:00", "ended_at": "10:10", "minutes": "70",
                 "note": ""}]
    rows = T.irr_minutes_rows(existing)
    assert rows[0] == existing[0]
    assert [(r["rater"], r["block"]) for r in rows[1:]] == [(r, "irr") for r in T.IRR_RATERS]
    assert T.irr_minutes_rows(rows) == rows


def _irr_env(tmp_path):
    rows, _ = _sheet(3)
    t1_dir = tmp_path / "t1"
    (t1_dir / T.IRR_RECEIVED_DIR).mkdir(parents=True)
    cls_of = {"md_9::p00001": rows[1]["target_class"]}

    def labelled(rater, rationale="{r}: span names the class for {i}.", judgement="none"):
        out = []
        for r in rows:
            r = dict(r)
            if r["row_type"] == "item":
                r.update(applies_to=r["source_class"], applies_to_rationale=rationale.format(r=rater, i=r["item_id"]))
            else:
                r.update(judgement=judgement)
            out.append(r)
        path = tmp_path / f"annotation_p2004_irr_{rater}.csv"
        T.write_sheet(path, out, T.SHEET_COLUMNS, header=T.IRR_HEADER, input_columns=())
        return path

    def ingest(path, rater, receipts):
        import hashlib

        rec = T.ingest_irr(path, rater, t1_dir=t1_dir, drawn=rows, tc=tc(), paragraph_class=cls_of,
                           receipts=receipts, received_at="2026-09-28T10:00:00+00:00",
                           sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        (t1_dir / T.IRR_RECEIVED_DIR / rec["stored_as"]).write_bytes(path.read_bytes())
        receipts[rater] = rec
        return rec

    return rows, t1_dir, labelled, ingest


def test_irr_ingest_accepts_each_file_once_and_records_sha_and_time(tmp_path):
    _, _, labelled, ingest = _irr_env(tmp_path)
    receipts = {}
    rec = ingest(labelled("akash"), "akash", receipts)
    assert rec["received_at"] == "2026-09-28T10:00:00+00:00" and len(rec["sha256"]) == 64
    second = labelled("akash", rationale="{r} revised: {i}.")
    with pytest.raises(T.T1Error, match="already received"):
        ingest(second, "akash", receipts)
    ingest(labelled("meer"), "meer", receipts)
    with pytest.raises(T.T1Error, match="unknown IRR rater"):
        ingest(labelled("akash"), "someone", receipts)


def test_irr_ingest_refuses_not_independent_and_mock_files(tmp_path):
    _, t1_dir, labelled, ingest = _irr_env(tmp_path)
    src = labelled("akash")
    parked = t1_dir / T.NOT_INDEPENDENT_DIR / src.name
    parked.parent.mkdir()
    parked.write_bytes(src.read_bytes())
    with pytest.raises(T.T1Error, match="not_independent"):
        ingest(parked, "akash", {})
    mock = tmp_path / "annotation_p2004_irr_akash_MOCK.csv"
    mock.write_bytes(src.read_bytes())
    with pytest.raises(T.T1Error, match="_mock"):
        ingest(mock, "akash", {})


def test_irr_ingest_refuses_identical_item_text_across_raters_but_not_prescribed_wording(tmp_path):
    rows, _, labelled, ingest = _irr_env(tmp_path)
    receipts = {}
    ingest(labelled("akash", rationale="Span names the class, {i}."), "akash", receipts)
    with pytest.raises(T.T1Error, match="identical to akash"):
        ingest(labelled("meer", rationale="Span names the class, {i}."), "meer", receipts)
    with pytest.raises(T.T1Error, match="byte-identical"):
        ingest(labelled("karan", rationale="Span names the class, {i}."), "karan", receipts)
    mine = T.item_text_cells([{**rows[0], "note": "not an RE obligation — duty on customer"}])
    assert mine == {}, "the v2.1 wording the guidelines prescribe may repeat across raters"


def test_irr_ingest_refuses_changed_shown_columns_and_blank_judgements(tmp_path):
    rows, _, labelled, ingest = _irr_env(tmp_path)
    path = labelled("akash")
    edited = T.read_sheet(path)
    edited[0]["source_span"] = "edited"
    T.write_sheet(path, edited, T.SHEET_COLUMNS, header=None, input_columns=())
    with pytest.raises(T.T1Error, match="differ from the drawn sheet"):
        ingest(path, "akash", {})
    blank = labelled("meer", judgement="")
    with pytest.raises(T.T1Error, match="judgement is blank"):
        ingest(blank, "meer", {})


# -- IRR scoring -------------------------------------------------------------------


def _rater_rows(judgements_by_item, not_obligation=(), applies=None):
    """Long-format rows for items i0..; each item has classes A..D with the given judgements."""
    rows = []
    for n, judgements in enumerate(judgements_by_item):
        iid = f"t1_i{n}"
        no = iid in not_obligation
        rows.append({"item_id": iid, "row_type": "item", "source_class": CB,
                     "not_obligation": "yes" if no else "", "applies_to": "" if no else (applies or {}).get(iid, CB),
                     "applies_to_rationale": "", "note": "", "target_class": "", "judgement": "",
                     "matched_paragraph_id": ""})
        for cls, j in zip((SFB, PB, NBFC, "Local Area Banks"), judgements):
            rows.append({"item_id": iid, "row_type": "class", "source_class": CB, "target_class": cls,
                         "judgement": "" if no else j, "matched_paragraph_id": ""})
    return rows


def test_parse_labelled_items_derives_the_v3_flag_and_skips_rejected_items():
    items = T.parse_labelled_items(_rater_rows([("same", "none"), ("none", "none"), ("none", "unsure"),
                                                ("same", "same")], not_obligation={"t1_i3"}))
    assert [items[f"t1_i{n}"]["flag"] for n in range(4)] == [T.FLAG_SHARED, T.FLAG_ABSENT, T.FLAG_AMBIGUOUS, None]
    assert items["t1_i2"]["needs_adjudication"] and items["t1_i3"]["not_obligation"]


def test_irr_metrics_perfect_agreement_and_complete_items_only_for_fleiss():
    base = [("same", "none"), ("different", "none"), ("none", "none"), ("same", "same")] * 3
    labels = {r: T.parse_labelled_items(_rater_rows(base)) for r in ("a", "b")}
    labels["c"] = T.parse_labelled_items(_rater_rows(base, not_obligation={"t1_i0"}))
    m = T.irr_metrics(labels, seed=1, resamples=200)
    ab = m["pairwise"]["a-b"]
    assert ab["differential_flag"]["kappa"] == 1.0 and ab["per_class_judgement"]["kappa"] == 1.0
    assert ab["applies_to"]["exact_set_agreement"] == 1.0 and ab["applies_to"]["mean_jaccard"] == 1.0
    assert ab["differential_flag"]["bootstrap"]["ci95"] == [1.0, 1.0]
    assert m["pairwise"]["a-c"]["differential_flag"]["n_items"] == 11, "c rejected one item"
    assert m["fleiss"]["differential_flag"]["n_items"] == 11 and m["fleiss"]["differential_flag"]["kappa"] == 1.0
    assert m["fleiss"]["not_obligation"]["n_items"] == 12
    assert m["fleiss"]["applies_to_all_three_identical"]["all_three_source_class_only"] == 11


def test_irr_metrics_known_kappa_and_disagreement_listing():
    a = T.parse_labelled_items(_rater_rows([("same", "same"), ("none", "none"), ("same", "none"), ("none", "none")]))
    b = T.parse_labelled_items(_rater_rows([("same", "same"), ("none", "none"), ("none", "none"), ("same", "unsure")],
                                           applies={"t1_i0": f"{CB};{SFB}"}))
    m = T.irr_metrics({"a": a, "b": b}, seed=1, resamples=100)
    pc = m["pairwise"]["a-b"]["per_class_judgement"]
    assert pc["n_units"] == 8 and pc["observed_agreement"] == 5 / 8
    from src.benchmark.annotation import cohen_kappa

    assert pc["kappa"] == cohen_kappa([("same", "same"), ("same", "same"), ("none", "none"), ("none", "none"),
                                       ("same", "none"), ("none", "none"), ("none", "same"), ("none", "unsure")],
                                      T.JUDGEMENTS)
    assert m["pairwise"]["a-b"]["applies_to"]["exact_set_agreement"] == 3 / 4
    dis = {x["item_id"]: x["differs_on"] for x in T.irr_disagreements({"a": a, "b": b})}
    assert set(dis) == {"t1_i0", "t1_i2", "t1_i3"}
    assert dis["t1_i0"] == ["applies_to"] and "unsure_or_ambiguous" in dis["t1_i3"]


# -- Part C ------------------------------------------------------------------------


def test_structure_problems_catch_schema_order_duplicates_and_edits():
    rows, _ = _sheet(2)
    assert T.structure_problems(rows, rows) == []
    assert any("differ from the drawn sheet" in p for p in T.structure_problems(list(reversed(rows)), rows))
    assert any("duplicate" in p for p in T.structure_problems(rows + [rows[1]], rows + [rows[1]]))
    assert any("columns" in p for p in T.structure_problems([{**rows[0], "extra": ""}], rows))


def test_validate_annotation_file_reports_without_modifying(tmp_path):
    rows, _ = _sheet(2)
    path = T.write_sheet(tmp_path / "p.csv", rows, T.SHEET_COLUMNS, header=None, input_columns=())
    before = path.read_bytes()
    v = T.validate_annotation_file(path, rows, tc(), {})
    assert v["problems"] and v["has_bom"] and path.read_bytes() == before


def test_pass1_tables_and_qrels_grades_and_exclusions():
    rows = _rater_rows([("same", "none"), ("different", "unsure"), ("none", "none")], not_obligation=set())
    rows = [dict(r) for r in rows]
    for r in rows:
        if r["row_type"] == "class" and r["judgement"] in ("same", "different"):
            r["matched_paragraph_id"] = "md_1::p00001"
        if r["item_id"] == "t1_i2" and r["target_class"] == SFB:
            r["note"] = "checked: md_7::p00007"
    rows[0]["not_obligation"] = ""
    labels = T.parse_labelled_items(rows)
    tables = T.pass1_tables(labels)
    assert tables["judgement_distribution"] == {"same": 1, "different": 1, "none": 3, "unsure": 1}
    assert tables["flag_distribution"] == {"shared": 1, "class-specific": 1, "absent": 1, "ambiguous": 0}
    shown = {"t1_i0": {SFB: ["md_2::p00001", "md_2::p00002"], PB: ["md_3::p00001"]},
             "t1_i1": {SFB: ["md_4::p00001"], PB: ["md_5::p00001"]},
             "t1_i2": {SFB: ["md_6::p00001"], PB: ["md_8::p00001"]}}
    key = {i: {"shown_targets": s} for i, s in shown.items()}
    sample = {i: {"source_candidate_id": "t1c_" + i, "paragraph_id": i, "subject_family": "F"} for i in shown}
    q = T.pass1_qrels(rows, key, sample, rater="karan", label_source="manual")
    got = {(x["item_id"], x["target_class"], x["paragraph_id"]): (x["relevance"], x["basis"]) for x in q}
    assert got[("t1_i0", SFB, "md_1::p00001")] == (2, "matched_paragraph_id")
    assert got[("t1_i1", SFB, "md_1::p00001")] == (1, "matched_paragraph_id")
    assert got[("t1_i0", PB, "md_3::p00001")] == (0, "shown")
    assert got[("t1_i2", SFB, "md_7::p00007")] == (0, "note_checked")
    assert not any(x["item_id"] == "t1_i1" and x["target_class"] == PB for x in q), "unsure gives no qrel"
    assert all(x["provenance"] == "annotator:karan:single-pass" for x in q)


def test_irr_adjudication_rows_list_every_disagreeing_comparison_with_blank_decisions():
    def sheet(judgements, not_obl=(), applies=None):
        rows = _rater_rows(judgements, not_obligation=set(not_obl), applies=applies)
        for r in rows:
            r.setdefault("source_paragraph_id", r["item_id"])
            r.setdefault("source_span", "OBLIGATION: text")
        return rows
    k = sheet([("same", "none"), ("none", "none"), ("same", "same")])
    a = sheet([("same", "none"), ("none", "unsure"), ("same", "same")], not_obl={"t1_i2"})
    m = sheet([("same", "none"), ("none", "none"), ("same", "same")], applies={"t1_i0": f"{CB};{SFB}"})
    adj = T.irr_adjudication_rows({"karan": k, "akash": a, "meer": m})
    keyed = {(r["item_id"], r["comparison"], r["target_class"]): r for r in adj}
    assert ("t1_i0", "item", "") in keyed and keyed[("t1_i0", "item", "")]["differs_on"] == "applies_to"
    assert keyed[("t1_i1", "class", PB)]["akash_decision"] == "unsure"
    assert keyed[("t1_i2", "item", "")]["akash_decision"] == "not_obligation"
    assert keyed[("t1_i2", "class", SFB)]["akash_decision"] == "(not an obligation)"
    assert ("t1_i1", "class", SFB) not in keyed, "agreeing rows are not listed"
    assert all(r["final_decision"] == "" and r["final_rationale"] == "" for r in adj)
    assert tuple(adj[0]) == T.IRR_ADJUDICATION_COLUMNS


# -- IRR adjudication: legacy item-level completion -> per-comparison rows -------------


def _legacy(rows):
    base = {c: "" for c in T.LEGACY_ADJ_COLUMNS}
    return [{**base, **r} for r in rows]


def test_legacy_adjudication_validation_accepts_a_clean_completion_and_names_every_fault():
    import json

    tmpl = _legacy([{"item_id": "t1_a", "source_class": CB, "differs_on": "not_obligation", "akash": "{}",
                     "karan": "{}", "meer": "{}"},
                    {"item_id": "t1_b", "source_class": CB, "differs_on": "judgement", "akash": "{}",
                     "karan": "{}", "meer": "{}"}])
    done = [dict(tmpl[0], final_applies_to="[]", final_judgements="{}", final_not_obligation="true",
                 rationale="Reject: incomplete span."),
            dict(tmpl[1], final_applies_to=json.dumps([CB]), final_judgements=json.dumps({SFB: "same", PB: "none"}),
                 final_not_obligation="false", rationale="SFB has the same rule.")]
    compared = {"t1_b": [SFB, PB]}
    decisions, problems = T.validate_legacy_adjudication(done, tmpl, compared, tc())
    assert problems == [] and decisions["t1_a"]["not_obligation"] and decisions["t1_b"]["judgements"][SFB] == "same"
    bad = [dict(done[0], karan="edited"), dict(done[1], final_judgements=json.dumps({SFB: "maybe"}), rationale="")]
    _, problems = T.validate_legacy_adjudication(bad, tmpl, compared, tc())
    text = " | ".join(problems)
    assert "karan: expected '{}', observed 'edited'" in text
    assert "rationale: blank" in text and "expected classes" in text
    swapped = [done[1], done[0]]
    assert T.validate_legacy_adjudication(swapped, tmpl, compared, tc())[1], "row order is part of identity"


def test_adjudication_mapping_is_deterministic_and_stops_on_an_unmappable_row():
    decisions = {"t1_a": {"not_obligation": True, "applies_to": [], "judgements": {}, "rationale": "R1"},
                 "t1_b": {"not_obligation": False, "applies_to": [CB, SFB], "judgements": {SFB: "different"},
                          "rationale": "R2"}}
    base = {c: "" for c in T.IRR_ADJUDICATION_COLUMNS}
    current = [dict(base, item_id="t1_a", comparison="item"), dict(base, item_id="t1_a", comparison="class",
                                                                    target_class=SFB),
               dict(base, item_id="t1_b", comparison="item", karan_decision="kept"),
               dict(base, item_id="t1_b", comparison="class", target_class=SFB)]
    mapped, problems = T.map_adjudication(current, decisions)
    assert problems == []
    assert [r["final_decision"] for r in mapped] == ["not_obligation", T.FINAL_NOT_OBLIGATION,
                                                     f"applies_to: {CB}; {SFB}", "different"]
    assert [r["final_rationale"] for r in mapped] == ["R1", "R1", "R2", "R2"]
    assert mapped[2]["karan_decision"] == "kept", "evidence columns are carried unchanged"
    _, problems = T.map_adjudication(current + [dict(base, item_id="t1_b", comparison="class", target_class=PB)],
                                     decisions)
    assert any("no judgement for this class" in p for p in problems)


def test_consensus_uses_adjudication_for_disputed_items_and_unanimous_labels_elsewhere():
    same = [("same", "none")]
    labels = {r: T.parse_labelled_items(_rater_rows(same + [("none", "none")])) for r in ("a", "b")}
    labels["c"] = T.parse_labelled_items(_rater_rows(same + [("none", "same")]))
    decisions = {"t1_i1": {"not_obligation": False, "applies_to": [CB], "judgements": {SFB: "none", PB: "same"},
                           "rationale": "R"}}
    out = {c["item_id"]: c for c in T.irr_consensus(labels, decisions)}
    assert out["t1_i0"]["route"] == "unanimous" and out["t1_i0"]["differential_flag"] == T.FLAG_SHARED
    assert out["t1_i1"]["route"] == "adjudicated" and out["t1_i1"]["judgements"] == {SFB: "none", PB: "same"}
    with pytest.raises(T.T1Error):
        T.irr_consensus(labels, {})


# -- C2: the blind pass-2 sheet ----------------------------------------------------------


def test_retest_rows_are_the_predetermined_items_reshuffled_blank_and_leak_free():
    rows, drawn = _sheet(6)
    filled = [dict(r, note="My pass-1 reasoning about this item.") if r["row_type"] == "item" else r for r in rows]
    ids = [it["item_id"] for it in drawn["items"]][:4]
    out = T.build_retest_rows(filled, ids, seed=1, block_size=2)
    assert sorted({r["item_id"] for r in out}) == sorted(ids)
    assert all(not r[c] for r in out for c in T.INPUT_COLUMNS), "answers never carry over"
    assert [r["block"] for r in out if r["row_type"] == "item"] == ["1", "1", "2", "2"]
    T.assert_blind(out)
    assert T.leaked_texts(out, {"My pass-1 reasoning about this item."}) == []
    assert T.leaked_texts(filled, {"My pass-1 reasoning about this item."}) != []
    orders = {tuple(r["item_id"] for r in T.build_retest_rows(rows, ids, seed=s, block_size=20)
                    if r["row_type"] == "item") for s in range(5)}
    assert len(orders) > 1, "the order depends on the seed"
    with pytest.raises(T.T1Error):
        T.build_retest_rows(rows, ids + ["t1_missing"], seed=1, block_size=20)


def _pilot_task(i, **over):
    base = {c: "" for c in TASK_FILE_COLUMNS}
    return {**base, "label_id": f"t1_pilot_md_9::p0000{i}_00", "paragraph_id": f"md_9::p0000{i}",
            "document_id": "md_9", "context_entity_class": CB, "context_subject_family": "F",
            "span_text": f"A bank shall do thing {i}.", **over}


def test_pass2_sheet_mixes_retest_and_pilot_items_blank_and_blind():
    rows, drawn = _sheet(6)
    ids = [it["item_id"] for it in drawn["items"]][:4]
    retest = T.build_retest_rows(rows, ids, seed=1, block_size=20)
    pilot = T.pilot_pass2_rows([_pilot_task(i) for i in range(5)])
    out = T.build_pass2_rows(retest, pilot, seed=7, block_size=3)
    T.assert_pass2_blind(out)
    assert tuple(out[0]) == T.PASS2_COLUMNS
    items = [r["item_id"] for r in out if r["row_type"] in ("item", "pilot_item")]
    assert sorted(items) == sorted(ids + [p["item_id"] for p in pilot])
    kinds = ["pilot" if r.startswith("t1_pilot") else "retest" for r in items]
    assert kinds != sorted(kinds) and kinds != sorted(kinds, reverse=True), "the two kinds are interleaved"
    for iid in ids:  # each retest item's class rows stay directly under it
        pos = [n for n, r in enumerate(out) if r["item_id"] == iid]
        assert pos == list(range(pos[0], pos[0] + len(pos))) and out[pos[0]]["row_type"] == "item"
    assert {r["block"] for r in out} == {"1", "2", "3"}
    with pytest.raises(T.T1Error):
        T.pilot_pass2_rows([_pilot_task(1, differential_flag="shared")])
    with pytest.raises(T.T1Error):
        T.assert_pass2_blind([dict(out[0], differential_flag="shared")])


def _pilot_row(**over):
    return {**{c: "" for c in T.PASS2_COLUMNS}, "item_id": "t1_pilot_x", "row_type": "pilot_item", **over}


def test_pilot_rows_enforce_v2_2_vocabulary_and_pilot_blank_rules():
    vocab = tc().applies_to_vocabulary
    ok = [_pilot_row(applies_to=f"{CB};Payment and Settlement System", differential_flag="shared"),
          _pilot_row(note="not an RE obligation — duty on customer")]
    assert T.validate_pilot_rows(ok, vocab) == []
    cases = {
        "Financial Market": _pilot_row(applies_to="Financial Market", differential_flag="shared"),
        "blank row with no note": _pilot_row(),
        "without applies_to": _pilot_row(differential_flag="shared"),
        "must be blank on pilot rows": _pilot_row(applies_to=CB, differential_flag="shared", judgement="same"),
        "is not one of": _pilot_row(applies_to=CB, differential_flag="unlabelled"),
    }
    for expect, row in cases.items():
        assert any(expect in p for p in T.validate_pilot_rows([row], vocab)), expect
    item_row = {**{c: "" for c in T.PASS2_COLUMNS}, "item_id": "t1_a", "row_type": "item", "differential_flag": "shared"}
    assert any("must be blank on item/class rows" in p for p in T.validate_pilot_rows([item_row], vocab))


def test_pilot_retest_metrics_and_retest_disagreements():
    p1 = {f"p{i}": {"not_obligation": False, "applies_to": (CB,), "flag": f, "note": ""}
          for i, f in enumerate(["shared", "shared", "absent", "class-specific"])}
    p2 = {k: dict(v) for k, v in p1.items()}
    p2["p3"]["flag"] = "shared"
    p2["p2"]["applies_to"] = (CB, SFB)
    m = T.pilot_retest_metrics(p1, p2, seed=1, resamples=100)
    assert m["differential_flag"]["n_items"] == 4 and m["differential_flag"]["observed_agreement"] == 0.75
    assert m["applies_to"]["exact_set_agreement"] == 0.75
    rows1 = _rater_rows([("same", "none"), ("none", "none")])
    rows2 = _rater_rows([("same", "none"), ("none", "same")])
    for rs in (rows1, rows2):
        for r in rs:
            r.setdefault("source_paragraph_id", r["item_id"])
            r.setdefault("source_span", "OBLIGATION: text")
            if r["row_type"] == "class" and r["judgement"] == "same":
                r["matched_paragraph_id"] = "md_1::p00001"
    ctx = {k: ("md_1::p00001", "text") for k in p1}
    adj = T.retest_adjudication_rows(rows1, rows2, p1, p2, ctx)
    keyed = {(r["item_id"], r["comparison"], r["target_class"]): r for r in adj}
    assert keyed[("t1_i1", "class", PB)]["pass1_decision"] == "none" and keyed[("t1_i1", "class", PB)]["pass2_decision"] == "same"
    assert keyed[("t1_i1", "item", "")]["differs_on"] == "differential_flag (derived)"
    assert {r["item_id"] for r in adj if r["kind"] == "pilot"} == {"p2", "p3"}
    assert all(not r["final_decision"] and not r["final_rationale"] for r in adj)


def test_correction_diff_allows_only_named_items_and_input_cells():
    orig = [_pilot_row(item_id="a", applies_to="Financial Market", differential_flag="shared"),
            _pilot_row(item_id="b", applies_to=CB, differential_flag="shared")]
    good = [dict(orig[0], applies_to=CB), dict(orig[1])]
    changes, problems = T.correction_diff(orig, good, ["a"], T.PASS2_INPUT_COLUMNS)
    assert problems == [] and changes == [{"row": 2, "item_id": "a",
                                           "cells": {"applies_to": {"from": "Financial Market", "to": CB}}}]
    _, problems = T.correction_diff(orig, [dict(orig[0]), dict(orig[1], applies_to=SFB)], ["a"], T.PASS2_INPUT_COLUMNS)
    assert any("only ['a'] may change" in p for p in problems)
    _, problems = T.correction_diff(orig, [dict(orig[0], source_span="edited"), orig[1]], ["a"], T.PASS2_INPUT_COLUMNS)
    assert any("shown column" in p for p in problems)
    _, problems = T.correction_diff(orig, orig[:1], ["a"], T.PASS2_INPUT_COLUMNS)
    assert any("rows" in p for p in problems)


def test_overlap_adjudication_lists_only_differences_from_karan():
    def sheet(judgements, not_obl=(), matched=None):
        rows = _rater_rows(judgements, not_obligation=set(not_obl))
        for r in rows:
            r.setdefault("source_paragraph_id", r["item_id"])
            r.setdefault("source_span", "OBLIGATION: text")
            if r["row_type"] == "class" and r["judgement"] in ("same", "different"):
                r["matched_paragraph_id"] = (matched or {}).get((r["item_id"], r["target_class"]), "md_1::p00001")
        return rows
    karan = sheet([("same", "none"), ("none", "none"), ("same", "same")])
    akash = sheet([("same", "none"), ("none", "none"), ("same", "same")], matched={("t1_i0", SFB): "md_2::p00002"})
    meer = sheet([("same", "none"), ("none", "same"), ("same", "same")], not_obl={"t1_i2"})
    rows = T.overlap_adjudication_rows(karan, {"akash": akash, "meer": meer}, ["t1_i0", "t1_i1", "t1_i2"])
    keyed = {(r["item_id"], r["comparison"], r["target_class"]): r for r in rows}
    assert keyed[("t1_i0", "class", SFB)]["differs_on"] == "matched_paragraph_id"
    assert keyed[("t1_i0", "class", SFB)]["akash_matched_paragraph_id"] == "md_2::p00002"
    assert keyed[("t1_i1", "class", PB)]["meer_decision"] == "same" and keyed[("t1_i1", "class", PB)]["karan_decision"] == "none"
    assert keyed[("t1_i2", "item", "")]["meer_decision"] == "not_obligation"
    assert ("t1_i1", "class", SFB) not in keyed, "agreement with Karan is not listed"
    assert all(not r["final_decision"] and not r["final_rationale"] for r in rows)


def test_item_decisions_parse_both_adjudication_formats():
    vocab = tc().applies_to_vocabulary
    assert T.parse_item_decision(f"applies_to: {SFB}; {CB} | flag: shared", vocab) == {
        "not_obligation": False, "applies_to": (CB, SFB), "stated_flag": "shared"}
    assert T.parse_item_decision(f"applies_to: {CB}", vocab)["stated_flag"] is None
    assert T.parse_item_decision("not_obligation | flag: None", vocab)["not_obligation"]
    assert T.parse_item_decision("not_obligation", vocab)["not_obligation"]
    for bad in ("applies_to: Financial Market", "maybe", ""):
        with pytest.raises(T.T1Error):
            T.parse_item_decision(bad, vocab)


def test_final_labels_apply_only_karans_decisions_and_leave_unresolved_unsure():
    rows = _rater_rows([("same", "unsure"), ("unsure", "none"), ("same", "same")])
    for r in rows:
        r.setdefault("source_paragraph_id", r["item_id"])
        r.setdefault("source_span", "OBLIGATION: text")
        r.setdefault("block", "1")
        r.setdefault("subject_family", "F")
        if r["row_type"] == "class" and r["judgement"] == "same":
            r["matched_paragraph_id"] = "md_1::p00001"
    base = {c: "" for c in T.OVERLAP_ADJ_COLUMNS}
    overlap = [dict(base, item_id="t1_i0", comparison="class", target_class=PB, final_decision="different",
                    akash_decision="different", akash_matched_paragraph_id="md_5::p00005"),
               dict(base, item_id="t1_i2", comparison="item", final_decision="not_obligation")]
    L, problems = T.final_labels(["t1_i0", "t1_i1", "t1_i2"], rows, retest_ids=[], retest_adj=[],
                                 overlap_adj=overlap, vocabulary=tc().applies_to_vocabulary)
    assert problems == []
    assert L["t1_i0"]["judgements"] == {SFB: "same", PB: "different"} and L["t1_i0"]["unsure_classes"] == []
    assert L["t1_i0"]["matched"][PB] == "md_5::p00005" and L["t1_i0"]["matched_source"][PB] == "akash"
    assert L["t1_i1"]["unsure_classes"] == [SFB], "no decision covers it"
    assert L["t1_i2"]["not_obligation"] and L["t1_i2"]["judgements"] == {}
    un = T.unsure_adjudication_rows(L, rows)
    assert [(r["item_id"], r["target_class"]) for r in un] == [("t1_i1", SFB)]
    assert all(not r["final_decision"] and not r["final_rationale"] for r in un)


def test_adjudication_completion_validation_names_blank_changed_and_bad_cells():
    tmpl = [{"item_id": "a", "comparison": "class", "target_class": CB, "context": "x", "final_decision": "",
             "final_rationale": ""}]
    ok = [dict(tmpl[0], final_decision="same", final_rationale="Same duty.")]
    assert T.validate_adjudication_completion(tmpl, ok, T.ADJUDICATION_INPUT_COLUMNS) == []
    cases = {"final_decision blank": dict(tmpl[0], final_rationale="r"),
             "final_rationale blank": dict(tmpl[0], final_decision="none"),
             "immutable": dict(ok[0], context="edited"),
             "not in": dict(ok[0], final_decision="maybe")}
    for expect, row in cases.items():
        assert any(expect in p for p in T.validate_adjudication_completion(tmpl, [row], T.ADJUDICATION_INPUT_COLUMNS)), expect
    u_tmpl = [dict(tmpl[0], final_matched_paragraph_id="")]
    bad_id = [dict(u_tmpl[0], final_decision="different", final_matched_paragraph_id="md_9::p00001", final_rationale="r")]
    assert any("is not a paragraph of" in p for p in
               T.validate_adjudication_completion(u_tmpl, bad_id, T.UNSURE_INPUT_COLUMNS, {"md_9::p00001": SFB}))


def test_validated_records_route_exclusions_and_derived_flag():
    rows = _rater_rows([("same", "none"), ("different", "none"), ("unsure", "none")], not_obligation=set())
    for r in rows:
        r.setdefault("source_paragraph_id", r["item_id"])
        r.setdefault("source_span", "OBLIGATION: text")
        if r["row_type"] == "class" and r["judgement"] in ("same", "different"):
            r["matched_paragraph_id"] = "md_1::p00001"
    rows.append({**rows[0], "item_id": "t1_i3", "not_obligation": "yes", "applies_to": ""})
    base = {c: "" for c in T.OVERLAP_ADJ_COLUMNS}
    L, _ = T.final_labels(["t1_i0", "t1_i1", "t1_i2", "t1_i3"], rows, retest_ids=["t1_i0"], retest_adj=[],
                          overlap_adj=[dict(base, item_id="t1_i1", comparison="class", target_class=PB, final_decision="none")],
                          vocabulary=tc().applies_to_vocabulary)
    cand_keys = ("item_id", "source_candidate_id", "md_id", "paragraph_id", "entity_class", "subject_family",
                 "section_id", "clause_path", "obligation_span", "in_force_from", "in_force_from_basis", "in_force_to",
                 "amended_by", "era")
    cands = {i: {k: (i if k == "item_id" else None) for k in cand_keys} for i in L}
    out, excluded, problems = T.validated_records(L, cands, rows, {})
    by = {r["item_id"]: r for r in out}
    assert by["t1_i0"]["provenance"] == T.ROUTE_RETEST_CONSISTENT and by["t1_i0"]["differential_flag"] == "shared"
    assert by["t1_i1"]["provenance"] == T.ROUTE_ADJUDICATED and by["t1_i1"]["differential_flag"] == "class-specific"
    assert excluded == {"rejected": ["t1_i3"], "in_review": ["t1_i2"]}, "unresolved unsure -> in_review"
    assert all(r["label_status"] == "validated" for r in out) and problems == []


def test_timed_draw_is_seeded_stratified_and_within_the_pool():
    pool = [{"item_id": f"t1_{c[:3]}_{i}", "entity_class": c} for c in CORE for i in range(3 + CORE.index(c) % 3)]
    a, b = T.draw_timed(pool), T.draw_timed(pool)
    assert a == b and len(a) == 20 and set(a) <= {p["item_id"] for p in pool}
    assert {p["entity_class"] for p in pool if p["item_id"] in a} == set(CORE), "every class represented"


def test_timed_minutes_parse_logged_clock_times_and_never_guess():
    from datetime import date as _date

    day = _date(2026, 9, 27)
    rows = [{"block": "1", "started_at": "2026-09-27 19:00", "ended_at": "19:40"},
            {"block": "2", "started_at": "7:45 PM", "ended_at": "8:15 pm"}]
    blocks, problems = T.timed_block_minutes(rows, {"1": 10, "2": 10}, day)
    assert problems == [] and [b["minutes"] for b in blocks] == [40.0, 30.0]
    m = T.minutes_per_item(blocks, seed=1, resamples=200)
    assert m["minutes_per_item"] == 3.5 and m["n_items"] == 20 and m["n_blocks"] == 2
    assert m["bootstrap_ci95"][0] >= 3.0 and m["bootstrap_ci95"][1] <= 4.0
    bad = [{"block": "1", "started_at": "", "ended_at": "19:40"}, {"block": "2", "started_at": "20:00", "ended_at": "19:00"}]
    _, problems = T.timed_block_minutes(bad, {"1": 10, "2": 10, "3": 5}, day)
    assert any("blank time" in p for p in problems) and any("not after" in p for p in problems)
    assert any("block 3: no row" in p for p in problems)


def test_retest_method_statement_claims_no_washout_and_names_the_recall_risk():
    s = T.RETEST_METHOD_STATEMENT
    assert "Blind test-retest procedure" in s and "No washout period was enforced" in s
    assert "may inflate agreement through recall" in s
    assert "5 days" not in s and "minimum interval was" not in s

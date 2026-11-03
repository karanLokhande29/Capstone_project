"""P2-003 §T: the pre-registered rule, the blind sheet and its key, scoring, decisions at the band edges."""

from __future__ import annotations

import copy
import csv
import json
from datetime import date
from pathlib import Path

import pytest

from src.benchmark.candidates import wilson_interval
from src.supplementary import alignment as AL
from src.supplementary import enforcement, faq, linking, withdrawn
from src.supplementary.common import SupplementaryError
from tests.supplementary_support import MANIFEST, PARAGRAPHS, fixture, repo_blocks

CUT = date(2025, 11, 28)
ENTRY = {"url": "https://x/u", "retrieved_at": "t", "content_hash": "h"}
RULE = {"paragraph_weak_min": 0.60, "direction_weak_min": 0.30}


def conf(**over):
    c = copy.deepcopy(repo_blocks()["supplementary"]["alignment"])
    c.update({"faq_items": 4, "enforcement_items": 3, "min_faq_items": 2, **over})
    return c


def fixture_items():
    topics = faq.parse_index(fixture("faq_index.html"), "https://x/?Id={id}")
    faqs = [i for t in topics for i in faq.parse_topic(fixture(f"faq_{t['faq_topic_id']}.html"), t, ENTRY, CUT)["items"]]
    enf = [enforcement.parse_release(fixture(f"pen_{n}.html"), {"prid": n}, ENTRY, CUT) for n in (801, 802, 803)]
    return {"faq": faqs, "enforcement": enf}


def links_for(items):
    blocks = repo_blocks()
    idx = linking.LinkIndex.build(MANIFEST, PARAGRAPHS, withdrawn.local_repeal_map(PARAGRAPHS),
                                  linking=blocks["supplementary"]["linking"],
                                  core_classes=blocks["matching"]["core_entity_classes"])
    by = {}
    for r in linking.link_items(idx, [i for rows in items.values() for i in rows]):
        by.setdefault(r["item_id"], []).append(r)
    return by


def draw(tmp: Path, c=None, force=False):
    items = fixture_items()
    return AL.draw_sheet(items_by_source=items, links_by_item=links_for(items),
                         titles={m["document_id"]: m["title"] for m in MANIFEST}, paragraphs_by_doc=PARAGRAPHS,
                         conf=c or conf(), rule_path=tmp / AL.RULE_FILE, sheet_path=tmp / AL.SHEET_FILE,
                         key_path=tmp / AL.KEY_FILE, best_link=linking.best_link,
                         entity_class_of={m["document_id"]: m["entity_class_raw"] for m in MANIFEST},
                         function_headings=repo_blocks()["matching"]["function_headings"], force=force)


# -- C2 rule ------------------------------------------------------------------------


def test_rule_file_is_written_with_a_timestamp(tmp_path):
    body = AL.write_rule(tmp_path / AL.RULE_FILE, tmp_path / AL.SHEET_FILE, RULE)
    assert body["rule"] == RULE and body["created_at"] and "17 points" in body["interval_note"]


def test_rule_refuses_once_the_sheet_exists(tmp_path):
    AL.write_rule(tmp_path / AL.RULE_FILE, tmp_path / AL.SHEET_FILE, RULE)
    draw(tmp_path)
    with pytest.raises(SupplementaryError, match="cannot be rewritten"):
        AL.write_rule(tmp_path / AL.RULE_FILE, tmp_path / AL.SHEET_FILE, RULE, force=True)


def test_rule_refuses_overwrite_without_force_and_bad_lines(tmp_path):
    AL.write_rule(tmp_path / AL.RULE_FILE, tmp_path / AL.SHEET_FILE, RULE)
    with pytest.raises(SupplementaryError, match="exists"):
        AL.write_rule(tmp_path / AL.RULE_FILE, tmp_path / AL.SHEET_FILE, RULE)
    with pytest.raises(SupplementaryError, match="must satisfy"):
        AL.write_rule(tmp_path / AL.RULE_FILE, tmp_path / AL.SHEET_FILE,
                      {"paragraph_weak_min": 0.3, "direction_weak_min": 0.6}, force=True)


def test_sheet_refuses_without_a_rule(tmp_path):
    with pytest.raises(SupplementaryError, match="no rule file"):
        draw(tmp_path)


def test_sheet_refuses_a_rule_not_older_than_the_sheet(tmp_path):
    AL.write_rule(tmp_path / AL.RULE_FILE, tmp_path / AL.SHEET_FILE, RULE)
    body = json.loads((tmp_path / AL.RULE_FILE).read_text())
    body["created_at"] = "2999-01-01T00:00:00.000000+00:00"
    (tmp_path / AL.RULE_FILE).write_text(json.dumps(body))
    with pytest.raises(SupplementaryError, match="not timestamped before"):
        draw(tmp_path)


# -- C3 sheet and key -----------------------------------------------------------------


def test_sheet_is_blind_and_the_key_is_separate(tmp_path):
    AL.write_rule(tmp_path / AL.RULE_FILE, tmp_path / AL.SHEET_FILE, RULE)
    meta = draw(tmp_path)
    raw = (tmp_path / AL.SHEET_FILE).read_text(encoding="utf-8")
    assert raw.startswith("# NOTE:") and "not only the candidates" in raw.splitlines()[0]
    rows = AL.read_sheet(tmp_path / AL.SHEET_FILE)
    assert tuple(rows[0]) == AL.SHEET_COLUMNS
    assert all(not r["label"] and not r["paragraph_ids"] and not r["note"] for r in rows)
    header = raw.splitlines()[1]
    assert not any(w in header for w in ("score", "rank", "tfidf", "method", "stratum"))
    key = json.loads((tmp_path / AL.KEY_FILE).read_text())
    assert set(key["items"]) == {r["item_id"] for r in rows}
    some = next(v for v in key["items"].values() if len(v["candidates"]) >= 3)
    assert [c["rank"] for c in some["candidates"]] == list(range(1, len(some["candidates"]) + 1))
    assert sorted(some["shown_order"]) == sorted(c["paragraph_id"] for c in some["candidates"])
    shuffled = [v for v in key["items"].values() if len(v["candidates"]) >= 3
                and v["shown_order"] != [c["paragraph_id"] for c in v["candidates"]]]
    assert shuffled, "candidates are shown in a shuffled order, not rank order"
    for r in rows:  # scores never leak into the sheet text
        for c in key["items"][r["item_id"]]["candidates"]:
            assert str(c["tfidf_score"]) not in r["candidates"]
    assert meta["n"] == {"faq": 3, "enforcement": 3} and meta["faq"]["shortfall"] == 1
    assert meta["faq"]["requirement_cue_counts"]["shall"] >= 1


FUNCTION_DIRECTIONS = {"md_90002", "md_90005"}  # the fixture's function-heading Directions (FID, FEM)


def test_linked_rows_draw_from_their_linked_direction_only(tmp_path):
    AL.write_rule(tmp_path / AL.RULE_FILE, tmp_path / AL.SHEET_FILE, RULE)
    draw(tmp_path)
    key = json.loads((tmp_path / AL.KEY_FILE).read_text())
    linked = [v for v in key["items"].values() if v["link"]]
    assert linked
    for v in linked:
        assert v["candidate_pool"] == AL.POOL_LINKED and v["candidate_pool_directions"] == 1
        assert {c["paragraph_id"].split("::")[0] for c in v["candidates"]} <= {v["link"]["md_id"]}
        assert len(v["candidates"]) <= 8


def test_unlinked_rows_draw_from_the_corpus_by_pool(tmp_path):
    AL.write_rule(tmp_path / AL.RULE_FILE, tmp_path / AL.SHEET_FILE, RULE)
    meta = draw(tmp_path)
    key = json.loads((tmp_path / AL.KEY_FILE).read_text())
    items = key["items"]
    # faq_0901_002 (Widget Accounts) links nowhere and has no entity class: the whole corpus.
    full = items["faq_0901_002"]
    assert full["link"] is None and full["candidate_pool"] == AL.POOL_FULL
    assert full["candidate_pool_directions"] == 6 and 0 < len(full["candidates"]) <= 8
    assert {c["paragraph_id"].split("::")[0] for c in full["candidates"]} <= {m["document_id"] for m in MANIFEST}
    assert full["candidates"][0]["paragraph_id"].startswith("md_90001::")  # the account-opening text ranks KYC first
    # enf_802 is an NBFC with no NBFC Direction in the corpus: its class (none here) plus function headings.
    nbfc = items["enf_802"]
    assert nbfc["link"] is None and nbfc["candidate_pool"] == AL.POOL_CLASS
    assert nbfc["candidate_pool_directions"] == 2
    assert {c["paragraph_id"].split("::")[0] for c in nbfc["candidates"]} <= FUNCTION_DIRECTIONS
    assert meta["candidate_pools"] == {AL.POOL_LINKED: sum(v["link"] is not None for v in items.values()),
                                       AL.POOL_CLASS: sum(v["candidate_pool"] == AL.POOL_CLASS for v in items.values()),
                                       AL.POOL_FULL: sum(v["candidate_pool"] == AL.POOL_FULL for v in items.values())}
    # Blind: the sheet row says "none", shows shuffled paragraph ids, and no scores, ranks or pool names.
    rows = {r["item_id"]: r for r in AL.read_sheet(tmp_path / AL.SHEET_FILE)}
    row = rows["faq_0901_002"]
    assert row["linked_directions"] == "none"
    assert [line.split("]")[0][1:] for line in row["candidates"].split("\n\n")] == full["shown_order"]
    raw = (tmp_path / AL.SHEET_FILE).read_text(encoding="utf-8")
    assert AL.POOL_CLASS not in raw and AL.POOL_FULL not in raw
    assert raw.replace("linked_directions", "").count(AL.POOL_LINKED) == 0  # only the column name contains it
    for c in full["candidates"]:
        assert str(c["tfidf_score"]) not in row["candidates"]


def test_corpus_pool_rule():
    classes = {"a": "Commercial Banks", "b": "Urban Co-operative Banks", "c": "Financial Market"}
    fh = ["Financial Market"]
    assert AL.corpus_pool("Commercial Banks", classes, fh) == (AL.POOL_CLASS, {"a", "c"})
    assert AL.corpus_pool("Financial Market", classes, fh) == (AL.POOL_CLASS, {"c"})
    assert AL.corpus_pool("unresolved", classes, fh) == (AL.POOL_FULL, {"a", "b", "c"})
    assert AL.corpus_pool(None, classes, fh) == (AL.POOL_FULL, {"a", "b", "c"})


def test_corpus_candidates_respect_min_chars_and_are_deterministic():
    cc = AL.CorpusCandidates(PARAGRAPHS, 40)
    out = cc.rank("periodic updation of KYC", {"md_90001", "md_90003", "md_90006"}, 8)
    assert [c["rank"] for c in out] == list(range(1, len(out) + 1))
    assert all(len(c["text"]) >= 40 for c in out) and "md_90001::p00005" not in {c["paragraph_id"] for c in out}
    assert {out[0]["paragraph_id"], out[1]["paragraph_id"]} == {"md_90001::p00002", "md_90003::p00001"}
    assert out == AL.CorpusCandidates(PARAGRAPHS, 40).rank("periodic updation of KYC",
                                                            {"md_90001", "md_90003", "md_90006"}, 8)


def test_redraw_is_byte_identical_and_refused_without_force(tmp_path):
    AL.write_rule(tmp_path / AL.RULE_FILE, tmp_path / AL.SHEET_FILE, RULE)
    draw(tmp_path)
    sheet, key = (tmp_path / AL.SHEET_FILE).read_bytes(), (tmp_path / AL.KEY_FILE).read_bytes()
    with pytest.raises(SupplementaryError, match="refusing to redraw"):
        draw(tmp_path)
    draw(tmp_path, force=True)
    assert (tmp_path / AL.SHEET_FILE).read_bytes() == sheet and (tmp_path / AL.KEY_FILE).read_bytes() == key


def test_too_few_qualifying_faq_items_stops(tmp_path):
    AL.write_rule(tmp_path / AL.RULE_FILE, tmp_path / AL.SHEET_FILE, RULE)
    with pytest.raises(SupplementaryError, match="Escalate"):
        draw(tmp_path, conf(min_faq_items=15))


def test_faq_filter_needs_a_requirement_and_an_entity_cue():
    c = conf()
    req, ent = AL.compile_cues(c["faq_requirement_cues"]), AL.compile_cues(c["faq_entity_cues"])
    assert AL.faq_qualifies("Banks shall report it.", req, ent)[0]
    assert not AL.faq_qualifies("Banks report it.", req, ent)[0]
    assert not AL.faq_qualifies("You shall report it.", req, ent)[0]
    assert AL.faq_qualifies("AD banks are required to allow it.", req, ent)[2] == ["banks?", "AD\\s+(?:Category|banks?)"]


# -- D1 score -------------------------------------------------------------------------


def labelled_copy(tmp: Path, labels: dict[str, tuple[str, str]], *, excel: bool = True) -> Path:
    rows = AL.read_sheet(tmp / AL.SHEET_FILE)
    out = tmp / AL.COMPLETED_FILE
    with out.open("w", encoding="utf-8-sig" if excel else "utf-8", newline="") as fh:
        fh.write('"' + AL.HEADER_NOTE + '",,,,,,,\n' if excel else AL.HEADER_NOTE + "\n")
        w = csv.DictWriter(fh, fieldnames=AL.SHEET_COLUMNS)
        w.writeheader()
        for r in rows:
            label, ids = labels.get(r["item_id"], ("unanchored", ""))
            w.writerow({**r, "label": label, "paragraph_ids": ids})
    return out


def _score(tmp: Path, path: Path, **kw):
    pids = {r["paragraph_id"] for rows in PARAGRAPHS.values() for r in rows}
    return AL.score_sheet(labelled_path=path, drawn_path=tmp / AL.SHEET_FILE, key_path=tmp / AL.KEY_FILE,
                          rule_path=tmp / AL.RULE_FILE, paragraph_ids=pids, **kw)


@pytest.fixture()
def drawn(tmp_path):
    AL.write_rule(tmp_path / AL.RULE_FILE, tmp_path / AL.SHEET_FILE, RULE)
    draw(tmp_path)
    return tmp_path


def test_score_refuses_the_blank_sheet(drawn):
    with pytest.raises(SupplementaryError, match="blank label"):
        _score(drawn, drawn / AL.SHEET_FILE)


def test_score_refuses_one_blank_label(drawn):
    path = labelled_copy(drawn, {})
    rows = AL.read_sheet(path)
    rows[0]["label"] = ""
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=AL.SHEET_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    with pytest.raises(SupplementaryError, match="1 of 6 rows have a blank label"):
        _score(drawn, path)


def test_score_refuses_changed_item_text(drawn):
    path = labelled_copy(drawn, {})
    text = path.read_text(encoding="utf-8-sig").replace("Widget", "Gizmo", 1)
    path.write_text(text, encoding="utf-8-sig")
    with pytest.raises(SupplementaryError, match="differ from the drawn sheet"):
        _score(drawn, path)


def test_score_refuses_a_rule_changed_after_the_draw(drawn):
    path = labelled_copy(drawn, {})
    body = json.loads((drawn / AL.RULE_FILE).read_text())
    body["rule"]["paragraph_weak_min"] = 0.5
    (drawn / AL.RULE_FILE).write_text(json.dumps(body))
    with pytest.raises(SupplementaryError, match="changed after the sheet was drawn"):
        _score(drawn, path)


def test_score_checks_labels_and_paragraph_ids(drawn):
    rows = AL.read_sheet(drawn / AL.SHEET_FILE)
    a, b = rows[0]["item_id"], rows[1]["item_id"]
    for labels, msg in (({a: ("maybe", "")}, "not one of"),
                        ({a: ("paragraph", "")}, "exactly one"),
                        ({a: ("multi_paragraph", "md_90001::p00001")}, "two or more"),
                        ({a: ("paragraph", "md_99999::p00001")}, "unknown paragraph_id")):
        with pytest.raises(SupplementaryError, match=msg):
            _score(drawn, labelled_copy(drawn, labels))
    assert b


def test_score_metrics_and_decisions(drawn):
    key = json.loads((drawn / AL.KEY_FILE).read_text())
    enf = sorted(i for i, v in key["items"].items() if v["source"] == "enforcement")
    faqs = sorted(i for i, v in key["items"].items() if v["source"] == "faq")
    linked_enf = [i for i in enf if key["items"][i]["link"]]
    first = linked_enf[0]
    shown = key["items"][first]["shown_order"][0]
    labels = {first: ("paragraph", shown), faqs[0]: ("paragraph", "md_90002::p00002"),
              faqs[1]: ("multi_paragraph", "md_90001::p00002;md_90001::p00003"), faqs[2]: ("direction_only", "")}
    for i in enf[1:]:
        labels[i] = ("wrong_direction", "") if key["items"][i]["link"] else ("unanchored", "")
    out = _score(drawn, labelled_copy(drawn, labels), minutes=24)
    e, f = out["per_source"]["enforcement"], out["per_source"]["faq"]
    assert e["clean_rate"]["k"] == 1 and e["clean_rate"]["n"] == 3
    assert f["label_distribution"] == {"paragraph": 1, "multi_paragraph": 1, "direction_only": 1,
                                       "wrong_direction": 0, "unanchored": 0}
    assert f["paragraph_or_multi_rate"]["k"] == 2
    assert e["candidate_hit_share"]["k"] == 1 and e["candidate_hit_share"]["n"] == 1
    assert e["candidate_hit_share_by_pool"][AL.POOL_LINKED] == e["candidate_hit_share"]
    # faqs[0] (faq_0901_002) has no link: its chosen paragraph is scored in the full-corpus pool.
    assert key["items"][faqs[0]]["candidate_pool"] == AL.POOL_FULL
    assert f["candidate_hit_share_by_pool"][AL.POOL_FULL]["n"] == 1
    assert f["candidate_hit_share_by_pool"][AL.POOL_FULL]["k"] == int(
        "md_90002::p00002" in key["items"][faqs[0]]["shown_order"])
    assert sum(e["items_by_pool"].values()) == 3 and e["items_by_pool"][AL.POOL_CLASS] >= 1
    assert out["decisions"]["faq"]["decision"] == AL.DECISION_DIRECTION  # 1/3 = 33.3%
    assert out["decisions"]["enforcement"]["rule_sha256"] == key["meta"]["rule_sha256"]
    assert out["minutes_per_item"] == 4.0
    assert set(out["by_stratum"]) == {"faq", "enforcement"}


# -- decision bands and intervals --------------------------------------------------------


@pytest.mark.parametrize("rate, decision", [(0.299, AL.DECISION_VALIDATION), (0.30, AL.DECISION_DIRECTION),
                                            (0.599, AL.DECISION_DIRECTION), (0.60, AL.DECISION_PARAGRAPH),
                                            (0.0, AL.DECISION_VALIDATION), (1.0, AL.DECISION_PARAGRAPH)])
def test_decision_bands_at_the_edges(rate, decision):
    assert AL.decide(rate, RULE) == decision


def test_wilson_interval_width_at_n_30():
    lo, hi = wilson_interval(18, 30)
    assert lo == pytest.approx(0.4232, abs=1e-3) and hi == pytest.approx(0.7541, abs=1e-3)
    assert (hi - lo) / 2 == pytest.approx(0.165, abs=0.01)  # "roughly +/-17 points"


def test_cohen_kappa():
    assert AL.cohen_kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0
    assert AL.cohen_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]) == 0.0


# -- Part D conventions (fixed before any rate was seen) -------------------------------------


def _key_item(source="enforcement", link="md_1", linked=("md_1", "md_2")):
    return {"source": source, "link": {"md_id": link} if link else None, "linked_md_ids": list(linked) if link else []}


@pytest.mark.parametrize("label, ids, note, verdict", [
    ("wrong_direction", "", "md_9", "wrong:wrong_direction"),
    ("unanchored", "", "", "wrong:unanchored_with_link"),
    ("paragraph", "md_2::p00001", "", "correct:paragraph_in_linked"),
    ("multi_paragraph", "md_1::p00001;md_9::p00002", "", "wrong:paragraph_outside_linked"),
    ("paragraph", "md_9::p00001", "link wrong", "wrong:paragraph_outside_linked"),
    ("direction_only", "", "md_1", "correct:direction_only_note_matches_link"),
    ("direction_only", "", "md_7;md_2;md_8", "correct:direction_only_note_matches_link"),
    ("direction_only", "", "", "correct:direction_only_no_note_md"),
    ("direction_only", "", "md_9; uncertain: elsewhere", "wrong:direction_only_note_names_other"),
])
def test_link_verdicts(label, ids, note, verdict):
    assert AL.link_verdict({"label": label, "paragraph_ids": ids, "note": note}, _key_item()) == verdict


def test_unlinked_rows_have_no_link_verdict():
    assert AL.link_verdict({"label": "unanchored", "paragraph_ids": "", "note": ""}, _key_item(link=None)) is None


def test_convention_metrics_strict_rate_notes_and_unparsed_charges():
    rows = [{"item_id": f"e{i}", "label": lab, "paragraph_ids": ids, "note": note} for i, (lab, ids, note) in enumerate([
        ("paragraph", "md_1::p1", ""), ("paragraph", "md_1::p2", "partial 1/2"), ("paragraph", "md_9::p1", "link wrong"),
        ("direction_only", "", "md_1; uncertain: x"), ("unanchored", "", ""),
        ("direction_only", "", "Uncertain"), ("paragraph", "md_1::p3", ""), ("paragraph", "md_1::p4", "")])]
    key = {r["item_id"]: _key_item() for r in rows}
    key["e5"] = _key_item(link=None)
    items = [{"item_id": "a", "fields": {"deficiencies": []}}, {"item_id": "b", "fields": {"deficiencies": ["x"]}}]
    out = AL.convention_metrics(rows, key, RULE, items)
    e = out["per_source"]["enforcement"]
    assert e["n"] == 8 and e["partial_notes"] == 1 and e["uncertain_notes"] == 2 and e["partial_among_paragraph"] == 1
    assert e["strict_clean_rate"]["k"] == 4 and e["strict_decision"] == AL.DECISION_DIRECTION  # 4/8 = 50%
    assert e["primary_decision"] == AL.DECISION_PARAGRAPH and e["strict_same_band"] is False  # 5/8 = 62.5%
    assert e["link_verdicts"] == {"correct:direction_only_note_matches_link": 1, "correct:paragraph_in_linked": 4,
                                  "wrong:paragraph_outside_linked": 1, "wrong:unanchored_with_link": 1}
    assert e["link_precision_strict"]["k"] == 5 and e["link_precision_strict"]["n"] == 7
    assert out["per_source"]["faq"]["n"] == 0
    assert out["enforcement_charges_none_parsed"] == {"k": 1, "n": 2}


# -- sensitivity: post-stratified clean rate -----------------------------------------------


def _stratum(n, k):
    return {"n": n, "clean_rate": {"k": k, "n": n, "rate": k / n}}


def test_post_stratified_weights_by_population_and_lists_unsampled():
    by = {"faq:A": _stratum(3, 3), "faq:B": _stratum(3, 0)}
    out = AL.post_stratified(by, {"A": 10, "B": 30, "C": 60}, "faq:", primary_rate=0.5, rule=RULE)
    assert out["weighted_clean_rate"] == 0.25  # (10 * 1.0 + 30 * 0.0) / 40; C (60%) excluded
    assert out["population_covered"] == 40 and out["population_covered_share"] == 0.4
    assert out["unsampled_strata"] == [{"stratum": "C", "population": 60, "share": 0.6}]
    assert out["weighted_decision"] == AL.DECISION_VALIDATION and out["primary_decision"] == AL.DECISION_DIRECTION
    assert out["same_band_as_primary"] is False and "no interval" in out["note"]
    assert [r["stratum"] for r in out["strata"]] == ["A", "B"] and out["strata"][0]["sampled"] == 3


def test_post_stratified_equals_the_plain_rate_when_allocation_is_proportional():
    by = {"e:A": _stratum(2, 1), "e:B": _stratum(4, 2)}
    out = AL.post_stratified(by, {"A": 20, "B": 40}, "e:", primary_rate=0.5, rule=RULE)
    assert out["weighted_clean_rate"] == 0.5 and out["same_band_as_primary"] is True


def test_post_stratified_flags_sampled_strata_missing_from_the_population():
    out = AL.post_stratified({"e:A": _stratum(2, 1), "e:Z": _stratum(1, 1)}, {"A": 5}, "e:", 0.5, RULE)
    assert out["sampled_strata_without_population"] == ["e:Z"] and out["weighted_clean_rate"] == 0.5

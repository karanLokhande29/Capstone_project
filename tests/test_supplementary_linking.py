"""P2-003 §T: direction-level linking. Order exact_ref -> repeal_map -> title_fuzzy -> none; threshold from config."""

from __future__ import annotations

import copy

import pytest

from src.supplementary import linking as L
from src.supplementary import withdrawn
from tests.supplementary_support import CB, MANIFEST, PARAGRAPHS, UCB, repo_blocks


def index(threshold: float | None = None) -> L.LinkIndex:
    blocks = repo_blocks()
    conf = copy.deepcopy(blocks["supplementary"]["linking"])
    if threshold is not None:
        conf["fuzzy_threshold"] = threshold
    return L.LinkIndex.build(MANIFEST, PARAGRAPHS, withdrawn.local_repeal_map(PARAGRAPHS), linking=conf,
                             core_classes=blocks["matching"]["core_entity_classes"])


def test_threshold_comes_from_config():
    assert index().threshold == repo_blocks()["supplementary"]["linking"]["fuzzy_threshold"]


def test_subject_and_title_normalisation():
    assert L.subject_of(MANIFEST[0]["title"], CB) == "Know Your Customer"
    assert L.subject_of(MANIFEST[4]["title"]) == "Gadget Remittances"
    assert L.normalise_title("Reserve Bank of India (Commercial Banks - Know Your Customer) Directions, 2025") \
        == L.normalise_title(MANIFEST[0]["title"])
    assert L.subject_tokens("Housing Finance for UCBs") == frozenset({"housing", "finance"})


def test_exact_ref_by_hyperlink_even_across_class():
    r = index().link_one("x", "anchor text", href="BS_ViewMasDirections.aspx?id=90002", entity_class=UCB)
    assert (r["md_id"], r["method"], r["basis"]) == ("md_90002", "exact_ref", "md_hyperlink")


def test_exact_ref_by_reference_number():
    r = index().link_one("x", "circular DOR.AML.REC.100/14.01.001/2025-26 dated November 28, 2025")
    assert (r["md_id"], r["method"], r["basis"]) == ("md_90001", "exact_ref", "reference_number")


def test_exact_ref_by_title_with_or_without_year():
    idx = index()
    r = idx.link_one("x", "Reserve Bank of India (Commercial Banks – Know Your Customer) Directions, 2025")
    assert (r["md_id"], r["method"], r["basis"]) == ("md_90001", "exact_ref", "title")
    r = idx.link_one("x", "Reserve Bank of India (Commercial Banks – Know Your Customer) Directions")
    assert (r["md_id"], r["basis"]) == ("md_90001", "title_no_year")


def test_repeal_map_by_annex_reference():
    r = index().link_one("x", "A.P. (DIR Series) Circular No. 64/2015-16")
    assert (r["md_id"], r["method"], r["basis"]) == ("md_90005", "repeal_map", "annex_reference")


def test_repeal_map_by_repeal_statement_subject():
    r = index().link_one("x", "Management of Advances – UCBs", entity_class=UCB)
    assert (r["md_id"], r["method"], r["basis"]) == ("md_90006", "repeal_map", "repeal_statement")


def test_repeal_map_never_crosses_a_resolved_class():
    r = index().link_one("x", "Management of Advances – UCBs", entity_class=CB)
    assert r["method"] != "repeal_map" and r["md_id"] != "md_90006"


def test_title_fuzzy_scoped_by_class_with_margin():
    idx = index()
    r = idx.link_one("x", "Know Your Customer (KYC)", entity_class=UCB)
    assert (r["md_id"], r["method"]) == ("md_90003", "title_fuzzy")
    assert r["score"] == pytest.approx(6 / 7, abs=1e-6)
    assert r["second_best_md_id"] is not None and r["margin"] is not None
    r = idx.link_one("x", "Know Your Customer (KYC)", entity_class=CB)
    assert r["md_id"] == "md_90001"


def test_ties_broken_by_class_order_then_recorded():
    r = index().link_one("x", "Know Your Customer")  # no class: CB and UCB tie
    assert r["md_id"] == "md_90001" and r["tied_best"] == 2 and r["margin"] == 0.0


def test_threshold_decides_fuzzy_vs_none():
    cited = "Know Your Customer (KYC)"
    assert index(0.80).link_one("x", cited, entity_class=UCB)["method"] == "title_fuzzy"
    below = index(0.90).link_one("x", cited, entity_class=UCB)
    assert below["method"] == "none" and below["md_id"] is None
    assert below["basis"] == "best_below_threshold:md_90003" and below["score"] == pytest.approx(6 / 7, abs=1e-6)


def test_method_order_exact_beats_repeal_beats_fuzzy():
    idx = index()
    # The title also fuzzy-matches, but the exact title wins.
    assert idx.link_one("x", MANIFEST[3]["title"], entity_class=UCB)["method"] == "exact_ref"
    # The subject is both a repeal-statement subject and not an exact title: repeal_map before fuzzy.
    assert idx.link_one("x", "Management of Advances", entity_class=UCB)["method"] == "repeal_map"


def test_none_when_nothing_matches_or_nothing_cited():
    idx = index()
    assert idx.link_one("x", "Auction procedure")["method"] == "none"
    r = idx.link_one("x", None)
    assert r["method"] == "none" and r["basis"] == "nothing_cited"


def _item(item_id, source, cited, entity=None, fields=None):
    return {"item_id": item_id, "source": source, "title": "", "cited_directions": cited, "entity_class": entity,
            "fields": fields or {}}


def test_link_items_records_and_best_link():
    idx = index()
    items = [
        _item("enf_1", "enforcement", ["Auction", "Know Your Customer (KYC)"], UCB),
        _item("enf_2", "enforcement", [], UCB),
        _item("faq_1", "faq", [], None, {"linked_md_ids": [], "topic_cited_directions": ["Priority Lending"],
                                         "topic_linked_md_ids": ["md_90002", "md_90005"]}),
        _item("wdr_local_1", "withdrawn", [], None, {"origin": "local_annex", "repealing_md_id": "md_90005"}),
    ]
    recs = L.link_items(idx, items)
    by = {}
    for r in recs:
        by.setdefault(r["item_id"], []).append(r)
    assert [r["method"] for r in by["enf_1"]] == ["none", "title_fuzzy"]
    assert L.best_link(by["enf_1"])["md_id"] == "md_90003"
    assert by["enf_2"] == [{**by["enf_2"][0], "method": "none", "basis": "nothing_cited"}]
    assert L.best_link(by["faq_1"])["md_id"] == "md_90002"  # topic scope, most-linked Direction first
    assert all(r["cited_scope"] == "topic" for r in by["faq_1"])
    assert by["wdr_local_1"][0]["method"] == "repeal_map" and by["wdr_local_1"][0]["md_id"] == "md_90005"
    assert all(tuple(r) == L.LINK_FIELDS for r in recs)
    cov = L.coverage(items, recs)
    assert cov["enforcement"]["title_fuzzy"] == 1 and cov["enforcement"]["none"] == 1
    assert cov["withdrawn:local_annex"]["repeal_map"] == 1


def test_linking_is_deterministic():
    items = [_item(f"enf_{i}", "enforcement", ["Know Your Customer", "Interest Rate on Deposits"], None)
             for i in range(5)]
    assert L.link_items(index(), items) == L.link_items(index(), items)

"""P2-003 §T: the four source parsers, on saved fixtures. No network."""

from __future__ import annotations

from datetime import date

from src.supplementary import amendments, enforcement, faq, withdrawn
from src.supplementary.common import ITEM_FIELDS
from tests.supplementary_support import PARAGRAPHS, fixture, repo_blocks

CUT = date(2025, 11, 28)
ENTRY = {"url": "https://x/u", "retrieved_at": "2026-09-26T00:00:00+00:00", "content_hash": "h"}


# -- FAQ: index -> topic -> Q&A --------------------------------------------------


def test_faq_index_lists_topics_with_category_date_and_pdf():
    topics = faq.parse_index(fixture("faq_index.html"), "https://x/FAQDisplay.aspx?Id={id}")
    assert [t["faq_topic_id"] for t in topics] == [901, 902, 903]
    assert topics[0]["category"] == "Commercial Banking" and topics[2]["category"] == "Foreign Exchange Management"
    assert topics[0]["topic_title"] == "Widget Accounts" and topics[0]["listed_date"] == "2026-01-10"
    assert topics[1]["pdf_url"].endswith("X.PDF") and topics[0]["pdf_url"] is None
    assert topics[0]["url"] == "https://x/FAQDisplay.aspx?Id=901"


def _topic(n: int):
    meta = next(t for t in faq.parse_index(fixture("faq_index.html"), "https://x/?Id={id}") if t["faq_topic_id"] == n)
    return faq.parse_topic(fixture(f"faq_{n}.html"), meta, ENTRY, CUT)


def test_faq_table_of_contents_is_dropped_and_answers_kept():
    out = _topic(901)
    qs = [i["fields"]["question"] for i in out["items"]]
    assert qs == ["Q 1. What is a Widget Account?", "Q 2. Who can open a Widget Account?",
                  "Q. 3. Can interest be paid on it?"]
    second = out["items"][1]["fields"]["answer"]
    assert second.startswith("Ans. Banks shall open it only") and "ii) The account may be joint." in second
    assert "Disclaimer" not in out["items"][-1]["fields"]["answer"]
    assert out["items"][0]["item_id"] == "faq_0901_001" and out["items"][0]["fields"]["faq_item_index"] == 1


def test_faq_query_clarification_rows_sections_and_md_links():
    items = _topic(902)["items"]
    assert len(items) == 3
    assert items[0]["fields"]["question"].startswith("Query 1: Can gadget loans")
    assert items[0]["fields"]["answer"].startswith("Clarification: Yes. Banks shall classify")
    assert items[0]["fields"]["section"] == "A. Classification of loans"
    assert items[1]["fields"]["section"] == "B. Computation"
    assert items[0]["fields"]["linked_md_ids"] == ["md_90002"]
    assert items[0]["cited_directions"] == ["Master Directions on Priority Lending, 2025"]
    assert items[2]["cited_directions"] == [] and items[2]["fields"]["topic_linked_md_ids"] == ["md_90002"]


def test_faq_leading_disclaimer_and_shared_answer():
    items = _topic(903)["items"]
    assert len(items) == 2
    assert items[0]["fields"]["question"] == "Q1. Can a resident remit for gadgets?\nQ2. Is there a limit on such remittances?"
    assert items[0]["fields"]["questions_grouped"] == 2 and items[0]["fields"]["answer"].startswith("A.(1 to 2)")
    assert items[1]["fields"]["answer"] == "Answer: Yes, as per its Board-approved policy."


def test_faq_items_follow_the_schema_and_era():
    for n in (901, 902, 903):
        for item in _topic(n)["items"]:
            assert tuple(item) == ITEM_FIELDS and item["source"] == "faq" and item["entity_class"] is None
    assert _topic(901)["items"][0]["era"] == "post_consolidation"
    assert _topic(903)["items"][0]["era"] == "pre_consolidation"


# -- enforcement -------------------------------------------------------------------


def test_listing_keeps_penalties_and_counts_near_misses():
    conf = repo_blocks()["supplementary"]["enforcement"]
    rows = enforcement.parse_dated_listing(fixture("pr_2026.html"), enforcement._PRID)
    out = enforcement.classify_titles(rows, conf["include_title_regex"], conf["near_miss_title_regexes"])
    assert sorted(r["id"] for r in out["kept"]) == [801, 802, 803, 804]
    assert out["near_miss_by_pattern"]["cancels_registration"] == 1
    assert out["near_miss_by_pattern"]["directions_section_35a"] == 1
    assert len(out["near_misses"]) == 2  # the Money Supply release is neither kept nor a near miss
    assert {r["id"]: r["listed_date"] for r in rows}[803] == "2026-01-15"


def _release(n: int):
    return enforcement.parse_release(fixture(f"pen_{n}.html"), {"prid": n}, ENTRY, CUT)


def test_quoted_titles_and_deficiencies_are_verbatim():
    item = _release(801)
    f = item["fields"]
    assert f["quoted_titles"] == ["Know Your Customer (KYC)", "Management of Advances – UCBs"]
    assert f["unquoted_subjects"] == []
    assert f["deficiencies"] == ["The bank had failed to carry out periodic updation of KYC of certain customers.",
                                 "The bank had sanctioned loans to relatives of its directors."]
    assert item["cited_directions"] == ["Know Your Customer (KYC)", "Management of Advances – UCBs"]
    assert item["entity_class"] == "Urban Co-operative Banks" and f["entity_class_rule"] == "name:urban_co_operative"
    assert f["penalty_amount"] == "₹1.00 lakh" and f["order_date"] == "2026-09-20"
    assert f["press_release_no"] == "2026-2027/1181"
    assert item["published_date"] == "2026-09-24" and item["era"] == "post_consolidation"


def test_unquoted_subject_and_listed_charges():
    f = _release(802)["fields"]
    assert f["quoted_titles"] == [] and f["unquoted_subjects"] == ["Know Your Customer (KYC)"]
    assert f["deficiencies"] == ["(i) The company failed to undertake enhanced due diligence for certain customers; and",
                                 "(ii) The company failed to report suspicious transactions within the prescribed time."]
    assert _release(802)["entity_class"] == "Non-Banking Financial Companies"


def test_statute_only_release_cites_no_direction():
    item = _release(803)
    assert item["cited_directions"] == []
    assert item["fields"]["statutes_cited"] == ["Section 20 read with Section 56 of the Banking Regulation Act, 1949 (BR Act)"]
    assert item["entity_class"] == "Rural Co-operative Banks"
    assert item["fields"]["deficiencies"] == ["The bank had sanctioned loans to its directors."]


def test_entity_class_rules_are_deterministic():
    r = enforcement.resolve_entity_class
    assert r("XYZ Payments Bank Limited", "")[0] == "Payments Banks"
    assert r("ABC Small Finance Bank Limited", "")[0] == "Small Finance Banks"
    assert r("Pragathi Gramin Bank", "")[0] == "Regional Rural Banks"
    assert r("The Kerala State Co-operative Bank Ltd.", "")[0] == "Rural Co-operative Banks"
    assert r("Shree Sahakari Bank Ltd.", "")[0] == "Urban Co-operative Banks"
    assert r("Foo Capital Limited", "powers under Section 58-G of the RBI Act")[0] == "Non-Banking Financial Companies"
    assert r("Big Bank Limited", "Section 47A of the Banking Regulation Act, 1949")[0] == "Commercial Banks"
    assert r("Mystery Traders", "")[0] == "unresolved"


# -- amendments --------------------------------------------------------------------


def test_amendment_listing_filters_directions_after_cutoff():
    conf = repo_blocks()["supplementary"]["amendments"]
    rows = enforcement.parse_dated_listing(fixture("notif_2026.html"), amendments._NOTIF_ID)
    out = enforcement.classify_titles(rows, conf["include_title_regex"],
                                      {"amendment_not_directions": conf["near_miss_title_regex"]})
    kept = sorted(r["id"] for r in out["kept"] if r["listed_date"] >= "2025-11-28")
    assert kept == [701, 702]
    assert out["near_miss_by_pattern"] == {"amendment_not_directions": 1}


def test_amended_direction_and_paragraph_numbers_are_verbatim():
    item = amendments.parse_notification(fixture("amd_701.html"), {"notification_id": 701,
                                                                   "listed_date": "2026-09-18"}, ENTRY, CUT)
    f = item["fields"]
    assert f["amended_directions_cited"] == ["Reserve Bank of India (Commercial Banks – Know Your Customer) Directions, 2025"]
    assert f["title_derived_target"] == "Reserve Bank of India (Commercial Banks – Know Your Customer) Directions"
    assert f["paragraph_refs"] == ["paragraph 5(1)(v)", "Paragraph 5(1)(v)", "Paragraphs 12 and 14"]
    assert f["linked_md_ids"] == ["md_90001"]
    assert f["rbi_ref"] == "RBI/2026-27/257" and f["dept_ref"] == "DOR.AML.REC.226/14.01.002/2026-27"


def test_earlier_amendments_are_kept_apart():
    f = amendments.parse_notification(fixture("amd_702.html"), {"notification_id": 702}, ENTRY, CUT)["fields"]
    assert f["amended_directions_cited"] == [
        "Reserve Bank of India (Urban Co-operative Banks – Interest Rate on Deposits) Directions, 2025"]
    assert f["earlier_amendments_cited"] == [
        "Reserve Bank of India (Urban Co-operative Banks – Interest Rate on Deposits) Amendment Directions, 2026"]
    assert f["paragraph_refs"] == ["paragraph 6.1"]


# -- withdrawn / repeal --------------------------------------------------------------


def test_online_withdrawn_list():
    out = withdrawn.parse_withdrawn_list(fixture("withdrawn_list.html"))
    assert [r["serial"] for r in out["rows"]] == [1, 2, 3]
    assert out["rows"][2]["repeal_deferred"] and out["rows"][2]["title"].endswith("Guidelines for Banks")
    assert out["rows"][1]["circular_number"] == "DCBR.BPD.MC.No.5/13.05.000/2015-16"
    assert out["rows"][0]["date"] == "2016-02-25" and out["rows"][0]["href"].endswith("Id=10000&Mode=0")
    assert out["notes"] == ["@-circulars shall be repealed with effect from January 01, 2026"]


def test_repeal_annex_extraction_on_processed_paragraphs():
    entries = withdrawn.extract_annex_entries(PARAGRAPHS["md_90005"])
    assert [e["refs"] for e in entries] == [["A.P. (DIR Series) Circular No. 64/2015-16"],
                                            ["Notification No. FEMA 5(R)/2015-RB"]]
    assert {e["md_id"] for e in entries} == {"md_90005"} and entries[0]["date"] == "2016-04-28"


def test_repeal_statement_extraction():
    (s,) = withdrawn.extract_repeal_statements(PARAGRAPHS["md_90006"])
    assert s["subject"] == "Management of Advances" and s["applicable_to"] == "Urban Co-operative Banks"
    assert s["via_ref"] == "DOR.RRC.REC.302/33-01-010/2025-26" and s["md_id"] == "md_90006"


def test_local_repeal_items_carry_their_repealing_direction():
    rep = withdrawn.local_repeal_map(PARAGRAPHS)
    items = withdrawn.local_items(rep, CUT)
    assert rep["directions_with_annex"] == 1 and rep["directions_with_repeal_statement"] == 1
    assert {i["fields"]["repealing_md_id"] for i in items} == {"md_90005", "md_90006"}
    assert all(tuple(i) == ITEM_FIELDS and i["source"] == "withdrawn" for i in items)

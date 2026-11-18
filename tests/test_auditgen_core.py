"""Audit generator: profile, applicability, temporal, changes, calendar, differential, enforcement, citations, excerpts,
disclaimer on every output, review re-import, exports, freshness dry run, research-file integrity."""

from __future__ import annotations

import copy
import io
import json
from datetime import date
from pathlib import Path

import pytest

from src.auditgen import applicability as APP
from src.auditgen import calendar_extract as CAL
from src.auditgen import exports as EX
from src.auditgen import freshness as FR
from src.auditgen import guard as GUARD
from src.auditgen import pack as PK
from src.auditgen import review as RV
from src.auditgen import temporal as TMP
from src.auditgen.corpus import excerpt, get_store, load_config, read_jsonl, word_count
from src.auditgen.profile import Profile, ProfileError

DISC = "Decision support only; verify against the official RBI text; not legal advice."


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def store(cfg):
    return get_store(cfg)


def _profile(cls="Payments Banks", acts=("deposits", "payments", "kyc_aml"), group=("Small Finance Banks",), as_of="2026-10-15"):
    return Profile("Test entity", cls, as_of, "2025-12-01", list(acts), list(group))


@pytest.fixture(scope="module")
def pack(store, cfg):
    return PK.generate(store, cfg, _profile())


@pytest.fixture(scope="module")
def nbfc_pack(store, cfg):
    return PK.generate(store, cfg, _profile("Non-Banking Financial Companies", ("lending",), ()))


# -- profile -------------------------------------------------------------------------------------------

def test_profile_validation(store):
    p = _profile().validate(store.core_classes)
    assert p.group_classes == ["Small Finance Banks"]
    for bad in (dict(entity_class="Foreign Exchange Management"), dict(activities=["crypto"]), dict(last_review="2027-01-01"),
                dict(as_of="15/10/2026"), dict(group_classes=["Issuer of Currency"]), dict(name=" ")):
        d = {**_profile().as_dict(), **bad}
        with pytest.raises(ProfileError):
            Profile.from_dict(d).validate(store.core_classes)
    with pytest.raises(ProfileError):
        Profile.from_dict({**_profile().as_dict(), "surprise": 1})


def test_profile_round_trip(tmp_path, store):
    p = _profile().validate(store.core_classes)
    f = tmp_path / "p.json"
    p.save(f)
    assert Profile.load(f).as_dict() == p.as_dict()


# -- applicability ---------------------------------------------------------------------------------------

def test_register_binds_the_class_or_a_cross_cutting_activity(pack, store):
    for r in pack["register"]:
        cls = store.docs[r["md_id"]]["entity_class"]
        assert cls == "Payments Banks" or (cls in store.function_headings and r["applies_to"].startswith("cross-cutting"))
        assert r["obligation_id"].startswith("t1c_")


def test_activity_filter_hides_but_never_deletes(store, cfg):
    full = APP.build_register(store, cfg, _profile(acts=APP.family_activities(cfg) and ["deposits", "payments", "kyc_aml", "outsourcing", "it_cyber", "lending"]).validate(store.core_classes))
    narrow = APP.build_register(store, cfg, _profile(acts=["deposits"]).validate(store.core_classes))
    ids_full = {r["obligation_id"] for r in full if not r["applies_to"].startswith("cross-cutting")}
    ids_narrow = {r["obligation_id"] for r in narrow if not r["applies_to"].startswith("cross-cutting")}
    assert ids_full == ids_narrow  # nothing deleted
    hidden = [r for r in narrow if r["filtered_by_activity"]]
    assert hidden and all(r["hidden"] and "filtered by activity" in r["hidden_reason"] for r in hidden)


def test_low_confidence_rows_need_review(pack, cfg):
    t = cfg["confidence"]["review_threshold"]
    assert all(r["needs_review"] for r in pack["register"] if r["confidence"] < t)


# -- temporal and changes --------------------------------------------------------------------------------------

def test_temporal_status_matches_t3_items(store):
    items = read_jsonl(store.root / "data/benchmark/t3/t3_items_v1.jsonl")
    drop = set(json.loads((store.root / "data/benchmark/t3/t3_dropped_after_check2_v1.json").read_text())["dropped_items"])
    for it in [i for i in items if i["t3_id"] not in drop][:15]:
        assert TMP.t3_prediction(store, it) == it["gold_status"]


def test_change_window(pack, store, cfg):
    lo, hi = pack["profile"]["last_review"], pack["profile"]["as_of"]
    for c in pack["changes"]:
        if c["change"] in ("amended", "deleted", "newly in force", "circular withdrawn") or c["change"].startswith("Direction text updated"):
            assert lo < c["effective"] <= hi
    same_day = PK.generate(store, cfg, Profile("x", "Payments Banks", "2026-10-15", "2026-10-15", ["deposits"], []))
    assert same_day["changes"] == []


# -- calendar ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text,kind,freq,offset", [
    ("The bank shall submit the return within 15 days from the end of each quarter.", "recurring", "quarterly", 15),
    ("The statement shall be furnished within seven days of the close of the month.", "recurring", "monthly", 7),
    ("Any change shall be reported within thirty days of such change.", "event", None, 30),
    ("A certificate shall be submitted on or before June 30 every year.", "fixed", "annually", None),
    ("Banks shall review the policy on a half-yearly basis.", "recurring", "half-yearly", 0),
])
def test_calendar_extraction(text, kind, freq, offset):
    e = CAL.extract(text)[0]
    assert e["kind"] == kind and e["frequency"] == freq
    if offset is not None:
        assert e["offset_days"] == offset
    assert 0 < e["confidence"] <= 1 and word_count(e["phrase"]) <= 25


def test_calendar_occurrences_and_ics():
    e = {"kind": "recurring", "frequency": "quarterly", "offset_days": 15, "entry_id": "E1", "phrase": "within 15 days", "summary": "quarterly return",
         "direction_title": "D", "paragraph_id": "md_1::p1", "source_url": "https://x", "confidence": 0.9, "verify": False}
    occ = CAL.occurrences(e, date(2026, 10, 15), date(2027, 10, 15))
    assert occ[0] == date(2026, 10, 15) and occ[1] == date(2027, 1, 15) and len(occ) == 5  # 30 Sep + 15 d is inside the window
    ics = CAL.to_ics([e], prodid="-//t//EN", start=date(2026, 10, 15), end=date(2027, 10, 15), fy_end="03-31")
    assert ics.startswith("BEGIN:VCALENDAR") and ics.count("BEGIN:VEVENT") == 5 and all(len(l.encode()) <= 75 for l in ics.split("\r\n"))
    assert CAL.occurrences({**e, "kind": "event"}, date(2026, 1, 1), date(2027, 1, 1)) == []


# -- differential and enforcement ----------------------------------------------------------------------------------

def test_differential_flags_every_non_shared_call(pack):
    rows = pack["differential"]
    assert rows
    for r in rows:
        if r["differential"] in ("possibly different", "no counterpart found (possibly class-specific)"):
            assert r["needs_review"] and "miss most differential cases" in r["caution"]
        if r["differential"] == "shared":
            assert r["counterpart_paragraph_id"] and not r["needs_review"]
    assert "miss most differential cases" in pack["differential_caution"]


def test_enforcement_links_same_class_releases(nbfc_pack):
    rows = nbfc_pack["enforcement"]
    assert rows and all(r["penalty_count"] == len(r["press_releases"]) > 0 for r in rows)
    assert all("not a prediction" in r["label"] for r in rows)
    assert all(p["url"].startswith("https://www.rbi.org.in/") for r in rows for p in r["press_releases"])
    assert all(r["entity_class"] == "Non-Banking Financial Companies" for r in rows)


def test_enforcement_keeps_releases_without_a_current_direction(store, cfg):
    # SFB penalty releases cite pre-2026 circulars only: they appear as release-level rows, never silently dropped.
    p = PK.generate(store, cfg, Profile(name="t", entity_class="Small Finance Banks", as_of="2026-10-30", last_review="2025-12-01",
                                        activities=["deposits"], group_classes=[]))
    rows = p["enforcement"]
    assert rows and all(r["citation_level"] == "release" and not r["md_id"] for r in rows)
    assert all(r["source_url"].startswith("https://www.rbi.org.in/") and "map it by hand" in r["link_note"] for r in rows)
    assert p["summary"]["enforcement_releases"] == 3 and p["summary"]["enforcement_directions"] == 0
    assert not p["dropped_without_citation"].get("enforcement")
    PK.require_citation("enforcement", rows[0])


# -- citations, excerpts, disclaimer --------------------------------------------------------------------------------

def test_citation_required_rule():
    good = {"row_id": "r", "md_id": "md_1", "paragraph_id": "md_1::p1", "direction_title": "T", "source_url": "https://rbidocs.rbi.org.in/x", "status": "in force"}
    PK.require_citation("register", good)
    for k in ("md_id", "paragraph_id", "direction_title", "source_url", "status"):
        with pytest.raises(PK.CitationError):
            PK.require_citation("register", {**good, k: ""})
    PK.require_citation("enforcement", {**good, "paragraph_id": None, "citation_level": "direction"})
    p = {"register": [good, {**good, "row_id": "bad", "direction_title": ""}], "changes": [], "calendar": [], "differential": [],
         "enforcement": [], "gaps": None}
    dropped = PK.enforce_rules(p, 25)
    assert [r["row_id"] for r in p["register"]] == ["r"] and dropped["register"]["count"] == 1


def test_every_row_is_cited_and_excerpts_are_short(pack):
    for sec in ("register", "changes", "calendar", "differential", "enforcement"):
        for r in pack[sec]:
            PK.require_citation(sec, r)
            for f in ("excerpt", "counterpart_excerpt", "phrase"):
                if r.get(f):
                    assert word_count(r[f]) <= 25, (sec, r["row_id"], f)
    assert word_count(excerpt(" ".join(["word"] * 80), 25)) == 25


def test_disclaimer_on_every_output(pack):
    import docx
    import pdfplumber
    from openpyxl import load_workbook

    assert pack["disclaimer"] == DISC and pack["about"]["disclaimer"] == DISC
    wb = load_workbook(io.BytesIO(EX.to_excel(pack)))
    assert list(wb.sheetnames) == list(EX.SHEETS)
    assert any(DISC in str(c.value) for row in wb["About"].iter_rows() for c in row)
    assert any(DISC in str(c.value) for row in wb["Applicability"].iter_rows() for c in row)
    d = docx.Document(io.BytesIO(EX.to_docx(pack)))
    assert DISC in "\n".join(p.text for p in d.paragraphs)
    with pdfplumber.open(io.BytesIO(EX.to_pdf(pack))) as pdf:
        assert DISC in (pdf.pages[0].extract_text() or "")
        assert len(pdf.pages) >= 2
    assert "Decision support only" in EX.to_ics(pack).replace("\r\n ", "")
    trail = EX.audit_trail(pack)
    assert trail["disclaimer"] == DISC and trail["corpus"]["sha256"] and trail["rules_version"]


def test_about_box_carries_versions_hash_profile_and_validation(pack):
    a = pack["about"]
    for k in ("tool_version", "rules_version", "rules_sha256", "corpus", "as_of", "entity_profile", "validation", "disclaimer"):
        assert a[k]
    assert len(a["corpus"]["sha256"]) == 64 and a["corpus"]["snapshot_date"]
    assert set(a["validation"]) >= {"applicability", "temporal", "calendar", "gap_analysis", "differential"}


# -- review --------------------------------------------------------------------------------------------------------

def test_review_updates_and_progress(pack):
    p = copy.deepcopy(pack)
    rid = p["register"][0]["row_id"]
    assert RV.apply_updates(p, [{"section": "register", "row_id": rid, "review_status": "confirmed", "reviewer": "A", "note": "ok"}]) == 1
    assert p["register"][0]["timestamp"]
    with pytest.raises(RV.ReviewError):
        RV.apply_updates(p, [{"section": "register", "row_id": rid, "review_status": "maybe", "reviewer": "A"}])
    with pytest.raises(RV.ReviewError):
        RV.apply_updates(p, [{"section": "register", "row_id": rid, "review_status": "confirmed", "reviewer": ""}])
    assert RV.progress(p)["reviewed"] == 1


def test_review_reimport_writes_a_new_signed_pack(pack, tmp_path):
    from openpyxl import load_workbook

    original = json.dumps(pack, sort_keys=True)
    f = tmp_path / "pack.xlsx"
    f.write_bytes(EX.to_excel(pack))
    wb = load_workbook(f)
    ws = wb["Applicability"]
    head = [c.value for c in ws[1]]
    ws.cell(row=2, column=head.index("review_status") + 1, value="disputed")
    ws.cell(row=2, column=head.index("reviewer") + 1, value="Reviewer One")
    ws.cell(row=2, column=head.index("note") + 1, value="threshold differs")
    wb.save(f)
    ups = RV.read_review_workbook(f)
    new = RV.signed_off(pack, ups, signer="Head of Compliance", source_name=f.name, source_sha256="x" * 64)
    assert json.dumps(pack, sort_keys=True) == original  # the original is kept unchanged
    assert new["derived_from"] == pack["pack_id"] and new["pack_id"] != pack["pack_id"]
    assert new["signoff"]["signer"] == "Head of Compliance" and new["signoff"]["disputed"][0]["note"] == "threshold differs"
    assert new["register"][0]["review_status"] == "disputed"
    with pytest.raises(RV.ReviewError):
        RV.signed_off(pack, ups, signer=" ", source_name="x", source_sha256="y")


# -- freshness ------------------------------------------------------------------------------------------------------

def test_freshness_status(store, cfg):
    s = FR.status(store, cfg, today=date(2026, 10, 15))
    assert s["snapshot_date"] and isinstance(s["age_days"], int)
    old = FR.status(store, cfg, today=date(2030, 1, 1))
    assert old["warn"] and "older than 30" in old["message"]


def test_refresh_dry_run_writes_nothing_and_respects_rate_limit(store, cfg, tmp_path):
    from src.supplementary.common import FetchResult
    from tests.test_scraper_rbi import FIXTURE_LISTING_HTML

    calls, sleeps = [], []

    def fake_fetch(url, session, rcfg, **kw):
        calls.append(url)
        if "BS_ViewMasDirections" in url:
            return FetchResult(url, True, FIXTURE_LISTING_HTML.encode(), None, 200, "2026-10-15T00:00:00+00:00")
        return FetchResult(url, False, None, "test_offline", None, "2026-10-15T00:00:00+00:00")

    before = GUARD.snapshot()
    f = FR.Fetcher(budget=4, session=object(), sleep=sleeps.append, fetch_fn=fake_fetch)
    res = FR.dry_run(store, cfg, fetcher=f)
    assert res["writes"] == "none (dry run)" and res["requests"] == len(calls) <= 4
    assert res["listing_count"] > 0 and isinstance(res["new_directions"], list)
    assert all(s <= FR.RATE_LIMIT_SEC for s in sleeps)
    assert GUARD.compare(before) == {"changed": [], "deleted": []}
    with pytest.raises(FR.RefreshError):
        g = FR.Fetcher(budget=0, session=object(), sleep=lambda s: None, fetch_fn=fake_fetch)
        g.get("https://example.invalid", marker=None)


@pytest.mark.parametrize("target", ["data/processed", "data/processed/inner", "data/benchmark/x", "data"])
def test_apply_refuses_research_targets_before_creating_anything(store, cfg, target):
    bad = {**cfg, "paths": {**cfg["paths"], "auditgen_corpus": target}}
    plan = {"new_directions": [], "updated_directions": [], "amendment_directions": {"new": []}}
    before = sorted(p.name for p in (store.root / "data/processed").iterdir())
    with pytest.raises(FR.RefreshError):
        FR.apply(store, bad, fetcher=FR.Fetcher(budget=1, session=object(), sleep=lambda s: None, fetch_fn=lambda *a, **k: None), plan=plan)
    assert sorted(p.name for p in (store.root / "data/processed").iterdir()) == before
    assert not (store.root / "data/processed/inner").exists()


# -- research integrity -----------------------------------------------------------------------------------------------

def test_research_files_unchanged_since_the_build_snapshot():
    if not GUARD.SNAPSHOT.exists():
        pytest.skip("no research hash snapshot on this machine")
    # Draft paper files deleted on purpose on 18 Nov 2026; paper/ now holds only the camera-ready paper.
    removed_on_purpose = ("paper/", "reports/private/scratch/main_skeleton_before_draft.tex")
    before = {k: v for k, v in json.loads(GUARD.SNAPSHOT.read_text())["files"].items()
              if not k.startswith(GUARD.LIVE_COLLECTION) and not k.startswith(removed_on_purpose)}
    assert GUARD.compare(before) == {"changed": [], "deleted": []}
    # New LLM response-cache entries appear whenever the research pipeline makes a fresh call (e.g. the V2 dev runs);
    # changes to or deletions of existing cache entries are still caught by compare() above.
    assert [p for p in GUARD.added(before) if not p.startswith(("paper/", "data/llm_cache/"))] == []

"""P2-003 §T: response validation, fetching, storage, era cut-off, config checks. No network."""

from __future__ import annotations

from datetime import date

import pytest
import requests

from src.supplementary.common import (
    ERA_POST,
    ERA_PRE,
    ERA_UNKNOWN,
    SourceStore,
    SupplementaryConfig,
    SupplementaryError,
    era_of,
    fetch_items,
    fetch_url,
    parse_listing_date,
    validate_payload,
)
from tests.supplementary_support import FakeSession, Response, fixture, make_ctx, supp_config

MARKER = 'class="tablebg"'


# -- response validation -------------------------------------------------------


def test_captcha_page_is_rejected_as_captcha():
    assert validate_payload(fixture("captcha.html"), marker=MARKER) == "captcha"


def test_captcha_marker_wins_even_when_the_content_marker_is_present():
    page = fixture("pen_801.html").replace(b"</body>", b"<div class='g-recaptcha'></div></body>")
    assert validate_payload(page, marker=MARKER) == "captcha"


def test_a_real_page_that_mentions_captcha_is_kept():
    # FAQ topic 176 (FLAIR) was rejected on Kaggle for this sentence; it is genuine content.
    page = fixture("faq_901.html").replace(
        b"<p>(Updated", b"<p>Enter the username and valid captcha code (Captcha is case-sensitive).</p><p>(Updated")
    assert validate_payload(page, marker='id="example-min"') is None


def test_the_word_captcha_without_content_is_captcha():
    assert validate_payload(b"<html><body>Enter the captcha to continue</body></html>", marker=MARKER) == "captcha"


def test_waf_block_page_without_content_is_captcha():
    assert validate_payload(b"<html><body>Access Denied. Request unsuccessful.</body></html>", marker=MARKER) \
        == "captcha"


def test_html_without_the_content_marker_is_unexpected():
    assert validate_payload(b"<!DOCTYPE html><html><body>Error 500</body></html>", marker=MARKER) \
        == "unexpected_content"


def test_pdf_must_start_with_magic():
    assert validate_payload(b"%PDF-1.7 ...", expect="pdf") is None
    assert validate_payload(b"<html>not a pdf</html>", expect="pdf") == "unexpected_content"


def test_real_pages_pass():
    assert validate_payload(fixture("pen_801.html"), marker=MARKER) is None
    assert validate_payload(fixture("faq_901.html"), marker='id="example-min"') is None


# -- fetch_url ------------------------------------------------------------------


class Scripted:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = 0

    def get(self, url, timeout=None):
        self.calls += 1
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(a, Exception):
            raise a
        return a


def _fetch(session):
    return fetch_url("https://x/y", session, supp_config(), marker=MARKER, sleep_fn=lambda s: None)


def test_captcha_response_is_a_failure_with_no_content():
    res = _fetch(Scripted(Response(200, fixture("captcha.html"))))
    assert not res.ok and res.reason == "captcha" and res.data is None and res.http_status == 200


def test_404_is_final_and_not_retried():
    session = Scripted(Response(404, b""))
    res = _fetch(session)
    assert res.reason == "http_404" and session.calls == 1


def test_503_is_retried_then_recorded():
    session = Scripted(Response(503, b""))
    res = _fetch(session)
    assert res.reason == "http_503" and session.calls == 3  # make_config: 3 attempts


def test_503_then_success():
    res = _fetch(Scripted(Response(503, b""), Response(200, fixture("pen_801.html"))))
    assert res.ok and res.content_hash and res.data.startswith(b"<!DOCTYPE")


def test_timeout_reason():
    res = _fetch(Scripted(requests.exceptions.ReadTimeout("slow")))
    assert res.reason == "timeout"


# -- storage ---------------------------------------------------------------------


def test_store_refuses_a_failed_fetch(tmp_path):
    ctx = make_ctx(supp_config(), tmp_path)
    res = _fetch(Scripted(Response(200, fixture("captcha.html"))))
    with pytest.raises(SupplementaryError):
        ctx.store("enforcement").save("enf_804", res)


def test_captcha_is_never_stored_and_is_counted(tmp_path):
    ctx = make_ctx(supp_config(), tmp_path)
    targets = [{"item_key": "enf_801", "url": "https://x/?prid=801", "prid": 801},
               {"item_key": "enf_804", "url": "https://x/?prid=804", "prid": 804}]
    summary = fetch_items(ctx, "enforcement", targets, marker=MARKER)
    store = ctx.store("enforcement")
    assert summary["fetched"] == 1 and summary["failure_reasons"] == {"captcha": 1}
    assert sorted(store.manifest()) == ["enf_801"]
    assert not store.raw_path("enf_804").exists()
    assert [f["reason"] for f in store.failures()] == ["captcha"]
    assert list(store.failures()[0])[:4] == ["url", "reason", "http_status", "retrieved_at"]


def test_only_missing_never_refetches_or_overwrites_a_good_record(tmp_path):
    session = FakeSession()
    ctx = make_ctx(supp_config(), tmp_path, session)
    targets = [{"item_key": "enf_801", "url": "https://x/?prid=801", "prid": 801}]
    fetch_items(ctx, "enforcement", targets, marker=MARKER)
    before = ctx.store("enforcement").raw_path("enf_801").read_bytes()
    n = len(session.requests)
    ctx2 = make_ctx(supp_config(), tmp_path, FakeSession({"prid=801": (200, fixture("captcha.html"))}))
    summary = fetch_items(ctx2, "enforcement", targets, marker=MARKER)
    assert summary["already_stored"] == 1 and summary["attempted"] == 0
    assert ctx2.store("enforcement").raw_path("enf_801").read_bytes() == before
    assert len(session.requests) == n


def test_a_tampered_raw_page_is_refetched(tmp_path):
    ctx = make_ctx(supp_config(), tmp_path)
    targets = [{"item_key": "enf_801", "url": "https://x/?prid=801", "prid": 801}]
    fetch_items(ctx, "enforcement", targets, marker=MARKER)
    ctx.store("enforcement").raw_path("enf_801").write_bytes(b"truncated")
    fresh = make_ctx(supp_config(), tmp_path)
    assert not fresh.store("enforcement").has_good("enf_801")
    assert fetch_items(fresh, "enforcement", targets, marker=MARKER)["fetched"] == 1


def test_source_stops_at_half_failures(tmp_path):
    ctx = make_ctx(supp_config(), tmp_path, FakeSession({"prid=": (200, fixture("captcha.html"))}))
    targets = [{"item_key": f"enf_{i}", "url": f"https://x/?prid={i}", "prid": i} for i in range(30)]
    summary = fetch_items(ctx, "enforcement", targets, marker=MARKER)
    assert summary["stopped"] and summary["attempted"] == 10 and summary["failed"] == 10


def test_rate_limit_sleeps_between_requests(tmp_path):
    slept = []
    ctx = make_ctx(supp_config(), tmp_path)
    ctx.sleep_fn = slept.append
    for _ in range(3):
        ctx.get("https://x/?prid=801", marker=MARKER)
    assert slept == [1.5, 1.5]


# -- era, dates, config ------------------------------------------------------------


@pytest.mark.parametrize("d, era", [("2025-11-27", ERA_PRE), ("2025-11-28", ERA_POST), ("2026-01-01", ERA_POST),
                                    (None, ERA_UNKNOWN)])
def test_era_cutoff(d, era):
    assert era_of(d, date(2025, 11, 28)) == era


def test_era_cutoff_comes_from_config():
    assert SupplementaryConfig.from_cfg(supp_config()).era_cutoff == date(2025, 11, 28)


@pytest.mark.parametrize("raw, iso", [("Sep 24, 2026", "2026-09-24"), ("Date : Sept 4, 2026", "2026-09-04"),
                                      ("November 28, 2025", "2025-11-28"), ("no date", None), (None, None)])
def test_listing_dates(raw, iso):
    assert parse_listing_date(raw) == iso


def test_rate_limit_below_one_second_is_refused():
    cfg = supp_config()
    cfg["supplementary"]["rate_limit_sec"] = 0.5
    with pytest.raises(SupplementaryError, match="rate_limit_sec"):
        SupplementaryConfig.from_cfg(cfg)


def test_store_paths_are_repo_relative_posix(tmp_path):
    ctx = make_ctx(supp_config(), tmp_path)
    fetch_items(ctx, "enforcement", [{"item_key": "enf_801", "url": "https://x/?prid=801", "prid": 801}],
                marker=MARKER)
    entry = SourceStore(ctx.resolver, "enforcement").manifest()["enf_801"]
    assert entry["raw_path"] == "raw/enf_801.html"

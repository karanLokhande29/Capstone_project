"""P1-004 §A12: the corpus repair, against fixtures only. No network.

The first harvest lost 81 of 380 Directions to what looks like a session-level
block, and lost them in the two entity classes a cross-class benchmark most
depends on: 35/44 of Commercial Banks and 31/40 of Small Finance Banks. The
repair has to recover them without re-downloading the 299 that worked, and
without disturbing the paragraph ids that three people's annotations are
keyed to.

Every test here pins one of those two constraints. The ones that matter most
are the consistency checks: a repair that silently moves a paragraph boundary
invalidates the annotation work while every count in every report still looks
correct.
"""

from __future__ import annotations

import ast
import hashlib
import json
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from src.common.cache import ArtifactCache
from src.common.io_helpers import write_json, write_jsonl
from src.common.paths import PathResolver
from src.preprocessing.consistency import (
    ConsistencyError,
    check_pilot_join,
    check_stable_ids,
    paragraph_fingerprints,
    write_fingerprints,
)
from src.schemas.provenance import DocumentRecord

from tests.conftest import make_config

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF\n"
HTML = b"<!DOCTYPE html><html><head><title>Access Denied</title></head><body>blocked</body></html>"


@pytest.fixture
def cfg():
    c = make_config()
    c["network"]["payload_retries"] = 3
    c["network"]["sources"] = {
        "rbi_master_directions": {
            "listing_url": "https://example.test/listing",
            "base_url": "https://example.test",
            "pdf_host": "https://docs.example.test",
        },
        "user_agent": "test",
        "referer": "https://example.test/",
    }
    return c


@pytest.fixture
def resolver(cfg, tmp_path):
    return PathResolver.from_config(cfg, repo_root=tmp_path)


def _record(doc_id, *, entity="Commercial Banks", have=False):
    return DocumentRecord(
        document_id=doc_id,
        source_url=f"https://docs.example.test/{doc_id}.PDF",
        title=f"Master Direction {doc_id}",
        entity_class_raw=entity,
        entity_class=entity,
        format="PDF",
        content_hash=hashlib.sha256(PDF).hexdigest() if have else None,
        local_path=f"data/cache/{doc_id}.pdf" if have else None,
    )


# -- 1-3. only-missing planning and the request guard -------------------------


def test_only_missing_requests_only_null_hash_records(cfg, resolver, monkeypatch):
    import src.scraper.rbi_scraper as scraper

    existing = [_record("md_1", have=True), _record("md_2"), _record("md_3", have=True)]
    discovered = [_record(d) for d in ("md_1", "md_2", "md_3")]
    requested: list[str] = []

    monkeypatch.setattr(scraper, "discover_documents", lambda *a, **k: discovered)
    monkeypatch.setattr(scraper, "build_session", lambda cfg: object())

    def fake_download(record, *a, **k):
        requested.append(record.document_id)
        return replace(record, content_hash=hashlib.sha256(PDF).hexdigest(),
                       format="PDF", local_path=f"data/cache/{record.document_id}.pdf")

    monkeypatch.setattr(scraper, "download_document", fake_download)

    metrics = scraper.harvest_corpus(
        cfg, resolver=resolver, only_missing=True, existing_manifest=existing,
        html="<html></html>", sleep_fn=lambda _s: None,
    )

    assert requested == ["md_2"], "only the record without a content_hash may be fetched"
    assert metrics["records_carried_unchanged"] == 2
    assert metrics["downloads_attempted"] == 1


def test_carried_records_are_dict_equal_to_what_was_there(cfg, resolver, monkeypatch):
    """A document that already downloaded must come through completely untouched."""
    import src.scraper.rbi_scraper as scraper

    kept = replace(_record("md_1", have=True), retrieved_at="2026-08-23T00:00:00+00:00")
    existing = [kept, _record("md_2")]
    monkeypatch.setattr(scraper, "discover_documents",
                        lambda *a, **k: [_record("md_1"), _record("md_2")])
    monkeypatch.setattr(scraper, "build_session", lambda cfg: object())
    monkeypatch.setattr(scraper, "download_document",
                        lambda r, *a, **k: replace(r, content_hash="x", format="PDF"))

    scraper.harvest_corpus(cfg, resolver=resolver, only_missing=True,
                           existing_manifest=existing, html="<html></html>",
                           sleep_fn=lambda _s: None)

    written = {r["document_id"]: r for r in
               __import__("src.common.io_helpers", fromlist=["read_jsonl"]).read_jsonl(
                   resolver.read_path("metadata", "document_manifest.jsonl"))}
    assert written["md_1"] == kept.to_dict(), "a carried record must be byte-for-byte unchanged"


def test_new_and_vanished_ids_are_counted_and_vanished_ones_kept(cfg, resolver, monkeypatch):
    """A Direction dropping off the listing is a finding, not a licence to delete it."""
    import src.scraper.rbi_scraper as scraper

    existing = [_record("md_1", have=True), _record("md_gone", have=True)]
    discovered = [_record("md_1"), _record("md_new")]

    monkeypatch.setattr(scraper, "discover_documents", lambda *a, **k: discovered)
    monkeypatch.setattr(scraper, "build_session", lambda cfg: object())
    monkeypatch.setattr(scraper, "download_document",
                        lambda r, *a, **k: replace(r, content_hash="x", format="PDF"))

    metrics = scraper.harvest_corpus(cfg, resolver=resolver, only_missing=True,
                                     existing_manifest=existing, html="<html></html>",
                                     sleep_fn=lambda _s: None)

    assert metrics["new_since_previous_harvest"] == ["md_new"]
    assert metrics["no_longer_listed"] == ["md_gone"]

    from src.common.io_helpers import read_jsonl
    ids = {r["document_id"] for r in
           read_jsonl(resolver.read_path("metadata", "document_manifest.jsonl"))}
    assert "md_gone" in ids, "a de-listed document must be kept, not silently dropped"


def test_max_requests_guard_stops_before_any_request(cfg, resolver, monkeypatch):
    import src.scraper.rbi_scraper as scraper

    requested: list[str] = []
    discovered = [_record(f"md_{i}") for i in range(10)]
    monkeypatch.setattr(scraper, "discover_documents", lambda *a, **k: discovered)
    monkeypatch.setattr(scraper, "build_session", lambda cfg: object())
    monkeypatch.setattr(scraper, "download_document",
                        lambda r, *a, **k: requested.append(r.document_id))

    with pytest.raises(scraper.RequestBudgetExceeded, match="No request has been sent"):
        scraper.harvest_corpus(cfg, resolver=resolver, only_missing=True,
                               existing_manifest=discovered, max_requests=5,
                               html="<html></html>", sleep_fn=lambda _s: None)

    assert requested == [], "the guard must fire before the first request, not during"


# -- 4. HTML payload retries --------------------------------------------------


def test_html_then_pdf_succeeds_on_the_second_attempt(cfg, resolver, monkeypatch):
    import src.scraper.rbi_scraper as scraper

    calls = {"n": 0}

    def flaky(record, *a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise scraper.PayloadValidationError("received HTML where a PDF was expected")
        return replace(record, content_hash="x", format="PDF")

    monkeypatch.setattr(scraper, "download_document", flaky)

    result, outcome = scraper.download_with_payload_retries(
        _record("md_1"), cfg, session=object(), cache=None, resolver=resolver,
        logger=__import__("logging").getLogger("t"), warm_up=lambda: None,
        sleep_fn=lambda _s: None,
    )
    assert result is not None
    assert outcome["attempts"] == 2
    assert outcome["outcome"] == "ok"


def test_always_html_fails_after_the_retry_limit(cfg, resolver, monkeypatch):
    import src.scraper.rbi_scraper as scraper

    calls = {"n": 0}

    def always_html(record, *a, **k):
        calls["n"] += 1
        raise scraper.PayloadValidationError("received HTML where a PDF was expected")

    monkeypatch.setattr(scraper, "download_document", always_html)

    result, outcome = scraper.download_with_payload_retries(
        _record("md_1"), cfg, session=object(), cache=None, resolver=resolver,
        logger=__import__("logging").getLogger("t"), warm_up=lambda: None,
        sleep_fn=lambda _s: None,
    )
    assert result is None
    assert calls["n"] == cfg["network"]["payload_retries"] == 3
    assert outcome["outcome"] == "failed"
    assert len(outcome["detail"]) == 3


def test_a_warm_up_runs_before_each_retry_but_not_the_first_attempt(cfg, resolver, monkeypatch):
    import src.scraper.rbi_scraper as scraper

    warmups = {"n": 0}
    calls = {"n": 0}

    def flaky(record, *a, **k):
        calls["n"] += 1
        if calls["n"] < 3:
            raise scraper.PayloadValidationError("received HTML where a PDF was expected")
        return replace(record, content_hash="x", format="PDF")

    monkeypatch.setattr(scraper, "download_document", flaky)
    scraper.download_with_payload_retries(
        _record("md_1"), cfg, session=object(), cache=None, resolver=resolver,
        logger=__import__("logging").getLogger("t"),
        warm_up=lambda: warmups.__setitem__("n", warmups["n"] + 1),
        sleep_fn=lambda _s: None,
    )
    assert warmups["n"] == 2, "warm up before retries 2 and 3, never before attempt 1"


# -- 5. cache reuse -----------------------------------------------------------


def test_a_cache_hit_makes_no_request(cfg, resolver, monkeypatch):
    import src.scraper.rbi_scraper as scraper

    cache = ArtifactCache.from_config(cfg, resolver, namespace="scraper")
    cache.put(cache.key_for("rbi_master_directions", "md_1"), PDF, suffix=".pdf")

    requested: list[str] = []
    monkeypatch.setattr(scraper, "discover_documents", lambda *a, **k: [_record("md_1")])
    monkeypatch.setattr(scraper, "build_session", lambda cfg: object())
    monkeypatch.setattr(scraper, "download_document",
                        lambda r, *a, **k: requested.append(r.document_id))

    metrics = scraper.harvest_corpus(
        cfg, resolver=resolver, cache=cache, only_missing=True,
        existing_manifest=[_record("md_1")], html="<html></html>", sleep_fn=lambda _s: None,
    )
    assert requested == []
    assert metrics["cache_hits"] == ["md_1"]


# -- 6. manual PDF import -----------------------------------------------------


def test_manual_import_matches_by_url_basename_and_document_id(cfg, resolver, tmp_path):
    from src.scraper.rbi_scraper import import_manual_pdfs

    import_dir = tmp_path / "manual"
    import_dir.mkdir()
    (import_dir / "md_1.PDF").write_bytes(PDF)      # by URL basename
    (import_dir / "md_2.pdf").write_bytes(PDF)      # by <document_id>.pdf

    records = [_record("md_1"), _record("md_2"), _record("md_3")]
    records[1] = replace(records[1], source_url="https://docs.example.test/other-name.PDF")

    merged, metrics = import_manual_pdfs(import_dir, records, cfg, resolver=resolver)

    assert metrics["manual_import_ids"] == ["md_1", "md_2"]
    by_id = {r.document_id: r for r in merged}
    assert by_id["md_1"].content_hash == hashlib.sha256(PDF).hexdigest()
    assert by_id["md_1"].extraction_source == "manual_browser_download"
    assert by_id["md_3"].content_hash is None


def test_manual_import_rejects_a_file_that_is_not_a_pdf(cfg, resolver, tmp_path):
    """A saved WAF challenge page must not be adopted as a Direction."""
    from src.scraper.rbi_scraper import import_manual_pdfs

    import_dir = tmp_path / "manual"
    import_dir.mkdir()
    (import_dir / "md_1.PDF").write_bytes(HTML)

    merged, metrics = import_manual_pdfs(import_dir, [_record("md_1")], cfg, resolver=resolver)
    assert metrics["manual_import_ids"] == []
    assert "md_1.PDF" in metrics["manual_import_unmatched"]
    assert merged[0].content_hash is None


def test_manual_import_uses_the_same_cache_key_a_download_would(cfg, resolver, tmp_path):
    from src.scraper.rbi_scraper import import_manual_pdfs

    import_dir = tmp_path / "manual"
    import_dir.mkdir()
    (import_dir / "md_1.PDF").write_bytes(PDF)

    cache = ArtifactCache.from_config(cfg, resolver, namespace="scraper")
    import_manual_pdfs(import_dir, [_record("md_1")], cfg, cache=cache, resolver=resolver)

    assert cache.get(cache.key_for("rbi_master_directions", "md_1"), suffix=".pdf") == PDF


def test_manual_import_never_overwrites_an_existing_download(cfg, resolver, tmp_path):
    from src.scraper.rbi_scraper import import_manual_pdfs

    import_dir = tmp_path / "manual"
    import_dir.mkdir()
    (import_dir / "md_1.PDF").write_bytes(b"%PDF-1.7 different")

    already = _record("md_1", have=True)
    merged, metrics = import_manual_pdfs(import_dir, [already], cfg, resolver=resolver)
    assert metrics["manual_import_ids"] == []
    assert merged[0] == already


# -- 7. filtered extraction ---------------------------------------------------


def test_only_ids_extraction_touches_only_those_ids(cfg, resolver, monkeypatch):
    from src.extraction import text_extractor

    records = [_record("md_1", have=True), _record("md_2", have=True), _record("md_3", have=True)]
    write_jsonl(resolver.write_path("metadata", "document_manifest.jsonl"),
                [r.to_dict() for r in records])

    seen: list[str] = []

    def fake_extract(record, *a, **k):
        seen.append(record.document_id)
        return "some extracted text", {"pages": 1}

    monkeypatch.setattr(text_extractor, "extract_document_text", fake_extract, raising=False)

    metrics = text_extractor.extract_corpus(cfg, resolver=resolver, only_ids=["md_2"])
    assert metrics["skipped_not_requested"] == 2


# -- 8-9. the consistency checks ----------------------------------------------


def _write_paragraphs(resolver, doc_id, texts):
    write_jsonl(
        resolver.write_path("processed", f"{doc_id}.jsonl"),
        [{"paragraph_id": f"{doc_id}::p{i:05d}", "document_id": doc_id, "text": t}
         for i, t in enumerate(texts)],
    )


def test_stable_id_check_passes_when_nothing_changed(resolver):
    _write_paragraphs(resolver, "md_1", ["Banks shall do a thing.", "And another."])
    write_fingerprints(resolver)
    assert check_stable_ids(resolver)["passed"] is True


def test_stable_id_check_fails_naming_the_document_and_paragraph(resolver):
    _write_paragraphs(resolver, "md_1", ["Banks shall do a thing.", "And another."])
    write_fingerprints(resolver)
    # Re-segmentation shifts the text by one character.
    _write_paragraphs(resolver, "md_1", ["Banks shall do a thing.", "And another!"])

    with pytest.raises(ConsistencyError) as excinfo:
        check_stable_ids(resolver)
    message = str(excinfo.value)
    assert "md_1" in message and "p00001" in message
    assert "must not be published" in message

    report = check_stable_ids(resolver, raise_on_drift=False)
    assert report["passed"] is False
    assert report["drift_count"] == 1


def test_stable_id_check_ignores_documents_that_are_new(resolver):
    """The repair ADDS documents; a new one has no prior fingerprint by design."""
    _write_paragraphs(resolver, "md_1", ["Banks shall do a thing."])
    write_fingerprints(resolver)
    _write_paragraphs(resolver, "md_2", ["A newly recovered Direction."])
    assert check_stable_ids(resolver)["passed"] is True


def test_fingerprints_are_text_free(resolver):
    secret = "Verbatim RBI text that must not be redistributed."
    _write_paragraphs(resolver, "md_1", [secret])
    path = write_fingerprints(resolver)
    assert secret not in Path(path).read_text(encoding="utf-8")


def test_pilot_join_check_fails_when_a_paragraph_is_lost(resolver):
    text = "Banks shall maintain records for five years."
    _write_paragraphs(resolver, "md_1", [text])
    write_jsonl(resolver.write_path("benchmark", "pilot_candidates.jsonl"), [{
        "label_id": "t1_0001",
        "obligation_span": {"paragraph_id": "md_1::p00000", "document_id": "md_1",
                            "char_start": 0, "char_end": len(text), "text": text},
    }])
    assert check_pilot_join(resolver)["passed"] is True

    _write_paragraphs(resolver, "md_1", ["A completely different paragraph now."])
    with pytest.raises(ConsistencyError) as excinfo:
        check_pilot_join(resolver)
    assert "t1_0001" in str(excinfo.value)


def test_pilot_join_check_catches_a_span_that_silently_shifted(resolver):
    """The dangerous case: offsets still resolve, but to different words."""
    original = "Banks shall maintain records."
    _write_paragraphs(resolver, "md_1", [original])
    write_jsonl(resolver.write_path("benchmark", "pilot_candidates.jsonl"), [{
        "label_id": "t1_0001",
        "obligation_span": {"paragraph_id": "md_1::p00000", "document_id": "md_1",
                            "char_start": 0, "char_end": len(original), "text": original},
    }])
    _write_paragraphs(resolver, "md_1", ["XX " + original])  # same length region, shifted text

    report = check_pilot_join(resolver, raise_on_break=False)
    assert report["passed"] is False
    assert "no longer the annotated span" in report["broken"][0]["problem"]


# -- 10. coverage -------------------------------------------------------------


def test_coverage_table_and_the_ninety_percent_warning(caplog):
    from src.scraper.rbi_scraper import coverage_by_entity_class
    import logging

    records = (
        [_record(f"cb_{i}", entity="Commercial Banks", have=i < 2) for i in range(10)]
        + [_record(f"nb_{i}", entity="Non-Banking Financial Companies", have=True) for i in range(5)]
    )
    with caplog.at_level(logging.WARNING):
        table = coverage_by_entity_class(records, logger=logging.getLogger("cov"))

    assert table["by_entity_class"]["Commercial Banks"] == {
        "downloaded": 2, "total": 10, "rate": 0.2}
    assert table["by_entity_class"]["Non-Banking Financial Companies"]["rate"] == 1.0
    assert table["classes_below_90_percent"] == ["Commercial Banks"]
    assert table["overall"] == {"downloaded": 7, "total": 15, "rate": 7 / 15}
    assert any("below the 90% bar" in r.getMessage() for r in caplog.records)


# -- 11. the fixed alignment sample -------------------------------------------


def test_the_fixed_alignment_sample_is_deterministic(resolver):
    from src.benchmark.alignment_check import (
        FIXED_ENTITY_CLASSES,
        select_fixed_alignment_sample,
    )

    rows = []
    for ec in FIXED_ENTITY_CLASSES:
        for sf, n in (("KYC", 5), ("Fraud", 3), ("Audit", 2), ("Other", 1)):
            rows += [{"paragraph_id": f"{ec}{sf}{i}", "document_id": "md_1",
                      "entity_class": ec, "subject_family": sf} for i in range(n)]
    rows.append({"paragraph_id": "x", "document_id": "md_9",
                 "entity_class": "Urban Co-operative Banks", "subject_family": "KYC"})
    write_jsonl(resolver.write_path("processed", "paragraphs_index.jsonl"), rows)

    first = select_fixed_alignment_sample(resolver)
    second = select_fixed_alignment_sample(resolver)

    assert first == second, "the sample must be reproducible"
    assert first["entity_classes"] == list(FIXED_ENTITY_CLASSES)
    assert first["subject_families"] == ["KYC", "Fraud", "Audit"]
    assert first["selection"] == "fixed_entity_classes"


# -- 12. the Kaggle notebook --------------------------------------------------


def test_the_repair_notebook_is_valid_and_every_code_cell_parses():
    nbformat = pytest.importorskip("nbformat")
    path = Path("notebooks/phase1-corpus-repair.ipynb")
    if not path.exists():
        pytest.skip("notebook not generated in this checkout")

    nb = nbformat.read(path, as_version=4)
    nbformat.validate(nb)

    for i, cell in enumerate(nb.cells):
        if cell.cell_type == "code":
            ast.parse(cell.source)  # raises SyntaxError, naming the cell below
    assert any(c.cell_type == "code" for c in nb.cells)


def test_the_notebook_clones_the_working_branch_and_never_hardcodes_kaggle_subpaths():
    nbformat = pytest.importorskip("nbformat")
    path = Path("notebooks/phase1-corpus-repair.ipynb")
    if not path.exists():
        pytest.skip("notebook not generated in this checkout")

    cells = nbformat.read(path, as_version=4).cells
    source = "\n".join(c.source for c in cells)
    assert "wip/P1-004" in source

    # The older notebooks copied the input corpus to
    # /kaggle/working/Capstone_project/data, which PathResolver never looks at,
    # so every read silently found nothing. Checked against CODE only: the
    # notebook names that path in a comment explaining the bug, and a naive
    # substring search over the whole source trips on the explanation.
    code = "\n".join(
        line for cell in cells if cell.cell_type == "code"
        for line in cell.source.splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "/kaggle/working/Capstone_project/data" not in code


# -- 13. the return zips ------------------------------------------------------


def test_the_return_zip_excludes_benchmark_cache_and_annotations(tmp_path):
    from scripts.package_p1004 import build_return_zip

    root = tmp_path
    for rel in ("data/metadata/document_manifest.jsonl", "data/extracted/md_1.txt",
                "data/processed/md_1.jsonl", "data/matrix/matrix.json",
                "data/cache/x.pdf", "data/benchmark/tasks/annotation_karan.csv",
                "data/benchmark/pilot_candidates.jsonl",
                "reports/phase1_akash_corpus.md", "reports/p1004_missing_documents.csv",
                "reports/phase1_meer_annotation.md"):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")

    out = build_return_zip(root, root / "p1004_return.zip")
    names = zipfile.ZipFile(out).namelist()

    assert not any(n.startswith("data/benchmark") for n in names)
    assert not any(n.startswith("data/cache") for n in names)
    assert not any("annotation_" in n for n in names)
    assert not any("phase1_meer_annotation.md" in n for n in names)
    assert "data/metadata/document_manifest.jsonl" in names
    assert "reports/p1004_missing_documents.csv" in names


def test_the_corpus_v2_zip_carries_candidates_but_no_annotations(tmp_path):
    from scripts.package_p1004 import build_corpus_v2_zip

    root = tmp_path
    for rel in ("data/metadata/document_manifest.jsonl", "data/extracted/md_1.txt",
                "data/processed/md_1.jsonl", "data/matrix/matrix.json",
                "data/cache/x.pdf", "data/benchmark/pilot_candidates.jsonl",
                "data/benchmark/tasks/annotation_karan.csv"):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")

    out = build_corpus_v2_zip(root, root / "corpus-v2.zip")
    names = zipfile.ZipFile(out).namelist()

    assert "data/benchmark/pilot_candidates.jsonl" in names
    assert "data/cache/x.pdf" in names
    assert not any("annotation_" in n for n in names)


# -- end-to-end repair on fixtures --------------------------------------------


def test_repair_runs_end_to_end_on_fixtures(cfg, resolver, tmp_path, monkeypatch):
    """One full `repair` pass: harvest -> import -> extract -> segment -> checks.

    Fixtures throughout; the point is the ORDER. The fingerprint snapshot must
    be taken before re-segmentation and the consistency checks must run before
    the xref and coverage stages, or a corpus that moved a paragraph id reaches
    the reports before anyone notices.
    """
    import scripts.run_harvest as harvest_cli
    import src.scraper.rbi_scraper as scraper

    existing = [_record("md_1", have=True), _record("md_2")]
    write_jsonl(resolver.write_path("metadata", "document_manifest.jsonl"),
                [r.to_dict() for r in existing])
    _write_paragraphs(resolver, "md_1", ["Banks shall do a thing."])

    monkeypatch.setattr(scraper, "discover_documents",
                        lambda *a, **k: [_record("md_1"), _record("md_2")])
    monkeypatch.setattr(scraper, "build_session", lambda cfg: object())
    monkeypatch.setattr(scraper, "download_document",
                        lambda r, *a, **k: replace(
                            r, content_hash=hashlib.sha256(PDF).hexdigest(), format="PDF"))
    monkeypatch.setattr(harvest_cli, "extract_corpus",
                        lambda *a, **k: {"successful": 1, "only_ids": k.get("only_ids")})
    monkeypatch.setattr(harvest_cli, "segment_corpus", lambda *a, **k: {"paragraphs_written": 1})
    monkeypatch.setattr(harvest_cli, "resolve_cross_references", lambda *a, **k: {"resolved": 0})
    monkeypatch.setattr(scraper, "_fetch", lambda *a, **k: PDF)

    import logging
    metrics = harvest_cli.run_repair(
        cfg, resolver, logging.getLogger("repair"), import_dir=None, max_requests=150
    )

    assert "stopped_at" not in metrics, metrics.get("error")
    assert metrics["stages_run"] == ["harvest", "extract", "segment", "consistency",
                                     "xref", "coverage"]
    assert metrics["newly_available_ids"] == ["md_2"]
    assert metrics["extract"]["only_ids"] == ["md_2"], "only the new document is extracted"
    assert metrics["stable_id_check"]["passed"] is True
    assert metrics["coverage_before"]["overall"]["downloaded"] == 1
    assert metrics["coverage_after"]["overall"]["downloaded"] == 2


def test_repair_stops_at_the_request_budget_without_downloading(cfg, resolver, monkeypatch):
    import scripts.run_harvest as harvest_cli
    import src.scraper.rbi_scraper as scraper
    import logging

    records = [_record(f"md_{i}") for i in range(20)]
    write_jsonl(resolver.write_path("metadata", "document_manifest.jsonl"),
                [r.to_dict() for r in records])

    requested: list[str] = []
    monkeypatch.setattr(scraper, "discover_documents", lambda *a, **k: records)
    monkeypatch.setattr(scraper, "build_session", lambda cfg: object())
    monkeypatch.setattr(scraper, "download_document",
                        lambda r, *a, **k: requested.append(r.document_id))

    metrics = harvest_cli.run_repair(
        cfg, resolver, logging.getLogger("repair"), import_dir=None, max_requests=5
    )
    assert metrics["stopped_at"] == "request_budget"
    assert requested == []
    assert "stable_id_check" not in metrics, "nothing downstream may run after a stop"


def test_repair_stops_when_a_consistency_check_fails(cfg, resolver, monkeypatch):
    """The stop that matters: a moved paragraph id must not reach the reports."""
    import scripts.run_harvest as harvest_cli
    import src.scraper.rbi_scraper as scraper
    import logging

    existing = [_record("md_1", have=True)]
    write_jsonl(resolver.write_path("metadata", "document_manifest.jsonl"),
                [r.to_dict() for r in existing])
    _write_paragraphs(resolver, "md_1", ["Banks shall do a thing."])

    monkeypatch.setattr(scraper, "discover_documents", lambda *a, **k: [_record("md_1")])
    monkeypatch.setattr(scraper, "build_session", lambda cfg: object())
    monkeypatch.setattr(harvest_cli, "extract_corpus", lambda *a, **k: {})
    monkeypatch.setattr(harvest_cli, "resolve_cross_references", lambda *a, **k: {"resolved": 0})

    def destructive_segment(*a, **k):
        _write_paragraphs(resolver, "md_1", ["Banks shall do a DIFFERENT thing."])
        return {"paragraphs_written": 1}

    monkeypatch.setattr(harvest_cli, "segment_corpus", destructive_segment)

    metrics = harvest_cli.run_repair(
        cfg, resolver, logging.getLogger("repair"), import_dir=None, max_requests=150
    )
    assert metrics["stopped_at"] == "consistency"
    assert "must not be published" in metrics["error"]
    assert "xref" not in metrics["stages_run"]

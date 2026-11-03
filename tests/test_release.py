"""P5-001 task 6: build-tables determinism, the RBI-text run detector, the release check, offline rehydration,
pseudonymisation and the README / CITATION links. Fixtures use invented text only."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import re
import zipfile
from pathlib import Path

import pytest

from src.release import check as C
from src.release import pseudonym as PS
from src.release.rbi_text import CorpusIndex, copied_runs, shorten, shorten_copied_runs
from src.release.rebuild import span_text

ROOT = Path(__file__).resolve().parents[1]

# 60 invented words standing in for a corpus paragraph.
CORPUS = ("the lender shall keep a register of every pledged asset and shall report the balance to the board each quarter "
          "unless the supervisor grants an exemption in writing after reviewing the audit trail the register must record "
          "the date of pledge the valuation method the custodian and the release date for each asset without exception "
          "and shall be retained for eight years")
W = CORPUS.split()


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def index() -> CorpusIndex:
    return CorpusIndex.from_texts([CORPUS])


# -- RBI-text run detector -------------------------------------------------------------------------------------


def test_thirty_copied_words_are_flagged(index):
    text = "Intro words here. " + " ".join(W[5:35]) + " and then our own commentary follows."
    runs = copied_runs(text, index)
    assert len(runs) == 1 and runs[0].length == 30


def test_twenty_nine_copied_words_are_allowed(index):
    assert copied_runs("Our note: " + " ".join(W[5:34]) + ", end.", index) == []


def test_short_quote_with_paragraph_id_is_allowed(index):
    quote = shorten(CORPUS, 25)
    assert copied_runs(f"As md_1::p00001 puts it: “{quote}”", index) == []
    assert quote.endswith("…") and len(quote.split()) == 26


def test_two_short_quotes_separated_by_own_words_are_allowed(index):
    text = " ".join(W[0:20]) + " — in other words, and quite separately — " + " ".join(W[30:50])
    assert copied_runs(text, index) == []


def test_case_and_punctuation_do_not_hide_a_copy(index):
    text = " ".join(w.upper() + "," for w in W[0:31])
    assert copied_runs(text, index)[0].length == 31


def test_shorten_copied_runs_cuts_to_25_words(index):
    text = "Answer: " + " ".join(W[0:40]) + ". Our conclusion."
    out, cuts = shorten_copied_runs(text, index)
    assert copied_runs(out, index) == []
    assert "[…]" in out and out.endswith("Our conclusion.")
    assert cuts == [{"run_words": 40, "kept_words": 25, "removed_words": 15, "locator": " ".join(W[0:12])}]


# -- release check: one fixture per failure type ------------------------------------------------------------------


def _f(path: str, data: bytes, size: int | None = None):
    return (path, len(data) if size is None else size, lambda: data)


def _kinds(problems):
    return {(p.path, p.kind) for p in problems}


@pytest.mark.parametrize("path", [
    ".env", "data/processed/md_1.jsonl", "data/rag_runs/t1/x.json", "data/llm_cache/k.json", "data/indexes/emb.npy",
    "data/raw_pages/a.html", "data/supplementary/faq/items_v1.jsonl", "docs/a.pdf", "data/benchmark/t1/annotation_x.csv",
    "data/benchmark/t1/p2004_key_v1.json", "data/benchmark/x_mock.csv", "data/benchmark/t1/not_independent/a.csv",
    "p4001_backups/b.zip", "external/RePASs/README.md", "reports/private/rater_map.json", "data/indexes/.gitkeep"])
def test_excluded_paths_fail(index, path):
    assert _kinds(C.scan([_f(path, b"nothing")], index, [])) == {(path, "excluded")}


@pytest.mark.parametrize("path", [".env.example", "data/benchmark/templates/annotation_task_template.csv", "data/raw/.gitkeep",
                                  "reports/phase1_annotation_ingest_metrics.json"])
def test_allowed_paths_pass(index, path):
    data = b"" if path.endswith(".gitkeep") else b"GEMINI_API_KEY=\n"
    assert C.scan([_f(path, data)], index, []) == []


def test_key_like_strings_fail(index):
    gem = ("AIza" + "Q" * 35).encode()
    groq = ("gsk_" + "b" * 40).encode()
    assert _kinds(C.scan([_f("a.md", b"key " + gem), _f("b.json", groq)], index, [])) == {("a.md", "key"), ("b.json", "key")}


def test_file_over_50_mb_fails_without_being_read(index):
    def boom():
        raise AssertionError("must not read")
    assert _kinds(C.scan([("big.jsonl", C.MAX_BYTES + 1, boom)], index, [])) == {("big.jsonl", "size")}


def test_copied_corpus_text_fails(index):
    text = ("Report text. " + " ".join(W[0:35])).encode()
    assert _kinds(C.scan([_f("reports/x.md", text)], index, [])) == {("reports/x.md", "rbi_text")}


def test_copied_text_inside_an_office_file_fails(index):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", "<w:t>" + " ".join(W[0:33]) + "</w:t>")
    assert _kinds(C.scan([_f("docs/slides.docx", buf.getvalue())], index, [])) == {("docs/slides.docx", "rbi_text")}


def test_a_run_inside_a_direction_title_is_allowed(index):
    title = " ".join(W[0:34])
    assert C.scan([_f("data/metadata/document_manifest.jsonl", json.dumps({"title": title}).encode())], index, [title]) == []


# -- rebuild rule and offline rehydration -------------------------------------------------------------------------


def test_span_text_rule():
    assert span_text("ab  cd\nef gh", [[0, 6], [7, 12]]) == "ab cd … ef gh"


def _sha(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


def test_rehydrate_offline_matched_drifted_missing(tmp_path, capsys):
    rel, proc = tmp_path / "release", tmp_path / "processed"
    (rel / "data" / "t1").mkdir(parents=True)
    proc.mkdir()
    texts = {"md_1::p00000": "First invented paragraph.", "md_1::p00001": "Second invented paragraph text.",
             "md_1::p00002": "Third one, not produced any more."}
    (rel / "data" / "documents.jsonl").write_text(json.dumps({"md_id": "md_1", "source_url": "https://example.invalid/a.pdf"}) + "\n")
    (rel / "data" / "paragraphs.jsonl").write_text("".join(
        json.dumps({"paragraph_id": k, "md_id": "md_1", "text_sha256": _sha(v)}) + "\n" for k, v in texts.items()))
    (rel / "data" / "t1" / "validated.jsonl").write_text(json.dumps(
        {"item_id": "t1_md_1::p00001", "md_id": "md_1", "obligation_span": {
            "paragraph_id": "md_1::p00001", "units": [[0, 6]], "rule": "span_text", "text_sha256": _sha("Second")}}) + "\n")
    # the corpus now: p00000 unchanged, p00001 edited by RBI, p00002 gone
    (proc / "md_1.jsonl").write_text(json.dumps({"paragraph_id": "md_1::p00000", "text": texts["md_1::p00000"]}) + "\n"
                                     + json.dumps({"paragraph_id": "md_1::p00001", "text": "Second paragraph, amended."}) + "\n")
    rh = _load("rehydrate_under_test", "scripts/rehydrate.py")
    assert rh.main(["--release", str(rel), "--offline", str(proc), "--json"]) == 0
    s = json.loads(capsys.readouterr().out)
    assert (s["matched"], s["drifted"], s["missing"]) == (1, 1, 1)
    assert s["derived_texts"] == {"skipped (a source paragraph did not match)": 1}
    # once the paragraph matches again, the span is rebuilt and its hash checks
    (proc / "md_1.jsonl").write_text("".join(json.dumps({"paragraph_id": k, "text": v}) + "\n" for k, v in texts.items()))
    assert rh.main(["--release", str(rel), "--offline", str(proc), "--json", "--out", str(tmp_path / "out")]) == 0
    s = json.loads(capsys.readouterr().out)
    assert (s["matched"], s["drifted"], s["missing"]) == (3, 0, 0) and s["derived_texts"] == {"rebuilt": 1}
    assert json.loads((tmp_path / "out" / "t1_spans.jsonl").read_text())["text"] == "Second"


# -- pseudonymisation ---------------------------------------------------------------------------------------------


def test_pseudonymisation_leaks_no_names():
    mapping = {"alice": "rater_1", "bob": "rater_2"}
    obj = {"provenance": "annotator:alice:single-pass", "raters": {"Alice": ["pass1"], "bob": ["irr"]},
           "note": "Bob's file annotation_p2004_bob.csv; declared by ALICE", "pairwise": {"alice__vs__bob": 0.5}}
    out = json.dumps(PS.pseudonymise_value(obj, mapping))
    assert not PS.name_pattern(mapping).search(out)
    assert "annotator:rater_1:single-pass" in out and "annotation_p2004_rater_2.csv" in out and "rater_1__vs__rater_2" in out


def test_names_inside_other_words_are_left_alone():
    assert PS.pseudonymise_text("Alicexyz and malice", {"alice": "rater_1"}) == "Alicexyz and malice"


def test_released_files_hold_no_rater_names():
    mapping, others = PS.load_map()
    if not mapping or not (ROOT / "release" / "data").is_dir():
        pytest.skip("needs the private rater map and a built release/")
    pat = PS.name_pattern(mapping, others)
    # LICENSE-DATA names the copyright holder (the author) by design; everything else must hold no name.
    hits = [str(p.relative_to(ROOT)) for p in sorted((ROOT / "release").rglob("*"))
            if p.is_file() and p.name != "LICENSE-DATA" and pat.search(p.read_text(encoding="utf-8", errors="replace"))]
    assert hits == []


# -- build_tables determinism -------------------------------------------------------------------------------------


def test_build_tables_is_deterministic_and_matches_disk():
    bt = _load("build_tables_under_test", "scripts/build_tables.py")
    try:
        r1, m1 = bt.build()
    except bt.MissingSource as exc:
        pytest.skip(str(exc))
    r2, m2 = bt.build()
    assert json.dumps(r1) == json.dumps(r2) and m1 == m2
    on_disk = ROOT / "reports" / "results_v1.json"
    if on_disk.exists():
        assert on_disk.read_text(encoding="utf-8") == json.dumps(r1, indent=1, ensure_ascii=False) + "\n"
        for k, v in m1.items():
            assert (ROOT / "reports" / "tables" / f"{k}.md").read_text(encoding="utf-8") == v


def test_every_table_ci_label_follows_the_strict_rule():
    for f in sorted((ROOT / "reports" / "tables").glob("*.md")):
        for lo, hi, lab in re.findall(r"\[([+-]?\d+\.\d+), ([+-]?\d+\.\d+)\] \((excludes 0 \((?:above|below)\)|does not exclude 0)\)",
                                      f.read_text(encoding="utf-8")):
            lo, hi = float(lo), float(hi)
            want = "excludes 0 (above)" if lo > 0 else "excludes 0 (below)" if hi < 0 else "does not exclude 0"
            assert lab == want, (f.name, lo, hi, lab)


# -- README / CITATION / card links -------------------------------------------------------------------------------


def _local_links(md: Path) -> list[str]:
    links = re.findall(r"\]\(([^)\s]+)\)", md.read_text(encoding="utf-8"))
    return [x.split("#")[0] for x in links if not re.match(r"[a-z]+://|#|mailto:", x)]


@pytest.mark.parametrize("doc", ["README.md", "NOTICE.md", "release/DATASET_CARD.md"])
def test_markdown_links_resolve(doc):
    p = ROOT / doc
    if not p.exists():
        pytest.skip(f"{doc} not built")
    missing = [x for x in _local_links(p) if not (p.parent / x).exists()]
    assert missing == []


def test_citation_cff_is_complete_and_its_files_exist():
    text = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    assert "cff-version: 1.2.0" in text and "family-names: Lokhande" in text and "given-names: Karan" in text
    assert re.search(r"^license: MIT$", text, re.M) and re.search(r"^repository-code: ", text, re.M)
    for f in ("LICENSE", "NOTICE.md", "release/LICENSE-DATA", "README.md"):
        assert (ROOT / f).is_file(), f
    assert "covers ONLY the annotations" in (ROOT / "release" / "LICENSE-DATA").read_text(encoding="utf-8")


def test_shorten_words_counts_like_the_copied_text_check():
    from src.release.rbi_text import shorten_words, words

    text = "9. A CIC intending to outsource its IT services shall put in place a comprehensive Board-approved IT outsourcing policy, the coverage of which is indicated in paragraph 15."
    out = shorten_words(text, 25)
    assert len(words(out.rstrip(" …"))) <= 25 and out.endswith("…")
    assert shorten_words("short text", 25) == "short text"

"""P2-003 §U: end to end on fixtures, from a mocked discover through score. No network.

3 FAQ topics, 4 penalty releases (one answered with a CAPTCHA page), 2 amendments, 1 repeal annex (plus
one repeal statement) in a six-Direction corpus.
"""

from __future__ import annotations

import ast
import csv
import json
import shutil
import zipfile
from pathlib import Path

import pytest

from scripts import run_supplementary as R
from src.common.io_helpers import read_json, read_jsonl
from src.supplementary import alignment as AL
from src.supplementary.common import SupplementaryConfig, SupplementaryError
from tests.supplementary_support import FakeSession, make_ctx, supp_config, write_corpus


@pytest.fixture()
def world(tmp_path):
    write_corpus(tmp_path)
    cfg = supp_config()
    ctx = make_ctx(cfg, tmp_path, FakeSession())
    return {"root": tmp_path, "cfg": cfg, "sc": SupplementaryConfig.from_cfg(cfg), "ctx": ctx,
            "resolver": ctx.resolver, "logger": ctx.logger}


def _harvest(w):
    ctx = w["ctx"]
    disc = R.run_discover(ctx, R.SOURCES)
    smoke = R.smoke(ctx, disc)
    fetch = R.run_fetch(ctx, R.SOURCES)
    parse = R.run_parse(ctx, R.SOURCES)
    audit = R.audit_stored(ctx, R.SOURCES)
    return disc, smoke, fetch, parse, audit


def test_end_to_end(world):
    w = world
    ctx, root = w["ctx"], w["root"]
    pre = R.preflight(w["sc"], *R.load_corpus(w["resolver"]))
    assert pre["passed"] and pre["directions"] == 6

    disc, smoke, fetch, parse, audit = _harvest(w)
    assert {s: d["discovered"] for s, d in disc.items()} == {"faq": 3, "enforcement": 4, "amendment": 2,
                                                              "withdrawn": 3}
    assert disc["enforcement"]["near_miss_by_pattern"]["cancels_registration"] == 1
    assert disc["amendment"]["amendment_directions_before_cutoff_excluded"] == 1
    assert smoke["ok"], smoke["stops"]
    assert smoke["per_source"]["enforcement"]["failure_reasons"] == {"captcha": 1}
    # The CAPTCHA is logged, never stored; the full fetch does not retry it into the store either.
    assert all(a["invalid_content"] == 0 and a["hash_mismatch"] == 0 for a in audit.values())
    assert audit["enforcement"]["stored"] == 3
    assert not ctx.store("enforcement").raw_path("enf_804").exists()
    assert fetch["faq"]["already_stored"] == 3 and fetch["faq"]["attempted"] == 0  # only-missing after smoke
    assert parse["faq"]["items"] == 8 and parse["enforcement"]["items"] == 3 and parse["amendment"]["items"] == 2

    harvest = R.harvest_metrics(ctx, R.SOURCES, parse)
    assert harvest["enforcement"]["failure_reasons"]["captcha"] >= 1
    assert harvest["enforcement"]["entity_class_resolution_rate"] == 1.0
    assert harvest["enforcement"]["releases_citing_statute_only"] == 1
    assert harvest["withdrawn"]["online_list_found"] is True

    # Return trip: zip, wipe, ingest.
    zpath = R.write_return_zip(ctx, root / R.RETURN_ZIP, {"harvest": harvest})
    names = zipfile.ZipFile(zpath).namelist()
    assert "p2003_metrics_v1.json" in names and "faq/raw/faq_topic_0901.html" in names
    assert not any("annotation_" in n for n in names)
    shutil.rmtree(root / "data" / "supplementary")
    ing = R.run_ingest(w["cfg"], w["sc"], w["resolver"], w["logger"], str(zpath))
    assert ing["reparse_identical_to_kaggle"] == {"faq": True, "enforcement": True, "amendment": True}
    assert ing["harvest"]["withdrawn"]["items"] == 3 + 2 + 1  # online rows + annex entries + statement

    # Link (twice: byte for byte).
    link = R.run_link(w["cfg"], w["sc"], w["resolver"], w["logger"])
    links_path = root / "data" / "supplementary" / R.LINKS_FILE
    first = links_path.read_bytes()
    R.run_link(w["cfg"], w["sc"], w["resolver"], w["logger"])
    assert links_path.read_bytes() == first
    cov = link["coverage"]
    assert cov["amendment"]["exact_ref"] == 2
    # 803 cites only a statute; 802 is an NBFC and the fixture corpus has no NBFC Direction (no cross-class fallback).
    assert cov["enforcement"]["items"] == 3 and cov["enforcement"]["none"] == 2
    recs = read_jsonl(links_path)
    enf801 = [r for r in recs if r["item_id"] == "enf_801"]
    assert {(r["cited_string"], r["md_id"], r["method"]) for r in enf801} == {
        ("Know Your Customer (KYC)", "md_90003", "title_fuzzy"),
        ("Management of Advances – UCBs", "md_90006", "repeal_map")}
    assert all("\\" not in json.dumps(r, ensure_ascii=False) for r in recs)  # no Windows paths
    assert link["enforcement_quoted_titles"]["pre_consolidation"] == 1  # 'Management of Advances – UCBs'

    # Rule, then the sheet (blind), then Karan's labels, then score.
    R.run_rule(w["cfg"], w["sc"], w["resolver"], w["logger"])
    sheet = R.run_sheet(w["cfg"], w["sc"], w["resolver"], w["logger"])
    d = root / "data" / "supplementary"
    assert sheet["n"] == {"faq": 3, "enforcement": 3} and sheet["faq"]["shortfall"] == 1  # 3 of 8 FAQ items qualify
    assert sum(sheet["candidate_pools"].values()) == 6 and sheet["candidate_pools"]["class_corpus"] >= 1
    assert read_json(d / AL.DRAW_LOG_FILE)["drawn_at"] > read_json(d / AL.RULE_FILE)["created_at"]
    with pytest.raises(SupplementaryError):
        R.run_rule(w["cfg"], w["sc"], w["resolver"], w["logger"], force=True)
    with pytest.raises(SupplementaryError, match="blank label"):
        R.run_score(w["cfg"], w["sc"], w["resolver"], w["logger"], str(d / AL.SHEET_FILE))

    key = read_json(d / AL.KEY_FILE)
    rows = AL.read_sheet(d / AL.SHEET_FILE)
    completed = d / AL.COMPLETED_FILE
    with completed.open("w", encoding="utf-8-sig", newline="") as fh:  # as Excel saves it
        fh.write('"' + AL.HEADER_NOTE + '",,,,,,,\n')
        wr = csv.DictWriter(fh, fieldnames=AL.SHEET_COLUMNS)
        wr.writeheader()
        for r in rows:
            k = key["items"][r["item_id"]]
            if k["candidates"]:
                wr.writerow({**r, "label": "paragraph", "paragraph_ids": k["shown_order"][0]})
            else:
                wr.writerow({**r, "label": "unanchored"})
    out = R.run_score(w["cfg"], w["sc"], w["resolver"], w["logger"], None, 18.0, None, "manual", "recalled_estimate")
    assert set(out["decisions"]) == {"faq", "enforcement"}
    assert out["minutes_source"] == "recalled_estimate"
    ps = out["post_stratified"]
    assert set(ps) == {"faq", "enforcement"} and ps["enforcement"]["population_total"] == 3  # 801, 802, 803 are post-cutoff
    assert ps["faq"]["weighted_clean_rate"] is not None
    for dec in out["decisions"].values():
        assert dec["decision"] in (AL.DECISION_PARAGRAPH, AL.DECISION_DIRECTION, AL.DECISION_VALIDATION)
        assert dec["rule_sha256"] == key["meta"]["rule_sha256"]
    assert out["minutes_per_item"] == 3.0  # 18 minutes over 6 items
    report = (root / "reports" / R.REPORT_FILE).read_text(encoding="utf-8")
    assert "NOT YET MEASURED" in report and "Wilson" in report and "Decision under the pre-registered rule" in report
    assert "source: recalled_estimate" in report and "Sensitivity: post-stratified clean rate" in report
    for section in ("## Harvest", "## Direction-level link coverage", "### By stratum", "## Provenance", "## Limitations"):
        assert section in report
    assert "Candidate-hit share by candidate pool" in report and "| class_corpus |" in report
    assert "Scoring conventions" in report and out["conventions"]["enforcement_charges_none_parsed"]["n"] == 3
    decisions = read_json(d / AL.DECISIONS_FILE)["decisions"]
    assert {x["source"] for x in decisions} == {"faq", "enforcement"}

    # Score again: byte for byte.
    before = {p: (d / p).read_bytes() for p in (AL.DECISIONS_FILE, AL.SCORE_FILE)}
    rep = (root / "reports" / R.REPORT_FILE).read_bytes()
    R.run_score(w["cfg"], w["sc"], w["resolver"], w["logger"], None, 18.0, None, "manual", "recalled_estimate")
    assert {p: (d / p).read_bytes() for p in before} == before
    assert (root / "reports" / R.REPORT_FILE).read_bytes() == rep


def test_discovery_zero_items_stops_the_smoke(world):
    w = world
    ctx = make_ctx(w["cfg"], w["root"], FakeSession({"WithdrawnCircular": (200, b"<html><body>no list</body></html>")}))
    disc = R.run_discover(ctx, R.SOURCES)
    smoke = R.smoke(ctx, disc)
    assert not smoke["ok"] and any(s.startswith("withdrawn: discovered 0") for s in smoke["stops"])


def test_smoke_stops_on_half_failures(world):
    w = world
    captcha = (200, (Path(__file__).parent / "fixtures" / "supplementary" / "captcha.html").read_bytes())
    ctx = make_ctx(w["cfg"], w["root"], FakeSession({"FAQDisplay.aspx?Id=": captcha}))
    smoke = R.smoke(ctx, R.run_discover(ctx, R.SOURCES))
    assert not smoke["ok"] and any(s.startswith("faq: smoke failure rate 100%") for s in smoke["stops"])


def test_preflight_stops_on_a_different_corpus(world):
    cfg = supp_config()
    cfg["supplementary"]["expected_corpus"]["paragraphs"] = 76188
    sc = SupplementaryConfig.from_cfg(cfg)
    with pytest.raises(SupplementaryError, match="A1 preflight failed"):
        R.preflight(sc, *R.load_corpus(world["resolver"]))


def test_real_config_preflight_values():
    import yaml

    exp = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "config.yaml").read_text())[
        "supplementary"]["expected_corpus"]
    assert (exp["directions"], exp["paragraphs"], exp["raw_entity_classes"]) == (381, 76188, 19)


def test_notebook_cells_parse_and_follow_the_pattern(tmp_path):
    from scripts.build_supplementary_notebook import CODE_CELLS, build

    nb = json.loads(build(tmp_path / "nb.ipynb").read_text(encoding="utf-8"))
    code = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
    assert len(code) == len(CODE_CELLS)
    for src in code:
        ast.parse(src)
    text = "\n".join(code)
    assert "p2003_code.zip" in text and "MANIFEST.json" in text and "R.smoke(" in text
    assert "raise SystemExit" in text and "annotation_" in text
    md = "\n".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "markdown")
    assert "\\n" not in md


def test_code_zip_has_code_and_no_data(tmp_path):
    info = R.build_code_zip(Path(__file__).resolve().parents[1], tmp_path)
    names = zipfile.ZipFile(tmp_path / R.CODE_ZIP).namelist()
    assert "src/supplementary/faq.py" in names and "scripts/run_supplementary.py" in names
    assert "config/config.yaml" in names and "MANIFEST.json" in names
    assert not any(n.startswith("data/") or n.startswith("tests/") for n in names)
    manifest = json.loads(zipfile.ZipFile(tmp_path / R.CODE_ZIP).read("MANIFEST.json"))
    assert manifest["prompt"] == "P2-003" and len(manifest["files"]) == info["files"]

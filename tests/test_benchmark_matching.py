"""P2-002 §T unit tests and §U integration test, with a deterministic fake embedder.

No model is ever downloaded: every embedding here comes from
:class:`src.benchmark.matching.FakeEmbedder`.
"""

from __future__ import annotations

import ast
import csv
import json
import zipfile
from pathlib import Path

import numpy as np
import pytest
import yaml

from src.benchmark import matching as M
from src.benchmark.candidates import build_candidate
from src.common.io_helpers import read_json, read_jsonl, write_jsonl
from src.common.paths import PathResolver
from tests.conftest import make_config

REPO = Path(__file__).resolve().parents[1]

CB, SFB, PB, FM = "Commercial Banks", "Small Finance Banks", "Payments Banks", "Financial Market"
F1, F2 = "Know Your Customer", "Credit Facilities"


def matching_block(**over) -> dict:
    block = yaml.safe_load((REPO / "config" / "config.yaml").read_text(encoding="utf-8"))["matching"]
    block = json.loads(json.dumps(block))
    block.update(over)
    return block


def mc_for(core, function, kept, raw, **over) -> M.MatchingConfig:
    return M.MatchingConfig.from_cfg({"matching": matching_block(
        core_entity_classes=list(core), function_headings=list(function),
        expected_kept_candidates=kept, expected_raw_entity_classes=raw, **over)})


def cand(pid: str, text: str, cls: str):
    return build_candidate({"paragraph_id": pid, "document_id": pid.split("::")[0], "text": text},
                           entity_class=cls, matrix_cell=None)


# -- A2 units ------------------------------------------------------------------


def test_units_take_only_kept_cues_with_correct_offsets():
    mc = mc_for([CB], [], 1, 1)
    text = ('"Bank" shall mean a banking company as defined in the Act. '
            "Every bank shall maintain a register of complaints for eight years; the register must be "
            "reviewed by the board every quarter. " + "Further context follows here. " * 12)
    c = cand("md_a::p00001", text, CB)
    assert c.cue_exclusions[0] is not None and c.cue_exclusions[1] is None
    spans = M.unit_spans(c, mc.whole_paragraph_max_chars)
    assert spans, "kept cues produce units"
    for s, e in spans:
        assert text[s:e] == text[s:e].strip()
        assert "shall mean" not in text[s:e], "an excluded cue's sentence is never a unit"
    assert any("shall maintain a register" in text[s:e] for s, e in spans)


def test_short_single_cue_paragraph_is_one_whole_unit():
    mc = mc_for([CB], [], 1, 1)
    c = cand("md_a::p00002", "(ii) Every bank shall maintain a register of complaints.", CB)
    assert M.unit_spans(c, mc.whole_paragraph_max_chars) == [(0, len(c.span_text))]


def test_multi_cue_units_are_sentence_level_and_merged_when_overlapping():
    mc = mc_for([CB], [], 1, 1)
    text = "The bank shall report and must disclose it. Other text. The bank shall also retain records."
    c = cand("md_a::p00003", text, CB)
    spans = M.unit_spans(c, mc.whole_paragraph_max_chars)
    assert [text[s:e] for s, e in spans] == [
        "The bank shall report and must disclose it.", "The bank shall also retain records."]


# -- A3 blocking -------------------------------------------------------------------


def test_blocking_excludes_function_headings_and_no_family_and_counts_them():
    mc = mc_for([CB, SFB], [FM], 4, 3)
    cs = [cand("md_a::p00001", "Banks shall comply.", CB), cand("md_b::p00001", "Banks shall comply.", SFB),
          cand("md_f::p00001", "Dealers shall comply.", FM), cand("md_n::p00001", "Banks shall report.", CB)]
    fam = {"md_a": F1, "md_b": F1, "md_f": F1, "md_n": None}
    eligible, no_family, acc = M.classify_candidates(cs, fam, mc)
    assert [c.candidate_id for c in eligible] == ["t1c_md_a::p00001", "t1c_md_b::p00001"]
    assert [c.candidate_id for c in no_family] == ["t1c_md_n::p00001"]
    assert acc["excluded_function_heading"] == 1 and acc["excluded_no_subject_family_core"] == 1
    assert acc["by_class"][FM][M.EXCLUDED_FUNCTION_HEADING] == 1


# -- A4 stage 1 ----------------------------------------------------------------------


def test_stage1_pair_guards_short_prefixes():
    assert M.stage1_pair("the bank shall", "the bank shall maintain a register of complaints", 40) is False
    long_prefix = "passbooks retained at the branches overnight shall be held under lock and key"
    assert M.stage1_pair(long_prefix, long_prefix + " in the custody of named officials", 40) is True
    assert M.stage1_pair("an rrb shall additionally call for the documents at paragraph 350",
                         "the ucb shall additionally call for the documents at paragraph 218", 40) is False


def test_star_clustering_does_not_chain_through_a_fragment():
    mc = mc_for([CB, SFB], [], 1, 2)
    a = "for opening an account of a partnership firm, the bank shall obtain the certified copies of the deed"
    b = "for opening an account of a trust, the bank shall obtain the certified copies of the trust deed and pan"
    frag = "for opening an account of a partnership firm, the bank shall obtain the certified"
    leader = M._star_clusters([a, b, frag], mc)
    assert leader[0] != leader[1], "two different obligations must not share a cluster"
    assert leader[2] == leader[0], "the fragment joins the sentence it is a prefix of"


def _units_from(texts_by_class):
    units = []
    for k, (cls, text) in enumerate(texts_by_class):
        cid = f"t1c_md_{k}::p00001"
        units.append(M.Unit(f"{cid}#u00", cid, cls, F1, True, 0, len(text), text, text.lower()))
    return units


def test_stage1_clusters_report_cross_class_separately():
    mc = mc_for([CB, SFB, PB], [], 1, 3)
    same = "every bank shall maintain a register of complaints received and resolve them within thirty days"
    units = _units_from([(CB, same), (SFB, same), (PB, "payments banks shall publish tariffs on the website"),
                         (CB, "a within class repeat of a long enough sentence shall be one text"),
                         (CB, "a within class repeat of a long enough sentence shall be one text")])
    s1 = M.stage1_clusters(units, mc)
    cross = [c for c in s1["clusters"] if c["n_classes"] >= 2]
    assert len(cross) == 1 and cross[0]["entity_classes"] == [CB, SFB]
    assert s1["summary"]["clusters_cross_class"] == 1 and s1["summary"]["clusters_within_one_class"] == 1


# -- A5-A7 scoring ---------------------------------------------------------------------


def test_rollup_is_max_over_unit_pairs():
    sim = np.array([[0.1, 0.9, 0.2], [0.3, 0.1, 0.8]])
    # source units {0,1} -> one paragraph; target units {0} and {1,2} -> two paragraphs
    out = M._rollup(sim, np.array([0]), np.array([0, 1]))
    assert out.tolist() == [[0.3, 0.9]]


def _scoring_fixture(texts, tops=3):
    mc = mc_for([CB, SFB], [], 1, 2, scoring={"top_k": tops, "score_decimals": 6})
    units = []
    for cls, cid, text in texts:
        units.append(M.Unit(f"{cid}#u00", cid, cls, F1, True, 0, len(text), text, text.lower()))
    units.sort(key=lambda u: u.unit_id)
    vec = M.FakeEmbedder()([u.text for u in units])
    lex = M.fit_lexical(units)
    return mc, units, vec, lex


def test_top_k_cap_and_tie_break_order():
    src = [(CB, "t1c_md_a::p00001", "banks shall maintain a register of complaints")]
    # identical texts in SFB: semantic ties, lexical ties, so candidate_id decides
    tgts = [(SFB, f"t1c_md_b::p0000{i}", "banks shall maintain a register of complaints") for i in (4, 2, 3, 1)]
    mc, units, vec, lex = _scoring_fixture(src + tgts)
    records, _ = M.score_matches(units, vec, lex, {}, {(SFB, F1)}, mc, model_id="fake", model_revision="t")
    rec = next(r for r in records if r["source_candidate_id"] == "t1c_md_a::p00001")
    assert [t["candidate_id"] for t in rec["top_targets"]] == [
        "t1c_md_b::p00001", "t1c_md_b::p00002", "t1c_md_b::p00003"], "top-3 cap, then candidate_id order"
    assert rec["margin_top1_top2"] == 0.0


def test_lexical_breaks_semantic_ties():
    mc, units, _, lex = _scoring_fixture([
        (CB, "t1c_md_a::p00001", "banks shall maintain a register of complaints"),
        (SFB, "t1c_md_b::p00001", "unrelated words entirely here"),
        (SFB, "t1c_md_b::p00002", "banks shall maintain a register of complaints"),
    ])
    vec = np.ones((len(units), 4), dtype=np.float32) / 2.0  # every semantic score ties at 1.0
    records, _ = M.score_matches(units, vec, lex, {}, {(SFB, F1)}, mc, model_id="fake", model_revision="t")
    rec = next(r for r in records if r["source_candidate_id"] == "t1c_md_a::p00001")
    assert rec["top_targets"][0]["candidate_id"] == "t1c_md_b::p00002"


def test_expected_statuses_match_scoring(tmp_path):
    from scripts.run_matching import expected_statuses

    env = _integration_env(tmp_path)
    fam = {r["document_id"]: r.get("subject_family") for r in env["manifest"]}
    eligible, _, _ = M.classify_candidates(env["cands"], fam, env["mc"])
    exp = expected_statuses(eligible, fam, env["cells"], env["mc"])
    assert set(exp.values()) == set(M.STATUSES), "all three statuses occur on the fixture"


# -- bands, sheet, scoring, threshold --------------------------------------------------


def test_band_edges_are_tertiles():
    e = M.band_edges([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9])
    assert (e["mid_lower"], e["high_lower"]) == (0.4, 0.7)
    assert [M.band_of(x, e) for x in (0.39, 0.4, 0.69, 0.7)] == ["low", "mid", "mid", "high"]


def test_sheet_blindness_is_enforced():
    good = [{c: ("x" if c not in ("label", "note") else "") for c in M.SHEET_COLUMNS}]
    M.assert_sheet_blind(good)
    with pytest.raises(M.MatchingError):
        M.assert_sheet_blind([{**good[0], "semantic_score": "0.9"}])
    with pytest.raises(M.MatchingError):
        M.assert_sheet_blind([{**good[0], "label": "same"}])


def test_threshold_picks_the_lowest_qualifying_band_edge():
    edges = {"high_lower": 0.8, "mid_lower": 0.6, "min": 0.1}

    def res(h, m, lo):
        return {"by_stratum": {b: {"counterpart_rate": {"rate": r}} for b, r in
                               (("high", h), ("mid", m), ("low", lo))}}

    assert M.choose_threshold(res(0.95, 0.85, 0.2), edges, 0.8)["chosen"]["edge"] == "mid_lower"
    assert M.choose_threshold(res(0.95, 0.9, 0.8), edges, 0.8)["chosen"]["edge"] == "min"
    assert M.choose_threshold(res(0.85, 0.5, 0.1), edges, 0.8)["chosen"]["edge"] == "high_lower"
    assert M.choose_threshold(res(0.7, 0.5, 0.1), edges, 0.8)["chosen"] is None
    # per band: a weak low band does not ride on the strong bands above it (an average would give 0.883)
    assert M.choose_threshold(res(1.0, 1.0, 0.65), edges, 0.8)["chosen"]["edge"] == "mid_lower"
    # walking down stops at the first band that fails
    assert M.choose_threshold(res(0.7, 0.9, 0.9), edges, 0.8)["chosen"] is None


def test_score_command_records_every_flag_as_run():
    from scripts.run_matching import score_command

    cmd = score_command(["score", "--label-source", "manual", "--sheet-file", "data/x completed.csv",
                         "--sensitivity", "P015:related,P018:related"])
    assert cmd == ("python scripts/run_matching.py score --label-source manual --sheet-file 'data/x completed.csv' "
                   "--sensitivity P015:related,P018:related")


def test_threshold_is_a_pure_semantic_cut():
    def rec(score, mtype, status=M.STATUS_SCORED):
        return {"status": status, "top_targets": [{"semantic_score": score, "match_type": mtype}]}

    out = M.apply_threshold([rec(0.9, "semantic"), rec(0.7, "near_duplicate"), rec(0.76, "exact"),
                             rec(0.5, "semantic"), rec(0.0, "semantic", M.STATUS_NO_DIRECTION)], 0.75)
    assert [r["status"] for r in out] == [M.STATUS_MATCHED, M.STATUS_BELOW_THRESHOLD, M.STATUS_MATCHED,
                                          M.STATUS_BELOW_THRESHOLD, M.STATUS_NO_DIRECTION]
    assert all(len(r["top_targets"]) == 1 and r["threshold_value"] == 0.75 for r in out)


def test_lexical_cut_comes_from_the_top1_targets_lexical_scores():
    # lexical_best_score (another target) is high everywhere; the cut must ignore it
    records = [{"status": M.STATUS_SCORED, "lexical_best_score": 0.99,
                "top_targets": [{"semantic_score": s, "lexical_score": x}]}
               for s, x in ((0.9, 0.6), (0.8, 0.5), (0.7, 0.4), (0.6, 0.3))]
    rows = [{"stratum": "high", "semantic_score": 0.9, "lexical_score": 0.6, "label": "same"},
            {"stratum": "mid", "semantic_score": 0.8, "lexical_score": 0.5, "label": "related"},
            {"stratum": "low", "semantic_score": 0.6, "lexical_score": 0.3, "label": "unrelated"}]
    out = M.lexical_at_matched_coverage(records, {"rows": rows}, 0.75)
    assert out["coverage"] == 0.5
    assert out["lexical_threshold"] == 0.5, "the 1/2 quantile of top-1 lexical scores, not of lexical_best_score"
    assert (out["lexical"]["k"], out["lexical"]["n"]) == (2, 2)


def test_labelled_sheet_with_excel_bom_is_read(tmp_path):
    path = tmp_path / "completed.csv"
    body = "pair_id,subject_family,class_a,span_a,class_b,span_b,label,note\r\nP001,F,A,x,B,y,same,\r\n"
    path.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    rows = M.read_labelled_sheet(path)
    assert list(rows[0])[0] == "pair_id" and rows[0]["pair_id"] == "P001" and rows[0]["label"] == "same"
    r = M.score_validation(rows, {"pairs": {"P001": {"stratum": "stage1", "semantic_score": 1.0,
                                                    "lexical_score": 1.0}}})
    assert r["complete"]
    with open(path, encoding="utf-8", newline="") as fh:  # without utf-8-sig the BOM sticks to the header
        assert list(csv.DictReader(fh))[0].get("pair_id") is None


def test_boilerplate_patterns_flag_non_obligations_only():
    flagged = {
        "repeal_savings": "Further, the repeal of these directions, instructions, or guidelines shall not in any "
                          "way prejudicially affect: (1) any right, obligation or liability acquired",
        "state_nodal_officer": "All the States and UTs shall notify a State Nodal officer for implementation of "
                               "Section 12A of the Act.",
        "format_table_row": "Guarantor PAN Alpha Numeric 10 Must be a minimum of 10 characters.",
    }
    for kind, text in flagged.items():
        assert M.boilerplate_kind(text) == kind
    for text in ("The bank shall appoint a nodal officer for grievance redressal.",
                 "The bank shall ensure that the video recording bears the date\n36",
                 "The ARC shall immediately inform the State Nodal Officer of the transaction details."):
        assert M.boilerplate_kind(text) is None, text
    units = {"u1#u00": flagged["repeal_savings"], "u2#u00": flagged["repeal_savings"],
             "u3#u00": "Banks shall report.", "u4#u00": "Banks shall report."}
    clusters = [{"unit_ids": ["u1#u00", "u2#u00"], "candidate_ids": ["u1", "u2"], "n_classes": 2},
                {"unit_ids": ["u3#u00", "u4#u00"], "candidate_ids": ["u3", "u4"], "n_classes": 2},
                {"unit_ids": ["u1#u00"], "candidate_ids": ["u1"], "n_classes": 1}]
    s = M.boilerplate_cluster_split(clusters, units)
    assert (s["clusters_cross_class"], s["clusters_boilerplate"], s["clusters_without_boilerplate"]) == (2, 1, 1)
    assert s["by_pattern"]["repeal_savings"] == 1


def test_scoring_against_the_key():
    key = {"pairs": {"P001": {"stratum": "stage1", "semantic_score": 0.99, "lexical_score": 0.9},
                     "P002": {"stratum": "high", "semantic_score": 0.9, "lexical_score": 0.5},
                     "P003": {"stratum": "high", "semantic_score": 0.85, "lexical_score": 0.4}}}
    rows = [{"pair_id": "P001", "label": "same"}, {"pair_id": "P002", "label": "Related"},
            {"pair_id": "P003", "label": "unrelated"}]
    r = M.score_validation(rows, key)
    assert r["complete"]
    assert r["by_stratum"]["stage1"]["same_rate"]["rate"] == 1.0
    assert r["by_stratum"]["high"]["counterpart_rate"]["k"] == 1
    assert r["by_stratum"]["high"]["related_share"] == 0.5
    assert not M.score_validation([{"pair_id": "P001", "label": ""}], key)["complete"]


def test_sheet_does_not_favour_alphabetically_first_family():
    # 10 class pairs, each present in the same 10 families; one pair per class pair is drawn,
    # so a fixed (alphabetical) family order would put every row in "Fam 00".
    validation = matching_block()["validation"]
    validation["strata"] = {"stage1": 0, "high": 0, "mid": 0, "low": 10}
    mc = mc_for([CB], [], 1, 1, validation=validation)
    edges = {"mid_lower": 0.8, "high_lower": 0.9, "min": 0.0}
    records, cands = [], {}
    for k in range(1, 11):
        for f in range(10):
            src = cand(f"md_s{k}f{f}::p00001", "Banks shall comply.", "C0")
            tgt = cand(f"md_t{k}f{f}::p00001", "Banks shall report.", f"C{k}")
            cands[src.candidate_id], cands[tgt.candidate_id] = src, tgt
            records.append({"status": M.STATUS_SCORED, "source_candidate_id": src.candidate_id,
                            "source_entity_class": "C0", "target_entity_class": f"C{k}",
                            "subject_family": f"Fam {f:02d}",
                            "top_targets": [{"candidate_id": tgt.candidate_id, "semantic_score": 0.5,
                                             "lexical_score": 0.1, "match_type": "semantic",
                                             "source_unit_offsets": [0, 5], "target_unit_offsets": [0, 5],
                                             "near_dup_cluster_id": None}]})
    rows, key = M.draw_validation_sheet(records, edges, {}, cands, mc)
    fams = [r["subject_family"] for r in rows]
    assert len(rows) == 10 and len({r["class_b"] for r in rows}) == 10
    assert len(set(fams)) >= 4, fams


# -- checkpoints, packaging, notebook -------------------------------------------------


def test_embedding_checkpoints_resume_and_reject_stale(tmp_path):
    calls = []

    def embed(texts):
        calls.append(len(texts))
        return M.FakeEmbedder(16)(texts)

    texts = [f"text number {i} shall be embedded" for i in range(7)]
    a = M.embed_with_checkpoints(texts, embed, tmp_path, every=3)
    assert calls == [3, 3, 1]
    b = M.embed_with_checkpoints(texts, embed, tmp_path, every=3)
    assert calls == [3, 3, 1], "second run resumes from checkpoints"
    assert np.array_equal(a, b)
    M.embed_with_checkpoints(texts[:-1] + ["changed"], embed, tmp_path, every=3)
    assert calls[-3:] == [3, 3, 1], "checkpoints for other texts are discarded"


def test_code_zip_has_no_data_and_a_manifest(tmp_path):
    from scripts.run_matching import build_code_zip

    info = build_code_zip(REPO, tmp_path)
    names = zipfile.ZipFile(info["zip"]).namelist()
    assert "MANIFEST.json" in names and "src/benchmark/matching.py" in names
    assert not any(n.startswith("data/") for n in names)
    assert not any("__pycache__" in n for n in names)
    manifest = json.loads(zipfile.ZipFile(info["zip"]).read("MANIFEST.json"))
    assert set(manifest["files"]) == set(names) - {"MANIFEST.json"}


def test_notebook_cells_parse_and_notebook_is_valid_json(tmp_path):
    from scripts.build_matching_notebook import CODE_CELLS, build

    for src in CODE_CELLS:
        ast.parse(src)
    nb = json.loads(build(tmp_path / "nb.ipynb").read_text(encoding="utf-8"))
    assert nb["nbformat"] == 4
    code = "".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
    assert "revision=mc.model_revision" in code and "smoke=True" in code
    assert "annotation_" in code, "the notebook asserts no annotation file is returned"


def test_return_zip_carries_no_annotation_and_no_embeddings(tmp_path):
    from scripts.run_matching import RETURN_MEMBERS, build_return_zip

    for n in RETURN_MEMBERS:
        (tmp_path / n).write_text("{}", encoding="utf-8")
    (tmp_path / "p2002_embeddings_v1.npz").write_bytes(b"x")
    names = zipfile.ZipFile(build_return_zip(tmp_path)).namelist()
    assert sorted(names) == sorted(RETURN_MEMBERS)


# -- §U integration ---------------------------------------------------------------------

F1_SHARED = [
    "Every regulated entity shall carry out customer due diligence before opening any account for a customer.",
    "The entity shall retain records of identity documents for at least five years after the relationship ends.",
    "The entity shall report every suspicious transaction to FIU-India within seven working days of detection.",
]
F1_OWN = {
    CB: ["Commercial banks shall seek board approval for their internal KYC policy every financial year.",
         "The bank must periodically update KYC records of high risk customers at least once in two years."],
    SFB: ["Small finance banks shall use video based customer identification only through their own staff.",
          "The bank is required to flag accounts opened through business correspondents for monthly review."],
    PB: ["Payments banks shall not open accounts for non resident customers under any circumstances whatsoever.",
         "Payments banks must restrict the end of day balance of each individual customer to two lakh rupees."],
}
F2_TEXT = {
    CB: ["Banks shall not sanction loans against their own shares to any borrower in any form.",
         "Loan sanction powers shall be delegated only by a board approved policy of the bank.",
         "Banks shall disclose the annual percentage rate to every borrower before sanction."],
}


def _integration_env(tmp_path: Path) -> dict:
    """3 core classes, 2 families, 1 function heading, 1 family-less core document."""
    docs = {"md_a1": (CB, F1), "md_a2": (CB, F2), "md_b1": (SFB, F1), "md_c1": (PB, F1),
            "md_c2": (PB, F2), "md_f1": (FM, F1), "md_n1": (CB, None)}
    paras: dict[str, list[str]] = {
        "md_a1": F1_SHARED + F1_OWN[CB],
        "md_b1": [s.replace("entity", "bank") if i == 2 else s for i, s in enumerate(F1_SHARED)] + F1_OWN[SFB],
        "md_c1": F1_SHARED[:2] + F1_OWN[PB],
        "md_a2": F2_TEXT[CB],
        "md_c2": ['"Loan" shall mean any credit facility sanctioned by the bank.'],  # boilerplate only
        "md_f1": ["Market participants shall report every trade to the trade repository the same day."],
        "md_n1": ["Every bank shall display the name of its grievance officer in each branch."],
    }
    cands = []
    for doc, texts in paras.items():
        for i, t in enumerate(texts):
            cands.append(cand(f"{doc}::p{i:05d}", t, docs[doc][0]))
    manifest = [{"document_id": d, "entity_class_raw": c, "entity_class": c, "subject_family": f}
                for d, (c, f) in docs.items()]
    cells = [{"entity_class": c, "subject_family": f, "populated": True}
             for (c, f) in {v for v in docs.values() if v[1]}]
    kept = sum(1 for c in cands if not c.exclusion_reason)
    mc = mc_for([CB, SFB, PB], [FM], kept, 4)
    return {"cands": cands, "manifest": manifest, "cells": cells, "mc": mc, "kept": kept}


def test_end_to_end_units_to_score(tmp_path, monkeypatch):
    from scripts import run_matching as R

    env = _integration_env(tmp_path)
    block = matching_block(core_entity_classes=[CB, SFB, PB], function_headings=[FM],
                           expected_kept_candidates=env["kept"], expected_raw_entity_classes=4,
                           validation={"strata": {"stage1": 2, "high": 2, "mid": 2, "low": 2},
                                       "counterpart_target": 0.8})
    cfg = make_config(matching=block)
    resolver = PathResolver.from_config(cfg, repo_root=tmp_path)
    write_jsonl(resolver.write_path("benchmark", "candidates", "t1_candidates_v4.jsonl"),
                [c.to_dict() for c in env["cands"]])
    write_jsonl(resolver.write_path("metadata", "document_manifest.jsonl"), env["manifest"])
    write_jsonl(resolver.write_path("matrix", "matrix_v1.jsonl"), env["cells"])

    units = R.run_units(cfg, resolver, None)
    assert units["accounting"]["excluded_function_heading"] == 1
    assert units["accounting"]["excluded_no_subject_family_core"] == 1
    s1 = R.run_stage1(cfg, resolver, None)
    assert s1["clusters_cross_class"] >= 2

    fake = M.FakeEmbedder()
    smoke = R.kaggle_run(cfg, resolver, fake, model_id="fake", model_revision="t", smoke=True)
    assert smoke["smoke"] and smoke["records"]
    result = R.kaggle_run(cfg, resolver, fake, model_id=block["model"]["id"],
                          model_revision=block["model"]["revision"], checkpoint_dir=tmp_path / "ckpt")
    statuses = {r["status"] for r in result["records"]}
    assert statuses == set(M.STATUSES)
    stage1_top = [r for r in result["records"] if r["status"] == M.STATUS_SCORED
                  and r["top_targets"][0]["match_type"] in M.STAGE1_TYPES]
    assert stage1_top, "shared sentences are stage-1 matches"
    assert all(r["source_entity_class"] != r["target_entity_class"] for r in result["records"])

    out = tmp_path / "kaggle_out"
    R.write_stage2_outputs(result, out, {"kaggle": {"device": "cpu"}})
    zpath = R.build_return_zip(out)

    # determinism: a second run on the same inputs writes the same match file
    again = R.kaggle_run(cfg, resolver, fake, model_id=block["model"]["id"],
                         model_revision=block["model"]["revision"])
    out2 = tmp_path / "kaggle_out2"
    R.write_stage2_outputs(again, out2, {"kaggle": {"device": "cpu"}})
    assert (out / R.MATCHES_FILE).read_bytes() == (out2 / R.MATCHES_FILE).read_bytes()

    ing = R.run_ingest(cfg, resolver, None, str(zpath))
    assert ing["stage1_clusters_identical_to_local"] is True

    with pytest.raises(M.MatchingError):  # no sheet before the bands exist
        R.run_sheet(cfg, resolver, None)
    edges = R.run_bands(cfg, resolver, None)
    assert edges["defined_before_sampling"]
    sheet = R.run_sheet(cfg, resolver, None)
    with pytest.raises(M.MatchingError):  # bands are frozen once a sheet exists
        R.run_bands(cfg, resolver, None)

    rows = list(csv.DictReader(open(sheet["sheet"], encoding="utf-8")))
    assert tuple(rows[0].keys()) == M.SHEET_COLUMNS
    assert all(r["label"] == "" and r["note"] == "" for r in rows)
    key = read_json(sheet["key"])
    assert set(key["pairs"]) == {r["pair_id"] for r in rows}
    used = []
    for p in key["pairs"].values():
        used += [p["source_candidate_id"], p["target_candidate_id"]]
    assert len(used) == len(set(used)), "no candidate appears in two sampled pairs"
    clusters = read_json(Path(ing["extracted_to"]) / R.CLUSTERS_FILE)["unit_cluster"]
    seen = set()
    for p in key["pairs"].values():
        cl = {c for u, c in clusters.items() if u.split("#u")[0] in (p["source_candidate_id"], p["target_candidate_id"])}
        assert not (cl & seen), "no two sampled pairs share a stage-1 cluster"
        seen |= cl

    for r in rows:
        stratum = key["pairs"][r["pair_id"]]["stratum"]
        r["label"] = "same" if stratum == "stage1" else ("related" if stratum == "high" else "unrelated")
    labelled = tmp_path / "labelled.csv"
    with labelled.open("w", encoding="utf-8-sig", newline="") as fh:  # Excel saves with a BOM
        w = csv.DictWriter(fh, fieldnames=M.SHEET_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    with pytest.raises(M.MatchingError):  # the label source must be declared
        R.run_score(cfg, resolver, None, str(labelled))
    with pytest.raises(M.MatchingError, match="blank label"):  # the drawn (blank) sheet is never scored
        R.run_score(cfg, resolver, None, None, "manual")
    one_blank = tmp_path / "one_blank.csv"
    with one_blank.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=M.SHEET_COLUMNS)
        w.writeheader()
        w.writerows([{**r, "label": ""} if i == 0 else r for i, r in enumerate(rows)])
    with pytest.raises(M.MatchingError, match="1 of"):
        R.run_score(cfg, resolver, None, str(one_blank), "manual")
    low = next(p for p, k in key["pairs"].items() if k["stratum"] == "low")
    scored = R.run_score(cfg, resolver, None, str(labelled), "manual", f"{low}:related")
    assert scored["validation"]["complete"] and scored["label_source"] == "manual"
    assert scored["sensitivity"]["relabels"] == {low: "related"}
    assert scored["d8_split"]["total"] == env["kept"]
    report = Path(scored["report"]).read_text(encoding="utf-8")
    assert "Label source: **manual**" in report and "Sensitivity" in report
    header = report.splitlines()[2]
    for flag in ("score", "--label-source manual", "--sheet-file", "labelled.csv", f"--sensitivity {low}:related"):
        assert flag in header, (flag, header)
    if scored["threshold"]["chosen"]:
        thr = read_jsonl(resolver.write_dir("benchmark") / "matching" / R.THRESHOLDED_FILE)
        assert {r["status"] for r in thr} <= {M.STATUS_MATCHED, M.STATUS_BELOW_THRESHOLD,
                                             M.STATUS_NO_CANDIDATES, M.STATUS_NO_DIRECTION}
        assert all(r["threshold_source"] == M.THRESHOLD_SOURCE for r in thr)

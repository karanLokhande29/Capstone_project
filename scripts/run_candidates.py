#!/usr/bin/env python3
"""CLI for P2-001 full-corpus obligation-candidate extraction.

    python scripts/run_candidates.py extract   # scan the corpus, write t1_candidates_<rules>.jsonl
    python scripts/run_candidates.py sample    # draw the 40-item precision spot-check CSV
    python scripts/run_candidates.py score     # read the hand-filled spot-check, compute precision
    python scripts/run_candidates.py report    # regenerate reports/p2001_candidate_extraction.md only
    python scripts/run_candidates.py all       # extract + sample + report

`--rules v1|v2` picks the exclusion rule set (default: v2, P2-001-CORRECTIVE).
Every artifact is versioned by rule set, so v1's files and hand-reviewed result
are never overwritten by a v2 run.

Guarantees, each enforced rather than promised:

* `pilot_candidates.jsonl` and every `annotation_*.csv` are hashed before and
  after the run. Any change fails the run (exit 3).
* `sample` refuses to overwrite a spot-check CSV that already holds hand
  judgments unless `--force-resample` is given, which keeps a `.bak` copy.
  The v2 sample never contains a candidate the v1 sample showed the reviewer.
* `score` never replaces a completed precision result with NOT YET MEASURED.
* Stop conditions exit non-zero: schema drift in a matrix cell reference
  (exit 2) and spot-check precision below 70% (exit 4).
* `report` only reads.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.benchmark.candidates import (  # noqa: E402
    CANDIDATES_SUBDIR,
    CURRENT_RULES,
    EXCLUSION_SUBTYPES,
    PRECISION_SAMPLE_SEEDS,
    PRECISION_STOP_THRESHOLD,
    RULE_VERSIONS,
    RULES_V1,
    RULES_V2,
    RULES_V3,
    RULES_V4,
    READMIT_GROUPS,
    SAMPLE_INDEX_START,
    ProtectedFileChanged,
    SampleOverwriteError,
    SchemaDriftError,
    assert_unchanged,
    candidates_filename,
    cue_sentence,
    score_distinct,
    draw_precision_sample,
    draw_readmit_sample,
    matrix_cell_counts,
    readmitted_candidates,
    score_by_group,
    write_group_map,
    extract_corpus_candidates,
    extraction_metrics,
    load_candidates,
    persist_candidates,
    precision_sample_filename,
    protected_file_hashes,
    read_sample,
    score_precision_sample,
    write_precision_sample,
)
from src.common.config import load_config  # noqa: E402
from src.common.io_helpers import read_json, read_text, write_json, write_text  # noqa: E402
from src.common.logging_setup import get_logger  # noqa: E402
from src.common.paths import PathResolver, repo_relative  # noqa: E402

REPORT = "p2001_candidate_extraction.md"
PRECISION_ROUNDS = "p2001_precision_rounds.md"
NOT_YET_MEASURED = "NOT YET MEASURED"


class ScoreOverwriteError(RuntimeError):
    """Refused to replace a completed precision result with an incomplete one."""


class SampleMismatchError(RuntimeError):
    """A labelled file does not match the sample drawn for the requested rules."""


def extract_metrics_name(rules: str) -> str:
    return f"p2001_candidate_metrics_{rules}.json"


def precision_metrics_name(rules: str) -> str:
    return f"p2001_precision_metrics_{rules}.json"


def _sample_path(resolver: PathResolver, rules: str) -> Path:
    return resolver.write_path("benchmark", CANDIDATES_SUBDIR, precision_sample_filename(rules))


def _earlier_sample_ids(resolver: PathResolver, rules: str) -> list[str]:
    """candidate_ids already shown to the reviewer by earlier rule versions."""
    ids: list[str] = []
    for earlier in RULE_VERSIONS[: RULE_VERSIONS.index(rules)]:
        path = resolver.find_read_path("benchmark", CANDIDATES_SUBDIR, precision_sample_filename(earlier))
        if path is not None:
            ids.extend(row["candidate_id"] for row in read_sample(path))
    return ids


def run_extract(cfg, resolver, logger, rules: str) -> dict:
    candidates, scan = extract_corpus_candidates(resolver, cfg, logger=logger, rules=rules)
    path = persist_candidates(candidates, resolver, rules)
    metrics = extraction_metrics(candidates, scan)
    metrics["candidates_path"] = repo_relative(path)
    metrics["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_json(resolver.write_path("reports", extract_metrics_name(rules)), metrics)
    return metrics


def _group_map_path(resolver: PathResolver, rules: str) -> Path:
    return resolver.write_path("benchmark", CANDIDATES_SUBDIR, f"t1_precision_sample_{rules}_groups.json")


def run_readmit_sample(cfg, resolver, logger, *, force: bool) -> dict:
    """P2-001-V4 §B.3: 10 re-admitted candidates per v4 change, written blank.

    The pool is candidates kept by v4 but excluded by v3. Every row an earlier
    sample showed the reviewer is removed from it, including round-2 #42 and
    #73, which are already labelled.
    """
    v3 = load_candidates(resolver.read_path("benchmark", CANDIDATES_SUBDIR, candidates_filename(RULES_V3)))
    v4 = load_candidates(resolver.read_path("benchmark", CANDIDATES_SUBDIR, candidates_filename(RULES_V4)))
    pools, multiple = readmitted_candidates(v3, v4)
    excluded_ids = _earlier_sample_ids(resolver, RULES_V4)
    sample = draw_readmit_sample(pools, seed=PRECISION_SAMPLE_SEEDS[RULES_V4], exclude_ids=excluded_ids)
    start = SAMPLE_INDEX_START[RULES_V4]
    path = write_precision_sample([c for c, _ in sample], _sample_path(resolver, RULES_V4),
                                  force=force, index_start=start)
    write_group_map(sample, _group_map_path(resolver, RULES_V4))

    earlier = set(excluded_ids)
    by_group: dict[str, int] = {}
    for _, g in sample:
        by_group[g] = by_group.get(g, 0) + 1
    result = {
        "kind": "re-admitted candidates only (kept by v4, excluded by v3)",
        "sample_path": repo_relative(path),
        "group_map_path": repo_relative(_group_map_path(resolver, RULES_V4)),
        "sample_size": len(sample),
        "seed": PRECISION_SAMPLE_SEEDS[RULES_V4],
        "sample_index_range": [start, start + len(sample) - 1],
        "readmitted_pool_by_group": {g: len(p) for g, p in pools.items()},
        "readmitted_by_multiple_changes": len(multiple),
        "readmitted_total": sum(len(p) for p in pools.values()) + len(multiple),
        "sample_by_group": by_group,
        "earlier_sample_rows_in_pool_removed": sum(1 for p in pools.values() for c in p if c.candidate_id in earlier),
        "earlier_sample_rows_excluded_from_pool": len(earlier),
        "overlap_with_earlier_samples": len({c.candidate_id for c, _ in sample} & earlier),
        "entity_classes_in_sample": len({c.entity_class for c, _ in sample}),
    }
    metrics_path = resolver.write_path("reports", extract_metrics_name(RULES_V4))
    if metrics_path.is_file():
        metrics = read_json(metrics_path)
        metrics["precision_sample"] = result
        write_json(metrics_path, metrics)
    logger.info("readmit sample (v4): %s", result)
    return result


def run_remetric(cfg, resolver, logger, rules: str) -> dict:
    """Recompute the kept-only matrix-cell counts (P2-001-V4 §B.5) in place.

    Reads the existing candidates file and never re-extracts, so the v1-v3
    candidate files are not rewritten. Only the matrix-cell fields of that
    version's metrics file change.
    """
    candidates = load_candidates(resolver.read_path("benchmark", CANDIDATES_SUBDIR, candidates_filename(rules)))
    metrics_path = resolver.read_path("reports", extract_metrics_name(rules))
    metrics = read_json(metrics_path)
    before = {k: metrics.get(k) for k in ("candidates_with_matrix_cell", "candidates_without_matrix_cell",
                                          "distinct_matrix_cells")}
    counts = matrix_cell_counts(candidates)
    metrics.update(counts)
    metrics["matrix_cell_counts_recomputed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_json(resolver.write_path("reports", extract_metrics_name(rules)), metrics)
    return {"rules": rules, "before_all_cue_paragraphs": before, "after_kept_only": counts}


def run_sample(cfg, resolver, logger, rules: str, *, force: bool) -> dict:
    if rules == RULES_V4:
        return run_readmit_sample(cfg, resolver, logger, force=force)
    candidates = load_candidates(resolver.read_path("benchmark", CANDIDATES_SUBDIR, candidates_filename(rules)))
    excluded_ids = _earlier_sample_ids(resolver, rules)
    sample = draw_precision_sample(candidates, seed=PRECISION_SAMPLE_SEEDS[rules], exclude_ids=excluded_ids)
    path = write_precision_sample(
        sample, _sample_path(resolver, rules), force=force, index_start=SAMPLE_INDEX_START[rules]
    )
    by_class: dict[str, int] = {}
    for c in sample:
        by_class[c.entity_class or "<none>"] = by_class.get(c.entity_class or "<none>", 0) + 1
    result = {
        "sample_path": repo_relative(path),
        "sample_size": len(sample),
        "seed": PRECISION_SAMPLE_SEEDS[rules],
        "sample_index_range": [SAMPLE_INDEX_START[rules], SAMPLE_INDEX_START[rules] + len(sample) - 1],
        "earlier_sample_rows_excluded_from_pool": len(set(excluded_ids)),
        "overlap_with_earlier_samples": len({c.candidate_id for c in sample} & set(excluded_ids)),
        "entity_classes_in_sample": len(by_class),
        "sample_by_entity_class": dict(sorted(by_class.items())),
    }
    metrics_path = resolver.write_path("reports", extract_metrics_name(rules))
    if metrics_path.is_file():
        metrics = read_json(metrics_path)
        metrics["precision_sample"] = result
        write_json(metrics_path, metrics)
    logger.info("sample (%s): %s", rules, result)
    return result


LABEL_SOURCE_MANUAL = "manual"
LABEL_SOURCE_AI = "ai_assisted"


def _v4_distinct_scores(resolver: PathResolver, rows: list[dict], group_of: dict) -> dict:
    """Precision per distinct re-admitted sentence, overall and per group (P2-001-V4-FINISH §B.4).

    Each row's text is the sentence around the first cue v4 re-admitted (the
    cue the row was sampled for), not the whole paragraph. Identical sentences
    sit inside differently-worded paragraphs across Directions.
    """
    wanted = {r["candidate_id"] for r in rows}
    found: dict[str, dict] = {}
    for rules in (RULES_V3, RULES_V4):
        path = resolver.read_path("benchmark", CANDIDATES_SUBDIR, candidates_filename(rules))
        for cand in load_candidates(path):
            if cand.candidate_id in wanted:
                found.setdefault(cand.candidate_id, {})[rules] = cand
    sentences = []
    for r in rows:
        old, new = found[r["candidate_id"]][RULES_V3], found[r["candidate_id"]][RULES_V4]
        readmitted = [pos for pos, was, now in zip(new.cue_position, old.cue_exclusions, new.cue_exclusions)
                      if was is not None and now is None]
        start, end = readmitted[0]
        sentences.append(cue_sentence(new.span_text, start, end))
    out = {"overall": score_distinct(rows, sentences), "groups": {}}
    for g in READMIT_GROUPS:
        idx = [i for i, r in enumerate(rows) if group_of[r["candidate_id"]] == g]
        out["groups"][g] = score_distinct([rows[i] for i in idx], [sentences[i] for i in idx])
    return out


def run_score(
    cfg, resolver, logger, rules: str, sample_file: str | None = None, label_source: str | None = None
) -> dict:
    """Score a hand-labelled sample. Read-only on the sample file.

    ``sample_file`` names a labelled copy in the candidates folder (for
    example ``t1_precision_sample_v3_labeled.csv``). It must hold exactly the
    candidates of that round's pipeline-drawn sample, so a file from a
    different round cannot be scored against the wrong rule set.
    """
    drawn = resolver.read_path("benchmark", CANDIDATES_SUBDIR, precision_sample_filename(rules))
    path = resolver.read_path("benchmark", CANDIDATES_SUBDIR, sample_file) if sample_file else drawn
    if path != drawn:
        drawn_ids = [r["candidate_id"] for r in read_sample(drawn)]
        labelled_ids = [r["candidate_id"] for r in read_sample(path)]
        if sorted(drawn_ids) != sorted(labelled_ids):
            raise SampleMismatchError(
                f"{path.name} does not hold the same candidates as the {rules} sample {drawn.name}"
            )
    rows = read_sample(path)
    result = score_precision_sample(rows)
    group_map = resolver.find_read_path("benchmark", CANDIDATES_SUBDIR, f"t1_precision_sample_{rules}_groups.json")
    if group_map is not None and result["precision"] != NOT_YET_MEASURED:
        group_of = read_json(group_map)
        result["by_group"] = score_by_group(rows, group_of)
        if rules == RULES_V4:
            result["by_distinct_text"] = _v4_distinct_scores(resolver, rows, group_of)
    result["sample_path"] = repo_relative(path)
    result["scored_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result["basis"] = "scored from the hand-filled sample CSV"
    # Declared by the reviewer and recorded as declared. It is not inferred from
    # the notes. AI-assisted labels are a diagnostic only and can never close a gate.
    result["label_source"] = label_source or "undeclared"
    result["counts_toward_gate"] = label_source == LABEL_SOURCE_MANUAL
    out = resolver.write_path("reports", precision_metrics_name(rules))
    if out.is_file() and result["precision"] == NOT_YET_MEASURED:
        existing = read_json(out)
        if existing.get("precision") != NOT_YET_MEASURED:
            raise ScoreOverwriteError(
                f"{out} already holds a completed {rules} result "
                f"({existing.get('true_obligation')}/{existing.get('sample_size')}); the sample CSV is not "
                "fully judged, so it would be replaced by NOT YET MEASURED. Refusing."
            )
    write_json(out, result)
    return result


def _excluded(metrics: dict) -> int:
    """Fully excluded paragraphs. Metrics written before v3 only carry the boilerplate count, which was all of them."""
    return metrics.get("candidates_excluded", metrics["candidates_excluded_boilerplate"])


def _pct(value) -> str:
    return f"{value:.1%}" if isinstance(value, (int, float)) and not isinstance(value, bool) else str(value)


def _precision_line(p: dict | None) -> str:
    if not p:
        return NOT_YET_MEASURED
    if p.get("precision") == NOT_YET_MEASURED:
        judged = p.get("true_obligation", 0) + p.get("not_obligation", 0)
        return f"{NOT_YET_MEASURED} ({judged} of {p.get('sample_size')} rows judged)"
    judged = p["true_obligation"] + p["not_obligation"]
    verdict = "**below 70%: stop condition fired**" if p["precision_stop_triggered"] else "meets the 70% floor"
    ci = p.get("wilson_95")
    interval = f", Wilson 95% {_pct(ci[0])}–{_pct(ci[1])}" if ci else ""
    return f"**{p['true_obligation']}/{judged} = {_pct(p['precision'])}** ({verdict}{interval})"


GROUP_LABELS = {
    "access_restriction": "Access restrictions (\"shall have access to ... only\")",
    "disclosure_scope": "Disclosure / reporting scope",
    "risk_weight_provisioning": "Risk weight / provisioning / capital charge",
}


def _v4_precision_lines(sample: dict | None, p3: dict | None, p4: dict | None) -> list[str]:
    """P2-001-V4 §B.4: v4 = v3's kept set (round 3) + the re-admitted set, each with its own figure."""
    lines = [
        "v4 changes only which v3-excluded paragraphs come back, so its precision is reported in two parts "
        "that are never merged into one number:",
        "",
        f"- **v3 kept set** (unchanged in v4): round 3, {_precision_line(p3)}.",
        f"- **Re-admitted set** (kept by v4, excluded by v3): {_precision_line(p4)}.",
    ]
    if sample:
        idx = sample["sample_index_range"]
        lines += [
            f"- Re-admitted pool: {sample['readmitted_total']:,} paragraphs. By group: "
            + ", ".join(f"{GROUP_LABELS.get(g, g)} {n:,}" for g, n in sample["readmitted_pool_by_group"].items())
            + f". Re-admitted by more than one change (left out of the per-group sample): "
            f"{sample['readmitted_by_multiple_changes']}.",
            f"- Sample: {sample['sample_size']} rows, 10 per group, stratified by entity class, seed {sample['seed']}, "
            f"`sample_index` {idx[0]}–{idx[1]}, written blank to "
            f"`data/benchmark/{CANDIDATES_SUBDIR}/{precision_sample_filename(RULES_V4)}`. The group of each row is "
            f"kept out of that file, in `t1_precision_sample_v4_groups.json`, and there is no prediction file. "
            f"{sample['earlier_sample_rows_in_pool_removed']} pool rows that earlier samples had already shown the "
            f"reviewer were removed; overlap with earlier samples: {sample['overlap_with_earlier_samples']}.",
        ]
    by_group = (p4 or {}).get("by_group")
    if by_group:
        lines += ["", "| Re-admitted group | Judged | True obligations | Precision | Wilson 95% | Gate (≥ 70%) |",
                  "|---|---|---|---|---|---|"]
        for g in READMIT_GROUPS:
            s = by_group["groups"][g]
            judged = s["true_obligation"] + s["not_obligation"]
            ci = s.get("wilson_95")
            gate = "**fails: v3 exclusion comes back**" if s["restore_v3_exclusion"] else "passes"
            lines.append(f"| {GROUP_LABELS[g]} | {judged} | {s['true_obligation']} | {_pct(s['precision'])} | "
                         f"{_pct(ci[0]) + '–' + _pct(ci[1]) if ci else 'n/a'} | {gate} |")
        o = by_group["overall"]
        ci = o.get("wilson_95")
        lines.append(f"| **All re-admitted** | {o['true_obligation'] + o['not_obligation']} | {o['true_obligation']} | "
                     f"{_pct(o['precision'])} | {_pct(ci[0]) + '–' + _pct(ci[1]) if ci else 'n/a'} | — |")
        lines += [
            "",
            f"- Label source (declared by the reviewer): **{p4.get('label_source', 'undeclared')}**. "
            + ("Counts toward the gate." if p4.get("counts_toward_gate")
               else "**Diagnostic only; cannot close the gate.**"),
            f"- Gate: {'no group below 70%, so no v3 exclusion is restored' if not by_group['groups_failing_gate'] else 'groups below 70%: ' + ', '.join(by_group['groups_failing_gate']) + ' (their v3 exclusion comes back; reported, not applied)'}.",
        ]
    distinct = (p4 or {}).get("by_distinct_text")
    if distinct:
        lines += ["", "Per **distinct text**. A near-identical sentence repeated across Directions counts once "
                  "(prefix or ≥ 90% similar), and a text counts as an obligation only if every copy is `y`:", "",
                  "| Re-admitted group | Rows | Distinct texts | True obligations | Precision | Wilson 95% |",
                  "|---|---|---|---|---|---|"]
        for g in READMIT_GROUPS:
            d = distinct["groups"][g]
            w = d["wilson_95"]
            lines.append(f"| {GROUP_LABELS[g]} | {d['rows']} | {d['distinct_texts']} | {d['true_obligation']} | "
                         f"{_pct(d['precision'])} | {_pct(w[0])}–{_pct(w[1])} |")
        d = distinct["overall"]
        w = d["wilson_95"]
        lines.append(f"| **All re-admitted** | {d['rows']} | {d['distinct_texts']} | {d['true_obligation']} | "
                     f"{_pct(d['precision'])} | {_pct(w[0])}–{_pct(w[1])} |")
        lines += ["", "- Repeated texts (rows): "
                  + "; ".join("#" + ", #".join(c) for c in d["repeated_texts"])
                  + f". Clusters whose copies were labelled differently: {len(d['clusters_with_conflicting_labels'])}."]
    else:
        lines.append(
            "- To score: fill `is_obligation` (y/n) on all 30 rows, then run "
            "`python scripts/run_candidates.py score --rules v4` (add `--sample-file <labelled copy>` if it was "
            "saved under another name). Any group below 70% gets its v3 exclusion back. That is reported, not "
            "applied automatically."
        )
    lines.append("")
    return lines


def _write_report(resolver: PathResolver) -> Path:
    runs: dict[str, dict] = {}
    precision: dict[str, dict | None] = {}
    for rules in RULE_VERSIONS:
        path = resolver.find_read_path("reports", extract_metrics_name(rules))
        if path is not None:
            runs[rules] = read_json(path)
        ppath = resolver.find_read_path("reports", precision_metrics_name(rules))
        precision[rules] = read_json(ppath) if ppath else None
    if not runs:
        raise FileNotFoundError("no p2001_candidate_metrics_<rules>.json; run `extract` first")
    versions = [v for v in RULE_VERSIONS if v in runs]
    current = versions[-1]  # the newest rule version that has been run
    m = runs[current]
    missing = m["documents_missing_paragraphs"]

    lines: list[str] = [
        "# P2-001 — Deontic obligation-span candidate extraction",
        "",
        f"_Current rules: **{current}**. Candidate file: `data/benchmark/{CANDIDATES_SUBDIR}/"
        f"{candidates_filename(current)}` (gitignored, not committed). Earlier rule versions' files and "
        "results are kept, not overwritten._",
        "",
        "This stage **proposes** candidates only. Nothing here is a label or a validation.",
        "",
    ]

    # Hand-written closing record (P2-001-CLOSE): precision rounds, labelling
    # rules, known limitations. Embedded verbatim so regenerating this report
    # never erases it.
    rounds_path = resolver.find_read_path("reports", PRECISION_ROUNDS)
    if rounds_path is not None:
        lines += [read_text(rounds_path).rstrip(), ""]

    if RULES_V3 in runs:
        p2 = precision.get(RULES_V2) or {}
        lines += [
            "## 0b. Correction note, round 2 (P2-001-CORRECTIVE-v2)",
            "",
            f"- v2 rules result as marked: {_precision_line(p2)}. Under the stricter reading of rows 42, 60, 61 "
            "and 73 it is 27/40 = 67.5%, the figure P2-001-CORRECTIVE-v2 acted on (see Precision rounds).",
            "- The v2 fix worked on its own targets: neither redirect nor classification clauses appear among the "
            "round-2 false positives. The misses were four new shapes: a disclosure-scope exclusion (\"this "
            "disclosure shall exclude ...\"), a non-diminishment clause (\"outsourcing ... shall not diminish its "
            "obligations\"), a scope-extension signpost (\"Instruction at (4) above shall also apply to ...\"), and "
            "an access-scope clause (\"shall have access to ... only those borrowers\").",
            "- v3 **replaces** v2's two narrow subtypes with one general exclusion, `non_action_effect`, for a cue "
            "that states a fact about legal position, another rule, a definition, or a permission/scope boundary, "
            "not an action the entity must take. The subtype is kept in `exclusion_reason` "
            "(`non_action_effect:legal_effect`, `:cross_reference`, `:definitional`, `:access_scope`, "
            "`:disclosure_scope`). P2-001's own checks (heading, definitional, procedural, quoted statute) run "
            "first and are unchanged. Mixed paragraphs stay candidates through the existing per-cue logic.",
            "- All 10 hand-identified false positives from both rounds are unit-test fixtures and classify as "
            "`non_action_effect`. v1 and v2 remain selectable, and their reruns reproduce "
            "`t1_candidates_v1.jsonl` and `t1_candidates_v2.jsonl` byte for byte.",
            "- The v3 sample is a fresh draw (new seed, all 80 earlier sample rows removed from the pool, numbered "
            "81–120) and is written **blank**: no pre-filled `is_obligation` or `reviewer_note`, and no "
            "separate prediction file, so the review starts unanchored.",
            "- If v3 also comes back below 70%, P2-001-CORRECTIVE-v2 §D applies: stop. Revisit paragraph-level "
            "cue matching itself rather than extending the exclusion list again.",
            "",
        ]

    if RULES_V1 in runs and RULES_V2 in runs:
        p1 = precision.get(RULES_V1) or {}
        lines += [
            "## 0. Correction note, round 1 (P2-001-CORRECTIVE)",
            "",
            f"- v1 rules result: {_precision_line(p1)}. P2-001 §F required a fix before Week 4 continues. "
            f"Basis: {p1.get('basis', 'n/a')}.",
            "- Root cause from the reviewed v1 sample: 13 of 40 were not obligations. Six fall into two "
            "unhandled patterns: **cross-reference redirects** (\"shall be governed by / subject to / guided by "
            "[another instrument]\", 4 rows) and **classification/deeming** clauses (\"shall be treated as\", "
            "\"shall be standardized at\", 2 rows).",
            "- v2 adds two `excluded_boilerplate` subtypes, `redirect_reference` and `classification_deeming`. "
            "It also extends `definitional` to \"shall bear the meaning(s)\" and \"shall be as defined in/under\". "
            "The v2 checks run after every v1 check, so no cue v1 excluded changes subtype. v1 is still "
            "selectable (`--rules v1`), and re-running it reproduces `t1_candidates_v1.jsonl` byte for byte.",
            "- The v2 precision sample is a **fresh** draw: new seed, and the 40 v1 rows are removed from the "
            "pool. It is numbered 41–80, so no v2 row shares a number with a v1 row. The reviewed v1 rows "
            "served only as unit-test fixtures, never as validation.",
            "- Still open after v1 and **deliberately not changed** (outside P2-001-CORRECTIVE's scope): "
            "\"interpretation ... shall be final and binding\" closing clauses, \"shall also be in order for\" and "
            "\"shall have the option to\" permissive clauses, and \"shall attract penal provisions\". The "
            "corrective prompt describes these v1 rows as already handled. They were not: all were kept "
            "candidates under v1, and no permissive-option rule exists.",
            "",
        ]

    lines += [
        "## 1. Rule versions side by side",
        "",
        "| | " + " | ".join(f"{v} rules" for v in versions) + " |",
        "|---|" + "---|" * len(versions),
        "| Paragraphs with a cue | " + " | ".join(f"{runs[v]['candidates_total']:,}" for v in versions) + " |",
        "| Kept as candidates | " + " | ".join(f"{runs[v]['candidates_kept']:,}" for v in versions) + " |",
        "| Fully excluded paragraphs (any reason) | "
        + " | ".join(f"{_excluded(runs[v]):,}" for v in versions) + " |",
        "| &nbsp;&nbsp;of which `excluded_boilerplate` only | "
        + " | ".join(f"{runs[v]['candidates_excluded_boilerplate']:,}" for v in versions) + " |",
        "| Cue matches excluded | " + " | ".join(
            f"{runs[v]['cue_matches_excluded']:,} of {runs[v]['cue_matches_total']:,}" for v in versions) + " |",
        "| **Rejection rate (cue level)** | "
        + " | ".join(f"**{_pct(runs[v]['rejection_rate_cue_level'])}**" for v in versions) + " |",
    ]
    for subtype in EXCLUSION_SUBTYPES:
        lines.append(
            f"| &nbsp;&nbsp;`{subtype}` cues | "
            + " | ".join(f"{runs[v]['exclusions_by_subtype'].get(subtype, 0):,}" for v in versions) + " |"
        )
    lines += [
        "| **Precision spot-check** | " + " | ".join(
            f"v3 kept set {_precision_line(precision.get(RULES_V3))} + re-admitted set "
            f"{_precision_line(precision.get(RULES_V4))} (reported separately, not merged)"
            if v == RULES_V4 else _precision_line(precision.get(v))
            for v in versions) + " |",
        "",
        f"## 2. Corpus scanned ({current} run)",
        "",
        f"- Documents in manifest: {m['documents_in_manifest']}",
        f"- Documents scanned: {m['documents_scanned']}",
        f"- Documents with no paragraph file: {len(missing)}"
        + (f" ({', '.join(missing[:10])}{' …' if len(missing) > 10 else ''})" if missing else ""),
        f"- Paragraphs scanned: {m['paragraphs_scanned']:,} (expected 76,188 from P1-004)",
        f"- Metrics generated {m.get('generated_at', '?')}",
        "",
        f"## 3. Candidates ({current} rules)",
        "",
        f"- Paragraphs with at least one cue: **{m['candidates_total']:,}** "
        f"({_pct(m['paragraphs_with_cue_rate'])} of paragraphs)",
        f"- Kept as candidates: **{m['candidates_kept']:,}**",
        f"- Fully excluded (every cue excluded): **{_excluded(m):,}**. By `exclusion_reason`: "
        + (", ".join(f"`{k}` {v:,}" for k, v in m.get("exclusion_reason_counts", {}).items())
           or f"`excluded_boilerplate` {m['candidates_excluded_boilerplate']:,}"),
        f"- Mixed paragraphs (some cues excluded, at least one kept): {m['mixed_paragraphs']:,}",
        f"- Kept candidates with a matrix cell: {m['candidates_with_matrix_cell']:,}, across "
        f"{m['distinct_matrix_cells']} distinct cells. Kept candidates without one (document has no derived subject "
        f"family): {m['candidates_without_matrix_cell']:,}"
        + ("" if m.get("matrix_cell_counts_basis") == "kept candidates only"
           else " (**stale: counts every cue paragraph, excluded ones included; run `remetric`**)"),
        "",
        "### Cue distribution (every match / kept matches only)",
        "",
        "| Cue | All matches | Kept |",
        "|---|---|---|",
    ]
    for cue, count in m["cue_distribution_all"].items():
        lines.append(f"| `{cue}` | {count:,} | {m['cue_distribution_kept'].get(cue, 0):,} |")

    lines += [
        "",
        "### By entity class (raw, from the manifest)",
        "",
        "| Entity class | Paragraphs | Kept | Excluded |",
        "|---|---|---|---|",
    ]
    for cls, n_paras in m["paragraphs_by_entity_class"].items():
        lines.append(
            f"| {cls} | {n_paras:,} | {m['kept_by_entity_class'].get(cls, 0):,} "
            f"| {m['excluded_by_entity_class'].get(cls, 0):,} |"
        )

    lines += [
        "",
        "## 4. Gate item 2: candidate rejection rate",
        "",
        f"- {current} rules: {m['cue_matches_excluded']:,} of {m['cue_matches_total']:,} cue matches excluded = "
        f"**{_pct(m['rejection_rate_cue_level'])}** (paragraph level: {_pct(m['rejection_rate_paragraph_level'])}). "
        "The per-subtype and per-version counts are in section 1.",
    ]
    if m.get("rejection_rate_zero_flag"):
        lines += ["", "> **WARNING: the rejection rate is 0%.** The exclusion rules never fired, which is not "
                  "credible on RBI text that opens every Direction with definitions. Investigate before using this file."]

    lines += ["", "## 5. Gate item 1: precision spot-check", ""]
    for v in versions:
        sample = runs[v].get("precision_sample")
        lines.append(f"### {v} rules")
        lines.append("")
        if v == RULES_V4:
            lines += _v4_precision_lines(sample, precision.get(RULES_V3), precision.get(RULES_V4))
            continue
        if sample:
            idx = sample.get("sample_index_range") or [1, sample["sample_size"]]
            lines.append(
                f"- Sample: {sample['sample_size']} kept candidates across {sample['entity_classes_in_sample']} "
                f"entity classes, stratified, seed {sample.get('seed', PRECISION_SAMPLE_SEEDS[v])}, "
                f"`sample_index` {idx[0]}–{idx[1]}, in `data/benchmark/{CANDIDATES_SUBDIR}/{precision_sample_filename(v)}`"
            )
            if sample.get("earlier_sample_rows_excluded_from_pool"):
                lines.append(
                    f"- Fresh draw: {sample['earlier_sample_rows_excluded_from_pool']} earlier-sample rows removed "
                    f"from the pool; overlap with earlier samples: {sample['overlap_with_earlier_samples']}"
                )
            lines.append(
                "- By entity class: "
                + ", ".join(f"{cls} {n}" for cls, n in sample["sample_by_entity_class"].items())
            )
        lines.append(f"- Precision: {_precision_line(precision.get(v))}")
        if v == current and (precision.get(v) or {}).get("precision", NOT_YET_MEASURED) == NOT_YET_MEASURED:
            lines.append(
                f"- To score: fill `is_obligation` (y/n) on every row, then run "
                f"`python scripts/run_candidates.py score --rules {v}`. Below 70% means stop and bring it back "
                "for audit, with no third iteration."
            )
        lines.append("")

    lines += [
        "## 6. Known limits",
        "",
        f"- `should` is not a cue. Paragraphs containing `should` and no cue: "
        f"{m['paragraphs_should_without_cue']:,}. That count is the upper bound of the recall gap this choice creates.",
        "- Exemptions (`shall not be required to`) match `shall not` and are kept. They are not boilerplate "
        "under step C.3, so Week 5 rejects them.",
        "- Reproduced statute is detected only when quoted (60+ characters inside quote marks) or introduced by "
        "\"reads as under/follows\"-type phrasing in the same or the preceding paragraph. Unquoted reproductions pass through.",
        "- `redirect_reference` needs the redirect's object (up to the end of its clause) to name an instrument "
        "(Direction, Act, guidelines, instructions, norms, paragraph, …). A duty named before that reference "
        "(validation, approval, audit, review, …) keeps the cue. \"Subject to a ceiling of 10 per cent\" and "
        "\"subject to the following conditions\" stay candidates.",
        "- `classification_deeming` (v2) and `non_action_effect:definitional` (v3) keep \"shall be treated as "
        "confidential\"-type clauses, which impose a duty.",
        "- v3 excluded risk-weight and provisioning measurement clauses (\"claims on the Central Government "
        "shall attract zero risk weight\", \"shall be risk weighted at 150 per cent\") as "
        "`non_action_effect:definitional`. **v4 re-admits them**, because the labelling line counts them as "
        "obligations and they are prime RQ2 differential content. Classification such as \"shall be reckoned as "
        "Tier 1 capital\" stays excluded.",
        "- `access_scope` (v3 and v4) treats \"shall be allowed/permitted to <verb>\" as a permission, but not "
        "\"shall be allowed to the <recipient>\", which obliges the entity to grant something. Negated forms "
        "(\"shall not be permitted to\") are prohibitions and stay candidates. **v4** also re-admits \"shall have "
        "access\" as a restriction, and keeps eligibility (\"shall be eligible for\") excluded as a status, not a "
        "duty.",
        "- v3's `disclosure_scope` needed a reporting noun within six words before the cue. **v4 removes the "
        "subtype entirely**, because the labelling line counts disclosure and reporting scope as an obligation.",
        "- `cue_exclusions` is one field beyond the P2-001 section D schema. It holds the per-cue subtype that "
        "the cue-level rejection rate needs.",
        "",
    ]
    path = resolver.write_path("reports", REPORT)
    write_text(path, "\n".join(lines))
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=("extract", "sample", "score", "report", "remetric", "all"))
    parser.add_argument("--rules", choices=RULE_VERSIONS, default=CURRENT_RULES)
    parser.add_argument("--config", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--sample-file", default=None,
        help="score: a hand-labelled copy of the sample, by file name inside data/benchmark/candidates/ "
             "(read only; must hold the same candidates as the --rules sample)",
    )
    parser.add_argument(
        "--label-source", choices=(LABEL_SOURCE_MANUAL, LABEL_SOURCE_AI), default=None,
        help="score: who produced the labels, as declared by the reviewer. 'ai_assisted' makes the result a "
             "diagnostic that cannot close the gate.",
    )
    parser.add_argument(
        "--force-resample", action="store_true",
        help="redraw the precision sample even though it holds hand judgments (old file kept as .bak)",
    )
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    resolver = PathResolver.from_config(cfg)
    logger = get_logger("scripts.run_candidates", cfg)

    before = protected_file_hashes(resolver)
    metrics: dict = {"stage": args.stage, "rules": args.rules, "protected_files_checked": len(before)}
    exit_code = 0
    try:
        if args.stage in ("extract", "all"):
            metrics["extract"] = run_extract(cfg, resolver, logger, args.rules)
        if args.stage in ("sample", "all"):
            metrics["sample"] = run_sample(cfg, resolver, logger, args.rules, force=args.force_resample)
        if args.stage == "remetric":
            metrics["remetric"] = run_remetric(cfg, resolver, logger, args.rules)
        if args.stage == "score":
            metrics["score"] = run_score(cfg, resolver, logger, args.rules, args.sample_file, args.label_source)
            failing = (metrics["score"].get("by_group") or {}).get("groups_failing_gate")
            if args.label_source == LABEL_SOURCE_AI:
                print("DIAGNOSTIC ONLY: labels declared ai_assisted; this result cannot close the gate. Stop and "
                      "report.", file=sys.stderr)
                exit_code = 5
            elif failing:
                # P2-001-V4 §B.3: report only. Restoring a v3 exclusion is a later, audited step.
                print(f"GATE: re-admitted group(s) below {PRECISION_STOP_THRESHOLD:.0%}: {', '.join(failing)}. "
                      "Their v3 exclusion should come back (reported, not applied).", file=sys.stderr)
                exit_code = 4
            elif metrics["score"]["precision_stop_triggered"] and "by_group" not in metrics["score"]:
                print(f"STOP: {args.rules} spot-check precision {metrics['score']['precision']:.1%} is below "
                      f"{PRECISION_STOP_THRESHOLD:.0%}", file=sys.stderr)
                exit_code = 4
        if args.stage in ("report", "all", "score", "remetric"):
            metrics["report_path"] = repo_relative(_write_report(resolver))
    except SchemaDriftError as exc:
        print(f"STOP (schema drift): {exc}", file=sys.stderr)
        exit_code = 2
    except (SampleOverwriteError, ScoreOverwriteError, SampleMismatchError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        exit_code = 1

    try:
        assert_unchanged(before, protected_file_hashes(resolver))
    except ProtectedFileChanged as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        return 3
    if exit_code in (1, 2):
        return exit_code

    if args.json:
        print(json.dumps(metrics, indent=2, default=str))
    else:
        for stage_name, stage_metrics in metrics.items():
            if not isinstance(stage_metrics, dict):
                print(f"{stage_name}: {stage_metrics}")
                continue
            print(f"=== {stage_name} ===")
            for key, value in stage_metrics.items():
                print(f"  {key}: {value}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

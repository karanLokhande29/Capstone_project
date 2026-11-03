#!/usr/bin/env python3
"""Draft paper figures (P1). Every count is read from the results bundle; T1 v2 numbers stay {{placeholders}}.

    python3 scripts/build_figures.py

Figures:
1. benchmark construction;
2. annotation and provenance flow, including the T1 v2 design;
3. evaluation architecture;
4. the class × subject-family matrix.

Writes PNG and SVG to reports/private/final_push/figures/, plus a manifest that names the source key of every number.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/private/final_push/figures"
R = json.loads((ROOT / "reports/results_v1.json").read_text())["tables"]
SRC: dict[str, dict[str, str]] = {}

INK, MUTED, EDGE = "#1f2328", "#57606a", "#8c959f"
FILL = {"data": "#eaf2fb", "human": "#fdf3e1", "system": "#eef7ee", "held": "#f4f0fb", "out": "#ffffff"}


def val(fig: str, key: str):
    """Read 'a.b.c' from the bundle tables and record it as a figure source."""
    v = R
    for k in key.split("."):
        v = v[k]
    SRC.setdefault(fig, {})[key] = v
    return v


def box(ax, x, y, w, h, text, kind="data", fs=8.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06", fc=FILL[kind], ec=EDGE, lw=0.9))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=INK, wrap=True)
    return (x, y, w, h)


def arrow(ax, a, b, label=None):
    (x1, y1, w1, h1), (x2, y2, w2, h2) = a, b
    if abs((y1 + h1 / 2) - (y2 + h2 / 2)) < 0.05:  # same row: left -> right
        p, q = (x1 + w1, y1 + h1 / 2), (x2, y2 + h2 / 2)
    else:  # top -> bottom
        p, q = (x1 + w1 / 2, y1), (x2 + w2 / 2, y2 + h2)
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=9, color=MUTED, lw=0.9))
    if label:
        ax.text((p[0] + q[0]) / 2 + 0.05, (p[1] + q[1]) / 2, label, fontsize=7, color=MUTED, va="center")


def canvas(w=11, h=6):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis("off")
    return fig, ax


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "svg"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig1_construction():
    f = "fig1_benchmark_construction"
    fig, ax = canvas(11, 4.6)
    a = box(ax, 0.2, 3.0, 2.2, 1.2, f"RBI Master Directions\n{val(f, '01_corpus.directions')} Directions\n{val(f, '01_corpus.paragraphs'):,} paragraphs")
    b = box(ax, 2.9, 3.0, 2.3, 1.2, f"Obligation candidates\n(deontic cues, rules v4)\n{val(f, '02_candidates.candidates_kept'):,} kept")
    c = box(ax, 5.7, 3.0, 2.4, 1.2, "Cross-class matching\n(P2-002, bge-base\n+ lexical; thresholded)")
    d = box(ax, 8.6, 3.0, 2.2, 1.2, f"T1 sample\n{val(f, '05_t1_benchmark.sample')} items\n(seeded, stratified)", "human")
    e = box(ax, 8.6, 1.2, 2.2, 1.2, f"T1 gold v1: {val(f, '05_t1_benchmark.validated')} validated\n{val(f, '05_t1_benchmark.rejected')} rejected\n(gold v2: {{{{T1_N}}}})", "human")
    t2 = box(ax, 0.2, 0.6, 2.4, 1.2, "T2 relevance sets\n(counterpart retrieval)")
    t3 = box(ax, 2.9, 0.6, 2.4, 1.2, f"T3 temporal\n{val(f, '08_t3.scored')} items (amendment parser)")
    t4 = box(ax, 5.7, 0.6, 2.4, 1.2, f"T4 metric audit\n{val(f, '09_t4.n_questions')} questions × 4 answer types")
    arrow(ax, a, b); arrow(ax, b, c); arrow(ax, c, d); arrow(ax, d, e, "human labels")
    for t in (t2, t3, t4):
        ax.add_patch(FancyArrowPatch((1.3, 3.0), (t[0] + t[2] / 2, t[1] + t[3]), arrowstyle="-|>", mutation_scale=8, color=EDGE, lw=0.7, ls="--"))
    save(fig, f)


def fig2_provenance():
    f = "fig2_annotation_provenance"
    fig, ax = canvas(12, 4.9)
    ax.text(0.2, 4.6, "T1 gold (P2-004): one expert annotator, recorded routes", fontsize=9.5, color=INK, weight="bold")
    s = box(ax, 0.2, 3.1, 2.1, 1.1, f"Sample\n{val(f, '05_t1_benchmark.sample')} items\n(seeded, stratified)", "data")
    p1 = box(ax, 2.7, 3.1, 2.3, 1.1, "rater_1 pass 1\n(all items; frozen)", "human")
    rt = box(ax, 5.4, 3.1, 2.3, 1.1, "rater_1 blind retest (25)\n+ timed re-label (20)", "human")
    adj = box(ax, 8.1, 3.1, 1.8, 1.1, "rater_1\nadjudication", "human")
    g1 = box(ax, 10.2, 3.1, 1.6, 1.1, f"gold\n{val(f, '05_t1_benchmark.validated')} validated\n{val(f, '05_t1_benchmark.rejected')} rejected", "out", fs=8)
    for x, y in ((s, p1), (p1, rt), (rt, adj), (adj, g1)):
        arrow(ax, x, y)
    ax.text(0.2, 2.25, "Reliability evidence (reported separately from the gold)", fontsize=9.5, color=INK, weight="bold")
    irr = box(ax, 0.2, 0.8, 5.4, 1.1, "Separate 30-item set, 3 raters (rater_1–rater_3), pre-adjudication:\n"
              "Fleiss kappa, class judgements and flag — NOT part of the gold", "held", fs=7.8)
    ret = box(ax, 6.0, 0.8, 5.8, 1.1, "rater_1 blind test-retest (25 items; 11.7–18.6 h gap):\n"
              "supplementary only (recall may inflate agreement)", "held", fs=7.8)
    ax.text(0.2, 0.3, "Every sheet showed the same two P2-002 candidate paragraphs per compared class (no scores).",
            fontsize=7.2, color=MUTED)
    save(fig, f)


def fig3_architecture():
    f = "fig3_evaluation_architecture"
    fig, ax = canvas(11.5, 5.2)
    q = box(ax, 0.2, 2.1, 2.0, 1.2, "T1 item / T2–T4 query\n(+ compared classes,\nas-of date)")
    ret = box(ax, 2.7, 3.4, 2.4, 1.1, "Hybrid retrieval\nBM25 + dense\n± class filter (A)", "system")
    tf = box(ax, 2.7, 1.9, 2.4, 1.1, "Temporal filter (B)\nin force on the as-of date", "system")
    lc = box(ax, 2.7, 0.4, 2.4, 1.1, "Long-context:\nall Directions of the\ncompared classes (100K cap)", "system", fs=7.8)
    llm = box(ax, 5.6, 2.1, 2.2, 1.2, "LLM judgement\n(gemini-3.5-flash-lite,\nfrozen prompts)", "system")
    ver = box(ax, 8.2, 3.4, 2.4, 1.1, "NLI verifier (C)\nretry or abstain", "system")
    cmp_ = box(ax, 8.2, 1.9, 2.4, 1.1, "Pairwise structured\ncomparator (targeted\nexperiment; rule-based verdict)", "held", fs=7.6)
    met = box(ax, 8.2, 0.4, 2.4, 1.1, "Metrics + bootstrap CIs\n(item resamples; paired diffs)", "out")
    for x in (ret, tf, lc):
        ax.add_patch(FancyArrowPatch((q[0] + q[2], q[1] + q[3] / 2), (x[0], x[1] + x[3] / 2), arrowstyle="-|>",
                                     mutation_scale=8, color=MUTED, lw=0.8))
    for x in (ret, tf, lc):
        ax.add_patch(FancyArrowPatch((x[0] + x[2], x[1] + x[3] / 2), (5.6, 2.7), arrowstyle="-|>", mutation_scale=8, color=MUTED, lw=0.8))
    ax.add_patch(FancyArrowPatch((7.8, 2.9), (8.2, 3.9), arrowstyle="-|>", mutation_scale=8, color=MUTED, lw=0.8))
    ax.add_patch(FancyArrowPatch((7.8, 2.5), (8.2, 2.45), arrowstyle="-|>", mutation_scale=8, color=EDGE, lw=0.8, ls="--"))
    ax.text(7.75, 1.75, "same model,\nfield extraction", fontsize=6.8, color=MUTED, ha="right")
    ax.add_patch(FancyArrowPatch((9.4, 1.9), (9.4, 1.5), arrowstyle="-|>", mutation_scale=8, color=MUTED, lw=0.8))
    ax.add_patch(FancyArrowPatch((10.6, 3.9), (10.75, 1.0), connectionstyle="arc3,rad=-0.3", arrowstyle="-|>", mutation_scale=8, color=MUTED, lw=0.8))
    ax.text(0.2, 4.85, "Baselines: majority (in-sample), P2-002 candidate labels, class-blind LLM, class-aware LLM; "
            "final agentic = class filter + verifier", fontsize=7.4, color=MUTED)
    save(fig, f)


def fig4_matrix():
    f = "fig4_class_subject_matrix"
    rows = [json.loads(l) for l in (ROOT / "release/data/matrix/matrix_v1.jsonl").read_text().splitlines() if l.strip()]
    classes = sorted({r["entity_class"] for r in rows})
    fams = sorted({r["subject_family"] for r in rows})
    grid = [[0] * len(classes) for _ in fams]
    for r in rows:
        grid[fams.index(r["subject_family"])][classes.index(r["entity_class"])] = r["n_documents"] if r["populated"] else 0
    fig, ax = plt.subplots(figsize=(8.5, 13))
    from matplotlib.colors import BoundaryNorm, ListedColormap
    vmax = max(max(r) for r in grid)
    cmap = ListedColormap(["#f6f8fa"] + [plt.get_cmap("Blues")(0.45 + 0.5 * k / max(vmax - 1, 1)) for k in range(vmax)])
    norm = BoundaryNorm([x - 0.5 for x in range(vmax + 2)], cmap.N)
    im = ax.imshow(grid, aspect="auto", cmap=cmap, norm=norm)
    ax.set_xticks(range(len(classes)), classes, rotation=60, ha="right", fontsize=7)
    ax.set_yticks(range(len(fams)), fams, fontsize=6.5)
    for i, row in enumerate(grid):
        for j, v in enumerate(row):
            if v:
                ax.text(j, i, str(v), ha="center", va="center", fontsize=5.5, color="#ffffff" if v > 2 else INK)
    fig.colorbar(im, ax=ax, fraction=0.03, label="Directions", ticks=list(range(vmax + 1)))
    ax.set_title(f"Entity class × subject family ({sum(1 for r in rows if r['populated'])} populated cells)", fontsize=9)
    SRC[f] = {"release/data/matrix/matrix_v1.jsonl": f"{len(rows)} cells, {len(classes)} classes, {len(fams)} families"}
    save(fig, f)


def main() -> int:
    fig1_construction()
    fig2_provenance()
    fig3_architecture()
    fig4_matrix()
    (OUT / "figures_manifest.json").write_text(json.dumps({"sources": SRC, "placeholders": ["{{T1_N}}"],
                                                           "note": "draft figures; T1 v2 numbers filled in Phase 5"},
                                                          indent=1, default=str) + "\n")
    print("\n".join(sorted(p.name for p in OUT.iterdir())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Charts and diagrams for the capstone report. Every number is copied from
reports/final/RBI-ObliBench_Master_Document_v2.md (results_v2.json)."""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"font.family": "Times New Roman", "font.size": 11, "axes.spines.top": False,
                     "axes.spines.right": False, "savefig.dpi": 220, "savefig.bbox": "tight"})
BLUE, RED, GREY, GREEN, GOLD = "#2f5d8a", "#a33a3a", "#8a8a8a", "#3f7f4f", "#b8892c"


def save(fig, name):
    fig.savefig(OUT / name)
    plt.close(fig)


# Fig: project Gantt chart (weeks from the repository history and phase reports)
phases = [
    ("Topic finalisation, literature review, synopsis", 0, 2),
    ("Phase 1: corpus harvest, segmentation, metadata matrix", 1, 3),
    ("Phase 1: corpus QA, annotation protocol, 3-rater pilot", 2, 3),
    ("P1-004: corpus repair to 381/381 Directions", 4, 2),
    ("P2-001/002: candidate extraction, cross-class matching", 4, 3),
    ("P2-003: supplementary sources (FAQ, enforcement)", 5, 2),
    ("P2-004: T1 sampling, expert labelling, retest, adjudication", 5, 3),
    ("P3: retrieval baselines (T2), RePASs audit (T4)", 7, 2),
    ("P4: RAG systems, T3, ablations A-C, long-context", 7, 2),
    ("Structured comparator, results consolidation", 8, 2),
    ("Research paper writing and submission (AISIGH-SD 2026)", 8, 2),
    ("Interactive demo and live API", 9, 1),
    ("Compliance audit generator + AI assistant", 10, 2),
    ("Final report, presentation, viva", 11, 2),
]
fig, ax = plt.subplots(figsize=(9, 5.2))
for i, (name, start, dur) in enumerate(phases):
    ax.barh(i, dur, left=start, color=BLUE if i < 10 else GOLD, height=0.6)
ax.set_yticks(range(len(phases)), [p[0] for p in phases], fontsize=9.5)
ax.invert_yaxis()
ax.set_xticks(range(0, 14), [f"W{w}" for w in range(1, 15)], fontsize=9)
ax.set_xlabel("Week of the project (August to November 2026)")
ax.grid(axis="x", color="#dddddd", lw=0.6)
ax.set_axisbelow(True)
save(fig, "gantt.png")

# Fig: T2 nDCG@10 per retrieval system and relevance set
systems = ["BM25", "Dense (bge)", "Hybrid RRF", "Hybrid -\nsource class", "Class-aware\nhybrid"]
sets = {
    "t2_xclass_t1 (n=291)": [0.458, 0.421, 0.443, 0.464, 0.894],
    "t2_xclass_p2002 (n=53)": [0.277, 0.334, 0.319, 0.337, 0.741],
    "t2_supp_p2003 (n=25)": [0.616, 0.362, 0.504, 0.504, 0.675],
}
fig, ax = plt.subplots(figsize=(8, 3.8))
w = 0.26
for k, (label, vals) in enumerate(sets.items()):
    xs = [i + (k - 1) * w for i in range(len(systems))]
    ax.bar(xs, vals, w, label=label, color=[BLUE, GREY, GOLD][k])
ax.set_xticks(range(len(systems)), systems)
ax.set_ylabel("nDCG@10")
ax.set_ylim(0, 1)
ax.legend(frameon=False, fontsize=9, loc="upper left")
save(fig, "t2_ndcg.png")

# Fig: T1 systems, 3-way flag F1 and `different` F1
t1 = [("Majority\n(in-sample)", 0.219, 0.000), ("P2-002\ncandidates", 0.459, 0.000),
      ("Class-blind\nLLM", 0.602, 0.321), ("Class-aware\nLLM", 0.551, 0.154),
      ("Final\nagentic", 0.483, 0.047), ("Class-blind\n+ verifier", 0.532, 0.176),
      ("Long-context\n(100K)", 0.509, 0.074), ("Structured\ncomparator", 0.616, 0.409)]
fig, ax = plt.subplots(figsize=(8.5, 3.8))
xs = range(len(t1))
ax.bar([x - 0.2 for x in xs], [r[1] for r in t1], 0.4, label="3-way flag macro-F1", color=BLUE)
ax.bar([x + 0.2 for x in xs], [r[2] for r in t1], 0.4, label="'different' F1", color=RED)
ax.set_xticks(list(xs), [r[0] for r in t1], fontsize=9)
ax.set_ylim(0, 0.8)
ax.set_ylabel("F1")
ax.legend(frameon=False, fontsize=9)
save(fig, "t1_systems.png")

# Fig: RePASs composite by answer type
types = ["Genuine", "Concatenated", "Negated", "Off-topic"]
means = [0.371, 0.746, 0.049, 0.229]
lo = [0.311, 0.692, 0.022, 0.198]
hi = [0.431, 0.796, 0.082, 0.257]
fig, ax = plt.subplots(figsize=(6, 3.4))
ax.bar(types, means, color=[BLUE, RED, GREY, GOLD], yerr=[[m - l for m, l in zip(means, lo)],
                                                          [h - m for m, h in zip(means, hi)]], capsize=5)
ax.set_ylabel("RePASs composite (mean, 95% CI)")
ax.set_ylim(0, 0.9)
save(fig, "repass.png")

# Fig: candidate-extraction precision over four rule rounds
fig, ax = plt.subplots(figsize=(5.5, 3.2))
p = [0.675, 0.775, 0.850, 0.929]
lo = [0.520, 0.625, 0.709, 0.774]
hi = [0.799, 0.877, 0.929, 0.980]
ax.errorbar(["v1", "v2", "v3", "v4"], p, yerr=[[a - b for a, b in zip(p, lo)], [b - a for a, b in zip(p, hi)]],
            marker="o", color=BLUE, capsize=5)
ax.set_ylabel("Precision (Wilson 95% CI)")
ax.set_xlabel("Extraction rule version")
ax.set_ylim(0.4, 1.0)
save(fig, "precision_rounds.png")

# Fig: `different` errors split into retrieval vs reasoning failures
rows = [("Class-blind LLM", 30, 30), ("Class-aware LLM", 12, 59), ("Final agentic", 12, 64),
        ("Class-blind + verifier", 30, 40), ("Long-context", 4, 69), ("Structured comparator", 0, 40)]
fig, ax = plt.subplots(figsize=(7.5, 3.4))
ys = range(len(rows))
ax.barh(list(ys), [r[1] for r in rows], color=GREY, label="Retrieval failure (gold paragraph not in context)")
ax.barh(list(ys), [r[2] for r in rows], left=[r[1] for r in rows], color=RED,
        label="Reasoning failure (gold paragraph in context)")
ax.set_yticks(list(ys), [r[0] for r in rows])
ax.invert_yaxis()
ax.set_xlabel("Errors on the 78 gold 'different' class units")
ax.legend(frameon=False, fontsize=9, loc="lower right")
save(fig, "different_errors.png")


# Block diagrams
def block_diagram(name, boxes, arrows, size):
    fig, ax = plt.subplots(figsize=size)
    ax.set_xlim(0, 100)
    ax.set_ylim(min(b[1] for b in boxes.values()) - 3, 100)
    ax.axis("off")
    for key, (x, y, w, h, text, color) in boxes.items():
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.5",
                                    fc=color, ec="#333333", lw=0.9))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=9.5, wrap=True)
    for a, b in arrows:
        xa, ya, wa, ha = boxes[a][:4]
        xb, yb, wb, hb = boxes[b][:4]
        if abs(ya - yb) < 1 and xb > xa:  # same row, left to right
            start, end = (xa + wa, ya + ha / 2), (xb, yb + hb / 2)
        elif abs(ya - yb) < 1:  # same row, right to left
            start, end = (xa, ya + ha / 2), (xb + wb, yb + hb / 2)
        else:  # different rows: top-to-bottom
            start, end = (xa + wa / 2, ya), (xb + wb / 2, yb + hb)
        ax.annotate("", xy=end, xytext=start, arrowprops=dict(arrowstyle="-|>", color="#333333", lw=1))
    save(fig, name)


L1, L2, L3 = "#dbe6f1", "#f3e3c3", "#e3efe2"
block_diagram("block_overall.png", {
    "rbi": (2, 78, 18, 14, "RBI website\n(381 Master\nDirections)", L1),
    "scr": (27, 78, 18, 14, "Scraper, PDF text\nextraction,\nsegmentation", L1),
    "meta": (52, 78, 20, 14, "Metadata: entity\nclass x subject\nfamily matrix", L1),
    "cand": (79, 78, 19, 14, "Obligation\ncandidate\nextraction", L1),
    "match": (79, 52, 19, 14, "Cross-class\nmatching (bge\n+ lexical)", L2),
    "ann": (52, 52, 20, 14, "Expert annotation,\nretest, 3-rater\nreliability", L2),
    "bench": (27, 52, 18, 14, "Benchmark\nT1-T4", L2),
    "sup": (2, 52, 18, 14, "FAQ, enforcement,\nAmendment\nDirections", L2),
    "rag": (2, 22, 22, 16, "Class- and date-aware\nRAG: BM25 + dense\n+ RRF, filters,\nLLM, NLI verifier", L3),
    "cmp": (30, 22, 20, 16, "Structured\ncomparator\n(13 fields + fixed\nrule)", L3),
    "eval": (56, 22, 20, 16, "Evaluation harness:\nF1, nDCG, kappa,\nbootstrap CIs", L3),
    "out": (81, 22, 17, 16, "Paper, release,\ndemo, audit\ngenerator", L3),
}, [("rbi", "scr"), ("scr", "meta"), ("meta", "cand"), ("cand", "match"), ("match", "ann"), ("ann", "bench"),
    ("sup", "bench"), ("bench", "rag"), ("rag", "cmp"), ("cmp", "eval"), ("eval", "out")], (9, 5.6))

block_diagram("block_auditgen.png", {
    "prof": (2, 70, 20, 18, "Entity profile\n(class, as-of date,\nactivities, last\nreview)", L1),
    "api": (30, 70, 22, 18, "FastAPI backend\n(127.0.0.1 only)", L1),
    "corp": (60, 70, 18, 18, "Corpus snapshot\n+ amendment\nindex", L1),
    "fresh": (84, 70, 14, 18, "Freshness\ncheck,\nrefresh", L1),
    "reg": (2, 38, 17, 18, "Applicability\nregister", L2),
    "chg": (22, 38, 17, 18, "Change-impact\nlog", L2),
    "cal": (42, 38, 16, 18, "Compliance\ncalendar", L2),
    "dif": (61, 38, 17, 18, "Cross-class\ndifferential", L2),
    "gap": (81, 38, 17, 18, "Policy gap\nanalysis\n(local)", L2),
    "ai": (2, 6, 30, 18, "Local AI assistant (Ollama):\ncited sentences, NLI check,\nnumbers must match source", L3),
    "rev": (38, 6, 24, 18, "Reviewer workflow\nand sign-off", L3),
    "exp": (68, 6, 30, 18, "Exports: Excel, DOCX, PDF,\nICS, JSON audit trail", L3),
}, [("prof", "api"), ("api", "corp"), ("corp", "fresh"), ("api", "reg"), ("api", "chg"), ("api", "cal"),
    ("api", "dif"), ("api", "gap"), ("ai", "rev"),
    ("rev", "exp")], (9, 5))
print("figures written to", OUT)

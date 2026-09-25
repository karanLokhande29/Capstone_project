#!/usr/bin/env python3
"""Generate notebooks/phase1-corpus-repair.ipynb with nbformat, and validate it.

The notebook is a thin wrapper: every cell calls into `src/` or
`scripts/run_harvest.py`, and no pipeline logic lives in it. Generating it from
here rather than editing JSON by hand means the cells are ordinary Python that
`ast.parse` can check in CI, and that a change to the repair never has to be
mirrored by hand into a notebook nobody runs locally.
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf

REPO_URL = "https://github.com/karanLokhande29/Capstone_project.git"
BRANCH = "wip/P1-004"

MD_INTRO = f"""# Phase 1 — P1-004: Corpus repair

**RBI-ObliBench / Agentic RAG compliance system**

Recovers the **81 Master Directions** the first harvest lost to what looks like
a session-level block, **without re-downloading the 299** that succeeded, then
re-extracts, re-segments, and re-runs the matrix, QA and the cross-class
alignment check.

The losses were not spread evenly. They fell on the two entity classes a
cross-class benchmark most depends on:

| Entity class | Missing / total |
|---|---|
| Commercial Banks | 35 / 44 |
| Small Finance Banks | 31 / 40 |
| Consumer Education and Protection | 7 / 7 |
| Payments Banks | 4 / 27 |
| Both Banker-to-Government headings | 2 / 2 each |

**Two hard stops** run before anything is packaged, because the repair
re-segments the whole corpus and three people's annotations are keyed to
paragraph ids:

* **stable-ID check** — the 299 already-good documents must re-segment to
  byte-identical paragraph fingerprints;
* **pilot-join check** — all 18 pilot spans must still resolve to the same
  paragraph *and the same text*.

A repair that fails either one is not published. Both failures are invisible in
every ordinary metric — the paragraph counts still look right — which is
exactly why they are asserted rather than eyeballed.

Requires **Internet: On** and the `rbi-oblibench-corpus-v1` Dataset attached.

> Branch: `{BRANCH}`. Change to `main` after the Phase 1 Audit merge.
"""

CELL_CLONE = f'''import os, subprocess, sys

REPO_URL = "{REPO_URL}"
BRANCH = "{BRANCH}"   # TODO: switch to "main" after the P1-004 merge
REPO_DIR = "/kaggle/working/Capstone_project"

if os.path.isdir(os.path.join(REPO_DIR, ".git")):
    # /kaggle/working commonly survives across "Run All" within a session, so a
    # directory left from an earlier run must not be silently reused — always
    # sync to the latest commit on BRANCH rather than trusting what is there.
    subprocess.run(["git", "-C", REPO_DIR, "fetch", "--depth", "1", "origin", BRANCH], check=True)
    subprocess.run(["git", "-C", REPO_DIR, "reset", "--hard", f"origin/{{BRANCH}}"], check=True)
else:
    subprocess.run(["git", "clone", "--depth", "1", "--branch", BRANCH, REPO_URL, REPO_DIR],
                   check=True)

os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR)

commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                        capture_output=True, text=True, check=True).stdout.strip()
print(f"running {{BRANCH}} @ {{commit}}")
'''

CELL_DEPS = '''import subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pdfplumber"], check=True)

import pdfplumber, bs4, requests
print("pdfplumber", pdfplumber.__version__)
print("beautifulsoup4", bs4.__version__)
print("requests", requests.__version__)
print("python", sys.version.split()[0])
'''

CELL_INPUTS = '''import shutil
from pathlib import Path

WORKING = Path("/kaggle/working")
DATA = WORKING / "data"

# PathResolver resolves to /kaggle/working/data/... and /kaggle/working/reports/...
# The older notebooks copied inputs to /kaggle/working/Capstone_project/data,
# which the resolver never looks at, so every read silently found nothing.
source_root = None
import_dir = None
for base in sorted(Path("/kaggle/input").glob("*")):
    for candidate in [base, *sorted(p for p in base.rglob("*") if p.is_dir())]:
        if (candidate / "metadata" / "document_manifest.jsonl").is_file():
            source_root = candidate
            break
        if (candidate / "data" / "metadata" / "document_manifest.jsonl").is_file():
            source_root = candidate / "data"
            break
    if source_root:
        break

for base in sorted(Path("/kaggle/input").glob("*")):
    pdfs = [p for p in base.rglob("*") if p.suffix.lower() == ".pdf"]
    if pdfs and base != (source_root.parent if source_root else None):
        import_dir = base
        print(f"found {len(pdfs)} hand-downloaded PDF(s) in {base}")
        break

assert source_root is not None, "attach the rbi-oblibench-corpus-v1 Dataset"
print("corpus input:", source_root)

DATA.mkdir(parents=True, exist_ok=True)
for name in ("metadata", "extracted", "processed", "matrix"):
    src = source_root / name
    if src.is_dir():
        shutil.copytree(src, DATA / name, dirs_exist_ok=True)

candidates = source_root / "benchmark" / "pilot_candidates.jsonl"
if candidates.is_file():
    (DATA / "benchmark").mkdir(parents=True, exist_ok=True)
    shutil.copy2(candidates, DATA / "benchmark" / "pilot_candidates.jsonl")

manifest_rows = sum(
    1 for line in (DATA / "metadata" / "document_manifest.jsonl").read_text().splitlines()
    if line.strip()
)
processed_docs = len(list((DATA / "processed").glob("md_*.jsonl")))
print(f"manifest rows: {manifest_rows}   processed documents: {processed_docs}")
assert manifest_rows == 380, f"expected 380 manifest rows, got {manifest_rows}"
assert processed_docs == 299, f"expected 299 processed documents, got {processed_docs}"
'''

CELL_TESTS = '''import subprocess, sys
result = subprocess.run([sys.executable, "-m", "pytest", "-q"], capture_output=True, text=True)
print(result.stdout[-3000:])
assert result.returncode == 0, "tests failed — stopping before touching the corpus"
'''

CELL_DIAGNOSE = '''import subprocess, sys
# Two fetches per document: one cold, one after a listing warm-up. This turns
# "the failures look session-level" from an inference into a measurement.
subprocess.run([sys.executable, "scripts/run_harvest.py", "diagnose",
                "--from-failures", "--max", "5"], check=False)
'''

CELL_REPAIR = '''import subprocess, sys

cmd = [sys.executable, "scripts/run_harvest.py", "repair", "--max-requests", "150"]
if import_dir is not None:
    cmd += ["--import-dir", str(import_dir)]

print(" ".join(cmd))
result = subprocess.run(cmd, capture_output=True, text=True)
print(result.stdout[-8000:])
if result.returncode != 0:
    print(result.stderr[-4000:])
assert result.returncode == 0, "repair stopped — read the stage it stopped at above"
'''

CELL_EXPORT = '''import csv, subprocess, sys
subprocess.run([sys.executable, "scripts/run_harvest.py", "export-missing"], check=True)

rows = list(csv.DictReader(open("reports/p1004_missing_documents.csv")))
print(f"still missing: {len(rows)}")
if rows:
    print("""
STILL MISSING — the host would not serve these to an automated client.

  1. Download each `source_url` below in a normal browser, keeping the
     original filename.
  2. Upload them together as a private Kaggle Dataset `rbi-missing-pdfs`.
  3. Add Input that Dataset to this notebook and Run All again.

No evasion is attempted here: a manual browser download is the honest route.
""")
    for r in rows[:20]:
        print(f"  {r['document_id']}  {r['entity_class_raw']:<40} {r['source_url']}")
    if len(rows) > 20:
        print(f"  ... and {len(rows) - 20} more in reports/p1004_missing_documents.csv")
'''

CELL_MATRIX = '''import subprocess, sys
subprocess.run([sys.executable, "scripts/run_matrix.py", "all"], check=True)
subprocess.run([sys.executable, "scripts/run_matrix.py", "report"], check=True)
'''

CELL_QA = '''import json, subprocess, sys

# QA and the Week-2 checks only. `pilot` and `ingest` are NOT run here: the
# filled task files live on Karan's machine and were never uploaded, so a pilot
# run on Kaggle would regenerate them blank.
subprocess.run([sys.executable, "scripts/run_annotation.py", "qa"], check=True)
subprocess.run([sys.executable, "scripts/run_annotation.py", "checks"], check=True)

from src.benchmark.alignment_check import cross_class_alignment
from src.common.config import load_config
from src.common.paths import PathResolver

cfg = load_config()
resolver = PathResolver.from_config(cfg)

runs = {
    "(a) as configured — coverage-ranked cells": cross_class_alignment(cfg, resolver=resolver),
    "(b) fixed: CB x SFB x PB": cross_class_alignment(cfg, resolver=resolver, fixed_sample=True),
}

print(f"{'run':<44} {'para':>8} {'base':>8} {'sect':>8} {'base':>8} {'n':>6}  trigger")
for name, r in runs.items():
    ent = r["entity_class_axis"]; sub = r["subject_family_axis_derived"]
    def rate(block, level):
        v = block[level]["alignment_rate"]
        return f"{v:.1%}" if isinstance(v, float) else "n/a"
    n = ent["paragraph_level"].get("positions_compared", "?")
    print(f"{name:<44} {rate(ent,'paragraph_level'):>8} {rate(sub,'paragraph_level'):>8} "
          f"{rate(ent,'section_level'):>8} {rate(sub,'section_level'):>8} {n:>6}  "
          f"{r['trigger_fired']}")

with open("reports/p1004_alignment_runs.json", "w") as fh:
    json.dump({k: v for k, v in runs.items()}, fh, indent=2, default=str)
'''

CELL_PACKAGE = '''import sys
sys.path.insert(0, ".")
from scripts.package_p1004 import build_return_zip, build_corpus_v2_zip

root = __import__("pathlib").Path("/kaggle/working")
ret = build_return_zip(root, root / "p1004_return.zip")
v2 = build_corpus_v2_zip(root, root / "rbi-oblibench-corpus-v2.zip")

import zipfile
for path in (ret, v2):
    names = zipfile.ZipFile(path).namelist()
    assert not any("annotation_" in n for n in names), f"{path.name} carries annotation files"
    print(f"{path.name}: {len(names)} files, {path.stat().st_size / 1e6:.1f} MB")

ret_names = zipfile.ZipFile(ret).namelist()
assert not any(n.startswith("data/benchmark") for n in ret_names)
assert not any(n.startswith("data/cache") for n in ret_names)
print("\\nboth zips clean — download them from the /kaggle/working output panel")
'''

CELL_SUMMARY = '''import json
from pathlib import Path

def load(name):
    p = Path("reports") / name
    return json.loads(p.read_text()) if p.is_file() else {}

repair = load("phase1_akash_repair_metrics.json").get("repair", {})
diag = load("phase1_akash_diagnose_metrics.json").get("diagnose", {})
harvest = repair.get("harvest", {})

print("=== P1-004 SUMMARY (Section Z) ===\\n")
print(f"diagnosis          : warm-up helped = {diag.get('warm_up_helped')}")
print(f"                     {diag.get('conclusion', 'not run')}")
print(f"discovered         : {harvest.get('documents_discovered')}")
print(f"carried unchanged  : {harvest.get('records_carried_unchanged')}")
print(f"downloaded now     : {harvest.get('downloads_successful')}")
print(f"manually imported  : {len(harvest.get('manual_import_ids', []))}")
print(f"still failed       : {harvest.get('downloads_failed')}")
print(f"newly listed       : {harvest.get('new_since_previous_harvest')}")
print(f"no longer listed   : {harvest.get('no_longer_listed')}")

before = repair.get("coverage_before", {}).get("by_entity_class", {})
after = repair.get("coverage_after", {}).get("by_entity_class", {})
print("\\ncoverage by entity class (before -> after):")
for cls in sorted(set(before) | set(after)):
    b, a = before.get(cls, {}), after.get(cls, {})
    flag = "  <-- BELOW 90%" if a.get("rate", 1) < 0.90 else ""
    print(f"  {b.get('downloaded','?'):>3}/{b.get('total','?'):<3} -> "
          f"{a.get('downloaded','?'):>3}/{a.get('total','?'):<3} "
          f"({a.get('rate', 0):6.1%})  {cls}{flag}")

print(f"\\nextraction         : {repair.get('extract', {})}")
print(f"paragraphs         : {repair.get('segment', {}).get('paragraphs_written', '?')}")
print(f"stable-ID check    : {repair.get('stable_id_check', {}).get('passed')}")
print(f"pilot-join check   : {repair.get('pilot_join_check', {}).get('passed')}")
print(f"still missing      : {len(repair.get('still_missing', []))}")
'''


def build() -> Path:
    nb = nbf.v4.new_notebook()
    cells = [
        nbf.v4.new_markdown_cell(MD_INTRO),
        nbf.v4.new_markdown_cell("## 1. Clone the repository"),
        nbf.v4.new_code_cell(CELL_CLONE),
        nbf.v4.new_markdown_cell("## 2. Dependencies"),
        nbf.v4.new_code_cell(CELL_DEPS),
        nbf.v4.new_markdown_cell(
            "## 3. Attach the corpus input\n\n"
            "Copies the attached Dataset into `/kaggle/working/data/`, which is where "
            "`PathResolver` actually looks, and asserts the corpus arrived intact before "
            "anything is changed."
        ),
        nbf.v4.new_code_cell(CELL_INPUTS),
        nbf.v4.new_markdown_cell(
            "## 4. Tests\n\nStops the run on any failure: a repair driven by broken code "
            "is worse than no repair, because it produces a corpus that looks repaired."
        ),
        nbf.v4.new_code_cell(CELL_TESTS),
        nbf.v4.new_markdown_cell(
            "## 5. Diagnose the block\n\nFetches a few failed documents cold, then after a "
            "listing warm-up, and records exactly what comes back."
        ),
        nbf.v4.new_code_cell(CELL_DIAGNOSE),
        nbf.v4.new_markdown_cell(
            "## 6. Repair\n\nOnly-missing harvest with payload retries -> manual import -> "
            "extract new only -> full re-segmentation -> **stable-ID and pilot-join checks** "
            "-> cross-references -> coverage. Stops at the first failed check."
        ),
        nbf.v4.new_code_cell(CELL_REPAIR),
        nbf.v4.new_markdown_cell("## 7. Anything still missing"),
        nbf.v4.new_code_cell(CELL_EXPORT),
        nbf.v4.new_markdown_cell("## 8. Matrix v1 on the repaired corpus"),
        nbf.v4.new_code_cell(CELL_MATRIX),
        nbf.v4.new_markdown_cell(
            "## 9. QA and the Week-2 checks\n\nTwo alignment runs: **(a)** the configured "
            "coverage-ranked sample, and **(b)** a fixed sample pinned to Commercial Banks x "
            "Small Finance Banks x Payments Banks. Run (a) picks whichever cells are best "
            "populated, which before the repair could not include the two classes that were "
            "most damaged — so (b) is what shows whether the repair changed the answer."
        ),
        nbf.v4.new_code_cell(CELL_QA),
        nbf.v4.new_markdown_cell(
            "## 10. Package for the return trip\n\nNeither zip may carry an annotation file. "
            "Kaggle never had the filled task files, so a returning `data/benchmark` could "
            "only overwrite real work with nothing."
        ),
        nbf.v4.new_code_cell(CELL_PACKAGE),
        nbf.v4.new_markdown_cell("## 11. Summary (Section Z)"),
        nbf.v4.new_code_cell(CELL_SUMMARY),
    ]
    nb["cells"] = cells
    nb["metadata"] = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
    }

    nbf.validate(nb)
    out = Path("notebooks/phase1-corpus-repair.ipynb")
    out.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(nb, out)
    return out


if __name__ == "__main__":
    path = build()
    print(f"wrote {path}")

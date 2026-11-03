#!/usr/bin/env python3
"""Generate notebooks/phase2-p2003-supplementary.ipynb (P2-003 §A4).

A thin wrapper, like the P2-002 one: every cell calls into ``src/`` or
``scripts/run_supplementary.py``; no pipeline logic lives in the notebook.
The v4 notebook JSON is written directly. The tests ``ast.parse`` every code cell.
"""

from __future__ import annotations

import json
from pathlib import Path

BRANCH = "wip/P2-003"
REPO_URL = "https://github.com/karanLokhande29/Capstone_project.git"

MD_INTRO = """# Phase 2 — P2-003: Supplementary sources (harvest on Kaggle)

Harvests the four supplementary sources with full provenance:

* **RBI FAQs:** the index, then every topic page, split into Q&A items.
* **Enforcement:** monetary-penalty press releases, from the year listings in config.
* **Amendment Directions:** post-consolidation (on or after 2025-11-28) notifications.
* **Circulars withdrawn:** the online withdrawn-circulars list. (The local repeal annexes are extracted in Part C.)

Every response is validated. A CAPTCHA, error or unexpected page is recorded as a failure with its reason and is
**never stored as content**. Requests are rate-limited (`supplementary.rate_limit_sec`, at least 1 s).
Linking and the alignment sheet run locally in Part C. No LLM or embedding model is used.

**Settings:** Internet **On**. No GPU. **Inputs:** `rbi-oblibench-code-p2003`, `rbi-oblibench-corpus-v2-karan`.

**Run All interactively**, and read the discovery smoke output (section 4) before the full fetch continues.
"""

CELL_CODE = f'''import hashlib, json, os, shutil, subprocess, sys, zipfile
from pathlib import Path

BRANCH = "{BRANCH}"      # used ONLY if the rbi-oblibench-code-p2003 Dataset is not attached
REPO_URL = "{REPO_URL}"
CODE_DIR = Path("/kaggle/working/p2003_code")
INPUT = Path("/kaggle/input")

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

code_zip = next(iter(sorted(INPUT.rglob("p2003_code.zip"))), None)
unpacked = next((p.parent for p in sorted(INPUT.rglob("MANIFEST.json"))
                 if (p.parent / "src" / "supplementary" / "faq.py").is_file()), None)
if CODE_DIR.exists():
    shutil.rmtree(CODE_DIR)
if code_zip is not None:
    CODE_SOURCE = f"dataset zip {{code_zip}}  sha256={{sha256(code_zip)}}"
    with zipfile.ZipFile(code_zip) as zf:
        zf.extractall(CODE_DIR)
elif unpacked is not None:
    # Kaggle unpacks uploaded zips; the per-file hashes below then stand in for the zip hash.
    CODE_SOURCE = f"dataset (unpacked by Kaggle) {{unpacked}}"
    shutil.copytree(unpacked, CODE_DIR)
else:
    subprocess.run(["git", "clone", "--depth", "1", "--branch", BRANCH, REPO_URL, str(CODE_DIR)], check=True)
    commit = subprocess.run(["git", "-C", str(CODE_DIR), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=True).stdout.strip()
    CODE_SOURCE = f"git {{BRANCH}} @ {{commit}}"

manifest_path = CODE_DIR / "MANIFEST.json"
if manifest_path.is_file():
    manifest = json.loads(manifest_path.read_text())
    bad = [f for f, h in manifest["files"].items() if sha256(CODE_DIR / f) != h]
    assert not bad, f"code files differ from MANIFEST.json: {{bad[:5]}}"
    CODE_SOURCE += f"  | manifest sha256={{sha256(manifest_path)}}  ({{len(manifest['files'])}} files verified)"

os.chdir(CODE_DIR)
sys.path.insert(0, str(CODE_DIR))
print("code source:", CODE_SOURCE)
'''

CELL_INPUTS = '''import shutil, sys, time
from pathlib import Path
import bs4, requests
from lxml import etree

WORKING = Path("/kaggle/working")
DATA = WORKING / "data"
corpus_root = None
for p in sorted(Path("/kaggle/input").rglob("document_manifest.jsonl")):
    if p.parent.name == "metadata" and (p.parent.parent / "processed").is_dir():
        corpus_root = p.parent.parent
        break
assert corpus_root is not None, "attach rbi-oblibench-corpus-v2-karan"
for name in ("metadata", "processed"):
    shutil.copytree(corpus_root / name, DATA / name, dirs_exist_ok=True)

from scripts import run_supplementary as R

cfg, sc, resolver, logger = R.setup()
print("resolver:", resolver.describe()["mode"], resolver.working_root, "| rate limit", sc.rate_limit_sec, "s")
PREFLIGHT = R.preflight(sc, *R.load_corpus(resolver))   # A1: stops unless this is the P1-004 corpus
print("A1 preflight passed:", PREFLIGHT)
VERSIONS = {"python": sys.version.split()[0], "requests": requests.__version__, "bs4": bs4.__version__,
            "lxml": ".".join(map(str, etree.LXML_VERSION))}
ctx = R.context(cfg, sc, resolver, logger)
T0 = time.time()
'''

CELL_DISCOVER = '''import json
DISCOVERY = R.run_discover(ctx, R.SOURCES)
for s, d in DISCOVERY.items():
    extra = {k: v for k, v in d.items() if k not in ("targets", "listing_pages", "near_miss_examples", "notes")}
    print(s, json.dumps(extra, default=str)[:600])
'''

CELL_SMOKE = '''SMOKE = R.smoke(ctx, DISCOVERY)
print(json.dumps(SMOKE, indent=2, default=str))
if not SMOKE["ok"]:
    raise SystemExit("STOP (discovery smoke): " + " | ".join(SMOKE["stops"]) +
                     "\\nCopy this output to Claude Code. Do not re-run blindly.")
print("smoke OK: every source discovered items and fetched with < 50% failures")
'''

CELL_FETCH = '''FETCH = R.run_fetch(ctx, R.SOURCES)
for s, f in FETCH.items():
    print(s, f)
STOPPED = {s: f["stopped"] for s, f in FETCH.items() if f.get("stopped")}
if STOPPED:
    print("WARNING, sources stopped at >= 50% failures (reported, not hidden):", STOPPED)
'''

CELL_PARSE = '''PARSE = R.run_parse(ctx, R.SOURCES)          # local repeal annexes are added in Part C
AUDIT = R.audit_stored(ctx, R.SOURCES)
print({s: {k: v for k, v in p.items() if k != "topic_records"} for s, p in PARSE.items()})
print(AUDIT)
bad = {s: a for s, a in AUDIT.items() if a["invalid_content"] or a["hash_mismatch"]}
assert not bad, f"STOP: a stored page is a CAPTCHA/error page or fails its hash: {bad}"
'''

CELL_WRITE = '''import zipfile
HARVEST = R.harvest_metrics(ctx, R.SOURCES, PARSE)
metrics = {"preflight": PREFLIGHT, "smoke": SMOKE, "fetch": FETCH, "audit": AUDIT, "harvest": HARVEST,
           "parse": {s: {k: v for k, v in p.items() if k != "topic_records"} for s, p in PARSE.items()},
           "kaggle": {"runtime_sec": round(time.time() - T0, 1), "code_source": CODE_SOURCE, "versions": VERSIONS,
                      "rate_limit_sec": sc.rate_limit_sec}}
zpath = R.write_return_zip(ctx, Path("/kaggle/working") / R.RETURN_ZIP, metrics)
names = zipfile.ZipFile(zpath).namelist()
assert not any("annotation_" in n for n in names), "annotation file in the return zip"
print(R.RETURN_ZIP, len(names), "files", round(zpath.stat().st_size / 1e6, 1), "MB")
'''

CELL_SUMMARY = '''print("=== P2-003 harvest summary (Section Z) ===")
for s, h in HARVEST.items():
    print(s, "| discovered", h["discovered"], "| stored", h["stored_pages"], "| failures", h["failure_reasons"],
          "| items", h["items"], "| by era", h["items_by_era"])
print("FAQ topics without HTML Q&A:", HARVEST["faq"].get("faq_topics_without_html_items"))
print("enforcement entity-class resolution:", HARVEST["enforcement"].get("entity_class_resolution_rate"))
print("online withdrawn list found:", HARVEST["withdrawn"].get("online_list_found"))
print("runtime:", metrics["kaggle"]["runtime_sec"], "s")
print("\\nDownload p2003_return.zip from /kaggle/working and put it in the repo root.")
'''


def _code(src: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
            "source": src.splitlines(keepends=True)}


def _md(src: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": src.splitlines(keepends=True)}


CODE_CELLS = (CELL_CODE, CELL_INPUTS, CELL_DISCOVER, CELL_SMOKE, CELL_FETCH, CELL_PARSE, CELL_WRITE, CELL_SUMMARY)


def build(out: Path | str) -> Path:
    cells = [
        _md(MD_INTRO),
        _md("## 1. Code\nFrom the `rbi-oblibench-code-p2003` Dataset: log its SHA-256 and check every file "
            "against MANIFEST.json. If that Dataset is not attached, clone `BRANCH` instead."),
        _code(CELL_CODE),
        _md("## 2. Inputs and the A1 preflight\nStops unless this is the P1-004 corpus (381 Directions, "
            "76,188 paragraphs, 19 raw classes)."),
        _code(CELL_INPUTS),
        _md("## 3. Discovery\nEvery source's `discover()`. Counts, near misses and listing failures are printed."),
        _code(CELL_DISCOVER),
        _md("## 4. Discovery smoke: 5 items per source\n**Read this output.** It stops if a source discovered 0 "
            "items or its smoke fetch failed for 50% or more; it never falls back silently."),
        _code(CELL_SMOKE),
        _md("## 5. Full fetch\nOnly-missing: a stored page is never re-fetched or overwritten, so after a dead "
            "session Run All resumes. A source stops at >= 50% failures and is reported."),
        _code(CELL_FETCH),
        _md("## 6. Parse, and audit every stored page\nNo stored page may be a CAPTCHA or error page."),
        _code(CELL_PARSE),
        _md("## 7. Write `p2003_return.zip`\nRaw pages, parsed items, manifests, discovery and failure logs, "
            "`p2003_metrics_v1.json`. No annotation file."),
        _code(CELL_WRITE),
        _md("## 8. Summary"),
        _code(CELL_SUMMARY),
    ]
    nb = {"cells": cells,
          "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                       "language_info": {"name": "python"}},
          "nbformat": 4, "nbformat_minor": 5}
    for i, cell in enumerate(nb["cells"]):
        cell["id"] = f"p2003-{i:02d}"
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    print(build(Path(__file__).resolve().parents[1] / "notebooks" / "phase2-p2003-supplementary.ipynb"))

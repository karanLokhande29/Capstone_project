#!/usr/bin/env python3
"""Generate notebooks/phase2-p2002-matching.ipynb (P2-002 §A9).

The notebook is a thin wrapper, like the P1-004 one: every cell calls into
``src/`` or ``scripts/run_matching.py``, and no pipeline logic lives in it.
nbformat is not installed on the authoring machine, so the v4 notebook JSON is
written directly. The tests ``ast.parse`` every code cell.
"""

from __future__ import annotations

import json
from pathlib import Path

BRANCH = "wip/P2-002"
REPO_URL = "https://github.com/karanLokhande29/Capstone_project.git"

MD_INTRO = """# Phase 2 — P2-002: Cross-class obligation matching (Stage 2 on Kaggle)

For every kept P2-001 candidate (rules v4) in a **core** entity class, this notebook finds the best counterparts
in each other core class's Directions on the same subject family:

* **Stage 1:** repeated wording (near-duplicate clusters).
* **Stage 2:** semantic similarity with `BAAI/bge-base-en-v1.5`, pinned to an exact revision, max cosine over
  matching units.
* **Baseline:** TF-IDF cosine on the same units.
* **Leakage check:** 200 seeded candidates searched with no blocking.

It produces **candidate matches only**, with no labels and no threshold.

**Settings:** Accelerator GPU T4, Internet On. **Inputs:** `rbi-oblibench-corpus-v2-karan`,
`rbi-oblibench-candidates-v4`, `rbi-oblibench-code-p2002`.

**Run All interactively**, and read the smoke-run output (cell 6) before the full run continues.
"""

CELL_CODE = f'''import hashlib, json, os, shutil, subprocess, sys, zipfile
from pathlib import Path

BRANCH = "{BRANCH}"      # used ONLY if the rbi-oblibench-code-p2002 Dataset is not attached
REPO_URL = "{REPO_URL}"
CODE_DIR = Path("/kaggle/working/p2002_code")
INPUT = Path("/kaggle/input")

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

code_zip = next(iter(sorted(INPUT.rglob("p2002_code.zip"))), None)
unpacked = next((p.parent for p in sorted(INPUT.rglob("MANIFEST.json"))
                 if (p.parent / "src" / "benchmark" / "matching.py").is_file()), None)
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

CELL_DEPS = '''import subprocess, sys
try:
    import sentence_transformers
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "sentence-transformers"], check=True)
    import sentence_transformers
import numpy, sklearn, torch, huggingface_hub

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
GPU = torch.cuda.get_device_name(0) if DEVICE == "cuda" else None
if DEVICE == "cpu":
    print("WARNING: no GPU attached; running on CPU (the unit count is small enough)")
VERSIONS = {"python": sys.version.split()[0], "sentence_transformers": sentence_transformers.__version__,
            "torch": torch.__version__, "numpy": numpy.__version__, "sklearn": sklearn.__version__,
            "huggingface_hub": huggingface_hub.__version__}
print(DEVICE, GPU, VERSIONS)
'''

CELL_INPUTS = '''import json, random, shutil
from pathlib import Path

WORKING = Path("/kaggle/working")
DATA = WORKING / "data"

corpus_root = None
for p in sorted(Path("/kaggle/input").rglob("document_manifest.jsonl")):
    if p.parent.name == "metadata" and (p.parent.parent / "processed").is_dir():
        corpus_root = p.parent.parent
        break
assert corpus_root is not None, "attach rbi-oblibench-corpus-v2-karan"
cand_file = next(iter(sorted(Path("/kaggle/input").rglob("t1_candidates_v4.jsonl"))), None)
assert cand_file is not None, "attach rbi-oblibench-candidates-v4"
print("corpus:", corpus_root, "| candidates:", cand_file)

for name in ("metadata", "processed", "matrix"):
    shutil.copytree(corpus_root / name, DATA / name, dirs_exist_ok=True)
(DATA / "benchmark" / "candidates").mkdir(parents=True, exist_ok=True)
shutil.copy2(cand_file, DATA / "benchmark" / "candidates" / "t1_candidates_v4.jsonl")

# A1 preflight, before anything else runs.
manifest_rows = sum(1 for l in (DATA / "metadata" / "document_manifest.jsonl").open() if l.strip())
proc = sorted((DATA / "processed").glob("md_*.jsonl"))
paragraphs = {}
for f in proc:
    for line in f.open(encoding="utf-8"):
        if line.strip():
            row = json.loads(line)
            paragraphs[row["paragraph_id"]] = row.get("text") or ""
print(f"manifest {manifest_rows}  processed docs {len(proc)}  paragraphs {len(paragraphs)}")
assert manifest_rows == 381 and len(proc) == 381 and len(paragraphs) == 76188, "corpus is not the P1-004 corpus"

from src.benchmark.candidates import load_candidates
cands = load_candidates(DATA / "benchmark" / "candidates" / "t1_candidates_v4.jsonl")
kept = [c for c in cands if not c.exclusion_reason]
assert len(kept) == 28694, f"expected 28,694 kept v4 candidates, got {len(kept)}"
check = random.Random(20260926).sample(kept, 200)
mismatch = [c.candidate_id for c in check if paragraphs.get(c.paragraph_id) != c.span_text]
assert not mismatch, f"candidate text differs from the corpus paragraph: {mismatch[:5]}"
print("A1 preflight passed: 28,694 kept candidates; 200/200 spot-checked spans match the corpus")
'''

CELL_MODEL = '''from huggingface_hub import model_info
from sentence_transformers import SentenceTransformer
from src.common.config import load_config
from src.common.paths import PathResolver
from src.benchmark.matching import MatchingConfig

cfg = load_config()
resolver = PathResolver.from_config(cfg)
mc = MatchingConfig.from_cfg(cfg)
print("resolver:", resolver.describe()["mode"], resolver.working_root)

try:
    resolved = model_info(mc.model_id, revision=mc.model_revision).sha
    model = SentenceTransformer(mc.model_id, revision=mc.model_revision, device=DEVICE)
except Exception as exc:  # no fallback model, by design
    raise SystemExit(f"STOP: could not load {mc.model_id} at revision {mc.model_revision}: {exc}")
assert resolved == mc.model_revision, f"STOP: revision resolved to {resolved}, pinned {mc.model_revision}"
model.max_seq_length = mc.max_seq_length
print("model", mc.model_id, "revision", resolved, "max_seq_length", model.max_seq_length)

def embed(texts):
    return model.encode(list(texts), batch_size=mc.batch_size, normalize_embeddings=True,
                        convert_to_numpy=True, show_progress_bar=False)

def token_lengths(texts):
    return [len(ids) for ids in model.tokenizer(list(texts), add_special_tokens=True, truncation=False)["input_ids"]]
'''

CELL_SMOKE = '''import time
from scripts.run_matching import kaggle_run

t = time.time()
smoke = kaggle_run(cfg, resolver, embed, model_id=mc.model_id, model_revision=mc.model_revision,
                   token_lengths=token_lengths, smoke=True)
recs = smoke["records"]
scored = [r for r in recs if r["status"] == "scored"]
SMOKE_SUMMARY = {
    "candidates": smoke["accounting"]["eligible"] + smoke["accounting"]["excluded_no_subject_family_core"],
    "eligible": smoke["accounting"]["eligible"],
    "units": smoke["unit_metrics"]["units_total"],
    "records": len(recs),
    "status": smoke["match_metrics"]["status_overall"],
    "stage1_cross_class_clusters": smoke["stage1"]["summary"]["clusters_cross_class"],
    "top1_agreement": smoke["score_stats"]["top1_agreement_semantic_vs_lexical"],
    "runtime_sec": round(time.time() - t, 1),
}
print(json.dumps(SMOKE_SUMMARY, indent=2))
assert len(recs) == SMOKE_SUMMARY["eligible"] * 10, "one record per (source, other core class)"
assert all(1 <= len(r["top_targets"]) <= mc.top_k for r in scored)
assert all(-1.0001 <= t["semantic_score"] <= 1.0001 for r in scored for t in r["top_targets"])
print("smoke run OK: check the numbers above, then let the full run continue")
'''

CELL_FULL = '''import time
t0 = time.time()
result = kaggle_run(cfg, resolver, embed, model_id=mc.model_id, model_revision=mc.model_revision,
                    token_lengths=token_lengths, checkpoint_dir="/kaggle/working/p2002_ckpt")
FULL_RUNTIME = round(time.time() - t0, 1)
print("full run:", FULL_RUNTIME, "s |", result["match_metrics"]["status_overall"])
'''

CELL_WRITE = '''import shutil, zipfile
from pathlib import Path
from scripts.run_matching import write_stage2_outputs, build_return_zip, write_embeddings, RETURN_ZIP, EMBEDDINGS_FILE

out = Path("/kaggle/working/p2002_out")
kaggle = {"device": DEVICE, "gpu": GPU, "runtime_sec_full": FULL_RUNTIME, "model_id": mc.model_id,
          "model_revision": mc.model_revision, "code_source": CODE_SOURCE, "versions": VERSIONS,
          "smoke": SMOKE_SUMMARY}
metrics = write_stage2_outputs(result, out, {"kaggle": kaggle})
zpath = build_return_zip(out)
shutil.copy2(zpath, Path("/kaggle/working") / RETURN_ZIP)
emb = write_embeddings(result, Path("/kaggle/working") / EMBEDDINGS_FILE)
names = zipfile.ZipFile(Path("/kaggle/working") / RETURN_ZIP).namelist()
assert not any("annotation_" in n for n in names), "annotation file in the return zip"
print(RETURN_ZIP, names, "|", EMBEDDINGS_FILE, round(emb.stat().st_size / 1e6, 1), "MB")
'''

CELL_SUMMARY = '''m = metrics
print("=== P2-002 Stage 2 summary (Section Z) ===")
print("units:", m["unit_metrics"]["units_total"], "| truncated:", m["unit_metrics"]["units_truncated"])
print("eligible:", m["accounting"]["eligible"], "| no family (core):", m["accounting"]["excluded_no_subject_family_core"],
      "| function heading:", m["accounting"]["excluded_function_heading"])
print("blocks:", m["unit_metrics"]["blocks"], "| shared by 2+ core classes:", m["unit_metrics"]["families_shared_by_2plus_core_classes"])
print("stage 1:", m["stage1_summary"]["clusters_cross_class"], "cross-class clusters; span", m["stage1_summary"]["cross_class_span_distribution"])
print("status:", m["match_metrics"]["status_overall"])
print("top-1 agreement (semantic vs lexical):", m["score_stats"]["top1_agreement_semantic_vs_lexical"])
print("provisional band edges:", m["provisional_band_edges"])
print("leakage (provisional edge):", {k: m["leakage_summary"][k] for k in ("n", "leaks", "leakage_rate")})
print("kaggle:", m["kaggle"]["device"], m["kaggle"]["gpu"], m["kaggle"]["runtime_sec_full"], "s")
print("\\nDownload p2002_return.zip and p2002_embeddings_v1.npz from /kaggle/working.")
'''


def _code(src: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
            "source": src.splitlines(keepends=True)}


def _md(src: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": src.splitlines(keepends=True)}


CODE_CELLS = (CELL_CODE, CELL_DEPS, CELL_INPUTS, CELL_MODEL, CELL_SMOKE, CELL_FULL, CELL_WRITE, CELL_SUMMARY)


def build(out: Path | str) -> Path:
    cells = [
        _md(MD_INTRO),
        _md("## 1. Code\nFrom the `rbi-oblibench-code-p2002` Dataset: log its SHA-256 and check every file "
            "against MANIFEST.json. If that Dataset is not attached, clone `BRANCH` instead."),
        _code(CELL_CODE),
        _md("## 2. Dependencies and device"),
        _code(CELL_DEPS),
        _md("## 3. Inputs and the A1 preflight\nStops unless this is the P1-004 corpus and the 28,694 kept "
            "v4 candidates."),
        _code(CELL_INPUTS),
        _md("## 4. Model, pinned to an exact revision\nThere is no fallback model. A download failure or a "
            "revision mismatch stops the run."),
        _code(CELL_MODEL),
        _md("## 5. Smoke run: every stage on 200 seeded candidates\n**Read this output before letting the full "
            "run continue.**"),
        _code(CELL_SMOKE),
        _md("## 6. Full run\nEmbeddings are checkpointed every 5,000 units to `/kaggle/working/p2002_ckpt`. "
            "If the session dies, Run All again and it resumes."),
        _code(CELL_FULL),
        _md("## 7. Write outputs\n`p2002_return.zip` carries matches, clusters, leakage and metrics. It "
            "carries no embeddings and no annotation file. Embeddings go separately to "
            "`p2002_embeddings_v1.npz` (float16)."),
        _code(CELL_WRITE),
        _md("## 8. Summary"),
        _code(CELL_SUMMARY),
    ]
    nb = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    for i, cell in enumerate(nb["cells"]):
        cell["id"] = f"p2002-{i:02d}"
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    print(build(Path(__file__).resolve().parents[1] / "notebooks" / "phase2-p2002-matching.ipynb"))

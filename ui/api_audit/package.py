#!/usr/bin/env python3
"""Build the hosted audit generator's deployment zip (ui/api_audit/.build/auditgen-api.zip).

    python3 ui/api_audit/package.py

Contents: the Function code, src/ (generation, exports, AI features), the three auditgen configs, the corpus files the
generator reads (server-side only: the service never returns more than 12 consecutive words of RBI text and has no
full-text route), the ONNX models and vectors (scripts/auditgen_hosted_models.py) and the capped sample packs with their
recorded AI outputs (ui/scripts/build_public_extras.py). No tests, uploads, research outputs, caches or keys.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BUILD = HERE / ".build"
MODELS = BUILD / "models"

CODE = ["function_app.py", "service.py", "host.json", "requirements.txt"]
CONFIG = ["config/config.yaml", "config/auditgen_v1.yaml", "config/auditgen_genai_v1.yaml"]
DATA = ["data/metadata/document_manifest.jsonl", "data/benchmark/candidates/t1_candidates_v4.jsonl",
        "data/benchmark/matching/t1_matches_v1_thresholded.jsonl", "data/supplementary/amendment/items_v1.jsonl",
        "data/supplementary/enforcement/items_v1.jsonl", "data/supplementary/supp_links_v1.jsonl",
        "data/supplementary/withdrawn/items_v1.jsonl", "data/auditgen_state/calendar_check_sheet_v1.csv",
        "data/auditgen_state/validation_v1.json"]


def main() -> None:
    need = [MODELS / "bge/model.onnx", MODELS / "nli/model.onnx"]
    vecs = sorted((MODELS / "vectors").glob("*.npz"))
    samples = ROOT / "ui/.public-auditgen"
    if not all(p.exists() for p in need) or not vecs:
        raise SystemExit("models or vectors missing: run scripts/auditgen_hosted_models.py export / vectors first")
    if not (samples / "index.json").exists():
        raise SystemExit("capped sample packs missing: run `python3 ui/scripts/build_public_extras.py` first")
    out = BUILD / "auditgen-api.zip"
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        def add(src: Path, arc: str) -> None:
            nonlocal n
            z.write(src, arc)
            n += 1

        for f in CODE:
            add(HERE / f, f)
        for p in sorted((ROOT / "src").rglob("*.py")):
            if "__pycache__" not in p.parts:
                add(p, p.relative_to(ROOT).as_posix())
        for f in CONFIG + DATA:
            add(ROOT / f, f)
        for p in sorted((ROOT / "data/processed").glob("md_*.jsonl")):
            add(p, p.relative_to(ROOT).as_posix())
        for k in ("bge", "nli"):
            for f in ("model.onnx", "tokenizer.json", "meta.json"):
                add(MODELS / k / f, f"models/{k}/{f}")
        for p in vecs:
            add(p, f"models/vectors/{p.name}")
        for p in sorted(samples.iterdir()):
            if p.is_file() and (p.name.endswith(".json.gz") or p.suffix == ".json"):
                add(p, f"samples/{p.name}")
    print(f"{out.relative_to(ROOT)}: {n} files, {out.stat().st_size / 1e6:.0f} MB")


if __name__ == "__main__":
    sys.exit(main())

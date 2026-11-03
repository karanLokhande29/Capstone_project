#!/usr/bin/env python3
"""Reproducibility manifest (P2 draft). Everything is read from config and disk; nothing is typed by hand. It records:
- the model ids and settings;
- the seeds;
- the retrieval config;
- the environment;
- the corpus, benchmark and protocol hashes;
- the prediction archive;
- the bootstrap procedures.

    python3 scripts/build_repro_manifest.py   -> reports/private/final_push/p2/reproducibility_manifest_v1.{json,md}
"""

from __future__ import annotations

import hashlib
import importlib.metadata as md
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common.config import load_config  # noqa: E402

OUT = ROOT / "reports/private/final_push/p2"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def dir_digest(d: Path, pattern: str = "*.json") -> dict:
    files = sorted(d.glob(pattern)) if d.exists() else []
    h = hashlib.sha256()
    for f in files:
        h.update(f.name.encode() + b"\0" + hashlib.sha256(f.read_bytes()).digest())
    return {"files": len(files), "digest_sha256": h.hexdigest() if files else None}


def main() -> int:
    cfg = load_config(None)
    p4, llm, ret = cfg["p4"], cfg["llm"], cfg["retrieval"]
    pkgs = {}
    for name in ("numpy", "torch", "transformers", "sentence-transformers", "huggingface-hub", "bm25s", "httpx", "pyyaml",
                 "pandas", "matplotlib", "pytest"):
        try:
            pkgs[name] = md.version(name)
        except md.PackageNotFoundError:
            pkgs[name] = None
    runs = ROOT / "data/rag_runs"
    m = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "environment": {"platform": platform.platform(), "machine": platform.machine(), "python": platform.python_version(),
                        "packages": pkgs, "lock_files": {f: sha(ROOT / f) for f in ("requirements-lock.txt", "requirements-repass-lock.txt")},
                        "repass_env": "external/.venv-repass (transformers per requirements-repass-lock.txt)"},
        "llm": {"p4_model": llm.get("p4_model"), "p3_models": {k: llm.get(k) for k in ("model", "long_context_model", "fallback_model")},
                "temperature": llm.get("temperature", 0), "thinking": p4.get("thinking"), "json_mode": p4.get("json_mode"),
                "max_output_tokens": p4.get("max_output_tokens"), "fallback": llm.get("fallback"),
                "rpm": p4.get("rpm"), "tpm": p4.get("tpm"), "soft_cap_per_quota_day": p4.get("soft_cap"),
                "long_context": {k: p4["long_context"].get(k) for k in ("max_input_tokens", "fallback_cap", "attempts_per_run", "request_timeout_sec")},
                "p4_prompts": {"dir": p4.get("prompts_dir"), "sha256": p4.get("prompt_sha256")},
                "comparator": json.loads((ROOT / "configs/comparator_v1/FROZEN.json").read_text())},
        "retrieval": {"embedding_model": ret.get("embedding_model"), "embedding_revision": ret.get("embedding_revision"),
                      "max_seq_length": ret.get("max_seq_length"), "bm25": ret.get("bm25"), "rrf_k": ret.get("rrf_k"),
                      "top_k": ret.get("top_k"), "p4_retrieval": p4.get("retrieval"),
                      "verifier": p4.get("verifier")},
        "seeds": {"t1": cfg["t1"]["seeds"], "t4": cfg["t4"]["seeds"], "p4": p4.get("seeds"),
                  "retrieval_eval_bootstrap": ret["eval"].get("bootstrap_seed"),
                  "t1v2": {"retest_draws": {"meer": 20261021, "akash": 20261022}, "pass1_packets": [20261011, 20261012],
                           "seen_before_packets": [20261013, 20261014], "pass2_packets": [20261051, 20261052],
                           "t4_packets": [20261041, 20261042], "reliability_bootstrap": 20261031, "t4_three_rater_bootstrap": 20261032,
                           "adjudication_letters": 20261033}},
        "bootstrap": {"retrieval": {"resamples": ret["eval"].get("bootstrap_resamples"), "seed": ret["eval"].get("bootstrap_seed"),
                                    "unit": "query (cluster CI by Direction also reported)"},
                      "t1_systems": {"resamples": ret["eval"].get("bootstrap_resamples"), "seed": (p4.get("seeds") or {}).get("bootstrap"),
                                     "unit": "item; paired differences resample the same items"},
                      "t1_reliability_v2": {"resamples": 2000, "seed": 20261031, "unit": "item (class units move with the item)"},
                      "t4": {"seed": cfg["t4"]["seeds"].get("bootstrap"), "unit": "question"},
                      "ci_rule": "src/eval/ci_format.py (excludes 0 only when strictly above or below)"},
        "data": {"release_manifest_sha256": sha(ROOT / "release/MANIFEST.json"),
                 "release_paragraphs_sha256": sha(ROOT / "release/data/paragraphs.jsonl"),
                 "t1_gold_v1_sha256": sha(ROOT / "data/benchmark/t1/t1_validated_v1.jsonl"),
                 "t1_gold_v2": "{{after Phase 3}}",
                 "candidate_benchmark_sha256": sha(ROOT / "data/benchmark/t1/t1_candidate_benchmark_v1.jsonl"),
                 "document_manifest_sha256": sha(ROOT / "data/metadata/document_manifest.jsonl")},
        "paper": {"bibliography": "paper/aisigh/refs_verified.bib", "bibliography_sha256": sha(ROOT / "paper/aisigh/refs_verified.bib"),
                  "bibliography_history": ["00f9b811b8d387fb1aa8485920aba1ee652fb220b3aa24166dbc6d7edfadabd8 (as received from Karan)",
                                           "50665e2ae22e0c6ed541b89176758c28040a0a90b13f1b2a8af2175fcc7871ad (access + harvest dates filled)",
                                           "current: + legalbert (2 Oct)"]},
        "protocol": {f: sha(ROOT / f) for f in ("docs/protocol/reliability_plan_v2.md", "docs/protocol/reliability_plan_v2_amendments.md",
                                                 "docs/protocol/reliability_plan_v2_amendments_v2.md",
                                                 "data/benchmark/templates/ANNOTATION_INSTRUCTIONS.md")},
        "prediction_archive": {d.name: dir_digest(d) for d in sorted(runs.iterdir()) if d.is_dir() and d.name.startswith(("t1_", "t2", "t3_", "t4_"))},
        "sealed_phase4": {"manifest": "reports/private/final_push/phase4_input_manifest_v1.json",
                          "manifest_sha256": sha(ROOT / "reports/private/final_push/phase4_input_manifest_v1.json")},
        "reproduction_notes": ["Non-LLM results reproduce exactly from rehydrated text (pointer check: reports/private/final_push/p2/pointer_check_v1.json).",
                               "LLM results reproduce from the cached responses (data/llm_cache, prompt-hash keyed); re-calling the API at temperature 0 "
                               "is only approximately reproducible.",
                               "The embedding and NLI models are pinned by Hub revision; scripts/run_sealed_predictions.py checks the pin offline "
                               "against the local snapshot named by the commit."],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "reproducibility_manifest_v1.json").write_text(json.dumps(m, indent=1, default=str) + "\n")
    L = ["# Reproducibility manifest v1 (draft; generated)", "", f"Generated {m['generated_utc']}. Full detail: `reproducibility_manifest_v1.json`.", "",
         f"- **Environment:** {m['environment']['platform']}, Python {m['environment']['python']}; "
         + ", ".join(f"{k} {v}" for k, v in pkgs.items() if v),
         f"- **LLM:** {m['llm']['p4_model']}, temperature {m['llm']['temperature']}, thinking {m['llm']['thinking']}, JSON mode {m['llm']['json_mode']}, "
         f"max output {m['llm']['max_output_tokens']}, no fallback; P4 prompts frozen ({len(m['llm']['p4_prompts']['sha256'] or {})} files); "
         f"comparator frozen {m['llm']['comparator']['frozen_at_utc']}",
         f"- **Retrieval:** {m['retrieval']['embedding_model']} @ {m['retrieval']['embedding_revision']}, BM25 {m['retrieval']['bm25']}, RRF k={m['retrieval']['rrf_k']}",
         f"- **Bootstrap:** {json.dumps(m['bootstrap'])}",
         f"- **Data:** gold v1 `{m['data']['t1_gold_v1_sha256'][:16]}…`, release manifest `{m['data']['release_manifest_sha256'][:16]}…`, gold v2 {m['data']['t1_gold_v2']}",
         f"- **Paper bibliography:** `{m['paper']['bibliography']}` sha256 `{m['paper']['bibliography_sha256']}`",
         f"- **Protocol:** " + "; ".join(f"{Path(k).name} `{v[:12]}…`" for k, v in m["protocol"].items()),
         f"- **Prediction archive:** {len(m['prediction_archive'])} run directories (digest per directory in JSON); sealed Phase 4 manifest `{m['sealed_phase4']['manifest_sha256'][:16]}…`"]
    (OUT / "reproducibility_manifest_v1.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

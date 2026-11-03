#!/usr/bin/env python3
"""P3-002: run the RegNLP RePASs code unchanged, from its own checkout and venv.

    external/.venv-repass/bin/python scripts/run_repass.py train
    external/.venv-repass/bin/python scripts/run_repass.py score --input <their-format.json> --group <name>

* The checkout is ``external/RePASs`` at the commit pinned in config (``t4.repass.commit``);
  the run refuses any other commit or a dirty tree.
* ``train`` seeds python / numpy / torch (their script seeds only the data split and,
  through the Trainer, training; the classifier head is initialised before that),
  then executes their ``scripts/train_model.py`` as ``__main__``, unmodified.
* ``score`` executes their ``scripts/evaluate_model.py`` ``main(input_file, group)``,
  unmodified: it writes ``data/<group>/results.csv`` and ``results.txt`` inside the checkout.

It runs in ``external/.venv-repass`` (transformers 4.x: their tokenizer call,
``encode_plus``, no longer exists in transformers 5), with the system torch.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import runpy
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHECKOUT = REPO / "external" / "RePASs"


def _pinned_commit() -> str:
    sys.path.insert(0, str(REPO))
    from src.common.config import get_required, load_config

    return str(get_required(load_config(), "t4.repass.commit"))


def _check_checkout() -> str:
    head = subprocess.run(["git", "-C", str(CHECKOUT), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    pinned = _pinned_commit()
    if head != pinned:
        raise SystemExit(f"STOP: RePASs checkout is at {head}, pinned {pinned}")
    dirty = subprocess.run(["git", "-C", str(CHECKOUT), "status", "--porcelain", "--", "scripts", "data/ObligationClassificationDataset.json"],
                           capture_output=True, text=True, check=True).stdout.strip()
    if dirty:
        raise SystemExit(f"STOP: RePASs code or dataset differs from the pinned commit:\n{dirty}")
    return head


def _versions() -> dict:
    import importlib.metadata as md

    out = {"python": platform.python_version(), "platform": platform.platform()}
    for p in ("torch", "transformers", "accelerate", "nltk", "scikit-learn", "numpy"):
        try:
            out[p] = md.version(p)
        except md.PackageNotFoundError:
            out[p] = None
    return out


def cmd_train(seed: int) -> int:
    commit = _check_checkout()
    import numpy as np
    import torch
    from transformers import TrainingArguments, set_seed

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    set_seed(seed)
    device = str(TrainingArguments(output_dir=str(CHECKOUT / "results")).device)
    print(f"RePASs {commit}; seed {seed}; Trainer device {device}", flush=True)
    os.chdir(CHECKOUT)
    started = time.time()
    runpy.run_path("scripts/train_model.py", run_name="__main__")
    secs = time.time() - started
    states = sorted((CHECKOUT / "results").glob("checkpoint-*/trainer_state.json"),
                    key=lambda p: int(p.parent.name.split("-")[1]))
    state = json.loads(states[-1].read_text()) if states else {}
    evals = [h for h in state.get("log_history", []) if "eval_f1" in h]
    info = {
        "commit": commit, "seed": seed, "trainer_device": device, "runtime_seconds": round(secs, 1),
        "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "best_checkpoint": state.get("best_model_checkpoint"), "best_metric_eval_loss": state.get("best_metric"),
        "epochs_run": state.get("epoch"), "eval_by_epoch": evals, "versions": _versions(),
        "base_model": "nlpaueb/legal-bert-base-uncased", "script": "scripts/train_model.py (unmodified)",
    }
    (CHECKOUT / "models" / "p3002_train_info.json").write_text(json.dumps(info, indent=1))
    print(json.dumps({k: v for k, v in info.items() if k != "eval_by_epoch"}, indent=1))
    return 0


def cmd_score(input_file: str, group: str) -> int:
    _check_checkout()
    input_path = Path(input_file).resolve()
    os.chdir(CHECKOUT)
    sys.argv = ["evaluate_model.py"]
    module = runpy.run_path("scripts/evaluate_model.py", run_name="repass_eval")
    started = time.time()
    module["main"](str(input_path), group)
    print(json.dumps({"group": group, "device": module["device"], "seconds": round(time.time() - started, 1)}))
    return 0


def cmd_relevance(input_file: str, output_file: str) -> int:
    """P3-002 repair term: mean over answer sentences of their NLI P(entailment | question => sentence).

    Uses their loaded NLI model and their own helpers (``get_nli_probabilities``, whose column 1 is
    entailment, and their cached ``sent_tokenize``), unchanged. Input: [{"id", "question", "answer"}].
    """
    _check_checkout()
    rows = json.loads(Path(input_file).read_text(encoding="utf-8"))
    os.chdir(CHECKOUT)
    sys.argv = ["evaluate_model.py"]
    module = runpy.run_path("scripts/evaluate_model.py", run_name="repass_eval")
    out = []
    for r in rows:
        sents = list(module["sent_tokenize"](r["answer"])) or [r["answer"]]
        probs = module["get_nli_probabilities"]([r["question"]] * len(sents), sents)
        ent = [float(x) for x in probs[:, 1]]
        out.append({"id": r["id"], "sentences": len(sents), "relevance": sum(ent) / len(ent), "per_sentence": ent})
    Path(output_file).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({"scored": len(out), "device": module["device"], "nli_model": "cross-encoder/nli-deberta-v3-xsmall"}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train")
    t.add_argument("--seed", type=int, default=42)
    s = sub.add_parser("score")
    s.add_argument("--input", required=True)
    s.add_argument("--group", required=True)
    r = sub.add_parser("relevance")
    r.add_argument("--input", required=True)
    r.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.cmd == "relevance":
        return cmd_relevance(args.input, args.output)
    if args.cmd == "train":
        return cmd_train(args.seed)
    return cmd_score(args.input, args.group)


if __name__ == "__main__":
    raise SystemExit(main())

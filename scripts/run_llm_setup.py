#!/usr/bin/env python3
"""P3-001 Task 0/1: list the live models, pick the configured ones, smoke-test each provider.

    python3 scripts/run_llm_setup.py select   # list models, write llm.* ids into config, record versions
    python3 scripts/run_llm_setup.py smoke    # one call per provider: provider, model id, OK / FAIL

Key values are never printed. A missing key prints only "<VAR> missing/empty".
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.config import DEFAULT_CONFIG_PATH, load_config  # noqa: E402
from src.common.io_helpers import read_json, write_json  # noqa: E402
from src.common.paths import PathResolver  # noqa: E402
from src.llm import client as L  # noqa: E402

MODELS_REPORT = "p3001_llm_models_v1.json"
BEGIN = "  # BEGIN selected-models"
END = "  # END selected-models"


def _provider(name: str) -> L._HttpProvider:
    return L.PROVIDER_CLASSES[name](L.require_key(L.KEY_ENV[name]), timeout_sec=60)


def cmd_select(cfg: dict, resolver: PathResolver) -> int:
    L.load_env()
    listed: dict[str, list[L.ModelInfo]] = {}
    for name in ("gemini", "groq"):
        try:
            listed[name] = _provider(name).list_models()
        except L.MissingKeyError as exc:
            print(exc)
        except L.LLMError as exc:
            print(f"{name}: model listing FAILED ({type(exc).__name__})")
    if "gemini" not in listed:
        print("STOP: the primary provider's model list is unavailable.")
        return 1

    pick = L.select_gemini_models(listed["gemini"])
    chosen = {"model": pick["model"], "long_context_model": pick["long_context_model"]}
    if "groq" in listed:
        fb = L.select_groq_model(listed["groq"])
        chosen["fallback_model"] = chosen["fallback_long_context_model"] = fb
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    lines = [BEGIN + ": written by scripts/run_llm_setup.py from the live model lists."]
    for key in ("model", "long_context_model", "fallback_model", "fallback_long_context_model"):
        m = chosen.get(key)
        lines.append(f"  {key}: {m.id if m else 'null'}")
    lines.append("  # Version strings exactly as the list endpoints returned them (Groq returns none).")
    lines.append("  model_versions:")
    for m in {m.id: m for m in chosen.values()}.values():
        lines.append(f'    "{m.id}": ' + (f'"{m.version}"' if m.version else "null"))
    lines.append(f'  models_listed_utc: "{now}"')
    lines.append(END)

    text = DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)
    if len(pattern.findall(text)) != 1:
        print("STOP: config/config.yaml has no single selected-models block")
        return 1
    DEFAULT_CONFIG_PATH.write_text(pattern.sub(lambda _: "\n".join(lines), text), encoding="utf-8")
    load_config()  # still valid YAML + schema

    report = {
        "listed_at_utc": now,
        "selection_rule": {
            "gemini": L.select_gemini_models.__doc__.strip(),
            "groq": L.select_groq_model.__doc__.strip(),
        },
        "selected": {k: asdict(v) for k, v in chosen.items()},
        "listed": {name: [asdict(m) for m in ms] for name, ms in listed.items()},
    }
    write_json(resolver.write_path("reports", MODELS_REPORT), report)
    for key, m in chosen.items():
        print(f"{key}: {m.provider} {m.id} (version {m.version}, input limit {m.input_token_limit})")
    print(f"recorded: reports/{MODELS_REPORT}")
    return 0


def cmd_smoke(cfg: dict, resolver: PathResolver) -> int:
    L.load_env()
    block = cfg["llm"]
    targets = [("gemini", block.get("model")), ("groq", block.get("fallback_model"))]
    messages = [{"role": "user", "content": "Reply with the single word OK."}]
    results = []
    for name, model in targets:
        status = "FAIL"
        served = None
        try:
            prov = _provider(name)
            slot = L.ProviderSlot(prov, {"default": str(model)}, rpm=5, tpm=10_000)
            # A throwaway cache, so the smoke test always reaches the API.
            with tempfile.TemporaryDirectory() as tmp:
                client = L.LLMClient([slot], cache_dir=tmp, max_calls=3, run_id=f"p3001_smoke_{name}",
                                     backoff_attempts=5)
                out = client.complete(messages)
            served = out.model_version
            status = "OK" if "ok" in out.text.lower() else "FAIL"
        except L.MissingKeyError as exc:
            print(exc)
        except L.LLMError as exc:
            status = f"FAIL ({type(exc).__name__})"
        print(f"{name}\t{model}\t{status}" + (f"\tserved={served}" if served else ""))
        results.append({"provider": name, "model": model, "served_version": served, "status": status})

    path = resolver.write_path("reports", MODELS_REPORT)
    report = read_json(path) if path.exists() else {}
    report["smoke_test"] = {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "results": results}
    write_json(path, report)
    return 0 if all(r["status"] == "OK" for r in results) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["select", "smoke"])
    args = parser.parse_args()
    cfg = load_config()
    resolver = PathResolver.from_config(cfg)
    return {"select": cmd_select, "smoke": cmd_smoke}[args.command](cfg, resolver)


if __name__ == "__main__":
    raise SystemExit(main())

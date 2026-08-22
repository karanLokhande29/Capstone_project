#!/usr/bin/env python3
"""Run the Phase 0 foundation check and report the result.

Called three ways, all of which go through the same code path in
:mod:`src.common.verify`:

    python scripts/verify_foundation.py            # local
    python scripts/verify_foundation.py --json     # machine-readable
    from scripts.verify_foundation import main     # Kaggle notebook

Exit code is 0 on PASS, 1 on FAIL, so it can gate a CI step.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow `python scripts/verify_foundation.py` from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.verify import (  # noqa: E402
    environment_versions,
    format_report,
    run_foundation_check,
)


def main(argv: list[str] | None = None) -> int:
    """Run the check. Returns the process exit code."""
    parser = argparse.ArgumentParser(description="Verify the Phase 0 shared foundation.")
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    parser.add_argument("--config", default=None, help="path to an alternative config.yaml")
    parser.add_argument("--versions", action="store_true", help="also report installed versions")
    args = parser.parse_args(argv)

    report = run_foundation_check(args.config)
    if args.versions:
        report["versions"] = environment_versions()

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_report(report))
        if args.versions:
            print("\nInstalled versions")
            print("-" * 40)
            for name, version in report["versions"].items():
                print(f"  {name}: {version}")

    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Entry point for rehydration from the release directory: runs scripts/rehydrate.py (see its --help)."""
import runpy
import sys
from pathlib import Path

sys.argv[0] = str(Path(__file__).resolve().parents[1] / "scripts" / "rehydrate.py")
runpy.run_path(sys.argv[0], run_name="__main__")

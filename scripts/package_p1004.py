#!/usr/bin/env python3
"""P1-004 packaging: the two zips that move the corpus on and off Kaggle.

Kept out of the notebook so the packaging rules are testable. One rule matters
more than the rest and is asserted rather than trusted:

**No annotation file crosses either boundary.** `data/benchmark/**` holds
three people's hand-entered labels and the pilot candidates, which carry
verbatim RBI span text. The return zip must not carry them back over the
copies on Karan's machine — Kaggle never had the filled files, so a returning
`data/benchmark` could only overwrite real work with nothing. The corpus zip
going *out* carries `pilot_candidates.jsonl`, because the consistency checks
need it to verify the pilot spans still resolve, but never a filled
`annotation_*.csv`.

Both builders therefore refuse to produce a zip containing an `annotation_`
file, rather than relying on the caller's include list being right.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Iterable

#: Data directories that make up the corpus itself.
CORPUS_DIRS = ("data/metadata", "data/extracted", "data/processed", "data/matrix")

#: Report prefixes the return trip carries back.
RETURN_REPORT_PREFIXES = (
    "phase1_akash_", "phase1_karan_", "p1004_",
    "phase1_meer_qa_metrics.json", "phase1_meer_checks_metrics.json",
)

#: Never packaged, in either direction.
FORBIDDEN_SUBSTRINGS = ("annotation_", ".DS_Store")


class PackagingError(RuntimeError):
    """A zip would have carried something it must not."""


def _iter_files(root: Path, relative_dirs: Iterable[str]) -> list[Path]:
    found: list[Path] = []
    for rel in relative_dirs:
        base = root / rel
        if not base.is_dir():
            continue
        found += [p for p in sorted(base.rglob("*")) if p.is_file()]
    return found


def _assert_clean(names: Iterable[str]) -> None:
    offenders = [
        n for n in names
        if any(bad in n for bad in FORBIDDEN_SUBSTRINGS if bad != ".DS_Store")
    ]
    if offenders:
        raise PackagingError(
            f"refusing to write a zip containing annotation files: {offenders[:5]}. "
            "Hand-entered labels must not cross this boundary in either direction."
        )


def _write_zip(root: Path, out: Path, files: Iterable[Path]) -> Path:
    members = []
    for path in files:
        if any(bad in path.name for bad in FORBIDDEN_SUBSTRINGS):
            continue
        members.append((path, str(path.relative_to(root))))

    _assert_clean(name for _p, name in members)

    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, name in members:
            zf.write(path, name)
    return out


def build_return_zip(root: Path | str, out: Path | str | None = None) -> Path:
    """Kaggle -> laptop: the repaired corpus and the reports it produced.

    Excludes `data/benchmark` (Kaggle never had the filled task files, so
    anything it returned there could only destroy them), `data/cache` (the raw
    PDFs, which are large and not redistributable) and
    `phase1_meer_annotation.md` (regenerated locally from the ingest, and a
    stale Kaggle copy would overwrite the real agreement figures).
    """
    root = Path(root)
    out = Path(out) if out else root / "p1004_return.zip"

    files = _iter_files(root, CORPUS_DIRS)
    reports = root / "reports"
    if reports.is_dir():
        for path in sorted(reports.rglob("*")):
            if not path.is_file() or path.name == "phase1_meer_annotation.md":
                continue
            if any(path.name.startswith(p) or path.name == p for p in RETURN_REPORT_PREFIXES):
                files.append(path)

    logs = root / "logs" / "harvest_diagnose"
    if logs.is_dir():
        files += [p for p in sorted(logs.rglob("*")) if p.is_file()]

    return _write_zip(root, out, files)


def build_corpus_v2_zip(root: Path | str, out: Path | str | None = None) -> Path:
    """Kaggle -> Kaggle Dataset: the repaired corpus for the next notebook run.

    Carries `data/cache` so a re-run needs no downloads at all, and
    `pilot_candidates.jsonl` so the pilot-join check can run — but no filled
    annotation file.
    """
    root = Path(root)
    out = Path(out) if out else root / "rbi-oblibench-corpus-v2.zip"

    files = _iter_files(root, (*CORPUS_DIRS, "data/cache"))
    candidates = root / "data/benchmark/pilot_candidates.jsonl"
    if candidates.is_file():
        files.append(candidates)

    return _write_zip(root, out, files)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("which", choices=["return", "corpus-v2", "both"])
    parser.add_argument("--root", default=".")
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else root

    if args.which in ("return", "both"):
        path = build_return_zip(root, out_dir / "p1004_return.zip")
        print(f"{path}  ({path.stat().st_size / 1e6:.1f} MB)")
    if args.which in ("corpus-v2", "both"):
        path = build_corpus_v2_zip(root, out_dir / "rbi-oblibench-corpus-v2.zip")
        print(f"{path}  ({path.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

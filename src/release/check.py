"""Release safety check (P5-001 task 5): what git would publish must hold no excluded path, no key, no file over
50 MB and no run of >= 30 consecutive words copied from data/processed.

Allowances, each stated so a reviewer can check it:
- a copied run whose words all lie inside one Direction title (bibliographic metadata, not body text);
- the blank annotation template under data/benchmark/templates/ (protocol documentation, no labels);
- ``.env.example`` (variable names only);
- empty ``.gitkeep`` placeholders that keep ignored data directories in the tree.
Office files (.docx / .pptx / .xlsx) are scanned through the text of their XML parts.
"""

from __future__ import annotations

import fnmatch
import io
import re
import zipfile
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from src.release.rbi_text import CorpusIndex, copied_runs, words

MAX_BYTES = 50 * 1024 * 1024

# (pattern, why). Patterns match the repo-relative path; a trailing "/" means "anything under this directory".
EXCLUDED: tuple[tuple[str, str], ...] = (
    (".env", "API keys"),
    ("data/llm_cache/", "LLM cache"),
    ("data/rag_runs/", "LLM run logs with retrieved RBI text"),
    ("data/indexes/", "retrieval indexes / embeddings"),
    ("*.npy", "embeddings"),
    ("*.npz", "embeddings"),
    ("*embeddings*", "embeddings"),
    ("data/raw*", "raw RBI pages"),
    ("data/cache/", "raw RBI pages"),
    ("data/extracted/", "extracted RBI text"),
    ("data/processed/", "RBI corpus text"),
    ("data/supplementary/", "raw FAQ / press-release / amendment text"),
    ("*.pdf", "raw RBI PDFs"),
    ("data/*.htm*", "raw RBI HTML"),
    ("annotation_*.csv", "raw annotation sheets"),
    ("*_key_v*", "hidden keys"),
    ("*_mock*", "mock files"),
    ("*not_independent/", "not-independent files"),
    ("*_backups/", "backups"),
    ("*_backup_*.zip", "backups"),
    ("external/", "third-party checkouts"),
    ("reports/private/", "private originals and the rater map"),
    ("rbi-oblibench-corpus-v2-karan/", "private corpus copy"),
    ("*_return.zip", "Kaggle return bundles with raw text"),
    # Scope decision 5 (3 Oct 2026): material of the unused 2–3 Oct annotation rounds and the extension runs is kept on
    # disk, unchanged, but never published.
    ("docs/protocol/reliability_plan_v2*", "plan and amendments for an unused annotation round (kept privately)"),
    ("*t1v2*", "unused annotation round: packets, inbox, tooling (kept privately)"),
    ("*t1v3*", "unused annotation round (kept privately)"),
    ("*t4v2*", "unused annotation round (kept privately)"),
    ("*_excluded/", "excluded annotation material (kept privately)"),
    ("*phase4x*", "extension runs not reported (kept privately)"),
    ("scripts/run_ext_*", "extension runs not reported (kept privately)"),
    ("*results_v2_ext*", "extension runs not reported (kept privately)"),
    ("docs/prompts/FINAL-*", "final-push instruction files that describe the unused rounds (kept privately)"),
    ("deliverables_*/", "convenience copies of the final documents, including the private dossier (kept privately)"),
    # Audit generator (local tool): confidential uploads and outputs carrying RBI text are never published.
    ("data/auditgen_uploads/", "uploaded company policies (confidential)"),
    ("data/auditgen_corpus/", "refreshed RBI corpus snapshot (RBI text)"),
    ("data/auditgen_runs/", "generated audit packs (RBI excerpts, company results)"),
    ("data/auditgen_state/", "audit generator state and check sheets"),
    ("outputs/auditgen_samples/", "sample audit packs (RBI excerpts)"),
    ("ui/public/auditgen/", "replay copies of the sample packs (RBI excerpts)"),
)
ALLOWED_PATHS = ("data/benchmark/templates/annotation_task_template.csv", ".env.example")
KEY_PATTERNS = (re.compile(rb"AIza[0-9A-Za-z_\-]{30,}"), re.compile(rb"gsk_[0-9A-Za-z]{20,}"))
TEXT_SUFFIXES = (".md", ".txt", ".json", ".jsonl", ".csv", ".py", ".yaml", ".yml", ".toml", ".cff", ".diff", ".ipynb",
                 ".html", ".tex", ".bib", ".cfg", ".ini", ".sh", ".ts", ".tsx", ".js", ".css", "")
OFFICE_SUFFIXES = (".docx", ".pptx", ".xlsx")


@dataclass
class Problem:
    path: str
    kind: str  # excluded | key | size | rbi_text | unreadable
    detail: str


def excluded_reason(path: str, size: int | None = None) -> str | None:
    if path in ALLOWED_PATHS or (path.endswith("/.gitkeep") and size == 0):
        return None
    parts = path.split("/")
    for pat, why in EXCLUDED:
        if pat.endswith("/"):
            d = pat[:-1]
            if any(fnmatch.fnmatch("/".join(parts[:i]), d) or fnmatch.fnmatch(parts[i - 1], d) for i in range(1, len(parts))):
                return f"{pat} ({why})"
        elif fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(parts[-1], pat):
            return f"{pat} ({why})"
    return None


def office_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return "\n".join(re.sub(r"<[^>]+>", " ", z.read(n).decode("utf-8", "replace"))
                         for n in z.namelist() if n.endswith(".xml"))


def title_allowed(excerpt_words: Sequence[str], run_words: Sequence[str], titles_words: Sequence[str]) -> bool:
    run = " ".join(run_words)
    return any(run in t for t in titles_words)


def scan(files: Iterable[tuple[str, int, Callable[[], bytes]]], index: CorpusIndex, titles: Sequence[str]) -> list[Problem]:
    """``files``: (repo-relative path, size in bytes, reader)."""
    titles_words = [" ".join(words(t)) for t in titles if t]
    out: list[Problem] = []
    for path, size, read in files:
        why = excluded_reason(path, size)
        if why:
            out.append(Problem(path, "excluded", why))
            continue
        if size > MAX_BYTES:
            out.append(Problem(path, "size", f"{size / 1e6:.1f} MB > 50 MB"))
            continue
        try:
            data = read()
        except OSError as exc:
            out.append(Problem(path, "unreadable", str(exc)))
            continue
        for pat in KEY_PATTERNS:
            if pat.search(data):
                out.append(Problem(path, "key", f"key-like string matching {pat.pattern.decode()[:12]}…"))
        suffix = "." + path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
        if suffix in OFFICE_SUFFIXES:
            try:
                text = office_text(data)
            except zipfile.BadZipFile:
                out.append(Problem(path, "unreadable", "not a valid Office zip"))
                continue
        elif suffix in TEXT_SUFFIXES:
            text = data.decode("utf-8", "replace")
        else:
            continue
        ws = words(text)
        for run in copied_runs(text, index):
            rw = ws[run.start_word:run.start_word + run.length]
            if not title_allowed(run.excerpt.split(), rw, titles_words):
                out.append(Problem(path, "rbi_text", f"{run.length}-word copied run at word {run.start_word}: “{run.excerpt[:90]}…”"))
    return out

"""Read-only access to the RBI corpus snapshot the audit generator runs on.

The research corpus (``data/processed``, the manifest, the P2-001 v4 candidates, the amendment items) is only ever
read. A refreshed snapshot written by ``refresh --apply`` lives in ``data/auditgen_corpus`` and overlays the research
corpus Direction by Direction; research results stay tied to the original corpus.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config/auditgen_v1.yaml"
_WORD = re.compile(r"\S+")
_SENT_END = re.compile(r"(?<=[.;:])\s+(?=[A-Z(\"'‘“0-9])")


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    cfg["_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return cfg


def research_config() -> dict[str, Any]:
    return yaml.safe_load((ROOT / "config/config.yaml").read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", errors="replace") as h:
        return [json.loads(line) for line in h if line.strip()]


def excerpt(text: str, max_words: int = 25) -> str:
    """At most ``max_words`` words of ``text`` (whitespace-normalised), with an ellipsis when cut."""
    words = _WORD.findall(text or "")
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]) + " …"


def word_count(s: str) -> int:
    return len([w for w in _WORD.findall(s or "") if w != "…"])


def cue_sentence(text: str, cue_start: int | None) -> str:
    """The sentence of ``text`` that contains the character offset ``cue_start`` (the whole text when unknown)."""
    if cue_start is None:
        return " ".join(text.split())
    start = 0
    for m in _SENT_END.finditer(text):
        if m.start() >= cue_start:
            return " ".join(text[start:m.start()].split())
        start = m.end()
    return " ".join(text[start:].split())


@dataclass
class Snapshot:
    kind: str                       # "research" | "refreshed"
    snapshot_date: str              # latest retrieval date in the manifest
    sha256: str                     # over the manifest and every paragraph file
    manifest_path: str
    processed_dirs: list[str]
    overlay_docs: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "snapshot_date": self.snapshot_date, "sha256": self.sha256,
                "manifest": self.manifest_path, "processed_dirs": self.processed_dirs, "overlay_docs": self.overlay_docs}


class CorpusStore:
    """Directions, paragraphs, obligation candidates and the amendment index for one snapshot."""

    def __init__(self, cfg: Mapping[str, Any] | None = None, *, root: Path = ROOT, use_overlay: bool = True):
        self.cfg = dict(cfg or load_config())
        self.root = root
        p = self.cfg["paths"]
        self.research_cfg = research_config()
        self.core_classes: list[str] = list(self.research_cfg["matching"]["core_entity_classes"])
        self.function_headings: list[str] = list(self.research_cfg["matching"]["function_headings"])
        overlay = root / p["auditgen_corpus"] / "active.json"
        self.overlay = json.loads(overlay.read_text()) if (use_overlay and overlay.exists()) else None
        manifest_path = root / (self.overlay["manifest"] if self.overlay else p["manifest"])
        self.manifest = read_jsonl(manifest_path)
        self.docs: dict[str, dict[str, Any]] = {d["document_id"]: d for d in self.manifest}
        self.paragraphs: dict[str, dict[str, Any]] = {}
        self.paras_by_md: dict[str, list[dict[str, Any]]] = {}
        files: dict[str, Path] = {f.stem: f for f in sorted((root / p["research_corpus"]).glob("md_*.jsonl"))}
        overlay_docs: list[str] = []
        if self.overlay:
            od = root / self.overlay["processed_dir"]
            for f in sorted(od.glob("md_*.jsonl")):
                files[f.stem] = f
                overlay_docs.append(f.stem)
            for gone in self.overlay.get("removed_docs", []):
                files.pop(gone, None)
        digest = hashlib.sha256(manifest_path.read_bytes())
        for md, f in sorted(files.items()):
            if md not in self.docs:
                continue
            data = f.read_bytes()
            digest.update(md.encode() + hashlib.sha256(data).digest())
            rows = sorted((json.loads(x) for x in data.decode("utf-8", "replace").splitlines() if x.strip()),
                          key=lambda r: r.get("position") or 0)
            self.paras_by_md[md] = rows
            for r in rows:
                self.paragraphs[r["paragraph_id"]] = r
        dates = sorted(str(d.get("retrieved_at") or "")[:10] for d in self.manifest if d.get("retrieved_at"))
        self.snapshot = Snapshot("refreshed" if self.overlay else "research", dates[-1] if dates else "unknown",
                                 digest.hexdigest(), manifest_path.relative_to(root).as_posix(),
                                 [p["research_corpus"]] + ([self.overlay["processed_dir"]] if self.overlay else []),
                                 overlay_docs)
        self._candidates: list[dict[str, Any]] | None = None
        self._temporal = None
        self._in_force: dict[str, tuple[str | None, str]] = {}

    # -- Directions ------------------------------------------------------------------------------

    def title(self, md: str) -> str:
        return (self.docs.get(md) or {}).get("title") or ""

    def url(self, md: str) -> str:
        return (self.docs.get(md) or {}).get("source_url") or ""

    def in_force_from(self, md: str) -> tuple[str | None, str]:
        if md not in self._in_force:
            from src.benchmark.t1 import in_force_from

            rows = self.paras_by_md.get(md) or [{}]
            self._in_force[md] = in_force_from(self.docs.get(md) or {}, rows[0].get("text"))
        return self._in_force[md]

    # -- obligations -----------------------------------------------------------------------------

    def candidates(self) -> list[dict[str, Any]]:
        """Kept deontic candidates (P2-001 rules v4); Directions replaced by a refresh are re-extracted with the same rules."""
        if self._candidates is not None:
            return self._candidates
        p = self.cfg["paths"]
        overlay = set(self.snapshot.overlay_docs)
        out = [c for c in read_jsonl(self.root / p["candidates"])
               if c.get("exclusion_reason") is None and c["document_id"] not in overlay and c["paragraph_id"] in self.paragraphs]
        if overlay:
            from src.benchmark.candidates import build_candidate

            for md in sorted(overlay):
                prev = None
                for r in self.paras_by_md.get(md, []):
                    c = build_candidate(r, entity_class=r.get("entity_class"), matrix_cell=None, previous_text=prev)
                    prev = r.get("text")
                    if c is not None and c.exclusion_reason is None:
                        out.append({"candidate_id": c.candidate_id, "document_id": c.document_id, "paragraph_id": c.paragraph_id,
                                    "entity_class": c.entity_class, "cue_matched": c.cue_matched, "cue_position": c.cue_position,
                                    "cue_exclusions": c.cue_exclusions, "exclusion_reason": None})
        self._candidates = out
        return out

    def first_cue(self, cand: Mapping[str, Any]) -> int | None:
        for pos, exc in zip(cand.get("cue_position") or [], cand.get("cue_exclusions") or [None] * 99):
            if exc is None:
                return int(pos[0])
        pos = cand.get("cue_position") or []
        return int(pos[0][0]) if pos else None

    def obligation_sentence(self, cand: Mapping[str, Any]) -> str:
        text = (self.paragraphs.get(cand["paragraph_id"]) or {}).get("text") or ""
        return cue_sentence(text, self.first_cue(cand))

    # -- temporal --------------------------------------------------------------------------------

    def temporal(self):
        if self._temporal is None:
            from src.rag.pipeline import TemporalIndex
            from src.t3 import parser as P

            apath = self.root / (self.overlay["amendments"] if self.overlay and self.overlay.get("amendments") else self.cfg["paths"]["amendments"])
            amendments = {it["item_id"]: it for it in read_jsonl(apath)}
            titles = {k: (v.get("title") or "") for k, v in self.docs.items()}
            actions = [a for it in sorted(amendments.values(), key=lambda x: x["item_id"]) for a in P.parse_amendment(it, titles)[0]]
            light = {md: [{"paragraph_id": r["paragraph_id"], "clause_path": r.get("clause_path")} for r in rows]
                     for md, rows in self.paras_by_md.items()}
            self.amendments = amendments
            self._temporal = TemporalIndex.build(actions, amendments, light)
        return self._temporal

    def amendment_url(self, item_id: str) -> str:
        self.temporal()
        return (self.amendments.get(item_id) or {}).get("source_url") or ""

    def amendment_date(self, item_id: str) -> str | None:
        self.temporal()
        return (self.amendments.get(item_id) or {}).get("published_date")


_STORE: dict[str, CorpusStore] = {}


def get_store(cfg: Mapping[str, Any] | None = None) -> CorpusStore:
    """A process-wide store (the corpus is loaded once); rebuilt when the active snapshot changes."""
    cfg = cfg or load_config()
    key = json.dumps(cfg["paths"], sort_keys=True)
    marker = ROOT / cfg["paths"]["auditgen_corpus"] / "active.json"
    stamp = marker.read_text() if marker.exists() else ""
    k = key + "|" + hashlib.sha256(stamp.encode()).hexdigest()
    if k not in _STORE:
        _STORE.clear()
        _STORE[k] = CorpusStore(cfg)
    return _STORE[k]


def parse_iso(s: str | None) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10]) if s else None
    except ValueError:
        return None


def iter_core(store: CorpusStore) -> Iterable[str]:
    return iter(store.core_classes)

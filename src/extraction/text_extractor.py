"""Text extraction from cached HTML/PDF Master Directions."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pdfplumber
from bs4 import BeautifulSoup

from src.utils import load_config, resolve_path, setup_logging


@dataclass
class ExtractionResult:
    document_id: str
    local_path: str
    format: str
    status: str  # success | failed | empty
    text_path: str | None
    char_count: int
    failure_reason: str | None = None


def extract_pdf_text(path: Path) -> str:
    chunks: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            if t.strip():
                chunks.append(t)
    return "\n\n".join(chunks)


def extract_html_text(path: Path) -> str:
    html = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    # Prefer main content tables / paragraphs
    texts: list[str] = []
    for el in soup.find_all(["p", "li", "td", "h1", "h2", "h3", "h4"]):
        t = el.get_text(" ", strip=True)
        if t:
            texts.append(t)
    if not texts:
        texts = [soup.get_text("\n", strip=True)]
    # Preserve rough paragraph boundaries
    return "\n\n".join(texts)


class TextExtractor:
    def __init__(self, config: dict[str, Any] | None = None):
        self.cfg = config or load_config()
        self.logger = setup_logging("extraction.text", self.cfg)
        self.out_dir = resolve_path(self.cfg, "extracted")
        self.min_chars = int(self.cfg.get("extraction", {}).get("min_text_chars", 50))

    def extract_one(self, document_id: str, local_path: str, fmt: str) -> ExtractionResult:
        path = Path(local_path)
        out_path = self.out_dir / f"{document_id}.txt"
        try:
            if not path.exists():
                return ExtractionResult(
                    document_id=document_id,
                    local_path=local_path,
                    format=fmt,
                    status="failed",
                    text_path=None,
                    char_count=0,
                    failure_reason="file_missing",
                )
            if fmt.upper() == "PDF" or path.suffix.lower() == ".pdf":
                text = extract_pdf_text(path)
            else:
                text = extract_html_text(path)
            text = re.sub(r"[ \t]+\n", "\n", text)
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            if len(text) < self.min_chars:
                self.logger.warning("Empty/short extraction for %s (%s chars)", document_id, len(text))
                return ExtractionResult(
                    document_id=document_id,
                    local_path=local_path,
                    format=fmt,
                    status="empty",
                    text_path=None,
                    char_count=len(text),
                    failure_reason="text_too_short",
                )
            out_path.write_text(text, encoding="utf-8")
            self.logger.info("Extracted %s -> %s (%s chars)", document_id, out_path, len(text))
            return ExtractionResult(
                document_id=document_id,
                local_path=local_path,
                format=fmt,
                status="success",
                text_path=str(out_path),
                char_count=len(text),
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.error("Extraction failed for %s: %s", document_id, exc)
            return ExtractionResult(
                document_id=document_id,
                local_path=local_path,
                format=fmt,
                status="failed",
                text_path=None,
                char_count=0,
                failure_reason=str(exc),
            )

    def run_from_manifest(
        self,
        manifest_path: Path | None = None,
        document_ids: list[str] | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        meta = resolve_path(self.cfg, "metadata")
        manifest_path = manifest_path or (meta / "scrape_manifest.json")
        rows = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        usable = [r for r in rows if r.get("download_status") in {"success", "cached"} and r.get("local_path")]
        if document_ids:
            idset = set(document_ids)
            usable = [r for r in usable if r["document_id"] in idset]
        if limit is not None:
            usable = usable[: int(limit)]

        results: list[ExtractionResult] = []
        for r in usable:
            # Prefer already-extracted
            out = self.out_dir / f"{r['document_id']}.txt"
            if out.exists() and out.stat().st_size > 0:
                text = out.read_text(encoding="utf-8")
                results.append(
                    ExtractionResult(
                        document_id=r["document_id"],
                        local_path=r["local_path"],
                        format=r.get("format", "PDF"),
                        status="success",
                        text_path=str(out),
                        char_count=len(text),
                    )
                )
                self.logger.info("SKIP extract (cached text) %s", r["document_id"])
                continue
            results.append(
                self.extract_one(r["document_id"], r["local_path"], r.get("format", "PDF"))
            )

        summary_path = meta / "extraction_results.json"
        summary_path.write_text(
            json.dumps([asdict(x) for x in results], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        success = sum(1 for x in results if x.status == "success")
        failed = [x for x in results if x.status != "success"]
        return {
            "documents_attempted": len(results),
            "extraction_success": success,
            "extraction_failed": len(failed),
            "extraction_success_rate": (success / len(results)) if results else 0.0,
            "failures": [
                {"document_id": x.document_id, "reason": x.failure_reason, "status": x.status}
                for x in failed
            ],
            "results_path": str(summary_path),
        }

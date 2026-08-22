"""First-pass metadata schema for RBI Master Directions and supplements."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


REQUIRED_DOCUMENT_FIELDS = (
    "document_id",
    "source_url",
    "title",
    "entity_classes",
    "subject_family_raw",
    "update_date_stamp",
    "extraction_source",
    "format",
)


@dataclass
class DocumentMetadata:
    """Provenance-bearing metadata for a harvested document."""

    document_id: str
    source_url: str
    title: str
    entity_classes: list[str] = field(default_factory=list)
    subject_family_raw: str = ""
    update_date_stamp: str | None = None
    extraction_source: str = "rbi_master_directions"
    format: str = "PDF"  # HTML | PDF
    label_role: str = "primary_corpus"  # or validation/motivation source
    local_path: str | None = None
    content_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocumentMetadata":
        missing = [k for k in REQUIRED_DOCUMENT_FIELDS if k not in data]
        if missing:
            raise ValueError(f"Missing required metadata fields: {missing}")
        entity_classes = data.get("entity_classes") or []
        if isinstance(entity_classes, str):
            entity_classes = [c.strip() for c in entity_classes.split(";") if c.strip()]
        return cls(
            document_id=str(data["document_id"]),
            source_url=str(data["source_url"]),
            title=str(data["title"]),
            entity_classes=list(entity_classes),
            subject_family_raw=str(data.get("subject_family_raw") or ""),
            update_date_stamp=data.get("update_date_stamp"),
            extraction_source=str(data.get("extraction_source") or "rbi_master_directions"),
            format=str(data.get("format") or "PDF"),
            label_role=str(data.get("label_role") or "primary_corpus"),
            local_path=data.get("local_path"),
            content_hash=data.get("content_hash"),
        )


def validate_metadata_dict(data: dict[str, Any]) -> list[str]:
    """Return a list of validation error strings (empty if valid)."""
    errors: list[str] = []
    for key in REQUIRED_DOCUMENT_FIELDS:
        if key not in data:
            errors.append(f"missing:{key}")
    if data.get("document_id") in (None, ""):
        errors.append("empty:document_id")
    if data.get("source_url") in (None, ""):
        errors.append("empty:source_url")
    fmt = data.get("format")
    if fmt is not None and str(fmt).upper() not in {"HTML", "PDF"}:
        errors.append(f"invalid_format:{fmt}")
    return errors

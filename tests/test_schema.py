"""Unit tests for metadata schema (no network)."""

from src.metadata.schema import DocumentMetadata, validate_metadata_dict


def test_document_metadata_roundtrip():
    meta = DocumentMetadata(
        document_id="md_1",
        source_url="https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=1",
        title="Reserve Bank of India (Commercial Banks – Know Your Customer) Directions, 2025",
        entity_classes=["Commercial Banks"],
        subject_family_raw="Know Your Customer",
        update_date_stamp="December 29, 2025",
        extraction_source="rbi_master_directions",
        format="PDF",
    )
    d = meta.to_dict()
    restored = DocumentMetadata.from_dict(d)
    assert restored.document_id == "md_1"
    assert restored.entity_classes == ["Commercial Banks"]
    assert restored.format == "PDF"


def test_validate_metadata_missing_fields():
    errors = validate_metadata_dict({"document_id": "x"})
    assert any(e.startswith("missing:") for e in errors)


def test_validate_metadata_invalid_format():
    data = {
        "document_id": "md_1",
        "source_url": "https://example.com",
        "title": "t",
        "entity_classes": [],
        "subject_family_raw": "s",
        "update_date_stamp": None,
        "extraction_source": "test",
        "format": "DOCX",
    }
    errors = validate_metadata_dict(data)
    assert any("invalid_format" in e for e in errors)


def test_from_dict_semicolon_entity_classes():
    data = {
        "document_id": "md_1",
        "source_url": "https://example.com",
        "title": "t",
        "entity_classes": "Commercial Banks; Small Finance Banks",
        "subject_family_raw": "KYC",
        "update_date_stamp": None,
        "extraction_source": "test",
        "format": "HTML",
    }
    m = DocumentMetadata.from_dict(data)
    assert m.entity_classes == ["Commercial Banks", "Small Finance Banks"]

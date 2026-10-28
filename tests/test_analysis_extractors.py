from datetime import datetime, timezone

from c2m_export.analysis.extractors import (
    extract_empty_with_attachments,
    extract_restricted_pages,
    extract_risk_pages,
    extract_stale_pages,
)
from c2m_export.assessment.models import (
    AssessmentResult,
    AttachmentMeta,
    PageMeta,
    RawInventory,
    RestrictionMeta,
    RiskItem,
)


def test_extract_risk_pages():
    p1 = PageMeta("100", "Title A", "SPACE", 1, 100, "2026-01-01T00:00:00Z", [])
    raw = RawInventory(pages=[p1])
    risk1 = RiskItem("100", "Title A", "SPACE/Title A.md", "PATH_LENGTH", "Path too long")
    risk2 = RiskItem("100", "Title A", "SPACE/Title A.md", "INVALID_CHAR", "Invalid char in path")

    res = AssessmentResult(
        total_pages=1,
        total_attachments=0,
        estimated_body_bytes=100,
        total_attachment_bytes=0,
        max_depth=1,
        level_distribution={1: 1},
        space_summary={},
        extension_summary=[],
        mime_summary=[],
        stale_page_count=0,
        empty_page_count=0,
        freshness_distribution={},
        explicit_restriction_count=0,
        unique_restriction_users=[],
        unique_restriction_groups=[],
        read_only_restriction_count=0,
        read_write_restriction_count=0,
        risk_items=[risk1, risk2],
        risk_summary_counts={},
        raw_inventory=raw,
    )

    records = extract_risk_pages(res, "https://example.com/wiki/")
    assert len(records) == 1
    assert records[0]["page_id"] == "100"
    assert records[0]["title"] == "Title A"
    assert records[0]["url"] == "https://example.com/wiki/pages/viewpage.action?pageId=100"
    assert set(records[0]["risk_types"]) == {"PATH_LENGTH", "INVALID_CHAR"}
    assert records[0]["risk_count"] == 2


def test_extract_stale_pages_naive_datetime():
    # Naive timestamp string without offset
    p1 = PageMeta("101", "Old Page", "SPACE", 1, 100, "2024-01-01T00:00:00", [])
    raw = RawInventory(pages=[p1])
    ref_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    stale = extract_stale_pages(raw, stale_days=365, reference_time=ref_time)
    assert len(stale) == 1
    assert stale[0]["page_id"] == "101"
    assert stale[0]["days_since_modified"] > 700


def test_extract_restricted_pages():
    r_meta = RestrictionMeta(has_explicit=True, read_users=["alice"], update_groups=["admin"])
    p1 = PageMeta("102", "Restricted Page", "SPACE", 1, 100, "2026-01-01T00:00:00Z", [], restriction=r_meta)
    raw = RawInventory(pages=[p1])

    restricted = extract_restricted_pages(raw, "https://example.com/wiki")
    assert len(restricted) == 1
    assert restricted[0]["page_id"] == "102"
    assert restricted[0]["read_users"] == ["alice"]
    assert restricted[0]["readwrite_groups"] == ["admin"]


def test_extract_empty_with_attachments():
    att = AttachmentMeta("103", "data.csv", "csv", "text/csv", 1000)
    p1 = PageMeta("103", "Empty Page", "SPACE", 1, 50, "2026-01-01T00:00:00Z", [], attachments=[att])
    raw = RawInventory(pages=[p1])

    records = extract_empty_with_attachments(raw, min_body_bytes=200)
    assert len(records) == 1
    assert records[0]["page_id"] == "103"
    assert records[0]["attachment_count"] == 1
    assert records[0]["body_bytes"] == 50

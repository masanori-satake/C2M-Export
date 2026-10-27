from datetime import datetime, timezone

from c2m_export.assessment.analyzers import analyze_inventory
from c2m_export.assessment.models import (
    AttachmentMeta,
    PageMeta,
    RawInventory,
    RestrictionMeta,
)


def test_analyze_inventory():
    now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    page1 = PageMeta(
        page_id="1",
        title="Root Page",
        space_key="TEST",
        level=1,
        body_bytes=500,
        last_modified="2024-12-01T12:00:00Z",
        ancestors_titles=[],
        attachments=[
            AttachmentMeta(
                page_id="1",
                filename="file1.pdf",
                extension="pdf",
                media_type="application/pdf",
                file_size=1024 * 1024,
                version=1,
            ),
            AttachmentMeta(
                page_id="1",
                filename="danger.exe",
                extension="exe",
                media_type="application/octet-stream",
                file_size=300 * 1024 * 1024,  # 300MB
                version=1,
            ),
        ],
        restriction=RestrictionMeta(
            has_explicit=True,
            read_users=["userA"],
            read_groups=["groupA"],
            update_users=[],
            update_groups=[],
        ),
    )

    page2 = PageMeta(
        page_id="2",
        title="Stale Empty Page",
        space_key="TEST",
        level=2,
        body_bytes=50,  # 空/極小
        last_modified="2020-01-01T12:00:00Z",  # 長期未更新
        ancestors_titles=["Root Page"],
        attachments=[],
        restriction=RestrictionMeta(has_explicit=False),
    )

    inventory = RawInventory(pages=[page1, page2])
    res = analyze_inventory(inventory, single_file_max_mb=250, reference_time=now)

    assert res.total_pages == 2
    assert res.total_attachments == 2
    assert res.estimated_body_bytes == 550
    assert res.total_attachment_bytes == (1024 * 1024 + 300 * 1024 * 1024)
    assert res.max_depth == 2
    assert res.stale_page_count == 1
    assert res.empty_page_count == 1

    assert res.explicit_restriction_count == 1
    assert res.read_only_restriction_count == 1
    assert res.unique_restriction_users == ["userA"]

    # リスク検出のチェック
    risk_types = [item.risk_type for item in res.risk_items]
    assert "BLOCKED_EXT" in risk_types
    assert "LARGE_FILE" in risk_types

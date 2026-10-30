"""c2m_export/analysis/checkpoint.py 内の純粋関数の単体テスト."""

from c2m_export.analysis.checkpoint import (
    compute_scope_hash,
    page_meta_to_record,
    record_to_page_meta,
)
from c2m_export.assessment.models import AttachmentMeta, PageMeta, RestrictionMeta


def test_compute_scope_hash_stability():
    """同一スコープで同一ハッシュ、異なるスコープで異なるハッシュが算出されることを確認."""
    base_url = "https://confluence.example.com/"
    root_ids = ["101", "102"]
    spaces = ["DEV", "TEST"]
    collect_flags = {"collect_macros": True, "collect_history": False}

    h1 = compute_scope_hash(
        base_url=base_url,
        root_page_ids=root_ids,
        space_keys=spaces,
        all_spaces=False,
        cql=None,
        collect_flags=collect_flags,
    )

    # 1. 末尾スラッシュ有無や引数の順序が入れ替わっても同一ハッシュになること
    h2 = compute_scope_hash(
        base_url="https://confluence.example.com",
        root_page_ids=["102", "101"],
        space_keys=["TEST", "DEV"],
        all_spaces=False,
        cql=None,
        collect_flags={"collect_history": False, "collect_macros": True},
    )

    assert h1 == h2
    assert len(h1) == 16

    # 2. スコープ内容変更でハッシュが変わること
    h3 = compute_scope_hash(
        base_url=base_url,
        root_page_ids=["101", "103"],
        space_keys=spaces,
        all_spaces=False,
        cql=None,
        collect_flags=collect_flags,
    )
    assert h1 != h3


def test_page_meta_record_roundtrip():
    """page_meta_to_record ⇔ record_to_page_meta の往復変換でネスト構造が同値保持されることを確認."""
    att = AttachmentMeta(
        page_id="101",
        filename="test.pdf",
        extension="pdf",
        media_type="application/pdf",
        file_size=1024,
        version=1,
        has_extracted_text=True,
        extracted_text_length=50,
        attachment_id="att1",
    )

    rest = RestrictionMeta(
        has_explicit=True,
        read_users=["user1"],
        read_groups=["group1"],
        update_users=[],
        update_groups=[],
        fetch_failed=False,
    )

    pm = PageMeta(
        page_id="101",
        title="Test Page",
        space_key="DEV",
        level=2,
        body_bytes=500,
        last_modified="2025-01-01T00:00:00Z",
        ancestors_titles=["Home"],
        attachments=[att],
        restriction=rest,
        macro_counts={"info": 2},
        created_by="alice",
        last_updated_by="bob",
        contributors=["alice", "bob"],
        owner_unknown=False,
        labels=["tech"],
        comment_count=1,
        unresolved_comment_count=0,
        inline_comment_count=1,
        footer_comment_count=0,
        effective_view_restrictions=rest,
    )

    record = page_meta_to_record(pm)
    assert record["_type"] == "page"
    assert record["page"]["page_id"] == "101"

    restored_pm = record_to_page_meta(record)

    assert restored_pm.page_id == pm.page_id
    assert restored_pm.title == pm.title
    assert len(restored_pm.attachments) == 1
    assert restored_pm.attachments[0].filename == "test.pdf"
    assert restored_pm.attachments[0].file_size == 1024
    assert isinstance(restored_pm.attachments[0], AttachmentMeta)
    assert isinstance(restored_pm.restriction, RestrictionMeta)
    assert restored_pm.restriction.read_users == ["user1"]
    assert isinstance(restored_pm.effective_view_restrictions, RestrictionMeta)
    assert restored_pm.effective_view_restrictions.read_groups == ["group1"]

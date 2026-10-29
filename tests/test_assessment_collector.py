from unittest.mock import MagicMock, patch

import pytest

from c2m_export.assessment.collector import Collector
from c2m_export.assessment.models import AttachmentMeta


def test_collector_collect():
    client = MagicMock()

    # 1. Page 1 (Root)
    page1 = {
        "id": "1",
        "title": "Root Page",
        "space": {"key": "TEST"},
        "body": {"storage": {"value": "<p>Hello</p>"}},
        "version": {"when": "2025-01-01T00:00:00Z"},
    }
    # 2. Page 2 (Child)
    page2 = {
        "id": "2",
        "title": "Child Page",
        "space": {"key": "TEST"},
        "body": {"storage": {"value": ""}},
        "version": {"when": "2025-01-02T00:00:00Z"},
    }

    client.get_page.side_effect = lambda pid, expand: page1 if pid == "1" else page2
    client.get_attachments.side_effect = lambda pid: (
        [
            {
                "title": "doc.pdf",
                "extensions": {"fileSize": 1024, "mediaType": "application/pdf"},
                "version": {"number": 1},
            }
        ]
        if pid == "1"
        else []
    )
    client.get_restrictions.return_value = {
        "read": {"restrictions": {"user": {"results": [{"username": "alice"}]}, "group": {"results": []}}},
        "update": {"restrictions": {"user": {"results": []}, "group": {"results": []}}},
    }
    client.get_child_pages.side_effect = lambda pid: [{"id": "2"}] if pid == "1" else []

    collector = Collector(client, analyze_restrictions=True)
    inventory = collector.collect(["1"])

    assert len(inventory.pages) == 2
    p1 = next(p for p in inventory.pages if p.page_id == "1")
    p2 = next(p for p in inventory.pages if p.page_id == "2")

    assert p1.title == "Root Page"
    assert len(p1.attachments) == 1
    assert p1.attachments[0].filename == "doc.pdf"
    assert p1.restriction.read_users == ["alice"]

    assert p2.title == "Child Page"
    assert p2.level == 2
    assert p2.ancestors_titles == ["Root Page"]


def test_collector_skip_on_error():
    client = MagicMock()
    client.get_page.side_effect = Exception("API Error")

    collector = Collector(client)
    inventory = collector.collect(["999"])

    assert len(inventory.pages) == 0
    assert inventory.skipped_page_ids == ["999"]


def test_collect_preserves_workspace_and_space_failures():
    """DFS の前後で収集したメタデータと失敗キーを同じ戻り値に保持する。"""
    client = MagicMock()
    client.get_space_labels.side_effect = RuntimeError("unavailable")
    client.get_space_root_pages.return_value = []
    client.get_current_user.return_value = {"username": "alice"}
    client.get_user_memberof.return_value = [{"name": "staff"}]
    client.get_access_mode.return_value = {"accessMode": "READ_WRITE"}
    client.get_server_information.return_value = {"version": "9.2", "buildNumber": 123}
    client.get_space_permissions.side_effect = RuntimeError("unavailable")
    client.get_space_watchers.side_effect = RuntimeError("unavailable")
    client.get_page.side_effect = RuntimeError("unavailable")
    collector = Collector(client, collect_space_permissions=True, collect_watchers=True)
    collector.collect_workspace_overview([{"key": "TEST", "name": "Test"}], ["999"])
    collector.collect_space_details(["TEST"])

    inventory = collector.collect(["999"])
    collector.collect_space_details(["AFTER"])

    assert inventory is collector.raw_inventory
    assert [sp.space_key for sp in inventory.spaces] == ["TEST", "AFTER"]
    assert inventory.visibility.username == "alice"
    assert inventory.visibility.groups == ["staff"]
    assert inventory.visibility.visible_space_keys == ["TEST"]
    assert inventory.visibility.unavailable_apis == ["space_labels"]
    assert inventory.environment.server_version == "9.2"
    assert inventory.space_permission_failed_keys == ["TEST", "AFTER"]
    assert inventory.space_watcher_failed_keys == ["TEST", "AFTER"]
    assert inventory.skipped_page_ids == ["999"]


@pytest.mark.parametrize("enabled, failed", [(True, False), (True, True), (False, False)])
def test_collect_extracted_text_uses_attachment_id(enabled, failed):
    """同名の添付でも ID ごとに照会し、失敗参照にも添付 ID を保持する。"""
    client = MagicMock()
    client.get_page.return_value = {"title": "Page", "space": {"key": "TEST"}}
    client.get_attachments.return_value = [
        {"id": "att-1", "title": "doc.pdf"},
        {"id": "att-2", "title": "doc.pdf"},
    ]
    client.get_child_pages.return_value = []
    client.get_attachment_extracted_text.side_effect = [
        RuntimeError("unavailable") if failed else {"text": "本文"},
        {"text": ""},
    ]
    collector = Collector(client, analyze_restrictions=False, collect_extracted_text=enabled)

    inventory = collector.collect(["100"])
    first, second = inventory.pages[0].attachments

    assert [first.attachment_id, second.attachment_id] == ["att-1", "att-2"]
    if enabled:
        assert client.get_attachment_extracted_text.call_args_list == [
            (("100", "att-1"),),
            (("100", "att-2"),),
        ]
        assert first.has_extracted_text is (None if failed else True)
        assert first.extracted_text_length == (None if failed else 2)
        assert second.has_extracted_text is False
        assert second.extracted_text_length == 0
    else:
        client.get_attachment_extracted_text.assert_not_called()
        assert first.has_extracted_text is None
    assert inventory.extracted_text_failed_refs == (["100:att-1"] if failed else [])


def test_attachment_id_defaults_to_empty():
    """既存の位置引数による生成と ID 欠落の添付メタデータを扱える。"""
    assert AttachmentMeta("100", "doc.pdf", "pdf", "application/pdf", 1, 2, True, 3).attachment_id == ""
    client = MagicMock()
    client.get_page.return_value = {"title": "Page"}
    client.get_attachments.return_value = [{"title": "doc.pdf"}]
    client.get_child_pages.return_value = []

    inventory = Collector(client, analyze_restrictions=False).collect(["100"])

    assert inventory.pages[0].attachments[0].attachment_id == ""

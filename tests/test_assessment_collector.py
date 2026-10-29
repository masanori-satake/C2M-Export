from unittest.mock import MagicMock, patch

from c2m_export.assessment.collector import Collector


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


def test_collector_retains_raw_inventory_after_overview_and_details():
    """collect_workspace_overview/collect_space_details 後に collect を呼んでも情報が破棄されないことを検証."""
    client = MagicMock()
    client.get_space_labels.return_value = {"results": []}
    client.get_space_root_pages.return_value = []
    client.get_current_user.return_value = {"username": "testuser", "displayName": "Test User"}
    client.get_user_memberof.return_value = [{"name": "group1"}]
    client.get_access_mode.return_value = {"accessMode": "READ_WRITE"}
    client.get_server_information.return_value = {"version": "9.2.0", "buildNumber": 9200}
    client.get_space_permissions.side_effect = Exception("Permission API Error")
    client.get_space_watchers.side_effect = Exception("Watcher API Error")

    page1 = {
        "id": "1",
        "title": "Root Page",
        "space": {"key": "SPACE1"},
        "body": {"storage": {"value": "<p>Hello</p>"}},
        "version": {"when": "2025-01-01T00:00:00Z"},
    }
    client.get_page.return_value = page1
    client.get_attachments.return_value = []
    client.get_restrictions.return_value = {}
    client.get_child_pages.return_value = []

    collector = Collector(
        client,
        analyze_restrictions=False,
        collect_space_permissions=True,
        collect_watchers=True,
    )

    # 1. Overview 収集
    collector.collect_workspace_overview([{"key": "SPACE1", "name": "Space 1"}], ["1"])
    # 2. Details 収集
    collector.collect_space_details(["SPACE1"])
    # 3. DFS 巡回
    inventory = collector.collect(["1"])

    # 情報が保持されているか検証
    assert len(inventory.spaces) == 1
    assert inventory.spaces[0].space_key == "SPACE1"
    assert inventory.visibility is not None
    assert inventory.visibility.username == "testuser"
    assert inventory.visibility.groups == ["group1"]
    assert inventory.environment is not None
    assert inventory.environment.server_version == "9.2.0"
    assert inventory.space_permission_failed_keys == ["SPACE1"]
    assert inventory.space_watcher_failed_keys == ["SPACE1"]
    assert len(inventory.pages) == 1


def test_collector_extracted_text_uses_attachment_id():
    """抽出テキスト取得時にファイル名ではなく attachment_id が API に渡ることを検証."""
    client = MagicMock()
    page1 = {
        "id": "100",
        "title": "Page 100",
        "space": {"key": "SPACE1"},
        "body": {"storage": {"value": "<p>Hello</p>"}},
    }
    client.get_page.return_value = page1
    client.get_attachments.return_value = [
        {
            "id": "att_999",
            "title": "sample_document.pdf",
            "extensions": {"fileSize": 500, "mediaType": "application/pdf"},
        }
    ]
    client.get_restrictions.return_value = {}
    client.get_child_pages.return_value = []
    client.get_attachment_extracted_text.return_value = {"text": "Extracted text content"}

    collector = Collector(client, analyze_restrictions=False, collect_extracted_text=True)
    inventory = collector.collect(["100"])

    assert len(inventory.pages) == 1
    p = inventory.pages[0]
    assert len(p.attachments) == 1
    att = p.attachments[0]
    assert att.attachment_id == "att_999"
    assert att.filename == "sample_document.pdf"
    assert att.has_extracted_text is True
    assert att.extracted_text_length == 22

    # API 呼び出しの第2引数が attachment_id ('att_999') であり、ファイル名 ('sample_document.pdf') ではないことを検証
    client.get_attachment_extracted_text.assert_called_once_with("100", "att_999")

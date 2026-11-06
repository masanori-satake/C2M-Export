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


def _overview_client(root_pages, count_behavior):
    """全体把握の子孫数取得だけを差し替えたモッククライアントを作る."""
    client = MagicMock()
    client.get_space_labels.return_value = {"results": []}
    client.get_space_root_pages.return_value = root_pages
    client.get_descendant_page_count.side_effect = count_behavior
    return client


def test_overview_descendant_count_partial_failure_is_recorded():
    """一部のルートで子孫数取得に失敗したら部分失敗として記録される (spec 0021)."""

    def behavior(pid):
        if pid == "2":
            raise RuntimeError("boom")
        return {"count": 5}

    client = _overview_client([{"id": "1"}, {"id": "2"}], behavior)
    collector = Collector(client)
    meta, unavailable = collector._collect_space_overview_one({"key": "S1", "name": "Space 1"})

    assert meta is not None
    # ルート 2 件 + 成功した子孫数 5 件。失敗したルート分は欠けたまま公開される
    assert meta.page_count_preview == 7
    assert meta.page_count_preview_partial is True
    assert unavailable == ["descendant_count_partial"]


def test_overview_descendant_count_all_failures_are_recorded():
    """全ルートで子孫数取得に失敗したらプレビューは None で descendant_count が記録される (spec 0021)."""

    def behavior(pid):
        raise RuntimeError("boom")

    client = _overview_client([{"id": "1"}], behavior)
    collector = Collector(client)
    meta, unavailable = collector._collect_space_overview_one({"key": "S1", "name": "Space 1"})

    assert meta is not None
    assert meta.page_count_preview is None
    assert meta.page_count_preview_partial is False
    assert unavailable == ["descendant_count"]


def test_overview_descendant_count_success_has_no_partial_marks():
    """子孫数取得が全て成功すれば従来どおり何も記録されない (spec 0021)."""
    client = _overview_client([{"id": "1"}], lambda pid: {"count": 3})
    collector = Collector(client)
    meta, unavailable = collector._collect_space_overview_one({"key": "S1", "name": "Space 1"})

    assert meta is not None
    assert meta.page_count_preview == 4
    assert meta.page_count_preview_partial is False
    assert unavailable == []


def test_workspace_output_marks_partial_preview_only_when_partial():
    """workspace 出力の page_count_preview_partial は部分失敗の Space にだけ現れる (spec 0021)."""
    from c2m_export.analysis.workspace import summarize_spaces
    from c2m_export.assessment.models import SpaceMeta

    ok = SpaceMeta(space_key="S1", name="a", type="global", status="current", page_count_preview=10)
    partial = SpaceMeta(
        space_key="S2",
        name="b",
        type="global",
        status="current",
        page_count_preview=7,
        page_count_preview_partial=True,
    )
    out = summarize_spaces([ok, partial])
    spaces = {s["space_key"]: s for s in out["spaces"]}

    assert "page_count_preview_partial" not in spaces["S1"]
    assert spaces["S2"]["page_count_preview_partial"] is True

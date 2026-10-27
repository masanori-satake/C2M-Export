"""現在インベントリの軽量収集 (sync.py collect_inventory) の単体テスト."""

from unittest.mock import MagicMock

import pytest

from c2m_export.fs_export.sync import collect_inventory


def test_collect_inventory_success():
    """ConfluenceClient をモックして正常に軽量メタデータが収集されることを検証する."""
    client = MagicMock()

    # モックの動作設定
    client.get_space_root_pages.return_value = [{"id": "100"}]
    client.get_page.side_effect = lambda pid, expand: {
        "100": {
            "id": "100",
            "title": "Root Page",
            "version": {"number": 3},
            "space": {"key": "DEV"},
            "ancestors": [],
        },
        "200": {
            "id": "200",
            "title": "Child Page",
            "version": {"number": 1},
            "space": {"key": "DEV"},
            "ancestors": [{"id": "100"}],
        },
    }[pid]

    client.get_child_pages.side_effect = lambda pid: {
        "100": [{"id": "200"}],
        "200": [],
    }[pid]

    client.get_attachments.side_effect = lambda pid: {
        "100": [
            {
                "id": "att1",
                "title": "file.pdf",
                "version": {"number": 2},
                "extensions": {"fileSize": 2048},
            }
        ],
        "200": [],
    }[pid]

    inv = collect_inventory(client, root_page_ids=[], space_keys=["DEV"])

    assert len(inv.pages) == 2
    assert "100" in inv.pages
    assert "200" in inv.pages
    assert inv.pages["100"].version == 3
    assert inv.pages["100"].title == "Root Page"
    assert inv.pages["100"].parent_id is None
    assert "att1" in inv.pages["100"].attachments
    assert inv.pages["100"].attachments["att1"].size == 2048

    assert inv.pages["200"].parent_id == "100"
    assert len(inv.failed_page_ids) == 0


def test_collect_inventory_failure_handling():
    """メタデータ取得に一部失敗した場合に failed_page_ids に記録され処理が継続されることを検証する."""
    client = MagicMock()

    client.get_space_root_pages.return_value = []
    client.get_page.side_effect = Exception("HTTP 500 Server Error")

    inv = collect_inventory(client, root_page_ids=["999"], space_keys=[])

    assert len(inv.pages) == 0
    assert "999" in inv.failed_page_ids

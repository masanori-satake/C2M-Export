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

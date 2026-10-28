from unittest.mock import MagicMock

from c2m_export.assessment.collector import Collector


def test_collector_macros_disabled():
    client = MagicMock()
    client.get_page.return_value = {
        "title": "Page",
        "space": {"key": "SPACE"},
        "body": {"storage": {"value": '<ac:structured-macro ac:name="toc"/>'}},
    }
    client.get_attachments.return_value = []
    client.get_restrictions.return_value = {}
    client.get_child_pages.return_value = []

    collector = Collector(client, collect_macros=False)
    inventory = collector.collect(["100"])

    assert len(inventory.pages) == 1
    assert inventory.pages[0].macro_counts == {}
    assert inventory.macro_parse_failed_count == 0


def test_collector_macros_enabled():
    client = MagicMock()
    client.get_page.return_value = {
        "title": "Page",
        "space": {"key": "SPACE"},
        "body": {"storage": {"value": '<ac:structured-macro ac:name="toc"/>'}},
    }
    client.get_attachments.return_value = []
    client.get_restrictions.return_value = {}
    client.get_child_pages.return_value = []

    collector = Collector(client, collect_macros=True)
    inventory = collector.collect(["100"])

    assert len(inventory.pages) == 1
    assert inventory.pages[0].macro_counts == {"toc": 1}
    assert inventory.macro_parse_failed_count == 0

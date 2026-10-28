from unittest.mock import MagicMock

import pytest

from c2m_export.analysis.macros import BeautifulSoup
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


@pytest.mark.parametrize("failure_stage", ["parse", "count"])
def test_collector_macro_failure_discards_partial_counts(failure_stage, monkeypatch, caplog):
    body = '<ac:structured-macro ac:name="toc"/>'
    client = MagicMock()
    client.get_page.return_value = {
        "title": "Page",
        "space": {"key": "SPACE"},
        "body": {"storage": {"value": body}},
    }
    client.get_attachments.return_value = []
    client.get_restrictions.return_value = {}
    client.get_child_pages.return_value = []

    error = ValueError("マクロ解析エラー")
    failed_soup = MagicMock()
    failed_soup.find_all.side_effect = [[{"ac:name": "toc"}], error]
    monkeypatch.setattr(
        "c2m_export.analysis.macros.BeautifulSoup",
        MagicMock(side_effect=[error if failure_stage == "parse" else failed_soup, BeautifulSoup(body, "html.parser")]),
    )

    inventory = Collector(client, collect_macros=True).collect(["100", "101"])

    assert len(inventory.pages) == 2
    assert inventory.pages[0].macro_counts == {}
    assert inventory.pages[1].macro_counts == {"toc": 1}
    assert inventory.macro_parse_failed_count == 1
    assert "ページ (ID: 100) のマクロ解析に失敗しました" in caplog.text

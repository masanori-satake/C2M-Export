"""spec 0014（収集の高速化）の検証テスト.

子ページの一括先読みとフォールバック、全体把握フェーズの並列化、
スレッドローカルセッション、timeout 分離、ルート確認の軽量化を確認する。
"""

import threading
from unittest.mock import MagicMock

import pytest

from c2m_export.analysis.api import _resolve_roots
from c2m_export.analysis.checkpoint import CollectInterrupted
from c2m_export.assessment.collector import Collector
from c2m_export.confluence import ConfluenceClient


class FakeTreeClient:
    """100 → [101, 102], 101 → [103] のツリーを持つフェイククライアント."""

    def __init__(self, descendants_mode: str = "ok"):
        self.children = {"100": ["101", "102"], "101": ["103"], "102": [], "103": []}
        self.child_calls: list = []
        self.descendants_mode = descendants_mode

    def get_page(self, page_id, expand="body.storage,space"):
        return {
            "id": page_id,
            "title": f"Title_{page_id}",
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>content</p>"}},
            "version": {"when": "2025-01-01T00:00:00Z"},
        }

    def get_attachments(self, page_id):
        return []

    def get_restrictions(self, page_id):
        return {}

    def get_child_pages(self, page_id):
        self.child_calls.append(page_id)
        return [{"id": c} for c in self.children[page_id]]

    def get_descendants(self, page_id, type_="page", expand=None, limit=25):
        if self.descendants_mode == "raise":
            raise RuntimeError("descendant endpoint unavailable")
        if self.descendants_mode == "empty":
            return []
        if self.descendants_mode == "nonlist":
            return {"results": []}
        out: list = []

        def walk(pid, ancestors):
            for cid in self.children[pid]:
                out.append({"id": cid, "ancestors": [{"id": a} for a in ancestors + [pid]]})
                walk(cid, ancestors + [pid])

        walk(page_id, [])
        return out


def _collect(mode: str):
    client = FakeTreeClient(mode)
    collector = Collector(client)  # type: ignore[arg-type]
    inv = collector.collect(["100"])
    return client, inv


def test_prefetch_avoids_individual_child_calls():
    """先読みが成功した場合、個別の子ページ取得は呼ばれず階層も正しい."""
    client, inv = _collect("ok")
    assert client.child_calls == []
    assert {p.page_id for p in inv.pages} == {"100", "101", "102", "103"}
    by_id = {p.page_id: p for p in inv.pages}
    assert by_id["103"].level == 3
    assert by_id["103"].ancestors_titles == ["Title_100", "Title_101"]


def test_prefetch_traversal_order_matches_fallback():
    """先読み時とフォールバック時で巡回順序が一致する."""
    _, inv_prefetch = _collect("ok")
    _, inv_fallback = _collect("empty")
    assert [p.page_id for p in inv_prefetch.pages] == [p.page_id for p in inv_fallback.pages]


@pytest.mark.parametrize("mode", ["empty", "raise", "nonlist"])
def test_prefetch_fallbacks(mode):
    """先読みできない場合は従来の個別取得で全ページを収集する."""
    client, inv = _collect(mode)
    assert client.child_calls != []
    assert {p.page_id for p in inv.pages} == {"100", "101", "102", "103"}


class FakeOverviewClient:
    """全体把握フェーズ用のフェイククライアント."""

    base_url = "https://confluence.example.com"

    def get_space_labels(self, space_key):
        return {"results": [{"name": "a"}, {"name": "b"}]}

    def get_space_root_pages(self, space_key):
        return [{"id": f"{space_key}-root"}]

    def get_descendant_page_count(self, page_id):
        return {"count": 3}

    def get_current_user(self):
        return {"username": "user1", "displayName": "User One"}

    def get_user_memberof(self):
        return [{"name": "group1"}]

    def get_access_mode(self):
        return {"accessMode": "READ_WRITE"}

    def get_server_information(self):
        return {"version": "8.5.0", "buildNumber": 12345}


def _overview(concurrency: int):
    spaces = [{"key": f"S{i}", "name": f"Space{i}"} for i in range(6)] + [{"name": "keyless"}]
    collector = Collector(FakeOverviewClient(), concurrency=concurrency)  # type: ignore[arg-type]
    collector.collect_workspace_overview(spaces, [])
    return collector.raw_inventory


def test_overview_parallel_matches_serial():
    """並列実行でも Space の並び・値・可視性情報が直列実行と同一になる."""
    serial = _overview(1)
    parallel = _overview(4)
    serial_spaces = [(s.space_key, s.label_count, s.page_count_preview) for s in serial.spaces]
    parallel_spaces = [(s.space_key, s.label_count, s.page_count_preview) for s in parallel.spaces]
    assert parallel_spaces == serial_spaces
    assert parallel_spaces[0] == ("S0", 2, 4)
    assert parallel.visibility.visible_space_keys == serial.visibility.visible_space_keys
    assert parallel.visibility.unavailable_apis == serial.visibility.unavailable_apis


def test_overview_parallel_interrupt():
    """並列実行中も中断判定が働く."""
    spaces = [{"key": f"S{i}"} for i in range(3)]
    collector = Collector(FakeOverviewClient(), concurrency=4, interrupt_checker=lambda: True)  # type: ignore[arg-type]
    with pytest.raises(CollectInterrupted):
        collector.collect_workspace_overview(spaces, [])


def test_thread_local_session():
    """メインスレッドでは既存セッション、別スレッドでは専用セッションが使われる."""
    client = ConfluenceClient("https://confluence.example.com", "dummy")
    assert client._get_session() is client.session
    results: dict = {}

    def worker():
        s1 = client._get_session()
        s2 = client._get_session()
        results["same_in_thread"] = s1 is s2
        results["different_from_main"] = s1 is not client.session

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert results == {"same_in_thread": True, "different_from_main": True}


class _FakeResponse:
    status_code = 200

    def json(self):
        return {}


class _FakeSession:
    def __init__(self):
        self.captured_timeout = None

    def request(self, method, url, params=None, timeout=None):
        self.captured_timeout = timeout
        return _FakeResponse()


def _captured_timeout(**kwargs):
    client = ConfluenceClient("https://confluence.example.com", "dummy", **kwargs)
    fake = _FakeSession()
    client.session = fake  # type: ignore[assignment]
    client._request("GET", "/rest/api/content")
    return fake.captured_timeout


def test_request_timeout_default_and_split():
    """未指定時は従来の単一値 30 秒、指定時は (connect, read) タプルになる."""
    assert _captured_timeout() == 30
    assert _captured_timeout(connect_timeout=5, read_timeout=15) == (5.0, 15.0)
    assert _captured_timeout(read_timeout=20) == (10.0, 20.0)


def test_resolve_roots_uses_light_expand():
    """ルート確認は本文を取得しない軽量な expand で行われる."""
    client = MagicMock()
    client.get_page.return_value = {"id": "101"}
    resolved, empty_space_keys, cql_failed = _resolve_roots(client, ["101"], [])
    assert resolved == ["101"]
    assert empty_space_keys == []
    assert cql_failed is False
    client.get_page.assert_called_once_with("101", expand="version")

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

    def __init__(self, descendants_mode: str = "ok", honor_max_items: bool = True):
        self.children = {"100": ["101", "102"], "101": ["103"], "102": [], "103": []}
        self.child_calls: list = []
        self.descendants_mode = descendants_mode
        self.honor_max_items = honor_max_items

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

    def get_descendants(self, page_id, type_="page", expand=None, limit=25, interrupt_checker=None, max_items=None):
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
        # 実クライアントの契約を模倣する（上限超過時は部分結果を返さず送出する）
        if self.honor_max_items and max_items is not None and len(out) > max_items:
            raise RuntimeError(f"子孫一覧の件数が上限 ({max_items} 件) を超えました")
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


@pytest.mark.parametrize("honor_max_items", [True, False])
def test_prefetch_falls_back_when_descendants_exceed_max_pages(honor_max_items):
    """子孫数が max_pages を超える起点は先読みせず、個別取得で上限まで収集する.

    honor_max_items=True はクライアント側の上限送出、False は Collector 側の
    事後チェックによるフォールバックをそれぞれ検証する。
    """
    client = FakeTreeClient("ok", honor_max_items=honor_max_items)
    collector = Collector(client, max_pages=2)  # type: ignore[arg-type]
    with pytest.raises(CollectInterrupted):
        collector.collect(["100"])
    assert client.child_calls != []
    assert [p.page_id for p in collector.raw_inventory.pages] == ["100", "101"]


class _PaginatedSession:
    """descendant エンドポイントのページングを再現するフェイクセッション."""

    def __init__(self):
        self.request_count = 0
        self.pages = {
            0: ([{"id": "a"}, {"id": "b"}], "/rest/api/content/100/descendant/page?start=2"),
            2: ([{"id": "c"}, {"id": "d"}], "/rest/api/content/100/descendant/page?start=4"),
            4: ([{"id": "e"}], None),
        }

    def request(self, method, url, params=None, timeout=None):
        self.request_count += 1
        results, next_link = self.pages[params["start"]]
        payload = {"results": results}
        if next_link:
            payload["_links"] = {"next": next_link}

        class _Resp:
            status_code = 200

            def json(self):
                return payload

        return _Resp()


def _descendant_client():
    client = ConfluenceClient("https://confluence.example.com", "dummy")
    session = _PaginatedSession()
    client.session = session  # type: ignore[assignment]
    return client, session


def test_get_descendants_paginates_all():
    """打ち切り条件がなければ全ページを取得する."""
    client, session = _descendant_client()
    items = client.get_descendants("100", limit=2)
    assert [i["id"] for i in items] == ["a", "b", "c", "d", "e"]
    assert session.request_count == 3


def test_get_descendants_aborts_on_interrupt():
    """ページング途中で中断条件が成立したら部分結果を返さず送出する."""
    client, session = _descendant_client()
    with pytest.raises(RuntimeError):
        client.get_descendants("100", limit=2, interrupt_checker=lambda: True)
    assert session.request_count == 1


def test_get_descendants_aborts_over_max_items():
    """累計件数が上限を超えたら部分結果を返さず送出する."""
    client, session = _descendant_client()
    with pytest.raises(RuntimeError):
        client.get_descendants("100", limit=2, max_items=3)
    assert session.request_count == 2


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


def test_analysis_config_validates_split_timeouts():
    """分離 timeout は validate() で検証される（未指定は許可、bool・0以下は拒否）."""
    from c2m_export.config import AnalysisConfig

    cfg = AnalysisConfig()
    cfg.base_url = "https://confluence.example.com"
    cfg.root_page_ids = ["101"]
    cfg.token = "dummy"
    cfg.validate()

    cfg.connect_timeout_seconds = 0
    with pytest.raises(ValueError, match="connect_timeout_seconds"):
        cfg.validate()

    cfg.connect_timeout_seconds = 5
    cfg.read_timeout_seconds = True
    with pytest.raises(ValueError, match="read_timeout_seconds"):
        cfg.validate()

    cfg.read_timeout_seconds = 30
    cfg.validate()


def test_resolve_roots_uses_light_expand():
    """ルート確認は本文を取得しない軽量な expand で行われる."""
    client = MagicMock()
    client.get_page.return_value = {"id": "101"}
    resolved, empty_space_keys, cql_failed = _resolve_roots(client, ["101"], [])
    assert resolved == ["101"]
    assert empty_space_keys == []
    assert cql_failed is False
    client.get_page.assert_called_once_with("101", expand="version")

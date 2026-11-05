"""Collector のチェックポイント追記・resume スキップ・協調的中断の検証テスト."""

from unittest.mock import MagicMock

import pytest

from c2m_export.analysis.checkpoint import CheckpointStore, CollectInterrupted
from c2m_export.assessment.collector import Collector


@pytest.fixture
def mock_client():
    client = MagicMock()

    # ページ 101, 102
    def get_page_side_effect(page_id, **kwargs):
        return {
            "id": page_id,
            "title": f"Title_{page_id}",
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>Content</p>"}},
            "version": {"when": "2025-01-01T00:00:00Z"},
        }

    client.get_page.side_effect = get_page_side_effect
    client.get_attachments.return_value = []
    client.get_restrictions.return_value = {}
    client.get_child_pages.return_value = []
    return client


def test_collector_append_to_checkpoint(mock_client, tmp_path):
    """収集時に CheckpointStore.append_page が各ページごとに呼び出されることを確認."""
    checkpoint_file = tmp_path / "collector_test.jsonl"
    store = CheckpointStore(checkpoint_file, scope_hash="hash123")

    mock_client.get_child_pages.side_effect = lambda pid: [{"id": "102"}] if pid == "101" else []

    collector = Collector(mock_client, checkpoint_store=store)
    inv = collector.collect(["101"])

    assert len(inv.pages) == 2
    store.close()

    # ファイルにヘッダ + 2 ページ = 3 行保存されていること
    with open(checkpoint_file, encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 3


def test_collector_resume_skip(mock_client):
    """resume_collected_ids に含まれるページが取得スキップされ、未収集分のみ追加されることを確認."""
    # 101 は収集済み、102 は未収集だが 101 の子ページ
    mock_client.get_child_pages.side_effect = lambda pid: [{"id": "102"}] if pid == "101" else []

    collector = Collector(mock_client, resume_collected_ids={"101"})
    inv = collector.collect(["101"])

    # 101 はスキップされたが子 102 は探索され取得されたこと
    assert len(inv.pages) == 1
    assert inv.pages[0].page_id == "102"


def test_collector_cooperative_interruption(mock_client):
    """interrupt_checker が True を返すと CollectInterrupted が送出され収集済み分が保持されることを確認."""
    # 先読み経路でも検証するため、子孫一括取得の成功レスポンスを設定する
    mock_client.get_descendants.return_value = [{"id": "102", "ancestors": [{"id": "101"}]}]
    mock_client.get_child_pages.side_effect = lambda pid: [{"id": "102"}] if pid == "101" else []

    holder: dict = {}

    def interrupt_checker():
        # 中断条件は収集済みページ数（保存後の状態）で判定する。
        # 呼び出し回数ベースだと、先読み等の判定ポイント追加で意味が変わってしまうため。
        collector = holder.get("collector")
        return collector is not None and len(collector.raw_inventory.pages) >= 1

    collector = Collector(mock_client, interrupt_checker=interrupt_checker)
    holder["collector"] = collector

    with pytest.raises(CollectInterrupted):
        collector.collect(["101"])

    # 最初の 1 ページ (101) は収集済み raw_inventory に保存されていること
    assert len(collector.raw_inventory.pages) == 1
    assert collector.raw_inventory.pages[0].page_id == "101"
    # 先読み経路で巡回したため、個別の子ページ取得は使われていないこと
    mock_client.get_child_pages.assert_not_called()

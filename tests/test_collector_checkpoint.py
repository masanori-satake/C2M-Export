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
    call_count = 0

    def interrupt_checker():
        nonlocal call_count
        call_count += 1
        return call_count > 1  # 2 回目のループで True

    mock_client.get_child_pages.side_effect = lambda pid: [{"id": "102"}] if pid == "101" else []

    collector = Collector(mock_client, interrupt_checker=interrupt_checker)

    with pytest.raises(CollectInterrupted):
        collector.collect(["101"])

    # 最初の 1 ページ (101) は収集済み raw_inventory に保存されていること
    assert len(collector.raw_inventory.pages) == 1
    assert collector.raw_inventory.pages[0].page_id == "101"

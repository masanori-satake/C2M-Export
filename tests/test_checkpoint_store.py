"""c2m_export/analysis/checkpoint.py 内 CheckpointStore の単体テスト."""

import json

import pytest

from c2m_export.analysis.checkpoint import CheckpointStore
from c2m_export.assessment.models import PageMeta


@pytest.fixture
def sample_page_meta():
    return PageMeta(
        page_id="201",
        title="Sample Page",
        space_key="TEST",
        level=1,
        body_bytes=100,
        last_modified="2025-01-01T12:00:00Z",
        ancestors_titles=[],
    )


def test_checkpoint_store_append_and_load(tmp_path, sample_page_meta):
    """追記と再読み込みでの同値性を検証."""
    checkpoint_file = tmp_path / "test_scope.jsonl"
    scope_hash = "abc123def4567890"
    scope_meta = {"root_page_ids": ["201"]}

    store = CheckpointStore(checkpoint_file, scope_hash=scope_hash, scope_meta=scope_meta, interval=1)
    store.open_for_write(append=False)

    store.append_page(sample_page_meta)
    store.close()

    assert checkpoint_file.exists()

    # スコープ照合の検証
    store_reader = CheckpointStore(checkpoint_file, scope_hash=scope_hash)
    assert store_reader.scope_matches(scope_hash) is True
    assert store_reader.scope_matches("wrong_hash_123456") is False

    # ロード検証
    pages, page_ids, corrupted = store_reader.load_collected()
    assert len(pages) == 1
    assert pages[0].page_id == "201"
    assert pages[0].title == "Sample Page"
    assert "201" in page_ids
    assert len(corrupted) == 0


def test_checkpoint_store_corrupted_line_handling(tmp_path, sample_page_meta):
    """途中切れや JSON 破損行が含まれる場合の復元動作を検証."""
    checkpoint_file = tmp_path / "corrupted_scope.jsonl"
    scope_hash = "hash1234567890ab"

    # ヘッダ + 正常レコード + 破損行 + 正常レコード
    store = CheckpointStore(checkpoint_file, scope_hash=scope_hash)
    store.open_for_write(append=False)
    store.append_page(sample_page_meta)
    store.close()

    # 破損行をファイルに追記
    with open(checkpoint_file, "a", encoding="utf-8") as f:
        f.write("CORRUPTED_NON_JSON_LINE\n")
        f.write('{"_type": "page", "page": "invalid_page_structure"}\n')

    # 再度正常ページを追加
    sample_page_2 = PageMeta(
        page_id="202",
        title="Page 2",
        space_key="TEST",
        level=1,
        body_bytes=200,
        last_modified=None,
        ancestors_titles=[],
    )
    store.open_for_write(append=True)
    store.append_page(sample_page_2)
    store.close()

    pages, page_ids, corrupted = store.load_collected()
    assert len(pages) == 2
    assert "201" in page_ids
    assert "202" in page_ids
    assert len(corrupted) == 2


def test_checkpoint_store_finalize_success(tmp_path, sample_page_meta):
    """finalize(success=True) でチェックポイントファイルが削除されることを確認."""
    checkpoint_file = tmp_path / "finalize_test.jsonl"
    store = CheckpointStore(checkpoint_file, scope_hash="hash123")
    store.open_for_write(append=False)
    store.append_page(sample_page_meta)

    assert checkpoint_file.exists()

    store.finalize(success=True)
    assert not checkpoint_file.exists()


def test_checkpoint_store_finalize_failure(tmp_path, sample_page_meta):
    """finalize(success=False) でチェックポイントファイルが残置されることを確認."""
    checkpoint_file = tmp_path / "finalize_fail_test.jsonl"
    store = CheckpointStore(checkpoint_file, scope_hash="hash123")
    store.open_for_write(append=False)
    store.append_page(sample_page_meta)

    store.finalize(success=False)
    assert checkpoint_file.exists()

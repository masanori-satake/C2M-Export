"""fsexport CLI エントリーポイントのテスト."""

from unittest.mock import MagicMock, patch

import pytest

from c2m_export.fs_export.models import ExportResult, SkipRecord
from c2m_export.fsexport import main


def test_main_overwrite_conflict(tmp_path):
    # 既存ファイルが存在するディレクトリを用意
    (tmp_path / "existing.txt").write_text("hello", encoding="utf-8")

    test_args = [
        "fsexport",
        "--base-url",
        "https://confluence.example.com",
        "--token",
        "dummy_token",
        "--root-page-id",
        "100",
        "--output-dir",
        str(tmp_path),
        "--config",
        str(tmp_path / "nonexistent.yaml"),
    ]

    with patch("sys.argv", test_args):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1


def test_main_success(tmp_path):
    output_dir = tmp_path / "out"

    test_args = [
        "fsexport",
        "--base-url",
        "https://confluence.example.com",
        "--token",
        "dummy_token",
        "--root-page-id",
        "100",
        "--output-dir",
        str(output_dir),
        "--config",
        str(tmp_path / "nonexistent.yaml"),
    ]

    dummy_node = MagicMock()
    dummy_node.page_id = "100"
    dummy_node.title = "Root"

    with patch("sys.argv", test_args):
        with patch(
            "c2m_export.fsexport.build_page_tree",
            return_value=([dummy_node], {}, {"100"}),
        ):
            with patch(
                "c2m_export.fsexport.export_tree_fs",
                return_value=MagicMock(
                    total_pages=1,
                    total_attachments=0,
                    total_bytes=10,
                    skipped_pages=[],
                    skipped_attachments=[],
                    unresolved_links_count=0,
                    renamed_nodes={},
                ),
            ):
                with patch("c2m_export.fsexport.write_summary"):
                    main()


def test_main_summary_includes_tree_and_writer_failures(tmp_path):
    client = MagicMock()
    client.get_page.side_effect = [RuntimeError("403 Forbidden"), {"id": "100", "title": "Root"}]
    client.get_child_pages.side_effect = [[{"id": "101", "title": "Child"}], RuntimeError("通信エラー")]
    client.get_space_root_pages.side_effect = RuntimeError("Space 取得エラー")
    writer_failure = SkipRecord("102", "page", "書込失敗ページ", "書き込みエラー")
    result = ExportResult(total_pages=1, skipped_pages=[writer_failure])
    test_args = [
        "fsexport",
        "--base-url",
        "https://confluence.example.com",
        "--token",
        "dummy_token",
        "--root-page-id",
        "999",
        "100",
        "--space-key",
        "PRIVATE",
        "--output-dir",
        str(tmp_path),
        "--config",
        str(tmp_path / "nonexistent.yaml"),
    ]

    with patch("sys.argv", test_args):
        with patch("c2m_export.fsexport.ConfluenceClient", return_value=client):
            with patch("c2m_export.fsexport.export_tree_fs", return_value=result):
                main()

    assert result.skipped_pages[0] == writer_failure
    summary_files = list(tmp_path.glob("fsexport_summary_*.txt"))
    assert len(summary_files) == 1
    summary = summary_files[0].read_text(encoding="utf-8")
    assert "出力成功ページ数: 1" in summary
    assert "スキップ・失敗ページ数: 4" in summary
    assert "[999] 999 (パス: ): ルートページ取得失敗 (403 Forbidden)" in summary
    assert "[101] Child (パス: 【UNKNOWN】 Root/Child): 子ページ取得失敗 (通信エラー)" in summary
    assert "[PRIVATE] Space PRIVATE (パス: ): Space ルートページ一覧取得失敗 (Space 取得エラー)" in summary
    assert "[102] 書込失敗ページ" in summary


@pytest.mark.parametrize("target_option", ["--root-page-id", "--space-key"])
def test_main_all_roots_failed_writes_summary_and_exits(tmp_path, target_option):
    client = MagicMock()
    client.get_page.side_effect = RuntimeError("403 Forbidden")
    client.get_space_root_pages.side_effect = RuntimeError("403 Forbidden")
    test_args = [
        "fsexport",
        "--base-url",
        "https://confluence.example.com",
        "--token",
        "dummy_token",
        target_option,
        "100",
        "--output-dir",
        str(tmp_path),
        "--config",
        str(tmp_path / "nonexistent.yaml"),
    ]

    with patch("sys.argv", test_args):
        with patch("c2m_export.fsexport.ConfluenceClient", return_value=client):
            with patch("c2m_export.fsexport.export_tree_fs") as writer:
                with pytest.raises(SystemExit) as exc_info:
                    main()

    assert exc_info.value.code == 1
    writer.assert_not_called()
    summary_files = list(tmp_path.glob("fsexport_summary_*.txt"))
    assert len(summary_files) == 1
    summary = summary_files[0].read_text(encoding="utf-8")
    assert "出力成功ページ数: 0" in summary
    assert "スキップ・失敗ページ数: 1" in summary
    assert "[100]" in summary
    assert "403 Forbidden" in summary

"""fsexport CLI エントリーポイントのテスト."""

from unittest.mock import MagicMock, patch

import pytest

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

"""c2m_export.permexport メインエントリーポイントのテスト."""

import sys
from unittest.mock import MagicMock, patch

import c2m_export.permexport as permexport
from c2m_export.permission.models import PermissionReport, PermissionResult


def test_permexport_main(tmp_path):
    test_args = [
        "permexport",
        "--base-url",
        "https://example.com",
        "--token",
        "testtoken",
        "--root-page-id",
        "100",
        "--output-dir",
        str(tmp_path),
        "--config",
        str(tmp_path / "nonexistent.yaml"),
    ]

    mock_client_cls = MagicMock()
    mock_collect = MagicMock()

    mock_result = PermissionResult(
        report=PermissionReport(pages=[]),
        exported_count=0,
        explicit_count=0,
        inherited_count=0,
        failed_page_ids=[],
    )
    mock_collect.return_value = mock_result

    with patch.object(sys, "argv", test_args):
        with patch("c2m_export.permexport.ConfluenceClient", mock_client_cls):
            with patch("c2m_export.permexport.collect_permissions", mock_collect):
                permexport.main()

    mock_client_cls.assert_called_once_with(
        base_url="https://example.com",
        token="testtoken",
        proxy=None,
    )
    mock_collect.assert_called_once()


def test_permexport_main_overwrite_conflict(tmp_path):
    import pytest

    test_args = [
        "permexport",
        "--base-url",
        "https://example.com",
        "--token",
        "testtoken",
        "--root-page-id",
        "100",
        "--output-dir",
        str(tmp_path),
        "--config",
        str(tmp_path / "nonexistent.yaml"),
    ]

    # 既存の _permissions.md を作成
    existing_file = tmp_path / "_permissions.md"
    existing_file.write_text("existing content", encoding="utf-8")

    mock_client_cls = MagicMock()
    mock_collect = MagicMock()

    mock_result = PermissionResult(
        report=PermissionReport(pages=[]),
        exported_count=0,
        explicit_count=0,
        inherited_count=0,
        failed_page_ids=[],
    )
    mock_collect.return_value = mock_result

    # overwrite なしで実行した場合、sys.exit(1) で終了すること
    with patch.object(sys, "argv", test_args):
        with patch("c2m_export.permexport.ConfluenceClient", mock_client_cls):
            with patch("c2m_export.permexport.collect_permissions", mock_collect):
                with pytest.raises(SystemExit) as exc_info:
                    permexport.main()
                assert exc_info.value.code == 1

    # --overwrite を指定した場合、正常終了すること
    test_args_overwrite = test_args + ["--overwrite"]
    with patch.object(sys, "argv", test_args_overwrite):
        with patch("c2m_export.permexport.ConfluenceClient", mock_client_cls):
            with patch("c2m_export.permexport.collect_permissions", mock_collect):
                permexport.main()

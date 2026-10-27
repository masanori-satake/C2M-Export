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

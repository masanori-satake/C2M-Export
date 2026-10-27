"""fsexport main 分岐 (sync/resume/full) の単体テスト."""

from unittest.mock import MagicMock, patch

from c2m_export.fsexport import main


@patch("c2m_export.fsexport.write_summary")
@patch("c2m_export.fsexport.execute_sync")
@patch("c2m_export.fsexport.compute_diff")
@patch("c2m_export.fsexport.collect_inventory")
@patch("c2m_export.fsexport.load_manifest")
@patch("c2m_export.fsexport.ConfluenceClient")
@patch("c2m_export.fsexport.FsExportConfig")
def test_fsexport_main_sync_path(
    mock_config_cls,
    mock_client_cls,
    mock_load_manifest,
    mock_collect_inv,
    mock_compute_diff,
    mock_execute_sync,
    mock_write_summary,
    tmp_path,
):
    """--sync オプション指定時に sync 経路へ分岐することを検証する."""
    config_mock = MagicMock()
    config_mock.sync = True
    config_mock.resume = False
    config_mock.full = False
    config_mock.output_dir = str(tmp_path)
    config_mock.overwrite = True
    config_mock.base_url = "https://confluence.example.com"
    config_mock.token = "token"
    config_mock.root_page_ids = ["100"]
    config_mock.space_keys = []
    config_mock.manifest_name = ".c2m_manifest.json"
    config_mock.deletion_policy = "quarantine"
    config_mock.quarantine_dir_name = "_c2m_quarantine"
    config_mock.page_filename_mode = "title"

    mock_config_cls.return_value = config_mock
    mock_load_manifest.return_value = None  # 初回
    mock_collect_inv.return_value = MagicMock()

    plan_mock = MagicMock()
    plan_mock.add_count = 1
    plan_mock.change_count = 0
    plan_mock.move_rename_count = 0
    plan_mock.delete_count = 0
    plan_mock.unchanged_count = 0
    mock_compute_diff.return_value = plan_mock

    main()

    assert mock_collect_inv.called
    assert mock_compute_diff.called
    assert mock_execute_sync.called
    assert mock_write_summary.called

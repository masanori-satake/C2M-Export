"""fsexport main 分岐 (sync/resume/full) の単体テスト."""

from unittest.mock import MagicMock, patch

import pytest

from c2m_export.fs_export.diff import compute_diff
from c2m_export.fs_export.manifest import load_manifest
from c2m_export.fs_export.sync import collect_inventory
from c2m_export.fsexport import main


@patch("c2m_export.fsexport.write_summary")
@patch("c2m_export.fsexport.execute_sync")
@patch("c2m_export.fsexport.compute_diff")
@patch("c2m_export.fsexport.collect_inventory")
@patch("c2m_export.fsexport.load_manifest")
@patch("c2m_export.fsexport.ConfluenceClient")
@patch("c2m_export.fsexport.FsExportConfig")
@pytest.mark.parametrize("resume", [False, True])
def test_fsexport_main_sync_path(
    mock_config_cls,
    mock_client_cls,
    mock_load_manifest,
    mock_collect_inv,
    mock_compute_diff,
    mock_execute_sync,
    mock_write_summary,
    tmp_path,
    resume,
):
    """--sync オプション指定時に sync 経路へ分岐することを検証する."""
    config_mock = MagicMock()
    config_mock.sync = not resume
    config_mock.resume = resume
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
    assert mock_execute_sync.call_args.kwargs["resume"] is resume
    assert mock_write_summary.called


@pytest.mark.parametrize("mode", ["title", "index"])
def test_full_export_manifest_is_reused_by_next_sync(tmp_path, mode):
    """フル出力の実際の保存先と取得済みメタデータを次回の同期に引き継ぐ."""
    pages = {
        "100": {"id": "100", "title": "Root", "version": {"number": 4}, "ancestors": [{"id": "outside"}]},
        "200": {"id": "200", "title": "Child", "version": {"number": 2}, "ancestors": [{"id": "100"}]},
        "201": {"id": "201", "title": "Child", "version": {"number": 3}, "ancestors": [{"id": "100"}]},
    }
    for page in pages.values():
        page.update({"space": {"key": "DEV"}, "body": {"storage": {"value": "<p>本文</p>"}}})
    client = MagicMock()
    client.get_page.side_effect = lambda pid, expand=None: pages[pid]
    client.get_child_pages.side_effect = lambda pid: [pages["200"], pages["201"]] if pid == "100" else []
    attachment = {
        "id": "att",
        "title": "a?.txt",
        "version": {"number": 5},
        "extensions": {"fileSize": 3},
        "_links": {"download": "/file"},
    }
    client.get_attachments.side_effect = lambda pid: [attachment] if pid == "200" else []

    def download(download_path, dest_file, max_bytes):
        from pathlib import Path

        target = Path(dest_file)
        target.parent.mkdir(parents=True, exist_ok=True)
        return target.write_bytes(b"att")

    client.download_attachment.side_effect = download
    args = [
        "fsexport",
        "--base-url",
        "https://confluence.example.com",
        "--token",
        "dummy",
        "--root-page-id",
        "100",
        "--output-dir",
        str(tmp_path),
        "--page-filename-mode",
        mode,
    ]
    with patch("sys.argv", args), patch("c2m_export.fsexport.ConfluenceClient", return_value=client):
        main()

    manifest = load_manifest(str(tmp_path))
    assert manifest is not None
    assert set(manifest.pages) == set(pages)
    assert manifest.completed is True
    for pid, entry in manifest.pages.items():
        assert entry.version == pages[pid]["version"]["number"]
        assert entry.title == pages[pid]["title"]
        assert entry.parent_id == pages[pid]["ancestors"][-1]["id"]
        assert (tmp_path / entry.rel_path / entry.body_file).is_file()
    assert manifest.pages["201"].rel_path == "【DEV】 Root/Child (2)"
    saved_attachment = manifest.pages["200"].attachments["att"]
    assert (saved_attachment.version, saved_attachment.size, saved_attachment.state) == (5, 3, "done")
    assert (
        tmp_path / manifest.pages["200"].rel_path / "_attachments" / saved_attachment.saved_name
    ).read_bytes() == b"att"
    inventory = collect_inventory(client, ["100"], [])
    assert compute_diff(manifest, inventory).unchanged_count == 3

    client.reset_mock()
    with patch("sys.argv", args + ["--sync"]), patch("c2m_export.fsexport.ConfluenceClient", return_value=client):
        main()

    client.download_attachment.assert_not_called()
    assert all(call.kwargs.get("expand") == "version,ancestors,space" for call in client.get_page.call_args_list)
    assert load_manifest(str(tmp_path)).pages == manifest.pages

"""ファイルシステム書き込み・エクスポート実行部のテスト."""

from unittest.mock import MagicMock

from c2m_export.fs_export.models import PageNode
from c2m_export.fs_export.writer import export_tree_fs


def test_export_tree_fs_success(tmp_path):
    client = MagicMock()
    client.get_page.return_value = {
        "id": "100",
        "title": "テストページ",
        "body": {"storage": {"value": "<p>本文</p>"}},
        "space": {"key": "DOC"},
        "version": {"number": 1},
        "history": {"lastUpdated": {"when": "2026-01-01T00:00:00+09:00"}},
    }
    client.get_attachments.return_value = [
        {
            "id": "att1",
            "title": "sample.txt",
            "extensions": {"fileSize": 100},
            "_links": {"download": "/download/sample.txt"},
        }
    ]
    client.download_attachment.return_value = 100

    converter = MagicMock()
    converter.convert.return_value = "本文\n![sample](sample.txt)"

    root_node = PageNode(
        page_id="100",
        title="テストページ",
        level=1,
        relative_dir_path="【DOC】 テストページ",
        body_file_name="テストページ.md",
    )

    result = export_tree_fs(
        client=client,
        converter=converter,
        output_dir=str(tmp_path),
        root_nodes=[root_node],
        attachment_dir_name="_attachments",
        attachment_link_mode="relative",
        single_file_max_mb=250.0,
        base_url="https://confluence.example.com",
    )

    assert result.total_pages == 1
    assert result.total_attachments == 1
    assert len(result.skipped_pages) == 0

    page_file = tmp_path / "【DOC】 テストページ" / "テストページ.md"
    assert page_file.exists()
    content = page_file.read_text(encoding="utf-8")
    assert 'title: "テストページ"' in content
    assert "![sample](_attachments/sample.txt)" in content


def test_export_tree_fs_single_file_max_mb(tmp_path):
    client = MagicMock()
    client.get_page.return_value = {
        "id": "100",
        "title": "テストページ",
        "body": {"storage": {"value": "<p>本文</p>"}},
        "space": {"key": "DOC"},
    }
    # 300MB の超巨大添付ファイル
    client.get_attachments.return_value = [
        {
            "id": "att1",
            "title": "huge.zip",
            "extensions": {"fileSize": 300 * 1024 * 1024},
            "_links": {"download": "/download/huge.zip"},
        }
    ]

    converter = MagicMock()
    converter.convert.return_value = "本文"

    root_node = PageNode(
        page_id="100",
        title="テストページ",
        level=1,
        relative_dir_path="【DOC】 テストページ",
        body_file_name="テストページ.md",
    )

    result = export_tree_fs(
        client=client,
        converter=converter,
        output_dir=str(tmp_path),
        root_nodes=[root_node],
        single_file_max_mb=250.0,
    )

    assert result.total_pages == 1
    assert result.total_attachments == 0
    assert len(result.skipped_attachments) == 1
    assert "単一ファイルサイズ上限超過" in result.skipped_attachments[0].reason


def test_manifest_records_only_written_pages_and_attachment_states(tmp_path):
    """ページ出力失敗は完了記録から除外し、添付の失敗・除外状態も保持する."""
    client = MagicMock()
    client.get_page.side_effect = [RuntimeError("取得失敗"), {"version": {"number": 2}}]
    client.get_attachments.return_value = [
        {"id": "skip", "title": "skip.exe", "version": {"number": 3}},
        {"id": "fail", "title": "fail.txt", "version": {"number": 4}},
    ]
    client.download_attachment.side_effect = RuntimeError("ダウンロード失敗")
    child = PageNode("child", "Child", 2, "Root/Child", "Child.md")
    root = PageNode("root", "Root", 1, "Root", "Root.md", children=[child])
    manifest_pages = {}

    result = export_tree_fs(
        client,
        MagicMock(convert=lambda *a, **kw: "本文"),
        str(tmp_path),
        [root],
        exclude_extensions=["exe"],
        manifest_pages=manifest_pages,
    )

    assert result.total_pages == 1
    assert set(manifest_pages) == {"child"}
    assert manifest_pages["child"].parent_id == "root"
    assert manifest_pages["child"].attachments["skip"].state == "skipped"
    assert manifest_pages["child"].attachments["skip"].version == 3
    assert manifest_pages["child"].attachments["fail"].state == "failed"
    assert manifest_pages["child"].attachments["fail"].version == 4

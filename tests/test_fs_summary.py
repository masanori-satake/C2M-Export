"""処理サマリ出力機能のテスト."""

from datetime import datetime

from c2m_export.fs_export.models import ExportResult, SkipRecord
from c2m_export.fs_export.summary import generate_summary_text, write_summary


def test_generate_summary_text():
    result = ExportResult(
        total_pages=5,
        total_attachments=10,
        total_bytes=10485760,  # 10 MB
        skipped_pages=[
            SkipRecord(
                target_id="101",
                target_type="page",
                title_or_name="権限なしページ",
                reason="403 Forbidden",
                path="dir/page",
            )
        ],
        skipped_attachments=[
            SkipRecord(
                target_id="att1",
                target_type="attachment",
                title_or_name="huge.zip",
                reason="単一ファイルサイズ上限超過",
                size_bytes=300000000,
                path="dir/_attachments/huge.zip",
            )
        ],
        unresolved_links_count=1,
        renamed_nodes={"102": "同名 -> 同名 (2)"},
    )

    text = generate_summary_text(result, "2026-02-01 12:00:00")

    assert "出力成功ページ数: 5" in text
    assert "出力成功添付ファイル数: 10" in text
    assert "権限なしページ" in text
    assert "huge.zip" in text
    assert "同名 -> 同名 (2)" in text


def test_write_summary_file(tmp_path):
    result = ExportResult(total_pages=2, total_attachments=1, total_bytes=500)
    dt = datetime(2026, 2, 1, 15, 30, 45)

    _, file_path = write_summary(result, str(tmp_path), execution_dt=dt)

    assert "fsexport_summary_20260201_153045.txt" in file_path
    assert (tmp_path / "fsexport_summary_20260201_153045.txt").exists()

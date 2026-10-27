"""処理サマリ出力機能のテスト."""

import logging
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
    output_dir = tmp_path / "nested" / "output"

    _, file_path = write_summary(result, str(output_dir), execution_dt=dt)

    assert "fsexport_summary_20260201_153045.txt" in file_path
    assert (output_dir / "fsexport_summary_20260201_153045.txt").exists()


def test_write_summary_directory_creation_failure(tmp_path, caplog):
    output_dir = tmp_path / "blocked"
    output_dir.write_text("既存ファイル", encoding="utf-8")
    result = ExportResult(total_pages=2)
    dt = datetime(2026, 2, 1, 15, 30, 45)

    with caplog.at_level(logging.INFO, logger="c2m_export.fs_export.summary"):
        summary_text, file_path = write_summary(result, str(output_dir), execution_dt=dt)

    assert file_path == str(output_dir / "fsexport_summary_20260201_153045.txt")
    assert "出力成功ページ数: 2" in summary_text
    assert summary_text in caplog.text
    errors = [record.message for record in caplog.records if record.levelno == logging.ERROR]
    assert len(errors) == 1
    assert f"現象: サマリファイルの書き込みに失敗しました ({file_path})。 原因:" in errors[0]
    assert "対処方法: 出力先ディレクトリのパーミッションを確認してください。" in errors[0]
    assert output_dir.read_text(encoding="utf-8") == "既存ファイル"

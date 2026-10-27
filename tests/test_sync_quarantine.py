"""退避ディレクトリ操作 (quarantine.py) の単体テスト."""

import os

from c2m_export.fs_export.quarantine import quarantine_path


def test_quarantine_path_quarantine_mode(tmp_path):
    """quarantine モードで退避先サブディレクトリへ移動されることを検証する."""
    out_dir = str(tmp_path)
    target_dir = os.path.join(out_dir, "SPACE", "SubDir")
    os.makedirs(target_dir, exist_ok=True)
    file_in_dir = os.path.join(target_dir, "test.md")
    with open(file_in_dir, "w", encoding="utf-8") as f:
        f.write("test content")

    rel_path = os.path.join("SPACE", "SubDir")
    quarantine_path(
        rel_path=rel_path,
        output_dir=out_dir,
        deletion_policy="quarantine",
        quarantine_dir_name="_quarantine",
        timestamp="20260101_120000",
    )

    assert not os.path.exists(target_dir)
    quarantine_dest = os.path.join(out_dir, "_quarantine", "20260101_120000", "SPACE", "SubDir")
    assert os.path.exists(quarantine_dest)
    assert os.path.exists(os.path.join(quarantine_dest, "test.md"))


def test_quarantine_path_delete_mode(tmp_path):
    """delete モードでローカル出力が物理削除されることを検証する."""
    out_dir = str(tmp_path)
    target_file = os.path.join(out_dir, "delete_me.md")
    with open(target_file, "w", encoding="utf-8") as f:
        f.write("content")

    quarantine_path(
        rel_path="delete_me.md",
        output_dir=out_dir,
        deletion_policy="delete",
    )

    assert not os.path.exists(target_file)


def test_quarantine_path_report_mode(tmp_path):
    """report モードでローカル出力が変更されず残ることを検証する."""
    out_dir = str(tmp_path)
    target_file = os.path.join(out_dir, "keep_me.md")
    with open(target_file, "w", encoding="utf-8") as f:
        f.write("content")

    quarantine_path(
        rel_path="keep_me.md",
        output_dir=out_dir,
        deletion_policy="report",
    )

    assert os.path.exists(target_file)

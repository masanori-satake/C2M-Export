import json
import sys
from unittest.mock import MagicMock, patch

import pytest

import c2m_export.tree as tree_cli


def test_tree_main_missing_args(tmp_path, monkeypatch, capsys):
    nonexistent_config = str(tmp_path / "nonexistent.yaml")
    monkeypatch.setattr(
        sys,
        "argv",
        ["tree.py", "--config", nonexistent_config, "--base-url", "https://wiki.example.com", "--token", "tok"],
    )

    with pytest.raises(SystemExit) as exc_info:
        tree_cli.main()

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "エラー: 現象: 起点" in captured.err


def test_tree_main_success_text(tmp_path, monkeypatch, capsys):
    nonexistent_config = str(tmp_path / "nonexistent.yaml")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tree.py",
            "--config",
            nonexistent_config,
            "--base-url",
            "https://wiki.example.com",
            "--token",
            "tok",
            "--space-key",
            "TEST",
        ],
    )

    mock_client = MagicMock()
    mock_client.get_space_root_pages.return_value = [{"id": "1", "title": "Home"}]
    mock_client.get_child_pages.return_value = []

    with patch("c2m_export.tree.ConfluenceClient", return_value=mock_client):
        with pytest.raises(SystemExit) as exc_info:
            tree_cli.main()

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "Home  [id:1]" in captured.out


def test_tree_main_success_json(tmp_path, monkeypatch, capsys):
    nonexistent_config = str(tmp_path / "nonexistent.yaml")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tree.py",
            "--config",
            nonexistent_config,
            "--base-url",
            "https://wiki.example.com",
            "--token",
            "tok",
            "--space-key",
            "TEST",
            "--format",
            "json",
        ],
    )

    mock_client = MagicMock()
    mock_client.get_space_root_pages.return_value = [{"id": "1", "title": "Home"}]
    mock_client.get_child_pages.return_value = []

    with patch("c2m_export.tree.ConfluenceClient", return_value=mock_client):
        with pytest.raises(SystemExit) as exc_info:
            tree_cli.main()

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    # JSON stdout check
    data = json.loads(captured.out)
    assert data["schema_version"] == "1.0"
    assert data["status"] == "ok"
    assert data["roots"][0]["page_id"] == "1"


def test_tree_main_file_output_overwrite(tmp_path, monkeypatch):
    out_file = tmp_path / "tree_out.txt"
    out_file.write_text("existing content", encoding="utf-8")

    nonexistent_config = str(tmp_path / "nonexistent.yaml")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tree.py",
            "--config",
            nonexistent_config,
            "--base-url",
            "https://wiki.example.com",
            "--token",
            "tok",
            "--root-page-id",
            "100",
            "--output",
            str(out_file),
        ],
    )

    # Without --overwrite, should fail with exit 2
    with pytest.raises(SystemExit) as exc_info:
        tree_cli.main()
    assert exc_info.value.code == 2

    # With --overwrite, should succeed
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tree.py",
            "--config",
            nonexistent_config,
            "--base-url",
            "https://wiki.example.com",
            "--token",
            "tok",
            "--root-page-id",
            "100",
            "--output",
            str(out_file),
            "--overwrite",
        ],
    )

    mock_client = MagicMock()
    mock_client.get_page.return_value = {"title": "Root 100"}
    mock_client.get_child_pages.return_value = []

    with patch("c2m_export.tree.ConfluenceClient", return_value=mock_client):
        with pytest.raises(SystemExit) as exc_info:
            tree_cli.main()

    assert exc_info.value.code == 0
    assert "Root 100  [id:100]" in out_file.read_text(encoding="utf-8")

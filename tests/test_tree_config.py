import sys

import pytest

from c2m_export.config import TreeConfig


def test_tree_config_defaults(tmp_path, monkeypatch):
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
    cfg = TreeConfig()
    cfg.load()
    cfg.validate()

    assert cfg.base_url == "https://wiki.example.com"
    assert cfg.space_keys == ["TEST"]
    assert cfg.token == "tok"
    assert cfg.format == "text"
    assert cfg.include == set()
    assert cfg.ascii is False
    assert cfg.output is None
    assert cfg.overwrite is False
    assert cfg.max_depth is None


def test_tree_config_include_all(tmp_path, monkeypatch):
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
            "123",
            "--include",
            "all",
            "--format",
            "markdown",
            "--ascii",
            "--max-depth",
            "3",
        ],
    )
    cfg = TreeConfig()
    cfg.load()
    cfg.validate()

    assert cfg.format == "markdown"
    assert cfg.ascii is True
    assert cfg.max_depth == 3
    assert cfg.include == {"restriction", "macros", "attachments", "last_modified"}


def test_tree_config_validation_errors(tmp_path, monkeypatch):
    nonexistent_config = str(tmp_path / "nonexistent.yaml")

    # Missing root/space
    monkeypatch.setattr(
        sys,
        "argv",
        ["tree.py", "--config", nonexistent_config, "--base-url", "https://wiki.example.com", "--token", "tok"],
    )
    cfg = TreeConfig()
    cfg.load()
    with pytest.raises(ValueError, match="起点"):
        cfg.validate()

    # Invalid format in CLI
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
            "S",
            "--format",
            "invalid_fmt",
        ],
    )
    cfg2 = TreeConfig()
    with pytest.raises(ValueError, match="無効なコマンドライン引数"):
        cfg2.load()

    # Invalid format manually set
    cfg3 = TreeConfig()
    cfg3.base_url = "https://wiki.example.com"
    cfg3.token = "tok"
    cfg3.space_keys = ["S"]
    cfg3.format = "unknown"
    with pytest.raises(ValueError, match="出力フォーマットが無効"):
        cfg3.validate()

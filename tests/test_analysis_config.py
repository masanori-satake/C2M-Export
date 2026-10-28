import os
import sys

import pytest

from c2m_export.config import AnalysisConfig, Config


@pytest.mark.parametrize(
    "contents, position",
    [
        (b"token: 'yaml-secret-token\n", "2 行、1 列"),
        (b"token: yaml-secret-token\x00\n", None),
        (b"\xfftoken: yaml-secret-token\n", None),
    ],
)
def test_analysis_config_load_failure_keeps_contents_private(monkeypatch, capsys, tmp_path, contents, position):
    """構文・文字コードエラー時も設定内容を出さず、環境変数の読み込みを継続します。"""
    config_path = tmp_path / "invalid.yaml"
    config_path.write_bytes(contents)
    monkeypatch.setenv("C2M_CONFLUENCE_TOKEN", "env-token")

    config = AnalysisConfig()
    config.load_file_and_env(config_path)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert str(config_path) in captured.err
    assert "読み込みに失敗" in captured.err
    assert "yaml-secret-token" not in captured.err
    if position is not None:
        assert position in captured.err
    assert config.token == "env-token"


def test_analysis_config_token_env_priority(monkeypatch, tmp_path):
    monkeypatch.setenv("C2M_CONFLUENCE_TOKEN", "c2m_env_token")
    monkeypatch.setenv("CONFLUENCE_TOKEN", "legacy_env_token")
    nonexistent_config = str(tmp_path / "nonexistent.yaml")

    # CLI args without --token
    test_args = [
        "analyze",
        "--base-url",
        "https://example.com/",
        "--space-key",
        "SPACE",
        "--config",
        nonexistent_config,
    ]
    monkeypatch.setattr(sys, "argv", test_args)

    cfg = AnalysisConfig()
    cfg.load()
    assert cfg.token == "c2m_env_token"

    # Priority: C2M_CONFLUENCE_TOKEN > CONFLUENCE_TOKEN
    monkeypatch.delenv("C2M_CONFLUENCE_TOKEN")
    cfg = AnalysisConfig()
    cfg.load()
    assert cfg.token == "legacy_env_token"


def test_analysis_config_stale_years_conversion(monkeypatch, tmp_path):
    nonexistent_config = str(tmp_path / "nonexistent.yaml")
    test_args = [
        "analyze",
        "--base-url",
        "https://example.com/",
        "--space-key",
        "SPACE",
        "--stale-years",
        "2",
        "--config",
        nonexistent_config,
    ]
    monkeypatch.setattr(sys, "argv", test_args)

    cfg = AnalysisConfig()
    cfg.load()
    assert cfg.stale_days == 730


def test_analysis_config_conflict_restricted_no_restrictions(monkeypatch, tmp_path):
    nonexistent_config = str(tmp_path / "nonexistent.yaml")
    test_args = [
        "analyze",
        "--base-url",
        "https://example.com/",
        "--space-key",
        "SPACE",
        "--token",
        "dummy_token",
        "--usecase",
        "restricted",
        "--no-restrictions",
        "--config",
        nonexistent_config,
    ]
    monkeypatch.setattr(sys, "argv", test_args)

    cfg = AnalysisConfig()
    cfg.load()
    with pytest.raises(ValueError) as excinfo:
        cfg.validate()
    assert "restricted" in str(excinfo.value)
    assert "--no-restrictions" in str(excinfo.value)


def test_existing_config_token_env_resolution(monkeypatch, tmp_path):
    monkeypatch.setenv("C2M_CONFLUENCE_TOKEN", "test_env_token")
    nonexistent_config = str(tmp_path / "nonexistent.yaml")
    test_args = ["cli", "--base-url", "https://example.com/", "--root-page-id", "123", "--config", nonexistent_config]
    monkeypatch.setattr(sys, "argv", test_args)

    cfg = Config()
    cfg.load()
    assert cfg.token == "test_env_token"

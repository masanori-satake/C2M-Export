import os
import sys

import pytest

from c2m_export.config import AnalysisConfig, Config


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


def test_analysis_config_descendant_count_timeout_from_cli_and_yaml(monkeypatch, tmp_path):
    """子孫数取得専用 timeout は CLI と YAML の両方から読み込める (spec 0021)."""
    nonexistent_config = str(tmp_path / "nonexistent.yaml")
    test_args = [
        "analyze",
        "--base-url",
        "https://example.com/",
        "--space-key",
        "SPACE",
        "--config",
        nonexistent_config,
        "--descendant-count-read-timeout-seconds",
        "120",
    ]
    monkeypatch.setattr(sys, "argv", test_args)
    cfg = AnalysisConfig()
    cfg.load()
    assert cfg.descendant_count_read_timeout_seconds == 120

    config_path = tmp_path / "c2m_config.yaml"
    config_path.write_text(
        "base_url: https://example.com/\nspace_keys: [SPACE]\nanalysis:\n  descendant_count_read_timeout_seconds: 90\n",
        encoding="utf-8",
    )
    test_args = [
        "analyze",
        "--base-url",
        "https://example.com/",
        "--space-key",
        "SPACE",
        "--config",
        str(config_path),
    ]
    monkeypatch.setattr(sys, "argv", test_args)
    cfg = AnalysisConfig()
    cfg.load()
    assert cfg.descendant_count_read_timeout_seconds == 90

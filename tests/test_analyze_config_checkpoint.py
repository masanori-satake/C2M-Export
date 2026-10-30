"""AnalysisConfig および AnalysisParams のチェックポイント設定読み込みテスト."""

import sys
from unittest.mock import patch

import pytest

from c2m_export.analysis.params import AnalysisParams
from c2m_export.config import AnalysisConfig


def test_analysis_params_checkpoint_defaults_and_validation():
    """AnalysisParams のデフォルト値および checkpoint_interval バリデーションの検証."""
    params = AnalysisParams()
    assert params.checkpoint_enabled is None
    assert params.resume is None
    assert params.checkpoint_interval == 1
    assert params.checkpoint_dir == ".c2m_analyze_checkpoint"

    params.validate()  # 正常

    invalid_params = AnalysisParams(checkpoint_interval=0)
    with pytest.raises(ValueError, match="checkpoint_interval"):
        invalid_params.validate()


def test_analysis_config_checkpoint_defaults():
    """AnalysisConfig のデフォルト設定値を検証."""
    cfg = AnalysisConfig()
    assert cfg.checkpoint_enabled is True
    assert cfg.resume is False
    assert cfg.checkpoint_interval == 1
    assert cfg.checkpoint_dir == ".c2m_analyze_checkpoint"


def test_analysis_config_checkpoint_cli_args(tmp_path):
    """CLI 引数によるチェックポイント設定のオーバーライド検証."""
    nonexistent_yaml = str(tmp_path / "nonexistent.yaml")
    test_args = [
        "analyze",
        "--config",
        nonexistent_yaml,
        "--base-url",
        "https://example.com/wiki",
        "--root-page-id",
        "100",
        "--no-checkpoint",
        "--resume",
        "--checkpoint-interval",
        "5",
        "--checkpoint-dir",
        "custom_dir",
    ]

    with patch.object(sys, "argv", test_args):
        cfg = AnalysisConfig()
        cfg.load()

        assert cfg.checkpoint_enabled is False
        assert cfg.resume is True
        assert cfg.checkpoint_interval == 5
        assert cfg.checkpoint_dir == "custom_dir"


def test_analysis_config_checkpoint_yaml(tmp_path):
    """YAML 設定ファイルからのチェックポイント設定読み込み検証."""
    config_file = tmp_path / "c2m_config.yaml"
    config_file.write_text(
        """
base_url: https://example.com/wiki
root_page_ids:
  - "100"
analysis:
  checkpoint_enabled: false
  resume: true
  checkpoint_interval: 10
  checkpoint_dir: yaml_dir
""",
        encoding="utf-8",
    )

    test_args = ["analyze", "--config", str(config_file)]

    with patch.object(sys, "argv", test_args):
        cfg = AnalysisConfig()
        cfg.load()

        assert cfg.checkpoint_enabled is False
        assert cfg.resume is True
        assert cfg.checkpoint_interval == 10
        assert cfg.checkpoint_dir == "yaml_dir"

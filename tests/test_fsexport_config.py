"""FsExportConfig の単体テスト."""

from unittest.mock import patch

import pytest

from c2m_export.config import FsExportConfig


def test_fs_export_config_validation():
    cfg = FsExportConfig()
    cfg.base_url = "https://confluence.example.com/"
    cfg.root_page_ids = ["100"]
    cfg.token = "token123"

    cfg.validate()
    assert cfg.base_url == "https://confluence.example.com"


def test_fs_export_config_missing_required():
    cfg = FsExportConfig()
    cfg.base_url = "https://confluence.example.com"
    cfg.token = "token123"

    # root_page_ids と space_keys のどちらも無い場合はエラー
    with pytest.raises(ValueError, match="At least one root_page_id or space_key"):
        cfg.validate()


def test_fs_export_config_invalid_choices():
    cfg = FsExportConfig()
    cfg.base_url = "https://confluence.example.com"
    cfg.root_page_ids = ["100"]
    cfg.token = "token123"
    cfg.attachment_link_mode = "invalid_mode"

    with pytest.raises(ValueError, match="attachment_link_mode must be"):
        cfg.validate()


def test_fs_export_config_yaml_loading(tmp_path):
    yaml_content = """
base_url: "https://yaml.example.com"
token: "yaml_token"
root_page_ids: ["200", "201"]
filesystem_export:
  attachment_dir_name: "custom_atts"
  attachment_link_mode: "original"
  page_filename_mode: "index"
  single_file_max_mb: 50
  exclude_extensions: ["zip", "exe"]
  path_length_limit: 300
"""
    cfg_file = tmp_path / "c2m_config.yaml"
    cfg_file.write_text(yaml_content, encoding="utf-8")

    cfg = FsExportConfig()
    with patch("sys.argv", ["fsexport", "--config", str(cfg_file)]):
        cfg.load()
        cfg.validate()

    assert cfg.base_url == "https://yaml.example.com"
    assert cfg.token == "yaml_token"
    assert cfg.root_page_ids == ["200", "201"]
    assert cfg.attachment_dir_name == "custom_atts"
    assert cfg.attachment_link_mode == "original"
    assert cfg.page_filename_mode == "index"
    assert cfg.single_file_max_mb == 50.0
    assert cfg.exclude_extensions == ["zip", "exe"]
    assert cfg.path_length_limit == 300

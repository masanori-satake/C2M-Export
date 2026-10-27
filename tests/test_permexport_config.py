"""PermissionExportConfig のテスト."""

import os
import sys
from unittest.mock import patch

import pytest

from c2m_export.config import PermissionExportConfig


def test_permission_export_config_defaults(tmp_path):
    config = PermissionExportConfig()
    test_args = [
        "permexport",
        "--base-url",
        "https://confluence.example.com/",
        "--token",
        "testtoken",
        "--root-page-id",
        "123",
    ]
    with patch.object(sys, "argv", test_args):
        config.load()
        config.validate()

    assert config.base_url == "https://confluence.example.com"
    assert config.token == "testtoken"
    assert config.root_page_ids == ["123"]
    assert config.report_layout == "aggregate"
    assert config.report_formats == "md"
    assert config.page_filename_mode == "title"


def test_permission_export_config_file(tmp_path):
    config_file = tmp_path / "c2m_config.yaml"
    config_file.write_text(
        """
base_url: "https://confluence.yaml.com/"
token: "yamltoken"
root_page_ids:
  - "101"
  - "102"
permission_export:
  report_layout: "per_page"
  report_formats: "both"
  page_filename_mode: "index"
""",
        encoding="utf-8",
    )

    config = PermissionExportConfig()
    test_args = ["permexport", "--config", str(config_file)]
    with patch.object(sys, "argv", test_args):
        config.load()
        config.validate()

    assert config.base_url == "https://confluence.yaml.com"
    assert config.token == "yamltoken"
    assert config.root_page_ids == ["101", "102"]
    assert config.report_layout == "per_page"
    assert config.report_formats == "both"
    assert config.page_filename_mode == "index"


def test_permission_export_config_validation_errors():
    config = PermissionExportConfig()
    test_args = ["permexport", "--base-url", "https://example.com", "--token", "tok"]
    with patch.object(sys, "argv", test_args):
        config.load()
        with pytest.raises(ValueError, match="At least one root_page_id or space_key is required"):
            config.validate()

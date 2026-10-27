import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from c2m_export.config import AssessConfig


def test_assess_config_defaults():
    config = AssessConfig()
    mock_known = (MagicMock(config="non_existent.yaml"), [])

    with patch("argparse.ArgumentParser.parse_known_args", return_value=mock_known), patch(
        "argparse.ArgumentParser.parse_args"
    ) as mock_parse:
        mock_args = mock_parse.return_value
        mock_args.config = "non_existent.yaml"
        mock_args.base_url = "https://confluence.example.com/"
        mock_args.root_page_id = ["10", "20"]
        mock_args.space_key = None
        mock_args.output_dir = None
        mock_args.proxy = None
        mock_args.token = "my_token"
        mock_args.overwrite = False
        mock_args.restrictions = None
        mock_args.single_file_max_mb = None
        mock_args.path_length_limit = None
        mock_args.blocked_ext = None
        mock_args.attachment_dir = None
        mock_args.stale_days = None
        mock_args.min_body_bytes = None
        mock_args.report_format = None

        config.load()
        config.validate()

        assert config.base_url == "https://confluence.example.com"
        assert config.root_page_ids == ["10", "20"]
        assert config.analyze_restrictions is True
        assert config.single_file_max_mb == 250
        assert config.path_length_limit == 400


def test_assess_config_yaml():
    yaml_content = """
base_url: "https://yaml-host/wiki"
token: "yaml-token"
root_page_ids: [100, 200]
space_keys: ["SPACE_A"]
assessment:
  analyze_restrictions: false
  single_file_max_mb: 500
  path_length_limit: 300
  blocked_extensions: ["exe", "zip"]
"""
    with TemporaryDirectory() as tmpdir:
        cfg_file = Path(tmpdir) / "test_c2m.yaml"
        cfg_file.write_text(yaml_content, encoding="utf-8")

        config = AssessConfig()
        mock_known = (MagicMock(config=str(cfg_file)), [])

        with patch("argparse.ArgumentParser.parse_known_args", return_value=mock_known), patch(
            "argparse.ArgumentParser.parse_args"
        ) as mock_parse:
            mock_args = mock_parse.return_value
            mock_args.config = str(cfg_file)
            mock_args.base_url = None
            mock_args.root_page_id = None
            mock_args.space_key = None
            mock_args.output_dir = None
            mock_args.proxy = None
            mock_args.token = None
            mock_args.overwrite = False
            mock_args.restrictions = None
            mock_args.single_file_max_mb = None
            mock_args.path_length_limit = None
            mock_args.blocked_ext = None
            mock_args.attachment_dir = None
            mock_args.stale_days = None
            mock_args.min_body_bytes = None
            mock_args.report_format = None

            config.load()
            config.validate()

            assert config.base_url == "https://yaml-host/wiki"
            assert config.root_page_ids == ["100", "200"]
            assert config.space_keys == ["SPACE_A"]
            assert config.analyze_restrictions is False
            assert config.single_file_max_mb == 500
            assert config.path_length_limit == 300
            assert config.blocked_extensions == {"exe", "zip"}

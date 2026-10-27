from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest

from c2m_export.assess import main, resolve_roots
from c2m_export.config import AssessConfig


def test_resolve_roots():
    client = MagicMock()
    client.get_space_root_pages.return_value = [{"id": "101"}, {"id": "102"}]

    config = AssessConfig()
    config.root_page_ids = ["201"]
    config.space_keys = ["SPACE_A"]

    roots = resolve_roots(client, config)
    assert roots == ["201", "101", "102"]


def test_assess_main_execution():
    with TemporaryDirectory() as tmpdir:
        with patch("c2m_export.assess.AssessConfig") as mock_cfg_cls, patch(
            "c2m_export.assess.ConfluenceClient"
        ), patch("c2m_export.assess.Collector") as mock_collector_cls:

            mock_cfg = mock_cfg_cls.return_value
            mock_cfg.base_url = "https://confluence.example.com"
            mock_cfg.token = "dummy"
            mock_cfg.proxy = None
            mock_cfg.root_page_ids = ["1"]
            mock_cfg.space_keys = []
            mock_cfg.output_dir = tmpdir
            mock_cfg.analyze_restrictions = True
            mock_cfg.single_file_max_mb = 250
            mock_cfg.path_length_limit = 400
            mock_cfg.blocked_extensions = {"exe"}
            mock_cfg.attachment_dir_name = "_attachments"
            mock_cfg.stale_days = 365
            mock_cfg.min_body_bytes = 200
            mock_cfg.report_format = "both"
            mock_cfg.overwrite = False

            mock_collector = mock_collector_cls.return_value
            mock_inventory = MagicMock()
            mock_inventory.pages = []
            mock_inventory.skipped_page_ids = []
            mock_inventory.skipped_attachment_refs = []
            mock_inventory.restriction_failed_page_ids = []
            mock_inventory.size_meta_missing_count = 0
            mock_collector.collect.return_value = mock_inventory

            main()

            mock_collector.collect.assert_called_once_with(["1"])

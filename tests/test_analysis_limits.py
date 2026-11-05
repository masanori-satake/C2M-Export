"""--timeout-seconds および --max-pages 実行保護オプションのテストモジュール."""

import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from c2m_export.analysis.api import run_analysis
from c2m_export.analysis.params import AnalysisParams
from c2m_export.config import AnalysisConfig


class DummyConfig:
    """テスト用の最小 Config モック."""

    def __init__(self):
        self.base_url = "https://confluence.example.com"
        self.token = "dummy_token"
        self.proxy = None
        self.root_page_ids = ["100"]
        self.space_keys = []
        self.all_spaces = False
        self.cql = None
        self.deep = False
        self.collect_history = False
        self.collect_labels = False
        self.collect_comments = False
        self.collect_watchers = False
        self.collect_effective_restrictions = False
        self.collect_extracted_text = False
        self.collect_space_permissions = False
        self.checkpoint_enabled = False
        self.resume = False
        self.checkpoint_interval = 1
        self.checkpoint_dir = ".c2m_analyze_checkpoint"
        self.timeout_seconds = None
        self.max_pages = None


def _make_mock_client() -> MagicMock:
    client = MagicMock()
    client.base_url = "https://confluence.example.com"
    client.list_spaces.return_value = []
    client.get_space_root_pages.return_value = []

    def get_page_side_effect(page_id: str, **kwargs: Any) -> dict:
        return {
            "id": page_id,
            "title": f"Page_{page_id}",
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>content</p>"}},
            "version": {"when": "2026-01-01T00:00:00.000Z"},
        }

    client.get_page.side_effect = get_page_side_effect

    def get_child_pages_side_effect(page_id: str, **kwargs: Any) -> list:
        # 100 -> 101, 102; 101 -> 103, 104
        if page_id == "100":
            return [{"id": "101"}, {"id": "102"}]
        if page_id == "101":
            return [{"id": "103"}, {"id": "104"}]
        return []

    client.get_child_pages.side_effect = get_child_pages_side_effect
    client.get_attachments.return_value = []
    client.get_restrictions.return_value = {}
    return client


def test_analysis_config_limits_cli(tmp_path):
    """AnalysisConfig で --timeout-seconds と --max-pages が正しくパースされることを検証."""
    cfg = AnalysisConfig()
    nonexistent = tmp_path / "nonexistent.yaml"
    with patch.object(
        sys,
        "argv",
        [
            "prog",
            "--config",
            str(nonexistent),
            "--base-url",
            "https://confluence.example.com",
            "--token",
            "tok",
            "--root-page-id",
            "1",
            "--timeout-seconds",
            "60",
            "--max-pages",
            "50",
        ],
    ):
        cfg.load()
        cfg.validate()
        assert cfg.timeout_seconds == 60
        assert cfg.max_pages == 50


def test_analysis_params_limits_validation():
    """AnalysisParams のバリデーションで不正値（0や負数）が弾かれることを検証."""
    with pytest.raises(ValueError, match="timeout_seconds"):
        AnalysisParams(timeout_seconds=0).validate()

    with pytest.raises(ValueError, match="max_pages"):
        AnalysisParams(max_pages=-1).validate()

    # 正常値
    params = AnalysisParams(timeout_seconds=10, max_pages=10)
    params.validate()
    assert params.timeout_seconds == 10
    assert params.max_pages == 10


def test_run_analysis_max_pages_limit():
    """--max-pages に達した場合に収集を安全に中断し、partial 結果が返ることを検証."""
    config = DummyConfig()
    client = _make_mock_client()
    params = AnalysisParams(usecases=["risk", "stale"], mode="summary", max_pages=2)

    res = run_analysis(params, config, client=client)

    assert res.status == "partial"
    assert res.uncertainties.interrupted is True


def test_run_analysis_resolved_config_validation():
    """run_analysis() で config.max_pages または config.timeout_seconds の不正値が検証されることを検証."""
    config = DummyConfig()
    config.max_pages = 0
    client = _make_mock_client()
    params = AnalysisParams(usecases=["risk"])  # params.max_pages は None

    res = run_analysis(params, config, client=client)
    assert res.status == "error"
    assert "max_pages" in res.error.message

    config.max_pages = None
    config.timeout_seconds = -5
    res = run_analysis(params, config, client=client)
    assert res.status == "error"
    assert "timeout_seconds" in res.error.message


def test_collector_max_pages_resume():
    """再開時 (resume) に復元済み件数で上限判定されず、新規取得試行数で判定されることを検証."""
    from c2m_export.assessment.collector import Collector
    from c2m_export.assessment.models import PageMeta

    client = _make_mock_client()

    # 復元済みページ 2 件
    restored_page_1 = PageMeta(
        page_id="100",
        title="Page_100",
        space_key="TEST",
        level=1,
        body_bytes=10,
        last_modified="2026-01-01T00:00:00Z",
        ancestors_titles=[],
    )
    restored_page_2 = PageMeta(
        page_id="101",
        title="Page_101",
        space_key="TEST",
        level=2,
        body_bytes=10,
        last_modified="2026-01-01T00:00:00Z",
        ancestors_titles=["Page_100"],
    )

    collector = Collector(
        client=client,
        resume_collected_ids={"100", "101"},
        max_pages=2,  # 新規に 2 ページ取得可能
    )
    collector.raw_inventory.pages.extend([restored_page_1, restored_page_2])

    from c2m_export.analysis.checkpoint import CollectInterrupted

    # collect 実行: 100(復元スキップ), 101(復元スキップ), 102(新規1), 103(新規2) -> ここで上限
    with pytest.raises(CollectInterrupted, match="最大ページ数上限"):
        collector.collect(["100"])

    # 復元済み 2 件 + 新規 2 件 = 計 4 件
    assert len(collector.raw_inventory.pages) == 4


def test_analysis_config_invalid_yaml_types(tmp_path):
    """AnalysisConfig で YAML 内の timeout_seconds/max_pages が文字列等の場合に validate() で正しく検出されることを検証."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(
        """
base_url: "https://confluence.example.com"
token: "dummy"
root_page_ids: ["123"]
analysis:
  timeout_seconds: "invalid_str"
  max_pages: "invalid_str"
""",
        encoding="utf-8",
    )
    cfg = AnalysisConfig()
    with patch.object(sys, "argv", ["prog", "--config", str(config_file)]):
        cfg.load()
        with pytest.raises(ValueError, match="timeout_seconds"):
            cfg.validate()


def test_run_analysis_timeout_seconds_limit():
    """--timeout-seconds に達した場合に収集を安全に中断し、partial 結果が返ることを検証."""
    config = DummyConfig()
    client = _make_mock_client()

    # 意図的に 1 秒未満でタイムアウトする設定
    params = AnalysisParams(usecases=["risk"], mode="summary", timeout_seconds=1)

    import time

    orig_get_page = client.get_page.side_effect

    def slow_get_page(page_id: str, **kwargs: Any) -> dict:
        time.sleep(0.6)  # 2ページ目で 1.2秒経過しタイムアウト
        return orig_get_page(page_id, **kwargs)

    client.get_page.side_effect = slow_get_page

    res = run_analysis(params, config, client=client)

    assert res.status == "partial"
    assert res.uncertainties.interrupted is True

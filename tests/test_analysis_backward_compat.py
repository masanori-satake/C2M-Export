"""
既存 CLI および設定クラスの後方互換性・非破壊検証テスト (test_analysis_backward_compat.py)
"""

from unittest.mock import MagicMock

from c2m_export.assessment.collector import Collector
from c2m_export.assessment.models import PageMeta
from c2m_export.config import AssessConfig, Config, FsExportConfig, PermissionExportConfig


def test_collector_default_no_macros():
    """Collector の既定動作 (collect_macros=False) でマクロ収集が走らず後方互換が保たれることを検証します。"""
    mock_client = MagicMock()
    mock_client.get_page.return_value = {
        "id": "100",
        "title": "テストページ",
        "body": {"storage": {"value": "<p><ac:structured-macro ac:name='toc'/></p>"}},
        "version": {"when": "2026-01-01T00:00:00.000Z"},
    }
    mock_client.get_attachments.return_value = []
    mock_client.get_child_pages.return_value = []
    mock_client.get_restrictions.return_value = {}

    collector = Collector(client=mock_client)  # collect_macros 未指定 (既定 False)
    inventory = collector.collect(root_ids=["100"])

    assert len(inventory.pages) == 1
    page = inventory.pages[0]
    assert isinstance(page, PageMeta)
    assert page.macro_counts == {}  # マクロ収集されていないこと


def test_assess_config_env_token_backward_compat(monkeypatch, tmp_path):
    """AssessConfig が環境変数からトークンを取得しつつ、既存の優先順位と Proxy 設定を保つことを検証します。"""
    monkeypatch.setenv("C2M_CONFLUENCE_TOKEN", "env-secret-token")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example.com:8080")

    dummy_config = tmp_path / "nonexistent.yaml"
    config = AssessConfig()
    monkeypatch.setattr("sys.argv", ["assess.py", "--config", str(dummy_config)])
    config.load()

    assert config.token == "env-secret-token"
    assert config.proxy == "http://proxy.example.com:8080"


def test_existing_configs_default_attributes():
    """既存の Config クラスの初期値が想定通りであることを検証します。"""
    cfg = Config()
    assert cfg.token is None
    assert cfg.overwrite is False

    fscfg = FsExportConfig()
    assert fscfg.sync is False
    assert fscfg.resume is False

    permcfg = PermissionExportConfig()
    assert permcfg.report_layout == "aggregate"

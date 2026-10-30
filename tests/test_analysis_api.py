from unittest.mock import MagicMock

import pytest

from c2m_export.analysis.api import run_analysis
from c2m_export.analysis.params import AnalysisParams
from c2m_export.config import AnalysisConfig


def test_run_analysis_success():
    client = MagicMock()
    client.get_page.return_value = {
        "title": "Page 1",
        "space": {"key": "SPACE"},
        "version": {"when": "2026-01-01T00:00:00Z"},
        "body": {"storage": {"value": '<ac:structured-macro ac:name="toc"/>'}},
    }
    client.get_attachments.return_value = []
    client.get_restrictions.return_value = {}
    client.get_child_pages.return_value = []

    cfg = AnalysisConfig()
    cfg.base_url = "https://example.com/wiki"
    cfg.root_page_ids = ["100"]

    params = AnalysisParams(usecases=["risk", "macros"], mode="summary")

    resp = run_analysis(params, cfg, client)

    assert resp.status == "ok"
    assert resp.schema_version == "1.2"
    assert "risk" in resp.usecases
    assert "macros" in resp.usecases
    assert resp.scope.resolved_root_count == 1


def test_run_analysis_target_not_found():
    client = MagicMock()
    import requests

    response = MagicMock()
    response.status_code = 404
    client.get_page.side_effect = requests.exceptions.HTTPError(response=response)

    cfg = AnalysisConfig()
    cfg.base_url = "https://example.com/wiki"
    cfg.root_page_ids = ["99999"]

    params = AnalysisParams()

    resp = run_analysis(params, cfg, client)

    assert resp.status == "error"
    assert resp.error is not None
    assert resp.error.code == "TARGET_NOT_FOUND"


@pytest.mark.parametrize(
    ("options", "expected_risks"),
    [
        ({}, {"BLOCKED_EXT": 1}),
        ({"single_file_max_mb": 100}, {"BLOCKED_EXT": 1, "LARGE_FILE": 1}),
        ({"path_length_limit": 250}, {"BLOCKED_EXT": 1, "PATH_LENGTH": 2}),
        ({"blocked_extensions": set()}, {}),
        ({"blocked_extensions": None}, {"BLOCKED_EXT": 1}),
        ({"attachment_dir_name": "assets" * 20}, {"BLOCKED_EXT": 1, "PATH_LENGTH": 1}),
    ],
)
def test_run_analysis_assessment_options(options, expected_risks):
    client = MagicMock()
    client.get_page.side_effect = lambda page_id, **kwargs: {
        "title": "a" * (100 if page_id == "100" else 200),
        "space": {"key": "SPACE"},
    }
    client.get_attachments.side_effect = lambda page_id: (
        [] if page_id == "100" else [{"title": "setup.exe", "extensions": {"fileSize": 150 * 1024 * 1024}}]
    )
    client.get_restrictions.return_value = {}
    client.get_child_pages.side_effect = lambda page_id: [{"id": "101"}] if page_id == "100" else []

    cfg = AnalysisConfig()
    cfg.base_url = "https://example.com/wiki"
    cfg.root_page_ids = ["100"]
    for name, value in options.items():
        setattr(cfg, name, value)

    resp = run_analysis(AnalysisParams(usecases=["risk"]), cfg, client)

    assert resp.status == "ok"
    assert resp.usecases["risk"]["counts"]["risk_summary"] == expected_risks


def test_cql_filters_type_page_only():
    """CQL 検索結果において type が page のコンテンツのみが起点に採用されることを検証."""
    client = MagicMock()
    client.search_cql.return_value = [
        {"id": "100", "type": "page"},
        {"id": "200", "type": "blogpost"},
        {"id": "300", "type": "comment"},
        {"id": "101", "type": "page"},
    ]
    client.get_page.side_effect = lambda pid, **kwargs: {
        "title": f"Page {pid}",
        "space": {"key": "SPACE"},
    }
    client.get_attachments.return_value = []
    client.get_restrictions.return_value = {}
    client.get_child_pages.return_value = []

    cfg = AnalysisConfig()
    cfg.base_url = "https://example.com/wiki"
    cfg.cql = "title ~ 'test'"

    params = AnalysisParams(cql="title ~ 'test'")
    resp = run_analysis(params, cfg, client)

    assert resp.status == "ok"
    assert resp.scope.resolved_root_count == 2
    # get_page が呼び出されたのは page タイプの 100 と 101 のみであることを検証
    called_pids = [call.args[0] for call in client.get_page.call_args_list]
    assert "100" in called_pids
    assert "101" in called_pids
    assert "200" not in called_pids
    assert "300" not in called_pids


def test_all_spaces_true_list_spaces_error_returns_error_response():
    """all_spaces=True かつ list_spaces 失敗時に構造化された error 応答が返ることを検証."""
    client = MagicMock()
    client.list_spaces.side_effect = Exception("Confluence API Connection Failed")

    cfg = AnalysisConfig()
    cfg.base_url = "https://example.com/wiki"

    params = AnalysisParams(all_spaces=True)
    resp = run_analysis(params, cfg, client)

    assert resp.status == "error"
    assert resp.error is not None
    assert resp.error.code == "API_ERROR"
    assert "全 Space 一覧の取得に失敗しました" in resp.error.message


def test_all_spaces_false_list_spaces_error_continues_with_explicit_roots():
    """all_spaces=False の場合は list_spaces 失敗でも既存通り明示ルートで分析が継続することを検証."""
    client = MagicMock()
    client.list_spaces.side_effect = Exception("Confluence API Connection Failed")
    client.get_page.return_value = {
        "title": "Page 100",
        "space": {"key": "SPACE"},
    }
    client.get_attachments.return_value = []
    client.get_restrictions.return_value = {}
    client.get_child_pages.return_value = []

    cfg = AnalysisConfig()
    cfg.base_url = "https://example.com/wiki"
    cfg.root_page_ids = ["100"]

    params = AnalysisParams(all_spaces=False)
    resp = run_analysis(params, cfg, client)

    assert resp.status == "ok"
    assert resp.scope.resolved_root_count == 1

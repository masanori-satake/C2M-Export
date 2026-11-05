"""事前見積もりモード (spec 0012) の単体テスト."""

from unittest.mock import MagicMock

import requests

from c2m_export.analysis.estimate import estimate_analysis
from c2m_export.analysis.params import AnalysisParams
from c2m_export.analysis.response import AnalysisResponse
from c2m_export.config import AnalysisConfig


def _make_config():
    cfg = AnalysisConfig()
    cfg.base_url = "https://example.com/wiki"
    cfg.token = "test-token"
    cfg.root_page_ids = ["100"]
    return cfg


def _make_client(descendant_count=9):
    client = MagicMock()
    client.list_spaces.return_value = [{"key": "DEV"}]
    client.get_page.return_value = {"id": "100", "title": "Root"}
    client.get_descendant_page_count.return_value = {"count": descendant_count}
    return client


def test_estimate_counts_pages_and_requests():
    """対象ページ数と想定リクエスト数が収集モデルどおり算出される."""
    resp = estimate_analysis(AnalysisParams(), _make_config(), _make_client())
    assert resp.status == "ok"
    est = resp.estimate
    assert est is not None
    assert est["target_pages"] == 10  # 起点 1 + 子孫 9
    assert est["effective_pages"] == 10
    assert est["per_root"] == [{"root_page_id": "100", "descendant_count": 9, "total_pages": 10}]
    # 既定: 基本3件 + 制限取得1件 = 4件/ページ、固定 = 5 + Space 1件×2 = 7
    assert est["requests_per_page"] == 4
    assert est["fixed_requests"] == 7
    assert est["estimated_requests"] == 7 + 10 * 4
    assert est["measured_calls"] >= 3  # list_spaces / get_page / descendant count
    assert est["is_large"] is False
    assert est["exceeds_skill_default_timeout"] is False
    assert resp.scope.resolved_root_count == 1


def test_estimate_respects_max_pages():
    """max_pages 指定時は有効ページ数が上限で丸められる."""
    params = AnalysisParams(max_pages=5)
    resp = estimate_analysis(params, _make_config(), _make_client())
    est = resp.estimate
    assert est["target_pages"] == 10
    assert est["effective_pages"] == 5
    assert est["estimated_requests"] == 7 + 5 * 4


def test_estimate_deep_increases_requests_per_page():
    """deep 有効時は収集フラグ分だけ 1ページあたり件数が増える."""
    params = AnalysisParams(deep=True)
    resp = estimate_analysis(params, _make_config(), _make_client())
    est = resp.estimate
    # 基本3 + 制限1 + history/labels/comments/watchers/effective 5 = 9
    assert est["requests_per_page"] == 9
    assert est["estimated_requests"] == est["fixed_requests"] + 10 * 9


def test_estimate_count_failure_is_reported():
    """子孫数の取得失敗は起点を明示し、起点ページのみとして数える."""
    client = _make_client()
    client.get_descendant_page_count.side_effect = RuntimeError("boom")
    resp = estimate_analysis(AnalysisParams(), _make_config(), client)
    est = resp.estimate
    assert resp.status == "ok"
    assert est["count_failed_root_page_ids"] == ["100"]
    assert est["target_pages"] == 1


def test_estimate_target_not_found():
    """起点ページが存在しない場合は本実行と同じエラー分類になる."""
    client = _make_client()
    response = MagicMock()
    response.status_code = 404
    client.get_page.side_effect = requests.exceptions.HTTPError(response=response)
    resp = estimate_analysis(AnalysisParams(), _make_config(), client)
    assert resp.status == "error"
    assert resp.error is not None
    assert resp.error.code == "TARGET_NOT_FOUND"


def test_normal_response_omits_estimate_field():
    """通常実行のレスポンス JSON には estimate キーが含まれない（後方互換）."""
    assert "estimate" not in AnalysisResponse().to_dict()
    resp = estimate_analysis(AnalysisParams(), _make_config(), _make_client())
    assert "estimate" in resp.to_dict()

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
    assert resp.schema_version == "1.0"
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

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from c2m_export.analysis.response import AnalysisResponse, Uncertainties
from c2m_export.analyze import main


def test_analyze_cli_no_checkpoint_and_params(monkeypatch, capsys, tmp_path):
    """--no-checkpoint, --resume, --checkpoint-interval, --checkpoint-dir パラメータの CLI 伝播を検証."""
    nonexistent_config = str(tmp_path / "nonexistent.yaml")
    chk_dir = str(tmp_path / "custom_chk")
    test_args = [
        "analyze",
        "--base-url",
        "https://example.com/wiki",
        "--root-page-id",
        "100",
        "--token",
        "secret_token_123",
        "--no-checkpoint",
        "--resume",
        "--checkpoint-interval",
        "5",
        "--checkpoint-dir",
        chk_dir,
        "--config",
        nonexistent_config,
    ]
    monkeypatch.setattr(sys, "argv", test_args)

    mock_client = MagicMock()
    mock_client.get_page.return_value = {
        "title": "Test Title",
        "space": {"key": "TEST"},
        "version": {"when": "2026-01-01T00:00:00Z"},
        "body": {"storage": {"value": "Test body"}},
    }
    mock_client.get_attachments.return_value = []
    mock_client.get_restrictions.return_value = {}
    mock_client.get_child_pages.return_value = []

    captured_params = []

    def dummy_run_analysis(params, config, client=None, interrupt_checker=None):
        captured_params.append(params)
        resp = AnalysisResponse(schema_version="1.2", status="ok")
        return resp

    with patch("c2m_export.analyze.run_analysis", side_effect=dummy_run_analysis):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    assert len(captured_params) == 1
    p = captured_params[0]
    assert p.checkpoint_enabled is False
    assert p.resume is True
    assert p.checkpoint_interval == 5
    assert p.checkpoint_dir == chk_dir


def test_analyze_cli_partial_exit_code_6(monkeypatch, capsys, tmp_path):
    """status == 'partial' の場合に終了コード 6 と stderr 案内が出力されることを検証."""
    nonexistent_config = str(tmp_path / "nonexistent.yaml")
    test_args = [
        "analyze",
        "--base-url",
        "https://example.com/wiki",
        "--root-page-id",
        "100",
        "--token",
        "secret_token_123",
        "--config",
        nonexistent_config,
    ]
    monkeypatch.setattr(sys, "argv", test_args)

    partial_resp = AnalysisResponse(
        schema_version="1.2",
        status="partial",
        uncertainties=Uncertainties(interrupted=True, interrupted_reason="signal", collected_page_count=10),
    )

    with patch("c2m_export.analyze.run_analysis", return_value=partial_resp):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 6

    captured = capsys.readouterr()
    out_json = json.loads(captured.out)
    assert out_json["status"] == "partial"
    assert out_json["uncertainties"]["interrupted"] is True
    assert "partial" in captured.err
    assert "--resume" in captured.err

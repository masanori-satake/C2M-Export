import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from c2m_export.analyze import main


def test_analyze_cli_success(monkeypatch, capsys, tmp_path):
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

    with patch("c2m_export.analysis.api.ConfluenceClient", return_value=mock_client):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    captured = capsys.readouterr()
    # stdout MUST be valid JSON
    out_json = json.loads(captured.out)
    assert out_json["status"] == "ok"
    assert "secret_token_123" not in captured.out
    assert "secret_token_123" not in captured.err


def test_analyze_cli_invalid_param(monkeypatch, capsys, tmp_path):
    nonexistent_config = str(tmp_path / "nonexistent.yaml")
    # Missing base_url
    test_args = [
        "analyze",
        "--root-page-id",
        "100",
        "--token",
        "secret_token_123",
        "--config",
        nonexistent_config,
    ]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 2

    captured = capsys.readouterr()
    out_json = json.loads(captured.out)
    assert out_json["schema_version"] == "1.1"
    assert out_json["status"] == "error"
    assert out_json["error"]["code"] == "INVALID_PARAM"
    assert "secret_token_123" not in captured.out
    assert "secret_token_123" not in captured.err

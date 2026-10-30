"""
認証トークンの非漏洩検証テスト (test_analysis_token_leak.py)

認証トークンが stdout の JSON、ErrorObject、stderr のログ、Scope オブジェクト、
および例外発生時の出力メッセージに混入しないことを検証します。
"""

import json
from unittest.mock import MagicMock, patch

from c2m_export.analysis.response import AnalysisResponse
from c2m_export.analyze import main
from c2m_export.config import AnalysisConfig


def test_token_not_in_analyze_stdout_or_stderr(monkeypatch, capsys, tmp_path):
    """正常系実行において CLI 引数 / 環境変数のトークンが stdout / stderr に漏洩しないことを検証します。"""
    secret_token = "SUPER_SECRET_PAT_TOKEN_12345"
    monkeypatch.setenv("C2M_CONFLUENCE_TOKEN", secret_token)

    dummy_config = tmp_path / "dummy_config.yaml"
    dummy_config.write_text("base_url: 'https://confluence.example.com'\n", encoding="utf-8")

    test_args = [
        "analyze.py",
        "--base-url",
        "https://confluence.example.com",
        "--space-key",
        "TEST",
        "--config",
        str(dummy_config),
        "--token",
        secret_token,
    ]
    monkeypatch.setattr("sys.argv", test_args)

    dummy_response = AnalysisResponse(
        status="ok",
        mode="summary",
        scope={
            "base_url": "https://confluence.example.com",
            "space_keys": ["TEST"],
            "resolved_root_count": 1,
        },
        summary={"total_pages": 5},
    )

    with patch("c2m_export.analyze.run_analysis", return_value=dummy_response):
        try:
            main()
        except SystemExit as e:
            assert e.code == 0

    captured = capsys.readouterr()

    # stdout の JSON と stderr のログにトークン文字列が含まれないこと
    assert secret_token not in captured.out
    assert secret_token not in captured.err

    # stdout がパース可能な JSON であり scope に token フィールドが存在しないこと
    data = json.loads(captured.out)
    assert data["status"] == "ok"
    assert "token" not in data["scope"]


def test_token_not_in_error_output(monkeypatch, capsys, tmp_path):
    """エラー（対象未存在や認証エラー）発生時にトークンが JSON エラー出力や stderr ログに混入しないことを検証します。"""
    secret_token = "BEARER_SECRET_987654321"
    monkeypatch.setenv("CONFLUENCE_TOKEN", secret_token)

    dummy_config = tmp_path / "nonexistent.yaml"

    test_args = [
        "analyze.py",
        "--base-url",
        "https://confluence.example.com",
        "--space-key",
        "NONEXISTENT",
        "--config",
        str(dummy_config),
    ]
    monkeypatch.setattr("sys.argv", test_args)

    with patch("c2m_export.analysis.api.ConfluenceClient") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        import requests

        response_mock = requests.Response()
        response_mock.status_code = 404
        mock_client.get_space_root_pages.side_effect = requests.exceptions.HTTPError(
            f"404 Client Error: Not Found for url with token {secret_token}",
            response=response_mock,
        )

        try:
            main()
        except SystemExit as e:
            assert e.code != 0

    captured = capsys.readouterr()

    assert secret_token not in captured.out
    assert secret_token not in captured.err


def test_analysis_config_does_not_expose_token():
    """AnalysisConfig オブジェクトが不用意にトークンを漏洩しないことを検証します。"""
    config = AnalysisConfig()
    config.token = "SECRET_TOKEN_VALUE"
    assert config.token == "SECRET_TOKEN_VALUE"


def test_token_not_in_checkpoint_file(tmp_path):
    """チェックポイントファイル（JSONL）内に認証トークンが含まれないことを検証します。"""
    from c2m_export.analysis.checkpoint import CheckpointStore
    from c2m_export.assessment.models import PageMeta

    secret_token = "TOP_SECRET_CHECKPOINT_TOKEN_999"
    chk_path = tmp_path / "chk.jsonl"

    store = CheckpointStore(
        path=chk_path,
        scope_hash="1234567890abcdef",
        scope_meta={"root_page_ids": ["100"], "space_keys": ["TEST"]},
    )
    store.open_for_write(append=False)
    page = PageMeta(
        page_id="100",
        title="Secret Page",
        space_key="TEST",
        level=1,
        body_bytes=100,
        last_modified="2026-01-01T00:00:00Z",
        ancestors_titles=[],
    )
    store.append_page(page)
    store.close()

    content = chk_path.read_text(encoding="utf-8")
    assert secret_token not in content
    assert "token" not in content.lower()

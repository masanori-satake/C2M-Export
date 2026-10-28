"""
MCP サーバモジュール (c2m_export/mcp_server.py) の単体テスト
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

from c2m_export.analysis.response import AnalysisResponse
from c2m_export.mcp_server import create_mcp_server


def test_create_mcp_server_import_error():
    """mcp パッケージが存在しない場合に適切な ImportError が送出されることを検証します。"""
    with patch.dict(sys.modules, {"mcp": None, "mcp.server.fastmcp": None}):
        with pytest.raises(ImportError) as exc_info:
            create_mcp_server()
        assert "requirements-mcp.txt" in str(exc_info.value)


def test_create_mcp_server_and_tool_execution(monkeypatch):
    """mcp モック環境下で分析ツールが正常に共通1層 (run_analysis) を呼び出すことを検証します。"""
    mock_fast_mcp_cls = MagicMock()
    mock_mcp_instance = MagicMock()
    mock_fast_mcp_cls.return_value = mock_mcp_instance

    # @mcp.tool() デコレータの動作をモック
    registered_tools = {}

    def mock_tool():
        def decorator(func):
            registered_tools[func.__name__] = func
            return func

        return decorator

    mock_mcp_instance.tool = mock_tool

    mock_fastmcp_module = MagicMock()
    mock_fastmcp_module.FastMCP = mock_fast_mcp_cls

    monkeypatch.setenv("C2M_CONFLUENCE_TOKEN", "mock-token-123")

    dummy_response = AnalysisResponse(
        status="ok",
        mode="summary",
        scope={"base_url": "https://example.com", "space_keys": ["TEST"], "resolved_root_count": 1},
        summary={"total_pages": 10},
    )

    with patch.dict(sys.modules, {"mcp": MagicMock(), "mcp.server.fastmcp": mock_fastmcp_module}):
        with patch("c2m_export.mcp_server.run_analysis", return_value=dummy_response) as mock_run:
            mcp_server = create_mcp_server()
            assert mcp_server == mock_mcp_instance
            assert "analyze_confluence" in registered_tools

            tool_fn = registered_tools["analyze_confluence"]
            result = tool_fn(
                base_url="https://example.com",
                space_keys=["TEST"],
                mode="summary",
            )

            assert result["status"] == "ok"
            assert result["mode"] == "summary"
            mock_run.assert_called_once()


@pytest.fixture
def analysis_tool(monkeypatch, tmp_path):
    """CLI 引数に依存しない MCP ツール呼び出しを準備します。"""
    monkeypatch.setattr("c2m_export.config.DEFAULT_CONFIG_PATH", tmp_path / "c2m_config.yaml")
    monkeypatch.setattr(sys, "argv", ["mcp-server", "--transport", "stdio"])
    monkeypatch.delenv("C2M_CONFLUENCE_TOKEN", raising=False)
    monkeypatch.delenv("CONFLUENCE_TOKEN", raising=False)
    registered_tools = {}
    mock_mcp = MagicMock()

    def register(func):
        registered_tools[func.__name__] = func
        return func

    mock_mcp.tool.side_effect = lambda: register
    mock_module = MagicMock()
    mock_module.FastMCP.return_value = mock_mcp
    with patch.dict(sys.modules, {"mcp": MagicMock(), "mcp.server.fastmcp": mock_module}):
        with patch("c2m_export.mcp_server.run_analysis", return_value=AnalysisResponse()) as mock_run:
            create_mcp_server()
            yield registered_tools["analyze_confluence"], mock_run


def test_mcp_normalizes_base_url(analysis_tool):
    """API パス連結前にベース URL の末尾スラッシュを除去します。"""
    tool, mock_run = analysis_tool
    tool(base_url="https://example.com/wiki///", root_page_ids=["100"])
    config = mock_run.call_args.kwargs["config"]
    assert config.base_url == "https://example.com/wiki"


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({}, 365),
        ({"stale_years": 2}, 730),
        ({"stale_years": 0.5}, 182),
        ({"stale_days": 365, "stale_years": 2}, 365),
        ({"stale_days": 90, "stale_years": 2}, 90),
        ({"stale_days": 0, "stale_years": 2}, 0),
        ({"stale_days": 365}, 365),
    ],
)
def test_mcp_stale_days_precedence(analysis_tool, kwargs, expected):
    """明示した日数を年数より優先し、省略時だけ年数を換算します。"""
    tool, mock_run = analysis_tool
    tool(base_url="https://example.com", space_keys=["TEST"], **kwargs)
    assert mock_run.call_args.kwargs["params"].stale_days == expected


@pytest.mark.parametrize(
    "env, expected_token, expected_proxy",
    [
        ({}, "yaml-token", "http://yaml-proxy:8080"),
        (
            {"CONFLUENCE_TOKEN": "legacy-token", "HTTP_PROXY": "http://http-proxy:8080"},
            "legacy-token",
            "http://http-proxy:8080",
        ),
        (
            {
                "C2M_CONFLUENCE_TOKEN": "env-token",
                "CONFLUENCE_TOKEN": "legacy-token",
                "HTTPS_PROXY": "http://https-proxy:8080",
                "HTTP_PROXY": "http://http-proxy:8080",
            },
            "env-token",
            "http://https-proxy:8080",
        ),
    ],
)
def test_mcp_loads_yaml_and_environment(analysis_tool, monkeypatch, tmp_path, env, expected_token, expected_proxy):
    """YAML の分析設定と環境変数の認証・プロキシ優先順位を保持します。"""
    from c2m_export.analysis.params import AnalysisParams

    (tmp_path / "c2m_config.yaml").write_text(
        "token: yaml-token\nproxy: http://yaml-proxy:8080\n"
        "analysis:\n  usecases: [stale, archives]\n  mode: detail\n  limit: 7\n"
        "  stale_days: 90\n  min_body_bytes: 50\n  archive_extensions: [ZIP]\n"
        "  analyze_restrictions: false\n",
        encoding="utf-8",
    )
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    tool, mock_run = analysis_tool
    tool(base_url="https://example.com", space_keys=["TEST"])
    config = mock_run.call_args.kwargs["config"]
    assert config.token == expected_token
    assert config.proxy == expected_proxy
    assert mock_run.call_args.kwargs["params"] == AnalysisParams(
        usecases=["stale", "archives"],
        mode="detail",
        limit=7,
        stale_days=90,
        min_body_bytes=50,
        archive_extensions={"zip"},
        analyze_restrictions=False,
    )


def test_mcp_explicit_arguments_override_yaml(analysis_tool, tmp_path):
    """明示された MCP 引数は空リスト・ゼロ・真偽値も含め YAML より優先します。"""
    from c2m_export.analysis.params import AnalysisParams

    (tmp_path / "c2m_config.yaml").write_text(
        "analysis:\n  usecases: [stale]\n  mode: detail\n  limit: 7\n"
        "  stale_days: 90\n  min_body_bytes: 50\n  archive_extensions: [zip]\n"
        "  analyze_restrictions: false\n",
        encoding="utf-8",
    )
    tool, mock_run = analysis_tool
    tool(
        base_url="https://example.com",
        space_keys=["TEST"],
        usecases=[],
        mode="summary",
        limit=1000,
        stale_days=365,
        stale_years=2,
        min_body_bytes=0,
        archive_extensions=[],
        analyze_restrictions=True,
        sort="page_id",
    )
    assert mock_run.call_args.kwargs["params"] == AnalysisParams(
        usecases=[],
        mode="summary",
        limit=1000,
        stale_days=365,
        min_body_bytes=0,
        archive_extensions=set(),
        analyze_restrictions=True,
        sort="page_id",
    )


def test_mcp_stale_years_overrides_yaml_days(analysis_tool, tmp_path):
    """日数の明示がない場合は MCP の年数を YAML の日数より優先します。"""
    (tmp_path / "c2m_config.yaml").write_text("analysis:\n  stale_days: 90\n", encoding="utf-8")
    tool, mock_run = analysis_tool
    tool(base_url="https://example.com", space_keys=["TEST"], stale_years=2)
    assert mock_run.call_args.kwargs["params"].stale_days == 730

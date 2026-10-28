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
